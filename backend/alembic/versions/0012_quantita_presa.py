"""Quanto se n'è preso davvero: le confezioni non si tagliano a misura

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-26

"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shopping_list_items", sa.Column("bought_quantity", sa.Float()))


def downgrade() -> None:
    op.drop_column("shopping_list_items", "bought_quantity")
