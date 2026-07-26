"""Diario della generazione: cosa sta scrivendo il modello, mentre lo scrive

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-26

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("week_plans", sa.Column("generation_progress", JSONB))


def downgrade() -> None:
    op.drop_column("week_plans", "generation_progress")
