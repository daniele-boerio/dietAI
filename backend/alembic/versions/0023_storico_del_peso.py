"""Lo storico del peso

Il peso del questionario era una fotografia: quella del giorno in cui lo si era
compilato. Le pesate danno il film, e permettono di accorgersi quando i target
calcolati appartengono a un peso che non c'è più.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-01

"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weight_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "day", name="uq_weight_entry_day"),
        sa.CheckConstraint("weight_kg > 0 AND weight_kg < 500", name="ck_weight_range"),
    )
    op.create_index("ix_weight_entries_user_id", "weight_entries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_weight_entries_user_id", table_name="weight_entries")
    op.drop_table("weight_entries")
