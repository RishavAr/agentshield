"""Verify Auth.js / NextAuth session JWTs (HS256) shared with the dashboard."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

try:
    import jwt
except ImportError:  # pragma: no cover
    jwt = None  # type: ignore


def auth_secret() -> Optional[str]:
    """Same value as dashboard AUTH_SECRET / NEXTAUTH_SECRET."""
    return (
        os.getenv("AGENTIVA_AUTH_SECRET")
        or os.getenv("AUTH_SECRET")
        or os.getenv("NEXTAUTH_SECRET")
        or ""
    ).strip() or None


def verify_bearer_token(token: str) -> Dict[str, Any]:
    """
    Decode and verify HS256 JWT from NextAuth session strategy.
    Raises jwt.InvalidTokenError on failure.
    """
    if jwt is None:
        raise RuntimeError("PyJWT is required for AGENTIVA_AUTH_SECRET")
    secret = auth_secret()
    if not secret:
        raise RuntimeError("AGENTIVA_AUTH_SECRET not configured")
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"verify_aud": False},
    )


def try_verify_bearer_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return verify_bearer_token(token)
    except Exception:
        return None
