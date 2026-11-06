"""Upload naar SharePoint via Microsoft Graph (app-registratie, client credentials).

Vereist in Entra ID een app-registratie met de applicatiepermissie Sites.Selected, en een
site-permissie (write) voor die app op de doelsite. Het client secret komt uit de omgeving
(SHAREPOINT_CLIENT_SECRET) en nooit uit de database.
"""
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

GRAPH = "https://graph.microsoft.com/v1.0"
CHUNK = 320 * 1024 * 10     # 3,2 MB, een veelvoud van 320 KiB zoals Graph vereist
MODERATION_LABELS = {0: "goedgekeurd", 1: "geweigerd", 2: "wacht op goedkeuring",
                     3: "concept", 4: "gepland"}

log = logging.getLogger(__name__)


class SharePointError(RuntimeError):
    pass


def secret() -> str:
    return os.environ.get("SHAREPOINT_CLIENT_SECRET", "").strip()


def _short(url: str) -> str:
    """URL zonder query; een upload-URL bevat een vooraf ondertekend token in de query."""
    return url.split("?", 1)[0]


def _error_detail(raw: str) -> str:
    """Haalt de nuttige foutmelding uit een Graph- of OAuth-foutantwoord."""
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except ValueError:
        return raw[:400]
    if isinstance(data, dict):
        if data.get("error_description"):
            return str(data["error_description"])
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str):
            return str(data.get("error_description") or error)
    return raw[:400]


def _request(method: str, url: str, token: str | None = None, data: bytes | None = None,
             headers: dict | None = None, form: dict | None = None) -> dict:
    hdrs = dict(headers or {})
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    log.debug("Graph: %s %s", method, _short(url))
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status = r.status
            body = r.read()
            request_id = r.headers.get("request-id") or r.headers.get("client-request-id")
    except urllib.error.HTTPError as e:
        detail = _error_detail(e.read().decode("utf-8", "replace"))
        request_id = e.headers.get("request-id") or e.headers.get("client-request-id")
        msg = f"{method} {_short(url)}: HTTP {e.code}: {detail}"
        if request_id:
            msg += f" (request-id {request_id})"
        raise SharePointError(msg) from e
    except urllib.error.URLError as e:
        raise SharePointError(f"{url.split('/')[2]} niet bereikbaar: {e.reason}") from e
    if not body:
        return {}
    try:
        return json.loads(body)
    except ValueError as e:
        snippet = body.decode("utf-8", "replace")[:200]
        msg = f"{method} {_short(url)}: HTTP {status}: onverwacht antwoord: {snippet}"
        if request_id:
            msg += f" (request-id {request_id})"
        raise SharePointError(msg) from e


def _token(tenant: str, client_id: str) -> str:
    if not secret():
        raise SharePointError("SHAREPOINT_CLIENT_SECRET is niet ingesteld in de omgeving van de container.")
    log.debug("SharePoint: token aanvragen voor tenant %s", tenant)
    r = _request("POST", f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                 form={"client_id": client_id, "client_secret": secret(),
                       "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"})
    return r["access_token"]


def _site_id(token: str, site_url: str) -> str:
    u = urllib.parse.urlparse(site_url)
    path = u.path.rstrip("/")
    url = f"{GRAPH}/sites/{u.netloc}:{path}" if path else f"{GRAPH}/sites/{u.netloc}"
    return _request("GET", url, token)["id"]


def _q(path: str) -> str:
    return urllib.parse.quote(path, safe="/")


ITEM_SELECT = "id,name,size,webUrl,publication"


def _item(token: str, site: str, target: str, select: str = ITEM_SELECT) -> dict:
    """Haalt de metadata van een bestand op via het pad in de documentbibliotheek."""
    url = f"{GRAPH}/sites/{site}/drive/root:/{_q(target)}"
    if select:
        url += f"?$select={select}"
    return _request("GET", url, token)


def _moderation_status(token: str, site: str, target: str) -> int | None:
    """Geeft de contentgoedkeuringsstatus van een bestand terug (0=goedgekeurd, 2=wacht, 3=concept)."""
    li = _request("GET", f"{GRAPH}/sites/{site}/drive/root:/{_q(target)}:/listItem?$expand=fields", token)
    fields = li.get("fields") or {}
    status = fields.get("_ModerationStatus", fields.get("OData__ModerationStatus"))
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _ensure_published(token: str, site: str, target: str, item: dict) -> dict:
    """Checkt een uitgecheckt bestand in als gepubliceerde versie.

    In bibliotheken met versiebeheer (of 'Vereist uitchecken') komt een upload via Graph
    als concept/uitgecheckte versie binnen. Het bestand bestaat dan wel (201 Created) maar
    is voor gebruikers niet zichtbaar. Inchecken als 'published' maakt het zichtbaar.
    """
    publication = item.get("publication") or {}
    level = publication.get("level")
    if level != "checkout":
        if level:
            log.debug("SharePoint: publicatiestatus van %s is %s", target, level)
        return item

    item_id = item.get("id")
    if not item_id:
        item = _item(token, site, target)
        item_id = item.get("id")
    if not item_id:
        raise SharePointError("SharePoint gaf geen item-ID terug; kan het bestand niet inchecken.")

    log.info("SharePoint: %s staat uitgecheckt (concept); wordt ingecheckt als gepubliceerde versie", target)
    _request("POST", f"{GRAPH}/sites/{site}/drive/items/{item_id}/checkin", token,
             data=json.dumps({"comment": "AccessController back-up", "checkInAs": "published"}).encode(),
             headers={"Content-Type": "application/json"})
    item = _item(token, site, target)
    if (item.get("publication") or {}).get("level") == "checkout":
        raise SharePointError(
            "Bestand is geüpload maar blijft uitgecheckt. Zet in de SharePoint-bibliotheek "
            "'Vereist uitchecken' uit, of keur het bestand goed.")
    return item


def _upload(cfg: dict, filename: str, content: bytes) -> dict:
    """Uploadt een bestand en geeft de metadata van het resulterende item terug."""
    if not content:
        raise SharePointError("Leeg bestand kan niet naar SharePoint geüpload worden.")
    token = _token(cfg["tenant_id"], cfg["client_id"])
    site = _site_id(token, cfg["site_url"])
    target = f"{cfg['folder']}/{filename}" if cfg["folder"] else filename
    log.info("SharePoint: upload %s (%d bytes) naar %s", filename, len(content), target)

    session = _request("POST", f"{GRAPH}/sites/{site}/drive/root:/{_q(target)}:/createUploadSession", token,
                       data=json.dumps({"item": {"@microsoft.graph.conflictBehavior": "replace"}}).encode(),
                       headers={"Content-Type": "application/json"})
    upload_url = session.get("uploadUrl")
    if not upload_url:
        raise SharePointError("SharePoint gaf geen upload-URL terug voor het uploaden.")

    total = len(content)
    result = {}
    for start in range(0, total, CHUNK):
        part = content[start:start + CHUNK]
        end = start + len(part) - 1
        log.debug("SharePoint: fragment %d-%d van %d bytes", start, end, total)
        # De upload-URL is vooraf ondertekend: geen Authorization-header meesturen.
        result = _request("PUT", upload_url, data=part,
                          headers={"Content-Type": "application/octet-stream",
                                   "Content-Length": str(len(part)),
                                   "Content-Range": f"bytes {start}-{end}/{total}"})
    if result.get("nextExpectedRanges"):
        raise SharePointError(f"SharePoint verwacht nog gegevens na de upload: {result['nextExpectedRanges']}")

    # Controleer dat het bestand echt bestaat en de juiste grootte heeft. Zo wordt een
    # upload die wel 201 teruggeeft maar toch niet zichtbaar is, meteen opgemerkt.
    item = result
    if not item.get("id") or item.get("size") != total or "publication" not in item:
        try:
            item = _item(token, site, target)
        except SharePointError as e:
            log.warning("SharePoint: controle na upload mislukt: %s", e)
            return result
    if item.get("size") not in (None, total):
        raise SharePointError(
            f"SharePoint meldt {item.get('size')} bytes, maar het bestand is {total} bytes.")
    if not item.get("webUrl") and result.get("webUrl"):
        item["webUrl"] = result["webUrl"]
    item = _ensure_published(token, site, target, item)

    # In een bibliotheek met contentgoedkeuring blijft een geüpload bestand 'wacht op
    # goedkeuring' staan en is het voor gebruikers onzichtbaar. Dat mag geen stille
    # 'geslaagde' back-up zijn.
    try:
        moderation = _moderation_status(token, site, target)
    except SharePointError as e:
        log.debug("SharePoint: goedkeuringsstatus niet op te vragen: %s", e)
        moderation = None
    if moderation in (1, 2, 3, 4):
        raise SharePointError(
            "Bestand is geüpload, maar is niet zichtbaar in SharePoint: "
            f"goedkeuringsstatus '{MODERATION_LABELS[moderation]}'. Keur het bestand goed "
            "of zet contentgoedkeuring uit in de bibliotheek.")
    return item


def upload(cfg: dict, filename: str, content: bytes) -> str:
    """Uploadt naar <documentbibliotheek>/<folder>/<filename>. Geeft de web-URL terug."""
    item = _upload(cfg, filename, content)
    log.info("SharePoint: upload van %s afgerond", filename)
    return item.get("webUrl", "")


def cleanup(cfg: dict, prefix: str, retention_days: int) -> int:
    """Verwijdert back-ups ouder dan retention_days in de doelmap. Geeft het aantal terug."""
    token = _token(cfg["tenant_id"], cfg["client_id"])
    site = _site_id(token, cfg["site_url"])
    folder = cfg["folder"]
    url = (f"{GRAPH}/sites/{site}/drive/root:/{_q(folder)}:/children" if folder
           else f"{GRAPH}/sites/{site}/drive/root/children") + "?$select=id,name,createdDateTime&$top=200"
    limit = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed = 0
    while url:
        page = _request("GET", url, token)
        for item in page.get("value", []):
            if not item["name"].startswith(prefix):
                continue
            created = datetime.fromisoformat(item["createdDateTime"].replace("Z", "+00:00"))
            if created < limit:
                _request("DELETE", f"{GRAPH}/sites/{site}/drive/items/{item['id']}", token)
                removed += 1
        url = page.get("@odata.nextLink")
    if removed:
        log.info("SharePoint: %d oude back-up(s) verwijderd", removed)
    return removed


# ---------- diagnose ----------

def diagnose(cfg: dict) -> dict:
    """Test de SharePoint-instellingen stap voor stap met een klein testbestand.

    Geeft per stap terug of ze geslaagd is en wat het resultaat was. Zo is in de UI
    zichtbaar waar het misgaat (secret, token, site, map, upload, publicatie).
    """
    steps: list[dict] = []
    state: dict = {}

    def step(name: str, fn):
        try:
            detail = fn()
            steps.append({"step": name, "ok": True, "detail": detail})
            return detail
        except Exception as e:  # noqa: BLE001 - elke stap moet apart gerapporteerd worden
            log.warning("SharePoint-diagnose '%s' mislukt: %s", name, e)
            steps.append({"step": name, "ok": False, "error": str(e)})
            return None

    def check_config():
        missing = [k for k in ("tenant_id", "client_id", "site_url") if not str(cfg.get(k, "")).strip()]
        if missing:
            raise SharePointError("Ontbrekende instellingen: " + ", ".join(missing))
        return "tenant-ID, client-ID en site-URL zijn ingevuld"

    def check_secret():
        if not secret():
            raise SharePointError("SHAREPOINT_CLIENT_SECRET is niet ingesteld.")
        return "client secret is aanwezig"

    def check_token():
        state["token"] = _token(cfg["tenant_id"], cfg["client_id"])
        return "toegangstoken ontvangen"

    def check_site():
        if not state.get("token"):
            raise SharePointError("Overgeslagen: geen toegangstoken.")
        state["site"] = _site_id(state["token"], cfg["site_url"])
        return f"site gevonden ({state['site']})"

    def check_drive():
        if not state.get("site"):
            raise SharePointError("Overgeslagen: site is niet gevonden.")
        drive = _request("GET", f"{GRAPH}/sites/{state['site']}/drive?$select=id,name,webUrl", state["token"])
        state["drive"] = drive.get("id")
        return f"documentbibliotheek '{drive.get('name')}' ({drive.get('webUrl', '')})"

    def check_folder():
        if not state.get("site"):
            raise SharePointError("Overgeslagen: site is niet gevonden.")
        folder = cfg.get("folder", "")
        if not folder:
            return "lege map: het bestand wordt in de hoofdmap gezet"
        url = f"{GRAPH}/sites/{state['site']}/drive/root:/{_q(folder)}:/children?$top=1&$select=id,name"
        try:
            page = _request("GET", url, state["token"])
        except SharePointError as e:
            if "HTTP 404" in str(e):
                return f"map '{folder}' bestaat nog niet (wordt bij de upload aangemaakt)"
            raise
        return f"map '{folder}' gevonden ({len(page.get('value', []))} item(s) op de eerste pagina)"

    def check_upload():
        if not state.get("site"):
            raise SharePointError("Overgeslagen: site is niet gevonden.")
        name = f"accesscontrol-diagnose-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.db.gz"
        content = b"AccessController SharePoint diagnostic\n" * 64
        state["item"] = _upload(cfg, name, content)
        state["item_name"] = name
        state["item_size"] = len(content)
        return {"file": name, "bytes": len(content), "url": state["item"].get("webUrl", "")}

    def check_publication():
        item = state.get("item")
        if not item:
            raise SharePointError("Overgeslagen: testbestand is niet geüpload.")
        publication = item.get("publication") or {}
        result = {"level": publication.get("level") or "geen publicatiegegevens"}
        target = f"{cfg['folder']}/{state['item_name']}" if cfg.get("folder") else state["item_name"]
        try:
            status = _moderation_status(state["token"], state["site"], target)
            if status is not None:
                result["moderation"] = MODERATION_LABELS.get(status, str(status))
        except SharePointError as e:
            result["moderation"] = f"niet op te vragen: {e}"
        if result.get("moderation") in ("geweigerd", "wacht op goedkeuring", "concept", "gepland"):
            raise SharePointError(
                "Bestand is geüpload, maar niet zichtbaar: goedkeuringsstatus is "
                f"'{result['moderation']}'. Keur het bestand goed of zet contentgoedkeuring "
                "uit in de bibliotheek.")
        return result

    def check_delete():
        item = state.get("item") or {}
        if not item.get("id"):
            return "testbestand kon niet verwijderd worden (geen item-ID)"
        _request("DELETE", f"{GRAPH}/sites/{state['site']}/drive/items/{item['id']}", state["token"])
        return "testbestand verwijderd"

    if step("configuratie", check_config) and step("client secret", check_secret):
        step("toegangstoken", check_token)
        step("site", check_site)
        step("documentbibliotheek", check_drive)
        step("map", check_folder)
        if step("upload", check_upload):
            step("publicatie", check_publication)
            step("opruimen", check_delete)

    return {"ok": all(s["ok"] for s in steps), "steps": steps}
