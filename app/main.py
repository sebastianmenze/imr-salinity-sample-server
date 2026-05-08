from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import logging
import pathlib
import shutil

from app.database import create_tables
from app.routers import register, measure, auth, guide

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_REPO_ROOT   = pathlib.Path(".")
_STATIC_IMG  = pathlib.Path("app/static/images")
_IMG_EXTS    = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _sync_guide_images():
    _STATIC_IMG.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in _REPO_ROOT.glob("*"):
        if src.suffix.lower() in _IMG_EXTS and src.is_file():
            dst = _STATIC_IMG / src.name
            shutil.copy2(src, dst)
            copied.append(src.name)
    if copied:
        logger.info("Guide images synced: %s", ", ".join(copied))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — creating database tables...")
    create_tables()
    logger.info("Database ready.")
    _sync_guide_images()
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="IMR Salinity Sample Tracker",
    description="QR-code based salinity sample management for research vessels",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(register.router, tags=["registration"])
app.include_router(measure.router, tags=["measurement"])
app.include_router(auth.router, tags=["auth"])
app.include_router(guide.router, tags=["guide"])
