"""Lo stesso piatto è una ricetta sola: dove si è accodato un pasto saltato

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-06

Fin qui ogni casella del piano aveva la **sua** riga di ricetta, anche quando il piatto
era identico: sette colazioni uguali erano sette ricette nel ricettario. Ora la riga è
una sola e le caselle ci puntano tutte, il che rompe l'unico posto dove "stessa ricetta"
veniva usato come identità: `unskip_meal` cercava la casella dove il piatto saltato si
era accodato confrontando le `recipe_id`, e con le ricette condivise avrebbe potuto
svuotare la colazione di martedì invece di quella dove il piatto era davvero finito.

Da qui la colonna, che dice **dove**. Il backfill applica la vecchia regola finché è
ancora affidabile — le ricette non sono ancora state fuse (`python -m app.merge_recipes`
si lancia a mano, dopo), quindi la corrispondenza per `recipe_id` è ancora univoca —
così i pasti saltati prima di questo deploy si annullano come si sono sempre annullati.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

# Per ogni pasto saltato che ha ancora una ricetta, la casella dove quel piatto si è
# accodato: stesso pasto della dieta, stessa ricetta, non saltata, in un giorno più
# avanti. È la ricerca che faceva `unskip_meal`, con la data a decidere fra più
# candidate — la prima casella libera era la prima in avanti.
CODE = """
SELECT saltato.id AS saltato_id,
       (SELECT coda.id
          FROM planned_meals AS coda
          JOIN day_plans AS giorno_coda ON giorno_coda.id = coda.day_plan_id
         WHERE coda.id <> saltato.id
           AND coda.meal_slot_id = saltato.meal_slot_id
           AND coda.recipe_id = saltato.recipe_id
           AND coda.is_skipped = false
           AND giorno_coda.date > giorno_saltato.date
         ORDER BY giorno_coda.date
         LIMIT 1) AS coda_id
  FROM planned_meals AS saltato
  JOIN day_plans AS giorno_saltato ON giorno_saltato.id = saltato.day_plan_id
 WHERE saltato.is_skipped = true
   AND saltato.recipe_id IS NOT NULL
"""


def upgrade() -> None:
    op.add_column(
        "planned_meals",
        sa.Column(
            "skipped_to_meal_id",
            sa.Integer(),
            sa.ForeignKey("planned_meals.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Il backfill si fa leggendo e riscrivendo, non con una UPDATE correlata: le righe
    # sono poche (solo i pasti saltati non ancora corretti) e questa forma è la stessa
    # su qualunque database, mentre `UPDATE ... AS alias SET` cambia da dialetto a
    # dialetto — una migrazione che non gira è peggio di una lenta.
    conn = op.get_bind()
    coppie = [
        (riga.saltato_id, riga.coda_id)
        for riga in conn.execute(sa.text(CODE))
        if riga.coda_id is not None
    ]
    for saltato_id, coda_id in coppie:
        conn.execute(
            sa.text(
                "UPDATE planned_meals SET skipped_to_meal_id = :coda WHERE id = :saltato"
            ),
            {"coda": coda_id, "saltato": saltato_id},
        )


def downgrade() -> None:
    op.drop_column("planned_meals", "skipped_to_meal_id")
