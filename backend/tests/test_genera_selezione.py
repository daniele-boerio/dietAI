"""Generare mezza settimana: quali giorni, quali pasti.

La generazione su tutta la settimana è la chiamata più cara dell'app, e quasi sempre
non serve intera: la colazione e gli spuntini se li prepara chi vuole, e i giorni già
pieni non si toccano. La dialog fa spuntare giorni e pasti; qui si controlla che il
filtro arrivi fino al modello (nel prompt ci finiscono solo le caselle scelte) e che
tutto il resto del piano resti esattamente com'era.
"""

import pytest

from app.services import planner

DAYS = 7
SLOTS = ["Colazione", "Pranzo", "Cena"]


def _fake_recipe(title, calories):
    return {
        "title": title,
        "description": "Ricetta di prova",
        "prep_time_min": 10,
        "cook_time_min": 15,
        "difficulty": "easy",
        "ingredients": [{"name": "zucchine", "quantity": 100, "unit": "g"}],
        "instructions": "1. Fai tutto.\n2. Servi.",
        "nutrition": {
            "calories": calories,
            "protein_g": 30.0,
            "carbs_g": 40.0,
            "fat_g": 15.0,
        },
        "tags": {"cuisine": "italiana", "type": "piatto unico"},
    }


class FakeModel:
    """Propone sempre la settimana intera: a scegliere le caselle è il nostro codice.

    Serve così apposta — se il filtro dei giorni e dei pasti non ci fosse, questa
    risposta riempirebbe tutto e i test lo vedrebbero.
    """

    ultimo_prompt = ""

    def __init__(self, user, giro):
        self.user = user
        self.giro = giro
        self.model = "finto/modello-di-test"
        self.supports_native_pdf = False

    def generate_json(self, system, prompt, **kwargs):
        FakeModel.ultimo_prompt = prompt
        return {
            "days": [
                {
                    "day_of_week": dow,
                    "meals": [
                        {
                            "slot_name": nome,
                            # Il numero del giro rende riconoscibile una rigenerazione:
                            # stessa casella, titolo diverso.
                            "recipe": _fake_recipe(f"{nome} {dow} g{self.giro}", 500),
                        }
                        for nome in SLOTS
                    ],
                }
                for dow in range(DAYS)
            ]
        }


@pytest.fixture()
def fake_ai(monkeypatch, client):
    giri = {"n": 0}

    def _client(db, user, role):
        giri["n"] += 1
        return FakeModel(user, giri["n"])

    monkeypatch.setattr(planner, "get_client", _client)
    res = client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    assert res.status_code == 200, res.text


def _genera(client, week_id, **corpo):
    return client.post(f"/api/planning/weeks/{week_id}/generate", json=corpo)


def _titoli(week):
    """{(giorno, pasto): titolo|None} — la settimana vista tutta insieme."""
    return {
        (d["day_of_week"], m["slot_name"]): (m["recipe"] or {}).get("title")
        for d in week["days"]
        for m in d["meals"]
    }


# ── Giorni ─────────────────────────────────────────────────────────────────────


def test_genera_solo_i_giorni_scelti(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()

    res = _genera(client, week["id"], days=[1, 2])
    assert res.status_code == 200, res.text

    dopo = res.json()
    assert dopo["generation"]["filled"] == 2 * len(SLOTS)
    titoli = _titoli(dopo)
    assert all(titoli[(dow, nome)] for dow in (1, 2) for nome in SLOTS)
    assert all(titoli[(dow, nome)] is None for dow in (0, 3, 4, 5, 6) for nome in SLOTS)


def test_i_giorni_non_scelti_non_finiscono_nel_prompt(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    _genera(client, week["id"], days=[2])

    da_riempire = FakeModel.ultimo_prompt.split("PASTI GIÀ ASSEGNATI")[0]
    assert "Mercoledì" in da_riempire
    assert "Lunedì" not in da_riempire


def test_quello_che_resta_fuori_ma_è_pieno_resta_nel_contesto(client, diet, fake_ai):
    """Generare mezza settimana non fa dimenticare l'altra metà.

    Il modello deve vedere i piatti già in programma o li ripropone tali e quali il
    giorno dopo: è la stessa ragione per cui `only_missing` passa i pasti conservati
    come `PASTI GIÀ ASSEGNATI`.
    """
    week = client.get("/api/planning/weeks/current").json()
    _genera(client, week["id"], days=[0])
    _genera(client, week["id"], days=[1])

    assert "Colazione 0 g1" in FakeModel.ultimo_prompt.split("PASTI GIÀ ASSEGNATI")[1]


# ── Pasti ──────────────────────────────────────────────────────────────────────


def test_genera_solo_i_pasti_scelti(client, diet, fake_ai):
    """«Le colazioni e gli spuntini ci penso io»: si pagano solo pranzi e cene."""
    week = client.get("/api/planning/weeks/current").json()
    cena = next(m["id"] for m in diet["meals"] if m["name"] == "Cena")

    res = _genera(client, week["id"], slot_ids=[cena])
    assert res.status_code == 200, res.text

    titoli = _titoli(res.json())
    assert all(titoli[(dow, "Cena")] for dow in range(DAYS))
    assert all(titoli[(dow, nome)] is None for dow in range(DAYS) for nome in ("Colazione", "Pranzo"))


def test_giorni_e_pasti_insieme(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    pranzo = next(m["id"] for m in diet["meals"] if m["name"] == "Pranzo")

    res = _genera(client, week["id"], days=[4, 5], slot_ids=[pranzo])
    assert res.json()["generation"]["filled"] == 2

    titoli = _titoli(res.json())
    assert titoli[(4, "Pranzo")] and titoli[(5, "Pranzo")]
    assert titoli[(4, "Cena")] is None


# ── Rigenerare solo una parte ──────────────────────────────────────────────────


def test_rigenerare_una_selezione_lascia_stare_il_resto(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    prima = _titoli(_genera(client, week["id"]).json())
    cena = next(m["id"] for m in diet["meals"] if m["name"] == "Cena")

    dopo = _titoli(
        _genera(client, week["id"], regenerate_all=True, slot_ids=[cena], days=[0]).json()
    )

    assert dopo[(0, "Cena")] != prima[(0, "Cena")]
    assert dopo[(0, "Pranzo")] == prima[(0, "Pranzo")]
    assert dopo[(1, "Cena")] == prima[(1, "Cena")]


# ── Quando non resta niente da fare ────────────────────────────────────────────


def test_selezione_vuota_lo_dice(client, diet, fake_ai):
    """Lista vuota è una scelta esplicita, non un campo dimenticato: non rifà tutto."""
    week = client.get("/api/planning/weeks/current").json()

    res = _genera(client, week["id"], days=[])
    assert res.status_code == 400
    assert "hai scelto" in res.json()["detail"]
    assert client.get("/api/planning/weeks/current").json()["meals_filled"] == 0


def test_selezione_gia_piena_lo_dice(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    _genera(client, week["id"], days=[0])

    res = _genera(client, week["id"], days=[0])
    assert res.status_code == 400
    assert "già pronti" in res.json()["detail"]


# ── Compatibilità ──────────────────────────────────────────────────────────────


def test_senza_selezione_genera_tutta_la_settimana(client, diet, fake_ai):
    """Il corpo è facoltativo: chi non lo manda ha il pulsante di sempre."""
    week = client.get("/api/planning/weeks/current").json()

    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.json()["generation"]["filled"] == DAYS * len(SLOTS)
