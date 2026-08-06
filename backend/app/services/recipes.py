"""Creazione e serializzazione delle ricette.

Le ricette arrivano da tre strade — generate dall'AI, scritte a mano dall'utente,
modificate via chat — ma la forma in DB deve essere una sola. Tutte passano da qui.

**Lo stesso piatto è una ricetta sola.** Il ricettario è l'archivio dei piatti, non il
diario delle caselle: la colazione che si ripete sette giorni è un piatto, e vederselo
sette volte in elenco rende l'archivio illeggibile proprio a chi lo usa di più. Perciò
`create_recipe` prima di inserire cerca un gemello (`find_twin`) e, se lo trova,
restituisce quello: le caselle del piano ci puntano tutte, e voto e preferito valgono
per il piatto invece di sparpagliarsi su dieci copie identiche.

Il prezzo da pagare è che modificare una ricetta condivisa toccherebbe tutti i giorni
che la usano, storia compresa. Da qui `fork_recipe_for_meal`: chi modifica *da un
pasto* — la chat, la sostituzione di un ingrediente — se la ricetta è in uso altrove ne
stacca prima una copia. È la stessa garanzia di quando le copie si facevano subito
(`copy_recipe` per i pasti ricorrenti), ma pagata solo quando serve davvero.
"""

from sqlalchemy.orm import Session

from ..models import Ingredient, PlannedMeal, Recipe, RecipeIngredient
from .ingredients import get_or_create_ingredient

_DIFFICULTIES = {"easy", "medium", "hard"}


def _text(value) -> str:
    """Riduce a stringa quello che manda il modello.

    I prompt chiedono stringhe, ma un modello ogni tanto risponde con una lista o un
    numero: senza questa conversione il primo `.strip()` faceva 500 e la risposta —
    già pagata — andava persa.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, (list, tuple)):
        return "\n".join(t for t in (_text(v) for v in value) if t)
    return str(value).strip()


def _instructions(value) -> str:
    """Il procedimento, che il prompt chiede numerato e un passo per riga.

    Quando arriva come lista di passi la si numera qui, così il risultato è lo stesso
    di quando arriva già come testo.
    """
    if isinstance(value, (list, tuple)):
        steps = [s for s in (_text(v) for v in value) if s]
        if not any(s[:1].isdigit() or s[:1] in "-•*" for s in steps):
            steps = [f"{i}. {s}" for i, s in enumerate(steps, 1)]
        return "\n".join(steps)
    return _text(value)


def _dict(value) -> dict:
    """Un sotto-oggetto del JSON dell'AI, o `{}` se il modello ha mandato altro."""
    return value if isinstance(value, dict) else {}


def _clamp_difficulty(value) -> str:
    v = _text(value).lower()
    return v if v in _DIFFICULTIES else "medium"


def _num(value, default=0.0) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _clean_ingredients(items) -> list[dict]:
    """Normalizza gli ingredienti del JSON, scartando quelli senza un nome."""
    out = []
    for item in items if isinstance(items, (list, tuple)) else []:
        item = _dict(item)
        name = _text(item.get("name"))
        if not name:
            continue
        out.append(
            {
                "name": name,
                "quantity": _num(item.get("quantity")),
                "unit": _text(item.get("unit"))[:20] or "g",
                "notes": _text(item.get("notes")) or None,
            }
        )
    return out


def _resolve(db: Session, items: list[dict]) -> list[dict]:
    """Attacca a ogni ingrediente la sua riga di anagrafica.

    Si fa prima di creare la ricetta perché è la parte che serve a riconoscere un
    gemello: due piatti sono lo stesso piatto se comprano le stesse cose, e "le stesse
    cose" si decide sull'`ingredient_id` (cioè dopo la normalizzazione del nome), non
    sulla stringa che ha scritto il modello.
    """
    return [
        {**item, "ingredient_id": get_or_create_ingredient(db, item["name"]).id}
        for item in items
    ]


def _add_ingredients(db: Session, recipe: Recipe, items: list[dict]) -> None:
    for item in items:
        db.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=item["ingredient_id"],
                quantity=item["quantity"],
                unit=item["unit"],
                notes=item["notes"],
            )
        )


# ── Lo stesso piatto è una ricetta sola ────────────────────────────────────────


def _title_key(title: str | None) -> str:
    return " ".join((title or "").split()).casefold()


def _macros_key(calories, protein_g, carbs_g, fat_g) -> tuple:
    return (
        int(calories or 0),
        round(float(protein_g or 0), 1),
        round(float(carbs_g or 0), 1),
        round(float(fat_g or 0), 1),
    )


def _items_key(items: list[dict]) -> tuple:
    """Cosa serve per farla, senza l'ordine e senza le glosse.

    Le note dell'ingrediente ("a rondelle") restano fuori: descrivono come si taglia,
    non cosa si compra, e due piatti identici che le scrivono in modo diverso restano
    lo stesso piatto.
    """
    return tuple(
        sorted(
            (
                item["ingredient_id"],
                round(float(item.get("quantity") or 0), 2),
                (item.get("unit") or "").strip().lower(),
            )
            for item in items
        )
    )


def recipe_items_key(db: Session, recipe_id: int) -> tuple:
    rows = db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == recipe_id).all()
    return tuple(
        sorted(
            (ri.ingredient_id, round(float(ri.quantity or 0), 2), (ri.unit or "").strip().lower())
            for ri in rows
        )
    )


def _find_twin(
    db: Session,
    user_id: int,
    *,
    title_key: str,
    macros_key: tuple,
    items_key: tuple,
    exclude_id: int | None = None,
) -> Recipe | None:
    """La ricetta identica che l'utente ha già, se c'è.

    Identica vuol dire: stesso nome (a meno di maiuscole e spazi), stessi macro e
    stessa spesa. Restano fuori dal confronto il procedimento e la descrizione — se il
    modello riscrive gli stessi passi con altre parole il piatto non diventa un altro
    piatto, e tenere due righe per quello vorrebbe dire non deduplicare mai niente.

    Le candidate si pescano per calorie, che sono un intero e tagliano l'archivio in un
    colpo solo; il resto si confronta in Python, dove i float non hanno sorprese.
    """
    candidates = (
        db.query(Recipe)
        .filter(Recipe.user_id == user_id, Recipe.calories == macros_key[0])
        .order_by(Recipe.id)
        .all()
    )
    for candidate in candidates:
        if candidate.id == exclude_id:
            continue
        if _title_key(candidate.title) != title_key:
            continue
        if (
            _macros_key(
                candidate.calories, candidate.protein_g, candidate.carbs_g, candidate.fat_g
            )
            != macros_key
        ):
            continue
        if recipe_items_key(db, candidate.id) != items_key:
            continue
        return candidate
    return None


def find_twin(
    db: Session,
    user_id: int,
    *,
    title: str,
    calories: int,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    items: list[dict],
) -> Recipe | None:
    """Come sopra, a partire da una ricetta che non è ancora in tabella."""
    return _find_twin(
        db,
        user_id,
        title_key=_title_key(title),
        macros_key=_macros_key(calories, protein_g, carbs_g, fat_g),
        items_key=_items_key(items),
    )


def create_recipe(
    db: Session,
    user_id: int,
    data: dict,
    *,
    is_custom: bool = False,
    generation_prompt: str | None = None,
) -> Recipe:
    """Crea una ricetta dal dizionario dell'AI o dal payload dell'utente.

    Il formato dei due è quasi lo stesso: i macro possono stare in `nutrition`
    (AI) o al primo livello (form utente), quindi si accettano entrambi invece di
    obbligare il router a rimappare.

    Se quella ricetta l'utente ce l'ha già identica non se ne crea una seconda: si
    restituisce la sua. Vale soprattutto per la generazione, che chiama questa funzione
    una volta per casella e sul piatto che si ripete stava fabbricando un doppione al
    giorno.
    """
    nutrition = _dict(data.get("nutrition"))
    items = _resolve(db, _clean_ingredients(data.get("ingredients")))

    title = _text(data.get("title"))[:200] or "Ricetta senza nome"
    calories = int(_num(nutrition.get("calories", data.get("calories"))))
    protein_g = _num(nutrition.get("protein_g", data.get("protein_g")))
    carbs_g = _num(nutrition.get("carbs_g", data.get("carbs_g")))
    fat_g = _num(nutrition.get("fat_g", data.get("fat_g")))

    twin = find_twin(
        db,
        user_id,
        title=title,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        items=items,
    )
    if twin is not None:
        return twin

    recipe = Recipe(
        user_id=user_id,
        title=title,
        description=_text(data.get("description")) or None,
        prep_time_min=int(_num(data.get("prep_time_min"))),
        cook_time_min=int(_num(data.get("cook_time_min"))),
        difficulty=_clamp_difficulty(data.get("difficulty")),
        instructions=_instructions(data.get("instructions")) or "Nessun procedimento.",
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        tags=data.get("tags"),
        is_custom=is_custom,
        generation_prompt=generation_prompt,
    )
    db.add(recipe)
    db.flush()

    _add_ingredients(db, recipe, items)

    db.flush()
    return recipe


def replace_ingredients(db: Session, recipe: Recipe, items: list[dict]) -> None:
    """Sostituisce in blocco gli ingredienti di una ricetta (modifica via chat).

    Se dal JSON non si salva un solo ingrediente valido non si cancella niente: una
    ricetta rimasta senza ingredienti uscirebbe dalla lista della spesa in silenzio.
    """
    cleaned = _clean_ingredients(items)
    if not cleaned:
        return
    resolved = _resolve(db, cleaned)
    db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == recipe.id).delete()
    _add_ingredients(db, recipe, resolved)


def update_recipe_from_ai(db: Session, recipe: Recipe, data: dict) -> None:
    """Applica alla ricetta le modifiche proposte dalla chat.

    Aggiorna solo i campi presenti: se il modello rimanda solo titolo e ingredienti,
    il procedimento precedente non deve sparire.
    """
    nutrition = _dict(data.get("nutrition"))

    if data.get("title"):
        recipe.title = _text(data["title"])[:200] or recipe.title
    if data.get("description") is not None:
        recipe.description = _text(data["description"]) or None
    if data.get("instructions"):
        recipe.instructions = _instructions(data["instructions"]) or recipe.instructions
    if data.get("prep_time_min") is not None:
        recipe.prep_time_min = int(_num(data["prep_time_min"]))
    if data.get("cook_time_min") is not None:
        recipe.cook_time_min = int(_num(data["cook_time_min"]))
    if data.get("difficulty"):
        recipe.difficulty = _clamp_difficulty(data["difficulty"])
    if data.get("tags"):
        recipe.tags = data["tags"]
    if nutrition:
        recipe.calories = int(_num(nutrition.get("calories"), recipe.calories))
        recipe.protein_g = _num(nutrition.get("protein_g"), recipe.protein_g)
        recipe.carbs_g = _num(nutrition.get("carbs_g"), recipe.carbs_g)
        recipe.fat_g = _num(nutrition.get("fat_g"), recipe.fat_g)
    if data.get("ingredients"):
        replace_ingredients(db, recipe, data["ingredients"])


def fork_recipe_for_meal(db: Session, meal: PlannedMeal) -> Recipe | None:
    """La ricetta da modificare per **questo** pasto, staccata se è condivisa.

    Chiamarla prima di ogni modifica fatta da dentro un pasto — la chat, la
    sostituzione di un ingrediente — è ciò che rende sicuro tenere una riga sola per
    piatto: se quel piatto è in programma anche altrove, "meno olio stasera" non deve
    riscrivere il giovedì né la settimana già archiviata.

    **Ogni** altra casella conta come uso, comprese quelle saltate: la `recipe_id` di
    una casella saltata è la memoria di cosa c'era in programma quel giorno, cioè un
    pezzo di storia come tutti gli altri. Modificare il piatto dove si è accodato non
    può riscrivere quello che il lunedì diceva.
    """
    recipe = db.get(Recipe, meal.recipe_id) if meal.recipe_id else None
    if recipe is None:
        return None

    condivisa = (
        db.query(PlannedMeal)
        .filter(PlannedMeal.recipe_id == recipe.id, PlannedMeal.id != meal.id)
        .first()
    )
    if condivisa is None:
        return recipe

    clone = copy_recipe(db, recipe)
    meal.recipe_id = clone.id
    db.flush()
    return clone


def settle_recipe(db: Session, meal: PlannedMeal) -> Recipe | None:
    """Dopo una modifica: se il piatto è tornato uguale a uno che c'è già, una riga sola.

    È il rovescio di `fork_recipe_for_meal`, e serve al caso che la chat della spesa
    produce da sola: "le zucchine non le trovo" riscrive **tutte** le ricette che le
    usano, e se lo stesso piatto era in programma due volte le due caselle — appena
    staccate una dall'altra — si ritrovano con lo stesso identico piatto nuovo. Senza
    questo passaggio il doppione rientrerebbe dalla finestra.

    La riga lasciata indietro si cancella solo se non la usa più nessun pasto e non
    porta un giudizio dell'utente: voto e preferito sono suoi, e non si buttano via per
    fare ordine.
    """
    recipe = db.get(Recipe, meal.recipe_id) if meal.recipe_id else None
    if recipe is None:
        return None

    twin = _find_twin(
        db,
        recipe.user_id,
        title_key=_title_key(recipe.title),
        macros_key=_macros_key(
            recipe.calories, recipe.protein_g, recipe.carbs_g, recipe.fat_g
        ),
        items_key=recipe_items_key(db, recipe.id),
        exclude_id=recipe.id,
    )
    if twin is None:
        return recipe

    meal.recipe_id = twin.id
    db.flush()

    ancora_in_uso = (
        db.query(PlannedMeal).filter(PlannedMeal.recipe_id == recipe.id).first() is not None
    )
    if not ancora_in_uso and not recipe.is_favorite and not recipe.rating:
        db.delete(recipe)
        db.flush()
    return twin


def copy_recipe(db: Session, recipe: Recipe) -> Recipe:
    """Duplica una ricetta.

    Serve a `fork_recipe_for_meal`: da qui in poi le due caselle hanno due piatti
    diversi, ed è giusto che siano due righe — la modifica vale per una sola.
    """
    clone = Recipe(
        user_id=recipe.user_id,
        title=recipe.title,
        description=recipe.description,
        prep_time_min=recipe.prep_time_min,
        cook_time_min=recipe.cook_time_min,
        difficulty=recipe.difficulty,
        instructions=recipe.instructions,
        calories=recipe.calories,
        protein_g=recipe.protein_g,
        carbs_g=recipe.carbs_g,
        fat_g=recipe.fat_g,
        tags=recipe.tags,
        is_favorite=recipe.is_favorite,
        is_custom=recipe.is_custom,
    )
    db.add(clone)
    db.flush()

    for ri in (
        db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == recipe.id).all()
    ):
        db.add(
            RecipeIngredient(
                recipe_id=clone.id,
                ingredient_id=ri.ingredient_id,
                quantity=ri.quantity,
                unit=ri.unit,
                notes=ri.notes,
            )
        )
    db.flush()
    return clone


def duplicate_groups(db: Session, user_id: int | None = None) -> list[list[Recipe]]:
    """I gruppi di ricette identiche, uno per piatto che ha più di una riga.

    Sta qui e non nel comando che le fonde perché l'anteprima e la fusione devono
    ragionare sulla **stessa** chiave: un elenco che promette una cosa e un comando che
    ne fa un'altra è peggio di nessuna anteprima.
    """
    query = db.query(Recipe).order_by(Recipe.id)
    if user_id is not None:
        query = query.filter(Recipe.user_id == user_id)

    gruppi: dict[tuple, list[Recipe]] = {}
    for recipe in query.all():
        chiave = (
            recipe.user_id,
            _title_key(recipe.title),
            _macros_key(recipe.calories, recipe.protein_g, recipe.carbs_g, recipe.fat_g),
            recipe_items_key(db, recipe.id),
        )
        gruppi.setdefault(chiave, []).append(recipe)

    return [rows for rows in gruppi.values() if len(rows) > 1]


def merge_duplicate_recipes(db: Session, user_id: int | None = None) -> list[tuple[str, int]]:
    """Fonde le ricette identiche già in tabella. Restituisce (titolo, quante fuse).

    Serve una volta sola, per l'archivio che si è gonfiato prima che `create_recipe`
    imparasse a riconoscere un gemello: il piatto che si ripete aveva una riga per
    casella, quindi una per giorno, e i pasti ricorrenti una per settimana.

    Tiene la riga con più storia addosso — prima i preferiti, poi il voto più alto,
    poi la più vecchia — e le sposta addosso le caselle del piano. Voto e preferito dei
    doppioni non si perdono: sono un giudizio sul piatto, non sulla riga, e il piatto
    resta. Rieseguirla non fa niente: dopo la prima volta gemelli non ce ne sono più.
    """
    fusi: list[tuple[str, int]] = []
    for rows in duplicate_groups(db, user_id):
        canonica = min(
            rows, key=lambda r: (not r.is_favorite, -(r.rating or 0), r.id)
        )
        doppioni = [r for r in rows if r.id != canonica.id]

        canonica.is_favorite = any(r.is_favorite for r in rows)
        voti = [r.rating for r in rows if r.rating]
        canonica.rating = max(voti) if voti else canonica.rating

        for doppione in doppioni:
            # Prima si spostano le caselle, poi si cancella: la FK è SET NULL, e
            # cancellare per primo lascerebbe dei pasti senza ricetta.
            db.query(PlannedMeal).filter(PlannedMeal.recipe_id == doppione.id).update(
                {"recipe_id": canonica.id}
            )
            db.delete(doppione)

        db.flush()
        fusi.append((canonica.title, len(doppioni)))

    db.commit()
    return fusi


# ── Serializzazione ────────────────────────────────────────────────────────────


def ingredients_of(db: Session, recipe_id: int) -> list[dict]:
    rows = (
        db.query(RecipeIngredient, Ingredient)
        .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
        .filter(RecipeIngredient.recipe_id == recipe_id)
        .order_by(RecipeIngredient.id)
        .all()
    )
    return [
        {
            "id": ri.id,
            "name": ing.name,
            "category": ing.category,
            "quantity": ri.quantity,
            "unit": ri.unit,
            "notes": ri.notes,
        }
        for ri, ing in rows
    ]


def serialize_recipe(db: Session, recipe: Recipe | None, *, full: bool = True) -> dict | None:
    if recipe is None:
        return None
    data = {
        "id": recipe.id,
        "title": recipe.title,
        "description": recipe.description,
        "prep_time_min": recipe.prep_time_min,
        "cook_time_min": recipe.cook_time_min,
        "difficulty": recipe.difficulty,
        "calories": recipe.calories,
        "protein_g": recipe.protein_g,
        "carbs_g": recipe.carbs_g,
        "fat_g": recipe.fat_g,
        "tags": recipe.tags,
        "rating": recipe.rating,
        "is_favorite": recipe.is_favorite,
        "is_custom": recipe.is_custom,
        "created_at": recipe.created_at.isoformat() if recipe.created_at else None,
    }
    if full:
        data["instructions"] = recipe.instructions
        data["ingredients"] = ingredients_of(db, recipe.id)
    return data


def recipe_for_prompt(db: Session, recipe: Recipe) -> dict:
    """Versione compatta da infilare in un prompt: niente id, niente metadati."""
    return {
        "title": recipe.title,
        "description": recipe.description,
        "prep_time_min": recipe.prep_time_min,
        "cook_time_min": recipe.cook_time_min,
        "difficulty": recipe.difficulty,
        "ingredients": [
            {"name": i["name"], "quantity": i["quantity"], "unit": i["unit"], "notes": i["notes"]}
            for i in ingredients_of(db, recipe.id)
        ],
        "instructions": recipe.instructions,
        "nutrition": {
            "calories": recipe.calories,
            "protein_g": recipe.protein_g,
            "carbs_g": recipe.carbs_g,
            "fat_g": recipe.fat_g,
        },
        "tags": recipe.tags,
    }
