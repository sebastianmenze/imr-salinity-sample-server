"""
Parser for Seabird .bot (bottle closure) files.

BOT files are produced by SBE Data Processing and contain one row per Niskin
bottle closure with all derived parameters at that depth.
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
    platform_id: Optional[str] = None
    cast_number: Optional[str] = None


@dataclass
class BotFile:
    records: list[BotRecord] = field(default_factory=list)
    start_time: Optional[datetime] = None
    cast_number: Optional[str] = None
    filename: Optional[str] = None
    raw_header: list[str] = field(default_factory=list)
    column_names: list[str] = field(default_factory=list)


def parse_bot_file(content: str, filename: str = "") -> BotFile:
    """
    Parse a Seabird BOT file from string content.

    Args:
        content: Full text content of the .bot file
        filename: Original filename (used to extract metadata if possible)

    Returns:
        BotFile with parsed records
    """
    bot = BotFile(filename=filename)
    lines = content.splitlines()

    header_lines = []
    column_names = []
    data_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("#"):
            header_lines.append(stripped)
            # Extract column names: "# name N = varname: Description"
            m = re.match(r"#\s+name\s+\d+\s+=\s+(\w+)", stripped)
            if m:
                column_names.append(m.group(1))
            # Extract start time: "# start_time = MMM DD YYYY HH:MM:SS"
            m = re.match(r"#\s+start_time\s+=\s+(.+)", stripped)
            if m:
                try:
                    bot.start_time = datetime.strptime(
                        m.group(1).strip(), "%b %d %Y %H:%M:%S"
                    )
                except ValueError:
                    pass
            # Extract cast number
            m = re.match(r"#\s+cast\s+(\d+)", stripped, re.IGNORECASE)
            if m:
                bot.cast_number = m.group(1)
        else:
            data_lines.append(stripped)

    bot.raw_header = header_lines
    bot.column_names = column_names

    col_map = {name.lower(): i for i, name in enumerate(column_names)}

    def find_col(*candidates) -> Optional[int]:
        for c in candidates:
            for key, idx in col_map.items():
                if c.lower() in key:
                    return idx
        return None

    depth_idx = find_col("depsm", "depth", "dep")
    sal1_idx = find_col("sal00", "sal_1", "psal_1", "sal")
    sal2_idx = find_col("sal11", "sal_2", "psal_2")
    temp_idx = find_col("t090c", "temp", "potemp")
    bottle_idx = find_col("bottle", "btl", "nbf")

    for i, line in enumerate(data_lines):
        parts = line.split()
        if not parts:
            continue
        try:
            record = BotRecord(
                depth_m=float(parts[depth_idx]) if depth_idx is not None else 0.0,
                bottle_number=parts[bottle_idx] if bottle_idx is not None else str(i + 1),
                psal_1=float(parts[sal1_idx]) if sal1_idx is not None else None,
                psal_2=float(parts[sal2_idx]) if sal2_idx is not None else None,
                temperature=float(parts[temp_idx]) if temp_idx is not None else None,
                utc_time=bot.start_time,
                cast_number=bot.cast_number,
            )
            bot.records.append(record)
        except (IndexError, ValueError) as e:
            logger.warning(f"Skipping BOT line {i}: {e} — '{line}'")

    logger.info(f"Parsed {len(bot.records)} bottle records from {filename}")
    return bot
