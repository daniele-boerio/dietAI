"""Segna le generazioni in corso, così la UI le ritrova dopo un cambio pagina

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-22

"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "week_plans", sa.Column("generation_started_at", sa.DateTime(timezone=True))
    )


def downgrade() -> None:
    op.drop_column("week_plans", "generation_started_at")
