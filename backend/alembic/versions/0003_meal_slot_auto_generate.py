"""Pasti che l'utente gestisce da sé (non generati dall'AI)

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-21

"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Default true: le diete già caricate continuano a generarsi tutte, come prima.
    op.add_column(
        "meal_slots",
        sa.Column("auto_generate", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("meal_slots", "auto_generate")
