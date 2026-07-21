"""Modello AI scelto per ruolo (pianificazione, chat, lettura dieta)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-21

"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: NULL significa "usa il default dell'ambiente", così chi non tocca
    # niente continua a funzionare e chi vuole risparmiare sceglie dalla UI.
    op.add_column("user_preferences", sa.Column("ai_model_planning", sa.String()))
    op.add_column("user_preferences", sa.Column("ai_model_chat", sa.String()))
    op.add_column("user_preferences", sa.Column("ai_model_diet", sa.String()))


def downgrade() -> None:
    op.drop_column("user_preferences", "ai_model_diet")
    op.drop_column("user_preferences", "ai_model_chat")
    op.drop_column("user_preferences", "ai_model_planning")
