"""Le cucine del mondo da cui attingere le ricette.

È un elenco chiuso e non testo libero per una ragione sola: il nome scelto qui
finisce **nel prompt** e nei tag delle ricette, quindi deve essere sempre lo stesso.
"giapponese", "Giappone" e "cucina nipponica" scritti a mano sarebbero tre preferenze
diverse per il modello e tre filtri diversi nel ricettario. Le regole libere
dell'utente (`UserPreferences.notes`) restano il posto per tutto il resto.

La riga che va nel prompt la costruisce `prompt_line()`, ed è lì che vive il vincolo
che rende utile la funzione: **la cucina viaggia, gli ingredienti no.** Scegliere la
cucina giapponese vuol dire chiedere quelle tecniche e quei condimenti con quello che
si compra sotto casa, non mandare l'utente a cercare il mirin — una ricetta che
richiede un negozio specializzato è una ricetta che non si cucina.
"""

import random

# Ogni voce: chiave (che è anche il nome che il modello legge e scrive nei tag),
# etichetta per l'interfaccia, e i termini con cui la si cerca. Gli alias servono
# perché si cerca per paese ("Giappone") o per piatto ("sushi", "curry"), non per
# l'aggettivo — che è il modo in cui la voce è scritta.
_CATALOG: list[tuple[str, list[tuple[str, str, list[str]]]]] = [
    (
        "Italia e Mediterraneo",
        [
            ("italiana", "Italiana", ["italia", "casa", "nonna"]),
            ("mediterranea", "Mediterranea", ["mediterraneo", "dieta mediterranea"]),
            ("siciliana", "Siciliana", ["sicilia", "sud"]),
            ("napoletana", "Napoletana", ["napoli", "campania", "pizza"]),
            ("toscana", "Toscana", ["toscana", "firenze"]),
            ("romana", "Romana", ["roma", "lazio", "carbonara", "cacio e pepe"]),
            ("pugliese", "Pugliese", ["puglia", "orecchiette"]),
            ("ligure", "Ligure", ["liguria", "genova", "pesto"]),
            ("sarda", "Sarda", ["sardegna"]),
            ("greca", "Greca", ["grecia", "feta", "tzatziki", "souvlaki"]),
            ("spagnola", "Spagnola", ["spagna", "tapas", "paella"]),
            ("portoghese", "Portoghese", ["portogallo", "baccala"]),
            ("provenzale", "Provenzale", ["provenza", "francia del sud", "ratatouille"]),
        ],
    ),
    (
        "Europa",
        [
            ("francese", "Francese", ["francia", "bistrot", "parigi"]),
            ("tedesca", "Tedesca", ["germania", "baviera"]),
            ("austriaca", "Austriaca", ["austria", "vienna", "cotoletta"]),
            ("britannica", "Britannica", ["inghilterra", "regno unito", "irlanda", "pub"]),
            ("olandese", "Olandese", ["olanda", "paesi bassi", "belgio", "belga"]),
            ("svizzera", "Svizzera", ["svizzera", "raclette", "fonduta"]),
            (
                "scandinava",
                "Scandinava",
                ["svezia", "norvegia", "danimarca", "finlandia", "nordica", "salmone"],
            ),
            ("polacca", "Polacca", ["polonia", "pierogi"]),
            ("ungherese", "Ungherese", ["ungheria", "gulasch", "paprika"]),
            ("ceca", "Ceca", ["repubblica ceca", "praga", "slovacchia"]),
            (
                "balcanica",
                "Balcanica",
                ["balcani", "croazia", "serbia", "bosnia", "romania", "bulgaria", "albania"],
            ),
            ("russa", "Russa", ["russia", "ucraina", "borsch", "est europa"]),
        ],
    ),
    (
        "Asia",
        [
            ("giapponese", "Giapponese", ["giappone", "sushi", "ramen", "teriyaki"]),
            ("cinese", "Cinese", ["cina", "wok", "saltato", "noodles"]),
            ("coreana", "Coreana", ["corea", "kimchi", "bibimbap"]),
            ("thailandese", "Thailandese", ["thailandia", "thai", "pad thai", "curry"]),
            ("vietnamita", "Vietnamita", ["vietnam", "pho", "involtini"]),
            ("indiana", "Indiana", ["india", "curry", "tandoori", "masala", "dal"]),
            ("nepalese", "Nepalese", ["nepal", "himalaya", "momo"]),
            ("indonesiana", "Indonesiana", ["indonesia", "bali", "malesia", "nasi goreng"]),
            ("filippina", "Filippina", ["filippine", "adobo"]),
            ("taiwanese", "Taiwanese", ["taiwan", "hong kong", "dim sum"]),
        ],
    ),
    (
        "Medio Oriente e Africa",
        [
            ("turca", "Turca", ["turchia", "kebab", "istanbul"]),
            ("libanese", "Libanese", ["libano", "mezze", "hummus", "tabule"]),
            ("israeliana", "Israeliana", ["israele", "falafel", "shakshuka"]),
            ("persiana", "Persiana", ["iran", "persia", "melograno"]),
            (
                "mediorientale",
                "Mediorientale",
                ["medio oriente", "siria", "giordania", "arabo", "tahina"],
            ),
            ("marocchina", "Marocchina", ["marocco", "tajine", "cous cous", "harissa"]),
            ("tunisina", "Tunisina", ["tunisia", "maghreb", "algeria"]),
            ("egiziana", "Egiziana", ["egitto", "koshari", "fave"]),
            ("etiope", "Etiope", ["etiopia", "eritrea", "berbere", "injera"]),
            (
                "africana occidentale",
                "Africana occidentale",
                ["africa", "nigeria", "senegal", "ghana", "arachidi"],
            ),
            ("sudafricana", "Sudafricana", ["sudafrica", "africa del sud"]),
        ],
    ),
    (
        "Americhe",
        [
            ("messicana", "Messicana", ["messico", "tacos", "burrito", "fajitas", "chili"]),
            ("tex-mex", "Tex-Mex", ["texas", "nachos", "quesadilla"]),
            (
                "statunitense",
                "Statunitense",
                ["stati uniti", "america", "usa", "burger", "barbecue"],
            ),
            ("cajun", "Cajun", ["louisiana", "new orleans", "gumbo", "creola"]),
            ("caraibica", "Caraibica", ["caraibi", "giamaica", "cuba", "cocco"]),
            ("brasiliana", "Brasiliana", ["brasile", "feijoada"]),
            ("argentina", "Argentina", ["argentina", "uruguay", "asado", "chimichurri"]),
            ("peruviana", "Peruviana", ["peru", "ceviche", "lima"]),
            ("colombiana", "Colombiana", ["colombia", "venezuela", "arepas"]),
            ("cilena", "Cilena", ["cile"]),
        ],
    ),
    (
        "Oceania",
        [
            ("australiana", "Australiana", ["australia", "nuova zelanda", "brunch"]),
            ("hawaiana", "Hawaiana", ["hawaii", "poke", "polinesia"]),
        ],
    ),
]

# Piatto, per cercare e validare senza riattraversare i gruppi a ogni chiamata.
_BY_KEY: dict[str, str] = {key: label for _, voci in _CATALOG for key, label, _ in voci}


def options() -> dict:
    """Il catalogo per il selettore, raggruppato come si legge.

    Lo serve il backend e non una copia nel frontend per lo stesso motivo del
    questionario: due elenchi che si allontanano fra loro sono un 400 in faccia
    all'utente ("cucina non valida") per una voce aggiunta da una parte sola.
    """
    return {
        "groups": [
            {
                "label": gruppo,
                "cuisines": [
                    {"key": key, "label": label, "aliases": alias}
                    for key, label, alias in voci
                ],
            }
            for gruppo, voci in _CATALOG
        ]
    }


def unknown(keys: list[str]) -> list[str]:
    """Le chiavi che il catalogo non conosce — la riga su cui il router risponde 400."""
    return [k for k in keys if k not in _BY_KEY]


def clean(keys: list[str] | None) -> list[str]:
    """Toglie i doppioni e rimette l'ordine del catalogo.

    L'ordine è quello del catalogo e non quello in cui si è cliccato: la lista finisce
    in un prompt, e la stessa preferenza scritta in due ordini diversi sarebbe due
    stringhe diverse — cioè due contesti diversi a parità di scelte.
    """
    scelte = set(keys or [])
    return [k for k in _BY_KEY if k in scelte]


def labels(keys: list[str] | None) -> list[str]:
    return [_BY_KEY[k] for k in clean(keys)]


# La metà che non si negozia: la cucina la si sceglie per tecniche e condimenti, gli
# ingredienti restano quelli del supermercato sotto casa. Gli esempi da una parte e
# dall'altra ci sono perché "reperibile in Italia" da solo è un giudizio che il
# modello dà a sentimento — con due elenchi corti il confine si vede.
INGREDIENTI_LOCALI = (
    "Un piatto appartiene a una cucina per tecnica, condimenti e struttura, non per "
    "gli ingredienti introvabili: usa SOLO ciò che si compra in un normale "
    "supermercato italiano (salsa di soia, curry in polvere, latte di cocco, zenzero, "
    "lime, tortillas, paprika affumicata, tahina e cous cous ci sono; dashi, mirin, "
    "galanga, foglie di kaffir, gochujang e salse regionali no). Dove il piatto tipico "
    "chiederebbe un ingrediente da negozio specializzato, mettici il sostituto più "
    "vicino e scrivilo in una riga nella descrizione."
)


def draw(
    keys: list[str] | None,
    count: int,
    *,
    avoid: str | None = None,
    rng: random.Random | None = None,
) -> list[str]:
    """Sorteggia `count` cucine fra quelle scelte. Le etichette, pronte per il prompt.

    Il sorteggio lo fa qui Python e non il modello, ed è il punto: «alternale
    nell'arco della settimana» scritto in un prompt non funziona — il modello ancora
    sulla prima voce dell'elenco, o su quella che gli viene più facile, e chi ha
    spuntato otto cucine si ritrova sette cene italiane. Una cucina assegnata è
    un'istruzione; una da alternare è un auspicio.

    **A mazzo, non a dadi.** Si mescola l'elenco e si distribuisce una carta per
    volta, rimescolando quando finisce: con tre cucine su sette giorni ognuna esce
    due o tre volte e nessuna resta fuori. Tirando un dado indipendente per ogni
    giorno, invece, cinque giapponesi e due greche sono un risultato onesto — e
    indistinguibile dal guasto che il sorteggio doveva riparare. Per la stessa
    ragione, a cavallo di due mazzi la stessa cucina non esce due volte di fila.

    `avoid` toglie una cucina dall'estrazione (di solito quella del piatto che si sta
    rifacendo), ma solo finché ne resta almeno un'altra: chi ne ha scelta una sola
    deve poter rigenerare lo stesso.
    """
    disponibili = labels(keys)
    if not disponibili or count <= 0:
        return []

    # `avoid` arriva dai tag di una ricetta, cioè da quello che ha scritto il modello:
    # può essere qualunque cosa, compreso un numero o una lista. Qui non è un dato da
    # validare — serve solo a togliere una carta dal mazzo — quindi quello che non è
    # una stringa non toglie niente, invece di far fallire una rigenerazione pagata.
    if isinstance(avoid, str) and avoid.strip():
        senza = [x for x in disponibili if x.casefold() != avoid.strip().casefold()]
        if senza:
            disponibili = senza
    if len(disponibili) == 1:
        return disponibili * count

    r = rng or random.Random()
    estratte: list[str] = []
    mazzo: list[str] = []
    while len(estratte) < count:
        if not mazzo:
            mazzo = disponibili[:]
            r.shuffle(mazzo)
            if estratte and mazzo[0] == estratte[-1]:
                mazzo[0], mazzo[1] = mazzo[1], mazzo[0]
        estratte.append(mazzo.pop(0))
    return estratte


# La riga del contesto quando il sorteggio è già stato fatto e sta scritto accanto a
# ogni giorno: qui si dice solo che è un'assegnazione e non un suggerimento. Il
# divieto di ripiegare sull'italiana è esplicito perché è il ripiego che il modello
# fa da solo — è la cucina di cui conosce più piatti che stanno nei macro.
PER_GIORNO = (
    "una per giorno, SORTEGGIATA fra quelle scelte dall'utente: la trovi scritta "
    "accanto a ogni giorno in «DA GENERARE», e per quel giorno si cucina quella. Non "
    "sceglierne un'altra, non ripiegare sull'italiana perché è più comoda, non fare "
    "sette volte la stessa. " + INGREDIENTI_LOCALI
)


def prompt_line_one(label: str) -> str:
    """La riga del contesto per un pasto solo, con la cucina già sorteggiata."""
    return (
        f"{label.lower()}, sorteggiata fra quelle scelte dall'utente: il piatto è di "
        f"questa cucina, non di un'altra. " + INGREDIENTI_LOCALI
    )


def prompt_line(keys: list[str] | None) -> str:
    """La riga «Cucina preferita» del contesto.

    Tre casi, non uno: nessuna scelta lascia mano libera al modello (che è quello che
    si aspetta chi quella schermata non l'ha aperta), la sola cucina italiana è il
    default storico e del discorso sugli ingredienti non ha bisogno — ce li ha già
    tutti —, e più cucine insieme vanno **alternate** nell'arco della settimana, o il
    modello prende la prima dell'elenco e ci resta.
    """
    scelte = labels(keys)
    if not scelte:
        return (
            "nessuna preferenza, scegli tu — resta su piatti che si cucinano davvero "
            "in casa con ingredienti da supermercato italiano."
        )
    if scelte == ["Italiana"]:
        return "italiana: piatti di casa, con ingredienti di un supermercato italiano."
    if len(scelte) == 1:
        return f"{scelte[0].lower()}. {INGREDIENTI_LOCALI}"
    elenco = ", ".join(s.lower() for s in scelte)
    return (
        "attingi a queste cucine, alternandole nell'arco della settimana invece di "
        f"restare sulla prima: {elenco}. {INGREDIENTI_LOCALI}"
    )
