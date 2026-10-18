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
