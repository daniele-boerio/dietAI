"""«Oggi» è uno solo: `planner.today()`, in ora italiana.

Il container gira in UTC: `date.today()` sparso nel codice faceva credere alla spesa e
all'andamento che fosse ancora ieri fra mezzanotte e le due, mentre il promemoria
usava già l'ora di Roma. E un `date.today()` diretto sfugge anche al lunedì fisso dei
test, che così cambiavano esito col giorno della settimana.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
VIETATI = re.compile(r"\b(date\.today|datetime\.today|datetime\.utcnow)\(|datetime\.now\(\)")


def test_nessuno_legge_la_data_del_container():
    colpevoli = []
    for path in APP.rglob("*.py"):
        if path.name == "clock.py":
            continue
        for n, riga in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            codice = riga.split("#", 1)[0]
            if VIETATI.search(codice) and "`" not in codice:
                colpevoli.append(f"{path.relative_to(APP)}:{n}: {riga.strip()}")
    assert not colpevoli, "Usa planner.today() o utils.clock:\n" + "\n".join(colpevoli)


def test_oggi_e_la_data_italiana(monkeypatch):
    from datetime import datetime

    from app.utils import clock

    # Le 23:30 UTC di domenica sono già lunedì a Roma.
    domenica_sera = datetime(2026, 10, 18, 23, 30, tzinfo=clock.ZoneInfo("UTC"))
    monkeypatch.setattr(clock, "now", lambda: domenica_sera.astimezone(clock.FUSO))
    assert clock.local_today().isoformat() == "2026-10-19"
