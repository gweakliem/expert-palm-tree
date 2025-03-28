"""create posts hypertable

Revision ID: 44ffbe238e1f
Revises: adec8d3a23a1
Create Date: 2025-02-09 15:20:45.966557

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "44ffbe238e1f"
down_revision = "adec8d3a23a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable the vector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create a table for user interests
    op.create_table(
        "user_interests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )

    # **Step 1: Drop the old primary key**
    op.drop_constraint("posts_pkey", "posts", type_="primary")

    # **Step 2: Create a new primary key that includes `created_at`**
    op.create_primary_key("posts_pkey", "posts", ["id", "created_at"])


def downgrade() -> None:
    op.drop_table("user_interests")
