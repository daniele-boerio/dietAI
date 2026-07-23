"""Pasti saltati a mano: la ricetta va in fondo alla coda

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-23

"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "planned_meals",
        sa.Column(
            "is_skipped", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("planned_meals", "is_skipped")
