"""Il contesto comune dei prompt: dieta, dispensa, esclusi, regole, cucine, voti."""

import logging

from sqlalchemy.orm import Session

from ...models import (
    BaseIngredient,
    ExcludedIngredient,
    Ingredient,
    PantryItem,
    Recipe,
    UserPreferences,
)
from ...utils import cuisines
from ...utils.seasonality import current_month, current_month_name, in_season
from ...utils.units import format_quantity
from .. import prompts
from ..exclusions import exclusion_rules, recipe_violations
from .settimane import meal_slots_of, require_active_diet
from .. import planner  # per i nomi che i test sostituiscono: vedi __init__

logger = logging.getLogger(__name__)


# ── Contesto per i prompt ──────────────────────────────────────────────────────


def _excluded_names(db: Session, user_id: int) -> list[str]:
    rows = (
        db.query(ExcludedIngredient, Ingredient)
        .outerjoin(Ingredient, Ingredient.id == ExcludedIngredient.ingredient_id)
        .filter(ExcludedIngredient.user_id == user_id)
        .all()
    )
    return [
        ing.name if ing else (exc.custom_name or "")
        for exc, ing in rows
        if ing or exc.custom_name
    ]


def _base_names(db: Session, user_id: int) -> list[str]:
    rows = (
        db.query(Ingredient.name)
        .join(BaseIngredient, BaseIngredient.ingredient_id == Ingredient.id)
        .filter(BaseIngredient.user_id == user_id)
        .all()
    )
    return [r[0] for r in rows]


# Entro quanti giorni una scadenza va detta al modello. Oltre una settimana non
# cambia niente per il piano che si sta generando.
SCADENZA_VICINA_GIORNI = 7


def _pantry_descriptions(db: Session, user_id: int) -> list[str]:
    """La dispensa per il contesto, con prima quello che scade.

    «Da consumare in via prioritaria» vale per tutta la dispensa, ma la ricotta che
    scade dopodomani non pesa quanto il pacco di riso: l'ordine e la scritta accanto
    dicono al modello cosa usare per primo, e in quali giorni (la data c'è apposta,
    perché giovedì è troppo tardi per una cosa che scade martedì). Una scorta già
    scaduta resta in elenco col suo avviso invece di sparire: la lista della spesa la
    conta ancora come presente, e il modello non deve né usarla né ignorarne il nome.
    """
    rows = (
        db.query(PantryItem, Ingredient)
        .join(Ingredient, Ingredient.id == PantryItem.ingredient_id)
        .filter(PantryItem.user_id == user_id)
        .all()
    )
    oggi = planner.today()
    rows.sort(key=lambda r: (r[0].expires_on is None, r[0].expires_on or oggi, r[1].name))
    out = []
    for item, ing in rows:
        voce = ing.name
        if item.quantity_available:
            voce += f" ({format_quantity(item.quantity_available, item.unit or 'unità')})"
        if item.expires_on:
            giorni = (item.expires_on - oggi).days
            data = item.expires_on.strftime("%d/%m")
            if giorni < 0:
                voce += f" — SCADUTA il {data}: non usarla"
            elif giorni <= SCADENZA_VICINA_GIORNI:
                voce += f" — SCADE il {data}: usala per prima, entro quel giorno"
        out.append(voce)
    return out


def _rated_titles(db: Session, user_id: int, high: bool) -> list[str]:
    query = db.query(Recipe).filter(Recipe.user_id == user_id)
    query = (
        query.filter(Recipe.rating >= 4) if high else query.filter(Recipe.rating <= 2)
    )
    recipes = query.order_by(Recipe.id.desc()).limit(15).all()
    if not high:
        return [r.title for r in recipes]
    # Le ricette amate sono modelli da imitare: una che contiene un alimento escluso
    # dopo (un'allergia scoperta tardi) non deve più essere proposta come esempio.
    regole = exclusion_rules(db, user_id)
    if not regole:
        return [r.title for r in recipes]
    return [r.title for r in recipes if not recipe_violations(db, user_id, r.id, regole)]


def _fmt_list(values: list[str], empty: str = "nessuno") -> str:
    values = [v for v in values if v]
    return ", ".join(sorted(set(values))) if values else empty


def cuisine_shares(db: Session, user_id: int) -> dict[str, int]:
    """Le cucine scelte dall'utente con la loro quota. Serve a chi deve sorteggiarle."""
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
    return cuisines.clean(prefs.cuisines if prefs else None)


def build_context(db: Session, user_id: int, *, cuisine: str | None = None) -> str:
    """Il blocco di contesto comune a tutti i prompt di generazione.

    `cuisine` sostituisce la riga delle cucine con una già pronta, e la passa chi ha
    **già sorteggiato**: la generazione della settimana (una cucina per giorno) e la
    rigenerazione di un pasto (una sola). Chi non la passa — le due chat, la
    sostituzione di un ingrediente — se le vede elencate e basta, ed è giusto così:
    lì si parte da una ricetta che una sua cucina ce l'ha già, e sorteggiarne un'altra
    vorrebbe dire riscrivere il piatto invece di correggerlo.
    """
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
        # Non `_fmt_list`, che ordina alfabeticamente: qui l'ordine è la scadenza.
        pantry=", ".join(_pantry_descriptions(db, user_id)) or "vuota",
        # La riga la compone il catalogo: è lì che sta il vincolo che la rende utile
        # — la cucina viaggia, gli ingredienti restano quelli del supermercato sotto
        # casa (vedi `utils/cuisines.prompt_line`).
        cuisine=cuisine or cuisines.prompt_line(prefs.cuisines if prefs else None),
        seasonality=seasonality,
        max_prep=(
            f"{prefs.max_prep_time_min} minuti"
            if prefs and prefs.max_prep_time_min
            else "nessun limite"
        ),
        liked=_fmt_list(_rated_titles(db, user_id, True), "nessuna ancora"),
        disliked=_fmt_list(_rated_titles(db, user_id, False), "nessuna ancora"),
    )
