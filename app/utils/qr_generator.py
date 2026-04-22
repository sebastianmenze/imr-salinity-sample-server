"""
QR code and label PDF generator.

Generates a printable label (PDF) for each salinity sample containing
human-readable metadata and a QR code linking to the lab measurement URL.
Label size: 50mm × 50mm square (Phomemo M110 format).
"""

import qrcode
import io
import os
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm as rl_mm
from PIL import Image as PILImage
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

LABEL_WIDTH_MM  = 50
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
    Generate a single 50mm × 50mm square label PDF.
    Text stacked at the top, large centred QR code at the bottom.
    Returns the PDF as bytes. Optionally saves to output_path.
    """
    buf = io.BytesIO()

    w = LABEL_WIDTH_MM  * rl_mm   # 141.7 pt
    h = LABEL_HEIGHT_MM * rl_mm   # 141.7 pt
    margin = 2.0 * rl_mm

    # QR code: right 1/3, centred vertically
    qr_size = w / 3 - margin - 1 * rl_mm
    qr_x    = w - margin - qr_size
    qr_y    = (h - qr_size) / 2

    # Text column: left 2/3
    text_w = qr_x - margin - 1 * rl_mm

    # Build metadata lines — uniform 7pt throughout
    SZ, LD = 7.0, 8.5
    time_str = utc_time.strftime("%Y-%m-%d %H:%M UTC")
    lat_str  = f"{latitude:.4f}°N"  if latitude  >= 0 else f"{abs(latitude):.4f}°S"
    lon_str  = f"{longitude:.4f}°E" if longitude >= 0 else f"{abs(longitude):.4f}°W"

    lines = [
        ("IMR Salinity Sample",      "Helvetica-Bold", SZ, LD),
        (platform_id,                "Helvetica-Bold", SZ, LD),
        (time_str,                   "Helvetica",      SZ, LD),
        (lat_str,                    "Helvetica",      SZ, LD),
        (lon_str,                    "Helvetica",      SZ, LD),
        (f"Depth: {depth_m:.1f} m", "Helvetica",      SZ, LD),
    ]
    if cruise_id:
        lines.append((f"Cruise: {cruise_id}",   "Helvetica", SZ, LD))
    if cast_number:
        lines.append((f"Station: {cast_number}", "Helvetica", SZ, LD))
    if bottle_number:
        lines.append((f"Bottle: {bottle_number}", "Helvetica", SZ, LD))
    # Full UUID split across two lines
    lines.append((sample_id[:18], "Helvetica", SZ, LD))
    lines.append((sample_id[18:], "Helvetica", SZ, LD))

    c = rl_canvas.Canvas(buf, pagesize=(w, h))

    # Draw text top-down in left column
    y = h - margin
    for text, font, size, leading in lines:
        y -= leading
        c.setFont(font, size)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(margin, y, text)

    # Draw QR code on the right
    qr_bytes = generate_qr_code(label_url, size_px=200)
    c.drawImage(ImageReader(io.BytesIO(qr_bytes)), qr_x, qr_y,
                width=qr_size, height=qr_size)

    c.save()

    pdf_bytes = buf.getvalue()

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        logger.info(f"Label saved to {output_path}")

    return pdf_bytes
