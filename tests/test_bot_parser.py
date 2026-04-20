from app.utils.bot_parser import parse_bot_file

SAMPLE_BOT = """
# name 0 = depSM: Depth [salt water, m]
# name 1 = t090C: Temperature [ITS-90, deg C]
# name 2 = sal00: Salinity, Practical [PSU]
# name 3 = sal11: Salinity, Practical, 2 [PSU]
# start_time = Mar 17 2025 15:44:00
# cast 3
      5.000  3.4521  34.3454  34.3448
     10.000  3.4499  34.3521  34.3519
     50.000  3.3211  34.5001  34.4998
"""


def test_parse_records():
    bot = parse_bot_file(SAMPLE_BOT, "test.bot")
    assert len(bot.records) == 3


def test_parse_depths():
    bot = parse_bot_file(SAMPLE_BOT)
    depths = [r.depth_m for r in bot.records]
    assert depths == [5.0, 10.0, 50.0]


def test_parse_psal():
    bot = parse_bot_file(SAMPLE_BOT)
    assert bot.records[0].psal_1 == 34.3454
    assert bot.records[0].psal_2 == 34.3448


def test_parse_start_time():
    bot = parse_bot_file(SAMPLE_BOT)
    assert bot.start_time is not None
    assert bot.start_time.year == 2025
    assert bot.start_time.month == 3


def test_cast_number():
    bot = parse_bot_file(SAMPLE_BOT)
    assert bot.cast_number == "3"


def test_empty_file():
    bot = parse_bot_file("", "empty.bot")
    assert len(bot.records) == 0
