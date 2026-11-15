"""users: google_sub column and optional password

Revision ID: 3b9d5c7e1a42
Revises: 890e8318e5c7
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "3b9d5c7e1a42"
down_revision = "890e8318e5c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_sub", sa.String(length=64), nullable=True))
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)
    op.alter_column("users", "hashed_password", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    # fails if Google-only users (no password) exist: delete or give them a password first
    op.alter_column("users", "hashed_password", existing_type=sa.String(length=255), nullable=False)
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_column("users", "google_sub")
