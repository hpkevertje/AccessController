import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("ENGINE_DISABLED", "true")
    from accesscontrol import auth, db, main
    monkeypatch.setattr(auth, "AUTH_DISABLED", True)
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "api.db"))
    with TestClient(main.app) as c:
        yield c, db


def test_sms_unread_and_seen(client):
    c, db = client
    assert c.get("/api/status").json()["sms_unread"]["count"] == 0
    db.log_event("sms", device="water", actor="Proximus", detail="Uw krediet is bijna op")
    db.log_event("sms", device="water", actor="+32470123456", detail="test")
    u = c.get("/api/status").json()["sms_unread"]
    assert u["count"] == 2 and u["newest"]["detail"] == "test"
    assert c.post("/api/sms/seen").json()["ok"]
    assert c.get("/api/status").json()["sms_unread"]["count"] == 0
    assert db.query("SELECT * FROM events WHERE reason='SMS gelezen'")
    db.log_event("sms", device="water", actor="Proximus", detail="nog een")
    assert c.get("/api/status").json()["sms_unread"]["count"] == 1


def test_empty_sms_not_unread(client):
    c, db = client
    db.log_event("sms", device="water", actor="+32470123456", reason="Lege SMS ontvangen", detail="(leeg)")
    assert c.get("/api/status").json()["sms_unread"]["count"] == 0


def test_sharepoint_test_endpoint(client, monkeypatch):
    c, db = client
    from accesscontrol import main
    monkeypatch.setattr(main.sharepoint, "diagnose",
                        lambda cfg: {"ok": True, "steps": [{"step": "configuratie", "ok": True,
                                                           "detail": "ok"}]})
    r = c.post("/api/backup/sharepoint/test")
    assert r.status_code == 200 and r.json()["ok"]
    assert db.query_one("SELECT result FROM events WHERE reason='SharePoint-test'")["result"] == "ok"


def test_ecaptain_sync_api(client):
    c, _ = client
    csv = b"Lidnr;Naam;Mobiel\n1;An;0470123456\n"

    r = c.post("/api/ecaptain/sync?dry_run=1", files={"file": ("e.csv", csv, "text/csv")})
    assert r.status_code == 200 and r.json()["dry_run"] is True and r.json()["nieuw"] == 1
    assert c.get("/api/members").json() == []

    r = c.post("/api/ecaptain/sync", files={"file": ("e.csv", csv, "text/csv")})
    assert r.status_code == 200 and r.json()["nieuw"] == 1
    member = c.get("/api/members").json()[0]
    assert member["source"] == "ecaptain" and member["active"] is True
    assert c.get("/api/ecaptain/status").json()["last"]["nieuw"] == 1


def test_ecaptain_sync_api_rejects_unknown_report(client):
    c, _ = client
    r = c.post("/api/ecaptain/sync",
               files={"file": ("x.csv", b"Kleur;Aantal\nrood;3\n", "text/csv")})
    assert r.status_code == 422 and r.json()["errors"]


def test_devices_api_relay_type(client):
    c, _ = client
    r = c.post("/api/devices", json={"name": "Shelly", "enabled": False, "relay_type": "shelly",
                                     "tasmota_topic": "shelly1g3-api", "on_seconds": 120,
                                     "grant_all": False})
    assert r.status_code == 200
    dev = r.json()
    assert dev["relay_type"] == "shelly"

    assert c.get("/api/devices").json()[0]["relay_type"] == "shelly"
    status = c.get("/api/status").json()["devices"]
    assert next(d for d in status if d["id"] == dev["id"])["relay_type"] == "shelly"

    r = c.put(f"/api/devices/{dev['id']}", json={"relay_type": "tasmota"})
    assert r.status_code == 200 and r.json()["relay_type"] == "tasmota"
