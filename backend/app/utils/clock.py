"""Che ore sono, per l'app: l'ora italiana, non quella del container.

Il container gira in UTC e non ha `TZ`. Il promemoria e healthAI usavano già l'ora di
Roma, il resto `date.today()`: fra mezzanotte e le due di notte, per la spesa, gli
stati della settimana e l'andamento era ancora ieri, mentre per il promemoria era già
oggi. Gli utenti sono in Italia, e «oggi» è il loro.

Il punto da cui il resto dell'app legge la data resta `planner.today()`, che i test
fissano a lunedì: questo modulo dice soltanto in che fuso.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("Europe/Rome")


def now() -> datetime:
    return datetime.now(FUSO)


def local_today() -> date:
    return now().date()
