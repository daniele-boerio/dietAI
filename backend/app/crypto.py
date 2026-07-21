"""Cifratura della API key Claude dell'utente.

La chiave sta nel DB, non nel `.env`: la inserisce l'utente dalla UI. In chiaro un
dump del database la regalerebbe, quindi in colonna finisce solo il ciphertext
Fernet. La chiave di cifratura (`ENCRYPTION_KEY`) vive nell'ambiente: chi ha solo
il database non può decifrare nulla.
"""

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from .config import ENCRYPTION_KEY


def _fernet() -> Fernet:
    if not ENCRYPTION_KEY:
        raise HTTPException(
            503,
            "ENCRYPTION_KEY non configurata: impossibile gestire la API key di Claude.",
        )
    try:
        return Fernet(ENCRYPTION_KEY.encode())
    except (ValueError, TypeError):
        # Il messaggio dice quanto è lunga la chiave letta: quasi sempre il problema
        # è il copia-incolla (virgolette rimaste, "=" finale perso, chiave troncata)
        # e la lunghezza lo rivela subito, senza dover stampare il segreto.
        raise HTTPException(
            503,
            f"ENCRYPTION_KEY non valida: letti {len(ENCRYPTION_KEY)} caratteri, "
            "ne servono 44 (chiave Fernet urlsafe-base64 da 32 byte, "
            "generata con Fernet.generate_key(), '=' finale compreso).",
        )


def encrypt_api_key(api_key: str) -> str:
    return _fernet().encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted: str) -> str:
    try:
        return _fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        # Succede se ENCRYPTION_KEY è stata cambiata dopo il salvataggio: il valore
        # in DB non è più decifrabile e l'utente deve reinserire la chiave.
        raise HTTPException(
            400, "API key non decifrabile. Reinseriscila nelle impostazioni."
        )
