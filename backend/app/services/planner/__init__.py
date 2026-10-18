"""Pianificazione settimanale: struttura delle settimane e generazione AI.

Il modello mentale: una settimana esiste sempre (lunedì → domenica) e contiene già
una casella per ogni incrocio giorno × pasto della dieta, anche vuota. Generare
significa riempire le caselle libere; rigenerare significa svuotarne una e
richiederla di nuovo. Le caselle "fissate" (pasti ricorrenti e ricette scelte a mano
dall'utente) l'AI non le tocca mai.
"""

# Il modulo era un file solo di duemila righe; ora è un pacchetto, un file per area,
# e qui si rimette insieme quello che il resto dell'app importa da `planner`. Le
# dipendenze vanno in un verso solo: settimane ← stato, pasti, contesto, frequenze ←
# lettura, generazione.
#
# Alcuni nomi i sottomoduli li leggono da qui al momento della chiamata
# (`planner.today()`, `planner.get_client`, `planner.ensure_week_structure`,
# `planner._in_background`), non per nome importato: sono quelli che la suite
# sostituisce sul pacchetto («oggi» fissato a lunedì, il modello finto, un conflitto
# simulato, il thread messo in coda), e una sostituzione deve arrivare ovunque. È la stessa regola per cui `tracking` chiama `planner.today()` e il router
# legge `planner.GENERATION_IN_BACKGROUND`.

from ..ai_client import get_client  # noqa: F401 — la sostituiscono i test, vedi sopra
from .settimane import (  # noqa: F401
    _as_utc, _casella_vissuta, current_week_start, DAY_NAMES, ensure_week_structure,
    get_active_diet, get_or_create_week, meal_slots_of, monday_of, next_week_start,
    realign_to_diet, refresh_week_statuses, require_active_diet, _slot_key, today,
    week_meals, _week_with_structure,
)
from .stato import (  # noqa: F401
    claim_generation, clear_generation_progress, ensure_not_generating,
    _failure_reason, generation_error, generation_outcome, GENERATION_TIMEOUT,
    GenerationProgress, is_generating, record_generation_failure,
    store_generation_outcome,
)
from .pasti import (  # noqa: F401
    apply_recurring_meals, clear_meal_cell, _empty_meal, ensure_not_skipped,
    forget_queued_meal, forget_tracking, _free_cells, _is_fixed, is_generable,
    _overflow_week, skip_day, skip_meal, stop_recurring_forward, unskip_meal,
)
from .contesto import (  # noqa: F401
    _base_names, build_context, cuisine_shares, _excluded_names, _fmt_list,
    _pantry_descriptions, _rated_titles, SCADENZA_VICINA_GIORNI,
)
from .frequenze import (  # noqa: F401
    _batch_groups, diet_frequencies, _foods_in_recipe, frequency_counts,
    frequency_report, is_main_slot,
)
from .lettura import (  # noqa: F401
    serialize_meal, serialize_week,
)
from .generazione import (  # noqa: F401
    _apply_generated_week, generate_week, GENERATION_IN_BACKGROUND, _in_background,
    meal_context_for_chat, _partial_ingredients, regenerate_meal, _run_generation,
    _single_meal_frequencies, _slot_line,
)
