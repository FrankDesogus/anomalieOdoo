"""
Pool storage: save/load/list/delete employee pools as JSON files.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

_VALID_NAME_RE = re.compile(r"^[\w\s\-]{1,64}$", re.UNICODE)


@dataclass
class Pool:
    name: str
    employee_ids: List[int]


def _pool_path(name: str, pools_dir: Path) -> Path:
    return pools_dir / f"{name}.json"


def validate_pool_name(name: str) -> None:
    if not name or not name.strip():
        raise ValueError("Il nome del pool non puo' essere vuoto")
    if not _VALID_NAME_RE.match(name):
        raise ValueError(
            f"Nome pool non valido '{name}': usare solo lettere, numeri, spazi, trattini e underscore (max 64 caratteri)"
        )


def save_pool(pool: Pool, pools_dir: Path) -> Path:
    validate_pool_name(pool.name)
    pools_dir.mkdir(parents=True, exist_ok=True)
    # Deduplicate preserving order
    seen = set()
    unique_ids = []
    for i in pool.employee_ids:
        if i not in seen:
            seen.add(i)
            unique_ids.append(i)
    data = {"name": pool.name, "employee_ids": unique_ids}
    path = _pool_path(pool.name, pools_dir)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_pool(name: str, pools_dir: Path) -> Pool:
    path = _pool_path(name, pools_dir)
    if not path.exists():
        raise FileNotFoundError(f"Pool '{name}' non trovato in {pools_dir}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Pool(name=data["name"], employee_ids=data["employee_ids"])


def list_pools(pools_dir: Path) -> List[str]:
    if not pools_dir.exists():
        return []
    return sorted(p.stem for p in pools_dir.glob("*.json"))


def delete_pool(name: str, pools_dir: Path) -> None:
    path = _pool_path(name, pools_dir)
    if not path.exists():
        raise FileNotFoundError(f"Pool '{name}' non trovato")
    path.unlink()
