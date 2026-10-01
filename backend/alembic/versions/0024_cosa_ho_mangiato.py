"""«Ho mangiato altro»: cosa, e quanto

Un pasto saltato era un buco nei dati: si sapeva che il piano non era stato seguito,
non cosa si era mangiato al suo posto. Ora quello che l'utente scrive viene stimato in
calorie e macro, e l'andamento può dire quanto si è mangiato davvero.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-01

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

JSONB = postgresql.JSONB(astext_type=sa.Text())

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("planned_meals", sa.Column("eaten_nutrition", JSONB))


def downgrade() -> None:
    op.drop_column("planned_meals", "eaten_nutrition")
