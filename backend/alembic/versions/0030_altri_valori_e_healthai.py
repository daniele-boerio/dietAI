"""Fibre, zuccheri, saturi, alcol e caffeina; lo stato dell'invio a healthAI

Calorie e tre macro bastavano alla dieta, non a dire cosa si è mangiato: healthAI
(i dati di salute, dove l'alimentazione si incrocia con sonno e allenamenti) vuole
anche fibre, zuccheri, grassi saturi, alcol e caffeina. Arrivano per 100 g
sull'anagrafica e per porzione sulla ricetta, tutti facoltativi: NULL vuol dire "non
si sa", che non è "zero". Le righe già in archivio partono NULL; il seed riempie
l'anagrafica del catalogo, `python -m app.recompute_macros --yes` le ricette.

`health_sync` è quello che healthAI sa di ogni pasto (vedi `services/healthai.py`):
`meal_id` senza FK, perché la riga deve restare quando il pasto se ne va — è lei che
ricorda che su healthAI c'è da cancellare.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-15

"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

INGREDIENTI = ("fiber_100g", "sugar_100g", "saturated_fat_100g", "alcohol_100g", "caffeine_mg_100g")
RICETTE = ("fiber_g", "sugar_g", "saturated_fat_g", "alcohol_g", "caffeine_mg")


def upgrade() -> None:
    for col in INGREDIENTI:
        op.add_column("ingredients", sa.Column(col, sa.Float(), nullable=True))
    for col in RICETTE:
        op.add_column("recipes", sa.Column(col, sa.Float(), nullable=True))

    op.create_table(
        "health_sync",
        sa.Column("meal_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sent_hash", sa.String(), nullable=True),
        sa.Column("failed_hash", sa.String(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("meal_id"),
    )
    op.create_index("ix_health_sync_user_id", "health_sync", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_health_sync_user_id", table_name="health_sync")
    op.drop_table("health_sync")
    for col in reversed(RICETTE):
        op.drop_column("recipes", col)
    for col in reversed(INGREDIENTI):
        op.drop_column("ingredients", col)
