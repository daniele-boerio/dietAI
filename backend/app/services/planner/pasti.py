"""Le caselle: pasti fissi e ricorrenti, il cestino, «ho mangiato altro» e i giorni saltati."""

import logging
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...models import (
    DayPlan,
    MealSlot,
    PlannedMeal,
    Recipe,
    WeekPlan,
)
from .settimane import DAY_NAMES, get_active_diet, get_or_create_week, week_meals
from .. import planner  # per i nomi che i test sostituiscono: vedi __init__

logger = logging.getLogger(__name__)


def ensure_not_skipped(day: DayPlan, meal: PlannedMeal | None = None) -> None:
    if meal is not None and meal.is_skipped:
        raise HTTPException(
            409,
            "Questo pasto è saltato: la sua ricetta si è accodata più avanti. "
            "Segnalo come seguito per riportarlo qui.",
        )
    if day.is_skipped:
        raise HTTPException(
            409,
            "Questa giornata è saltata: le sue ricette si sono accodate più avanti. "
            "Rimettila in programma per tornare a modificarla.",
        )


# ── Pasti fissi ────────────────────────────────────────────────────────────────


def _is_fixed(meal: PlannedMeal, slot: MealSlot) -> bool:
    """Un pasto fissato non viene toccato né dalla generazione né dagli spostamenti.

    Tre modi per esserlo: è ricorrente, l'utente gli ha assegnato una ricetta a mano,
    oppure il pasto è marcato nella dieta come "lo gestisco io" (`auto_generate` a
    False) — la colazione di sempre, che non ha senso far reinventare ogni settimana.
    """
    return meal.is_recurring or meal.source == "user_custom" or not slot.auto_generate


def is_generable(day: DayPlan, meal: PlannedMeal, slot: MealSlot) -> bool:
    """Questa casella la può riempire una generazione? La regola, in un posto solo.

    Era scritta tre volte — qui in `generate_week`, in `lib/generation.js` e nel conto
    della home — e il numero sul pulsante («Genera 9 pasti») è una promessa su quanto
    si sta per pagare: la prossima condizione andava aggiunta in tre posti, uno dei
    quali lavorava su dict serializzati. Ora la calcola solo il server, e
    `serialize_meal` la espone come `generable`.
    """
    return not day.is_skipped and not meal.is_skipped and not _is_fixed(meal, slot)


# ── Pasti ricorrenti ───────────────────────────────────────────────────────────


def apply_recurring_meals(db: Session, user_id: int, week: WeekPlan) -> int:
    """Pre-assegna alla settimana i pasti marcati come ricorrenti nella precedente.

    La ricetta è la stessa riga, non una copia: la colazione di sempre è **un** piatto,
    e farne una copia a settimana (per giorno, con la regola "daily") era il modo più
    veloce di riempire il ricettario di doppioni. La garanzia che c'era prima non si
    perde: modificare la colazione di questa settimana non riscrive quella archiviata,
    perché chi modifica da dentro un pasto passa da `fork_recipe_for_meal`, che la
    copia stacca lì — quando serve davvero.
    """
    previous = (
        db.query(WeekPlan)
        .filter(
            WeekPlan.user_id == user_id, WeekPlan.week_start_date < week.week_start_date
        )
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

    days = {
        d.day_of_week: d
        for d in db.query(DayPlan).filter(DayPlan.week_plan_id == week.id)
    }
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
            target.recipe_id = recipe.id
            target.source = meal.source
            target.is_recurring = True
            target.recurring_rule = rule
            applied += 1

    db.flush()
    return applied


def clear_meal_cell(db: Session, meal: PlannedMeal) -> None:
    """Riporta la casella a com'era prima che ci finisse dentro qualcosa.

    Non è `_empty_meal`, che serve a un'altra cosa — lì la ricetta se n'è andata da
    un'altra parte, qui non c'è più — e infatti spegne anche il pasto fisso: una
    casella vuota che si ripete ogni settimana non vuol dire niente. La ricetta resta
    nel ricettario: quello che si svuota è il posto, non il piatto.

    Se il pasto è rimandato (is_skipped), svuota anche la casella dove era stata
    accodata la ricetta, altrimenti rimane orfana.
    """
    # Se il pasto è rimandato, svuota anche la casella dove era stata accodata la ricetta
    if meal.is_skipped and meal.skipped_to_meal_id:
        accodata = db.get(PlannedMeal, meal.skipped_to_meal_id)
        if accodata is not None and accodata.recipe_id and not accodata.is_skipped:
            _empty_meal(db, accodata)

    meal.recipe_id = None
    meal.source = "ai_generated"
    meal.is_recurring = False
    meal.recurring_rule = None
    meal.is_followed = None
    meal.is_skipped = False
    meal.deviation_notes = None
    meal.eaten_nutrition = None
    meal.pantry_used = None
    meal.skipped_to_meal_id = None
    forget_queued_meal(db, meal)


def stop_recurring_forward(
    db: Session, user_id: int, meal: PlannedMeal, day: DayPlan
) -> int:
    """Togliendo il «fisso», leva quel piatto anche dalle caselle che l'hanno ricevuto.

    Un pasto fisso si ricopia da sé sulle settimane che si aprono — e una settimana si
    apre anche solo sfogliandola — quindi quando si toglie la spunta quelle copie sono
    già scritte in giro: spegnere l'interruttore e trovare la luce accesa lo stesso è
    il motivo per cui la spunta sembrava non funzionare. Si tolgono le caselle che
    hanno **quella** ricetta su **quel** pasto e il segno di fisso addosso: una
    colazione uguale scelta a mano un altro giorno non è una copia, e resta dov'è.

    Due limiti, per non cancellare fatti invece di previsioni. Solo **dopo** questa
    casella e mai prima di oggi: quello che è già stato è storia, anche se lo si
    scopre sfogliando all'indietro. E mai una casella dove l'utente ha già segnato
    com'è andata — seguita o rimandata: lì la ricetta non è un programma, è il
    racconto di una giornata.

    Le altre — quelle che restano, perché vengono prima o perché sono già state
    vissute — perdono comunque il **segno** di fisso, che è la parte che si propaga:
    `apply_recurring_meals` legge la settimana precedente, quindi con la regola
    "daily" bastava una casella accesa il lunedì per far ricomparire tutto la
    settimana dopo, e togliere la spunta dal mercoledì sarebbe sembrato non aver
    fatto niente. La ricetta lì non si tocca: è già in programma, ed è un piatto che
    l'utente ha davanti.
    """
    if not meal.recipe_id:
        return 0

    caselle = (
        db.query(PlannedMeal, DayPlan)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .filter(
            WeekPlan.user_id == user_id,
            DayPlan.date >= planner.today(),
            PlannedMeal.id != meal.id,
            PlannedMeal.meal_slot_id == meal.meal_slot_id,
            PlannedMeal.recipe_id == meal.recipe_id,
            PlannedMeal.is_recurring.is_(True),
        )
        .all()
    )

    tolte = 0
    for casella, giorno in caselle:
        vissuta = casella.is_followed is not None or casella.is_skipped
        if giorno.date <= day.date or vissuta:
            casella.is_recurring = False
            casella.recurring_rule = None
            continue
        clear_meal_cell(db, casella)
        tolte += 1

    db.flush()
    return tolte


def spread_recurring(db: Session, user_id: int, meal: PlannedMeal, day: DayPlan) -> int:
    """Mettendo il «fisso», il piatto va subito nelle caselle che la regola copre.

    Prima la spunta si limitava a segnare la casella, e `apply_recurring_meals` la
    ricopiava solo sulle settimane create **dopo**: il resto di questa settimana e
    quelle già aperte restavano come prima, e il pulsante sembrava non fare niente —
    «la colazione è sempre questa» lasciava sei colazioni diverse.

    Si riempiono le caselle dello stesso pasto, dopo questa e mai prima di oggi, nei
    giorni della regola (tutti, o quel giorno della settimana), anche se avevano già un
    piatto: fissare vuol dire proprio sostituirlo. Restano fuori quelle già vissute
    (seguite o rimandate), i giorni saltati e la casella dove è accodato un piatto
    rimandato: sono fatti o scelte dell'utente, non programma.
    """
    if not meal.recipe_id:
        return 0
    rule = meal.recurring_rule or {"type": "weekly", "day": day.day_of_week}

    caselle = (
        db.query(PlannedMeal, DayPlan)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .filter(
            WeekPlan.user_id == user_id,
            DayPlan.date > day.date,
            DayPlan.date >= planner.today(),
            DayPlan.is_skipped.is_(False),
            PlannedMeal.id != meal.id,
            PlannedMeal.meal_slot_id == meal.meal_slot_id,
            PlannedMeal.is_skipped.is_(False),
            PlannedMeal.is_followed.is_(None),
        )
        .all()
    )
    accodate = {
        target
        for (target,) in db.query(PlannedMeal.skipped_to_meal_id).filter(
            PlannedMeal.skipped_to_meal_id.in_([c.id for c, _ in caselle] or [0])
        )
    }

    messe = 0
    for casella, giorno in caselle:
        if rule.get("type") != "daily" and giorno.day_of_week != rule.get("day"):
            continue
        if casella.id in accodate:
            continue
        if casella.recipe_id != meal.recipe_id:
            forget_tracking(casella)
        casella.recipe_id = meal.recipe_id
        casella.source = meal.source
        casella.is_recurring = True
        casella.recurring_rule = rule
        messe += 1

    db.flush()
    return messe


# ── Pasti saltati ──────────────────────────────────────────────────────────────


def forget_tracking(meal: PlannedMeal) -> None:
    """Il pasto torna «non ancora tracciato»: nella casella c'è un altro piatto.

    Il segno, la nota, la stima di «cosa ho mangiato» e la memoria di cosa era uscito
    dalla dispensa vanno via insieme, perché descrivevano il piatto di prima. Prima ogni
    rotta azzerava il suo pezzo — assegnare una ricetta toglieva il segno ma lasciava la
    stima, generare lasciava `pantry_used` — e i vincoli della migrazione 0035
    (`ck_planned_meal_*`) adesso lo impediscono. Quello che era stato scalato resta
    scalato: mangiato è mangiato.
    """
    meal.is_followed = None
    meal.deviation_notes = None
    meal.eaten_nutrition = None
    meal.pantry_used = None


def forget_queued_meal(db: Session, meal: PlannedMeal) -> None:
    """Questa casella non è più «il piatto che avevo rimandato».

    Da chiamare quando ci si mette dentro qualcos'altro di proposito — rigenerata,
    riassegnata, svuotata: da lì in poi annullare il salto non deve più portarsela via,
    perché quello che c'è ora l'ha scelto l'utente.
    """
    db.query(PlannedMeal).filter(PlannedMeal.skipped_to_meal_id == meal.id).update(
        {"skipped_to_meal_id": None}
    )


def _empty_meal(db: Session, meal: PlannedMeal) -> None:
    """Svuota una casella: la ricetta se n'è andata da un'altra parte."""
    meal.recipe_id = None
    meal.source = "ai_generated"
    forget_tracking(meal)
    meal.skipped_to_meal_id = None
    forget_queued_meal(db, meal)


def _overflow_week(db: Session, user_id: int, week: WeekPlan) -> WeekPlan | None:
    """La settimana dopo, dove finisce quello che in questa non entra più."""
    if not get_active_diet(db, user_id):
        return None
    return get_or_create_week(db, user_id, week.week_start_date + timedelta(days=7))


def _free_cells(
    db: Session, user_id: int, week: WeekPlan, slot_id: int
) -> list[PlannedMeal]:
    """Le caselle libere di quello slot da oggi in avanti, in ordine di giorno.

    Prima quelle rimaste vuote in questa settimana, poi quelle della prossima: è la
    coda su cui si accoda un piatto saltato.
    """
    now = planner.today()
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


def skip_meal(
    db: Session, user_id: int, meal: PlannedMeal, day: DayPlan, week: WeekPlan
) -> dict:
    """ "Ho mangiato altro": il piatto non è stato cucinato, la ricetta va in fondo.

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
    forget_tracking(target)
    # Dove è finito il piatto, scritto invece che indovinato: annullare il salto deve
    # svuotare **questa** casella, non un'altra che per caso ha lo stesso piatto — e da
    # quando lo stesso piatto in due giorni è una riga di ricetta sola, "stessa ricetta"
    # non è più un indirizzo.
    meal.skipped_to_meal_id = target.id
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


def unskip_meal(db: Session, meal: PlannedMeal) -> None:
    """Annulla il salto: la ricetta torna qui e la casella dove si era accodata si svuota.

    Quale casella lo dice `skipped_to_meal_id`, scritto da `skip_meal`. Prima lo si
    cercava per somiglianza — stesso pasto, stessa `recipe_id` — e finché ogni casella
    aveva la sua riga di ricetta era un indirizzo univoco; ora che lo stesso piatto in
    due giorni è **una** riga, quella ricerca svuoterebbe la prima colazione uguale che
    incontra.
    """
    if not meal.is_skipped:
        return

    meal.is_skipped = False
    accodata = (
        db.get(PlannedMeal, meal.skipped_to_meal_id)
        if meal.skipped_to_meal_id
        else None
    )
    meal.skipped_to_meal_id = None

    # Basta che là ci sia ancora qualcosa: il puntatore è l'indirizzo, e vale finché
    # nessuno ci ha messo dentro altro di proposito — chi rigenera, riassegna o svuota
    # quella casella lo cancella (`forget_queued_meal`). Non si confrontano le ricette,
    # perché nel frattempo il piatto rimandato può essere stato modificato in chat, e
    # quella modifica gliene ha staccata una copia sua.
    if accodata is not None and accodata.recipe_id and not accodata.is_skipped:
        _empty_meal(db, accodata)

    db.flush()


def skip_day(
    db: Session, user_id: int, day: DayPlan, week: WeekPlan, skipped: bool
) -> None:
    """Salta (o rimette) l'intera giornata: vale per tutti i suoi pasti insieme.

    Serve per il weekend fuori, e vale da oggi in avanti: una giornata già passata la
    si racconta pasto per pasto ("l'ho seguito" / "ho mangiato altro"), che è la
    stessa cosa ma detta bene.
    """
    if day.date < planner.today():
        raise HTTPException(409, "Un giorno già passato non si salta a mano.")

    day.is_skipped = skipped
    meals = db.query(PlannedMeal).filter(PlannedMeal.day_plan_id == day.id).all()
    for meal in meals:
        if skipped:
            skip_meal(db, user_id, meal, day, week)
        else:
            unskip_meal(db, meal)
    db.flush()
