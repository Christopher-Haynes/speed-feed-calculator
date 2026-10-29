"""Unit conversion, display formatting, and reading typed numbers.

All calculations run in inch units. Metric input is converted to inch on
the way in, and results are converted back for display, so the formulas
and the data only ever deal with one unit system.
"""

import math
import re
from collections import namedtuple

INCH = "inch"
METRIC = "metric"
UNIT_SYSTEMS = (INCH, METRIC)

MM_PER_INCH = 25.4
M_PER_FOOT = 0.3048
KW_PER_HP = 0.745699872
CM3_PER_IN3 = 16.387064

# factor: metric value = inch value x factor
Kind = namedtuple("Kind", "factor inch_label metric_label inch_decimals metric_decimals")

KINDS = {
    "rpm": Kind(1, "RPM", "RPM", 0, 0),
    "length": Kind(MM_PER_INCH, "in", "mm", 4, 3),
    "speed": Kind(M_PER_FOOT, "SFM", "m/min", 0, 0),
    "feed_tooth": Kind(MM_PER_INCH, "in/tooth", "mm/tooth", 4, 3),
    "feed_rev": Kind(MM_PER_INCH, "in/rev", "mm/rev", 4, 3),
    "feed_rate": Kind(MM_PER_INCH, "IPM", "mm/min", 1, 0),
    "mrr": Kind(CM3_PER_IN3, "in³/min", "cm³/min", 3, 2),
    "power": Kind(KW_PER_HP, "HP", "kW", 2, 2),
    "unit_power": Kind(KW_PER_HP / CM3_PER_IN3, "HP per in³/min", "kW per cm³/min", 2, 4),
    "ratio": Kind(1, "×", "×", 2, 2),
    # Thread pitch is the odd one out: inch shops use threads per inch,
    # which is 1 / lead, so it can't be converted with a plain factor.
    "thread": Kind(None, "TPI", "mm pitch", 1, 3),
}

_MIXED = re.compile(r"^(\d+)[ -]+(\d+)/(\d+)$")
_FRACTION = re.compile(r"^(\d+)/(\d+)$")


def to_inch(value, kind, unit_system):
    """Convert a value typed in unit_system to inch units."""
    if kind == "thread":
        return 1 / value if unit_system == INCH else value / MM_PER_INCH
    if unit_system == INCH:
        return value
    return value / KINDS[kind].factor


def from_inch(value, kind, unit_system):
    """Convert an inch-unit value to unit_system."""
    if kind == "thread":
        return 1 / value if unit_system == INCH else value * MM_PER_INCH
    if unit_system == INCH:
        return value
    return value * KINDS[kind].factor


def label(kind, unit_system):
    """Return the unit label, e.g. label("feed_rate", METRIC) -> "mm/min"."""
    k = KINDS[kind]
    return k.inch_label if unit_system == INCH else k.metric_label


def decimals(kind, unit_system):
    k = KINDS[kind]
    return k.inch_decimals if unit_system == INCH else k.metric_decimals


def fmt(value, kind, unit_system, with_label=False):
    """Format an inch-unit value for display.

    fmt(0.5, "length", METRIC) -> "12.700"
    fmt(0.5, "length", METRIC, with_label=True) -> "12.700 mm"
    """
    if value is None:
        return "—"
    text = f"{from_inch(value, kind, unit_system):.{decimals(kind, unit_system)}f}"
    return f"{text} {label(kind, unit_system)}" if with_label else text


def input_text(value, kind, unit_system):
    """Format an inch-unit value to put back in a form field.

    Keeps two more decimals than the display so flipping inch/metric back
    and forth doesn't drift, and drops trailing zeros. Blank for None.
    """
    if value is None:
        return ""
    text = f"{from_inch(value, kind, unit_system):.{decimals(kind, unit_system) + 2}f}"
    return _trim_zeros(text)


def convert_text(text, kind, from_units, to_units):
    """Convert a typed value between unit systems, for the inch/metric toggle."""
    return input_text(to_inch(parse_number(text), kind, from_units), kind, to_units)


def parse_number(text):
    """Turn what a machinist types into a float.

    Accepts decimals ("0.5", ".5", "12,7"), fractions ("3/8") and mixed
    fractions ("1 1/4" or "1-1/4"). A trailing inch mark is ignored.
    Raises ValueError for anything else.
    """
    text = text.strip().rstrip('"').strip()
    if "," in text and "." not in text:
        text = text.replace(",", ".")  # decimal comma

    match = _MIXED.match(text)
    if match:
        whole, num, den = (int(part) for part in match.groups())
        return whole + _divide(num, den)
    match = _FRACTION.match(text)
    if match:
        num, den = (int(part) for part in match.groups())
        return _divide(num, den)

    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"not a number: {text!r}")
    return value


def _divide(num, den):
    if den == 0:
        raise ValueError("fraction with zero on the bottom")
    return num / den


def _trim_zeros(text):
    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".")
