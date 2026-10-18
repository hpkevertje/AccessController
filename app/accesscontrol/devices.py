"""Toestellen: 1 toestel = 1 RTU5024 (eigen telefoonnummer) + 1 Tasmota-relais."""
from . import db

FIELDS = ("name", "enabled", "serial_port", "baudrate", "tasmota_topic", "on_seconds", "dedupe_seconds")
LABELS = {
    "name": "Naam", "enabled": "Actief", "serial_port": "Seriële poort", "baudrate": "Baudrate",
    "tasmota_topic": "Tasmota-topic", "on_seconds": "Aan-tijd (s)", "dedupe_seconds": "Ontdubbeling (s)",
}
# PulseTime van Tasmota gaat tot 64900 = 64800 seconden (18 uur).
RANGES = {"baudrate": (300, 921600), "on_seconds": (1, 64800), "dedupe_seconds": (0, 3600)}


class DeviceError(ValueError):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def _to_api(r: dict) -> dict:
    out = {k: r[k] for k in ("id", *FIELDS, "sort_order")}
    out["enabled"] = bool(out["enabled"])
    return out


def list_devices() -> list[dict]:
    return [_to_api(r) for r in db.query("SELECT * FROM devices ORDER BY sort_order, name COLLATE NOCASE")]


def get(device_id: int) -> dict | None:
    r = db.query_one("SELECT * FROM devices WHERE id=?", (device_id,))
    return _to_api(r) if r else None


def by_name() -> dict[str, dict]:
    """Toestellen op naam (kleine letters), voor import."""
    return {d["name"].lower(): d for d in list_devices()}


def validate(data: dict, existing_id: int | None = None) -> dict:
    errors = []
    out = {}
    out["name"] = str(data.get("name") or "").strip()
    if not out["name"]:
        errors.append("Naam is verplicht.")
    out["enabled"] = bool(data.get("enabled", True))
    out["serial_port"] = str(data.get("serial_port") or "").strip()
    out["tasmota_topic"] = str(data.get("tasmota_topic") or "").strip()
    if not out["tasmota_topic"] or any(c in out["tasmota_topic"] for c in "#+/ "):
        errors.append("Tasmota-topic is verplicht en mag geen #, +, / of spatie bevatten.")
    defaults = {"baudrate": 38400, "on_seconds": 1, "dedupe_seconds": 5}
    for f, (lo, hi) in RANGES.items():
        try:
            v = data.get(f, defaults[f])
            out[f] = int(defaults[f] if v in (None, "") else v)
            if not lo <= out[f] <= hi:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{LABELS[f]} moet tussen {lo} en {hi} liggen.")
    if out["enabled"] and not out["serial_port"]:
        errors.append("Seriële poort is verplicht voor een actief toestel.")
    if out["name"]:
        dup = db.query_one("SELECT id FROM devices WHERE name=? COLLATE NOCASE AND id IS NOT ?",
                           (out["name"], existing_id))
        if dup:
            errors.append(f"Er bestaat al een toestel met de naam '{out['name']}'.")
    if out["tasmota_topic"]:
        dup = db.query_one("SELECT name FROM devices WHERE tasmota_topic=? AND id IS NOT ?",
                           (out["tasmota_topic"], existing_id))
        if dup:
            errors.append(f"Tasmota-topic '{out['tasmota_topic']}' wordt al gebruikt door {dup['name']}.")
    if out["enabled"] and out["serial_port"]:
        dup = db.query_one("SELECT name FROM devices WHERE enabled=1 AND serial_port=? AND id IS NOT ?",
                           (out["serial_port"], existing_id))
        if dup:
            errors.append(f"Seriële poort '{out['serial_port']}' wordt al gebruikt door {dup['name']}.")
    if errors:
        raise DeviceError(errors)
    return out


def _describe(d: dict) -> str:
    return "; ".join(f"{LABELS[f]}: {('ja' if d[f] else 'nee') if f == 'enabled' else d[f]}" for f in FIELDS)


def create(data: dict, grant_all, actor: str) -> dict:
    if grant_all is None:
        raise DeviceError(["Kies of alle bestaande leden toegang krijgen tot dit toestel."])
    d = validate(data)
    with db.tx() as c:
        order = c.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM devices").fetchone()[0]
        cur = c.execute(
            """INSERT INTO devices (name, enabled, serial_port, baudrate, tasmota_topic, on_seconds,
                                    dedupe_seconds, sort_order, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (d["name"], int(d["enabled"]), d["serial_port"], d["baudrate"], d["tasmota_topic"],
             d["on_seconds"], d["dedupe_seconds"], order, db.now_iso()))
        new_id = cur.lastrowid
        n = 0
        if grant_all:
            n = c.execute("INSERT INTO member_access (member_id, device_id) SELECT id, ? FROM members",
                          (new_id,)).rowcount
    dev = get(new_id)
    db.log_event("admin", device=dev, actor=actor, result="ok", reason="Toestel toegevoegd",
                 detail=_describe(dev) + f"; toegang gegeven aan {n} bestaande leden")
    return dev


def update(device_id: int, data: dict, actor: str) -> dict:
    old = get(device_id)
    if not old:
        raise KeyError(device_id)
    d = validate({**old, **{k: v for k, v in data.items() if k in FIELDS}}, existing_id=device_id)
    db.execute("""UPDATE devices SET name=?, enabled=?, serial_port=?, baudrate=?, tasmota_topic=?,
                  on_seconds=?, dedupe_seconds=? WHERE id=?""",
               (d["name"], int(d["enabled"]), d["serial_port"], d["baudrate"], d["tasmota_topic"],
                d["on_seconds"], d["dedupe_seconds"], device_id))
    new = get(device_id)
    changes = [f"{LABELS[f]}: {old[f]} -> {new[f]}" for f in FIELDS if old[f] != new[f]]
    if changes:
        db.log_event("admin", device=new, actor=actor, result="ok", reason="Toestel gewijzigd",
                     detail="; ".join(changes))
    return new


def delete(device_id: int, actor: str) -> None:
    old = get(device_id)
    if not old:
        raise KeyError(device_id)
    n = db.query_one("SELECT COUNT(*) AS n FROM member_access WHERE device_id=?", (device_id,))["n"]
    db.execute("DELETE FROM devices WHERE id=?", (device_id,))
    db.log_event("admin", device=old, actor=actor, result="ok", reason="Toestel verwijderd",
                 detail=_describe(old) + f"; toegang van {n} leden verwijderd. Logboekregels blijven bewaard.")
