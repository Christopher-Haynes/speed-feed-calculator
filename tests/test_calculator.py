"""Tests for calculator.py.

Material data comes from the fake rows in conftest.py.
"""

import math

import pytest

import calculator
from units import INCH, METRIC


def headline(result):
    return {item.label: item.value for item in result.headline}


def details(result):
    return {item.label: item.value for item in result.details}


def messages(result, level):
    return " ".join(m.text for m in result.messages if m.level == level)


def with_defaults(defaults, overrides):
    """Merge overrides into defaults. An override of None removes the field."""
    args = {**defaults, **overrides}
    return {key: value for key, value in args.items() if value is not None}


# --- Milling ---------------------------------------------------------------

MILL = {"diameter": "0.5", "flutes": "3", "woc": "0.25", "doc": "0.5",
        "sfm": "800", "chip_load": "0.002", "max_rpm": "10000"}
RPM_800_HALF_INCH = 800 * 12 / (math.pi * 0.5)


def mill(lookup, units=INCH, **overrides):
    return calculator.calculate_milling(with_defaults(MILL, overrides), units, lookup)


def test_empty_form_shows_placeholder(lookup):
    assert calculator.calculate_milling({}, INCH, lookup) is None


def test_milling_with_own_numbers(lookup):
    result = mill(lookup)
    assert not result.errors
    assert headline(result)["Spindle"] == pytest.approx(RPM_800_HALF_INCH)
    # 50% WOC: no chip thinning, so feed = RPM x 0.002 x 3 flutes
    assert headline(result)["Feed"] == pytest.approx(RPM_800_HALF_INCH * 0.002 * 3)


def test_fraction_input(lookup):
    assert headline(mill(lookup, diameter="1/2"))["Spindle"] == pytest.approx(RPM_800_HALF_INCH)


def test_required_field_missing(lookup):
    assert "Machine max RPM is required." in mill(lookup, max_rpm=None).errors


def test_bad_number(lookup):
    assert any('"abc"' in error for error in mill(lookup, diameter="abc").errors)


def test_speed_needed_without_material(lookup):
    assert any("surface speed" in error for error in mill(lookup, sfm=None).errors)


def test_woc_bigger_than_tool(lookup):
    assert any("can't be more than" in error for error in mill(lookup, woc="0.6").errors)


def test_rpm_capped_and_feed_follows(lookup):
    result = mill(lookup, max_rpm="5000")
    assert headline(result)["Spindle"] == 5000
    assert headline(result)["Feed"] == pytest.approx(5000 * 0.002 * 3)
    assert "capped" in messages(result, "warn")


def test_chip_thinning_raises_chip_load(lookup):
    result = mill(lookup, woc="0.05")  # 10% WOC, factor 1 / 0.6
    d = details(result)
    assert d["Chip thinning factor"] == pytest.approx(1 / 0.6)
    assert d["Chip load (programmed)"] == pytest.approx(0.002 / 0.6)
    assert d["Actual chip thickness"] == pytest.approx(0.002)


def test_chip_thinning_turned_off(lookup):
    result = mill(lookup, woc="0.05", thinning="ignore")
    d = details(result)
    assert d["Chip load (programmed)"] == pytest.approx(0.002)
    assert d["Actual chip thickness"] == pytest.approx(0.002 * 0.6)
    assert "thinner" in messages(result, "info")


def test_circle_inside_a_hole(lookup):
    result = mill(lookup, path="internal", feature_diameter="1.0")
    edge = details(result)["Feed at the cutting edge"]
    assert headline(result)["Feed"] == pytest.approx(edge * (1.0 - 0.5) / 1.0)


def test_circle_around_a_boss(lookup):
    result = mill(lookup, path="external", feature_diameter="1.0")
    edge = details(result)["Feed at the cutting edge"]
    assert headline(result)["Feed"] == pytest.approx(edge * (1.0 + 0.5) / 1.0)


def test_hole_smaller_than_tool(lookup):
    result = mill(lookup, path="internal", feature_diameter="0.4")
    assert any("bigger than the tool" in error for error in result.errors)


def test_metric_gives_same_answer_as_inch(lookup):
    inch = mill(lookup)
    metric = calculator.calculate_milling(
        {"diameter": "12.7", "flutes": "3", "woc": "6.35", "doc": "12.7",
         "sfm": "243.84", "chip_load": "0.0508", "max_rpm": "10000"},
        METRIC, lookup)
    assert headline(metric)["Spindle"] == pytest.approx(headline(inch)["Spindle"])
    assert headline(metric)["Feed"] == pytest.approx(headline(inch)["Feed"])


def test_uses_material_data(lookup):
    result = mill(lookup, material="alu-test", sfm=None, chip_load=None)
    assert not result.errors
    # Manufacturer row (800) beats the handbook row (700).
    assert headline(result)["Spindle"] == pytest.approx(RPM_800_HALF_INCH)
    # The flat end mill row for 0.25-0.5" beats the general row.
    assert details(result)["Chip load (programmed)"] == pytest.approx(0.005)
    assert result.range is not None
    whats = [s.what for s in result.sources]
    assert whats[:2] == ["Surface speed", "Surface speed (cross-check)"]


def test_override_is_noted(lookup):
    result = mill(lookup, material="alu-test", chip_load=None)
    assert "Using your surface speed" in messages(result, "info")


def test_power_check(lookup):
    result = mill(lookup, material="alu-test", spindle_hp="0.1")
    assert "Cutting power (est.)" in details(result)
    assert "spindle" in messages(result, "warn")


def test_rubbing_warning(lookup):
    # Thinning ignored at 10% WOC: chip is 0.005 x 0.6 = 0.003, under the 0.004 low end.
    result = mill(lookup, material="alu-test", sfm=None, chip_load=None,
                  woc="0.05", thinning="ignore")
    assert "rub" in messages(result, "warn")


def test_small_tool_in_hard_material(lookup):
    result = mill(lookup, material="hard-test", diameter="0.1", woc="0.05", doc="0.1")
    assert "Small tool" in messages(result, "warn")


def test_long_stickout(lookup):
    assert "Stickout" in messages(mill(lookup, stickout="2"), "warn")  # 4x diameter


def test_ball_mill_effective_diameter(lookup):
    assert "ball only cuts" in messages(mill(lookup, tool_type="ball", doc="0.05"), "info")


def test_copy_text(lookup):
    lines = mill(lookup).copy_text.splitlines()
    assert lines[0] == "(MILLING - MATERIAL NOT SET)"
    assert "(S6112 F36.7 IPM)" in lines
    assert all(line.startswith("(") and line.endswith(")") for line in lines)


def test_gcode_comment_has_no_nested_parentheses():
    assert calculator.gcode_comment("4140 Annealed (175–225 HB)") == "(4140 ANNEALED 175-225 HB)"


# --- Drilling --------------------------------------------------------------

DRILL = {"diameter": "0.25", "sfm": "300", "ipr": "0.004", "max_rpm": "10000"}


def drill(lookup, **overrides):
    return calculator.calculate_drilling(with_defaults(DRILL, overrides), INCH, lookup)


def test_drilling(lookup):
    result = drill(lookup)
    rpm = 300 * 12 / (math.pi * 0.25)
    assert headline(result)["Spindle"] == pytest.approx(rpm)
    assert headline(result)["Feed"] == pytest.approx(rpm * 0.004)
    assert details(result)["Material removal rate"] == pytest.approx(
        math.pi / 4 * 0.25 ** 2 * rpm * 0.004)


def test_drilling_uses_material_data(lookup):
    result = drill(lookup, material="alu-test", sfm=None, ipr=None)
    assert not result.errors
    assert details(result)["Feed per rev"] == pytest.approx(0.004)


def test_range_only_data_uses_the_middle(lookup):
    # The drilling speed row gives 250-350 SFM and no recommended value.
    result = drill(lookup, material="alu-test", sfm=None, ipr=None)
    assert headline(result)["Spindle"] == pytest.approx(300 * 12 / (math.pi * 0.25))
    assert "uses the middle" in messages(result, "info")
    assert result.range.columns == ["Low", "Middle", "High"]
    surface_speed = dict((label, values) for label, _, values in result.range.rows)["Surface speed"]
    assert surface_speed == pytest.approx([250, 300, 350])


# --- Turning ---------------------------------------------------------------

TURN = {"start_diameter": "2.0", "finish_diameter": "1.5", "doc": "0.05",
        "sfm": "500", "ipr": "0.008", "max_rpm": "4000"}


def turn(lookup, units=INCH, **overrides):
    return calculator.calculate_turning(with_defaults(TURN, overrides), units, lookup)


def test_od_turning(lookup):
    result = turn(lookup)
    h, d = headline(result), details(result)
    assert h["G96 S"] == 500
    assert h["Feed"] == 0.008
    assert h["G50 S"] == 4000
    assert d["RPM at start diameter"] == pytest.approx(500 * 12 / (math.pi * 2.0))
    assert d["RPM at finish diameter"] == pytest.approx(500 * 12 / (math.pi * 1.5))
    assert d["Material removal rate"] == pytest.approx(12 * 500 * 0.008 * 0.05)


def test_chuck_limit_sets_g50(lookup):
    result = turn(lookup, chuck_max_rpm="1000")
    assert headline(result)["G50 S"] == 1000
    assert details(result)["RPM at finish diameter"] == 1000


def test_facing_to_center_hits_the_clamp(lookup):
    result = turn(lookup, cut_type="face", finish_diameter="0")
    d = details(result)
    assert d["RPM at finish diameter"] == 4000
    assert d["RPM limit reached below"] == pytest.approx(500 * 12 / (math.pi * 4000))
    assert "Below" in messages(result, "info")


def test_whole_cut_at_the_limit(lookup):
    assert "whole cut" in messages(turn(lookup, max_rpm="500"), "warn")


def test_turning_uses_material_data(lookup):
    result = turn(lookup, material="alu-test", sfm=None, ipr=None)
    assert not result.errors
    assert headline(result)["G96 S"] == 500
    assert headline(result)["Feed"] == 0.008
    assert result.range is not None


def test_grooving_ignores_turning_data(lookup):
    result = turn(lookup, material="alu-test", cut_type="groove", sfm=None)
    assert any("Grooving and parting" in error for error in result.errors)


def test_threading(lookup):
    result = turn(lookup, cut_type="thread", pitch="16", sfm="300",
                  finish_diameter=None, ipr=None)
    rpm = 300 * 12 / (math.pi * 2.0)
    h = headline(result)
    assert h["G97 S"] == pytest.approx(rpm)
    assert h["Pitch"] == pytest.approx(1 / 16)
    assert h["Feed"] == pytest.approx(rpm / 16)
    assert "G97" in messages(result, "info")


def test_threading_needs_its_own_speed(lookup):
    result = turn(lookup, material="alu-test", cut_type="thread", pitch="16", sfm=None)
    assert any("threading surface speed" in error for error in result.errors)


def test_metric_thread_pitch(lookup):
    result = calculator.calculate_turning(
        {"cut_type": "thread", "start_diameter": "20", "pitch": "1.5",
         "sfm": "100", "max_rpm": "4000"},
        METRIC, lookup)
    assert headline(result)["Pitch"] == pytest.approx(1.5 / 25.4)


# --- Unit toggle -----------------------------------------------------------

def test_convert_args_to_metric():
    args = {"diameter": "1/2", "sfm": "800", "flutes": "3", "tool_type": "flat",
            "units": "inch", "convert_to": "metric"}
    assert calculator.convert_args("milling", args, INCH, METRIC) == {
        "diameter": "12.7", "sfm": "243.84", "flutes": "3", "tool_type": "flat",
        "units": "metric",
    }


def test_convert_args_leaves_bad_input_alone():
    converted = calculator.convert_args("milling", {"diameter": "abc"}, INCH, METRIC)
    assert converted["diameter"] == "abc"
