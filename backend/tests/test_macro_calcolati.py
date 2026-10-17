"""I macro di una ricetta si calcolano dagli ingredienti.

Il modello dichiara calorie e macro, ma è una somma fatta a memoria: qui si prova che
la somma la fa Python (`services/macros.py`), che una ricetta fuori dal ±10% viene
ritoccata nelle grammature e che dove il conto non si può fare si dice.

La suite intera gira coi macro dichiarati (`macro_dichiarati` in `conftest.py`): qui
si riaccende il calcolo.
"""

import pytest

from app.models import Ingredient, Recipe
from app.services import macros, planner
from app.services.ingredients import get_or_create_ingredient
from app.utils.composition import (
    ALCOHOL,
    CAFFEINE_MG,
    COMPOSITION,
    DENSITY,
    DETAILS,
    GRAMS_PER_UNIT,
)
from app.utils.pricing import INGREDIENT_CATALOG
from tests.test_flow import FakeModel


@pytest.fixture(autouse=True)
def calcolo_acceso(monkeypatch):
    monkeypatch.setattr(macros, "ATTIVO", True)


def righe(db, *voci):
    return [
        {
            "name": nome,
            "quantity": q,
            "unit": u,
            "notes": None,
            "ingredient_id": get_or_create_ingredient(db, nome).id,
        }
        for nome, q, u in voci
    ]


# ── La tabella ─────────────────────────────────────────────────────────────────


def test_ogni_voce_del_catalogo_ha_la_sua_composizione():
    """Un alimento del catalogo senza composizione lascerebbe ogni ricetta che lo usa
    coi macro dichiarati: il catalogo e la tabella devono avere le stesse chiavi."""
    assert set(COMPOSITION) == set(INGREDIENT_CATALOG)
    assert set(GRAMS_PER_UNIT) <= set(INGREDIENT_CATALOG)
    assert set(DENSITY) <= set(INGREDIENT_CATALOG)


# Alcol (7 kcal/g), acido acetico (3,6 kcal/g) e la fibra delle spezie secche non
# stanno nei tre macro: per queste voci la regola di Atwater non torna, ed è giusto
# così. Sono tutte voci che in una ricetta pesano qualche grammo.
_FUORI_ATWATER = {
    "vino bianco", "vino rosso", "mirin", "cacao amaro",
    "aceto di vino", "aceto di riso",
    "cannella", "curry", "origano", "paprika", "pepe nero", "peperoncino",
}


@pytest.mark.parametrize("nome", sorted(set(COMPOSITION) - _FUORI_ATWATER))
def test_le_calorie_tornano_coi_macro(nome):
    """kcal ≈ 4·P + 4·C + 9·G: è la guardia contro un numero scritto male (un 35
    al posto di 3,5 nei grassi si vede subito)."""
    kcal, p, c, f = COMPOSITION[nome]
    atwater = 4 * p + 4 * c + 9 * f
    assert abs(kcal - atwater) <= max(15, 0.25 * kcal), (kcal, atwater)


def test_ogni_voce_del_catalogo_ha_gli_altri_valori():
    """Fibre, zuccheri e saturi per tutte; alcol e caffeina solo dove ci sono, e
    l'assenza vale zero. Una voce senza dettagli lascerebbe aperti quei valori in
    ogni ricetta che la usa."""
    assert set(DETAILS) == set(COMPOSITION)
    assert set(ALCOHOL) <= set(COMPOSITION)
    assert set(CAFFEINE_MG) <= set(COMPOSITION)


@pytest.mark.parametrize("nome", sorted(COMPOSITION))
def test_zuccheri_e_saturi_stanno_dentro_carboidrati_e_grassi(nome):
    """Sono una parte di quei numeri, mai di più: è la guardia contro una colonna
    scambiata con un'altra. Le fibre no: i carboidrati CREA non le contano."""
    _, _, carbs, fat = COMPOSITION[nome]
    _, sugar, saturated = DETAILS[nome]
    assert sugar <= carbs, (sugar, carbs)
    assert saturated <= fat, (saturated, fat)


@pytest.mark.parametrize("nome", sorted(ALCOHOL))
def test_con_l_alcol_le_calorie_tornano(nome):
    """kcal ≈ 4·P + 4·C + 9·G + 7·alcol: il vino fuori Atwater torna dentro."""
    kcal, p, c, f = COMPOSITION[nome]
    atwater = 4 * p + 4 * c + 9 * f + 7 * ALCOHOL[nome]
    assert abs(kcal - atwater) <= max(15, 0.25 * kcal), (kcal, atwater)


# ── Il conto ───────────────────────────────────────────────────────────────────


def test_gli_altri_valori_si_sommano_come_i_macro(db):
    n = macros.compute(
        db, righe(db, ("pasta", 100, "g"), ("olio extravergine d'oliva", 1, "cucchiai"))
    ).as_nutrition()

    assert n["fiber_g"] == 2.7
    # 0,3 della pasta + 13,8 g d'olio × 14,5% = 2,3 g di saturi.
    assert n["saturated_fat_g"] == pytest.approx(0.3 + 13.8 * 0.145, abs=0.1)
    # Non ce n'è: zero, che non è "non si sa".
    assert n["alcohol_g"] == 0
    assert n["caffeine_mg"] == 0


def test_un_valore_che_un_ingrediente_non_sa_resta_aperto(db):
    """Il conto si fa valore per valore: senza le fibre del tempeh le fibre della
    ricetta non si sanno, le calorie e gli zuccheri sì."""
    items = righe(db, ("pasta", 80, "g"), ("tempeh", 100, "g"))
    tempeh = db.get(Ingredient, items[1]["ingredient_id"])
    tempeh.kcal_100g, tempeh.protein_100g, tempeh.carbs_100g, tempeh.fat_100g = 192, 20.3, 7.6, 10.8
    tempeh.sugar_100g, tempeh.saturated_fat_100g = 0.5, 2.2
    tempeh.alcohol_100g = tempeh.caffeine_mg_100g = 0.0
    db.flush()

    n = macros.compute(db, items).as_nutrition()

    assert n["fiber_g"] is None
    assert n["sugar_g"] == pytest.approx(0.8 * 3.5 + 0.5, abs=0.1)
    assert n["calories"] == round(0.8 * 356 + 192)


def test_il_sale_q_b_non_lascia_aperto_niente(db):
    sale = get_or_create_ingredient(db, "sale")
    sale.fiber_100g = None  # anche se non si sapesse: pesa zero
    n = macros.compute(db, righe(db, ("pasta", 100, "g"), ("sale", 1, "q.b."))).as_nutrition()
    assert n["fiber_g"] == 2.7


def test_la_somma_la_fa_python(db):
    t = macros.compute(db, righe(db, ("pasta", 100, "g"), ("olio extravergine d'oliva", 1, "cucchiai")))

    # 100 g di pasta = 356 kcal; un cucchiaio d'olio = 15 ml × 0,92 = 13,8 g = 122 kcal.
    assert t.as_nutrition()["calories"] == 478
    assert t.as_nutrition()["fat_g"] == pytest.approx(1.5 + 13.8, abs=0.1)


def test_pezzi_e_pizzichi(db):
    t = macros.compute(db, righe(db, ("uova", 2, "unità"), ("sale", 1, "pizzichi")))

    # Due uova = 110 g di parte edibile; il pizzico di sale non pesa niente.
    assert t.as_nutrition()["calories"] == round(110 * 1.43)


def test_un_ingrediente_sconosciuto_ferma_il_conto(db):
    """Un totale che ne tiene fuori uno è peggio di un totale dichiarato: sembra vero."""
    assert macros.compute(db, righe(db, ("pasta", 80, "g"), ("polvere di stelle", 10, "g"))) is None


# ── Il ritocco delle grammature ────────────────────────────────────────────────


def test_una_ricetta_fuori_target_si_ritocca_sulle_leve(db):
    """Pollo, riso e olio sono le tre leve: si muovono loro, il resto no."""
    items = righe(
        db,
        ("petto di pollo", 100, "g"),
        ("riso", 50, "g"),
        ("olio extravergine d'oliva", 5, "ml"),
        ("zucchine", 150, "g"),
    )
    target = macros.Target(kcal=700, protein=45, carbs=75, fat=20)

    ritoccati = macros.fit_to_target(db, items, target)
    t = macros.compute(db, ritoccati)

    assert abs(t.kcal - 700) <= 70
    assert abs(t.protein - 45) <= 5
    # La verdura non è lì per i numeri e resta com'era.
    assert next(i for i in ritoccati if i["name"] == "zucchine")["quantity"] == 150


def test_una_ricetta_gia_nei_numeri_non_si_tocca(db):
    items = righe(db, ("pasta", 100, "g"), ("olio extravergine d'oliva", 1, "cucchiai"))
    target = macros.Target(kcal=480, protein=12.5, carbs=72, fat=15)

    assert macros.fit_to_target(db, items, target) is items


def test_le_grammature_si_arrotondano_come_in_cucina(db):
    items = righe(db, ("pasta", 100, "g"), ("olio extravergine d'oliva", 1, "cucchiai"))
    ritoccati = macros.fit_to_target(db, items, macros.Target(kcal=700, protein=18, carbs=100, fat=20))

    for item in ritoccati:
        if item["unit"] == "g" and item["quantity"] >= 100:
            assert item["quantity"] % 5 == 0
        if item["unit"] == "cucchiai":
            assert (item["quantity"] * 2) % 1 == 0


# ── Dalla generazione alla ricetta ─────────────────────────────────────────────


@pytest.fixture()
def generata(client, diet, monkeypatch):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text
    return res.json()


def test_la_settimana_generata_ha_i_macro_calcolati_e_nel_target(client, generata):
    """Il modello finto dichiara 700 kcal per un pranzo che ne pesa 496: la ricetta
    salvata dice il vero, e le grammature sono state allungate per arrivarci."""
    pranzo = next(m for m in generata["days"][0]["meals"] if m["slot_name"] == "Pranzo")
    ricetta = client.get(f"/api/planning/meals/{pranzo['id']}").json()["recipe"]

    assert ricetta["nutrition_source"] == "calcolata"
    assert abs(ricetta["calories"] - 700) <= 70
    pasta = next(i for i in ricetta["ingredients"] if i["name"] == "pasta")
    assert pasta["quantity"] > 100


def test_le_ricette_scritte_a_mano_tengono_i_loro_numeri(client):
    res = client.post(
        "/api/recipes",
        json={
            "title": "Il mio panino",
            "instructions": "Componi.",
            "calories": 500,
            "protein_g": 30,
            "carbs_g": 50,
            "fat_g": 18,
            "ingredients": [{"name": "pane", "quantity": 100, "unit": "g"}],
        },
    )
    assert res.status_code in (200, 201), res.text
    assert res.json()["calories"] == 500
    assert res.json()["nutrition_source"] == "utente"
    # Gli altri valori non li ha scritti: non si sanno, e non diventano zero.
    assert res.json()["fiber_g"] is None


def test_la_ricetta_scritta_a_mano_tiene_anche_gli_altri_valori(client):
    res = client.post(
        "/api/recipes",
        json={
            "title": "Il mio porridge", "instructions": "Cuoci.",
            "calories": 350, "protein_g": 12, "carbs_g": 55, "fat_g": 8,
            "fiber_g": 7.5, "sugar_g": 12, "saturated_fat_g": 1.5,
            "alcohol_g": 0, "caffeine_mg": 0,
        },
    )
    assert res.status_code in (200, 201), res.text
    r = res.json()
    assert (r["fiber_g"], r["sugar_g"], r["saturated_fat_g"]) == (7.5, 12, 1.5)
    assert r["alcohol_g"] == 0 and r["caffeine_mg"] == 0


def test_la_ricetta_generata_ha_gli_altri_valori(client, generata):
    pranzo = next(m for m in generata["days"][0]["meals"] if m["slot_name"] == "Pranzo")
    ricetta = client.get(f"/api/planning/meals/{pranzo['id']}").json()["recipe"]
    # Gli ingredienti del modello finto sono tutti del catalogo: si sanno tutti.
    for campo in macros.CAMPI_DETTAGLIO:
        assert ricetta[campo] is not None, campo
    assert ricetta["sugar_g"] <= ricetta["carbs_g"]


class ModelloCheConosce:
    """Risponde alla domanda sulla composizione, e a nient'altro."""

    def __init__(self):
        self.chiamate = 0

    def generate_json(self, system, prompt, **kwargs):
        self.chiamate += 1
        return {
            "items": [
                {"name": "tempeh", "kcal": 192, "protein_g": 20.3, "carbs_g": 7.6,
                 "fat_g": 10.8, "fiber_g": 5.0, "sugar_g": 0.5, "saturated_fat_g": 2.2,
                 "alcohol_g": 0, "caffeine_mg": 0, "grams_per_unit": None, "density": None}
            ]
        }


def test_un_nome_nuovo_si_impara_una_volta(db):
    client = ModelloCheConosce()
    tempeh = get_or_create_ingredient(db, "tempeh")
    assert not macros.has_composition(tempeh)

    assert macros.ensure_composition(db, client, [tempeh.id]) == 1
    assert macros.ensure_composition(db, client, [tempeh.id]) == 0  # già saputo

    db.refresh(tempeh)
    assert tempeh.kcal_100g == 192
    assert tempeh.composition_source == "ai"
    assert client.chiamate == 1


def test_una_stima_che_fallisce_non_ferma_niente(db):
    class ModelloRotto:
        def generate_json(self, *a, **k):
            raise RuntimeError("provider giù")

    seitan = get_or_create_ingredient(db, "seitan")
    assert macros.ensure_composition(db, ModelloRotto(), [seitan.id]) == 0


def test_il_seed_non_tocca_la_composizione_corretta_a_mano(db):
    from app.seed import seed_ingredients

    db.add(Ingredient(name="pasta", category="cereali", kcal_100g=999, protein_100g=1,
                      carbs_100g=1, fat_100g=1, composition_source="utente"))
    db.commit()
    seed_ingredients(db)

    assert db.query(Ingredient).filter_by(name="pasta").one().kcal_100g == 999
    assert db.query(Ingredient).filter_by(name="riso").one().kcal_100g == 350


def test_la_ricetta_ricalcolata_dopo_la_chat(db, client):
    from app.services.recipes import create_recipe, update_recipe_from_ai

    r = create_recipe(db, 1, {
        "title": "Pasta", "instructions": "x",
        "nutrition": {"calories": 1, "protein_g": 1, "carbs_g": 1, "fat_g": 1},
        "ingredients": [{"name": "pasta", "quantity": 100, "unit": "g"}],
    })
    assert r.calories == 356

    update_recipe_from_ai(db, r, {
        "nutrition": {"calories": 1, "protein_g": 1, "carbs_g": 1, "fat_g": 1},
        "ingredients": [{"name": "pasta", "quantity": 50, "unit": "g"}],
    })
    assert db.get(Recipe, r.id).calories == 178


@pytest.mark.parametrize(
    ("nome", "per_pezzo", "quantita", "unita", "grammi"),
    [
        ("mozzarella", 125.0, 2, "fette", 50.0),
        ("melanzane", 300.0, 3, "fette", 90.0),
        ("aglio", 40.0, 2, "spicchi", 10.0),
        ("basilico", None, 4, "foglie", 2.0),
        ("formaggio", None, 1, "cucchiai", 6.0),
        ("farina", None, 3, "cucchiaini", 9.0),
        ("formaggio spalmabile", None, 1, "cucchiai", 15.0),
        ("polpo", 800.0, 2, "fette", None),
    ],
)
def test_fette_spicchi_e_cucchiai_pesano_il_giusto(nome, per_pezzo, quantita, unita, grammi):
    """Una fetta non è il pezzo intero: 2 fette di mozzarella erano 250 g."""
    from app.models import Ingredient
    from app.services.macros import grams_of

    ingrediente = Ingredient(name=nome, category="altro", grams_per_unit=per_pezzo)
    assert grams_of(ingrediente, quantita, unita) == pytest.approx(grammi) if grammi else (
        grams_of(ingrediente, quantita, unita) is None
    )


@pytest.mark.parametrize(
    ("valori", "alcol", "ok"),
    [
        ([165, 31, 0, 3.6], None, True),  # petto di pollo
        ([165, 31, 0, 36], None, False),  # un 36 al posto di 3,6
        ([500, 60, 60, 5], None, False),  # più di 100 g in 100 g
        ([70, 0, 2, 0], 9.5, True),  # vino
        ([-5, 1, 1, 1], None, False),
    ],
)
def test_una_composizione_stimata_deve_tornare(valori, alcol, ok):
    from app.services.macros import composizione_plausibile

    assert composizione_plausibile(valori, alcol) is ok


def test_calorie_giuste_con_grassi_doppi_non_sono_dentro():
    """Prima il ritocco guardava solo calorie e proteine."""
    from app.services.macros import Target, Totali, _dentro

    obiettivo = Target(kcal=600, protein=40, carbs=70, fat=18)
    assert _dentro(Totali(kcal=600, protein=40, carbs=70, fat=18), obiettivo)
    # Stesse calorie (±2%), ma grassi quasi doppi e carboidrati tagliati.
    assert not _dentro(Totali(kcal=612, protein=40, carbs=38, fat=32), obiettivo)
