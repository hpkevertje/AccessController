import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from accesscontrol import auth

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJwks:
    def get_signing_key_from_jwt(self, token):
        class K:
            key = KEY.public_key()
        return K()


@pytest.fixture(autouse=True)
def cf(monkeypatch):
    monkeypatch.setattr(auth, "AUTH_DISABLED", False)
    monkeypatch.setattr(auth, "TEAM_DOMAIN", "team.cloudflareaccess.com")
    monkeypatch.setattr(auth, "AUDIENCE", "aud123")
    monkeypatch.setattr(auth, "_client", lambda: FakeJwks())


def req(headers=None, cookie=None):
    h = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if cookie:
        h.append((b"cookie", f"CF_Authorization={cookie}".encode()))
    return Request({"type": "http", "headers": h})


def token(**over):
    claims = {"email": "hans@x.be", "aud": "aud123", "iss": "https://team.cloudflareaccess.com",
              "exp": int(time.time()) + 300, **over}
    return jwt.encode(claims, KEY, algorithm="RS256")


def test_valid_header_and_cookie():
    assert auth.current_user(req({"Cf-Access-Jwt-Assertion": token()})) == "hans@x.be"
    assert auth.current_user(req(cookie=token())) == "hans@x.be"


@pytest.mark.parametrize("over,code", [({"aud": "other"}, 403), ({"iss": "https://evil"}, 403),
                                       ({"exp": int(time.time()) - 10}, 403), ({"email": None}, 403)])
def test_rejected(over, code):
    with pytest.raises(HTTPException) as e:
        auth.current_user(req({"Cf-Access-Jwt-Assertion": token(**over)}))
    assert e.value.status_code == code


def test_missing_token_and_unconfigured(monkeypatch):
    with pytest.raises(HTTPException) as e:
        auth.current_user(req())
    assert e.value.status_code == 401
    monkeypatch.setattr(auth, "AUDIENCE", "")
    with pytest.raises(HTTPException) as e:
        auth.current_user(req())
    assert e.value.status_code == 503


def test_spoofed_email_header_ignored():
    with pytest.raises(HTTPException):
        auth.current_user(req({"Cf-Access-Authenticated-User-Email": "boss@x.be"}))
