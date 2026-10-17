"""Indici sulle chiavi esterne che il codice filtra di continuo

Postgres non indicizza da solo le colonne di una FK. `planned_meals.recipe_id` si
filtra a ogni fork, riaccorpamento e cancellazione di ricetta; `meal_slot_id` e
`skipped_to_meal_id` nei riallineamenti e nei pasti rimandati; `ingredient_id` di
ricette, dispensa e lista in ogni fusione di ingredienti e in ogni CASCADE. Con poche
centinaia di righe non si vedeva, ma `planned_meals` cresce di una trentina di righe a
settimana e ogni DELETE su una ricetta o un ingrediente scandiva le tabelle figlie per
intero. Nessun dato cambia: solo indici, che si tolgono col downgrade.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-17

"""

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

INDICI = (
    ("recipe_ingredients", "ingredient_id"),
    ("planned_meals", "meal_slot_id"),
    ("planned_meals", "recipe_id"),
    ("planned_meals", "skipped_to_meal_id"),
    ("pantry_items", "ingredient_id"),
    ("shopping_list_items", "ingredient_id"),
)


def upgrade() -> None:
    for tabella, colonna in INDICI:
        op.create_index(
            f"ix_{tabella}_{colonna}", tabella, [colonna], if_not_exists=True
        )


def downgrade() -> None:
    for tabella, colonna in reversed(INDICI):
        op.drop_index(f"ix_{tabella}_{colonna}", table_name=tabella, if_exists=True)
