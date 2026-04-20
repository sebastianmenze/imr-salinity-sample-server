from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str = "postgresql://salinity:salinity@db:5432/salinity"
    base_url: str = "http://localhost:8000"
    secret_key: str = "changeme"
    physchem_api_url: Optional[str] = None
    physchem_api_key: Optional[str] = None
    label_printer_url: Optional[str] = None
    labels_dir: str = "labels"

    class Config:
        env_file = ".env"


settings = Settings()
