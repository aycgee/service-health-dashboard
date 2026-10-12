import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
    name TEXT PRIMARY KEY, protocol TEXT, host TEXT, port INTEGER
);
CREATE TABLE IF NOT EXISTS health_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT, ts TEXT, ok INTEGER, latency_ms REAL, error TEXT
);
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT, started_at TEXT, ended_at TEXT, reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_checks_service_ts ON health_checks(service, ts);
"""

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

class Database:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def upsert_service(self, s):
        self.conn.execute(
            "INSERT OR REPLACE INTO services VALUES (?,?,?,?)",
            (s["name"], s["protocol"], s["host"], s["port"]))
        self.conn.commit()

    def add_check(self, service, ok, latency_ms, error):
        self.conn.execute(
            "INSERT INTO health_checks(service, ts, ok, latency_ms, error) VALUES (?,?,?,?,?)",
            (service, now(), int(ok), latency_ms, error))
        self.conn.commit()

    def open_incident(self, service, reason):
        if self.get_open_incident(service) is None:
            self.conn.execute(
                "INSERT INTO incidents(service, started_at, reason) VALUES (?,?,?)",
                (service, now(), reason))
            self.conn.commit()

    def close_incident(self, service):
        self.conn.execute(
            "UPDATE incidents SET ended_at=? WHERE service=? AND ended_at IS NULL",
            (now(), service))
        self.conn.commit()

    def get_open_incident(self, service):
        return self.conn.execute(
            "SELECT * FROM incidents WHERE service=? AND ended_at IS NULL",
            (service,)).fetchone()
