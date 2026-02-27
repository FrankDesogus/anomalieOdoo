from collections import defaultdict
from datetime import date
from zoneinfo import ZoneInfo
from typing import List, Dict, Tuple, Optional

from .models import AttendanceSession, Anomaly
from .rules import (
    rule_missing_or_late_checkin,
    rule_lunch_return,
    rule_autoclose,
    rule_no_attendance_all_day,   # <-- nuova
)


def detect_for_day(
    day: date,
    sessions: List[AttendanceSession],
    cfg: dict,
    employees: Optional[List[Tuple[int, str]]] = None  # [(employee_id, name)]
) -> List[Anomaly]:
    tz = ZoneInfo(cfg["timezone"])
    rules_cfg = cfg["rules"]

    exemptions_cfg = cfg.get("exemptions") or {}
    limited_ids = set(exemptions_cfg.get("limited_rules_employee_ids", []))

    per_emp: Dict[int, List[AttendanceSession]] = defaultdict(list)
    for s in sessions:
        per_emp[s.employee_id].append(s)

    # Se non passiamo employees, usiamo solo chi compare nelle timbrature (comportamento vecchio)
    if employees is None:
        employees = sorted({(s.employee_id, s.employee_name) for s in sessions}, key=lambda x: x[0])

    anomalies: List[Anomaly] = []

    for emp_id, emp_name in employees:
        emp_sessions = per_emp.get(emp_id, [])
        is_limited = (emp_id in limited_ids)

        # 0) ASSENZA TOTALE: solo se NON limited
        if not is_limited:
            a_abs = rule_no_attendance_all_day(day, emp_sessions)
            if a_abs:
                anomalies.append(a_abs.__class__(**{**a_abs.__dict__, "employee_id": emp_id, "employee_name": emp_name}))
                # Se vuoi, qui potresti anche "continue" per non fare altre regole,
                # ma in pratica se è assente non avrà altre sessioni comunque.

        # 1) ingresso: solo se NON limited
        if not is_limited:
            a_in = rule_missing_or_late_checkin(day, emp_sessions, rules_cfg["ingress_deadline"], tz, is_exempt=False)
            if a_in:
                anomalies.append(a_in.__class__(**{**a_in.__dict__, "employee_id": emp_id, "employee_name": emp_name}))

            # 2) pranzo: solo se NON limited
            for a in rule_lunch_return(day, emp_sessions, rules_cfg["lunch"], tz):
                anomalies.append(a.__class__(**{**a.__dict__, "employee_id": emp_id, "employee_name": emp_name}))

        # 3) autoclose: SEMPRE (anche per limited)
        a_auto = rule_autoclose(day, emp_sessions, rules_cfg["autoclose"], tz)
        if a_auto:
            anomalies.append(a_auto.__class__(**{**a_auto.__dict__, "employee_id": emp_id, "employee_name": emp_name}))

    return anomalies
