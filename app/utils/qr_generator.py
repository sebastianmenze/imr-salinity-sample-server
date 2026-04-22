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

    # QR code: right side, centred vertically
    qr_size = 30 * rl_mm
    qr_x    = w - margin - qr_size
    qr_y    = (h - qr_size) / 2

    # Text column: everything to the left of the QR
    text_w = qr_x - margin - 1.5 * rl_mm   # 1.5 mm gap before QR

    # Build metadata lines: (text, font_name, font_size, leading)
    time_str = utc_time.strftime("%Y-%m-%d %H:%M")
    lat_str  = f"{latitude:.3f}°N"  if latitude  >= 0 else f"{abs(latitude):.3f}°S"
    lon_str  = f"{longitude:.3f}°E" if longitude >= 0 else f"{abs(longitude):.3f}°W"

    lines = [
        ("IMR Salinity",             "Helvetica-Bold", 7.0, 8.5),
        ("Sample",                   "Helvetica-Bold", 7.0, 8.5),
        (platform_id,                "Helvetica-Bold", 6.0, 7.5),
        (time_str + " UTC",          "Helvetica",      5.5, 7.0),
        (lat_str,                    "Helvetica",      5.5, 6.5),
        (lon_str,                    "Helvetica",      5.5, 6.5),
        (f"Depth: {depth_m:.1f} m", "Helvetica",      5.5, 6.5),
    ]
    if cruise_id:
        lines.append((f"C: {cruise_id}", "Helvetica", 5.0, 6.0))
    if cast_number:
        lines.append((f"St: {cast_number}", "Helvetica", 5.0, 6.0))
    if bottle_number:
        lines.append((f"Bot: {bottle_number}", "Helvetica", 5.0, 6.0))
    lines.append((f"ID:{sample_id[:8]}", "Helvetica", 4.5, 6.0))

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
