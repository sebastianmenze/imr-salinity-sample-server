"""
QR code and label PDF generator.

Generates a printable label (PDF) for each salinity sample containing
human-readable metadata and a QR code linking to the lab measurement URL.
Label size: 30mm × 50mm (Phomemo M110 format).
"""

import qrcode
import io
import os
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
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
    Generate a single 30mm × 50mm label PDF for a salinity sample (Phomemo M110).
    Returns the PDF as bytes. Optionally saves to output_path.
    """
    buf = io.BytesIO()

    w = LABEL_WIDTH_MM * rl_mm   # 85.0 pt
    h = LABEL_HEIGHT_MM * rl_mm  # 141.7 pt
    margin = 2 * rl_mm           # 5.67 pt
    usable_w = w - 2 * margin    # 73.7 pt

    c = rl_canvas.Canvas(buf, pagesize=(w, h))

    # --- metadata text lines (font, size, leading) ---
    time_str = utc_time.strftime("%Y-%m-%d %H:%M UTC")
    lat_str = f"{latitude:.4f}N" if latitude >= 0 else f"{abs(latitude):.4f}S"
    lon_str = f"{longitude:.4f}E" if longitude >= 0 else f"{abs(longitude):.4f}W"

    lines = [
        ("IMR Salinity Sample", "Helvetica-Bold", 6.0, 7.5),
        (platform_id,           "Helvetica-Bold", 6.0, 7.5),
        (time_str,              "Helvetica",       5.5, 7.0),
        (f"{lat_str}  {lon_str}", "Helvetica",     5.5, 7.0),
        (f"Depth: {depth_m:.1f} m", "Helvetica",  5.5, 7.0),
    ]
    if cruise_id:
        lines.append((f"Cruise: {cruise_id}", "Helvetica", 5.5, 7.0))
    if station_id:
        lines.append((f"Station: {station_id}", "Helvetica", 5.5, 7.0))

    # --- draw text top-down ---
    y = h - margin
    for text, font, size, leading in lines:
        y -= leading
        c.setFont(font, size)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(margin, y, text)

    # --- QR code, centred ---
    qr_size = 22 * rl_mm
    gap = 1.5 * rl_mm
    y -= gap
    qr_y = y - qr_size
    qr_x = (w - qr_size) / 2
    qr_bytes = generate_qr_code(label_url, size_px=150)
    c.drawImage(ImageReader(io.BytesIO(qr_bytes)), qr_x, qr_y,
                width=qr_size, height=qr_size)
    y = qr_y - gap

    # --- sample ID in small grey text, wrapped if too wide ---
    id_font = "Helvetica"
    id_size = 3.5
    id_leading = 4.5
    c.setFont(id_font, id_size)
    c.setFillGray(0.55)
    id_str = f"ID: {sample_id}"
    if stringWidth(id_str, id_font, id_size) <= usable_w:
        c.drawString(margin, y - id_leading, id_str)
    else:
        mid = len(id_str) // 2
        c.drawString(margin, y - id_leading,       id_str[:mid])
        c.drawString(margin, y - id_leading * 2,   id_str[mid:])

    c.save()

    pdf_bytes = buf.getvalue()

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        logger.info(f"Label saved to {output_path}")

    return pdf_bytes
