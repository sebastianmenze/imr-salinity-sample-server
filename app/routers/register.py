"""
Shipboard sample registration router.
Handles both manual entry and BTL file upload (two-step: preview → confirm).
"""

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List
import uuid
import json

from app.database import get_db
from app.models.sample import SalinitySample, SampleStatus
from app.utils.bot_parser import parse_bot_file
from app.utils.qr_generator import generate_label_pdf
from app.config import settings
from app.data.platforms import PLATFORMS

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


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
    psal_1: Optional[str] = Form(None),
    psal_2: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    utc_dt = datetime.fromisoformat(utc_time.replace("Z", ""))
    psal_1_val = float(psal_1) if psal_1 else None
    psal_2_val = float(psal_2) if psal_2 else None
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
        psal_1=psal_1_val,
        psal_2=psal_2_val,
        notes=notes,
        status=SampleStatus.registered,
        source="manual",
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return RedirectResponse(url=f"/label/{sample.id}", status_code=303)


@router.post("/register/bot/preview", response_class=HTMLResponse)
async def register_bot_preview(
    request: Request,
    bot_file: UploadFile = File(...),
):
    """Parse a BTL file and show a bottle selection table before registering."""
    content = (await bot_file.read()).decode("utf-8", errors="replace")
    bot = parse_bot_file(content, filename=bot_file.filename)

    if not bot.records:
        raise HTTPException(status_code=400, detail="No bottle records found in BTL file")

    bottles = [
        {
            "idx": i,
            "bottle_number": r.bottle_number,
            "depth_m": r.depth_m,
            "psal_1": r.psal_1,
            "psal_2": r.psal_2,
            "temperature": r.temperature,
            "utc_time": r.utc_time.isoformat() if r.utc_time else (
                bot.start_time.isoformat() if bot.start_time else None
            ),
            "latitude": r.latitude if r.latitude is not None else bot.latitude,
            "longitude": r.longitude if r.longitude is not None else bot.longitude,
            "cast_number": r.cast_number or bot.cast_number,
        }
        for i, r in enumerate(bot.records)
    ]

    return templates.TemplateResponse("bot_preview.html", {
        "request": request,
        "bot": bot,
        "bottles": bottles,
        "bottles_json": json.dumps(bottles),
        "filename": bot_file.filename,
    })


@router.post("/register/bot/confirm", response_class=HTMLResponse)
async def register_bot_confirm(
    request: Request,
    bottles_json: str = Form(...),
    selected: List[str] = Form(default=[]),
    platform_name: Optional[str] = Form(None),
    cruise_id: Optional[str] = Form(None),
    cast_number: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Create SalinitySample records for each selected bottle."""
    if not selected:
        raise HTTPException(status_code=400, detail="No bottles selected")

    bottles = json.loads(bottles_json)
    selected_set = set(selected)
    # Pre-validate: at least one selected bottle must have a timestamp
    if not any(b.get("utc_time") for b in bottles if str(b["idx"]) in selected_set):
        raise HTTPException(status_code=400, detail="All selected bottles are missing UTC timestamps. Edit the table to add timestamps before registering.")

    samples = []
    skipped = 0
    for bottle in bottles:
        if str(bottle["idx"]) not in selected_set:
            continue

        if not bottle.get("utc_time"):
            skipped += 1
            continue

        utc_time = datetime.fromisoformat(bottle["utc_time"])

        sample = SalinitySample(
            id=uuid.uuid4(),
            utc_time=utc_time,
            latitude=bottle.get("latitude"),
            longitude=bottle.get("longitude"),
            depth_m=bottle["depth_m"],
            platform_id=platform_name or "Unknown",
            cruise_id=cruise_id or None,
            station_id=cast_number or None,
            cast_number=cast_number or bottle.get("cast_number"),
            bottle_number=bottle.get("bottle_number"),
            psal_1=bottle.get("psal_1"),
            psal_2=bottle.get("psal_2"),
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
        "filename": f"{len(samples)} bottle(s) from station {cast_number or '—'}",
        "bot": None,
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
