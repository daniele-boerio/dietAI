"""La durata di ogni chiamata AI e il modello per le stime veloci

«L'app è lenta» senza numeri non si misurava: il registro sapeva token e costo, non
quanto si era aspettato (`ai_usage.duration_ms`, NULL sulle righe di prima).
`user_preferences.ai_model_quick`: il modello delle stime brevi; NULL = quello della
chat.

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-03

"""

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_usage", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("user_preferences", sa.Column("ai_model_quick", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_preferences", "ai_model_quick")
    op.drop_column("ai_usage", "duration_ms")
