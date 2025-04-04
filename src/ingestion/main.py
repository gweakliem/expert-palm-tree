import asyncio
import json
import logging
from datetime import datetime, timezone
import websockets
from sqlalchemy import create_engine, text
from typing import Optional
from dataclasses import dataclass, field
from shared.config import settings
from uuid import uuid4
import os


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
    if len(record.keys()) == 0:
        logger.info("empty record %s", op)
        return
    # Handle the case where createdAt might be None or empty
    # TODO: some of these dates are clearly BS, 1970-01-01 00:00:00 for example (obv unix 0 time)
    created_at_str = record.get("createdAt", "")
    if created_at_str:
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
    else:
        created_at = datetime.now(timezone.utc)  # fallback to current time if missing

    record_text = record.get("text", "")
    # if there's no record.text, fall back on embed - either external.description, external.title, images.alt, or video.text
    if record_text == "":
        embed = record.get("embed", {})

        if embed.get("external"):
            # .embed["$type": "app.bsky.embed.external"].external.description
            record_text = embed["external"].get("description", "")
            if record_text == "":
                # .embed["$type": "app.bsky.embed.external"].external.title (both may be present, title is less detailed)
                record_text = embed["external"].get("title", "")
        elif embed.get("images"):
            # .embed[$type='app.bsky.embed.images'].images[].alt - alt text for images if no other text is present
            record_text = " ".join([img.get("alt", "") for img in embed["images"]])
        elif embed.get("video"):
            # .embed[$type='app.bsky.embed.images'].images[].alt - alt text for images if no other text is present
            record_text = embed["video"].get("text", "")

    # .bridgyOriginalText - contains markup, one of the above embeds should be present.
    # TODO: scrub markup?
    # if record_text == "":
    #     record_text = record.get("bridgyOriginalText", "")

    # Seem to get a few of these, probably due to bad encoding from the client.
    if "\x00" in record_text:
        logger.info("DID %s record_text contains null byte %s", did, op)
        return

    if record_text == "":
        # logger.info("empty text %s", op)
        return

    # This runs terrible, I think embedding needs to be taken out-of-band
    # 0.2127881232 seconds/250 records w/o embedding
    # 1.832572528 seconds/250 records w/ embedding, about 10x slower
    # Also the firehose frequently disconnects with embeddings on I suspect a timeout
    # Also, the database acts strangely, it seems like the app thinks it's committing rows
    # but they don't show up in the database as an increasing row count.
    embedding = None # generate_embedding(record_text)

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
        "record_text": record_text,
        "ingest_time": datetime.now(timezone.utc),
        "cursor": cursor,  # Cursor tells us where we left off
        'embedding': embedding
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
        ON CONFLICT (created_at, commit_rev, commit_operation, commit_collection, commit_rkey, commit_cid)
        DO UPDATE SET
            id = EXCLUDED.id,  -- Keep latest ID
            did = EXCLUDED.did,
            created_at = EXCLUDED.created_at,  -- Ensuring latest timestamp is kept
            langs = EXCLUDED.langs,
            reply_parent_cid = EXCLUDED.reply_parent_cid,
            reply_parent_uri = EXCLUDED.reply_parent_uri,
            reply_root_cid = EXCLUDED.reply_root_cid,
            reply_root_uri = EXCLUDED.reply_root_uri,
            record_text = EXCLUDED.record_text,
            ingest_time = EXCLUDED.ingest_time,
            cursor = EXCLUDED.cursor
        WHERE posts.created_at < EXCLUDED.created_at;
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
            logger.warning("no cursor in %s", data)
            return

        state.cursor = str(cursor)

        if data.get("kind") != "commit":
            # for now we're interested in posts only
            # we also see things like identity and account, account has interesting account.status like deleted and takendown
            return

        if "commit" not in data:
            logger.warning("no commit %s", data)
            return

        # We're only interested in new posts
        if data.get("commit", {}).get("operation", "") != "create":
            return

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
    try:
        asyncio.run(run_ingestion())
    except asyncio.exceptions.CancelledError:
        logger.info("Cancelled, stopping...")
