"""Create feeds table

Revision ID: e0c4b5b68ea7
Revises: 445cd5e810b3
Create Date: 2025-02-01 18:54:25.200928

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e0c4b5b68ea7'
down_revision = '445cd5e810b3'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'feeds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_feeds_user_id', 'feeds', ['user_id'])
    
    # Add feed_id to user_keywords
    op.add_column('user_keywords', 
        sa.Column('feed_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_user_keywords_feed_id', 
        'user_keywords', 'feeds',
        ['feed_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_user_keywords_feed_id', 'user_keywords', ['feed_id'])

def downgrade() -> None:
    op.drop_index('ix_user_keywords_feed_id')
    op.drop_constraint('fk_user_keywords_feed_id', 'user_keywords', type_='foreignkey')
    op.drop_column('user_keywords', 'feed_id')
    op.drop_index('ix_feeds_user_id')
    op.drop_table('feeds')
