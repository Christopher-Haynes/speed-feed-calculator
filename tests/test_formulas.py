"""Tests for formulas.py.

Most tests are arithmetic checks worked out by hand. Inputs like 800 SFM
are just numbers to exercise the math, not cutting recommendations.
"""

import pytest

from formulas import (
    cap_rpm,
    chip_thinning_factor,
    milling_feed_rate,
    milling_mrr,
    milling_rpm_inch,
    milling_rpm_metric,
    sfm_from_rpm,
    turning_feed_rate,
    turning_rpm_inch,
    turning_rpm_metric,
    vc_from_rpm,
)


# --- Spindle speed ---------------------------------------------------------

def test_milling_rpm_inch():
    # 800 * 12 / (pi * 0.5) = 6111.55
    assert milling_rpm_inch(800, 0.5) == pytest.approx(6111.55, abs=0.01)


def test_milling_rpm_metric():
    # 100 * 1000 / (pi * 10) = 3183.10
    assert milling_rpm_metric(100, 10) == pytest.approx(3183.10, abs=0.01)


def test_inch_and_metric_rpm_agree():
    # Same cut in both systems: 800 SFM = 243.84 m/min, 0.5 in = 12.7 mm
    assert milling_rpm_metric(243.84, 12.7) == pytest.approx(milling_rpm_inch(800, 0.5))


def test_doubling_diameter_halves_rpm():
    assert milling_rpm_inch(800, 1.0) == pytest.approx(milling_rpm_inch(800, 0.5) / 2)


def test_turning_rpm_inch():
    # 500 * 12 / (pi * 2.0) = 954.93
    assert turning_rpm_inch(500, 2.0) == pytest.approx(954.93, abs=0.01)


def test_turning_rpm_metric():
    # 200 * 1000 / (pi * 40) = 1591.55
    assert turning_rpm_metric(200, 40) == pytest.approx(1591.55, abs=0.01)


def test_sfm_from_rpm_reverses_rpm():
    rpm = milling_rpm_inch(800, 0.5)
    assert sfm_from_rpm(rpm, 0.5) == pytest.approx(800)


def test_vc_from_rpm_reverses_rpm():
    rpm = milling_rpm_metric(100, 10)
    assert vc_from_rpm(rpm, 10) == pytest.approx(100)


def test_cap_rpm_below_limit_is_unchanged():
    assert cap_rpm(5000, 10000) == 5000


def test_cap_rpm_above_machine_max():
    assert cap_rpm(12000, 10000) == 10000


def test_cap_rpm_uses_lower_of_machine_and_chuck():
    assert cap_rpm(5000, 6000, chuck_max_rpm=3500) == 3500


# --- Feed rate -------------------------------------------------------------

def test_milling_feed_rate():
    # 6000 RPM * 0.002 in/tooth * 3 flutes = 36 IPM
    assert milling_feed_rate(6000, 0.002, 3) == pytest.approx(36)


def test_turning_feed_rate():
    # 1000 RPM * 0.008 IPR = 8 IPM
    assert turning_feed_rate(1000, 0.008) == pytest.approx(8)


def test_no_chip_thinning_at_half_engagement_or_more():
    assert chip_thinning_factor(0.25, 0.5) == 1.0  # 50%
    assert chip_thinning_factor(0.4, 0.5) == 1.0   # 80%
    assert chip_thinning_factor(0.5, 0.5) == 1.0   # full slot


def test_chip_thinning_at_25_percent():
    # 1 / sqrt(1 - 0.5^2) = 1 / sqrt(0.75) = 1.1547
    assert chip_thinning_factor(0.125, 0.5) == pytest.approx(1.1547, abs=0.0001)


def test_chip_thinning_at_10_percent():
    # 1 / sqrt(1 - 0.8^2) = 1 / sqrt(0.36) = 1 / 0.6 = 1.667
    assert chip_thinning_factor(0.05, 0.5) == pytest.approx(1 / 0.6)


# --- Material removal ------------------------------------------------------

def test_milling_mrr():
    # 0.25 in WOC * 0.5 in DOC * 36 IPM = 4.5 in^3/min
    assert milling_mrr(0.25, 0.5, 36) == pytest.approx(4.5)


# --- Bad input -------------------------------------------------------------

def test_zero_diameter_raises():
    with pytest.raises(ValueError):
        milling_rpm_inch(800, 0)


def test_negative_sfm_raises():
    with pytest.raises(ValueError):
        turning_rpm_inch(-500, 2.0)


def test_zero_flutes_raises():
    with pytest.raises(ValueError):
        milling_feed_rate(6000, 0.002, 0)


def test_radial_doc_larger_than_tool_raises():
    with pytest.raises(ValueError):
        chip_thinning_factor(0.6, 0.5)


# --- Machinery's Handbook worked examples ----------------------------------
# Fill these in from your copy, then delete the @pytest.mark.skip line.

@pytest.mark.skip(reason="TODO: add a worked example from Machinery's Handbook")
def test_milling_rpm_matches_handbook():
    # Source: Machinery's Handbook, ___ edition, page ___
    sfm = None
    tool_diameter_in = None
    handbook_rpm = None
    assert milling_rpm_inch(sfm, tool_diameter_in) == pytest.approx(handbook_rpm, abs=1)


@pytest.mark.skip(reason="TODO: add a worked example from Machinery's Handbook")
def test_turning_rpm_matches_handbook():
    # Source: Machinery's Handbook, ___ edition, page ___
    sfm = None
    part_diameter_in = None
    handbook_rpm = None
    assert turning_rpm_inch(sfm, part_diameter_in) == pytest.approx(handbook_rpm, abs=1)
