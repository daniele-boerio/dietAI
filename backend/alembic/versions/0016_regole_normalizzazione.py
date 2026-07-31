"""Regole di normalizzazione aggiungibili dalle Impostazioni

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-31

"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "normalization_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("term", sa.String(), nullable=False),
        sa.Column("replacement", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "term", name="uq_normalization_rule"),
        sa.CheckConstraint("kind IN ('noise','alias')", name="ck_normalization_kind"),
        sa.CheckConstraint(
            "kind <> 'alias' OR replacement IS NOT NULL",
            name="ck_normalization_alias_target",
        ),
    )


def downgrade() -> None:
    op.drop_table("normalization_rules")
