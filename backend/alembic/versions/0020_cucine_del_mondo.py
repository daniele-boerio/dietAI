"""Le cucine si scelgono da un elenco, non da un interruttore

L'interruttore "cucina italiana" faceva una domanda con due risposte, e la seconda
("no") non diceva niente al modello — restava "nessuna preferenza particolare".
Adesso la domanda è quale cucina, e le risposte sono un elenco: `cuisines` tiene le
chiavi del catalogo (`utils/cuisines.py`).

La conversione è quella ovvia — acceso significava cucina italiana — e tiene insieme
le due cose che il vecchio flag diceva davvero: chi non l'aveva mai toccato (acceso
per default) si ritrova "Italiana" spuntata, cioè le stesse ricette di prima; chi
l'aveva spento si ritrova l'elenco vuoto, che è la stessa mano libera di prima.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-21

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Come nelle altre migrazioni: in produzione gira Postgres e la colonna è JSONB,
# esattamente come la dichiara `models.JSONType`.
JSONB = postgresql.JSONB(astext_type=sa.Text())

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("cuisines", JSONB))
    # Le due UPDATE vanno prima della DROP, perché `prefer_italian` è l'unico posto
    # da cui quell'informazione si può ancora leggere. Il documento si scrive come
    # testo e si lascia convertire dal cast: un elenco di una voce sola non merita
    # una tabella temporanea.
    op.execute(
        "UPDATE user_preferences SET cuisines = '[\"italiana\"]'::jsonb "
        "WHERE prefer_italian"
    )
    op.execute(
        "UPDATE user_preferences SET cuisines = '[]'::jsonb WHERE NOT prefer_italian"
    )
    op.drop_column("user_preferences", "prefer_italian")


def downgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column(
            "prefer_italian", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.drop_column("user_preferences", "cuisines")
