"""Configurazione dell'utente: ingredienti di base, esclusi, dispensa, preferenze.

Sono le quattro liste che vincolano ogni generazione: cosa c'è sempre in casa, cosa
non deve comparire mai, cosa c'è adesso in dispensa e come si vuole mangiare.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_admin, get_current_user, get_current_user_id
from ..database import get_db
from ..models import (
    BaseIngredient,
    ExcludedIngredient,
    Ingredient,
    NormalizationRule,
    PantryItem,
    User,
    UserPreferences,
)
from ..config import (
    AI_PROVIDER,
    API_KEY_PREFIX,
    API_KEY_URL,
    default_model,
    model_matches_provider,
)
from ..schemas import (
    AiModelsUpdate,
    ExcludedCreate,
    IngredientCategoryUpdate,
    IngredientNameRequest,
    NormalizationRuleCreate,
    PantryCreate,
    PantryUpdate,
    PreferencesUpdate,
)
from ..services.ai_client import ai_owner
from ..services.catalog import list_models
from ..services.ingredients import (
    NormalizationRules,
    builtin_rules,
    get_or_create_ingredient,
    load_rules,
    merge_duplicates,
    normalize_name,
    preview_rule,
)
from ..services.shopping import CATEGORY_LABELS
from ..utils.pricing import DEFAULT_BASE_INGREDIENTS
from ..utils.units import format_quantity, normalize_unit

router = APIRouter(prefix="/api/config", tags=["Configurazione"])

BUDGET_LEVELS = {"economico", "medio", "premium"}


# ── Ingredienti di base ────────────────────────────────────────────────────────


@router.get("/base-ingredients")
def list_base(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    rows = (
        db.query(BaseIngredient, Ingredient)
        .join(Ingredient, Ingredient.id == BaseIngredient.ingredient_id)
        .filter(BaseIngredient.user_id == user_id)
        .order_by(Ingredient.name)
        .all()
    )
    return [
        {"id": b.id, "ingredient_id": i.id, "name": i.name, "category": i.category}
        for b, i in rows
    ]


@router.post("/base-ingredients", status_code=201)
def add_base(
    body: IngredientNameRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ingredient = get_or_create_ingredient(db, body.ingredient_name)
    row = BaseIngredient(user_id=user_id, ingredient_id=ingredient.id)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"'{ingredient.name}' è già tra gli ingredienti di base.")
    return {
        "id": row.id,
        "ingredient_id": ingredient.id,
        "name": ingredient.name,
        "category": ingredient.category,
    }


@router.post("/base-ingredients/defaults")
def add_default_base(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Riempie la lista con i soliti sospetti (sale, olio, pepe...) durante l'onboarding."""
    added = 0
    for name in DEFAULT_BASE_INGREDIENTS:
        ingredient = get_or_create_ingredient(db, name)
        exists = (
            db.query(BaseIngredient)
            .filter(
                BaseIngredient.user_id == user_id,
                BaseIngredient.ingredient_id == ingredient.id,
            )
            .first()
        )
        if not exists:
            db.add(BaseIngredient(user_id=user_id, ingredient_id=ingredient.id))
            added += 1
    db.commit()
    return {"added": added}


@router.delete("/base-ingredients/{item_id}", status_code=204)
def remove_base(
    item_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    deleted = (
        db.query(BaseIngredient)
        .filter(BaseIngredient.id == item_id, BaseIngredient.user_id == user_id)
        .delete()
    )
    db.commit()
    if not deleted:
        raise HTTPException(404, "Non trovato")
    return Response(status_code=204)


# ── Ingredienti esclusi ────────────────────────────────────────────────────────


@router.get("/excluded")
def list_excluded(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    rows = (
        db.query(ExcludedIngredient, Ingredient)
        .outerjoin(Ingredient, Ingredient.id == ExcludedIngredient.ingredient_id)
        .filter(ExcludedIngredient.user_id == user_id)
        .all()
    )
    items = [
        {
            "id": e.id,
            "ingredient_id": e.ingredient_id,
            "name": i.name if i else e.custom_name,
            "category": i.category if i else None,
            "reason": e.reason,
        }
        for e, i in rows
    ]
    return sorted(items, key=lambda x: x["name"] or "")


@router.post("/excluded", status_code=201)
def add_excluded(
    body: ExcludedCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Aggiunge un alimento da non usare mai.

    Se il nome corrisponde a un ingrediente noto lo si aggancia all'anagrafica (così
    la lista della spesa e la dispensa parlano la stessa lingua); altrimenti si
    conserva il testo libero — "frutti di mare" non è un ingrediente, è una famiglia.
    """
    clean = normalize_name(body.ingredient_name, load_rules(db))
    if not clean:
        raise HTTPException(400, "Nome non valido")

    known = db.query(Ingredient).filter(Ingredient.name == clean).first()
    already = (
        db.query(ExcludedIngredient)
        .filter(
            ExcludedIngredient.user_id == user_id,
            (ExcludedIngredient.ingredient_id == known.id)
            if known
            else (ExcludedIngredient.custom_name == clean),
        )
        .first()
    )
    if already:
        raise HTTPException(409, f"'{clean}' è già nella lista degli esclusi.")

    row = ExcludedIngredient(
        user_id=user_id,
        ingredient_id=known.id if known else None,
        custom_name=None if known else clean,
        reason=body.reason,
    )
    db.add(row)
    db.commit()
    return {
        "id": row.id,
        "ingredient_id": row.ingredient_id,
        "name": known.name if known else clean,
        "category": known.category if known else None,
        "reason": row.reason,
    }


@router.delete("/excluded/{item_id}", status_code=204)
def remove_excluded(
    item_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    deleted = (
        db.query(ExcludedIngredient)
        .filter(ExcludedIngredient.id == item_id, ExcludedIngredient.user_id == user_id)
        .delete()
    )
    db.commit()
    if not deleted:
        raise HTTPException(404, "Non trovato")
    return Response(status_code=204)


# ── Dispensa ───────────────────────────────────────────────────────────────────


def _serialize_pantry(item: PantryItem, ingredient: Ingredient) -> dict:
    return {
        "id": item.id,
        "ingredient_id": ingredient.id,
        "name": ingredient.name,
        "category": ingredient.category,
        "quantity": item.quantity_available,
        "unit": item.unit,
        "label": (
            format_quantity(item.quantity_available, item.unit or "unità")
            if item.quantity_available
            else None
        ),
    }


@router.get("/pantry")
def list_pantry(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    rows = (
        db.query(PantryItem, Ingredient)
        .join(Ingredient, Ingredient.id == PantryItem.ingredient_id)
        .filter(PantryItem.user_id == user_id)
        .order_by(Ingredient.category, Ingredient.name)
        .all()
    )
    return [_serialize_pantry(p, i) for p, i in rows]


@router.post("/pantry", status_code=201)
def add_pantry(
    body: PantryCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ingredient = get_or_create_ingredient(db, body.ingredient_name)
    existing = (
        db.query(PantryItem)
        .filter(PantryItem.user_id == user_id, PantryItem.ingredient_id == ingredient.id)
        .first()
    )
    if existing:
        raise HTTPException(409, f"'{ingredient.name}' è già in dispensa.")

    item = PantryItem(
        user_id=user_id,
        ingredient_id=ingredient.id,
        quantity_available=body.quantity,
        unit=normalize_unit(body.unit) if body.unit else None,
    )
    db.add(item)
    db.commit()
    return _serialize_pantry(item, ingredient)


@router.put("/pantry/{item_id}")
def update_pantry(
    item_id: int,
    body: PantryUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    item = (
        db.query(PantryItem)
        .filter(PantryItem.id == item_id, PantryItem.user_id == user_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Non trovato")

    # Cambiare il nome vuol dire puntare la riga a un altro ingrediente dell'anagrafica:
    # non è una modifica di testo, perché da quel collegamento dipendono il reparto, il
    # prezzo e soprattutto lo scomputo dalla lista della spesa.
    if body.ingredient_name is not None:
        try:
            ingredient = get_or_create_ingredient(db, body.ingredient_name)
        except ValueError:
            raise HTTPException(400, "Nome ingrediente non valido")

        if ingredient.id != item.ingredient_id:
            # In dispensa c'è una riga sola per ingrediente (vincolo UNIQUE). Sommare
            # le due quantità sarebbe una sorpresa — e con unità diverse un errore.
            occupato = (
                db.query(PantryItem)
                .filter(
                    PantryItem.user_id == user_id,
                    PantryItem.ingredient_id == ingredient.id,
                    PantryItem.id != item.id,
                )
                .first()
            )
            if occupato:
                raise HTTPException(
                    409, f"'{ingredient.name}' è già in dispensa: modifica quella riga."
                )
            item.ingredient_id = ingredient.id

    if "quantity" in body.model_fields_set:
        item.quantity_available = body.quantity
    if "unit" in body.model_fields_set:
        item.unit = normalize_unit(body.unit) if body.unit else None
    db.commit()
    return _serialize_pantry(item, db.get(Ingredient, item.ingredient_id))


@router.delete("/pantry/{item_id}", status_code=204)
def remove_pantry(
    item_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    deleted = (
        db.query(PantryItem)
        .filter(PantryItem.id == item_id, PantryItem.user_id == user_id)
        .delete()
    )
    db.commit()
    if not deleted:
        raise HTTPException(404, "Non trovato")
    return Response(status_code=204)


# ── Preferenze ─────────────────────────────────────────────────────────────────


def _serialize_prefs(prefs: UserPreferences) -> dict:
    return {
        "prefer_seasonal": prefs.prefer_seasonal,
        "prefer_italian": prefs.prefer_italian,
        "max_prep_time_min": prefs.max_prep_time_min,
        "budget_level": prefs.budget_level,
        "notes": prefs.notes,
    }


@router.get("/preferences")
def get_preferences(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
    if not prefs:
        # Default impliciti: la spec dice cucina italiana e stagionalità attive.
        prefs = UserPreferences(user_id=user_id, prefer_seasonal=True, prefer_italian=True)
        db.add(prefs)
        db.commit()
    return _serialize_prefs(prefs)


@router.put("/preferences")
def update_preferences(
    body: PreferencesUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if body.budget_level and body.budget_level not in BUDGET_LEVELS:
        raise HTTPException(400, "Livello di budget non valido")

    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
    if not prefs:
        prefs = UserPreferences(user_id=user_id)
        db.add(prefs)

    prefs.prefer_seasonal = body.prefer_seasonal
    prefs.prefer_italian = body.prefer_italian
    prefs.max_prep_time_min = body.max_prep_time_min
    prefs.budget_level = body.budget_level
    prefs.notes = (body.notes or "").strip() or None
    db.commit()
    return _serialize_prefs(prefs)


# ── Modelli AI ─────────────────────────────────────────────────────────────────

ROLE_LABELS = {
    "planning": "Pianificazione settimanale",
    "chat": "Chat e modifiche",
    "diet": "Lettura della dieta",
}

ROLE_HINTS = {
    "planning": (
        "La parte difficile: incastrare tutti i pasti dentro i macro senza ripetizioni "
        "e riusando gli avanzi. Si esegue una volta a settimana — è qui che conviene "
        "spendere."
    ),
    "chat": (
        "Tante chiamate piccole su compiti facili ('sostituisci il pollo'). Un modello "
        "economico qui si nota poco e si sente sulla bolletta."
    ),
    "diet": (
        "Due o tre volte l'anno. Se il PDF contiene testo va bene qualunque modello; "
        "se è una scansione serve un modello che sappia guardare le immagini."
    ),
}


def _prefs_of(db: Session, user_id: int) -> UserPreferences:
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
    if not prefs:
        prefs = UserPreferences(user_id=user_id)
        db.add(prefs)
        db.commit()
    return prefs


@router.get("/ai")
def get_ai_config(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Provider attivo e modello scelto per ogni ruolo (col default se non scelto).

    I modelli mostrati sono quelli di chi paga: per chi non è amministratore sono
    quelli scelti dall'admin, ed è con quelli che genererà davvero.
    """
    owner = ai_owner(db, user)
    prefs = _prefs_of(db, owner.id)
    return {
        "provider": AI_PROVIDER,
        "key_prefix": API_KEY_PREFIX,
        "key_url": API_KEY_URL,
        "can_list_models": AI_PROVIDER == "openrouter",
        # Sceglie i modelli chi ne paga le chiamate: agli altri la scheda non si mostra.
        "can_choose_models": user.is_admin,
        "roles": [
            {
                "key": role,
                "label": ROLE_LABELS[role],
                "hint": ROLE_HINTS[role],
                "model": getattr(prefs, f"ai_model_{role}", None),
                "default": default_model(role),
            }
            for role in ("planning", "chat", "diet")
        ],
    }


@router.get("/ai/models")
def get_ai_models(
    q: str = "",
    _admin: User = Depends(get_current_admin),
):
    """Catalogo dei modelli del provider, filtrabile.

    Evita di far digitare gli slug a memoria: un errore di battitura si scoprirebbe
    solo alla prima generazione. La lista arriva dal provider, quindi comprende anche
    i modelli usciti dopo questo codice.

    Si restituisce il catalogo **intero** (qualche centinaio di voci, una manciata di
    KB, già in cache da un'ora): troncarlo qui significherebbe che la ricerca lato
    client lavora su un sottoinsieme, e un modello in fondo all'alfabeto diventerebbe
    introvabile invece che solo poco visibile.
    """
    models = list_models()
    term = q.strip().lower()
    if term:
        models = [m for m in models if term in m["id"].lower() or term in m["name"].lower()]
    return {"models": models, "total": len(models)}


@router.put("/ai/models")
def update_ai_models(
    body: AiModelsUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Cambia i modelli. Solo l'amministratore: valgono anche per gli altri account,
    che generano con la sua chiave."""
    prefs = _prefs_of(db, admin.id)
    for role in ("planning", "chat", "diet"):
        value = (getattr(body, role) or "").strip()
        # Meglio rifiutare qui che lasciar scoprire lo slug sbagliato dopo mezzo
        # minuto di generazione, con una 400 del fornitore.
        if value and not model_matches_provider(value):
            raise HTTPException(
                400,
                f"'{value}' non è un modello valido per {AI_PROVIDER}: "
                + (
                    f"su OpenRouter serve lo slug completo, tipo 'anthropic/{value}'."
                    if AI_PROVIDER == "openrouter"
                    else "con l'SDK Anthropic serve l'ID senza il prefisso del fornitore."
                ),
            )
        setattr(prefs, f"ai_model_{role}", value or None)
    db.commit()
    return get_ai_config(user=admin, db=db)


# ── Regole di normalizzazione ──────────────────────────────────────────────────

# Sono dell'amministratore per lo stesso motivo per cui non hanno `user_id`:
# l'anagrafica ingredienti è una sola, e fondere due righe tocca le ricette, la
# dispensa e le liste **di tutti**.


def _serialize_rule(rule: NormalizationRule) -> dict:
    return {
        "id": rule.id,
        "kind": rule.kind,
        "term": rule.term,
        "replacement": rule.replacement,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


def _validate_rule(db: Session, body: NormalizationRuleCreate) -> tuple[str, str, str | None]:
    """Ripulisce la regola e rifiuta quelle che non farebbero niente.

    Il termine si salva **già normalizzato** con le regole di serie, perché è contro il
    nome normalizzato che verrà confrontato: scrivere "penne rigate" e salvarlo così
    com'è darebbe una regola che non scatta mai, visto che a quel punto della catena il
    nome è già diventato "pasta rigate". Meglio dirlo qui che lasciarlo scoprire fra un
    mese guardando una lista della spesa che non si accorpa.
    """
    kind = body.kind.strip().lower()
    if kind not in ("noise", "alias"):
        raise HTTPException(400, "Tipo di regola non valido")

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


@router.get("/normalization")
def get_normalization(_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Le regole, come si guardano: un nome normalizzato e l'elenco di chi ci finisce.

    I termini di serie e quelli aggiunti a mano stanno nello **stesso** gruppo, perché
    fanno la stessa cosa: la differenza è solo che i primi non si tolgono da qui (ci si
    appoggiano il catalogo dei prezzi e i test) e i secondi sì.
    """
    rows = (
        db.query(NormalizationRule)
        .order_by(NormalizationRule.kind, NormalizationRule.term)
        .all()
    )
    builtin = builtin_rules()

    groups = [{**g, "custom": []} for g in builtin["groups"]]
    per_target = {g["target"]: g for g in groups}
    noise_custom = []

    for row in rows:
        if row.kind == "noise":
            noise_custom.append(_serialize_rule(row))
            continue
        gruppo = per_target.get(row.replacement)
        if not gruppo:
            # Un gruppo nato dalle Impostazioni: nessun termine di serie dentro.
            gruppo = {"target": row.replacement, "terms": [], "note": None, "custom": []}
            per_target[row.replacement] = gruppo
            groups.append(gruppo)
        gruppo["custom"].append(_serialize_rule(row))

    return {
        "groups": groups,
        "noise": {"builtin": builtin["noise"], "custom": noise_custom},
        "scoped": builtin["scoped"],
        "kept": builtin["kept"],
    }


@router.post("/normalization/preview")
def preview_normalization(
    body: NormalizationRuleCreate,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Cosa cambierebbe salvando questa regola. Non scrive niente."""
    kind, term, replacement = _validate_rule(db, body)
    result = preview_rule(db, kind, term, replacement)
    return {"kind": kind, "term": term, "replacement": replacement, **result}


@router.post("/normalization", status_code=201)
def add_normalization(
    body: NormalizationRuleCreate,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Salva la regola e riallinea subito l'anagrafica.

    Riallineare fa parte della regola, non è un extra: senza, "tortiglioni" resterebbe
    una riga a sé finché non lo si rigenera, e la dispensa non coprirebbe la ricetta
    che dice "pasta". È lo stesso lavoro di `python -m app.merge_ingredients`, fatto
    adesso invece che da un terminale.
    """
    kind, term, replacement = _validate_rule(db, body)

    rule = NormalizationRule(kind=kind, term=term, replacement=replacement)
    db.add(rule)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"«{term}» è già fra le regole.")

    fusi = merge_duplicates(db)  # committa
    return {
        "rule": _serialize_rule(rule),
        "merged": [{"name": nome, "from": doppioni} for nome, doppioni in fusi],
    }


@router.delete("/normalization/{rule_id}", status_code=204)
def remove_normalization(
    rule_id: int,
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Toglie la regola **da qui in avanti**.

    Quello che ha già fuso resta fuso: le righe cancellate non si ricreano e le
    quantità sommate in dispensa non si dividono. Da questo momento i nomi nuovi non
    verranno più accorpati, e il vecchio nome tornerà a fare riga a sé.
    """
    deleted = (
        db.query(NormalizationRule).filter(NormalizationRule.id == rule_id).delete()
    )
    db.commit()
    if not deleted:
        raise HTTPException(404, "Regola non trovata")
    return Response(status_code=204)


# ── Ricerca ingredienti (autocomplete) ─────────────────────────────────────────


@router.get("/ingredients/search")
def search_ingredients(
    q: str = "", _user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Suggerimenti per i campi "aggiungi ingrediente"."""
    term = normalize_name(q, load_rules(db))
    if len(term) < 2:
        return []
    rows = (
        db.query(Ingredient)
        .filter(Ingredient.name.ilike(f"%{term}%"))
        .order_by(Ingredient.name)
        .limit(10)
        .all()
    )
    return [{"id": i.id, "name": i.name, "category": i.category} for i in rows]


@router.put("/ingredients/{ingredient_id}/category")
def move_ingredient(
    ingredient_id: int,
    body: IngredientCategoryUpdate,
    _user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Sposta un ingrediente in un altro reparto della lista della spesa.

    Il reparto serve a chi gira per il supermercato, quindi la parola giusta la sa
    l'utente e non il catalogo: gli spaghetti finiti in "altro" vanno in "pane e
    cereali" perché è lì che stanno nel suo negozio. La scelta vale da subito su tutte
    le liste (la lista si raggruppa alla lettura) e resta per sempre — anche dopo il
    seed, che a ogni avvio riallinea l'anagrafica al catalogo.
    """
    if body.category not in CATEGORY_LABELS:
        raise HTTPException(400, "Reparto non valido")

    ingredient = db.get(Ingredient, ingredient_id)
    if not ingredient:
        raise HTTPException(404, "Ingrediente non trovato")

    ingredient.category = body.category
    ingredient.category_by_user = True
    db.commit()
    return {
        "id": ingredient.id,
        "name": ingredient.name,
        "category": ingredient.category,
        "label": CATEGORY_LABELS[ingredient.category],
    }
