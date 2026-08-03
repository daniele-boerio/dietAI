"""Anagrafica ingredienti: normalizzazione dei nomi e creazione al volo.

L'AI genera nomi liberi ("Zucchine", "zucchine medie", "ZUCCHINE"). Se finissero in
tabella così come sono, la lista della spesa avrebbe tre righe di zucchine e la
dispensa non ne coprirebbe nessuna. Qui si normalizza e si riusa sempre la stessa riga.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    BaseIngredient,
    ExcludedIngredient,
    Ingredient,
    NormalizationRule,
    PantryItem,
    PlannedMeal,
    RecipeIngredient,
    ShoppingListItem,
)
from ..utils.pricing import INGREDIENT_CATALOG, catalog_entry, guess_category
from ..utils.seasonality import season_months_for
from ..utils.units import to_base

# Qualificatori che si tolgono dal nome. La linea di taglio: via tutto ciò che dice
# **com'è messo** l'alimento — conservazione, taglio, calibro — e resta tutto ciò che
# dice **cos'è**. "Pesce spada surgelato" e "pesce spada fresco" sono lo stesso pesce
# comprato in due banchi diversi, e chi fa la spesa lo sa già; "mandorle a lamelle"
# sono mandorle.
#
# Restano fuori di proposito le parole che cambiano i numeri della dieta — integrale,
# magro, light, intero, al naturale, sott'olio, senza zuccheri — perché lì cambia
# l'alimento, non la sua confezione: uno yogurt magro e uno intero non sono la stessa
# riga della spesa nemmeno volendo. Fuori anche "pelati", che in italiano non è lo
# stato dei pomodori ma una conserva.
#
# I termini stanno in tuple e non dentro la regex già compilata perché sono anche
# **contenuto**: le Impostazioni li mostrano uno per uno (Impostazioni →
# Normalizzazione), e una lista che si può leggere è l'unico modo di accorgersi che
# una parola manca. Sono schemi, non parole: `fresc[ao]` copre fresco e fresca.
_NOISE_GROUPS = {
    "Marchi e denominazioni": (
        "hero", "barilla", r"de\s+cecco", "rustichella", "garofalo", "buitoni",
        "mutti", "sa", "valfrutta", "unifruit", "reggiano",
    ),
    "Conservazione e stato": (
        "fresc[ao]", "fresch[ei]", "secc[ao]", "secch[ei]", "surgelat[oaie]",
        "congelat[oaie]", "sgusciat[oaie]", "sbucciat[oaie]", "maturo", "matura",
        # Quello che fai tu in cucina prima di pesarlo: il tonno lo compri in scatola
        # e basta ("tonno al naturale" e "tonno al naturale sgocciolato" erano due
        # righe, e la dispensa non copriva l'altra).
        "sgocciolat[oaie]", "scolat[oaie]",
    ),
    "Calibro e qualità": (
        "medi[ao]", "medie", "grande", "grandi", "piccol[oaie]", "bio", "biologic[ao]",
    ),
    "Taglio e preparazione": (
        "tritat[oaie]", "macinat[oaie]", "grattugiat[oaie]", "affettat[oaie]",
        r"a\s+cubetti", r"a\s+dadini", r"a\s+fette", r"a\s+fettine", r"a\s+rondelle",
        r"a\s+lamelle", r"a\s+listarelle", r"a\s+striscioline", r"a\s+julienne",
        r"a\s+spicchi", r"a\s+pezzi", r"a\s+pezzetti", r"in\s+scaglie", r"in\s+filetti",
    ),
    # "pasta corta" è pasta, come "pasta di semola di grano duro" — dicono che taglio
    # è, non che alimento è, e al supermercato si compra un pacco solo. Restano fuori i
    # formati con un'identità propria ("pasta all'uovo", "pasta sfoglia") e
    # "integrale", che sta fra le parole che cambiano i macro.
    "Formato e quantità": (
        "cort[aeio]", "lung[ao]", "lungh[ei]", "formato",
        r"di\s+semola(\s+di\s+grano\s+duro)?", r"q\.?b\.?",
    ),
}

# Formati di pasta da normalizzare a "pasta": penne o fusilli sono lo stesso pacco
# per la spesa e lo stesso alimento per la dieta.
#
# **Qui dentro ci va solo pasta.** Un altro cereale è un altro alimento, con altri
# macro e un altro scaffale: riso, cous cous, orzo, farro e quinoa restano quello che
# sono. Fuori anche la pasta ripiena (ravioli, tortellini: dentro c'è carne o
# formaggio) e gli gnocchi, che sono patate.
_PASTA_NAMES = (
    "spaghetti", "penne", "fusilli", "farfalle", "rigatoni", "sedani", "bucatini",
    "linguine", "fettuccine", "tagliatelle", "bavette", "trenette", "vermicelli",
    "pennette", "mezzemaniche", "tortiglioni", "tagliolini", "pappardelle",
    "maltagliati", "casarecce", "orecchiette", "rotelle", "conchiglie", "tubetti",
    "ditalini",
)

# Tipi di pesce magro da normalizzare a "filetto di pesce magro"
_PESCE_NAMES = ("branzino", "orata", "sogliola", "merluzzo", "platessa")

# Gamberi: togliere qualificatori geografici e conservare solo "gamberi"
_GAMBERI_QUALIFIERS = ("indopacifici?", "rossi?", "bianchi?", r"di\s+\w+")

# I formaggi da grattugia stanno tutti sulla riga "formaggio", che è come li chiama la
# dieta: sulla pasta ci va quello che c'è in casa. Si confronta il **nome intero**, non
# una parola qualsiasi dentro — "formaggio spalmabile" è un altro alimento, e cercare
# "grana" in mezzo a un nome trasformava "grana padano" in "formaggio padano".
_DA_GRATTUGIA = {
    "parmigiano",
    "parmigiano reggiano",
    "grana",
    "grana padano",
    "pecorino",
    "pecorino romano",
}

# Olive: togliere tipi e qualificatori, conservare solo "olive"
_OLIVE_QUALIFIERS = (
    "taggiasche", "nere", "verdi", "denocciolate", "snocciolate", r"di\s+\w+",
)
# I tre che si dicono anche prima del nome ("olive nere" ma anche "nere olive").
_OLIVE_PREFISSI = ("taggiasche", "nere", "verdi")

# Varianti di scrittura: la stessa parola scritta in due modi. Non è un accorpamento —
# non si uniscono due alimenti diversi — è lo stesso identico alimento che il modello
# scrive come gli viene, e che in anagrafica fa una riga in più (e una dispensa che non
# copre la ricetta: 865 g di "cous cous" in casa e la lista che chiede "couscous").
# Vale sulla parola, non sul nome intero, o "couscous integrale" resterebbe fuori.
_VARIANTI = {"cous cous": ("couscous",)}

# Peperoni: il colore è come il calibro — dice com'è fatto, non cos'è. Rosso e giallo
# stanno nello stesso banco, costano uguale e in una ricetta si scambiano senza che
# cambi un macro; tenerli separati vuol dire due righe nella lista della spesa e una
# dispensa che non copre né l'una né l'altra. Vale anche al singolare, e per più colori
# di fila ("peperoni rossi e gialli"), perché è così che li scrive il modello.
_PEPERONI_QUALIFIERS = ("ross[oaie]", "giall[oaie]", "verd[ei]", "mist[oaie]")

# Quello che sta fra parentesi è sempre una glossa, mai l'alimento: "pasta corta
# (penne)", "legumi (ceci o fagioli)". Si toglie prima dei qualificatori, o resterebbe
# attaccato al nome e farebbe una riga a sé nella lista della spesa.
_PARENTESI = re.compile(r"\([^)]*\)")

# Preposizioni rimaste appese dopo aver tolto un qualificatore ("mandorle a" → "mandorle").
_DANGLING = re.compile(r"\s+(a|di|in|al|alla|con|da)\s*$", re.IGNORECASE)

# La pasta è pasta: "fusilli integrali" e "pasta integrale" sono la stessa riga della
# spesa e lo stesso piatto. È l'unica eccezione alla regola per cui "integrale" resta
# (vale ancora per il pane e per il riso, dove è un altro alimento sullo scaffale).
_PASTA_INTEGRALE = re.compile(r"\bpasta\s+integral[ei]\b", re.IGNORECASE)

# Segni che a schermo sono lo stesso segno e per il database no. È il doppione
# peggiore che ci sia: in dispensa compaiono due righe di "tonno all'olio d'oliva"
# identiche a vedersi — una scritta con l'apostrofo dritto, l'altra con quello
# tipografico che il modello mette da sé — e non c'è modo di accorgersene guardando,
# né di correggerle con una regola scritta a mano, perché anche quella andrebbe
# scritta con l'apostrofo giusto. Qui i due caratteri diventano uno solo, e con loro
# gli spazi che non si vedono (lo spazio unificatore) e i trattini lunghi.
_SEGNI = str.maketrans(
    {
        "’": "'", "‘": "'", "ʼ": "'", "´": "'", "`": "'",
        " ": " ", " ": " ", " ": " ",  # spazi che non si vedono
        "‐": "-", "‑": "-", "–": "-", "—": "-",
    }
)
# Lo spazio attorno all'apostrofo non c'è mai: "all' olio" è "all'olio".
_APOSTROFO = re.compile(r"\s*'\s*")
# "olio di oliva" e "olio d'oliva" sono la stessa bottiglia. Si tiene la forma elisa,
# che è quella che l'italiano scrive davvero e quella che il catalogo usa già
# ("fiocchi d'avena").
_ELISIONE = re.compile(r"\bdi\s+(?=[aeiou])")


def _segni(name: str) -> str:
    """Minuscolo e con un solo modo di scrivere apostrofi, spazi ed elisioni."""
    n = (name or "").strip().lower().translate(_SEGNI)
    return _ELISIONE.sub("d'", _APOSTROFO.sub("'", n))


# Singolare e plurale sono lo stesso alimento, ma il modello scrive ora l'uno ora
# l'altro: "peperone" oggi, "peperoni" domani, e sono due righe di anagrafica — cioè
# una dispensa che non copre la ricetta e due voci nella lista della spesa. La forma
# buona è quella del catalogo, perché è il nome a cui sono attaccati reparto e prezzo.
#
# La mappa si **deriva** dal catalogo invece di scriverla a mano: un elenco a parte
# resterebbe indietro al primo ingrediente aggiunto, e sarebbe una bugia scritta
# proprio dove si va a capire perché due righe si sono fuse. Si generano solo le
# coppie che in italiano sono davvero singolare/plurale (o↔i, a↔e, e↔i): senza quel
# vincolo "pesca" e "pesce" avrebbero lo stesso gambo e la frutta diventerebbe pesce.
_COPPIE = (("o", "i"), ("i", "o"), ("a", "e"), ("e", "a"), ("e", "i"), ("i", "e"))

# I plurali che nessuna regola sulla vocale finale può indovinare.
_IRREGOLARI = {"uovo": "uova"}


def _catalog_forms() -> dict[str, str]:
    forme: dict[str, set[str]] = {}
    for name in INGREDIENT_CATALOG:
        # Solo i nomi di una parola: "petto di pollo" non lo si scrive al plurale, e
        # declinare ogni parola di un nome composto moltiplicherebbe le forme senza
        # che ne serva nemmeno una.
        if " " in name or len(name) < 4 or name[-1] not in "aeiou":
            continue
        for finale, altra in _COPPIE:
            if name[-1] == finale:
                forme.setdefault(name[:-1] + altra, set()).add(name)

    # Una forma che porta a due nomi del catalogo non decide niente da sola, e una che
    # è già un nome del catalogo è già un alimento suo: in tutti e due i casi si lascia
    # stare, perché unire due alimenti diversi è un danno che si disfa a mano.
    forms = {
        forma: next(iter(nomi))
        for forma, nomi in forme.items()
        if len(nomi) == 1 and forma not in INGREDIENT_CATALOG
    }
    forms.update(_IRREGOLARI)
    return forms


_CATALOG_FORMS = _catalog_forms()


def _tidy(n: str) -> str:
    """Spazi doppi, virgole e preposizioni appese dopo aver tolto una parola."""
    n = re.sub(r"[\s,;]+", " ", n).strip(" -,.")
    return _DANGLING.sub("", n).strip(" -,.")


def _alt(terms: tuple[str, ...]) -> str | None:
    """L'alternanza `a|b|c`, o niente se non è rimasto nessun termine acceso."""
    return "|".join(terms) or None


@dataclass(frozen=True)
class _Builtin:
    """Le regex di serie, già filtrate dei termini spenti dall'utente."""

    noise: re.Pattern | None
    pasta: re.Pattern | None
    pesce: re.Pattern | None
    gamberi: re.Pattern | None
    olive: re.Pattern | None
    peperoni: re.Pattern | None
    varianti: tuple[tuple[str, re.Pattern], ...]
    grattugia: frozenset


@lru_cache(maxsize=32)
def _builtin(spenti: frozenset) -> _Builtin:
    """Compila le regole di serie senza i termini disattivati.

    In cache perché l'insieme dei termini spenti cambia una volta ogni mai, mentre
    normalizzare succede cento volte per generazione. Con l'insieme vuoto — il caso
    normale — escono esattamente le regex di prima.
    """
    tieni = lambda terms: tuple(t for t in terms if t not in spenti)  # noqa: E731

    rumore = _alt(tuple(t for g in _NOISE_GROUPS.values() for t in g if t not in spenti))
    pasta = _alt(tieni(_PASTA_NAMES))
    pesce = _alt(tieni(_PESCE_NAMES))
    gamberi = _alt(tieni(_GAMBERI_QUALIFIERS))
    olive = _alt(tieni(_OLIVE_QUALIFIERS))
    olive_prefissi = _alt(tieni(_OLIVE_PREFISSI))
    peperoni = _alt(tieni(_PEPERONI_QUALIFIERS))

    compila = lambda p: re.compile(p, re.IGNORECASE)  # noqa: E731
    return _Builtin(
        noise=compila(rf"\b({rumore})\b") if rumore else None,
        pasta=compila(rf"\b({pasta})\b") if pasta else None,
        pesce=compila(
            rf"\b(filetti?|filett[io])\s+di\s+({pesce})\b|\b({pesce})\b"
        )
        if pesce
        else None,
        gamberi=compila(rf"\bgamberi\s+({gamberi})\b") if gamberi else None,
        olive=compila(
            rf"\bolive\s+({olive})\b"
            + (rf"|\b({olive_prefissi})\s+olive\b" if olive_prefissi else "")
        )
        if olive
        else None,
        # Il gruppo si ripete perché i colori si elencano ("rossi e gialli"): fermarsi
        # al primo lascerebbe "peperoni e gialli", che è peggio del nome di partenza.
        peperoni=compila(rf"\bpeperon[ei](?:\s+(?:e\s+)?(?:{peperoni}))+")
        if peperoni
        else None,
        varianti=tuple(
            (target, compila(rf"\b({termini})\b"))
            for target, gruppo in _VARIANTI.items()
            if (termini := _alt(tieni(gruppo)))
        ),
        grattugia=frozenset(t for t in _DA_GRATTUGIA if t not in spenti),
    )


def _builtin_normalize(name: str, spenti: frozenset = frozenset()) -> str:
    regole = _builtin(spenti)

    n = _PARENTESI.sub(" ", _segni(name))
    if regole.pasta:
        n = regole.pasta.sub("pasta", n)
    if regole.pesce:
        n = regole.pesce.sub("filetto di pesce magro", n)
    if regole.gamberi:
        n = regole.gamberi.sub("gamberi", n)
    if regole.olive:
        n = regole.olive.sub("olive", n)
    if regole.peperoni:
        n = regole.peperoni.sub("peperoni", n)
    for target, variante in regole.varianti:
        n = variante.sub(target, n)
    if regole.noise:
        n = regole.noise.sub(" ", n)
    n = re.sub(r"[\s,;]+", " ", n).strip(" -,.")
    n = _PASTA_INTEGRALE.sub("pasta", n)
    n = _DANGLING.sub("", n).strip(" -,.")

    # "Formaggio grattugiato" ci arriva già così: `grattugiato` è un taglio, l'ha tolto
    # il rumore qui sopra.
    if n in regole.grattugia or n == "formaggio":
        return "formaggio"
    # Per ultimo il singolare/plurale, che confronta il nome intero: prima devono aver
    # già fatto il loro lavoro gli accorpamenti (altrimenti "sedani" arriverebbe qui
    # come sedano invece che come pasta) e i qualificatori (o arriverebbe "peperone
    # rosso", che non è nessuna delle due forme).
    return _CATALOG_FORMS.get(n, n)


@dataclass(frozen=True)
class NormalizationRules:
    """Le regole aggiunte a mano, che si applicano **dopo** quelle di serie.

    Funzionano come quelle di serie — una sostituzione con regex su parola intera —
    solo che i termini stanno in tabella invece che nel codice: `aliases` è
    `{"pasta": ("tortiglioni", "calamarata"), ...}`, cioè esattamente il gruppo che si
    riempie dalle Impostazioni.

    L'ordine non è arbitrario: le regole di serie sono quelle su cui si reggono il
    catalogo dei prezzi e mezza suite di test, e devono restare prevedibili. Le
    aggiunte lavorano su ciò che esce da lì.
    """

    noise: tuple[str, ...] = ()
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Termini di serie spenti a mano: restano scritti nel codice — sono la base su cui
    # poggiano il catalogo e i test — ma smettono di valere. È il modo di togliere
    # "sedani" da pasta (che è anche il plurale del sedano) senza un deploy, e di
    # rimetterlo cancellando la regola.
    disabled: frozenset = frozenset()

    def __bool__(self) -> bool:
        """Senza regole aggiunte non si tocca niente: la normalizzazione resta quella
        di serie, byte per byte."""
        return bool(self.noise or self.aliases or self.disabled)

    def apply(self, n: str) -> str:
        # Prima gli accorpamenti, poi le parole da ignorare: è lo stesso ordine delle
        # regole di serie, dove "penne integrali" diventa "pasta integrali" prima che
        # si tolga il rumore.
        for target, terms in self.aliases.items():
            if not terms:
                continue
            pattern = "|".join(re.escape(t) for t in terms)
            n = re.sub(rf"\b({pattern})\b", target, n, flags=re.IGNORECASE)
            # "olive taggiasche" con «taggiasche» accorpato su «olive» darebbe "olive
            # olive": succede quando il termine è un qualificatore e non un nome. Si
            # ripulisce **solo** la parola appena sostituita, perché i nomi ripetuti
            # per davvero esistono — "cous cous" è uno di quelli.
            fuga = re.escape(target)
            n = re.sub(rf"\b{fuga}( {fuga}\b)+", target, n, flags=re.IGNORECASE)

        if self.noise:
            pattern = "|".join(re.escape(t) for t in self.noise)
            n = re.sub(rf"\b({pattern})\b", " ", n, flags=re.IGNORECASE)

        return _tidy(n)

    def plus(self, kind: str, term: str, replacement: str | None) -> "NormalizationRules":
        """Le stesse regole più una, senza salvarla: serve all'anteprima."""
        if kind == "off":
            return NormalizationRules(
                self.noise, dict(self.aliases), self.disabled | {term}
            )
        if kind == "noise":
            return NormalizationRules(
                self.noise + (term,), dict(self.aliases), self.disabled
            )
        target = replacement or term
        aliases = dict(self.aliases)
        aliases[target] = aliases.get(target, ()) + (term,)
        return NormalizationRules(self.noise, aliases, self.disabled)


NO_RULES = NormalizationRules()


def load_rules(db: Session) -> NormalizationRules:
    """Legge le regole dal database. Una query su una tabella di poche righe.

    Nessuna cache: le chiamate sono poche (una per ingrediente creato) e stanno dentro
    richieste che durano minuti perché parlano con un modello. Una cache di processo
    sarebbe un valore vecchio da invalidare a mano, cioè un bug in attesa.
    """
    rows = db.query(NormalizationRule).order_by(NormalizationRule.id).all()

    aliases: dict[str, tuple[str, ...]] = {}
    for row in rows:
        if row.kind == "alias" and row.replacement:
            aliases[row.replacement] = aliases.get(row.replacement, ()) + (row.term,)

    return NormalizationRules(
        noise=tuple(r.term for r in rows if r.kind == "noise"),
        aliases=aliases,
        disabled=frozenset(r.term for r in rows if r.kind == "off"),
    )


def normalize_name(name: str, rules: NormalizationRules | None = None) -> str:
    """Minuscolo, senza glosse fra parentesi, senza qualificatori e senza spazi doppi.

    Oltre a togliere il rumore, unisce sulla stessa riga le cose che per la dieta e
    per la spesa sono lo stesso alimento: i formati della pasta (spaghetti, penne e
    anche "pasta integrale" → `pasta`), i pesci bianchi (`_PESCE_MAGRO`), i formaggi da
    grattugia (`_DA_GRATTUGIA` → `formaggio`), il colore dei peperoni, e il singolare
    di quello che il catalogo chiama al plurale (`_CATALOG_FORMS`: "peperone" →
    "peperoni"). **Un altro cereale non è pasta**: riso, cous cous, farro e orzo
    restano quello che sono, e lo stesso vale per la pasta ripiena e gli gnocchi.

    Prima di tutto il resto passa da `_segni`, che dà un modo solo di scrivere
    apostrofi, spazi ed elisioni: "tonno all’olio d’oliva" e "tonno all'olio di oliva"
    sono la stessa scatoletta, e a schermo sono anche lo stesso nome.

    `rules` sono le aggiunte dell'utente (`load_rules`). Chi ha una sessione in mano le
    passa sempre: senza, si otterrebbe la normalizzazione di serie, e due punti dell'app
    che chiamano questa funzione in modo diverso creerebbero due righe di anagrafica per
    lo stesso alimento — che è esattamente il problema che questo file risolve.
    """
    n = _builtin_normalize(name, rules.disabled if rules else frozenset())
    if rules:
        n = rules.apply(n)
    return n[:120]


def get_or_create_ingredient(db: Session, name: str) -> Ingredient:
    """Restituisce la riga di anagrafica per un nome, creandola se serve.

    Categoria, prezzo e stagionalità vengono dal catalogo quando l'ingrediente è
    noto; altrimenti la categoria si indovina dalle parole chiave (serve a
    raggruppare la lista della spesa per reparto) e il prezzo resta NULL — meglio
    "costo non stimabile" che un numero inventato.
    """
    clean = normalize_name(name, load_rules(db))
    if not clean:
        raise ValueError("Nome ingrediente vuoto")

    existing = db.query(Ingredient).filter(Ingredient.name == clean).first()
    if existing:
        return existing

    entry = catalog_entry(clean)
    if entry:
        category, price, price_unit = entry
    else:
        category, price, price_unit = guess_category(clean), None, None

    ingredient = Ingredient(
        name=clean,
        category=category,
        season_months=season_months_for(clean),
        avg_price_per_unit=price,
        price_unit=price_unit,
    )
    db.add(ingredient)
    try:
        db.flush()
    except IntegrityError:
        # Race con un'altra richiesta che ha creato lo stesso ingrediente: il vincolo
        # UNIQUE sul nome è l'arbitro, noi ci riprendiamo la riga sua.
        db.rollback()
        return db.query(Ingredient).filter(Ingredient.name == clean).one()
    return ingredient


# ── Le regole, viste da fuori ──────────────────────────────────────────────────


def _readable(term: str) -> str:
    """Lo schema com'è scritto, ma senza la sintassi delle regex davanti agli occhi."""
    return (
        term.replace(r"\s+", " ").replace(r"\w+", "…").replace("\\.", ".").replace("\\", "")
    )


# I gruppi di serie, nella stessa forma di quelli che si riempiono dalle Impostazioni:
# un nome normalizzato e l'elenco dei termini che ci finiscono sopra. Si costruiscono
# dalle stesse tuple che compilano le regex — una lista scritta a parte per la UI si
# allontanerebbe dal codice al primo termine aggiunto, e sarebbe una bugia detta
# proprio nella pagina che si apre per capire perché due ingredienti stanno insieme.
def _term(raw: str) -> dict:
    """Il termine come lo applica il codice e come si legge a schermo.

    Servono tutti e due: a schermo si mostra «de cecco», ma per spegnerlo bisogna
    rimandare indietro `de\\s+cecco`, che è la chiave con cui il termine sta scritto
    nella regex.
    """
    return {"term": raw, "label": _readable(raw)}


def builtin_groups() -> list[dict]:
    return [
        {
            "target": "pasta",
            "terms": [_term(t) for t in sorted(_PASTA_NAMES)],
            "note": "Solo pasta: riso, cous cous, farro e orzo sono altri alimenti, con "
            "altri macro e un altro scaffale. Fuori anche pasta ripiena e gnocchi.",
        },
        {
            "target": "filetto di pesce magro",
            "terms": [_term(t) for t in sorted(_PESCE_NAMES)],
            "note": "Valgono con o senza «filetto di» davanti.",
        },
        {
            "target": "formaggio",
            "terms": [_term(t) for t in sorted(_DA_GRATTUGIA)],
            "note": "Confrontati per nome intero: sulla pasta ci va quello che c'è in "
            "casa. «Formaggio spalmabile» resta un altro alimento.",
        },
        *(
            {
                "target": target,
                "terms": [_term(t) for t in sorted(termini)],
                "note": "Non è un accorpamento: è la stessa parola scritta in due modi.",
            }
            for target, termini in _VARIANTI.items()
        ),
    ]


def builtin_terms() -> set[str]:
    """Tutti i termini di serie che si possono spegnere, nella forma con cui si spengono."""
    return (
        {t for gruppo in _NOISE_GROUPS.values() for t in gruppo}
        | set(_PASTA_NAMES)
        | set(_PESCE_NAMES)
        | set(_DA_GRATTUGIA)
        | set(_GAMBERI_QUALIFIERS)
        | set(_OLIVE_QUALIFIERS)
        | set(_PEPERONI_QUALIFIERS)
        | {t for gruppo in _VARIANTI.values() for t in gruppo}
    )


def builtin_rules() -> dict:
    """Le regole di serie in forma leggibile, per la schermata delle Impostazioni."""
    return {
        "groups": builtin_groups(),
        "noise": [
            {"label": label, "terms": [_term(t) for t in terms]}
            for label, terms in _NOISE_GROUPS.items()
        ],
        # Due casi che non sono né accorpamenti né rumore: un qualificatore che si
        # toglie **solo** dopo un certo alimento. "Nere" da solo non vuol dire niente,
        # dopo "olive" sì.
        "scoped": [
            {
                "target": "gamberi",
                "terms": [_term(t) for t in _GAMBERI_QUALIFIERS],
                "note": "Tolti quando seguono «gamberi».",
            },
            {
                "target": "olive",
                "terms": [_term(t) for t in _OLIVE_QUALIFIERS],
                "note": "Tolti quando seguono «olive».",
            },
            {
                "target": "peperoni",
                "terms": [_term(t) for t in _PEPERONI_QUALIFIERS],
                "note": "Il colore non cambia l'alimento: stesso banco, stesso prezzo, "
                "stessi macro. Tolti quando seguono «peperoni» o «peperone».",
            },
        ],
        "kept": [
            "integrale", "magro", "light", "intero", "al naturale", "sott'olio",
            "senza zuccheri", "pelati",
        ],
    }


def preview_rule(
    db: Session, kind: str, term: str, replacement: str | None = None
) -> dict:
    """Cosa cambierebbe in anagrafica se la regola ci fosse già. Non scrive niente.

    Serve perché un accorpamento sbagliato non si annulla togliendo la regola: le
    righe fuse restano fuse, e rimetterle a posto è lavoro a mano. Vedere prima che
    «riso» sta per diventare «pasta» costa una schermata e salva mezza serata.
    """
    rules = load_rules(db)
    candidate = rules.plus(kind, term, replacement)

    esistenti = {row.name for row in db.query(Ingredient.name).all()}
    changes = []
    for ingredient in db.query(Ingredient).order_by(Ingredient.name).all():
        prima = normalize_name(ingredient.name, rules)
        dopo = normalize_name(ingredient.name, candidate)
        if dopo and dopo != prima:
            changes.append(
                {
                    "from": ingredient.name,
                    "to": dopo,
                    # Se la riga di destinazione esiste già, le due si fondono: è il
                    # caso che porta via dati (quantità sommate, righe cancellate).
                    "merges": dopo in esistenti,
                }
            )
    return {"changes": changes, "checked": len(esistenti)}


# ── Riallineamento dell'anagrafica ─────────────────────────────────────────────


def _merge_rows(db: Session, canonical: Ingredient, doppione: Ingredient) -> None:
    """Sposta sulla riga buona tutto ciò che puntava al doppione, poi lo cancella."""
    # Le ricette non hanno vincoli di unicità: si ripuntano e basta.
    db.query(RecipeIngredient).filter(
        RecipeIngredient.ingredient_id == doppione.id
    ).update({RecipeIngredient.ingredient_id: canonical.id}, synchronize_session=False)

    # La dispensa ne ha una riga per utente: dove ci sono entrambe si sommano, ma solo
    # se le unità si parlano — sommare grammi e unità darebbe un numero inventato.
    for item in (
        db.query(PantryItem).filter(PantryItem.ingredient_id == doppione.id).all()
    ):
        gemella = (
            db.query(PantryItem)
            .filter(
                PantryItem.user_id == item.user_id,
                PantryItem.ingredient_id == canonical.id,
            )
            .first()
        )
        if not gemella:
            item.ingredient_id = canonical.id
            continue
        if item.quantity_available and gemella.quantity_available:
            somma, unit = to_base(item.quantity_available, item.unit or "unità")
            base, unit_gemella = to_base(
                gemella.quantity_available, gemella.unit or "unità"
            )
            if unit == unit_gemella:
                gemella.quantity_available = round(base + somma, 2)
                gemella.unit = unit
        elif item.quantity_available:
            gemella.quantity_available = item.quantity_available
            gemella.unit = item.unit
        db.delete(item)

    # Liste, ingredienti di base ed esclusi: dove il posto è già occupato la riga in
    # più si butta, perché è esattamente lo stesso alimento.
    for model, chiave in (
        (BaseIngredient, ("user_id",)),
        (ExcludedIngredient, ("user_id",)),
        (ShoppingListItem, ("shopping_list_id", "unit")),
    ):
        for row in db.query(model).filter(model.ingredient_id == doppione.id).all():
            filtri = [getattr(model, campo) == getattr(row, campo) for campo in chiave]
            occupato = (
                db.query(model)
                .filter(model.ingredient_id == canonical.id, *filtri)
                .first()
            )
            if occupato:
                db.delete(row)
            else:
                row.ingredient_id = canonical.id

    db.flush()
    db.delete(doppione)


def merge_duplicates(db: Session) -> list[tuple[str, list[str]]]:
    """Riporta l'anagrafica alla normalizzazione di oggi e fonde i doppioni.

    Serve dopo aver allargato l'elenco dei qualificatori: le righe già in tabella
    restano scritte come erano ("pesce spada surgelato"), e finché restano la dispensa
    non copre la ricetta che dice "pesce spada" — è lo stesso alimento per chi cucina,
    ma sono due righe diverse per il database.

    Tiene la riga più vecchia di ogni gruppo, le sposta addosso ricette, dispensa,
    liste e preferenze, e restituisce cosa ha fuso perché lo si possa leggere prima di
    fidarsi. Rieseguirla non fa niente: dopo la prima volta non ci sono più doppioni.
    """
    rules = load_rules(db)
    gruppi: dict[str, list[Ingredient]] = {}
    for ingredient in db.query(Ingredient).order_by(Ingredient.id).all():
        gruppi.setdefault(normalize_name(ingredient.name, rules), []).append(ingredient)

    fusi: list[tuple[str, list[str]]] = []
    rimappati: dict[int, int] = {}

    for clean, rows in gruppi.items():
        if not clean:
            continue
        if len(rows) == 1 and rows[0].name == clean:
            continue

        # La riga da tenere è quella che ha già il nome giusto; altrimenti la più
        # vecchia, che è quella con più storia attaccata.
        canonical = next((r for r in rows if r.name == clean), rows[0])
        doppioni = [r for r in rows if r.id != canonical.id]

        for doppione in doppioni:
            rimappati[doppione.id] = canonical.id
            _merge_rows(db, canonical, doppione)

        canonical.name = clean
        if doppioni:
            fusi.append((clean, [d.name for d in doppioni]))

    # Il promemoria di cosa è stato scalato dalla dispensa cita gli ingredienti per id:
    # senza rimapparlo, annullare un "l'ho seguito" cercherebbe una riga cancellata.
    if rimappati:
        for meal in (
            db.query(PlannedMeal).filter(PlannedMeal.pantry_used.isnot(None)).all()
        ):
            meal.pantry_used = [
                {
                    **voce,
                    "ingredient_id": rimappati.get(
                        voce.get("ingredient_id"), voce.get("ingredient_id")
                    ),
                }
                for voce in (meal.pantry_used or [])
            ]

    db.commit()
    return fusi
