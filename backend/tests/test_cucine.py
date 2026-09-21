"""Le cucine del mondo: cosa si può scegliere e cosa ne arriva al modello.

Due cose da difendere. La prima è il catalogo: le chiavi finiscono nel prompt e nel
database, quindi un doppione o una voce rinominata è una preferenza che cambia
significato sotto i piedi dell'utente. La seconda è la riga del contesto, che è il
punto della funzione — scegliere la cucina giapponese deve chiedere quelle tecniche
**senza** mandare l'utente a cercare il mirin.
"""

import pytest

from app.services.planner import build_context
from app.utils import cuisines


# ── Il catalogo ────────────────────────────────────────────────────────────────


def test_le_chiavi_sono_uniche_e_minuscole():
    """Due voci con la stessa chiave sarebbero due etichette per una preferenza sola.

    E la chiave la legge anche il modello (finisce in `tags.cuisine`): scritta in
    maiuscolo o con l'iniziale grande sarebbe un tag diverso a ogni generazione.
    """
    chiavi = [c["key"] for g in cuisines.options()["groups"] for c in g["cuisines"]]

    assert len(chiavi) == len(set(chiavi))
    assert all(k == k.lower().strip() for k in chiavi)
    assert chiavi, "il catalogo non può essere vuoto: il selettore resterebbe muto"


def test_ogni_voce_si_cerca_anche_per_paese():
    """Si cerca "Giappone", non "giapponese": il nome del paese è il modo in cui si

    pensa alla cucina, mentre la voce è scritta con l'aggettivo. Senza alias il campo
    di ricerca risponderebbe "nessun risultato" alla parola più ovvia.
    """
    voci = {c["key"]: c for g in cuisines.options()["groups"] for c in g["cuisines"]}

    assert "giappone" in voci["giapponese"]["aliases"]
    assert "messico" in voci["messicana"]["aliases"]
    assert all(v["aliases"] for v in voci.values())


def test_l_ordine_non_dipende_da_come_si_e_cliccato():
    """La lista finisce in un prompt: le stesse scelte devono dare la stessa stringa."""
    assert cuisines.clean(["messicana", "giapponese"]) == cuisines.clean(
        ["giapponese", "messicana"]
    )
    # E i doppioni spariscono, o il modello leggerebbe due volte la stessa cucina.
    assert cuisines.clean(["greca", "greca"]) == ["greca"]


def test_una_chiave_fuori_catalogo_si_riconosce():
    assert cuisines.unknown(["giapponese"]) == []
    assert cuisines.unknown(["giapponese", "marziana"]) == ["marziana"]
    # In lettura si scarta in silenzio: una voce tolta dal catalogo resterebbe
    # spuntata in un selettore che non ce l'ha più, cioè impossibile da togliere.
    assert cuisines.clean(["giapponese", "marziana"]) == ["giapponese"]


# ── La riga che legge il modello ───────────────────────────────────────────────


def test_senza_scelte_il_modello_ha_mano_libera():
    riga = cuisines.prompt_line([])

    assert "nessuna preferenza" in riga
    assert cuisines.prompt_line(None) == riga


def test_la_sola_italiana_non_si_porta_dietro_la_spiegazione():
    """Il discorso sugli ingredienti locali qui non serve: ce li ha già tutti.

    Ed è il default storico, cioè la riga che si genera più spesso: allungarla con
    un paragrafo che non dice niente sarebbe un costo a ogni chiamata.
    """
    riga = cuisines.prompt_line(["italiana"])

    assert "italiana" in riga
    assert "negozio specializzato" not in riga


@pytest.mark.parametrize(
    "scelte", [["giapponese"], ["giapponese", "messicana", "thailandese"]]
)
def test_una_cucina_straniera_porta_sempre_il_vincolo_degli_ingredienti(scelte):
    """È il punto della funzione: la cucina viaggia, gli ingredienti no.

    Una ricetta giapponese che chiede dashi e mirin è una ricetta che non si cucina —
    e peggio, finisce in lista della spesa come roba da comprare.
    """
    riga = cuisines.prompt_line(scelte)

    assert "supermercato italiano" in riga
    assert "negozio specializzato" in riga
    assert "mirin" in riga  # l'esempio di cosa NON si trova


def test_piu_cucine_vanno_alternate_e_sono_tutte_nominate():
    riga = cuisines.prompt_line(["greca", "messicana", "giapponese"])

    assert "alternandole" in riga
    for nome in ("greca", "messicana", "giapponese"):
        assert nome in riga


def test_le_cucine_arrivano_nel_contesto_di_ogni_generazione(client, diet, db):
    """`build_context` è la strada comune a piano, rigenerazione e chat.

    Se le cucine si fermassero alle preferenze, la chat "aggiusterebbe" una ricetta
    giapponese riportandola all'italiana al primo messaggio.
    """
    client.put(
        "/api/config/preferences",
        json={"prefer_seasonal": True, "cuisines": ["giapponese", "coreana"]},
    )

    contesto = build_context(db, 1)

    assert "giapponese" in contesto
    assert "coreana" in contesto
    assert "supermercato italiano" in contesto


# ── L'endpoint ─────────────────────────────────────────────────────────────────


def test_il_catalogo_si_scarica_e_le_preferenze_lo_ricordano(client):
    gruppi = client.get("/api/config/cuisines").json()["groups"]
    assert gruppi and all(g["label"] and g["cuisines"] for g in gruppi)

    salvate = client.put(
        "/api/config/preferences",
        json={"prefer_seasonal": True, "cuisines": ["thailandese", "italiana"]},
    ).json()

    assert salvate["cuisines"] == ["italiana", "thailandese"]  # ordine del catalogo
    assert client.get("/api/config/preferences").json()["cuisines"] == [
        "italiana",
        "thailandese",
    ]


def test_una_cucina_inventata_viene_rifiutata_dicendo_quale(client):
    """400 e non un silenzioso scarto: una voce scritta a mano che sparisce senza

    spiegazioni sembra una preferenza che non si salva.
    """
    r = client.put(
        "/api/config/preferences",
        json={"prefer_seasonal": True, "cuisines": ["giapponese", "atlantidea"]},
    )

    assert r.status_code == 400
    assert "atlantidea" in r.json()["detail"]


def test_il_corpo_senza_cucine_le_svuota(client):
    """Nessuna cucina è una scelta legittima — «scegli tu» — e va salvata come tale."""
    client.put(
        "/api/config/preferences", json={"prefer_seasonal": True, "cuisines": ["greca"]}
    )

    assert client.put(
        "/api/config/preferences", json={"prefer_seasonal": True}
    ).json()["cuisines"] == []
