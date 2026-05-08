"""
QR code and label PDF generator.

Generates a printable label (PDF) for each salinity sample containing
human-readable metadata and a QR code linking to the lab measurement URL.
Label size: 50mm × 30mm (Phomemo M110 format).
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
LABEL_HEIGHT_MM = 30


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
    Generate a single 50mm × 30mm label PDF.
    Text stacked at the top, large centred QR code at the bottom.
    Returns the PDF as bytes. Optionally saves to output_path.
    """
    buf = io.BytesIO()

    w = LABEL_WIDTH_MM  * rl_mm
    h = LABEL_HEIGHT_MM * rl_mm

    margin_left   = 0.8 * rl_mm
    margin_right  = 1.0 * rl_mm
    margin_top    = 1.0 * rl_mm
    margin_bottom = 1.0 * rl_mm
    gap           = 1.5 * rl_mm   # gap between text and QR columns

    # Right column geometry (QR + UUID underneath)
    right_col_x = w / 2 + gap / 2
    right_col_w = w / 2 - margin_right - gap / 2

    # Build metadata lines — 7pt throughout, no UUID here
    SZ, LD = 7.0, 8.5
    UUID_SZ, UUID_LD = 8.0, 9.5

    uuid_lines  = [sample_id]
    uuid_height = UUID_LD

    # QR sits above the UUID block
    qr_size = min(right_col_w, h - margin_top - margin_bottom - uuid_height - 1.5 * rl_mm)
    qr_y    = margin_bottom + uuid_height + 1.0 * rl_mm
    time_str = utc_time.strftime("%Y-%m-%d %H:%M UTC")
    lat_str  = f"{latitude:.4f}°N"  if latitude  >= 0 else f"{abs(latitude):.4f}°S"
    lon_str  = f"{longitude:.4f}°E" if longitude >= 0 else f"{abs(longitude):.4f}°W"

    lines = [
        ("IMR Salinity Sample",       "Helvetica-Bold", SZ, LD),
        (platform_id,                 "Helvetica",      SZ, LD),
        (time_str,                    "Helvetica",      SZ, LD),
        (lat_str,                     "Helvetica",      SZ, LD),
        (lon_str,                     "Helvetica",      SZ, LD),
        (f"Depth: {depth_m:.1f} m",  "Helvetica-Bold", SZ, LD),
    ]
    if cruise_id:
        lines.append((f"Cruise: {cruise_id}",     "Helvetica",      SZ, LD))
    if cast_number:
        lines.append((f"Station: {cast_number}",  "Helvetica",      SZ, LD))
    if bottle_number:
        lines.append((f"Bottle: {bottle_number}", "Helvetica-Bold", SZ, LD))

    c = rl_canvas.Canvas(buf, pagesize=(w, h))

    # Text column — left half, small left margin
    y = h - margin_top
    for text, font, size, leading in lines:
        y -= leading
        c.setFont(font, size)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(margin_left, y, text)

    # QR code — right column, above UUID
    qr_bytes = generate_qr_code(label_url, size_px=200)
    c.drawImage(ImageReader(io.BytesIO(qr_bytes)), right_col_x, qr_y,
                width=qr_size, height=qr_size)

    # UUID — two lines below QR code, centred in right column
    c.setFont("Helvetica", UUID_SZ)
    c.setFillColorRGB(0, 0, 0)
    for i, uid_line in enumerate(uuid_lines):
        line_y = margin_bottom + (len(uuid_lines) - 1 - i) * UUID_LD
        c.drawCentredString(right_col_x + right_col_w / 2, line_y, uid_line)

    c.save()

    pdf_bytes = buf.getvalue()

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        logger.info(f"Label saved to {output_path}")

    return pdf_bytes
