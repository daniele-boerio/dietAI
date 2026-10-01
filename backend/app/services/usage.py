"""Il registro delle chiamate al modello, e il conto per utente.

Ogni chiamata lascia una riga (`AIUsage`): token in entrata e in uscita e, quando si
sa, il costo. Il costo lo dichiara OpenRouter nella risposta; quando non lo fa (il
backend Anthropic, o un provider che non lo manda) si stima dal listino del catalogo
modelli, **se è già in memoria** — il registro non deve mai essere il motivo di una
richiesta di rete in più nel mezzo di una generazione.

Registrare non deve mai rompere niente: una generazione pagata non si perde per una
riga di registro che non si scrive.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session, sessionmaker

from ..models import AIUsage, User

logger = logging.getLogger(__name__)


def _cost_from_catalog(model: str, usage: dict) -> float | None:
    from . import catalog

    cached = catalog._cache[1] if catalog._cache else []
    entry = next((m for m in cached if m.get("id") == model), None)
    if not entry or entry.get("prompt_price") is None or entry.get("completion_price") is None:
        return None
    return round(
        usage.get("input_tokens", 0) / 1e6 * entry["prompt_price"]
        + usage.get("output_tokens", 0) / 1e6 * entry["completion_price"],
        6,
    )


def recorder(bind, user_id: int, role: str):
    """La funzione che il client chiama dopo ogni risposta. Sessione propria: quella
    di chi chiama può avere in mano mezza settimana non ancora committata."""
    factory = sessionmaker(bind=bind)

    def record(model: str, usage: dict) -> None:
        try:
            cost = usage.get("cost_usd")
            estimated = False
            if cost is None:
                cost = _cost_from_catalog(model, usage)
                estimated = cost is not None
            session = factory()
            try:
                session.add(
                    AIUsage(
                        user_id=user_id,
                        role=role,
                        model=model,
                        input_tokens=int(usage.get("input_tokens") or 0),
                        output_tokens=int(usage.get("output_tokens") or 0),
                        cost_usd=cost,
                        cost_estimated=estimated,
                    )
                )
                session.commit()
            finally:
                session.close()
        except Exception:  # noqa: BLE001 — vedi docstring del modulo
            logger.warning("Registro dell'uso AI non scritto", exc_info=True)

    return record


def summary(db: Session, days: int = 30) -> dict:
    """Chiamate, token e costo per utente negli ultimi `days` giorni."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(
            User.id,
            User.email,
            func.count(AIUsage.id),
            func.coalesce(func.sum(AIUsage.input_tokens), 0),
            func.coalesce(func.sum(AIUsage.output_tokens), 0),
            func.sum(AIUsage.cost_usd),
            func.sum(case((AIUsage.id.isnot(None) & AIUsage.cost_usd.is_(None), 1), else_=0)),
        )
        .outerjoin(AIUsage, (AIUsage.user_id == User.id) & (AIUsage.created_at >= since))
        .group_by(User.id, User.email)
        .order_by(User.id)
        .all()
    )
    users = [
        {
            "user_id": uid,
            "email": email,
            "calls": calls,
            "input_tokens": int(tin),
            "output_tokens": int(tout),
            "cost_usd": round(cost, 4) if cost is not None else None,
            # Chiamate di cui il costo non si sa: il totale le esclude, e va detto.
            "calls_without_cost": int(senza or 0),
        }
        for uid, email, calls, tin, tout, cost, senza in rows
    ]
    return {
        "days": days,
        "users": users,
        "total_cost_usd": round(sum(u["cost_usd"] or 0 for u in users), 4),
    }
