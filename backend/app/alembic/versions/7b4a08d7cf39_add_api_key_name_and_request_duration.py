"""Add api_key_name and request duration

Revision ID: 7b4a08d7cf39
Revises: l3m4n5o6p7q8
Create Date: 2026-04-04 19:53:48.703670

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '7b4a08d7cf39'
down_revision = 'l3m4n5o6p7q8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('ai_api_requests', sa.Column('duration', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False, server_default="never"))
    # The user might have already added api_key_name manually, so we check first or just execute wrapped.
    # To avoid failures if the user already added it via pgadmin:
    connection = op.get_bind()
    from sqlalchemy import inspect
    inspector = inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('ai_api_credentials')]
    if 'api_key_name' not in columns:
        op.add_column('ai_api_credentials', sa.Column('api_key_name', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False, server_default="test"))

def downgrade():
    op.drop_column('ai_api_requests', 'duration')
    op.drop_column('ai_api_credentials', 'api_key_name')
