"""Pasti che l'utente gestisce da sé: l'AI non li genera, ma contano nella giornata.

È la parte che si sbaglia facilmente: saltare la generazione è ovvio, ricordarsi che
quel pasto viene comunque mangiato lo è molto meno. Senza la seconda metà, il tracking
mostrerebbe un buco di 400 kcal al giorno e un'aderenza rovinata per un pasto che
invece rispetta la dieta alla lettera.
"""

import pytest

from app.services import planner
from tests.test_flow import DAYS, FakeModel


@pytest.fixture()
def fake_ai(monkeypatch, client):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})


@pytest.fixture()
def diet_con_colazione_mia(client):
    """Colazione a carico dell'utente, pranzo e cena a carico dell'AI."""
    res = client.post(
        "/api/diet/manual",
        json={
            "meals": [
                {"name": "Colazione", "order": 0, "calories": 400, "protein_g": 20,
                 "carbs_g": 50, "fat_g": 12, "auto_generate": False},
                {"name": "Pranzo", "order": 1, "calories": 700, "protein_g": 40,
                 "carbs_g": 80, "fat_g": 20},
                {"name": "Cena", "order": 2, "calories": 600, "protein_g": 45,
                 "carbs_g": 50, "fat_g": 22},
            ]
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_il_flag_si_salva_e_si_rilegge(client, diet_con_colazione_mia):
    meals = {m["name"]: m for m in client.get("/api/diet/current").json()["meals"]}

    assert meals["Colazione"]["auto_generate"] is False
    assert meals["Pranzo"]["auto_generate"] is True


def test_di_default_i_pasti_li_genera_l_ai(client, diet):
    assert all(m["auto_generate"] for m in diet["meals"])


def test_la_colazione_mia_non_conta_tra_i_pasti_da_riempire(client, diet_con_colazione_mia):
    week = client.get("/api/planning/weeks/current").json()

    # 7 giorni × 2 pasti generabili, non × 3.
    assert week["meals_total"] == DAYS * 2
    assert week["meals_self_managed"] == DAYS
    # La casella però esiste ancora nella griglia, marcata.
    colazione = week["days"][0]["meals"][0]
    assert colazione["slot_name"] == "Colazione"
    assert colazione["self_managed"] is True
    assert colazione["recipe"] is None


def test_la_generazione_salta_il_pasto_gestito_dall_utente(
    client, diet_con_colazione_mia, fake_ai
):
    """Il modello finto propone anche la colazione: va ignorata comunque."""
    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text

    generated = res.json()
    assert generated["generation"]["filled"] == DAYS * 2

    for day in generated["days"]:
        per_nome = {m["slot_name"]: m for m in day["meals"]}
        assert per_nome["Colazione"]["recipe"] is None
        assert per_nome["Pranzo"]["recipe"] is not None
        assert per_nome["Cena"]["recipe"] is not None


def test_i_macro_del_pasto_mio_restano_nel_totale_del_giorno(
    client, diet_con_colazione_mia, fake_ai
):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    day = client.get("/api/planning/weeks/current").json()["days"][0]

    # 400 (colazione, dal target) + 700 + 600 dalle ricette generate.
    assert day["totals"]["calories"] == 1700
    assert day["totals"]["target_calories"] == 1700


def test_il_tracking_considera_centrato_il_pasto_gestito_dall_utente(
    client, diet_con_colazione_mia, fake_ai
):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    tracking = client.get("/api/tracking/weekly").json()
    colazione = tracking["days"][0]["meals"][0]

    assert colazione["self_managed"] is True
    assert colazione["planned"]["calories"] == 400  # dato per centrato sul target
    assert colazione["color"] == "green"

    summary = tracking["weekly_summary"]
    assert summary["avg_daily_calories_planned"] == 1700
    assert summary["compliance_pct"] == 100.0
    # Tutti e tre i pasti entrano nel conto, non solo i due generati.
    assert summary["meals_planned"] == DAYS * 3


def test_la_lista_della_spesa_ignora_il_pasto_gestito_dall_utente(
    client, diet_con_colazione_mia, fake_ai
):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    lst = client.get("/api/shopping/current").json()
    names = [i["name"] for cat in lst["categories"] for i in cat["items"]]

    # Latte e avena erano solo nella colazione: non essendo generata, non si comprano.
    assert "latte" not in names
    assert "fiocchi d'avena" not in names
    assert "zucchine" in names


def test_se_tutti_i_pasti_sono_miei_non_c_e_niente_da_generare(client, fake_ai):
    client.post(
        "/api/diet/manual",
        json={
            "meals": [
                {"name": "Colazione", "order": 0, "calories": 400, "protein_g": 20,
                 "carbs_g": 50, "fat_g": 12, "auto_generate": False},
                {"name": "Cena", "order": 1, "calories": 600, "protein_g": 45,
                 "carbs_g": 50, "fat_g": 22, "auto_generate": False},
            ]
        },
    )
    week = client.get("/api/planning/weeks/current").json()

    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 400
    assert "gestiti da te" in res.json()["detail"]


def test_il_flag_si_puo_togliere_e_il_pasto_torna_generabile(
    client, diet_con_colazione_mia, fake_ai
):
    meals = client.get("/api/diet/current").json()["meals"]
    for m in meals:
        m["auto_generate"] = True
    client.put(f"/api/diet/{diet_con_colazione_mia['id']}/meals", json={"meals": meals})

    week = client.get("/api/planning/weeks/current").json()
    assert week["meals_total"] == DAYS * 3

    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.json()["generation"]["filled"] == DAYS * 3
