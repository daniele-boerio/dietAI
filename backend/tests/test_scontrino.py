"""La foto dello scontrino: prezzi e quantità prese, riga per riga.

Il modello legge le righe e le abbina agli articoli della lista; da lì vale la logica
del prezzo scritto a mano — cifra sulla riga, prezzo al chilo imparato, riga spuntata.
Qui il modello è finto e risponde con le righe che servono a ciascun test.
"""

import pytest

from app.models import Ingredient
from app.routers import shopping as shopping_router
from app.services import planner
from tests.test_flow import FakeModel

FOTO = ("scontrino.jpg", b"\xff\xd8\xff\xe0finto-jpeg", "image/jpeg")


class ModelloCheLegge(FakeModel):
    righe = []
    prompt = None

    def read_image_json(self, system, prompt, image_b64, media_type, **kw):
        ModelloCheLegge.prompt = prompt
        return {"lines": ModelloCheLegge.righe, "total": 12.5}


@pytest.fixture()
def lista(client, diet, monkeypatch):
    finto = lambda db, user, role: ModelloCheLegge(user)  # noqa: E731
    monkeypatch.setattr(planner, "get_client", finto)
    monkeypatch.setattr(shopping_router, "get_client", finto)
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    return client.get("/api/shopping/current").json()


def articolo(lista, nome):
    return next(i for c in lista["categories"] for i in c["items"] if i["name"] == nome)


def test_il_modello_riceve_gli_articoli_con_il_loro_id(client, lista):
    ModelloCheLegge.righe = []
    client.post("/api/shopping/current/receipt", files={"file": FOTO})
    pasta = articolo(lista, "pasta")
    assert f"{pasta['id']} → pasta" in ModelloCheLegge.prompt


def test_le_righe_abbinate_portano_prezzo_quantita_e_spunta(client, lista, db):
    pasta = articolo(lista, "pasta")
    ModelloCheLegge.righe = [
        {"text": "PASTA SEMOLA 500G", "item_id": pasta["id"], "price": 0.89,
         "quantity": 500, "unit": "g"},
        {"text": "PASTA SEMOLA 500G", "item_id": pasta["id"], "price": 0.89,
         "quantity": 500, "unit": "g"},
        {"text": "SACCHETTO BIO", "item_id": None, "price": 0.10},
    ]

    res = client.post("/api/shopping/current/receipt", files={"file": FOTO}).json()

    assert res["matched"] == 1
    assert res["unmatched"] == [{"text": "SACCHETTO BIO", "price": 0.1}]
    riga = articolo(res["list"], "pasta")
    assert riga["is_checked"] is True
    assert riga["paid_price"] == 1.78  # due righe, un articolo: si sommano
    assert riga["bought_quantity"] == 1000
    # Il prezzo al chilo si impara, come col prezzo scritto a mano.
    assert db.query(Ingredient).filter_by(name="pasta").one().avg_price_per_unit == 1.78


def test_una_quantita_in_un_unita_che_non_si_converte_non_si_inventa(client, lista):
    pasta = articolo(lista, "pasta")
    ModelloCheLegge.righe = [
        {"text": "PASTA", "item_id": pasta["id"], "price": 1.20, "quantity": 1, "unit": "l"},
    ]
    res = client.post("/api/shopping/current/receipt", files={"file": FOTO}).json()
    riga = articolo(res["list"], "pasta")
    assert riga["paid_price"] == 1.2
    assert riga["bought_quantity"] is None


def test_un_id_che_non_e_in_lista_resta_fuori(client, lista):
    ModelloCheLegge.righe = [{"text": "X", "item_id": 999999, "price": 3.0}]
    res = client.post("/api/shopping/current/receipt", files={"file": FOTO}).json()
    assert res["matched"] == 0
    assert res["unmatched"][0]["text"] == "X"


def test_serve_una_foto(client, lista):
    res = client.post(
        "/api/shopping/current/receipt",
        files={"file": ("scontrino.pdf", b"%PDF", "application/pdf")},
    )
    assert res.status_code == 400


@pytest.mark.parametrize("anthropic", [True, False])
def test_l_immagine_parte_nella_forma_del_suo_backend(anthropic):
    """Anthropic vuole un blocco `image`, le API OpenAI-compatibili un `image_url` con
    un data URL: sbagliare forma è un 400 del fornitore a ogni scontrino."""
    from app.services import ai_client

    visti = []

    class Backend:
        supports_native_pdf = False

        def complete(self, **kw):
            visti.append(kw["messages"])
            self.last_usage = None
            return '{"lines": []}'

    c = ai_client.AIClient.__new__(ai_client.AIClient)
    c.model, c.on_usage = "x", None
    c._backend = Backend()
    if anthropic:
        c._backend.__class__ = type("B", (ai_client._AnthropicBackend,), {
            "__init__": lambda self: None, "complete": Backend.complete,
        })

    assert c.read_image_json("s", "p", "QUJD", "image/jpeg") == {"lines": []}
    blocco = visti[0][0]["content"][0]
    if anthropic:
        assert blocco == {"type": "image", "source": {"type": "base64",
                          "media_type": "image/jpeg", "data": "QUJD"}}
    else:
        assert blocco == {"type": "image_url",
                          "image_url": {"url": "data:image/jpeg;base64,QUJD"}}
