"""initial schema

Revision ID: initial_schema
Create Date: 2024-01-11 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'initial_schema'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'posts',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('did', sa.Text()),
        sa.Column('kind', sa.Text()),
        sa.Column('commit_rev', sa.Text()),
        sa.Column('commit_operation', sa.Text()),
        sa.Column('commit_collection', sa.Text()),
        sa.Column('commit_rkey', sa.Text()),
        sa.Column('commit_cid', sa.Text()),
        sa.Column('created_at', sa.TIMESTAMP()),
        sa.Column('langs', sa.ARRAY(sa.Text())),
        sa.Column('reply_parent_cid', sa.Text()),
        sa.Column('reply_parent_uri', sa.Text()),
        sa.Column('reply_root_cid', sa.Text()),
        sa.Column('reply_root_uri', sa.Text()),
        sa.Column('record_text', sa.Text()),
        sa.Column('ingest_time', sa.TIMESTAMP(timezone=True)),
        sa.Column('cursor', sa.Text()),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('idx_posts_cursor', 'posts', ['cursor'], unique=False)
    op.create_index('idx_posts_created_at', 'posts', ['created_at'], unique=False)

    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )

    op.create_table(
        'user_keywords',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('keyword', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('user_keywords')
    op.drop_table('users')
    op.drop_table('posts')