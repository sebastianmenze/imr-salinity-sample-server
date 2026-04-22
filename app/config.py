from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str = "postgresql://salinity:salinity@db:5432/salinity"
    base_url: str = "http://nautilus.imr.no:8000"
    secret_key: str = "changeme"
    physchem_api_url: str = "https://physchem-api-test.hi.no"
    physchem_api_key: Optional[str] = None
    label_printer_url: Optional[str] = None
    labels_dir: str = "labels"

    # Azure AD — device code flow for PhysChem token acquisition
    azure_client_id: str = "bd2f9153-6b50-4cb8-8dad-eea0124a534f"
    azure_tenant_id: str = "22d38a39-3819-4265-b19c-1da98686b272"
    azure_scope: str = "api://bd2f9153-6b50-4cb8-8dad-eea0124a534f/Physchem.Write"
    token_cache_path: str = "/data/token_cache.json"

    class Config:
        env_file = ".env"


settings = Settings()
