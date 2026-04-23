from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import markdown
import pathlib

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

_GUIDE_PATH = pathlib.Path("USER_GUIDE.md")


@router.get("/guide", response_class=HTMLResponse)
async def user_guide(request: Request):
    md_text = _GUIDE_PATH.read_text(encoding="utf-8")
    # Rewrite relative image paths so they resolve via /static/images/
    md_text = md_text.replace("](images/", "](/static/images/")
    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code"],
    )
    return templates.TemplateResponse("guide.html", {
        "request": request,
        "content": html_body,
    })
