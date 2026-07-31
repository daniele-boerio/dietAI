"""La via di rientro quando il flag di amministratore manca.

Non è un caso di scuola: le rotte che rimetterebbero a posto il flag sono proprio
quelle riservate all'amministratore, quindi un database che nasce senza nessun admin
non si aggiusta dalla UI — è chiuso a chiave dall'interno.
"""

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
