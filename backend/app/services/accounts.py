"""Gli account dell'app: chi è l'amministratore, e come nasce un utente nuovo.

L'app è nata per una persona sola e per la maggior parte lo è rimasta: ogni tabella di
dati personali porta `user_id` e ogni query lo filtra, quindi due utenti non si vedono
tra loro. Quello che **non** si duplica è la API key: la mette l'amministratore, e chi
non lo è genera con la sua. Da qui discende il resto — l'admin è l'unico che vede la
schermata della chiave e sceglie i modelli, perché è l'unico che ne paga il conto.

L'anagrafica ingredienti (`Ingredient`) resta invece comune a tutti: è un dizionario di
nomi, reparti e prezzi al kg, non un dato personale. Se un utente corregge il prezzo
del pane, il prezzo del pane è corretto per tutti.
"""

from sqlalchemy.orm import Session

from ..auth import get_password_hash
from ..models import BaseIngredient, Ingredient, User, UserPreferences
from ..utils.pricing import DEFAULT_BASE_INGREDIENTS


def admin_user(db: Session) -> User | None:
    """L'amministratore: chi possiede la API key e sceglie i modelli.

    Se per qualche ragione ce ne fosse più d'uno vince il più vecchio — è quello che
    ha creato gli altri.
    """
    return (
        db.query(User)
        .filter(User.is_admin.is_(True))
        .order_by(User.id)
        .first()
    )


def create_user(
    db: Session, email: str, password: str, *, is_admin: bool = False
) -> User:
    """Crea un account già utilizzabile: preferenze e ingredienti di base compresi.

    Le preferenze devono esistere subito perché ci vivono i modelli AI e le regole
    libere, e l'onboarding le legge prima ancora che l'utente le tocchi. Gli
    ingredienti di base (sale, olio, pepe) sono un regalo: nessuno li vuole in lista
    della spesa, e chiederli a uno a uno al primo accesso è un compito inutile.
    """
    user = User(
        email=email.lower().strip(),
        password_hash=get_password_hash(password),
        is_admin=is_admin,
    )
    db.add(user)
    db.flush()

    db.add(UserPreferences(user_id=user.id, prefer_seasonal=True, prefer_italian=True))

    for name in DEFAULT_BASE_INGREDIENTS:
        ingredient = db.query(Ingredient).filter(Ingredient.name == name).first()
        if ingredient:
            db.add(BaseIngredient(user_id=user.id, ingredient_id=ingredient.id))

    return user
