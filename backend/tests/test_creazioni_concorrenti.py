"""Due richieste che creano la stessa riga nello stesso istante.

Il vincolo unico è l'arbitro: chi perde annulla solo il suo tentativo (SAVEPOINT) e
rilegge la riga dell'altra. Prima la settimana finiva in un 500, e l'ingrediente
faceva `db.rollback()` di tutta la transazione — a metà di una generazione buttava
via le ricette già scritte.
"""

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Ingredient, WeekPlan
from app.services import ingredients, planner


def test_un_ingrediente_creato_in_parallelo_non_butta_via_il_resto(client, db, monkeypatch):
    # Una riga in sospeso del chiamante (come le ricette già scritte di una
    # generazione): il conflitto sull'ingrediente non deve portarsela via.
    db.add(Ingredient(name="riga in sospeso", category="altro"))
    db.flush()

    def l_altra_richiesta_arriva_prima(nome):
        db.execute(
            text("INSERT INTO ingredients (name, category) VALUES (:n, 'altro')"),
            {"n": nome},
        )
        return None

    monkeypatch.setattr(ingredients, "catalog_entry", l_altra_richiesta_arriva_prima)
    trovato = ingredients.get_or_create_ingredient(db, "radice di loto")

    assert trovato.name == "radice di loto"
    assert db.query(Ingredient).filter(Ingredient.name == "radice di loto").count() == 1
    db.commit()
    assert db.query(Ingredient).filter(Ingredient.name == "riga in sospeso").count() == 1


def test_una_settimana_creata_in_parallelo_si_rilegge(client, diet, db, monkeypatch):
    originale = planner.ensure_week_structure
    chiamate = []

    def prima_volta_in_conflitto(db_, week, slots):
        chiamate.append(week.id)
        if len(chiamate) == 1:
            raise IntegrityError("INSERT", {}, Exception("uq_week_plan_user_week"))
        return originale(db_, week, slots)

    monkeypatch.setattr(planner, "ensure_week_structure", prima_volta_in_conflitto)
    res = client.get("/api/planning/weeks/current")

    assert res.status_code == 200, res.text
    assert len(chiamate) == 2
    assert db.query(WeekPlan).count() == 1
