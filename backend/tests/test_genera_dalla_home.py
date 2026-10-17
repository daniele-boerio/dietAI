"""Il pulsante «Genera N pasti» della home promette quello che la dialog propone.

Contava `meals_total - meals_filled`, cioè anche i pasti vuoti dei giorni già
passati: di venerdì, su una settimana vuota, «Genera 21 pasti», e la dialog che
apriva ne generava 9. Ora conta da oggi in avanti, come `lib/generation.js`.
"""

from app.services import planner


def test_la_home_conta_solo_da_oggi_in_avanti(client, diet):
    home = client.get("/api/tracking/dashboard").json()
    giorni_rimasti = 7 - planner.today().weekday()
    da_generare = [m for m in home["today"]["meals"] if not m["self_managed"]]

    assert home["week"]["meals_to_generate"] == giorni_rimasti * len(da_generare)


def test_i_pasti_gia_pieni_e_quelli_saltati_non_si_contano(client, diet):
    week = client.get("/api/planning/weeks/current").json()
    oggi = planner.today().isoformat()
    pasti_di_oggi = next(d for d in week["days"] if d["date"] == oggi)["meals"]
    prima = client.get("/api/tracking/dashboard").json()["week"]["meals_to_generate"]

    # «Ho mangiato altro» su un pasto vuoto di oggi: non c'è più niente da generarci.
    client.put(
        f"/api/planning/meals/{pasti_di_oggi[0]['id']}/followed", json={"is_followed": False}
    )

    dopo = client.get("/api/tracking/dashboard").json()["week"]["meals_to_generate"]
    assert dopo == prima - 1
