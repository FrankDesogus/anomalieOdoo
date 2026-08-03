"""
Unit tests for app.stats_builder.

Run with:
    pytest tests/test_stats_builder.py -v
"""
import statistics
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.models import AttendanceSession
from app.stats_builder import (
    ArrivalRecord,
    _assign_to_bucket,
    _build_buckets,
    _time_to_minutes,
    build_arrival_records,
    compute_monthly_stats,
    compute_period_stats,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

TZ = ZoneInfo("Europe/Rome")
DEFAULT_START = time(8, 0)
DEFAULT_END = time(9, 0)
BUCKET_MIN = 10

# A stable Monday for all single-day tests
DAY = date(2026, 1, 5)

POOL_ONE = [(1, "Mario Rossi")]
POOL_TWO = [(1, "Mario Rossi"), (2, "Anna Bianchi")]


def make_session(
    emp_id: int,
    day: date,
    h_in: int,
    m_in: int,
    h_out: int = 18,
    m_out: int = 0,
    emp_name: str = "Test User",
) -> AttendanceSession:
    check_in = datetime(day.year, day.month, day.day, h_in, m_in, 0, tzinfo=TZ)
    check_out = datetime(day.year, day.month, day.day, h_out, m_out, 0, tzinfo=TZ)
    return AttendanceSession(
        employee_id=emp_id,
        employee_name=emp_name,
        check_in=check_in,
        check_out=check_out,
    )


def records_for(sessions, pool=None, start=DEFAULT_START, end=DEFAULT_END):
    if pool is None:
        pool = POOL_ONE
    return build_arrival_records(sessions, pool, start, end)


# ---------------------------------------------------------------------------
# 1. 08:00 incluso
# ---------------------------------------------------------------------------

def test_0800_included():
    s = make_session(1, DAY, 8, 0)
    recs = records_for([s])
    assert len(recs) == 1
    assert recs[0].included is True
    assert recs[0].exclusion_reason == "VALID"


# ---------------------------------------------------------------------------
# 2. 09:00 incluso
# ---------------------------------------------------------------------------

def test_0900_included():
    s = make_session(1, DAY, 9, 0)
    recs = records_for([s])
    assert recs[0].included is True
    assert recs[0].exclusion_reason == "VALID"


# ---------------------------------------------------------------------------
# 3. 07:59 escluso
# ---------------------------------------------------------------------------

def test_0759_excluded():
    s = make_session(1, DAY, 7, 59)
    recs = records_for([s])
    assert recs[0].included is False
    assert recs[0].exclusion_reason == "BEFORE_TIME_WINDOW"


# ---------------------------------------------------------------------------
# 4. 09:01 escluso
# ---------------------------------------------------------------------------

def test_0901_excluded():
    s = make_session(1, DAY, 9, 1)
    recs = records_for([s])
    assert recs[0].included is False
    assert recs[0].exclusion_reason == "AFTER_TIME_WINDOW"


# ---------------------------------------------------------------------------
# 5. Prima timbratura 07:50, seconda 08:20 → escluso (conta solo 07:50)
# ---------------------------------------------------------------------------

def test_first_checkin_0750_second_0820_excluded():
    s1 = make_session(1, DAY, 7, 50, h_out=12, m_out=0)
    s2 = make_session(1, DAY, 8, 20, h_out=18, m_out=0)
    recs = records_for([s1, s2])
    assert len(recs) == 1
    assert recs[0].included is False
    assert recs[0].exclusion_reason == "BEFORE_TIME_WINDOW"
    assert recs[0].first_checkin.hour == 7
    assert recs[0].first_checkin.minute == 50


# ---------------------------------------------------------------------------
# 6. Prima timbratura 08:18, sessioni successive → incluso con 08:18
# ---------------------------------------------------------------------------

def test_first_checkin_0818_with_later_sessions():
    s1 = make_session(1, DAY, 8, 18, h_out=12, m_out=0)
    s2 = make_session(1, DAY, 12, 45, h_out=13, m_out=35)
    s3 = make_session(1, DAY, 13, 35, h_out=18, m_out=0)
    recs = records_for([s1, s2, s3])
    assert len(recs) == 1
    assert recs[0].included is True
    assert recs[0].first_checkin.hour == 8
    assert recs[0].first_checkin.minute == 18


# ---------------------------------------------------------------------------
# 7. Media corretta
# ---------------------------------------------------------------------------

def test_mean_correct():
    # 08:00 → 480 min, 08:30 → 510 min → media 495 min = 08:15
    s1 = make_session(1, date(2026, 1, 5), 8, 0)
    s2 = make_session(1, date(2026, 1, 6), 8, 30)
    pool = [(1, "Mario Rossi")]
    recs = build_arrival_records([s1, s2], pool, DEFAULT_START, DEFAULT_END)
    pstats = compute_period_stats(recs, pool, date(2026, 1, 5), date(2026, 1, 6),
                                   DEFAULT_START, DEFAULT_END, BUCKET_MIN)
    assert pstats.mean_dt == time(8, 15)
    assert pstats.valid_count == 2


# ---------------------------------------------------------------------------
# 8. Mediana corretta
# ---------------------------------------------------------------------------

def test_median_correct():
    # tre valori: 08:00, 08:10, 08:20 → mediana 08:10
    days = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    hours = [(8, 0), (8, 10), (8, 20)]
    sessions = [make_session(1, d, hh, mm) for d, (hh, mm) in zip(days, hours)]
    pool = [(1, "Mario Rossi")]
    recs = build_arrival_records(sessions, pool, DEFAULT_START, DEFAULT_END)
    pstats = compute_period_stats(recs, pool, days[0], days[-1],
                                   DEFAULT_START, DEFAULT_END, BUCKET_MIN)
    assert pstats.median_dt == time(8, 10)


# ---------------------------------------------------------------------------
# 9. Deviazione standard corretta
# ---------------------------------------------------------------------------

def test_std_correct():
    # 08:00=480, 08:10=490, 08:20=500 → stdev([480,490,500]) = 10.0
    days = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    hours = [(8, 0), (8, 10), (8, 20)]
    sessions = [make_session(1, d, hh, mm) for d, (hh, mm) in zip(days, hours)]
    pool = [(1, "Mario Rossi")]
    recs = build_arrival_records(sessions, pool, DEFAULT_START, DEFAULT_END)
    pstats = compute_period_stats(recs, pool, days[0], days[-1],
                                   DEFAULT_START, DEFAULT_END, BUCKET_MIN)
    assert pstats.std_minutes == pytest.approx(10.0, abs=0.1)


# ---------------------------------------------------------------------------
# 10. Raggruppamento mensile corretto
# ---------------------------------------------------------------------------

def test_monthly_grouping():
    # 2 sessioni in gennaio, 1 in febbraio
    jan5 = date(2026, 1, 5)
    jan6 = date(2026, 1, 6)
    feb2 = date(2026, 2, 2)
    sessions = [
        make_session(1, jan5, 8, 10),
        make_session(1, jan6, 8, 20),
        make_session(1, feb2, 8, 30),
    ]
    pool = [(1, "Mario Rossi")]
    recs = build_arrival_records(sessions, pool, DEFAULT_START, DEFAULT_END)
    monthly = compute_monthly_stats(recs, DEFAULT_START, DEFAULT_END, BUCKET_MIN)

    assert len(monthly) == 2
    jan = next(m for m in monthly if m.year_month == "2026-01")
    feb = next(m for m in monthly if m.year_month == "2026-02")
    assert jan.valid_count == 2
    assert feb.valid_count == 1


# ---------------------------------------------------------------------------
# 11. Distribuzione per fasce corretta
# ---------------------------------------------------------------------------

def test_bucket_distribution():
    # 4 ingressi: 08:00, 08:05, 08:10, 08:55
    # Con bucket 10 min: bucket[0]=08:00-08:10 → 2, bucket[1]=08:10-08:20 → 1, bucket[5]=08:50-09:00 → 1
    days = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 8)]
    hours = [(8, 0), (8, 5), (8, 10), (8, 55)]
    sessions = [make_session(1, d, hh, mm) for d, (hh, mm) in zip(days, hours)]
    pool = [(1, "Mario Rossi")]
    recs = build_arrival_records(sessions, pool, DEFAULT_START, DEFAULT_END)
    pstats = compute_period_stats(recs, pool, days[0], days[-1],
                                   DEFAULT_START, DEFAULT_END, BUCKET_MIN)
    counts = {b.label: b.count for b in pstats.buckets}
    assert counts["08:00-08:10"] == 2
    assert counts["08:10-08:20"] == 1
    assert counts["08:50-09:00"] == 1


# ---------------------------------------------------------------------------
# 12. Filtro del pool rispettato
# ---------------------------------------------------------------------------

def test_pool_filter():
    # emp_id=1 è nel pool, emp_id=2 no
    s1 = make_session(1, DAY, 8, 15, emp_name="Mario Rossi")
    s2 = make_session(2, DAY, 8, 20, emp_name="Anna Bianchi")
    recs = records_for([s1, s2], pool=[(1, "Mario Rossi")])
    emp_ids = {r.employee_id for r in recs}
    assert emp_ids == {1}
    assert 2 not in emp_ids


# ---------------------------------------------------------------------------
# 13. Errore chiaro quando il pool è vuoto
# ---------------------------------------------------------------------------

def test_empty_pool_raises():
    s = make_session(1, DAY, 8, 10)
    with pytest.raises(ValueError, match="pool"):
        build_arrival_records([s], [], DEFAULT_START, DEFAULT_END)


# ---------------------------------------------------------------------------
# 14. Mese senza record validi gestito correttamente
# ---------------------------------------------------------------------------

def test_month_without_valid_records():
    # Tutti gli ingressi sono fuori fascia (07:50)
    sessions = [make_session(1, date(2026, 3, d), 7, 50) for d in range(2, 6)]
    pool = [(1, "Mario Rossi")]
    recs = build_arrival_records(sessions, pool, DEFAULT_START, DEFAULT_END)
    monthly = compute_monthly_stats(recs, DEFAULT_START, DEFAULT_END, BUCKET_MIN)

    assert len(monthly) == 1
    m = monthly[0]
    assert m.year_month == "2026-03"
    assert m.valid_count == 0
    assert m.excluded_count == 4
    assert m.mean_dt is None
    assert m.median_dt is None
    assert m.std_minutes is None
    assert m.most_frequent_bucket is None
    # percentili devono essere None quando non ci sono validi
    assert m.pct_by_0815 is None
    assert m.pct_by_0830 is None
    assert m.pct_by_0845 is None


# ---------------------------------------------------------------------------
# Bucket assignment edge cases
# ---------------------------------------------------------------------------

def test_bucket_boundary_0900_in_last_bucket():
    buckets = _build_buckets(time(8, 0), time(9, 0), 10)
    # 09:00 deve andare nell'ultimo bucket (08:50-09:00)
    idx = _assign_to_bucket(time(9, 0), buckets)
    assert idx == len(buckets) - 1
    assert buckets[idx].label == "08:50-09:00"


def test_bucket_boundary_0810_in_second_bucket():
    buckets = _build_buckets(time(8, 0), time(9, 0), 10)
    # 08:10 deve andare nel secondo bucket (08:10-08:20), NON nel primo
    idx = _assign_to_bucket(time(8, 10), buckets)
    assert idx == 1
    assert buckets[idx].label == "08:10-08:20"


def test_bucket_uneven_window():
    # Finestra 60 min, bucket 25 min → buckets: 08:00-08:25, 08:25-08:50, 08:50-09:00
    buckets = _build_buckets(time(8, 0), time(9, 0), 25)
    assert len(buckets) == 3
    assert buckets[-1].end_time == time(9, 0)
