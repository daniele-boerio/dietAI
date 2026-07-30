"""Due account: cosa può l'amministratore e cosa no l'altro.

La regola da tenere: nascondere un pulsante nel frontend non protegge niente. Qui si
prova la sostanza — chi non amministra non tocca la API key, non cambia i modelli, non
crea utenti — e il rovescio, cioè che l'app gli funzioni comunque perché genera con la
chiave dell'amministratore.
"""

import pytest

from app.models import User
from app.services.ai_client import AIError, ai_owner, get_client, model_for
from tests.conftest import GUEST_EMAIL, TEST_EMAIL


def _user(db, email) -> User:
    return db.query(User).filter(User.email == email).one()


# ── Chi è chi ──────────────────────────────────────────────────────────────────


def test_admin_e_ospite_si_riconoscono_dal_profilo(client, guest_client):
    io = client.get("/api/auth/me").json()
    altro = guest_client.get("/api/auth/me").json()

    assert io["is_admin"] is True
    assert io["can_manage_api_key"] is True
    assert altro["is_admin"] is False
    assert altro["can_manage_api_key"] is False


def test_l_ospite_vede_la_chiave_dell_admin_come_propria(client, guest_client, db):
    """`has_api_key` deve dire *la chiave con cui genererà*, non "ne possiede una".

    Se dicesse di no, l'onboarding gli aprirebbe davanti la schermata della API key:
    uno schermo che chiede una cosa che quell'utente non può nemmeno salvare.
    """
    assert guest_client.get("/api/auth/me").json()["has_api_key"] is False

    client.put("/api/auth/api-key", json={"api_key": "sk-or-" + "x" * 40})

    assert guest_client.get("/api/auth/me").json()["has_api_key"] is True
    # E resta comunque una chiave che non è sua: non la vede e non la cambia.
    assert _user(db, GUEST_EMAIL).claude_api_key_enc is None


# ── Quello che l'ospite non può fare ───────────────────────────────────────────


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("put", "/api/auth/api-key", {"api_key": "sk-or-" + "x" * 40}),
        ("delete", "/api/auth/api-key", None),
        ("get", "/api/config/ai/models", None),
        ("put", "/api/config/ai/models", {"planning": "anthropic/claude-opus-4-8"}),
        ("get", "/api/admin/users", None),
        ("post", "/api/admin/users", {"email": "terzo@dietai.local", "password": "12345678"}),
    ],
)
def test_le_rotte_da_amministratore_rispondono_403(guest_client, method, path, body):
    call = getattr(guest_client, method)
    res = call(path, json=body) if body is not None else call(path)
    assert res.status_code == 403, res.text


def test_l_ospite_non_cambia_i_modelli_nemmeno_di_nascosto(client, guest_client, db):
    client.put(
        "/api/config/ai/models",
        json={"planning": "anthropic/claude-opus-4-8", "chat": None, "diet": None},
    )
    guest_client.put("/api/config/ai/models", json={"planning": "openai/gpt-4o-mini"})

    ospite = _user(db, GUEST_EMAIL)
    assert model_for(db, ospite.id, "planning") == "anthropic/claude-opus-4-8"


# ── Quello che l'ospite fa con la chiave dell'altro ────────────────────────────


def test_le_chiamate_dell_ospite_usano_chiave_e_modelli_dell_admin(client, guest_client, db):
    client.put("/api/auth/api-key", json={"api_key": "sk-or-" + "x" * 40})
    client.put(
        "/api/config/ai/models",
        json={"planning": "anthropic/claude-opus-4-8", "chat": None, "diet": None},
    )

    ospite = _user(db, GUEST_EMAIL)
    admin = _user(db, TEST_EMAIL)

    assert ai_owner(db, ospite).id == admin.id
    assert get_client(db, ospite, "planning").model == "anthropic/claude-opus-4-8"


def test_senza_chiave_dell_admin_il_messaggio_non_manda_l_ospite_dove_non_puo_andare(
    client, guest_client, db
):
    ospite = _user(db, GUEST_EMAIL)
    with pytest.raises(AIError) as exc:
        get_client(db, ospite, "planning")

    assert "Impostazioni" not in exc.value.detail
    assert "amministratore" in exc.value.detail


def test_la_configurazione_ai_mostra_all_ospite_i_modelli_con_cui_generera(client, guest_client):
    client.put(
        "/api/config/ai/models",
        json={"planning": "anthropic/claude-opus-4-8", "chat": None, "diet": None},
    )

    config = guest_client.get("/api/config/ai").json()
    planning = next(r for r in config["roles"] if r["key"] == "planning")

    assert config["can_choose_models"] is False
    assert planning["model"] == "anthropic/claude-opus-4-8"


# ── L'interruttore AI ──────────────────────────────────────────────────────────


def test_l_interruttore_ai_spegne_le_generazioni_ma_non_l_app(client, guest_client, db):
    client.put("/api/auth/api-key", json={"api_key": "sk-or-" + "x" * 40})
    guest_client.post(
        "/api/diet/manual",
        json={"meals": [{"name": "Pranzo", "order": 0, "calories": 700,
                         "protein_g": 40, "carbs_g": 80, "fat_g": 20}]},
    )
    ospite = _user(db, GUEST_EMAIL)

    res = client.put(f"/api/admin/users/{ospite.id}/flags", json={"ai_enabled": False})
    assert res.status_code == 200, res.text
    assert res.json()["ai_enabled"] is False

    db.refresh(ospite)
    with pytest.raises(AIError) as exc:
        get_client(db, ospite, "planning")
    assert exc.value.status_code == 403

    # Il resto dell'app resta in piedi: i dati sono suoi e non sono stati toccati.
    assert guest_client.get("/api/planning/weeks/current").status_code == 200


# ── Sospensione, password, cancellazione ───────────────────────────────────────


def test_sospendere_chiude_le_sessioni_gia_aperte(client, guest_client, db):
    ospite = _user(db, GUEST_EMAIL)
    assert guest_client.get("/api/auth/me").status_code == 200

    client.put(f"/api/admin/users/{ospite.id}/flags", json={"is_active": False})

    # Il cookie che aveva in mano non vale più, e il refresh non lo salva.
    assert guest_client.get("/api/auth/me").status_code == 401
    login = guest_client.post(
        "/api/auth/login", json={"email": GUEST_EMAIL, "password": "password-di-test"}
    )
    assert login.status_code == 403


def test_l_admin_rimette_la_password_a_chi_l_ha_persa(client, guest_client, db):
    ospite = _user(db, GUEST_EMAIL)

    res = client.post(
        f"/api/admin/users/{ospite.id}/password", json={"new_password": "nuova-password"}
    )
    assert res.status_code == 200, res.text

    assert guest_client.get("/api/auth/me").status_code == 401
    login = guest_client.post(
        "/api/auth/login", json={"email": GUEST_EMAIL, "password": "nuova-password"}
    )
    assert login.status_code == 200


def test_l_amministratore_non_si_sospende_da_solo(client, db):
    """Da lì si tornerebbe soltanto col comando di reset dal container."""
    admin = _user(db, TEST_EMAIL)

    res = client.put(f"/api/admin/users/{admin.id}/flags", json={"is_active": False})
    assert res.status_code == 400

    assert client.delete(f"/api/admin/users/{admin.id}").status_code == 400


def test_due_account_con_la_stessa_email_no(client, guest_client):
    res = client.post(
        "/api/admin/users", json={"email": GUEST_EMAIL, "password": "una-password"}
    )
    assert res.status_code == 409


def test_cancellare_un_account_porta_via_i_suoi_dati(client, guest_client, db):
    """Le FK sono in CASCADE: è il motivo per cui esiste la sospensione."""
    guest_client.post(
        "/api/diet/manual",
        json={"meals": [{"name": "Pranzo", "order": 0, "calories": 700,
                         "protein_g": 40, "carbs_g": 80, "fat_g": 20}]},
    )
    ospite = _user(db, GUEST_EMAIL)

    assert client.delete(f"/api/admin/users/{ospite.id}").status_code == 204
    assert db.query(User).filter(User.email == GUEST_EMAIL).first() is None


# ── I dati non si mescolano ────────────────────────────────────────────────────


def test_ognuno_vede_solo_la_propria_dieta(client, guest_client, diet):
    """`diet` è la dieta dell'amministratore: l'ospite non deve vederla."""
    assert client.get("/api/diet/current").json()["id"] == diet["id"]
    assert guest_client.get("/api/diet/current").status_code == 404


def _ricetta(grammi: int, calorie: int) -> dict:
    return {
        "title": "Pasta con le zucchine",
        "instructions": "Salta le zucchine, unisci la pasta.",
        "calories": calorie,
        "protein_g": 20,
        "carbs_g": 70,
        "fat_g": 15,
        "ingredients": [{"name": "zucchine", "quantity": grammi, "unit": "g"}],
    }


def test_il_ricettario_non_e_in_comune(client, guest_client):
    """Le ricette sono di chi le ha generate, grammature comprese.

    È il punto in cui due diete diverse si toccherebbero peggio: lo stesso piatto pesa
    200 g per uno e 120 g per l'altro, e una riga condivisa vorrebbe dire mangiare i
    macro di qualcun altro. In comune c'è solo l'anagrafica degli ingredienti — nome,
    reparto, prezzo al kg — che di grammi e calorie non sa niente.
    """
    mia = client.post("/api/recipes", json=_ricetta(200, 700)).json()
    sua = guest_client.post("/api/recipes", json=_ricetta(120, 450)).json()

    assert {r["id"] for r in client.get("/api/recipes").json()["items"]} == {mia["id"]}
    assert {r["id"] for r in guest_client.get("/api/recipes").json()["items"]} == {sua["id"]}

    # E nemmeno indovinando l'id: la riga di un altro non si apre.
    assert client.get(f"/api/recipes/{sua['id']}").status_code == 404
    assert guest_client.get(f"/api/recipes/{mia['id']}").status_code == 404

    # Stesso ingrediente, due quantità: la riga condivisa è solo il nome.
    dettaglio_mio = client.get(f"/api/recipes/{mia['id']}").json()
    dettaglio_suo = guest_client.get(f"/api/recipes/{sua['id']}").json()
    assert dettaglio_mio["ingredients"][0]["quantity"] == 200
    assert dettaglio_suo["ingredients"][0]["quantity"] == 120
    assert dettaglio_mio["calories"] == 700 and dettaglio_suo["calories"] == 450
