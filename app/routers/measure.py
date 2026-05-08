"""
Lab measurement router.
Handles QR scan landing page and salinity measurement submission.
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import csv
import io

from app.database import get_db
from app.models.sample import SalinitySample, SampleMeasurement, SampleStatus
from app.utils.physchem import physchem_client
from app.utils import azure_auth

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _sync_physchem_measurements(db: Session, sample: SalinitySample, physchem_data: dict) -> bool:
    """
    Upsert PSAL_LAB readings returned by PhysChem into the local sample_measurements table.
    - Inserts a new row for any PhysChem reading not yet stored locally (identified by reading_id).
    - Fills in a missing physchem_ordinal on existing rows where the reading_id now matches.
    Returns True if any rows were written.
    """
    if not physchem_data:
        return False

    changed = False
    existing_by_reading_id = {
        m.physchem_reading_id: m
        for m in sample.measurements
        if m.physchem_reading_id
    }

    for entry in physchem_data.get("psal_lab_values", []):
        reading_id = entry.get("reading_id")
        value = entry.get("value")
        if reading_id is None or value is None:
            continue

        rid_str = str(reading_id)

        if rid_str in existing_by_reading_id:
            row = existing_by_reading_id[rid_str]
            if row.physchem_ordinal is None and entry.get("ordinal") is not None:
                row.physchem_ordinal = entry["ordinal"]
                changed = True
        else:
            db.add(SampleMeasurement(
                sample_id=sample.id,
                psal_lab=value,
                physchem_reading_id=rid_str,
                physchem_ordinal=entry.get("ordinal"),
            ))
            changed = True

    if changed:
        db.commit()
        db.refresh(sample)

    return changed


@router.get("/measure/{sample_id}", response_class=HTMLResponse)
async def measure_sample(request: Request, sample_id: str, db: Session = Depends(get_db)):
    """QR code lands here — shows sample metadata and measurement form."""
    sample = db.query(SalinitySample).filter(SalinitySample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    if sample.status == SampleStatus.registered:
        sample.status = SampleStatus.in_lab
        db.commit()

    try:
        physchem_data = await physchem_client.fetch_physchem_values(
            cruise_id=sample.cruise_id,
            utc_time=sample.utc_time,
            latitude=sample.latitude,
            longitude=sample.longitude,
            depth_m=sample.depth_m,
            bottle_number=sample.bottle_number,
        )
    except Exception:
        physchem_data = None

    _sync_physchem_measurements(db, sample, physchem_data)

    return templates.TemplateResponse("measure.html", {
        "request": request,
        "sample": sample,
        "physchem_authenticated": azure_auth.is_authenticated(),
        "physchem_token_status": azure_auth.get_token_status(),
        "physchem_data": physchem_data,
    })


@router.post("/measure/{sample_id}", response_class=HTMLResponse)
async def submit_measurement(
    request: Request,
    sample_id: str,
    psal_lab: float = Form(...),
    measured_by: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    sample = db.query(SalinitySample).filter(SalinitySample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    previous_status = sample.status
    now = datetime.utcnow()
    sample.psal_lab = psal_lab
    sample.measured_by = measured_by
    sample.measured_at = now
    sample.notes = notes or sample.notes
    sample.status = SampleStatus.measured

    # Record this measurement in the per-sample history table
    meas = SampleMeasurement(
        sample_id=sample.id,
        psal_lab=psal_lab,
        measured_by=measured_by,
        measured_at=now,
        notes=notes,
    )
    db.add(meas)
    db.commit()
    db.refresh(meas)

    upload_result = {"success": False, "message": "PhysChem not configured"}
    if physchem_client.is_configured():
        upload_result = await physchem_client.upload_measurement(
            sample_id=sample.id,
            utc_time=sample.utc_time,
            latitude=sample.latitude,
            longitude=sample.longitude,
            depth_m=sample.depth_m,
            platform_id=sample.platform_id,
            psal_lab=psal_lab,
            psal_1=sample.psal_1,
            psal_2=sample.psal_2,
            cruise_id=sample.cruise_id,
            station_id=sample.station_id,
            cast_number=sample.cast_number,
            bottle_number=sample.bottle_number,
            notes=notes,
        )
        if upload_result["success"]:
            sample.status = SampleStatus.uploaded
            sample.physchem_upload_id = upload_result.get("upload_id", "")
            sample.physchem_operation_id = str(upload_result.get("operation_id", ""))
            meas.physchem_reading_id = str(upload_result.get("reading_id", ""))
            meas.physchem_ordinal = upload_result.get("physchem_ordinal")
            db.commit()

    db.refresh(sample)
    if upload_result["success"]:
        physchem_data = await physchem_client.fetch_physchem_values(
            cruise_id=sample.cruise_id,
            utc_time=sample.utc_time,
            latitude=sample.latitude,
            longitude=sample.longitude,
            depth_m=sample.depth_m,
            bottle_number=sample.bottle_number,
        )
        return templates.TemplateResponse("measure_success.html", {
            "request": request,
            "sample": sample,
            "upload_result": upload_result,
            "physchem_data": physchem_data,
        })

    # Upload failed — restore uploaded status if this was an additional measurement attempt
    if previous_status == SampleStatus.uploaded:
        sample.status = SampleStatus.uploaded
        db.commit()

    physchem_data = await physchem_client.fetch_physchem_values(
        cruise_id=sample.cruise_id,
        utc_time=sample.utc_time,
        latitude=sample.latitude,
        longitude=sample.longitude,
        depth_m=sample.depth_m,
        bottle_number=sample.bottle_number,
    )
    return templates.TemplateResponse("measure.html", {
        "request": request,
        "sample": sample,
        "physchem_authenticated": azure_auth.is_authenticated(),
        "physchem_token_status": azure_auth.get_token_status(),
        "upload_error": upload_result.get("message", "Unknown error"),
        "upload_error_url": upload_result.get("physchem_url"),
        "physchem_data": physchem_data,
    })


@router.post("/measure/{sample_id}/upload", response_class=HTMLResponse)
async def retry_physchem_upload(
    request: Request,
    sample_id: str,
    db: Session = Depends(get_db),
):
    """Retry PhysChem upload for an already-measured sample."""
    sample = db.query(SalinitySample).filter(SalinitySample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    if sample.status == SampleStatus.uploaded:
        raise HTTPException(status_code=400, detail="Sample already uploaded to PhysChem")
    if sample.psal_lab is None:
        raise HTTPException(status_code=400, detail="No measurement recorded yet")

    upload_result = await physchem_client.upload_measurement(
        sample_id=str(sample.id),
        utc_time=sample.utc_time,
        latitude=sample.latitude,
        longitude=sample.longitude,
        depth_m=sample.depth_m,
        platform_id=sample.platform_id,
        psal_lab=sample.psal_lab,
        psal_1=sample.psal_1,
        psal_2=sample.psal_2,
        cruise_id=sample.cruise_id,
        station_id=sample.station_id,
        cast_number=sample.cast_number,
        bottle_number=sample.bottle_number,
        notes=sample.notes,
    )

    if upload_result["success"]:
        sample.status = SampleStatus.uploaded
        sample.physchem_upload_id = upload_result.get("upload_id", "")
        sample.physchem_operation_id = str(upload_result.get("operation_id", ""))
        # Update the most recent measurement record that hasn't been linked to PhysChem yet
        pending = (
            db.query(SampleMeasurement)
            .filter(
                SampleMeasurement.sample_id == sample.id,
                SampleMeasurement.physchem_reading_id == None,  # noqa: E711
            )
            .order_by(SampleMeasurement.created_at.desc())
            .first()
        )
        if pending:
            pending.physchem_reading_id = str(upload_result.get("reading_id", ""))
            pending.physchem_ordinal = upload_result.get("physchem_ordinal")
        db.commit()
        db.refresh(sample)
        physchem_data = await physchem_client.fetch_physchem_values(
            cruise_id=sample.cruise_id,
            utc_time=sample.utc_time,
            latitude=sample.latitude,
            longitude=sample.longitude,
            depth_m=sample.depth_m,
            bottle_number=sample.bottle_number,
        )
        return templates.TemplateResponse("measure_success.html", {
            "request": request,
            "sample": sample,
            "upload_result": upload_result,
            "physchem_data": physchem_data,
        })

    db.refresh(sample)
    physchem_data = await physchem_client.fetch_physchem_values(
        cruise_id=sample.cruise_id,
        utc_time=sample.utc_time,
        latitude=sample.latitude,
        longitude=sample.longitude,
        depth_m=sample.depth_m,
        bottle_number=sample.bottle_number,
    )
    return templates.TemplateResponse("measure.html", {
        "request": request,
        "sample": sample,
        "physchem_authenticated": azure_auth.is_authenticated(),
        "physchem_token_status": azure_auth.get_token_status(),
        "upload_error": upload_result.get("message", "Unknown error"),
        "upload_error_url": upload_result.get("physchem_url"),
        "physchem_data": physchem_data,
    })


@router.get("/samples", response_class=HTMLResponse)
async def list_samples(
    request: Request,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(SalinitySample)
    if platform:
        query = query.filter(SalinitySample.platform_id == platform)
    if status:
        query = query.filter(SalinitySample.status == status)
    samples = query.order_by(SalinitySample.created_at.desc()).limit(200).all()

    return templates.TemplateResponse("samples_list.html", {
        "request": request,
        "samples": samples,
        "SampleStatus": SampleStatus,
    })


@router.get("/samples/export.csv")
async def export_samples_csv(db: Session = Depends(get_db)):
    samples = db.query(SalinitySample).order_by(SalinitySample.utc_time.desc()).all()

    fields = [
        "id", "utc_time", "latitude", "longitude", "depth_m",
        "platform_id", "cruise_id", "station_id", "cast_number", "bottle_number",
        "psal_1", "psal_2", "status", "source", "created_at",
        "measurement_ordinal", "psal_lab", "measured_by", "measured_at",
        "measurement_notes", "physchem_reading_id", "physchem_operation_id",
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(fields)
    for s in samples:
        meta = [
            s.id,
            s.utc_time.strftime("%Y-%m-%dT%H:%M:%SZ") if s.utc_time else "",
            s.latitude, s.longitude, s.depth_m,
            s.platform_id, s.cruise_id or "", s.station_id or "",
            s.cast_number or "", s.bottle_number or "",
            s.psal_1 if s.psal_1 is not None else "",
            s.psal_2 if s.psal_2 is not None else "",
            s.status.value,
            s.source or "",
            s.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if s.created_at else "",
        ]
        if s.measurements:
            for m in s.measurements:
                writer.writerow(meta + [
                    m.physchem_ordinal if m.physchem_ordinal is not None else "",
                    m.psal_lab,
                    m.measured_by or "",
                    m.measured_at.strftime("%Y-%m-%dT%H:%M:%SZ") if m.measured_at else "",
                    m.notes or "",
                    m.physchem_reading_id or "",
                    s.physchem_operation_id or "",
                ])
        else:
            writer.writerow(meta + ["", "", "", "", "", "", s.physchem_operation_id or ""])

    buf.seek(0)
    filename = f"salinity_samples_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
