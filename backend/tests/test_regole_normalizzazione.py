"""Le regole di normalizzazione aggiunte dalle Impostazioni.

Funzionano come quelle di serie — una sostituzione con regex su parola intera — solo
che i termini stanno in tabella invece che nel codice, e si aggiungono senza deploy.
Quello che questi test difendono è il confine: le regole di serie non devono cambiare
comportamento adesso che c'è un secondo strato, e un accorpamento sbagliato deve
potersi vedere **prima** di salvarlo, perché dopo non si annulla.
"""

import pytest

from app.models import Ingredient, NormalizationRule
from app.services.ingredients import (
    NO_RULES,
    get_or_create_ingredient,
    load_rules,
    normalize_name,
)


def _regola(client, kind, term, replacement=None):
    return client.post(
        "/api/config/normalization",
        json={"kind": kind, "term": term, "replacement": replacement},
    )


# ── Il confine con le regole di serie ──────────────────────────────────────────


@pytest.mark.parametrize(
    "grezzo,atteso",
    [
        ("Penne rigate", "pasta rigate"),
        ("Zucchine fresche medie", "zucchine"),
        ("cous cous", "cous cous"),  # i nomi ripetuti per davvero restano
        ("Grana Padano", "formaggio"),
        ("filetto di merluzzo surgelato", "filetto di pesce magro"),
    ],
)
def test_senza_regole_aggiunte_non_cambia_niente(grezzo, atteso):
    """Il secondo strato deve essere invisibile finché è vuoto."""
    assert normalize_name(grezzo) == atteso
    assert normalize_name(grezzo, NO_RULES) == atteso


def test_le_regole_aggiunte_lavorano_come_quelle_di_serie(client, db):
    _regola(client, "alias", "calamarata", "pasta")
    rules = load_rules(db)

    # Sostituzione su parola intera, dentro un nome più lungo: è la stessa cosa che
    # fanno "penne" e "fusilli" nel codice.
    assert normalize_name("calamarata", rules) == "pasta"
    assert normalize_name("Calamarata integrale", rules) == "pasta integrale"
    # E non tocca le parole che quel termine se lo portano dentro per caso.
    assert normalize_name("sugo alla calamarataccia", rules) == "sugo alla calamarataccia"


def test_una_parola_da_ignorare(client, db):
    _regola(client, "noise", "a filetti")
    rules = load_rules(db)

    assert normalize_name("Pesce spada a filetti", rules) == "pesce spada"


def test_un_qualificatore_accorpato_non_raddoppia_il_nome(client, db):
    """«olive taggiasche» con «taggiasche» → «olive» darebbe "olive olive"."""
    _regola(client, "alias", "taggiasche", "olive")
    rules = load_rules(db)

    assert normalize_name("olive taggiasche", rules) == "olive"


# ── Quello che non si accetta ──────────────────────────────────────────────────


def test_una_regola_che_non_farebbe_niente_viene_rifiutata(client):
    # "surgelato" è già rumore di serie
    res = _regola(client, "noise", "surgelato")
    assert res.status_code == 400
    assert "regole di serie" in res.json()["detail"]

    # "penne" è già pasta
    res = _regola(client, "alias", "penne", "pasta")
    assert res.status_code == 400
    assert "già" in res.json()["detail"]


def test_un_accorpamento_senza_destinazione_no(client):
    assert _regola(client, "alias", "calamarata").status_code == 400


def test_lo_stesso_termine_due_volte_no(client):
    assert _regola(client, "alias", "calamarata", "pasta").status_code == 201
    res = _regola(client, "alias", "calamarata", "pasta")
    assert res.status_code == 409


def test_solo_l_amministratore(guest_client):
    """L'anagrafica è una sola: queste regole toccano i dati di tutti."""
    assert guest_client.get("/api/config/normalization").status_code == 403
    assert _regola(guest_client, "alias", "calamarata", "pasta").status_code == 403


# ── L'anteprima ────────────────────────────────────────────────────────────────


def test_l_anteprima_dice_cosa_verrebbe_fuso_senza_fondere_niente(client, db):
    get_or_create_ingredient(db, "calamarata")
    get_or_create_ingredient(db, "pasta")
    db.commit()

    res = client.post(
        "/api/config/normalization/preview",
        json={"kind": "alias", "term": "calamarata", "replacement": "pasta"},
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["changes"] == [{"from": "calamarata", "to": "pasta", "merges": True}]
    # Non ha scritto niente: la riga è ancora lì e la regola non esiste.
    assert db.query(Ingredient).filter(Ingredient.name == "calamarata").first()
    assert db.query(NormalizationRule).count() == 0


def test_l_anteprima_mostra_il_disastro_prima_che_succeda(client, db):
    """Il caso da cui ci si vuole difendere: un accorpamento troppo largo."""
    get_or_create_ingredient(db, "riso")
    db.commit()

    body = client.post(
        "/api/config/normalization/preview",
        json={"kind": "alias", "term": "riso", "replacement": "pasta"},
    ).json()

    assert {c["from"] for c in body["changes"]} == {"riso"}
    assert body["changes"][0]["to"] == "pasta"


# ── Salvare riallinea l'anagrafica ─────────────────────────────────────────────


def test_salvare_fonde_le_righe_che_gia_c_erano(client, db):
    calamarata = get_or_create_ingredient(db, "calamarata")
    get_or_create_ingredient(db, "pasta")
    db.commit()
    vecchio_id = calamarata.id

    res = _regola(client, "alias", "calamarata", "pasta")
    assert res.status_code == 201, res.text
    assert res.json()["merged"] == [{"name": "pasta", "from": ["calamarata"]}]

    assert db.get(Ingredient, vecchio_id) is None
    assert db.query(Ingredient).filter(Ingredient.name == "calamarata").first() is None


def test_da_li_in_poi_i_nomi_nuovi_ci_finiscono_dentro(client, db):
    _regola(client, "alias", "calamarata", "pasta")

    ingrediente = get_or_create_ingredient(db, "Calamarata fresca")
    assert ingrediente.name == "pasta"


def test_togliere_la_regola_non_disfa_la_fusione(client, db):
    get_or_create_ingredient(db, "calamarata")
    get_or_create_ingredient(db, "pasta")
    db.commit()

    regola = _regola(client, "alias", "calamarata", "pasta").json()["rule"]
    assert client.delete(f"/api/config/normalization/{regola['id']}").status_code == 204

    # La riga fusa resta fusa — è scritto nella UI, ed è il motivo dell'anteprima.
    assert db.query(Ingredient).filter(Ingredient.name == "calamarata").first() is None
    # Ma da adesso un nome nuovo torna a fare riga a sé.
    assert get_or_create_ingredient(db, "calamarata").name == "calamarata"


# ── La lista che si legge ──────────────────────────────────────────────────────


def test_la_lista_mette_insieme_termini_di_serie_e_aggiunti(client):
    _regola(client, "alias", "calamarata", "pasta")
    _regola(client, "noise", "a filetti")

    body = client.get("/api/config/normalization").json()
    pasta = next(g for g in body["groups"] if g["target"] == "pasta")

    assert "penne" in pasta["terms"] and "fusilli" in pasta["terms"]
    assert [c["term"] for c in pasta["custom"]] == ["calamarata"]
    assert [c["term"] for c in body["noise"]["custom"]] == ["a filetti"]
    # I termini di serie ci sono tutti, raggruppati come nel codice.
    assert {g["target"] for g in body["groups"]} >= {
        "pasta", "filetto di pesce magro", "formaggio"
    }
    assert any(g["label"] == "Conservazione e stato" for g in body["noise"]["builtin"])


def test_un_gruppo_nuovo_nasce_dalla_prima_regola(client):
    _regola(client, "alias", "seitan affumicato", "seitan")

    body = client.get("/api/config/normalization").json()
    gruppo = next(g for g in body["groups"] if g["target"] == "seitan")

    assert gruppo["terms"] == []
    assert [c["term"] for c in gruppo["custom"]] == ["seitan affumicato"]
