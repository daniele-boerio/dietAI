"""Regole aggiuntive in linguaggio naturale

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-21

"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("notes", sa.Text()))


def downgrade() -> None:
    op.drop_column("user_preferences", "notes")
