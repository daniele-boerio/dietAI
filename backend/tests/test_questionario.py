"""La dieta calcolata dal questionario, per chi non è mai stato da un nutrizionista."""

import pytest

from app.utils.nutrition import KCAL_PER_G, basal_metabolic_rate, compute_plan

RISPOSTE = {
    "sex": "uomo",
    "age": 30,
    "height_cm": 180,
    "weight_kg": 80,
    "activity": "moderato",
    "goal": "mantenere",
    "meals_count": 4,
}


# ── La formula ─────────────────────────────────────────────────────────────────


def test_mifflin_st_jeor_da_i_numeri_di_riferimento():
    # 10×80 + 6.25×180 − 5×30 + 5 = 1780
    assert basal_metabolic_rate("uomo", 30, 180, 80) == pytest.approx(1780)
    # La stessa persona, donna: 1780 − 5 − 161
    assert basal_metabolic_rate("donna", 30, 180, 80) == pytest.approx(1614)


def test_il_taglio_e_una_percentuale_del_fabbisogno():
    mantiene = compute_plan(**RISPOSTE)
    dimagrisce = compute_plan(**{**RISPOSTE, "goal": "dimagrire"})

    assert mantiene["daily_calories"] == mantiene["tdee"]
    assert dimagrisce["daily_calories"] == pytest.approx(mantiene["tdee"] * 0.85, abs=2)
    # Chi taglia mangia più proteine: è la massa magra che si difende in deficit.
    assert dimagrisce["protein_g"] > mantiene["protein_g"]


def test_non_si_scende_mai_sotto_il_metabolismo_basale():
    """Il caso che fa danno: piccola, sedentaria, in deficit."""
    piano = compute_plan(
        sex="donna", age=55, height_cm=155, weight_kg=50,
        activity="sedentario", goal="dimagrire", meals_count=3,
    )
    assert piano["daily_calories"] >= piano["bmr"]
    assert piano["daily_calories"] >= 1200


def test_i_macro_tornano_alle_calorie():
    piano = compute_plan(**RISPOSTE)
    dai_macro = (
        piano["protein_g"] * KCAL_PER_G["protein_g"]
        + piano["carbs_g"] * KCAL_PER_G["carbs_g"]
        + piano["fat_g"] * KCAL_PER_G["fat_g"]
    )
    assert dai_macro == pytest.approx(piano["daily_calories"], abs=5)


@pytest.mark.parametrize("meals_count", [3, 4, 5, 6])
def test_la_somma_dei_pasti_e_esattamente_il_totale_del_giorno(meals_count):
    """L'arrotondamento non deve mangiarsi calorie: è la stessa regola di lib/macros.js."""
    piano = compute_plan(**{**RISPOSTE, "meals_count": meals_count})

    assert len(piano["meals"]) == meals_count
    assert sum(m["calories"] for m in piano["meals"]) == piano["daily_calories"]
    for campo in ("protein_g", "carbs_g", "fat_g"):
        assert sum(m[campo] for m in piano["meals"]) == pytest.approx(piano[campo], abs=0.05)


def test_le_carbo_non_vanno_mai_sotto_zero():
    """Peso alto e calorie basse: le proteine in g/kg sfonderebbero il budget."""
    piano = compute_plan(
        sex="donna", age=60, height_cm=150, weight_kg=110,
        activity="sedentario", goal="dimagrire", meals_count=3,
    )
    assert piano["carbs_g"] >= 0
    assert piano["protein_g"] * 4 <= piano["daily_calories"] * 0.41


@pytest.mark.parametrize(
    "campo,valore",
    [("sex", "altro"), ("activity", "tantissimo"), ("goal", "boh"), ("meals_count", 9)],
)
def test_valori_fuori_elenco(campo, valore):
    with pytest.raises(ValueError):
        compute_plan(**{**RISPOSTE, campo: valore})


# ── Quali pasti si fanno ───────────────────────────────────────────────────────


def test_i_pasti_si_scelgono_uno_per_uno():
    piano = compute_plan(**RISPOSTE, meals=["pranzo", "cena"])

    assert [m["key"] for m in piano["meals"]] == ["pranzo", "cena"]
    assert sum(m["calories"] for m in piano["meals"]) == piano["daily_calories"]


def test_saltare_la_colazione_non_accorcia_la_giornata():
    """Chi non fa colazione mangia le stesse calorie in meno volte, non di meno."""
    con = compute_plan(**RISPOSTE, meals=["colazione", "pranzo", "cena"])
    senza = compute_plan(**RISPOSTE, meals=["pranzo", "cena"])

    assert senza["daily_calories"] == con["daily_calories"]
    assert sum(m["calories"] for m in senza["meals"]) == senza["daily_calories"]
    # Le calorie della colazione sono andate sugli altri due, in proporzione.
    per_nome = {m["key"]: m["calories"] for m in con["meals"]}
    assert all(m["calories"] > per_nome[m["key"]] for m in senza["meals"])


def test_l_ordine_e_quello_della_giornata_non_quello_dei_clic():
    piano = compute_plan(**RISPOSTE, meals=["cena", "colazione", "spuntino_mattina"])

    assert [m["key"] for m in piano["meals"]] == ["colazione", "spuntino_mattina", "cena"]
    assert [m["order"] for m in piano["meals"]] == [0, 1, 2]


def test_un_pasto_inventato_e_un_errore():
    with pytest.raises(ValueError):
        compute_plan(**RISPOSTE, meals=["merenda_di_mezzanotte"])


def test_zero_pasti_non_e_una_dieta():
    with pytest.raises(ValueError):
        compute_plan(**RISPOSTE, meals=[])


# ── Il lucchetto: i totali scritti a mano ──────────────────────────────────────


def test_i_totali_corretti_a_mano_vincono_sulla_formula():
    piano = compute_plan(
        **RISPOSTE,
        meals=["colazione", "pranzo", "cena"],
        targets={"calories": 2400, "protein_g": 180, "carbs_g": 240, "fat_g": 70},
    )

    assert piano["daily_calories"] == 2400
    assert piano["protein_g"] == 180
    assert sum(m["calories"] for m in piano["meals"]) == 2400
    # Quello che direbbe la formula resta a disposizione: è il metro di paragone.
    assert piano["proposed"]["daily_calories"] != 2400


def test_a_mano_si_scende_anche_sotto_i_pavimenti_della_formula():
    """I minimi difendono un calcolo automatico, non discutono una dieta scritta."""
    piano = compute_plan(
        sex="donna", age=30, height_cm=165, weight_kg=60,
        activity="sedentario", goal="dimagrire",
        meals=["pranzo", "cena"],
        targets={"calories": 1100, "protein_g": 90, "carbs_g": 100, "fat_g": 35},
    )
    assert piano["daily_calories"] == 1100


# ── L'endpoint ─────────────────────────────────────────────────────────────────


def test_il_questionario_crea_una_dieta_come_le_altre(client):
    res = client.post("/api/diet/questionnaire", json=RISPOSTE)
    assert res.status_code == 200, res.text
    dieta = res.json()

    assert dieta["source"] == "questionario"
    assert len(dieta["meals"]) == 4
    assert sum(m["calories"] for m in dieta["meals"]) == dieta["total_daily_calories"]
    # I pasti sono MealSlot veri: la settimana ci si costruisce sopra da sola.
    settimana = client.get("/api/planning/weeks/current").json()
    assert len(settimana["days"][0]["meals"]) == 4


def test_le_risposte_restano_per_poter_ricalcolare(client):
    """Il peso cambia: riaprire il questionario deve costare tre secondi."""
    client.post("/api/diet/questionnaire", json=RISPOSTE)

    dieta = client.get("/api/diet/current").json()
    assert dieta["profile"]["weight_kg"] == 80
    assert dieta["profile"]["goal"] == "mantenere"


def test_rifarlo_sostituisce_la_dieta_e_non_ne_lascia_due_attive(client):
    prima = client.post("/api/diet/questionnaire", json=RISPOSTE).json()
    dopo = client.post(
        "/api/diet/questionnaire", json={**RISPOSTE, "weight_kg": 75, "goal": "dimagrire"}
    ).json()

    assert dopo["id"] != prima["id"]
    assert client.get("/api/diet/current").json()["id"] == dopo["id"]
    assert dopo["total_daily_calories"] < prima["total_daily_calories"]


def test_una_risposta_fuori_elenco_e_un_400(client):
    res = client.post("/api/diet/questionnaire", json={**RISPOSTE, "activity": "tantissimo"})
    assert res.status_code == 400


def test_anche_l_ospite_puo_calcolarsi_la_dieta(guest_client):
    """Non serve nessuna chiamata AI: è una formula, e vale per tutti."""
    res = guest_client.post("/api/diet/questionnaire", json=RISPOSTE)
    assert res.status_code == 200, res.text
    assert guest_client.get("/api/auth/me").json()["has_active_diet"] is True


def test_le_opzioni_del_questionario_le_serve_il_backend(client):
    opzioni = client.get("/api/diet/questionnaire/options").json()

    assert "uomo" in opzioni["sexes"]
    assert {o["key"] for o in opzioni["goals"]} == {"dimagrire", "mantenere", "aumentare"}
    assert all(o["hint"] for o in opzioni["activity_levels"])


def test_le_opzioni_portano_i_pesi_dei_pasti(client):
    """Col peso il frontend divide in locale mentre si spuntano, senza una chiamata a clic."""
    opzioni = client.get("/api/diet/questionnaire/options").json()

    assert [m["key"] for m in opzioni["meals"]][:2] == ["colazione", "spuntino_mattina"]
    assert all(m["weight"] > 0 and m["name"] for m in opzioni["meals"])
    assert opzioni["default_meals"]["3"] == ["colazione", "pranzo", "cena"]


def test_l_anteprima_non_salva_niente(client):
    """In mezzo ai due passi non deve nascere una dieta che nessuno ha ancora visto."""
    res = client.post("/api/diet/questionnaire/preview", json=RISPOSTE)

    assert res.status_code == 200, res.text
    assert res.json()["daily_calories"] > 0
    assert client.get("/api/diet/current").status_code == 404


def test_i_pasti_scelti_diventano_le_caselle_della_settimana(client):
    dieta = client.post(
        "/api/diet/questionnaire", json={**RISPOSTE, "meals": ["pranzo", "cena"]}
    ).json()

    assert [m["name"] for m in dieta["meals"]] == ["Pranzo", "Cena"]
    settimana = client.get("/api/planning/weeks/current").json()
    assert [m["slot_name"] for m in settimana["days"][0]["meals"]] == ["Pranzo", "Cena"]


def test_i_pasti_scelti_restano_per_riaprire_il_questionario(client):
    client.post("/api/diet/questionnaire", json={**RISPOSTE, "meals": ["pranzo", "cena"]})

    assert client.get("/api/diet/current").json()["profile"]["meals"] == ["pranzo", "cena"]


def test_i_pasti_restano_scritti_anche_dicendo_solo_quanti(client):
    """Chi non li sceglie uno per uno riapre comunque il questionario già spuntato."""
    client.post("/api/diet/questionnaire", json={**RISPOSTE, "meals_count": 3})

    assert client.get("/api/diet/current").json()["profile"]["meals"] == [
        "colazione",
        "pranzo",
        "cena",
    ]


def test_i_totali_sbloccati_arrivano_fino_ai_pasti(client):
    dieta = client.post(
        "/api/diet/questionnaire",
        json={
            **RISPOSTE,
            "meals": ["colazione", "pranzo", "cena"],
            "targets": {"calories": 2400, "protein_g": 180, "carbs_g": 240, "fat_g": 70},
        },
    ).json()

    assert dieta["total_daily_calories"] == 2400
    assert sum(m["calories"] for m in dieta["meals"]) == 2400
    assert sum(m["protein_g"] for m in dieta["meals"]) == pytest.approx(180, abs=0.05)
    # Nelle note resta scritto che i numeri sono stati forzati, e da cosa.
    assert "a mano" in dieta["notes"]


def test_un_pasto_inventato_dal_client_e_un_400(client):
    res = client.post("/api/diet/questionnaire", json={**RISPOSTE, "meals": ["brunch"]})
    assert res.status_code == 400
