from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from typing import List, Optional
from .models import AttendanceSession, Anomaly

def _parse_hhmm(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))

def _dt(day: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, t).replace(tzinfo=tz)

def rule_missing_or_late_checkin(
    day: date,
    sessions: List[AttendanceSession],
    ingress_deadline: str,
    tz: ZoneInfo,
    is_exempt: bool = False
) -> Optional[Anomaly]:
    if is_exempt:
        return None
    deadline_dt = _dt(day, _parse_hhmm(ingress_deadline), tz)

    if not sessions:
        return Anomaly(
            day=day,
            employee_id=-1, employee_name="",
            code="NO_CHECKIN_BY_0900",
            severity="high",
            message=f"Nessuna timbratura di ingresso entro le {ingress_deadline}.",
            evidence={}
        )

    first_in = min(s.check_in for s in sessions if s.check_in.date() == day)
    if first_in > deadline_dt:
        return Anomaly(
            day=day,
            employee_id=-1, employee_name="",
            code="LATE_CHECKIN",
            severity="medium",
            message=f"Ingresso alle {first_in:%H:%M} (oltre le {ingress_deadline}).",
            evidence={"first_check_in": first_in.isoformat()}
        )
    return None

def rule_lunch_return(
    day: date,
    sessions: List[AttendanceSession],
    lunch_cfg: dict,
    tz: ZoneInfo
) -> List[Anomaly]:
    if not lunch_cfg.get("enabled", True):
        return []

    out_start = _dt(day, _parse_hhmm(lunch_cfg["out_window_start"]), tz)
    out_end = _dt(day, _parse_hhmm(lunch_cfg["out_window_end"]), tz)
    deadline = _dt(day, _parse_hhmm(lunch_cfg["return_deadline"]), tz)

    # timeline ordinata
    sessions_sorted = sorted(sessions, key=lambda s: s.check_in)

    lunch_out = None
    lunch_in = None

    # trova una check_out "da pranzo"
    for s in sessions_sorted:
        if s.check_out and out_start <= s.check_out <= out_end:
            lunch_out = s.check_out
            break

    if not lunch_out:
        return []

    # trova primo check_in dopo lunch_out
    for s in sessions_sorted:
        if s.check_in > lunch_out:
            lunch_in = s.check_in
            break

    anomalies = []
    if not lunch_in:
        anomalies.append(Anomaly(
            day=day, employee_id=-1, employee_name="",
            code="LUNCH_NO_RETURN", severity="high",
            message=f"Uscita pranzo alle {lunch_out:%H:%M}, nessun rientro entro le {lunch_cfg['return_deadline']}.",
            evidence={"lunch_out": lunch_out.isoformat()}
        ))
        return anomalies

    if lunch_in > deadline:
        anomalies.append(Anomaly(
            day=day, employee_id=-1, employee_name="",
            code="LUNCH_LATE_RETURN", severity="medium",
            message=f"Rientro post-pranzo alle {lunch_in:%H:%M} (oltre le {lunch_cfg['return_deadline']}).",
            evidence={"lunch_out": lunch_out.isoformat(), "lunch_in": lunch_in.isoformat()}
        ))

    return anomalies

def rule_autoclose(
    day: date,
    sessions: List[AttendanceSession],
    autoclose_cfg: dict,
    tz: ZoneInfo
) -> Optional[Anomaly]:
    if not autoclose_cfg.get("enabled", True):
        return None

    target = _dt(day, _parse_hhmm(autoclose_cfg["time"]), tz)
    tol = int(autoclose_cfg.get("tolerance_seconds", 60))

    for s in sessions:
        if s.check_out:
            if abs((s.check_out - target).total_seconds()) <= tol:
                return Anomaly(
                    day=day, employee_id=-1, employee_name="",
                    code="AUTO_CLOSE_LATE", severity="medium",
                    message=f"Timbratura chiusa automaticamente alle {autoclose_cfg['time']} (probabile dimenticanza uscita).",
                    evidence={"check_in": s.check_in.isoformat(), "check_out": s.check_out.isoformat()}
                )
    return None

def rule_no_attendance_all_day(
    day: date,
    sessions: list[AttendanceSession]
) -> Optional[Anomaly]:
    """
    Anomalia se non esistono timbrature per tutta la giornata.
    """
    if sessions:
        return None

    return Anomaly(
        day=day,
        employee_id=-1,
        employee_name="",
        code="NO_ATTENDANCE_ALL_DAY",
        severity="high",
        message="Nessuna timbratura registrata per l’intera giornata.",
        evidence={}
    )
