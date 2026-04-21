"""
QR code and label PDF generator.

Generates a printable label (PDF) for each salinity sample containing
human-readable metadata and a QR code linking to the lab measurement URL.
Label size: 30mm × 50mm (Phomemo M110 format).
"""

import qrcode
import io
import os
from reportlab.lib.pagesizes import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Image, Spacer
from reportlab.lib.units import mm as rl_mm
from PIL import Image as PILImage
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

LABEL_WIDTH_MM = 30
LABEL_HEIGHT_MM = 50


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
    Generate a 30mm × 50mm label PDF for a salinity sample (Phomemo M110).
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
        "tiny_bold", parent=tiny, fontName="Helvetica-Bold", fontSize=6, leading=7.5
    )
    micro = ParagraphStyle(
        "micro", parent=styles["Normal"], fontSize=4, leading=5.5,
        textColor=colors.grey, wordWrap="CJK",
    )

    time_str = utc_time.strftime("%Y-%m-%d %H:%M UTC")
    lat_str = f"{latitude:.4f}°N" if latitude >= 0 else f"{abs(latitude):.4f}°S"
    lon_str = f"{longitude:.4f}°E" if longitude >= 0 else f"{abs(longitude):.4f}°W"

    meta_lines = [
        ("<b>IMR Salinity Sample</b>", tiny_bold),
        (f"<b>{platform_id}</b>", tiny_bold),
        (time_str, tiny),
        (f"{lat_str}  {lon_str}", tiny),
        (f"Depth: {depth_m:.1f} m", tiny),
    ]
    if cruise_id:
        meta_lines.append((f"Cruise: {cruise_id}", tiny))
    if station_id:
        meta_lines.append((f"Station: {station_id}", tiny))

    qr_size = 24 * rl_mm
    qr_bytes = generate_qr_code(label_url, size_px=150)
    qr_img = Image(io.BytesIO(qr_bytes), width=qr_size, height=qr_size)
    qr_img.hAlign = "CENTER"

    id_para = Paragraph(f"ID: {sample_id}", micro)

    story = [Paragraph(text, style) for text, style in meta_lines]
    story.append(Spacer(1, 1.5 * rl_mm))
    story.append(qr_img)
    story.append(Spacer(1, 1 * rl_mm))
    story.append(id_para)

    doc.build(story)

    pdf_bytes = buf.getvalue()

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        logger.info(f"Label saved to {output_path}")

    return pdf_bytes
