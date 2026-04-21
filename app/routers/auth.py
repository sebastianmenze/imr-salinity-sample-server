"""
PhysChem token endpoints.
"""

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from app.utils import azure_auth

router = APIRouter(prefix="/auth")


@router.post("/token")
async def set_token(token: str = Form(...)):
    if not token.strip():
        return JSONResponse(status_code=400, content={"error": "Token is empty"})
    azure_auth.set_manual_token(token)
    return {"status": "ok", **azure_auth.get_token_status()}


@router.get("/status")
async def auth_status():
    return {
        "authenticated": azure_auth.is_authenticated(),
        **azure_auth.get_token_status(),
    }


@router.post("/logout")
async def auth_logout():
    azure_auth.logout()
    return {"status": "logged_out"}
