"""Un giro alla volta, anche con più processi.

I giri ogni minuto (promemoria, healthAI) sono thread del processo: con un solo
uvicorn ce n'è uno per tipo, con `--workers 2` o due repliche su Coolify partirebbero
in due — promemoria doppi, pasti mandati due volte a healthAI, e le stime di
composizione (a pagamento) chieste da entrambi. L'advisory lock di Postgres li mette
in fila: chi non lo prende salta il giro, il minuto dopo ci riprova. Su SQLite (i
test) non c'è altro processo, e il giro parte sempre.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Una chiave per giro: numeri fissi, scelti una volta. Non devono cambiare fra un
# deploy e l'altro, o due versioni in rolling update non si vedrebbero.
PROMEMORIA = 7_301_001
HEALTHAI = 7_301_002


@contextmanager
def giro_unico(bind: Engine, chiave: int) -> Iterator[bool]:
    """`with giro_unico(engine, CHIAVE) as mio:` — `mio` è False se un altro lo fa.

    Su una connessione **sua**, tenuta per tutto il giro: l'advisory lock appartiene
    alla connessione, e quella di una `Session` torna nel pool a ogni commit — lo
    sblocco sarebbe finito su un'altra connessione, e il lock sarebbe rimasto preso.
    """
    if bind.dialect.name != "postgresql":
        yield True
        return
    with bind.connect() as conn:
        preso = bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": chiave}).scalar())
        conn.commit()
        try:
            yield preso
        finally:
            if preso:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": chiave})
                conn.commit()
