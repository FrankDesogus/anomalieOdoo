from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

@dataclass(frozen=True)
class AttendanceSession:
    employee_id: int
    employee_name: str
    check_in: datetime
    check_out: Optional[datetime]  # None se presenza aperta

@dataclass(frozen=True)
class Anomaly:
    day: date
    employee_id: int
    employee_name: str
    code: str
    severity: str
    message: str
    evidence: dict
