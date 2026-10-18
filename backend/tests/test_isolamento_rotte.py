"""Nessuna rotta con un id nel path lascia toccare i dati di un altro account.

Il filtro per `user_id` è scritto a mano in ogni router (`_get_meal`, `_own_item`,
`_get_week`...): un endpoint nuovo che se lo dimentica è un bug di sicurezza. Questo
test scorre **tutte** le rotte dell'app, e per ognuna con un id l'ospite prova a usare
quello dell'amministratore, con un corpo valido — un 422 vorrebbe dire che la richiesta
non è nemmeno arrivata al controllo, e non proverebbe niente. Deve ricevere 403 o 404,
e alla fine i dati dell'amministratore devono essere quelli di prima.

Un parametro nuovo che qui non è classificato fa fallire il test: va deciso a quale
risorsa si riferisce, o perché è condiviso per scelta.
"""

import re

import pytest

from app.main import app
from app.routers import chat as chat_router
from app.routers import planning as planning_router
from app.routers import recipes as recipes_router
from app.services import planner
from tests.test_flow import FakeModel

# Parametri che non sono una risorsa di un utente, e perché.
CONDIVISI_O_PROPRI = {
    "user_id",  # rotte da amministratore: 403 per l'ospite, guardia in test_due_account
    "rule_id",  # regole di normalizzazione: solo amministratore
    "ingredient_id",  # anagrafica condivisa per scelta (docs/spesa.md)
    "week_start",  # una data: ognuno vede la sua settimana
    "day",  # una data: ognuno la sua pesata
}

CORPI = {
    ("PUT", "/api/diet/{diet_id}/frequencies"): {"frequencies": []},
    ("PUT", "/api/diet/{diet_id}/meals"): {
        "meals": [{"name": "X", "order": 0, "calories": 500, "protein_g": 10,
                   "carbs_g": 10, "fat_g": 10}]
    },
    ("PUT", "/api/config/pantry/{item_id}"): {"quantity": 1},
    ("PUT", "/api/shopping/items/{item_id}/check"): {"is_checked": True},
    ("PUT", "/api/shopping/items/{item_id}/quantity"): {"quantity": 1},
    ("POST", "/api/chat/shopping/{week_id}/messages"): {"content": "ciao"},
    ("POST", "/api/chat/meals/{meal_id}/messages"): {"content": "ciao"},
    ("PUT", "/api/planning/meals/{meal_id}/assign"): {"recipe_id": 1},
    ("PUT", "/api/planning/meals/{meal_id}/recurring"): {"is_recurring": False},
    ("PUT", "/api/planning/meals/{meal_id}/eaten"): {"nothing": True},
    ("PUT", "/api/planning/meals/{meal_id}/followed"): {"is_followed": True},
    ("POST", "/api/planning/meals/{meal_id}/swap"): {"other_meal_id": 1},
    ("PUT", "/api/planning/days/{day_id}/skip"): {"is_skipped": True},
    ("PUT", "/api/recipes/{recipe_id}"): {
        "title": "x",
        "instructions": "x",
        "ingredients": [{"name": "pasta", "quantity": 80, "unit": "g"}],
    },
    ("PUT", "/api/recipes/{recipe_id}/rate"): {"rating": 1},
    ("PUT", "/api/recipes/{recipe_id}/favorite"): {"is_favorite": True},
    ("POST", "/api/recipes/{recipe_id}/substitute"): {"ingredient_to_replace": "pasta"},
}


class NessunModello(FakeModel):
    """Se una rotta arrivasse al modello coi dati di un altro, il test lo vedrebbe."""

    def chat(self, *a, **k):
        raise AssertionError("una rotta altrui è arrivata al modello")

    def generate_json(self, *a, **k):
        raise AssertionError("una rotta altrui è arrivata al modello")


def _rotte():
    for r in app.routes:
        path = getattr(r, "path", "")
        params = re.findall(r"{(\w+)}", path)
        if not params or not path.startswith("/api/"):
            continue
        for metodo in sorted(r.methods - {"HEAD", "OPTIONS"}):
            yield metodo, path, params


def _risorsa(path: str, param: str) -> str:
    if param != "item_id":
        return param
    if "/base-ingredients/" in path:
        return "base_id"
    if "/excluded/" in path:
        return "excluded_id"
    if "/pantry/" in path:
        return "pantry_id"
    return "shopping_item_id"


@pytest.fixture()
def admin_e_ospite(client, guest_client, diet, monkeypatch):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    week = client.get("/api/planning/weeks/current").json()

    pasto = week["days"][0]["meals"][1]
    ids = {
        "diet_id": diet["id"],
        "week_id": week["id"],
        "day_id": week["days"][0]["id"],
        "meal_id": pasto["id"],
        "recipe_id": pasto["recipe"]["id"],
        "pantry_id": client.post(
            "/api/config/pantry", json={"ingredient_name": "riso", "quantity": 500, "unit": "g"}
        ).json()["id"],
        "base_id": client.post(
            "/api/config/base-ingredients", json={"ingredient_name": "sale"}
        ).json()["id"],
        "excluded_id": client.post(
            "/api/config/excluded", json={"ingredient_name": "kiwi"}
        ).json()["id"],
        "shopping_item_id": client.get("/api/shopping/current").json()["categories"][0][
            "items"
        ][0]["id"],
    }

    # Anche l'ospite ha una dieta: senza, molte rotte si fermerebbero prima del
    # controllo di proprietà («nessuna dieta attiva») e il test non proverebbe niente.
    guest_client.post(
        "/api/diet/manual",
        json={"meals": [{"name": "Pranzo", "order": 0, "calories": 700, "protein_g": 40,
                         "carbs_g": 80, "fat_g": 20}]},
    )
    for modulo in (planner, chat_router, recipes_router, planning_router):
        monkeypatch.setattr(modulo, "get_client", lambda db, user, role: NessunModello(user))
    return client, guest_client, ids


def _fotografia(client):
    return {
        "settimana": client.get("/api/planning/weeks/current").json()["days"],
        "dispensa": client.get("/api/config/pantry").json(),
        "base": client.get("/api/config/base-ingredients").json(),
        "esclusi": client.get("/api/config/excluded").json(),
        "spesa": client.get("/api/shopping/current").json()["categories"],
        "dieta": client.get("/api/diet/current").json()["meals"],
    }


def test_l_ospite_non_tocca_niente_dell_amministratore(admin_e_ospite):
    admin, ospite, ids = admin_e_ospite
    prima = _fotografia(admin)

    provate = 0
    for metodo, path, params in _rotte():
        if all(p in CONDIVISI_O_PROPRI for p in params):
            continue
        sconosciuti = [p for p in params if p not in CONDIVISI_O_PROPRI and
                       _risorsa(path, p) not in ids]
        assert not sconosciuti, f"{metodo} {path}: parametro da classificare {sconosciuti}"

        url = path
        for p in params:
            url = url.replace("{" + p + "}", str(ids[_risorsa(path, p)]))
        res = ospite.request(metodo, url, json=CORPI.get((metodo, path)))
        assert res.status_code in (403, 404), (metodo, path, res.status_code, res.text)
        provate += 1

    assert provate >= 29
    assert _fotografia(admin) == prima
