"""Cifratura della API key di Claude e robustezza della chiave letta dall'ambiente."""

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app import crypto
from app.config import _clean

API_KEY = "sk-ant-api03-esempio-di-chiave"


def test_cifra_e_decifra(monkeypatch):
    monkeypatch.setattr(crypto, "ENCRYPTION_KEY", Fernet.generate_key().decode())
    token = crypto.encrypt_api_key(API_KEY)

    assert API_KEY not in token  # in DB non deve finirci nulla di leggibile
    assert crypto.decrypt_api_key(token) == API_KEY


def test_chiave_cambiata_non_decifra(monkeypatch):
    monkeypatch.setattr(crypto, "ENCRYPTION_KEY", Fernet.generate_key().decode())
    token = crypto.encrypt_api_key(API_KEY)

    monkeypatch.setattr(crypto, "ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(HTTPException) as exc:
        crypto.decrypt_api_key(token)
    assert "Reinseriscila" in exc.value.detail


def test_chiave_assente(monkeypatch):
    monkeypatch.setattr(crypto, "ENCRYPTION_KEY", "")
    with pytest.raises(HTTPException) as exc:
        crypto.encrypt_api_key(API_KEY)
    assert "non configurata" in exc.value.detail


def test_chiave_malformata_dice_quanto_e_lunga(monkeypatch):
    monkeypatch.setattr(crypto, "ENCRYPTION_KEY", "troppo-corta")
    with pytest.raises(HTTPException) as exc:
        crypto.encrypt_api_key(API_KEY)
    assert "letti 12 caratteri" in exc.value.detail
    assert "44" in exc.value.detail


@pytest.mark.parametrize("wrapper", ['"{}"', "'{}'", " {} ", "{}\n", '  "{}"  '])
def test_virgolette_e_spazi_del_copia_incolla_vengono_tolti(wrapper):
    """Un valore incollato in un pannello web arriva spesso con questa roba attorno."""
    key = Fernet.generate_key().decode()
    assert _clean(wrapper.format(key)) == key
