"""
Azure AD authentication endpoints for PhysChem token acquisition.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.utils import azure_auth

router = APIRouter(prefix="/auth")


@router.post("/start")
async def auth_start():
    """Begin device code flow. Returns user_code + verification_uri to show the user."""
    result = azure_auth.start_device_flow()
    if "error" in result:
        return JSONResponse(status_code=500, content=result)
    return result


@router.get("/status")
async def auth_status():
    """Poll this until status == 'success' or 'error'."""
    status = azure_auth.get_flow_status()
    status["user"] = azure_auth.get_logged_in_user()
    status["authenticated"] = azure_auth.is_authenticated()
    return status


@router.post("/logout")
async def auth_logout():
    azure_auth.logout()
    return {"status": "logged_out"}
