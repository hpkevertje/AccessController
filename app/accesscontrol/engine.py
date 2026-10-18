"""Kern: leest de RTU5024-debuglijn, beslist, schakelt Tasmota-relaismodules via MQTT.

RTU-debuglijn (38400 baud) bij een oproep:
    g_RecPhoneNo:32470123456
    Call Phonenumber:32470123456 Len=11
    not this tel.
Elk blok is een aparte oproep (de RTU hangt zelf op). Elke 'Call Phonenumber'-regel wordt
beslist en gelogd. Een korte ontdubbeling (standaard 5 s, 0 = uit) vangt dubbele regels op.
"""
import json
import logging
import re
import threading
import time
import uuid

import paho.mqtt.client as mqtt
import serial

from . import backup, db, devices, members, settings
from .phone import PhoneError, normalize

log = logging.getLogger(__name__)

RE_CALL = re.compile(r"Call Phonenumber:\s*([+\d]*)")
GSM_PATTERNS = [
    (re.compile(r"InitOk", re.I), "ok"),
    (re.compile(r"not reg", re.I), "niet geregistreerd"),
    (re.compile(r"no sim", re.I), "geen SIM"),
    (re.compile(r"InitGsm", re.I), "initialiseren"),
]

# SMS op de RTU-debuglijn:
#   newsms come / Have 1 sms / Read sms 1 / del sms 1 / sms Analy
#   SMS From TEL:+32470123456
#   <tekst>            (de RTU toont max. ~60 tekens, daarna rommel uit zijn geheugen)
RE_SMS_FROM = re.compile(r"SMS From TEL:\s*(\S*)")
# Regels waarmee de RTU een SMS-commando verwerkt en beantwoordt (horen niet bij de SMS-tekst):
#   password ok / Savetel:... / resmsdat:...smsphone:...ReplyBuf:<antwoord> / RESMSOK
RE_REPLY_BUF = re.compile(r"ReplyBuf:(.*)$")
RE_REPLY_OK = re.compile(r"RESMSOK")
RE_REPLY_LINE = re.compile(r"password ok|Savetel:|resmsdat:|smsphone:|ReplyBuf:|RESMSOK", re.I)
RE_RTU_MARKER = re.compile(r"newsms come|Have \d+ sms|Read sms|del sms|sms Analy|SMS From TEL:|"
                           r"Call Phonenumber|g_RecPhoneNo|not this tel|InitGsm|InitOk|not reg|no sim|"
                           r"Sysinfo\.|Send AT|FindphoneID|PhoneRelayOpen|RESETGSM|tel1:|UserInfo\.|DEL Phone",
                           re.I)
# Oproep van een nummer dat in de eigen witte lijst van de RTU staat (die lijst hoort leeg te zijn).
RE_WHITELIST_HIT = re.compile(r"FindphoneID=(\d+)")
SMS_MAX_LINES = 10
SMS_BODY_SILENCE_S = 3.0     # geen nieuwe regels meer na de tekst
SMS_REPLY_SILENCE_S = 20.0   # antwoord versturen kan enkele seconden duren


def clean_sms_line(raw: bytes) -> tuple[str, bool]:
    """Knipt af bij het eerste onleesbare teken. Geeft (tekst, afgeknipt) terug."""
    text = raw.decode("utf-8", "replace")
    for i, ch in enumerate(text):
        if ch == "\ufffd" or (ord(ch) < 32 and ch != "\t") or 0x7F <= ord(ch) <= 0x9F:
            return text[:i].rstrip(), True
    return text.rstrip(), False


def mask_sms(text: str) -> str:
    """Verbergt het RTU-wachtwoord op basis van patronen (de app kent het wachtwoord niet):
    4 cijfers vooraan een commando, PWD####, en 'Password modified OK:####'."""
    text = re.sub(r"^\d{4}(?=[#A-Za-z])", "****", text)
    text = re.sub(r"^(\*{4})([Pp])\d{4}", r"\1\2****", text)
    text = re.sub(r"(PWD)\d+", r"\1****", text, flags=re.I)
    text = re.sub(r"(Password modified OK:)\s*\d+", r"\1****", text, flags=re.I)
    return text


class DeviceState:
    def __init__(self):
        self.serial_connected = None   # None = niet gestart / onbekend
        self.serial_error = ""
        self.last_line_at = None
        self.gsm = "onbekend"
        self.esp = "onbekend"
        self.relay = None          # "on" / "off" / None
        self.relay_until = None    # epoch, schatting op basis van remaining_s
        self.last_sms = None       # {"ts", "sender", "text"}
        self.last_call_number = None
        self.sms_pending = None    # SMS die nog binnenkomt
        self.pulse_pending = False # PulseTime moet nog gezet worden zodra het relais uit is
        self.pulse_sent = None     # (waarde, tijdstip) laatst verstuurde PulseTime

    def as_dict(self):
        return {
            "serial_connected": bool(self.serial_connected),
            "serial_error": self.serial_error,
            "last_line_at": self.last_line_at,
            "gsm": self.gsm,
            "esp": self.esp,
            "relay": self.relay,
            "relay_remaining_s": max(0, int(self.relay_until - time.time()))
            if self.relay == "on" and self.relay_until else None,
            "last_sms": self.last_sms,
        }


class SerialReader(threading.Thread):
    def __init__(self, engine, dev_id, port, baudrate):
        super().__init__(daemon=True, name=f"serial-{dev_id}")
        self.engine, self.dev_id, self.port, self.baudrate = engine, dev_id, port, baudrate
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        while not self.stop_event.is_set():
            try:
                with serial.serial_for_url(self.port, baudrate=self.baudrate, timeout=1) as ser:
                    self.engine.set_serial(self.dev_id, True, "")
                    buf = b""
                    while not self.stop_event.is_set():
                        chunk = ser.read(256)
                        if not chunk:
                            self.engine.tick(self.dev_id)
                            continue
                        buf += chunk
                        *lines, buf = re.split(rb"[\r\n]+", buf)
                        if len(buf) > 2048:      # rommel zonder regeleinde
                            buf = b""
                        for raw in lines:
                            self.engine.handle_raw(self.dev_id, raw)
                        self.engine.tick(self.dev_id)
            except Exception as e:  # noqa: BLE001
                self.engine.set_serial(self.dev_id, False, str(e))
            self.stop_event.wait(5)
        self.engine.serial_stopped(self.dev_id)


class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.cfg = settings.load()
        self.devices: dict[int, dict] = {d["id"]: d for d in devices.list_devices()}
        self.state: dict[int, DeviceState] = {}
        self.readers: dict[int, SerialReader] = {}
        self.mqtt: mqtt.Client | None = None
        self.mqtt_connected = False
        self.mqtt_error = ""
        self.subscribed: set[str] = set()
        self.dedupe: dict[tuple[int, str], float] = {}
        self.pending: dict[int, list[tuple[str, str, float]]] = {}
        self._poll_soon: dict[int, float] = {}
        self._stop = threading.Event()
        for dev_id in self.devices:
            self._init_state(dev_id)

    def _init_state(self, dev_id: int):
        st = self.state[dev_id] = DeviceState()
        # De RTU meldt de GSM-status alleen bij het opstarten. Na een herstart van de server
        # nemen we de laatst gekende status over uit het logboek.
        last = db.query_one("SELECT reason FROM events WHERE device_id=? AND reason LIKE 'GSM: %' "
                            "ORDER BY id DESC LIMIT 1", (dev_id,))
        if last:
            st.gsm = last["reason"][5:]
        sms = db.query_one("SELECT ts, actor, detail FROM events WHERE device_id=? AND category='sms' "
                           "AND IFNULL(reason, '') != 'Lege SMS ontvangen' ORDER BY id DESC LIMIT 1", (dev_id,))
        if sms:
            st.last_sms = {"ts": sms["ts"], "sender": sms["actor"], "text": sms["detail"]}

    # ---------- levenscyclus ----------

    def start(self, with_serial=True, with_mqtt=True):
        if with_mqtt:
            self._start_mqtt()
        if with_serial:
            self._start_serial()
        threading.Thread(target=self._housekeeping, daemon=True, name="housekeeping").start()
        threading.Thread(target=self._poller, daemon=True, name="pulsetime-poller").start()
        threading.Thread(target=self._backup_scheduler, daemon=True, name="backup").start()

    def stop(self):
        self._stop.set()
        self._stop_serial()
        self._stop_mqtt()

    def reload(self, cfg):
        """Algemene configuratie gewijzigd. Alleen bij andere broker-instellingen opnieuw verbinden."""
        with self.lock:
            old = self.cfg
            self.cfg = cfg
        if old["mqtt"] != cfg["mqtt"]:
            self._stop_mqtt()
            self._start_mqtt()

    def reload_devices(self):
        """Toestellen toegevoegd, gewijzigd of verwijderd. Geen MQTT-herverbinding nodig."""
        new = {d["id"]: d for d in devices.list_devices()}
        with self.lock:
            old, self.devices = self.devices, new
        restart = [i for i in set(old) | set(new)
                   if (old.get(i) or {}).get("enabled") != (new.get(i) or {}).get("enabled")
                   or any((old.get(i) or {}).get(k) != (new.get(i) or {}).get(k)
                          for k in ("serial_port", "baudrate"))]
        self._stop_serial(restart)
        for i in set(old) - set(new):
            self.state.pop(i, None)
        for i in set(new) - set(old):
            self._init_state(i)
        self._start_serial([i for i in restart if i in new])
        self._sync_subscriptions()
        for i, d in new.items():
            o = old.get(i)
            if d["enabled"] and (o is None or not o["enabled"] or o["tasmota_topic"] != d["tasmota_topic"]
                                 or o["on_seconds"] != d["on_seconds"]):
                self.query_tasmota(i)

    def _start_serial(self, only=None):
        for dev_id, d in self.devices.items():
            if only is not None and dev_id not in only:
                continue
            if d["enabled"] and d["serial_port"] and dev_id not in self.readers:
                r = SerialReader(self, dev_id, d["serial_port"], d["baudrate"])
                self.readers[dev_id] = r
                r.start()

    def _stop_serial(self, only=None):
        targets = [d for d in list(self.readers) if only is None or d in only]
        for d in targets:
            self.readers[d].stop()
        for d in targets:
            self.readers.pop(d).join(timeout=3)

    def _start_mqtt(self):
        m = self.cfg["mqtt"]
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=m["client_id"], clean_session=True)
        if m["username"]:
            c.username_pw_set(m["username"], m["password"] or None)
        c.on_connect = self._on_connect
        c.on_disconnect = self._on_disconnect
        c.on_message = self._on_message
        c.reconnect_delay_set(1, 30)
        self.mqtt = c
        try:
            c.connect_async(m["host"], m["port"], keepalive=30)
        except Exception as e:  # noqa: BLE001
            self.mqtt_error = str(e)
        c.loop_start()

    def _stop_mqtt(self):
        if self.mqtt:
            try:
                self.mqtt.disconnect()
                self.mqtt.loop_stop()
            except Exception:  # noqa: BLE001
                pass
        self.mqtt = None
        self.mqtt_connected = False
        self.subscribed = set()

    def _backup_scheduler(self):
        while not self._stop.wait(30):
            try:
                backup.run_if_due(self.cfg)
            except Exception:  # noqa: BLE001
                log.exception("back-up")

    def _housekeeping(self):
        while not self._stop.is_set():
            try:
                n = db.purge_events(self.cfg["retention_months"])
                if n:
                    db.log_event("systeem", result="info", reason="Logboek opgeschoond",
                                 detail=f"{n} regels ouder dan {self.cfg['retention_months']} maanden verwijderd")
                now = time.time()
                with self.lock:
                    self.dedupe = {k: v for k, v in self.dedupe.items() if now - v < 3600}
            except Exception:  # noqa: BLE001
                log.exception("housekeeping")
            self._stop.wait(6 * 3600)

    # ---------- MQTT / Tasmota ----------
    #
    # Per toestel een Tasmota-relaismodule met MQTT-topic <t> (standaard FullTopic %prefix%/%topic%/):
    #   cmnd/<t>/POWER ON|OFF        schakelen (ON herstart ook PulseTime)
    #   cmnd/<t>/PulseTime1 <n>      duur instellen; leeg = opvragen (antwoord op stat/<t>/RESULT)
    #   cmnd/<t>/PowerOnState 0      na stroomuitval altijd uit
    #   stat/<t>/POWER               relaisstatus na elke wijziging
    #   tele/<t>/STATE               periodieke status (bevat POWER)
    #   tele/<t>/LWT                 Online / Offline (retained)

    def _devices(self):
        for dev_id, d in list(self.devices.items()):
            if d["enabled"] and d["tasmota_topic"]:
                yield dev_id, d

    def _wanted_topics(self) -> set[str]:
        out = set()
        for _, d in self._devices():
            t = d["tasmota_topic"]
            out |= {f"stat/{t}/+", f"tele/{t}/LWT", f"tele/{t}/STATE"}
        return out

    def _sync_subscriptions(self):
        c = self.mqtt
        if not c or not self.mqtt_connected:
            return
        want = self._wanted_topics()
        for t in self.subscribed - want:
            c.unsubscribe(t)
        for t in want - self.subscribed:
            c.subscribe(t, qos=1)
        self.subscribed = want

    def _publish(self, topic: str, payload: str = "") -> str:
        c = self.mqtt
        if not c or not self.mqtt_connected:
            return "MQTT niet verbonden"
        info = c.publish(topic, payload, qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            return f"MQTT-fout {info.rc}"
        return ""

    def query_tasmota(self, dev_id: int):
        """Vraagt PulseTime, PowerOnState en relaisstatus op. Instellen gebeurt pas bij het antwoord,
        en alleen als de waarde verschilt (PulseTime nooit terwijl het relais aan is)."""
        d = self.devices.get(dev_id)
        if not d or not d["enabled"] or not d["tasmota_topic"]:
            return
        t = d["tasmota_topic"]
        self._publish(f"cmnd/{t}/PulseTime1", "")
        self._publish(f"cmnd/{t}/PowerOnState", "")
        self._publish(f"cmnd/{t}/POWER", "")

    def _set_pulsetime(self, dev_id: int, d: dict):
        st = self.state[dev_id]
        st.pulse_pending = False
        value = encode_pulsetime(d["on_seconds"])
        if st.pulse_sent and st.pulse_sent[0] == value and time.time() - st.pulse_sent[1] < 15:
            return                                  # net al verstuurd (dubbel antwoord op een vraag)
        st.pulse_sent = (value, time.time())
        self._publish(f"cmnd/{d['tasmota_topic']}/PulseTime1", str(encode_pulsetime(d["on_seconds"])))
        db.log_event("systeem", device=d, result="info", reason="PulseTime ingesteld op de relaismodule",
                     detail=f"{_dur(d['on_seconds'])} (PulseTime1 {encode_pulsetime(d['on_seconds'])})")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code.is_failure:
            self.mqtt_error = str(reason_code)
            return
        self.mqtt_connected = True
        self.mqtt_error = ""
        self.subscribed = set()
        self._sync_subscriptions()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.mqtt_connected = False
        if reason_code and reason_code.value != 0:
            self.mqtt_error = str(reason_code)

    def _on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode("utf-8", "replace").strip()
            for dev_id, d in self._devices():
                t = d["tasmota_topic"]
                if msg.topic == f"tele/{t}/LWT":
                    self._on_lwt(dev_id, d, payload)
                elif msg.topic in (f"stat/{t}/POWER", f"stat/{t}/POWER1"):
                    self._on_power(dev_id, d, payload)
                elif msg.topic == f"tele/{t}/STATE":
                    data = json.loads(payload or "{}")
                    p = data.get("POWER", data.get("POWER1"))
                    if p:
                        self._on_power(dev_id, d, p)
                elif msg.topic == f"stat/{t}/RESULT":
                    self._on_result(dev_id, d, json.loads(payload or "{}"))
        except Exception:  # noqa: BLE001
            log.exception("MQTT-bericht %s", msg.topic)

    def _on_result(self, dev_id, d, data):
        st = self.state[dev_id]
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
            self._publish(f"cmnd/{d['tasmota_topic']}/PowerOnState", "0")

    def _on_lwt(self, dev_id, d, payload):
        st = self.state[dev_id]
        new = payload.lower() if payload.lower() in ("online", "offline") else "onbekend"
        if new != st.esp and st.esp != "onbekend":
            db.log_event("systeem", device=d, result="info", reason=f"Relaismodule {new}")
        st.esp = new
        if new == "online":
            self.query_tasmota(dev_id)

    def _on_power(self, dev_id, d, payload):
        relay = {"ON": "on", "OFF": "off"}.get(payload.strip().upper())
        if not relay:
            return
        st = self.state[dev_id]
        prev = st.relay
        st.relay = relay
        now = time.time()
        if relay == "on":
            if prev != "on" or not st.relay_until:
                st.relay_until = now + d["on_seconds"]
            self._poll_soon[dev_id] = now + 1
        else:
            st.relay_until = None
            if st.pulse_pending:
                self._set_pulsetime(dev_id, d)
        # Commando's bevestigen die op deze toestand wachten.
        with self.lock:
            keep = []
            for cmd_id, expect, ts in self.pending.get(dev_id, []):
                if now - ts > 15:
                    continue
                if expect == relay:
                    db.confirm_cmd(cmd_id)
                else:
                    keep.append((cmd_id, expect, ts))
            self.pending[dev_id] = keep
        # Voor een tijdschakeling (water) het uitgaan loggen; bij een puls (poort) is dat ruis.
        if prev == "on" and relay == "off" and d["on_seconds"] >= 10:
            db.log_event("systeem", device=d, result="info", reason="Relais uit")

    def _poller(self):
        """Vraagt elke 10 s de resterende PulseTime op zolang een relais aan is."""
        while not self._stop.is_set():
            now = time.time()
            for dev_id, d in list(self._devices()):
                st = self.state[dev_id]
                due = self._poll_soon.get(dev_id)
                if st.relay == "on" and (due is None or now >= due):
                    self._publish(f"cmnd/{d['tasmota_topic']}/PulseTime1", "")
                    self._poll_soon[dev_id] = now + 10
            self._stop.wait(1)

    def send(self, dev_id: int, action: str) -> tuple[str | None, str]:
        """Stuurt ON of OFF. Geeft (cmd_id, foutmelding) terug."""
        d = self.devices[dev_id]
        if not d["tasmota_topic"]:
            return None, "Geen Tasmota-topic ingesteld"
        err = self._publish(f"cmnd/{d['tasmota_topic']}/POWER", "ON" if action == "on" else "OFF")
        if err:
            return None, err
        cmd_id = uuid.uuid4().hex[:12]
        with self.lock:
            self.pending.setdefault(dev_id, []).append((cmd_id, action, time.time()))
        return cmd_id, ""

    # ---------- RTU ----------

    def serial_stopped(self, dev_id):
        """Bewust gestopt (config gewijzigd of afsluiten): niet loggen als fout."""
        st = self.state[dev_id]
        st.serial_connected = None
        st.serial_error = ""

    def set_serial(self, dev_id, connected, error):
        st = self.state[dev_id]
        if connected != st.serial_connected:
            db.log_event("systeem", device=self.devices.get(dev_id), result="info" if connected else "fout",
                         reason="RTU verbonden" if connected else "RTU niet bereikbaar",
                         detail=None if connected else error)
        st.serial_connected = connected
        st.serial_error = error

    def handle_raw(self, dev_id: str, raw: bytes):
        """Eén regel van de seriële lijn (bytes)."""
        st = self.state[dev_id]
        line = "".join(ch for ch in raw.decode("latin-1") if ch.isprintable()).strip()
        p = st.sms_pending
        if p is not None:
            if RE_REPLY_LINE.search(line):
                p["phase"] = "reply"
                p["t"] = time.time()
                m = RE_REPLY_BUF.search(line)
                if m:
                    raw_reply = raw[raw.find(b"ReplyBuf:") + len(b"ReplyBuf:"):]
                    p["reply"] = clean_sms_line(raw_reply)[0].strip()
                if RE_REPLY_OK.search(line):
                    p["sent"] = True
                    self._flush_sms(dev_id)
                return
            if not RE_RTU_MARKER.search(line):
                if p["phase"] == "body" and not p["dirty"]:
                    text, cut = clean_sms_line(raw)
                    if text.strip():
                        p["lines"].append(text.strip())
                    p["dirty"] = cut
                    p["t"] = time.time()
                    if len(p["lines"]) >= SMS_MAX_LINES:
                        p["dirty"] = True
                return
            self._flush_sms(dev_id)
        if line:
            self.handle_line(dev_id, line)

    def tick(self, dev_id: str):
        p = self.state[dev_id].sms_pending
        if p is None:
            return
        limit = SMS_REPLY_SILENCE_S if p["phase"] == "reply" else SMS_BODY_SILENCE_S
        if time.time() - p["t"] >= limit:
            self._flush_sms(dev_id)

    def _flush_sms(self, dev_id: str):
        st = self.state[dev_id]
        p, st.sms_pending = st.sms_pending, None
        if p is None:
            return
        text = mask_sms("\n".join(p["lines"]))
        sender = p["sender"]
        member = None
        try:
            number = normalize(sender, self.cfg["phone_region"])
            member = members.find_by_phone(number) if number else None
        except PhoneError:
            number = None
        command = text.startswith("****")
        empty = not text and p["reply"] is None
        detail = text or "(leeg)"
        result = "info"
        if p["reply"] is not None:
            reply = mask_sms(p["reply"])
            detail += f"\nAntwoord: {reply} ({'verzonden' if p['sent'] else 'niet bevestigd'})"
            if "error" in reply.lower():
                result = "fout"
        db.log_event("sms", device=self.devices.get(dev_id), actor=sender or "onbekend", phone=number, member=member,
                     result=result,
                     reason="Lege SMS ontvangen" if empty else "SMS-commando ontvangen" if command else "SMS ontvangen",
                     detail=detail)
        if not empty:   # lege SMS (bv. na RESETGSM) niet als laatste SMS tonen
            st.last_sms = {"ts": db.now_iso(), "sender": sender, "text": text}

    def handle_line(self, dev_id: str, line: str):
        st = self.state[dev_id]
        st.last_line_at = db.now_iso()
        m = RE_SMS_FROM.search(line)
        if m:
            st.gsm = "ok"
            st.sms_pending = {"sender": m.group(1), "lines": [], "dirty": False, "t": time.time(),
                              "phase": "body", "reply": None, "sent": False}
            return
        m = RE_WHITELIST_HIT.search(line)
        if m:
            slot = int(m.group(1))
            db.log_event("systeem", device=self.devices.get(dev_id), result="info", phone=st.last_call_number,
                         reason="Nummer staat in de witte lijst van de RTU",
                         detail=f"Plaats {slot:03d} in de RTU. Die lijst hoort leeg te zijn; "
                                f"verwijder met <wachtwoord>#TEL#{slot:03d}#")
            return
        m = RE_CALL.search(line)
        if m:
            st.gsm = "ok"          # een binnenkomende oproep bewijst dat GSM werkt
            try:
                st.last_call_number = normalize(m.group(1), self.cfg["phone_region"])
            except PhoneError:
                st.last_call_number = m.group(1)
            self.handle_call(dev_id, m.group(1))
            return
        for pat, gsm in GSM_PATTERNS:
            if pat.search(line):
                if gsm != st.gsm:
                    db.log_event("systeem", device=self.devices.get(dev_id), result="info" if gsm in ("ok", "initialiseren") else "fout",
                                 reason=f"GSM: {gsm}", detail=line)
                    st.gsm = gsm
                return

    def handle_call(self, dev_id: str, raw: str, source: str = "oproep"):
        raw = (raw or "").strip()
        if not raw.strip("+"):
            db.log_event(source, device=self.devices.get(dev_id), result="geweigerd", reason="Nummer afgeschermd")
            return "geweigerd"
        try:
            number = normalize(raw, self.cfg["phone_region"])
        except PhoneError:
            number = raw
        d = self.devices[dev_id]
        now = time.time()
        with self.lock:
            last = self.dedupe.get((dev_id, number))
            if last is not None and now - last < d["dedupe_seconds"]:
                return "ontdubbeld"
            self.dedupe[(dev_id, number)] = now

        member = members.find_by_phone(number)
        common = {"device": d, "actor": number, "phone": number, "member": member}
        if member is None:
            db.log_event(source, result="geweigerd", reason="Onbekend nummer", **common)
            return "geweigerd"
        if not members.has_access(member, dev_id):
            db.log_event(source, result="geweigerd", reason="Geen toegang tot dit toestel", **common)
            return "geweigerd"

        cmd_id, err = self.send(dev_id, "on")
        if err:
            db.log_event(source, result="fout", reason=f"Toegelaten, maar commando niet verzonden: {err}", **common)
            return "fout"
        db.log_event(source, result="toegelaten",
                     reason=f"Aan voor {_dur(d['on_seconds'])}", cmd_id=cmd_id, **common)
        return "toegelaten"

    # ---------- manueel ----------

    def manual(self, dev_id: int, action: str, actor: str):
        d = self.devices.get(dev_id)
        if d is None:
            raise KeyError(dev_id)
        if not d["enabled"]:
            raise ValueError(f"{d['name']} is niet actief in de configuratie.")
        cmd_id, err = self.send(dev_id, action)
        reason = f"Manueel aan voor {_dur(d['on_seconds'])}" if action == "on" else "Manueel uit"
        db.log_event("manueel", device=self.devices.get(dev_id), actor=actor, cmd_id=cmd_id,
                     result="fout" if err else "ok", reason=reason, detail=err or None)
        if err:
            raise RuntimeError(err)
        return cmd_id

    def status(self):
        return {
            "mqtt": {"connected": self.mqtt_connected, "error": self.mqtt_error},
            "devices": [
                {"id": dev_id, "name": d["name"], "enabled": d["enabled"], "on_seconds": d["on_seconds"],
                 **self.state[dev_id].as_dict()}
                for dev_id, d in list(self.devices.items()) if dev_id in self.state
            ],
        }


def _dur(s: int) -> str:
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
