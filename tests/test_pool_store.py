"""Tests for app/pool_store.py"""
from __future__ import annotations

import json
import pytest

from app.pool_store import Pool, delete_pool, list_pools, load_pool, save_pool, validate_pool_name


# ---------------------------------------------------------------------------
# validate_pool_name
# ---------------------------------------------------------------------------

def test_valid_name_accepted():
    validate_pool_name("Ufficio tecnico")


def test_invalid_name_special_chars_raises():
    with pytest.raises(ValueError, match="Nome pool non valido"):
        validate_pool_name("Pool<>!")


def test_empty_name_raises():
    with pytest.raises(ValueError):
        validate_pool_name("")


# ---------------------------------------------------------------------------
# save / load
# ---------------------------------------------------------------------------

def test_save_and_load_pool(tmp_path):
    pool = Pool(name="test_pool", employee_ids=[1, 2, 3])
    save_pool(pool, tmp_path)
    loaded = load_pool("test_pool", tmp_path)
    assert loaded.name == "test_pool"
    assert loaded.employee_ids == [1, 2, 3]


def test_save_deduplicates_ids(tmp_path):
    pool = Pool(name="dup_pool", employee_ids=[5, 3, 5, 3, 7])
    save_pool(pool, tmp_path)
    loaded = load_pool("dup_pool", tmp_path)
    assert loaded.employee_ids == [5, 3, 7]


def test_load_missing_pool_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_pool("non_existent", tmp_path)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def test_list_pools_empty_dir(tmp_path):
    assert list_pools(tmp_path) == []


def test_list_pools_sorted(tmp_path):
    for name in ("Zeta", "Alpha", "Medio"):
        save_pool(Pool(name=name, employee_ids=[1]), tmp_path)
    assert list_pools(tmp_path) == ["Alpha", "Medio", "Zeta"]


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_delete_pool(tmp_path):
    save_pool(Pool(name="to_delete", employee_ids=[10]), tmp_path)
    delete_pool("to_delete", tmp_path)
    assert list_pools(tmp_path) == []


def test_delete_missing_pool_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        delete_pool("ghost", tmp_path)
