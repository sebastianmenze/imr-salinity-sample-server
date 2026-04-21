"""
PhysChem token management — manual paste flow.

Lab staff get a token from https://physchem-token-test.hi.no and paste it here.
Azure AD access tokens expire in ~1 hour; the UI shows remaining time.
Token is persisted to /data/token_cache.json so it survives container restarts
within the same 1-hour validity window.
"""

import time
import json
import os
import logging

logger = logging.getLogger(__name__)

TOKEN_LIFETIME = 3600  # seconds
CACHE_FILE = "/data/token_cache.json"

_token: str | None = None
_token_set_at: float | None = None


def _load_from_disk() -> None:
    global _token, _token_set_at
    try:
        if os.path.exists(CACHE_FILE):
            data = json.loads(open(CACHE_FILE).read())
            t = data.get("token")
            sat = data.get("set_at")
            if t and sat and time.time() - sat < TOKEN_LIFETIME:
                _token = t
                _token_set_at = sat
                logger.info("PhysChem: token restored from disk")
    except Exception as e:
        logger.warning(f"PhysChem: could not load token cache: {e}")


def _save_to_disk() -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        open(CACHE_FILE, "w").write(json.dumps({"token": _token, "set_at": _token_set_at}))
    except Exception as e:
        logger.warning(f"PhysChem: could not save token cache: {e}")


def set_manual_token(token: str) -> None:
    global _token, _token_set_at
    _token = token.strip()
    _token_set_at = time.time()
    _save_to_disk()
    logger.info("PhysChem: manual token updated")


def get_access_token() -> str | None:
    if not _token or _token_set_at is None:
        _load_from_disk()
    if not _token or _token_set_at is None:
        return None
    if time.time() - _token_set_at >= TOKEN_LIFETIME:
        return None
    return _token


def is_authenticated() -> bool:
    return get_access_token() is not None


def get_token_status() -> dict:
    get_access_token()  # ensure disk load attempted
    if not _token or _token_set_at is None:
        return {"state": "none"}
    remaining = int(TOKEN_LIFETIME - (time.time() - _token_set_at))
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
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
    except Exception:
        pass
    logger.info("PhysChem: token cleared")
