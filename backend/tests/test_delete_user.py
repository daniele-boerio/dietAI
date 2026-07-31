"""La cancellazione di un account dal container.

Esiste per il caso che il pannello Utenti si rifiuta di fare — un **altro**
amministratore — e per questo ha tre rifiuti suoi: l'ultimo account, l'ultimo
amministratore e l'utente del seed, che tornerebbe da solo al riavvio successivo.
"""

import sys

import pytest

from app import delete_user as cmd
from app.delete_user import delete_user, inventory, pick_target
from app.models import Recipe, User
from tests.conftest import GUEST_EMAIL, TEST_EMAIL


def _user(db, email) -> User:
    return db.query(User).filter(User.email == email).one()


def test_cancella_l_account_e_i_suoi_dati(client, guest_client, db):
    guest_client.post(
        "/api/recipes",
        json={
            "title": "Insalata di riso",
            "instructions": "Mescola.",
            "calories": 500,
            "protein_g": 12,
            "carbs_g": 70,
            "fat_g": 15,
            "ingredients": [{"name": "riso", "quantity": 80, "unit": "g"}],
        },
    )
    ospite_id = _user(db, GUEST_EMAIL).id

    assert delete_user(db, GUEST_EMAIL) == GUEST_EMAIL

    assert db.query(User).filter(User.email == GUEST_EMAIL).first() is None
    assert db.query(Recipe).filter(Recipe.user_id == ospite_id).count() == 0


def test_anche_un_amministratore_purche_non_sia_l_ultimo(client, guest_client, db):
    """È il motivo per cui questo comando esiste: dal pannello non si può."""
    ospite = _user(db, GUEST_EMAIL)
    ospite.is_admin = True
    db.commit()

    delete_user(db, GUEST_EMAIL)

    assert db.query(User).filter(User.is_admin.is_(True)).count() == 1


def test_l_ultimo_amministratore_no(client, guest_client, db):
    with pytest.raises(ValueError, match="unico amministratore"):
        delete_user(db, TEST_EMAIL)


def test_l_unico_account_no(client, db):
    with pytest.raises(ValueError, match="unico account"):
        delete_user(db, TEST_EMAIL)


def test_l_utente_del_seed_torna_al_riavvio_quindi_serve_insistere(
    client, guest_client, db, monkeypatch
):
    monkeypatch.setattr(cmd, "SEED_USER_EMAIL", GUEST_EMAIL)

    with pytest.raises(ValueError, match="SEED_USER_EMAIL"):
        delete_user(db, GUEST_EMAIL)

    # Chi lo sa, lo fa lo stesso.
    assert delete_user(db, GUEST_EMAIL, force_seed=True) == GUEST_EMAIL


def test_un_indirizzo_che_non_esiste_dice_quali_ci_sono(client, guest_client, db):
    with pytest.raises(ValueError, match=GUEST_EMAIL):
        pick_target(db, "nessuno@dietai.local")


def test_senza_yes_non_cancella_niente(client, guest_client, db, monkeypatch):
    """La prima esecuzione è un preventivo: dice cosa sparirebbe e si ferma."""
    monkeypatch.setattr(cmd, "SessionLocal", lambda: db)
    monkeypatch.setattr(sys, "argv", ["app.delete_user", "--email", GUEST_EMAIL])

    assert cmd.main() == 0
    assert db.query(User).filter(User.email == GUEST_EMAIL).first() is not None

    monkeypatch.setattr(
        sys, "argv", ["app.delete_user", "--email", GUEST_EMAIL, "--yes"]
    )
    assert cmd.main() == 0
    assert db.query(User).filter(User.email == GUEST_EMAIL).first() is None


def test_l_inventario_conta_quello_che_sparisce(client, guest_client, db, diet):
    ospite = _user(db, GUEST_EMAIL)
    guest_client.post(
        "/api/diet/manual",
        json={"meals": [{"name": "Pranzo", "order": 0, "calories": 700,
                         "protein_g": 40, "carbs_g": 80, "fat_g": 20}]},
    )

    conti = inventory(db, ospite)

    assert conti["diete"] == 1
    assert conti["sessioni aperte"] >= 1
    # `diet` è dell'amministratore: non deve entrare nel conto dell'ospite.
    assert inventory(db, _user(db, TEST_EMAIL))["diete"] == 1
