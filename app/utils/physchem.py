"""
PhysChem API client — https://physchem-api.hi.no

Upload flow for each lab measurement:
  1. GET /mission/list?cruise=...           → find the mission by cruise ID
  2. GET /mission/{id}/operation/list       → find the CTD cast by UTC time + position
  3. POST /operation/{id}/instrument        → create a salinometer (BTL) instrument
  4. POST /instrument/{id}/parameter        → add PSAL_LAB parameter
  5. POST /parameter/{id}/reading           → store the measured salinity value
"""

import math
import httpx
import logging
from typing import Optional
from datetime import datetime
from app.config import settings
from app.utils import azure_auth

logger = logging.getLogger(__name__)


def _parse_json(r: httpx.Response) -> object:
    """Parse JSON response body, raising a clear error if empty or non-JSON."""
    text = r.text.strip()
    if not text:
        raise ValueError(
            f"PhysChem returned HTTP {r.status_code} with an empty body (URL: {r.url})"
        )
    try:
        return r.json()
    except Exception:
        raise ValueError(
            f"PhysChem returned non-JSON (HTTP {r.status_code}): {text[:300]} (URL: {r.url})"
        )


def _operation_score(
    op: dict,
    utc_time: Optional[datetime],
    latitude: Optional[float],
    longitude: Optional[float],
) -> float:
    """
    Lower is better. Primary: time difference in hours. Secondary: distance in degrees.
    Uses OperationDTO field names: timeStart, latitudeStart, longitudeStart.
    """
    time_diff_h = float("inf")
    val = op.get("timeStart")
    if val and utc_time is not None:
        try:
            op_time = datetime.fromisoformat(val.replace("Z", "+00:00")).replace(tzinfo=None)
            time_diff_h = abs((utc_time - op_time).total_seconds()) / 3600
        except Exception:
            pass

    dist_deg = 0.0
    op_lat = op.get("latitudeStart")
    op_lon = op.get("longitudeStart")
    if op_lat is not None and op_lon is not None and latitude is not None and longitude is not None:
        dist_deg = math.sqrt((float(op_lat) - latitude) ** 2 + (float(op_lon) - longitude) ** 2)

    return time_diff_h + dist_deg


class PhysChemClient:

    def __init__(self):
        self.base_url = settings.physchem_api_url.rstrip("/")
        self.api_key = settings.physchem_api_key

    def is_configured(self) -> bool:
        has_token = azure_auth.is_authenticated() or bool(self.api_key)
        has_url = self.base_url.startswith("http")
        return has_token and has_url

    def _headers(self) -> dict:
        token = azure_auth.get_access_token() or self.api_key
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "*/*",
        }

    async def find_mission(self, cruise: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.base_url}/mission/list",
                params={"cruise": cruise},
                headers=self._headers(),
            )
            logger.info(f"GET /mission/list → {r.status_code}: {r.text[:300]}")
            r.raise_for_status()
            missions = _parse_json(r)
            if not missions:
                logger.warning(f"No PhysChem mission found for cruise '{cruise}'")
                return None
            return missions[0]

    async def find_operation(
        self,
        mission_id: int,
        utc_time: datetime,
        latitude: float,
        longitude: float,
    ) -> Optional[dict]:
        """Find the CTD operation closest in time and position to the sample."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.base_url}/mission/{mission_id}/operation/list",
                params={"extend": "false", "instrumentTypeList": "false"},
                headers=self._headers(),
            )
            logger.info(
                f"GET /mission/{mission_id}/operation/list → {r.status_code}: {r.text[:500]}"
            )
            r.raise_for_status()
            operations = _parse_json(r)

        if not operations:
            logger.warning(f"No operations found in mission {mission_id}")
            return None

        best = min(operations, key=lambda op: _operation_score(op, utc_time, latitude, longitude))
        score = _operation_score(best, utc_time, latitude, longitude)
        logger.info(
            f"Best matching operation: id={best.get('id')} "
            f"op#={best.get('operationNumber')} score={score:.3f} "
            f"(time+dist; lower=better)"
        )
        return best

    async def create_instrument(self, operation_id: int, sample_id: str) -> dict:
        payload = {
            "instrumentType": "BOT",
            "instrumentSerialNumber": sample_id,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            logger.info(f"POST /operation/{operation_id}/instrument payload: {payload}")
            r = await client.post(
                f"{self.base_url}/operation/{operation_id}/instrument",
                json=payload,
                headers=self._headers(),
            )
            logger.info(f"POST /operation/{operation_id}/instrument → {r.status_code}: {r.text[:500]}")
            r.raise_for_status()
            return _parse_json(r)

    async def create_parameter(self, instrument_id: int) -> dict:
        payload = {
            "parameterCode": "PSAL",
            "ordinal": 1,
            "suppliedParameterName": "PSAL_LAB",
            "units": "PSU",
            "suppliedUnits": "PSU",
            "acquirementMethod": "discrete bottle salinometer",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self.base_url}/instrument/{instrument_id}/parameter",
                json=payload,
                headers=self._headers(),
            )
            logger.info(f"POST /instrument/{instrument_id}/parameter → {r.status_code}: {r.text[:300]}")
            r.raise_for_status()
            return _parse_json(r)

    async def create_reading(
        self,
        parameter_id: int,
        psal_value: float,
        sample_number: int,
        value_datetime: datetime,
    ) -> dict:
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
            logger.info(f"POST /parameter/{parameter_id}/reading → {r.status_code}: {r.text[:300]}")
            r.raise_for_status()
            return _parse_json(r)

    async def upload_measurement(
        self,
        sample_id: str,
        utc_time: datetime,
        latitude: float,
        longitude: float,
        depth_m: float,
        platform_id: str,
        psal_lab: float,
        psal_1: Optional[float] = None,
        psal_2: Optional[float] = None,
        cruise_id: Optional[str] = None,
        station_id: Optional[str] = None,
        cast_number: Optional[str] = None,
        bottle_number: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        if not self.is_configured():
            if not self.base_url.startswith("http"):
                return {"success": False, "message": "PhysChem API URL not set"}
            return {"success": False, "message": "PhysChem token not set or expired — paste a new token on the measure page"}

        if not cruise_id:
            return {"success": False, "message": "cruise_id required for PhysChem upload"}

        try:
            mission = await self.find_mission(cruise_id)
            if not mission:
                return {"success": False, "message": f"No PhysChem mission found for cruise '{cruise_id}'"}
            mission_id = mission["id"]
            logger.info(f"PhysChem mission {mission_id} ({mission.get('missionName')}) for cruise {cruise_id}")

            operation = await self.find_operation(mission_id, utc_time, latitude, longitude)
            if not operation:
                return {
                    "success": False,
                    "message": f"No matching operation found in PhysChem mission {mission_id}",
                }
            operation_id = operation["id"]
            logger.info(f"PhysChem operation {operation_id}")

            instrument = await self.create_instrument(operation_id, sample_id)
            instrument_id = instrument["id"]
            logger.info(f"Created PhysChem instrument {instrument_id}")

            parameter = await self.create_parameter(instrument_id)
            parameter_id = parameter["id"]
            logger.info(f"Created PhysChem parameter {parameter_id}")

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
            logger.info(f"PhysChem reading {reading_id}: PSAL_LAB={psal_lab}")

            return {
                "success": True,
                "upload_id": str(reading_id),
                "mission_id": mission_id,
                "operation_id": operation_id,
                "parameter_id": parameter_id,
                "reading_id": reading_id,
            }

        except httpx.HTTPStatusError as e:
            msg = f"HTTP {e.response.status_code}: {e.response.text[:300]}"
            logger.error(f"PhysChem upload failed: {msg}")
            return {"success": False, "message": msg}
        except Exception as e:
            logger.error(f"PhysChem upload error: {e}")
            return {"success": False, "message": str(e)}


physchem_client = PhysChemClient()
