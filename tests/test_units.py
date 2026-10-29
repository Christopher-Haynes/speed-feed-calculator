"""Tests for units.py."""

import pytest

import units
from units import INCH, METRIC


@pytest.mark.parametrize("text, expected", [
    ("0.5", 0.5),
    (".5", 0.5),
    ("1/2", 0.5),
    ("3/8", 0.375),
    ("1 1/4", 1.25),
    ("1-1/4", 1.25),
    ('0.5"', 0.5),
    ("12,7", 12.7),
    ("  2  ", 2.0),
])
def test_parse_number(text, expected):
    assert units.parse_number(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "abc", "1/0", "nan", "inf", "1//2"])
def test_parse_number_rejects_junk(text):
    with pytest.raises(ValueError):
        units.parse_number(text)


def test_metric_to_inch_and_back():
    assert units.to_inch(12.7, "length", METRIC) == pytest.approx(0.5)
    assert units.from_inch(0.5, "length", METRIC) == pytest.approx(12.7)
    assert units.to_inch(243.84, "speed", METRIC) == pytest.approx(800)


def test_inch_values_pass_through():
    assert units.to_inch(0.5, "length", INCH) == 0.5
    assert units.from_inch(800, "speed", INCH) == 800


def test_thread_pitch():
    assert units.to_inch(16, "thread", INCH) == pytest.approx(0.0625)  # 16 TPI
    assert units.to_inch(1.5, "thread", METRIC) == pytest.approx(1.5 / 25.4)
    assert units.from_inch(0.0625, "thread", METRIC) == pytest.approx(1.5875)


def test_fmt():
    assert units.fmt(6111.55, "rpm", INCH) == "6112"
    assert units.fmt(0.5, "length", METRIC, with_label=True) == "12.700 mm"
    assert units.fmt(None, "length", INCH) == "—"


def test_convert_text_between_units():
    assert units.convert_text("1/2", "length", INCH, METRIC) == "12.7"
    assert units.convert_text("800", "speed", INCH, METRIC) == "243.84"
    assert units.convert_text("243.84", "speed", METRIC, INCH) == "800"
    assert units.convert_text("16", "thread", INCH, METRIC) == "1.5875"
