"""
Lab measurement router.
Handles QR scan landing page and salinity measurement submission.
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import uuid

from app.database import get_db
from app.models.sample import SalinitySample, SampleStatus
from app.utils.physchem import physchem_client
from app.utils import azure_auth

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/measure/{sample_id}", response_class=HTMLResponse)
async def measure_sample(request: Request, sample_id: uuid.UUID, db: Session = Depends(get_db)):
    """QR code lands here — shows sample metadata and measurement form."""
    sample = db.query(SalinitySample).filter(SalinitySample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    if sample.status == SampleStatus.registered:
        sample.status = SampleStatus.in_lab
        db.commit()

    return templates.TemplateResponse("measure.html", {
        "request": request,
        "sample": sample,
        "physchem_authenticated": azure_auth.is_authenticated(),
        "physchem_token_status": azure_auth.get_token_status(),
    })


@router.post("/measure/{sample_id}", response_class=HTMLResponse)
async def submit_measurement(
    request: Request,
    sample_id: uuid.UUID,
    psal_lab: float = Form(...),
    measured_by: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    sample = db.query(SalinitySample).filter(SalinitySample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    if sample.status == SampleStatus.uploaded:
        raise HTTPException(status_code=400, detail="Sample already uploaded to PhysChem")

    sample.psal_lab = psal_lab
    sample.measured_by = measured_by
    sample.measured_at = datetime.utcnow()
    sample.notes = notes or sample.notes
    sample.status = SampleStatus.measured
    db.commit()

    upload_result = {"success": False, "message": "PhysChem not configured"}
    if physchem_client.is_configured():
        upload_result = await physchem_client.upload_measurement(
            sample_id=str(sample.id),
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
            db.commit()

    db.refresh(sample)
    if upload_result["success"]:
        return templates.TemplateResponse("measure_success.html", {
            "request": request,
            "sample": sample,
            "upload_result": upload_result,
        })

    # Upload failed — stay on measure page so user can retry
    return templates.TemplateResponse("measure.html", {
        "request": request,
        "sample": sample,
        "physchem_authenticated": azure_auth.is_authenticated(),
        "physchem_token_status": azure_auth.get_token_status(),
        "upload_error": upload_result.get("message", "Unknown error"),
    })


@router.post("/measure/{sample_id}/upload", response_class=HTMLResponse)
async def retry_physchem_upload(
    request: Request,
    sample_id: uuid.UUID,
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
        db.commit()
        db.refresh(sample)
        return templates.TemplateResponse("measure_success.html", {
            "request": request,
            "sample": sample,
            "upload_result": upload_result,
        })

    db.refresh(sample)
    return templates.TemplateResponse("measure.html", {
        "request": request,
        "sample": sample,
        "physchem_authenticated": azure_auth.is_authenticated(),
        "physchem_token_status": azure_auth.get_token_status(),
        "upload_error": upload_result.get("message", "Unknown error"),
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
