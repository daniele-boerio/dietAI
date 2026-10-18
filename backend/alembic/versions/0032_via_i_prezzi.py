"""Via i prezzi: stima della spesa, prezzo pagato, scontrino e budget

I prezzi del catalogo erano medie nazionali che al negozio vero non dicevano quasi
niente, e il prezzo scritto a mano «a spesa fatta» non funzionava: dopo «Ho fatto la
spesa» la riga usciva dalla lista e segnarne il prezzo dava 404. L'utente non li usava,
e ha deciso di toglierli tutti: stima del costo, prezzo pagato per riga, lettura dello
scontrino, livello di budget e tetto settimanale che arrivavano al modello.

Le colonne si tolgono con i loro dati; il downgrade le rimette vuote (i prezzi del
catalogo li riscriverebbe il seed della versione di prima).

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-18

"""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("shopping_list_items", "estimated_price")
    op.drop_column("shopping_list_items", "paid_price")
    op.drop_column("shopping_lists", "estimated_cost")
    op.drop_column("user_preferences", "weekly_budget_eur")
    op.drop_column("user_preferences", "budget_level")
    op.drop_column("ingredients", "last_paid_at")
    op.drop_column("ingredients", "price_by_user")
    op.drop_column("ingredients", "price_unit")
    op.drop_column("ingredients", "avg_price_per_unit")


def downgrade() -> None:
    op.add_column("ingredients", sa.Column("avg_price_per_unit", sa.Float()))
    op.add_column("ingredients", sa.Column("price_unit", sa.String()))
    op.add_column(
        "ingredients",
        sa.Column("price_by_user", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("ingredients", sa.Column("last_paid_at", sa.DateTime(timezone=True)))
    op.add_column("user_preferences", sa.Column("budget_level", sa.String()))
    op.add_column("user_preferences", sa.Column("weekly_budget_eur", sa.Float()))
    op.add_column("shopping_lists", sa.Column("estimated_cost", sa.Float()))
    op.add_column("shopping_list_items", sa.Column("paid_price", sa.Float()))
    op.add_column("shopping_list_items", sa.Column("estimated_price", sa.Float()))
