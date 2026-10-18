"""Back-ups: dagelijks naar een map (en optioneel SharePoint), handmatig, en terugzetten."""
import gzip
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import db, sharepoint

log = logging.getLogger(__name__)

PREFIX = "accesscontrol-"
LOCAL_TZ = ZoneInfo(os.environ.get("TZ", "Europe/Brussels"))


class BackupError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(LOCAL_TZ)


def make() -> tuple[str, bytes]:
    """Consistente kopie van de database, gzip-gecomprimeerd."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        db.backup_to(path)
        with open(path, "rb") as f:
            data = gzip.compress(f.read(), compresslevel=6)
    finally:
        os.remove(path)
    return f"{PREFIX}{_now().strftime('%Y%m%d-%H%M%S')}.db.gz", data


def status() -> dict:
    return db.get_setting("backup_status", {})


def _save_status(st: dict) -> None:
    db.set_setting("backup_status", st)


def _write_local(folder: str, name: str, data: bytes, retention_days: int) -> tuple[str, int]:
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    limit = (_now() - timedelta(days=retention_days)).timestamp()
    removed = 0
    for fn in os.listdir(folder):
        p = os.path.join(folder, fn)
        if fn.startswith(PREFIX) and fn != name and os.path.isfile(p) and os.path.getmtime(p) < limit:
            os.remove(p)
            removed += 1
    return path, removed


def run(cfg: dict, actor: str = "systeem", automatic: bool = False) -> dict:
    """Maakt een back-up naar de map en (indien actief) SharePoint. Logt het resultaat."""
    b = cfg["backup"]
    sp = b["sharepoint"]
    name, data = make()
    result = {"ts": db.now_iso(), "file": name, "size": len(data), "automatic": automatic,
              "local": None, "sharepoint": None}
    errors = []
    try:
        path, removed = _write_local(b["folder"], name, data, b["retention_days"])
        result["local"] = {"ok": True, "path": path, "removed": removed}
    except OSError as e:
        result["local"] = {"ok": False, "error": str(e)}
        errors.append(f"Map {b['folder']}: {e}")
    if sp["enabled"]:
        try:
            url = sharepoint.upload(sp, name, data)
            removed = sharepoint.cleanup(sp, PREFIX, sp["retention_days"])
            result["sharepoint"] = {"ok": True, "url": url, "removed": removed}
        except Exception as e:  # noqa: BLE001
            result["sharepoint"] = {"ok": False, "error": str(e)}
            errors.append(f"SharePoint: {e}")
    result["ok"] = not errors
    st = status()
    st["last"] = result
    if automatic:
        st["last_auto_date"] = _now().strftime("%Y-%m-%d")
    if result["ok"]:
        st["last_ok"] = result["ts"]
    _save_status(st)
    where = ", ".join(w for w, r in (("map", result["local"]), ("SharePoint", result["sharepoint"])) if r and r["ok"])
    db.log_event("systeem" if automatic else "admin", actor=None if automatic else actor,
                 result="ok" if result["ok"] else "fout",
                 reason=("Automatische back-up" if automatic else "Back-up gemaakt") +
                        ("" if result["ok"] else " met fouten"),
                 detail=f"{name} ({len(data) // 1024} kB)" + (f" naar {where}" if where else "") +
                        ("" if result["ok"] else ". " + " | ".join(errors)))
    return result


def run_if_due(cfg: dict) -> dict | None:
    b = cfg["backup"]
    if not b["enabled"]:
        return None
    now = _now()
    if now.strftime("%H:%M") < b["time"]:
        return None
    if status().get("last_auto_date") == now.strftime("%Y-%m-%d"):
        return None
    return run(cfg, automatic=True)


# ---------- terugzetten ----------

REQUIRED_TABLES = {"members", "events", "settings"}


def _unpack(content: bytes) -> bytes:
    if content[:2] == b"\x1f\x8b":
        try:
            content = gzip.decompress(content)
        except OSError as e:
            raise BackupError(f"Bestand kan niet uitgepakt worden: {e}") from e
    if not content.startswith(b"SQLite format 3\x00"):
        raise BackupError("Dit is geen back-up van AccessController (geen SQLite-database).")
    return content


def restore(content: bytes, cfg: dict, actor: str, filename: str = "") -> dict:
    """Zet een back-up terug. Maakt eerst een veiligheidskopie van de huidige database."""
    raw = _unpack(content)
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(raw)
        try:
            chk = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            tables = {r[0] for r in chk.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            ok = chk.execute("PRAGMA quick_check").fetchone()[0]
            members_n = chk.execute("SELECT COUNT(*) FROM members").fetchone()[0] if "members" in tables else 0
            chk.close()
        except sqlite3.DatabaseError as e:
            raise BackupError(f"Database is beschadigd: {e}") from e
        missing = REQUIRED_TABLES - tables
        if missing:
            raise BackupError(f"Dit is geen back-up van AccessController (ontbrekende tabellen: {', '.join(sorted(missing))}).")
        if ok != "ok":
            raise BackupError(f"Database is beschadigd: {ok}")

        # Veiligheidskopie van de huidige toestand.
        name, data = make()
        safety_name = name.replace(PREFIX, PREFIX + "voor-terugzetten-")
        folder = cfg["backup"]["folder"]
        try:
            os.makedirs(folder, exist_ok=True)
            safety = os.path.join(folder, safety_name)
            with open(safety, "wb") as f:
                f.write(data)
        except OSError:
            safety = os.path.join(os.path.dirname(db.DB_PATH) or ".", safety_name)
            with open(safety, "wb") as f:
                f.write(data)

        keep_status = status()           # back-upgeschiedenis van deze server behouden
        db.restore_from(path)
        _save_status(keep_status)
    finally:
        os.remove(path)
    db.log_event("admin", actor=actor, result="ok", reason="Back-up teruggezet",
                 detail=f"{filename or 'upload'}: {members_n} leden. Vorige toestand bewaard als {safety}")
    return {"members": members_n, "safety_copy": safety}
