"""Le frequenze settimanali della dieta: «pesce 2-3 volte, carne rossa al massimo una».

Tre cose da difendere: che il conto sia giusto (cosa vale come «una volta»), che la
generazione assegni le proteine prima di chiamare il modello invece di sperare che le
alterni, e che le frequenze non si perdano cambiando dieta.
"""

import random

import pytest

from app.services import planner
from app.utils import frequencies as freq
from tests.test_flow import FakeModel


# ── Il catalogo e il conto ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "categoria, nome, gruppo",
    [
        ("pesce", "salmone", "pesce"),
        ("carne", "petto di pollo", "carne_bianca"),
        ("carne", "fesa di tacchino", "carne_bianca"),
        ("carne", "manzo", "carne_rossa"),
        ("carne", "prosciutto crudo", "salumi"),
        ("latticini", "mozzarella", "formaggi"),
        ("latticini", "yogurt greco", None),  # lo yogurt non è la porzione di formaggi
        ("uova", "uova", "uova"),
        ("verdura", "zucchine", None),
    ],
)
def test_a_che_gruppo_appartiene_un_ingrediente(categoria, nome, gruppo):
    assert freq.food_of(categoria, nome) == gruppo


def test_le_frequenze_si_puliscono():
    pulite = freq.clean([
        {"food": "pesce", "min": 2, "max": 3},
        {"food": "carne_rossa", "min": -1, "max": 1},
        {"food": "inventato", "min": 1},
        {"food": "legumi", "min": 4, "max": 2},  # max sotto il min: si porta al min
        {"food": "uova", "min": 0, "max": None},  # nessun vincolo: sparisce
    ])
    assert pulite == [
        {"food": "pesce", "min": 2, "max": 3},
        {"food": "legumi", "min": 4, "max": 4},
        {"food": "carne_rossa", "min": 0, "max": 1},
    ]


def test_il_resoconto_dice_cosa_manca_e_cosa_avanza():
    righe = freq.report(
        [{"food": "pesce", "min": 2, "max": 3}, {"food": "carne_rossa", "min": 0, "max": 1}],
        {"pesce": 1, "carne_rossa": 2},
    )
    assert [(r["food"], r["status"]) for r in righe] == [
        ("pesce", "sotto"), ("carne_rossa", "sopra")
    ]


# ── L'assegnazione ─────────────────────────────────────────────────────────────


def test_i_minimi_si_assegnano_e_si_sparpagliano():
    """Pesce due volte su sette cene: due giorni diversi, e lontani."""
    slots = [(d, 100 + d) for d in range(7)]
    posto = freq.assign([{"food": "pesce", "min": 2, "max": 3}], {}, slots, rng=random.Random(1))

    giorni = sorted(mid - 100 for mid, a in posto.items() if a["food"] == "pesce")
    assert len(giorni) == 2
    assert giorni[1] - giorni[0] >= 3


def test_quello_che_la_settimana_ha_gia_conta():
    slots = [(d, d) for d in range(5)]
    posto = freq.assign([{"food": "pesce", "min": 2}], {"pesce": 2}, slots, rng=random.Random(0))
    assert all(a["food"] is None for a in posto.values())


def test_un_gruppo_al_massimo_si_vieta_nelle_caselle_libere():
    slots = [(d, d) for d in range(4)]
    posto = freq.assign(
        [{"food": "carne_rossa", "min": 1, "max": 1}], {}, slots, rng=random.Random(0)
    )
    rosse = [a for a in posto.values() if a["food"] == "carne_rossa"]
    libere = [a for a in posto.values() if a["food"] is None]
    assert len(rosse) == 1
    assert all(a["avoid"] == ["carne_rossa"] for a in libere)
    assert "ma non carne rossa" in freq.prompt_hint(libere[0])


def test_piu_minimi_che_caselle_passa_chi_e_piu_lontano():
    slots = [(0, 1), (1, 2)]
    posto = freq.assign(
        [{"food": "pesce", "min": 3}, {"food": "legumi", "min": 1}], {}, slots,
        rng=random.Random(0),
    )
    assert sorted(a["food"] for a in posto.values()) == ["pesce", "pesce"]


# ── Dalla dieta alla generazione ───────────────────────────────────────────────


class ModelloCheRicorda(FakeModel):
    prompt = None

    def generate_json(self, system, prompt, **kwargs):
        ModelloCheRicorda.prompt = prompt
        return super().generate_json(system, prompt, **kwargs)


@pytest.fixture()
def con_frequenze(client, diet, monkeypatch):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: ModelloCheRicorda(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    res = client.put(
        f"/api/diet/{diet['id']}/frequencies",
        json={"frequencies": [
            {"food": "pesce", "min": 2, "max": 3},
            {"food": "carne_rossa", "min": 0, "max": 1},
        ]},
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_la_dieta_porta_le_sue_frequenze(con_frequenze):
    assert con_frequenze["frequencies"] == [
        {"food": "pesce", "min": 2, "max": 3},
        {"food": "carne_rossa", "min": 0, "max": 1},
    ]


def test_la_generazione_scrive_la_proteina_accanto_alla_casella(client, con_frequenze):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    prompt = ModelloCheRicorda.prompt
    assert prompt.count("PROTEINA: Pesce") == 2
    # Le colazioni non sono pasti principali: niente proteina assegnata.
    assert all("PROTEINA" not in riga for riga in prompt.splitlines() if "Colazione" in riga)


def test_la_settimana_dice_quante_volte_c_e_ogni_gruppo(client, con_frequenze):
    """Il modello finto mette pollo a cena tutti i giorni e niente pesce: il resoconto
    lo dice, invece di far finta che le frequenze siano state rispettate."""
    week = client.get("/api/planning/weeks/current").json()
    generata = client.post(f"/api/planning/weeks/{week['id']}/generate").json()

    righe = {r["food"]: r for r in generata["frequencies"]}
    assert righe["pesce"]["count"] == 0
    assert righe["pesce"]["status"] == "sotto"
    assert righe["carne_rossa"]["status"] == "ok"


def test_ricalcolare_dal_questionario_non_perde_le_frequenze(client, con_frequenze):
    from tests.test_questionario import RISPOSTE

    res = client.post("/api/diet/questionnaire", json=RISPOSTE)
    assert res.status_code == 200, res.text
    assert res.json()["frequencies"] == con_frequenze["frequencies"]


def test_un_gruppo_sconosciuto_e_rifiutato(client, diet):
    res = client.put(
        f"/api/diet/{diet['id']}/frequencies",
        json={"frequencies": [{"food": "sushi", "min": 1}]},
    )
    assert res.status_code == 400


def test_la_dieta_di_un_altro_non_si_tocca(client, guest_client, diet):
    res = guest_client.put(
        f"/api/diet/{diet['id']}/frequencies",
        json={"frequencies": [{"food": "pesce", "min": 2}]},
    )
    assert res.status_code == 404


def test_le_opzioni_portano_le_consigliate(client):
    opzioni = client.get("/api/diet/frequencies/options").json()
    assert {f["key"] for f in opzioni["foods"]} == set(freq.FOODS)
    assert {"food": "carne_rossa", "min": 0, "max": 1} in opzioni["recommended"]
