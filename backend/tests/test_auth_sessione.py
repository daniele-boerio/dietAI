"""La sessione: refresh con rotazione, riuso, logout, cookie.

Il refresh concorrente è il caso che buttava fuori l'utente: scaduto l'access token,
le richieste parallele di una pagina presentano tutte lo stesso cookie, e il server
prendeva la seconda per un furto e revocava la sessione.
"""

from datetime import datetime, timedelta, timezone

from app.auth import REFRESH_COOKIE_NAME
from app.models import RefreshToken, User

from tests.conftest import TEST_EMAIL, TEST_PASSWORD


def _refresh_con(client, raw):
    # Solo quel cookie: il jar ne terrebbe due omonimi con domini diversi.
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE_NAME, raw)
    return client.post("/api/auth/refresh")


def _cookie(client):
    return client.cookies.get(REFRESH_COOKIE_NAME)


def test_il_refresh_ruota_il_token(client):
    vecchio = _cookie(client)
    res = client.post("/api/auth/refresh")
    assert res.status_code == 200
    assert _cookie(client) != vecchio
    assert client.get("/api/auth/me").status_code == 200


def test_due_refresh_insieme_non_chiudono_la_sessione(client):
    vecchio = _cookie(client)
    primo = _refresh_con(client, vecchio)
    assert primo.status_code == 200
    nuovo = primo.cookies[REFRESH_COOKIE_NAME]

    # La seconda richiesta parallela arriva col cookie di prima: niente token nuovi,
    # ma nemmeno la revoca.
    res = _refresh_con(client, vecchio)
    assert res.status_code == 200
    assert REFRESH_COOKIE_NAME not in res.cookies

    assert _refresh_con(client, nuovo).status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_un_riuso_tardivo_revoca_la_famiglia(client, db):
    vecchio = _cookie(client)
    primo = _refresh_con(client, vecchio)
    assert primo.status_code == 200
    nuovo = primo.cookies[REFRESH_COOKIE_NAME]

    # Il token di prima è stato ruotato un'ora fa: chi lo presenta ora l'ha copiato.
    db.query(RefreshToken).filter(RefreshToken.used_at.isnot(None)).update(
        {"used_at": datetime.now(timezone.utc) - timedelta(hours=1)}
    )
    db.commit()

    assert _refresh_con(client, vecchio).status_code == 401
    # Insieme al ladro esce anche la vittima: non si sa chi dei due fosse.
    assert _refresh_con(client, nuovo).status_code == 401


def test_dopo_il_logout_la_sessione_non_si_rinnova(client):
    vecchio = _cookie(client)
    assert client.post("/api/auth/logout").status_code in (200, 204)
    assert client.get("/api/auth/me").status_code == 401
    assert _refresh_con(client, vecchio).status_code == 401


def test_un_account_spento_non_rinnova_la_sessione(client, db):
    utente = db.query(User).filter(User.email == TEST_EMAIL).one()
    utente.is_active = False
    db.commit()

    assert client.post("/api/auth/refresh").status_code == 401


def test_i_cookie_di_sessione_sono_httponly(client):
    res = client.post(
        "/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    intestazioni = res.headers.get_list("set-cookie")
    assert len(intestazioni) == 2
    for riga in intestazioni:
        assert "HttpOnly" in riga
        assert "samesite=lax" in riga.lower()


def test_una_scrittura_da_un_altro_sito_si_rifiuta(client):
    res = client.post("/api/auth/logout", headers={"Sec-Fetch-Site": "same-site"})
    assert res.status_code == 403
    assert client.get("/api/auth/me").status_code == 200  # la sessione è intatta
    # Dalla stessa origine, e dai client che non lo dicono, si passa.
    assert client.post("/api/auth/refresh", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
