"""La generazione: la settimana in una chiamata (in un thread) e il singolo pasto."""

import json
import logging
import threading

from fastapi import HTTPException
from sqlalchemy.orm import Session, sessionmaker

from ...models import (
    DayPlan,
    Ingredient,
    MealSlot,
    PlannedMeal,
    Recipe,
    RecipeIngredient,
    User,
    WeekPlan,
)
from ...utils import cuisines
from ...utils import frequencies as freq
from .. import prompts
from ..ai_client import AIError
from ..exclusions import ExcludedFoodError
from ..recipes import (
    create_recipe,
    fit_recipe_data,
    learn_composition,
    recipe_for_prompt,
)
from .settimane import DAY_NAMES, current_week_start, get_active_diet, week_meals
from .stato import GenerationProgress, _failure_reason, claim_generation, clear_generation_progress, ensure_not_generating, record_generation_failure, store_generation_outcome
from .pasti import ensure_not_skipped, forget_queued_meal, forget_tracking, is_generable
from .contesto import _fmt_list, build_context, cuisine_shares
from .frequenze import _batch_groups, diet_frequencies, frequency_counts, is_main_slot
from .. import planner  # per i nomi che i test sostituiscono: vedi __init__

logger = logging.getLogger(__name__)


# ── Generazione ────────────────────────────────────────────────────────────────


def _slot_line(slot: MealSlot) -> str:
    line = (
        f"{slot.name} — {slot.target_calories} kcal, P {slot.target_protein_g:g}g, "
        f"C {slot.target_carbs_g:g}g, G {slot.target_fat_g:g}g"
    )
    return line + (f" (note: {slot.notes})" if slot.notes else "")


def generate_week(
    db: Session,
    user: User,
    week: WeekPlan,
    *,
    only_missing: bool = True,
    days: list[int] | None = None,
    slot_ids: list[int] | None = None,
    background: bool = False,
) -> dict:
    """Genera in un'unica chiamata le ricette della settimana.

    Con `background` la chiamata al modello parte in un thread e la funzione torna
    subito con `{"status": "started"}`: vedi `_in_background`. Senza, aspetta e
    restituisce il resoconto (`filled`, `missing`), come fanno i test.

    Una chiamata sola, non una per pasto: è l'unico modo perché l'AI possa
    distribuire gli avanzi (mezza zucchina lunedì, l'altra metà giovedì) e non
    ripetere gli stessi ingredienti in giorni consecutivi. Vale anche generando
    mezza settimana: quello che resta fuori dalla selezione ma una ricetta ce l'ha
    finisce comunque nel prompt come `PASTI GIÀ ASSEGNATI`.

    `only_missing` è il default perché ogni chiamata si paga: riempire i buchi è
    l'operazione di tutti i giorni, rifare da capo una settimana già piena è una
    scelta esplicita che la UI fa confermare.

    `days` (day_of_week) e `slot_ids` sono la selezione della dialog: `None` vuol dire
    tutto, che è come ha sempre funzionato il pulsante. Restringere non è un vezzo —
    chi la colazione se la prepara da sé non deve pagarne sette — e non cambia niente
    del resto: si genera sempre in una chiamata sola, solo su meno caselle.
    """
    ensure_not_generating(week)
    rows = week_meals(db, week)
    if not rows:
        raise HTTPException(400, "La settimana non ha pasti da generare.")

    # I giorni saltati sono passati e i pasti saltati sono già stati risolti altrove:
    # generarci una ricetta vorrebbe dire pagare una chiamata per un piatto che nessuno
    # cucinerà. Vale anche per "Rigenera tutto", che altrimenti li ripescherebbe.
    rows = [(d, m, s) for d, m, s in rows if not d.is_skipped and not m.is_skipped]
    generabili = [(d, m, s) for d, m, s in rows if is_generable(d, m, s)]

    # La selezione fatta nella dialog. Sono filtri e non validazioni: un giorno o un
    # pasto che non esistono semplicemente non selezionano niente, e la lista vuota —
    # che è una scelta esplicita, non un campo dimenticato — cade nel messaggio qui
    # sotto invece di rifare tutta la settimana.
    scelti = generabili
    if days is not None:
        giorni = set(days)
        scelti = [t for t in scelti if t[0].day_of_week in giorni]
    if slot_ids is not None:
        pasti = set(slot_ids)
        scelti = [t for t in scelti if t[2].id in pasti]

    to_fill = [t for t in scelti if t[1].recipe_id is None] if only_missing else scelti

    if not to_fill:
        if days is not None or slot_ids is not None:
            raise HTTPException(
                400,
                "Nei giorni e nei pasti che hai scelto non c'è niente da generare: "
                "allarga la selezione, oppure spunta «rifai anche i pasti già pronti».",
            )
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

    # Le frequenze della dieta: quale proteina va in quale pranzo o cena, decise qui
    # — come la cucina — e scritte accanto alla casella. Si parte da quello che la
    # settimana ha già, cioè tutto ciò che non si sta per rifare.
    # Batch cooking: i giorni consecutivi di un pasto «cucinato una volta» diventano un
    # gruppo, e al modello si chiede solo la prima casella di ogni gruppo. Le altre
    # ricevono la stessa ricetta dopo (`seguaci`). Da qui in avanti il prompt parla
    # solo delle prime: `da_rifare` qui sopra resta su tutte, perché tutte cambiano.
    prompt_rows, seguaci, note_batch = _batch_groups(to_fill)

    regole = diet_frequencies(db, user.id)
    proteine: dict[int, dict] = {}
    if regole:
        diet = get_active_diet(db, user.id)
        principali = [
            (d.day_of_week, m.id) for d, m, s in prompt_rows
            if is_main_slot(s, diet.total_daily_calories)
        ]
        gia = frequency_counts(db, week, exclude_meal_ids={m.id for _, m, _ in to_fill})
        proteine = freq.assign(regole, gia, principali)

    by_day: dict[int, list[str]] = {}
    for day, meal, slot in prompt_rows:
        by_day.setdefault(day.day_of_week, []).append(
            _slot_line(slot)
            + freq.prompt_hint(proteine.get(meal.id))
            + note_batch.get(meal.id, "")
        )
    giorni = sorted(by_day)

    # Il sorteggio: una cucina per giorno, estratta qui e scritta **accanto al
    # giorno**, che è il posto dove il modello la legge mentre compone quel giorno —
    # non in fondo a un blocco di contesto lungo venti righe. Sotto le due cucine non
    # c'è niente da sorteggiare e il contesto resta quello di sempre: lo strato non
    # esiste finché non lo si usa.
    scelte = cuisine_shares(db, user.id)
    sorteggio = (
        dict(zip(giorni, cuisines.draw(scelte, len(giorni)))) if len(scelte) > 1 else {}
    )

    slots_to_fill = "\n".join(
        f"{DAY_NAMES[dow]} (day_of_week {dow})"
        + (f" — CUCINA: {sorteggio[dow]}" if dow in sorteggio else "")
        + ":\n"
        + "\n".join(f"  · {line}" for line in by_day[dow])
        for dow in giorni
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
        context=build_context(
            db, user.id, cuisine=cuisines.PER_GIORNO if sorteggio else None
        ),
        slots_to_fill=slots_to_fill,
        already_assigned=already,
    )

    client = planner.get_client(db, user, "planning")

    # Da qui in avanti la settimana risulta "in generazione". Il commit chiude anche
    # la transazione aperta dalle letture qui sopra: senza, Postgres si terrebbe una
    # connessione "idle in transaction" per tutta la durata della chiamata.
    claim_generation(db, week)
    clear_generation_progress(db, week)
    db.commit()

    progress = GenerationProgress(
        week.id,
        expected_recipes=len(prompt_rows),
        # Stesso database, connessione diversa: così il diario si committa da solo
        # senza portarsi dietro la settimana a metà che ha in mano questa sessione.
        session_factory=sessionmaker(bind=db.get_bind()),
    )
    progress.flush()  # una prima riga subito: la pagina ha già qualcosa da mostrare

    # Budget: ~2.000 token a ricetta più il margine per il ragionamento. Sopra la
    # soglia il client passa automaticamente in streaming.
    max_tokens = min(64000, 2000 * len(prompt_rows) + 6000)

    if background:
        ids = [(d.id, m.id, s.id) for d, m, s in prompt_rows]
        week_id = week.id
        planner._in_background(
            db.get_bind(),
            f"genera-settimana-{week.id}",
            on_failure=lambda s, exc: record_generation_failure(
                s, s.get(WeekPlan, week_id), _failure_reason(exc)
            ),
            work=lambda s: _run_generation(
                s,
                s.get(User, user.id),
                s.get(WeekPlan, week_id),
                [(s.get(DayPlan, d), s.get(PlannedMeal, m), s.get(MealSlot, sl)) for d, m, sl in ids],
                client=client,
                prompt=prompt,
                max_tokens=max_tokens,
                progress=progress,
                followers=seguaci,
            ),
        )
        return {"status": "started", "expected": len(to_fill)}

    return _run_generation(
        db, user, week, prompt_rows,
        client=client, prompt=prompt, max_tokens=max_tokens, progress=progress,
        followers=seguaci,
    )


# La rotta genera in background; i test lo spengono (`conftest.py`) e aspettano il
# resoconto, come faceva la POST prima. Chi prova il thread lo riaccende.
GENERATION_IN_BACKGROUND = True

# I thread delle generazioni in corso. Servono ai test (per aspettarle) e a nient'altro:
# lo stato vero di una generazione sta sul `WeekPlan`, non qui.
_THREADS: list[threading.Thread] = []


def _in_background(bind, name: str, work, on_failure=None) -> threading.Thread:
    """Fa girare `work(sessione)` in un thread, con una sessione tutta sua.

    **La generazione non vive dentro la richiesta HTTP.** Dura minuti, e davanti c'è
    un proxy che chiude molto prima (nginx a 300 s, e un proxy davanti può chiudere anche prima): la POST restava
    appesa per tutto quel tempo su una connessione già morta, tenendo occupato un
    worker del threadpool. Lo stato, il diario e l'errore stavano già sul `WeekPlan`
    proprio per questo; adesso ci sta anche il lavoro, e la POST risponde subito 202.

    Sessione propria perché quella della richiesta si chiude quando la richiesta
    finisce. Il thread è `daemon`: se il processo si riavvia a metà, la settimana resta
    "in generazione" fino a `GENERATION_TIMEOUT`, come prima — il segno sul database
    è l'unica cosa che sopravvive a un riavvio.
    """

    def corpo():
        session = sessionmaker(bind=bind)()
        try:
            work(session)
        except Exception as exc:  # noqa: BLE001
            if getattr(exc, "registrata", False):
                return  # già loggata e scritta sulla settimana da _run_generation
            # Fallita prima di arrivarci (una riga sparita, il database giù) o mentre
            # registrava il fallimento: prima finiva in un `pass`, senza una riga di
            # log, e la settimana restava "in generazione" per un quarto d'ora.
            logger.exception("Generazione in background %s fallita", name)
            if on_failure is not None:
                try:
                    on_failure(session, exc)
                except Exception:  # noqa: BLE001
                    logger.exception("Non riesco a segnare il fallimento di %s", name)
        finally:
            session.close()

    thread = threading.Thread(target=corpo, name=name, daemon=True)
    _THREADS[:] = [t for t in _THREADS if t.is_alive()]
    _THREADS.append(thread)
    thread.start()
    return thread


def _run_generation(
    db: Session,
    user: User,
    week: WeekPlan,
    to_fill: list[tuple[DayPlan, PlannedMeal, MealSlot]],
    *,
    client,
    prompt: str,
    max_tokens: int,
    progress,
    followers: dict[int, list[int]] | None = None,
) -> dict:
    """La chiamata al modello e la scrittura del piano: la parte che dura minuti."""
    try:
        # Nel thread le letture qui sopra hanno aperto una transazione: chiuderla prima
        # della chiamata, o la connessione resta "idle in transaction" per minuti.
        db.commit()
        data = client.generate_json(
            prompts.WEEK_PLAN_SYSTEM,
            prompt,
            max_tokens=max_tokens,
            thinking=True,
            on_progress=progress,
        )
        # Anche l'applicazione della risposta sta dentro il try: una risposta parsabile
        # ma di forma sbagliata sollevava fuori di qui, e lasciava la settimana
        # bloccata su "sto generando" fino allo scadere del quarto d'ora.
        return _apply_generated_week(
            db, user, week, data, to_fill, client=client, followers=followers
        )
    except Exception as exc:
        # Il log è l'unico posto dove questo messaggio arriva per davvero: la risposta
        # HTTP viene scritta su una connessione che il proxy ha chiuso da minuti, e
        # senza questa riga una generazione fallita non lasciava alcuna traccia.
        logger.exception("Generazione fallita per la settimana %s", week.id)
        # Sblocca la settimana — altrimenti resta ferma fino al timeout — e ricorda
        # perché, per chi la sta guardando dal polling.
        record_generation_failure(db, week, _failure_reason(exc))
        exc.registrata = True
        raise


def _apply_generated_week(
    db: Session,
    user: User,
    week: WeekPlan,
    data: dict | list,
    to_fill: list[tuple[DayPlan, PlannedMeal, MealSlot]],
    *,
    client=None,
    followers: dict[int, list[int]] | None = None,
) -> dict:
    """Scrive nel piano le ricette uscite dal modello."""
    if not isinstance(data, dict) or not isinstance(data.get("days"), list):
        raise AIError("Claude ha restituito un piano in un formato inatteso.")

    # Prima di scrivere: i nomi che il catalogo non conosce ricevono una composizione
    # (una chiamata per tutta la settimana), così i macro si possono calcolare.
    if client is not None:
        learn_composition(
            db,
            client,
            [
                (m.get("recipe") or {})
                for d in data["days"] if isinstance(d, dict)
                for m in (d.get("meals") or []) if isinstance(m, dict)
            ],
        )

    # Indice delle caselle da riempire: (giorno, nome pasto normalizzato) → riga DB.
    index = {(d.day_of_week, s.name.strip().lower()): (d, m, s) for d, m, s in to_fill}
    filled = 0
    excluded: list[str] = []

    for day_data in data["days"]:
        # La risposta del modello si prende per quello che è: un giorno o un pasto che
        # non sono oggetti (una stringa, una lista) davano AttributeError, e il rollback
        # buttava anche le ricette buone già pagate.
        if not isinstance(day_data, dict):
            continue
        try:
            dow = int(day_data.get("day_of_week"))
        except (TypeError, ValueError):
            continue
        pasti = day_data.get("meals")
        for meal_data in pasti if isinstance(pasti, list) else []:
            if not isinstance(meal_data, dict):
                continue
            slot_name = str(meal_data.get("slot_name") or "").strip().lower()
            target = index.pop((dow, slot_name), None)
            if not target:
                # L'AI ha inventato un pasto che non esiste (o l'ha già riempito):
                # ignorarlo è meglio che sovrascrivere qualcosa a caso.
                logger.info(
                    "Pasto ignorato dalla risposta AI: giorno %s, slot %r",
                    dow,
                    slot_name,
                )
                continue
            recipe_data = meal_data.get("recipe")
            if not isinstance(recipe_data, dict) or not recipe_data.get("title"):
                continue
            _day, meal, slot = target
            try:
                recipe = create_recipe(
                    db,
                    user.id,
                    fit_recipe_data(db, recipe_data, slot),
                    generation_prompt="week_plan",
                )
            except ExcludedFoodError as exc:
                # Un piatto con un alimento escluso non entra: la casella resta vuota e
                # si rigenera da sola, invece di buttare tutta la settimana.
                logger.warning("Ricetta scartata (esclusi): %s", exc.detail)
                excluded.append(exc.detail)
                index[(dow, slot_name)] = target
                continue
            meal.recipe_id = recipe.id
            meal.source = "ai_generated"
            forget_tracking(meal)
            filled += 1
            # Il batch: la stessa ricetta nei giorni dopo, cucinata una volta sola.
            for seguace_id in (followers or {}).get(meal.id, []):
                seguace = db.get(PlannedMeal, seguace_id)
                seguace.recipe_id = recipe.id
                seguace.source = "ai_generated"
                forget_tracking(seguace)
                forget_queued_meal(db, seguace)
                filled += 1

    week.generation_started_at = None
    esito = {"filled": filled, "missing": len(index), "excluded": excluded}
    # Il resoconto resta solo se c'è qualcosa da dire: una settimana piena è «pronta»,
    # e il diario di questa generazione non deve sopravviverle.
    if esito["missing"]:
        store_generation_outcome(db, week, esito)
    else:
        clear_generation_progress(db, week)

    if filled == 0:
        # Niente commit: a rimettere in ordine la settimana — sbloccarla e segnare
        # perché — ci pensa chi cattura, che è anche l'unico a saperlo dire all'utente.
        raise AIError(
            "Il modello non ha prodotto nessuna ricetta utilizzabile. Riprova."
            + (f" Scartate per gli esclusi: {'; '.join(excluded)}" if excluded else "")
        )

    if week.status == "draft" and week.week_start_date == current_week_start():
        week.status = "active"

    db.commit()

    # La lista della spesa segue sempre il piano: le ricette appena generate chiedono
    # ingredienti che in dispensa non ci sono, e devono comparire subito in lista —
    # anche se la settimana generata è la prossima, perché la spesa è una sola.
    from ..shopping import rebuild_shopping_list

    rebuild_shopping_list(db, user.id)
    db.commit()

    return {**esito, "notes": data.get("ingredient_reuse_notes")}


def _single_meal_frequencies(
    db: Session, user: User, week: WeekPlan, meal: PlannedMeal, slot: MealSlot
) -> str:
    """La riga delle frequenze per un pasto rigenerato da solo.

    Non si assegna un gruppo — si sta rifacendo un piatto, non pianificando la
    settimana — ma si dice cosa manca e cosa è già al massimo, senza contare il piatto
    che si sta buttando. Con una richiesta dell'utente non si scrive niente: comanda lei.
    """
    regole = diet_frequencies(db, user.id)
    diet = get_active_diet(db, user.id)
    if not regole or not diet or not is_main_slot(slot, diet.total_daily_calories):
        return ""
    righe = freq.report(regole, frequency_counts(db, week, exclude_meal_ids={meal.id}))
    mancano = [r["label"].lower() for r in righe if r["status"] == "sotto"]
    pieni = [
        r["label"].lower() for r in righe
        if r["max"] is not None and r["count"] >= r["max"]
    ]
    parti = []
    if mancano:
        parti.append("mancano ancora in settimana: " + ", ".join(mancano) + " — preferiscili")
    if pieni:
        parti.append("già al massimo della settimana, da non usare: " + ", ".join(pieni))
    return ("FREQUENZE DELLA DIETA: " + "; ".join(parti) + "\n") if parti else ""


def _partial_ingredients(
    db: Session, week: WeekPlan, exclude_meal_id: int
) -> list[str]:
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
    """Genera (o rigenera) la ricetta di un singolo pasto.

    Due modi, stesso pulsante. Senza `user_request` sceglie il modello, col vincolo di
    proporre qualcosa di diverso dal piatto di prima e dagli altri della settimana.
    Con `user_request` — un'idea, degli ingredienti da usare, un piatto preciso — decide
    l'utente e all'AI resta il mestiere: pesare gli ingredienti perché i macro del pasto
    tornino, completare quello che manca e scrivere il procedimento. È il caso che la
    chat non copriva: lì si parte da una ricetta e la si modifica, qui la casella può
    essere ancora vuota.

    La vecchia ricetta non viene cancellata: resta nel ricettario (magari era
    votata) e semplicemente non è più assegnata a questo pasto.
    """
    day = db.get(DayPlan, meal.day_plan_id)
    week = db.get(WeekPlan, day.week_plan_id)
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

    # Una cucina sorteggiata anche qui, ed è il caso in cui la differenza si sente di
    # più: «rigenera» premuto tre volte di fila dava tre piatti italiani, perché a
    # parità di macro è la cucina di cui il modello conosce più ricette. Si esclude
    # quella del piatto che si sta buttando (`avoid`), che è la stessa ragione per cui
    # gli si dice di non riproporlo: chi rigenera vuole un'altra cosa.
    #
    # Con una richiesta dell'utente non si sorteggia niente. Lì comanda lei — dice il
    # prompt, e lo dice anche il buon senso: «fammi una carbonara» più «oggi è
    # coreano» sono due ordini contrari, e a scegliere quale seguire sarebbe il
    # modello. Se una cucina la vuole, l'utente la scrive nella richiesta.
    scelte = cuisine_shares(db, user.id)
    tags = previous.tags if previous and isinstance(previous.tags, dict) else {}
    estratta = (
        cuisines.draw(scelte, 1, avoid=tags.get("cuisine"))
        if len(scelte) > 1 and not user_request
        else []
    )

    prompt = prompts.render(
        prompts.SINGLE_MEAL_PROMPT,
        context=build_context(
            db,
            user.id,
            cuisine=cuisines.prompt_line_one(estratta[0]) if estratta else None,
        ),
        slot_name=slot.name,
        day_name=DAY_NAMES[day.day_of_week],
        target_calories=slot.target_calories,
        target_protein=f"{slot.target_protein_g:g}",
        target_carbs=f"{slot.target_carbs_g:g}",
        target_fat=f"{slot.target_fat_g:g}",
        slot_notes=slot.notes or "nessuna",
        previous_recipe=previous.title if previous else "nessuna",
        week_recipes=_fmt_list(week_titles, "nessuna"),
        partial_ingredients=_fmt_list(
            _partial_ingredients(db, week, meal.id), "nessuno"
        ),
        frequencies=_single_meal_frequencies(db, user, week, meal, slot)
        if not user_request
        else "",
        user_request=(
            "\nRICHIESTA DELL'UTENTE (ha la precedenza sulle regole di varietà qui "
            f"sopra): {user_request}\n"
            "Costruisci il piatto attorno a questa richiesta: scegli e pesa gli "
            "ingredienti perché i macro target tornino, e scrivi il procedimento."
            if user_request
            else ""
        ),
    )

    client = planner.get_client(db, user, "planning")
    db.commit()  # come sopra: niente transazione aperta durante la chiamata al modello
    data = client.generate_json(
        prompts.SINGLE_MEAL_SYSTEM, prompt, max_tokens=8000, thinking=False
    )
    if not isinstance(data, dict) or not data.get("title"):
        raise AIError("Claude non ha restituito una ricetta valida.")

    learn_composition(db, client, [data])
    recipe = create_recipe(
        db,
        user.id,
        fit_recipe_data(db, data, slot),
        generation_prompt=json.dumps({"slot": slot.name}),
    )

    # Se il pasto era stato tracciato come seguito, reimmetti gli ingredienti nella dispensa
    if meal.is_followed is True and meal.pantry_used:
        from ..shopping import restore_to_pantry

        restore_to_pantry(db, user.id, meal.pantry_used)

    meal.recipe_id = recipe.id
    meal.source = "ai_generated"
    forget_tracking(meal)
    # Qui dentro c'è un piatto nuovo, scelto adesso: se questa casella era la coda di un
    # pasto rimandato, non lo è più.
    forget_queued_meal(db, meal)
    db.commit()

    from ..shopping import rebuild_shopping_list

    rebuild_shopping_list(db, user.id)
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
