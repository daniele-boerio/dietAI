"""La dispensa si svuota mangiando: cosa ha consumato ogni pasto seguito

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-26

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("planned_meals", sa.Column("pantry_used", JSONB))


def downgrade() -> None:
    op.drop_column("planned_meals", "pantry_used")
