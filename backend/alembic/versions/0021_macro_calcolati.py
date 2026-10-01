"""I macro di una ricetta si calcolano dagli ingredienti

Fin qui calorie e macro di ogni ricetta erano quelli che dichiarava il modello, e
nessuno li controllava: un modello che scrive "650 kcal" sotto una ricetta che ne pesa
820 sbaglia una somma, e su quel numero si reggevano totali del giorno, aderenza e
grafici. Ora l'anagrafica porta la composizione per 100 g (il seed la riempie per il
catalogo, il modello la stima per gli altri nomi) e la ricetta dice da dove vengono i
suoi numeri.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-01

"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_COLONNE_INGREDIENTE = (
    "kcal_100g",
    "protein_100g",
    "carbs_100g",
    "fat_100g",
    "grams_per_unit",
    "density",
)


def upgrade() -> None:
    for nome in _COLONNE_INGREDIENTE:
        op.add_column("ingredients", sa.Column(nome, sa.Float()))
    op.add_column("ingredients", sa.Column("composition_source", sa.String()))
    # Le ricette che esistono restano coi numeri che avevano (NULL = di prima): le
    # ricalcola, se si vuole, `python -m app.recompute_macros`.
    op.add_column("recipes", sa.Column("nutrition_source", sa.String()))


def downgrade() -> None:
    op.drop_column("recipes", "nutrition_source")
    op.drop_column("ingredients", "composition_source")
    for nome in reversed(_COLONNE_INGREDIENTE):
        op.drop_column("ingredients", nome)
