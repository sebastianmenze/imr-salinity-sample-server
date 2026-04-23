"""
PhysChem API client — https://physchem-api-test.hi.no

Upload flow for each lab measurement:
  1. GET /mission/list?cruise=...           → find the mission by cruise ID
  2. GET /mission/{id}/operation/list       → find the CTD cast by UTC time + position
  3. GET /operation/{id}/instrument/list    → find existing BOT instrument (never create)
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


def _mission_score(mission: dict, utc_time: Optional[datetime]) -> float:
    """Score a mission by proximity of its time range to the sample. Lower is better."""
    if utc_time is None:
        return float("inf")
    sample_t = utc_time.replace(tzinfo=None) if utc_time.tzinfo else utc_time

    start_t = end_t = None
    for key in ("timeStart", "dateStart"):
        val = mission.get(key)
        if val:
            try:
                start_t = datetime.fromisoformat(val.replace("Z", "+00:00")).replace(tzinfo=None)
                break
            except Exception:
                pass
    for key in ("timeEnd", "dateEnd"):
        val = mission.get(key)
        if val:
            try:
                end_t = datetime.fromisoformat(val.replace("Z", "+00:00")).replace(tzinfo=None)
                break
            except Exception:
                pass

    if start_t is None:
        return float("inf")
    if end_t and start_t <= sample_t <= end_t:
        return 0.0
    if end_t:
        return min(abs((sample_t - start_t).total_seconds()), abs((sample_t - end_t).total_seconds())) / 3600
    return abs((sample_t - start_t).total_seconds()) / 3600


def _operation_score(
    op: dict,
    utc_time: Optional[datetime],
    latitude: Optional[float],
    longitude: Optional[float],
) -> float:
    """Lower is better. Primary: time diff in hours. Secondary: position distance in degrees."""
    time_diff_h = float("inf")
    val = op.get("timeStart")
    if val and utc_time is not None:
        try:
            op_time = datetime.fromisoformat(val.replace("Z", "+00:00")).replace(tzinfo=None)
            sample_time = utc_time.replace(tzinfo=None) if utc_time.tzinfo else utc_time
            time_diff_h = abs((sample_time - op_time).total_seconds()) / 3600
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

    def _editor_url(self, mission_id, operation_id, instrument_id) -> str:
        editor_base = self.base_url.replace("-api-", "-editor-")
        return f"{editor_base}/mission/{mission_id}/operation/{operation_id}/instrument/{instrument_id}/parameter"

    async def find_mission(
        self,
        cruise: Optional[str],
        utc_time: Optional[datetime] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Optional[dict]:
        params = {"cruise": cruise} if cruise else {}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.base_url}/mission/list",
                params=params,
                headers=self._headers(),
            )
            logger.info(f"GET /mission/list → {r.status_code}: {r.text[:300]}")
            r.raise_for_status()
            missions = _parse_json(r)

        if not missions:
            logger.warning(f"No PhysChem missions found" + (f" for cruise '{cruise}'" if cruise else ""))
            return None

        if cruise:
            return missions[0]

        # No cruise ID — score all missions by time proximity and return the best
        best = min(missions, key=lambda m: _mission_score(m, utc_time))
        score = _mission_score(best, utc_time)
        logger.info(
            f"No cruise ID — best mission by time: id={best.get('id')} "
            f"cruise={best.get('cruise')} score={score:.1f}h"
        )
        return best

    async def find_operation(
        self,
        mission_id: int,
        utc_time: Optional[datetime],
        latitude: Optional[float],
        longitude: Optional[float],
    ) -> Optional[dict]:
        """Find the CTD operation closest in time and position to the sample."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.base_url}/mission/{mission_id}/operation/list",
                params={"extend": "false", "instrumentTypeList": "false"},
                headers=self._headers(),
            )
            logger.info(f"GET /mission/{mission_id}/operation/list → {r.status_code}: {r.text[:500]}")
            r.raise_for_status()
            operations = _parse_json(r)

        if not operations:
            logger.warning(f"No operations found in mission {mission_id}")
            return None

        best = min(operations, key=lambda op: _operation_score(op, utc_time, latitude, longitude))
        score = _operation_score(best, utc_time, latitude, longitude)
        logger.info(
            f"Best matching operation: id={best.get('id')} "
            f"op#={best.get('operationNumber')} score={score:.3f}"
        )
        return best

    async def find_bot_instrument(self, operation_id: int) -> Optional[dict]:
        """Find the existing BOT instrument on a CTD operation."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.base_url}/operation/{operation_id}/instrument/list",
                headers=self._headers(),
            )
            logger.info(f"GET /operation/{operation_id}/instrument/list → {r.status_code}: {r.text[:300]}")
            r.raise_for_status()
            instruments = _parse_json(r)

        for inst in instruments:
            if inst.get("instrumentType") == "BOT":
                logger.info(f"Found BOT instrument {inst['id']} on operation {operation_id}")
                return inst

        logger.warning(f"No BOT instrument found on operation {operation_id}")
        return None

    async def _get_parameter_readings(self, parameter_id: int) -> list:
        """Fetch all readings for a parameter."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.base_url}/parameter/{parameter_id}/reading/list",
                headers=self._headers(),
            )
            logger.info(f"GET /parameter/{parameter_id}/reading/list → {r.status_code}")
            r.raise_for_status()
            return _parse_json(r)

    async def find_or_create_psal_parameter(
        self,
        instrument_id: int,
        sample_number: Optional[int] = None,
        psal_value: Optional[float] = None,
        value_datetime: Optional[datetime] = None,
    ) -> dict:
        """
        Return a PSAL_LAB (S LAB) parameter to write a reading to.

        - If no S LAB parameter exists: create one with ordinal=1.
        - If some exist but one lacks a reading at sample_number: return that one.
        - If all existing S LAB params already have a reading at sample_number:
          create a new one with ordinal = max_existing_ordinal + 1.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.base_url}/instrument/{instrument_id}/parameter/list",
                headers=self._headers(),
            )
            logger.info(f"GET /instrument/{instrument_id}/parameter/list → {r.status_code}: {r.text[:2000]}")
            r.raise_for_status()
            params = _parse_json(r)

        slab_params = [p for p in params if p.get("suppliedParameterName") == "S LAB"]

        next_ordinal = 1
        if slab_params:
            if sample_number is not None:
                # Check each existing S LAB parameter for a reading at this sampleNumber
                for p in slab_params:
                    try:
                        readings = await self._get_parameter_readings(p["id"])
                        has_reading = any(rd.get("sampleNumber") == sample_number for rd in readings)
                        if not has_reading:
                            logger.info(
                                f"Reusing S LAB parameter {p['id']} "
                                f"(no reading yet at sampleNumber {sample_number})"
                            )
                            return p
                    except Exception as e:
                        logger.warning(f"Could not check readings for parameter {p['id']}: {e}")
                        return p

                # All existing S LAB params have a reading at this sampleNumber → increment ordinal
                max_ordinal = max(p.get("ordinal", 1) for p in slab_params)
                next_ordinal = max_ordinal + 1
                logger.info(
                    f"All S LAB parameters already have a reading at sampleNumber {sample_number}; "
                    f"creating new parameter with ordinal {next_ordinal}"
                )
            else:
                # No sample_number to check — return the first existing S LAB parameter
                logger.info(f"Reusing existing S LAB parameter {slab_params[0]['id']} (no sample_number to check)")
                return slab_params[0]

        # Create a new PSAL_LAB parameter
        next_param_number = max((p.get("parameterNumber", 0) for p in params), default=0) + 1
        payload = {
            "parameterNumber": next_param_number,
            "parameterCode": "PSAL_LAB",
            "ordinal": next_ordinal,
            "suppliedParameterName": "S LAB",
            "units": "Dmnless",
            "processingLevel": "L0",
            "acquirementMethod": "1019900",
        }
        if sample_number is not None and psal_value is not None and value_datetime is not None:
            payload["reading"] = [{
                "sampleNumber": sample_number,
                "valueDateTime": value_datetime.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "valueDec": psal_value,
                "quality": "1",
            }]

        logger.info(f"Creating PSAL_LAB parameter on instrument {instrument_id} with payload: {payload}")
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self.base_url}/instrument/{instrument_id}/parameter",
                json=payload,
                headers=self._headers(),
            )
            logger.info(f"POST /instrument/{instrument_id}/parameter → {r.status_code}: {r.text[:500]}")
            r.raise_for_status()
            return _parse_json(r)

    async def find_sample_number_by_depth(
        self, instrument_id: int, depth_m: float
    ) -> Optional[int]:
        """Match depth_m to a sampleNumber via PRES readings on the BOT instrument."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.base_url}/instrument/{instrument_id}/parameter/list",
                headers=self._headers(),
            )
            r.raise_for_status()
            params = _parse_json(r)

        pres_param = next((p for p in params if p.get("parameterCode") == "PRES"), None)
        if not pres_param:
            logger.warning(f"No PRES parameter on instrument {instrument_id}, cannot match by depth")
            return None

        readings = await self._get_parameter_readings(pres_param["id"])
        if not readings:
            logger.warning(f"No PRES readings on instrument {instrument_id}, cannot match by depth")
            return None

        best = min(readings, key=lambda rd: abs(float(rd.get("valueDec", 0)) - depth_m))
        diff = abs(float(best.get("valueDec", 0)) - depth_m)
        logger.info(
            f"Depth match: {depth_m}m → sampleNumber={best['sampleNumber']} "
            f"at {best.get('valueDec')}dbar (diff={diff:.1f}m)"
        )
        return best["sampleNumber"]

    async def upsert_reading(
        self,
        parameter_id: int,
        psal_value: float,
        sample_number: int,
        value_datetime: datetime,
    ) -> dict:
        """Create a reading for sample_number; skip if one already exists."""
        readings = await self._get_parameter_readings(parameter_id)

        existing = next((rd for rd in readings if rd.get("sampleNumber") == sample_number), None)
        if existing:
            logger.info(
                f"Reading already exists for parameter {parameter_id} sampleNumber {sample_number} "
                f"(id={existing['id']}, valueDec={existing.get('valueDec')}) — not overwriting"
            )
            return existing

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
            logger.info(f"POST /parameter/{parameter_id}/reading → {r.status_code}: {r.text[:500]}")
            r.raise_for_status()
            return _parse_json(r)

    async def fetch_physchem_values(
        self,
        cruise_id: Optional[str],
        utc_time: Optional[datetime],
        latitude: Optional[float],
        longitude: Optional[float],
        depth_m: float,
        bottle_number: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Look up existing PSAL (CTD sensor) and PSAL_LAB readings in PhysChem for a sample.
        Returns a dict with psal_values and psal_lab_values lists, or None if unavailable.
        """
        try:
            if not self.is_configured():
                return None

            mission = await self.find_mission(cruise_id, utc_time=utc_time, latitude=latitude, longitude=longitude)
            if not mission:
                return None

            operation = await self.find_operation(mission["id"], utc_time, latitude, longitude)
            if not operation:
                return None

            instrument = await self.find_bot_instrument(operation["id"])
            if not instrument:
                return None

            instrument_id = instrument["id"]

            sample_num = await self.find_sample_number_by_depth(instrument_id, depth_m)
            if sample_num is None and bottle_number:
                try:
                    sample_num = int(bottle_number)
                except ValueError:
                    pass

            # Fetch all parameters on the instrument
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(
                    f"{self.base_url}/instrument/{instrument_id}/parameter/list",
                    headers=self._headers(),
                )
                r.raise_for_status()
                params = _parse_json(r)

            psal_values = []
            psal_lab_values = []

            for p in params:
                code = p.get("parameterCode", "")
                name = p.get("suppliedParameterName", "")

                if code in ("PSAL", "PSAL_LAB") or name == "S LAB":
                    try:
                        readings = await self._get_parameter_readings(p["id"])
                        reading = (
                            next((rd for rd in readings if rd.get("sampleNumber") == sample_num), None)
                            if sample_num is not None
                            else None
                        )
                        entry = {
                            "parameter_id": p["id"],
                            "ordinal": p.get("ordinal"),
                            "supplied_name": name,
                            "value": float(reading["valueDec"]) if reading and reading.get("valueDec") is not None else None,
                            "reading_id": reading.get("id") if reading else None,
                            "sample_number": reading.get("sampleNumber") if reading else None,
                        }
                        if code == "PSAL":
                            psal_values.append(entry)
                        else:
                            psal_lab_values.append(entry)
                    except Exception as e:
                        logger.warning(f"Could not fetch readings for parameter {p['id']}: {e}")

            return {
                "sample_number": sample_num,
                "mission_id": mission["id"],
                "operation_id": operation["id"],
                "instrument_id": instrument_id,
                "psal_values": psal_values,
                "psal_lab_values": psal_lab_values,
                "physchem_url": self._editor_url(mission["id"], operation["id"], instrument_id),
            }

        except Exception as e:
            logger.warning(f"fetch_physchem_values failed: {e}")
            return None

    async def upload_measurement(
        self,
        sample_id: str,
        utc_time: Optional[datetime],
        latitude: Optional[float],
        longitude: Optional[float],
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

        if utc_time is None:
            return {"success": False, "message": "Sample has no UTC timestamp — edit the BTL table to add one before uploading"}

        try:
            mission = await self.find_mission(cruise_id, utc_time=utc_time, latitude=latitude, longitude=longitude)
            if not mission:
                label = f"cruise '{cruise_id}'" if cruise_id else "time/position"
                return {"success": False, "message": f"No PhysChem mission found matching {label}"}
            mission_id = mission["id"]
            logger.info(f"PhysChem mission {mission_id} (cruise={mission.get('cruise')})")

            operation = await self.find_operation(mission_id, utc_time, latitude, longitude)
            if not operation:
                return {"success": False, "message": f"No matching CTD operation found in PhysChem mission {mission_id}"}
            operation_id = operation["id"]
            logger.info(f"PhysChem operation {operation_id}")

            instrument = await self.find_bot_instrument(operation_id)
            if not instrument:
                return {"success": False, "message": f"No BOT instrument found on PhysChem operation {operation_id} — ensure the CTD cast has bottle data in PhysChem"}
            instrument_id = instrument["id"]

            sample_num = await self.find_sample_number_by_depth(instrument_id, depth_m)
            if sample_num is None:
                sample_num = 1
                if bottle_number:
                    try:
                        sample_num = int(bottle_number)
                    except ValueError:
                        pass
                logger.info(f"Depth match unavailable, using bottle_number as sampleNumber: {sample_num}")

            parameter = await self.find_or_create_psal_parameter(
                instrument_id,
                sample_number=sample_num,
                psal_value=psal_lab,
                value_datetime=utc_time,
            )
            parameter_id = parameter["id"]
            logger.info(f"Using PhysChem PSAL parameter {parameter_id}")

            reading = await self.upsert_reading(
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
                "instrument_id": instrument_id,
                "parameter_id": parameter_id,
                "reading_id": reading_id,
                "physchem_url": self._editor_url(mission_id, operation_id, instrument_id),
            }

        except httpx.HTTPStatusError as e:
            msg = f"HTTP {e.response.status_code}: {e.response.text[:300]}"
            logger.error(f"PhysChem upload failed: {msg}")
            return {"success": False, "message": msg}
        except Exception as e:
            logger.error(f"PhysChem upload error: {e}")
            return {"success": False, "message": str(e)}


physchem_client = PhysChemClient()
