"""
Helpers for building and managing report file paths.
Usato sia dalla GUI Qt che dalla CLI.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path


def sanitize_filename_component(value: str) -> str:
    """
    Converte un nome arbitrario in un componente sicuro per nomi file Windows.

    Examples:
        "Meccanica"             -> "meccanica"
        "Ufficio Tecnico"       -> "ufficio_tecnico"
        "Qualita' / Collaudo"   -> "qualita_collaudo"
        "Pool: Amministrazione" -> "pool_amministrazione"
    """
    # Decomposizione NFD: separa lettera base dal segno diacritico
    nfd = unicodedata.normalize("NFD", value)
    # Rimuovi i caratteri combining (accenti, dieresi, ecc.)
    ascii_approx = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    # Minuscolo
    lowered = ascii_approx.lower()
    # Caratteri vietati su Windows (\ / : * ? " < > |) + spazi → underscore
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", lowered)
    # Qualunque altro carattere non alfanumerico/underscore → underscore
    cleaned = re.sub(r"[^\w]", "_", cleaned)
    # Collassa underscore consecutivi
    cleaned = re.sub(r"_+", "_", cleaned)
    # Rimuovi underscore iniziali e finali
    cleaned = cleaned.strip("_")
    return cleaned or "selezione_manuale"


def build_default_report_filename(
    pool_name: str | None,
    from_day: date,
    to_day: date,
) -> str:
    """
    Costruisce il nome file suggerito per il report.

    Se pool_name è None o stringa vuota usa il fallback 'selezione_manuale'.
    """
    if pool_name and pool_name.strip():
        pool_part = sanitize_filename_component(pool_name)
    else:
        pool_part = "selezione_manuale"
    return f"statistiche_ingressi_{pool_part}_{from_day}_{to_day}.xlsx"


def next_available_path(path: Path) -> Path:
    """
    Ritorna path invariato se non esiste.
    Altrimenti trova il primo percorso disponibile con suffisso _02, _03, …

    Esempio:
        stats.xlsx       (esiste) -> stats_02.xlsx
        stats_02.xlsx    (esiste) -> stats_03.xlsx
    """
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter:02d}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
