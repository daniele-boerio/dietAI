"""Catalogo degli ingredienti comuni italiani: il reparto di ciascuno.

È la fonte unica per due cose: il seed dell'anagrafica (`python -m app.seed`) e la
classificazione degli ingredienti nuovi che l'AI inventa strada facendo. Fino alla
migrazione 0032 portava anche un prezzo medio per la stima della spesa: tolto con la
stima, perché al negozio vero non diceva niente.

Formato: nome → categoria (il reparto della lista della spesa).
"""

import re

INGREDIENT_CATALOG: dict[str, str] = {
    # ── Verdura ──
    "zucchine": "verdura",
    "melanzane": "verdura",
    "pomodori": "verdura",
    "pomodorini": "verdura",
    "pomodori pelati": "verdura",
    "passata di pomodoro": "verdura",
    "peperoni": "verdura",
    "carote": "verdura",
    "cipolle": "verdura",
    "cipolla rossa": "verdura",
    "aglio": "verdura",
    "sedano": "verdura",
    "patate": "verdura",
    "patate dolci": "verdura",
    "spinaci": "verdura",
    "bietola": "verdura",
    "broccoli": "verdura",
    "cavolfiore": "verdura",
    "cavolo nero": "verdura",
    "verza": "verdura",
    "finocchi": "verdura",
    "radicchio": "verdura",
    "lattuga": "verdura",
    "rucola": "verdura",
    "insalata mista": "verdura",
    "cetrioli": "verdura",
    "zucca": "verdura",
    "asparagi": "verdura",
    "carciofi": "verdura",
    "funghi champignon": "verdura",
    "funghi porcini": "verdura",
    "fagiolini": "verdura",
    "piselli": "verdura",
    "porri": "verdura",
    "cicoria": "verdura",
    "cavolini di bruxelles": "verdura",
    "prezzemolo": "verdura",
    "basilico": "verdura",
    "rosmarino": "verdura",
    "salvia": "verdura",
    # ── Frutta ──
    "mele": "frutta",
    "pere": "frutta",
    "banane": "frutta",
    "arance": "frutta",
    "mandarini": "frutta",
    "limoni": "frutta",
    "pompelmo": "frutta",
    "kiwi": "frutta",
    "fragole": "frutta",
    "ciliegie": "frutta",
    "pesche": "frutta",
    "albicocche": "frutta",
    "susine": "frutta",
    "uva": "frutta",
    "melone": "frutta",
    "anguria": "frutta",
    "fichi": "frutta",
    "cachi": "frutta",
    "melagrana": "frutta",
    "mirtilli": "frutta",
    "lamponi": "frutta",
    "ananas": "frutta",
    "avocado": "frutta",
    "frutta mista": "frutta",  # "secca" è conservazione: via dal nome
    "mandorle": "frutta",
    "noci": "frutta",
    "nocciole": "frutta",
    "pinoli": "frutta",
    "pistacchi": "frutta",
    "uvetta": "frutta",
    # ── Carne ──
    "petto di pollo": "carne",
    "cosce di pollo": "carne",
    "fesa di tacchino": "carne",
    "manzo": "carne",  # "macinato" è un taglio: via dal nome
    "fettine di manzo": "carne",
    "vitello": "carne",
    "lonza di maiale": "carne",
    "salsiccia": "carne",
    "prosciutto crudo": "carne",
    "prosciutto cotto": "carne",
    "bresaola": "carne",
    "speck": "carne",
    "pancetta": "carne",
    "guanciale": "carne",
    "coniglio": "carne",
    # ── Pesce ──
    "salmone": "pesce",
    "salmone affumicato": "pesce",
    "tonno": "pesce",  # quello al banco; in scatola sta qui sotto
    "tonno in scatola": "pesce",
    "sgombro": "pesce",
    "alici": "pesce",
    "gamberi": "pesce",
    "calamari": "pesce",
    "seppie": "pesce",
    "cozze": "pesce",
    "vongole": "pesce",
    # ── Latticini e uova ──
    "latte": "latticini",
    "latte scremato": "latticini",
    "yogurt greco": "latticini",
    "yogurt bianco": "latticini",
    "ricotta": "latticini",
    "mozzarella": "latticini",
    "mozzarella di bufala": "latticini",
    "stracchino": "latticini",
    "philadelphia": "latticini",
    "fiocchi di latte": "latticini",
    "burro": "latticini",
    "panna da cucina": "latticini",
    "uova": "uova",
    "albume": "uova",
    # ── Cereali e derivati ──
    "pasta": "cereali",
    "riso": "cereali",
    "riso integrale": "cereali",
    "riso basmati": "cereali",
    "orzo perlato": "cereali",
    "farro": "cereali",
    "quinoa": "cereali",
    "cous cous": "cereali",
    "pane": "cereali",
    "pane integrale": "cereali",
    "fette biscottate": "cereali",
    "pane azzimo": "cereali",
    "farina 00": "cereali",
    "farina integrale": "cereali",
    "polenta": "cereali",
    "avena": "cereali",
    "fiocchi d'avena": "cereali",
    "pangrattato": "cereali",
    "gnocchi": "cereali",
    "cous cous integrale": "cereali",
    # ── Legumi ──
    "ceci": "legumi",
    "ceci in scatola": "legumi",
    "lenticchie": "legumi",
    "fagioli borlotti": "legumi",
    "fagioli cannellini": "legumi",
    "fave": "legumi",
    "soia": "legumi",
    "tofu": "legumi",
    "hummus": "legumi",
    # ── Condimenti e dispensa ──
    # Elisa, come la normalizzazione scrive ogni "di" davanti a vocale: il seed semina
    # l'anagrafica con questi nomi così come sono scritti, e un nome che
    # `normalize_name` non può più produrre sarebbe una riga che nessuna ricetta userà
    # mai — ricreata a ogni avvio del container.
    "olio extravergine d'oliva": "condimenti",
    "olio di semi": "condimenti",
    "aceto di vino": "condimenti",
    "aceto balsamico": "condimenti",
    "sale": "condimenti",
    "pepe nero": "condimenti",
    "zucchero": "condimenti",
    "miele": "condimenti",
    "origano": "condimenti",
    "peperoncino": "condimenti",
    "curry": "condimenti",
    "paprika": "condimenti",
    "curcuma": "condimenti",
    "cannella": "condimenti",
    "noce moscata": "condimenti",
    "senape": "condimenti",
    # ── Le salse che fanno un piatto straniero ──
    # Stanno a catalogo perché il prompt le chiama per nome (`INGREDIENTI_LOCALI`: non
    # si riducono tutte alla salsa di soia), e un nome che arriva in lista senza riga
    # di anagrafica prende il reparto che `guess_category` indovina — che qui sbaglia
    # proprio sulle più usate: "salsa di pesce" finisce al banco del pesce, "pasta di
    # curry" fra i cereali, "latte di cocco" fra i latticini. Si compra una bottiglia e
    # dura mesi, che è la ragione per cui queste salse si possono chiedere.
    "salsa di soia": "condimenti",
    "salsa teriyaki": "condimenti",
    # Elisa, come la scrive `normalize_name` ("salsa di ostriche" → "salsa d'ostriche").
    "salsa d'ostriche": "condimenti",
    "salsa di pesce": "condimenti",
    "salsa hoisin": "condimenti",
    "sriracha": "condimenti",
    "gochujang": "condimenti",
    "miso": "condimenti",
    "mirin": "condimenti",
    "aceto di riso": "condimenti",
    "olio di sesamo": "condimenti",
    "pasta di curry": "condimenti",
    "latte di cocco": "condimenti",
    "tahina": "condimenti",
    "harissa": "condimenti",
    "brodo vegetale": "condimenti",
    "lievito": "condimenti",
    "cacao amaro": "condimenti",
    "cioccolato fondente": "condimenti",
    "vino bianco": "bevande",
    "vino rosso": "bevande",
    # ── Piatti pronti e semilavorati ──
    # "Surgelato" non fa più parte del nome (lo toglie `normalize_name`: è come è
    # conservato, non cos'è), quindi qui non ci sono più voci col surgelato accanto —
    # spinaci e piselli hanno già la loro riga sopra. Il reparto lo sposta l'utente
    # dalla lista della spesa, che è l'unico posto da cui si vede il proprio negozio.
    "minestrone": "verdura",
    # I nomi che la normalizzazione fabbrica unendo alimenti diversi: branzino, orata
    # e merluzzo finiscono in "filetto di pesce magro", parmigiano e grana in
    # "formaggio". Le loro righe qui sopra sono state tolte apposta — il catalogo
    # semina l'anagrafica coi nomi così come sono scritti, e un nome che
    # `normalize_name` non può produrre diventa una riga che nessuna ricetta userà mai.
    "filetto di pesce magro": "pesce",
    "formaggio": "latticini",
}

# Ingredienti proposti come "di base" al primo avvio: quelli che chiunque ha in casa
# e che in lista della spesa farebbero solo rumore.
DEFAULT_BASE_INGREDIENTS = [
    "olio extravergine d'oliva",
    "sale",
    "pepe nero",
    "aceto di vino",
    "zucchero",
    "aglio",
    "origano",
]

# Parole chiave per indovinare la categoria di un ingrediente che non è a catalogo
# (l'AI ne inventa di continuo). Sono **inizi di parola**, non pezzi qualsiasi: come
# le legge `guess_category` è scritto lì.
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("pesce", ("pesce", "salmone", "tonno", "merluzzo", "orata", "branzino", "gambero",
               "calamar", "seppi", "cozz", "vongol", "alici", "acciug", "sgombro", "gamber",
               "platessa", "polpo", "sogliola", "trota", "baccalà")),
    ("carne", ("pollo", "tacchino", "manzo", "vitello", "maiale", "agnello", "coniglio",
               "salsicc", "prosciutto", "bresaola", "speck", "pancetta", "guanciale",
               "wurstel", "hamburger", "carne", "bistecc", "arrosto", "mortadella",
               "salame")),
    ("latticini", ("latte", "yogurt", "ricotta", "mozzarella", "formaggio", "parmigiano",
                   "grana", "pecorino", "stracchino", "mascarpone", "burro", "panna",
                   "scamorza", "provola", "gorgonzola", "feta", "philadelphia",
                   "fiocchi di latte", "caciotta")),
    ("uova", ("uovo", "uova", "albume", "tuorlo")),
    ("legumi", ("cec", "lentic", "fagiol", "fave", "soia", "tofu",
                "tempeh", "hummus", "lupini", "edamame")),
    ("cereali", ("pasta", "riso", "pane", "farina", "farro", "orzo", "quinoa", "avena",
                 "cous", "polenta", "gnocchi", "crackers", "fette biscottate", "cereali",
                 "grissini", "piadina", "tortilla", "bulgur", "miglio", "mais",
                 "pangrattato", "biscott")),
    ("frutta", ("mel", "pera", "pere", "banan", "arance", "arancia", "mandarin", "limon",
                "pompelmo", "kiwi", "fragol", "cilieg", "pesc", "albicocc", "susin",
                "uva", "melone", "anguria", "fich", "cachi", "melagrana", "mirtill",
                "lampon", "ananas", "avocado", "mandorl", "noci", "nocciol", "pinoli",
                "pistacch", "uvetta", "datter", "prugn", "frutta")),
    # Nessuna parola chiave per i surgelati: "surgelato" e "congelato" li toglie la
    # normalizzazione prima di arrivare qui, quindi un nome che li contenga non
    # esiste. Il reparto resta, ma ce le mette l'utente, che sa dove sono nel suo
    # supermercato — un tacchino surgelato non è nel banco del pesce solo perché è
    # nel congelatore.
    ("bevande", ("acqua", "vino", "birra", "succo", "tè", "the", "caffè", "bevanda")),
    ("condimenti", ("olio", "aceto", "sale", "pepe", "zucchero", "miele", "spezi",
                    "origano", "peperoncino", "curry", "paprika", "curcuma", "cannella",
                    "noce moscata", "senape", "salsa", "brodo", "lievito", "cacao",
                    "cioccolat", "vaniglia", "maionese", "ketchup", "erbe", "aroma",
                    "teriyaki", "hoisin", "sriracha", "gochujang", "miso", "mirin",
                    "tahin", "harissa", "pasta di curry", "latte di cocco")),
    ("verdura", ("zucchin", "melanzan", "pomodor", "peperon", "carot", "cipoll", "aglio",
                 "sedano", "patat", "spinac", "bietol", "broccol", "cavol", "verza",
                 "finocch", "radicch", "lattug", "rucola", "insalat", "cetriol", "zucca",
                 "asparag", "carciof", "fungh", "fagiolin", "pisell", "porr", "cicoria",
                 "prezzemolo", "basilico", "rosmarino", "salvia", "menta", "ravanell",
                 "barbabietol", "sedano rapa", "topinambur", "germogli", "verdur", "minestron")),
]


_INIZI_DI_PAROLA = re.compile(r"(?:^|(?<=[\s'-]))\w")


def guess_category(name: str) -> str:
    """Categoria per un ingrediente non a catalogo. Ripiega su "altro".

    Due regole, e tutte e due vengono da un errore. La prima: una parola chiave vale
    solo **all'inizio di una parola**. Cercata in mezzo, "pepe" stava dentro
    "peperoni" (finiti fra i condimenti), "grana" dentro "melagrana" (fra i
    latticini), "mel" dentro qualunque cosa cominciasse diversamente.

    La seconda: in italiano il nome che conta è il **primo**, il resto lo qualifica —
    "salsa di pesce" è una salsa, "aceto di riso" un aceto, "petto di pollo" (dove
    "petto" non dice niente) è pollo. Quindi si scorre il nome parola per parola, e la
    prima parola che riconosce qualcosa decide; se ci sono più parole chiave che vi
    combaciano vince la più lunga, che è la più precisa ("peperon" batte "pepe",
    "fagiolin" batte "fagiol", "pesce" batte "pesc"). L'ordine delle categorie non
    conta più: conta solo per i pareggi esatti, che non succedono.
    """
    n = name.strip().lower()
    for inizio in _INIZI_DI_PAROLA.finditer(n):
        resto = n[inizio.start():]
        migliore = max(
            (
                (len(k), category)
                for category, keywords in _CATEGORY_KEYWORDS
                for k in keywords
                if resto.startswith(k)
            ),
            default=None,
            key=lambda c: c[0],
        )
        if migliore:
            return migliore[1]
    return "altro"


def catalog_entry(name: str) -> str | None:
    return INGREDIENT_CATALOG.get(name.strip().lower())
