"""Vincoli su stati dei pasti, porzioni e quantità — dopo aver ripulito i dati

Finora questi limiti stavano solo negli schemi degli input e nelle singole rotte, e
ogni rotta azzerava il suo pezzo: assegnare una ricetta toglieva «l'ho seguito» ma
lasciava la stima di «cosa ho mangiato», generare lasciava `pantry_used`. Il codice ora
passa tutto da `planner.forget_tracking`, e il database rifiuta gli stati che non
stanno insieme:

- `ck_planned_meal_skipped_to`: un rinvio (`skipped_to_meal_id`) solo su un pasto saltato;
- `ck_planned_meal_eaten`: la stima di «cosa ho mangiato» solo su «ho mangiato altro»;
- `ck_planned_meal_pantry`: la memoria della dispensa scalata solo su «l'ho seguito»;
- porzioni e batch almeno 1, target, macro e quantità mai negativi.

Un vincolo aggiunto su dati che lo violano fa fallire la migrazione, e il backend non
parte. Per questo, **prima** di ogni vincolo, le righe fuori regola si correggono nel
modo che non inventa niente: lo stato orfano si azzera, il numero negativo va a 0, la
porzione a 1. I JSON azzerati possono essere SQL NULL o il JSON `null`, e valgono
tutti e due.

Il downgrade toglie i vincoli; i dati ripuliti restano come sono.

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-18

"""

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

# (tabella, nome, condizione, pulizia che la rende vera)
VINCOLI = (
    (
        "meal_slots",
        "ck_meal_slot_counts",
        "servings >= 1 AND batch_days >= 1",
        "UPDATE meal_slots SET servings = GREATEST(servings, 1), "
        "batch_days = GREATEST(batch_days, 1) WHERE servings < 1 OR batch_days < 1",
    ),
    (
        "meal_slots",
        "ck_meal_slot_targets",
        "target_calories >= 0 AND target_protein_g >= 0 AND target_carbs_g >= 0 "
        "AND target_fat_g >= 0",
        "UPDATE meal_slots SET target_calories = GREATEST(target_calories, 0), "
        "target_protein_g = GREATEST(target_protein_g, 0), "
        "target_carbs_g = GREATEST(target_carbs_g, 0), "
        "target_fat_g = GREATEST(target_fat_g, 0) "
        "WHERE target_calories < 0 OR target_protein_g < 0 OR target_carbs_g < 0 "
        "OR target_fat_g < 0",
    ),
    (
        "recipes",
        "ck_recipe_macros",
        "calories >= 0 AND protein_g >= 0 AND carbs_g >= 0 AND fat_g >= 0",
        "UPDATE recipes SET calories = GREATEST(calories, 0), "
        "protein_g = GREATEST(protein_g, 0), carbs_g = GREATEST(carbs_g, 0), "
        "fat_g = GREATEST(fat_g, 0) "
        "WHERE calories < 0 OR protein_g < 0 OR carbs_g < 0 OR fat_g < 0",
    ),
    (
        "recipe_ingredients",
        "ck_recipe_ingredient_quantity",
        "quantity >= 0",
        "UPDATE recipe_ingredients SET quantity = 0 WHERE quantity < 0",
    ),
    (
        "planned_meals",
        "ck_planned_meal_skipped_to",
        "skipped_to_meal_id IS NULL OR is_skipped IS TRUE",
        "UPDATE planned_meals SET skipped_to_meal_id = NULL "
        "WHERE skipped_to_meal_id IS NOT NULL AND is_skipped IS NOT TRUE",
    ),
    (
        "planned_meals",
        "ck_planned_meal_eaten",
        "eaten_nutrition IS NULL OR CAST(eaten_nutrition AS TEXT) = 'null' "
        "OR is_followed IS FALSE",
        "UPDATE planned_meals SET eaten_nutrition = NULL "
        "WHERE eaten_nutrition IS NOT NULL AND is_followed IS NOT FALSE",
    ),
    (
        "planned_meals",
        "ck_planned_meal_pantry",
        "pantry_used IS NULL OR CAST(pantry_used AS TEXT) = 'null' "
        "OR is_followed IS TRUE",
        "UPDATE planned_meals SET pantry_used = NULL "
        "WHERE pantry_used IS NOT NULL AND is_followed IS NOT TRUE",
    ),
    (
        "pantry_items",
        "ck_pantry_quantity",
        "quantity_available IS NULL OR quantity_available >= 0",
        "UPDATE pantry_items SET quantity_available = 0 WHERE quantity_available < 0",
    ),
    (
        "shopping_list_items",
        "ck_shopping_item_quantity",
        "total_quantity >= 0 AND (bought_quantity IS NULL OR bought_quantity > 0)",
        "UPDATE shopping_list_items SET total_quantity = GREATEST(total_quantity, 0), "
        "bought_quantity = CASE WHEN bought_quantity > 0 THEN bought_quantity END "
        "WHERE total_quantity < 0 OR bought_quantity <= 0",
    ),
)


def upgrade() -> None:
    for tabella, nome, condizione, pulizia in VINCOLI:
        op.execute(pulizia)
        op.create_check_constraint(nome, tabella, condizione)


def downgrade() -> None:
    for tabella, nome, _condizione, _pulizia in reversed(VINCOLI):
        op.drop_constraint(nome, tabella, type_="check")
