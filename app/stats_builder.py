from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from .models import AttendanceSession


@dataclass(frozen=True)
class ArrivalRecord:
    employee_id: int
    employee_name: str
    day: date
    first_checkin: datetime
    included: bool
    exclusion_reason: str  # VALID | BEFORE_TIME_WINDOW | AFTER_TIME_WINDOW


@dataclass
class BucketCount:
    label: str
    start_time: time
    end_time: time
    count: int


@dataclass
class PeriodStats:
    from_day: date
    to_day: date
    arrival_start: time
    arrival_end: time
    bucket_minutes: int
    employee_count: int
    valid_count: int
    excluded_count: int
    mean_dt: Optional[time]
    median_dt: Optional[time]
    std_minutes: Optional[float]
    most_frequent_bucket: Optional[str]
    pct_by_0815: Optional[float]
    pct_by_0830: Optional[float]
    pct_by_0845: Optional[float]
    buckets: List[BucketCount]


@dataclass
class MonthlyStats:
    year_month: str  # "YYYY-MM"
    valid_count: int
    excluded_count: int
    mean_dt: Optional[time]
    median_dt: Optional[time]
    std_minutes: Optional[float]
    most_frequent_bucket: Optional[str]
    pct_by_0815: Optional[float]
    pct_by_0830: Optional[float]
    pct_by_0845: Optional[float]
    buckets: List[BucketCount]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _time_to_minutes(t: time) -> float:
    return t.hour * 60 + t.minute + t.second / 60.0


def _minutes_to_time(mins: float) -> time:
    total = round(mins)
    return time(total // 60 % 24, total % 60)


def _build_buckets(arrival_start: time, arrival_end: time, bucket_minutes: int) -> List[BucketCount]:
    _base = date(2000, 1, 1)
    cur = datetime.combine(_base, arrival_start)
    end = datetime.combine(_base, arrival_end)
    delta = timedelta(minutes=bucket_minutes)
    buckets: List[BucketCount] = []
    while cur < end:
        nxt = min(cur + delta, end)
        buckets.append(BucketCount(
            label=f"{cur.strftime('%H:%M')}-{nxt.strftime('%H:%M')}",
            start_time=cur.time(),
            end_time=nxt.time(),
            count=0,
        ))
        cur = nxt
    return buckets


def _assign_to_bucket(t: time, buckets: List[BucketCount]) -> Optional[int]:
    last = len(buckets) - 1
    for i, b in enumerate(buckets):
        if i < last:
            if b.start_time <= t < b.end_time:
                return i
        else:
            if b.start_time <= t <= b.end_time:
                return i
    return None


def _classify(t: time, arrival_start: time, arrival_end: time) -> Tuple[bool, str]:
    if t < arrival_start:
        return False, "BEFORE_TIME_WINDOW"
    if t > arrival_end:
        return False, "AFTER_TIME_WINDOW"
    return True, "VALID"


def _compute_stats_from_valid(
    valid: List[ArrivalRecord],
    buckets: List[BucketCount],
) -> Tuple[
    Optional[time], Optional[time], Optional[float], Optional[str],
    Optional[float], Optional[float], Optional[float],
]:
    if not valid:
        return None, None, None, None, None, None, None

    mins = [_time_to_minutes(r.first_checkin.time()) for r in valid]
    mean_dt = _minutes_to_time(statistics.mean(mins))
    median_dt = _minutes_to_time(float(statistics.median(mins)))
    std_mins: Optional[float] = round(statistics.stdev(mins), 1) if len(mins) > 1 else 0.0

    for r in valid:
        idx = _assign_to_bucket(r.first_checkin.time(), buckets)
        if idx is not None:
            buckets[idx].count += 1

    most_freq = max(buckets, key=lambda b: b.count).label if any(b.count > 0 for b in buckets) else None

    n = len(valid)
    t_0815, t_0830, t_0845 = time(8, 15), time(8, 30), time(8, 45)
    pct_0815 = round(100.0 * sum(1 for r in valid if r.first_checkin.time() <= t_0815) / n, 1)
    pct_0830 = round(100.0 * sum(1 for r in valid if r.first_checkin.time() <= t_0830) / n, 1)
    pct_0845 = round(100.0 * sum(1 for r in valid if r.first_checkin.time() <= t_0845) / n, 1)

    return mean_dt, median_dt, std_mins, most_freq, pct_0815, pct_0830, pct_0845


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_arrival_records(
    sessions: List[AttendanceSession],
    employee_pool: List[Tuple[int, str]],
    arrival_start: time,
    arrival_end: time,
) -> List[ArrivalRecord]:
    """
    For each (employee_in_pool, day) pair found in sessions, pick the session
    with the minimum check_in and classify it against the arrival window.

    Days with no session for a given employee are simply omitted (no synthetic
    rows for weekends, holidays, or absences).
    """
    if not employee_pool:
        raise ValueError("Il pool dipendenti è vuoto. Specificare --employees, --employees-file o --all-employees.")

    pool_ids = {emp_id for emp_id, _ in employee_pool}
    pool_names = {emp_id: name for emp_id, name in employee_pool}

    by_emp_day: Dict[Tuple[int, date], List[AttendanceSession]] = defaultdict(list)
    for s in sessions:
        if s.employee_id in pool_ids:
            by_emp_day[(s.employee_id, s.check_in.date())].append(s)

    records: List[ArrivalRecord] = []
    for (emp_id, day), day_sessions in by_emp_day.items():
        first_in = min(day_sessions, key=lambda s: s.check_in).check_in
        # first_in is timezone-aware local; .time() strips tzinfo → naive local time
        t = first_in.time()
        included, reason = _classify(t, arrival_start, arrival_end)
        records.append(ArrivalRecord(
            employee_id=emp_id,
            employee_name=pool_names.get(emp_id, "Unknown"),
            day=day,
            first_checkin=first_in,
            included=included,
            exclusion_reason=reason,
        ))

    return sorted(records, key=lambda r: (r.day, r.employee_name, r.employee_id))


def compute_period_stats(
    records: List[ArrivalRecord],
    employee_pool: List[Tuple[int, str]],
    from_day: date,
    to_day: date,
    arrival_start: time,
    arrival_end: time,
    bucket_minutes: int,
) -> PeriodStats:
    valid = [r for r in records if r.included]
    excluded = len(records) - len(valid)
    buckets = _build_buckets(arrival_start, arrival_end, bucket_minutes)
    mean_dt, median_dt, std_mins, most_freq, p15, p30, p45 = _compute_stats_from_valid(valid, buckets)

    return PeriodStats(
        from_day=from_day,
        to_day=to_day,
        arrival_start=arrival_start,
        arrival_end=arrival_end,
        bucket_minutes=bucket_minutes,
        employee_count=len(employee_pool),
        valid_count=len(valid),
        excluded_count=excluded,
        mean_dt=mean_dt,
        median_dt=median_dt,
        std_minutes=std_mins,
        most_frequent_bucket=most_freq,
        pct_by_0815=p15,
        pct_by_0830=p30,
        pct_by_0845=p45,
        buckets=buckets,
    )


def compute_monthly_stats(
    records: List[ArrivalRecord],
    arrival_start: time,
    arrival_end: time,
    bucket_minutes: int,
) -> List[MonthlyStats]:
    by_month: Dict[str, List[ArrivalRecord]] = defaultdict(list)
    for r in records:
        by_month[f"{r.day.year:04d}-{r.day.month:02d}"].append(r)

    result: List[MonthlyStats] = []
    for ym in sorted(by_month):
        month_recs = by_month[ym]
        valid = [r for r in month_recs if r.included]
        excluded = len(month_recs) - len(valid)
        buckets = _build_buckets(arrival_start, arrival_end, bucket_minutes)
        mean_dt, median_dt, std_mins, most_freq, p15, p30, p45 = _compute_stats_from_valid(valid, buckets)

        result.append(MonthlyStats(
            year_month=ym,
            valid_count=len(valid),
            excluded_count=excluded,
            mean_dt=mean_dt,
            median_dt=median_dt,
            std_minutes=std_mins,
            most_frequent_bucket=most_freq,
            pct_by_0815=p15,
            pct_by_0830=p30,
            pct_by_0845=p45,
            buckets=buckets,
        ))

    return result
