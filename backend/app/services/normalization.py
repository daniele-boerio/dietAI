"""Le regole di normalizzazione aggiunte dalle Impostazioni: validarle, mostrarle, salvarle.

Sono dell'amministratore per lo stesso motivo per cui non hanno `user_id`:
l'anagrafica ingredienti è una sola, e fondere due righe tocca le ricette, la
dispensa e le liste **di tutti**. Il meccanismo (come una regola trasforma un nome)
sta in `ingredients.py`; qui c'è quello che serve alla schermata.
"""

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import NormalizationRule
from ..schemas import NormalizationRuleCreate
from .ingredients import (
    NormalizationRules,
    builtin_rules,
    builtin_terms,
    load_rules,
    merge_duplicates,
    normalize_name,
)


def serialize_rule(rule: NormalizationRule) -> dict:
    return {
        "id": rule.id,
        "kind": rule.kind,
        "term": rule.term,
        "replacement": rule.replacement,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


def validate_rule(db: Session, body: NormalizationRuleCreate) -> tuple[str, str, str | None]:
    """Ripulisce la regola e rifiuta quelle che non farebbero niente.

    Il termine si salva **già normalizzato** con le regole di serie, perché è contro il
    nome normalizzato che verrà confrontato: scrivere "penne rigate" e salvarlo così
    com'è darebbe una regola che non scatta mai, visto che a quel punto della catena il
    nome è già diventato "pasta rigate". Meglio dirlo qui che lasciarlo scoprire fra un
    mese guardando una lista della spesa che non si accorpa.
    """
    kind = body.kind.strip().lower()
    if kind not in ("noise", "alias", "off"):
        raise HTTPException(400, "Tipo di regola non valido")

    # Spegnere un termine di serie è l'unico caso in cui il termine **non** si
    # normalizza: è uno schema di regex (`fresc[ao]`), e va confrontato con la lista
    # del codice esattamente com'è scritto lì.
    if kind == "off":
        if body.term not in builtin_terms():
            raise HTTPException(400, f"«{body.term}» non è un termine di serie.")
        return kind, body.term, None

    rules = load_rules(db)
    # Le regole già salvate valgono per pulire il termine, tranne gli accorpamenti:
    # incatenarli (a → b, b → c) renderebbe illeggibile la lista.
    solo_rumore = NormalizationRules(noise=rules.noise)

    grezzo = " ".join(body.term.strip().lower().split())
    term = normalize_name(grezzo, solo_rumore)
    if not term:
        raise HTTPException(
            400,
            f"«{grezzo}» sparisce già del tutto con le regole di serie: "
            "non c'è niente da aggiungere.",
        )

    if kind == "noise":
        if term != grezzo:
            raise HTTPException(
                400,
                f"«{grezzo}» viene già ridotto a «{term}» dalle regole di serie: "
                "quella parola è già tolta.",
            )
        return kind, term, None

    replacement = normalize_name(body.replacement or "", solo_rumore)
    if not replacement:
        raise HTTPException(400, "Serve il nome su cui accorpare.")
    if term == replacement:
        raise HTTPException(
            400, f"«{grezzo}» è già «{replacement}»: la regola non farebbe niente."
        )
    return kind, term, replacement


def overview(db: Session) -> dict:
    """Le regole, come si guardano: un nome normalizzato e l'elenco di chi ci finisce.

    I termini di serie e quelli aggiunti a mano stanno nello **stesso** gruppo, perché
    fanno la stessa cosa: la differenza è solo che i primi non si tolgono da qui (ci si
    appoggiano il catalogo e i test) e i secondi sì.
    """
    rows = (
        db.query(NormalizationRule)
        .order_by(NormalizationRule.kind, NormalizationRule.term)
        .all()
    )
    builtin = builtin_rules()
    # Quali termini di serie sono stati spenti, e con quale regola: la crocetta su un
    # termine di serie crea una riga, e per riaccenderlo si cancella quella riga.
    spenti = {r.term: r.id for r in rows if r.kind == "off"}

    def con_stato(terms: list[dict]) -> list[dict]:
        return [
            {**t, "disabled": t["term"] in spenti, "rule_id": spenti.get(t["term"])}
            for t in terms
        ]

    groups = [
        {**g, "terms": con_stato(g["terms"]), "custom": []} for g in builtin["groups"]
    ]
    per_target = {g["target"]: g for g in groups}
    noise_custom = []

    for row in rows:
        if row.kind == "off":
            continue
        if row.kind == "noise":
            noise_custom.append(serialize_rule(row))
            continue
        gruppo = per_target.get(row.replacement)
        if not gruppo:
            # Un gruppo nato dalle Impostazioni: nessun termine di serie dentro.
            gruppo = {"target": row.replacement, "terms": [], "note": None, "custom": []}
            per_target[row.replacement] = gruppo
            groups.append(gruppo)
        gruppo["custom"].append(serialize_rule(row))

    return {
        "groups": groups,
        "noise": {
            "builtin": [
                {**g, "terms": con_stato(g["terms"])} for g in builtin["noise"]
            ],
            "custom": noise_custom,
        },
        "scoped": [{**g, "terms": con_stato(g["terms"])} for g in builtin["scoped"]],
        "kept": builtin["kept"],
    }


def add_rule(db: Session, body: NormalizationRuleCreate) -> dict:
    """Salva la regola e riallinea subito l'anagrafica.

    Riallineare fa parte della regola, non è un extra: senza, "tortiglioni" resterebbe
    una riga a sé finché non lo si rigenera, e la dispensa non coprirebbe la ricetta
    che dice "pasta". È lo stesso lavoro di `python -m app.merge_ingredients`, fatto
    adesso invece che da un terminale.
    """
    kind, term, replacement = validate_rule(db, body)

    rule = NormalizationRule(kind=kind, term=term, replacement=replacement)
    db.add(rule)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"«{term}» è già fra le regole.")

    fusi = merge_duplicates(db)  # committa
    return {
        "rule": serialize_rule(rule),
        "merged": [{"name": nome, "from": doppioni} for nome, doppioni in fusi],
    }
