"""Il percorso completo: dieta → piano generato → lista della spesa → blocco.

Claude è sostituito da una finta risposta: qui si verifica la logica nostra
(struttura della settimana, aggregazione della spesa, regole di blocco), non la
qualità delle ricette.
"""

import pytest

from app.services import planner
from app.utils.units import format_quantity, price_for, to_base

DAYS = 7


def _fake_recipe(title, calories, ingredients):
    return {
        "title": title,
        "description": "Ricetta di prova",
        "prep_time_min": 10,
        "cook_time_min": 15,
        "difficulty": "easy",
        "ingredients": ingredients,
        "instructions": "1. Fai tutto.\n2. Servi.",
        "nutrition": {
            "calories": calories,
            "protein_g": 30.0,
            "carbs_g": 40.0,
            "fat_g": 15.0,
        },
        "tags": {"cuisine": "italiana", "type": "piatto unico"},
    }


class FakeClaude:
    """Sostituto di ClaudeClient: restituisce un piano coerente con gli slot chiesti."""

    def __init__(self, user):
        self.user = user

    def generate_json(self, system, prompt, **kwargs):
        days = []
        for dow in range(DAYS):
            days.append(
                {
                    "day_of_week": dow,
                    "meals": [
                        {
                            "slot_name": "Colazione",
                            "recipe": _fake_recipe(
                                f"Colazione {dow}",
                                400,
                                [
                                    {"name": "latte", "quantity": 200, "unit": "ml"},
                                    {"name": "fiocchi d'avena", "quantity": 60, "unit": "g"},
                                ],
                            ),
                        },
                        {
                            "slot_name": "Pranzo",
                            "recipe": _fake_recipe(
                                f"Pranzo {dow}",
                                700,
                                [
                                    {"name": "pasta", "quantity": 100, "unit": "g"},
                                    {"name": "zucchine", "quantity": 0.15, "unit": "kg"},
                                    {"name": "olio extravergine di oliva", "quantity": 1,
                                     "unit": "cucchiai"},
                                ],
                            ),
                        },
                        {
                            "slot_name": "Cena",
                            "recipe": _fake_recipe(
                                f"Cena {dow}",
                                600,
                                [
                                    {"name": "petto di pollo", "quantity": 150, "unit": "g"},
                                    {"name": "zucchine", "quantity": 100, "unit": "g"},
                                ],
                            ),
                        },
                    ],
                }
            )
        return {"days": days, "ingredient_reuse_notes": "Zucchine divise tra pranzo e cena."}


@pytest.fixture()
def fake_ai(monkeypatch, client):
    """Sostituisce Claude e dà all'utente una API key finta (serve a costruire il client)."""
    monkeypatch.setattr(planner, "ClaudeClient", FakeClaude)
    res = client.put("/api/auth/api-key", json={"api_key": "sk-ant-chiave-finta-per-i-test"})
    assert res.status_code == 200, res.text


# ── Struttura ──────────────────────────────────────────────────────────────────


def test_login_espone_lo_stato_di_onboarding(client):
    me = client.get("/api/auth/me").json()
    assert me["email"] == "test@dietai.local"
    assert me["has_api_key"] is False
    assert me["has_active_diet"] is False


def test_senza_dieta_la_settimana_non_esiste(client):
    assert client.get("/api/planning/weeks/current").status_code == 400


def test_la_settimana_nasce_con_una_casella_per_pasto(client, diet):
    week = client.get("/api/planning/weeks/current").json()

    assert len(week["days"]) == DAYS
    assert week["meals_total"] == DAYS * 3
    assert week["meals_filled"] == 0
    assert [d["day_name"] for d in week["days"]][:2] == ["Lunedì", "Martedì"]
    # I target vengono dalla dieta, anche prima che esista una ricetta.
    assert week["days"][0]["meals"][0]["target"]["calories"] == 400


def test_modificare_la_dieta_riallinea_le_settimane(client, diet):
    client.get("/api/planning/weeks/current")

    meals = [m for m in diet["meals"] if m["name"] != "Colazione"]
    res = client.put(f"/api/diet/{diet['id']}/meals", json={"meals": meals})
    assert res.status_code == 200

    week = client.get("/api/planning/weeks/current").json()
    assert week["meals_total"] == DAYS * 2
    assert all(len(d["meals"]) == 2 for d in week["days"])


# ── Generazione ────────────────────────────────────────────────────────────────


def test_generazione_riempie_la_settimana(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text

    generated = res.json()
    assert generated["generation"]["filled"] == DAYS * 3
    assert generated["meals_filled"] == DAYS * 3
    assert generated["days"][0]["meals"][0]["recipe"]["title"] == "Colazione 0"
    # I totali giornalieri si calcolano dalle ricette assegnate.
    assert generated["days"][0]["totals"]["calories"] == 1700


def test_la_lista_della_spesa_aggrega_e_sottrae(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    lst = client.get("/api/shopping/current").json()
    items = {i["name"]: i for cat in lst["categories"] for i in cat["items"]}

    # Zucchine: 150 g a pranzo + 100 g a cena, per sette giorni, in unità diverse.
    assert items["zucchine"]["quantity"] == pytest.approx(7 * 250)
    assert items["zucchine"]["unit"] == "g"
    assert items["zucchine"]["label"] == "1,8 kg"
    # L'olio è tra gli ingredienti di base? No, in questo test non lo è: deve esserci.
    assert "olio extravergine di oliva" in items
    assert lst["estimated_cost"] > 0


def test_gli_ingredienti_di_base_non_entrano_in_lista(client, diet, fake_ai):
    client.post("/api/config/base-ingredients", json={"ingredient_name": "olio extravergine di oliva"})

    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    lst = client.get("/api/shopping/current").json()
    names = [i["name"] for cat in lst["categories"] for i in cat["items"]]
    assert "olio extravergine di oliva" not in names
    assert "zucchine" in names


def test_la_dispensa_scala_le_quantita(client, diet, fake_ai):
    # 1 kg di zucchine in casa: la lista deve chiederne 750 g invece di 1750.
    client.post(
        "/api/config/pantry",
        json={"ingredient_name": "zucchine", "quantity": 1, "unit": "kg"},
    )

    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    lst = client.get("/api/shopping/current").json()
    items = {i["name"]: i for cat in lst["categories"] for i in cat["items"]}
    assert items["zucchine"]["quantity"] == pytest.approx(750)


# ── Blocco settimanale ─────────────────────────────────────────────────────────


def test_la_spesa_completata_blocca_il_piano(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    lst = client.get("/api/shopping/current").json()
    first = lst["categories"][0]["items"][0]
    assert client.put(f"/api/shopping/items/{first['id']}/check", json={"is_checked": True}).status_code == 200

    res = client.post("/api/shopping/current/complete")
    assert res.status_code == 200, res.text
    assert "week_locked_until" in res.json()

    locked = client.get("/api/planning/weeks/current").json()
    assert locked["is_locked"] is True
    assert locked["status"] == "locked"

    # A piano bloccato non si rigenera niente.
    meal_id = locked["days"][0]["meals"][0]["id"]
    assert client.post(f"/api/planning/meals/{meal_id}/regenerate").status_code == 409
    assert client.post(f"/api/planning/weeks/{locked['id']}/generate").status_code == 409

    # Gli articoli spuntati sono finiti in dispensa.
    pantry = client.get("/api/config/pantry").json()
    assert any(p["name"] == first["name"] for p in pantry)

    # Ma il tracking (dire "l'ho seguito") resta possibile.
    assert client.put(
        f"/api/planning/meals/{meal_id}/followed", json={"is_followed": True}
    ).status_code == 200


def test_la_settimana_prossima_resta_modificabile(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    client.post("/api/shopping/current/complete")

    nxt = client.get("/api/planning/weeks/next").json()
    assert nxt["is_locked"] is False
    assert client.post(f"/api/planning/weeks/{nxt['id']}/generate").status_code == 200


def test_lo_sblocco_manuale_riapre_il_piano(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    client.post("/api/shopping/current/complete")

    res = client.post(f"/api/planning/weeks/{week['id']}/unlock")
    assert res.status_code == 200
    assert res.json()["is_locked"] is False


# ── Pasti fissi e ricettario ───────────────────────────────────────────────────


def test_un_pasto_fisso_non_viene_rigenerato(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    week = client.get("/api/planning/weeks/current").json()
    meal = week["days"][0]["meals"][0]
    original_title = meal["recipe"]["title"]

    res = client.put(
        f"/api/planning/meals/{meal['id']}/recurring",
        json={"is_recurring": True, "recurring_rule": {"type": "daily"}},
    )
    assert res.status_code == 200
    assert res.json()["is_recurring"] is True

    # Rigenerando la settimana il pasto fisso resta quello che era.
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    after = client.get("/api/planning/weeks/current").json()
    assert after["days"][0]["meals"][0]["recipe"]["title"] == original_title


def test_i_voti_finiscono_nel_ricettario(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    week = client.get("/api/planning/weeks/current").json()
    recipe_id = week["days"][0]["meals"][0]["recipe"]["id"]

    client.put(f"/api/recipes/{recipe_id}/rate", json={"rating": 5})
    client.put(f"/api/recipes/{recipe_id}/favorite", json={"is_favorite": True})

    favorites = client.get("/api/recipes", params={"is_favorite": True}).json()
    assert favorites["total"] == 1
    assert favorites["items"][0]["rating"] == 5


def test_il_tracking_confronta_pianificato_e_target(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    tracking = client.get("/api/tracking/weekly").json()
    assert tracking["weekly_summary"]["avg_daily_calories_planned"] == 1700
    assert tracking["weekly_summary"]["avg_daily_calories_target"] == 1700
    assert tracking["weekly_summary"]["compliance_pct"] == 100.0
    assert tracking["days"][0]["totals"]["color"] == "green"


# ── Configurazione ─────────────────────────────────────────────────────────────


def test_gli_esclusi_accettano_anche_nomi_liberi(client):
    res = client.post("/api/config/excluded", json={"ingredient_name": "frutti di mare", "reason": "allergia"})
    assert res.status_code == 201
    assert res.json()["name"] == "frutti di mare"

    # Due volte lo stesso alimento non ha senso.
    assert client.post("/api/config/excluded", json={"ingredient_name": "frutti di mare"}).status_code == 409


def test_i_nomi_degli_ingredienti_si_normalizzano(client):
    a = client.post("/api/config/pantry", json={"ingredient_name": "Zucchine fresche"}).json()
    assert a["name"] == "zucchine"
    # Lo stesso ingrediente scritto diversamente è sempre la stessa riga.
    assert client.post("/api/config/pantry", json={"ingredient_name": "ZUCCHINE"}).status_code == 409


# ── Unità di misura ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "quantity,unit,expected",
    [
        (1.5, "kg", (1500, "g")),
        (2, "cucchiai", (30, "ml")),
        (0.5, "l", (500, "ml")),
        (3, "spicchi", (3, "unità")),
        (1, "q.b.", (1, "q.b.")),  # sconosciuta: si lascia com'è
    ],
)
def test_conversione_unita(quantity, unit, expected):
    assert to_base(quantity, unit) == expected


def test_formattazione_quantita():
    assert format_quantity(1750, "g") == "1,8 kg"
    assert format_quantity(200, "g") == "200 g"
    assert format_quantity(2.0, "unità") == "2 unità"


def test_stima_prezzo():
    assert price_for(500, "g", 9.5, "kg") == pytest.approx(4.75)
    # Prezzo al kg per un ingrediente contato a pezzi: nessuna stima inventata.
    assert price_for(2, "unità", 9.5, "kg") is None
