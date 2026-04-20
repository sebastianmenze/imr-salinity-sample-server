"""
PhysChem API client.

Uploads finalized lab salinity measurements to the IMR PhysChem database.
Update the payload format to match your PhysChem API specification.
"""

import httpx
import logging
from typing import Optional
from datetime import datetime
from app.config import settings

logger = logging.getLogger(__name__)


class PhysChemClient:

    def __init__(self):
        self.base_url = settings.physchem_api_url
        self.api_key = settings.physchem_api_key

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    async def upload_measurement(
        self,
        sample_id: str,
        utc_time: datetime,
        latitude: float,
        longitude: float,
        depth_m: float,
        platform_id: str,
        operator: str,
        psal_lab: float,
        psal_1: Optional[float] = None,
        psal_2: Optional[float] = None,
        cruise_id: Optional[str] = None,
        station_id: Optional[str] = None,
        cast_number: Optional[str] = None,
        bottle_number: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """
        Upload a lab salinity measurement to PhysChem.

        Returns dict with 'success', 'upload_id', and optional 'message'.
        TODO: Update payload structure to match actual PhysChem API spec.
        """
        if not self.is_configured():
            logger.warning("PhysChem API not configured — skipping upload")
            return {"success": False, "message": "PhysChem API not configured"}

        # --- Update this payload to match your PhysChem API ---
        payload = {
            "sample_id": str(sample_id),
            "timestamp_utc": utc_time.isoformat(),
            "latitude": latitude,
            "longitude": longitude,
            "depth_m": depth_m,
            "platform": platform_id,
            "operator": operator,
            "parameter": "PSAL",
            "value": psal_lab,
            "unit": "PSU",
            "method": "salinometer",
            "ctd_psal_1": psal_1,
            "ctd_psal_2": psal_2,
            "cruise_id": cruise_id,
            "station_id": station_id,
            "cast_number": cast_number,
            "bottle_number": bottle_number,
            "notes": notes,
        }
        # -------------------------------------------------------

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}/measurements",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()
                logger.info(f"PhysChem upload successful: {data}")
                return {"success": True, "upload_id": data.get("id", ""), "data": data}

        except httpx.HTTPStatusError as e:
            logger.error(f"PhysChem HTTP error {e.response.status_code}: {e.response.text}")
            return {"success": False, "message": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            logger.error(f"PhysChem upload failed: {e}")
            return {"success": False, "message": str(e)}


physchem_client = PhysChemClient()
