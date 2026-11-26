"""Server MCP di DietAI: piano, pasti, spesa e dispensa chiesti (e segnati) da Claude.

Lo usa SpassoHub (l'hub MCP di Daniele), non un client qualsiasi: per questo
l'accesso è un **token fisso** (`MCP_TOKEN`, almeno 32 caratteri) e non OAuth. Il
token vale per l'**amministratore** (`accounts.admin_user`), l'unico che ha
chiesto di collegare l'app; senza `MCP_TOKEN` l'endpoint non esiste (404).

Ogni strumento chiama **le stesse funzioni delle rotte** (o dei servizi che le rotte
chiamano), con lo stesso utente: nessuna regola è riscritta qui, quindi spesa,
dispensa, tracking e ricette si comportano come dall'app. Gli errori delle rotte
(`HTTPException`) tornano come risultato `isError` col loro messaggio.

Protocollo: Streamable HTTP senza sessione, risposte JSON (come SpassoConti).
La rotta è `def` come tutte le altre (`tests/test_concurrency.py`).
"""

import hmac
import json
import logging
from datetime import date, timedelta
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import DayPlan, MealSlot, PlannedMeal, Recipe, User, WeekPlan
from ..schemas import (
    CheckItemRequest,
    FollowedRequest,
    PantryCreate,
    PantryUpdate,
    SkipDayRequest,
    RecipeIngredientInput,
    RecipeUpdate,
    SwapMealRequest,
    WeightEntryIn,
)
from ..services import meals, planner
from ..services.accounts import admin_user
from ..services.ai_client import get_client
from ..services.ownership import own_meal
from ..services.recipes import edit_recipe, fork_recipe_for_meal, serialize_recipe, settle_recipe
from . import config as config_router
from . import diet as diet_router
from . import planning as planning_router
from . import recipes as recipes_router
from . import shopping as shopping_router
from . import tracking as tracking_router

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MCP"])

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

ISTRUZIONI = (
    "DietAI: la dieta, il piano settimanale dei pasti, le ricette, la lista della spesa e la "
    "dispensa dell'utente. Le date sono AAAA-MM-GG in ora italiana. Parti da `oggi` (i pasti "
    "di un giorno con gli id) o `settimana`; gli strumenti che segnano un pasto vogliono il "
    "`meal_id` che trovi lì. `segna_seguito` scala la dispensa; `ho_mangiato_altro` stima cosa "
    "si è mangiato al posto del piatto previsto; `ho_mangiato_questo` riempie una casella vuota, "
    "`sostituisci_pasto` mette un piatto nuovo al posto di quello che c'è; `modifica_pasto` "
    "corregge ingredienti e grammature del piatto di un pasto; `svuota_pasto` lo toglie. "
    "Quelli con l'AI (`ho_mangiato_*`, `sostituisci_pasto`, `rigenera_pasto`) usano il modello e costano."
)


# --- Argomenti ----------------------------------------------------------------


def _data(args: dict, nome: str, default: Optional[date] = None) -> date:
    valore = args.get(nome)
    if valore in (None, ""):
        if default is None:
            raise ValueError(f"manca `{nome}` (AAAA-MM-GG)")
        return default
    try:
        giorno = date.fromisoformat(str(valore))
    except ValueError:
        raise ValueError(f"`{nome}` non è una data AAAA-MM-GG: {valore!r}")
    if not 2000 <= giorno.year <= 2100:
        raise ValueError(f"`{nome}` fuori dall'intervallo gestito")
    return giorno


def _int(args: dict, nome: str) -> int:
    valore = args.get(nome)
    if isinstance(valore, bool) or valore is None:
        raise ValueError(f"manca `{nome}` (numero intero)")
    try:
        return int(valore)
    except (TypeError, ValueError):
        raise ValueError(f"`{nome}` deve essere un numero intero")


def _bool(args: dict, nome: str, default: bool) -> bool:
    valore = args.get(nome, default)
    if isinstance(valore, bool):
        return valore
    raise ValueError(f"`{nome}` deve essere true o false")


# --- Strumenti: lettura -------------------------------------------------------


def t_oggi(db: Session, user: User, args: dict):
    return tracking_router.day_summary(_data(args, "data", planner.today()), user.id, db)


def t_home(db: Session, user: User, args: dict):
    return tracking_router.dashboard(user.id, db)


def t_settimana(db: Session, user: User, args: dict):
    return planning_router.get_week_by_date(_data(args, "data", planner.today()), user.id, db)


def t_pasto(db: Session, user: User, args: dict):
    return planning_router.get_meal(_int(args, "meal_id"), user.id, db)


def t_andamento(db: Session, user: User, args: dict):
    giorno = args.get("data")
    if giorno:
        giorno = _data(args, "data").isoformat()
    return tracking_router.weekly(giorno or None, user.id, db)


def t_anno(db: Session, user: User, args: dict):
    anno = args.get("anno")
    return tracking_router.year(int(anno) if anno else None, user.id, db)


def t_peso(db: Session, user: User, args: dict):
    return tracking_router.get_weight(user.id, db)


def t_dieta(db: Session, user: User, args: dict):
    return diet_router.get_current_diet(user, db)


def t_ricette(db: Session, user: User, args: dict):
    per_pagina = min(max(int(args.get("per_pagina") or 20), 1), 100)
    return recipes_router.list_recipes(
        page=max(int(args.get("pagina") or 1), 1),
        per_page=per_pagina,
        rating_min=None,
        is_favorite=bool(args.get("solo_preferite")) or None,
        scope="saved",
        difficulty=None,
        search=(args.get("cerca") or None),
        user_id=user.id,
        db=db,
    )


def t_ricetta(db: Session, user: User, args: dict):
    return recipes_router.get_recipe(_int(args, "recipe_id"), user.id, db)


def t_lista_spesa(db: Session, user: User, args: dict):
    return shopping_router.get_current_list(user.id, db)


def t_dispensa(db: Session, user: User, args: dict):
    return config_router.list_pantry(user.id, db)


def t_pasti_consumati(db: Session, user: User, args: dict):
    """I pasti segnati in un periodo: seguiti, «ho mangiato altro», con la data."""
    fine = _data(args, "a", planner.today())
    inizio = _data(args, "da", fine - timedelta(days=29))
    if inizio > fine:
        raise ValueError("`da` viene dopo `a`")
    if (fine - inizio).days > 366:
        raise ValueError("al massimo un anno alla volta")
    rows = (
        db.query(PlannedMeal, DayPlan, MealSlot, Recipe)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .join(MealSlot, MealSlot.id == PlannedMeal.meal_slot_id)
        .outerjoin(Recipe, Recipe.id == PlannedMeal.recipe_id)
        .filter(
            WeekPlan.user_id == user.id,
            DayPlan.date >= inizio,
            DayPlan.date <= fine,
            PlannedMeal.is_followed.isnot(None),
        )
        .order_by(DayPlan.date, MealSlot.order_index)
        .all()
    )
    pasti = [
        {
            "data": day.date.isoformat(),
            "pasto": slot.name,
            "meal_id": meal.id,
            "esito": "seguito" if meal.is_followed else "mangiato altro",
            "piatto": recipe.title if recipe and meal.is_followed else None,
            "nota": meal.deviation_notes,
        }
        for meal, day, slot, recipe in rows
    ]
    seguiti = sum(1 for p in pasti if p["esito"] == "seguito")
    return {
        "da": inizio.isoformat(),
        "a": fine.isoformat(),
        "segnati": len(pasti),
        "seguiti": seguiti,
        "mangiato_altro": len(pasti) - seguiti,
        "giorni_con_pasti_segnati": len({p["data"] for p in pasti}),
        "pasti": pasti,
    }


# --- Strumenti: scrittura -----------------------------------------------------


def t_segna_seguito(db: Session, user: User, args: dict):
    body = FollowedRequest(
        is_followed=_bool(args, "seguito", True), deviation_notes=args.get("note") or None
    )
    return planning_router.set_followed(_int(args, "meal_id"), body, user.id, db)


def t_mangiato_altro(db: Session, user: User, args: dict):
    meal, day, week = own_meal(db, user.id, _int(args, "meal_id"))
    niente = _bool(args, "niente", False)
    testo = (args.get("cosa") or "").strip() or None
    if not niente and not testo:
        raise ValueError("serve `cosa` (cosa hai mangiato) oppure `niente: true`")
    # Nell'app sono due tocchi («ho mangiato altro», poi «cosa?»); qui è una frase sola,
    # quindi il segno lo mette lo strumento. Prima `niente` su un pasto ancora da segnare
    # rispondeva 400 e serviva un `segna_seguito(seguito=false)` in più.
    if meal.is_followed is not False:
        meals.set_followed(db, user.id, meal, day, week, False, None)
    return meals.eaten_instead(
        db, lambda: get_client(db, user, "quick"), meal, day, testo, niente
    )


def t_mangiato_questo(db: Session, user: User, args: dict):
    meal, day, _week = own_meal(db, user.id, _int(args, "meal_id"))
    testo = (args.get("cosa") or "").strip()
    if len(testo) < 3:
        raise ValueError("serve `cosa`: il piatto a parole")
    return meals.ate(
        db, user, lambda: get_client(db, user, "quick"), meal, day, testo,
        already_eaten=_bool(args, "gia_mangiato", True),
    )


def t_sostituisci(db: Session, user: User, args: dict):
    meal, day, _week = own_meal(db, user.id, _int(args, "meal_id"))
    testo = (args.get("cosa") or "").strip()
    if len(testo) < 3:
        raise ValueError("serve `cosa`: il piatto a parole")
    return meals.ate(
        db, user, lambda: get_client(db, user, "quick"), meal, day, testo,
        already_eaten=_bool(args, "gia_mangiato", True), replace=True,
    )


def t_svuota(db: Session, user: User, args: dict):
    return planning_router.clear_meal(_int(args, "meal_id"), user.id, db)


def _ingrediente(riga: Any) -> dict:
    if not isinstance(riga, dict):
        raise ValueError("ogni ingrediente è un oggetto {nome, quantita, unita, note}")
    return RecipeIngredientInput(
        name=str(riga.get("nome") or riga.get("name") or ""),
        quantity=riga.get("quantita", riga.get("quantity")),
        unit=str(riga.get("unita") or riga.get("unit") or ""),
        notes=riga.get("note") or riga.get("notes") or None,
    ).model_dump()


def t_modifica(db: Session, user: User, args: dict):
    """Corregge il piatto di **questo** pasto: titolo, ingredienti, procedimento.

    Come la chat del pasto: la ricetta si stacca se è in programma anche altrove
    (`fork_recipe_for_meal`), si corregge (`edit_recipe`: macro rifatti dagli
    ingredienti, spesa e dispensa che seguono) e si riaccorpa se torna uguale a
    un'altra (`settle_recipe`).
    """
    meal, day, _week = own_meal(db, user.id, _int(args, "meal_id"))
    planner.ensure_not_skipped(day, meal)
    if not meal.recipe_id:
        raise ValueError("il pasto è vuoto: per riempirlo usa `ho_mangiato_questo`")
    ingredienti = args.get("ingredienti")
    if ingredienti is not None and not isinstance(ingredienti, list):
        raise ValueError("`ingredienti` è la lista completa degli ingredienti")
    if ingredienti is None and not args.get("titolo") and not args.get("procedimento"):
        raise ValueError("niente da cambiare: passa ingredienti, titolo o procedimento")

    recipe = fork_recipe_for_meal(db, meal)
    attuale = serialize_recipe(db, recipe, full=True)
    dati = RecipeUpdate(
        title=str(args.get("titolo") or attuale["title"]),
        description=attuale.get("description"),
        prep_time_min=attuale.get("prep_time_min") or 0,
        cook_time_min=attuale.get("cook_time_min") or 0,
        difficulty=attuale.get("difficulty") or "medium",
        instructions=str(args.get("procedimento") or attuale.get("instructions") or "-"),
        ingredients=(
            [_ingrediente(r) for r in ingredienti]
            if ingredienti is not None
            else [
                {k: r.get(k) for k in ("name", "quantity", "unit", "notes")}
                for r in attuale["ingredients"]
            ]
        ),
    ).model_dump()
    edit_recipe(db, user.id, recipe, dati)
    settle_recipe(db, meal)
    db.commit()
    return planning_router.get_meal(meal.id, user.id, db)


def t_rigenera(db: Session, user: User, args: dict):
    meal, day, _week = own_meal(db, user.id, _int(args, "meal_id"))
    richiesta = (args.get("richiesta") or "").strip() or None
    planner.regenerate_meal(db, user, meal, user_request=richiesta)
    slot = db.get(MealSlot, meal.meal_slot_id)
    return planner.serialize_meal(db, day, meal, slot, full=True)


def t_scambia(db: Session, user: User, args: dict):
    body = SwapMealRequest(other_meal_id=_int(args, "altro_meal_id"))
    return planning_router.swap_meal(_int(args, "meal_id"), body, user.id, db)


def t_salta_giorno(db: Session, user: User, args: dict):
    body = SkipDayRequest(is_skipped=_bool(args, "saltato", True))
    return planning_router.set_day_skipped(_int(args, "day_id"), body, user.id, db)


def t_registra_peso(db: Session, user: User, args: dict):
    giorno = args.get("data")
    body = WeightEntryIn(
        weight_kg=float(args.get("kg") or 0),
        day=_data(args, "data") if giorno else None,
    )
    return tracking_router.put_weight(body, user.id, db)


def t_spunta_spesa(db: Session, user: User, args: dict):
    body = CheckItemRequest(is_checked=_bool(args, "spuntato", True))
    return shopping_router.check_item(_int(args, "item_id"), body, user.id, db)


def t_spesa_fatta(db: Session, user: User, args: dict):
    return shopping_router.complete(user.id, db)


def t_dispensa_aggiungi(db: Session, user: User, args: dict):
    body = PantryCreate(
        ingredient_name=str(args.get("nome") or ""),
        quantity=args.get("quantita"),
        unit=args.get("unita") or None,
        expires_on=_data(args, "scadenza") if args.get("scadenza") else None,
    )
    return config_router.add_pantry(body, user.id, db)


def t_dispensa_modifica(db: Session, user: User, args: dict):
    campi = {}
    if "quantita" in args:
        campi["quantity"] = args["quantita"]
    if "unita" in args:
        campi["unit"] = args["unita"] or None
    if "scadenza" in args:
        campi["expires_on"] = _data(args, "scadenza") if args["scadenza"] else None
    if not campi:
        raise ValueError("niente da cambiare: passa quantita, unita o scadenza")
    return config_router.update_pantry(_int(args, "item_id"), PantryUpdate(**campi), user.id, db)


def t_dispensa_togli(db: Session, user: User, args: dict):
    item_id = _int(args, "item_id")
    config_router.remove_pantry(item_id, user.id, db)
    return {"tolto": item_id}


# --- Catalogo -----------------------------------------------------------------

_DATA = {"type": "string", "description": "AAAA-MM-GG"}
_MEAL = {"type": "integer", "description": "id del pasto (da `oggi` o `settimana`)"}

LETTURA = {"readOnlyHint": True, "openWorldHint": False}
SCRITTURA = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}
CON_AI = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True}


def _tool(fn: Callable, descrizione: str, proprieta: dict, obbligatori=(), annotazioni=LETTURA):
    return fn, {
        "description": descrizione,
        "inputSchema": {
            "type": "object",
            "properties": proprieta,
            **({"required": list(obbligatori)} if obbligatori else {}),
        },
        "annotations": annotazioni,
    }


TOOLS: dict[str, tuple[Callable, dict]] = {
    "oggi": _tool(
        t_oggi,
        "I pasti di un giorno (default oggi) con meal_id, piatto, stato (seguito, ho mangiato "
        "altro, da segnare), macro mangiati contro il target della dieta.",
        {"data": _DATA},
    ),
    "home": _tool(t_home, "Il riepilogo della home: oggi, a che punto è il piano e la spesa.", {}),
    "settimana": _tool(
        t_settimana,
        "Il piano della settimana che contiene `data` (default questa): giorni (con day_id), "
        "pasti, ricette, totali. Una settimana passata mai pianificata torna vuota.",
        {"data": _DATA},
    ),
    "pasto": _tool(
        t_pasto, "Dettaglio completo di un pasto: ricetta, ingredienti, macro, target, stato.",
        {"meal_id": _MEAL}, ["meal_id"],
    ),
    "andamento": _tool(
        t_andamento,
        "Andamento della settimana che contiene `data`: aderenza, calorie e macro giorno per "
        "giorno contro i target.",
        {"data": _DATA},
    ),
    "aderenza_anno": _tool(
        t_anno, "Aderenza giorno per giorno in un anno solare.",
        {"anno": {"type": "integer"}},
    ),
    "peso": _tool(t_peso, "Storico delle pesate e, se serve, la proposta di ricalcolo della dieta.", {}),
    "dieta": _tool(t_dieta, "La dieta attiva: calorie e macro del giorno, pasti e loro target, frequenze.", {}),
    "ricette": _tool(
        t_ricette, "Il ricettario (ricette salvate: preferite, votate o scritte a mano).",
        {
            "cerca": {"type": "string", "description": "Nel titolo"},
            "solo_preferite": {"type": "boolean"},
            "pagina": {"type": "integer", "minimum": 1},
            "per_pagina": {"type": "integer", "minimum": 1, "maximum": 100},
        },
    ),
    "ricetta": _tool(
        t_ricetta, "Una ricetta completa con ingredienti, procedimento, macro e quando è stata in piano.",
        {"recipe_id": {"type": "integer"}}, ["recipe_id"],
    ),
    "lista_spesa": _tool(
        t_lista_spesa,
        "La lista della spesa: quello che il piano chiede da oggi in avanti e la dispensa non ha, "
        "per reparto, con item_id e spunte.",
        {},
    ),
    "dispensa": _tool(t_dispensa, "Cosa c'è in dispensa, con quantità, scadenze e item_id.", {}),
    "pasti_consumati": _tool(
        t_pasti_consumati,
        "I pasti segnati in un periodo (default ultimi 30 giorni): quanti seguiti e quanti «ho "
        "mangiato altro», giorno per giorno.",
        {"da": _DATA, "a": _DATA},
    ),
    "segna_seguito": _tool(
        t_segna_seguito,
        "Segna un pasto come seguito (scala la dispensa) o, con seguito=false, come non seguito. "
        "Per dire cosa si è mangiato invece usa ho_mangiato_altro.",
        {"meal_id": _MEAL, "seguito": {"type": "boolean", "default": True}, "note": {"type": "string"}},
        ["meal_id"], SCRITTURA,
    ),
    "ho_mangiato_altro": _tool(
        t_mangiato_altro,
        "«Ho mangiato altro»: cosa si è mangiato al posto del piatto previsto; il modello ne stima "
        "calorie e macro e la ricetta prevista slitta più avanti. niente=true per un pasto saltato. "
        "Segna da sé il pasto come «ho mangiato altro»; richiamarlo corregge la stima.",
        {"meal_id": _MEAL, "cosa": {"type": "string"}, "niente": {"type": "boolean"}},
        ["meal_id"], CON_AI,
    ),
    "ho_mangiato_questo": _tool(
        t_mangiato_questo,
        "Riempie una casella **vuota** col piatto descritto a parole (ricetta stimata dal modello). "
        "gia_mangiato=false se è oggi e lo mangerai dopo.",
        {"meal_id": _MEAL, "cosa": {"type": "string"}, "gia_mangiato": {"type": "boolean", "default": True}},
        ["meal_id", "cosa"], CON_AI,
    ),
    "sostituisci_pasto": _tool(
        t_sostituisci,
        "Mette al posto del piatto di un pasto (anche già segnato) quello descritto a parole: "
        "ricetta stimata dal modello, come `ho_mangiato_questo`. Il piatto di prima resta nel "
        "ricettario e la dispensa scalata torna com'era. Nel passato il pasto risulta "
        "mangiato; oggi gia_mangiato=false se lo mangerai dopo. Per un pasto «ho mangiato "
        "altro» si corregge la stima con `ho_mangiato_altro`.",
        {"meal_id": _MEAL, "cosa": {"type": "string"}, "gia_mangiato": {"type": "boolean", "default": True}},
        ["meal_id", "cosa"], CON_AI,
    ),
    "modifica_pasto": _tool(
        t_modifica,
        "Corregge il piatto di un pasto senza AI: titolo, procedimento o la lista **completa** "
        "degli ingredienti (leggila prima con `pasto`, poi passala intera con le modifiche). "
        "I macro si ricalcolano dagli ingredienti; vale solo per questo pasto.",
        {
            "meal_id": _MEAL,
            "titolo": {"type": "string"},
            "procedimento": {"type": "string"},
            "ingredienti": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "nome": {"type": "string"},
                        "quantita": {"type": "number", "minimum": 0},
                        "unita": {"type": "string", "description": "g, ml, unità…"},
                        "note": {"type": "string"},
                    },
                    "required": ["nome", "quantita", "unita"],
                },
            },
        },
        ["meal_id"], SCRITTURA,
    ),
    "svuota_pasto": _tool(
        t_svuota,
        "Toglie il piatto da un pasto: la casella torna vuota (e non segnata), la ricetta "
        "resta nel ricettario, la dispensa scalata torna com'era.",
        {"meal_id": _MEAL}, ["meal_id"],
        {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
    ),
    "rigenera_pasto": _tool(
        t_rigenera,
        "Genera una nuova ricetta per un pasto, a scelta del modello o seguendo `richiesta` "
        "(es. «qualcosa con la zucca»). Può richiedere un minuto.",
        {"meal_id": _MEAL, "richiesta": {"type": "string"}},
        ["meal_id"], CON_AI,
    ),
    "scambia_pasti": _tool(
        t_scambia, "Scambia la ricetta di due pasti della stessa settimana.",
        {"meal_id": _MEAL, "altro_meal_id": _MEAL}, ["meal_id", "altro_meal_id"], SCRITTURA,
    ),
    "salta_giorno": _tool(
        t_salta_giorno,
        "Salta un'intera giornata (fuori casa): le sue ricette slittano ai giorni dopo. "
        "saltato=false la rimette.",
        {"day_id": {"type": "integer", "description": "da `settimana`"}, "saltato": {"type": "boolean", "default": True}},
        ["day_id"], SCRITTURA,
    ),
    "registra_peso": _tool(
        t_registra_peso, "Segna il peso di un giorno (default oggi); ripesarsi lo stesso giorno corregge.",
        {"kg": {"type": "number", "minimum": 35, "maximum": 250}, "data": _DATA},
        ["kg"], SCRITTURA,
    ),
    "spunta_spesa": _tool(
        t_spunta_spesa, "Spunta (o toglie la spunta a) un articolo della lista della spesa.",
        {"item_id": {"type": "integer"}, "spuntato": {"type": "boolean", "default": True}},
        ["item_id"], SCRITTURA,
    ),
    "spesa_fatta": _tool(
        t_spesa_fatta, "«Ho fatto la spesa»: gli articoli spuntati passano in dispensa.",
        {}, (), SCRITTURA,
    ),
    "dispensa_aggiungi": _tool(
        t_dispensa_aggiungi, "Aggiunge un alimento alla dispensa.",
        {
            "nome": {"type": "string"},
            "quantita": {"type": "number", "minimum": 0},
            "unita": {"type": "string", "description": "g, ml, unità…"},
            "scadenza": _DATA,
        },
        ["nome"], SCRITTURA,
    ),
    "dispensa_modifica": _tool(
        t_dispensa_modifica, "Cambia quantità, unità o scadenza di una riga della dispensa.",
        {
            "item_id": {"type": "integer"},
            "quantita": {"type": "number", "minimum": 0},
            "unita": {"type": "string"},
            "scadenza": {"type": ["string", "null"], "description": "AAAA-MM-GG, null per toglierla"},
        },
        ["item_id"], SCRITTURA,
    ),
    "dispensa_togli": _tool(
        t_dispensa_togli, "Toglie una riga dalla dispensa.",
        {"item_id": {"type": "integer"}}, ["item_id"],
        {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
    ),
}


# --- Protocollo ---------------------------------------------------------------


def _rpc_ok(id_: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _rpc_err(id_: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _errore(testo: str) -> dict:
    return {"content": [{"type": "text", "text": testo}], "isError": True}


def _gestisci(db: Session, user: User, msg: Any) -> Optional[dict]:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
        return _rpc_err(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")
    if "id" not in msg:  # notifica (notifications/initialized): nessuna risposta
        return None
    metodo, id_ = msg["method"], msg.get("id")
    params = msg.get("params") or {}

    if metodo == "initialize":
        richiesta = params.get("protocolVersion")
        return _rpc_ok(id_, {
            "protocolVersion": richiesta if richiesta in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "dietai", "title": "DietAI", "version": "1.0.0"},
            "instructions": ISTRUZIONI,
        })
    if metodo == "ping":
        return _rpc_ok(id_, {})
    if metodo == "tools/list":
        return _rpc_ok(id_, {"tools": [{"name": n, **d} for n, (_f, d) in TOOLS.items()]})
    if metodo == "tools/call":
        nome = params.get("name")
        if nome not in TOOLS:
            return _rpc_err(id_, -32602, f"Strumento sconosciuto: {nome}")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return _rpc_err(id_, -32602, "arguments deve essere un oggetto")
        try:
            risultato = TOOLS[nome][0](db, user, args)
        except HTTPException as e:
            db.rollback()
            return _rpc_ok(id_, _errore(f"Errore {e.status_code}: {e.detail}"))
        except (ValueError, TypeError) as e:
            db.rollback()
            # Le validazioni Pydantic sono ValueError: il messaggio dice già cosa non va.
            return _rpc_ok(id_, _errore(f"Errore: {e}"))
        except Exception:
            logger.exception("MCP: errore nello strumento %s", nome)
            db.rollback()
            return _rpc_ok(id_, _errore("Errore interno di DietAI, riprova."))
        testo = json.dumps(risultato, ensure_ascii=False, default=str)
        return _rpc_ok(id_, {"content": [{"type": "text", "text": testo}]})
    if metodo in ("resources/list", "prompts/list"):
        chiave = metodo.split("/")[0]
        return _rpc_ok(id_, {chiave: []})
    return _rpc_err(id_, -32601, f"Metodo non supportato: {metodo}")


def _token_valido(request: Request) -> bool:
    atteso = config.MCP_TOKEN
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return False
    return hmac.compare_digest(header[7:].strip().encode(), atteso.encode())


@router.post("/api/mcp", include_in_schema=False)
def mcp_endpoint(request: Request, body: Any = Body(None), db: Session = Depends(get_db)):
    if len(config.MCP_TOKEN) < 32:
        return Response(status_code=404)
    if not _token_valido(request):
        return JSONResponse({"error": "invalid_token"}, status_code=401,
                            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
    user = admin_user(db)
    if not user or not user.is_active:
        return JSONResponse({"error": "nessun amministratore attivo"}, status_code=403)
    if body is None:
        return JSONResponse(_rpc_err(None, -32700, "Parse error"), status_code=400)
    if isinstance(body, list):
        risposte = [r for r in (_gestisci(db, user, m) for m in body) if r is not None]
        return JSONResponse(risposte) if risposte else Response(status_code=202)
    risposta = _gestisci(db, user, body)
    return Response(status_code=202) if risposta is None else JSONResponse(risposta)


@router.get("/api/mcp", include_in_schema=False)
@router.delete("/api/mcp", include_in_schema=False)
def mcp_senza_stream():
    # Nessuno stream dal server e nessuna sessione da chiudere.
    return Response(status_code=405, headers={"Allow": "POST"})
