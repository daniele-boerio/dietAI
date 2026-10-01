"""Le frequenze settimanali stanno sulla dieta

«Pesce 2-3 volte, carne rossa al massimo una»: le diete dei nutrizionisti sono scritte
così, e fin qui il vincolo poteva vivere solo nelle regole libere. Ora è un dato della
dieta, che la generazione rispetta assegnando le proteine prima di chiamare il modello
(vedi `utils/frequencies.py`).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-01

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

JSONB = postgresql.JSONB(astext_type=sa.Text())

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("diet_plans", sa.Column("frequencies", JSONB))


def downgrade() -> None:
    op.drop_column("diet_plans", "frequencies")
