"""Schemi Pydantic: validano gli input e documentano i contratti dell'API.

Le risposte sono serializzate a mano nei router (dict espliciti): le entità qui in
gioco sono aggregate da più tabelle (pasto + ricetta + ingredienti + macro target) e
un dict costruito nel servizio è più leggibile di dieci schemi annidati.
"""

from pydantic import BaseModel, Field

# ── Auth ───────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    # `str` e non `EmailStr`: l'email qui è solo il nome utente, l'app non manda posta.
    # Con EmailStr un indirizzo come `io@dietai.local` verrebbe rifiutato (i domini
    # .local sono riservati) e l'utente creato dal seed non potrebbe fare login.
    email: str = Field(min_length=3, max_length=255)
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ApiKeyRequest(BaseModel):
    # Le chiavi Anthropic iniziano per "sk-ant-": controllarlo qui evita che l'utente
    # salvi per sbaglio un valore a caso e scopra l'errore solo alla prima generazione.
    api_key: str = Field(min_length=20, max_length=200)


# ── Amministrazione degli account ──────────────────────────────────────────────


class UserCreateRequest(BaseModel):
    """Nuovo account. La password iniziale la sceglie l'amministratore."""

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class UserFlagsUpdate(BaseModel):
    """Interruttori di un account. I campi non passati restano come sono."""

    is_active: bool | None = None
    ai_enabled: bool | None = None


class UserPasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


# ── Dieta ──────────────────────────────────────────────────────────────────────


class MealSlotInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    order: int = Field(ge=0, le=20)
    calories: int = Field(ge=0, le=5000)
    protein_g: float = Field(ge=0, le=500)
    carbs_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=500)
    notes: str | None = None
    # False = lo prepara l'utente, l'AI non deve generarlo. Default True perché le
    # diete lette dal PDF non hanno questa informazione.
    auto_generate: bool = True


class DietMealsUpdate(BaseModel):
    meals: list[MealSlotInput] = Field(min_length=1, max_length=20)


class DailyTargets(BaseModel):
    """I totali del giorno scritti a mano: il lucchetto aperto nel questionario.

    Gli estremi sono larghi apposta — servono a fermare gli zeri e i refusi da tastiera
    (25000 kcal), non a discutere la dieta di chi la sta correggendo.
    """

    calories: int = Field(ge=500, le=6000)
    protein_g: float = Field(ge=0, le=500)
    carbs_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=400)


class QuestionnaireRequest(BaseModel):
    """Le risposte da cui si calcolano calorie e macro, per chi non ha una dieta.

    I valori ammessi per sesso, attività e obiettivo li controlla il router contro
    `utils/nutrition.py`, che è l'unico posto dove sono scritti.
    """

    sex: str = Field(min_length=1, max_length=10)
    age: int = Field(ge=14, le=100)
    height_cm: float = Field(ge=120, le=230)
    weight_kg: float = Field(ge=35, le=250)
    activity: str = Field(min_length=1, max_length=20)
    goal: str = Field(min_length=1, max_length=20)
    # Quanti pasti, per chi non li sceglie uno per uno: `meals` (le chiavi del catalogo)
    # vince quando c'è, ed è la strada che percorre la UI dal secondo passo in poi.
    meals_count: int = Field(default=4, ge=3, le=6)
    meals: list[str] | None = Field(default=None, max_length=12)
    targets: DailyTargets | None = None


# ── Configurazione ─────────────────────────────────────────────────────────────


class IngredientNameRequest(BaseModel):
    ingredient_name: str = Field(min_length=1, max_length=120)


class IngredientCategoryUpdate(BaseModel):
    """Il reparto in cui spostare l'ingrediente. I valori validi li controlla il router."""

    category: str = Field(min_length=1, max_length=20)


class ExcludedCreate(BaseModel):
    ingredient_name: str = Field(min_length=1, max_length=120)
    reason: str | None = Field(default=None, max_length=100)


class PantryCreate(BaseModel):
    ingredient_name: str = Field(min_length=1, max_length=120)
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=20)


class PantryUpdate(BaseModel):
    """Cambia una riga della dispensa. I campi non passati restano come sono."""

    ingredient_name: str | None = Field(default=None, min_length=1, max_length=120)
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=20)


class PreferencesUpdate(BaseModel):
    prefer_seasonal: bool
    prefer_italian: bool
    max_prep_time_min: int | None = Field(default=None, ge=5, le=480)
    budget_level: str | None = None
    # Regole libere ("niente insaccati", "carne max 2 volte a settimana"). Il tetto
    # serve a non far esplodere il prompt: viene rimandato a ogni generazione.
    notes: str | None = Field(default=None, max_length=2000)


class NormalizationRuleCreate(BaseModel):
    """Una regola di normalizzazione dei nomi.

    `kind = "noise"`: `term` è una parola da togliere dal nome ("a filetti").
    `kind = "alias"`: il nome intero `term` diventa `replacement` ("tortiglioni" → "pasta").
    `kind = "off"`: spegne un termine di serie ("sedani", che è anche un ortaggio).
    """

    kind: str = Field(min_length=3, max_length=5)
    term: str = Field(min_length=2, max_length=60)
    replacement: str | None = Field(default=None, max_length=60)


class AiModelsUpdate(BaseModel):
    """Slug del modello per ciascun ruolo. None (o stringa vuota) = default d'ambiente."""

    planning: str | None = Field(default=None, max_length=120)
    chat: str | None = Field(default=None, max_length=120)
    diet: str | None = Field(default=None, max_length=120)


# ── Ricette ────────────────────────────────────────────────────────────────────


class RecipeIngredientInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=20)
    notes: str | None = Field(default=None, max_length=100)


class RecipeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    prep_time_min: int = Field(default=0, ge=0, le=600)
    cook_time_min: int = Field(default=0, ge=0, le=600)
    difficulty: str = "medium"
    instructions: str = Field(min_length=1)
    calories: int = Field(ge=0, le=5000)
    protein_g: float = Field(ge=0, le=500)
    carbs_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=500)
    ingredients: list[RecipeIngredientInput] = Field(default_factory=list)
    tags: dict | None = None


class RatingRequest(BaseModel):
    rating: int = Field(ge=1, le=5)


class FavoriteRequest(BaseModel):
    is_favorite: bool


class SubstituteRequest(BaseModel):
    ingredient_to_replace: str = Field(min_length=1, max_length=120)
    reason: str | None = Field(default=None, max_length=200)
    # Da quale casella del piano arriva la richiesta. Serve perché lo stesso piatto in
    # più giorni è una ricetta sola: senza, sostituire il pollo di lunedì lo
    # sostituirebbe anche giovedì. Assente = si sta modificando il piatto in sé, dal
    # ricettario, e allora vale ovunque.
    meal_id: int | None = None


# ── Pianificazione ─────────────────────────────────────────────────────────────


class RegenerateMealRequest(BaseModel):
    """Cosa vuole l'utente in quella casella, se ha qualcosa da dire.

    Vuoto (o assente) = sceglie il modello, che è come ha sempre funzionato il pulsante.
    Pieno = un'idea, degli ingredienti da usare, un piatto preciso: l'AI ci pesa sopra i
    macro. Il limite è corto apposta — è una richiesta, non una ricetta scritta a mano.
    """

    user_request: str | None = Field(default=None, max_length=500)


class AssignMealRequest(BaseModel):
    """Assegna una ricetta esistente al pasto, oppure ne crea una custom al volo."""

    recipe_id: int | None = None
    recipe: RecipeCreate | None = None


class RecurringRequest(BaseModel):
    is_recurring: bool
    # {"type": "daily"} oppure {"type": "weekly", "day": 5}
    recurring_rule: dict | None = None


class FollowedRequest(BaseModel):
    is_followed: bool
    deviation_notes: str | None = Field(default=None, max_length=500)


class SkipDayRequest(BaseModel):
    is_skipped: bool


# ── Chat ───────────────────────────────────────────────────────────────────────


class ChatMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


# ── Spesa ──────────────────────────────────────────────────────────────────────


class CheckItemRequest(BaseModel):
    is_checked: bool


class BoughtQuantityRequest(BaseModel):
    """Quanto se n'è preso davvero, nell'unità della riga. None = quanto ne serviva."""

    quantity: float | None = Field(default=None, gt=0)


class PaidPriceRequest(BaseModel):
    """Quanto è costato, in euro, per la quantità presa. None = torna al catalogo."""

    paid: float | None = Field(default=None, gt=0, le=10000)
