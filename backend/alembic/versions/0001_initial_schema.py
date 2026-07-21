"""Schema iniziale di DietAI

Revision ID: 0001
Revises:
Create Date: 2026-07-21

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # ── Utente e sessioni ──
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("claude_api_key_enc", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("family_id", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent", sa.String()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    # ── Anagrafica ingredienti ──
    op.create_table(
        "ingredients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False, server_default="altro"),
        sa.Column("season_months", JSONB),
        sa.Column("avg_price_per_unit", sa.Float()),
        sa.Column("price_unit", sa.String()),
        sa.CheckConstraint(
            "category IN ('frutta','verdura','carne','pesce','latticini','cereali',"
            "'legumi','uova','condimenti','surgelati','bevande','altro')",
            name="ck_ingredient_category",
        ),
    )
    op.create_index("ix_ingredients_name", "ingredients", ["name"], unique=True)

    # ── Dieta ──
    op.create_table(
        "diet_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String()),
        sa.Column("parsed_data", JSONB, nullable=False),
        sa.Column("total_daily_calories", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_diet_plans_user_id", "diet_plans", ["user_id"])

    op.create_table(
        "meal_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("diet_plan_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("target_calories", sa.Integer(), nullable=False),
        sa.Column("target_protein_g", sa.Float(), nullable=False),
        sa.Column("target_carbs_g", sa.Float(), nullable=False),
        sa.Column("target_fat_g", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.ForeignKeyConstraint(["diet_plan_id"], ["diet_plans.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("diet_plan_id", "order_index", name="uq_meal_slot_order"),
    )
    op.create_index("ix_meal_slots_diet_plan_id", "meal_slots", ["diet_plan_id"])

    # ── Ricette ──
    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("prep_time_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cook_time_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("difficulty", sa.String(), nullable=False, server_default="medium"),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("calories", sa.Integer(), nullable=False),
        sa.Column("protein_g", sa.Float(), nullable=False),
        sa.Column("carbs_g", sa.Float(), nullable=False),
        sa.Column("fat_g", sa.Float(), nullable=False),
        sa.Column("tags", JSONB),
        sa.Column("rating", sa.Integer()),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("generation_prompt", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "difficulty IN ('easy','medium','hard')", name="ck_recipe_difficulty"
        ),
        sa.CheckConstraint(
            "rating IS NULL OR (rating >= 1 AND rating <= 5)", name="ck_recipe_rating"
        ),
    )
    op.create_index("ix_recipes_user_id", "recipes", ["user_id"])

    op.create_table(
        "recipe_ingredients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("notes", sa.String()),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_recipe_ingredients_recipe_id", "recipe_ingredients", ["recipe_id"])

    # ── Pianificazione ──
    op.create_table(
        "week_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("lock_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "week_start_date", name="uq_week_plan_user_week"),
        sa.CheckConstraint(
            "status IN ('draft','active','locked','archived')", name="ck_week_status"
        ),
    )
    op.create_index("ix_week_plans_user_id", "week_plans", ["user_id"])

    op.create_table(
        "day_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_plan_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["week_plan_id"], ["week_plans.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("week_plan_id", "date", name="uq_day_plan_date"),
    )
    op.create_index("ix_day_plans_week_plan_id", "day_plans", ["week_plan_id"])

    op.create_table(
        "planned_meals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day_plan_id", sa.Integer(), nullable=False),
        sa.Column("meal_slot_id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer()),
        sa.Column("source", sa.String(), nullable=False, server_default="ai_generated"),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("recurring_rule", JSONB),
        sa.Column("is_followed", sa.Boolean()),
        sa.Column("deviation_notes", sa.Text()),
        sa.ForeignKeyConstraint(["day_plan_id"], ["day_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meal_slot_id"], ["meal_slots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("day_plan_id", "meal_slot_id", name="uq_planned_meal"),
        sa.CheckConstraint(
            "source IN ('ai_generated','user_custom','from_favorites')",
            name="ck_planned_meal_source",
        ),
    )
    op.create_index("ix_planned_meals_day_plan_id", "planned_meals", ["day_plan_id"])

    op.create_table(
        "meal_chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("planned_meal_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["planned_meal_id"], ["planned_meals.id"], ondelete="CASCADE"),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_chat_role"),
    )
    op.create_index(
        "ix_meal_chat_messages_planned_meal_id", "meal_chat_messages", ["planned_meal_id"]
    )

    # ── Configurazione utente ──
    op.create_table(
        "base_ingredients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "ingredient_id", name="uq_base_ingredient"),
    )
    op.create_index("ix_base_ingredients_user_id", "base_ingredients", ["user_id"])

    op.create_table(
        "excluded_ingredients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer()),
        sa.Column("custom_name", sa.String()),
        sa.Column("reason", sa.String()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "ingredient_id IS NOT NULL OR custom_name IS NOT NULL",
            name="ck_excluded_has_name",
        ),
    )
    op.create_index("ix_excluded_ingredients_user_id", "excluded_ingredients", ["user_id"])

    op.create_table(
        "pantry_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("quantity_available", sa.Float()),
        sa.Column("unit", sa.String()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "ingredient_id", name="uq_pantry_item"),
    )
    op.create_index("ix_pantry_items_user_id", "pantry_items", ["user_id"])

    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("prefer_seasonal", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("prefer_italian", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("max_prep_time_min", sa.Integer()),
        sa.Column("budget_level", sa.String()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id"),
    )

    # ── Lista della spesa ──
    op.create_table(
        "shopping_lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_plan_id", sa.Integer(), nullable=False),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("estimated_cost", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["week_plan_id"], ["week_plans.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("week_plan_id"),
    )

    op.create_table(
        "shopping_list_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shopping_list_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("total_quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("is_checked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("estimated_price", sa.Float()),
        sa.ForeignKeyConstraint(["shopping_list_id"], ["shopping_lists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "shopping_list_id", "ingredient_id", "unit", name="uq_shopping_item"
        ),
    )
    op.create_index(
        "ix_shopping_list_items_shopping_list_id", "shopping_list_items", ["shopping_list_id"]
    )


def downgrade() -> None:
    op.drop_table("shopping_list_items")
    op.drop_table("shopping_lists")
    op.drop_table("user_preferences")
    op.drop_table("pantry_items")
    op.drop_table("excluded_ingredients")
    op.drop_table("base_ingredients")
    op.drop_table("meal_chat_messages")
    op.drop_table("planned_meals")
    op.drop_table("day_plans")
    op.drop_table("week_plans")
    op.drop_table("recipe_ingredients")
    op.drop_table("recipes")
    op.drop_table("meal_slots")
    op.drop_table("diet_plans")
    op.drop_table("ingredients")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
