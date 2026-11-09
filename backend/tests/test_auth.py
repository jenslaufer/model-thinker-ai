"""OIDC (launch-kit) authentication: JWKS-validated bearer tokens, one workspace per user."""

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

ISSUER = "https://auth.example.test/t/model-thinking"
CLIENT_ID = "mta-spa"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PROBLEM = {"description": "Customers churn between active and dormant states.", "actors": ["Company", "Customers"]}


class FakeJWKS:
    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=KEY.public_key())


def token(sub="user-1", key=KEY, **over):
    now = int(time.time())
    claims = {"sub": sub, "iss": ISSUER, "aud": CLIENT_ID, "exp": now + 3600, "iat": now,
              "email": f"{sub}@example.test", "name": sub, "role": "user", "tid": "tenant-uuid"} | over
    claims = {k: v for k, v in claims.items() if v is not None}
    return {"Authorization": f"Bearer {jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'main'})}"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/auth.db")
    monkeypatch.delenv("AUTH_DEV_MODE", raising=False)
    monkeypatch.setenv("OIDC_ISSUER_URL", ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", CLIENT_ID)
    from app import auth
    monkeypatch.setattr(auth, "make_jwks_client", lambda uri: FakeJWKS())
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_public_endpoints(client):
    assert client.get("/api/health").status_code == 200
    cfg = client.get("/api/auth/config").json()
    assert cfg == {"mode": "oidc", "issuer": ISSUER, "client_id": CLIENT_ID}


@pytest.mark.parametrize("path", ["/api/models", "/api/analyses", "/api/dashboard", "/api/settings", "/api/audit"])
def test_protected_without_token(client, path):
    assert client.get(path).status_code == 401


def test_valid_token_creates_personal_workspace(client):
    assert client.get("/api/analyses", headers=token()).json() == []
    me = client.get("/api/auth/me", headers=token()).json()
    assert me["email"] == "user-1@example.test" and me["role"] == "user"


@pytest.mark.parametrize("bad", [
    {"exp": int(time.time()) - 10},           # expired
    {"iss": "https://evil.test/t/model-thinking"},  # wrong issuer
    {"aud": "other-client"},                  # wrong audience
    {"token_use": "id"},                      # ID token is no API credential
])
def test_invalid_tokens_rejected(client, bad):
    assert client.get("/api/analyses", headers=token(**bad)).status_code == 401


def test_wrong_signature_rejected(client):
    assert client.get("/api/analyses", headers=token(key=OTHER_KEY)).status_code == 401


def test_malformed_header_rejected(client):
    assert client.get("/api/analyses", headers={"Authorization": "Bearer nonsense"}).status_code == 401


@pytest.mark.parametrize("over", [{"type": "client_credentials"}, {"role": "guest"}, {"role": None}])
def test_service_tokens_and_unknown_roles_forbidden(client, over):
    assert client.get("/api/analyses", headers=token(**over)).status_code == 403


def test_users_are_isolated_and_header_is_ignored(client):
    aid = client.post("/api/analyses", json={"problem": PROBLEM}, headers=token("alice")).json()["id"]
    bob = token("bob") | {"X-Workspace": "alice"}
    assert client.get("/api/analyses", headers=bob).json() == []
    assert client.get(f"/api/analyses/{aid}", headers=bob).status_code == 404
    assert client.get(f"/api/analyses/{aid}", headers=token("alice")).status_code == 200
    audit = client.get("/api/audit", headers=token("alice")).json()
    assert audit[0]["actor"] == "alice@example.test"


def test_startup_refuses_without_oidc_or_dev_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/x.db")
    for var in ("OIDC_ISSUER_URL", "AUTH_DEV_MODE"):
        monkeypatch.delenv(var, raising=False)
    from app.main import create_app

    with pytest.raises(RuntimeError, match="OIDC_ISSUER_URL"), TestClient(create_app()):
        pass
