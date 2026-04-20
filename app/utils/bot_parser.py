"""
Parser for Seabird BTL (bottle summary) files produced by SBE Data Processing.

File format:
  - Lines starting with '*' : metadata (NMEA position, cruise, station, platform)
  - Lines starting with '#' : sensor configuration XML — ignored for data extraction
  - Plain text line containing 'Bottle' and 'Date': column header
  - Plain text line containing 'Position' and 'Time': second header row — ignored
  - Data rows in pairs:
      avg row:  bottle_num  Month DD YYYY  sal00  ...  prdm  ...  (avg)
      sdev row: HH:MM:SS    sdev_values...                        (sdev)
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class BotRecord:
    depth_m: float
    bottle_number: Optional[str] = None
    psal_1: Optional[float] = None
    psal_2: Optional[float] = None
    temperature: Optional[float] = None
    utc_time: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    cast_number: Optional[str] = None


@dataclass
class BotFile:
    records: list[BotRecord] = field(default_factory=list)
    start_time: Optional[datetime] = None
    cast_number: Optional[str] = None
    cruise_id: Optional[str] = None
    platform_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    filename: Optional[str] = None


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def _parse_nmea_lat(s: str) -> Optional[float]:
    """'60 52.00 N' → 60.8667"""
    m = re.match(r"(\d+)\s+([\d.]+)\s+([NS])", s.strip())
    if not m:
        return None
    val = float(m.group(1)) + float(m.group(2)) / 60.0
    return -val if m.group(3) == "S" else val


def _parse_nmea_lon(s: str) -> Optional[float]:
    """'005 21.69 E' → 5.3615"""
    m = re.match(r"(\d+)\s+([\d.]+)\s+([EW])", s.strip())
    if not m:
        return None
    val = float(m.group(1)) + float(m.group(2)) / 60.0
    return -val if m.group(3) == "W" else val


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_bot_file(content: str, filename: str = "") -> BotFile:
    """
    Parse a Seabird BTL bottle summary file.

    Args:
        content : Full text of the .btl / .bot file
        filename: Original filename (informational only)

    Returns:
        BotFile with header metadata and one BotRecord per bottle closure
    """
    bot = BotFile(filename=filename)
    lines = content.splitlines()

    col_names: list[str] = []
    col_header_found = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # ------------------------------------------------------------------
        # * metadata lines
        # ------------------------------------------------------------------
        if stripped.startswith("*"):
            # NMEA position
            m = re.match(r"\*\s+NMEA Latitude\s*=\s*(.+)", stripped)
            if m:
                bot.latitude = _parse_nmea_lat(m.group(1))

            m = re.match(r"\*\s+NMEA Longitude\s*=\s*(.+)", stripped)
            if m:
                bot.longitude = _parse_nmea_lon(m.group(1))

            # NMEA cast start time: "Oct 03 2025  03:27:10"
            m = re.match(r"\*\s+NMEA UTC \(Time\)\s*=\s*(.+)", stripped)
            if m:
                time_str = re.sub(r"\s+", " ", m.group(1).strip())
                try:
                    bot.start_time = datetime.strptime(time_str, "%b %d %Y %H:%M:%S")
                except ValueError:
                    pass

            # ** Station: 0728
            m = re.match(r"\*\*\s+Station:\s*(\S+)", stripped)
            if m:
                bot.cast_number = m.group(1).strip()

            # ** Cruise: 2025001014
            m = re.match(r"\*\*\s+Cruise:\s*(\S+)", stripped)
            if m:
                bot.cruise_id = m.group(1).strip()

            # ** Ship name [platform code]: G.O.Sars [4174]
            m = re.match(r"\*\*\s+Ship name.*:\s*(.+?)\s*\[", stripped)
            if m:
                bot.platform_name = m.group(1).strip()

            continue

        # ------------------------------------------------------------------
        # # config/sensor XML lines — skip entirely
        # ------------------------------------------------------------------
        if stripped.startswith("#"):
            continue

        # ------------------------------------------------------------------
        # Column header line: contains "Bottle" and "Date"
        # ------------------------------------------------------------------
        if not col_header_found and "Bottle" in stripped and "Date" in stripped:
            col_names = stripped.split()
            col_header_found = True
            continue

        # Second header row: "Position  Time  ..."
        if col_header_found and "Position" in stripped and "Time" in stripped:
            continue

        # ------------------------------------------------------------------
        # Data rows — (avg) and (sdev) pairs
        # ------------------------------------------------------------------
        if col_header_found and stripped.endswith("(avg)"):
            avg_parts = stripped.split()

            # Grab the matching (sdev) line for the bottle timestamp
            sdev_parts: list[str] = []
            for j in range(i + 1, min(i + 4, len(lines))):
                nxt = lines[j].strip()
                if nxt.endswith("(sdev)"):
                    sdev_parts = nxt.split()
                    break

            try:
                bottle_num = avg_parts[0]

                # avg_parts layout: [btl, Mon, DD, YYYY, col2_val, col3_val, ...]
                # col_names layout: [Bottle, Date, col2, col3, ...]
                # Data values start at avg_parts[4] and col_names[2]
                date_str = f"{avg_parts[1]} {avg_parts[2]} {avg_parts[3]}"
                time_str = sdev_parts[0] if sdev_parts else "00:00:00"
                try:
                    utc_time = datetime.strptime(f"{date_str} {time_str}", "%b %d %Y %H:%M:%S")
                except ValueError:
                    utc_time = bot.start_time

                def avg_idx(col_name_substr: str) -> Optional[int]:
                    """Map a column name substring to its index in avg_parts."""
                    for k, name in enumerate(col_names):
                        if col_name_substr.lower() in name.lower():
                            # col_names[0]=Bottle → avg_parts[0]
                            # col_names[1]=Date   → avg_parts[1..3] (3 tokens)
                            # col_names[k>=2]     → avg_parts[k+2]
                            return k + 2 if k >= 2 else k
                    return None

                def safe_float(parts: list, idx: Optional[int]) -> Optional[float]:
                    if idx is None or idx >= len(parts):
                        return None
                    try:
                        return float(parts[idx])
                    except ValueError:
                        return None

                depth = safe_float(avg_parts, avg_idx("PrDM")) or 0.0
                psal_1 = safe_float(avg_parts, avg_idx("Sal00"))
                psal_2 = safe_float(avg_parts, avg_idx("Sal11"))
                temperature = safe_float(avg_parts, avg_idx("T068C")) or safe_float(avg_parts, avg_idx("T090"))

                record = BotRecord(
                    depth_m=depth,
                    bottle_number=bottle_num,
                    psal_1=psal_1,
                    psal_2=psal_2,
                    temperature=temperature,
                    utc_time=utc_time,
                    latitude=bot.latitude,
                    longitude=bot.longitude,
                    cast_number=bot.cast_number,
                )
                bot.records.append(record)

            except (IndexError, ValueError) as e:
                logger.warning(f"Skipping BTL bottle record at line {i}: {e} — '{stripped[:80]}'")

    logger.info(f"Parsed {len(bot.records)} bottle records from {filename or 'unknown'}")
    return bot
