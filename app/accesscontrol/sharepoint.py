"""Upload naar SharePoint via Microsoft Graph (app-registratie, client credentials).

Vereist in Entra ID een app-registratie met de applicatiepermissie Sites.Selected, en een
site-permissie (write) voor die app op de doelsite. Het client secret komt uit de omgeving
(SHAREPOINT_CLIENT_SECRET) en nooit uit de database.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

GRAPH = "https://graph.microsoft.com/v1.0"
CHUNK = 320 * 1024 * 10     # 3,2 MB, een veelvoud van 320 KiB zoals Graph vereist


class SharePointError(RuntimeError):
    pass


def secret() -> str:
    return os.environ.get("SHAREPOINT_CLIENT_SECRET", "").strip()


def _request(method: str, url: str, token: str | None = None, data: bytes | None = None,
             headers: dict | None = None, form: dict | None = None) -> dict:
    hdrs = dict(headers or {})
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        try:
            j = json.loads(detail)
            detail = (j.get("error_description") or (j.get("error") or {}).get("message") or detail)
        except (ValueError, AttributeError):
            pass
        raise SharePointError(f"{method} {url.split('?')[0]}: HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise SharePointError(f"{url.split('/')[2]} niet bereikbaar: {e.reason}") from e
    return json.loads(body) if body else {}


def _token(tenant: str, client_id: str) -> str:
    if not secret():
        raise SharePointError("SHAREPOINT_CLIENT_SECRET is niet ingesteld in de omgeving van de container.")
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


def upload(cfg: dict, filename: str, content: bytes) -> str:
    """Uploadt naar <documentbibliotheek>/<folder>/<filename>. Geeft de web-URL terug."""
    token = _token(cfg["tenant_id"], cfg["client_id"])
    site = _site_id(token, cfg["site_url"])
    target = f"{cfg['folder']}/{filename}" if cfg["folder"] else filename
    session = _request("POST", f"{GRAPH}/sites/{site}/drive/root:/{_q(target)}:/createUploadSession", token,
                       data=json.dumps({"item": {"@microsoft.graph.conflictBehavior": "replace"}}).encode(),
                       headers={"Content-Type": "application/json"})
    upload_url = session["uploadUrl"]
    total = len(content)
    result = {}
    for start in range(0, total, CHUNK):
        part = content[start:start + CHUNK]
        end = start + len(part) - 1
        # De upload-URL is vooraf ondertekend: geen Authorization-header meesturen.
        result = _request("PUT", upload_url, data=part,
                          headers={"Content-Length": str(len(part)), "Content-Range": f"bytes {start}-{end}/{total}"})
    return result.get("webUrl", "")


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
    return removed
