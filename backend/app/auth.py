"""Authentication via launch-kit (or any OIDC provider): the app validates JWTs, never handles passwords.

Modes:
- oidc: OIDC_ISSUER_URL set. Bearer access tokens are checked against the issuer's JWKS
  (RS256 signature, iss, aud = OIDC_CLIENT_ID, exp). ID tokens and client_credentials tokens are
  rejected. Each user (`sub`) gets a personal workspace.
- dev:  AUTH_DEV_MODE=1 and no issuer. No authentication; the workspace comes from the X-Workspace
  header. For local development and tests only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

import jwt

ROLES = {"admin", "user"}  # launch-kit user roles


@dataclass(frozen=True)
class AuthConfig:
    mode: Literal["oidc", "dev"]
    issuer: str = ""
    client_id: str = ""
    jwks_uri: str = ""

    @classmethod
    def from_env(cls) -> AuthConfig:
        issuer = os.environ.get("OIDC_ISSUER_URL", "").rstrip("/")
        if issuer:
            return cls(mode="oidc", issuer=issuer, client_id=os.environ.get("OIDC_CLIENT_ID", ""),
                       jwks_uri=os.environ.get("OIDC_JWKS_URI") or f"{issuer}/auth/jwks")
        if os.environ.get("AUTH_DEV_MODE") == "1":
            return cls(mode="dev")
        raise RuntimeError("Set OIDC_ISSUER_URL (launch-kit tenant issuer) or AUTH_DEV_MODE=1 for local development")


@dataclass(frozen=True)
class Identity:
    sub: str
    email: str
    name: str
    role: str


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def make_jwks_client(uri: str):
    return jwt.PyJWKClient(uri, cache_jwk_set=True, lifespan=300)


class TokenVerifier:
    def __init__(self, cfg: AuthConfig):
        self.cfg = cfg
        self.jwks = make_jwks_client(cfg.jwks_uri)

    def verify(self, authorization: str | None) -> Identity:
        scheme, _, raw = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not raw:
            raise AuthError(401, "missing bearer token")
        try:
            key = self.jwks.get_signing_key_from_jwt(raw).key
            claims = jwt.decode(raw, key, algorithms=["RS256"], issuer=self.cfg.issuer,
                                audience=self.cfg.client_id or None,
                                options={"verify_aud": bool(self.cfg.client_id), "require": ["exp", "iss", "sub"]})
        except (jwt.PyJWTError, ValueError) as e:
            raise AuthError(401, f"invalid token: {e}") from e
        if claims.get("token_use") == "id":
            raise AuthError(401, "invalid token: ID token is no access token")
        if claims.get("type") == "client_credentials":
            raise AuthError(403, "service tokens cannot access user data")
        if claims.get("role") not in ROLES:
            raise AuthError(403, "token carries no permitted role")
        return Identity(sub=claims["sub"], email=claims.get("email", ""), name=claims.get("name", ""),
                        role=claims["role"])
