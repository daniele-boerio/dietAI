"""Quanto costa l'AI, utente per utente.

Chi mette la chiave paga per tutti: il registro (`AIUsage`) è il numero che gli serve
per decidere quando usare il freno `ai_enabled`.
"""

from types import SimpleNamespace

from app.models import AIUsage
from app.services import ai_client, usage
from app.services.ai_client import _usage_dict, get_client


def test_l_uso_di_openrouter_porta_il_costo():
    risposta = SimpleNamespace(prompt_tokens=1200, completion_tokens=800, cost=0.0123)
    assert _usage_dict(risposta) == {
        "input_tokens": 1200, "output_tokens": 800, "cost_usd": 0.0123,
    }


def test_il_costo_fra_i_campi_sconosciuti_all_sdk():
    risposta = SimpleNamespace(
        prompt_tokens=10, completion_tokens=5, model_extra={"cost": "0.002"}
    )
    assert _usage_dict(risposta)["cost_usd"] == 0.002


def test_il_registro_scrive_chi_ha_premuto_il_pulsante(client, guest_client, db):
    """L'ospite genera con la chiave dell'admin: la riga va all'ospite."""
    from app.models import User

    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    ospite = db.query(User).filter(User.is_admin.is_(False)).one()

    c = get_client(db, ospite, "chat")
    c.on_usage(c.model, {"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.01})

    riga = db.query(AIUsage).one()
    assert riga.user_id == ospite.id
    assert riga.role == "chat"
    assert riga.cost_usd == 0.01


def test_senza_costo_dichiarato_si_stima_dal_listino(db, client, monkeypatch):
    from app.services import catalog

    monkeypatch.setattr(catalog, "_cache", (0, [
        {"id": "x/modello", "prompt_price": 1.0, "completion_price": 4.0}
    ]))
    usage.recorder(db.get_bind(), 1, "planning")(
        "x/modello", {"input_tokens": 1_000_000, "output_tokens": 500_000, "cost_usd": None}
    )
    riga = db.query(AIUsage).one()
    assert riga.cost_usd == 3.0
    assert riga.cost_estimated is True


def test_una_chiamata_fallita_e_pagata_lo_stesso(db, client):
    """Una risposta finita a vuoto i token li ha consumati: il registro la conta."""
    righe = []

    class Backend:
        supports_native_pdf = False

        def complete(self, **kw):
            self.last_usage = {"input_tokens": 9, "output_tokens": 9000, "cost_usd": 0.5}
            raise ai_client.AIError("vuota")

    c = ai_client.AIClient.__new__(ai_client.AIClient)
    c.model = "x/m"
    c._backend = Backend()
    c.on_usage = lambda model, u: righe.append(u)
    try:
        c.chat("s", [{"role": "user", "content": "x"}])
    except ai_client.AIError:
        pass
    assert righe and righe[0]["output_tokens"] == 9000


def test_il_riepilogo_per_utente(client, guest_client, db):
    rec = usage.recorder(db.get_bind(), 1, "planning")
    rec("m", {"input_tokens": 1000, "output_tokens": 2000, "cost_usd": 0.25})
    rec("m", {"input_tokens": 10, "output_tokens": 20, "cost_usd": None})

    res = client.get("/api/admin/usage").json()
    admin = next(u for u in res["users"] if u["user_id"] == 1)
    ospite = next(u for u in res["users"] if u["user_id"] != 1)
    assert admin["calls"] == 2
    assert admin["cost_usd"] == 0.25
    assert admin["calls_without_cost"] == 1
    assert ospite["calls"] == 0
    assert ospite["calls_without_cost"] == 0
    assert res["total_cost_usd"] == 0.25


def test_il_riepilogo_e_solo_dell_amministratore(guest_client):
    assert guest_client.get("/api/admin/usage").status_code == 403
