"""Il server MCP per SpassoHub (`routers/mcp.py`).

Gli strumenti chiamano le stesse funzioni delle rotte: qui si prova l'accesso (token
fisso, solo amministratore) e che le risposte coincidano con quelle dell'app.
"""

import json

import pytest

from app import config
from app.services import planner
from tests.test_dettaglio_pasto import ModelloDiProva

TOKEN = "t" * 40


@pytest.fixture()
def mcp(client, monkeypatch):
    monkeypatch.setattr(config, "MCP_TOKEN", TOKEN)

    def chiama(metodo, params=None, token=TOKEN):
        return client.post(
            "/api/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": metodo, "params": params or {}},
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )

    return chiama


def strumento(mcp, _strumento, **args):
    res = mcp("tools/call", {"name": _strumento, "arguments": args})
    assert res.status_code == 200, res.text
    risultato = res.json()["result"]
    testo = risultato["content"][0]["text"]
    return risultato.get("isError", False), (testo if risultato.get("isError") else json.loads(testo))


def test_senza_token_configurato_l_endpoint_non_c_e(client, monkeypatch):
    monkeypatch.setattr(config, "MCP_TOKEN", "")
    res = client.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                      headers={"Authorization": "Bearer "})
    assert res.status_code == 404


def test_token_sbagliato_o_assente(mcp):
    assert mcp("ping", token="x" * 40).status_code == 401
    assert mcp("ping", token=None).status_code == 401
    assert mcp("ping").json()["result"] == {}


def test_initialize_e_strumenti(mcp):
    init = mcp("initialize", {"protocolVersion": "2025-06-18"}).json()["result"]
    assert init["serverInfo"]["name"] == "dietai"
    assert init["protocolVersion"] == "2025-06-18"

    tools = {t["name"]: t for t in mcp("tools/list").json()["result"]["tools"]}
    assert {"oggi", "settimana", "lista_spesa", "dispensa", "segna_seguito", "registra_peso"} <= set(tools)
    for t in tools.values():
        assert t["inputSchema"]["type"] == "object"
        assert "readOnlyHint" in t["annotations"]


def test_notifica_senza_risposta(client, mcp):
    res = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert res.status_code == 202


def test_vale_per_l_amministratore_non_per_l_ospite(mcp, client, db):
    """Il token parla a nome dell'amministratore: è suo il peso che si segna."""
    errore, storico = strumento(mcp, "registra_peso", kg=79.4)
    assert not errore
    assert [e["weight_kg"] for e in storico["entries"]] == [79.4]
    assert client.get("/api/tracking/weight").json()["entries"] == storico["entries"]


def test_oggi_e_settimana_come_le_rotte(mcp, client, diet):
    _, oggi = strumento(mcp, "oggi")
    assert oggi == client.get(f"/api/tracking/day/{planner.today().isoformat()}").json()
    _, settimana = strumento(mcp, "settimana")
    assert settimana["id"] == client.get("/api/planning/weeks/current").json()["id"]


def test_segna_seguito_e_pasti_consumati(mcp, client, diet, monkeypatch):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: ModelloDiProva(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    week = client.get("/api/planning/weeks/current").json()
    pranzo = next(m for m in week["days"][0]["meals"] if m["slot_name"] == "Pranzo")

    errore, pasto = strumento(mcp, "segna_seguito", meal_id=pranzo["id"])
    assert not errore, pasto
    assert pasto["is_followed"] is True

    _, consumati = strumento(mcp, "pasti_consumati", da=week["week_start_date"], a=planner.today().isoformat())
    assert consumati["seguiti"] == 1
    assert consumati["pasti"][0]["meal_id"] == pranzo["id"]
    assert consumati["pasti"][0]["pasto"] == "Pranzo"


def test_dispensa_dall_inizio_alla_fine(mcp):
    errore, riga = strumento(mcp, "dispensa_aggiungi", nome="riso", quantita=500, unita="g")
    assert not errore, riga
    _, righe = strumento(mcp, "dispensa")
    assert [r["id"] for r in righe] == [riga["id"]]

    _, cambiata = strumento(mcp, "dispensa_modifica", item_id=riga["id"], quantita=250)
    assert cambiata["quantity"] == 250

    assert strumento(mcp, "dispensa_togli", item_id=riga["id"]) == (False, {"tolto": riga["id"]})
    assert strumento(mcp, "dispensa")[1] == []


def test_gli_errori_delle_rotte_tornano_come_errore(mcp):
    errore, testo = strumento(mcp, "pasto", meal_id=999999)
    assert errore and "404" in testo
    errore, testo = strumento(mcp, "registra_peso", kg=10)
    assert errore
    errore, testo = strumento(mcp, "oggi", data="ieri")
    assert errore and "AAAA-MM-GG" in testo
    assert mcp("tools/call", {"name": "non_esiste"}).json()["error"]["code"] == -32602


# --- Sostituire, correggere, svuotare un pasto --------------------------------

from app.routers import mcp as mcp_router  # noqa: E402
from tests.test_ho_mangiato_questo import PIZZA, ModelloFinto  # noqa: E402

PANINO = {**PIZZA, "title": "Panino col salame", "ingredients": [
    {"name": "pane", "quantity": 120, "unit": "g"},
    {"name": "salame", "quantity": 60, "unit": "g"},
]}


@pytest.fixture()
def cena(client, diet, monkeypatch):
    """La cena di lunedì (oggi nella suite), riempita con «ho mangiato questo»."""
    modello = ModelloFinto()
    monkeypatch.setattr(mcp_router, "get_client", lambda db, user, role: modello)
    week = client.get("/api/planning/weeks/current").json()
    pasto = next(m for m in week["days"][0]["meals"] if m["slot_name"] == "Cena")
    return pasto["id"], modello


def test_sostituisci_un_pasto_gia_segnato(mcp, client, cena):
    meal_id, modello = cena
    errore, prima = strumento(mcp, "ho_mangiato_questo", meal_id=meal_id, cosa="una pizza")
    assert not errore, prima
    assert prima["is_followed"] is True

    # Su una casella piena «ho mangiato questo» resta un no...
    errore, testo = strumento(mcp, "ho_mangiato_questo", meal_id=meal_id, cosa="un panino")
    assert errore and "409" in testo

    # ...e «sostituisci» mette il piatto nuovo al suo posto, sempre segnato.
    modello.risposta = PANINO
    errore, dopo = strumento(mcp, "sostituisci_pasto", meal_id=meal_id, cosa="un panino col salame")
    assert not errore, dopo
    assert dopo["recipe"]["title"] == "Panino col salame"
    assert dopo["recipe"]["id"] != prima["recipe"]["id"]
    assert dopo["is_followed"] is True
    assert dopo == client.get(f"/api/planning/meals/{meal_id}").json()
    # La pizza resta nel ricettario (è una ricetta dell'utente).
    assert prima["recipe"]["id"] in {r["id"] for r in client.get("/api/recipes").json()["items"]}


def test_sostituisci_se_il_modello_sbaglia_il_pasto_resta_com_era(mcp, client, cena):
    meal_id, modello = cena
    _, prima = strumento(mcp, "ho_mangiato_questo", meal_id=meal_id, cosa="una pizza")
    modello.risposta = {"niente": "di leggibile"}
    errore, _ = strumento(mcp, "sostituisci_pasto", meal_id=meal_id, cosa="un panino")
    assert errore
    assert client.get(f"/api/planning/meals/{meal_id}").json()["recipe"]["id"] == prima["recipe"]["id"]


def test_modifica_pasto_cambia_le_grammature(mcp, client, cena):
    meal_id, _ = cena
    _, prima = strumento(mcp, "ho_mangiato_questo", meal_id=meal_id, cosa="una pizza")
    ingredienti = [
        {"nome": i["name"], "quantita": i["quantity"] * (2 if i["name"] == "mozzarella" else 1), "unita": i["unit"]}
        for i in prima["recipe"]["ingredients"]
    ]
    errore, dopo = strumento(mcp, "modifica_pasto", meal_id=meal_id, ingredienti=ingredienti,
                             titolo="Pizza con doppia mozzarella")
    assert not errore, dopo
    assert dopo["recipe"]["title"] == "Pizza con doppia mozzarella"
    mozzarella = next(i for i in dopo["recipe"]["ingredients"] if i["name"] == "mozzarella")
    assert mozzarella["quantity"] == 200
    assert dopo["is_followed"] is True
    assert dopo == client.get(f"/api/planning/meals/{meal_id}").json()


def test_modifica_pasto_vuoto_o_senza_niente(mcp, cena):
    meal_id, _ = cena
    errore, testo = strumento(mcp, "modifica_pasto", meal_id=meal_id, titolo="x")
    assert errore and "vuoto" in testo
    strumento(mcp, "ho_mangiato_questo", meal_id=meal_id, cosa="una pizza")
    errore, testo = strumento(mcp, "modifica_pasto", meal_id=meal_id)
    assert errore and "niente da cambiare" in testo


def test_svuota_pasto(mcp, client, cena):
    meal_id, _ = cena
    strumento(mcp, "ho_mangiato_questo", meal_id=meal_id, cosa="una pizza")
    errore, dopo = strumento(mcp, "svuota_pasto", meal_id=meal_id)
    assert not errore, dopo
    assert dopo["recipe"] is None and dopo["is_followed"] is None


def test_niente_su_un_pasto_ancora_da_segnare(mcp, cena):
    """Prima rispondeva 400 («prima segna il pasto come ho mangiato altro»)."""
    meal_id, modello = cena
    chiamate = modello.chiamate
    errore, dopo = strumento(mcp, "ho_mangiato_altro", meal_id=meal_id, niente=True)
    assert not errore, dopo
    assert dopo["is_followed"] is False
    assert dopo["eaten_nutrition"]["calories"] == 0
    assert modello.chiamate == chiamate
