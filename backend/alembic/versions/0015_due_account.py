"""Due account: amministratore, accesso sospendibile, interruttore AI

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-31

"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column("ai_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # L'utente che c'era già è l'amministratore: è il suo database e la sua API key.
    # Senza questa riga nessuno sarebbe admin dopo il deploy, e la schermata della
    # chiave sparirebbe anche a chi la paga.
    op.execute("UPDATE users SET is_admin = true WHERE id = (SELECT MIN(id) FROM users)")


def downgrade() -> None:
    op.drop_column("users", "ai_enabled")
    op.drop_column("users", "is_active")
    op.drop_column("users", "is_admin")
