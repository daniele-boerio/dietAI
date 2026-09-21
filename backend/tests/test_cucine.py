"""Le cucine del mondo: cosa si può scegliere e cosa ne arriva al modello.

Due cose da difendere. La prima è il catalogo: le chiavi finiscono nel prompt e nel
database, quindi un doppione o una voce rinominata è una preferenza che cambia
significato sotto i piedi dell'utente. La seconda è la riga del contesto, che è il
punto della funzione — scegliere la cucina giapponese deve chiedere quelle tecniche
**senza** mandare l'utente a cercare il mirin.
"""

import random

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
    """La preferenza finisce in un prompt: le stesse scelte, la stessa stringa.

    Il confronto è su `list(...)`, cioè sulle chiavi in fila: due dizionari con le
    stesse coppie sono uguali anche scritti in ordine diverso, quindi `==` da solo
    non proverebbe niente di quello che qui interessa.
    """
    assert list(cuisines.clean(["messicana", "giapponese"])) == list(
        cuisines.clean(["giapponese", "messicana"])
    )
    # E i doppioni spariscono, o il modello leggerebbe due volte la stessa cucina.
    assert cuisines.clean(["greca", "greca"]) == {"greca": 100}


def test_una_chiave_fuori_catalogo_si_riconosce():
    assert cuisines.unknown(["giapponese"]) == []
    assert cuisines.unknown(["giapponese", "marziana"]) == ["marziana"]
    assert cuisines.unknown({"giapponese": 70, "marziana": 30}) == ["marziana"]
    # In lettura si scarta in silenzio: una voce tolta dal catalogo resterebbe
    # spuntata in un selettore che non ce l'ha più, cioè impossibile da togliere.
    # E la quota che lasciava libera torna a chi resta, o la somma non farebbe 100.
    assert cuisines.clean({"giapponese": 70, "marziana": 30}) == {"giapponese": 100}


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


def test_piu_cucine_si_dicono_con_le_loro_quote():
    """Le percentuali stanno anche qui, dove nessuno sorteggia, perché questa riga la

    leggono le chat: chiedendo un'alternativa a un piatto, la proporzione dice da che
    parte guardare — con 70% italiana il sostituto giusto è quasi sempre italiano.
    """
    riga = cuisines.prompt_line({"italiana": 70, "greca": 20, "giapponese": 10})

    assert "italiana 70%" in riga
    assert "greca 20%" in riga
    assert "giapponese 10%" in riga


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
        json={"prefer_seasonal": True, "cuisines": {"thailandese": 30, "italiana": 70}},
    ).json()

    assert salvate["cuisines"] == {"italiana": 70, "thailandese": 30}
    assert list(salvate["cuisines"]) == ["italiana", "thailandese"]  # ordine catalogo
    assert client.get("/api/config/preferences").json()["cuisines"] == {
        "italiana": 70,
        "thailandese": 30,
    }


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

    assert (
        client.put("/api/config/preferences", json={"prefer_seasonal": True}).json()[
            "cuisines"
        ]
        == {}
    )


# ── Il sorteggio ───────────────────────────────────────────────────────────────

# Il sorteggio sta in Python e non nel prompt perche' "alternale nell'arco della
# settimana" e' un auspicio: il modello ancora sulla prima voce dell'elenco, o su
# quella che gli viene piu' facile, e chi ha spuntato otto cucine si ritrova sette
# cene italiane. Qui si difende la proprieta' che il prompt non puo' garantire.

SCELTE = ["giapponese", "greca", "messicana"]


def test_il_sorteggio_pesca_solo_fra_le_scelte():
    estratte = cuisines.draw(SCELTE, 7, rng=random.Random(1))

    assert len(estratte) == 7
    assert set(estratte) <= set(cuisines.labels(SCELTE))


def test_nessuna_cucina_resta_fuori_e_nessuna_prende_tutto():
    """E' la proprieta' del mazzo, quella che un dado non da'.

    Con tre cucine su sette giorni, tirando un dado indipendente per ogni giorno
    cinque giapponesi e due greche sono un risultato onesto — e indistinguibile dal
    guasto che il sorteggio doveva riparare. Distribuendo un mazzo mescolato, ognuna
    esce due o tre volte, con qualunque seme.
    """
    for seme in range(50):
        estratte = cuisines.draw(SCELTE, 7, rng=random.Random(seme))
        conta = {c: estratte.count(c) for c in cuisines.labels(SCELTE)}

        assert min(conta.values()) >= 2
        assert max(conta.values()) <= 3


def test_la_stessa_cucina_non_esce_due_giorni_di_fila():
    """A cavallo di due mazzi e' il punto in cui puo' succedere, ed e' proprio

    quello che sembra il guasto: due cene greche di seguito su una settimana
    sorteggiata si leggono come "non ha sorteggiato niente".
    """
    for seme in range(50):
        estratte = cuisines.draw(SCELTE, 9, rng=random.Random(seme))

        assert all(a != b for a, b in zip(estratte, estratte[1:])), estratte


def test_due_sorteggi_non_danno_lo_stesso_ordine():
    """Se l'ordine fosse sempre quello, il lunedi' sarebbe giapponese per sempre."""
    ordini = {tuple(cuisines.draw(SCELTE, 7, rng=random.Random(s))) for s in range(30)}

    assert len(ordini) > 1


def test_si_puo_escludere_la_cucina_del_piatto_che_si_sta_rifacendo():
    for seme in range(20):
        estratte = cuisines.draw(SCELTE, 1, avoid="Greca", rng=random.Random(seme))

        assert estratte[0] != "Greca"


def test_ma_chi_ne_ha_scelta_una_sola_deve_poter_rigenerare_lo_stesso():
    """`avoid` non puo' svuotare il mazzo: senza estrazione non si genera niente."""
    assert cuisines.draw(["greca"], 1, avoid="Greca") == ["Greca"]


def test_senza_scelte_non_si_sorteggia_niente():
    """Lista vuota e non un ripiego: e' il segno che il contesto resta quello di prima."""
    assert cuisines.draw([], 7) == []
    assert cuisines.draw(None, 7) == []
    assert cuisines.draw(SCELTE, 0) == []


# ── Dal sorteggio al prompt ────────────────────────────────────────────────────

# Sorteggiare e non dirlo al modello non cambia niente: queste provano il pezzo di
# strada che sta fra le due cose.


def _ricetta(titolo):
    return {
        "title": titolo,
        "description": "Ricetta di prova",
        "prep_time_min": 10,
        "cook_time_min": 10,
        "difficulty": "easy",
        "ingredients": [{"name": "zucchine", "quantity": 100, "unit": "g"}],
        "instructions": "1. Fai tutto.",
        "nutrition": {
            "calories": 500,
            "protein_g": 30.0,
            "carbs_g": 40.0,
            "fat_g": 15.0,
        },
        "tags": {"cuisine": "greca", "type": "piatto unico"},
    }


class ModelloSpia:
    """Non genera niente di interessante: serve solo a tenersi il prompt ricevuto."""

    ultimo = ""

    def __init__(self):
        self.model = "finto/modello-di-test"
        self.supports_native_pdf = False

    def generate_json(self, system, prompt, **kwargs):
        ModelloSpia.ultimo = prompt
        # Sull'intestazione intera: anche il prompt del singolo pasto dice "PASTO DA
        # GENERARE", e riconoscendolo per settimana si rispondeva con sette giorni a
        # chi ne aveva chiesto uno.
        if "DA GENERARE (giorno" in prompt:
            return {
                "days": [
                    {
                        "day_of_week": dow,
                        "meals": [
                            {"slot_name": n, "recipe": _ricetta(f"{n} {dow}")}
                            for n in ("Colazione", "Pranzo", "Cena")
                        ],
                    }
                    for dow in range(7)
                ]
            }
        return _ricetta("Piatto rigenerato")


@pytest.fixture()
def spia(monkeypatch, client):
    from app.services import planner as mod

    monkeypatch.setattr(mod, "get_client", lambda db, user, role: ModelloSpia())
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    return ModelloSpia


def _scegli(client, chiavi):
    res = client.put(
        "/api/config/preferences", json={"prefer_seasonal": True, "cuisines": chiavi}
    )
    assert res.status_code == 200, res.text


def _righe_dei_giorni(prompt):
    """Le intestazioni dei giorni nel blocco «DA GENERARE».

    Si taglia sull'intestazione intera e non sulle due parole: il contesto adesso
    rimanda a quel blocco («la trovi scritta accanto a ogni giorno in «DA GENERARE»»)
    e tagliare lì dividerebbe il prompt nel punto sbagliato.
    """
    blocco = prompt.split("DA GENERARE (giorno")[1].split("PASTI GIÀ ASSEGNATI")[0]
    return [r for r in blocco.splitlines() if "day_of_week" in r]


def test_ogni_giorno_della_settimana_arriva_col_suo_sorteggio(client, diet, spia):
    _scegli(client, SCELTE)
    week = client.get("/api/planning/weeks/current").json()

    res = client.post(f"/api/planning/weeks/{week['id']}/generate", json={})
    assert res.status_code == 200, res.text

    righe = _righe_dei_giorni(spia.ultimo)
    assert len(righe) == 7
    assert all("CUCINA:" in r for r in righe), righe
    # E tutte e tre escono: una settimana con una cucina sola sarebbe il guasto di
    # prima, scritto da un sorteggio invece che dal modello.
    for nome in cuisines.labels(SCELTE):
        assert any(nome in r for r in righe), (nome, righe)


def test_il_contesto_dice_che_il_sorteggio_e_gia_fatto(client, diet, spia):
    """Senza questa riga il modello legge «CUCINA: Greca» come un suggerimento."""
    _scegli(client, SCELTE)
    week = client.get("/api/planning/weeks/current").json()

    client.post(f"/api/planning/weeks/{week['id']}/generate", json={})

    assert "SORTEGGIATA" in spia.ultimo
    assert "non ripiegare sull'italiana" in spia.ultimo


def test_con_una_cucina_sola_non_si_sorteggia_e_il_prompt_resta_quello_di_prima(
    client, diet, spia
):
    """Lo strato non esiste finché non lo si usa: con una scelta sola non c'è niente

    da estrarre, e il contesto torna a essere la riga corta di sempre.
    """
    _scegli(client, ["italiana"])
    week = client.get("/api/planning/weeks/current").json()

    client.post(f"/api/planning/weeks/{week['id']}/generate", json={})

    assert all("CUCINA:" not in r for r in _righe_dei_giorni(spia.ultimo))
    assert "SORTEGGIATA" not in spia.ultimo


def test_rigenerare_un_pasto_ne_sorteggia_una_sola(client, diet, spia):
    _scegli(client, SCELTE)
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate", json={})
    meal = client.get("/api/planning/weeks/current").json()["days"][0]["meals"][0]

    res = client.post(f"/api/planning/meals/{meal['id']}/regenerate", json={})
    assert res.status_code == 200, res.text

    nominate = [n for n in cuisines.labels(SCELTE) if n.lower() in spia.ultimo.lower()]
    assert len(nominate) == 1, nominate
    # Il piatto buttato era greco (vedi `_ricetta`): rigenerare deve portare altrove.
    assert "Greca" not in nominate


def test_una_richiesta_dell_utente_manda_in_pensione_il_sorteggio(client, diet, spia):
    """«fammi una carbonara» più «oggi è coreano» sono due ordini contrari, e a

    scegliere quale seguire sarebbe il modello.
    """
    _scegli(client, SCELTE)
    week = client.get("/api/planning/weeks/current").json()
    meal = client.get("/api/planning/weeks/current").json()["days"][0]["meals"][0]

    client.post(
        f"/api/planning/meals/{meal['id']}/regenerate",
        json={"user_request": "una carbonara"},
    )

    assert "sorteggiata" not in spia.ultimo.lower()
    assert "carbonara" in spia.ultimo


@pytest.mark.parametrize("sporco", [None, 42, ["greca"], "", "   "])
def test_un_tag_malscritto_non_fa_saltare_la_rigenerazione(sporco):
    """`avoid` arriva dai tag della ricetta, cioe' da quello che ha scritto il

    modello: puo' essere qualunque cosa. Non e' un dato da validare — serve solo a
    togliere una carta dal mazzo — e far fallire per questo una rigenerazione gia'
    pagata sarebbe il modo peggiore di scoprirlo.
    """
    estratte = cuisines.draw(SCELTE, 3, avoid=sporco, rng=random.Random(0))

    assert len(estratte) == 3
    assert set(estratte) <= set(cuisines.labels(SCELTE))


# -- Le quote ------------------------------------------------------------------


def test_le_quote_sommano_sempre_a_cento():
    """Anche quando non ci arrivano da sole: il numero che si legge a schermo e'

    una percentuale, e tre voci che dicono 33% l'una sono una percentuale rotta.
    """
    for scritte in (
        {"italiana": 70, "greca": 30},
        {"italiana": 1, "greca": 1, "giapponese": 1},
        {"italiana": 5, "greca": 3},
        {"italiana": 999},
        ["italiana", "greca", "giapponese", "messicana", "turca", "indiana", "cinese"],
    ):
        assert sum(cuisines.clean(scritte).values()) == 100, scritte


def test_un_elenco_senza_quote_vale_parti_uguali():
    """E' la forma della prima versione, che in archivio c'e' ancora: leggerla

    invece di migrarla e' una scelta — una migrazione che riscrive un JSON per dire
    la stessa cosa puo' solo introdurre bug, e la riga si risalva da se'.
    """
    assert cuisines.clean(["italiana", "greca"]) == {"italiana": 50, "greca": 50}
    assert cuisines.clean(["italiana"]) == {"italiana": 100}


def test_una_cucina_in_elenco_non_scende_mai_a_zero():
    """Una voce spuntata che non puo' mai uscire e' una voce che mente: chi non la

    vuole piu' la toglie, e finche' c'e' deve poter capitare.
    """
    quote = cuisines.clean({"italiana": 1000, "greca": 1})

    assert quote["greca"] >= cuisines.QUOTA_MINIMA
    assert sum(quote.values()) == 100


def test_il_sorteggio_rispetta_la_percentuale_su_questa_settimana():
    """Non "in media": la settimana che si genera adesso e' una sola.

    Con 70/30 su sette giorni un dado da' cinque italiane in media, ma sette italiane
    di fila sono un risultato onesto del dado — e per chi guarda il piano sono il
    guasto che le percentuali dovevano riparare.
    """
    for seme in range(30):
        estratte = cuisines.draw(
            {"italiana": 70, "greca": 30}, 7, rng=random.Random(seme)
        )

        assert estratte.count("Italiana") == 5
        assert estratte.count("Greca") == 2


def test_alzare_una_quota_alza_le_sue_caselle():
    poca = cuisines.draw({"italiana": 30, "greca": 70}, 10, rng=random.Random(0))
    tanta = cuisines.draw({"italiana": 80, "greca": 20}, 10, rng=random.Random(0))

    assert poca.count("Italiana") == 3
    assert tanta.count("Italiana") == 8


def test_le_ripetizioni_stanno_lontane_fin_dove_le_quote_lo_permettono():
    """Con l'80% su cinque giorni due di fila sono aritmetica, non un difetto: quello

    che si pretende e' che le poche non finiscano tutte attaccate in fondo.
    """
    for seme in range(30):
        estratte = cuisines.draw(
            {"italiana": 80, "greca": 20}, 10, rng=random.Random(seme)
        )
        greche = [i for i, c in enumerate(estratte) if c == "Greca"]

        assert len(greche) == 2
        # Due su dieci ben distanziate non possono essere adiacenti.
        assert greche[1] - greche[0] > 1, estratte


def test_le_quote_arrivano_nel_contesto_delle_chat(client, diet, db):
    client.put(
        "/api/config/preferences",
        json={"prefer_seasonal": True, "cuisines": {"italiana": 70, "greca": 30}},
    )

    contesto = build_context(db, 1)

    assert "italiana 70%" in contesto
    assert "greca 30%" in contesto


def test_la_settimana_generata_rispetta_le_quote(client, diet, spia):
    """Dalla percentuale scritta nelle preferenze fino al prompt davvero spedito."""
    _scegli(client, {"italiana": 70, "greca": 30})
    week = client.get("/api/planning/weeks/current").json()

    client.post(f"/api/planning/weeks/{week['id']}/generate", json={})

    righe = _righe_dei_giorni(spia.ultimo)
    assert sum("CUCINA: Italiana" in r for r in righe) == 5
    assert sum("CUCINA: Greca" in r for r in righe) == 2


def test_troppe_cucine_vengono_rifiutate_spiegando_perche(client):
    troppe = [c["key"] for g in cuisines.options()["groups"] for c in g["cuisines"]]
    r = client.put(
        "/api/config/preferences",
        json={"prefer_seasonal": True, "cuisines": troppe[: cuisines.MAX_CUCINE + 1]},
    )

    assert r.status_code == 400
    assert str(cuisines.MAX_CUCINE) in r.json()["detail"]


def test_con_una_quota_alta_la_fila_cambia_comunque_ogni_settimana():
    """La trappola del sorteggio "ovvio", scoperta guardando tre semi di fila.

    Pescando ogni volta la cucina a cui ne restano di piu' (saltando quella appena
    uscita) la fila e' ben distanziata ma **sempre la stessa**: con 5/1/1 usciva
    "italiana, greca, italiana, giapponese, italiana, italiana, italiana" a ogni
    generazione. Un sorteggio che da' sempre lo stesso risultato e' il guasto di
    partenza servito una riga piu' in la'.
    """
    quote = {"italiana": 70, "giapponese": 20, "greca": 10}
    file = {
        tuple(cuisines.draw(quote, 7, rng=random.Random(s))) for s in range(20)
    }

    assert len(file) > 10, "la fila e' troppo prevedibile"


def test_le_poche_capitano_in_tutti_i_giorni_della_settimana():
    """Distanziare vuol dire anche non ammassare le tante sempre nello stesso posto.

    Su una singola settimana le due minori possono benissimo cadere vicine — e' il
    caso, non un difetto: pretendere il contrario vorrebbe dire togliere proprio la
    casualita' che si e' appena messa. Quello che si pretende e' che su molte
    settimane **ogni giorno** capiti prima o poi a una cucina minore: se la coda
    fosse sempre un blocco di italiane, gli ultimi giorni non comparirebbero mai.
    """
    visti = set()
    for seme in range(100):
        estratte = cuisines.draw(
            {"italiana": 70, "giapponese": 20, "greca": 10}, 7, rng=random.Random(seme)
        )
        visti |= {i for i, c in enumerate(estratte) if c != "Italiana"}

    assert visti == set(range(7)), sorted(visti)
