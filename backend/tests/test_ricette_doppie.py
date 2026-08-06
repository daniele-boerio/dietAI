"""Lo stesso piatto è una ricetta sola.

Il ricettario è l'archivio dei piatti, non il diario delle caselle: la colazione che si
ripete sette giorni è un piatto. Prima ogni casella si portava dietro la sua riga —
`create_recipe` a ogni pasto generato, `copy_recipe` a ogni settimana per i pasti fissi
— e l'archivio cresceva di una riga al giorno per lo stesso identico piatto.

Il rovescio della medaglia è che una riga condivisa, se la si modifica, cambierebbe
tutti i giorni che la usano: chi modifica da dentro un pasto deve staccarne una copia.
Metà di questi test guardano proprio lì.
"""

import json

import pytest

from app.models import PlannedMeal, Recipe
from app.routers import chat as chat_router
from app.services import planner
from app.services.recipes import merge_duplicate_recipes
from tests.test_flow import _fake_recipe

DAYS = 7

COLAZIONE = _fake_recipe(
    "Yogurt e frutta secca",
    400,
    [
        {"name": "yogurt greco", "quantity": 200, "unit": "g"},
        {"name": "noci", "quantity": 30, "unit": "g"},
    ],
)
PRANZO = _fake_recipe(
    "Pasta e zucchine",
    700,
    [
        {"name": "pasta", "quantity": 100, "unit": "g"},
        {"name": "zucchine", "quantity": 150, "unit": "g"},
    ],
)
CENA = _fake_recipe(
    "Pollo e insalata",
    600,
    [
        {"name": "petto di pollo", "quantity": 150, "unit": "g"},
        {"name": "insalata", "quantity": 80, "unit": "g"},
    ],
)


class ModelloRipetitivo:
    """Propone lo stesso identico piatto tutti i giorni — come fa chi fa colazione."""

    def __init__(self, user):
        self.user = user
        self.model = "finto/modello-di-test"
        self.supports_native_pdf = False

    def generate_json(self, system, prompt, **kwargs):
        return {
            "days": [
                {
                    "day_of_week": dow,
                    "meals": [
                        {"slot_name": "Colazione", "recipe": COLAZIONE},
                        {"slot_name": "Pranzo", "recipe": PRANZO},
                        {"slot_name": "Cena", "recipe": CENA},
                    ],
                }
                for dow in range(DAYS)
            ]
        }


@pytest.fixture()
def settimana_ripetitiva(client, diet, monkeypatch):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: ModelloRipetitivo(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})

    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text
    return res.json()


def ricettario(client) -> list[dict]:
    return client.get("/api/recipes?per_page=100").json()["items"]


def pasto(week: dict, dow: int, slot: str) -> dict:
    return next(m for m in week["days"][dow]["meals"] if m["slot_name"] == slot)


# ── Generazione ────────────────────────────────────────────────────────────────


def test_lo_stesso_piatto_sette_giorni_e_una_ricetta_sola(client, settimana_ripetitiva):
    items = ricettario(client)

    assert len(items) == 3
    assert sorted(r["title"] for r in items) == [
        "Pasta e zucchine",
        "Pollo e insalata",
        "Yogurt e frutta secca",
    ]


def test_tutte_le_caselle_puntano_alla_stessa_riga(client, settimana_ripetitiva):
    week = client.get("/api/planning/weeks/current").json()
    ids = {pasto(week, dow, "Colazione")["recipe"]["id"] for dow in range(DAYS)}

    assert len(ids) == 1


def test_la_spesa_conta_comunque_ogni_giorno(client, settimana_ripetitiva):
    """Una riga sola non vuol dire una porzione sola: si cucina sette volte."""
    lst = client.get("/api/shopping/current").json()
    items = {i["name"]: i for cat in lst["categories"] for i in cat["items"]}

    assert items["zucchine"]["quantity"] == pytest.approx(DAYS * 150)
    assert items["pasta"]["quantity"] == pytest.approx(DAYS * 100)


def test_generare_la_settimana_dopo_non_ricrea_gli_stessi_piatti(client, settimana_ripetitiva):
    nxt = client.get("/api/planning/weeks/next").json()
    client.post(f"/api/planning/weeks/{nxt['id']}/generate")

    assert len(ricettario(client)) == 3


def test_un_pasto_fisso_non_si_ricopia_a_ogni_settimana(client, settimana_ripetitiva):
    """`apply_recurring_meals` condivide la riga invece di clonarla ogni lunedì."""
    week = client.get("/api/planning/weeks/current").json()
    colazione = pasto(week, 0, "Colazione")
    client.put(
        f"/api/planning/meals/{colazione['id']}/recurring",
        json={"is_recurring": True, "recurring_rule": {"type": "daily"}},
    )

    nxt = client.get("/api/planning/weeks/next").json()

    assert len(ricettario(client)) == 3
    assert pasto(nxt, 3, "Colazione")["recipe"]["id"] == colazione["recipe"]["id"]


def test_il_ricettario_dice_dove_e_in_programma(client, settimana_ripetitiva):
    """Con una riga sola, «quante volte» lo racconta la cronologia d'uso."""
    week = client.get("/api/planning/weeks/current").json()
    recipe_id = pasto(week, 0, "Colazione")["recipe"]["id"]

    dettaglio = client.get(f"/api/recipes/{recipe_id}").json()
    assert len(dettaglio["usage_history"]) == DAYS


# ── Modificare una ricetta condivisa ───────────────────────────────────────────


class FakeChat:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, system, messages, **kwargs):
        return self.reply


def test_la_chat_modifica_solo_il_giorno_da_cui_parte(client, settimana_ripetitiva, monkeypatch):
    week = client.get("/api/planning/weeks/current").json()
    lunedi = pasto(week, 0, "Pranzo")
    martedi = pasto(week, 1, "Pranzo")
    assert lunedi["recipe"]["id"] == martedi["recipe"]["id"]

    modificata = {**PRANZO, "title": "Pasta e zucchine senza olio"}
    monkeypatch.setattr(
        chat_router,
        "get_client",
        lambda db, user, role: FakeChat(
            "Ecco fatto.\n[RECIPE_UPDATE]\n" + json.dumps(modificata)
        ),
    )

    res = client.post(
        f"/api/chat/meals/{lunedi['id']}/messages", json={"content": "togli l'olio"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["recipe_updated"] is True

    dopo = client.get("/api/planning/weeks/current").json()
    assert pasto(dopo, 0, "Pranzo")["recipe"]["title"] == "Pasta e zucchine senza olio"
    # Il martedì non l'ha chiesto nessuno: resta il piatto di prima.
    assert pasto(dopo, 1, "Pranzo")["recipe"]["title"] == "Pasta e zucchine"
    assert pasto(dopo, 0, "Pranzo")["recipe"]["id"] != pasto(dopo, 1, "Pranzo")["recipe"]["id"]


def test_la_copia_si_stacca_solo_quando_serve(client, diet, monkeypatch):
    """Una ricetta usata da una casella sola si modifica sul posto, senza doppioni."""
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: ModelloRipetitivo(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})

    week = client.get("/api/planning/weeks/current").json()
    solo_lunedi = pasto(week, 0, "Pranzo")
    client.put(
        f"/api/planning/meals/{solo_lunedi['id']}/assign",
        json={"recipe": {**PRANZO, **PRANZO["nutrition"]}},
    )

    prima = len(ricettario(client))
    modificata = {**PRANZO, "title": "Pasta e zucchine al limone"}
    monkeypatch.setattr(
        chat_router,
        "get_client",
        lambda db, user, role: FakeChat("Fatto.\n[RECIPE_UPDATE]\n" + json.dumps(modificata)),
    )
    client.post(f"/api/chat/meals/{solo_lunedi['id']}/messages", json={"content": "col limone"})

    assert len(ricettario(client)) == prima


def test_una_modifica_che_non_cambia_niente_non_lascia_una_copia(
    client, settimana_ripetitiva, monkeypatch
):
    """Il modello può rimandare la ricetta identica: non deve nascerne una seconda."""
    week = client.get("/api/planning/weeks/current").json()
    lunedi = pasto(week, 0, "Pranzo")

    monkeypatch.setattr(
        chat_router,
        "get_client",
        lambda db, user, role: FakeChat("Va già bene.\n[RECIPE_UPDATE]\n" + json.dumps(PRANZO)),
    )
    client.post(f"/api/chat/meals/{lunedi['id']}/messages", json={"content": "controlla"})

    assert len(ricettario(client)) == 3
    dopo = client.get("/api/planning/weeks/current").json()
    assert pasto(dopo, 0, "Pranzo")["recipe"]["id"] == pasto(dopo, 1, "Pranzo")["recipe"]["id"]


def test_la_chat_della_spesa_non_sdoppia_il_piatto_ripetuto(
    client, settimana_ripetitiva, monkeypatch
):
    """Cambiare un ingrediente in tutta la lista tocca due caselle con lo stesso piatto:
    ricevono la stessa modifica, e devono restare una riga sola."""
    week = client.get("/api/planning/weeks/current").json()
    lunedi = pasto(week, 0, "Pranzo")
    martedi = pasto(week, 1, "Pranzo")

    senza_zucchine = {
        **PRANZO,
        "title": "Pasta e peperoni",
        "ingredients": [
            {"name": "pasta", "quantity": 100, "unit": "g"},
            {"name": "peperoni", "quantity": 150, "unit": "g"},
        ],
    }
    payload = {
        "meals": [
            {"meal_id": lunedi["id"], "recipe": senza_zucchine},
            {"meal_id": martedi["id"], "recipe": senza_zucchine},
        ]
    }
    monkeypatch.setattr(
        chat_router,
        "get_client",
        lambda db, user, role: FakeChat(
            "Sostituite.\n[RECIPES_UPDATE]\n" + json.dumps(payload)
        ),
    )

    res = client.post(
        f"/api/chat/shopping/{week['id']}/messages",
        json={"content": "non trovo le zucchine"},
    )
    assert res.status_code == 200, res.text
    assert len(res.json()["changed_meals"]) == 2

    titoli = [r["title"] for r in ricettario(client)]
    assert titoli.count("Pasta e peperoni") == 1
    dopo = client.get("/api/planning/weeks/current").json()
    assert pasto(dopo, 0, "Pranzo")["recipe"]["id"] == pasto(dopo, 1, "Pranzo")["recipe"]["id"]
    # E gli altri cinque giorni sono rimasti col piatto di prima, in una riga sola.
    assert titoli.count("Pasta e zucchine") == 1


# ── "Ho mangiato altro" con lo stesso piatto in più giorni ─────────────────────


def test_annullare_il_salto_svuota_la_casella_giusta(client, settimana_ripetitiva):
    """La ricetta è la stessa tutti i giorni: la coda si riconosce dall'indirizzo, non
    dalla somiglianza — altrimenti si svuoterebbe la cena di martedì."""
    week = client.get("/api/planning/weeks/current").json()
    cena = pasto(week, 0, "Cena")

    res = client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})
    assert res.status_code == 200, res.text
    accodata = res.json()["moved_to"]
    # La settimana è piena: il piatto si accoda sul lunedì della prossima.
    assert accodata["next_week"] is True

    # Nel frattempo tutti gli altri giorni hanno ancora la loro cena.
    durante = client.get("/api/planning/weeks/current").json()
    assert all(pasto(durante, dow, "Cena")["recipe"] for dow in range(1, DAYS))

    client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": True})

    dopo = client.get("/api/planning/weeks/current").json()
    assert all(pasto(dopo, dow, "Cena")["recipe"] for dow in range(1, DAYS))
    nxt = client.get("/api/planning/weeks/next").json()
    assert pasto(nxt, 0, "Cena")["recipe"] is None


# ── La fusione dei doppioni già in tabella ─────────────────────────────────────


def _ricetta_doppia(db, user_id: int, **extra) -> Recipe:
    from app.services.recipes import _add_ingredients, _resolve, _clean_ingredients

    recipe = Recipe(
        user_id=user_id,
        title="Pasta e zucchine",
        instructions="1. Fai tutto.",
        calories=700,
        protein_g=30.0,
        carbs_g=40.0,
        fat_g=15.0,
        **extra,
    )
    db.add(recipe)
    db.flush()
    _add_ingredients(db, recipe, _resolve(db, _clean_ingredients(PRANZO["ingredients"])))
    db.flush()
    return recipe


def test_la_fusione_tiene_una_riga_sola_e_ci_sposta_i_pasti(client, db, diet):
    """Il caso di chi ha già l'archivio pieno: le righe gemelle si fondono."""
    user_id = client.get("/api/auth/me").json()["id"]
    tenuta = _ricetta_doppia(db, user_id, rating=4)
    doppia = _ricetta_doppia(db, user_id, is_favorite=True)
    db.commit()

    week = client.get("/api/planning/weeks/current").json()
    client.put(
        f"/api/planning/meals/{week['days'][0]['meals'][1]['id']}/assign",
        json={"recipe_id": doppia.id},
    )

    fusi = merge_duplicate_recipes(db)

    assert fusi == [("Pasta e zucchine", 1)]
    rimaste = db.query(Recipe).filter(Recipe.user_id == user_id).all()
    assert len(rimaste) == 1
    # Il giudizio sul piatto non si perde per strada: era su due righe, adesso è su una.
    assert rimaste[0].rating == 4
    assert rimaste[0].is_favorite is True
    # E la casella che puntava alla riga cancellata punta a quella tenuta, non a NULL.
    assert (
        db.query(PlannedMeal).filter(PlannedMeal.recipe_id == rimaste[0].id).count() == 1
    )


def test_la_fusione_non_tocca_piatti_diversi(client, db, diet):
    user_id = client.get("/api/auth/me").json()["id"]
    _ricetta_doppia(db, user_id)
    _ricetta_doppia(db, user_id, description="con più zucchine")  # stessa spesa: gemella
    diversa = _ricetta_doppia(db, user_id)
    diversa.calories = 750  # macro diversi: piatto diverso
    db.commit()

    merge_duplicate_recipes(db)

    assert db.query(Recipe).filter(Recipe.user_id == user_id).count() == 2


def test_rifare_la_fusione_non_fa_niente(client, db, diet, settimana_ripetitiva):
    assert merge_duplicate_recipes(db) == []
