"""Cloudflare Access: controle van de JWT die Cloudflare meestuurt.

Wie via Cloudflare Access binnenkomt, is admin. De app vertrouwt niet blind op de
e-mail-header: de JWT wordt gecontroleerd op handtekening, audience en issuer, zodat
een verzoek dat de tunnel omzeilt geweigerd wordt.
"""
import logging
import os

import jwt
from fastapi import HTTPException, Request

log = logging.getLogger(__name__)

TEAM_DOMAIN = os.environ.get("CF_ACCESS_TEAM_DOMAIN", "").strip().removeprefix("https://").rstrip("/")
AUDIENCE = os.environ.get("CF_ACCESS_AUD", "").strip()
AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "false").lower() in ("1", "true", "yes")
LOCAL_USER = os.environ.get("AUTH_DISABLED_USER", "lokaal")

_jwks: jwt.PyJWKClient | None = None


def _client() -> jwt.PyJWKClient:
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(f"https://{TEAM_DOMAIN}/cdn-cgi/access/certs",
                                cache_keys=True, lifespan=3600)
    return _jwks


def configured() -> bool:
    return AUTH_DISABLED or bool(TEAM_DOMAIN and AUDIENCE)


def current_user(request: Request) -> str:
    """FastAPI dependency: geeft het e-mailadres van de admin terug."""
    if AUTH_DISABLED:
        return LOCAL_USER
    if not (TEAM_DOMAIN and AUDIENCE):
        raise HTTPException(503, "Cloudflare Access is niet geconfigureerd "
                                 "(CF_ACCESS_TEAM_DOMAIN / CF_ACCESS_AUD).")
    token = request.headers.get("Cf-Access-Jwt-Assertion") or request.cookies.get("CF_Authorization")
    if not token:
        raise HTTPException(401, "Geen Cloudflare Access-token.")
    try:
        key = _client().get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=AUDIENCE,
                            issuer=f"https://{TEAM_DOMAIN}")
    except Exception as e:  # noqa: BLE001
        log.warning("Ongeldige Cloudflare-token: %s", e)
        raise HTTPException(403, "Ongeldige Cloudflare Access-token.") from e
    email = claims.get("email")
    if not email:
        raise HTTPException(403, "Token zonder e-mailadres (service token niet toegelaten).")
    return email
