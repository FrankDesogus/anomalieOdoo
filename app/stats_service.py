"""
Service layer for arrival-stats: validation, pool resolution, and full pipeline.
Used by both the CLI (main.py) and the GUI (arrival_stats_gui.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from .odoo_client import OdooClient
from .stats_builder import (
    ArrivalRecord,
    MonthlyStats,
    PeriodStats,
    build_arrival_records,
    compute_monthly_stats,
    compute_period_stats,
)
from .stats_report import export_stats_excel


# ---------------------------------------------------------------------------
# Validation helpers  (pure functions — no Odoo, no I/O)
# ---------------------------------------------------------------------------

def parse_date(value: str) -> date:
    """Parse 'YYYY-MM-DD' string; raise ValueError with a clear message on failure."""
    try:
        return date.fromisoformat(value.strip())
    except (ValueError, AttributeError):
        raise ValueError(f"Formato data non valido '{value}': atteso YYYY-MM-DD")


def parse_time(value: str) -> time:
    """Parse 'HH:MM' string; raise ValueError with a clear message on failure."""
    try:
        parts = value.strip().split(":")
        if len(parts) != 2:
            raise ValueError()
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        raise ValueError(f"Formato orario non valido '{value}': atteso HH:MM")


def validate_params(
    from_day: date,
    to_day: date,
    arrival_start: time,
    arrival_end: time,
    bucket_minutes: int,
) -> None:
    """Raise ValueError if any parameter combination is invalid."""
    if from_day > to_day:
        raise ValueError(f"Data iniziale {from_day} deve essere <= data finale {to_day}")
    if arrival_start > arrival_end:
        raise ValueError(
            f"Orario inizio {arrival_start.strftime('%H:%M')} deve essere"
            f" <= orario fine {arrival_end.strftime('%H:%M')}"
        )
    window_minutes = (
        (arrival_end.hour * 60 + arrival_end.minute)
        - (arrival_start.hour * 60 + arrival_start.minute)
    )
    if window_minutes <= 0:
        raise ValueError("La finestra oraria deve avere ampiezza positiva")
    if bucket_minutes <= 0:
        raise ValueError("L'ampiezza delle fasce deve essere > 0")
    if bucket_minutes > window_minutes:
        raise ValueError(
            f"Ampiezza fasce {bucket_minutes} min supera la finestra oraria ({window_minutes} min)"
        )


def resolve_pool_from_ids(
    ids: List[int],
    active: Dict[int, str],
) -> Tuple[List[Tuple[int, str]], List[int]]:
    """
    Filter requested IDs against the active employees dict.
    Returns (pool, missing_ids).  Does NOT raise — caller decides.
    """
    pool = [(i, active[i]) for i in ids if i in active]
    missing = [i for i in ids if i not in active]
    return pool, missing


def default_output_path(from_day: date, to_day: date) -> Path:
    return Path("reports") / f"statistiche_ingressi_{from_day}_{to_day}.xlsx"


# ---------------------------------------------------------------------------
# Full pipeline dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ArrivalStatsParams:
    from_day: date
    to_day: date
    arrival_start: time
    arrival_end: time
    bucket_minutes: int
    employee_pool: List[Tuple[int, str]]
    output_path: Path


@dataclass
class ArrivalStatsResult:
    period_stats: PeriodStats
    monthly_stats: List[MonthlyStats]
    records: List[ArrivalRecord]
    output_path: Path


# ---------------------------------------------------------------------------
# Internal: UTC range helper (avoids importing from main.py)
# ---------------------------------------------------------------------------

def _day_range_utc(day: date, tz: ZoneInfo) -> Tuple[str, str]:
    fmt = "%Y-%m-%d %H:%M:%S"
    start_local = datetime.combine(day, time(0, 0)).replace(tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end_utc = end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return start_utc.strftime(fmt), end_utc.strftime(fmt)


# ---------------------------------------------------------------------------
# Step-by-step pipeline (used by GUI for progress reporting)
# ---------------------------------------------------------------------------

def fetch_sessions(
    client: OdooClient,
    from_day: date,
    to_day: date,
    tz_name: str,
):
    """Fetch all attendance sessions for the period in a single Odoo query."""
    tz = ZoneInfo(tz_name)
    start_utc, _ = _day_range_utc(from_day, tz)
    _, end_utc = _day_range_utc(to_day, tz)
    return client.fetch_sessions_for_day(start_utc, end_utc)


def run_pipeline(
    sessions,
    params: ArrivalStatsParams,
) -> ArrivalStatsResult:
    """Pure computation pipeline: no Odoo calls, no I/O except writing Excel."""
    if not params.employee_pool:
        raise ValueError(
            "Il pool dipendenti e' vuoto. Selezionare almeno un dipendente."
        )
    records = build_arrival_records(
        sessions, params.employee_pool, params.arrival_start, params.arrival_end
    )
    period_stats = compute_period_stats(
        records, params.employee_pool,
        params.from_day, params.to_day,
        params.arrival_start, params.arrival_end,
        params.bucket_minutes,
    )
    monthly_stats = compute_monthly_stats(
        records, params.arrival_start, params.arrival_end, params.bucket_minutes
    )
    output = export_stats_excel(
        period_stats, monthly_stats, records, params.employee_pool, params.output_path
    )
    return ArrivalStatsResult(
        period_stats=period_stats,
        monthly_stats=monthly_stats,
        records=records,
        output_path=output,
    )


# ---------------------------------------------------------------------------
# CLI convenience wrapper (creates its own client)
# ---------------------------------------------------------------------------

def run(params: ArrivalStatsParams, cfg: dict) -> ArrivalStatsResult:
    """End-to-end pipeline: connect to Odoo, fetch, compute, write Excel."""
    o = cfg["odoo"]
    client = OdooClient(o["url"], o["db"], o["user"], o["password"], cfg["timezone"])
    sessions = fetch_sessions(client, params.from_day, params.to_day, cfg["timezone"])
    return run_pipeline(sessions, params)
