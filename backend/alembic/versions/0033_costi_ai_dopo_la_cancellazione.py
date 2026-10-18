"""I costi AI restano quando si cancella un account

`ai_usage.user_id` era in CASCADE come ogni dato personale, ma queste righe non sono
dell'utente: sono soldi già spesi dall'amministratore, e cancellando un ospite il
conto del mese calava da solo. Ora la FK è SET NULL e la colonna accetta NULL; il
riepilogo mette quelle righe sotto «Account cancellati».

Il downgrade cancella le righe orfane (con NOT NULL non ci starebbero) e rimette il
CASCADE.

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-18

"""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

# Il nome che Postgres dà alla FK creata senza nome in 0028.
FK = "ai_usage_user_id_fkey"


def upgrade() -> None:
    op.drop_constraint(FK, "ai_usage", type_="foreignkey")
    op.alter_column("ai_usage", "user_id", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key(FK, "ai_usage", "users", ["user_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.execute("DELETE FROM ai_usage WHERE user_id IS NULL")
    op.drop_constraint(FK, "ai_usage", type_="foreignkey")
    op.alter_column("ai_usage", "user_id", existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key(FK, "ai_usage", "users", ["user_id"], ["id"], ondelete="CASCADE")
