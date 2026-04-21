"""
Azure AD authentication via MSAL device code flow.

Usage pattern:
  1. Call start_device_flow() → returns {user_code, verification_uri, message}
  2. Show those to the user; they go to microsoft.com/devicelogin
  3. Background thread polls Azure AD and saves the token when auth completes
  4. Poll get_flow_status() from the frontend until status == "success"
  5. get_access_token() then returns a valid Bearer token (auto-refreshed by MSAL)
"""

import os
import threading
import logging
import msal

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = [settings.azure_scope]
AUTHORITY = f"https://login.microsoftonline.com/{settings.azure_tenant_id}"

# In-process state for the active device flow
_flow_status: str = "idle"   # "idle" | "pending" | "success" | "error"
_flow_message: str = ""
_flow_lock = threading.Lock()


# ── Token cache helpers ────────────────────────────────────────────────────────

def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if os.path.exists(settings.token_cache_path):
        try:
            cache.deserialize(open(settings.token_cache_path).read())
        except Exception:
            pass
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        os.makedirs(os.path.dirname(settings.token_cache_path), exist_ok=True)
        open(settings.token_cache_path, "w").write(cache.serialize())


def _make_app(cache: msal.SerializableTokenCache | None = None) -> msal.PublicClientApplication:
    return msal.PublicClientApplication(
        settings.azure_client_id,
        authority=AUTHORITY,
        token_cache=cache,
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def get_access_token() -> str | None:
    """Return a valid access token from cache, refreshing silently if needed."""
    cache = _load_cache()
    app = _make_app(cache)
    accounts = app.get_accounts()
    if not accounts:
        return None
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    _save_cache(cache)
    if result and "access_token" in result:
        return result["access_token"]
    return None


def get_logged_in_user() -> str | None:
    """Return the UPN of the cached account, or None if not logged in."""
    cache = _load_cache()
    app = _make_app(cache)
    accounts = app.get_accounts()
    return accounts[0].get("username") if accounts else None


def is_authenticated() -> bool:
    return get_access_token() is not None


def logout() -> None:
    global _flow_status, _flow_message
    if os.path.exists(settings.token_cache_path):
        os.remove(settings.token_cache_path)
    with _flow_lock:
        _flow_status = "idle"
        _flow_message = ""


def get_flow_status() -> dict:
    with _flow_lock:
        return {"status": _flow_status, "message": _flow_message}


def start_device_flow() -> dict:
    """
    Initiate a device code flow. Returns {user_code, verification_uri, message}.
    Spawns a background thread that polls Azure AD and caches the token on success.
    """
    global _flow_status, _flow_message

    app = _make_app()
    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        error = flow.get("error_description", "Failed to start device flow")
        logger.error(f"Device flow initiation failed: {error}")
        with _flow_lock:
            _flow_status = "error"
            _flow_message = error
        return {"error": error}

    with _flow_lock:
        _flow_status = "pending"
        _flow_message = ""

    thread = threading.Thread(target=_poll_device_flow, args=(flow,), daemon=True)
    thread.start()

    return {
        "user_code": flow["user_code"],
        "verification_uri": flow["verification_uri"],
        "message": flow["message"],
        "expires_in": flow.get("expires_in", 900),
    }


def _poll_device_flow(flow: dict) -> None:
    """Background thread: blocks until the user authenticates or the flow expires."""
    global _flow_status, _flow_message
    cache = _load_cache()
    app = _make_app(cache)
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        _save_cache(cache)
        user = get_logged_in_user()
        logger.info(f"PhysChem: authenticated as {user}")
        with _flow_lock:
            _flow_status = "success"
            _flow_message = user or ""
    else:
        error = result.get("error_description", result.get("error", "Authentication failed"))
        logger.warning(f"Device flow failed: {error}")
        with _flow_lock:
            _flow_status = "error"
            _flow_message = error
