"""Schemi Pydantic: validano gli input e documentano i contratti dell'API.

Le risposte sono serializzate a mano nei router (dict espliciti): le entità qui in
gioco sono aggregate da più tabelle (pasto + ricetta + ingredienti + macro target) e
un dict costruito nel servizio è più leggibile di dieci schemi annidati.
"""

from datetime import date
from urllib.parse import urlsplit

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ── Auth ───────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    # `str` e non `EmailStr`: l'email qui è solo il nome utente, l'app non manda posta.
    # Con EmailStr un indirizzo come `io@dietai.local` verrebbe rifiutato (i domini
    # .local sono riservati) e l'utente creato dal seed non potrebbe fare login.
    email: str = Field(min_length=3, max_length=255)
    # Un tetto anche qui: bcrypt ne legge 72 byte, ma il corpo intero arrivava fino a
    # lui senza limite.
    password: str = Field(max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
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
    # Il pasto che si sta correggendo, se esiste già: l'editor lo rimanda così il
    # salvataggio aggiorna quella riga invece di ricrearla (vedi `update_meals_in_place`).
    id: int | None = None
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
    # Per quante persone si cucina, e per quanti giorni di fila lo stesso piatto.
    servings: int = Field(default=1, ge=1, le=8)
    batch_days: int = Field(default=1, ge=1, le=4)


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
    expires_on: date | None = None


class PantryUpdate(BaseModel):
    """Cambia una riga della dispensa. I campi non passati restano come sono."""

    ingredient_name: str | None = Field(default=None, min_length=1, max_length=120)
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=20)
    expires_on: date | None = None


class PreferencesUpdate(BaseModel):
    prefer_seasonal: bool
    # Le cucine scelte con la loro quota: {"italiana": 70, "giapponese": 30}, chiavi
    # del catalogo (`utils/cuisines.py`). Vuoto = nessuna preferenza, sceglie il
    # modello. Si accetta ancora il semplice elenco della prima versione
    # (`["italiana", "greca"]`), che vale "in parti uguali": è la forma che hanno in
    # archivio le righe mai risalvate, e rifiutarla qui vorrebbe dire non poter più
    # salvare le preferenze senza prima toccare le cucine. Le quote le normalizza
    # `cuisines.clean()`, che le riporta a somma 100.
    cuisines: dict[str, float] | list[str] = Field(default_factory=dict)
    max_prep_time_min: int | None = Field(default=None, ge=5, le=480)
    # Regole libere ("niente insaccati", "carne max 2 volte a settimana"). Il tetto
    # serve a non far esplodere il prompt: viene rimandato a ogni generazione.
    notes: str | None = Field(default=None, max_length=2000)


class NormalizationRuleCreate(BaseModel):
    """Una regola di normalizzazione dei nomi.

    `kind = "noise"`: `term` è una parola da togliere dal nome ("a filetti").
    `kind = "alias"`: il nome intero `term` diventa `replacement` ("tortiglioni" → "pasta").
    `kind = "off"`: spegne un termine di serie ("sedani", che è anche un ortaggio).
    """

    kind: Literal["noise", "alias", "off"]
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
    # Tetti anche sui testi: finiscono nei prompt a ogni generazione (le ricette amate
    # sono esempi), e un procedimento da 5 MB passava.
    description: str | None = Field(default=None, max_length=1000)
    prep_time_min: int = Field(default=0, ge=0, le=600)
    cook_time_min: int = Field(default=0, ge=0, le=600)
    # Un valore fuori elenco era un IntegrityError sul CHECK del database, cioè un 500.
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    instructions: str = Field(min_length=1, max_length=10000)
    calories: int = Field(ge=0, le=5000)
    protein_g: float = Field(ge=0, le=500)
    carbs_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=500)
    # Facoltativi: chi scrive una ricetta a mano spesso sa i macro e non le fibre.
    # Vuoto vuol dire "non lo so", non zero.
    fiber_g: float | None = Field(default=None, ge=0, le=500)
    sugar_g: float | None = Field(default=None, ge=0, le=1000)
    saturated_fat_g: float | None = Field(default=None, ge=0, le=500)
    alcohol_g: float | None = Field(default=None, ge=0, le=500)
    caffeine_mg: float | None = Field(default=None, ge=0, le=2000)
    ingredients: list[RecipeIngredientInput] = Field(default_factory=list, max_length=60)
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


class GenerateWeekRequest(BaseModel):
    """Cosa generare della settimana: quali giorni, quali pasti, e se rifare i pieni.

    Corpo assente (o campi a `None`) = tutta la settimana, che è come ha sempre
    funzionato il pulsante e come chiamano ancora i test. Con la selezione della
    dialog si paga una chiamata sola sui soli pasti spuntati: chi la colazione se la
    prepara da sé non deve pagarne sette.

    I valori si validano solo nei limiti (giorni 0-6, liste corte): `days` e `slot_ids`
    sono filtri, quindi uno slot che non esiste semplicemente non seleziona niente. Una lista **vuota** però
    è una scelta esplicita — "nessun giorno" — e vale come tale: il servizio risponde
    che nella selezione non c'è niente da generare invece di rifare tutto.
    """

    regenerate_all: bool = False
    # `day_of_week`, da 0 (lunedì) a 6 (domenica). I limiti non cambiano cosa vuol dire
    # la selezione: tengono fuori solo liste che nessuna dialog manda.
    days: list[Annotated[int, Field(ge=0, le=6)]] | None = Field(default=None, max_length=7)
    slot_ids: list[int] | None = Field(default=None, max_length=20)


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

    @model_validator(mode="after")
    def _una_sola_fonte(self):
        if (self.recipe_id is None) == (self.recipe is None):
            raise ValueError("Serve recipe_id oppure una ricetta completa, non tutti e due")
        return self


class RecurringRule(BaseModel):
    # Era un dict libero: {"day": "x"} dava 500 e {"day": 9} passava, e quel fisso
    # non si ricopiava mai più senza dire niente.
    type: Literal["daily", "weekly"]
    day: int | None = Field(default=None, ge=0, le=6)


class RecurringRequest(BaseModel):
    is_recurring: bool
    # {"type": "daily"} oppure {"type": "weekly", "day": 5}
    recurring_rule: RecurringRule | None = None


class SwapMealRequest(BaseModel):
    """Il pasto con cui scambiare la ricetta: della stessa settimana."""

    other_meal_id: int


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


class DietFrequency(BaseModel):
    food: str = Field(max_length=40)
    min: int = Field(default=0, ge=0, le=21)
    max: int | None = Field(default=None, ge=0, le=21)


class DietFrequenciesUpdate(BaseModel):
    frequencies: list[DietFrequency] = Field(default_factory=list, max_length=20)


class WeightEntryIn(BaseModel):
    # Gli stessi limiti del questionario: una pesata fuori da lì diventava il
    # riferimento del ricalcolo proposto, che poi rimbalzava sul questionario con 422.
    weight_kg: float = Field(ge=35, le=250)
    day: date | None = None


class EatenInsteadRequest(BaseModel):
    text: str | None = Field(default=None, max_length=500)
    # «Non ho mangiato niente»: una risposta, non un buco. Zero noto, senza chiedere
    # al modello di stimare il nulla.
    nothing: bool = False


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


# I servizi push dei browser: Chrome/Edge/Android (FCM), Safari e iOS (Apple),
# Firefox (Mozilla), Edge legacy (WNS). L'endpoint arriva dal browser, ma il server ci
# fa una POST: con una stringa libera un utente poteva far chiamare al backend un
# indirizzo della rete interna (SSRF), e `/push/test` diceva se aveva risposto.
PUSH_HOSTS = (
    "fcm.googleapis.com",
    "push.apple.com",
    "push.services.mozilla.com",
    "notify.windows.com",
)


class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    keys: PushKeys

    @field_validator("endpoint")
    @classmethod
    def _servizio_push(cls, value: str) -> str:
        parti = urlsplit(value)
        host = (parti.hostname or "").lower()
        if parti.scheme != "https" or not any(
            host == h or host.endswith("." + h) for h in PUSH_HOSTS
        ):
            raise ValueError("Indirizzo di notifica non riconosciuto")
        return value


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)


class ReminderUpdate(BaseModel):
    time: str | None = Field(default=None, max_length=5)
