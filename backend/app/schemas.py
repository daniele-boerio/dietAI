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


# ── Configurazione ─────────────────────────────────────────────────────────────


class IngredientNameRequest(BaseModel):
    ingredient_name: str = Field(min_length=1, max_length=120)


class ExcludedCreate(BaseModel):
    ingredient_name: str = Field(min_length=1, max_length=120)
    reason: str | None = Field(default=None, max_length=100)


class PantryCreate(BaseModel):
    ingredient_name: str = Field(min_length=1, max_length=120)
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=20)


class PantryUpdate(BaseModel):
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=20)


class PreferencesUpdate(BaseModel):
    prefer_seasonal: bool
    prefer_italian: bool
    max_prep_time_min: int | None = Field(default=None, ge=5, le=480)
    budget_level: str | None = None


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


# ── Pianificazione ─────────────────────────────────────────────────────────────


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


# ── Chat ───────────────────────────────────────────────────────────────────────


class ChatMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


# ── Spesa ──────────────────────────────────────────────────────────────────────


class CheckItemRequest(BaseModel):
    is_checked: bool
