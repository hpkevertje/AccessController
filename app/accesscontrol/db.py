"""SQLite opslag. Eén verbinding, beschermd met een lock (lage belasting)."""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", "/data/accesscontrol.db")

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_no     TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    phone         TEXT UNIQUE,
    note          TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- Toestel = 1 RTU (eigen telefoonnummer) + 1 Tasmota-relais.
CREATE TABLE IF NOT EXISTS devices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE COLLATE NOCASE,
    enabled         INTEGER NOT NULL DEFAULT 1,
    serial_port     TEXT NOT NULL DEFAULT '',
    baudrate        INTEGER NOT NULL DEFAULT 38400,
    tasmota_topic   TEXT NOT NULL UNIQUE,
    on_seconds      INTEGER NOT NULL DEFAULT 1,
    dedupe_seconds  INTEGER NOT NULL DEFAULT 5,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

-- Toegang: een rij = dit lid mag dit toestel gebruiken.
CREATE TABLE IF NOT EXISTS member_access (
    member_id  INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    device_id  INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    PRIMARY KEY (member_id, device_id)
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    category     TEXT NOT NULL,      -- oproep | manueel | admin | sms | systeem
    device       TEXT,               -- naam van het toestel op dat moment
    device_id    INTEGER,
    actor        TEXT,               -- e-mail admin of telefoonnummer beller
    member_no    TEXT,
    member_name  TEXT,
    phone        TEXT,
    result       TEXT,               -- toegelaten | geweigerd | ok | fout | info
    reason       TEXT,
    detail       TEXT,
    cmd_id       TEXT,
    confirmed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_cmd ON events(cmd_id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def now_iso() -> str:
    """UTC, ISO 8601 met Z. Sorteerbaar als tekst."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init(path: str | None = None) -> None:
    global _conn, DB_PATH
    with _lock:
        if path:
            DB_PATH = path
        if DB_PATH != ":memory:":
            os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.executescript(SCHEMA)
        migrate()


def conn() -> sqlite3.Connection:
    assert _conn is not None, "db.init() niet aangeroepen"
    return _conn


@contextmanager
def tx():
    """Transactie: alles of niets."""
    with _lock:
        c = conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise


def query(sql: str, params=()) -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, params).fetchall()]


def query_one(sql: str, params=()) -> dict | None:
    with _lock:
        r = conn().execute(sql, params).fetchone()
        return dict(r) if r else None


def execute(sql: str, params=()) -> int:
    with _lock:
        cur = conn().execute(sql, params)
        return cur.lastrowid


# ---------- events ----------

def log_event(category: str, *, device=None, actor=None, member=None, phone=None,
              result=None, reason=None, detail=None, cmd_id=None) -> int:
    """device: dict van het toestel (naam + id worden bewaard) of None."""
    if isinstance(detail, (dict, list)):
        detail = json.dumps(detail, ensure_ascii=False)
    return execute(
        """INSERT INTO events (ts, category, device, device_id, actor, member_no, member_name, phone,
                               result, reason, detail, cmd_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (now_iso(), category,
         device["name"] if isinstance(device, dict) else device,
         device["id"] if isinstance(device, dict) else None, actor,
         member["member_no"] if member else None,
         member["name"] if member else None,
         phone, result, reason, detail, cmd_id),
    )


def confirm_cmd(cmd_id: str) -> bool:
    with _lock:
        cur = conn().execute(
            "UPDATE events SET confirmed_at=? WHERE cmd_id=? AND confirmed_at IS NULL",
            (now_iso(), cmd_id))
        return cur.rowcount > 0


def purge_events(months: int) -> int:
    with _lock:
        cur = conn().execute(
            "DELETE FROM events WHERE ts < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)", (f"-{int(months)} months",))
        return cur.rowcount


# ---------- settings ----------

def get_setting(key: str, default=None):
    r = query_one("SELECT value FROM settings WHERE key=?", (key,))
    return json.loads(r["value"]) if r else default


def set_setting(key: str, value) -> None:
    execute("INSERT INTO settings(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)))


def backup_to(path: str) -> None:
    with _lock:
        dest = sqlite3.connect(path)
        try:
            conn().backup(dest)
        finally:
            dest.close()


def restore_from(path: str) -> None:
    """Vervangt de volledige database door die in `path` (SQLite backup-API, op de open verbinding)."""
    with _lock:
        src = sqlite3.connect(path)
        try:
            src.backup(conn())
        finally:
            src.close()
        conn().executescript(SCHEMA)
        migrate()


# ---------- migraties ----------

def _columns(table: str) -> set[str]:
    return {r[1] for r in conn().execute(f"PRAGMA table_info({table})").fetchall()}


def migrate() -> None:
    """Brengt een oudere database naar het huidige schema. Idempotent."""
    with _lock:
        c = conn()
        if "device_id" not in _columns("events"):
            c.execute("ALTER TABLE events ADD COLUMN device_id INTEGER")
        cols = _columns("members")
        if "access_water" not in cols:
            return
        # Versie met vaste toestellen water/poort -> dynamische toestellen.
        c.execute("BEGIN IMMEDIATE")
        try:
            row = c.execute("SELECT value FROM settings WHERE key='config'").fetchone()
            cfg = json.loads(row[0]) if row else {}
            old_devs = cfg.pop("devices", {}) or {}
            ts = now_iso()
            ids = {}
            defaults = {"water": ("Water", "water", 1200, True), "gate": ("Poort", "poort", 1, False)}
            for order, (key, (name, topic, secs, enabled)) in enumerate(defaults.items()):
                d = old_devs.get(key, {})
                cur = c.execute(
                    """INSERT INTO devices (name, enabled, serial_port, baudrate, tasmota_topic, on_seconds,
                                            dedupe_seconds, sort_order, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (name, int(d.get("enabled", enabled)), d.get("serial_port", ""), int(d.get("baudrate", 38400)),
                     d.get("tasmota_topic", topic), int(d.get("on_seconds", secs)),
                     int(d.get("dedupe_seconds", 5)), order, ts))
                ids[key] = cur.lastrowid
                c.execute("UPDATE events SET device=?, device_id=? WHERE device=?", (name, ids[key], key))
            c.execute("INSERT INTO member_access (member_id, device_id) SELECT id, ? FROM members WHERE access_water=1",
                      (ids["water"],))
            c.execute("INSERT INTO member_access (member_id, device_id) SELECT id, ? FROM members WHERE access_gate=1",
                      (ids["gate"],))
            c.execute("ALTER TABLE members DROP COLUMN access_water")
            c.execute("ALTER TABLE members DROP COLUMN access_gate")
            if row:
                c.execute("UPDATE settings SET value=? WHERE key='config'", (json.dumps(cfg),))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
