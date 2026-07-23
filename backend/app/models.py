"""Modelli SQLAlchemy.

L'app è single-user, ma ogni tabella che contiene dati personali porta comunque
`user_id`: è quello che permette di riusare lo schema se un giorno gli utenti
diventano due, ed è il filtro obbligatorio in ogni query (vedi CLAUDE.md).
"""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from .database import Base

# In produzione gira Postgres e vogliamo JSONB (indicizzabile, più compatto); nei test
# gira SQLite, che JSONB non ce l'ha. La variante lascia allo stesso modello entrambe
# le strade, senza duplicare la definizione delle tabelle.
JSONType = JSON().with_variant(JSONB, "postgresql")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    # Incrementandola si invalidano di colpo tutti gli access token già emessi
    # (es. al cambio password), senza dover aspettare la loro scadenza.
    token_version = Column(Integer, nullable=False, default=1, server_default="1")
    # API key Claude cifrata (Fernet). NULL finché l'utente non la inserisce:
    # senza, tutte le funzioni AI sono spente.
    claude_api_key_enc = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    """Sessione persistente per dispositivo. In DB solo l'hash del token."""

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash = Column(String, unique=True, nullable=False, index=True)
    # I token nati da rotazioni successive condividono la famiglia: se ne viene
    # riusato uno vecchio, si revoca l'intera catena.
    family_id = Column(String, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    used_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    user_agent = Column(String)


# ─────────────────────────── Dieta ───────────────────────────


class DietPlan(Base):
    """La dieta del nutrizionista, come estratta dal PDF.

    `parsed_data` conserva il JSON grezzo restituito dall'AI: i macro "veri" sono
    quelli in `meal_slots` (modificabili a mano dall'utente), ma tenere l'originale
    permette di capire cosa aveva letto l'AI quando qualcosa non torna.
    """

    __tablename__ = "diet_plans"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename = Column(String)
    parsed_data = Column(JSONType, nullable=False)
    total_daily_calories = Column(Integer, nullable=False)
    notes = Column(Text)
    # Una sola dieta attiva per utente: caricarne una nuova disattiva la precedente
    # invece di cancellarla, così lo storico dei piani resta leggibile.
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MealSlot(Base):
    """Un pasto della giornata secondo la dieta (Colazione, Pranzo, ...) con i suoi target."""

    __tablename__ = "meal_slots"

    id = Column(Integer, primary_key=True)
    diet_plan_id = Column(
        Integer,
        ForeignKey("diet_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    order_index = Column(Integer, nullable=False)
    target_calories = Column(Integer, nullable=False)
    target_protein_g = Column(Float, nullable=False)
    target_carbs_g = Column(Float, nullable=False)
    target_fat_g = Column(Float, nullable=False)
    notes = Column(Text)
    # False = "questo pasto lo gestisco io": l'AI non lo genera mai, ma i suoi macro
    # contano lo stesso nella giornata, perché l'utente lo mangia comunque centrando
    # i target. Senza questa seconda parte il tracking mostrerebbe un buco.
    auto_generate = Column(Boolean, nullable=False, default=True, server_default="true")

    __table_args__ = (
        UniqueConstraint("diet_plan_id", "order_index", name="uq_meal_slot_order"),
    )


# ─────────────────────────── Ingredienti ───────────────────────────

INGREDIENT_CATEGORIES = (
    "frutta",
    "verdura",
    "carne",
    "pesce",
    "latticini",
    "cereali",
    "legumi",
    "uova",
    "condimenti",
    "surgelati",
    "bevande",
    "altro",
)


class Ingredient(Base):
    """Anagrafica ingredienti, condivisa da ricette, dispensa e lista della spesa.

    `name` è normalizzato in minuscolo dal servizio che li crea: senza, "Zucchine" e
    "zucchine" diventerebbero due righe distinte nella lista della spesa.
    """

    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    category = Column(String, nullable=False, default="altro", server_default="altro")
    # Mesi di stagionalità: [6,7,8] = giugno-agosto. NULL = disponibile tutto l'anno.
    season_months = Column(JSONType)
    avg_price_per_unit = Column(Float)
    price_unit = Column(String)  # "kg", "l", "unità"

    __table_args__ = (
        CheckConstraint(
            "category IN ('frutta','verdura','carne','pesce','latticini','cereali',"
            "'legumi','uova','condimenti','surgelati','bevande','altro')",
            name="ck_ingredient_category",
        ),
    )


# ─────────────────────────── Ricette ───────────────────────────


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String, nullable=False)
    description = Column(Text)
    prep_time_min = Column(Integer, nullable=False, default=0, server_default="0")
    cook_time_min = Column(Integer, nullable=False, default=0, server_default="0")
    difficulty = Column(String, nullable=False, default="medium", server_default="medium")
    instructions = Column(Text, nullable=False)  # markdown, passo passo
    calories = Column(Integer, nullable=False)
    protein_g = Column(Float, nullable=False)
    carbs_g = Column(Float, nullable=False)
    fat_g = Column(Float, nullable=False)
    # {"cuisine": "italiana", "season": ["estate"], "type": "primo"}
    tags = Column(JSONType)
    rating = Column(Integer)  # 1-5, NULL = non votata
    is_favorite = Column(Boolean, nullable=False, default=False, server_default="false")
    is_custom = Column(Boolean, nullable=False, default=False, server_default="false")
    generation_prompt = Column(Text)  # utile per capire perché è uscita così
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "difficulty IN ('easy','medium','hard')", name="ck_recipe_difficulty"
        ),
        CheckConstraint(
            "rating IS NULL OR (rating >= 1 AND rating <= 5)", name="ck_recipe_rating"
        ),
    )


class RecipeIngredient(Base):
    """Un ingrediente dentro una ricetta, con quantità per UNA persona."""

    __tablename__ = "recipe_ingredients"

    id = Column(Integer, primary_key=True)
    recipe_id = Column(
        Integer,
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ingredient_id = Column(
        Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False
    )
    quantity = Column(Float, nullable=False)
    unit = Column(String, nullable=False)  # "g", "ml", "unità", "cucchiai", ...
    notes = Column(String)  # "a dadini", "tritato", ...


# ─────────────────────────── Pianificazione ───────────────────────────


class WeekPlan(Base):
    """Una settimana di pasti. `week_start_date` è sempre un lunedì."""

    __tablename__ = "week_plans"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_start_date = Column(Date, nullable=False)
    status = Column(String, nullable=False, default="draft", server_default="draft")
    is_locked = Column(Boolean, nullable=False, default=False, server_default="false")
    locked_at = Column(DateTime(timezone=True))
    lock_expires_at = Column(DateTime(timezone=True))
    # Valorizzato mentre una generazione è in corso, NULL quando finisce. Sta nel
    # database e non nel browser perché deve sopravvivere a un cambio pagina e a un
    # ricaricamento: senza, si riparte a premere "Genera" e si paga due volte.
    generation_started_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "week_start_date", name="uq_week_plan_user_week"),
        CheckConstraint(
            "status IN ('draft','active','locked','archived')", name="ck_week_status"
        ),
    )


class DayPlan(Base):
    __tablename__ = "day_plans"

    id = Column(Integer, primary_key=True)
    week_plan_id = Column(
        Integer,
        ForeignKey("week_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date = Column(Date, nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0 = lunedì, 6 = domenica
    # Giorno passato senza che la spesa fosse fatta: quello che c'era in piano non è
    # stato cucinato. Le sue ricette slittano in avanti e il giorno esce dalla lista
    # della spesa, dalla generazione e dal tracking.
    is_skipped = Column(Boolean, nullable=False, default=False, server_default="false")

    __table_args__ = (
        UniqueConstraint("week_plan_id", "date", name="uq_day_plan_date"),
    )


class PlannedMeal(Base):
    """L'incrocio giorno × pasto: qui vive la ricetta assegnata (o il buco da riempire).

    Una riga esiste per ogni coppia (giorno, meal_slot) anche prima della generazione,
    con `recipe_id` a NULL: è quello che permette alla griglia settimanale di mostrare
    subito la struttura della dieta e all'AI di sapere quali caselle deve riempire.
    """

    __tablename__ = "planned_meals"

    id = Column(Integer, primary_key=True)
    day_plan_id = Column(
        Integer,
        ForeignKey("day_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    meal_slot_id = Column(
        Integer, ForeignKey("meal_slots.id", ondelete="CASCADE"), nullable=False
    )
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="SET NULL"))
    source = Column(
        String, nullable=False, default="ai_generated", server_default="ai_generated"
    )
    # Un pasto ricorrente non viene rigenerato: viene ricopiato ogni settimana.
    is_recurring = Column(Boolean, nullable=False, default=False, server_default="false")
    recurring_rule = Column(JSONType)  # {"type":"daily"} | {"type":"weekly","day":5}
    is_followed = Column(Boolean)  # NULL = non ancora tracciato
    deviation_notes = Column(Text)
    # "Ho mangiato altro": il piatto non è stato cucinato e la sua ricetta è finita in
    # fondo alla coda, su un giorno più avanti. La casella conserva `recipe_id` come
    # memoria di cosa c'era in programma, ma non conta più da nessuna parte — spesa,
    # totali del giorno, tracking e generazione la saltano tutti.
    is_skipped = Column(Boolean, nullable=False, default=False, server_default="false")
    # Ricetta arrivata qui traboccando dalla settimana precedente, che slittava. Se lo
    # slittamento si ripete il giorno dopo, va rimessa in coda insieme alle altre:
    # senza questo flag la ricetta di sabato le passerebbe davanti.
    is_shifted = Column(Boolean, nullable=False, default=False, server_default="false")

    __table_args__ = (
        UniqueConstraint("day_plan_id", "meal_slot_id", name="uq_planned_meal"),
        CheckConstraint(
            "source IN ('ai_generated','user_custom','from_favorites')",
            name="ck_planned_meal_source",
        ),
    )


class MealChatMessage(Base):
    """Messaggio della chat contestuale su un singolo pasto."""

    __tablename__ = "meal_chat_messages"

    id = Column(Integer, primary_key=True)
    planned_meal_id = Column(
        Integer,
        ForeignKey("planned_meals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="ck_chat_role"),
    )


# ─────────────────────────── Configurazione utente ───────────────────────────


class BaseIngredient(Base):
    """Ingredienti sempre in casa (sale, olio, spezie): non entrano nella lista spesa."""

    __tablename__ = "base_ingredients"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ingredient_id = Column(
        Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "ingredient_id", name="uq_base_ingredient"),
    )


class ExcludedIngredient(Base):
    """Ingredienti da non usare MAI (allergie, intolleranze, gusti).

    `custom_name` copre i casi che non sono un singolo ingrediente dell'anagrafica
    ("frutti di mare", "roba piccante"): in quel caso `ingredient_id` resta NULL e il
    nome libero viene passato all'AI così com'è.
    """

    __tablename__ = "excluded_ingredients"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ingredient_id = Column(Integer, ForeignKey("ingredients.id", ondelete="CASCADE"))
    custom_name = Column(String)
    reason = Column(String)  # "allergia", "intolleranza", "non piace"

    __table_args__ = (
        CheckConstraint(
            "ingredient_id IS NOT NULL OR custom_name IS NOT NULL",
            name="ck_excluded_has_name",
        ),
    )


class PantryItem(Base):
    """Dispensa virtuale: quantità già in casa, sottratte dalla lista della spesa."""

    __tablename__ = "pantry_items"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ingredient_id = Column(
        Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False
    )
    quantity_available = Column(Float)
    unit = Column(String)

    __table_args__ = (
        UniqueConstraint("user_id", "ingredient_id", name="uq_pantry_item"),
    )


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    prefer_seasonal = Column(Boolean, nullable=False, default=True, server_default="true")
    prefer_italian = Column(Boolean, nullable=False, default=True, server_default="true")
    max_prep_time_min = Column(Integer)
    budget_level = Column(String)  # "economico", "medio", "premium"
    # Regole in linguaggio naturale che non stanno in una lista: "niente insaccati",
    # "carne al massimo due volte a settimana", "la domenica mangio fuori". Vanno nel
    # prompt così come sono — il destinatario è un modello, non un parser.
    notes = Column(Text)
    # Modello scelto per ciascun ruolo (slug del provider, es. "anthropic/claude-opus-4-8").
    # NULL = si usa il default dell'ambiente. Sono qui e non in configurazione perché
    # cambiarli è una decisione di tutti i giorni — costo contro qualità — non di deploy.
    ai_model_planning = Column(String)
    ai_model_chat = Column(String)
    ai_model_diet = Column(String)


# ─────────────────────────── Lista della spesa ───────────────────────────


class ShoppingList(Base):
    __tablename__ = "shopping_lists"

    id = Column(Integer, primary_key=True)
    week_plan_id = Column(
        Integer,
        ForeignKey("week_plans.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    is_completed = Column(Boolean, nullable=False, default=False, server_default="false")
    completed_at = Column(DateTime(timezone=True))
    estimated_cost = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"

    id = Column(Integer, primary_key=True)
    shopping_list_id = Column(
        Integer,
        ForeignKey("shopping_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ingredient_id = Column(
        Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False
    )
    total_quantity = Column(Float, nullable=False)
    unit = Column(String, nullable=False)
    is_checked = Column(Boolean, nullable=False, default=False, server_default="false")
    estimated_price = Column(Float)

    __table_args__ = (
        UniqueConstraint(
            "shopping_list_id", "ingredient_id", "unit", name="uq_shopping_item"
        ),
    )
