"""Tests for app/stats_service.py (pure functions only — no Odoo, no I/O)."""
from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from app.stats_service import (
    default_output_path,
    parse_date,
    parse_time,
    resolve_pool_from_ids,
    validate_params,
)


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------

def test_parse_date_valid():
    assert parse_date("2024-03-15") == date(2024, 3, 15)


def test_parse_date_invalid_raises():
    with pytest.raises(ValueError, match="Formato data non valido"):
        parse_date("15/03/2024")


def test_parse_date_garbage_raises():
    with pytest.raises(ValueError):
        parse_date("not-a-date")


# ---------------------------------------------------------------------------
# parse_time
# ---------------------------------------------------------------------------

def test_parse_time_valid():
    assert parse_time("08:30") == time(8, 30)


def test_parse_time_invalid_raises():
    with pytest.raises(ValueError, match="Formato orario non valido"):
        parse_time("8:60")


def test_parse_time_missing_colon_raises():
    with pytest.raises(ValueError):
        parse_time("0800")


# ---------------------------------------------------------------------------
# validate_params
# ---------------------------------------------------------------------------

def test_validate_params_ok():
    validate_params(date(2024, 1, 1), date(2024, 12, 31), time(8, 0), time(9, 0), 10)


def test_validate_params_from_after_to_raises():
    with pytest.raises(ValueError):
        validate_params(date(2024, 12, 31), date(2024, 1, 1), time(8, 0), time(9, 0), 10)


def test_validate_params_start_after_end_raises():
    with pytest.raises(ValueError):
        validate_params(date(2024, 1, 1), date(2024, 12, 31), time(9, 0), time(8, 0), 10)


def test_validate_params_bucket_exceeds_window_raises():
    with pytest.raises(ValueError):
        validate_params(date(2024, 1, 1), date(2024, 12, 31), time(8, 0), time(8, 15), 30)


def test_validate_params_zero_bucket_raises():
    with pytest.raises(ValueError):
        validate_params(date(2024, 1, 1), date(2024, 12, 31), time(8, 0), time(9, 0), 0)


# ---------------------------------------------------------------------------
# resolve_pool_from_ids
# ---------------------------------------------------------------------------

def test_resolve_all_active():
    active = {1: "Alice", 2: "Bob", 3: "Carlo"}
    pool, missing = resolve_pool_from_ids([1, 3], active)
    assert pool == [(1, "Alice"), (3, "Carlo")]
    assert missing == []


def test_resolve_some_missing():
    active = {1: "Alice", 3: "Carlo"}
    pool, missing = resolve_pool_from_ids([1, 2, 3], active)
    assert pool == [(1, "Alice"), (3, "Carlo")]
    assert missing == [2]


def test_resolve_empty_ids():
    pool, missing = resolve_pool_from_ids([], {1: "Alice"})
    assert pool == []
    assert missing == []


# ---------------------------------------------------------------------------
# default_output_path
# ---------------------------------------------------------------------------

def test_default_output_path():
    p = default_output_path(date(2024, 1, 1), date(2024, 12, 31))
    assert p == Path("reports") / "statistiche_ingressi_2024-01-01_2024-12-31.xlsx"
