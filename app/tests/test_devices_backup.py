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
            return {"webUrl": "https://contoso.sharepoint.com/x"}
        if "/children" in url:
            return {"value": [
                {"id": "1", "name": "accesscontrol-20200101-000000.db.gz", "createdDateTime": "2020-01-01T00:00:00Z"},
                {"id": "2", "name": "andere.docx", "createdDateTime": "2020-01-01T00:00:00Z"}]}
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


def test_sharepoint_without_secret_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.delenv("SHAREPOINT_CLIENT_SECRET", raising=False)
    cfg = cfg_with(tmp_path, enabled=True, tenant_id="t", client_id="c",
                   site_url="https://contoso.sharepoint.com/sites/IT")
    r = backup.run(cfg, actor="a")
    assert not r["ok"] and r["local"]["ok"] and "SHAREPOINT_CLIENT_SECRET" in r["sharepoint"]["error"]
