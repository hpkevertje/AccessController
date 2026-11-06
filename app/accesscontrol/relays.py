"""Relaismodules via MQTT: één driver per type.

- TasmotaDriver: Tasmota (cmnd/stat/tele-topics).
- ShellyDriver: Shelly 1 Gen3 (RPC over MQTT).

De Engine beslist (toegang, ontdubbeling, logboek, bevestiging van commando's) en kent geen protocol.
Een driver vertaalt: welke topics, hoe vragen we de status, hoe schakelen we en wat betekent een bericht.
Wijzigingen meldt de driver terug via Engine._apply_relay() (aan/uit en resterende tijd) en
Engine._on_online() (module online/offline).
"""
import itertools
import json
import threading
import time

from . import db


def dur(s: int) -> str:
    s = int(s)
    if s < 60:
        return f"{s} s"
    if s % 60 == 0:
        return f"{s // 60} min"
    return f"{s // 60} min {s % 60} s"


def encode_pulsetime(seconds: int) -> int:
    """Tasmota PulseTime: 1..111 = 0,1 s-stappen, 112..64900 = seconden + 100."""
    seconds = int(seconds)
    return seconds * 10 if seconds * 10 <= 111 else seconds + 100


def decode_pulsetime(value: int) -> float:
    return value / 10 if value <= 111 else value - 100


class RelayDriver:
    """Interface van een relaismodule. `eng` is de Engine; `d` is het toestel (dict uit devices.py)."""

    type = ""
    topic_label = ""        # naam van het topic-veld in meldingen

    def __init__(self, eng):
        self.eng = eng

    def topics(self, d: dict) -> set[str]:
        """MQTT-topics waarop dit toestel moet luisteren."""
        raise NotImplementedError

    def query(self, dev_id: int, d: dict) -> None:
        """Vraagt status en instellingen op. Instellen gebeurt pas bij het antwoord."""
        raise NotImplementedError

    def send(self, dev_id: int, d: dict, action: str) -> str:
        """Schakelt 'on' (met de aan-tijd van het toestel) of 'off'. Geeft een foutmelding of ''."""
        raise NotImplementedError

    def poll(self, dev_id: int, d: dict) -> None:
        """Vraagt de resterende tijd op (de Engine roept dit elke 10 s aan zolang het relais aan is)."""
        raise NotImplementedError

    def on_relay_off(self, dev_id: int, d: dict) -> None:
        """Het relais is uit: hier kan een uitgestelde instelling toegepast worden."""

    def on_message(self, topic: str, payload: str) -> None:
        """Verwerkt een MQTT-bericht voor alle toestellen van dit type."""
        raise NotImplementedError


# ---------------------------------------------------------------------------------------------
# Tasmota
# ---------------------------------------------------------------------------------------------

class TasmotaDriver(RelayDriver):
    """Per toestel een Tasmota-relaismodule met MQTT-topic <t> (standaard FullTopic %prefix%/%topic%/):

      cmnd/<t>/POWER ON|OFF        schakelen (ON herstart ook PulseTime)
      cmnd/<t>/PulseTime1 <n>      duur instellen; leeg = opvragen (antwoord op stat/<t>/RESULT)
      cmnd/<t>/PowerOnState 0      na stroomuitval altijd uit
      stat/<t>/POWER               relaisstatus na elke wijziging
      tele/<t>/STATE               periodieke status (bevat POWER)
      tele/<t>/LWT                 Online / Offline (retained)
    """

    type = "tasmota"
    topic_label = "Tasmota-topic"

    def topics(self, d):
        t = d["tasmota_topic"]
        return {f"stat/{t}/+", f"tele/{t}/LWT", f"tele/{t}/STATE"}

    def query(self, dev_id, d):
        """Vraagt PulseTime, PowerOnState en relaisstatus op. Instellen gebeurt pas bij het antwoord,
        en alleen als de waarde verschilt (PulseTime nooit terwijl het relais aan is)."""
        t = d["tasmota_topic"]
        self.eng._publish(f"cmnd/{t}/PulseTime1", "")
        self.eng._publish(f"cmnd/{t}/PowerOnState", "")
        self.eng._publish(f"cmnd/{t}/POWER", "")

    def send(self, dev_id, d, action):
        return self.eng._publish(f"cmnd/{d['tasmota_topic']}/POWER", "ON" if action == "on" else "OFF")

    def poll(self, dev_id, d):
        self.eng._publish(f"cmnd/{d['tasmota_topic']}/PulseTime1", "")

    def on_relay_off(self, dev_id, d):
        if self.eng.state[dev_id].pulse_pending:
            self._set_pulsetime(dev_id, d)

    def on_message(self, topic, payload):
        for dev_id, d in self.eng.devices_of(self.type):
            t = d["tasmota_topic"]
            if topic == f"tele/{t}/LWT":
                new = payload.lower() if payload.lower() in ("online", "offline") else "onbekend"
                self.eng._on_online(dev_id, d, new)
            elif topic in (f"stat/{t}/POWER", f"stat/{t}/POWER1"):
                self._on_power(dev_id, d, payload)
            elif topic == f"tele/{t}/STATE":
                data = json.loads(payload or "{}")
                p = data.get("POWER", data.get("POWER1"))
                if p:
                    self._on_power(dev_id, d, p)
            elif topic == f"stat/{t}/RESULT":
                self._on_result(dev_id, d, json.loads(payload or "{}"))

    def _on_power(self, dev_id, d, payload):
        relay = {"ON": "on", "OFF": "off"}.get(payload.strip().upper())
        if relay:
            self.eng._apply_relay(dev_id, d, relay)

    def _on_result(self, dev_id, d, data):
        st = self.eng.state[dev_id]
        pt = data.get("PulseTime1")
        if isinstance(pt, dict):
            if "Remaining" in pt:
                rem = decode_pulsetime(int(pt["Remaining"]))
                if st.relay == "on" and rem > 0:
                    st.relay_until = time.time() + rem
            if "Set" in pt and int(pt["Set"]) != encode_pulsetime(d["on_seconds"]):
                if st.relay == "on":
                    st.pulse_pending = True       # niet onderbreken: pas instellen als het relais uit is
                else:
                    self._set_pulsetime(dev_id, d)
        if "PowerOnState" in data and str(data["PowerOnState"]) != "0":
            self.eng._publish(f"cmnd/{d['tasmota_topic']}/PowerOnState", "0")

    def _set_pulsetime(self, dev_id, d):
        st = self.eng.state[dev_id]
        st.pulse_pending = False
        value = encode_pulsetime(d["on_seconds"])
        if st.pulse_sent and st.pulse_sent[0] == value and time.time() - st.pulse_sent[1] < 15:
            return                                  # net al verstuurd (dubbel antwoord op een vraag)
        st.pulse_sent = (value, time.time())
        self.eng._publish(f"cmnd/{d['tasmota_topic']}/PulseTime1", str(encode_pulsetime(d["on_seconds"])))
        db.log_event("systeem", device=d, result="info", reason="PulseTime ingesteld op de relaismodule",
                     detail=f"{dur(d['on_seconds'])} (PulseTime1 {encode_pulsetime(d['on_seconds'])})")


# ---------------------------------------------------------------------------------------------
# Shelly 1 Gen3
# ---------------------------------------------------------------------------------------------

SWITCH_ID = 0
CALL_TTL_S = 60


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def remaining_from_timer(sw: dict, now_dev: float) -> float | None:
    """Resterende seconden uit timer_started_at + timer_duration, gemeten op de klok van de Shelly
    (now_dev). None als er geen bruikbare timer is of de klokken niet kloppen."""
    started, duration = sw.get("timer_started_at"), sw.get("timer_duration")
    if not (_num(started) and _num(duration)) or duration <= 0:
        return None
    rem = started + duration - now_dev
    if rem <= 0 or rem > duration + 5:
        return None
    return rem


class ShellyDriver(RelayDriver):
    """Shelly 1 Gen3 met RPC over MQTT. Het Shelly-ID is de topic-prefix van de module
    (bv. shelly1g3-d0cf13dde9dc, zoals ingesteld bij het toestel):

      <p>/rpc            server > Shelly   {"id":n,"src":<client-id>,"method":...,"params":...}
      <client-id>/rpc    Shelly > server   antwoord (result of error), gekoppeld via het id
      <p>/events/rpc     Shelly > server   NotifyStatus met switch:0 (alleen de gewijzigde velden)
      <p>/online         Shelly > server   true / false (retained, LWT)

    Timeout: elk AAN-commando bevat toggle_after = aan-tijd; een herhaald AAN herstart de teller.
    Daarnaast staan auto_off en auto_off_delay op de module (zodat ook een lokale bediening uitgaat)
    en initial_state op 'off' (na stroomuitval blijft het relais uit). Die instellingen worden alleen
    aangepast als ze verschillen, en nooit terwijl het relais aan is of de toestand onbekend is.
    """

    type = "shelly"
    topic_label = "Shelly-ID"

    def __init__(self, eng):
        super().__init__(eng)
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._calls: dict[int, tuple] = {}      # id -> (dev_id, methode, verwachte toestand, tijdstip)

    # ---------- interface ----------

    def src(self) -> str:
        return self.eng.cfg["mqtt"]["client_id"]

    def reply_topic(self) -> str:
        return f"{self.src()}/rpc"

    def topics(self, d):
        p = d["tasmota_topic"]
        return {f"{p}/online", f"{p}/events/rpc", self.reply_topic()}

    def query(self, dev_id, d):
        self._call(dev_id, d, "Switch.GetStatus", {"id": SWITCH_ID})
        self._call(dev_id, d, "Switch.GetConfig", {"id": SWITCH_ID})

    def send(self, dev_id, d, action):
        if action == "on":
            params = {"id": SWITCH_ID, "on": True, "toggle_after": d["on_seconds"]}
        else:
            params = {"id": SWITCH_ID, "on": False}
        return self._call(dev_id, d, "Switch.Set", params, expect=action)

    def poll(self, dev_id, d):
        self._call(dev_id, d, "Switch.GetStatus", {"id": SWITCH_ID})

    def on_relay_off(self, dev_id, d):
        if self.eng.state[dev_id].pulse_pending:
            self._set_config(dev_id, d)

    def on_message(self, topic, payload):
        for dev_id, d in self.eng.devices_of(self.type):
            p = d["tasmota_topic"]
            if topic == f"{p}/online":
                new = {"true": "online", "false": "offline"}.get(payload.strip().lower(), "onbekend")
                self.eng._on_online(dev_id, d, new)
            elif topic == f"{p}/events/rpc":
                self._on_notify(dev_id, d, payload)
        if topic == self.reply_topic():
            self._on_reply(payload)

    # ---------- RPC ----------

    def _call(self, dev_id, d, method, params, expect=None) -> str:
        """Publiceert een RPC-aanvraag. Geeft een foutmelding of ''."""
        cid = next(self._ids)
        now = time.time()
        with self._lock:
            self._calls = {k: v for k, v in self._calls.items() if now - v[3] < CALL_TTL_S}
            self._calls[cid] = (dev_id, method, expect, now)
        frame = {"id": cid, "src": self.src(), "method": method, "params": params}
        err = self.eng._publish(f"{d['tasmota_topic']}/rpc", json.dumps(frame))
        if err:
            with self._lock:
                self._calls.pop(cid, None)
        return err

    def _on_reply(self, payload):
        data = json.loads(payload or "{}")
        if not isinstance(data, dict):
            return
        with self._lock:
            call = self._calls.pop(data.get("id"), None)
        if call is None:
            return                                  # antwoord op iets dat niet van ons komt
        dev_id, method, expect, _ = call
        d = self.eng.devices.get(dev_id)
        if d is None or dev_id not in self.eng.state:
            return
        err = data.get("error")
        if err:
            code = err.get("code") if isinstance(err, dict) else None
            msg = err.get("message") if isinstance(err, dict) else err
            db.log_event("systeem", device=d, result="fout", reason=f"Shelly: {method} mislukt",
                         detail=f"{code}: {msg}")
            return
        result = data.get("result")
        result = result if isinstance(result, dict) else {}
        if method == "Switch.Set":
            # De module heeft het commando uitgevoerd: dat bevestigt het commando ook als de toestand
            # niet verandert (een herhaald AAN levert geen aan/uit-wijziging op).
            if expect == "on":
                self.eng._apply_relay(dev_id, d, "on", remaining=d["on_seconds"])
            else:
                self.eng._apply_relay(dev_id, d, "off")
        elif method == "Switch.GetStatus":
            self._apply_switch(dev_id, d, result, time.time(), from_poll=True)
        elif method == "Switch.GetConfig":
            self._check_config(dev_id, d, result)

    # ---------- status ----------

    def _on_notify(self, dev_id, d, payload):
        data = json.loads(payload or "{}")
        if not isinstance(data, dict) or data.get("method") != "NotifyStatus":
            return
        params = data.get("params") or {}
        sw = params.get(f"switch:{SWITCH_ID}")
        if not isinstance(sw, dict):
            return
        ts = params.get("ts")
        self._apply_switch(dev_id, d, sw, ts if _num(ts) else time.time())

    def _apply_switch(self, dev_id, d, sw, now_dev, from_poll=False):
        """sw: switch:0 uit een NotifyStatus (alleen gewijzigde velden) of uit Switch.GetStatus."""
        out = sw.get("output")
        rem = remaining_from_timer(sw, now_dev)
        if out is True:
            self.eng._apply_relay(dev_id, d, "on", remaining=rem, from_poll=from_poll)
        elif out is False:
            self.eng._apply_relay(dev_id, d, "off")
        elif rem is not None and self.eng.state[dev_id].relay == "on":
            self.eng._apply_relay(dev_id, d, "on", remaining=rem, from_poll=from_poll)   # teller herstart

    # ---------- instellingen ----------

    def _check_config(self, dev_id, d, cfg):
        st = self.eng.state[dev_id]
        delay = cfg.get("auto_off_delay")
        ok = (cfg.get("auto_off") is True and _num(delay) and abs(delay - d["on_seconds"]) < 0.01
              and cfg.get("initial_state") == "off")
        if ok:
            st.pulse_pending = False
        elif st.relay == "off":
            self._set_config(dev_id, d)
        else:
            st.pulse_pending = True       # relais aan of onbekend: pas instellen als het relais uit is

    def _set_config(self, dev_id, d):
        st = self.eng.state[dev_id]
        st.pulse_pending = False
        value = d["on_seconds"]
        if st.pulse_sent and st.pulse_sent[0] == value and time.time() - st.pulse_sent[1] < 15:
            return                                  # net al verstuurd (dubbel antwoord op een vraag)
        st.pulse_sent = (value, time.time())
        cfg = {"auto_off": True, "auto_off_delay": value, "initial_state": "off"}
        err = self._call(dev_id, d, "Switch.SetConfig", {"id": SWITCH_ID, "config": cfg})
        if err:
            db.log_event("systeem", device=d, result="fout", reason="Auto-uit instellen op de relaismodule mislukt",
                         detail=err)
            return
        db.log_event("systeem", device=d, result="info", reason="Auto-uit ingesteld op de relaismodule",
                     detail=f"{dur(value)} (auto_off_delay {value} s), begintoestand uit")
