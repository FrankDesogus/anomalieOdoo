from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from .models import AttendanceSession

def _dt(d: date, hh: int, mm: int, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, time(hh, mm)).replace(tzinfo=tz)

def build_fake_sessions(day: date, tz_name="Europe/Rome"):
    tz = ZoneInfo(tz_name)

    # Dipendente 1: non timbra fino a dopo le 9
    e1 = [
        AttendanceSession(1, "Mario Rossi", _dt(day, 9, 12, tz), _dt(day, 13, 0, tz)),
        AttendanceSession(1, "Mario Rossi", _dt(day, 14, 10, tz), _dt(day, 18, 0, tz)),
    ]

    # Dipendente 2: esce pranzo ma rientra tardi
    e2 = [
        AttendanceSession(2, "Giulia Bianchi", _dt(day, 8, 30, tz), _dt(day, 12, 45, tz)),
        AttendanceSession(2, "Giulia Bianchi", _dt(day, 14, 45, tz), _dt(day, 18, 10, tz)),
    ]

    # Dipendente 3: chiusura automatica alle 23:30
    e3 = [
        AttendanceSession(3, "Luca Verdi", _dt(day, 8, 15, tz), _dt(day, 23, 30, tz)),
    ]

    return e1 + e2 + e3
