"""
QR code and label PDF generator.

Generates a printable label (PDF) for each salinity sample containing
human-readable metadata and a QR code linking to the lab measurement URL.
Label size: 50mm × 20mm landscape (Phomemo M110 format).
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

LABEL_WIDTH_MM  = 50
LABEL_HEIGHT_MM = 20


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
    Generate a single 50mm × 20mm landscape label PDF (Phomemo M110).
    QR code on the right, metadata text on the left.
    Returns the PDF as bytes. Optionally saves to output_path.
    """
    buf = io.BytesIO()

    w = LABEL_WIDTH_MM  * rl_mm   # 141.7 pt
    h = LABEL_HEIGHT_MM * rl_mm   #  56.7 pt
    margin = 1.5 * rl_mm          #   4.25 pt

    # QR code fills the usable height on the right side
    qr_size = h - 2 * margin      # ~47.2 pt = 16.7 mm
    qr_x = w - margin - qr_size
    qr_y = margin

    # Text column sits to the left of the QR code
    text_col_w = qr_x - margin - 1 * rl_mm   # 1 mm gap before QR

    # --- build metadata lines: (text, font_name, font_size, leading) ---
    time_str = utc_time.strftime("%Y-%m-%d %H:%M UTC")
    lat_str  = f"{latitude:.4f}N"  if latitude  >= 0 else f"{abs(latitude):.4f}S"
    lon_str  = f"{longitude:.4f}E" if longitude >= 0 else f"{abs(longitude):.4f}W"

    lines = [
        ("IMR Salinity Sample",       "Helvetica-Bold", 5.5, 7.0),
        (platform_id,                 "Helvetica-Bold", 5.0, 6.5),
        (time_str,                    "Helvetica",      4.5, 6.0),
        (f"{lat_str}  {lon_str}",     "Helvetica",      4.5, 6.0),
        (f"Depth: {depth_m:.1f} m",  "Helvetica",      4.5, 6.0),
    ]
    if cruise_id:
        lines.append((f"Cruise: {cruise_id}", "Helvetica", 4.5, 6.0))
    if station_id:
        lines.append((f"Station: {station_id}", "Helvetica", 4.5, 6.0))

    c = rl_canvas.Canvas(buf, pagesize=(w, h))

    # Draw text top-down in the left column
    y = h - margin
    for text, font, size, leading in lines:
        y -= leading
        c.setFont(font, size)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(margin, y, text)

    # Sample ID — tiny grey text at the bottom of the text column
    id_font, id_size, id_leading = "Helvetica", 3.0, 4.0
    c.setFont(id_font, id_size)
    c.setFillGray(0.55)
    id_str = f"ID: {sample_id}"
    id_y = margin
    if stringWidth(id_str, id_font, id_size) <= text_col_w:
        c.drawString(margin, id_y, id_str)
    else:
        # split at the hyphen nearest the midpoint
        mid = len(id_str) // 2
        c.drawString(margin, id_y + id_leading, id_str[:mid])
        c.drawString(margin, id_y,              id_str[mid:])

    # Draw QR code on the right
    qr_bytes = generate_qr_code(label_url, size_px=150)
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
