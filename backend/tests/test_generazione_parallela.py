"""La settimana in parallelo: prima il piano di tutta la settimana, poi le ricette a
pezzi di qualche giorno, scritte insieme.

Una chiamata sola scriveva le ricette una dopo l'altra (nove ricette, cinque o sei
minuti). Spezzarla e basta avrebbe perso l'anti-spreco, che vale sulla settimana
intera: qui l'incastro lo decide una chiamata breve, e ogni pezzo lo riceve.
"""

import re
import threading

import pytest

from app.services import planner, prompts
from tests.test_flow import DAYS, _fake_recipe


class ModelloAPezzi:
    """Risponde al piano col piano e a ogni pezzo con le ricette dei suoi giorni."""

    def __init__(self, piano_fallisce=False, pezzo_che_fallisce=None):
        self.model = "finto/modello"
        self.supports_native_pdf = False
        self.chiamate: list[tuple[str, str]] = []
        self._lock = threading.Lock()
        self.piano_fallisce = piano_fallisce
        self.pezzo_che_fallisce = pezzo_che_fallisce

    def generate_json(self, system, prompt, **kwargs):
        with self._lock:
            self.chiamate.append((system, prompt))
        if system == prompts.WEEK_OUTLINE_SYSTEM:
            if self.piano_fallisce:
                raise RuntimeError("piano non riuscito")
            return {
                "days": [
                    {"day_of_week": d, "meals": [
                        {"slot_name": n, "title": f"{n} {d}", "main_ingredients": ["zucchine 150 g"]}
                        for n in ("Colazione", "Pranzo", "Cena")
                    ]}
                    for d in range(DAYS)
                ],
                "ingredient_reuse_notes": "Zucchine divise fra i giorni.",
            }
        sezione = prompt.split("DA GENERARE ORA", 1)[-1].split("PASTI GIÀ ASSEGNATI", 1)[0]
        giorni = sorted({int(g) for g in re.findall(r"day_of_week (\d)", sezione)})
        if self.pezzo_che_fallisce is not None and self.pezzo_che_fallisce in giorni:
            raise RuntimeError("pezzo non riuscito")
        return {
            "days": [
                {"day_of_week": d, "meals": [
                    {"slot_name": n, "recipe": _fake_recipe(f"{n} {d}", kcal, [
                        {"name": "zucchine", "quantity": 150, "unit": "g"},
                    ])}
                    for n, kcal in (("Colazione", 400), ("Pranzo", 700), ("Cena", 600))
                ]}
                for d in giorni
            ]
        }

    def pezzi(self):
        return [p for s, p in self.chiamate if s == prompts.WEEK_PLAN_SYSTEM]


@pytest.fixture()
def in_parallelo(monkeypatch, client):
    monkeypatch.setattr(planner, "PARALLEL_GENERATION", True)
    res = client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    assert res.status_code == 200


def _usa(monkeypatch, modello):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: modello)
    return modello


def _genera(client):
    week = client.get("/api/planning/weeks/current").json()
    return client.post(f"/api/planning/weeks/{week['id']}/generate")


def test_prima_il_piano_poi_i_pezzi_con_il_piano_dentro(client, diet, in_parallelo, monkeypatch):
    modello = _usa(monkeypatch, ModelloAPezzi())

    res = _genera(client)

    assert res.status_code == 200, res.text
    assert res.json()["generation"]["filled"] == DAYS * 3
    assert modello.chiamate[0][0] == prompts.WEEK_OUTLINE_SYSTEM
    pezzi = modello.pezzi()
    assert len(pezzi) == planner.MAX_PARALLEL
    # Ogni pezzo legge il piano di TUTTA la settimana, non solo dei suoi giorni.
    for p in pezzi:
        assert "Domenica / Cena: Cena 6 — zucchine 150 g" in p
        assert "Zucchine divise fra i giorni." in p
    # E i giorni da scrivere non si sovrappongono.
    giorni = [
        set(re.findall(r"day_of_week (\d)", p.split("DA GENERARE ORA", 1)[1].split("PASTI GIÀ", 1)[0]))
        for p in pezzi
    ]
    assert sum(len(g) for g in giorni) == DAYS
    assert set().union(*giorni) == {str(d) for d in range(DAYS)}


def test_senza_piano_si_torna_alla_chiamata_unica(client, diet, in_parallelo, monkeypatch):
    modello = ModelloAPezzi(piano_fallisce=True)

    def una_chiamata(system, prompt, **kwargs):
        if system == prompts.WEEK_OUTLINE_SYSTEM:
            return modello.generate_json(system, prompt, **kwargs)
        modello.chiamate.append((system, prompt))
        assert "DA GENERARE ORA" not in prompt
        from tests.test_flow import FakeModel
        return FakeModel(None).generate_json(system, prompt)

    finto = type("F", (), {"model": "x", "supports_native_pdf": False,
                           "generate_json": staticmethod(una_chiamata)})()
    _usa(monkeypatch, finto)

    res = _genera(client)

    assert res.status_code == 200, res.text
    assert res.json()["generation"]["filled"] == DAYS * 3


def test_un_pezzo_fallito_non_butta_gli_altri(client, diet, in_parallelo, monkeypatch):
    """Le ricette già scritte sono pagate: i pasti del pezzo fallito restano vuoti e si
    riempiono rigenerando i buchi."""
    _usa(monkeypatch, ModelloAPezzi(pezzo_che_fallisce=0))

    res = _genera(client)

    assert res.status_code == 200, res.text
    esito = res.json()["generation"]
    assert 0 < esito["filled"] < DAYS * 3
    assert esito["missing"] == DAYS * 3 - esito["filled"]


def test_poche_ricette_restano_in_una_chiamata():
    assert planner._split_days({0: ["a", "b"], 1: ["c"]}) == [[0, 1]]


def test_i_pezzi_sono_giorni_consecutivi_e_di_peso_simile():
    pezzi = planner._split_days({d: ["a", "b", "c"] for d in range(7)})
    assert [g for p in pezzi for g in p] == list(range(7))
    assert len(pezzi) == 4
    assert max(len(p) for p in pezzi) - min(len(p) for p in pezzi) <= 1


def test_il_diario_conta_le_ricette_di_tutti_i_pezzi():
    progress = planner.GenerationProgress(1, expected_recipes=4)
    piano = progress.channel(counts_recipes=False)
    a, b = progress.channel(), progress.channel()
    piano("content", '{"title": "solo nel piano"}')
    a("content", '{"title": "uno"}')
    b("content", '{"title": "due"}, {"title": "tre"}')
    assert progress.snapshot()["recipes_written"] == 3
