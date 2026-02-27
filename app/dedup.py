import sqlite3
from pathlib import Path

class DedupStore:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)

    def init(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS sent (
                day TEXT NOT NULL,
                employee_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                PRIMARY KEY (day, employee_id, code)
            )
            """)

    def already_sent(self, day: str, employee_id: int, code: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT 1 FROM sent WHERE day=? AND employee_id=? AND code=?",
                (day, employee_id, code)
            )
            return cur.fetchone() is not None

    def mark_sent(self, day: str, employee_id: int, code: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sent(day, employee_id, code) VALUES(?,?,?)",
                (day, employee_id, code)
            )
