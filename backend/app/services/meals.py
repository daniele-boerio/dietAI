"""Quello che si fa a un singolo pasto del piano: assegnarlo, svuotarlo, fissarlo,
segnarlo «l'ho seguito» o «ho mangiato altro (cosa?)».

Le rotte di `routers/planning.py` tengono la proprietà e il client del modello;
qui ogni azione cambia il pasto, ricalcola la spesa e risponde col pasto intero
(`serialize_meal(full=True)`), come vuole la regola delle risposte complete.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import DayPlan, MealSlot, PlannedMeal, Recipe, User, WeekPlan
from . import macros, prompts
from .exclusions import recipe_violations
from .ownership import own_meal
from .planner import (
    DAY_NAMES,
    clear_meal_cell,
    ensure_not_skipped,
    forget_queued_meal,
    forget_tracking,
    serialize_meal,
    skip_meal,
    spread_recurring,
    stop_recurring_forward,
    unskip_meal,
    week_meals,
)
from .recipes import create_recipe, declared_details
from .shopping import consume_from_pantry, rebuild_shopping_list, restore_to_pantry

NIENTE = "Non ho mangiato niente"

MAX_KCAL_PASTO = 5000


def _full(db: Session, day: DayPlan, meal: PlannedMeal) -> dict:
    slot = db.get(MealSlot, meal.meal_slot_id)
    return serialize_meal(db, day, meal, slot, full=True)


def assign(
    db: Session,
    user: User,
    meal: PlannedMeal,
    day: DayPlan,
    recipe_id: int | None,
    recipe_data: dict | None,
) -> dict:
    """Assegna al pasto una ricetta del ricettario o una scritta al momento."""
    ensure_not_skipped(day, meal)

    if recipe_id:
        recipe = (
            db.query(Recipe)
            .filter(Recipe.id == recipe_id, Recipe.user_id == user.id)
            .first()
        )
        if not recipe:
            raise HTTPException(404, "Ricetta non trovata")
        # Un piatto del modello nato prima che l'alimento fosse escluso (un'allergia
        # scoperta dopo) dal ricettario non torna nel piano. Quelli scritti dall'utente
        # li decide lui.
        trovati = [] if recipe.is_custom else recipe_violations(db, user.id, recipe.id)
        if trovati:
            raise HTTPException(
                422, f"«{recipe.title}» contiene {', '.join(trovati)}, che hai escluso."
            )
        meal.recipe_id = recipe.id
        meal.source = "from_favorites" if recipe.is_favorite else "user_custom"
    elif recipe_data:
        recipe = create_recipe(db, user.id, recipe_data, is_custom=True)
        meal.recipe_id = recipe.id
        meal.source = "user_custom"
    else:
        raise HTTPException(400, "Serve recipe_id oppure una ricetta completa.")

    # Il piatto è un altro: quello che era stato scalato dalla dispensa resta scalato
    # (mangiato è mangiato), ma non ha più senso rimetterlo se domani si corregge — e la
    # stima di «cosa ho mangiato» descriveva il piatto di prima.
    forget_tracking(meal)
    # E se questa casella era la coda di un pasto rimandato, adesso non lo è più:
    # annullare quel salto non deve portarsi via la ricetta appena scelta.
    forget_queued_meal(db, meal)
    db.commit()

    rebuild_shopping_list(db, user.id)
    db.commit()
    return _full(db, day, meal)


def clear(db: Session, user_id: int, meal: PlannedMeal, day: DayPlan) -> dict:
    """Svuota la casella (la ricetta resta nel ricettario).

    È il "elimina" del piano, e non c'entra con "ho mangiato altro": lì il piatto era
    in programma e si è deciso altrimenti — resta scritto, e si accoda più avanti —
    qui invece in programma non c'è più, e la casella torna vuota come se non fosse
    mai stata riempita.

    Se il pasto era stato segnato come "seguito", gli ingredienti che erano stati
    tolti dalla dispensa vengono reimmessi prima di eliminare la ricetta.
    """
    if meal.is_followed is True and meal.pantry_used:
        restore_to_pantry(db, user_id, meal.pantry_used)

    clear_meal_cell(db, meal)
    db.commit()

    rebuild_shopping_list(db, user_id)
    db.commit()
    return _full(db, day, meal)


def set_recurring(
    db: Session, user_id: int, meal: PlannedMeal, day: DayPlan, is_recurring: bool, regola
) -> dict:
    """Marca il pasto come fisso: non verrà più rigenerato e si ripete ogni settimana."""
    if is_recurring and not meal.recipe_id:
        raise HTTPException(400, "Assegna prima una ricetta a questo pasto.")

    if regola is None or regola.type == "weekly":
        giorno = regola.day if regola is not None and regola.day is not None else day.day_of_week
        rule = {"type": "weekly", "day": giorno}
    else:
        rule = {"type": "daily"}

    meal.is_recurring = is_recurring
    meal.recurring_rule = rule if is_recurring else None

    # Togliere la spunta non è solo smettere di ricopiare in avanti: le copie sulle
    # settimane già aperte ci sono già, e lasciarle vorrebbe dire spegnere
    # l'interruttore trovandosi la luce accesa lo stesso.
    tolte = 0 if is_recurring else stop_recurring_forward(db, user_id, meal, day)
    messe = spread_recurring(db, user_id, meal, day) if is_recurring else 0
    db.commit()

    if tolte or messe:
        # Il piano è cambiato da qui in avanti, quindi la spesa pure.
        rebuild_shopping_list(db, user_id)
        db.commit()

    payload = _full(db, day, meal)
    # Quante caselle si è portata via o ha riempito: senza dirlo, la ricetta sparita (o
    # comparsa) nei giorni dopo sembra un effetto collaterale invece della cosa chiesta.
    payload["cleared_forward"] = tolte
    payload["filled_forward"] = messe
    return payload


def eaten_instead(
    db: Session, client_for, meal: PlannedMeal, day: DayPlan, text: str | None, nothing: bool
) -> dict:
    """«Ho mangiato altro: cosa?» — il testo e la stima di calorie e macro.

    Vale solo su un pasto segnato «ho mangiato altro»: su uno seguito si è mangiato il
    piatto in programma, e su uno non ancora segnato non si sa cosa sia successo. Il
    testo vuoto cancella testo e stima. La stima la fa il modello (ruolo `chat`, una
    chiamata breve): è un ordine di grandezza, e la pagina lo dice. `client_for`
    costruisce il client solo se serve davvero chiamarlo.
    """
    slot = db.get(MealSlot, meal.meal_slot_id)
    if meal.is_followed is not False:
        raise HTTPException(
            400, "Prima segna il pasto come «ho mangiato altro», poi scrivi cosa."
        )
    testo = (text or "").strip()
    if nothing:
        # Saltato davvero: tutto a zero, e uno zero che si sa — nell'andamento il
        # giorno torna completo, e a healthAI arriva un pasto a 0 kcal, non un buco.
        # Nessuna chiamata al modello: non c'è niente da stimare.
        meal.deviation_notes = NIENTE
        meal.eaten_nutrition = {
            "calories": 0,
            "protein_g": 0.0,
            "carbs_g": 0.0,
            "fat_g": 0.0,
            **{campo: 0.0 for campo in macros.CAMPI_DETTAGLIO},
            "note": None,
        }
    elif not testo:
        meal.deviation_notes = None
        meal.eaten_nutrition = None
    else:
        client = client_for()
        db.commit()  # niente transazione aperta durante la chiamata al modello
        data = client.generate_json(
            prompts.EATEN_ESTIMATE_SYSTEM,
            prompts.render(prompts.EATEN_ESTIMATE_PROMPT, slot_name=slot.name, text=testo),
            max_tokens=800,
            thinking=False,
        )
        meal.deviation_notes = testo
        meal.eaten_nutrition = _eaten_estimate(data)
    db.commit()
    return serialize_meal(db, day, meal, slot, full=True)


def _eaten_estimate(data) -> dict | None:
    """La stima ripulita: numeri non negativi, o None se il modello non ne ha dati."""
    if not isinstance(data, dict):
        return None
    out = {}
    for key in ("calories", "protein_g", "carbs_g", "fat_g"):
        try:
            out[key] = max(0.0, float(data.get(key)))
        except (TypeError, ValueError):
            return None
    out["calories"] = int(round(out["calories"]))
    # Un pasto da 40000 kcal è una risposta sbagliata, non un pasto: finiva così
    # nell'andamento e a healthAI. Oltre un tetto largo la stima non vale.
    if out["calories"] > MAX_KCAL_PASTO:
        return None
    for key in ("protein_g", "carbs_g", "fat_g"):
        out[key] = round(out[key], 1)
    # Gli altri valori sono facoltativi uno per uno: un None resta None ("non lo so"),
    # uno zero resta zero ("non ce n'è") — healthAI li legge in due modi diversi.
    out.update(
        macros.coherent_details(declared_details(data), out["carbs_g"], out["fat_g"])
    )
    note = data.get("note")
    out["note"] = str(note)[:200] if note else None
    return out


def set_followed(
    db: Session,
    user_id: int,
    meal: PlannedMeal,
    day: DayPlan,
    week: WeekPlan,
    is_followed: bool | None,
    deviation_notes: str | None,
) -> dict:
    """Traccia com'è andata — e con "ho mangiato altro" rimanda il piatto più avanti.

    Funziona anche a piano bloccato, anzi soprattutto: a spesa fatta gli ingredienti
    sono in frigo, quindi un piatto non cucinato non è perso, si accoda alla prima
    casella libera di quel pasto. Dire invece "l'ho seguito" annulla il rinvio e la
    ricetta torna al suo posto.

    "L'ho seguito" è anche il momento in cui gli ingredienti finiscono davvero: la
    dispensa si scala qui, una volta sola per pasto (`pantry_used` è la memoria di
    cosa è stato tolto), e si rimette identica se il pasto viene corretto.
    """
    # La stima di «cosa ho mangiato» vale finché il pasto resta «ho mangiato altro»:
    # cambiando risposta non descrive più niente.
    if meal.is_followed is not False or is_followed is not False:
        meal.eaten_nutrition = None
    meal.is_followed = is_followed
    meal.deviation_notes = deviation_notes

    pantry_used: list[dict] = []
    pantry_skipped: list[dict] = []
    if is_followed:
        unskip_meal(db, meal)
        moved = {"moved_to": None}
        if meal.pantry_used is None:
            slot = db.get(MealSlot, meal.meal_slot_id)
            pantry_used, pantry_skipped = consume_from_pantry(
                db, user_id, meal.recipe_id, slot.servings if slot else 1
            )
            # Niente scalato, niente da ricordare: `pantry_used` risponde a "cosa ho
            # tolto", ed è anche la guardia contro il doppio scalo. Segnarci una lista
            # vuota vorrebbe dire "già fatto" per sempre, e un pasto segnato prima
            # della spesa non si scalerebbe più nemmeno a dispensa piena.
            meal.pantry_used = pantry_used or None
    else:
        # Prima la dispensa, poi il salto: `skip_meal` scrive sul database, e un pasto
        # «non seguito» con ancora `pantry_used` è uno stato che il vincolo rifiuta.
        tolto, meal.pantry_used = meal.pantry_used, None
        restore_to_pantry(db, user_id, tolto)
        moved = skip_meal(db, user_id, meal, day, week)
    db.commit()

    rebuild_shopping_list(db, user_id)
    db.commit()

    data = _full(db, day, meal)
    data["moved_to"] = moved["moved_to"]
    # Quello che è appena uscito dalla dispensa: la pagina lo dice, altrimenti la
    # scorta cala di nascosto e nessuno si fida più del numero. E quello che non è
    # uscito, col motivo: una dispensa che resta ferma senza spiegazioni sembra un
    # pulsante che non funziona.
    data["pantry_used"] = pantry_used
    data["pantry_skipped"] = pantry_skipped
    return data


# ── Scambio fra due pasti della settimana ──────────────────────────────────────


def swap_block(day: DayPlan, meal: PlannedMeal, slot: MealSlot) -> str | None:
    """Perché questa casella non può entrare in uno scambio, o None se può.

    Una regola sola per la lista dei candidati e per lo scambio vero: se la pagina
    decidesse da sé, prima o poi proporrebbe uno scambio che il server rifiuta.
    """
    if day.is_skipped or meal.is_skipped:
        return "saltato"
    if not slot.auto_generate:
        # Una casella «lo faccio io» non ha ricetta e non va in spesa: un piatto
        # spostato lì non verrebbe comprato.
        return "lo fai tu"
    if meal.is_recurring:
        # Il fisso è ancorato al suo giorno e si ricopia da lì ogni settimana.
        return "fisso"
    if meal.is_followed is not None:
        return "già segnato"
    return None


def _label(day: DayPlan, slot: MealSlot) -> str:
    return f"{slot.name} di {DAY_NAMES[day.day_of_week].lower()}"


def swap_candidates(db: Session, meal: PlannedMeal, week: WeekPlan) -> list[dict]:
    """Gli altri pasti della settimana, ognuno col motivo per cui non si può, se c'è."""
    out = []
    for day, other, slot in week_meals(db, week):
        if other.id == meal.id:
            continue
        recipe = db.get(Recipe, other.recipe_id) if other.recipe_id else None
        out.append(
            {
                "meal_id": other.id,
                "date": day.date.isoformat(),
                "day_name": DAY_NAMES[day.day_of_week],
                "slot_name": slot.name,
                "target_calories": slot.target_calories,
                "recipe": (
                    {"id": recipe.id, "title": recipe.title, "calories": recipe.calories}
                    if recipe
                    else None
                ),
                "blocked": swap_block(day, other, slot),
            }
        )
    return out


def swap(
    db: Session, user_id: int, meal: PlannedMeal, day: DayPlan, week: WeekPlan, other_id: int
) -> dict:
    """Scambia le ricette di due pasti della stessa settimana.

    I target dei due pasti non si toccano, quindi i totali dei due giorni cambiano: è
    voluto, perché quello che conta in nutrizione è il fabbisogno della settimana, e
    quello resta identico. Una casella vuota vale: il piatto si sposta e basta.

    Il rinvio di un pasto saltato (`skipped_to_meal_id`) segue il piatto: se una
    delle due caselle ospitava un piatto rimandato, «l'ho seguito» sul pasto saltato
    deve svuotare la casella dove il piatto è finito adesso, non quella di prima.
    """
    if other_id == meal.id:
        raise HTTPException(400, "Scegli un altro pasto.")
    other, other_day, other_week = own_meal(db, user_id, other_id)
    if other_week.id != week.id:
        raise HTTPException(400, "Si scambia solo con un pasto della stessa settimana.")

    slot = db.get(MealSlot, meal.meal_slot_id)
    other_slot = db.get(MealSlot, other.meal_slot_id)
    for d, m, s in ((day, meal, slot), (other_day, other, other_slot)):
        motivo = swap_block(d, m, s)
        if motivo:
            raise HTTPException(409, f"{_label(d, s).capitalize()}: {motivo}, non si scambia.")
    if not meal.recipe_id and not other.recipe_id:
        raise HTTPException(400, "Tutte e due le caselle sono vuote: non c'è niente da scambiare.")

    meal.recipe_id, other.recipe_id = other.recipe_id, meal.recipe_id
    meal.source, other.source = other.source, meal.source
    forget_tracking(meal)
    forget_tracking(other)

    verso_qui = db.query(PlannedMeal).filter(PlannedMeal.skipped_to_meal_id == meal.id).all()
    verso_la = db.query(PlannedMeal).filter(PlannedMeal.skipped_to_meal_id == other.id).all()
    for saltato in verso_qui:
        saltato.skipped_to_meal_id = other.id
    for saltato in verso_la:
        saltato.skipped_to_meal_id = meal.id
    db.commit()

    rebuild_shopping_list(db, user_id)
    db.commit()

    data = _full(db, day, meal)
    data["swapped_with"] = {
        "meal_id": other.id,
        "day_name": DAY_NAMES[other_day.day_of_week],
        "slot_name": other_slot.name,
        "date": other_day.date.isoformat(),
    }
    return data
