"""Porzioni per più persone e batch cooking, per pasto

«Cucino per due» e «cucino domenica per tre giorni» sono due modi di stare in cucina
che la dieta di una persona sola non diceva: il primo moltiplica la spesa, il secondo
ripete lo stesso piatto per più giorni. Sono impostazioni del pasto, come «lo faccio
io».

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-01

"""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meal_slots",
        sa.Column("servings", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "meal_slots",
        sa.Column("batch_days", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("meal_slots", "batch_days")
    op.drop_column("meal_slots", "servings")
