"""Chat della spesa: cambia un ingrediente in tutte le ricette della settimana

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-23

"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shopping_chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_plan_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["week_plan_id"], ["week_plans.id"], ondelete="CASCADE"),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_shopping_chat_role"),
    )
    op.create_index(
        "ix_shopping_chat_messages_week_plan_id",
        "shopping_chat_messages",
        ["week_plan_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_shopping_chat_messages_week_plan_id", table_name="shopping_chat_messages"
    )
    op.drop_table("shopping_chat_messages")
