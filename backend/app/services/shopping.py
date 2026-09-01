"""Lista della spesa: aggregazione, stima costo, spesa fatta.

La lista non è una cosa che l'utente compila e non è nemmeno una cosa che si chiude:
è una funzione del piano, e dice sempre la stessa cosa — **quello che le ricette da
oggi a domenica otto chiedono e che in dispensa non c'è**. Ogni volta che il piano
cambia viene ricalcolata da zero, sottraendo quello che in casa c'è già (dispensa) e
quello che c'è sempre (ingredienti di base).

Da lì viene tutto il resto, senza regole aggiuntive: "ho fatto la spesa" sposta gli
articoli spuntati in dispensa, e la lista si svuota da sé perché adesso la dispensa
copre il piano. Una ricetta nuova aggiunge quello che le serve, perché in dispensa
non c'è. Cambiare una ricetta già comprata non toglie niente dalla dispensa: quello
che è in casa resta in casa, ed è l'utente a correggere la scorta se serve.

Restano fuori dalla lista i giorni già passati (non si compra per ieri), quelli oltre
domenica otto (si comprano quando arrivano) e i pasti già segnati come seguiti: sono
stati cucinati, quindi comprarli di nuovo sarebbe comprare due volte la stessa cena.
"""

from datetime import date, datetime, timedelta, timezone

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
    """La lista, che vive sulla settimana corrente e non si chiude mai.

    L'aggancio a una settimana è solo il posto dove la riga sta di casa: quello che la
    lista contiene lo decidono le ricette da oggi in avanti, non quella settimana.
    """
    lst = db.query(ShoppingList).filter(ShoppingList.week_plan_id == week.id).first()
    if not lst:
        lst = ShoppingList(week_plan_id=week.id)
        db.add(lst)
        db.flush()
    return lst


def current_list(db: Session, user_id: int) -> tuple[WeekPlan, ShoppingList]:
    """La lista di adesso: una sola, sulla settimana corrente."""
    from .planner import current_week_start, get_or_create_week

    week = get_or_create_week(db, user_id, current_week_start())
    return week, get_or_create_list(db, week)


# Fin dove guarda la spesa: questa settimana e la prossima, cioè fino a domenica otto.
# Due e non una, perché il senso di tutto è la confezione sola invece di due mezze e il
# lunedì non è un muro. Due e non "tutte", perché più avanti il piano non è una
# previsione ma un'ipotesi: le settimane future nascono appena le sfogli e ci si
# ricopiano dentro i pasti fissi da sole (`apply_recurring_meals`), quindi senza tetto
# bastava guardare avanti nel calendario per far crescere la lista all'infinito — e a
# quel punto non diceva più cosa comprare oggi.
SHOPPING_HORIZON_WEEKS = 2


def shopping_horizon() -> date:
    """L'ultimo giorno che la spesa comprende: la domenica della settimana prossima."""
    from .planner import current_week_start

    return current_week_start() + timedelta(days=7 * SHOPPING_HORIZON_WEEKS - 1)


def meals_to_buy(db: Session, user_id: int) -> list[tuple[DayPlan, PlannedMeal]]:
    """I pasti per cui si compra: da oggi a domenica otto, non saltati, non già mangiati.

    Restano fuori quattro cose, tutte per lo stesso motivo — non comprare quello che
    non servirà, o che è già servito:

    · i giorni già passati, perché per ieri non si cucina più;
    · quelli oltre l'orizzonte (`shopping_horizon`), che si compreranno a tempo debito;
    · i giorni e i pasti saltati — un pasto saltato ha già la sua ricetta accodata su
      un'altra casella, e comprarlo qui vorrebbe dire comprarlo due volte;
    · i pasti segnati come seguiti: quel piatto è stato cucinato, con quello che c'era
      in casa. Senza questo la lista continuerebbe a chiedere la colazione di stamattina.
    """
    from .planner import today

    return (
        db.query(DayPlan, PlannedMeal)
        .join(PlannedMeal, PlannedMeal.day_plan_id == DayPlan.id)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .filter(
            WeekPlan.user_id == user_id,
            DayPlan.date >= today(),
            DayPlan.date <= shopping_horizon(),
            DayPlan.is_skipped.is_(False),
            PlannedMeal.is_skipped.is_(False),
            PlannedMeal.recipe_id.isnot(None),
            PlannedMeal.is_followed.isnot(True),
        )
        .order_by(DayPlan.date)
        .all()
    )


def meals_beyond_horizon(db: Session, user_id: int) -> int:
    """Quanti pasti con una ricetta restano fuori dall'orizzonte.

    Serve solo a dirlo: chi ha pianificato tre settimane e vede in lista gli ingredienti
    di due deve capire che non manca niente, e che quella roba arriverà quando è ora.
    """
    return (
        db.query(PlannedMeal)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .filter(
            WeekPlan.user_id == user_id,
            DayPlan.date > shopping_horizon(),
            DayPlan.is_skipped.is_(False),
            PlannedMeal.is_skipped.is_(False),
            PlannedMeal.recipe_id.isnot(None),
        )
        .count()
    )


def _aggregate_ingredients(db: Session, user_id: int) -> dict[tuple[int, str], float]:
    """Somma le quantità di tutte le ricette da comprare, per (ingrediente, unità base)."""
    recipe_ids = [meal.recipe_id for _, meal in meals_to_buy(db, user_id)]
    if not recipe_ids:
        return {}

    totals: dict[tuple[int, str], float] = {}
    # Una ricetta può stare in due caselle (un piatto ripetuto): si conta ogni volta,
    # perché ogni volta la si cucina.
    per_recipe: dict[int, list[RecipeIngredient]] = {}
    for ri in (
        db.query(RecipeIngredient)
        .filter(RecipeIngredient.recipe_id.in_(set(recipe_ids)))
        .all()
    ):
        per_recipe.setdefault(ri.recipe_id, []).append(ri)

    for recipe_id in recipe_ids:
        for ri in per_recipe.get(recipe_id, []):
            quantity, unit = to_base(ri.quantity or 0, ri.unit)
            if quantity <= 0:
                continue
            key = (ri.ingredient_id, unit)
            totals[key] = totals.get(key, 0) + quantity
    return totals


def rebuild_shopping_list(db: Session, user_id: int) -> ShoppingList:
    """Ricalcola la lista dal piano: quello che serve da oggi, meno quello che c'è già."""
    _, lst = current_list(db, user_id)

    totals = _aggregate_ingredients(db, user_id)

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
    # E il prezzo scritto a mano è la cosa che meno di tutte si può rifare da soli:
    # è una cifra letta su uno scaffale.
    paid = {key: i.paid_price for key, i in previous.items() if i.paid_price is not None}
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
        # quantità che serve, il conto alla cassa è quello del pacco. A meno che il
        # prezzo l'utente non l'abbia scritto: quello vale com'è, anche se intanto la
        # quantità in lista è cambiata perché il piano è cambiato.
        pagato = paid.get((ingredient_id, unit))
        taken = bought.get((ingredient_id, unit)) or round(net, 2)
        price = (
            pagato
            if pagato is not None
            else price_for(taken, unit, ingredient.avg_price_per_unit, ingredient.price_unit)
        )
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
                paid_price=pagato,
                estimated_price=price,
            )
        )

    lst.estimated_cost = round(estimated_total, 2) if estimated_total else None
    db.flush()
    return lst


def _pantry_note(scorta: PantryItem | None, item: ShoppingListItem) -> dict | None:
    """Perché questo articolo è in lista pur essendoci qualcosa in dispensa.

    Una voce in lista ha per definizione `net > 0`, cioè la scorta compatibile è già
    stata scalata tutta: la quantità che si legge è quello che *manca*. Detto questo,
    restano due casi che senza una riga di spiegazione sembrano un errore dell'app:

    · l'unità è la stessa e la scorta non bastava (`usable`) — non c'è niente da
      riparare, ma sapere che la dispensa è stata contata toglie il dubbio che l'app
      se ne sia dimenticata;
    · l'unità non è la stessa, e allora non si è potuto scalare **niente**: 30 ml di
      limone contro una ricetta che li conta a unità. È l'unico caso in cui la lista
      chiede davvero una cosa che in casa c'è, ed è quasi sempre correggibile in dieci
      secondi cambiando l'unità della scorta — ma solo se lo si vede.

    La nota si calcola alla lettura, come il reparto: è un dato derivato, e tenerlo in
    una colonna di `ShoppingListItem` vorrebbe dire una migrazione e un valore da
    riallineare a mano ogni volta che la dispensa cambia — cioè un modo per farlo
    mentire.
    """
    if not scorta or not scorta.quantity_available:
        return None

    quanto, unita = to_base(scorta.quantity_available, scorta.unit or "unità")
    return {
        "quantity": round(quanto, 2),
        "unit": unita,
        "label": format_quantity(quanto, unita),
        "usable": unita == item.unit,
    }


def serialize_shopping_list(db: Session, user_id: int, lst: ShoppingList) -> dict:
    rows = (
        db.query(ShoppingListItem, Ingredient)
        .join(Ingredient, Ingredient.id == ShoppingListItem.ingredient_id)
        .filter(ShoppingListItem.shopping_list_id == lst.id)
        .all()
    )

    # In dispensa c'è una riga sola per ingrediente (UNIQUE user_id + ingredient_id).
    scorte = {
        p.ingredient_id: p
        for p in db.query(PantryItem).filter(PantryItem.user_id == user_id).all()
    }

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
                # Quello che l'utente ha scritto per *questa* riga: è la cifra che
                # ritrova nel campo quando lo riapre, e quella che il totale conta al
                # posto della stima.
                "paid_price": item.paid_price,
                # Un prezzo che l'utente ha segnato allo scaffale vale come dato, uno
                # del catalogo vale come indizio: la UI li distingue. Il flag sta
                # sull'ingrediente perché il prezzo al chilo imparato vale per tutte
                # le liste, anche dove nessuno ha scritto niente.
                "price_by_user": ingredient.price_by_user,
                "last_paid_at": (
                    ingredient.last_paid_at.isoformat() if ingredient.last_paid_at else None
                ),
                "unit_price": ingredient.avg_price_per_unit,
                "price_unit": ingredient.price_unit,
                # Quello che di questo articolo è già in casa, e se è servito a
                # qualcosa: senza, una riga che la dispensa copre a metà (o che non
                # copre per un'unità che non torna) sembra un conto sbagliato.
                "pantry": _pantry_note(scorte.get(ingredient.id), item),
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
    # Quanti costi vengono da un prezzo segnato allo scaffale invece che dalla media
    # del catalogo: è la misura di quanto ci si può fidare del totale.
    priced_items = sum(1 for c in categories for i in c["items"] if i["price_by_user"])

    # Il periodo che la lista sta comprando: dal primo all'ultimo giorno con una
    # ricetta ancora da cucinare. Non è "questa settimana" — se hai generato anche la
    # prossima la spesa comprende anche quella, ed è metà del punto di tutto: una
    # confezione sola invece di due mezze.
    giorni = [day.date for day, _ in meals_to_buy(db, user_id)]

    return {
        "id": lst.id,
        "week_plan_id": lst.week_plan_id,
        "completed_at": lst.completed_at.isoformat() if lst.completed_at else None,
        "estimated_cost": lst.estimated_cost,
        "covers_from": min(giorni).isoformat() if giorni else None,
        "covers_to": max(giorni).isoformat() if giorni else None,
        # Dove si ferma la spesa e quanto piano resta fuori: senza, chi ha pianificato
        # tre settimane vede meno roba di quella che si aspetta e pensa a un errore.
        "horizon": shopping_horizon().isoformat(),
        "meals_beyond": meals_beyond_horizon(db, user_id),
        "total_items": total_items,
        "checked_items": checked_items,
        "priced_items": priced_items,
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


def consume_from_pantry(
    db: Session, user_id: int, recipe_id: int | None
) -> tuple[list[dict], list[dict]]:
    """Toglie dalla dispensa quello che la ricetta ha consumato.

    Si tocca solo quello che in dispensa c'è davvero: il sale e l'olio non ci sono
    quasi mai (sono ingredienti di base, non si comprano) e restano fuori da soli,
    senza bisogno di un elenco di eccezioni. Restano fuori anche le righe senza
    quantità — "ce l'ho ma non so quanto" — perché sottrarre da un valore ignoto
    darebbe un numero inventato, e le unità che non si parlano (una scorta contata a
    unità, una ricetta in grammi): è la stessa regola con cui la lista della spesa
    scomputa la dispensa.

    Restituisce due liste: quello che ha scalato — sia per mostrarlo (una conferma che
    non si vede non convince) sia per poterlo rimettere identico se il pasto viene
    corretto — e quello che ha lasciato stare, col motivo. Il secondo serve a dirlo:
    "l'ho seguito" che non muove niente sembra un pulsante rotto, mentre di solito è
    una scorta senza quantità o contata in un'unità che con la ricetta non si parla,
    e sapere quale è ciò che permette di sistemarla.
    """
    if not recipe_id:
        return [], []

    used: list[dict] = []
    skipped: list[dict] = []
    rows = (
        db.query(RecipeIngredient, Ingredient)
        .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
        .filter(RecipeIngredient.recipe_id == recipe_id)
        .all()
    )

    for ri, ingredient in rows:
        pantry = _pantry_of(db, user_id, ingredient.id)
        if not pantry:
            skipped.append({"name": ingredient.name, "reason": "assente"})
            continue
        if not pantry.quantity_available:
            skipped.append({"name": ingredient.name, "reason": "senza_quantita"})
            continue

        needed, unit = to_base(ri.quantity or 0, ri.unit)
        available, pantry_unit = to_base(pantry.quantity_available, pantry.unit or "unità")
        if needed <= 0:
            skipped.append({"name": ingredient.name, "reason": "quantita_ricetta"})
            continue
        if unit != pantry_unit:
            skipped.append(
                {
                    "name": ingredient.name,
                    "reason": "unita",
                    "pantry_unit": pantry_unit,
                    "recipe_unit": unit,
                }
            )
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
    return used, skipped


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


def complete_shopping(db: Session, user_id: int, lst: ShoppingList) -> dict:
    """Spesa fatta: quello che hai spuntato passa in dispensa e la lista si svuota.

    Non c'è niente da bloccare e niente da chiudere. Gli articoli spuntati diventano
    scorta, e la lista — che è sempre "quello che il piano chiede e la dispensa non
    copre" — si accorcia da sé al ricalcolo: la roba adesso è in casa. Quello che non
    hai spuntato resta in lista, perché non l'hai comprato.
    """
    presi = (
        db.query(ShoppingListItem)
        .filter(
            ShoppingListItem.shopping_list_id == lst.id,
            ShoppingListItem.is_checked.is_(True),
        )
        .all()
    )
    if not presi:
        raise HTTPException(
            400,
            "Non hai spuntato niente: segna quello che hai preso, poi conferma la spesa.",
        )

    now = datetime.now(timezone.utc)
    lst.completed_at = now

    # Quello che è stato spuntato è finito nel carrello, quindi ora è in dispensa —
    # nella quantità che si è presa davvero, non in quella che serviva: è la
    # differenza fra una dispensa che descrive il frigo e una che descrive il piano.
    for item in presi:
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

    # La lista si rifà subito: gli articoli appena messi in dispensa spariscono da
    # soli, ed è così che "ho fatto la spesa" la svuota senza cancellare niente.
    rebuild_shopping_list(db, user_id)
    db.commit()

    return {
        "detail": f"Spesa fatta: {len(presi)} articoli sono passati in dispensa.",
        "items_stored": len(presi),
        "completed_at": now.isoformat(),
    }


def export_text(db: Session, user_id: int, lst: ShoppingList) -> str:
    """Lista in testo semplice, da incollare in un messaggio o in una nota."""
    data = serialize_shopping_list(db, user_id, lst)
    if data["covers_from"] and data["covers_to"]:
        testata = (
            f"Lista della spesa — dal {date.fromisoformat(data['covers_from']).strftime('%d/%m/%Y')} "
            f"al {date.fromisoformat(data['covers_to']).strftime('%d/%m/%Y')}"
        )
    else:
        testata = "Lista della spesa"
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
