"""Il costo delle chiamate AI in Numeric invece che Float

Le chiamate costano frazioni di centesimo (0,00012 $) e il riepilogo ne somma
migliaia: in Float ogni valore porta l'errore di rappresentazione binaria e la somma
lo accumula. Numeric(14, 8) li tiene esatti fino all'ottava cifra decimale, che è
più di quanto OpenRouter dichiari. La conversione è senza perdita: i valori esistenti
stanno tutti in 14 cifre.

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-18

"""

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "ai_usage",
        "cost_usd",
        existing_type=sa.Float(),
        type_=sa.Numeric(14, 8),
        postgresql_using="cost_usd::numeric(14, 8)",
    )


def downgrade() -> None:
    op.alter_column(
        "ai_usage",
        "cost_usd",
        existing_type=sa.Numeric(14, 8),
        type_=sa.Float(),
        postgresql_using="cost_usd::double precision",
    )
