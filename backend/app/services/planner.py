"""Pianificazione settimanale: struttura delle settimane e generazione AI.

Il modello mentale: una settimana esiste sempre (lunedì → domenica) e contiene già
una casella per ogni incrocio giorno × pasto della dieta, anche vuota. Generare
significa riempire le caselle libere; rigenerare significa svuotarne una e
richiederla di nuovo. Le caselle "fissate" (pasti ricorrenti e ricette scelte a mano
dall'utente) l'AI non le tocca mai.
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import (
    BaseIngredient,
    DayPlan,
    DietPlan,
    ExcludedIngredient,
    Ingredient,
    MealSlot,
    PantryItem,
    PlannedMeal,
    Recipe,
    RecipeIngredient,
    ShoppingList,
    User,
    UserPreferences,
    WeekPlan,
)
from ..utils.seasonality import current_month, current_month_name, in_season
from ..utils.units import format_quantity
from . import prompts
from .ai_client import AIError, get_client
from .recipes import copy_recipe, create_recipe, recipe_for_prompt, serialize_recipe

logger = logging.getLogger(__name__)

DAY_NAMES = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

LOCK_DAYS = 7


# ── Settimane ──────────────────────────────────────────────────────────────────


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def today() -> date:
    """Il punto unico da cui l'app legge la data di oggi.

    Esiste perché lo slittamento dei giorni saltati dipende da che giorno è: i test
    devono poterlo spostare, altrimenti la stessa suite darebbe risultati diversi il
    lunedì e il venerdì.
    """
    return date.today()


def current_week_start() -> date:
    return monday_of(today())


def next_week_start() -> date:
    return current_week_start() + timedelta(days=7)


def get_active_diet(db: Session, user_id: int) -> DietPlan | None:
    return (
        db.query(DietPlan)
        .filter(DietPlan.user_id == user_id, DietPlan.is_active.is_(True))
        .order_by(DietPlan.created_at.desc())
        .first()
    )


def require_active_diet(db: Session, user_id: int) -> DietPlan:
    diet = get_active_diet(db, user_id)
    if not diet:
        raise HTTPException(
            400, "Nessuna dieta attiva: carica il PDF del nutrizionista per iniziare."
        )
    return diet


def meal_slots_of(db: Session, diet_plan_id: int) -> list[MealSlot]:
    return (
        db.query(MealSlot)
        .filter(MealSlot.diet_plan_id == diet_plan_id)
        .order_by(MealSlot.order_index)
        .all()
    )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def refresh_week_statuses(db: Session, user_id: int) -> None:
    """Archivia le settimane scadute e promuove quella corrente.

    Il blocco della spesa dura 7 giorni; quando scade la settimana diventa storia e
    quella nuova prende il posto di "corrente". Viene chiamato all'inizio di ogni
    lettura del piano, così lo stato è sempre coerente senza bisogno di uno scheduler.
    """
    now = datetime.now(timezone.utc)
    this_monday = current_week_start()
    changed = False

    for week in db.query(WeekPlan).filter(WeekPlan.user_id == user_id).all():
        expired_lock = (
            week.is_locked
            and week.lock_expires_at is not None
            and _as_utc(week.lock_expires_at) < now
        )
        if expired_lock:
            week.is_locked = False
            changed = True

        if week.week_start_date < this_monday:
            if week.status != "archived":
                week.status = "archived"
                changed = True
        elif week.week_start_date == this_monday:
            target = "locked" if week.is_locked else "active"
            if week.status != target:
                week.status = target
                changed = True

    if changed:
        db.commit()


def ensure_week_structure(db: Session, week: WeekPlan, slots: list[MealSlot]) -> None:
    """Crea i giorni e le caselle mancanti.

    Serve anche dopo una modifica della dieta (pasti aggiunti o rinominati): le
    settimane già create devono adeguarsi senza essere buttate via.
    """
    days = {d.day_of_week: d for d in db.query(DayPlan).filter(DayPlan.week_plan_id == week.id)}

    for offset in range(7):
        if offset not in days:
            day = DayPlan(
                week_plan_id=week.id,
                date=week.week_start_date + timedelta(days=offset),
                day_of_week=offset,
            )
            db.add(day)
            db.flush()
            days[offset] = day

    slot_ids = {s.id for s in slots}
    for day in days.values():
        existing = {
            m.meal_slot_id
            for m in db.query(PlannedMeal).filter(PlannedMeal.day_plan_id == day.id)
        }
        for slot_id in slot_ids - existing:
            db.add(
                PlannedMeal(day_plan_id=day.id, meal_slot_id=slot_id, source="ai_generated")
            )
    db.flush()


def get_or_create_week(db: Session, user_id: int, week_start: date) -> WeekPlan:
    diet = require_active_diet(db, user_id)
    slots = meal_slots_of(db, diet.id)
    if not slots:
        raise HTTPException(400, "La dieta attiva non ha pasti configurati.")

    week = (
        db.query(WeekPlan)
        .filter(WeekPlan.user_id == user_id, WeekPlan.week_start_date == week_start)
        .first()
    )
    created = week is None
    if created:
        week = WeekPlan(
            user_id=user_id,
            week_start_date=week_start,
            status="active" if week_start == current_week_start() else "draft",
        )
        db.add(week)
        db.flush()

    ensure_week_structure(db, week, slots)
    if created:
        apply_recurring_meals(db, user_id, week)
    # Sta qui e non nel router perché ogni lettura del piano passa da questa funzione:
    # aprire l'app è ciò che fa scattare lo slittamento, senza pulsanti da premere.
    if week.week_start_date == current_week_start():
        shift_past_days(db, user_id, week)
    db.commit()
    return week


# Oltre questo tempo una generazione si considera morta (processo riavviato, container
# ricreato): senza, una settimana resterebbe "in generazione" per sempre.
GENERATION_TIMEOUT = timedelta(minutes=15)


def is_generating(week: WeekPlan) -> bool:
    started = _as_utc(week.generation_started_at)
    if started is None:
        return False
    return datetime.now(timezone.utc) - started < GENERATION_TIMEOUT


def ensure_not_generating(week: WeekPlan) -> None:
    """Una generazione alla volta per settimana.

    Non è pignoleria: ogni chiamata si paga, e senza questo controllo bastava
    ricaricare la pagina e ripremere il pulsante per farne partire una seconda.
    """
    if is_generating(week):
        raise HTTPException(
            409,
            "C'è già una generazione in corso per questa settimana: aspetta che finisca.",
        )


def ensure_unlocked(week: WeekPlan) -> None:
    if week.is_locked:
        raise HTTPException(
            409,
            "Piano bloccato: hai già fatto la spesa per questa settimana. "
            "Modifica la settimana successiva, oppure sblocca il piano dalle impostazioni.",
        )


def ensure_not_skipped(day: DayPlan, meal: PlannedMeal | None = None) -> None:
    if meal is not None and meal.is_skipped:
        raise HTTPException(
            409,
            "Questo pasto è saltato: la sua ricetta si è accodata più avanti. "
            'Segnalo come seguito per riportarlo qui.',
        )
    if day.is_skipped:
        raise HTTPException(
            409,
            "Questo giorno è saltato: è passato senza che la spesa fosse fatta e le "
            "sue ricette sono slittate in avanti.",
        )


# ── Pasti fissi ────────────────────────────────────────────────────────────────


def _is_fixed(meal: PlannedMeal, slot: MealSlot) -> bool:
    """Un pasto fissato non viene toccato né dalla generazione né dallo slittamento.

    Tre modi per esserlo: è ricorrente, l'utente gli ha assegnato una ricetta a mano,
    oppure il pasto è marcato nella dieta come "lo gestisco io" (`auto_generate` a
    False) — la colazione di sempre, che non ha senso far reinventare ogni settimana.
    """
    return meal.is_recurring or meal.source == "user_custom" or not slot.auto_generate


# ── Pasti ricorrenti ───────────────────────────────────────────────────────────


def apply_recurring_meals(db: Session, user_id: int, week: WeekPlan) -> int:
    """Pre-assegna alla settimana i pasti marcati come ricorrenti nella precedente.

    La ricetta viene COPIATA, non condivisa: modificare la colazione di questa
    settimana non deve riscrivere quella delle settimane già archiviate.
    """
    previous = (
        db.query(WeekPlan)
        .filter(WeekPlan.user_id == user_id, WeekPlan.week_start_date < week.week_start_date)
        .order_by(WeekPlan.week_start_date.desc())
        .first()
    )
    if not previous:
        return 0

    recurring = (
        db.query(PlannedMeal, DayPlan)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .filter(
            DayPlan.week_plan_id == previous.id,
            PlannedMeal.is_recurring.is_(True),
            PlannedMeal.recipe_id.isnot(None),
        )
        .all()
    )
    if not recurring:
        return 0

    days = {d.day_of_week: d for d in db.query(DayPlan).filter(DayPlan.week_plan_id == week.id)}
    applied = 0

    for meal, source_day in recurring:
        rule = meal.recurring_rule or {"type": "weekly", "day": source_day.day_of_week}
        if rule.get("type") == "daily":
            targets = list(days.values())
        else:
            day = days.get(rule.get("day", source_day.day_of_week))
            targets = [day] if day else []

        recipe = db.get(Recipe, meal.recipe_id)
        if not recipe:
            continue

        for target_day in targets:
            target = (
                db.query(PlannedMeal)
                .filter(
                    PlannedMeal.day_plan_id == target_day.id,
                    PlannedMeal.meal_slot_id == meal.meal_slot_id,
                )
                .first()
            )
            if not target or target.recipe_id:
                continue
            target.recipe_id = copy_recipe(db, recipe).id
            target.source = meal.source
            target.is_recurring = True
            target.recurring_rule = rule
            applied += 1

    db.flush()
    return applied


# ── Giorni saltati e slittamento ───────────────────────────────────────────────


def _shopping_done(db: Session, week: WeekPlan) -> bool:
    return (
        db.query(ShoppingList)
        .filter(ShoppingList.week_plan_id == week.id, ShoppingList.is_completed.is_(True))
        .first()
        is not None
    )


def _eaten(db: Session, day: DayPlan) -> bool:
    """L'utente ha confermato di aver seguito almeno un pasto di quel giorno.

    Solo il "sì" conta: "ho mangiato altro" vuol dire l'opposto — quel piatto non è
    stato cucinato — e non deve impedire di dare il giorno per saltato.
    """
    return (
        db.query(PlannedMeal)
        .filter(PlannedMeal.day_plan_id == day.id, PlannedMeal.is_followed.is_(True))
        .first()
        is not None
    )


def _empty_meal(meal: PlannedMeal) -> None:
    meal.recipe_id = None
    meal.source = "ai_generated"
    meal.is_shifted = False
    meal.is_followed = None
    meal.deviation_notes = None


def _overflow_week(db: Session, user_id: int, week: WeekPlan) -> WeekPlan | None:
    """La settimana dopo, dove finisce quello che in questa non entra più."""
    if not get_active_diet(db, user_id):
        return None
    following = get_or_create_week(db, user_id, week.week_start_date + timedelta(days=7))
    # Se per la prossima la spesa è già stata fatta, quel piano è intoccabile: le
    # ricette in eccedenza restano nel ricettario e basta.
    return None if following.is_locked else following


def shift_past_days(db: Session, user_id: int, week: WeekPlan) -> int:
    """Finché la spesa non è fatta, i giorni che passano si saltano e il piano slitta.

    Il piano è ancorato alla spesa, non al calendario. Se lunedì non sei andato a fare
    la spesa, lunedì non hai cucinato quello che c'era in piano: comprarne mercoledì
    gli ingredienti vorrebbe dire comprare roba per un giorno che non tornerà. Il
    giorno diventa "saltato" — fuori dalla lista della spesa, dalla generazione e dal
    tracking — e le ricette scalano tutte in avanti di un posto, così quello che avevi
    in programma lo mangi lo stesso. Quelle che non entrano più in settimana
    traboccano su quella dopo.

    Due eccezioni. I pasti fissi non slittano: la pizza del sabato è del sabato, non
    di giovedì. E un giorno già tracciato non si salta — aver detto "questo pasto
    l'ho seguito" significa che quel giorno hai mangiato, spesa o no.

    Ritorna quanti giorni sono stati saltati adesso; 0 se non c'era niente da fare.
    """
    if week.is_locked or week.week_start_date != current_week_start():
        return 0
    # Non basta guardare il blocco: dopo uno sblocco d'emergenza la spesa resta fatta,
    # e allora il cibo è in casa. Slittare lì vorrebbe dire spostare piatti di cui gli
    # ingredienti sono già nel frigo.
    if _shopping_done(db, week):
        return 0
    # Il modello sta scrivendo proprio in queste caselle: si rimanda alla lettura dopo.
    if is_generating(week):
        return 0

    days = (
        db.query(DayPlan)
        .filter(DayPlan.week_plan_id == week.id)
        .order_by(DayPlan.day_of_week)
        .all()
    )
    to_skip = [
        d for d in days if d.date < today() and not d.is_skipped and not _eaten(db, d)
    ]
    if not to_skip:
        return 0

    for day in to_skip:
        day.is_skipped = True
    db.flush()

    _reflow_recipes(db, user_id, week)
    db.flush()
    return len(to_skip)


# ── Pasti saltati a mano ───────────────────────────────────────────────────────


def _free_cells(db: Session, user_id: int, week: WeekPlan, slot_id: int) -> list[PlannedMeal]:
    """Le caselle libere di quello slot da oggi in avanti, in ordine di giorno.

    Prima quelle rimaste vuote in questa settimana, poi quelle della prossima: è la
    coda su cui si accoda un piatto saltato.
    """
    now = today()
    out = []
    for source in (week, _overflow_week(db, user_id, week)):
        if source is None:
            continue
        for day, meal, slot in week_meals(db, source):
            if slot.id != slot_id or _is_fixed(meal, slot):
                continue
            if day.is_skipped or meal.is_skipped or meal.recipe_id:
                continue
            if source is week and day.date < now:
                continue  # un giorno già passato non è un posto dove rimandare niente
            out.append(meal)
    return out


def skip_meal(db: Session, user_id: int, meal: PlannedMeal, day: DayPlan, week: WeekPlan) -> dict:
    """"Ho mangiato altro": il piatto non è stato cucinato, la ricetta va in fondo.

    Non fa slittare niente: gli altri giorni restano dove sono e la ricetta saltata si
    accoda sulla prima casella libera di quel pasto — più avanti in settimana se ce
    n'è una, altrimenti nella settimana prossima. È la lettura giusta a spesa fatta:
    gli ingredienti sono in frigo, quel piatto lo cucini un altro giorno.

    La casella saltata tiene la sua `recipe_id` come memoria di cosa c'era in
    programma, ma smette di contare ovunque: spesa, totali, tracking, generazione.
    """
    if meal.is_skipped:
        return {"moved_to": None}

    slot = db.get(MealSlot, meal.meal_slot_id)
    meal.is_skipped = True

    # Un pasto fisso o gestito dall'utente non si sposta: è ancorato a quel giorno
    # per scelta di chi l'ha messo lì, e la settimana prossima si ricopia da solo.
    if _is_fixed(meal, slot) or not meal.recipe_id:
        db.flush()
        return {"moved_to": None}

    free = _free_cells(db, user_id, week, slot.id)
    if not free:
        db.flush()
        return {"moved_to": None}

    target = free[0]
    target.recipe_id = meal.recipe_id
    target.source = meal.source
    target.is_followed = None
    target.deviation_notes = None
    db.flush()

    target_day = db.get(DayPlan, target.day_plan_id)
    return {
        "moved_to": {
            "meal_id": target.id,
            "date": target_day.date.isoformat(),
            "day_name": DAY_NAMES[target_day.day_of_week],
            "next_week": target_day.week_plan_id != week.id,
        }
    }


def unskip_meal(db: Session, user_id: int, meal: PlannedMeal, week: WeekPlan) -> None:
    """Annulla il salto: la ricetta torna qui dalla casella dov'era stata accodata."""
    if not meal.is_skipped:
        return

    meal.is_skipped = False
    if not meal.recipe_id:
        db.flush()
        return

    for source in (week, _overflow_week(db, user_id, week)):
        if source is None:
            continue
        for _day, other, slot in week_meals(db, source):
            same = (
                other.id != meal.id
                and other.meal_slot_id == meal.meal_slot_id
                and other.recipe_id == meal.recipe_id
                and not other.is_skipped
                and not _is_fixed(other, slot)
            )
            if same:
                _empty_meal(other)
                db.flush()
                return
    db.flush()


def skip_day(db: Session, user_id: int, day: DayPlan, week: WeekPlan, skipped: bool) -> None:
    """Salta (o rimette) l'intera giornata: vale per tutti i suoi pasti insieme.

    Serve per il weekend fuori. Solo da oggi in avanti: i giorni passati senza spesa
    li salta già `shift_past_days`, e lì le ricette slittano invece di accodarsi —
    sono due cose diverse, perché lì il cibo non è mai stato comprato.
    """
    if day.date < today():
        raise HTTPException(409, "Un giorno già passato non si salta a mano.")

    day.is_skipped = skipped
    meals = db.query(PlannedMeal).filter(PlannedMeal.day_plan_id == day.id).all()
    for meal in meals:
        if skipped:
            skip_meal(db, user_id, meal, day, week)
        else:
            unskip_meal(db, user_id, meal, week)
    db.flush()


def _reflow_recipes(db: Session, user_id: int, week: WeekPlan) -> None:
    """Rimette in fila le ricette dopo che uno o più giorni sono stati saltati.

    Una fila per ogni pasto della dieta: si prendono le ricette ancora da mangiare —
    in ordine di giorno, comprese quelle rimaste sui giorni saltati — e si riscrivono
    sulle caselle libere da oggi in avanti, poi su quelle della settimana dopo. Fila
    per slot e non per giornata intera perché così un pasto fisso non viene
    sovrascritto: la coda lo scavalca e prosegue.
    """
    now = today()
    # Prima la settimana di sbocco: crearla fa un commit, e leggere i pasti dopo evita
    # di ritrovarsi in mano oggetti scaduti da ricaricare uno per uno.
    following = _overflow_week(db, user_id, week)
    rows = week_meals(db, week)
    next_rows = week_meals(db, following) if following else []

    # Un giorno passato ma non saltato è un giorno già mangiato (l'utente l'ha
    # tracciato): non mette ricette in fila e non ne riceve. Un pasto saltato a mano
    # è fuori da entrambe le parti: la sua ricetta si è già accodata altrove, e la
    # casella resta com'è a ricordare cosa c'era.
    def gives(day: DayPlan, meal: PlannedMeal) -> bool:
        return (day.is_skipped or day.date >= now) and not meal.is_skipped

    def takes(day: DayPlan, meal: PlannedMeal) -> bool:
        return not day.is_skipped and not meal.is_skipped and day.date >= now

    for slot_id in sorted({s.id for _, _, s in rows}):
        queue = [
            m
            for d, m, s in rows
            if s.id == slot_id and gives(d, m) and not _is_fixed(m, s) and m.recipe_id
        ]
        # Quello che era già traboccato sulla settimana dopo rientra in fila: senza,
        # slittando due giorni di seguito la ricetta di oggi gli passerebbe davanti.
        queue += [
            m
            for _, m, s in next_rows
            if s.id == slot_id
            and m.is_shifted
            and not m.is_skipped
            and not _is_fixed(m, s)
            and m.recipe_id
        ]
        recipes = [(m.recipe_id, m.source) for m in queue]

        cells = [
            (m, False)
            for d, m, s in rows
            if s.id == slot_id and takes(d, m) and not _is_fixed(m, s)
        ]
        cells += [
            (m, True)
            for _, m, s in next_rows
            if s.id == slot_id
            and not _is_fixed(m, s)
            and not m.is_skipped
            and (m.recipe_id is None or m.is_shifted)
        ]

        for meal in queue:
            _empty_meal(meal)
        for (meal, overflowed), (recipe_id, source) in zip(cells, recipes):
            meal.recipe_id = recipe_id
            meal.source = source
            meal.is_shifted = overflowed
            meal.is_followed = None
            meal.deviation_notes = None

        if len(recipes) > len(cells):
            logger.info(
                "Slittamento: %s ricette senza più posto (slot %s), restano nel ricettario",
                len(recipes) - len(cells),
                slot_id,
            )


# ── Contesto per i prompt ──────────────────────────────────────────────────────


def _excluded_names(db: Session, user_id: int) -> list[str]:
    rows = (
        db.query(ExcludedIngredient, Ingredient)
        .outerjoin(Ingredient, Ingredient.id == ExcludedIngredient.ingredient_id)
        .filter(ExcludedIngredient.user_id == user_id)
        .all()
    )
    return [ing.name if ing else (exc.custom_name or "") for exc, ing in rows if ing or exc.custom_name]


def _base_names(db: Session, user_id: int) -> list[str]:
    rows = (
        db.query(Ingredient.name)
        .join(BaseIngredient, BaseIngredient.ingredient_id == Ingredient.id)
        .filter(BaseIngredient.user_id == user_id)
        .all()
    )
    return [r[0] for r in rows]


def _pantry_descriptions(db: Session, user_id: int) -> list[str]:
    rows = (
        db.query(PantryItem, Ingredient)
        .join(Ingredient, Ingredient.id == PantryItem.ingredient_id)
        .filter(PantryItem.user_id == user_id)
        .all()
    )
    out = []
    for item, ing in rows:
        if item.quantity_available:
            out.append(f"{ing.name} ({format_quantity(item.quantity_available, item.unit or 'unità')})")
        else:
            out.append(ing.name)
    return out


def _rated_titles(db: Session, user_id: int, high: bool) -> list[str]:
    query = db.query(Recipe.title).filter(Recipe.user_id == user_id)
    query = query.filter(Recipe.rating >= 4) if high else query.filter(Recipe.rating <= 2)
    return [r[0] for r in query.order_by(Recipe.id.desc()).limit(15).all()]


def _fmt_list(values: list[str], empty: str = "nessuno") -> str:
    values = [v for v in values if v]
    return ", ".join(sorted(set(values))) if values else empty


def build_context(db: Session, user_id: int) -> str:
    """Il blocco di contesto comune a tutti i prompt di generazione."""
    diet = require_active_diet(db, user_id)
    slots = meal_slots_of(db, diet.id)
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()

    meals_config = "\n".join(
        f"  · {s.name}: {s.target_calories} kcal — proteine {s.target_protein_g:g}g, "
        f"carboidrati {s.target_carbs_g:g}g, grassi {s.target_fat_g:g}g"
        + (f" — note: {s.notes}" if s.notes else "")
        # Elencato lo stesso, perché conta nel bilancio della giornata, ma va detto
        # che non si tocca: senza, il modello prova a proporcelo comunque.
        + ("" if s.auto_generate else " — NON generare: se lo prepara l'utente")
        for s in slots
    )

    prefer_seasonal = prefs.prefer_seasonal if prefs else True
    prefer_italian = prefs.prefer_italian if prefs else True

    if prefer_seasonal:
        seasonal = ", ".join(in_season(current_month())[:25])
        seasonality = (
            f"privilegia gli ingredienti di stagione. Siamo a {current_month_name()}: "
            f"di stagione ci sono {seasonal}."
        )
    else:
        seasonality = "nessun vincolo di stagionalità."

    return prompts.render(
        prompts.CONTEXT_TEMPLATE,
        daily_calories=diet.total_daily_calories,
        meals_config=meals_config,
        excluded=_fmt_list(_excluded_names(db, user_id)),
        # Testo libero dell'utente: passa così com'è, senza interpretarlo. Regole
        # come "carne al massimo due volte a settimana" funzionano proprio perché il
        # piano si genera tutto in una volta e il modello vede l'intera settimana.
        extra_rules=((prefs.notes or "").strip() if prefs else "") or "nessuna",
        base=_fmt_list(_base_names(db, user_id)),
        pantry=_fmt_list(_pantry_descriptions(db, user_id), "vuota"),
        cuisine=(
            "italiana o mediterranea, piatti che si cucinano davvero in casa"
            if prefer_italian
            else "nessuna preferenza particolare"
        ),
        seasonality=seasonality,
        max_prep=(
            f"{prefs.max_prep_time_min} minuti"
            if prefs and prefs.max_prep_time_min
            else "nessun limite"
        ),
        budget=(prefs.budget_level if prefs and prefs.budget_level else "medio"),
        liked=_fmt_list(_rated_titles(db, user_id, True), "nessuna ancora"),
        disliked=_fmt_list(_rated_titles(db, user_id, False), "nessuna ancora"),
    )


# ── Lettura della settimana ────────────────────────────────────────────────────


def week_meals(db: Session, week: WeekPlan) -> list[tuple[DayPlan, PlannedMeal, MealSlot]]:
    return (
        db.query(DayPlan, PlannedMeal, MealSlot)
        .join(PlannedMeal, PlannedMeal.day_plan_id == DayPlan.id)
        .join(MealSlot, MealSlot.id == PlannedMeal.meal_slot_id)
        .filter(DayPlan.week_plan_id == week.id)
        .order_by(DayPlan.day_of_week, MealSlot.order_index)
        .all()
    )


def serialize_meal(
    db: Session, day: DayPlan, meal: PlannedMeal, slot: MealSlot, *, full: bool = False
) -> dict:
    recipe = db.get(Recipe, meal.recipe_id) if meal.recipe_id else None
    return {
        "id": meal.id,
        "day_of_week": day.day_of_week,
        "day_name": DAY_NAMES[day.day_of_week],
        "date": day.date.isoformat(),
        # Il giorno è passato senza spesa: la casella è in sola lettura come quando
        # il piano è bloccato, ma per un motivo diverso.
        "day_is_skipped": day.is_skipped,
        "slot_id": slot.id,
        "slot_name": slot.name,
        "slot_order": slot.order_index,
        "target": {
            "calories": slot.target_calories,
            "protein_g": slot.target_protein_g,
            "carbs_g": slot.target_carbs_g,
            "fat_g": slot.target_fat_g,
            "notes": slot.notes,
        },
        # "lo gestisco io": niente da generare, ma i macro contano nella giornata
        "self_managed": not slot.auto_generate,
        "source": meal.source,
        # "Ho mangiato altro": la ricetta qui sotto è quella che era in programma, ma
        # non è stata cucinata — si è accodata più avanti e qui non conta più.
        "is_skipped": meal.is_skipped,
        "is_recurring": meal.is_recurring,
        "recurring_rule": meal.recurring_rule,
        "is_followed": meal.is_followed,
        "deviation_notes": meal.deviation_notes,
        "recipe": serialize_recipe(db, recipe, full=full),
    }


def serialize_week(db: Session, week: WeekPlan) -> dict:
    rows = week_meals(db, week)
    days: dict[int, dict] = {}

    for day, meal, slot in rows:
        entry = days.setdefault(
            day.day_of_week,
            {
                "id": day.id,
                "date": day.date.isoformat(),
                "day_of_week": day.day_of_week,
                "day_name": DAY_NAMES[day.day_of_week],
                # Giorno passato senza spesa: le ricette sono slittate via, la
                # griglia lo mostra spento e la lista della spesa lo ignora.
                "is_skipped": day.is_skipped,
                "meals": [],
            },
        )
        entry["meals"].append(serialize_meal(db, day, meal, slot))

    for entry in days.values():
        # I pasti gestiti dall'utente non hanno una ricetta, ma lui li mangia centrando
        # i target: contarli col loro target è l'unico modo perché il totale del giorno
        # rappresenti quello che si mangia davvero e non solo quello che ha scritto l'AI.
        def _macros(meal: dict) -> dict:
            # Un pasto saltato conserva la ricetta per memoria, ma non è stato
            # mangiato: contarlo gonfierebbe la giornata di un piatto mai cucinato.
            if meal["is_skipped"]:
                return {}
            if meal["recipe"]:
                return meal["recipe"]
            return meal["target"] if meal["self_managed"] else {}

        contributi = [_macros(m) for m in entry["meals"]]
        entry["totals"] = {
            "calories": sum(c.get("calories", 0) for c in contributi),
            "protein_g": round(sum(c.get("protein_g", 0) for c in contributi), 1),
            "carbs_g": round(sum(c.get("carbs_g", 0) for c in contributi), 1),
            "fat_g": round(sum(c.get("fat_g", 0) for c in contributi), 1),
            # Anche il target scende: un pasto saltato non è un buco da colmare, è un
            # pasto che quel giorno non era in programma mangiare.
            "target_calories": sum(
                m["target"]["calories"] for m in entry["meals"] if not m["is_skipped"]
            ),
        }

    # "Da riempire" conta solo le caselle che l'AI deve generare: includere quelle
    # gestite dall'utente farebbe sembrare il piano perennemente incompleto. Stesso
    # motivo per i giorni saltati: sono passati, non c'è più niente da riempirci.
    da_vivere = [(d, m, s) for d, m, s in rows if not d.is_skipped and not m.is_skipped]
    generabili = [(d, m, s) for d, m, s in da_vivere if s.auto_generate]
    total_slots = len(generabili)
    filled = sum(1 for _, meal, _ in generabili if meal.recipe_id)
    self_managed = len(da_vivere) - total_slots

    return {
        "id": week.id,
        "week_start_date": week.week_start_date.isoformat(),
        "status": week.status,
        "is_locked": week.is_locked,
        "locked_at": week.locked_at.isoformat() if week.locked_at else None,
        "lock_expires_at": week.lock_expires_at.isoformat() if week.lock_expires_at else None,
        "is_current": week.week_start_date == current_week_start(),
        # La UI ci si aggancia per rimettere il loader quando si torna sulla pagina
        # a generazione avviata.
        "is_generating": is_generating(week),
        "meals_total": total_slots,
        "meals_filled": filled,
        "meals_self_managed": self_managed,
        "days_skipped": sum(1 for d in days.values() if d["is_skipped"]),
        "days": [days[k] for k in sorted(days)],
    }


# ── Generazione ────────────────────────────────────────────────────────────────


def _slot_line(slot: MealSlot) -> str:
    line = (
        f"{slot.name} — {slot.target_calories} kcal, P {slot.target_protein_g:g}g, "
        f"C {slot.target_carbs_g:g}g, G {slot.target_fat_g:g}g"
    )
    return line + (f" (note: {slot.notes})" if slot.notes else "")


def generate_week(
    db: Session, user: User, week: WeekPlan, *, only_missing: bool = True
) -> dict:
    """Genera in un'unica chiamata le ricette della settimana.

    Una chiamata sola, non una per pasto: è l'unico modo perché l'AI possa
    distribuire gli avanzi (mezza zucchina lunedì, l'altra metà giovedì) e non
    ripetere gli stessi ingredienti in giorni consecutivi.

    `only_missing` è il default perché ogni chiamata si paga: riempire i buchi è
    l'operazione di tutti i giorni, rifare da capo una settimana già piena è una
    scelta esplicita che la UI fa confermare.
    """
    ensure_unlocked(week)
    ensure_not_generating(week)
    rows = week_meals(db, week)
    if not rows:
        raise HTTPException(400, "La settimana non ha pasti da generare.")

    # I giorni saltati sono passati e i pasti saltati sono già stati risolti altrove:
    # generarci una ricetta vorrebbe dire pagare una chiamata per un piatto che nessuno
    # cucinerà. Vale anche per "Rigenera tutto", che altrimenti li ripescherebbe.
    rows = [(d, m, s) for d, m, s in rows if not d.is_skipped and not m.is_skipped]
    generabili = [(d, m, s) for d, m, s in rows if not _is_fixed(m, s)]
    to_fill = [t for t in generabili if t[1].recipe_id is None] if only_missing else generabili

    if not to_fill:
        if generabili:
            raise HTTPException(
                400,
                'Non ci sono pasti da riempire: usa "Rigenera tutto" per rifare la settimana.',
            )
        raise HTTPException(
            400,
            "Non c'è niente da generare: tutti i pasti sono fissi o gestiti da te.",
        )

    # Tutto ciò che conserva la sua ricetta va passato al modello come contesto: sono
    # i piatti da non ripetere e gli ingredienti già in casa da riutilizzare.
    da_rifare = {m.id for _, m, _ in to_fill}
    fixed = [(d, m, s) for d, m, s in rows if m.recipe_id and m.id not in da_rifare]

    by_day: dict[int, list[str]] = {}
    for day, _meal, slot in to_fill:
        by_day.setdefault(day.day_of_week, []).append(_slot_line(slot))
    slots_to_fill = "\n".join(
        f"{DAY_NAMES[dow]} (day_of_week {dow}):\n" + "\n".join(f"  · {line}" for line in lines)
        for dow, lines in sorted(by_day.items())
    )

    if fixed:
        already = "\n".join(
            f"  · {DAY_NAMES[d.day_of_week]} / {s.name}: "
            f"{db.get(Recipe, m.recipe_id).title}"
            for d, m, s in fixed
        )
    else:
        already = "  (nessuno)"

    prompt = prompts.render(
        prompts.WEEK_PLAN_PROMPT,
        context=build_context(db, user.id),
        slots_to_fill=slots_to_fill,
        already_assigned=already,
    )

    client = get_client(db, user, "planning")

    # Da qui in avanti la settimana risulta "in generazione". Il commit chiude anche
    # la transazione aperta dalle letture qui sopra: senza, Postgres si terrebbe una
    # connessione "idle in transaction" per tutta la durata della chiamata.
    week.generation_started_at = datetime.now(timezone.utc)
    db.commit()

    # Budget: ~2.000 token a ricetta più il margine per il ragionamento. Sopra la
    # soglia il client passa automaticamente in streaming.
    max_tokens = min(64000, 2000 * len(to_fill) + 6000)
    try:
        data = client.generate_json(
            prompts.WEEK_PLAN_SYSTEM,
            prompt,
            max_tokens=max_tokens,
            thinking=True,
        )
    except Exception:
        # Anche se va male la settimana deve tornare generabile, altrimenti resta
        # bloccata su "sto generando" fino allo scadere del timeout.
        week.generation_started_at = None
        db.commit()
        raise

    if not isinstance(data, dict) or not isinstance(data.get("days"), list):
        raise AIError("Claude ha restituito un piano in un formato inatteso.")

    # Indice delle caselle da riempire: (giorno, nome pasto normalizzato) → riga DB.
    index = {(d.day_of_week, s.name.strip().lower()): (d, m, s) for d, m, s in to_fill}
    filled = 0

    for day_data in data["days"]:
        try:
            dow = int(day_data.get("day_of_week"))
        except (TypeError, ValueError):
            continue
        for meal_data in day_data.get("meals") or []:
            slot_name = (meal_data.get("slot_name") or "").strip().lower()
            target = index.pop((dow, slot_name), None)
            if not target:
                # L'AI ha inventato un pasto che non esiste (o l'ha già riempito):
                # ignorarlo è meglio che sovrascrivere qualcosa a caso.
                logger.info("Pasto ignorato dalla risposta AI: giorno %s, slot %r", dow, slot_name)
                continue
            recipe_data = meal_data.get("recipe") or {}
            if not recipe_data.get("title"):
                continue
            _day, meal, _slot = target
            recipe = create_recipe(db, user.id, recipe_data, generation_prompt="week_plan")
            meal.recipe_id = recipe.id
            meal.source = "ai_generated"
            meal.is_followed = None
            filled += 1

    week.generation_started_at = None

    if filled == 0:
        db.commit()
        raise AIError("Il modello non ha prodotto nessuna ricetta utilizzabile. Riprova.")

    if week.status == "draft" and week.week_start_date == current_week_start():
        week.status = "active"

    db.commit()

    # La lista della spesa segue sempre il piano: ricostruirla qui evita che l'utente
    # veda una lista che non c'entra con le ricette appena generate.
    from .shopping import rebuild_shopping_list

    rebuild_shopping_list(db, user.id, week)
    db.commit()

    return {
        "filled": filled,
        "missing": len(index),
        "notes": data.get("ingredient_reuse_notes"),
    }


def _partial_ingredients(db: Session, week: WeekPlan, exclude_meal_id: int) -> list[str]:
    """Ingredienti già previsti in settimana: la nuova ricetta dovrebbe riusarli."""
    rows = (
        db.query(Ingredient.name)
        .join(RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id)
        .join(PlannedMeal, PlannedMeal.recipe_id == RecipeIngredient.recipe_id)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .filter(DayPlan.week_plan_id == week.id, PlannedMeal.id != exclude_meal_id)
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def regenerate_meal(
    db: Session, user: User, meal: PlannedMeal, *, user_request: str | None = None
) -> Recipe:
    """Rigenera la ricetta di un singolo pasto.

    La vecchia ricetta non viene cancellata: resta nel ricettario (magari era
    votata) e semplicemente non è più assegnata a questo pasto.
    """
    day = db.get(DayPlan, meal.day_plan_id)
    week = db.get(WeekPlan, day.week_plan_id)
    ensure_unlocked(week)
    ensure_not_skipped(day, meal)

    slot = db.get(MealSlot, meal.meal_slot_id)
    previous = db.get(Recipe, meal.recipe_id) if meal.recipe_id else None

    week_titles = [
        r.title
        for r in db.query(Recipe)
        .join(PlannedMeal, PlannedMeal.recipe_id == Recipe.id)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .filter(DayPlan.week_plan_id == week.id, PlannedMeal.id != meal.id)
        .all()
    ]

    prompt = prompts.render(
        prompts.SINGLE_MEAL_PROMPT,
        context=build_context(db, user.id),
        slot_name=slot.name,
        day_name=DAY_NAMES[day.day_of_week],
        target_calories=slot.target_calories,
        target_protein=f"{slot.target_protein_g:g}",
        target_carbs=f"{slot.target_carbs_g:g}",
        target_fat=f"{slot.target_fat_g:g}",
        slot_notes=slot.notes or "nessuna",
        previous_recipe=previous.title if previous else "nessuna",
        week_recipes=_fmt_list(week_titles, "nessuna"),
        partial_ingredients=_fmt_list(_partial_ingredients(db, week, meal.id), "nessuno"),
        user_request=(
            f"\nRichiesta esplicita dell'utente da rispettare: {user_request}"
            if user_request
            else ""
        ),
    )

    client = get_client(db, user, "planning")
    db.commit()  # come sopra: niente transazione aperta durante la chiamata al modello
    data = client.generate_json(
        prompts.SINGLE_MEAL_SYSTEM, prompt, max_tokens=8000, thinking=False
    )
    if not isinstance(data, dict) or not data.get("title"):
        raise AIError("Claude non ha restituito una ricetta valida.")

    recipe = create_recipe(db, user.id, data, generation_prompt=json.dumps({"slot": slot.name}))
    meal.recipe_id = recipe.id
    meal.source = "ai_generated"
    meal.is_followed = None
    db.commit()

    from .shopping import rebuild_shopping_list

    rebuild_shopping_list(db, user.id, week)
    db.commit()
    return recipe


def meal_context_for_chat(db: Session, meal: PlannedMeal) -> dict:
    """Dati del pasto usati per costruire il system prompt della chat."""
    day = db.get(DayPlan, meal.day_plan_id)
    week = db.get(WeekPlan, day.week_plan_id)
    slot = db.get(MealSlot, meal.meal_slot_id)
    recipe = db.get(Recipe, meal.recipe_id) if meal.recipe_id else None
    return {
        "day": day,
        "week": week,
        "slot": slot,
        "recipe": recipe,
        "recipe_json": (
            json.dumps(recipe_for_prompt(db, recipe), ensure_ascii=False, indent=2)
            if recipe
            else "nessuna ricetta ancora assegnata a questo pasto"
        ),
    }
