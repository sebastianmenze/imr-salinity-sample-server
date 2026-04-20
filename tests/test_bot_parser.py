"""Tests for the Seabird BTL file parser."""

import os
from app.utils.bot_parser import parse_bot_file

# Minimal synthetic BTL file matching real Seabird format
SAMPLE_BTL = """\
* Sea-Bird SBE 9 Data File:
* NMEA Latitude = 60 52.00 N
* NMEA Longitude = 005 21.69 E
* NMEA UTC (Time) = Oct 03 2025  03:27:12
** Ship name [platform code]: G.O.Sars [4174]
** Station: 0728
** Cruise: 2025001014
# start_time = Oct 03 2025 03:27:12 [System UTC, header]
    Bottle        Date      Sal00 Sbeox0ML/L      Sal11       PrDM      T068C      T168C
  Position        Time
      1    Oct 03 2025    35.0375     4.9272    35.0292    464.665     8.3820     8.3816 (avg)
              03:35:00                                       0.087     0.0001     0.0001 (sdev)
      2    Oct 03 2025    34.9100     5.1000    34.9050    200.000     7.5000     7.4990 (avg)
              03:40:00                                       0.050     0.0001     0.0001 (sdev)
"""


def test_parse_two_bottles():
    bot = parse_bot_file(SAMPLE_BTL, "test.btl")
    assert len(bot.records) == 2


def test_bottle_numbers():
    bot = parse_bot_file(SAMPLE_BTL)
    assert bot.records[0].bottle_number == "1"
    assert bot.records[1].bottle_number == "2"


def test_psal_values():
    bot = parse_bot_file(SAMPLE_BTL)
    assert bot.records[0].psal_1 == 35.0375
    assert bot.records[0].psal_2 == 35.0292
    assert bot.records[1].psal_1 == 34.9100


def test_depth_from_prdm():
    bot = parse_bot_file(SAMPLE_BTL)
    assert bot.records[0].depth_m == 464.665
    assert bot.records[1].depth_m == 200.0


def test_utc_time_combined_from_avg_and_sdev_rows():
    bot = parse_bot_file(SAMPLE_BTL)
    t = bot.records[0].utc_time
    assert t is not None
    assert t.year == 2025
    assert t.month == 10
    assert t.day == 3
    assert t.hour == 3
    assert t.minute == 35


def test_nmea_latitude():
    bot = parse_bot_file(SAMPLE_BTL)
    assert bot.latitude is not None
    assert abs(bot.latitude - 60.8667) < 0.001


def test_nmea_longitude():
    bot = parse_bot_file(SAMPLE_BTL)
    assert bot.longitude is not None
    assert abs(bot.longitude - 5.3615) < 0.001


def test_metadata_station_cruise_platform():
    bot = parse_bot_file(SAMPLE_BTL)
    assert bot.cast_number == "0728"
    assert bot.cruise_id == "2025001014"
    assert bot.platform_name == "G.O.Sars"


def test_position_propagated_to_records():
    bot = parse_bot_file(SAMPLE_BTL)
    assert bot.records[0].latitude == bot.latitude
    assert bot.records[0].longitude == bot.longitude


def test_empty_file():
    bot = parse_bot_file("", "empty.btl")
    assert len(bot.records) == 0


# ---------------------------------------------------------------------------
# Integration test against the real example files (if present in repo)
# ---------------------------------------------------------------------------

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..")


def _load_example(name: str):
    path = os.path.join(EXAMPLES_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def test_real_sta0728():
    content = _load_example("sta0728.btl")
    if content is None:
        return  # file not present — skip
    bot = parse_bot_file(content, "sta0728.btl")
    assert len(bot.records) >= 1
    assert bot.cruise_id == "2025001014"
    assert bot.cast_number == "0728"
    assert bot.platform_name == "G.O.Sars"
    assert bot.latitude is not None
    assert bot.longitude is not None
    for r in bot.records:
        assert r.depth_m > 0
        assert r.psal_1 is not None


def test_real_sta0729():
    content = _load_example("sta0729.btl")
    if content is None:
        return
    bot = parse_bot_file(content, "sta0729.btl")
    assert len(bot.records) >= 1
    assert bot.cruise_id == "2025001014"
    assert bot.cast_number == "0729"
