"""Il prezzo pagato sta sulla riga della lista, non solo al chilo sull'ingrediente

Prima si conservava soltanto il prezzo unitario ricavato dalla cifra scritta
dall'utente, e il costo della riga veniva **ricalcolato** ogni volta da quel prezzo
per la quantità del momento. Bastava correggere la quantità presa, o rigenerare una
ricetta (che cambia quanto ne serve), perché il numero scritto a mano diventasse un
altro: al supermercato sembrava che l'app cambiasse i prezzi da sé.

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-30

"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shopping_list_items", sa.Column("paid_price", sa.Float()))


def downgrade() -> None:
    op.drop_column("shopping_list_items", "paid_price")
