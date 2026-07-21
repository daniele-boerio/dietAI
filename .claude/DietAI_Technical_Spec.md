# DietAI — Specifica Tecnica per Implementazione

> **Scopo di questo documento**: specifica tecnica completa per la generazione del progetto DietAI con Claude Code. Ogni sezione contiene indicazioni implementative precise: struttura cartelle, modelli dati, endpoint API, componenti frontend, prompt AI e regole di business.

---

## 1. Overview del Progetto

**DietAI** è una webapp single-user per la gestione della dieta, generazione automatica di ricette con AI e compilazione della lista della spesa settimanale.

### Flusso principale

1. L'utente carica un PDF della dieta dal nutrizionista → il sistema lo parsa con Claude AI ed estrae i pasti e i macro
2. L'utente configura: ingredienti di base, alimenti esclusi, dispensa, preferenze (stagionalità, cucina italiana)
3. Il sistema genera un piano settimanale di ricette che rispettano i vincoli nutrizionali
4. L'utente può rigenerare, modificare via chat, votare, salvare tra i preferiti o forzare ricette custom
5. La lista della spesa si compila automaticamente dagli ingredienti delle ricette
6. Quando l'utente fa la spesa, il piano si blocca per 7 giorni (nessuna modifica alle ricette)
7. In parallelo viene mostrata l'anteprima della settimana successiva (modificabile)

### Vincoli chiave

- **Single-user**: un solo utente, autenticazione obbligatoria perché protegge la API key Claude
- **Porzioni**: sempre per 1 persona
- **Cucina**: preferenza forte per ricette italiane
- **API key Claude**: dell'utente, salvata crittografata nel DB, usata server-side

---

## 2. Tech Stack

| Layer | Tecnologia | Versione |
|---|---|---|
| **Frontend** | React + TypeScript | 18.x / 19.x |
| **Build tool** | Vite | 5.x |
| **State management** | Redux Toolkit + RTK Query | 2.x |
| **UI** | Tailwind CSS + shadcn/ui | 3.x / latest |
| **Routing** | React Router | 7.x |
| **Backend** | Python + FastAPI | 3.12+ / 0.110+ |
| **ORM** | SQLAlchemy 2.0 (async) | 2.x |
| **Migrazioni** | Alembic | 1.x |
| **Database** | PostgreSQL | 16 |
| **Auth** | JWT (python-jose) + bcrypt (passlib) | — |
| **AI** | Anthropic Claude API (SDK Python) | anthropic 0.40+ |
| **PDF parsing** | Claude Vision API (PDF come immagine/documento) | — |
| **Containerizzazione** | Docker + Docker Compose | — |
| **Validazione** | Pydantic v2 (backend), Zod (frontend) | — |

---

## 3. Struttura del Progetto

```
dietai/
├── docker-compose.yml
├── .env.example
├── README.md
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app factory
│   │   ├── config.py                  # Settings (pydantic-settings)
│   │   ├── database.py                # Async engine, session factory
│   │   ├── dependencies.py            # Dependency injection (get_db, get_current_user)
│   │   │
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── router.py              # POST /login, /refresh, /logout
│   │   │   ├── service.py             # Hash/verify password, create/decode JWT
│   │   │   └── schemas.py             # LoginRequest, TokenResponse
│   │   │
│   │   ├── diet/
│   │   │   ├── __init__.py
│   │   │   ├── router.py              # Upload PDF, get/update diet
│   │   │   ├── service.py             # Parse PDF via Claude, CRUD diet
│   │   │   ├── schemas.py             # DietCreate, DietResponse, MealSlotSchema
│   │   │   └── prompts.py             # Prompt template per parsing PDF
│   │   │
│   │   ├── planning/
│   │   │   ├── __init__.py
│   │   │   ├── router.py              # Week plans, day plans, meals
│   │   │   ├── service.py             # Generate week plan, lock, regenerate
│   │   │   ├── schemas.py             # WeekPlanResponse, DayPlanResponse, PlannedMealResponse
│   │   │   └── prompts.py             # Prompt templates per generazione ricette
│   │   │
│   │   ├── recipes/
│   │   │   ├── __init__.py
│   │   │   ├── router.py              # CRUD ricette, rate, favorite, substitute
│   │   │   ├── service.py             # Recipe logic, AI substitution
│   │   │   └── schemas.py             # RecipeCreate, RecipeResponse, RecipeFilter
│   │   │
│   │   ├── shopping/
│   │   │   ├── __init__.py
│   │   │   ├── router.py              # Shopping list, export, cost estimate
│   │   │   ├── service.py             # Aggregate ingredients, subtract pantry
│   │   │   └── schemas.py             # ShoppingListResponse, CostEstimate
│   │   │
│   │   ├── chat/
│   │   │   ├── __init__.py
│   │   │   ├── router.py              # POST message, GET history
│   │   │   ├── service.py             # Claude chat, context building
│   │   │   └── schemas.py             # ChatMessage, ChatHistory
│   │   │
│   │   ├── config_module/             # "config" è riservato Python
│   │   │   ├── __init__.py
│   │   │   ├── router.py              # Base ingredients, excluded, pantry, preferences
│   │   │   ├── service.py             # CRUD per ogni sezione
│   │   │   └── schemas.py             # BaseIngredientSchema, ExcludedSchema, PantrySchema
│   │   │
│   │   ├── tracking/
│   │   │   ├── __init__.py
│   │   │   ├── router.py              # GET weekly tracking data
│   │   │   ├── service.py             # Calcolo macro pianificati vs target
│   │   │   └── schemas.py             # TrackingWeekResponse
│   │   │
│   │   ├── ai/
│   │   │   ├── __init__.py
│   │   │   ├── client.py              # Wrapper Anthropic SDK, decrypt API key, retry logic
│   │   │   ├── prompts.py             # System prompts condivisi, builder contesto
│   │   │   └── response_parser.py     # Parse JSON da risposta AI, validazione, retry
│   │   │
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── diet.py
│   │   │   ├── planning.py
│   │   │   ├── recipe.py
│   │   │   ├── ingredient.py
│   │   │   ├── shopping.py
│   │   │   ├── chat.py
│   │   │   └── config.py              # BaseIngredient, ExcludedIngredient, PantryItem, Preferences
│   │   │
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── crypto.py              # AES-256 encrypt/decrypt per API key
│   │       ├── seasonality.py         # Tabella stagionalità prodotti italiani
│   │       └── pricing.py             # Database prezzi medi ingredienti
│   │
│   └── tests/
│       ├── conftest.py
│       ├── test_auth.py
│       ├── test_diet.py
│       ├── test_planning.py
│       └── ...
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── index.html
│   │
│   ├── public/
│   │
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── routes.tsx                 # Route definitions
│       │
│       ├── store/
│       │   ├── index.ts               # configureStore
│       │   ├── api.ts                 # RTK Query baseApi (con JWT injection)
│       │   ├── authSlice.ts
│       │   ├── dietApi.ts             # RTK Query endpoints dieta
│       │   ├── planningApi.ts         # RTK Query endpoints planning
│       │   ├── recipesApi.ts
│       │   ├── shoppingApi.ts
│       │   ├── chatApi.ts
│       │   ├── configApi.ts
│       │   └── trackingApi.ts
│       │
│       ├── components/
│       │   ├── ui/                    # shadcn/ui components
│       │   ├── layout/
│       │   │   ├── AppLayout.tsx       # Sidebar + header + main
│       │   │   ├── Sidebar.tsx
│       │   │   └── Header.tsx
│       │   ├── planning/
│       │   │   ├── WeekGrid.tsx        # Griglia 7 colonne × N pasti
│       │   │   ├── DayColumn.tsx       # Colonna singolo giorno
│       │   │   ├── MealCard.tsx        # Card pasto con azioni rapide
│       │   │   └── MealDetailSheet.tsx # Pannello dettaglio pasto
│       │   ├── recipes/
│       │   │   ├── RecipeDetail.tsx     # Vista completa ricetta
│       │   │   ├── RecipeCard.tsx       # Card ricetta per liste
│       │   │   ├── RecipeFilters.tsx
│       │   │   └── RatingStars.tsx
│       │   ├── shopping/
│       │   │   ├── ShoppingList.tsx     # Lista raggruppata per categoria
│       │   │   ├── ShoppingItem.tsx
│       │   │   └── CostSummary.tsx
│       │   ├── chat/
│       │   │   ├── MealChat.tsx         # Chat contestuale per pasto
│       │   │   ├── ChatMessage.tsx
│       │   │   └── ChatInput.tsx
│       │   ├── tracking/
│       │   │   ├── MacroGauge.tsx       # Indicatore singolo macro
│       │   │   ├── NutritionChart.tsx   # Grafico settimanale
│       │   │   └── DayComplianceRow.tsx
│       │   ├── config/
│       │   │   ├── IngredientManager.tsx # CRUD ingredienti (base/esclusi/dispensa)
│       │   │   └── PreferencesForm.tsx
│       │   └── common/
│       │       ├── LoadingSkeleton.tsx
│       │       ├── ConfirmDialog.tsx
│       │       └── EmptyState.tsx
│       │
│       ├── pages/
│       │   ├── LoginPage.tsx
│       │   ├── DashboardPage.tsx
│       │   ├── PlanningPage.tsx         # Settimana corrente
│       │   ├── PlanningNextPage.tsx     # Settimana successiva
│       │   ├── MealDetailPage.tsx       # Ricetta + chat + azioni
│       │   ├── ShoppingPage.tsx
│       │   ├── RecipesPage.tsx          # Archivio/ricettario
│       │   ├── RecipeDetailPage.tsx
│       │   ├── TrackingPage.tsx
│       │   ├── SettingsDietPage.tsx
│       │   ├── SettingsBasePage.tsx
│       │   ├── SettingsExcludedPage.tsx
│       │   ├── SettingsPantryPage.tsx
│       │   └── SettingsPreferencesPage.tsx
│       │
│       ├── hooks/
│       │   ├── useAuth.ts
│       │   ├── useWeekPlan.ts
│       │   └── useRecipeActions.ts
│       │
│       ├── types/
│       │   └── index.ts                # TypeScript interfaces (mirror Pydantic schemas)
│       │
│       └── lib/
│           ├── utils.ts                # cn(), formatters
│           └── constants.ts            # Meal categories, difficulty levels, etc.
│
└── docs/
    └── TECHNICAL_SPEC.md              # Questo file
```

---

## 4. Configurazione e Environment

### `.env.example`

```env
# Database
DATABASE_URL=postgresql+asyncpg://dietai:dietai@db:5432/dietai

# Auth
JWT_SECRET_KEY=<genera-un-secret-sicuro-256-bit>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Encryption (per API key Claude)
ENCRYPTION_KEY=<genera-una-chiave-AES-256-base64>

# App
APP_ENV=development
CORS_ORIGINS=http://localhost:5173

# Seed user (creato al primo avvio)
SEED_USER_EMAIL=daniele@dietai.local
SEED_USER_PASSWORD=<password-iniziale>
```

> **NOTA**: La API key Claude NON va nel `.env`. Viene inserita dall'utente via UI dopo il login e salvata crittografata nel DB.

### `docker-compose.yml`

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: dietai
      POSTGRES_PASSWORD: dietai
      POSTGRES_DB: dietai
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  backend:
    build: ./backend
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      - db
    volumes:
      - ./backend:/app

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    depends_on:
      - backend
    volumes:
      - ./frontend:/app
      - /app/node_modules

volumes:
  pgdata:
```

---

## 5. Modelli Database (SQLAlchemy 2.0)

Usa il pattern Mapped column di SQLAlchemy 2.0 con async. Tutti i modelli ereditano da una `Base` comune con `id` UUID auto-generato e `created_at`/`updated_at`.

### Base model

```python
# app/models/base.py
import uuid
from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

class Base(DeclarativeBase):
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

### User

```python
class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    claude_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # API key Claude crittografata con AES-256. Null finché l'utente non la inserisce.
```

### DietPlan

```python
class DietPlan(Base):
    __tablename__ = "diet_plans"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    original_pdf: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    parsed_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # parsed_data contiene il JSON strutturato estratto dal PDF:
    # {
    #   "notes": "...",
    #   "daily_calories": 2000,
    #   "meals": [
    #     {"name": "Colazione", "order": 0, "calories": 400, "protein_g": 20, "carbs_g": 50, "fat_g": 15},
    #     {"name": "Spuntino", "order": 1, ...},
    #     ...
    #   ]
    # }
    total_daily_calories: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="diet_plans")
    meal_slots: Mapped[list["MealSlot"]] = relationship(back_populates="diet_plan", cascade="all, delete-orphan")
```

### MealSlot

```python
class MealSlot(Base):
    __tablename__ = "meal_slots"

    diet_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diet_plans.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Colazione", "Pranzo", ecc.
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    target_calories: Mapped[int] = mapped_column(Integer, nullable=False)
    target_protein_g: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False)
    target_carbs_g: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False)
    target_fat_g: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False)

    diet_plan: Mapped["DietPlan"] = relationship(back_populates="meal_slots")
```

### WeekPlan

```python
class WeekPlanStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    LOCKED = "locked"
    ARCHIVED = "archived"

class WeekPlan(Base):
    __tablename__ = "week_plans"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)  # Sempre un lunedì
    status: Mapped[WeekPlanStatus] = mapped_column(
        SQLEnum(WeekPlanStatus), default=WeekPlanStatus.DRAFT
    )
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="week_plans")
    day_plans: Mapped[list["DayPlan"]] = relationship(back_populates="week_plan", cascade="all, delete-orphan")
```

### DayPlan

```python
class DayPlan(Base):
    __tablename__ = "day_plans"

    week_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("week_plans.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Lunedì, 6=Domenica

    week_plan: Mapped["WeekPlan"] = relationship(back_populates="day_plans")
    planned_meals: Mapped[list["PlannedMeal"]] = relationship(back_populates="day_plan", cascade="all, delete-orphan")
```

### PlannedMeal

```python
class MealSource(str, enum.Enum):
    AI_GENERATED = "ai_generated"
    USER_CUSTOM = "user_custom"
    FROM_FAVORITES = "from_favorites"

class PlannedMeal(Base):
    __tablename__ = "planned_meals"

    day_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("day_plans.id"), nullable=False)
    meal_slot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meal_slots.id"), nullable=False)
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recipes.id"), nullable=True)
    source: Mapped[MealSource] = mapped_column(SQLEnum(MealSource), nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurring_rule: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # recurring_rule esempio:
    # {"type": "daily"}                    → tutti i giorni (es. colazione fissa)
    # {"type": "weekly", "day": 6}         → ogni domenica (es. pizza sabato sera — day 5 = sabato)
    is_followed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # null = non ancora tracciato
    deviation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    day_plan: Mapped["DayPlan"] = relationship(back_populates="planned_meals")
    meal_slot: Mapped["MealSlot"] = relationship()
    recipe: Mapped["Recipe | None"] = relationship()
    chat_messages: Mapped[list["MealChatMessage"]] = relationship(back_populates="planned_meal", cascade="all, delete-orphan")
```

### Recipe

```python
class Difficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

class Recipe(Base):
    __tablename__ = "recipes"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    prep_time_min: Mapped[int] = mapped_column(Integer, nullable=False)
    cook_time_min: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(SQLEnum(Difficulty), default=Difficulty.MEDIUM)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)  # Procedimento step-by-step in markdown
    calories: Mapped[int] = mapped_column(Integer, nullable=False)
    protein_g: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False)
    carbs_g: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False)
    fat_g: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False)
    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # tags: {"cuisine": "italiana", "season": ["estate", "primavera"], "type": "primo"}
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5, null = non votata
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)  # True = inserita manualmente dall'utente
    generation_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)  # Prompt usato (per debug)

    user: Mapped["User"] = relationship(back_populates="recipes")
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")
```

### Ingredient + RecipeIngredient

```python
class IngredientCategory(str, enum.Enum):
    FRUTTA = "frutta"
    VERDURA = "verdura"
    CARNE = "carne"
    PESCE = "pesce"
    LATTICINI = "latticini"
    CEREALI = "cereali"
    LEGUMI = "legumi"
    UOVA = "uova"
    CONDIMENTI = "condimenti"
    SURGELATI = "surgelati"
    BEVANDE = "bevande"
    ALTRO = "altro"

class Ingredient(Base):
    __tablename__ = "ingredients"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    category: Mapped[IngredientCategory] = mapped_column(SQLEnum(IngredientCategory), nullable=False)
    season_months: Mapped[list | None] = mapped_column(ARRAY(Integer), nullable=True)  # [6,7,8] = estate
    avg_price_per_unit: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    price_unit: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "kg", "l", "unità"


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    recipe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipes.id"), nullable=False)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)  # "g", "ml", "unità", "cucchiai", ecc.
    notes: Mapped[str | None] = mapped_column(String(100), nullable=True)  # "a dadini", "tritato", ecc.

    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients")
    ingredient: Mapped["Ingredient"] = relationship()
```

### Configurazione utente (ingredienti base, esclusi, dispensa)

```python
class BaseIngredient(Base):
    """Ingredienti sempre disponibili (sale, olio, ecc.) — esclusi dalla lista spesa."""
    __tablename__ = "base_ingredients"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"), nullable=False)

    ingredient: Mapped["Ingredient"] = relationship()


class ExcludedIngredient(Base):
    """Ingredienti MAI da usare (allergeni, intolleranze, gusti)."""
    __tablename__ = "excluded_ingredients"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"), nullable=True)
    custom_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Se ingredient_id è null, custom_name contiene il nome libero (es. "frutti di mare")
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)  # "allergia", "intolleranza", "non piace"


class PantryItem(Base):
    """Dispensa virtuale — ingredienti attualmente in casa."""
    __tablename__ = "pantry_items"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"), nullable=False)
    quantity_available: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)

    ingredient: Mapped["Ingredient"] = relationship()


class UserPreferences(Base):
    """Preferenze globali dell'utente."""
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    prefer_seasonal: Mapped[bool] = mapped_column(Boolean, default=True)
    prefer_italian: Mapped[bool] = mapped_column(Boolean, default=True)
    max_prep_time_min: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Tempo max preparazione
    budget_level: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "economico", "medio", "premium"

    user: Mapped["User"] = relationship(back_populates="preferences")
```

### Chat per pasto

```python
class ChatRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"

class MealChatMessage(Base):
    __tablename__ = "meal_chat_messages"

    planned_meal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("planned_meals.id"), nullable=False)
    role: Mapped[ChatRole] = mapped_column(SQLEnum(ChatRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    planned_meal: Mapped["PlannedMeal"] = relationship(back_populates="chat_messages")
```

### Lista della spesa

```python
class ShoppingList(Base):
    __tablename__ = "shopping_lists"

    week_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("week_plans.id"), nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)

    week_plan: Mapped["WeekPlan"] = relationship()
    items: Mapped[list["ShoppingListItem"]] = relationship(back_populates="shopping_list", cascade="all, delete-orphan")


class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"

    shopping_list_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shopping_lists.id"), nullable=False)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"), nullable=False)
    total_quantity: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    is_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    estimated_price: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)

    shopping_list: Mapped["ShoppingList"] = relationship(back_populates="items")
    ingredient: Mapped["Ingredient"] = relationship()
```

---

## 6. API Endpoints — Contratti Dettagliati

Tutte le rotte sotto `/api/` richiedono JWT Bearer token tranne `/api/auth/login`.

### 6.1 Auth

```
POST /api/auth/login
  Body: { "email": str, "password": str }
  Response 200: { "access_token": str, "refresh_token": str, "token_type": "bearer" }
  Response 401: { "detail": "Credenziali non valide" }

POST /api/auth/refresh
  Body: { "refresh_token": str }
  Response 200: { "access_token": str, "refresh_token": str, "token_type": "bearer" }

POST /api/auth/logout
  Response 200: { "detail": "Logout effettuato" }

GET /api/auth/me
  Response 200: { "id": uuid, "email": str, "has_api_key": bool, "has_active_diet": bool }

PUT /api/auth/api-key
  Body: { "api_key": str }
  Response 200: { "detail": "API key salvata" }
  Note: la API key viene crittografata con AES-256 prima del salvataggio
```

### 6.2 Dieta

```
POST /api/diet/upload
  Body: multipart/form-data con campo "file" (PDF)
  Response 200: {
    "id": uuid,
    "total_daily_calories": int,
    "meals": [
      { "name": str, "order": int, "calories": int, "protein_g": float, "carbs_g": float, "fat_g": float }
    ],
    "notes": str
  }
  Note: il PDF viene inviato a Claude Vision API per parsing. Il risultato viene salvato e restituito.

GET /api/diet/current
  Response 200: DietPlanResponse (come sopra, con meal_slots popolati)
  Response 404: nessun piano attivo

PUT /api/diet/{diet_id}/meals
  Body: { "meals": [ { "name": str, "order": int, "calories": int, "protein_g": float, "carbs_g": float, "fat_g": float } ] }
  Response 200: DietPlanResponse aggiornato
  Note: permette di modificare manualmente i macro dopo il parsing AI
```

### 6.3 Planning

```
GET /api/planning/weeks/current
  Response 200: WeekPlanResponse { id, week_start_date, status, is_locked, days: DayPlanResponse[] }
  Note: se non esiste, viene creato automaticamente (status=draft)

GET /api/planning/weeks/next
  Response 200: WeekPlanResponse per la settimana successiva
  Note: se non esiste, viene creato con ricette pre-generate

POST /api/planning/weeks/{week_id}/generate
  Response 200: WeekPlanResponse con tutte le ricette generate
  Note: genera solo i pasti non fissati (is_recurring=false e source != user_custom).
        Rispetta: macro, esclusi, base, stagionalità, rating storici, anti-spreco.
        Può richiedere 10-30 secondi → usare SSE o polling.

POST /api/planning/weeks/{week_id}/lock
  Response 200: { "locked_at": datetime, "lock_expires_at": datetime }
  Response 409: "Piano già bloccato"
  Note: imposta is_locked=true, locked_at=now, lock_expires_at=now+7days.
        Tutti i PlannedMeal della settimana diventano non modificabili.
        Crea anche gli item della ShoppingList se non esistono.

POST /api/planning/weeks/{week_id}/unlock
  Response 200: WeekPlanResponse sbloccato
  Note: sblocco manuale (emergenza). Richiede conferma UI.

GET /api/planning/weeks/{week_id}/days
  Response 200: DayPlanResponse[] con planned_meals e recipe per ognuno

GET /api/planning/meals/{meal_id}
  Response 200: PlannedMealDetail { ...planned_meal, recipe: RecipeDetail, chat_count: int }

POST /api/planning/meals/{meal_id}/regenerate
  Response 200: PlannedMealDetail con nuova ricetta
  Response 409: "Piano bloccato, impossibile rigenerare"
  Note: genera una nuova ricetta per quel pasto, sostituendo la precedente.
        La vecchia ricetta resta in archivio ma non è più assegnata.

PUT /api/planning/meals/{meal_id}/assign
  Body: { "recipe_id": uuid } | { "source": "user_custom", "recipe": RecipeCreate }
  Response 200: PlannedMealDetail
  Response 409: "Piano bloccato"

PUT /api/planning/meals/{meal_id}/recurring
  Body: { "is_recurring": bool, "recurring_rule": { "type": "daily" | "weekly", "day"?: int } }
  Response 200: PlannedMealDetail
  Note: i pasti ricorrenti vengono pre-assegnati alla generazione del piano successivo

PUT /api/planning/meals/{meal_id}/followed
  Body: { "is_followed": bool, "deviation_notes"?: str }
  Response 200: PlannedMealDetail
```

### 6.4 Ricette

```
GET /api/recipes?page=1&per_page=20&rating_min=3&is_favorite=true&difficulty=easy&search=pasta
  Response 200: { "items": RecipeResponse[], "total": int, "page": int, "per_page": int }

GET /api/recipes/{recipe_id}
  Response 200: RecipeDetailResponse (con ingredients e usage_history)

POST /api/recipes
  Body: RecipeCreate { title, prep_time_min, cook_time_min, difficulty, instructions, calories, protein_g, carbs_g, fat_g, ingredients: [{name, quantity, unit}], tags }
  Response 201: RecipeDetailResponse
  Note: crea una ricetta custom (is_custom=true). Gli ingredienti che non esistono nel DB vengono creati.

PUT /api/recipes/{recipe_id}/rate
  Body: { "rating": int }  # 1-5
  Response 200: RecipeResponse

PUT /api/recipes/{recipe_id}/favorite
  Body: { "is_favorite": bool }
  Response 200: RecipeResponse

POST /api/recipes/{recipe_id}/substitute
  Body: { "ingredient_to_replace": str, "reason"?: str }
  Response 200: {
    "original_ingredient": str,
    "substitute_ingredient": str,
    "new_quantity": str,
    "updated_macros": { "calories": int, "protein_g": float, "carbs_g": float, "fat_g": float },
    "notes": str
  }
  Note: chiede a Claude di suggerire un sostituto, ricalcola i macro, aggiorna la ricetta
```

### 6.5 Chat per Pasto

```
POST /api/chat/meals/{meal_id}/messages
  Body: { "content": str }
  Response 200: { "role": "assistant", "content": str, "recipe_updated": bool }
  Note: invia il messaggio a Claude con contesto della ricetta corrente.
        Se la risposta AI contiene una modifica alla ricetta, recipe_updated=true
        e la ricetta viene aggiornata nel DB.

GET /api/chat/meals/{meal_id}/messages
  Response 200: ChatMessage[] (ordinati per created_at)
```

### 6.6 Lista della Spesa

```
GET /api/shopping/current
  Response 200: ShoppingListResponse {
    id, is_completed, estimated_cost,
    items: ShoppingListItemResponse[] (raggruppati per categoria),
    categories_summary: { "verdura": float, "carne": float, ... }
  }

GET /api/shopping/next
  Response 200: ShoppingListResponse (anteprima settimana successiva)

PUT /api/shopping/items/{item_id}/check
  Body: { "is_checked": bool }
  Response 200: ShoppingListItemResponse

POST /api/shopping/current/complete
  Response 200: { "detail": "Spesa completata", "week_locked_until": datetime }
  Note: segna la spesa come fatta → blocca il WeekPlan corrente per 7 giorni.
        Aggiorna la dispensa virtuale con gli ingredienti acquistati.

GET /api/shopping/export
  Query: ?format=text|json
  Response 200: testo formattato della lista (per copia/condivisione)
```

### 6.7 Configurazione

```
GET /api/config/base-ingredients
  Response 200: BaseIngredientResponse[]

POST /api/config/base-ingredients
  Body: { "ingredient_name": str }
  Response 201: BaseIngredientResponse
  Note: se l'ingrediente non esiste nel DB Ingredient, lo crea con categoria "condimenti"

DELETE /api/config/base-ingredients/{id}
  Response 204

GET /api/config/excluded
  Response 200: ExcludedIngredientResponse[]

POST /api/config/excluded
  Body: { "ingredient_name": str, "reason"?: str }
  Response 201: ExcludedIngredientResponse

DELETE /api/config/excluded/{id}
  Response 204

GET /api/config/pantry
  Response 200: PantryItemResponse[]

POST /api/config/pantry
  Body: { "ingredient_name": str, "quantity"?: float, "unit"?: str }
  Response 201: PantryItemResponse

PUT /api/config/pantry/{id}
  Body: { "quantity": float, "unit": str }
  Response 200: PantryItemResponse

DELETE /api/config/pantry/{id}
  Response 204

GET /api/config/preferences
  Response 200: UserPreferencesResponse

PUT /api/config/preferences
  Body: { "prefer_seasonal": bool, "prefer_italian": bool, "max_prep_time_min"?: int, "budget_level"?: str }
  Response 200: UserPreferencesResponse
```

### 6.8 Tracking

```
GET /api/tracking/weekly?week_start_date=2026-07-20
  Response 200: {
    "week_start_date": date,
    "target": { "daily_calories": int, "meals": [...] },
    "days": [
      {
        "date": date,
        "day_name": "Lunedì",
        "meals": [
          {
            "slot_name": "Pranzo",
            "target": { "calories": 600, "protein_g": 35, ... },
            "planned": { "calories": 580, "protein_g": 33, ... },
            "is_followed": true | false | null,
            "deviation_notes": str | null
          }
        ],
        "totals": { "planned_calories": int, "target_calories": int, "delta": int }
      }
    ],
    "weekly_summary": {
      "avg_daily_calories_planned": int,
      "avg_daily_calories_target": int,
      "compliance_pct": float,
      "macro_averages": { "protein_g": float, "carbs_g": float, "fat_g": float }
    }
  }
```

---

## 7. Integrazione AI — Prompt e Strategie

### 7.1 Client Claude (`app/ai/client.py`)

```python
import anthropic
from app.utils.crypto import decrypt_api_key

class ClaudeClient:
    def __init__(self, encrypted_api_key: str):
        api_key = decrypt_api_key(encrypted_api_key)
        self.client = anthropic.Anthropic(api_key=api_key)

    async def generate(self, system: str, user: str, model: str = "claude-sonnet-4-6", max_tokens: int = 4096) -> str:
        """Chiamata singola. Retry fino a 3 volte con backoff esponenziale."""
        ...

    async def chat(self, system: str, messages: list[dict], model: str = "claude-haiku-4-5-20251001", max_tokens: int = 2048) -> str:
        """Chiamata multi-turn per la chat per pasto."""
        ...
```

### 7.2 Prompt: Parsing PDF Dieta

```
SYSTEM:
Sei un assistente specializzato nella lettura di piani dietetici.
Analizza il documento PDF fornito ed estrai le seguenti informazioni in formato JSON.

FORMATO OUTPUT (JSON rigoroso, nessun testo aggiuntivo):
{
  "daily_calories": <int>,
  "notes": "<eventuali note del nutrizionista>",
  "meals": [
    {
      "name": "<nome pasto>",
      "order": <int, 0-based>,
      "calories": <int>,
      "protein_g": <float>,
      "carbs_g": <float>,
      "fat_g": <float>,
      "notes": "<note specifiche per il pasto, se presenti>"
    }
  ]
}

REGOLE:
- Se i macro non sono esplicitamente indicati per un pasto, stimali in base alle calorie con ripartizione standard (25% proteine, 50% carboidrati, 25% grassi) e segnalalo nelle note.
- Se il documento menziona alimenti specifici obbligatori (es. "assumere 200g di proteine a pranzo"), includili nelle note del pasto.
- Il campo "order" parte da 0 per il primo pasto della giornata.
- Rispondi ESCLUSIVAMENTE con il JSON, senza markdown, senza backtick, senza spiegazioni.
```

### 7.3 Prompt: Generazione Piano Settimanale

```
SYSTEM:
Sei DietAI, un nutrizionista e chef italiano esperto. Il tuo compito è generare un piano settimanale di ricette personalizzate.

CONTESTO UTENTE:
- Calorie giornaliere target: {daily_calories} kcal
- Pasti configurati: {meals_config}  (nome, calorie target, macro target per pasto)
- Ingredienti ESCLUSI (MAI usare): {excluded_ingredients}
- Ingredienti di BASE (sempre disponibili, non mettere in lista spesa): {base_ingredients}
- Dispensa attuale (ingredienti già in casa): {pantry_items}
- Preferenze: cucina italiana {if prefer_italian}, ingredienti di stagione ({current_month}) {if prefer_seasonal}
- Tempo preparazione massimo: {max_prep_time_min} minuti (se impostato)
- Pasti FISSI (non generare): {recurring_meals}
- Ricette già assegnate questa settimana (evita ripetizioni): {already_assigned}
- Storico rating: {rating_history}  (ricette con voto alto → simili gradite; voto basso → evita simili)

REGOLE DI GENERAZIONE:
1. Le ricette DEVONO rispettare i macro target per pasto (tolleranza ±10%).
2. Le ricette DEVONO essere di cucina italiana o mediterranea.
3. MAI usare ingredienti nella lista esclusi.
4. OTTIMIZZA gli ingredienti: se una ricetta usa mezza zucchina, piazza l'altra metà in un altro pasto della settimana.
5. VARIA le ricette: non ripetere lo stesso piatto nella settimana e non ripetere ingredienti principali in pasti consecutivi.
6. PREFERISCI ingredienti di stagione (mese corrente: {month}).
7. Includi sempre: titolo, tempo preparazione, tempo cottura, difficoltà, ingredienti con quantità e unità, procedimento step-by-step, valori nutrizionali calcolati.
8. I pasti marcati come FISSI non vanno generati — saltali.

FORMATO OUTPUT (JSON rigoroso):
{
  "days": [
    {
      "day_of_week": 0,
      "day_name": "Lunedì",
      "meals": [
        {
          "slot_name": "Colazione",
          "recipe": {
            "title": "<nome>",
            "description": "<breve descrizione>",
            "prep_time_min": <int>,
            "cook_time_min": <int>,
            "difficulty": "easy|medium|hard",
            "ingredients": [
              { "name": "<nome ingrediente>", "quantity": <float>, "unit": "<g|ml|unità|cucchiai|...>", "notes": "<opzionale: a dadini, tritato, ecc.>" }
            ],
            "instructions": "<procedimento step-by-step, numerato>",
            "nutrition": {
              "calories": <int>,
              "protein_g": <float>,
              "carbs_g": <float>,
              "fat_g": <float>
            },
            "tags": { "cuisine": "italiana", "season": ["<stagioni>"], "type": "<primo|secondo|contorno|colazione|spuntino>" }
          }
        }
      ]
    }
  ],
  "ingredient_reuse_notes": "<spiegazione di come hai ottimizzato gli ingredienti per ridurre sprechi>"
}

Rispondi ESCLUSIVAMENTE con il JSON.
```

### 7.4 Prompt: Rigenerazione Singola Ricetta

```
SYSTEM:
Sei DietAI, un nutrizionista e chef italiano. Genera UNA ricetta alternativa per il pasto indicato.

VINCOLI:
- Pasto: {meal_slot_name} ({day_name})
- Calorie target: {target_calories} kcal (±10%)
- Macro target: P {protein_g}g, C {carbs_g}g, G {fat_g}g
- Ingredienti esclusi: {excluded}
- Ingredienti di base: {base}
- Ricetta precedente (da NON ripetere): {previous_recipe_title}
- Altre ricette nella settimana (evita ripetizioni): {week_recipes}
- Ingredienti parzialmente usati nella settimana (preferisci riutilizzarli): {partial_ingredients}
- Preferenze: cucina italiana, stagionalità ({month})

OUTPUT: JSON con la struttura "recipe" (stessa del piano settimanale, senza wrapping "days").
```

### 7.5 Prompt: Chat Contestuale per Pasto

```
SYSTEM:
Sei DietAI, un assistente culinario e nutrizionista italiano. Stai parlando con l'utente riguardo a un pasto specifico.

CONTESTO PASTO:
- Pasto: {meal_slot_name} di {day_name}
- Ricetta attuale: {current_recipe_json}
- Macro target: {target_macros}
- Ingredienti esclusi: {excluded}

REGOLE:
- Se l'utente chiede una modifica alla ricetta, restituisci la ricetta aggiornata in JSON preceduto da [RECIPE_UPDATE].
- Se l'utente chiede solo informazioni o delucidazioni, rispondi in linguaggio naturale.
- Se l'utente chiede una sostituzione ingrediente, suggerisci l'alternativa e ricalcola i macro.
- Rispondi sempre in italiano.
- Se la modifica richiesta viola i vincoli (macro, esclusi), spiega perché e suggerisci un'alternativa.

FORMATO RISPOSTA:
- Risposte normali: testo libero in italiano
- Modifiche ricetta: "[RECIPE_UPDATE]\n" seguito dal JSON completo della ricetta aggiornata
```

### 7.6 Prompt: Sostituzione Ingrediente

```
SYSTEM:
Sei DietAI. L'utente vuole sostituire un ingrediente in una ricetta.

RICETTA: {recipe_json}
INGREDIENTE DA SOSTITUIRE: {ingredient_name}
MOTIVO: {reason}
INGREDIENTI ESCLUSI: {excluded}

Suggerisci un sostituto adeguato che:
1. Mantenga il gusto e la consistenza del piatto
2. Resti nei vincoli calorici (±10% delle calorie originali)
3. Non sia nella lista degli ingredienti esclusi
4. Sia facilmente reperibile in Italia

OUTPUT JSON:
{
  "original": { "name": str, "quantity": float, "unit": str },
  "substitute": { "name": str, "quantity": float, "unit": str },
  "updated_nutrition": { "calories": int, "protein_g": float, "carbs_g": float, "fat_g": float },
  "explanation": "<perché questa sostituzione funziona>"
}
```

---

## 8. Regole di Business Critiche

### 8.1 Logica di Blocco Settimanale

```
QUANDO l'utente completa la spesa (POST /api/shopping/current/complete):
  1. week_plan.is_locked = True
  2. week_plan.locked_at = now()
  3. week_plan.lock_expires_at = now() + 7 giorni
  4. week_plan.status = "locked"
  5. Tutti i planned_meals della settimana → non modificabili
  6. Gli ingredienti della shopping_list con is_checked=True vengono aggiunti alla dispensa virtuale
  7. La lista della spesa diventa read-only

QUANDO lock_expires_at < now():
  1. week_plan.status = "archived"
  2. La settimana successiva diventa "current" (status = "active")
  3. La nuova settimana successiva viene creata in draft con ricette pre-generate

DURANTE IL BLOCCO:
  - GET ricette/pasti → OK (sola lettura)
  - POST regenerate/assign → 409 Conflict
  - PUT rate/favorite → OK (non modifica il piano)
  - Chat → OK ma non può aggiornare la ricetta (informativo)
  - Shopping next week → OK (modificabile)
```

### 8.2 Pasti Ricorrenti

```
QUANDO un pasto è marcato come ricorrente:
  - type "daily": viene pre-assegnato ad OGNI giorno della settimana per quel meal_slot
  - type "weekly" con day: viene pre-assegnato SOLO a quel giorno per quel meal_slot
  - Alla generazione del piano, i pasti ricorrenti sono esclusi dalla generazione AI
  - La ricetta ricorrente viene COPIATA (nuovo record Recipe legato allo stesso utente)
```

### 8.3 Anti-Spreco

```
DURANTE la generazione del piano settimanale:
  1. Dopo aver generato le ricette, il backend analizza gli ingredienti
  2. Identifica ingredienti "parziali" (es. ricetta usa 150g di un pacco da 500g)
  3. Passa l'elenco degli ingredienti parziali come contesto nella generazione delle ricette successive
  4. L'AI cerca di riutilizzare quegli ingredienti nei pasti successivi
  5. Questo viene fatto in un unico prompt batch che genera tutta la settimana
```

### 8.4 Lista della Spesa — Calcolo

```
PER OGNI settimana:
  1. Raccogli tutti gli ingredienti da tutte le ricette dei 7 giorni
  2. Aggrega per ingrediente: somma le quantità (convertendo le unità se necessario)
  3. Sottrai gli ingredienti di base (BaseIngredient) — non vanno nella lista
  4. Sottrai le quantità presenti nella dispensa (PantryItem)
  5. Se la quantità netta è <= 0, l'ingrediente non appare nella lista
  6. Raggruppa per categoria (frutta, verdura, carne, ecc.)
  7. Calcola stima costo: quantità × avg_price_per_unit per ogni ingrediente
```

### 8.5 Stagionalità

File `app/utils/seasonality.py` — dizionario con i principali prodotti ortofrutticoli italiani e i mesi di disponibilità:

```python
SEASONAL_PRODUCTS = {
    "fragole": [4, 5, 6],
    "zucchine": [5, 6, 7, 8, 9],
    "melanzane": [6, 7, 8, 9],
    "pomodori": [6, 7, 8, 9],
    "peperoni": [6, 7, 8, 9],
    "carciofi": [1, 2, 3, 4, 11, 12],
    "funghi porcini": [9, 10, 11],
    "zucca": [9, 10, 11, 12],
    "cavolo nero": [10, 11, 12, 1, 2],
    "agrumi": [11, 12, 1, 2, 3],
    "asparagi": [3, 4, 5, 6],
    "piselli": [4, 5, 6],
    "fave": [3, 4, 5],
    "ciliegie": [5, 6],
    "pesche": [6, 7, 8],
    "fichi": [7, 8, 9],
    "uva": [8, 9, 10],
    "castagne": [10, 11],
    "radicchio": [10, 11, 12, 1, 2, 3],
    "broccoli": [10, 11, 12, 1, 2, 3],
    "finocchi": [10, 11, 12, 1, 2, 3],
    "verza": [10, 11, 12, 1, 2, 3],
    "spinaci": [1, 2, 3, 4, 10, 11, 12],
    "bietola": [3, 4, 5, 6, 7, 8, 9, 10, 11],
    # ... estendere
}
```

---

## 9. Frontend — Dettagli Implementativi

### 9.1 Redux Store Structure

```typescript
interface RootState {
  auth: {
    token: string | null;
    user: User | null;
    isAuthenticated: boolean;
  };
  // RTK Query gestisce tutto il server-state:
  [dietApi.reducerPath]: ReturnType<typeof dietApi.reducer>;
  [planningApi.reducerPath]: ReturnType<typeof planningApi.reducer>;
  [recipesApi.reducerPath]: ReturnType<typeof recipesApi.reducer>;
  [shoppingApi.reducerPath]: ReturnType<typeof shoppingApi.reducer>;
  [chatApi.reducerPath]: ReturnType<typeof chatApi.reducer>;
  [configApi.reducerPath]: ReturnType<typeof configApi.reducer>;
  [trackingApi.reducerPath]: ReturnType<typeof trackingApi.reducer>;
}
```

### 9.2 RTK Query — Base API

```typescript
// store/api.ts
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

export const baseApi = createApi({
  reducerPath: 'api',
  baseQuery: fetchBaseQuery({
    baseUrl: '/api',
    prepareHeaders: (headers, { getState }) => {
      const token = (getState() as RootState).auth.token;
      if (token) headers.set('Authorization', `Bearer ${token}`);
      return headers;
    },
  }),
  tagTypes: ['Diet', 'WeekPlan', 'Meal', 'Recipe', 'Shopping', 'Chat', 'Config', 'Tracking'],
  endpoints: () => ({}),
});

// I singoli file (dietApi.ts, planningApi.ts, ecc.) usano:
// export const dietApi = baseApi.injectEndpoints({ endpoints: (build) => ({ ... }) });
```

### 9.3 Routing

```typescript
// routes.tsx
const routes = [
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: <ProtectedLayout />,  // Controlla auth, mostra AppLayout
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'plan', element: <PlanningPage /> },
      { path: 'plan/next', element: <PlanningNextPage /> },
      { path: 'plan/day/:dayId/meal/:mealId', element: <MealDetailPage /> },
      { path: 'shopping', element: <ShoppingPage /> },
      { path: 'recipes', element: <RecipesPage /> },
      { path: 'recipes/:recipeId', element: <RecipeDetailPage /> },
      { path: 'tracking', element: <TrackingPage /> },
      { path: 'settings/diet', element: <SettingsDietPage /> },
      { path: 'settings/base', element: <SettingsBasePage /> },
      { path: 'settings/excluded', element: <SettingsExcludedPage /> },
      { path: 'settings/pantry', element: <SettingsPantryPage /> },
      { path: 'settings/preferences', element: <SettingsPreferencesPage /> },
    ],
  },
];
```

### 9.4 Componenti principali — specifiche

#### WeekGrid

- Griglia 7 colonne (lun-dom) × N righe (1 per meal slot)
- Header con nome giorno e data
- Ogni cella contiene un `<MealCard />`
- Su mobile: swipe orizzontale tra giorni (una colonna alla volta)
- Se il piano è locked, overlay grigio con lucchetto e testo "Piano bloccato fino al {data}"

#### MealCard

- Thumbnail (icona in base al tipo di pasto)
- Titolo ricetta (troncato a 2 righe)
- Badge: calorie, tempo preparazione
- Mini barra macro (P/C/G come barre colorate proporzionali)
- Azioni rapide (icon button):
  - 🔄 Rigenera (disabilitato se locked)
  - 💬 Chat (apre MealChat)
  - ⭐ Rating
  - 📌 Imposta ricorrente
- Se source = user_custom → badge "Custom"
- Se source = from_favorites → badge "Preferita"

#### MealChat

- Desktop: pannello laterale a destra (width 400px)
- Mobile: bottom sheet a schermo pieno
- Header: nome pasto + giorno + pulsante chiudi
- Corpo: storico messaggi (bolle user/assistant)
- Input: textarea + pulsante invio
- Loading: indicatore "DietAI sta rispondendo..."
- Se la risposta contiene [RECIPE_UPDATE]: mostra toast "Ricetta aggiornata" e invalida la cache RTK Query

#### ShoppingList

- Due tab: "Questa settimana" | "Prossima settimana"
- Sezioni accordion per categoria (🥬 Verdura, 🥩 Carne, 🐟 Pesce, ecc.)
- Ogni item: checkbox + nome + quantità + unità + prezzo stimato
- Footer fisso: "Totale stimato: €XX.XX" + pulsante "Ho fatto la spesa ✓"
- Pulsante "Ho fatto la spesa" → dialog di conferma → POST complete → blocca piano
- Pulsante esporta (icona condividi) → copia testo formattato

#### NutritionChart (Tracking)

- Grafico a barre raggruppate: 7 giorni × (target vs pianificato) per calorie
- Sotto: breakdown macro in gauge circolari (proteine, carbs, grassi) — media settimanale
- Indicatore compliance: "Hai seguito il piano X giorni su 7"
- Colori: verde = entro ±10%, giallo = ±20%, rosso = oltre

---

## 10. Onboarding (primo accesso)

Flusso guidato step-by-step alla prima visita dopo il login:

1. **Benvenuto** — splash screen con breve spiegazione
2. **API Key** — form per inserire la Claude API key (con link alla documentazione Anthropic)
3. **Carica Dieta** — upload del PDF del nutrizionista. Mostra risultato parsing con possibilità di modificare
4. **Ingredienti Base** — suggerimenti pre-compilati (sale, olio EVO, pepe, aceto, zucchero) + possibilità di aggiungerne
5. **Alimenti Esclusi** — input libero per allergeni e cibi sgraditi
6. **Preferenze** — toggle stagionalità, conferma cucina italiana, tempo preparazione max
7. **Genera Piano** — il sistema genera il primo piano settimanale. Mostra loading con skeleton e poi il risultato

L'onboarding si mostra solo se:
- `user.claude_api_key_enc IS NULL` → step 2
- `DietPlan.is_active` non esiste → step 3
- Dopo il primo piano generato, l'onboarding non si mostra più

---

## 11. Sicurezza

### Crittografia API Key

```python
# app/utils/crypto.py
from cryptography.fernet import Fernet
import os

# ENCRYPTION_KEY dal .env, generata con: Fernet.generate_key()
fernet = Fernet(os.environ["ENCRYPTION_KEY"])

def encrypt_api_key(api_key: str) -> str:
    return fernet.encrypt(api_key.encode()).decode()

def decrypt_api_key(encrypted: str) -> str:
    return fernet.decrypt(encrypted.encode()).decode()
```

### Middleware e protezioni

- **CORS**: solo `CORS_ORIGINS` dal `.env`
- **Rate limiting**: `slowapi` su endpoint AI (max 20 chiamate/minuto)
- **Input sanitization**: Pydantic valida tutti gli input; i prompt utente verso l'AI vengono sanitizzati (rimozione tentativi di injection)
- **JWT**: access token 60 min, refresh token 7 giorni; token invalidato al logout (blacklist in-memory o Redis se necessario)
- **HTTPS**: obbligatorio in produzione (gestito da reverse proxy nginx/caddy)

---

## 12. Seed Data

Al primo avvio (`alembic upgrade head` + script seed):

1. Crea l'utente seed da `.env` (`SEED_USER_EMAIL`, `SEED_USER_PASSWORD`)
2. Popola la tabella `ingredients` con ~200 ingredienti comuni italiani (nome, categoria, stagionalità, prezzo medio)
3. Crea `user_preferences` con defaults (prefer_seasonal=true, prefer_italian=true)

Il file seed è in `backend/app/seed.py` e viene chiamato da un comando CLI:

```bash
python -m app.seed
```

---

## 13. Ordine di Implementazione

Segui quest'ordine per costruire il progetto in modo incrementale e testabile:

### Fase 1 — Scaffolding e Auth
1. Setup Docker Compose (db + backend + frontend)
2. Setup FastAPI con struttura cartelle
3. Setup SQLAlchemy + Alembic + modelli Base/User
4. Implementa auth (login, JWT, middleware)
5. Setup React + Vite + Tailwind + shadcn/ui
6. Setup Redux store + authSlice + LoginPage
7. AppLayout con sidebar e routing protetto

### Fase 2 — Dieta e Configurazione
8. Modelli DietPlan + MealSlot
9. Endpoint upload PDF + parsing AI (Claude Vision)
10. UI: SettingsDietPage con upload e risultato parsing
11. Modelli e CRUD per BaseIngredient, ExcludedIngredient, PantryItem, UserPreferences
12. UI: pagine settings (ingredienti base, esclusi, dispensa, preferenze)
13. Seed data ingredienti

### Fase 3 — Planning e Ricette AI
14. Modelli WeekPlan, DayPlan, PlannedMeal, Recipe, RecipeIngredient
15. Service generazione piano settimanale (prompt AI batch)
16. Endpoint CRUD planning + generate
17. UI: PlanningPage con WeekGrid + MealCard
18. Endpoint e UI rigenerazione singola ricetta
19. Pasti ricorrenti (assign + recurring rule)
20. Ricette custom (insert manuale)

### Fase 4 — Chat e Interazione
21. Modello MealChatMessage
22. Service chat contestuale (Claude Haiku)
23. Endpoint chat (POST message, GET history)
24. UI: MealDetailPage con RecipeDetail + MealChat
25. Sostituzione ingrediente via AI
26. Rating e preferiti

### Fase 5 — Lista Spesa
27. Modelli ShoppingList + ShoppingListItem
28. Service calcolo lista spesa (aggregazione, sottrazione dispensa)
29. Logica di blocco settimanale
30. Service stima costo
31. UI: ShoppingPage con tab corrente/prossima
32. Esportazione lista (testo)
33. Completamento spesa → lock piano + aggiornamento dispensa

### Fase 6 — Tracking e Polish
34. Service tracking nutrizionale
35. UI: TrackingPage con grafici
36. DashboardPage (overview)
37. Onboarding flow
38. Responsive design (mobile)
39. Settimana successiva (pre-generazione, anteprima)
40. Testing E2E e deploy

---

## 14. Note per Claude Code

- **Lingua UI**: tutta in italiano
- **Lingua codice**: variabili, commenti e documentazione in inglese; stringhe utente in italiano
- **Stile codice Python**: Black formatter, isort, type hints ovunque
- **Stile codice TypeScript**: ESLint + Prettier, strict mode
- **Commit**: conventional commits in inglese (feat:, fix:, chore:, ecc.)
- **Error handling**: mai errori generici; ogni endpoint restituisce messaggi in italiano per l'utente
- **Logging**: `structlog` con JSON per il backend; log ogni chiamata AI con token usati e tempo di risposta
- **Testing**: pytest (async) per backend, Vitest per frontend — almeno i flussi critici (auth, generazione piano, blocco spesa)
