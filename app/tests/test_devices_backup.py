import gzip
import io
import json
import os
import sqlite3

import openpyxl
import pytest

from accesscontrol import backup, db, devices, members, settings, sharepoint


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db.init(str(tmp_path / "t.db"))
    yield


def mkdev(name, topic, grant=True, **kw):
    return devices.create({"name": name, "tasmota_topic": topic, "serial_port": f"/dev/x-{topic}", **kw},
                          grant, "admin@x")


def mk(no, phone, **kw):
    return members.create({"member_no": no, "name": f"Lid {no}", "phone": phone, **kw}, "BE", "admin@x")


# ---------- toestellen ----------

def test_create_requires_grant_choice_and_applies_it():
    m = mk("1", "0470000001")
    with pytest.raises(devices.DeviceError):
        devices.create({"name": "Water", "tasmota_topic": "water", "serial_port": "/dev/a"}, None, "x")
    w = mkdev("Water", "water", grant=True)
    p = mkdev("Poort", "poort", grant=False)
    acc = members.get(m["id"])["access"]
    assert acc == {w["id"]: True, p["id"]: False}
    assert "toegang gegeven aan 1 bestaande leden" in db.query_one(
        "SELECT detail FROM events WHERE reason='Toestel toegevoegd' AND device='Water'")["detail"]


def test_device_validation_uniqueness():
    mkdev("Water", "water")
    with pytest.raises(devices.DeviceError) as e:
        devices.create({"name": "water", "tasmota_topic": "water", "serial_port": "/dev/x-water"}, True, "x")
    text = " ".join(e.value.errors)
    assert "naam" in text and "Tasmota-topic" in text and "Seriële poort" in text
    with pytest.raises(devices.DeviceError):
        devices.create({"name": "X", "tasmota_topic": "a/b", "serial_port": ""}, True, "x")


def test_delete_device_keeps_log_and_removes_access():
    m = mk("1", "0470000001")
    w = mkdev("Water", "water")
    db.log_event("oproep", device=w, result="toegelaten")
    devices.delete(w["id"], "admin@x")
    assert members.get(m["id"])["access"] == {}
    assert db.query_one("SELECT device FROM events WHERE category='oproep'")["device"] == "Water"


def test_new_member_gets_access_to_all_by_default():
    w = mkdev("Water", "water")
    p = mkdev("Poort", "poort")
    m = mk("1", "0470000001", access={str(p["id"]): False})
    assert m["access"] == {w["id"]: True, p["id"]: False}


def test_import_export_dynamic_columns():
    w = mkdev("Water", "water")
    s = mkdev("Slagboom 2", "slagboom2")
    mk("1", "0470000001", access={s["id"]: False})
    wb = openpyxl.load_workbook(io.BytesIO(members.export_xlsx()))
    assert [c.value for c in wb.active[1]] == ["Lidnr", "Naam", "Telefoon", "Toegang Water",
                                              "Toegang Slagboom 2", "Opmerking"]
    assert members.import_file("x.xlsx", members.export_xlsx(), "BE", "a")["ongewijzigd"] == 1

    def xlsx(rows):
        wb = openpyxl.Workbook()
        for r in rows:
            wb.active.append(r)
        b = io.BytesIO()
        wb.save(b)
        return b.getvalue()

    members.import_file("x.xlsx", xlsx([["Lidnr", "Toegang Slagboom 2"], ["1", "ja"]]), "BE", "a")
    assert members.list_members()[0]["access"] == {w["id"]: True, s["id"]: True}
    with pytest.raises(members.ValidationError) as e:
        members.import_file("x.xlsx", xlsx([["Lidnr", "Toegang Garage"], ["1", "ja"]]), "BE", "a")
    assert "Toegang Garage" in e.value.errors[0] and "Toegang Slagboom 2" in e.value.errors[0]


# ---------- migratie ----------

OLD_SCHEMA = """
CREATE TABLE members (id INTEGER PRIMARY KEY AUTOINCREMENT, member_no TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  phone TEXT UNIQUE, access_water INTEGER NOT NULL DEFAULT 1, access_gate INTEGER NOT NULL DEFAULT 1,
  note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, category TEXT NOT NULL, device TEXT,
  actor TEXT, member_no TEXT, member_name TEXT, phone TEXT, result TEXT, reason TEXT, detail TEXT, cmd_id TEXT,
  confirmed_at TEXT);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def make_old_db(path):
    c = sqlite3.connect(path)
    c.executescript(OLD_SCHEMA)
    c.execute("INSERT INTO members VALUES (1,'101','An','+32470000001',1,0,'',  'x','x')")
    c.execute("INSERT INTO members VALUES (2,'102','Bo','+32470000002',0,1,'',  'x','x')")
    c.execute("INSERT INTO events (ts, category, device, result) VALUES ('2026-10-01T10:00:00Z','oproep','water','toegelaten')")
    cfg = {"mqtt": {"host": "broker"}, "devices": {
        "water": {"enabled": True, "serial_port": "/dev/serial/by-id/usb-x", "baudrate": 38400,
                  "tasmota_topic": "water", "on_seconds": 1200, "dedupe_seconds": 5},
        "gate": {"enabled": False, "serial_port": "/dev/ttyUSB1", "tasmota_topic": "poort", "on_seconds": 1}}}
    c.execute("INSERT INTO settings VALUES ('config', ?)", (json.dumps(cfg),))
    c.commit()
    c.close()


def test_migration_from_fixed_devices(tmp_path):
    path = str(tmp_path / "old.db")
    make_old_db(path)
    db.init(path)
    devs = {d["name"]: d for d in devices.list_devices()}
    assert devs["Water"]["serial_port"] == "/dev/serial/by-id/usb-x" and devs["Water"]["on_seconds"] == 1200
    assert devs["Poort"]["enabled"] is False and devs["Poort"]["tasmota_topic"] == "poort"
    by = {m["member_no"]: m for m in members.list_members()}
    assert by["101"]["access"] == {devs["Water"]["id"]: True, devs["Poort"]["id"]: False}
    assert by["102"]["access"] == {devs["Water"]["id"]: False, devs["Poort"]["id"]: True}
    ev = db.query_one("SELECT device, device_id FROM events WHERE category='oproep'")
    assert ev == {"device": "Water", "device_id": devs["Water"]["id"]}
    assert "devices" not in db.get_setting("config")
    assert settings.load()["mqtt"]["host"] == "broker"
    db.init(path)                       # tweede keer: niets meer te doen
    assert len(devices.list_devices()) == 2


# ---------- back-up ----------

def cfg_with(backup_dir, **sp):
    cfg = settings.load()
    cfg["backup"].update({"enabled": True, "folder": str(backup_dir), "retention_days": 30})
    cfg["backup"]["sharepoint"].update(sp)
    return cfg


def test_backup_to_folder_and_retention(tmp_path):
    folder = tmp_path / "bk"
    folder.mkdir()
    old = folder / "accesscontrol-20200101-000000.db.gz"
    old.write_bytes(b"x")
    os.utime(old, (0, 0))
    other = folder / "iets-anders.txt"
    other.write_bytes(b"x")
    os.utime(other, (0, 0))
    r = backup.run(cfg_with(folder), actor="admin@x")
    assert r["ok"] and r["local"]["removed"] == 1
    assert not old.exists() and other.exists()
    data = gzip.decompress((folder / r["file"]).read_bytes())
    assert data.startswith(b"SQLite format 3")
    assert backup.status()["last"]["file"] == r["file"]


def test_backup_folder_error_logged(tmp_path):
    f = tmp_path / "file"
    f.write_text("x")
    r = backup.run(cfg_with(f / "sub"), actor="a")
    assert not r["ok"]
    assert db.query_one("SELECT result FROM events WHERE reason LIKE 'Back-up gemaakt%'")["result"] == "fout"


def test_run_if_due_once_per_day(tmp_path, monkeypatch):
    cfg = cfg_with(tmp_path)
    cfg["backup"]["time"] = "00:00"
    assert backup.run_if_due(cfg)["ok"]
    assert backup.run_if_due(cfg) is None
    cfg["backup"]["enabled"] = False
    st = backup.status()
    st["last_auto_date"] = "2000-01-01"
    db.set_setting("backup_status", st)
    assert backup.run_if_due(cfg) is None


def test_restore_roundtrip_and_safety_copy(tmp_path):
    mkdev("Water", "water")
    mk("1", "0470000001")
    name, data = backup.make()
    mk("2", "0470000002")
    assert len(members.list_members()) == 2
    r = backup.restore(data, cfg_with(tmp_path), "admin@x", name)
    assert r["members"] == 1 and len(members.list_members()) == 1
    assert os.path.exists(r["safety_copy"])
    assert db.query_one("SELECT actor FROM events WHERE reason='Back-up teruggezet'")["actor"] == "admin@x"


def test_restore_old_version_backup_is_migrated(tmp_path):
    path = str(tmp_path / "old.db")
    make_old_db(path)
    with open(path, "rb") as f:
        content = f.read()
    backup.restore(content, cfg_with(tmp_path), "a")
    assert {d["name"] for d in devices.list_devices()} == {"Water", "Poort"}


@pytest.mark.parametrize("content,msg", [(b"hallo", "geen SQLite"), (gzip.compress(b"x"), "geen SQLite")])
def test_restore_rejects_garbage(tmp_path, content, msg):
    mk("1", "0470000001")
    with pytest.raises(backup.BackupError) as e:
        backup.restore(content, cfg_with(tmp_path), "a")
    assert msg in str(e.value)
    assert len(members.list_members()) == 1


def test_restore_rejects_foreign_sqlite(tmp_path):
    p = tmp_path / "x.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE foo (a)")
    c.commit()
    c.close()
    with pytest.raises(backup.BackupError) as e:
        backup.restore(p.read_bytes(), cfg_with(tmp_path), "a")
    assert "ontbrekende tabellen" in str(e.value)


# ---------- SharePoint (Graph gesimuleerd) ----------

def test_sharepoint_upload_and_cleanup(tmp_path, monkeypatch):
    calls = []
    state = {"total": 0, "level": "checkout"}

    def fake(method, url, token=None, data=None, headers=None, form=None):
        calls.append((method, url, headers))
        if "oauth2" in url:
            assert form["client_secret"] == "geheim"
            return {"access_token": "T"}
        if url.startswith("https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com:/sites/IT"):
            return {"id": "SITE"}
        if url.endswith("createUploadSession"):
            return {"uploadUrl": "https://upload.example/abc"}
        if url == "https://upload.example/abc":
            assert "Authorization" not in (headers or {})
            start, rest = headers["Content-Range"].split(" ")[1].split("-")
            state["total"] = int(rest.split("/")[1])
            return {"id": "FILE", "name": "x", "size": state["total"],
                    "webUrl": "https://contoso.sharepoint.com/x",
                    "publication": {"level": state["level"]}}
        if url.endswith("/checkin"):
            assert json.loads(data)["checkInAs"] == "published"
            state["level"] = "published"
            return {}
        if "/children" in url:
            return {"value": [
                {"id": "1", "name": "accesscontrol-20200101-000000.db.gz", "createdDateTime": "2020-01-01T00:00:00Z"},
                {"id": "2", "name": "andere.docx", "createdDateTime": "2020-01-01T00:00:00Z"}]}
        if "/drive/root:/" in url:
            return {"id": "FILE", "name": "x", "size": state["total"],
                    "webUrl": "https://contoso.sharepoint.com/x",
                    "publication": {"level": state["level"]}}
        if method == "DELETE":
            return {}
        raise AssertionError(url)

    monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", "geheim")
    monkeypatch.setattr(sharepoint, "_request", fake)
    cfg = cfg_with(tmp_path, enabled=True, tenant_id="t", client_id="c",
                   site_url="https://contoso.sharepoint.com/sites/IT", folder="Back-ups/AC")
    r = backup.run(cfg, actor="a")
    assert r["ok"] and r["sharepoint"]["removed"] == 1
    deletes = [u for m, u, _ in calls if m == "DELETE"]
    assert deletes == ["https://graph.microsoft.com/v1.0/sites/SITE/drive/items/1"]
    assert any("root:/Back-ups/AC/accesscontrol-" in u for _, u, _ in calls)
    assert any(u.endswith("/items/FILE/checkin") for m, u, _ in calls if m == "POST")
    assert state["level"] == "published"


def _sp_cfg(tmp_path):
    return cfg_with(tmp_path, enabled=True, tenant_id="t", client_id="c",
                    site_url="https://contoso.sharepoint.com/sites/IT", folder="Back-ups/AC")


def _sp_base(method, url, state):
    """Minimale Graph-simulatie voor uploadtests; geeft None als de URL niet bekend is."""
    if "oauth2" in url:
        return {"access_token": "T"}
    if url.startswith("https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com:/sites/IT"):
        return {"id": "SITE"}
    if url.endswith("createUploadSession"):
        return {"uploadUrl": "https://upload.example/abc"}
    if url == "https://upload.example/abc":
        start, rest = state["headers"]["Content-Range"].split(" ")[1].split("-")
        state["total"] = int(rest.split("/")[1])
        return {"id": "FILE", "size": state["total"], "webUrl": "https://x/y"}
    if "/children" in url:
        return {"value": []}
    if "/drive/root:/" in url:
        return {"id": "FILE", "size": state.get("reported_size", state["total"]),
                "webUrl": "https://x/y", "publication": {"level": state["level"]}}
    if method == "DELETE":
        return {}
    return None


def test_sharepoint_upload_verifies_size(tmp_path, monkeypatch):
    state = {"total": 0, "level": "published", "reported_size": 1}

    def fake(method, url, token=None, data=None, headers=None, form=None):
        state["headers"] = headers or {}
        result = _sp_base(method, url, state)
        if result is None:
            raise AssertionError(url)
        return result

    monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", "geheim")
    monkeypatch.setattr(sharepoint, "_request", fake)
    r = backup.run(_sp_cfg(tmp_path), actor="a")
    assert not r["ok"] and not r["sharepoint"]["ok"]
    assert "bytes" in r["sharepoint"]["error"]


def test_sharepoint_upload_that_stays_checked_out_is_an_error(tmp_path, monkeypatch):
    state = {"total": 0, "level": "checkout"}

    def fake(method, url, token=None, data=None, headers=None, form=None):
        state["headers"] = headers or {}
        if url.endswith("/checkin"):
            return {}                      # check-in lukt niet / blijft concept
        result = _sp_base(method, url, state)
        if result is None:
            raise AssertionError(url)
        return result

    monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", "geheim")
    monkeypatch.setattr(sharepoint, "_request", fake)
    r = backup.run(_sp_cfg(tmp_path), actor="a")
    assert not r["ok"] and "uitgecheckt" in r["sharepoint"]["error"]


def test_sharepoint_upload_pending_approval_is_reported(tmp_path, monkeypatch):
    state = {"total": 0, "level": "published", "headers": {}}

    def fake(method, url, token=None, data=None, headers=None, form=None):
        if "/listItem" in url:
            return {"fields": {"_ModerationStatus": 2}}
        state["headers"] = headers or {}
        result = _sp_base(method, url, state)
        if result is None:
            raise AssertionError(url)
        return result

    monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", "geheim")
    monkeypatch.setattr(sharepoint, "_request", fake)
    r = backup.run(_sp_cfg(tmp_path), actor="a")
    assert not r["ok"] and "goedkeuring" in r["sharepoint"]["error"]


def test_sharepoint_diagnose_reports_each_step(tmp_path, monkeypatch):
    calls = []

    def fake(method, url, token=None, data=None, headers=None, form=None):
        calls.append((method, url))
        if "oauth2" in url:
            return {"access_token": "T"}
        if url.startswith("https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com:/sites/IT"):
            return {"id": "SITE"}
        if "/drive?$select=" in url:
            return {"id": "DRIVE", "name": "Documents", "webUrl": "https://contoso.sharepoint.com/Shared Documents"}
        if "/children" in url:
            return {"value": []}
        if url.endswith("createUploadSession"):
            return {"uploadUrl": "https://upload.example/abc"}
        if url == "https://upload.example/abc":
            start, rest = headers["Content-Range"].split(" ")[1].split("-")
            return {"id": "FILE", "size": int(rest.split("/")[1]), "webUrl": "https://x/diagnose"}
        if "/listItem" in url:
            return {"fields": {"_ModerationStatus": 0}}
        if "/drive/root:/" in url:
            return {"id": "FILE", "size": 2496, "webUrl": "https://x/diagnose",
                    "publication": {"level": "published"}}
        if method == "DELETE":
            return {}
        raise AssertionError(url)

    monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", "geheim")
    monkeypatch.setattr(sharepoint, "_request", fake)
    result = sharepoint.diagnose(_sp_cfg(tmp_path)["backup"]["sharepoint"])
    assert result["ok"]
    names = [s["step"] for s in result["steps"]]
    assert names == ["config", "secret", "token", "site", "drive",
                     "folder", "upload", "publication", "cleanup"]
    assert result["steps"][1]["detail"] == {"set": True}
    assert result["steps"][7]["detail"]["moderation"] == "approved"
    assert any(m == "DELETE" and u.endswith("/items/FILE") for m, u in calls)


def test_sharepoint_without_secret_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.delenv("SHAREPOINT_CLIENT_SECRET", raising=False)
    cfg = cfg_with(tmp_path, enabled=True, tenant_id="t", client_id="c",
                   site_url="https://contoso.sharepoint.com/sites/IT")
    r = backup.run(cfg, actor="a")
    assert not r["ok"] and r["local"]["ok"] and "SHAREPOINT_CLIENT_SECRET" in r["sharepoint"]["error"]


# ---------- Shelly: type relaismodule ----------

def test_device_relay_type_validation():
    with pytest.raises(devices.DeviceError) as e:
        devices.create({"name": "X", "relay_type": "anders", "tasmota_topic": "x",
                        "serial_port": "/dev/x"}, True, "x")
    assert "Type relaismodule moet tasmota of shelly zijn." in e.value.errors

    s = devices.create({"name": "Shelly", "relay_type": "shelly",
                        "tasmota_topic": "shelly1g3-d0cf13dde9dc",
                        "serial_port": "/dev/x-shelly"}, True, "x")
    assert s["relay_type"] == "shelly"

    with pytest.raises(devices.DeviceError) as e:
        devices.create({"name": "Shelly 2", "relay_type": "shelly",
                        "tasmota_topic": "shelly1g3-d0cf13dde9dc",
                        "serial_port": "/dev/x-shelly2"}, True, "x")
    assert "Shelly-ID" in " ".join(e.value.errors)

    devices.create({"name": "Tasmota 1", "relay_type": "tasmota", "tasmota_topic": "water",
                    "serial_port": "/dev/x-t1"}, True, "x")
    with pytest.raises(devices.DeviceError) as e:
        devices.create({"name": "Tasmota 2", "relay_type": "tasmota", "tasmota_topic": "water",
                        "serial_port": "/dev/x-t2"}, True, "x")
    assert "Tasmota-topic" in " ".join(e.value.errors)


def test_device_update_behoudt_relay_type():
    s = devices.create({"name": "Shelly", "relay_type": "shelly",
                        "tasmota_topic": "shelly1g3-d0cf13dde9dc",
                        "serial_port": "/dev/x-shelly"}, True, "x")
    updated = devices.update(s["id"], {"on_seconds": 60}, "x")
    assert updated["relay_type"] == "shelly"
    assert updated["on_seconds"] == 60


NO_RELAY_TYPE_SCHEMA = """
CREATE TABLE members (id INTEGER PRIMARY KEY AUTOINCREMENT, member_no TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  phone TEXT UNIQUE, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, category TEXT NOT NULL, device TEXT,
  device_id INTEGER, actor TEXT, member_no TEXT, member_name TEXT, phone TEXT, result TEXT, reason TEXT, detail TEXT,
  cmd_id TEXT, confirmed_at TEXT);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE devices (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  enabled INTEGER NOT NULL DEFAULT 1, serial_port TEXT NOT NULL DEFAULT '',
  baudrate INTEGER NOT NULL DEFAULT 38400, tasmota_topic TEXT NOT NULL UNIQUE,
  on_seconds INTEGER NOT NULL DEFAULT 1, dedupe_seconds INTEGER NOT NULL DEFAULT 5,
  sort_order INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
"""


def make_db_without_relay_type(path):
    c = sqlite3.connect(path)
    c.executescript(NO_RELAY_TYPE_SCHEMA)
    c.execute("INSERT INTO devices (name, enabled, serial_port, baudrate, tasmota_topic, on_seconds, "
              "dedupe_seconds, sort_order, created_at) VALUES "
              "('Water', 1, '/dev/x-water', 38400, 'water', 1200, 5, 0, 'x')")
    c.commit()
    c.close()


def test_migration_adds_relay_type_idempotent(tmp_path):
    path = str(tmp_path / "zonder-relay-type.db")
    make_db_without_relay_type(path)
    db.init(path)
    devs = devices.list_devices()
    assert len(devs) == 1 and devs[0]["relay_type"] == "tasmota"
    db.init(path)
    devs = devices.list_devices()
    assert len(devs) == 1 and devs[0]["relay_type"] == "tasmota"


def test_restore_database_without_relay_type_gets_tasmota(tmp_path):
    path = str(tmp_path / "zonder-relay-type.db")
    make_db_without_relay_type(path)
    content = open(path, "rb").read()
    backup.restore(content, cfg_with(tmp_path / "backups"), "a")
    devs = devices.list_devices()
    assert len(devs) == 1 and devs[0]["relay_type"] == "tasmota"


def test_restore_old_version_sets_relay_type(tmp_path):
    path = str(tmp_path / "old.db")
    make_old_db(path)
    content = open(path, "rb").read()
    backup.restore(content, cfg_with(tmp_path / "backups"), "a")
    assert {d["name"]: d["relay_type"] for d in devices.list_devices()} == {
        "Water": "tasmota", "Poort": "tasmota"}
