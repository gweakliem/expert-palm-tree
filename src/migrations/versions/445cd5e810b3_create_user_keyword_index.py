"""Create user_keyword index

Revision ID: 445cd5e810b3
Revises: initial_schema
Create Date: 2025-02-01 12:37:20.508465

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '445cd5e810b3'
down_revision = 'initial_schema'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add updated_at column to users table
    op.add_column('users', sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False))
    
    # Add updated_at column to user_keywords table
    op.add_column('user_keywords', sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False))
    
    # Create secondary index on user_keywords.user_id
    op.create_index('ix_user_keywords_user_id', 'user_keywords', ['user_id'])

def downgrade() -> None:
    # Drop the secondary index on user_keywords.user_id
    op.drop_index('ix_user_keywords_user_id', table_name='user_keywords')
    
    # Drop updated_at column from user_keywords table
    op.drop_column('user_keywords', 'updated_at')
    
    # Drop updated_at column from users table
    op.drop_column('users', 'updated_at')