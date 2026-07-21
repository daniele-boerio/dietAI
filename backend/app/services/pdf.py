"""Estrazione del testo dal PDF della dieta.

Perché non mandare sempre il PDF al modello: quasi tutte le diete sono PDF generati
da un gestionale, quindi contengono già il testo. Estrarlo qui è gratis, istantaneo,
deterministico — e soprattutto rende la lettura della dieta indipendente dal modello:
funziona anche con un modello che non ha la vista.

Resta il caso della dieta fotografata o scansionata: lì di testo non ce n'è, e serve
un modello che guardi la pagina. Quel caso lo riconosciamo e lo diciamo chiaramente,
invece di mandare al modello una stringa vuota e farci restituire ricette inventate.
"""

import io
import logging
import re

logger = logging.getLogger(__name__)

# Sotto questa soglia il PDF è quasi certamente una scansione: un piano alimentare
# vero, anche di una sola pagina, di caratteri ne ha molti di più.
MIN_USEFUL_CHARS = 200


def extract_text(content: bytes) -> str:
    """Testo del PDF, pagina per pagina. Stringa vuota se non se ne cava nulla."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # pypdf solleva di tutto sui file malformati
        logger.warning("PDF illeggibile: %s", exc)
        return ""

    text = "\n\n".join(p.strip() for p in pages if p.strip())
    # I PDF impaginati a colonne producono cascate di spazi e righe vuote: ripulirle
    # riduce i token da pagare e non toglie informazione.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def looks_scanned(text: str) -> bool:
    return len(text) < MIN_USEFUL_CHARS
