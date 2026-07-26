"""Lista della spesa: aggregazione, stima costo, completamento e blocco.

La lista non è una cosa che l'utente compila: è una funzione del piano. Ogni volta
che il piano cambia viene ricalcolata da zero, sottraendo quello che in casa c'è già
(dispensa) e quello che c'è sempre (ingredienti di base).

"Il piano", non "la settimana": la lista copre tutte le settimane generate di cui la
spesa non è ancora stata fatta, non solo quella corrente. È l'utente a decidere
quanto avanti spingersi, generando o non generando le settimane successive.
"""

from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import (
    BaseIngredient,
    DayPlan,
    Ingredient,
    PantryItem,
    PlannedMeal,
    RecipeIngredient,
    ShoppingList,
    ShoppingListItem,
    WeekPlan,
)
from ..utils.units import format_quantity, price_for, to_base

LOCK_DAYS = 7

# Ordine dei reparti nella lista: è il giro che si fa al supermercato, non l'alfabeto.
CATEGORY_ORDER = [
    "verdura",
    "frutta",
    "carne",
    "pesce",
    "latticini",
    "uova",
    "cereali",
    "legumi",
    "surgelati",
    "condimenti",
    "bevande",
    "altro",
]

CATEGORY_LABELS = {
    "verdura": "Verdura",
    "frutta": "Frutta",
    "carne": "Carne",
    "pesce": "Pesce",
    "latticini": "Latticini",
    "uova": "Uova",
    "cereali": "Pane e cereali",
    "legumi": "Legumi",
    "surgelati": "Surgelati",
    "condimenti": "Dispensa e condimenti",
    "bevande": "Bevande",
    "altro": "Altro",
}


def get_or_create_list(db: Session, week: WeekPlan) -> ShoppingList:
    lst = db.query(ShoppingList).filter(ShoppingList.week_plan_id == week.id).first()
    if not lst:
        lst = ShoppingList(week_plan_id=week.id)
        db.add(lst)
        db.flush()
    return lst


def weeks_covered(db: Session, user_id: int, week: WeekPlan) -> list[WeekPlan]:
    """Le settimane che entrano in questa lista: dalla sua in avanti, quelle non comprate.

    La spesa segue il piano, non il calendario: se è già stata generata anche la
    settimana prossima i suoi ingredienti servono davvero, e comprarli nello stesso
    giro è il motivo per cui l'app esiste (una zucchina che avanza lunedì si usa
    giovedì solo se la si compra una volta sola). Quanto avanti spingersi lo decide
    l'utente generando le settimane che vuole.

    Restano fuori le settimane già bloccate: `is_locked` significa che quella spesa è
    stata fatta, quindi quel cibo è in frigo e non nel carrello. Vale anche per la
    settimana della lista stessa — se è bloccata la sua lista è storia, non una spesa
    da rifare.

    E restano fuori le settimane senza ricette. Una settimana vuota esiste appena la
    si apre nel piano, ma non ha niente da comprare: contarla vorrebbe dire scrivere
    "spesa per due settimane" a chi ne ha generata una, e soprattutto bloccarla a
    spesa fatta — cioè impedire di generarla proprio quando ci si vuole mettere.
    """
    candidate = (
        db.query(WeekPlan)
        .filter(
            WeekPlan.user_id == user_id,
            WeekPlan.week_start_date >= week.week_start_date,
            WeekPlan.is_locked.is_(False),
        )
        .order_by(WeekPlan.week_start_date)
        .all()
    )
    if not candidate:
        return []

    with_recipes = {
        row[0]
        for row in db.query(DayPlan.week_plan_id)
        .join(PlannedMeal, PlannedMeal.day_plan_id == DayPlan.id)
        .filter(
            DayPlan.week_plan_id.in_([w.id for w in candidate]),
            PlannedMeal.recipe_id.isnot(None),
            DayPlan.is_skipped.is_(False),
            PlannedMeal.is_skipped.is_(False),
        )
        .distinct()
    }
    return [w for w in candidate if w.id in with_recipes]


def active_shopping_week(db: Session, user_id: int) -> WeekPlan:
    """La settimana da cui parte la spesa da fare.

    Di liste aperte ce n'è una sola. Una lista comprende già tutte le settimane
    generate e non ancora comprate, quindi "la spesa della settimana prossima" non è
    più una cosa a sé: o è dentro questa, o è quella che si farà dopo aver comprato
    questa. Il punto di partenza è perciò la prima settimana che ha qualcosa da
    comprare — che a spesa fatta diventa la prossima, senza che nessuno cambi scheda.

    Se non c'è più niente da comprare si torna alla settimana corrente: la sua lista è
    la spesa appena fatta, ed è quella giusta da mostrare. Una lista vuota al suo
    posto sembrerebbe un errore.
    """
    from .planner import current_week_start, get_or_create_week

    # Come ogni lettura del piano, aprire la spesa fa scattare lo slittamento dei
    # giorni passati senza spesa: la lista deve seguire le ricette dove sono finite.
    current = get_or_create_week(db, user_id, current_week_start())
    covered = weeks_covered(db, user_id, current)
    return covered[0] if covered else current


def _aggregate_ingredients(db: Session, weeks: list[WeekPlan]) -> dict[tuple[int, str], float]:
    """Somma le quantità di tutte le ricette delle settimane, per (ingrediente, unità base).

    Giorni e pasti saltati restano fuori: i primi sono passati senza che si facesse la
    spesa (comprare oggi gli ingredienti di lunedì è esattamente lo spreco da
    evitare), i secondi hanno già la loro ricetta accodata su un altro giorno, e
    contarli qui vorrebbe dire comprare due volte lo stesso piatto.
    """
    if not weeks:
        return {}

    rows = (
        db.query(RecipeIngredient)
        .join(PlannedMeal, PlannedMeal.recipe_id == RecipeIngredient.recipe_id)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .filter(
            DayPlan.week_plan_id.in_([w.id for w in weeks]),
            DayPlan.is_skipped.is_(False),
            PlannedMeal.is_skipped.is_(False),
        )
        .all()
    )

    totals: dict[tuple[int, str], float] = {}
    for ri in rows:
        quantity, unit = to_base(ri.quantity or 0, ri.unit)
        if quantity <= 0:
            continue
        key = (ri.ingredient_id, unit)
        totals[key] = totals.get(key, 0) + quantity
    return totals


def rebuild_shopping_list(db: Session, user_id: int, week: WeekPlan) -> ShoppingList:
    """Ricalcola la lista dal piano. Non tocca una lista già completata (spesa fatta)."""
    lst = get_or_create_list(db, week)
    if lst.is_completed:
        return lst

    totals = _aggregate_ingredients(db, weeks_covered(db, user_id, week))

    base_ids = {
        r[0]
        for r in db.query(BaseIngredient.ingredient_id)
        .filter(BaseIngredient.user_id == user_id)
        .all()
    }

    pantry: dict[tuple[int, str], float] = {}
    for item in db.query(PantryItem).filter(PantryItem.user_id == user_id).all():
        if item.quantity_available:
            quantity, unit = to_base(item.quantity_available, item.unit or "unità")
            pantry[(item.ingredient_id, unit)] = pantry.get((item.ingredient_id, unit), 0) + quantity

    # Le spunte già messe e le quantità prese si conservano tra un ricalcolo e l'altro:
    # rigenerare una ricetta non deve far ripartire da capo chi sta già girando per il
    # supermercato, né cancellargli il pacco da 400 g che ha appena segnato.
    previous = {
        (i.ingredient_id, i.unit): i
        for i in db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == lst.id)
    }
    checked = {key for key, i in previous.items() if i.is_checked}
    bought = {key: i.bought_quantity for key, i in previous.items() if i.bought_quantity}
    db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == lst.id).delete()

    estimated_total = 0.0
    for (ingredient_id, unit), quantity in totals.items():
        if ingredient_id in base_ids:
            continue  # sempre in casa, non si compra
        net = quantity - pantry.get((ingredient_id, unit), 0)
        if net <= 0:
            continue  # la dispensa copre tutto

        ingredient = db.get(Ingredient, ingredient_id)
        # Il costo segue quello che si porta a casa: se il pacco è più grande della
        # quantità che serve, il conto alla cassa è quello del pacco.
        taken = bought.get((ingredient_id, unit)) or round(net, 2)
        price = price_for(taken, unit, ingredient.avg_price_per_unit, ingredient.price_unit)
        if price:
            estimated_total += price

        db.add(
            ShoppingListItem(
                shopping_list_id=lst.id,
                ingredient_id=ingredient_id,
                total_quantity=round(net, 2),
                unit=unit,
                is_checked=(ingredient_id, unit) in checked,
                bought_quantity=bought.get((ingredient_id, unit)),
                estimated_price=price,
            )
        )

    lst.estimated_cost = round(estimated_total, 2) if estimated_total else None
    db.flush()
    return lst


def rebuild_lists_for(db: Session, user_id: int, week: WeekPlan) -> None:
    """Ricostruisce ogni lista aperta che comprende questa settimana.

    Da quando una lista copre più settimane, generare o cambiare una ricetta della
    prossima cambia anche la spesa di questa. Rifare solo la lista della settimana
    toccata lascerebbe l'altra ferma a prima — e al supermercato si va con quella.
    """
    from .planner import current_week_start

    anchors = (
        db.query(WeekPlan)
        .join(ShoppingList, ShoppingList.week_plan_id == WeekPlan.id)
        .filter(
            WeekPlan.user_id == user_id,
            # Una lista comincia dalla sua settimana: quelle successive non c'entrano.
            WeekPlan.week_start_date <= week.week_start_date,
            # Le liste delle settimane passate sono storia, anche se rimaste aperte.
            WeekPlan.week_start_date >= current_week_start(),
            ShoppingList.is_completed.is_(False),
        )
        .all()
    )
    for anchor in anchors:
        rebuild_shopping_list(db, user_id, anchor)


def serialize_shopping_list(db: Session, week: WeekPlan, lst: ShoppingList) -> dict:
    rows = (
        db.query(ShoppingListItem, Ingredient)
        .join(Ingredient, Ingredient.id == ShoppingListItem.ingredient_id)
        .filter(ShoppingListItem.shopping_list_id == lst.id)
        .all()
    )

    groups: dict[str, list[dict]] = {}
    summary: dict[str, float] = {}

    for item, ingredient in rows:
        category = ingredient.category or "altro"
        groups.setdefault(category, []).append(
            {
                "id": item.id,
                "ingredient_id": ingredient.id,
                "name": ingredient.name,
                "category": category,
                "quantity": item.total_quantity,
                "unit": item.unit,
                "label": format_quantity(item.total_quantity, item.unit),
                "is_checked": item.is_checked,
                # Quanto se n'è preso davvero, se diverso da quanto ne serviva: è
                # questo che finirà in dispensa.
                "bought_quantity": item.bought_quantity,
                "bought_label": (
                    format_quantity(item.bought_quantity, item.unit)
                    if item.bought_quantity
                    else None
                ),
                "estimated_price": item.estimated_price,
            }
        )
        if item.estimated_price:
            summary[category] = round(summary.get(category, 0) + item.estimated_price, 2)

    categories = [
        {
            "key": key,
            "label": CATEGORY_LABELS.get(key, key.capitalize()),
            "items": sorted(groups[key], key=lambda i: i["name"]),
            "estimated_price": summary.get(key),
        }
        for key in CATEGORY_ORDER
        if key in groups
    ]

    total_items = sum(len(c["items"]) for c in categories)
    checked_items = sum(1 for c in categories for i in c["items"] if i["is_checked"])

    # L'avviso "la lista è più corta" parla di spesa mancata, quindi conta solo i
    # giorni saltati perché ormai passati: una giornata saltata a mano più avanti
    # (weekend fuori) accorcia la lista pure lei, ma è una scelta esplicita e non ha
    # bisogno di essere spiegata come un ammanco.
    from .planner import current_week_start, today

    days = (
        db.query(DayPlan)
        .filter(DayPlan.week_plan_id == week.id)
        .order_by(DayPlan.day_of_week)
        .all()
    )
    covered = [d for d in days if not d.is_skipped]
    past_skipped = [d for d in days if d.is_skipped and d.date < today()]

    # Le settimane che la lista sta comprando. Su una lista già completata la domanda
    # non ha più senso (quelle settimane sono bloccate, cioè fuori dal calcolo): si
    # riporta la sua, che è quella a cui la spesa è intestata.
    weeks = [week] if lst.is_completed else weeks_covered(db, week.user_id, week)
    last_day = max((w.week_start_date for w in weeks), default=week.week_start_date)

    return {
        "id": lst.id,
        "week_plan_id": week.id,
        "week_start_date": week.week_start_date.isoformat(),
        "is_completed": lst.is_completed,
        "completed_at": lst.completed_at.isoformat() if lst.completed_at else None,
        "estimated_cost": lst.estimated_cost,
        "is_locked": week.is_locked,
        "days_skipped": len(past_skipped),
        "covers_from": covered[0].date.isoformat() if covered else None,
        # La spesa parte da una settimana futura: questa è già comprata. Va detto, o
        # sembra che la lista si sia dimenticata i prossimi giorni.
        "starts_ahead": week.week_start_date > current_week_start(),
        # Fin dove arriva la spesa: la domenica dell'ultima settimana coperta.
        "covers_to": (last_day + timedelta(days=6)).isoformat(),
        "weeks_covered": [
            {"id": w.id, "week_start_date": w.week_start_date.isoformat()} for w in weeks
        ],
        "total_items": total_items,
        "checked_items": checked_items,
        "categories": categories,
        "categories_summary": summary,
        # Tutti i reparti, non solo quelli con qualcosa dentro: servono a spostarci un
        # ingrediente finito nel posto sbagliato (gli spaghetti in "altro").
        "all_categories": [
            {"key": key, "label": CATEGORY_LABELS[key]} for key in CATEGORY_ORDER
        ],
    }


def shopping_list_summary(db: Session, lst: ShoppingList) -> str:
    """Gli articoli in lista come stringa piatta, per infilarli nel prompt della chat."""
    rows = (
        db.query(ShoppingListItem, Ingredient)
        .join(Ingredient, Ingredient.id == ShoppingListItem.ingredient_id)
        .filter(ShoppingListItem.shopping_list_id == lst.id)
        .all()
    )
    names = [
        f"{ing.name} ({format_quantity(item.total_quantity, item.unit)})"
        for item, ing in rows
    ]
    return ", ".join(sorted(names)) if names else "(lista vuota)"


# ── Dispensa ───────────────────────────────────────────────────────────────────
#
# Si riempie con la spesa (`complete_shopping`) e si svuota mangiando: senza la seconda
# metà, a fine settimana la dispensa direbbe che è ancora tutto in casa e la spesa
# successiva salterebbe metà carrello.


def _pantry_of(db: Session, user_id: int, ingredient_id: int) -> PantryItem | None:
    return (
        db.query(PantryItem)
        .filter(PantryItem.user_id == user_id, PantryItem.ingredient_id == ingredient_id)
        .first()
    )


def consume_from_pantry(db: Session, user_id: int, recipe_id: int | None) -> list[dict]:
    """Toglie dalla dispensa quello che la ricetta ha consumato.

    Si tocca solo quello che in dispensa c'è davvero: il sale e l'olio non ci sono
    quasi mai (sono ingredienti di base, non si comprano) e restano fuori da soli,
    senza bisogno di un elenco di eccezioni. Restano fuori anche le righe senza
    quantità — "ce l'ho ma non so quanto" — perché sottrarre da un valore ignoto
    darebbe un numero inventato, e le unità che non si parlano (una scorta contata a
    unità, una ricetta in grammi): è la stessa regola con cui la lista della spesa
    scomputa la dispensa.

    Restituisce quello che ha scalato, sia per mostrarlo (una conferma che non si vede
    non convince) sia per poterlo rimettere identico se il pasto viene corretto.
    """
    if not recipe_id:
        return []

    used: list[dict] = []
    rows = (
        db.query(RecipeIngredient, Ingredient)
        .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
        .filter(RecipeIngredient.recipe_id == recipe_id)
        .all()
    )

    for ri, ingredient in rows:
        pantry = _pantry_of(db, user_id, ingredient.id)
        if not pantry or not pantry.quantity_available:
            continue

        needed, unit = to_base(ri.quantity or 0, ri.unit)
        available, pantry_unit = to_base(pantry.quantity_available, pantry.unit or "unità")
        if needed <= 0 or unit != pantry_unit:
            continue

        # Se la scorta non basta si toglie quello che c'era, non di più: il resto
        # l'utente l'ha comprato apposta o ce l'aveva senza averlo segnato.
        taken = min(needed, available)
        remaining = available - taken
        if remaining <= 0.01:
            db.delete(pantry)
        else:
            pantry.quantity_available = round(remaining, 2)
            pantry.unit = pantry_unit

        used.append(
            {
                "ingredient_id": ingredient.id,
                "name": ingredient.name,
                "quantity": round(taken, 2),
                "unit": unit,
                "label": format_quantity(taken, unit),
            }
        )

    db.flush()
    return used


def restore_to_pantry(db: Session, user_id: int, used: list[dict]) -> None:
    """Rimette in dispensa quello che era stato tolto, non quello che la ricetta pesa.

    È la differenza fra correggere un errore e inventare del cibo: se in dispensa
    c'erano 100 g di pesce spada e la ricetta ne voleva 200, tolti ne erano 100 — e
    100 devono tornare.
    """
    for entry in used or []:
        ingredient_id = entry.get("ingredient_id")
        quantity, unit = to_base(entry.get("quantity") or 0, entry.get("unit") or "unità")
        if not ingredient_id or quantity <= 0:
            continue

        pantry = _pantry_of(db, user_id, ingredient_id)
        if not pantry:
            db.add(
                PantryItem(
                    user_id=user_id,
                    ingredient_id=ingredient_id,
                    quantity_available=round(quantity, 2),
                    unit=unit,
                )
            )
            continue

        available, pantry_unit = to_base(pantry.quantity_available or 0, pantry.unit or unit)
        if pantry.quantity_available and pantry_unit != unit:
            continue  # unità incompatibili: meglio non toccare niente
        pantry.quantity_available = round(available + quantity, 2)
        pantry.unit = unit
    db.flush()


def lock_bought_week(week: WeekPlan, now: datetime) -> None:
    """Blocca una settimana perché il suo cibo è stato comprato.

    Il blocco dura sette giorni, ma per una settimana futura partono dal suo lunedì:
    contati da oggi scadrebbero prima ancora che la settimana cominci, e il piano
    tornerebbe modificabile con gli ingredienti già in frigo.
    """
    start = datetime.combine(week.week_start_date, time.min, tzinfo=timezone.utc)
    week.is_locked = True
    week.locked_at = now
    week.lock_expires_at = max(now, start) + timedelta(days=LOCK_DAYS)
    week.status = "locked"


def complete_shopping(db: Session, user_id: int, week: WeekPlan, lst: ShoppingList) -> dict:
    """Segna la spesa come fatta: blocca il piano e riempie la dispensa.

    Il blocco è il punto del progetto: una volta comprato il cibo, cambiare le
    ricette significa buttarlo. Si bloccano **tutte** le settimane che la lista
    copriva, non solo la prima: se la spesa comprendeva anche la prossima, anche
    quelle ricette adesso sono pagate.
    """
    if lst.is_completed:
        raise HTTPException(409, "Questa spesa risulta già completata.")

    now = datetime.now(timezone.utc)
    covered = weeks_covered(db, user_id, week) or [week]

    lst.is_completed = True
    lst.completed_at = now

    for covered_week in covered:
        lock_bought_week(covered_week, now)

    # Quello che è stato spuntato è finito nel carrello, quindi ora è in dispensa —
    # nella quantità che si è presa davvero, non in quella che serviva: è la
    # differenza fra una dispensa che descrive il frigo e una che descrive il piano.
    for item in db.query(ShoppingListItem).filter(
        ShoppingListItem.shopping_list_id == lst.id, ShoppingListItem.is_checked.is_(True)
    ):
        taken = item.bought_quantity or item.total_quantity
        pantry = (
            db.query(PantryItem)
            .filter(PantryItem.user_id == user_id, PantryItem.ingredient_id == item.ingredient_id)
            .first()
        )
        if pantry and pantry.unit == item.unit and pantry.quantity_available:
            pantry.quantity_available += taken
        elif pantry:
            pantry.quantity_available = taken
            pantry.unit = item.unit
        else:
            db.add(
                PantryItem(
                    user_id=user_id,
                    ingredient_id=item.ingredient_id,
                    quantity_available=taken,
                    unit=item.unit,
                )
            )

    db.commit()

    # Il blocco più lontano: è fin lì che il piano comprato è intoccabile.
    until = max(w.lock_expires_at for w in covered)
    return {
        "detail": (
            "Spesa completata: il piano è bloccato per 7 giorni."
            if len(covered) == 1
            else f"Spesa completata: bloccate {len(covered)} settimane di piano."
        ),
        "weeks_locked": len(covered),
        "week_locked_until": until.isoformat(),
    }


def export_text(db: Session, week: WeekPlan, lst: ShoppingList) -> str:
    """Lista in testo semplice, da incollare in un messaggio o in una nota."""
    data = serialize_shopping_list(db, week, lst)
    if len(data["weeks_covered"]) > 1:
        testata = (
            f"Lista della spesa — dal {week.week_start_date.strftime('%d/%m/%Y')} "
            f"al {date.fromisoformat(data['covers_to']).strftime('%d/%m/%Y')}"
        )
    else:
        testata = f"Lista della spesa — settimana del {week.week_start_date.strftime('%d/%m/%Y')}"
    lines = [testata, ""]

    for category in data["categories"]:
        lines.append(f"{category['label'].upper()}")
        for item in category["items"]:
            mark = "x" if item["is_checked"] else " "
            lines.append(f"  [{mark}] {item['name']} — {item['label']}")
        lines.append("")

    if data["estimated_cost"]:
        lines.append(f"Totale stimato: € {data['estimated_cost']:.2f}".replace(".", ","))
    return "\n".join(lines)
