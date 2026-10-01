"""Cucinare per più persone, e cucinare una volta per più giorni.

Due impostazioni del pasto, come «lo faccio io». Le persone moltiplicano la spesa e la
dispensa, non la ricetta né i macro, che restano la dieta di chi usa l'app. Il batch
raggruppa i giorni consecutivi e chiede al modello un piatto solo per gruppo.
"""

import pytest

from app.services import planner
from tests.test_flow import FakeModel


class ModelloCheRicorda(FakeModel):
    prompt = None

    def generate_json(self, system, prompt, **kwargs):
        ModelloCheRicorda.prompt = prompt
        return super().generate_json(system, prompt, **kwargs)


def imposta(client, diet, nome, **campi):
    pasti = [
        {**{k: m[k] for k in ("name", "order", "calories", "protein_g", "carbs_g",
                              "fat_g", "notes", "auto_generate")},
         **(campi if m["name"] == nome else {})}
        for m in diet["meals"]
    ]
    res = client.put(f"/api/diet/{diet['id']}/meals", json={"meals": pasti})
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture()
def genera(client, monkeypatch):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: ModelloCheRicorda(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})

    def _genera():
        week = client.get("/api/planning/weeks/current").json()
        res = client.post(f"/api/planning/weeks/{week['id']}/generate")
        assert res.status_code == 200, res.text
        return res.json()

    return _genera


def pasta_in_lista(client):
    lista = client.get("/api/shopping/current").json()
    return next(i for c in lista["categories"] for i in c["items"] if i["name"] == "pasta")


# ── Persone ────────────────────────────────────────────────────────────────────


def test_la_dieta_ricorda_persone_e_batch(client, diet):
    salvata = imposta(client, diet, "Pranzo", servings=2, batch_days=3)
    pranzo = next(m for m in salvata["meals"] if m["name"] == "Pranzo")
    assert (pranzo["servings"], pranzo["batch_days"]) == (2, 3)


def test_per_due_persone_la_spesa_raddoppia(client, diet, genera):
    genera()
    una = pasta_in_lista(client)["quantity"]

    imposta(client, diet, "Pranzo", servings=2)
    genera()
    assert pasta_in_lista(client)["quantity"] == 2 * una


def test_l_ho_seguito_scala_per_tutte_le_persone(client, diet, genera):
    imposta(client, diet, "Pranzo", servings=2)
    settimana = genera()
    client.post("/api/config/pantry", json={"ingredient_name": "pasta", "quantity": 500, "unit": "g"})

    pranzo = next(m for m in settimana["days"][0]["meals"] if m["slot_name"] == "Pranzo")
    client.put(f"/api/planning/meals/{pranzo['id']}/followed", json={"is_followed": True})

    scorta = next(p for p in client.get("/api/config/pantry").json() if p["name"] == "pasta")
    assert scorta["quantity"] == 300  # 100 g a testa, due persone


# ── Batch ──────────────────────────────────────────────────────────────────────


def test_il_batch_chiede_un_piatto_per_gruppo_di_giorni(client, diet, genera):
    imposta(client, diet, "Pranzo", batch_days=3)
    settimana = genera()

    prompt = ModelloCheRicorda.prompt
    righe_pranzo = [r for r in prompt.splitlines() if "Pranzo —" in r]
    # Sette giorni a gruppi di tre: lun-mer, gio-sab, dom.
    assert len(righe_pranzo) == 3
    assert sum("BATCH" in r for r in righe_pranzo) == 2

    ricetta = [
        next(m for m in d["meals"] if m["slot_name"] == "Pranzo")["recipe"]["id"]
        for d in settimana["days"]
    ]
    assert ricetta[0] == ricetta[1] == ricetta[2]
    assert ricetta[3] == ricetta[4] == ricetta[5]
    assert ricetta[2] != ricetta[3]


def test_un_buco_chiude_il_gruppo(client, diet, genera):
    """Un giorno già pieno in mezzo: lunedì e mercoledì non sono un batch."""
    imposta(client, diet, "Pranzo", batch_days=3)
    settimana = genera()
    martedi = next(m for m in settimana["days"][1]["meals"] if m["slot_name"] == "Pranzo")
    # Si svuotano lunedì e mercoledì, martedì resta pieno.
    for dow in (0, 2):
        m = next(m for m in settimana["days"][dow]["meals"] if m["slot_name"] == "Pranzo")
        client.delete(f"/api/planning/meals/{m['id']}/recipe")
    assert martedi["recipe"]

    genera()
    righe = [r for r in ModelloCheRicorda.prompt.splitlines() if "Pranzo —" in r]
    assert len(righe) == 2
    assert not any("BATCH" in r for r in righe)


def test_il_batch_conta_ogni_giorno_nella_spesa(client, diet, genera):
    genera()
    senza = pasta_in_lista(client)["quantity"]
    imposta(client, diet, "Pranzo", batch_days=3)
    genera()
    # Lo stesso piatto per tre giorni si compra tre volte: è cucinato una volta, ma
    # mangiato tre.
    assert pasta_in_lista(client)["quantity"] == senza
