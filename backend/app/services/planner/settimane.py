"""Settimane: «oggi», la dieta attiva, la struttura delle caselle e il riallineamento a una dieta nuova."""

import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...models import (
    DayPlan,
    DietPlan,
    MealSlot,
    PlannedMeal,
    WeekPlan,
)
from ...utils import clock
from .. import planner  # per i nomi che i test sostituiscono: vedi __init__

logger = logging.getLogger(__name__)


DAY_NAMES = [
    "Lunedì",
    "Martedì",
    "Mercoledì",
    "Giovedì",
    "Venerdì",
    "Sabato",
    "Domenica",
]


# ── Settimane ──────────────────────────────────────────────────────────────────


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def today() -> date:
    """Il punto unico da cui l'app legge la data di oggi.

    Esiste perché parecchie regole dipendono da che giorno è — la lista della spesa
    guarda da oggi in avanti, un pasto saltato si accoda a un giorno futuro — e i test
    devono poterlo spostare, altrimenti la stessa suite darebbe risultati diversi il
    lunedì e il venerdì.

    È la data italiana (`utils.clock`): il container gira in UTC, e fra mezzanotte e
    le due la spesa e la settimana credevano che fosse ancora ieri.
    """
    return clock.local_today()


def current_week_start() -> date:
    return monday_of(planner.today())


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
    """Rimette a posto lo stato delle settimane: passate in archivio, questa attiva.

    Viene chiamato all'inizio di ogni lettura del piano, così lo stato è sempre
    coerente senza bisogno di uno scheduler. Archiviata non vuol dire intoccabile: una
    settimana passata si può ancora aprire e correggere, serve solo a distinguerla da
    quella in corso.
    """
    this_monday = current_week_start()
    changed = False

    for week in db.query(WeekPlan).filter(WeekPlan.user_id == user_id).all():
        if week.week_start_date < this_monday:
            target = "archived"
        elif week.week_start_date == this_monday:
            target = "active"
        else:
            continue
        if week.status != target:
            week.status = target
            changed = True

    if changed:
        db.commit()


def _slot_key(name: str | None) -> str:
    """Il nome di un pasto ridotto a chiave: due diete diverse scrivono «Pranzo» uguale."""
    return " ".join((name or "").split()).casefold()


def _casella_vissuta(meal: PlannedMeal) -> bool:
    """C'è qualcosa dentro questa casella, o è solo il buco che nasce con la settimana?"""
    return bool(
        meal.recipe_id
        or meal.is_followed is not None
        or meal.is_skipped
        or meal.is_recurring
        or meal.deviation_notes
    )


def realign_to_diet(db: Session, days: list[DayPlan], slots: list[MealSlot]) -> None:
    """Riporta le caselle già in griglia sui pasti della dieta **attiva**.

    Cambiare dieta — ricalcolare i macro dal questionario, caricare un altro PDF —
    non modifica i `MealSlot` esistenti: ne crea di nuovi, e i vecchi restano attaccati
    alla dieta archiviata. Le caselle della settimana però puntano ancora a quelli, e
    `ensure_week_structure` qui sotto aggiunge per ogni giorno una casella vuota per
    ogni pasto nuovo: senza questo passaggio la griglia finisce con due colazioni, due
    pranzi e due cene — quelle di prima, piene, e quelle della dieta nuova, vuote.

    Il pasto si sposta sul suo omonimo della dieta attiva invece di essere buttato via:
    la ricetta che c'è dentro è costata una chiamata al modello, e quello che l'utente
    ha già segnato («l'ho seguito», la dispensa scalata) è storia sua. Cambiano solo i
    target, che sono quelli della dieta nuova. Sparisce soltanto ciò che nella dieta
    nuova non ha più un posto dove stare: un pasto che non si fa più non può restare in
    griglia, o continuerebbe a pesare su spesa, totali del giorno e aderenza.
    """
    if not days:
        return

    slot_ids = {s.id for s in slots}
    meals = (
        db.query(PlannedMeal)
        .filter(PlannedMeal.day_plan_id.in_([d.id for d in days]))
        .all()
    )
    orfane = [m for m in meals if m.meal_slot_id not in slot_ids]
    if not orfane:
        return

    # Il primo pasto vince, se la dieta ha due pasti con lo stesso nome: sono due
    # caselle diverse, ma una delle due deve pur essere quella dove atterrare.
    per_nome: dict[str, MealSlot] = {}
    for slot in slots:
        per_nome.setdefault(_slot_key(slot.name), slot)

    nomi_vecchi = {
        s.id: _slot_key(s.name)
        for s in db.query(MealSlot)
        .filter(MealSlot.id.in_({m.meal_slot_id for m in orfane}))
        .all()
    }
    occupanti = {
        (m.day_plan_id, m.meal_slot_id): m for m in meals if m.meal_slot_id in slot_ids
    }

    da_rimuovere: list[PlannedMeal] = []
    da_spostare: list[tuple[PlannedMeal, int]] = []
    spostate: set[int] = set()

    for orfana in orfane:
        destinazione = per_nome.get(nomi_vecchi.get(orfana.meal_slot_id, ""))
        if destinazione is None:
            da_rimuovere.append(orfana)
            continue

        occupante = occupanti.get((orfana.day_plan_id, destinazione.id))
        if occupante is not None:
            # La casella nuova esiste già: sopravvive quella che ha qualcosa da dire —
            # e chi ci è appena atterrato non lo si sfratta, o si finirebbe per
            # cancellare una riga che nello stesso giro è già stata spostata.
            if (
                occupante.id in spostate
                or _casella_vissuta(occupante)
                or not _casella_vissuta(orfana)
            ):
                da_rimuovere.append(orfana)
                continue
            da_rimuovere.append(occupante)

        da_spostare.append((orfana, destinazione.id))
        spostate.add(orfana.id)
        occupanti[(orfana.day_plan_id, destinazione.id)] = orfana

    # Prima si cancella e si scarica, poi si sposta: `uq_planned_meal` vieta due caselle
    # sullo stesso (giorno, pasto), e la UPDATE arriverebbe prima della DELETE.
    for meal in da_rimuovere:
        db.delete(meal)
    db.flush()

    for meal, slot_id in da_spostare:
        meal.meal_slot_id = slot_id
    db.flush()

    logger.info(
        "Settimana riallineata alla dieta attiva: %s caselle spostate, %s rimosse",
        len(da_spostare),
        len(da_rimuovere),
    )


def ensure_week_structure(db: Session, week: WeekPlan, slots: list[MealSlot]) -> None:
    """Crea i giorni e le caselle mancanti.

    Serve anche dopo una modifica della dieta (pasti aggiunti o rinominati): le
    settimane già create devono adeguarsi senza essere buttate via. Se la dieta è stata
    proprio sostituita, prima si riportano le caselle esistenti sui pasti di quella
    attiva (`realign_to_diet`), altrimenti alle vecchie si sommerebbero le nuove.
    """
    days = {
        d.day_of_week: d
        for d in db.query(DayPlan).filter(DayPlan.week_plan_id == week.id)
    }

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

    realign_to_diet(db, list(days.values()), slots)

    slot_ids = {s.id for s in slots}
    for day in days.values():
        existing = {
            m.meal_slot_id
            for m in db.query(PlannedMeal).filter(PlannedMeal.day_plan_id == day.id)
        }
        for slot_id in slot_ids - existing:
            db.add(
                PlannedMeal(
                    day_plan_id=day.id, meal_slot_id=slot_id, source="ai_generated"
                )
            )
    db.flush()


def _week_with_structure(
    db: Session, user_id: int, week_start: date, slots: list[MealSlot]
) -> tuple[WeekPlan, bool]:
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
    planner.ensure_week_structure(db, week, slots)
    return week, created


def get_or_create_week(db: Session, user_id: int, week_start: date) -> WeekPlan:
    diet = require_active_diet(db, user_id)
    slots = meal_slots_of(db, diet.id)
    if not slots:
        raise HTTPException(400, "La dieta attiva non ha pasti configurati.")

    # Due richieste che aprono insieme una settimana nuova (il lunedì mattina, la
    # dashboard e la spesa in parallelo) la creavano tutte e due, e la seconda finiva
    # in un 500 su `uq_week_plan_user_week` o `uq_planned_meal`. Il vincolo resta
    # l'arbitro: chi perde annulla solo il suo tentativo (SAVEPOINT, non tutta la
    # transazione del chiamante) e rilegge quello che ha scritto l'altra.
    for tentativo in range(2):
        try:
            with db.begin_nested():
                week, created = _week_with_structure(db, user_id, week_start, slots)
            break
        except IntegrityError:
            if tentativo:
                raise
            logger.info("Settimana %s creata in parallelo: rileggo", week_start)

    if created:
        # Import qui: `pasti` dipende da `settimane`, e a livello di modulo
        # sarebbe un ciclo.
        from .pasti import apply_recurring_meals

        apply_recurring_meals(db, user_id, week)
    db.commit()
    return week


# Oltre questo tempo una generazione si considera morta (processo riavviato, container
# ricreato): senza, una settimana resterebbe "in generazione" per sempre.


def week_meals(
    db: Session, week: WeekPlan
) -> list[tuple[DayPlan, PlannedMeal, MealSlot]]:
    return (
        db.query(DayPlan, PlannedMeal, MealSlot)
        .join(PlannedMeal, PlannedMeal.day_plan_id == DayPlan.id)
        .join(MealSlot, MealSlot.id == PlannedMeal.meal_slot_id)
        .filter(DayPlan.week_plan_id == week.id)
        .order_by(DayPlan.day_of_week, MealSlot.order_index)
        .all()
    )
