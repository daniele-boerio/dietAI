"""Una ricetta dell'utente scritta a parole, per N porzioni, ridotta a una porzione.

Il modello divide le quantità e ripulisce il procedimento; il server tiene la ricetta
come dell'utente (salvata, proponibile, mai ritoccata) ma coi macro calcolati.
"""

from app.routers import recipes as recipes_router

PORZIONE = {
    "title": "Pasta al sugo di cavolfiore",
    "description": "Il sugo della domenica, una porzione.",
    "prep_time_min": 10,
    "cook_time_min": 30,
    "difficulty": "easy",
    "ingredients": [
        {"name": "cavolfiore", "quantity": 200, "unit": "g"},
        {"name": "pasta", "quantity": 80, "unit": "g"},
        {"name": "olio EVO", "quantity": 5, "unit": "ml"},
    ],
    "instructions": "1. Si prepara per 4 porzioni: questa è una.\n2. Cuoci il cavolfiore.",
    "nutrition": {"calories": 420, "protein_g": 15, "carbs_g": 68, "fat_g": 8},
    "tags": {"type": "primo"},
}


class ModelloFinto:
    def __init__(self, risposta):
        self.risposta = risposta
        self.prompt = None
        self.system = None

    def generate_json(self, system, prompt, **kwargs):
        self.system, self.prompt = system, prompt
        return self.risposta


def usa(monkeypatch, risposta=PORZIONE) -> ModelloFinto:
    finto = ModelloFinto(risposta)
    monkeypatch.setattr(recipes_router, "get_client", lambda db, user, role: finto)
    return finto


def crea(client, **campi):
    corpo = {
        "title": "Pasta al sugo di cavolfiore",
        "ingredients": "1 cavolfiore da 800 g\n4 cucchiai di olio\n80 g di pasta a porzione",
        "instructions": "Cuoci il cavolfiore con l'olio, frulla metà, condisci la pasta.",
        "portions": 4,
        **campi,
    }
    return client.post("/api/recipes/from-text", json=corpo)


def test_la_ricetta_nasce_per_una_porzione_e_va_nel_ricettario(client, monkeypatch):
    finto = usa(monkeypatch)

    res = crea(client)

    assert res.status_code == 201, res.text
    ricetta = res.json()
    assert ricetta["title"] == "Pasta al sugo di cavolfiore"
    quantita = {i["name"]: i["quantity"] for i in ricetta["ingredients"]}
    assert quantita["cavolfiore"] == 200 and quantita["pasta"] == 80
    # Il nome dell'olio passa dalla normalizzazione come tutti gli altri.
    assert "olio extravergine d'oliva" in quantita
    salvate = client.get("/api/recipes", params={"scope": "proposable"}).json()["items"]
    assert ricetta["id"] in {r["id"] for r in salvate}
    # Al modello arrivano le porzioni e le parole dell'utente, così come le ha scritte.
    assert "PORZIONI: 4" in finto.prompt
    assert "80 g di pasta a porzione" in finto.prompt
    assert "dividi" in finto.system.lower()


def test_il_titolo_dell_utente_resta_il_suo(client, monkeypatch):
    usa(monkeypatch, {**PORZIONE, "title": "Un altro nome"})
    assert crea(client, title="Il sugo della nonna").json()["title"] == "Il sugo della nonna"


def test_senza_titolo_lo_sceglie_il_modello(client, monkeypatch):
    finto = usa(monkeypatch)
    res = crea(client, title=None)
    assert res.json()["title"] == "Pasta al sugo di cavolfiore"
    assert "TITOLO: (scegli tu)" in finto.prompt


def test_una_risposta_illeggibile_non_crea_niente(client, monkeypatch):
    usa(monkeypatch, {"testo": "non è una ricetta"})
    res = crea(client)
    assert res.status_code >= 400
    assert client.get("/api/recipes").json()["items"] == []


def test_le_porzioni_hanno_un_limite(client, monkeypatch):
    usa(monkeypatch)
    assert crea(client, portions=0).status_code == 422
    assert crea(client, portions=21).status_code == 422
