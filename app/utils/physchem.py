"""
PhysChem API client — https://physchem-api.hi.no

Upload flow for each lab measurement:
  1. GET /mission/list?cruise=...       → find the mission
  2. GET /mission/{id}/operation/list   → find the CTD operation by cast number
  3. POST /operation/{id}/instrument    → create a salinometer (BTL) instrument
  4. POST /instrument/{id}/parameter    → add a PSAL parameter to it
  5. POST /parameter/{id}/reading       → store the measured salinity value
"""

import httpx
import logging
from typing import Optional
from datetime import datetime
from app.config import settings

logger = logging.getLogger(__name__)


class PhysChemClient:

    def __init__(self):
        self.base_url = settings.physchem_api_url.rstrip("/")
        self.api_key = settings.physchem_api_key

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "*/*",
        }

    async def find_mission(self, cruise: str) -> Optional[dict]:
        """Look up PhysChem mission by cruise string (e.g. '2025001002')."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.base_url}/mission/list",
                params={"cruise": cruise},
                headers=self._headers(),
            )
            r.raise_for_status()
            missions = r.json()
            if not missions:
                logger.warning(f"No PhysChem mission found for cruise '{cruise}'")
                return None
            return missions[0]

    async def find_operation(self, mission_id: int, cast_number: str) -> Optional[dict]:
        """Find a CTD operation within a mission by its operation number."""
        try:
            target = int(cast_number)
        except (ValueError, TypeError):
            logger.error(f"cast_number '{cast_number}' is not a valid integer")
            return None

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.base_url}/mission/{mission_id}/operation/list",
                params={"extend": "false", "instrumentTypeList": "false"},
                headers=self._headers(),
            )
            r.raise_for_status()
            for op in r.json():
                if op.get("operationNumber") == target:
                    return op
        logger.warning(f"Operation {cast_number} not found in mission {mission_id}")
        return None

    async def create_instrument(self, operation_id: int, serial_number: str = "") -> dict:
        """Create a salinometer bottle instrument entry under an operation."""
        payload = {
            "instrumentType": "BTL",
            "instrumentSerialNumber": serial_number or "salinometer",
            "instrumentModel": "Autosal salinometer",
            "equipment": "Salinometer",
            "instrumentDataOwner": "IMR",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self.base_url}/operation/{operation_id}/instrument",
                json=payload,
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def create_parameter(self, instrument_id: int) -> dict:
        """Add a PSAL parameter to a salinometer instrument."""
        payload = {
            "parameterCode": "PSAL",
            "ordinal": 1,
            "suppliedParameterName": "Practical Salinity",
            "units": "0.001",
            "suppliedUnits": "PSU",
            "acquirementMethod": "discrete bottle salinometer",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self.base_url}/instrument/{instrument_id}/parameter",
                json=payload,
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def create_reading(
        self,
        parameter_id: int,
        psal_value: float,
        sample_number: int,
        value_datetime: datetime,
    ) -> dict:
        """Post the actual salinity reading value."""
        payload = {
            "sampleNumber": sample_number,
            "valueDateTime": value_datetime.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "valueDec": psal_value,
            "quality": "1",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self.base_url}/parameter/{parameter_id}/reading",
                json=payload,
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

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

        Requires cruise_id (e.g. '2025001002') and cast_number to locate
        the correct mission and operation in PhysChem.

        Returns dict with 'success', 'upload_id' (reading ID), and optional 'message'.
        """
        if not self.is_configured():
            return {"success": False, "message": "PhysChem API key not configured"}

        if not cruise_id:
            return {"success": False, "message": "cruise_id required for PhysChem upload"}

        if not cast_number:
            return {"success": False, "message": "cast_number (operation number) required for PhysChem upload"}

        try:
            # Step 1: find mission
            mission = await self.find_mission(cruise_id)
            if not mission:
                return {"success": False, "message": f"No PhysChem mission found for cruise '{cruise_id}'"}
            mission_id = mission["id"]
            logger.info(f"PhysChem mission {mission_id} ({mission.get('missionName')}) for cruise {cruise_id}")

            # Step 2: find operation (CTD cast)
            operation = await self.find_operation(mission_id, cast_number)
            if not operation:
                return {
                    "success": False,
                    "message": f"Operation {cast_number} not found in PhysChem mission {mission_id}",
                }
            operation_id = operation["id"]
            logger.info(f"PhysChem operation {operation_id} (op#{cast_number})")

            # Step 3: create salinometer instrument
            instrument = await self.create_instrument(operation_id)
            instrument_id = instrument["id"]
            logger.info(f"Created PhysChem instrument {instrument_id}")

            # Step 4: create PSAL parameter
            parameter = await self.create_parameter(instrument_id)
            parameter_id = parameter["id"]
            logger.info(f"Created PhysChem parameter {parameter_id}")

            # Step 5: create reading
            sample_num = 1
            if bottle_number:
                try:
                    sample_num = int(bottle_number)
                except ValueError:
                    pass

            reading = await self.create_reading(
                parameter_id=parameter_id,
                psal_value=psal_lab,
                sample_number=sample_num,
                value_datetime=utc_time,
            )
            reading_id = reading.get("id", "")
            logger.info(f"PhysChem reading {reading_id}: PSAL={psal_lab}")

            return {
                "success": True,
                "upload_id": str(reading_id),
                "mission_id": mission_id,
                "operation_id": operation_id,
                "parameter_id": parameter_id,
                "reading_id": reading_id,
            }

        except httpx.HTTPStatusError as e:
            msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            logger.error(f"PhysChem upload failed: {msg}")
            return {"success": False, "message": msg}
        except Exception as e:
            logger.error(f"PhysChem upload error: {e}")
            return {"success": False, "message": str(e)}


physchem_client = PhysChemClient()
