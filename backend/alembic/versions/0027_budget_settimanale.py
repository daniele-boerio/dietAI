"""Un tetto di spesa in euro a settimana

Il livello di budget (economico, medio, premium) diceva al modello che tipo di
ingredienti scegliere, ma non era un numero contro cui misurare la spesa. Ora che i
prezzi sono quelli veri dello scaffale, un tetto in euro si può confrontare.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-01

"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("weekly_budget_eur", sa.Float()))


def downgrade() -> None:
    op.drop_column("user_preferences", "weekly_budget_eur")
