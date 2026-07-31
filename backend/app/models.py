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
    # Gli account sono più d'uno, ma la API key la mette una persona sola: l'admin è
    # chi paga, e quindi l'unico che sceglie i modelli e vede la schermata della
    # chiave. Gli altri usano la sua chiave e i suoi modelli senza saperlo.
    is_admin = Column(Boolean, nullable=False, default=False, server_default="false")
    # Accesso sospeso: l'account resta con tutti i suoi dati ma non fa più login.
    # È l'alternativa non distruttiva a cancellarlo (che porta via tutto, in CASCADE).
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    # Interruttore delle funzioni AI: spento, l'utente usa l'app — piano, spesa,
    # dispensa, tracking — ma non genera niente. È il freno sulla bolletta di chi
    # mette la chiave, e non tocca nemmeno un dato.
    ai_enabled = Column(Boolean, nullable=False, default=True, server_default="true")
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
    # La categoria decide in che reparto finisce l'ingrediente nella lista della spesa.
    # Quando la sposta l'utente il flag protegge la scelta dal seed, che a ogni avvio
    # riallinea l'anagrafica al catalogo e altrimenti se la rimangerebbe.
    category_by_user = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Mesi di stagionalità: [6,7,8] = giugno-agosto. NULL = disponibile tutto l'anno.
    season_months = Column(JSONType)
    avg_price_per_unit = Column(Float)
    price_unit = Column(String)  # "kg", "l", "unità"
    # Il prezzo del catalogo è una media italiana: al negozio dove fa la spesa
    # l'utente vale poco. Quando lo corregge segnando quanto ha pagato, il flag
    # protegge il suo numero dal seed e dice alla UI che quella cifra è vera.
    price_by_user = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_paid_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "category IN ('frutta','verdura','carne','pesce','latticini','cereali',"
            "'legumi','uova','condimenti','surgelati','bevande','altro')",
            name="ck_ingredient_category",
        ),
    )


class NormalizationRule(Base):
    """Una regola di normalizzazione dei nomi aggiunta a mano.

    Le regole di serie stanno nel codice (`services/ingredients.py`) perché su di esse
    si reggono il catalogo dei prezzi e mezza suite di test. Queste sono le aggiunte
    che si fanno guardando la lista della spesa — «anche "a filetti" è un taglio», «i
    tortiglioni sono pasta» — e chiedono un deploy solo se restano nel codice.

    Non hanno `user_id`: l'anagrafica ingredienti è una sola per tutti, quindi lo sono
    anche le regole che decidono come ci si scrive dentro. Per lo stesso motivo le
    tocca solo l'amministratore.

    `kind = "noise"` → `term` è una parola da togliere dal nome.
    `kind = "alias"` → il nome **intero** `term` diventa `replacement`.
    `kind = "off"`   → un termine **di serie** che smette di valere. Resta scritto nel
    codice (ci poggiano il catalogo dei prezzi e i test): questa riga lo spegne, e
    cancellarla lo riaccende. È così che si toglie "sedani" da pasta senza un deploy —
    è un formato, ma è anche il plurale del sedano.
    """

    __tablename__ = "normalization_rules"

    id = Column(Integer, primary_key=True)
    kind = Column(String, nullable=False)
    # Già normalizzato con le regole di serie quando la riga viene creata: è contro il
    # nome normalizzato che verrà confrontato, e scoprirlo dopo vorrebbe dire avere una
    # regola che non scatta mai.
    term = Column(String, nullable=False)
    replacement = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("kind", "term", name="uq_normalization_rule"),
        CheckConstraint("kind IN ('noise','alias','off')", name="ck_normalization_kind"),
        CheckConstraint(
            "kind <> 'alias' OR replacement IS NOT NULL",
            name="ck_normalization_alias_target",
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
    # Valorizzato mentre una generazione è in corso, NULL quando finisce. Sta nel
    # database e non nel browser perché deve sopravvivere a un cambio pagina e a un
    # ricaricamento: senza, si riparte a premere "Genera" e si paga due volte.
    generation_started_at = Column(DateTime(timezone=True))
    # Diario di bordo della generazione in corso: coda del ragionamento, coda del
    # testo e contatori. Serve solo a far vedere che sta succedendo qualcosa nei
    # minuti in cui il modello scrive. Si azzera insieme a generation_started_at.
    generation_progress = Column(JSONType)
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
    # Cosa è stato tolto dalla dispensa quando il pasto è stato segnato come seguito:
    # [{ingredient_id, name, quantity, unit, label}]. NULL = mai scalato. Serve a due
    # cose: non scalare due volte se si ripreme il pulsante, e rimettere ESATTAMENTE
    # quello che si era tolto se il pasto viene poi corretto in "ho mangiato altro"
    # (la dispensa poteva averne meno di quanto la ricetta ne chiedeva).
    pantry_used = Column(JSONType)
    is_recurring = Column(Boolean, nullable=False, default=False, server_default="false")
    recurring_rule = Column(JSONType)  # {"type":"daily"} | {"type":"weekly","day":5}
    is_followed = Column(Boolean)  # NULL = non ancora tracciato
    deviation_notes = Column(Text)
    # "Ho mangiato altro": il piatto non è stato cucinato e la sua ricetta è finita in
    # fondo alla coda, su un giorno più avanti. La casella conserva `recipe_id` come
    # memoria di cosa c'era in programma, ma non conta più da nessuna parte — spesa,
    # totali del giorno, tracking e generazione la saltano tutti.
    is_skipped = Column(Boolean, nullable=False, default=False, server_default="false")

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


class ShoppingChatMessage(Base):
    """Chat "da supermercato": è legata alla settimana, non a un pasto.

    Serve a cambiare un ingrediente ovunque compaia — non lo trovo, non mi va — e a
    farsi riscrivere tutte le ricette che lo usano in un colpo solo. Per questo vive
    sulla settimana e non su una singola casella.
    """

    __tablename__ = "shopping_chat_messages"

    id = Column(Integer, primary_key=True)
    week_plan_id = Column(
        Integer,
        ForeignKey("week_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="ck_shopping_chat_role"),
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
    # Quando si è detto l'ultima volta "spesa fatta": la lista non si chiude mai — è
    # sempre quello che il piano chiede e la dispensa non copre — ma sapere quand'è
    # stato l'ultimo giro serve a leggere una lista corta senza sospettare un bug.
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
    # Quanto se n'è preso davvero, nella stessa unità: le confezioni non si tagliano a
    # misura, e per 140 g di tacchino si porta a casa il pacco da 400. NULL = ho preso
    # quello che c'era scritto. È questo che finisce in dispensa a spesa fatta.
    bought_quantity = Column(Float)
    estimated_price = Column(Float)

    __table_args__ = (
        UniqueConstraint(
            "shopping_list_id", "ingredient_id", "unit", name="uq_shopping_item"
        ),
    )
