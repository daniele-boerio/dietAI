"""Le scorte in dispensa possono avere una scadenza

La dispensa era «da consumare in via prioritaria» tutta uguale: la ricotta che scade
dopodomani pesava quanto il pacco di riso. Con la data, la generazione sa cosa usare
prima.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-01

"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pantry_items", sa.Column("expires_on", sa.Date()))


def downgrade() -> None:
    op.drop_column("pantry_items", "expires_on")
