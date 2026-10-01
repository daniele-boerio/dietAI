"""Il tetto di spesa settimanale: arriva al modello, e il conto lo confronta.

Il livello di budget diceva al modello che tipo di ingredienti scegliere; il tetto è un
numero. Il confronto si fa sul periodo che la lista copre davvero, non su una settimana
fissa, o chiunque generi anche la prossima risulterebbe fuori budget.
"""

import pytest

from app.services import planner
from app.services.planner import build_context
from tests.test_flow import FakeModel

PREFS = {"prefer_seasonal": True, "cuisines": {"italiana": 100}}


def test_il_tetto_si_salva_e_non_si_perde_salvando_altro(client):
    client.put("/api/config/preferences", json={**PREFS, "weekly_budget_eur": 60})
    # Un salvataggio che non lo manda non lo cancella.
    res = client.put("/api/config/preferences", json={**PREFS, "prefer_seasonal": False})
    assert res.json()["weekly_budget_eur"] == 60
    # Mandarlo a null sì.
    res = client.put("/api/config/preferences", json={**PREFS, "weekly_budget_eur": None})
    assert res.json()["weekly_budget_eur"] is None


def test_il_tetto_arriva_nel_contesto(client, diet, db):
    client.put("/api/config/preferences", json={**PREFS, "weekly_budget_eur": 45})
    assert "TETTO di spesa: 45 € a settimana" in build_context(db, 1)


def test_senza_tetto_il_contesto_resta_com_era(client, diet, db):
    client.put("/api/config/preferences", json={**PREFS, "budget_level": "economico"})
    riga = next(r for r in build_context(db, 1).splitlines() if "budget" in r)
    assert riga.endswith("economico")


@pytest.fixture()
def con_lista(client, diet, monkeypatch):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")


def test_il_conto_scala_il_tetto_sui_giorni_coperti(client, con_lista):
    client.put("/api/config/preferences", json={**PREFS, "weekly_budget_eur": 70})
    lista = client.get("/api/shopping/current").json()

    budget = lista["budget"]
    assert budget["weekly"] == 70
    assert budget["days"] == 7  # la settimana generata, da lunedì a domenica
    assert budget["limit"] == 70
    assert budget["over"] == (lista["estimated_cost"] > 70)


def test_un_tetto_piccolo_e_superato(client, con_lista):
    client.put("/api/config/preferences", json={**PREFS, "weekly_budget_eur": 1})
    assert client.get("/api/shopping/current").json()["budget"]["over"] is True


def test_senza_tetto_niente_confronto(client, con_lista):
    assert client.get("/api/shopping/current").json()["budget"] is None
