"""
QR code and label PDF generator.

Generates a printable label (PDF) for each salinity sample containing
human-readable metadata and a QR code linking to the lab measurement URL.
Label size: 62mm × 40mm (Brother QL format).
"""

import qrcode
import io
import os
from reportlab.lib.pagesizes import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Image, Table
from reportlab.lib.units import mm as rl_mm
from PIL import Image as PILImage
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

LABEL_WIDTH_MM = 62
LABEL_HEIGHT_MM = 40


def generate_qr_code(url: str, size_px: int = 200) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img = img.resize((size_px, size_px), PILImage.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def generate_label_pdf(
    sample_id: str,
    utc_time: datetime,
    latitude: float,
    longitude: float,
    depth_m: float,
    platform_id: str,
    label_url: str,
    cruise_id: Optional[str] = None,
    station_id: Optional[str] = None,
    cast_number: Optional[str] = None,
    bottle_number: Optional[str] = None,
    output_path: Optional[str] = None,
) -> bytes:
    """
    Generate a 62mm × 40mm label PDF for a salinity sample.
    Returns the PDF as bytes. Optionally saves to output_path.
    """
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=(LABEL_WIDTH_MM * rl_mm, LABEL_HEIGHT_MM * rl_mm),
        leftMargin=2 * rl_mm,
        rightMargin=2 * rl_mm,
        topMargin=2 * rl_mm,
        bottomMargin=2 * rl_mm,
    )

    styles = getSampleStyleSheet()
    tiny = ParagraphStyle(
        "tiny", parent=styles["Normal"], fontSize=5.5, leading=7, spaceAfter=0
    )
    tiny_bold = ParagraphStyle(
        "tiny_bold", parent=tiny, fontName="Helvetica-Bold"
    )
    micro = ParagraphStyle(
        "micro", parent=styles["Normal"], fontSize=4.5, leading=6, textColor=colors.grey
    )

    qr_bytes = generate_qr_code(label_url, size_px=120)
    qr_img = Image(io.BytesIO(qr_bytes), width=18 * rl_mm, height=18 * rl_mm)

    time_str = utc_time.strftime("%Y-%m-%d %H:%M UTC")
    lat_str = f"{latitude:.4f}°N" if latitude >= 0 else f"{abs(latitude):.4f}°S"
    lon_str = f"{longitude:.4f}°E" if longitude >= 0 else f"{abs(longitude):.4f}°W"

    meta_lines = [
        "<b>IMR Salinity Sample</b>",
        f"<b>{platform_id}</b>",
        time_str,
        f"{lat_str}  {lon_str}",
        f"Depth: {depth_m:.1f} m",
    ]
    if cruise_id:
        meta_lines.append(f"Cruise: {cruise_id}")
    if station_id:
        meta_lines.append(f"Station: {station_id}")
    if cast_number:
        meta_lines.append(f"Cast: {cast_number}  Btl: {bottle_number or '-'}")

    meta_content = [
        Paragraph(line, tiny_bold if i == 0 else tiny)
        for i, line in enumerate(meta_lines)
    ]

    table = Table(
        [[meta_content, qr_img]],
        colWidths=[36 * rl_mm, 20 * rl_mm],
    )
    table.setStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ])

    id_para = Paragraph(f"ID: {str(sample_id)[:8]}…", micro)

    doc.build([table, id_para])

    pdf_bytes = buf.getvalue()

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        logger.info(f"Label saved to {output_path}")

    return pdf_bytes
