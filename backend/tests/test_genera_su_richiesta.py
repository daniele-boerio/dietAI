"""Generare un pasto: a scelta del modello, o dicendogli cosa si vuole.

Lo stesso pulsante fa due cose. Senza indicazioni è la generazione di sempre — sceglie
il modello, col vincolo di non ripetere i piatti della settimana. Con indicazioni
("qualcosa con la zucca", "ho del salmone da finire") decide l'utente, e all'AI resta il
mestiere: pesare gli ingredienti perché i macro tornino e scrivere il procedimento.

È il caso che la chat non copriva: lì si parte da una ricetta e la si modifica, qui la
casella può essere ancora vuota.
"""

import pytest

from app.services import planner
from tests.test_flow import FakeModel, _fake_recipe


class ModelloCheRicorda(FakeModel):
    """Tiene l'ultimo prompt ricevuto: serve a leggere cosa gli è arrivato davvero."""

    ultimo_prompt = None
    ultimo_system = None

    def generate_json(self, system, prompt, **kwargs):
        ModelloCheRicorda.ultimo_prompt = prompt
        ModelloCheRicorda.ultimo_system = system
        # La rigenerazione di un singolo pasto vuole una ricetta, non una settimana.
        if "PASTO DA GENERARE" in prompt:
            return _fake_recipe(
                "Vellutata di zucca",
                600,
                [
                    {"name": "zucca", "quantity": 300, "unit": "g"},
                    {"name": "riso", "quantity": 60, "unit": "g"},
                ],
            )
        return super().generate_json(system, prompt, **kwargs)


@pytest.fixture()
def fake_ai(monkeypatch, client):
    ModelloCheRicorda.ultimo_prompt = None
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: ModelloCheRicorda(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})


@pytest.fixture()
def casella_vuota(client, diet, fake_ai):
    """La cena di lunedì, ancora da riempire: è da lì che si parte il più delle volte."""
    week = client.get("/api/planning/weeks/current").json()
    return next(m for m in week["days"][0]["meals"] if m["slot_name"] == "Cena")


def test_senza_indicazioni_e_la_generazione_di_sempre(client, casella_vuota):
    res = client.post(f"/api/planning/meals/{casella_vuota['id']}/regenerate")

    assert res.status_code == 200, res.text
    assert res.json()["recipe"]["title"] == "Vellutata di zucca"
    assert "RICHIESTA DELL'UTENTE" not in ModelloCheRicorda.ultimo_prompt


def test_il_corpo_resta_facoltativo(client, casella_vuota):
    """La chiamata senza corpo è quella che fa la griglia settimanale: non deve rompersi."""
    res = client.post(
        f"/api/planning/meals/{casella_vuota['id']}/regenerate", json={"user_request": None}
    )

    assert res.status_code == 200, res.text
    assert "RICHIESTA DELL'UTENTE" not in ModelloCheRicorda.ultimo_prompt


def test_la_richiesta_arriva_al_modello(client, casella_vuota):
    res = client.post(
        f"/api/planning/meals/{casella_vuota['id']}/regenerate",
        json={"user_request": "ho della zucca da finire"},
    )

    assert res.status_code == 200, res.text
    prompt = ModelloCheRicorda.ultimo_prompt
    assert "ho della zucca da finire" in prompt
    # E arriva detto in modo che comandi lei, non come una nota in fondo.
    assert "RICHIESTA DELL'UTENTE" in prompt
    assert "precedenza" in prompt
    # I macro del pasto restano nel prompt: è quello che l'AI deve far tornare.
    assert "Macro target" in prompt


def test_le_regole_di_varieta_decadono_solo_a_parole_del_sistema(client, casella_vuota):
    """Il permesso di ripetere un piatto sta nel system prompt, non nel messaggio."""
    client.post(
        f"/api/planning/meals/{casella_vuota['id']}/regenerate",
        json={"user_request": "la stessa cosa di ieri ma col tacchino"},
    )

    assert "RICHIESTA DELL'UTENTE" in ModelloCheRicorda.ultimo_system
    assert "decadono" in ModelloCheRicorda.ultimo_system


def test_una_richiesta_di_soli_spazi_vale_come_nessuna(client, casella_vuota):
    res = client.post(
        f"/api/planning/meals/{casella_vuota['id']}/regenerate",
        json={"user_request": "   "},
    )

    assert res.status_code == 200, res.text
    assert "RICHIESTA DELL'UTENTE" not in ModelloCheRicorda.ultimo_prompt


def test_una_richiesta_lunghissima_e_un_422(client, casella_vuota):
    """Il campo è per una richiesta, non per una ricetta scritta a mano."""
    res = client.post(
        f"/api/planning/meals/{casella_vuota['id']}/regenerate",
        json={"user_request": "zucca " * 200},
    )

    assert res.status_code == 422


def test_la_ricetta_generata_finisce_nella_casella(client, casella_vuota):
    client.post(
        f"/api/planning/meals/{casella_vuota['id']}/regenerate",
        json={"user_request": "ho della zucca da finire"},
    )

    week = client.get("/api/planning/weeks/current").json()
    cena = next(m for m in week["days"][0]["meals"] if m["slot_name"] == "Cena")
    assert cena["recipe"]["title"] == "Vellutata di zucca"
    assert [i["name"] for i in client.get(f"/api/recipes/{cena['recipe']['id']}").json()[
        "ingredients"
    ]] == ["zucca", "riso"]
