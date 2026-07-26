"""Quanto è costato davvero: il prezzo segnato dall'utente batte il catalogo

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-26

"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingredients",
        sa.Column("price_by_user", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("ingredients", sa.Column("last_paid_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("ingredients", "last_paid_at")
    op.drop_column("ingredients", "price_by_user")
