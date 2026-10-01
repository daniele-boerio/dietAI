"""Il promemoria serale con le notifiche push

Un giorno mai segnato finisce rosso nel grafico della settimana, e il motivo quasi
sempre è una dimenticanza. Le notifiche push, all'ora scelta e solo se c'è qualcosa
da segnare, costano un tocco.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-01

"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("reminder_time", sa.String(5)))
    op.add_column("user_preferences", sa.Column("last_reminder_on", sa.Date()))
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.String(), nullable=False),
        sa.Column("auth", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
    op.drop_column("user_preferences", "last_reminder_on")
    op.drop_column("user_preferences", "reminder_time")
