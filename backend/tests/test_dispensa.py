"""Dispensa: correggere quello che c'è in casa, nome compreso.

La dispensa si riempie da sola quando una spesa risulta fatta, quindi le righe
arrivano col nome che l'AI ha dato all'ingrediente nella ricetta ("petto di pollo"
quando in frigo c'è del pollo) e con la quantità comprata, non quella rimasta. Doverle
cancellare e riscrivere per correggerle sarebbe assurdo: da lì dipende cosa viene
scomputato dalla prossima lista della spesa.
"""

import pytest


@pytest.fixture()
def riga(client):
    res = client.post(
        "/api/config/pantry",
        json={"ingredient_name": "petto di pollo", "quantity": 500, "unit": "g"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def dispensa(client) -> list:
    return client.get("/api/config/pantry").json()


# ── Quantità ───────────────────────────────────────────────────────────────────


def test_la_quantita_si_corregge(client, riga):
    res = client.put(f"/api/config/pantry/{riga['id']}", json={"quantity": 250, "unit": "g"})

    assert res.status_code == 200, res.text
    assert res.json()["quantity"] == 250
    assert res.json()["label"] == "250 g"


def test_la_quantita_si_puo_anche_togliere(client, riga):
    """"Ce l'ho ma non so quanto" è una risposta legittima: la riga resta, ma non
    scomputa niente dalla lista della spesa."""
    res = client.put(f"/api/config/pantry/{riga['id']}", json={"quantity": None, "unit": None})

    assert res.status_code == 200, res.text
    assert res.json()["quantity"] is None
    assert res.json()["label"] is None


# ── Nome ───────────────────────────────────────────────────────────────────────


def test_il_nome_si_cambia_e_la_riga_punta_a_un_altro_ingrediente(client, riga):
    res = client.put(
        f"/api/config/pantry/{riga['id']}", json={"ingredient_name": "Tacchino a fette"}
    )

    assert res.status_code == 200, res.text
    body = res.json()
    # Normalizzato come ovunque nell'app, e agganciato all'anagrafica.
    assert body["name"] == "tacchino"
    assert body["ingredient_id"] != riga["ingredient_id"]
    # La quantità non si tocca: si stava correggendo il nome.
    assert body["quantity"] == 500
    assert [p["name"] for p in dispensa(client)] == ["tacchino"]


def test_rinominare_su_qualcosa_che_c_e_gia_viene_rifiutato(client, riga):
    """Somma silenziosa no: con due unità diverse sarebbe un numero inventato."""
    client.post("/api/config/pantry", json={"ingredient_name": "riso", "quantity": 1, "unit": "kg"})

    res = client.put(f"/api/config/pantry/{riga['id']}", json={"ingredient_name": "riso"})

    assert res.status_code == 409
    assert "già in dispensa" in res.json()["detail"]
    # E niente è cambiato: due righe, quelle di prima.
    assert sorted(p["name"] for p in dispensa(client)) == ["petto di pollo", "riso"]


def test_riscrivere_lo_stesso_nome_non_da_conflitto(client, riga):
    """Salvando senza toccare il nome si riscrive lo stesso valore: non è un doppione."""
    res = client.put(
        f"/api/config/pantry/{riga['id']}",
        json={"ingredient_name": "Petto di pollo", "quantity": 300, "unit": "g"},
    )

    assert res.status_code == 200, res.text
    assert res.json()["quantity"] == 300


def test_un_nome_che_non_resta_niente_viene_rifiutato(client, riga):
    """La normalizzazione toglie i qualificatori: "fresche" da solo non è un alimento."""
    res = client.put(f"/api/config/pantry/{riga['id']}", json={"ingredient_name": "fresche"})

    assert res.status_code == 400
    assert dispensa(client)[0]["name"] == "petto di pollo"


def test_una_riga_di_un_altro_utente_non_si_tocca(client, db):
    """Il filtro su user_id non è stile: senza, un id basterebbe a modificare la
    dispensa di qualcun altro."""
    from app.models import Ingredient, PantryItem, User

    altro = User(email="altro@dietai.local", password_hash="x")
    db.add(altro)
    db.flush()
    ingrediente = Ingredient(name="pane", category="cereali")
    db.add(ingrediente)
    db.flush()
    riga_altrui = PantryItem(
        user_id=altro.id, ingredient_id=ingrediente.id, quantity_available=200, unit="g"
    )
    db.add(riga_altrui)
    db.commit()

    res = client.put(f"/api/config/pantry/{riga_altrui.id}", json={"quantity": 999})

    assert res.status_code == 404
    db.refresh(riga_altrui)
    assert riga_altrui.quantity_available == 200


# ── Effetto sulla spesa ────────────────────────────────────────────────────────


def test_correggere_la_dispensa_cambia_quello_che_si_compra(client, diet, monkeypatch):
    """È il motivo per cui la modifica serve: la dispensa si sottrae dalla lista."""
    from app.services import planner
    from tests.test_flow import FakeModel

    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    def pasta() -> float:
        lst = client.get("/api/shopping/current").json()
        return next(
            (i["quantity"] for c in lst["categories"] for i in c["items"] if i["name"] == "pasta"),
            0,
        )

    assert pasta() == pytest.approx(700)  # sette pranzi da 100 g

    riga = client.post(
        "/api/config/pantry", json={"ingredient_name": "pasta", "quantity": 200, "unit": "g"}
    ).json()
    assert pasta() == pytest.approx(500)

    # Ricontata la scorta: erano 500 g, non 200.
    client.put(f"/api/config/pantry/{riga['id']}", json={"quantity": 500, "unit": "g"})
    assert pasta() == pytest.approx(200)


# ── Cucinare consuma la dispensa ───────────────────────────────────────────────


@pytest.fixture()
def settimana(client, diet, monkeypatch):
    """Una settimana generata: ogni pranzo usa 100 g di pasta e 150 g di zucchine."""
    from app.services import planner
    from tests.test_flow import FakeModel

    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text
    return res.json()


def pranzo(settimana, dow=0) -> dict:
    return next(m for m in settimana["days"][dow]["meals"] if m["slot_name"] == "Pranzo")


def scorta(client, nome: str):
    return next((p for p in client.get("/api/config/pantry").json() if p["name"] == nome), None)


def test_seguire_una_ricetta_scala_quello_che_ha_usato(client, settimana):
    client.post("/api/config/pantry", json={"ingredient_name": "pasta", "quantity": 500, "unit": "g"})

    res = client.put(
        f"/api/planning/meals/{pranzo(settimana)['id']}/followed", json={"is_followed": True}
    )

    assert res.status_code == 200, res.text
    assert res.json()["pantry_used"] == [
        {"ingredient_id": scorta(client, "pasta")["ingredient_id"], "name": "pasta",
         "quantity": 100, "unit": "g", "label": "100 g"}
    ]
    assert scorta(client, "pasta")["quantity"] == 400


def test_quello_che_non_c_e_in_dispensa_non_si_scala(client, settimana):
    """Il sale e l'olio non sono in dispensa e restano fuori da soli: nessuna
    eccezione da mantenere, basta la regola "solo quello che c'è"."""
    res = client.put(
        f"/api/planning/meals/{pranzo(settimana)['id']}/followed", json={"is_followed": True}
    )

    assert res.json()["pantry_used"] == []
    assert client.get("/api/config/pantry").json() == []


def test_una_scorta_senza_quantita_resta_com_e(client, settimana):
    """"Ce l'ho ma non so quanto": sottrarre da un valore ignoto darebbe un numero finto."""
    client.post("/api/config/pantry", json={"ingredient_name": "pasta"})

    client.put(f"/api/planning/meals/{pranzo(settimana)['id']}/followed", json={"is_followed": True})

    assert scorta(client, "pasta")["quantity"] is None


def test_la_scorta_finita_sparisce_dalla_dispensa(client, settimana):
    client.post("/api/config/pantry", json={"ingredient_name": "pasta", "quantity": 100, "unit": "g"})

    client.put(f"/api/planning/meals/{pranzo(settimana)['id']}/followed", json={"is_followed": True})

    assert scorta(client, "pasta") is None


def test_non_si_scala_piu_di_quello_che_c_era(client, settimana):
    """La ricetta ne vuole 100, in dispensa ce n'erano 40: si toglie 40."""
    client.post("/api/config/pantry", json={"ingredient_name": "pasta", "quantity": 40, "unit": "g"})

    res = client.put(
        f"/api/planning/meals/{pranzo(settimana)['id']}/followed", json={"is_followed": True}
    )

    assert res.json()["pantry_used"][0]["quantity"] == 40
    assert scorta(client, "pasta") is None


def test_ripremere_il_pulsante_non_scala_due_volte(client, settimana):
    client.post("/api/config/pantry", json={"ingredient_name": "pasta", "quantity": 500, "unit": "g"})
    mid = pranzo(settimana)["id"]

    client.put(f"/api/planning/meals/{mid}/followed", json={"is_followed": True})
    res = client.put(f"/api/planning/meals/{mid}/followed", json={"is_followed": True})

    assert res.json()["pantry_used"] == []  # niente di nuovo: era già scalato
    assert scorta(client, "pasta")["quantity"] == 400


def test_correggersi_rimette_in_dispensa_quello_che_era_stato_tolto(client, settimana):
    client.post("/api/config/pantry", json={"ingredient_name": "pasta", "quantity": 500, "unit": "g"})
    mid = pranzo(settimana)["id"]

    client.put(f"/api/planning/meals/{mid}/followed", json={"is_followed": True})
    client.put(f"/api/planning/meals/{mid}/followed", json={"is_followed": False})

    assert scorta(client, "pasta")["quantity"] == 500


def test_si_rimette_quello_tolto_non_quello_che_pesa_la_ricetta(client, settimana):
    """La differenza fra correggere un errore e inventare del cibo: c'erano 40 g,
    la ricetta ne voleva 100, tornano 40."""
    client.post("/api/config/pantry", json={"ingredient_name": "pasta", "quantity": 40, "unit": "g"})
    mid = pranzo(settimana)["id"]

    client.put(f"/api/planning/meals/{mid}/followed", json={"is_followed": True})
    client.put(f"/api/planning/meals/{mid}/followed", json={"is_followed": False})

    assert scorta(client, "pasta")["quantity"] == 40


def test_a_fine_settimana_la_dispensa_racconta_quello_che_resta(client, settimana):
    """Il caso per cui la cosa esiste: senza, alla spesa dopo la dispensa direbbe
    che è ancora tutto in casa e mezzo carrello non verrebbe comprato."""
    client.post("/api/config/pantry", json={"ingredient_name": "pasta", "quantity": 500, "unit": "g"})

    for dow in range(3):
        client.put(
            f"/api/planning/meals/{pranzo(settimana, dow)['id']}/followed",
            json={"is_followed": True},
        )

    assert scorta(client, "pasta")["quantity"] == 200


# ── Quanto se n'è preso davvero ────────────────────────────────────────────────


def voce(client, nome: str) -> dict:
    lst = client.get("/api/shopping/current").json()
    return next(i for c in lst["categories"] for i in c["items"] if i["name"] == nome)


def test_di_default_in_dispensa_va_quello_che_serviva(client, settimana):
    """Nessuna modifica = ho rispettato la grammatura: è il caso normale."""
    pasta = voce(client, "pasta")
    client.put(f"/api/shopping/items/{pasta['id']}/check", json={"is_checked": True})

    client.post("/api/shopping/current/complete")

    assert scorta(client, "pasta")["quantity"] == pytest.approx(700)


def test_la_confezione_intera_finisce_in_dispensa(client, settimana):
    """Il caso per cui esiste: la ricetta ne vuole 700 g, il pacco è da 1 kg."""
    pasta = voce(client, "pasta")

    res = client.put(f"/api/shopping/items/{pasta['id']}/quantity", json={"quantity": 1000})

    assert res.status_code == 200, res.text
    aggiornata = next(
        i for c in res.json()["categories"] for i in c["items"] if i["name"] == "pasta"
    )
    # Segnare quanto se n'è preso vuol dire averlo preso: la riga si spunta da sé.
    assert aggiornata["is_checked"] is True
    assert aggiornata["bought_quantity"] == 1000
    assert aggiornata["bought_label"] == "1 kg"
    # E la quantità che serve resta lì: è quella che dice quanto ne avanzerà.
    assert aggiornata["quantity"] == pytest.approx(700)

    client.post("/api/shopping/current/complete")
    assert scorta(client, "pasta")["quantity"] == pytest.approx(1000)


def test_il_totale_stimato_segue_quello_che_si_porta_a_casa(client, settimana):
    prima = client.get("/api/shopping/current").json()["estimated_cost"]
    pasta = voce(client, "pasta")

    dopo = client.put(
        f"/api/shopping/items/{pasta['id']}/quantity", json={"quantity": 2000}
    ).json()["estimated_cost"]

    assert dopo > prima


def test_togliere_la_spunta_cancella_la_quantita(client, settimana):
    """"Non l'ho preso" non può lasciarsi dietro un "ne ho preso 1 kg"."""
    pasta = voce(client, "pasta")
    client.put(f"/api/shopping/items/{pasta['id']}/quantity", json={"quantity": 1000})

    client.put(f"/api/shopping/items/{pasta['id']}/check", json={"is_checked": False})

    assert voce(client, "pasta")["bought_quantity"] is None


def test_la_quantita_presa_sopravvive_a_un_ricalcolo_della_lista(client, settimana):
    """Il piano può cambiare mentre si è al supermercato (una rigenerazione, un pasto
    saltato): quello che si è già messo nel carrello non si cancella."""
    pasta = voce(client, "pasta")
    client.put(f"/api/shopping/items/{pasta['id']}/quantity", json={"quantity": 1000})

    cena = next(m for m in settimana["days"][6]["meals"] if m["slot_name"] == "Cena")
    client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})

    aggiornata = voce(client, "pasta")
    assert aggiornata["bought_quantity"] == 1000
    assert aggiornata["is_checked"] is True


def test_a_spesa_fatta_non_si_cambia_piu(client, settimana):
    pasta = voce(client, "pasta")
    client.put(f"/api/shopping/items/{pasta['id']}/check", json={"is_checked": True})
    client.post("/api/shopping/current/complete")

    res = client.put(f"/api/shopping/items/{pasta['id']}/quantity", json={"quantity": 1000})
    assert res.status_code == 409


def test_la_quantita_di_un_altro_utente_non_si_tocca(client, settimana, db):
    """La proprietà si verifica risalendo articolo → lista → settimana → utente."""
    from app.models import ShoppingListItem, WeekPlan

    pasta = voce(client, "pasta")  # la lista nasce da questa lettura
    db.query(WeekPlan).update({WeekPlan.user_id: 999})
    db.commit()

    res = client.put(f"/api/shopping/items/{pasta['id']}/quantity", json={"quantity": 500})

    assert res.status_code == 404
    assert db.get(ShoppingListItem, pasta["id"]).bought_quantity is None


# ── Quanto è costato davvero ───────────────────────────────────────────────────


def test_il_prezzo_segnato_diventa_il_prezzo_dell_ingrediente(client, settimana, db):
    """Dalla cifra dello scaffale si ricava il prezzo al chilo: è quello che serve
    per stimare tutte le liste che verranno."""
    from app.models import Ingredient

    pasta = voce(client, "pasta")  # 700 g in lista
    res = client.put(f"/api/shopping/items/{pasta['id']}/price", json={"paid": 2.10})

    assert res.status_code == 200, res.text
    riga = next(i for c in res.json()["categories"] for i in c["items"] if i["name"] == "pasta")
    assert riga["price_by_user"] is True
    assert riga["estimated_price"] == pytest.approx(2.10)
    # 2,10 € per 700 g fanno 3,00 €/kg.
    assert riga["unit_price"] == pytest.approx(3.00)
    assert riga["price_unit"] == "kg"
    assert db.query(Ingredient).filter(Ingredient.name == "pasta").first().last_paid_at


def test_il_prezzo_si_ricava_da_quello_che_hai_preso_non_da_quello_che_serviva(client, settimana):
    """Se hai comprato il pacco da 1 kg, i 3 € che hai pagato sono per 1 kg."""
    pasta = voce(client, "pasta")
    client.put(f"/api/shopping/items/{pasta['id']}/quantity", json={"quantity": 1000})

    res = client.put(f"/api/shopping/items/{pasta['id']}/price", json={"paid": 3.00})

    riga = next(i for c in res.json()["categories"] for i in c["items"] if i["name"] == "pasta")
    assert riga["unit_price"] == pytest.approx(3.00)  # 3 € per 1 kg


def test_il_prezzo_vero_vale_anche_per_le_liste_dopo(client, settimana):
    pasta = voce(client, "pasta")
    client.put(f"/api/shopping/items/{pasta['id']}/price", json={"paid": 7.00})  # 10 €/kg

    client.post("/api/shopping/current/complete")
    w = client.get("/api/planning/weeks/next").json()
    client.post(f"/api/planning/weeks/{w['id']}/generate")

    prossima = voce(client, "pasta")
    assert prossima["estimated_price"] == pytest.approx(7.00)
    assert prossima["price_by_user"] is True


def test_il_totale_dice_quanti_prezzi_sono_tuoi(client, settimana):
    lst = client.get("/api/shopping/current").json()
    assert lst["priced_items"] == 0

    client.put(f"/api/shopping/items/{voce(client, 'pasta')['id']}/price", json={"paid": 2.10})

    assert client.get("/api/shopping/current").json()["priced_items"] == 1


def test_cancellare_il_prezzo_rimette_quello_del_catalogo(client, settimana):
    from app.utils.pricing import INGREDIENT_CATALOG

    pasta = voce(client, "pasta")
    client.put(f"/api/shopping/items/{pasta['id']}/price", json={"paid": 9.99})

    res = client.put(f"/api/shopping/items/{pasta['id']}/price", json={"paid": None})

    riga = next(i for c in res.json()["categories"] for i in c["items"] if i["name"] == "pasta")
    assert riga["price_by_user"] is False
    assert riga["unit_price"] == pytest.approx(INGREDIENT_CATALOG["pasta"][1])


def test_il_prezzo_si_segna_anche_a_spesa_fatta(client, settimana):
    """Lo scontrino si guarda a casa: la spesa è chiusa, i prezzi no."""
    pasta = voce(client, "pasta")
    client.put(f"/api/shopping/items/{pasta['id']}/check", json={"is_checked": True})
    client.post("/api/shopping/current/complete")

    res = client.put(f"/api/shopping/items/{pasta['id']}/price", json={"paid": 2.10})
    assert res.status_code == 200, res.text


def test_il_prezzo_segnato_sopravvive_al_seed(client, settimana, db):
    """Il seed gira a ogni avvio del container e riallinea i prezzi al catalogo:
    senza il flag, il prezzo vero durerebbe fino al primo deploy."""
    from app.models import Ingredient
    from app.seed import seed_ingredients

    pasta = voce(client, "pasta")
    client.put(f"/api/shopping/items/{pasta['id']}/price", json={"paid": 7.00})

    seed_ingredients(db)

    riga = db.query(Ingredient).filter(Ingredient.name == "pasta").first()
    db.refresh(riga)
    assert riga.avg_price_per_unit == pytest.approx(10.00)
    assert riga.price_by_user is True
