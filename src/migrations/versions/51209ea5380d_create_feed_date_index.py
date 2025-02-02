"""Create feed date index

Revision ID: 51209ea5380d
Revises: 445cd5e810b3
Create Date: 2025-02-01 13:26:50.957235

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '51209ea5380d'
down_revision = '445cd5e810b3'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_index('ix_posts_created_at', 'posts', ['created_at'])

def downgrade() -> None:
    op.drop_index('ix_posts_created_at', table_name='posts')