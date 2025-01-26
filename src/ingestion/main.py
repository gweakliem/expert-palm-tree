import asyncio
import json
import logging
from datetime import datetime, timezone
import websockets
from sqlalchemy import create_engine, text
from typing import Optional
from dataclasses import dataclass, field
from shared.config import settings
import os
from uuid import uuid4


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Database configuration
engine = create_engine(settings.database_url)

# load settings
batch_size = settings.batch_size
flush_interval = settings.flush_interval_seconds
base_uri = settings.jetstream_uri
logger.info(f"CurDir: {os.getcwd()}")
logger.info(settings.model_dump())


@dataclass
class IngestionState:
    cursor: Optional[str] = None
    last_flush: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    buffer: list = None

    def __post_init__(self):
        self.buffer = []


async def get_last_cursor() -> Optional[str]:
    """Retrieve the cursor of the most recently stored record"""
    query = text(
        """
        SELECT cursor
        FROM posts
        WHERE cursor IS NOT NULL
        ORDER BY cursor DESC
        LIMIT 1
    """
    )
    with engine.connect() as conn:
        result = conn.execute(query).first()
        return result[0] if result else None


async def process_commit(did: str, op, cursor: str):
    """Extract post data from an operation"""
    record = op.get("record", {})
    # Handle the case where createdAt might be None or empty
    created_at_str = record.get("createdAt", "")
    if created_at_str:
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
    else:
        created_at = datetime.now(timezone.utc)  # fallback to current time if missing

    return {
        "id": uuid4(),
        "did": did,
        "commit_rev": op.get("rev"),
        "commit_operation": op.get("operation"),
        "commit_collection": op.get("collection"),
        "commit_rkey": op.get("rkey"),
        "commit_cid": op.get("cid"),
        "created_at": created_at,
        "langs": record.get("langs", []),
        "reply_parent_cid": record.get("reply", {}).get("parent", {}).get("cid"),
        "reply_parent_uri": record.get("reply", {}).get("parent", {}).get("uri"),
        "reply_root_cid": record.get("reply", {}).get("root", {}).get("cid"),
        "reply_root_uri": record.get("reply", {}).get("root", {}).get("uri"),
        "record_text": record.get("text", ""),
        "ingest_time": datetime.now(timezone.utc),
        "cursor": cursor,  # Store the cursor with each record
    }


async def store_posts(posts, engine):
    """Store multiple posts in the database"""
    if not posts:
        return

    insert_stmt = text(
        """
        INSERT INTO posts (
            id, did, commit_rev, commit_operation, 
            commit_collection, commit_rkey, commit_cid,
            created_at, langs, reply_parent_cid,
            reply_parent_uri, reply_root_cid, reply_root_uri,
            record_text, ingest_time, cursor
        )
        VALUES (
            :id, :did, :commit_rev, :commit_operation,
            :commit_collection, :commit_rkey, :commit_cid,
            :created_at, :langs, :reply_parent_cid,
            :reply_parent_uri, :reply_root_cid, :reply_root_uri,
            :record_text, :ingest_time, :cursor
        )
        ON CONFLICT (id) DO NOTHING
    """
    )

    with engine.begin() as conn:
        for post in posts:
            try:
                conn.execute(insert_stmt, post)
            except Exception as e:
                logger.error(f"Error inserting post {post['id']}: {e}")


async def process_message(message, state: IngestionState):
    """Process a message from the firehose"""
    try:
        data = json.loads(message)

        # Update cursor from message
        cursor = data.get("time_us")
        if cursor is None:
            logger.warn("no cursor in %s", data)
            return

        state.cursor = str(cursor)

        if data.get("kind") != "commit":
            # for now we're interested in posts only
            # we also see things like identity and account, account has interesting account.status like deleted and takendown
            return

        if "commit" not in data:
            logger.warn("no commit %s", data)
            return

        # if data.get("commit", {}).get("record", {}).get("text", "") == "":
        #     logger.info("empty text %s", data)

        post_data = await process_commit(
            data.get("did"), data.get("commit"), state.cursor
        )
        if post_data:
            state.buffer.append(post_data)

    except json.JSONDecodeError:
        logger.error("Failed to decode message")
    except Exception as e:
        logger.error(f"Error processing message: {e}")


async def run_ingestion():
    """Main ingestion loop"""
    # Initialize state
    state = IngestionState()
    state.cursor = await get_last_cursor()

    logger.info(
        f"Initializing with batch size {batch_size} and flushing every {flush_interval} seconds"
    )

    # Construct initial URI
    uri = f"{base_uri}?wantedCollections=app.bsky.feed.post"
    if state.cursor:
        uri = f"{uri}&cursor={state.cursor}"
        logger.info(f"Resuming from cursor: {state.cursor}")
    else:
        logger.info("Starting from beginning of stream")

    while True:
        try:
            async with websockets.connect(uri) as websocket:
                logger.info("Connected to Bluesky firehose")

                while True:
                    message = await websocket.recv()
                    await process_message(message, state)

                    # Flush buffer if it's big enough or enough time has passed
                    now = datetime.now(timezone.utc)
                    elapsed = (now - state.last_flush).total_seconds()
                    if len(state.buffer) >= batch_size or elapsed >= flush_interval:
                        logger.info(
                            f"Flushing {len(state.buffer)} posts after {elapsed} seconds"
                        )
                        await store_posts(state.buffer, engine)
                        state.buffer = []
                        state.last_flush = now

        except websockets.exceptions.ConnectionClosed:
            logger.warning("Connection closed, attempting to reconnect...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Error in ingestion loop: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    with engine.begin() as conn:
        conn.execute(
            text(
                """
            ALTER TABLE posts 
            ADD COLUMN IF NOT EXISTS cursor TEXT;
            
            CREATE INDEX IF NOT EXISTS idx_posts_cursor 
            ON posts(cursor DESC NULLS LAST);
        """
            )
        )

    try:
        asyncio.run(run_ingestion())
    except asyncio.exceptions.CancelledError:
        logger.info("Cancelled, stopping...")
