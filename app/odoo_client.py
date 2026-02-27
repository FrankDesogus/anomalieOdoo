import xmlrpc.client
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, time, timedelta, date
from zoneinfo import ZoneInfo

from .models import AttendanceSession


class OdooClient:
    def __init__(self, url: str, db: str, user: str, password: str, timezone: str):
        self.url = url.rstrip("/")
        self.db = db
        self.user = user
        self.password = password
        self.tz = ZoneInfo(timezone)

        self.common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

        self.uid = self.common.authenticate(self.db, self.user, self.password, {})
        if not self.uid:
            raise RuntimeError("Login Odoo fallito (db/user/password/url).")

    # ---------- Helpers ----------

    def _to_local(self, dt_str: str) -> datetime:
        """
        Odoo via XML-RPC tipicamente ritorna datetime come stringa "YYYY-MM-DD HH:MM:SS"
        in UTC (naive). Qui lo interpretiamo come UTC e lo convertiamo in timezone locale.
        """
        dt_utc = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("UTC"))
        return dt_utc.astimezone(self.tz)

    def _day_range_utc_strings(self, day_local: date) -> Tuple[str, str]:
        """
        Ritorna (start_utc_str, end_utc_str) per la giornata locale [00:00, 24:00)
        """
        start_local = datetime.combine(day_local, time(0, 0)).replace(tzinfo=self.tz)
        end_local = start_local + timedelta(days=1)

        start_utc = start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        end_utc = end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        return (
            start_utc.strftime("%Y-%m-%d %H:%M:%S"),
            end_utc.strftime("%Y-%m-%d %H:%M:%S"),
        )

    # ---------- Employee ----------

    def fetch_active_employees(self) -> List[Tuple[int, str]]:
        employees = self.models.execute_kw(
            self.db, self.uid, self.password,
            "hr.employee", "search_read",
            [[("active", "=", True)]],
            {"fields": ["id", "name"], "limit": 0}
        )
        return [(e["id"], e["name"]) for e in employees]

    def search_employees(self, query: str, limit: int = 10):
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            "hr.employee", "search_read",
            [["|", ("work_email", "ilike", query), ("name", "ilike", query)]],
            {"fields": ["id", "name", "work_email", "company_id"], "limit": limit}
        )

    # ---------- Attendance (debug raw) ----------

    def fetch_attendances_for_day(self, day_local: date) -> List[Dict[str, Any]]:
        """
        Legge le attendances di TUTTI per la giornata indicata (in base al check_in nel range).
        Utile per debug connessione/dati/timezone.
        """
        start_utc, end_utc = self._day_range_utc_strings(day_local)

        attendances = self.models.execute_kw(
            self.db, self.uid, self.password,
            "hr.attendance", "search_read",
            [[("check_in", ">=", start_utc), ("check_in", "<", end_utc)]],
            {"fields": ["employee_id", "check_in", "check_out"], "limit": 0, "order": "check_in asc"}
        )

        rows = []
        for a in attendances:
            rows.append({
                "employee_id": a["employee_id"][0],
                "employee_name": a["employee_id"][1],
                "raw_check_in": a["check_in"],
                "raw_check_out": a.get("check_out"),
                "check_in_local": self._to_local(a["check_in"]).isoformat(),
                "check_out_local": self._to_local(a["check_out"]).isoformat() if a.get("check_out") else None,
            })
        return rows

    def fetch_my_attendances_today(self) -> List[Dict[str, Any]]:
        """
        Opzionale: funziona SOLO se l'utente Odoo (uid) è collegato a hr.employee.user_id.
        (Admin spesso NON lo è.)
        """
        emp = self.models.execute_kw(
            self.db, self.uid, self.password,
            "hr.employee", "search_read",
            [[("user_id", "=", self.uid)]],
            {"fields": ["id", "name"], "limit": 1}
        )
        if not emp:
            raise RuntimeError("Nessun hr.employee collegato a questo utente (campo user_id).")

        emp_id = emp[0]["id"]
        emp_name = emp[0]["name"]

        today = datetime.now(self.tz).date()
        start_utc, end_utc = self._day_range_utc_strings(today)

        att = self.models.execute_kw(
            self.db, self.uid, self.password,
            "hr.attendance", "search_read",
            [[("employee_id", "=", emp_id), ("check_in", ">=", start_utc), ("check_in", "<", end_utc)]],
            {"fields": ["check_in", "check_out"], "limit": 50, "order": "check_in asc"}
        )

        rows = []
        for a in att:
            rows.append({
                "employee": emp_name,
                "raw_check_in": a["check_in"],
                "raw_check_out": a.get("check_out"),
                "check_in_local": self._to_local(a["check_in"]).isoformat(),
                "check_out_local": self._to_local(a["check_out"]).isoformat() if a.get("check_out") else None,
            })
        return rows

    # ---------- Attendance (to detector) ----------

    def fetch_sessions_for_day(self, day_start_utc: str, day_end_utc: str) -> List[AttendanceSession]:
        """
        Ritorna AttendanceSession (employee_id, employee_name, check_in/check_out locali)
        per tutte le timbrature che hanno check_in dentro [day_start_utc, day_end_utc).
        """
        attendances = self.models.execute_kw(
            self.db, self.uid, self.password,
            "hr.attendance", "search_read",
            [[("check_in", ">=", day_start_utc), ("check_in", "<", day_end_utc)]],
            {"fields": ["employee_id", "check_in", "check_out"], "limit": 0, "order": "check_in asc"}
        )

        # employee_id già contiene (id, name) nella maggior parte dei casi via search_read,
        # ma facciamo fallback robusto caricando nomi da hr.employee.
        emp_ids = list({a["employee_id"][0] for a in attendances if a.get("employee_id")})
        emp_name: Dict[int, str] = {}

        if emp_ids:
            employees = self.models.execute_kw(
                self.db, self.uid, self.password,
                "hr.employee", "search_read",
                [[("id", "in", emp_ids)]],
                {"fields": ["id", "name"], "limit": 0}
            )
            emp_name = {e["id"]: e["name"] for e in employees}

        out: List[AttendanceSession] = []
        for a in attendances:
            emp_id = a["employee_id"][0]
            # prova a usare il nome ritornato da employee_id, altrimenti fallback
            name_from_rel = a["employee_id"][1] if isinstance(a["employee_id"], list) and len(a["employee_id"]) > 1 else None
            resolved_name = name_from_rel or emp_name.get(emp_id, "Unknown")

            out.append(AttendanceSession(
                employee_id=emp_id,
                employee_name=resolved_name,
                check_in=self._to_local(a["check_in"]),
                check_out=self._to_local(a["check_out"]) if a.get("check_out") else None
            ))

        return out

    def get_employee_names_by_ids(self, employee_ids):
        if not employee_ids:
            return {}

        employees = self.models.execute_kw(
            self.db, self.uid, self.password,
            "hr.employee", "search_read",
            [[("id", "in", employee_ids)]],
            {"fields": ["id", "name"], "limit": 0}
        )
        return {e["id"]: e["name"] for e in employees}
