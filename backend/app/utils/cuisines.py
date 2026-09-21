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


# Quanto pesa poco una cucina che resta comunque in elenco. Zero non si usa: una
# voce spuntata che non può mai uscire è una voce che mente, e chi non la vuole più
# la toglie. Di riflesso il massimo per una sola è 100 meno le altre.
QUOTA_MINIMA = 1

# Sopra la dozzina "attingi a queste" equivale a non aver chiesto niente, con in più
# i token per dirlo — e con quote da 8% l'una il sorteggio su sette giorni ne
# pescherebbe comunque solo una manciata.
MAX_CUCINE = 12


def _as_shares(value: object) -> dict[str, float]:
    """Le due forme in cui una preferenza può arrivare, ridotte a una.

    In archivio esistono ancora le righe della prima versione, che erano un elenco
    senza quote (`["italiana", "greca"]`): valevano "queste, in parti uguali", ed è
    esattamente quello che diventano qui. Leggerle invece di migrarle è una scelta:
    una migrazione che riscrive un JSON per dire la stessa cosa è una migrazione che
    può solo introdurre bug, e la riga si riscrive da sé al primo salvataggio.
    """
    if isinstance(value, dict):
        quote: dict[str, float] = {}
        for key, peso in value.items():
            if not isinstance(key, str):
                continue
            try:
                n = float(peso)
            except (TypeError, ValueError):
                n = 0.0
            quote[key] = max(n, 0.0)
        return quote
    if isinstance(value, (list, tuple, set)):
        return {k: 1.0 for k in value if isinstance(k, str)}
    return {}


def unknown(value: object) -> list[str]:
    """Le chiavi che il catalogo non conosce — la riga su cui il router risponde 400."""
    return [k for k in _as_shares(value) if k not in _BY_KEY]


def clean(value: object) -> dict[str, int]:
    """Le cucine scelte con la loro quota: interi che sommano a **100**, in ordine di catalogo.

    L'ordine è quello del catalogo e non quello in cui si è cliccato: la preferenza
    finisce in un prompt, e la stessa scelta scritta in due ordini diversi sarebbe due
    contesti diversi a parità di cucine.

    Le quote si normalizzano sempre, anche quando arrivano già a 100: è l'unico modo
    perché la somma sia 100 **davvero** dopo che una voce è stata tolta, o che una
    riga vecchia senza quote è stata letta come parti uguali. Il resto
    dell'arrotondamento va sulla quota più grande, dove si nota meno — la stessa
    aritmetica di `_share_out` e di `lib/macros.js`, applicata qui alle cucine.
    """
    quote = {k: v for k, v in _as_shares(value).items() if k in _BY_KEY}
    ordinate = [k for k in _BY_KEY if k in quote]
    if not ordinate:
        return {}

    # **Se c'è, è scelta: il numero dice solo quanto.** Una quota a zero non la si
    # scarta — la si porta al minimo — perché il numero e la spunta sono due cose
    # diverse e chi tira un cursore a fondo corsa non sta togliendo la voce, che ha
    # la sua X apposta. Scartandola, la cucina sparirebbe dall'elenco al salvataggio
    # e ricomparirebbe solo ri-cercandola.
    totale = sum(quote[k] for k in ordinate)
    if totale <= 0:
        quote = {k: 1.0 for k in ordinate}
        totale = float(len(ordinate))
    interi = {k: round(100 * quote[k] / totale) for k in ordinate}
    # Il minimo va applicato prima del pareggio del resto, o riportarlo su romperebbe
    # di nuovo la somma.
    interi = {k: max(v, QUOTA_MINIMA) for k, v in interi.items()}

    scarto = 100 - sum(interi.values())
    if scarto:
        # In diminuzione non si scende sotto il minimo: si passa alla successiva.
        for k in sorted(ordinate, key=lambda k: interi[k], reverse=(scarto > 0)):
            passo = scarto if scarto > 0 else max(scarto, QUOTA_MINIMA - interi[k])
            interi[k] += passo
            scarto -= passo
            if not scarto:
                break
    return interi


def keys_of(value: object) -> list[str]:
    """Solo le chiavi, in ordine di catalogo."""
    return list(clean(value))


def labels(value: object) -> list[str]:
    return [_BY_KEY[k] for k in clean(value)]


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


def _quante_volte(quote: dict[str, int], count: int, r: random.Random) -> dict[str, int]:
    """Quante caselle spettano a ciascuna cucina: il metodo del resto più grande.

    Non si tira un dado per ogni giorno. Con 70/30 su sette giorni un dado dà cinque
    italiane e due greche *in media*, ma la settimana che si genera adesso è una
    sola: sette italiane di fila sono un risultato onesto del dado e, per chi guarda
    il piano, sono il guasto che le percentuali dovevano riparare. Contando prima le
    caselle, il 70% è 70% **di questa settimana**.

    Il resto va a chi ha la parte frazionaria più alta, coi pareggi sciolti a caso
    (di qui il mescolìo prima dell'ordinamento, che è stabile): senza, con tre cucine
    in parti uguali la carta in più sarebbe sempre della prima in ordine di catalogo.
    """
    totale = sum(quote.values())
    esatti = {k: count * v / totale for k, v in quote.items()}
    volte = {k: int(x) for k, x in esatti.items()}

    ordine = list(quote)
    r.shuffle(ordine)
    ordine.sort(key=lambda k: esatti[k] - volte[k], reverse=True)
    for k in ordine[: count - sum(volte.values())]:
        volte[k] += 1
    return volte


def _sta_bene(fila: list[str], p: int) -> bool:
    """La casella `p` non ha la stessa cucina di chi le sta accanto."""
    return (p == 0 or fila[p] != fila[p - 1]) and (
        p == len(fila) - 1 or fila[p] != fila[p + 1]
    )


def _distanziate(volte: dict[str, int], r: random.Random) -> list[str]:
    """Mette in fila le caselle contate, distanziando le ripetizioni.

    Le cinque italiane di una settimana al 70% vanno sparse, non messe in coda. Il
    modo ovvio — pescare ogni volta la cucina a cui ne restano di più, saltando quella
    appena uscita — distanzia bene ma è **sempre la stessa fila**: con 5/1/1 esce
    «italiana, greca, italiana, giapponese, italiana, italiana, italiana» ogni
    benedetta settimana, e un sorteggio che dà sempre lo stesso risultato è il guasto
    di partenza servito una riga più in là.

    Quindi si assegna a ogni casella una posizione: la i-esima di una cucina che ne ha
    `n` cade a caso dentro l'i-esima fetta di settimana larga `1/n`. Le cinque
    italiane finiscono una per fetta — sparse per costruzione — ma **dove** dentro la
    fetta lo decide il caso, e la fila cambia a ogni generazione.

    Resta da riparare quello che le fette non garantiscono: due fette confinanti
    possono consegnare la stessa cucina a cavallo del confine. Chi si trova un gemello
    accanto cerca uno scambio che sistemi tutt'e due i posti; se non c'è, si ripete —
    con l'80% su cinque giorni due di fila sono aritmetica, non un difetto, ed è
    esattamente quello che l'utente ha chiesto.
    """
    coppie = [
        ((i + r.random()) / n, k) for k, n in volte.items() for i in range(n) if n > 0
    ]
    # Il caso ha già sciolto ogni pareggio (due chiavi identiche sono impossibili),
    # quindi si ordina sulla sola posizione: le cucine non vanno confrontate fra loro.
    coppie.sort(key=lambda c: c[0])
    fila = [k for _, k in coppie]

    for i in range(1, len(fila)):
        if fila[i] != fila[i - 1]:
            continue
        posizioni = [j for j in range(len(fila)) if j != i]
        r.shuffle(posizioni)
        for j in posizioni:
            fila[i], fila[j] = fila[j], fila[i]
            if _sta_bene(fila, i) and _sta_bene(fila, j):
                break
            fila[i], fila[j] = fila[j], fila[i]
    return fila


def draw(
    value: object,
    count: int,
    *,
    avoid: str | None = None,
    rng: random.Random | None = None,
) -> list[str]:
    """Sorteggia `count` cucine fra quelle scelte, rispettandone le quote.

    Le etichette, pronte per il prompt. Il sorteggio lo fa qui Python e non il
    modello, ed è il punto: «alternale nell'arco della settimana» scritto in un
    prompt non funziona — il modello ancora sulla prima voce dell'elenco, o su quella
    che gli viene più facile, e chi ha spuntato otto cucine si ritrova sette cene
    italiane. Una cucina assegnata è un'istruzione; una da alternare è un auspicio.

    Due passaggi, e sono due domande diverse: **quante** caselle per ciascuna
    (`_quante_volte`, che fa valere le percentuali su questa settimana e non sulla
    media di infinite settimane) e **in che ordine** (`_distanziate`, che tiene le
    ripetizioni lontane fin dove le quote lo permettono).

    `avoid` toglie una cucina dall'estrazione (di solito quella del piatto che si sta
    rifacendo), ma solo finché ne resta almeno un'altra: chi ne ha scelta una sola
    deve poter rigenerare lo stesso.
    """
    quote = clean(value)
    if not quote or count <= 0:
        return []

    # `avoid` arriva dai tag di una ricetta, cioè da quello che ha scritto il modello:
    # può essere qualunque cosa, compreso un numero o una lista. Qui non è un dato da
    # validare — serve solo a togliere una carta dal mazzo — quindi quello che non è
    # una stringa non toglie niente, invece di far fallire una rigenerazione pagata.
    if isinstance(avoid, str) and avoid.strip():
        fuori = avoid.strip().casefold()
        resto = {k: v for k, v in quote.items() if _BY_KEY[k].casefold() != fuori}
        if resto:
            quote = resto
    if len(quote) == 1:
        return [_BY_KEY[next(iter(quote))]] * count

    r = rng or random.Random()
    return [_BY_KEY[k] for k in _distanziate(_quante_volte(quote, count, r), r)]


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


def prompt_line(value: object) -> str:
    """La riga «CUCINE da cui attingere» del contesto, per chi non ha sorteggiato.

    Tre casi, non uno: nessuna scelta lascia mano libera al modello (che è quello che
    si aspetta chi quella schermata non l'ha aperta), la sola cucina italiana è il
    default storico e del discorso sugli ingredienti non ha bisogno — ce li ha già
    tutti —, e più cucine insieme si dicono **con le loro quote**.

    Le percentuali ci sono anche qui, dove nessuno sorteggia, perché questa riga la
    leggono le chat: chiedendo un'alternativa a un piatto, la proporzione dice da che
    parte guardare — con 70% italiana e 30% greca il sostituto giusto è quasi sempre
    italiano, e senza quel numero le due cucine peserebbero uguale.
    """
    quote = clean(value)
    if not quote:
        return (
            "nessuna preferenza, scegli tu — resta su piatti che si cucinano davvero "
            "in casa con ingredienti da supermercato italiano."
        )
    if list(quote) == ["italiana"]:
        return "italiana: piatti di casa, con ingredienti di un supermercato italiano."
    if len(quote) == 1:
        return f"{_BY_KEY[next(iter(quote))].lower()}. {INGREDIENTI_LOCALI}"
    elenco = ", ".join(f"{_BY_KEY[k].lower()} {v}%" for k, v in quote.items())
    return (
        "attingi a queste cucine, in queste proporzioni sul totale dei piatti: "
        f"{elenco}. {INGREDIENTI_LOCALI}"
    )
