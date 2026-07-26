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
