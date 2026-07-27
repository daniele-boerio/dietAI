"""Un pasto "pieno" ha la stessa forma da qualunque endpoint arrivi.

La pagina di dettaglio si ridisegna con quello che le torna dal pulsante appena
premuto, non solo con la lettura iniziale: se una risposta è più povera della GET, la
pagina si rompe in mano all'utente. È successo davvero — `week` lo aggiungeva solo la
GET, e il primo clic su "L'ho seguito" spegneva la schermata con un TypeError su
`week.is_locked`.
"""

import pytest

from app.services import planner, prompts
from tests.test_flow import FakeModel, _fake_recipe

CHIAVI_SETTIMANA = {
    "id",
    "week_start_date",
    "is_locked",
    "status",
    "is_current",
    # Il piano si sfoglia all'indietro: da lì si arriva a pasti di settimane
    # archiviate, e la pagina deve sapere che non si rigenerano più.
    "is_past",
}


class ModelloDiProva(FakeModel):
    """FakeModel risponde sempre con una settimana intera: qui serve anche il caso
    del pasto singolo, che ha un prompt di sistema suo."""

    def generate_json(self, system, prompt, **kwargs):
        if system == prompts.SINGLE_MEAL_SYSTEM:
            return _fake_recipe(
                "Pranzo rigenerato", 700, [{"name": "riso", "quantity": 80, "unit": "g"}]
            )
        return super().generate_json(system, prompt, **kwargs)


@pytest.fixture()
def pasto(client, diet, monkeypatch):
    """Il pranzo di lunedì di una settimana generata."""
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: ModelloDiProva(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})

    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    week = client.get("/api/planning/weeks/current").json()
    return next(m for m in week["days"][0]["meals"] if m["slot_name"] == "Pranzo")


# Tutti i modi in cui la pagina di dettaglio si riprende un pasto. Il primo è la
# lettura, gli altri sono i pulsanti: devono restituire la stessa cosa.
AZIONI = {
    "lettura": lambda c, mid, r: c.get(f"/api/planning/meals/{mid}"),
    "rigenera": lambda c, mid, r: c.post(f"/api/planning/meals/{mid}/regenerate"),
    "assegna": lambda c, mid, r: c.put(
        f"/api/planning/meals/{mid}/assign", json={"recipe_id": r}
    ),
    "rendi_fisso": lambda c, mid, r: c.put(
        f"/api/planning/meals/{mid}/recurring", json={"is_recurring": True}
    ),
    "l_ho_seguito": lambda c, mid, r: c.put(
        f"/api/planning/meals/{mid}/followed", json={"is_followed": True}
    ),
    "ho_mangiato_altro": lambda c, mid, r: c.put(
        f"/api/planning/meals/{mid}/followed", json={"is_followed": False}
    ),
    "svuota": lambda c, mid, r: c.delete(f"/api/planning/meals/{mid}/recipe"),
}


@pytest.mark.parametrize("nome", list(AZIONI))
def test_ogni_risposta_porta_la_settimana(client, pasto, nome):
    res = AZIONI[nome](client, pasto["id"], pasto["recipe"]["id"])

    assert res.status_code == 200, res.text
    body = res.json()
    assert "week" in body, f"{nome}: risposta senza settimana, la pagina si spegne"
    assert set(body["week"]) == CHIAVI_SETTIMANA
    # E il resto di quello su cui la pagina si ricostruisce.
    assert {"target", "slot_name", "day_name", "is_followed"} <= set(body)


def test_la_settimana_dice_se_e_bloccata(client, pasto):
    """Il campo che serve davvero: da lì la pagina decide cosa si può ancora toccare."""
    prima = client.get(f"/api/planning/meals/{pasto['id']}").json()
    assert prima["week"]["is_locked"] is False
    assert prima["week"]["is_current"] is True

    client.post("/api/shopping/current/complete")

    dopo = client.put(
        f"/api/planning/meals/{pasto['id']}/followed", json={"is_followed": True}
    ).json()
    # Il tracking funziona anche a piano bloccato, e la risposta lo dice.
    assert dopo["week"]["is_locked"] is True
