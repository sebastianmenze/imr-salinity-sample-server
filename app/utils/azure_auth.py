"""
PhysChem token management — manual paste flow.

Lab staff get a token from https://physchem-token-test.hi.no and paste it here.
Azure AD access tokens expire in ~1 hour; the UI shows remaining time.
"""

import time
import logging

logger = logging.getLogger(__name__)

TOKEN_LIFETIME = 3600  # seconds; standard Azure AD access token lifetime

_token: str | None = None
_token_set_at: float | None = None


def set_manual_token(token: str) -> None:
    global _token, _token_set_at
    _token = token.strip()
    _token_set_at = time.time()
    logger.info("PhysChem: manual token updated")


def get_access_token() -> str | None:
    if not _token or _token_set_at is None:
        return None
    if time.time() - _token_set_at >= TOKEN_LIFETIME:
        return None  # expired
    return _token


def is_authenticated() -> bool:
    return get_access_token() is not None


def get_token_status() -> dict:
    """Returns status info for the UI."""
    if not _token or _token_set_at is None:
        return {"state": "none"}
    age = time.time() - _token_set_at
    remaining = int(TOKEN_LIFETIME - age)
    if remaining <= 0:
        return {"state": "expired"}
    return {
        "state": "valid",
        "remaining_minutes": remaining // 60,
        "remaining_seconds": remaining % 60,
    }


def get_logged_in_user() -> str | None:
    return "token active" if is_authenticated() else None


def logout() -> None:
    global _token, _token_set_at
    _token = None
    _token_set_at = None
    logger.info("PhysChem: token cleared")
