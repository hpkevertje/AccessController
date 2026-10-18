"""Configuratie die de admin in de UI aanpast. Opgeslagen in SQLite.

Bij de eerste start komen de standaardwaarden uit de omgeving (.env).
"""
import copy
import os
import re

from . import db

def _defaults() -> dict:
    return {
        "mqtt": {
            "host": os.environ.get("MQTT_HOST", "mosquitto"),
            "port": int(os.environ.get("MQTT_PORT", "1883")),
            "username": os.environ.get("MQTT_USER", ""),
            "password": os.environ.get("MQTT_PASSWORD", ""),
            "client_id": "accesscontrol-server",
        },
        "retention_months": 24,
        "phone_region": "BE",
        "backup": {
            "enabled": False,
            "folder": "/backups",
            "time": "03:00",
            "retention_days": 30,
            "sharepoint": {
                "enabled": False,
                "tenant_id": "",
                "client_id": "",
                "site_url": "",
                "folder": "AccessController",
                "retention_days": 90,
            },
        },
    }


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        elif k in out:
            out[k] = v
    return out


def load() -> dict:
    return _merge(_defaults(), db.get_setting("config", {}))


class ConfigError(ValueError):
    pass


def validate(cfg: dict) -> dict:
    """Valideert en geeft een opgeschoonde config terug. Gooit ConfigError."""
    cfg = _merge(_defaults(), cfg)
    errors = []
    m = cfg["mqtt"]
    m["host"] = str(m["host"]).strip()
    if not m["host"]:
        errors.append("MQTT host is verplicht.")
    try:
        m["port"] = int(m["port"])
        if not 1 <= m["port"] <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("MQTT poort moet tussen 1 en 65535 liggen.")
    try:
        cfg["retention_months"] = int(cfg["retention_months"])
        if not 1 <= cfg["retention_months"] <= 240:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("Bewaartermijn moet tussen 1 en 240 maanden liggen.")
    cfg["phone_region"] = str(cfg["phone_region"]).strip().upper() or "BE"

    b = cfg["backup"]
    b["enabled"] = bool(b["enabled"])
    b["folder"] = str(b["folder"]).strip()
    if b["enabled"] and not b["folder"].startswith("/"):
        errors.append("Back-upmap moet een absoluut pad in de container zijn (bv. /backups).")
    b["time"] = str(b["time"]).strip()
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", b["time"]):
        errors.append("Tijdstip back-up moet UU:MM zijn (bv. 03:00).")
    for key, sub in (("retention_days", b), ("retention_days", b["sharepoint"])):
        try:
            sub[key] = int(sub[key])
            if not 1 <= sub[key] <= 3650:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("Bewaartermijn back-ups moet tussen 1 en 3650 dagen liggen.")
    sp = b["sharepoint"]
    sp["enabled"] = bool(sp["enabled"])
    for k in ("tenant_id", "client_id", "site_url", "folder"):
        sp[k] = str(sp[k]).strip()
    sp["folder"] = sp["folder"].strip("/")
    if sp["enabled"]:
        if not (sp["tenant_id"] and sp["client_id"]):
            errors.append("SharePoint: tenant-ID en client-ID zijn verplicht.")
        if not re.fullmatch(r"https://[^/]+\.sharepoint\.com(/.*)?", sp["site_url"]):
            errors.append("SharePoint: site-URL moet beginnen met https://<naam>.sharepoint.com/.")
    if errors:
        raise ConfigError(errors)
    return cfg


def save(cfg: dict) -> dict:
    cfg = validate(cfg)
    db.set_setting("config", cfg)
    return cfg


def public(cfg: dict) -> dict:
    """Config voor de UI: wachtwoord niet terugsturen."""
    out = copy.deepcopy(cfg)
    out["mqtt"]["password_set"] = bool(out["mqtt"].get("password"))
    out["mqtt"]["password"] = ""
    return out


def diff(old: dict, new: dict, path="") -> list[str]:
    """Leesbare lijst van wijzigingen voor het logboek (zonder wachtwoord)."""
    changes = []
    for k in sorted(set(old) | set(new)):
        p = f"{path}.{k}" if path else k
        a, b = old.get(k), new.get(k)
        if isinstance(a, dict) and isinstance(b, dict):
            changes += diff(a, b, p)
        elif a != b:
            changes.append(f"{p}: gewijzigd" if "password" in k else f"{p}: {a!r} -> {b!r}")
    return changes
