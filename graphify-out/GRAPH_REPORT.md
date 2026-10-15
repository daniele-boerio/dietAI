# Graph Report - dietAI  (2026-10-15)

## Corpus Check
- 223 files · ~186,165 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 13 file(s) not represented in the graph (top: (none) 6, .example 2, .ini 1)

## Summary
- 2685 nodes · 6643 edges · 156 communities (113 shown, 43 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 580 edges (avg confidence: 0.94)
- Token cost: 294,210 input · 0 output

## Community Hubs (Navigation)
- Shopping List Aggregation
- Config & Input Schemas
- Week Planner Core
- DB Session & Admin CLI
- Project Rules & Skills
- App Shell & Settings UI
- Push Reminders
- AI Usage & Model Catalog
- Auth & JWT Tokens
- Recipes Router
- Weight Tracking
- Questionnaire Nutrition Math
- Meal & Shopping Chat
- Alembic Env & Model Slugs
- Duplicate Recipe Tests
- Multi-week Shopping Tests
- DayPlan & PlannedMeal
- WeekPlan & Planning Routes
- Recipe Model & Macro Recompute
- Generation Progress Log
- Ingredient Seed & Categories
- Frequencies & Questionnaire UI
- Meal Slots & Cell Actions
- User Normalization Rules
- FastAPI App & Test Fixtures
- End-to-end Flow Tests
- Diet Plan & PDF Import
- Admin & Session Revocation
- Fixed Meals Tests
- Selective Generation Tests
- Skipped Meals Tests
- PDF Extraction & AI Provider
- Shopping Chat Tests
- Pantry Purchase Flow
- Two-account Isolation Tests
- Meal Detail & Recipe View
- Planning Page & Day Dots
- Cuisine Context Tests
- Skipped Days Tests
- Generation & Planning Docs
- Cuisine Picker & Quotas UI
- Delete User Command
- Builtin Name Rules
- Name Normalization
- Meal Chat Tests
- Shared UI Components
- Food Frequency Groups
- Frequency Assignment Tests
- Tracking UI & Empty States
- Recipe Merging
- Push Subscriptions & Prefs
- Recipe Archive Actions
- Ingredient Merge & Registry
- Cuisine Draw
- Pantry Staples Tests
- Reasoning Budget Tests
- Year View Tests
- Week Browsing Tests
- API Key Encryption
- Diet Change Realign Tests
- Fake AI Fixtures
- On-request Generation Tests
- Generation State Tests
- Week Regeneration Tests
- Frontend API & Service Worker
- Anthropic Backend
- Cuisine Preference Cleaning
- Early Migrations
- Recipe Ingredients & Cereal Repair
- Weight History Tests
- Meal Detail Tests
- Computed Macro Tests
- Eaten Instead Tests
- Receipt Scan Tests
- Self-managed Meal Tests
- AIClient Interface
- Pantry Editing Tests
- Servings & Batch Tests
- Cuisine & Macro Doc Concepts
- Ingredient Naming Docs
- Week Generate Dialog
- Ingredient Composition
- Macro Refit Command
- Cuisine Prompt Line
- Context Template & User Notes
- Mid Migrations
- Tracked Meal Deletion Tests
- Questionnaire Options
- Macro Least Squares
- User Rules Tests
- Chat & Shared Registry Docs
- Adherence Docs
- Cuisine Spacing
- Frontend Package Config
- AIError Handling
- Background Generation Thread
- Weekly Budget Tests
- Fake Chat Models
- Cuisine Catalog
- Account Docs
- Push Reminder UI
- Recipe Macro Compute
- Fit To Target
- Account & Usage Concepts
- Questionnaire Preview Route
- Spy Model Fixture
- Pantry Expiry Tests
- Weight Recalc Proposal
- Questionnaire Speed Tests
- Cuisine Deck Labels
- Frontend Dependencies
- Frontend Dev Dependencies
- Frontend Scripts
- Shared Recipes Migration
- Recipe Fork
- Pantry Week Fixture
- Fake Completions Endpoint
- Interface Docs
- Migration 0002 AI Models
- Migration 0003 Auto Generate
- Migration 0004 User Notes
- Migration 0005 Generation State
- Migration 0007 Skipped Meals
- Migration 0008 Shopping Chat
- Migration 0009 Manual Category
- Migration 0013 Real Prices
- Migration 0014 Lock Removal
- Migration 0016 Norm Rules
- Migration 0019 Paid Price
- Migration 0021 Computed Macros
- Migration 0023 Weight History
- Migration 0025 Pantry Expiry
- Migration 0026 Push Reminders
- Migration 0027 Weekly Budget
- Migration 0028 AI Cost
- Migration 0029 Servings Batch
- Chat Meal Fixture
- Prompt Render Guard
- Shopping Chat Week Fixture
- Pantry Subtraction Test
- Kcal Consistency Guard
- Empty Rules Invariance
- Mobile-first Layout
- Pantry Default Quantity Test
- Whole Package Pantry Test
- Uncheck Clears Quantity
- Price Per Package Test
- Seed Keeps Manual Price
- Paid Price Stability Test
- Multi-unit Ingredient Test
- Recipe Origin Tag
- Computed Macros Rule
- PDF via pypdf Concept
- Page Split Layout

## God Nodes (most connected - your core abstractions)
1. `User` - 127 edges
2. `Ingredient` - 81 edges
3. `WeekPlan` - 74 edges
4. `FakeModel` - 67 edges
5. `PlannedMeal` - 57 edges
6. `Recipe` - 56 edges
7. `useApp()` - 51 edges
8. `MealSlot` - 44 edges
9. `DayPlan` - 41 edges
10. `lucide-react` - 38 edges

## Surprising Connections (you probably didn't know these)
- `Calcolo lista della spesa (aggrega, sottrai base e dispensa)` --semantically_similar_to--> `Lista della spesa come funzione del piano (rebuild_shopping_list)`  [INFERRED] [semantically similar]
  .claude/DietAI_Technical_Spec.md → CLAUDE.md
- `Blocco settimanale dopo la spesa (lock 7 giorni)` --conceptually_related_to--> `Lista della spesa come funzione del piano (rebuild_shopping_list)`  [INFERRED]
  .claude/DietAI_Technical_Spec.md → CLAUDE.md
- `README DietAI` --references--> `Blocco settimanale dopo la spesa (lock 7 giorni)`  [INFERRED]
  README.md → .claude/DietAI_Technical_Spec.md
- `Anti-spreco: ingredienti parziali in un unico prompt batch` --rationale_for--> `Una chiamata sola per settimana (generazione)`  [INFERRED]
  .claude/DietAI_Technical_Spec.md → CLAUDE.md
- `Stack originale (TypeScript, Redux Toolkit, Tailwind, SQLAlchemy async)` --conceptually_related_to--> `Le rotte sono def, mai async def`  [INFERRED]
  .claude/DietAI_Technical_Spec.md → CLAUDE.md

## Import Cycles
- 3-file cycle: `frontend/src/App.jsx -> frontend/src/pages/DietPage.jsx -> frontend/src/components/Questionnaire.jsx -> frontend/src/App.jsx`
- 3-file cycle: `frontend/src/App.jsx -> frontend/src/pages/OnboardingPage.jsx -> frontend/src/components/Questionnaire.jsx -> frontend/src/App.jsx`
- 3-file cycle: `frontend/src/App.jsx -> frontend/src/pages/DietPage.jsx -> frontend/src/components/FrequenciesCard.jsx -> frontend/src/App.jsx`
- 3-file cycle: `frontend/src/App.jsx -> frontend/src/pages/ShoppingPage.jsx -> frontend/src/components/ReceiptReader.jsx -> frontend/src/App.jsx`
- 3-file cycle: `frontend/src/App.jsx -> frontend/src/pages/ShoppingPage.jsx -> frontend/src/components/ShoppingChat.jsx -> frontend/src/App.jsx`
- 3-file cycle: `frontend/src/App.jsx -> frontend/src/pages/MealDetailPage.jsx -> frontend/src/components/EatenInstead.jsx -> frontend/src/App.jsx`
- 3-file cycle: `frontend/src/App.jsx -> frontend/src/pages/MealDetailPage.jsx -> frontend/src/components/MealChat.jsx -> frontend/src/App.jsx`
- 3-file cycle: `frontend/src/App.jsx -> frontend/src/pages/SettingsPage.jsx -> frontend/src/components/NormalizationSettings.jsx -> frontend/src/App.jsx`
- 3-file cycle: `frontend/src/App.jsx -> frontend/src/pages/SettingsPage.jsx -> frontend/src/components/ReminderSettings.jsx -> frontend/src/App.jsx`
- 3-file cycle: `frontend/src/App.jsx -> frontend/src/pages/TrackingPage.jsx -> frontend/src/components/WeightView.jsx -> frontend/src/App.jsx`
- 3-file cycle: `frontend/src/App.jsx -> frontend/src/pages/TrackingPage.jsx -> frontend/src/components/YearHeatmap.jsx -> frontend/src/App.jsx`

## Hyperedges (group relationships)
- **Procedure del progetto DietAI (skill .claude)** — _claude_skills_avvia_dietai_skill, _claude_skills_ingredienti_e_nomi_skill, _claude_skills_interfaccia_skill, _claude_skills_migrazione_db_skill, _claude_skills_nuova_funzione_skill, _claude_skills_prompt_ai_skill, _claude_skills_rilascio_skill [EXTRACTED 1.00]
- **Invarianti backend controllate dal revisore** — claude_sync_routes_rule, claude_user_id_filter_rule, claude_full_entity_response_rule, claude_prompts_render_rule, claude_shopping_as_function, _claude_agents_revisore_dietai [EXTRACTED 1.00]
- **Infrastruttura di deploy e sviluppo** — docker_compose, docker_compose_dev, backend_requirements, _claude_skills_rilascio_skill_coolify_git_source, claude_encryption_key_immutable [INFERRED 0.85]
- **Cio' che si puo' calcolare lo calcola il codice, non il modello** — docs_dieta_questionnaire, docs_cucine_draw, docs_dieta_freq_assign, docs_macro_computed_macros, docs_piano_batch_days [INFERRED 0.85]
- **Stato, diario ed errore della generazione sul WeekPlan** — docs_generazione_generation_state, docs_generazione_generation_failure, docs_generazione_generation_progress, docs_generazione_in_background [EXTRACTED 1.00]
- **Pipeline di normalizzazione dei nomi degli ingredienti** — docs_ingredienti_normalize_name, docs_ingredienti_segni, docs_ingredienti_varianti, docs_ingredienti_merge_lists, docs_ingredienti_catalog_forms, docs_ingredienti_normalization_rule [EXTRACTED 1.00]

## Communities (156 total, 43 thin omitted)

### Community 0 - "Shopping List Aggregation"
Cohesion: 0.05
Nodes (38): main(), PantryItem, ShoppingList, ShoppingListItem, check_item(), clear_shopping_list(), complete(), export() (+30 more)

### Community 1 - "Config & Input Schemas"
Cohesion: 0.06
Nodes (36): model_matches_provider(), BaseIngredient, ExcludedIngredient, NormalizationRule, add_base(), add_default_base(), add_excluded(), add_normalization() (+28 more)

### Community 2 - "Week Planner Core"
Cohesion: 0.07
Nodes (32): _apply_generated_week(), _as_utc(), _base_names(), _budget_line(), build_context(), clear_generation_progress(), cuisine_shares(), diet_frequencies() (+24 more)

### Community 3 - "DB Session & Admin CLI"
Cohesion: 0.08
Nodes (20): main(), make_admin(), User, main(), main(), pick_user(), reset_password(), main() (+12 more)

### Community 4 - "Project Rules & Skills"
Cohesion: 0.06
Nodes (41): Agente revisore-dietai, DietAI Technical Spec (storica), Modello dati originale (User, DietPlan, MealSlot, WeekPlan, DayPlan, PlannedMeal, Recipe, Ingredient, ShoppingList...), Stack originale (TypeScript, Redux Toolkit, Tailwind, SQLAlchemy async), Prompt originali (parsing PDF, piano settimanale, rigenerazione, chat [RECIPE_UPDATE], sostituzione), Pasti ricorrenti (daily/weekly), SEASONAL_PRODUCTS (stagionalità prodotti italiani), Calcolo lista della spesa (aggrega, sottrai base e dispensa) (+33 more)

### Community 5 - "App Shell & Settings UI"
Cohesion: 0.09
Nodes (34): setSessionExpiredHandler(), App(), AppContext, AuthenticatedApp(), AuthContext, AuthProvider(), useAuth(), AiUsageCard() (+26 more)

### Community 6 - "Push Reminders"
Cohesion: 0.05
Nodes (20): _avvia_promemoria(), _b64url(), meals_to_answer(), _private_key(), public_key(), reminder_payload(), send(), send_due_reminders() (+12 more)

### Community 7 - "AI Usage & Model Catalog"
Cohesion: 0.06
Nodes (29): AIUsage, get_ai_models(), _usage_dict(), list_models(), _normalize(), _price_per_million(), _cost_from_catalog(), recorder() (+21 more)

### Community 8 - "Auth & JWT Tokens"
Cohesion: 0.10
Nodes (23): _as_utc(), clear_auth_cookies(), consume_refresh_token(), create_access_token(), get_current_admin(), get_current_user(), get_password_hash(), _hash_refresh_token() (+15 more)

### Community 9 - "Recipes Router"
Cohesion: 0.07
Nodes (30): get_current_user_id(), get_db(), ApiKeyRequest, AssignMealRequest, BoughtQuantityRequest, ChangePasswordRequest, CheckItemRequest, DailyTargets (+22 more)

### Community 10 - "Weight Tracking"
Cohesion: 0.09
Nodes (19): WeightEntry, delete_weight(), get_weight(), put_weight(), weekly(), year(), get_active_diet(), week_meals() (+11 more)

### Community 11 - "Questionnaire Nutrition Math"
Cohesion: 0.08
Nodes (19): basal_metabolic_rate(), compute_plan(), test_a_mano_si_scende_anche_sotto_i_pavimenti_della_formula(), test_i_macro_tornano_alle_calorie(), test_i_pasti_restano_scritti_anche_dicendo_solo_quanti(), test_i_pasti_si_scelgono_uno_per_uno(), test_i_totali_corretti_a_mano_vincono_sulla_formula(), test_i_totali_sbloccati_arrivano_fino_ai_pasti() (+11 more)

### Community 12 - "Meal & Shopping Chat"
Cohesion: 0.11
Nodes (20): MealChatMessage, ShoppingChatMessage, _apply_recipes_update(), clear_history(), clear_shopping_history(), _editable_meals(), get_history(), _get_meal() (+12 more)

### Community 13 - "Alembic Env & Model Slugs"
Cohesion: 0.07
Nodes (13): _clean(), default_model(), ai_owner(), model_for(), _provider_message(), test_esiste_un_default_per_ogni_ruolo(), test_il_modello_scelto_sostituisce_il_default(), test_forma_dello_slug() (+5 more)

### Community 14 - "Duplicate Recipe Tests"
Cohesion: 0.09
Nodes (19): FakeChat, ModelloRipetitivo, pasto(), ricettario(), settimana_ripetitiva(), test_anche_la_memoria_di_un_pasto_rimandato_resta_com_era(), test_annullare_il_salto_svuota_la_casella_giusta(), test_generare_la_settimana_dopo_non_ricrea_gli_stessi_piatti() (+11 more)

### Community 15 - "Multi-week Shopping Tests"
Cohesion: 0.07
Nodes (17): fake_ai(), prossima(), quantita(), questa(), spunta_tutto(), test_a_spesa_fatta_le_ricette_si_cambiano_lo_stesso(), test_generare_la_prossima_riallinea_la_lista_di_questa(), test_il_piano_oltre_l_orizzonte_viene_dichiarato() (+9 more)

### Community 16 - "DayPlan & PlannedMeal"
Cohesion: 0.09
Nodes (18): DayPlan, PlannedMeal, apply_recurring_meals(), _batch_groups(), _casella_vissuta(), clear_meal_cell(), _empty_meal(), ensure_week_structure() (+10 more)

### Community 17 - "WeekPlan & Planning Routes"
Cohesion: 0.14
Nodes (20): WeekPlan, generation_progress(), get_current_week(), get_next_week(), _get_week(), get_week_by_date(), dashboard(), list_weeks() (+12 more)

### Community 18 - "Recipe Model & Macro Recompute"
Cohesion: 0.13
Nodes (19): Recipe, main(), _add_ingredients(), _clamp_difficulty(), _clean_ingredients(), create_recipe(), _dict(), fit_recipe_data() (+11 more)

### Community 19 - "Generation Progress Log"
Cohesion: 0.10
Nodes (18): GenerationProgress, api_key(), _backend(), _chiama(), _Chunk, _Completions, _Delta, test_durante_la_generazione_la_pagina_legge_il_diario() (+10 more)

### Community 20 - "Ingredient Seed & Categories"
Cohesion: 0.07
Nodes (16): seed_ingredients(), apply_catalog_composition(), guess_category(), season_months_for(), test_il_seed_non_tocca_la_composizione_corretta_a_mano(), reparto(), seitan(), seitan_id() (+8 more)

### Community 21 - "Frequencies & Questionnaire UI"
Cohesion: 0.15
Nodes (27): FrequenciesCard(), DEFAULTS, LIMITS, MealSplit(), NUMBERS, Questionnaire(), TOTALI, addMeal() (+19 more)

### Community 22 - "Meal Slots & Cell Actions"
Cohesion: 0.12
Nodes (13): MealSlot, assign_meal(), clear_meal(), _eaten_estimate(), generate(), _get_meal(), regenerate(), set_day_skipped() (+5 more)

### Community 23 - "User Normalization Rules"
Cohesion: 0.12
Nodes (22): get_or_create_ingredient(), load_rules(), _regola(), test_da_li_in_poi_i_nomi_nuovi_ci_finiscono_dentro(), test_l_anteprima_dice_cosa_verrebbe_fuso_senza_fondere_niente(), test_l_anteprima_mostra_il_disastro_prima_che_succeda(), test_la_lista_dice_quali_sono_spenti(), test_la_lista_mette_insieme_termini_di_serie_e_aggiunti() (+14 more)

### Community 24 - "FastAPI App & Test Fixtures"
Cohesion: 0.08
Nodes (8): health(), client(), db(), diet(), generazione_in_primo_piano(), guest_client(), macro_dichiarati(), oggi_e_lunedi()

### Community 25 - "End-to-end Flow Tests"
Cohesion: 0.08
Nodes (9): test_a_spesa_fatta_il_piano_resta_modificabile(), test_conversione_unita(), test_correggere_l_unita_dalla_dispensa_ripara_la_lista(), test_formattazione_quantita(), test_la_lista_dice_quanto_ce_n_e_gia_in_casa(), test_la_spesa_fatta_riempie_la_dispensa_e_svuota_la_lista(), test_senza_niente_in_casa_non_c_e_niente_da_spiegare(), test_una_scorta_in_un_altra_unita_si_dichiara_invece_di_sparire() (+1 more)

### Community 26 - "Diet Plan & PDF Import"
Cohesion: 0.16
Nodes (12): DietPlan, create_diet_from_questionnaire(), create_diet_manually(), _deactivate_previous(), get_current_diet(), _replace_meals(), _serialize_diet(), update_diet_meals() (+4 more)

### Community 27 - "Admin & Session Revocation"
Cohesion: 0.13
Nodes (12): revoke_all_sessions(), add_user(), ai_usage(), delete_user(), list_users(), reset_user_password(), _serialize(), _target() (+4 more)

### Community 28 - "Fixed Meals Tests"
Cohesion: 0.10
Nodes (14): colazione_fissa(), colazioni(), pasto(), test_e_non_ricomincia_da_solo(), test_eliminare_svuota_la_casella_e_basta(), test_eliminare_toglie_anche_il_segno_di_fisso(), test_eliminare_toglie_il_piatto_dalla_spesa(), test_il_pasto_fisso_riempie_la_settimana_dopo() (+6 more)

### Community 29 - "Selective Generation Tests"
Cohesion: 0.12
Nodes (15): fake_ai(), _client(), _fake_recipe(), FakeModel, _genera(), test_genera_solo_i_giorni_scelti(), test_genera_solo_i_pasti_scelti(), test_giorni_e_pasti_insieme() (+7 more)

### Community 30 - "Skipped Meals Tests"
Cohesion: 0.13
Nodes (17): fake_ai(), pasto(), _pollo(), settimana_generata(), test_funziona_anche_a_spesa_fatta(), test_gli_altri_giorni_non_si_muovono(), test_ho_mangiato_altro_manda_la_ricetta_in_fondo(), test_i_totali_del_giorno_scendono_col_pasto_saltato() (+9 more)

### Community 31 - "PDF Extraction & AI Provider"
Cohesion: 0.13
Nodes (11): extract_text(), looks_scanned(), build_pdf(), FakeDietModel, test_dal_pdf_si_estrae_il_testo(), test_la_chiave_deve_avere_il_prefisso_del_provider(), test_un_file_illeggibile_non_esplode(), test_un_pdf_senza_testo_e_riconosciuto_come_scansione() (+3 more)

### Community 32 - "Shopping Chat Tests"
Cohesion: 0.17
Nodes (16): etichetta(), pranzo_id(), _senza_zucchine(), test_anche_a_spesa_fatta_la_chat_cambia_le_ricette(), test_cambia_la_ricetta_e_rifa_la_lista(), test_cambia_piu_ricette_in_un_colpo(), test_il_procedimento_a_lista_non_fa_500(), test_il_prompt_riceve_indice_e_lista() (+8 more)

### Community 33 - "Pantry Purchase Flow"
Cohesion: 0.08
Nodes (17): test_a_spesa_fatta_la_riga_sparisce_dalla_lista(), test_cancellare_il_prezzo_rimette_quello_del_catalogo(), test_cancellare_il_prezzo_toglie_anche_quello_della_riga(), test_correggere_la_quantita_non_riscrive_il_prezzo(), test_il_prezzo_scritto_conta_nel_totale(), test_il_prezzo_segnato_diventa_il_prezzo_dell_ingrediente(), test_il_prezzo_si_segna_anche_a_spesa_fatta(), test_il_prezzo_vero_vale_anche_per_le_liste_dopo() (+9 more)

### Community 34 - "Two-account Isolation Tests"
Cohesion: 0.11
Nodes (14): _ricetta(), test_cancellare_un_account_porta_via_i_suoi_dati(), test_il_ricettario_non_e_in_comune(), test_l_admin_rimette_la_password_a_chi_l_ha_persa(), test_l_amministratore_non_si_sospende_da_solo(), test_l_interruttore_ai_spegne_le_generazioni_ma_non_l_app(), test_l_ospite_non_cambia_i_modelli_nemmeno_di_nascosto(), test_l_ospite_vede_la_chiave_dell_admin_come_propria() (+6 more)

### Community 35 - "Meal Detail & Recipe View"
Cohesion: 0.19
Nodes (17): useApp(), EatenInstead(), MealChat(), DIFFICULTY, NUMERI_DA, Nutrient(), passi(), RecipeView() (+9 more)

### Community 36 - "Planning Page & Day Dots"
Cohesion: 0.18
Nodes (19): DayDots(), statoPasto(), durata(), GenerationLog(), MealCard(), todayIso(), WeekGrid(), MOTIVI (+11 more)

### Community 37 - "Cuisine Context Tests"
Cohesion: 0.11
Nodes (12): _righe_dei_giorni(), _scegli(), test_con_una_cucina_sola_non_si_sorteggia_e_il_prompt_resta_quello_di_prima(), test_il_contesto_dice_che_il_sorteggio_e_gia_fatto(), test_il_corpo_senza_cucine_le_svuota(), test_la_ricetta_dice_da_che_paese_viene(), test_la_settimana_generata_rispetta_le_quote(), test_le_cucine_arrivano_nel_contesto_di_ogni_generazione() (+4 more)

### Community 38 - "Skipped Days Tests"
Cohesion: 0.12
Nodes (11): fake_ai(), oggi(), quantita(), settimana_generata(), test_i_giorni_passati_restano_dove_sono(), test_il_pasto_saltato_non_esce_dalla_spesa_ma_si_sposta(), test_la_generazione_non_riempie_i_giorni_saltati(), test_per_i_giorni_passati_non_si_compra_piu() (+3 more)

### Community 39 - "Generation & Planning Docs"
Cohesion: 0.10
Nodes (17): lib/generation.js (conta caselle identica al server), generate_week only_missing=True (riempie solo i buchi, PASTI GIA' ASSEGNATI), WeekGenerateDialog (selezione days e slot_ids), Home: pasti sopra la piega (.day-summary, .today-grid, .shop-bar), recent_adherence (spia aderenza ultime quattro settimane), docs/piano.md - Il piano della settimana, 'Lo faccio io' (MealSlot.auto_generate=False), Pasti fissi (_is_fixed, apply_recurring_meals) (+9 more)

### Community 40 - "Cuisine Picker & Quotas UI"
Cohesion: 0.20
Nodes (19): CuisinePicker(), piatto(), aggiungi(), normalizza(), num(), QUOTA_MINIMA, riparti(), tetto() (+11 more)

### Community 41 - "Delete User Command"
Cohesion: 0.17
Nodes (13): delete_user(), inventory(), main(), pick_target(), test_anche_un_amministratore_purche_non_sia_l_ultimo(), test_cancella_l_account_e_i_suoi_dati(), test_l_inventario_conta_quello_che_sparisce(), test_l_ultimo_amministratore_no() (+5 more)

### Community 42 - "Builtin Name Rules"
Cohesion: 0.11
Nodes (9): _alt(), _Builtin, builtin_groups(), _builtin_normalize(), builtin_rules(), _readable(), _segni(), _term() (+1 more)

### Community 43 - "Name Normalization"
Cohesion: 0.15
Nodes (13): normalize_name(), test_due_alimenti_diversi_non_si_toccano(), test_due_voci_di_catalogo_non_finiscono_sulla_stessa_riga(), test_i_due_apostrofi_finiscono_sulla_stessa_riga(), test_i_nomi_del_catalogo_sopravvivono_alla_normalizzazione(), test_i_qualificatori_spariscono(), test_il_peperoncino_non_e_un_peperone(), test_la_mappa_del_singolare_non_scavalca_il_catalogo() (+5 more)

### Community 44 - "Meal Chat Tests"
Cohesion: 0.16
Nodes (16): _risposta_con_ricetta(), test_il_prompt_di_sistema_arriva_completo_al_modello(), test_la_chat_aggiorna_davvero_la_ricetta(), test_la_lista_della_spesa_segue_la_modifica(), test_lo_storico_conserva_domanda_e_risposta(), test_lo_storico_precedente_viene_rimandato_al_modello(), test_lo_storico_si_puo_svuotare(), test_se_sbaglia_due_volte_la_risposta_non_si_perde() (+8 more)

### Community 45 - "Shared UI Components"
Cohesion: 0.19
Nodes (17): formatDate(), formatMoney(), ConfirmDialog(), MacroBar(), ReceiptReader(), rimpicciolisci(), useDueColonne(), useMediaQuery() (+9 more)

### Community 46 - "Food Frequency Groups"
Cohesion: 0.12
Nodes (12): frequency_options(), assign(), clean(), label(), options(), prompt_hint(), report(), test_il_resoconto_dice_cosa_manca_e_cosa_avanza() (+4 more)

### Community 47 - "Frequency Assignment Tests"
Cohesion: 0.10
Nodes (6): food_of(), con_frequenze(), ModelloCheRicorda, test_a_che_gruppo_appartiene_un_ingrediente(), test_i_minimi_si_assegnano_e_si_sparpagliano(), test_la_settimana_dice_quante_volte_c_e_ogni_gruppo()

### Community 48 - "Tracking UI & Empty States"
Cohesion: 0.24
Nodes (17): formatNumber(), EmptyState(), LoadError(), giorno(), WeightChart(), WeightView(), buildCalendar(), mondayOf() (+9 more)

### Community 49 - "Recipe Merging"
Cohesion: 0.17
Nodes (12): main(), duplicate_groups(), find_twin(), _find_twin(), _items_key(), _macros_key(), merge_duplicate_recipes(), recipe_items_key() (+4 more)

### Community 50 - "Push Subscriptions & Prefs"
Cohesion: 0.19
Nodes (11): PushSubscription, UserPreferences, get_push(), set_reminder(), _state(), subscribe(), test_notification(), unsubscribe() (+3 more)

### Community 51 - "Recipe Archive Actions"
Cohesion: 0.16
Nodes (11): create_custom_recipe(), delete_recipe(), favorite_recipe(), _get_recipe(), list_recipes(), rate_recipe(), substitute_ingredient(), _usage_history() (+3 more)

### Community 52 - "Ingredient Merge & Registry"
Cohesion: 0.15
Nodes (10): main(), Ingredient, merge_duplicates(), _merge_rows(), preview_rule(), test_la_dispensa_si_somma_invece_di_perdersi(), test_le_due_scatolette_di_tonno_tornano_una(), test_le_ricette_seguono_l_ingrediente() (+2 more)

### Community 53 - "Cuisine Draw"
Cohesion: 0.10
Nodes (11): draw(), test_alzare_una_quota_alza_le_sue_caselle(), test_con_una_quota_alta_la_fila_cambia_comunque_ogni_settimana(), test_due_sorteggi_non_danno_lo_stesso_ordine(), test_il_sorteggio_rispetta_la_percentuale_su_questa_settimana(), test_la_stessa_cucina_non_esce_due_giorni_di_fila(), test_le_poche_capitano_in_tutti_i_giorni_della_settimana(), test_le_ripetizioni_stanno_lontane_fin_dove_le_quote_lo_permettono() (+3 more)

### Community 54 - "Pantry Staples Tests"
Cohesion: 0.14
Nodes (13): pranzo(), scorta(), test_a_fine_settimana_la_dispensa_racconta_quello_che_resta(), test_chi_non_si_scala_lo_dice_col_motivo(), test_correggersi_rimette_in_dispensa_quello_che_era_stato_tolto(), test_la_scorta_finita_sparisce_dalla_dispensa(), test_non_si_scala_piu_di_quello_che_c_era(), test_quello_che_non_c_e_in_dispensa_non_si_scala() (+5 more)

### Community 55 - "Reasoning Budget Tests"
Cohesion: 0.25
Nodes (13): _backend(), _call(), _Choice, _Response, test_al_contenuto_resta_sempre_la_maggioranza_del_budget(), test_budget_esaurito_lo_dice_chiaramente(), test_contenuto_nullo_non_diventa_una_stringa_none(), test_i_compiti_brevi_chiedono_ragionamento_basso() (+5 more)

### Community 56 - "Year View Tests"
Cohesion: 0.18
Nodes (13): fake_ai(), oggi(), a(), segna(), settimana(), test_i_giorni_non_ancora_arrivati_non_allungano_la_serie(), test_i_giorni_non_tracciati_restano_fuori(), test_la_serie_conta_i_giorni_pieni_di_fila() (+5 more)

### Community 57 - "Week Browsing Tests"
Cohesion: 0.15
Nodes (10): fake_ai(), lunedi(), oggi(), imposta(), test_anche_il_passato_si_modifica(), test_avanti_la_settimana_nasce_quando_la_si_apre(), test_il_pasto_passato_si_puo_ancora_tracciare(), test_la_settimana_scorsa_si_rilegge_intera() (+2 more)

### Community 58 - "API Key Encryption"
Cohesion: 0.17
Nodes (9): decrypt_api_key(), encrypt_api_key(), _fernet(), set_api_key(), test_chiave_assente(), test_chiave_cambiata_non_decifra(), test_chiave_malformata_dice_quanto_e_lunga(), test_cifra_e_decifra() (+1 more)

### Community 59 - "Diet Change Realign Tests"
Cohesion: 0.16
Nodes (10): fake_ai(), pasti(), pasto(), settimana_generata(), test_la_ricetta_gia_generata_resta_al_suo_posto(), test_quello_che_era_gia_segnato_non_si_perde(), test_ricalcolare_i_macro_non_raddoppia_i_pasti(), test_senza_una_settimana_gia_letta_non_cambia_niente() (+2 more)

### Community 60 - "Fake AI Fixtures"
Cohesion: 0.14
Nodes (7): fake_ai(), FakeModel, esegui(), lavori(), test_finito_il_lavoro_la_settimana_e_piena(), test_un_fallimento_nel_thread_finisce_sulla_settimana(), test_una_seconda_post_durante_la_generazione_e_rifiutata()

### Community 61 - "On-request Generation Tests"
Cohesion: 0.12
Nodes (6): casella_vuota(), fake_ai(), ModelloCheRicorda, test_il_corpo_resta_facoltativo(), test_le_regole_di_varieta_decadono_solo_a_parole_del_sistema(), test_una_richiesta_lunghissima_e_un_422()

### Community 62 - "Generation State Tests"
Cohesion: 0.16
Nodes (9): api_key(), test_durante_la_generazione_lo_stato_e_visibile_nel_database(), generate_json(), test_la_pagina_ritrova_la_generazione_in_corso(), test_se_il_modello_fallisce_lo_stato_viene_ripulito(), test_una_generazione_dimenticata_scade(), test_una_risposta_di_forma_sbagliata_non_blocca_la_settimana(), test_una_seconda_generazione_in_parallelo_viene_rifiutata() (+1 more)

### Community 63 - "Week Regeneration Tests"
Cohesion: 0.14
Nodes (8): ContaChiamate, fake_ai(), test_anche_a_spesa_fatta_si_rigenera(), test_la_generazione_normale_riempie_solo_i_vuoti(), test_le_ricette_conservate_arrivano_al_modello_come_contesto(), test_le_ricette_vecchie_restano_nel_ricettario(), test_rigenera_tutto_rifa_ogni_ricetta(), _titoli()

### Community 64 - "Frontend API & Service Worker"
Cohesion: 0.18
Nodes (13): SHELL, api, NO_REFRESH_RETRY, raw(), request(), text(), upload(), ChatText() (+5 more)

### Community 65 - "Anthropic Backend"
Cohesion: 0.13
Nodes (5): _AnthropicBackend, _empty_response_error(), _OpenAICompatibleBackend, _reasoning_delta(), test_diagnosi_per_ogni_motivo_di_arresto()

### Community 66 - "Cuisine Preference Cleaning"
Cohesion: 0.12
Nodes (9): _as_shares(), clean(), keys_of(), unknown(), test_l_ordine_non_dipende_da_come_si_e_cliccato(), test_le_quote_sommano_sempre_a_cento(), test_un_elenco_senza_quote_vale_parti_uguali(), test_una_chiave_fuori_catalogo_si_riconosce() (+1 more)

### Community 67 - "Early Migrations"
Cohesion: 0.12
Nodes (5): upgrade(), upgrade(), upgrade(), upgrade(), upgrade()

### Community 68 - "Recipe Ingredients & Cereal Repair"
Cohesion: 0.18
Nodes (7): RecipeIngredient, _cereale_citato(), main(), _tidy(), _ricetta(), test_dove_il_testo_non_decide_non_si_indovina(), test_i_cereali_fusi_tornano_al_loro_nome()

### Community 69 - "Weight History Tests"
Cohesion: 0.17
Nodes (7): oggi(), test_il_questionario_e_la_prima_pesata(), test_la_dieta_del_nutrizionista_non_si_ricalcola(), test_le_pesate_stanno_in_ordine_di_data(), test_oltre_la_soglia_si_propone_il_ricalcolo(), test_un_giorno_futuro_non_si_segna(), test_una_pesata_si_cancella()

### Community 70 - "Meal Detail Tests"
Cohesion: 0.16
Nodes (5): ModelloDiProva, pasto(), test_la_settimana_dice_dove_ci_si_trova(), test_ogni_risposta_porta_la_settimana(), _fake_recipe()

### Community 71 - "Computed Macro Tests"
Cohesion: 0.17
Nodes (9): calcolo_acceso(), generata(), righe(), test_la_settimana_generata_ha_i_macro_calcolati_e_nel_target(), test_la_somma_la_fa_python(), test_ogni_voce_del_catalogo_ha_la_sua_composizione(), test_pezzi_e_pizzichi(), test_un_ingrediente_sconosciuto_ferma_il_conto() (+1 more)

### Community 72 - "Eaten Instead Tests"
Cohesion: 0.19
Nodes (10): ModelloCheStima, pasto(), settimana(), test_cambiare_risposta_cancella_la_stima(), test_il_pasto_di_un_altro_non_si_tocca(), test_il_testo_vuoto_cancella(), test_l_andamento_conta_quello_che_si_e_mangiato_davvero(), test_la_stima_si_salva_sul_pasto() (+2 more)

### Community 73 - "Receipt Scan Tests"
Cohesion: 0.16
Nodes (7): articolo(), lista(), ModelloCheLegge, test_il_modello_riceve_gli_articoli_con_il_loro_id(), test_l_immagine_parte_nella_forma_del_suo_backend(), test_le_righe_abbinate_portano_prezzo_quantita_e_spunta(), test_una_quantita_in_un_unita_che_non_si_converte_non_si_inventa()

### Community 74 - "Self-managed Meal Tests"
Cohesion: 0.13
Nodes (3): diet_con_colazione_mia(), fake_ai(), test_la_generazione_salta_il_pasto_gestito_dall_utente()

### Community 76 - "Pantry Editing Tests"
Cohesion: 0.16
Nodes (7): dispensa(), test_il_nome_si_cambia_e_la_riga_punta_a_un_altro_ingrediente(), test_la_quantita_si_puo_anche_togliere(), test_rinominare_su_qualcosa_che_c_e_gia_viene_rifiutato(), test_riscrivere_lo_stesso_nome_non_da_conflitto(), test_un_nome_che_non_resta_niente_viene_rifiutato(), test_una_riga_di_un_altro_utente_non_si_tocca()

### Community 77 - "Servings & Batch Tests"
Cohesion: 0.27
Nodes (10): genera(), imposta(), ModelloCheRicorda, pasta_in_lista(), test_il_batch_chiede_un_piatto_per_gruppo_di_giorni(), test_il_batch_conta_ogni_giorno_nella_spesa(), test_l_ho_seguito_scala_per_tutte_le_persone(), test_la_dieta_ricorda_persone_e_batch() (+2 more)

### Community 78 - "Cuisine & Macro Doc Concepts"
Cohesion: 0.14
Nodes (11): cuisines.draw() (sorteggio una cucina per giorno, fatto da Python), PER_GIORNO / CUCINA accanto al giorno in DA GENERARE, regenerate_meal sorteggia con avoid, freq.assign (proteina per pasto principale, PROTEINA: in DA GENERARE), Rigenerazione singolo pasto con user_request (SINGLE_MEAL_SYSTEM), App scura, tre font, --accent vs --accent-fill, docs/macro.md - I macro delle ricette, Composizione per 100 g: catalogo, ensure_composition (AI), utente (+3 more)

### Community 79 - "Ingredient Naming Docs"
Cohesion: 0.15
Nodes (12): docs/ingredienti.md - Nomi degli ingredienti e accorpamenti, _CATALOG_FORMS (singolare/plurale derivato dal catalogo), merge_ingredients / repair_cereals, NormalizationRule / load_rules(db) (alias, noise, off), normalize_name (via com'e' messo, resta cos'e'), _segni (apostrofi, spazi, elisioni), _VARIANTI (stessa parola scritta in due modi), fit_to_target (ritocco delle tre leve fuori dal +-10%) (+4 more)

### Community 80 - "Week Generate Dialog"
Cohesion: 0.28
Nodes (12): leggiEsclusi(), plurale(), scriviEsclusi(), WeekGenerateDialog(), contaSelezione(), daGenerare(), generabile(), giorniPredefiniti() (+4 more)

### Community 81 - "Ingredient Composition"
Cohesion: 0.18
Nodes (7): ensure_composition(), has_composition(), missing_composition(), _righe(), ModelloCheConosce, test_un_nome_nuovo_si_impara_una_volta(), test_una_stima_che_fallisce_non_ferma_niente()

### Community 82 - "Macro Refit Command"
Cohesion: 0.21
Nodes (6): Esito, _items(), refit_future_meals(), _target(), calcolo_acceso(), test_le_ricette_fuori_target_si_ritoccano_e_il_passato_no()

### Community 83 - "Cuisine Prompt Line"
Cohesion: 0.15
Nodes (7): prompt_line(), test_i_condimenti_non_si_riducono_tutti_alla_salsa_di_soia(), test_la_sola_italiana_non_si_porta_dietro_la_spiegazione(), test_piu_cucine_si_dicono_con_le_loro_quote(), test_senza_scelte_il_modello_ha_mano_libera(), test_un_tag_malscritto_non_fa_saltare_la_rigenerazione(), test_una_cucina_straniera_porta_sempre_il_vincolo_degli_ingredienti()

### Community 84 - "Context Template & User Notes"
Cohesion: 0.14
Nodes (8): CONTEXT_TEMPLATE / build_context, docs/cucine.md - Le cucine del mondo, clean() (quote che sommano a 100, ordine del catalogo), Catalogo chiuso delle cucine (utils/cuisines.py, UserPreferences.cuisines), lib/quote.js e CuisinePicker (cursori proporzionali, saveTraPoco), DietPlan.frequencies (utils/frequencies.FOODS), frequency_report (conta cosa c'e' davvero nel piano, SOGLIA_G), PantryItem.expires_on / _pantry_descriptions (prima cio' che scade)

### Community 85 - "Mid Migrations"
Cohesion: 0.22
Nodes (5): upgrade(), upgrade(), upgrade(), downgrade(), upgrade()

### Community 86 - "Tracked Meal Deletion Tests"
Cohesion: 0.23
Nodes (6): pranzo(), scorta(), settimana(), test_eliminare_pasto_non_tracciato_non_cambia_dispensa(), test_eliminare_un_pasto_tracciato_rimette_gli_ingredienti_in_dispensa(), test_rigenerare_un_pasto_tracciato_rimette_gli_ingredienti_in_dispensa()

### Community 87 - "Questionnaire Options"
Cohesion: 0.18
Nodes (5): questionnaire_options(), default_selection(), options(), _share_out(), split_meals()

### Community 88 - "Macro Least Squares"
Cohesion: 0.20
Nodes (5): _det3(), grams_of(), _limita(), _minimi_quadrati(), _risolvi3()

### Community 89 - "User Rules Tests"
Cohesion: 0.23
Nodes (7): _set_rules(), test_le_regole_arrivano_alla_generazione_settimanale(), generate_json(), test_le_regole_finiscono_nel_contesto_dei_prompt(), test_le_regole_si_salvano_e_si_rileggono(), test_senza_regole_il_contesto_lo_dice(), test_spazi_e_righe_vuote_non_diventano_una_regola()

### Community 90 - "Chat & Shared Registry Docs"
Cohesion: 0.17
Nodes (9): Anagrafica ingredienti condivisa (non per-utente), docs/chat.md - Chat e regole libere, ChatText (markdown minimo come elementi React), Chat del pasto ([RECIPE_UPDATE]), Chat della spesa (SHOPPING_CHAT_SYSTEM, [RECIPES_UPDATE]), prompt_line (tecniche della cucina, base reperibile in Italia), guess_category (inizio parola, primo nome, parola chiave piu' lunga), useDueColonne / useTelefono (lib/schermo.js) (+1 more)

### Community 91 - "Adherence Docs"
Cohesion: 0.17
Nodes (10): docs/andamento.md - Andamento e aderenza, compliance_color, PlannedMeal.eaten_nutrition (stima di cosa si e' mangiato al posto), Promemoria serale push (push.start_scheduler), Chiavi VAPID ricavate da SECRET_KEY / PushSubscription, year_adherence / YearHeatmap (calendario dell'anno), clear_meal_cell (cestino, non 'ho mangiato altro'), DayPlan.is_skipped / skip_day (+2 more)

### Community 92 - "Cuisine Spacing"
Cohesion: 0.24
Nodes (4): _distanziate(), prompt_line_one(), _quante_volte(), _sta_bene()

### Community 93 - "Frontend Package Config"
Cohesion: 0.20
Nodes (9): name, private, type, version, react-dom, @types/react, vite, @vitejs/plugin-react (+1 more)

### Community 94 - "AIError Handling"
Cohesion: 0.22
Nodes (6): AIError, _fallisci(), generate_json(), test_il_motivo_del_fallimento_resta_sulla_settimana(), generate_json(), test_una_generazione_riuscita_cancella_l_errore_di_prima()

### Community 95 - "Background Generation Thread"
Cohesion: 0.22
Nodes (4): _in_background(), test_il_thread_vero_lavora_con_una_sessione_sua(), lavoro(), test_un_eccezione_nel_thread_vero_non_esce()

### Community 96 - "Weekly Budget Tests"
Cohesion: 0.20
Nodes (3): con_lista(), test_il_tetto_arriva_nel_contesto(), test_senza_tetto_il_contesto_resta_com_era()

### Community 97 - "Fake Chat Models"
Cohesion: 0.22
Nodes (3): FakeChat, FakeChatSequence, test_la_chat_della_spesa_cambia_anche_i_pasti_della_prossima()

### Community 98 - "Cuisine Catalog"
Cohesion: 0.22
Nodes (5): list_cuisines(), options(), test_le_chiavi_sono_uniche_e_minuscole(), test_ogni_voce_si_cerca_anche_per_paese(), test_troppe_cucine_vengono_rifiutate_spiegando_perche()

### Community 99 - "Account Docs"
Cohesion: 0.22
Nodes (6): docs/account.md - Account, amministratore e accesso, has_api_key in /me e can_manage_api_key, User.is_admin (chi paga la API key), docs/generazione.md - Generazione delle ricette e modelli, Modelli per ruolo (planning, chat, diet), Scontrino fotografato (POST /shopping/current/receipt, read_image_json)

### Community 100 - "Push Reminder UI"
Cohesion: 0.50
Nodes (7): ReminderSettings(), chiaveInByte(), iscrivi(), iscrizioneCorrente(), registrazione(), supportoPush(), PreferencesTab()

### Community 101 - "Recipe Macro Compute"
Cohesion: 0.29
Nodes (4): compute(), _Riga, _somma(), Totali

### Community 102 - "Fit To Target"
Cohesion: 0.36
Nodes (5): _dentro(), fit_to_target(), Target, test_le_grammature_si_arrotondano_come_in_cucina(), test_una_ricetta_fuori_target_si_ritocca_sulle_leve()

### Community 103 - "Account & Usage Concepts"
Cohesion: 0.29
Nodes (7): AIUsage (registro token e costo per chiamata), Cancellazione account in CASCADE (delete_user), is_active vs ai_enabled (sospensione vs spegnimento AI), token_version (revoca immediata delle sessioni), GenerationProgress / on_progress (diario in streaming), Stato della generazione sul WeekPlan (generation_started_at, is_generating, 409), _in_background / _run_generation (202 + polling)

### Community 104 - "Questionnaire Preview Route"
Cohesion: 0.33
Nodes (3): _compute(), preview_questionnaire(), QuestionnaireRequest

### Community 105 - "Spy Model Fixture"
Cohesion: 0.29
Nodes (3): ModelloSpia, _ricetta(), spia()

### Community 106 - "Pantry Expiry Tests"
Cohesion: 0.48
Nodes (5): oggi(), test_il_contesto_mette_prima_quello_che_scade(), test_la_scadenza_si_corregge_e_si_toglie(), test_la_scadenza_si_segna_e_si_legge(), test_una_scorta_scaduta_si_dice()

### Community 107 - "Weight Recalc Proposal"
Cohesion: 0.29
Nodes (5): WeightEntry (storico del peso, una pesata al giorno), docs/dieta.md - Questionario ed editor della dieta, MEAL_CATALOG e _share_out (peso per pasto), POST /questionnaire/preview (calcola senza salvare), Questionario -> DietPlan identica (utils/nutrition.py, Mifflin-St Jeor)

### Community 108 - "Questionnaire Speed Tests"
Cohesion: 0.20
Nodes (3): test_anche_l_ospite_puo_calcolarsi_la_dieta(), test_l_anteprima_non_salva_niente(), test_le_risposte_restano_per_poter_ricalcolare()

### Community 109 - "Cuisine Deck Labels"
Cohesion: 0.40
Nodes (4): labels(), test_il_sorteggio_pesca_solo_fra_le_scelte(), test_nessuna_cucina_resta_fuori_e_nessuna_prende_tutto(), test_rigenerare_un_pasto_ne_sorteggia_una_sola()

### Community 110 - "Frontend Dependencies"
Cohesion: 0.40
Nodes (5): dependencies, lucide-react, react, react-dom, react-router-dom

### Community 111 - "Frontend Dev Dependencies"
Cohesion: 0.40
Nodes (5): devDependencies, @types/react, vite, @vitejs/plugin-react, vitest

### Community 112 - "Frontend Scripts"
Cohesion: 0.40
Nodes (5): scripts, build, dev, preview, test

### Community 117 - "Interface Docs"
Cohesion: 0.50
Nodes (4): docs/interfaccia.md - L'interfaccia, MealCard (stesso markup griglia/riga, stato detto una volta), .plan-head sticky e .day-strip con DayDots, WeekGrid: display contents e celle con riga/colonna esplicite

## Knowledge Gaps
- **59 isolated node(s):** `@types/react`, `Pasti ricorrenti (daily/weekly)`, `SEASONAL_PRODUCTS (stagionalità prodotti italiani)`, `Modello dati originale (User, DietPlan, MealSlot, WeekPlan, DayPlan, PlannedMeal, Recipe, Ingredient, ShoppingList...)`, `Mappa area → file di test` (+54 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1020 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **43 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `DB Session & Admin CLI` to `Shopping List Aggregation`, `Config & Input Schemas`, `Week Planner Core`, `AI Usage & Model Catalog`, `Auth & JWT Tokens`, `Recipes Router`, `Meal & Shopping Chat`, `Alembic Env & Model Slugs`, `Multi-week Shopping Tests`, `WeekPlan & Planning Routes`, `Meal Slots & Cell Actions`, `FastAPI App & Test Fixtures`, `Diet Plan & PDF Import`, `Admin & Session Revocation`, `PDF Extraction & AI Provider`, `Pantry Purchase Flow`, `Two-account Isolation Tests`, `Delete User Command`, `Name Normalization`, `Food Frequency Groups`, `Push Subscriptions & Prefs`, `Recipe Archive Actions`, `Ingredient Merge & Registry`, `API Key Encryption`, `Anthropic Backend`, `Recipe Ingredients & Cereal Repair`, `AIClient Interface`, `Pantry Editing Tests`, `Questionnaire Options`, `User Rules Tests`, `Cuisine Catalog`, `Questionnaire Preview Route`?**
  _High betweenness centrality (0.071) - this node is a cross-community bridge._
- **Are the 91 inferred relationships involving `User` (e.g. with `get_current_admin()` and `get_current_user()`) actually correct?**
  _`User` has 91 INFERRED edges - model-reasoned connections that need verification._
- **What connects `@types/react`, `Pasti ricorrenti (daily/weekly)`, `SEASONAL_PRODUCTS (stagionalità prodotti italiani)` to the rest of the system?**
  _59 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Shopping List Aggregation` be split into smaller, more focused modules?**
  _Cohesion score 0.0502497796062298 - nodes in this community are weakly interconnected._
- **Why does `FakeModel` connect `Fake AI Fixtures` to `Push Reminders`, `Chat Meal Fixture`, `Shopping Chat Week Fixture`, `Pantry Subtraction Test`, `Multi-week Shopping Tests`, `Generation Progress Log`, `End-to-end Flow Tests`, `Skipped Meals Tests`, `Shopping Chat Tests`, `Skipped Days Tests`, `Meal Chat Tests`, `Frequency Assignment Tests`, `Year View Tests`, `Week Browsing Tests`, `Diet Change Realign Tests`, `On-request Generation Tests`, `Generation State Tests`, `Week Regeneration Tests`, `Meal Detail Tests`, `Computed Macro Tests`, `Eaten Instead Tests`, `Receipt Scan Tests`, `Self-managed Meal Tests`, `Pantry Editing Tests`, `Servings & Batch Tests`, `Macro Refit Command`, `Tracked Meal Deletion Tests`, `User Rules Tests`, `AIError Handling`, `Weekly Budget Tests`, `Pantry Week Fixture`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Are the 47 inferred relationships involving `Ingredient` (e.g. with `main()` and `main()`) actually correct?**
  _`Ingredient` has 47 INFERRED edges - model-reasoned connections that need verification._
- **Should `Config & Input Schemas` be split into smaller, more focused modules?**
  _Cohesion score 0.05794556628621598 - nodes in this community are weakly interconnected._