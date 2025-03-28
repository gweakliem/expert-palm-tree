"""Create embeddings table

Revision ID: 9604122f044f
Revises: 44ffbe238e1f
Create Date: 2025-02-23 22:12:17.875436

"""

from alembic import op
import sqlalchemy as sa
from shared.types import Vector


# revision identifiers, used by Alembic.
revision = "9604122f044f"
down_revision = "44ffbe238e1f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Text(), nullable=False),
        sa.Column('post_created_at', sa.TIMESTAMP()),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id","created_at"),
    )

    # Create index for vector similarity search
    op.execute(
        "CREATE INDEX post_embedding_idx ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    # Convert `embeddings` table to a hypertable**
    op.execute(
        """
        SELECT create_hypertable('embeddings', 'created_at',
        if_not_exists => TRUE,
        migrate_data => TRUE,
        chunk_time_interval => INTERVAL '1 hour'
        );
        """
    )
    op.execute("ALTER TABLE embeddings SET (timescaledb.compress = true);")

    # Set retention policy
    op.execute(
        "SELECT add_retention_policy('embeddings', INTERVAL '7 days', if_not_exists => TRUE);"
    )

    # Create compression policy (compress chunks older than 1 day)
    op.execute(
        "SELECT add_compression_policy('embeddings', INTERVAL '1 day', if_not_exists => TRUE);"
    )



def downgrade() -> None:
    op.drop_index("post_embedding_idx", table_name="embeddings")
    op.drop_table("embeddings")
