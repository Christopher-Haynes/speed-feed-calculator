"""Core feeds and speeds formulas."""

import math


def _require_positive(name, value):
    """Raise ValueError if value is not greater than 0."""
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")


# --- Spindle speed ---------------------------------------------------------

def milling_rpm_inch(sfm, tool_diameter_in):
    """Return spindle RPM for a milling cutter (inch units).

    sfm: surface speed in surface feet per minute
    tool_diameter_in: cutter diameter in inches
    """
    _require_positive("sfm", sfm)
    _require_positive("tool_diameter_in", tool_diameter_in)

    # Machinery's Handbook form: N = 12V / (pi * D).
    # 12 / pi = 3.8197
    return (sfm * 12) / (math.pi * tool_diameter_in)


def milling_rpm_metric(vc_m_per_min, tool_diameter_mm):
    """Return spindle RPM for a milling cutter (metric units).

    vc_m_per_min: cutting speed in meters per minute
    tool_diameter_mm: cutter diameter in millimeters
    """
    _require_positive("vc_m_per_min", vc_m_per_min)
    _require_positive("tool_diameter_mm", tool_diameter_mm)

    # 1000 converts meters to millimeters.
    return (vc_m_per_min * 1000) / (math.pi * tool_diameter_mm)


def turning_rpm_inch(sfm, part_diameter_in):
    """Return spindle RPM for turning (inch units).

    On a lathe the part spins, so this uses the PART diameter, not the tool.

    sfm: surface speed in surface feet per minute
    part_diameter_in: workpiece diameter in inches
    """
    _require_positive("sfm", sfm)
    _require_positive("part_diameter_in", part_diameter_in)
    return (sfm * 12) / (math.pi * part_diameter_in)


def turning_rpm_metric(vc_m_per_min, part_diameter_mm):
    """Return spindle RPM for turning (metric units).

    vc_m_per_min: cutting speed in meters per minute
    part_diameter_mm: workpiece diameter in millimeters
    """
    _require_positive("vc_m_per_min", vc_m_per_min)
    _require_positive("part_diameter_mm", part_diameter_mm)
    return (vc_m_per_min * 1000) / (math.pi * part_diameter_mm)


def sfm_from_rpm(rpm, diameter_in):
    """Return surface speed in SFM for a given RPM and diameter (inches).

    Use after capping RPM to show the SFM the machine will actually run.
    """
    _require_positive("rpm", rpm)
    _require_positive("diameter_in", diameter_in)
    return (rpm * math.pi * diameter_in) / 12


def vc_from_rpm(rpm, diameter_mm):
    """Return cutting speed in m/min for a given RPM and diameter (mm)."""
    _require_positive("rpm", rpm)
    _require_positive("diameter_mm", diameter_mm)
    return (rpm * math.pi * diameter_mm) / 1000


def cap_rpm(rpm, machine_max_rpm, chuck_max_rpm=None):
    """Return rpm lowered to the machine max, and the chuck max if given.

    Calculate feed from the capped RPM, not the original.
    """
    _require_positive("rpm", rpm)
    _require_positive("machine_max_rpm", machine_max_rpm)

    capped = min(rpm, machine_max_rpm)
    if chuck_max_rpm is not None:
        _require_positive("chuck_max_rpm", chuck_max_rpm)
        capped = min(capped, chuck_max_rpm)
    return capped


# --- Feed rate -------------------------------------------------------------

def milling_feed_rate(rpm, chip_load, flutes):
    """Return table feed for milling.

    Inch: chip_load in inches per tooth gives feed in IPM.
    Metric: chip_load in mm per tooth gives feed in mm/min.
    """
    _require_positive("rpm", rpm)
    _require_positive("chip_load", chip_load)
    _require_positive("flutes", flutes)
    return rpm * chip_load * flutes


def turning_feed_rate(rpm, feed_per_rev):
    """Return feed per minute for turning.

    Inch: feed_per_rev in IPR gives feed in IPM.
    Metric: feed_per_rev in mm/rev gives feed in mm/min.
    """
    _require_positive("rpm", rpm)
    _require_positive("feed_per_rev", feed_per_rev)
    return rpm * feed_per_rev


def chip_thinning_factor(radial_doc, tool_diameter):
    """Return the chip load multiplier for radial chip thinning.

    Under 50% radial engagement the chip comes out thinner than the
    programmed chip load. Multiply chip load by this factor to get the
    intended chip thickness back. Returns 1.0 at 50% engagement or more.

    radial_doc (WOC) and tool_diameter must be in the same unit.
    """
    _require_positive("radial_doc", radial_doc)
    _require_positive("tool_diameter", tool_diameter)
    if radial_doc > tool_diameter:
        raise ValueError("radial_doc cannot be larger than tool_diameter")

    if radial_doc >= tool_diameter / 2:
        return 1.0

    # factor = 1 / sqrt(1 - (1 - 2 * WOC / D)^2)
    return 1 / math.sqrt(1 - (1 - 2 * radial_doc / tool_diameter) ** 2)


# --- Material removal ------------------------------------------------------

def milling_mrr(radial_doc, axial_doc, feed_rate):
    """Return material removal rate for milling: WOC x DOC x feed.

    Inch: inches and IPM give cubic inches per minute.
    Metric: mm and mm/min give mm^3/min (divide by 1000 for cm^3/min).
    """
    _require_positive("radial_doc", radial_doc)
    _require_positive("axial_doc", axial_doc)
    _require_positive("feed_rate", feed_rate)
    return radial_doc * axial_doc * feed_rate
