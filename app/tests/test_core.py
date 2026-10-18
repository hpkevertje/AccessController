import io
import time

import openpyxl
import pytest

from accesscontrol import db, devices, members, settings
from accesscontrol.engine import Engine
from accesscontrol.phone import PhoneError, normalize


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db.init(str(tmp_path / "t.db"))
    devices.create({"name": "Water", "serial_port": "socket://127.0.0.1:1", "tasmota_topic": "water",
                    "on_seconds": 1200}, True, "test")
    devices.create({"name": "Poort", "enabled": False, "tasmota_topic": "poort", "on_seconds": 1}, True, "test")
    yield


def W():
    return devices.by_name()["water"]["id"]


def G():
    return devices.by_name()["poort"]["id"]


def dstatus(eng, dev_id):
    return next(d for d in eng.status()["devices"] if d["id"] == dev_id)


# ---------- telefoon ----------

@pytest.mark.parametrize("raw", ["0470 12 34 56", "+32 470 12 34 56", "0032470123456",
                                 "32470123456", "0470/12.34.56", "32470123456.0"])
def test_normalize_be_mobile(raw):
    assert normalize(raw) == "+32470123456"


def test_normalize_empty_and_invalid():
    assert normalize("") is None
    assert normalize(None) is None
    with pytest.raises(PhoneError):
        normalize("abc")
    with pytest.raises(PhoneError):
        normalize("12")


def test_normalize_foreign():
    assert normalize("+31 6 12345678") == "+31612345678"


# ---------- leden ----------

def mk(no, name, phone, **kw):
    return members.create({"member_no": no, "name": name, "phone": phone, **kw}, "BE", "test@x")


def test_create_defaults_and_uniqueness():
    m = mk("1", "An", "0470123456")
    assert m["phone"] == "+32470123456"
    assert m["access"] == {W(): True, G(): True}
    with pytest.raises(members.ValidationError):
        mk("1", "Dubbel lidnr", "0494000001")
    with pytest.raises(members.ValidationError):
        mk("2", "Dubbel tel", "+32470123456")
    with pytest.raises(members.ValidationError):
        members.create({"member_no": "", "name": "x"}, "BE", "t")


def test_update_logs_diff():
    m = mk("1", "An", "0470123456")
    members.update(m["id"], {"access": {str(W()): False}}, "BE", "admin@x")
    ev = db.query("SELECT * FROM events WHERE reason='Lid gewijzigd'")
    assert ev and "Toegang Water: ja -> nee" in ev[0]["detail"] and ev[0]["actor"] == "admin@x"


def _xlsx(text):
    """Bouwt een xlsx uit 'a;b;c'-regels."""
    wb = openpyxl.Workbook()
    for line in text.strip("\n").split("\n"):
        wb.active.append(line.split(";"))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_upsert_keeps_missing():
    mk("1", "An", "0494000001")
    mk("2", "Bert", "0494000002")
    data = _xlsx("Lidnr;Naam;Telefoon;Toegang water;Toegang poort;Opmerking\n"
                "1;An Peeters;0494 00 00 01;ja;nee;\n"
                "3;Cis;0494000003;;;nieuw\n")
    r = members.import_file("leden.xlsx", data, "BE", "a@x")
    assert r == {"nieuw": 1, "gewijzigd": 1, "ongewijzigd": 0, "niet_in_bestand": 1}
    by = {m["member_no"]: m for m in members.list_members()}
    assert by["1"]["name"] == "An Peeters" and by["1"]["access"][G()] is False
    assert by["2"]["name"] == "Bert"                       # behouden
    assert by["3"]["access"] == {W(): True, G(): True}   # standaard ja


def test_import_rejects_whole_file_on_error():
    mk("1", "An", "0494000001")
    data = _xlsx("Lidnr;Naam;Telefoon\n1;An nieuw;0494000001\n2;Bert;onzin\n")
    with pytest.raises(members.ValidationError) as e:
        members.import_file("x.xlsx", data, "BE", "a@x")
    assert any("Rij 3" in x for x in e.value.errors)
    assert members.list_members()[0]["name"] == "An"       # niets gewijzigd


def test_import_duplicate_phone_and_lidnr():
    mk("9", "Zed", "0494000009")
    data = _xlsx("Lidnr;Naam;Telefoon\n1;A;0494000001\n1;B;0494000002\n2;C;0494000009\n")
    with pytest.raises(members.ValidationError) as e:
        members.import_file("x.xlsx", data, "BE", "a@x")
    text = " ".join(e.value.errors)
    assert "staat ook op rij" in text and "+32494000009" in text


def test_import_swap_phones():
    mk("1", "A", "0494000001")
    mk("2", "B", "0494000002")
    data = _xlsx("Lidnr;Telefoon\n1;0494000002\n2;0494000001\n")
    members.import_file("x.xlsx", data, "BE", "a@x")
    by = {m["member_no"]: m["phone"] for m in members.list_members()}
    assert by == {"1": "+32494000002", "2": "+32494000001"}


def test_import_unknown_column_rejected():
    with pytest.raises(members.ValidationError):
        members.import_file("x.xlsx", _xlsx("Lidnr;Naam;Kleur\n1;A;rood\n"), "BE", "a@x")


def test_export_import_roundtrip_xlsx():
    mk("1", "An", "0494000001", note="sleutel", access={G(): False})
    mk("2", "Bert", None, access={W(): False})
    xlsx = members.export_xlsx()
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    assert [c.value for c in wb.active[1]] == ["Lidnr", "Naam", "Telefoon", "Toegang Water",
                                              "Toegang Poort", "Opmerking"]
    r = members.import_file("leden.xlsx", xlsx, "BE", "a@x")
    assert r["ongewijzigd"] == 2 and r["gewijzigd"] == 0


def test_import_rejects_csv():
    with pytest.raises(members.ValidationError):
        members.import_file("leden.csv", b"Lidnr;Naam\n1;A\n", "BE", "a@x")


# ---------- engine ----------

class FakeInfo:
    rc = 0


class FakeMqtt:
    def __init__(self):
        self.sent = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.sent.append((topic, payload, qos, retain))
        return FakeInfo()

    def subscribe(self, topic, qos=0):
        self.sent.append(("SUB", topic, qos, False))

    def unsubscribe(self, topic):
        self.sent.append(("UNSUB", topic, 0, False))


@pytest.fixture
def eng():
    e = Engine()
    e.mqtt = FakeMqtt()
    e.mqtt_connected = True
    return e


def test_call_allowed_publishes_and_dedupes(eng):
    mk("1", "An", "0470123456")
    eng.handle_line(W(), "g_RecPhoneNo:32470123456")
    eng.handle_line(W(), "Call Phonenumber:32470123456 Len=11")
    eng.handle_line(W(), "not this tel.")
    eng.handle_line(W(), "Call Phonenumber:32470123456 Len=11")   # binnen 5 s: ontdubbeld
    assert len(eng.mqtt.sent) == 1
    topic, payload, qos, retain = eng.mqtt.sent[0]
    assert (topic, payload, retain) == ("cmnd/water/POWER", "ON", False)
    ev = db.query("SELECT * FROM events WHERE category='oproep'")
    assert len(ev) == 1 and ev[0]["result"] == "toegelaten" and ev[0]["member_no"] == "1"


def test_call_retrigger_after_dedupe(eng):
    mk("1", "An", "0470123456")
    eng.devices[W()]["dedupe_seconds"] = 0
    eng.handle_call(W(), "32470123456")
    eng.handle_call(W(), "32470123456")
    assert len(eng.mqtt.sent) == 2


@pytest.mark.parametrize("setup,reason", [
    (None, "Onbekend nummer"),
    ({"access": "water-uit"}, "Geen toegang tot dit toestel"),
])
def test_call_denied(eng, setup, reason):
    if setup is not None:
        mk("1", "An", "0470123456", access={W(): False})
    assert eng.handle_call(W(), "32470123456") == "geweigerd"
    assert not eng.mqtt.sent
    assert db.query("SELECT reason FROM events WHERE category='oproep'")[0]["reason"] == reason


def test_gate_access_separate(eng):
    mk("1", "An", "0470123456", access={W(): False})
    eng.devices[G()]["enabled"] = True
    assert eng.handle_call(G(), "32470123456") == "toegelaten"
    assert eng.mqtt.sent[0][:2] == ("cmnd/poort/POWER", "ON")


def test_mqtt_down_logged_as_error(eng):
    mk("1", "An", "0470123456")
    eng.mqtt_connected = False
    assert eng.handle_call(W(), "32470123456") == "fout"


def test_gsm_state_changes_logged_once(eng):
    for line in ["InitGsm...", "not reg", "not reg", "InitOk"]:
        eng.handle_line(W(), line)
    reasons = [e["reason"] for e in db.query("SELECT reason FROM events WHERE reason LIKE 'GSM:%' ORDER BY id")]
    assert reasons == ["GSM: initialiseren", "GSM: niet geregistreerd", "GSM: ok"]
    assert eng.state[W()].gsm == "ok"


class Msg:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload.encode()


def test_power_on_confirms_and_result_sets_remaining(eng):
    mk("1", "An", "0470123456")
    eng.handle_call(W(), "32470123456")
    eng._on_message(None, None, Msg("stat/water/POWER", "ON"))
    ev = db.query_one("SELECT confirmed_at FROM events WHERE category='oproep'")
    assert ev["confirmed_at"]
    eng._on_message(None, None, Msg("stat/water/RESULT", '{"PulseTime1":{"Set":1300,"Remaining":1250}}'))
    st = dstatus(eng, W())
    assert st["relay"] == "on" and 1145 <= st["relay_remaining_s"] <= 1150
    eng._on_message(None, None, Msg("stat/water/POWER", "OFF"))
    assert db.query("SELECT * FROM events WHERE reason='Relais uit'")


def sent(eng):
    return [(t, p) for t, p, *_ in eng.mqtt.sent]


def test_lwt_online_only_queries(eng):
    eng._on_message(None, None, Msg("tele/water/LWT", "Online"))
    assert sent(eng) == [("cmnd/water/PulseTime1", ""), ("cmnd/water/PowerOnState", ""), ("cmnd/water/POWER", "")]
    assert eng.state[W()].esp == "online"


def test_pulsetime_set_only_when_different_and_relay_off(eng):
    eng._on_message(None, None, Msg("stat/water/RESULT", '{"PulseTime1":{"Set":1300,"Remaining":0}}'))
    assert sent(eng) == []                                   # gelijk: niets sturen
    eng._on_message(None, None, Msg("stat/water/RESULT", '{"PulseTime1":{"Set":0,"Remaining":0}}'))
    assert sent(eng) == [("cmnd/water/PulseTime1", "1300")]  # relais uit en verschillend: instellen


def test_pulsetime_not_touched_while_relay_on(eng):
    """Bug: opslaan van de configuratie terwijl het relais aftelt, mocht de teller niet herstarten."""
    eng._on_message(None, None, Msg("stat/water/POWER", "ON"))
    eng.devices[W()]["on_seconds"] = 600
    eng._on_message(None, None, Msg("stat/water/RESULT", '{"PulseTime1":{"Set":1300,"Remaining":900}}'))
    assert ("cmnd/water/PulseTime1", "700") not in sent(eng)
    eng._on_message(None, None, Msg("stat/water/POWER", "OFF"))
    assert sent(eng)[-1] == ("cmnd/water/PulseTime1", "700")


def test_poweronstate_corrected(eng):
    eng._on_message(None, None, Msg("stat/water/RESULT", '{"PowerOnState":3}'))
    assert sent(eng) == [("cmnd/water/PowerOnState", "0")]
    eng.mqtt.sent.clear()
    eng._on_message(None, None, Msg("stat/water/RESULT", '{"PowerOnState":0}'))
    assert sent(eng) == []


def test_tele_state_sets_relay(eng):
    eng._on_message(None, None, Msg("tele/water/STATE", '{"Time":"x","POWER":"ON"}'))
    assert eng.state[W()].relay == "on"


@pytest.mark.parametrize("sec,val", [(1, 10), (11, 110), (12, 112), (1200, 1300), (64800, 64900)])
def test_pulsetime_encoding(sec, val):
    from accesscontrol.engine import decode_pulsetime, encode_pulsetime
    assert encode_pulsetime(sec) == val
    assert decode_pulsetime(val) == sec


def test_purge_events():
    db.execute("DELETE FROM events")
    db.execute("INSERT INTO events (ts, category) VALUES ('2020-01-01T00:00:00Z', 'oproep')")
    db.log_event("oproep")
    assert db.purge_events(24) == 1
    assert len(db.query("SELECT * FROM events")) == 1


def test_config_validation():
    cfg = settings.load()
    cfg["backup"]["time"] = "25:00"
    cfg["mqtt"]["port"] = 0
    with pytest.raises(settings.ConfigError) as e:
        settings.save(cfg)
    assert len(e.value.args[0]) == 2


# ---------- SMS ----------

JUNK = b"\xb1860000000000000\xb1\xb1T;.6B+32470123456"


def feed(eng, *lines):
    for raw in lines:
        eng.handle_raw(W(), raw)


def test_sms_logged_and_junk_cut(eng):
    mk("1", "An", "0470123456")
    feed(eng, b"newsms come", b"", b"Have 1 sms", b"Read sms 1", b"del sms 1", b"sms Analy",
         b"SMS From TEL:+32470123456",
         b"Hello, uw krediet is bijna op. Ga naar een shop om te kijke" + JUNK,
         b"     = r\xb1 \xb1A(\xb1\xb1", b"\xb12", b"newsms come")
    ev = db.query("SELECT * FROM events WHERE category='sms'")
    assert len(ev) == 1
    assert ev[0]["detail"] == "Hello, uw krediet is bijna op. Ga naar een shop om te kijke"
    assert ev[0]["actor"] == "+32470123456" and ev[0]["member_no"] == "1"
    assert dstatus(eng, W())["last_sms"]["text"].startswith("Hello")


def test_sms_password_masked(eng):
    feed(eng, b"SMS From TEL:+32470123456", b"1234P4321", b"newsms come")
    feed(eng, b"SMS From TEL:+32470123456", b"1234TEL0032470999888#", b"newsms come")
    ev = db.query("SELECT reason, detail FROM events WHERE category='sms' ORDER BY id")
    assert [e["detail"] for e in ev] == ["****P****", "****TEL0032470999888#"]
    assert ev[0]["reason"] == "SMS-commando ontvangen"


HDR = [b"newsms come", b"", b"Have 1 sms", b"Read sms 1", b"del sms 1", b"sms Analy",
       b"SMS From TEL:+32470123456"]


def sms_events():
    return db.query("SELECT result, reason, detail FROM events WHERE category='sms' ORDER BY id")


def test_sms_pwd_change_reply_masked(eng):
    feed(eng, *HDR, b"1234#PWD4321#PWD4321#", b"", b"password ok",
         b"resmsdat:Password modified OK:4321smsphone:+32470123456    resmsdat:Password modified OK:4321"
         b"ReplyBuf:Password modified OK:4321",
         b"RESMSOK", b"newsms come")
    ev = sms_events()
    assert len(ev) == 1
    assert ev[0]["detail"] == "****#PWD****#PWD****#\nAntwoord: Password modified OK:**** (verzonden)"
    assert "4321" not in ev[0]["detail"]


def test_sms_tel_reply(eng):
    feed(eng, *HDR, b"4321#TEL0032470123456#001#", b"", b"password ok", b"Savetel:0032470123456  NO=1",
         b"resmsdat:TEL:001:0032470123456smsphone:+32470123456    resmsdat:TEL:001:0032470123456"
         b"ReplyBuf:TEL:001:0032470123456", b"RESMSOK")
    assert sms_events()[0]["detail"] == "****#TEL0032470123456#001#\nAntwoord: TEL:001:0032470123456 (verzonden)"


def test_sms_wrong_password_flagged(eng):
    feed(eng, *HDR, b"1234#TEL00321234123412#002#", b"ReplyBuf:Password Error", b"RESMSOK")
    ev = sms_events()[0]
    assert ev["result"] == "fout" and ev["detail"].endswith("Antwoord: Password Error (verzonden)")


def test_sms_no_reply(eng):
    feed(eng, *HDR, b"1234EE", *HDR, b"hallo", b"newsms come")
    ev = sms_events()
    assert [e["detail"] for e in ev] == ["****EE", "hallo"]


def test_sms_reply_not_confirmed(eng):
    feed(eng, *HDR, b"1234#PWD5555#PWD5555#", b"ReplyBuf:Password modified OK:5555")
    eng.state[W()].sms_pending["t"] -= 30
    eng.tick(W())
    assert sms_events()[0]["detail"].endswith("(niet bevestigd)")


def test_sms_flushed_after_silence(eng, monkeypatch):
    feed(eng, b"SMS From TEL:Proximus", b"Uw saldo is 1,20 EUR.")
    assert not db.query("SELECT * FROM events WHERE category='sms'")
    eng.state[W()].sms_pending["t"] -= 5
    eng.tick(W())
    ev = db.query("SELECT actor, phone, detail FROM events WHERE category='sms'")
    assert ev == [{"actor": "Proximus", "phone": None, "detail": "Uw saldo is 1,20 EUR."}]


def test_sms_multiline_clean_text(eng):
    feed(eng, b"SMS From TEL:+32470123456", b"regel 1", b"regel 2", b"newsms come")
    assert db.query_one("SELECT detail FROM events WHERE category='sms'")["detail"] == "regel 1\nregel 2"


def test_call_after_sms_still_works(eng):
    mk("1", "An", "0470123456")
    feed(eng, b"SMS From TEL:+32470123456", b"test", b"Call Phonenumber:32470123456 Len=11")
    assert len(db.query("SELECT * FROM events WHERE category='sms'")) == 1
    assert db.query_one("SELECT result FROM events WHERE category='oproep'")["result"] == "toegelaten"


def test_whitelisted_call_and_empty_sms(eng):
    mk("1", "An", "0470123456")
    feed(eng, b"g_RecPhoneNo:32470123456", b"Call Phonenumber:32470123456 Len=11", b"FindphoneID=1", b"",
         b"PhoneRelayOpen", b"RESETGSM", *HDR, b"", b"newsms come")
    rows = db.query("SELECT category, reason, phone, detail FROM events WHERE category != 'admin' ORDER BY id")
    assert [r["reason"] for r in rows] == ["Aan voor 20 min", "Nummer staat in de witte lijst van de RTU",
                                           "Lege SMS ontvangen"]
    assert rows[1]["phone"] == "+32470123456" and "#TEL#001#" in rows[1]["detail"]
    assert eng.state[W()].last_sms is None


def test_reload_devices_keeps_mqtt_connection(eng):
    client = eng.mqtt
    eng.subscribed = eng._wanted_topics()
    new = devices.create({"name": "Slagboom", "tasmota_topic": "slagboom", "serial_port": "socket://127.0.0.1:2"},
                         False, "a")
    eng.reload_devices()
    try:
        assert eng.mqtt is client                       # geen herverbinding
        assert ("SUB", "stat/slagboom/+", 1, False) in eng.mqtt.sent
        assert ("cmnd/slagboom/PulseTime1", "", 1, False) in eng.mqtt.sent
        assert not any(t[1] == "cmnd/water/PulseTime1" for t in eng.mqtt.sent)   # water ongemoeid
        devices.update(new["id"], {"enabled": False}, "a")
        eng.reload_devices()
        assert ("UNSUB", "stat/slagboom/+", 0, False) in eng.mqtt.sent
    finally:
        eng.stop()
