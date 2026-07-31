"""Un termine di serie si può spegnere: kind = 'off'

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-31

"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # I termini di serie restano nel codice — ci poggiano il catalogo dei prezzi e i
    # test — ma una riga con kind='off' li disattiva, e cancellarla li riaccende.
    op.drop_constraint("ck_normalization_kind", "normalization_rules", type_="check")
    op.create_check_constraint(
        "ck_normalization_kind", "normalization_rules", "kind IN ('noise','alias','off')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM normalization_rules WHERE kind = 'off'")
    op.drop_constraint("ck_normalization_kind", "normalization_rules", type_="check")
    op.create_check_constraint(
        "ck_normalization_kind", "normalization_rules", "kind IN ('noise','alias')"
    )
