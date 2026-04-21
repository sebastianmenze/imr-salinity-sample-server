from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import logging

from app.database import create_tables
from app.routers import register, measure, auth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — creating database tables...")
    create_tables()
    logger.info("Database ready.")
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
