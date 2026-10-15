"""I pasti consumati arrivano a healthAI, e ne escono quando non lo sono più.

Il giro (`services/healthai.sync`) non segue le azioni ma confronta gli stati: quello
che il pasto dice adesso contro quello che healthAI ha. Qui si prova ogni
transizione (seguito, «ho mangiato altro», desegnato, cambiato, cancellato), che
l'ultima azione vince sempre, e come si comporta coi fallimenti: 401 e 422 non si
ritentano, la rete giù sì, con l'attesa.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import config
from app.models import HealthSync, MealSlot, PlannedMeal, Recipe
from app.routers import planning as planning_router
from app.services import healthai, planner
from tests.test_flow import FakeModel

ORA = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


class Posta:
    """healthAI finto: si segna ogni chiamata e risponde quello che gli si dice."""

    def __init__(self):
        self.chiamate: list[tuple[str, int, dict | None]] = []
        self.risposta = healthai.Esito(True, 200)

    def __call__(self, method, meal_id, payload):
        self.chiamate.append((method, meal_id, payload))
        return self.risposta

    def metodi(self):
        return [(m, mid) for m, mid, _ in self.chiamate]


class ModelloCheStima(FakeModel):
    def generate_json(self, system, prompt, **kwargs):
        if "COSA HA MANGIATO INVECE" in prompt:
            return {"calories": 850, "protein_g": 32, "carbs_g": 105, "fat_g": 30,
                    "fiber_g": 5.0, "sugar_g": 9.0, "saturated_fat_g": 12.0,
                    "alcohol_g": 15.8, "caffeine_mg": 0, "note": "pizza e birra"}
        return super().generate_json(system, prompt, **kwargs)


@pytest.fixture(autouse=True)
def acceso(monkeypatch):
    monkeypatch.setattr(config, "HEALTHAI_URL", "http://healthai.test")
    monkeypatch.setattr(config, "HEALTHAI_TOKEN", "token-di-prova")
    healthai.reset_process_state()
    yield
    healthai.reset_process_state()


@pytest.fixture()
def posta():
    return Posta()


@pytest.fixture()
def settimana(client, diet, monkeypatch):
    finto = lambda db, user, role: ModelloCheStima(user)  # noqa: E731
    monkeypatch.setattr(planner, "get_client", finto)
    monkeypatch.setattr(planning_router, "get_client", finto)
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    return client.post(f"/api/planning/weeks/{week['id']}/generate").json()


def pasto(settimana, dow, nome):
    return next(m for m in settimana["days"][dow]["meals"] if m["slot_name"] == nome)


def giro(db, posta, **kw):
    """Un giro con "oggi" = il lunedì dei test e la finestra che lo comprende."""
    kw.setdefault("ora", ORA)
    return healthai.sync(db, oggi=planner.today(), giorni=30, send=posta, **kw)


def segui(client, meal_id, seguito=True):
    res = client.put(f"/api/planning/meals/{meal_id}/followed", json={"is_followed": seguito})
    assert res.status_code == 200, res.text
    return res.json()


# ── Cosa si manda ──────────────────────────────────────────────────────────────


def test_il_pasto_seguito_parte_con_i_valori_della_ricetta(client, db, settimana, posta):
    pranzo = pasto(settimana, 0, "Pranzo")
    ricetta = segui(client, pranzo["id"])["recipe"]

    giro(db, posta)

    assert posta.metodi() == [("POST", pranzo["id"])]
    body = posta.chiamate[0][2]
    assert body["date"] == planner.today().isoformat()
    assert body["meal_name"] == "Pranzo"
    assert body["recipe_title"] == ricetta["title"]
    assert body["calories"] == ricetta["calories"]
    assert body["protein_g"] == ricetta["protein_g"]
    assert body["source"] == "dietai"
    assert body["external_meal_id"] == pranzo["id"]


def test_le_porzioni_per_piu_persone_non_moltiplicano_il_piatto(client, db, settimana, posta):
    """Cucinare per due raddoppia la spesa, non quello che si mangia."""
    pranzo = pasto(settimana, 0, "Pranzo")
    ricetta = segui(client, pranzo["id"])["recipe"]
    slot = db.get(MealSlot, db.get(PlannedMeal, pranzo["id"]).meal_slot_id)
    slot.servings = 2
    db.commit()

    giro(db, posta)

    assert posta.chiamate[0][2]["calories"] == ricetta["calories"]


def test_zero_e_non_so_restano_diversi(client, db, settimana, posta):
    pranzo = pasto(settimana, 0, "Pranzo")
    segui(client, pranzo["id"])
    recipe = db.get(Recipe, db.get(PlannedMeal, pranzo["id"]).recipe_id)
    recipe.alcohol_g = 0.0
    recipe.fiber_g = None
    db.commit()

    giro(db, posta)

    body = posta.chiamate[0][2]
    assert body["alcohol_g"] == 0
    assert body["fiber_g"] is None


def test_ho_mangiato_altro_parte_con_la_stima(client, db, settimana, posta):
    cena = pasto(settimana, 0, "Cena")
    segui(client, cena["id"], False)
    giro(db, posta)
    assert posta.chiamate == []  # saltato senza dire cosa: non si sa, non si manda

    client.put(f"/api/planning/meals/{cena['id']}/eaten", json={"text": "pizza e una birra media"})
    giro(db, posta)

    assert posta.metodi() == [("POST", cena["id"])]
    body = posta.chiamate[0][2]
    assert body["recipe_title"] == "pizza e una birra media"
    assert body["calories"] == 850
    assert body["alcohol_g"] == 15.8  # grammi di etanolo, come li ha stimati
    assert body["caffeine_mg"] == 0


def test_non_ho_mangiato_niente_parte_a_zero(client, db, settimana, posta):
    """Un digiuno detto è un dato: healthAI riceve il pasto a 0 kcal, con gli altri
    valori a zero (saputi), non a null."""
    cena = pasto(settimana, 0, "Cena")
    segui(client, cena["id"], False)
    client.put(f"/api/planning/meals/{cena['id']}/eaten", json={"nothing": True})

    giro(db, posta)

    body = posta.chiamate[0][2]
    assert body["calories"] == 0
    assert body["recipe_title"] == "Non ho mangiato niente"
    assert body["caffeine_mg"] == 0 and body["fiber_g"] == 0


def test_un_giorno_futuro_non_parte(client, db, settimana, posta):
    domani = pasto(settimana, 1, "Pranzo")
    segui(client, domani["id"])
    giro(db, posta)
    assert posta.chiamate == []


def test_i_pasti_dell_ospite_non_partono(client, guest_client, db, posta):
    """healthAI è dell'amministratore: i pasti di un altro non sono i suoi."""
    guest_client.post(
        "/api/diet/manual",
        json={"meals": [{"name": "Pranzo", "order": 0, "calories": 700, "protein_g": 40,
                         "carbs_g": 80, "fat_g": 20}]},
    )
    week = guest_client.get("/api/planning/weeks/current").json()
    meal = db.get(PlannedMeal, week["days"][0]["meals"][0]["id"])
    meal.is_followed = False
    meal.eaten_nutrition = {"calories": 500, "protein_g": 20, "carbs_g": 60, "fat_g": 15}
    db.commit()

    giro(db, posta)

    assert posta.chiamate == []


def test_spento_senza_configurazione(client, db, settimana, posta, monkeypatch):
    monkeypatch.setattr(config, "HEALTHAI_TOKEN", "")
    segui(client, pasto(settimana, 0, "Pranzo")["id"])

    assert giro(db, posta).fermato == "spento"
    assert posta.chiamate == []


# ── Le transizioni ─────────────────────────────────────────────────────────────


def test_un_pasto_gia_inviato_non_si_rimanda(client, db, settimana, posta):
    segui(client, pasto(settimana, 0, "Pranzo")["id"])
    giro(db, posta)
    giro(db, posta)
    assert len(posta.chiamate) == 1


def test_desegnato_si_cancella(client, db, settimana, posta):
    pranzo = pasto(settimana, 0, "Pranzo")
    segui(client, pranzo["id"])
    giro(db, posta)

    # «Ho mangiato altro» senza dire cosa: il pasto non è più consumato, per quanto
    # se ne sa.
    segui(client, pranzo["id"], False)
    giro(db, posta)

    assert posta.metodi() == [("POST", pranzo["id"]), ("DELETE", pranzo["id"])]
    assert db.get(HealthSync, pranzo["id"]) is None


def test_da_seguito_ad_altro_si_aggiorna(client, db, settimana, posta):
    """Lo stesso pasto, un'altra cosa mangiata: un POST con lo stesso id, che su
    healthAI sovrascrive. Nessuna DELETE in mezzo."""
    cena = pasto(settimana, 0, "Cena")
    segui(client, cena["id"])
    giro(db, posta)

    segui(client, cena["id"], False)
    client.put(f"/api/planning/meals/{cena['id']}/eaten", json={"text": "pizza"})
    giro(db, posta)

    assert posta.metodi() == [("POST", cena["id"]), ("POST", cena["id"])]
    assert posta.chiamate[1][2]["calories"] == 850


def test_la_ricetta_che_cambia_si_rimanda(client, db, settimana, posta):
    pranzo = pasto(settimana, 0, "Pranzo")
    segui(client, pranzo["id"])
    giro(db, posta)

    recipe = db.get(Recipe, db.get(PlannedMeal, pranzo["id"]).recipe_id)
    recipe.calories += 50
    db.commit()
    giro(db, posta)

    assert posta.metodi() == [("POST", pranzo["id"])] * 2
    assert posta.chiamate[1][2]["calories"] == recipe.calories


def test_il_cestino_lo_toglie(client, db, settimana, posta):
    """Svuotare la casella di un pasto mangiato: non c'è più niente da dire su cosa
    si è mangiato lì, e healthAI se lo dimentica."""
    pranzo = pasto(settimana, 0, "Pranzo")
    segui(client, pranzo["id"])
    giro(db, posta)

    assert client.delete(f"/api/planning/meals/{pranzo['id']}/recipe").status_code == 200
    giro(db, posta)

    assert posta.metodi()[-1] == ("DELETE", pranzo["id"])


def test_il_pasto_cancellato_si_toglie(client, db, settimana, posta):
    pranzo = pasto(settimana, 0, "Pranzo")
    segui(client, pranzo["id"])
    giro(db, posta)

    db.delete(db.get(PlannedMeal, pranzo["id"]))
    db.commit()
    giro(db, posta)

    assert posta.metodi()[-1] == ("DELETE", pranzo["id"])


def test_conta_l_ultima_azione(client, db, settimana, posta):
    """Segnato mentre healthAI era giù, poi desegnato: il POST vecchio non deve
    partire dopo, o il pasto ricomparirebbe. E non serve nemmeno una DELETE: healthAI
    quel pasto non l'ha mai avuto."""
    pranzo = pasto(settimana, 0, "Pranzo")
    segui(client, pranzo["id"])
    posta.risposta = healthai.Esito(False, None, "ConnectError")
    giro(db, posta)

    segui(client, pranzo["id"], False)
    posta.risposta = healthai.Esito(True, 200)
    giro(db, posta, ora=ORA + timedelta(hours=2))

    assert posta.metodi() == [("POST", pranzo["id"])]  # solo il tentativo fallito
    assert db.get(HealthSync, pranzo["id"]) is None


# ── I fallimenti ───────────────────────────────────────────────────────────────


def test_la_rete_giu_si_ritenta_con_l_attesa(client, db, settimana, posta):
    pranzo = pasto(settimana, 0, "Pranzo")
    segui(client, pranzo["id"])
    posta.risposta = healthai.Esito(False, None, "ConnectTimeout")

    g = giro(db, posta)
    assert g.fermato == "healthAI non raggiungibile"
    row = db.get(HealthSync, pranzo["id"])
    assert row.attempts == 1 and row.next_attempt_at is not None

    giro(db, posta, ora=ORA + timedelta(seconds=30))  # dentro l'attesa: niente
    assert len(posta.chiamate) == 1

    posta.risposta = healthai.Esito(True, 200)
    giro(db, posta, ora=ORA + timedelta(minutes=2))
    assert len(posta.chiamate) == 2
    row = db.get(HealthSync, pranzo["id"])
    assert row.sent_hash is not None and row.failed_hash is None


def test_le_attese_crescono_e_dopo_un_giorno_ci_si_arrende(client, db, settimana, posta):
    pranzo = pasto(settimana, 0, "Pranzo")
    segui(client, pranzo["id"])
    posta.risposta = healthai.Esito(False, 503, "giù")

    ora = ORA
    attese = []
    for _ in range(4):
        giro(db, posta, ora=ora)
        row = db.get(HealthSync, pranzo["id"])
        prossimo = row.next_attempt_at.replace(tzinfo=timezone.utc)
        attese.append(prossimo - ora)
        ora = prossimo
    assert [a.total_seconds() / 60 for a in attese] == [1, 5, 30, 60]

    giro(db, posta, ora=ORA + timedelta(hours=25))
    assert db.get(HealthSync, pranzo["id"]).next_attempt_at is None  # resa


def test_un_401_non_si_ritenta(client, db, settimana, posta):
    segui(client, pasto(settimana, 0, "Pranzo")["id"])
    segui(client, pasto(settimana, 0, "Colazione")["id"])
    posta.risposta = healthai.Esito(False, 401, "token non valido")

    g = giro(db, posta)
    assert g.fermato == "token rifiutato"
    assert len(posta.chiamate) == 1  # il giro si ferma al primo

    giro(db, posta, ora=ORA + timedelta(hours=3))
    assert len(posta.chiamate) == 1  # e non riprova fino al riavvio


def test_un_422_non_si_ritenta_finche_il_pasto_non_cambia(client, db, settimana, posta):
    pranzo = pasto(settimana, 0, "Pranzo")
    segui(client, pranzo["id"])
    posta.risposta = healthai.Esito(False, 422, "calories: oltre il limite")

    giro(db, posta)
    giro(db, posta, ora=ORA + timedelta(hours=3))
    assert len(posta.chiamate) == 1
    assert "422" in db.get(HealthSync, pranzo["id"]).last_error

    recipe = db.get(Recipe, db.get(PlannedMeal, pranzo["id"]).recipe_id)
    recipe.calories = 650
    db.commit()
    posta.risposta = healthai.Esito(True, 200)
    giro(db, posta, ora=ORA + timedelta(hours=4))
    assert len(posta.chiamate) == 2


def test_l_allineamento_rimanda_tutto(client, db, settimana, posta):
    """Il comando di allineamento (`force`) rimanda anche quello che c'è già: dopo
    un periodo in cui healthAI ha perso i dati, l'upsert li rimette senza doppioni."""
    segui(client, pasto(settimana, 0, "Pranzo")["id"])
    giro(db, posta)
    giro(db, posta, force=True)
    assert len(posta.chiamate) == 2


def test_il_token_non_finisce_nei_log(client, db, settimana, caplog):
    """L'invio vero, con healthAI che non esiste: il giro non solleva, e nel log c'è
    l'errore ma non il segreto."""
    segui(client, pasto(settimana, 0, "Pranzo")["id"])
    with caplog.at_level("INFO"):
        g = healthai.sync(db, oggi=planner.today(), giorni=30, ora=ORA)
    assert g.falliti == 1
    assert "token-di-prova" not in caplog.text
