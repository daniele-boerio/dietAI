"""Giorni saltati quando la spesa non è stata fatta, e ricette che slittano

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-23

"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "day_plans",
        sa.Column(
            "is_skipped", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "planned_meals",
        sa.Column(
            "is_shifted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("planned_meals", "is_shifted")
    op.drop_column("day_plans", "is_skipped")
