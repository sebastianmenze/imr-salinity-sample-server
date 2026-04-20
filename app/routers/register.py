"""
Shipboard sample registration router.
Handles both manual entry and BOT file upload.
"""

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import uuid

from app.database import get_db
from app.models.sample import SalinitySample, SampleStatus
from app.utils.bot_parser import parse_bot_file
from app.utils.qr_generator import generate_label_pdf
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PLATFORMS = [
    "G.O. Sars", "Johan Hjort", "Kronprins Haakon",
    "Vendla", "Hans Brattström", "Other"
]


@router.get("/", response_class=HTMLResponse)
async def registration_home(request: Request):
    return templates.TemplateResponse("register.html", {
        "request": request,
        "platforms": PLATFORMS,
        "now": datetime.utcnow().strftime("%Y-%m-%dT%H:%M"),
    })


@router.post("/register/manual", response_class=HTMLResponse)
async def register_manual(
    request: Request,
    utc_time: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    depth_m: float = Form(...),
    platform_id: str = Form(...),
    cruise_id: Optional[str] = Form(None),
    station_id: Optional[str] = Form(None),
    cast_number: Optional[str] = Form(None),
    bottle_number: Optional[str] = Form(None),
    psal_1: Optional[float] = Form(None),
    psal_2: Optional[float] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    utc_dt = datetime.fromisoformat(utc_time.replace("Z", ""))
    sample = SalinitySample(
        id=uuid.uuid4(),
        utc_time=utc_dt,
        latitude=latitude,
        longitude=longitude,
        depth_m=depth_m,
        platform_id=platform_id,
        cruise_id=cruise_id or None,
        station_id=station_id or None,
        cast_number=cast_number or None,
        bottle_number=bottle_number or None,
        psal_1=psal_1,
        psal_2=psal_2,
        notes=notes,
        status=SampleStatus.registered,
        source="manual",
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return RedirectResponse(url=f"/label/{sample.id}", status_code=303)


@router.post("/register/bot", response_class=HTMLResponse)
async def register_from_bot(
    request: Request,
    bot_file: UploadFile = File(...),
    platform_id: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    cruise_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    content = (await bot_file.read()).decode("utf-8", errors="replace")
    bot = parse_bot_file(content, filename=bot_file.filename)

    if not bot.records:
        raise HTTPException(status_code=400, detail="No bottle records found in BTL file")

    # Use values from BTL header when form fields are not provided
    resolved_platform = platform_id or bot.platform_name or "Unknown"
    resolved_lat = latitude if latitude is not None else bot.latitude
    resolved_lon = longitude if longitude is not None else bot.longitude
    resolved_cruise = cruise_id or bot.cruise_id

    if resolved_lat is None or resolved_lon is None:
        raise HTTPException(
            status_code=400,
            detail="No NMEA position found in BTL file — please enter coordinates manually.",
        )

    samples = []
    for record in bot.records:
        sample = SalinitySample(
            id=uuid.uuid4(),
            utc_time=record.utc_time or bot.start_time or datetime.utcnow(),
            latitude=record.latitude if record.latitude is not None else resolved_lat,
            longitude=record.longitude if record.longitude is not None else resolved_lon,
            depth_m=record.depth_m,
            platform_id=resolved_platform,
            cruise_id=resolved_cruise,
            station_id=bot.cast_number,
            cast_number=record.cast_number or bot.cast_number,
            bottle_number=record.bottle_number,
            psal_1=record.psal_1,
            psal_2=record.psal_2,
            status=SampleStatus.registered,
            source="bot_file",
        )
        db.add(sample)
        samples.append(sample)

    db.commit()
    for s in samples:
        db.refresh(s)

    return templates.TemplateResponse("bot_results.html", {
        "request": request,
        "samples": samples,
        "base_url": settings.base_url,
        "filename": bot_file.filename,
        "bot": bot,
    })


@router.get("/label/{sample_id}", response_class=HTMLResponse)
async def view_label(request: Request, sample_id: uuid.UUID, db: Session = Depends(get_db)):
    sample = db.query(SalinitySample).filter(SalinitySample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return templates.TemplateResponse("label_view.html", {
        "request": request,
        "sample": sample,
        "label_url": sample.label_url,
    })


@router.get("/label/{sample_id}/pdf")
async def download_label_pdf(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    from fastapi.responses import Response
    sample = db.query(SalinitySample).filter(SalinitySample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    pdf_bytes = generate_label_pdf(
        sample_id=str(sample.id),
        utc_time=sample.utc_time,
        latitude=sample.latitude,
        longitude=sample.longitude,
        depth_m=sample.depth_m,
        platform_id=sample.platform_id,
        label_url=sample.label_url,
        cruise_id=sample.cruise_id,
        station_id=sample.station_id,
        cast_number=sample.cast_number,
        bottle_number=sample.bottle_number,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="label_{str(sample.id)[:8]}.pdf"'},
    )
