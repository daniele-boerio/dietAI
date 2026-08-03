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


# ── Spegnere un termine di serie ───────────────────────────────────────────────


def test_un_termine_di_serie_si_spegne_e_si_riaccende(client, db):
    """«sedani» è un formato di pasta, ma è anche il plurale del sedano."""
    assert normalize_name("sedani") == "pasta"

    res = _regola(client, "off", "sedani")
    assert res.status_code == 201, res.text
    # Spento l'accorpamento, «sedani» torna a essere una verdura — e finisce sul nome
    # con cui il catalogo la chiama, che è al singolare.
    assert normalize_name("sedani", load_rules(db)) == "sedano"

    # Il termine resta nel codice: quella riga era una sospensione, non una cancellazione.
    client.delete(f"/api/config/normalization/{res.json()['rule']['id']}")
    assert normalize_name("sedani", load_rules(db)) == "pasta"


def test_si_spegne_anche_una_parola_ignorata(client, db):
    assert normalize_name("passata bio") == "passata"

    _regola(client, "off", "bio")
    assert normalize_name("passata bio", load_rules(db)) == "passata bio"


def test_spegnere_tutto_un_gruppo_non_rompe_la_regex(client, db):
    """Con l'ultimo termine spento la sostituzione va saltata, non compilata vuota."""
    for pesce in ("branzino", "orata", "sogliola", "merluzzo", "platessa"):
        assert _regola(client, "off", pesce).status_code == 201

    assert normalize_name("filetto di merluzzo", load_rules(db)) == "filetto di merluzzo"
    # E il resto della normalizzazione continua a funzionare.
    assert normalize_name("Zucchine fresche medie", load_rules(db)) == "zucchine"


def test_un_termine_che_di_serie_non_c_e_non_si_spegne(client):
    res = _regola(client, "off", "calamarata")
    assert res.status_code == 400
    assert "non è un termine di serie" in res.json()["detail"]


def test_la_lista_dice_quali_sono_spenti(client):
    _regola(client, "off", "sedani")

    body = client.get("/api/config/normalization").json()
    pasta = next(g for g in body["groups"] if g["target"] == "pasta")
    sedani = next(t for t in pasta["terms"] if t["term"] == "sedani")
    penne = next(t for t in pasta["terms"] if t["term"] == "penne")

    assert sedani["disabled"] is True and sedani["rule_id"]
    assert penne["disabled"] is False and penne["rule_id"] is None


def test_i_termini_arrivano_con_la_forma_per_spegnerli_e_quella_da_leggere(client):
    body = client.get("/api/config/normalization").json()
    marchi = next(g for g in body["noise"]["builtin"] if g["label"].startswith("Marchi"))
    cecco = next(t for t in marchi["terms"] if "cecco" in t["label"])

    assert cecco["label"] == "de cecco"
    assert cecco["term"] == r"de\s+cecco"


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

    di_serie = {t["term"] for t in pasta["terms"]}
    assert "penne" in di_serie and "fusilli" in di_serie
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
