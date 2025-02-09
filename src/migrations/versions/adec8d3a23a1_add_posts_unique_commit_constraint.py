"""add posts_unique_commit constraint

Revision ID: adec8d3a23a1
Revises: e0c4b5b68ea7
Create Date: 2025-02-09 07:00:51.981521

"""
from alembic import op
import sqlalchemy as sa

# Revision identifiers, used by Alembic.
revision = 'adec8d3a23a1'
down_revision = 'e0c4b5b68ea7'
branch_labels = None
depends_on = None

def upgrade():
    op.create_unique_constraint(
        "posts_unique_commit",
        "posts",
        ["commit_rev", "commit_operation", "commit_collection", "commit_rkey", "commit_cid"]
    )

def downgrade():
    op.drop_constraint("posts_unique_commit", "posts", type_="unique")