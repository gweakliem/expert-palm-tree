import asyncio
import logging
from datetime import datetime, UTC
from sentence_transformers import SentenceTransformer
from shared.config import settings
from sqlalchemy import create_engine
import numpy as np
import torch
from sqlalchemy import text

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Database configuration
engine = create_engine(settings.database_url)

# Initialize the embedding model
# Using all-MiniLM-L6-v2 as it's a good balance of speed and quality
model = SentenceTransformer(
    "all-MiniLM-L6-v2", device="cuda" if torch.cuda.is_available() else "cpu"
    # "nomic-ai/nomic-embed-text-v2-moe", trust_remote_code=True
)


def generate_embedding(text: str) -> list[float]:
    """Generate embedding for post text"""
    try:
        # Generate embedding
        embedding = model.encode(text, convert_to_numpy=True, show_progress_bar=False)
        return embedding.tolist()
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        return None


async def run_ingestion():
    """Main ingestion loop to process posts without embeddings"""
    logger.info("Starting embedding ingestion process")
    batch_size = settings.batch_size

    while True:
        try:
            with engine.begin() as conn:
                # Get a batch of posts without embeddings, ordered by created_at
                pull_time = datetime.now(UTC)
                posts = conn.execute(
                    text("""
                    SELECT p.id, p.created_at, p.record_text 
                    FROM posts p
                    LEFT JOIN embeddings e ON p.id = e.post_id
                    WHERE e.post_id IS NULL
                    LIMIT :batch_size;
                    """),
                    {"batch_size": batch_size}
                ).fetchall()
                elapsed_pull = (datetime.now(UTC) - pull_time).total_seconds()

                if not posts:
                    logger.info("No posts found without embeddings, waiting...")
                    await asyncio.sleep(10)  # Wait before checking again
                    continue                
                
                # Process posts in batch
                last_flush = datetime.now(UTC)
                elapsed_embed = 0
                elapsed_query = 0
                for post in posts:
                    if not post.record_text:  # Skip posts with no text
                        logger.warning(f"Post {post.id} has no text, skipping")
                        continue

                    embed_time = datetime.now(UTC)
                    embedding = generate_embedding(post.record_text)
                    elapsed_embed += (datetime.now(UTC) - embed_time).total_seconds()
                    if embedding:
                        # Update the post with its embedding
                        query_time = datetime.now(UTC)
                        result = conn.execute(
                            text("""
                            INSERT INTO embeddings (id, post_id, post_created_at, embedding, created_at, updated_at)
                            VALUES (0, :post_id, :post_created_at, :embedding, :created_at, :updated_at);
                            """),
                            {
                                "post_id": post.id,
                                "post_created_at": post.created_at,
                                "embedding": embedding,
                                "created_at": datetime.now(UTC),
                                "updated_at": datetime.now(UTC)
                            }
                        )
                        elapsed_query += (datetime.now(UTC) - query_time).total_seconds()
                        logger.debug(f"Generated embedding for post {post.id} with result {result.rowcount}")
                    else:
                        logger.error(f"Failed to generate embedding for post {post.id}")

                now = datetime.now(UTC)
                elapsed = (now - last_flush).total_seconds()
                logger.info(f"Completed batch of {len(posts)} posts after {elapsed} seconds elapsed pull {elapsed_pull} average embed time {elapsed_embed/len(posts)} average query time {elapsed_query/len(posts)}")


        except Exception as e:
            logger.error(f"Error in ingestion loop: {e}")
            await asyncio.sleep(5)  # Wait before retrying


if __name__ == "__main__":
    try:
        asyncio.run(run_ingestion())
    except asyncio.exceptions.CancelledError:
        logger.info("Cancelled, stopping...")
