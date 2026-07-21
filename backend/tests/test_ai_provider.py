"""Scelta del provider e del modello, ed estrazione del testo dal PDF della dieta."""

import pytest

from app.config import default_model
from app.routers import diet as diet_router
from app.services.ai_client import model_for
from app.services.pdf import extract_text, looks_scanned

DIET_TEXT = """PIANO ALIMENTARE SETTIMANALE
Paziente: Mario Rossi — 2000 kcal al giorno

COLAZIONE (400 kcal): proteine 20 g, carboidrati 50 g, grassi 12 g
Latte parzialmente scremato con fiocchi d'avena e frutta fresca di stagione.

PRANZO (700 kcal): proteine 40 g, carboidrati 80 g, grassi 20 g
Primo piatto con verdure di stagione, una fonte proteica e olio a crudo.

CENA (600 kcal): proteine 45 g, carboidrati 50 g, grassi 22 g
Secondo piatto con contorno di verdura e una porzione di pane integrale.
"""


def build_pdf(text: str) -> bytes:
    """Un PDF minimo ma valido, con il testo dentro uno stream come quelli veri."""
    lines = text.strip().split("\n")
    parts = ["BT /F1 12 Tf 72 720 Td 14 TL"]
    for line in lines:
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        parts.append(f"({escaped}) Tj T*")
    parts.append("ET")
    stream = "\n".join(parts).encode("latin-1", "replace")

    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length %d>>stream\n" % len(stream) + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj" % i + body + b"endobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1,
        xref,
    )
    return bytes(out)


EMPTY_PDF = build_pdf("x")  # una pagina praticamente senza testo: finge la scansione


class FakeDietModel:
    """Legge il testo che gli arriva nel prompt e restituisce la struttura attesa."""

    supports_native_pdf = False
    model = "finto/modello-di-test"

    def __init__(self):
        self.received_prompt = None

    def generate_json(self, system, prompt, **kwargs):
        self.received_prompt = prompt
        return {
            "daily_calories": 1700,
            "notes": "",
            "meals": [
                {"name": "Colazione", "order": 0, "calories": 400, "protein_g": 20,
                 "carbs_g": 50, "fat_g": 12, "notes": ""},
                {"name": "Pranzo", "order": 1, "calories": 700, "protein_g": 40,
                 "carbs_g": 80, "fat_g": 20, "notes": ""},
                {"name": "Cena", "order": 2, "calories": 600, "protein_g": 45,
                 "carbs_g": 50, "fat_g": 22, "notes": ""},
            ],
        }


# ── Estrazione del testo ───────────────────────────────────────────────────────


def test_dal_pdf_si_estrae_il_testo():
    text = extract_text(build_pdf(DIET_TEXT))

    assert "COLAZIONE" in text
    assert "proteine 40 g" in text
    assert not looks_scanned(text)


def test_un_pdf_senza_testo_e_riconosciuto_come_scansione():
    assert looks_scanned(extract_text(EMPTY_PDF))


def test_un_file_illeggibile_non_esplode():
    assert extract_text(b"non sono un pdf") == ""


# ── Percorso di upload ─────────────────────────────────────────────────────────


def _upload(client, content):
    return client.post(
        "/api/diet/upload",
        files={"file": ("dieta.pdf", content, "application/pdf")},
    )


def test_upload_manda_al_modello_il_testo_estratto(client, monkeypatch):
    """Con un PDF testuale non serve un modello che veda: basta il testo."""
    fake = FakeDietModel()
    monkeypatch.setattr(diet_router, "get_client", lambda db, user, role: fake)
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta"})

    res = _upload(client, build_pdf(DIET_TEXT))

    assert res.status_code == 200, res.text
    assert res.json()["total_daily_calories"] == 1700
    assert len(res.json()["meals"]) == 3
    # Il testo del PDF è finito davvero nel prompt, non il file.
    assert "COLAZIONE" in fake.received_prompt


def test_una_scansione_senza_modello_con_vista_lo_dice_chiaramente(client, monkeypatch):
    fake = FakeDietModel()  # supports_native_pdf = False
    monkeypatch.setattr(diet_router, "get_client", lambda db, user, role: fake)
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta"})

    res = _upload(client, EMPTY_PDF)

    assert res.status_code == 400
    assert "scansione" in res.json()["detail"]
    assert "a mano" in res.json()["detail"]  # dice anche come uscirne


def test_un_file_non_pdf_viene_rifiutato(client):
    res = client.post(
        "/api/diet/upload", files={"file": ("dieta.txt", b"ciao", "text/plain")}
    )
    assert res.status_code == 400


# ── Scelta del modello ─────────────────────────────────────────────────────────


def test_la_chiave_deve_avere_il_prefisso_del_provider(client):
    """Di default il provider è OpenRouter: una chiave Anthropic è quasi certamente
    un incollaggio sbagliato, e dirlo subito evita di scoprirlo alla prima ricetta."""
    res = client.put("/api/auth/api-key", json={"api_key": "sk-ant-chiave-di-un-altro"})
    assert res.status_code == 400
    assert "sk-or-" in res.json()["detail"]


def test_config_ai_espone_un_modello_per_ruolo(client):
    data = client.get("/api/config/ai").json()

    assert data["provider"] == "openrouter"
    assert data["key_prefix"] == "sk-or-"
    assert [r["key"] for r in data["roles"]] == ["planning", "chat", "diet"]
    # Nessuna scelta ancora fatta: si mostra il default dell'ambiente.
    assert all(r["model"] is None for r in data["roles"])
    assert all(r["default"] for r in data["roles"])


def test_il_modello_scelto_sostituisce_il_default(client, db):
    res = client.put(
        "/api/config/ai/models",
        json={"planning": "z-ai/glm-4.6", "chat": "  ", "diet": None},
    )
    assert res.status_code == 200

    roles = {r["key"]: r for r in res.json()["roles"]}
    assert roles["planning"]["model"] == "z-ai/glm-4.6"
    # Stringa vuota = "torna al default", non "modello chiamato stringa vuota".
    assert roles["chat"]["model"] is None

    from app.models import User

    user_id = db.query(User).one().id
    assert model_for(db, user_id, "planning") == "z-ai/glm-4.6"
    assert model_for(db, user_id, "chat") == default_model("chat")


@pytest.mark.parametrize("role", ["planning", "chat", "diet"])
def test_esiste_un_default_per_ogni_ruolo(role):
    assert default_model(role)
