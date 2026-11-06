"""Shelly 1 Gen3 via RPC over MQTT: abonnementen, schakelen, status en configuratie."""
import json
import time

import pytest

from accesscontrol import db, devices
from accesscontrol.engine import Engine
from accesscontrol.relays import remaining_from_timer

PREFIX = "shelly1g3-d0cf13dde9dc"
CLIENT = "accesscontrol-server"
REPLY = f"{CLIENT}/rpc"


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


class Msg:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload.encode()


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db.init(str(tmp_path / "t.db"))
    devices.create({"name": "Shelly", "relay_type": "shelly", "tasmota_topic": PREFIX,
                    "serial_port": "socket://127.0.0.1:3", "on_seconds": 1200}, True, "test")
    yield


@pytest.fixture
def eng(fresh_db):
    e = Engine()
    e.mqtt = FakeMqtt()
    e.mqtt_connected = True
    return e


def S():
    return devices.by_name()["shelly"]["id"]


def sent(eng):
    return [(t, p) for t, p, *_ in eng.mqtt.sent]


def rpc_frames(eng, method=None):
    out = []
    for topic, payload, *_ in eng.mqtt.sent:
        if topic == f"{PREFIX}/rpc":
            frame = json.loads(payload)
            if method is None or frame.get("method") == method:
                out.append(frame)
    return out


def reply(eng, call_id, result=None, error=None):
    frame = {"id": call_id, "src": PREFIX, "dst": CLIENT}
    if error is not None:
        frame["error"] = error
    else:
        frame["result"] = {} if result is None else result
    eng._on_message(None, None, Msg(REPLY, json.dumps(frame)))


def notify(eng, switch, ts):
    payload = {"src": PREFIX, "dst": f"{PREFIX}/events", "method": "NotifyStatus",
               "params": {"ts": ts, "switch:0": switch}}
    eng._on_message(None, None, Msg(f"{PREFIX}/events/rpc", json.dumps(payload)))


def test_subscriptions_and_unsubscribe(eng):
    eng._sync_subscriptions()
    assert ("SUB", f"{PREFIX}/online", 1, False) in eng.mqtt.sent
    assert ("SUB", f"{PREFIX}/events/rpc", 1, False) in eng.mqtt.sent
    assert ("SUB", REPLY, 1, False) in eng.mqtt.sent

    devices.update(S(), {"enabled": False}, "test")
    eng.reload_devices()
    assert ("UNSUB", f"{PREFIX}/online", 0, False) in eng.mqtt.sent
    assert ("UNSUB", f"{PREFIX}/events/rpc", 0, False) in eng.mqtt.sent
    assert ("UNSUB", REPLY, 0, False) in eng.mqtt.sent


def test_send_on_en_off(eng):
    _, err = eng.send(S(), "on")
    assert not err
    assert eng.mqtt.sent[-1][0] == f"{PREFIX}/rpc"
    on = rpc_frames(eng, "Switch.Set")[-1]
    assert on["src"] == CLIENT
    assert on["params"] == {"id": 0, "on": True, "toggle_after": 1200}

    eng.send(S(), "off")
    off = rpc_frames(eng, "Switch.Set")[-1]
    assert off["params"] == {"id": 0, "on": False}


def test_set_reply_bevestigt_en_zet_restende_tijd(eng):
    cmd_id = eng.manual(S(), "on", "tester")
    request = rpc_frames(eng, "Switch.Set")[-1]
    reply(eng, request["id"], {"was_on": False})

    st = eng.state[S()]
    assert st.relay == "on"
    assert 1195 <= st.relay_until - time.time() <= 1201
    assert db.query_one("SELECT confirmed_at FROM events WHERE cmd_id=?", (cmd_id,))["confirmed_at"]


def test_tweede_aan_ververst_en_bevestigt_opnieuw(eng):
    first = eng.manual(S(), "on", "tester")
    reply(eng, rpc_frames(eng, "Switch.Set")[-1]["id"], {"was_on": False})
    st = eng.state[S()]
    st.relay_until = time.time() - 10

    second = eng.manual(S(), "on", "tester")
    request = rpc_frames(eng, "Switch.Set")[-1]
    reply(eng, request["id"], {"was_on": True})

    assert first != second
    assert st.relay == "on"
    assert st.relay_until > time.time() + 1190
    rows = db.query("SELECT confirmed_at FROM events WHERE cmd_id IN (?,?)", (first, second))
    assert len(rows) == 2 and all(r["confirmed_at"] for r in rows)


def test_notify_status_aan_en_uit_door_timer(eng):
    notify(eng, {"id": 0, "output": True, "source": "MQTT", "timer_duration": 10.00,
                 "timer_started_at": 1793923641.17}, 1793923641.17)
    st = eng.state[S()]
    assert st.relay == "on"
    assert 8 <= st.relay_until - time.time() <= 10
    assert not db.query("SELECT * FROM events WHERE reason='Relais uit'")

    notify(eng, {"id": 0, "output": False, "source": "timer", "timer_duration": None,
                 "timer_started_at": None}, 1793923651.17)
    assert st.relay == "off" and st.relay_until is None
    assert len(db.query("SELECT * FROM events WHERE reason='Relais uit'")) == 1


def test_notify_status_zonder_output_ververst_alleen_de_timer(eng):
    notify(eng, {"id": 0, "output": True, "source": "MQTT", "timer_duration": 10.00,
                 "timer_started_at": 1793923641.17}, 1793923641.17)
    st = eng.state[S()]
    st.relay_until = time.time() - 100

    notify(eng, {"id": 0, "timer_duration": 60.00, "timer_started_at": 1793924000.00}, 1793924000.00)
    assert st.relay == "on"
    assert 58 <= st.relay_until - time.time() <= 60


def test_online_offline_alleen_loggen_bij_wijziging_en_query(eng):
    st = eng.state[S()]
    st.esp = "offline"
    eng._on_message(None, None, Msg(f"{PREFIX}/online", "true"))
    reasons = [e["reason"] for e in db.query("SELECT reason FROM events WHERE reason LIKE 'Relaismodule %'")]
    assert reasons == ["Relaismodule online"]
    assert [f["method"] for f in rpc_frames(eng)] == ["Switch.GetStatus", "Switch.GetConfig"]

    eng._on_message(None, None, Msg(f"{PREFIX}/online", "true"))
    assert len(db.query("SELECT * FROM events WHERE reason LIKE 'Relaismodule %'")) == 1

    eng._on_message(None, None, Msg(f"{PREFIX}/online", "false"))
    assert st.esp == "offline"
    reasons = [e["reason"] for e in db.query("SELECT reason FROM events WHERE reason LIKE 'Relaismodule %' ORDER BY id")]
    assert reasons == ["Relaismodule online", "Relaismodule offline"]


def config_reply(eng, cfg):
    eng.query_relay(S())
    request = rpc_frames(eng, "Switch.GetConfig")[-1]
    eng.mqtt.sent.clear()
    reply(eng, request["id"], cfg)


def test_config_sync_stuurt_een_keer_als_ze_verschilt(eng):
    eng.state[S()].relay = "off"
    config_reply(eng, {"id": 0, "auto_off": False, "auto_off_delay": 60,
                       "initial_state": "match_input"})
    configs = rpc_frames(eng, "Switch.SetConfig")
    assert len(configs) == 1
    assert configs[0]["params"] == {"id": 0, "config": {
        "auto_off": True, "auto_off_delay": 1200, "initial_state": "off"}}


def test_config_sync_identiek_stuurt_niets(eng):
    eng.state[S()].relay = "off"
    config_reply(eng, {"id": 0, "auto_off": True, "auto_off_delay": 1200, "initial_state": "off"})
    assert rpc_frames(eng, "Switch.SetConfig") == []


def test_config_sync_initial_state_match_input_stuurt(eng):
    eng.state[S()].relay = "off"
    config_reply(eng, {"id": 0, "auto_off": True, "auto_off_delay": 1200,
                       "initial_state": "match_input"})
    assert len(rpc_frames(eng, "Switch.SetConfig")) == 1


def test_config_sync_wacht_tot_relais_uit_is(eng):
    st = eng.state[S()]
    st.relay = "on"
    config_reply(eng, {"id": 0, "auto_off": False, "auto_off_delay": 60,
                       "initial_state": "match_input"})
    assert rpc_frames(eng, "Switch.SetConfig") == []
    assert st.pulse_pending is True

    notify(eng, {"id": 0, "output": False, "source": "MQTT", "timer_duration": None,
                 "timer_started_at": None}, 1793923651.17)
    assert st.pulse_pending is False
    assert len(rpc_frames(eng, "Switch.SetConfig")) == 1


def test_config_sync_wacht_bij_onbekende_toestand(eng):
    st = eng.state[S()]
    assert st.relay is None
    config_reply(eng, {"id": 0, "auto_off": False, "auto_off_delay": 60,
                       "initial_state": "match_input"})
    assert rpc_frames(eng, "Switch.SetConfig") == []
    assert st.pulse_pending is True


def test_foutantwoord_logt_en_verandert_niets(eng):
    eng.manual(S(), "on", "tester")
    request = rpc_frames(eng, "Switch.Set")[-1]
    reply(eng, request["id"], error={"code": -105, "message": "Out of range"})

    ev = db.query_one("SELECT result, reason, detail FROM events WHERE result='fout'")
    assert ev["reason"] == "Shelly: Switch.Set mislukt"
    assert "-105" in ev["detail"] and "Out of range" in ev["detail"]
    assert eng.state[S()].relay is None


def test_onbekend_id_wordt_genegeerd(eng):
    before = len(db.query("SELECT * FROM events"))
    reply(eng, 999999, {"was_on": False})
    assert len(db.query("SELECT * FROM events")) == before
    assert eng.state[S()].relay is None


def test_reload_devices_vraagt_alleen_het_nieuwe_toestel_op(fresh_db):
    devices.create({"name": "Tasmota", "relay_type": "tasmota", "tasmota_topic": "water",
                    "enabled": False, "serial_port": "socket://127.0.0.1:4"}, True, "test")
    eng = Engine()
    eng.mqtt = FakeMqtt()
    eng.mqtt_connected = True
    eng._start_serial = lambda only=None: None
    eng.subscribed = eng._wanted_topics()
    eng.mqtt.sent.clear()

    new = devices.create({"name": "Shelly 2", "relay_type": "shelly",
                          "tasmota_topic": "shelly1g3-abc", "serial_port": "socket://127.0.0.1:5",
                          "on_seconds": 60}, True, "test")
    eng.reload_devices()

    assert ("SUB", "shelly1g3-abc/online", 1, False) in eng.mqtt.sent
    assert ("SUB", "shelly1g3-abc/events/rpc", 1, False) in eng.mqtt.sent
    frames = [json.loads(p) for t, p, *_ in eng.mqtt.sent if t == "shelly1g3-abc/rpc"]
    assert [f["method"] for f in frames] == ["Switch.GetStatus", "Switch.GetConfig"]
    assert not any(t.startswith("cmnd/water") for t, *_ in eng.mqtt.sent)

    eng.mqtt.sent.clear()
    devices.update(new["id"], {"relay_type": "tasmota"}, "test")
    eng.reload_devices()
    assert ("cmnd/shelly1g3-abc/PulseTime1", "") in sent(eng)


@pytest.mark.parametrize("switch,now,expected", [
    ({"timer_started_at": 1000, "timer_duration": 60}, 1030, 30),
    ({"timer_started_at": None, "timer_duration": 60}, 1030, None),
    ({"timer_duration": 60}, 1030, None),
    ({"timer_started_at": 1000, "timer_duration": 60}, 500, None),
    ({"timer_started_at": 1000, "timer_duration": 0}, 1000, None),
])
def test_remaining_from_timer(switch, now, expected):
    assert remaining_from_timer(switch, now) == expected
