"""Il pasto fisso: quando si toglie la spunta, e quando si svuota la casella.

Un pasto fisso si ricopia da sé sulle settimane che si aprono, e una settimana si apre
anche solo sfogliandola: togliere la spunta non può limitarsi a smettere di ricopiare,
o le copie già scritte restano lì e l'interruttore sembra rotto. Qui si controlla che
se ne vada in avanti — e solo in avanti, e solo da quello che non è ancora stato.
"""

import pytest

RICETTA = {
    "title": "Yogurt e frutta secca",
    "description": "La colazione di sempre",
    "prep_time_min": 5,
    "cook_time_min": 0,
    "difficulty": "easy",
    "instructions": "1. Versa. 2. Mangia.",
    "calories": 400,
    "protein_g": 20.0,
    "carbs_g": 50.0,
    "fat_g": 12.0,
    "ingredients": [
        {"name": "yogurt greco", "quantity": 200, "unit": "g"},
        {"name": "mandorle", "quantity": 30, "unit": "g"},
    ],
}


def pasto(week, dow, nome):
    return next(m for m in week["days"][dow]["meals"] if m["slot_name"] == nome)


def colazioni(week):
    return [pasto(week, dow, "Colazione") for dow in range(7)]


@pytest.fixture()
def colazione_fissa(client, diet):
    """Lunedì la colazione è assegnata a mano e marcata «fissa», tutti i giorni."""
    week = client.get("/api/planning/weeks/current").json()
    meal = pasto(week, 0, "Colazione")

    res = client.put(f"/api/planning/meals/{meal['id']}/assign", json={"recipe": RICETTA})
    assert res.status_code == 200, res.text

    res = client.put(
        f"/api/planning/meals/{meal['id']}/recurring",
        json={"is_recurring": True, "recurring_rule": {"type": "daily"}},
    )
    assert res.status_code == 200, res.text
    return res.json()


# ── Si ricopia in avanti ───────────────────────────────────────────────────────


def test_il_pasto_fisso_riempie_la_settimana_dopo(client, colazione_fissa):
    nxt = client.get("/api/planning/weeks/next").json()

    assert all(c["recipe"]["title"] == RICETTA["title"] for c in colazioni(nxt))
    assert all(c["is_recurring"] for c in colazioni(nxt))


# ── Togliendo la spunta se ne va da lì in poi ──────────────────────────────────


def test_togliere_il_fisso_svuota_le_caselle_in_avanti(client, colazione_fissa):
    client.get("/api/planning/weeks/next")  # la settimana prossima esiste ed è piena

    res = client.put(
        f"/api/planning/meals/{colazione_fissa['id']}/recurring",
        json={"is_recurring": False},
    )
    assert res.status_code == 200, res.text
    assert res.json()["cleared_forward"] == 7

    nxt = client.get("/api/planning/weeks/next").json()
    assert all(c["recipe"] is None for c in colazioni(nxt))


def test_la_casella_da_cui_si_toglie_resta_com_era(client, colazione_fissa):
    """Si spegne la ripetizione, non si cancella il piatto che si ha davanti."""
    res = client.put(
        f"/api/planning/meals/{colazione_fissa['id']}/recurring",
        json={"is_recurring": False},
    )

    meal = res.json()
    assert meal["is_recurring"] is False
    assert meal["recipe"]["title"] == RICETTA["title"]


def test_e_non_ricomincia_da_solo(client, colazione_fissa):
    """Le settimane che si apriranno dopo non devono ripescarlo dalla precedente."""
    client.get("/api/planning/weeks/next")
    client.put(
        f"/api/planning/meals/{colazione_fissa['id']}/recurring", json={"is_recurring": False}
    )

    dopo = client.get("/api/planning/weeks/by-date/2100-01-04").json()
    assert all(c["recipe"] is None for c in colazioni(dopo))


def test_una_casella_già_vissuta_non_si_cancella(client, colazione_fissa):
    """Segnare com'è andata rende quella riga un fatto, non più un programma."""
    nxt = client.get("/api/planning/weeks/next").json()
    martedi = pasto(nxt, 1, "Colazione")
    assert client.put(
        f"/api/planning/meals/{martedi['id']}/followed", json={"is_followed": True}
    ).status_code == 200

    res = client.put(
        f"/api/planning/meals/{colazione_fissa['id']}/recurring",
        json={"is_recurring": False},
    )
    assert res.json()["cleared_forward"] == 6

    rimasta = pasto(client.get("/api/planning/weeks/next").json(), 1, "Colazione")
    assert rimasta["recipe"]["title"] == RICETTA["title"]
    # Il segno di fisso però va via: la ricetta resta come memoria, non come regola.
    assert rimasta["is_recurring"] is False


def test_una_colazione_uguale_scelta_a_mano_non_e_una_copia(client, colazione_fissa):
    """Si tolgono le caselle che quel piatto l'hanno *ricevuto*, non quelle scelte.

    A distinguerle è il segno di fisso, non la ricetta: qui la casella viene prima
    svuotata (e lì il segno se ne va) e poi riempita a mano con lo stesso piatto —
    che è una riga sola, quindi anche la `recipe_id` coincide. È scelta, e resta.
    """
    nxt = client.get("/api/planning/weeks/next").json()
    mercoledi = pasto(nxt, 2, "Colazione")
    client.delete(f"/api/planning/meals/{mercoledi['id']}/recipe")
    scelta = client.put(
        f"/api/planning/meals/{mercoledi['id']}/assign", json={"recipe": RICETTA}
    ).json()
    assert scelta["is_recurring"] is False
    assert scelta["recipe"]["id"] == colazione_fissa["recipe"]["id"]

    res = client.put(
        f"/api/planning/meals/{colazione_fissa['id']}/recurring", json={"is_recurring": False}
    )
    assert res.json()["cleared_forward"] == 6

    rimasta = pasto(client.get("/api/planning/weeks/next").json(), 2, "Colazione")
    assert rimasta["recipe"]["title"] == RICETTA["title"]


def test_togliendolo_da_meta_settimana_non_ricomincia_dal_lunedi(client, colazione_fissa):
    """Il buco che si vede solo con la regola "tutti i giorni".

    Togliendo la spunta dal mercoledì, i giorni prima restano pieni — è roba già in
    programma — ma il **segno** di fisso se ne va anche da lì: `apply_recurring_meals`
    legge la settimana precedente, e una sola casella accesa il lunedì avrebbe
    riempito da capo tutta la settimana dopo.
    """
    nxt = client.get("/api/planning/weeks/next").json()
    mercoledi = pasto(nxt, 2, "Colazione")

    res = client.put(
        f"/api/planning/meals/{mercoledi['id']}/recurring", json={"is_recurring": False}
    )
    assert res.json()["cleared_forward"] == 4  # da giovedì a domenica

    dopo = client.get("/api/planning/weeks/next").json()
    assert [bool(c["recipe"]) for c in colazioni(dopo)] == [True] * 3 + [False] * 4
    assert not any(c["is_recurring"] for c in colazioni(dopo))

    # E la settimana ancora dopo nasce senza colazioni ricopiate.
    fra_due = client.get("/api/planning/weeks/by-date/2100-01-04").json()
    assert all(c["recipe"] is None for c in colazioni(fra_due))


def test_la_spesa_si_accorcia(client, colazione_fissa):
    client.get("/api/planning/weeks/next")

    def yogurt():
        lst = client.get("/api/shopping/current").json()
        voci = {i["name"]: i for cat in lst["categories"] for i in cat["items"]}
        return voci.get("yogurt greco", {}).get("quantity", 0)

    prima = yogurt()
    client.put(
        f"/api/planning/meals/{colazione_fissa['id']}/recurring", json={"is_recurring": False}
    )

    # Restava solo il lunedì da cui si è tolta la spunta.
    assert prima == pytest.approx(8 * 200)
    assert yogurt() == pytest.approx(200)


# ── Il tasto elimina ───────────────────────────────────────────────────────────


def test_eliminare_svuota_la_casella_e_basta(client, colazione_fissa):
    """Non è "ho mangiato altro": il piatto non si accoda da nessuna parte."""
    nxt = client.get("/api/planning/weeks/next").json()
    martedi = pasto(nxt, 1, "Colazione")

    res = client.delete(f"/api/planning/meals/{martedi['id']}/recipe")
    assert res.status_code == 200, res.text
    assert res.json()["recipe"] is None
    assert res.json()["is_skipped"] is False

    dopo = client.get("/api/planning/weeks/next").json()
    assert pasto(dopo, 1, "Colazione")["recipe"] is None
    # Gli altri giorni non si sono spostati di un millimetro.
    assert pasto(dopo, 2, "Colazione")["recipe"]["title"] == RICETTA["title"]


def test_eliminare_toglie_anche_il_segno_di_fisso(client, colazione_fissa):
    """Una casella vuota che si ripete ogni settimana non vuol dire niente."""
    res = client.delete(f"/api/planning/meals/{colazione_fissa['id']}/recipe")

    assert res.json()["is_recurring"] is False
    assert res.json()["recurring_rule"] is None


def test_eliminare_toglie_il_piatto_dalla_spesa(client, colazione_fissa):
    def mandorle():
        lst = client.get("/api/shopping/current").json()
        voci = {i["name"]: i for cat in lst["categories"] for i in cat["items"]}
        return voci.get("mandorle", {}).get("quantity", 0)

    assert mandorle() == pytest.approx(30)
    client.delete(f"/api/planning/meals/{colazione_fissa['id']}/recipe")
    assert mandorle() == 0
