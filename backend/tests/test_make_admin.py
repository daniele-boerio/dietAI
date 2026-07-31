"""La via di rientro quando il flag di amministratore manca.

Non è un caso di scuola: le rotte che rimetterebbero a posto il flag sono proprio
quelle riservate all'amministratore, quindi un database che nasce senza nessun admin
non si aggiusta dalla UI — è chiuso a chiave dall'interno.
"""

import sys

from app import make_admin as make_admin_cmd
from app import reset_password as reset_password_cmd
from app.make_admin import make_admin
from app.models import User
from app.seed import seed_user
from tests.conftest import GUEST_EMAIL, TEST_EMAIL


def test_promuove_l_unico_utente(client, db):
    user = db.query(User).filter(User.email == TEST_EMAIL).one()
    user.is_admin = False
    db.commit()

    assert client.get("/api/auth/me").json()["is_admin"] is False

    make_admin(db)

    # Nessun logout, nessun riavvio: il flag si legge a ogni richiesta.
    assert client.get("/api/auth/me").json()["is_admin"] is True
    assert client.get("/api/admin/users").status_code == 200


def test_con_piu_utenti_serve_dire_quale(client, guest_client, db):
    make_admin(db, GUEST_EMAIL)

    assert db.query(User).filter(User.email == GUEST_EMAIL).one().is_admin is True
    # E l'altro resta com'era.
    assert db.query(User).filter(User.email == TEST_EMAIL).one().is_admin is True


def test_rilanciarlo_non_fa_danni(client, db):
    make_admin(db)
    make_admin(db)
    assert db.query(User).filter(User.is_admin.is_(True)).count() == 1


def test_i_comandi_arrivano_in_fondo_senza_esplodere(client, db, monkeypatch):
    """La riga di riepilogo non deve leggere l'utente a sessione chiusa.

    Ci si è già passati: `main` chiudeva la sessione nel `finally` e poi stampava
    `user.email`, che dopo la commit è un attributo scaduto su un'istanza staccata —
    DetachedInstanceError sputato addosso a un comando **riuscito**. Il lavoro era
    fatto, ma il traceback diceva il contrario, che è il modo peggiore di sbagliare.
    Vale per tutti e due i comandi, perché il codice è lo stesso.
    """
    monkeypatch.setattr(make_admin_cmd, "SessionLocal", lambda: db)
    monkeypatch.setattr(reset_password_cmd, "SessionLocal", lambda: db)

    db.query(User).filter(User.email == TEST_EMAIL).one().is_admin = False
    db.commit()

    monkeypatch.setattr(sys, "argv", ["app.make_admin", "--email", TEST_EMAIL])
    assert make_admin_cmd.main() == 0

    monkeypatch.setattr(
        sys, "argv", ["app.reset_password", "password-nuova", "--email", TEST_EMAIL]
    )
    assert reset_password_cmd.main() == 0

    assert db.query(User).filter(User.email == TEST_EMAIL).one().is_admin is True


def test_il_seed_promuove_se_nessuno_e_amministratore(db, monkeypatch):
    """Il caso di un database creato prima dei due account: il seed lo rimette a posto.

    Gira a ogni avvio del container, quindi in produzione questo si risolve da sé al
    primo deploy — purché l'email sia quella di `SEED_USER_EMAIL`.
    """
    monkeypatch.setattr("app.seed.SEED_USER_EMAIL", TEST_EMAIL)
    db.add(User(email=TEST_EMAIL, password_hash="x", is_admin=False))
    db.commit()

    seed_user(db)

    assert db.query(User).filter(User.email == TEST_EMAIL).one().is_admin is True
