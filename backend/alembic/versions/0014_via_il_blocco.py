"""Via il blocco: il piano si modifica sempre, la lista è quello che manca

Il blocco settimanale non c'è più, e con lui se ne vanno le colonne che esistevano
solo per lui: lo stato del lucchetto sulla settimana, il flag delle ricette traboccate
dallo slittamento automatico (che seguiva la spesa) e la chiusura della lista. La
lista non si chiude: è sempre quello che il piano chiede da oggi in avanti e la
dispensa non copre, quindi a spesa fatta si svuota da sé — la roba è in dispensa.
Resta `completed_at`, che dice quando è stato l'ultimo giro di spesa.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-27

"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("week_plans", "lock_expires_at")
    op.drop_column("week_plans", "locked_at")
    op.drop_column("week_plans", "is_locked")
    op.drop_column("planned_meals", "is_shifted")
    op.drop_column("shopping_lists", "is_completed")


def downgrade() -> None:
    # Le colonne tornano, il loro contenuto no: era stato del lucchetto, e il
    # lucchetto non esiste più. Ripartono tutte da "aperto".
    op.add_column(
        "shopping_lists",
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "planned_meals",
        sa.Column("is_shifted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "week_plans",
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("week_plans", sa.Column("locked_at", sa.DateTime(timezone=True)))
    op.add_column("week_plans", sa.Column("lock_expires_at", sa.DateTime(timezone=True)))
