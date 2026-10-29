"""Turns form input into results for the Milling, Drilling and Turning tabs.

Each calculate_* function:
1. reads and checks the form (metric input is converted to inch),
2. looks up material data,
3. runs the formulas in formulas.py,
4. returns a Result for templates/_results.html to display,
   or None while the form is still empty.

Everything in here is in inch units. units.fmt() converts for display.
"""

from collections import namedtuple

import formulas
import units

# Rules of thumb that trigger warnings. These aren't cutting data; adjust
# them to match your shop.
LONG_STICKOUT_RATIO = 3          # stickout more than 3x the tool diameter
SMALL_TOOL_DIAMETER_IN = 0.125   # tools under 1/8"
HARD_ISO_GROUPS = ("H", "S")

TOOL_MATERIALS = [("carbide", "Carbide"), ("HSS", "HSS"), ("cobalt", "Cobalt")]
MILL_TOOL_TYPES = [
    ("flat", "Flat end mill"),
    ("ball", "Ball end mill"),
    ("bull nose", "Bull nose end mill"),
    ("chamfer", "Chamfer mill"),
    ("face mill", "Face mill"),
]
MILL_COATINGS = [
    ("uncoated", "Uncoated"), ("TiN", "TiN"), ("TiAlN", "TiAlN"),
    ("AlTiN", "AlTiN"), ("ZrN", "ZrN"), ("DLC", "DLC"),
]
MILL_PATHS = [
    ("straight", "Straight line"),
    ("internal", "Circle inside a hole"),
    ("external", "Circle around a boss"),
]
CHIP_THINNING = [("apply", "Adjust feed for it"), ("ignore", "Don't adjust")]
TURNING_CUTS = [
    ("od", "OD turning"),
    ("id", "Boring (ID)"),
    ("face", "Facing"),
    ("groove", "Grooving"),
    ("part", "Parting"),
    ("thread", "Threading"),
]
INSERT_SHAPES = [(shape, shape) for shape in
                 ("CNMG", "DNMG", "VNMG", "WNMG", "TNMG", "CCMT", "DCMT", "VCMT")]
LATHE_COATINGS = [("uncoated", "Uncoated"), ("CVD", "CVD"), ("PVD", "PVD"), ("cermet", "Cermet")]
CHIPBREAKERS = [("finishing", "Finishing"), ("medium", "Medium"), ("roughing", "Roughing")]

CHOICES = {
    "tool_materials": TOOL_MATERIALS,
    "mill_tool_types": MILL_TOOL_TYPES,
    "mill_coatings": MILL_COATINGS,
    "mill_paths": MILL_PATHS,
    "chip_thinning": CHIP_THINNING,
    "turning_cuts": TURNING_CUTS,
    "insert_shapes": INSERT_SHAPES,
    "lathe_coatings": LATHE_COATINGS,
    "chipbreakers": CHIPBREAKERS,
}

# Turning data only applies to these cuts. Grooving, parting and threading
# run at different speeds and feeds, so they need the user's own numbers.
TURNING_DATA_CUTS = ("od", "id", "face")

LEVELS = (("low", "Low"), ("rec", "Recommended"), ("high", "High"))

# Form fields that hold measurements, and what kind each one is. Used to
# convert the form when someone flips between inch and metric.
MILLING_FIELDS = {
    "diameter": "length", "woc": "length", "doc": "length", "stickout": "length",
    "corner_radius": "length", "feature_diameter": "length", "sfm": "speed",
    "chip_load": "feed_tooth", "max_feed": "feed_rate", "spindle_hp": "power",
}
DRILLING_FIELDS = {
    "diameter": "length", "sfm": "speed", "ipr": "feed_rev",
    "max_feed": "feed_rate", "spindle_hp": "power",
}
TURNING_FIELDS = {
    "start_diameter": "length", "finish_diameter": "length", "doc": "length",
    "nose_radius": "length", "sfm": "speed", "ipr": "feed_rev", "pitch": "thread",
    "max_feed": "feed_rate", "spindle_hp": "power",
}


# --- Reading the form ------------------------------------------------------

class FormReader:
    """Reads form values, converts metric to inch, and collects errors."""

    def __init__(self, args, unit_system):
        self.args = args
        self.units = unit_system
        self.errors = []

    def raw(self, name):
        return (self.args.get(name) or "").strip()

    def all_blank(self, *names):
        return not any(self.raw(name) for name in names)

    def choice(self, name, options):
        """Return the picked option, or the first option if it isn't valid."""
        value = self.raw(name)
        keys = [key for key, _ in options]
        return value if value in keys else keys[0]

    def text(self, name, max_length=40):
        return self.raw(name)[:max_length]

    def number(self, name, label, kind=None, required=False, allow_zero=False, whole=False):
        """Return the field as an inch-unit float, or None if blank or bad."""
        raw = self.raw(name)
        if not raw:
            if required:
                self.errors.append(f"{label} is required.")
            return None
        try:
            value = units.parse_number(raw)
        except ValueError:
            self.errors.append(f'{label}: "{raw}" isn\'t a number.')
            return None
        if value < 0 or (value == 0 and not allow_zero):
            self.errors.append(f"{label} must be greater than 0.")
            return None
        if whole and value != int(value):
            self.errors.append(f"{label} must be a whole number.")
            return None
        if kind:
            value = units.to_inch(value, kind, self.units)
        return value


# --- What the results panel shows ------------------------------------------

Item = namedtuple("Item", "label value kind note")
Message = namedtuple("Message", "level text")
SourceNote = namedtuple("SourceNote", "what value kind source source_ref date_checked confidence")
Range = namedtuple("Range", "columns rows")


class Result:
    """Everything the results panel shows. Values are in inch units."""

    def __init__(self, unit_system, errors):
        self.units = unit_system
        self.errors = errors
        self.headline = []
        self.details = []
        self.range = None
        self.messages = []
        self.sources = []
        self.copy_lines = []

    def show(self, value, kind):
        """Format a value with its unit, for use inside a sentence."""
        return units.fmt(value, kind, self.units, with_label=True)

    def add_headline(self, label, value, kind):
        self.headline.append(Item(label, value, kind, ""))

    def add_detail(self, label, value, kind, note=""):
        self.details.append(Item(label, value, kind, note))

    def warn(self, text):
        self.messages.append(Message("warn", text))

    def info(self, text):
        self.messages.append(Message("info", text))

    @property
    def headline_text(self):
        """One line for the phone bar, e.g. "Spindle 6112 RPM   Feed 110.0 IPM"."""
        return "   ".join(f"{item.label} {self.show(item.value, item.kind)}" for item in self.headline)

    @property
    def copy_text(self):
        return "\n".join(gcode_comment(line) for line in self.copy_lines)


def gcode_comment(text):
    """Format one line as a G-code comment: (UPPERCASE, NO NESTED PARENTHESES)."""
    for fancy, plain in (("³", "3"), ("×", "X"), ("–", "-"), ("—", "-"), ("Ø", "DIA ")):
        text = text.replace(fancy, plain)
    text = text.replace("(", "").replace(")", "")
    text = text.encode("ascii", "ignore").decode()
    return "(" + " ".join(text.upper().split()) + ")"


# --- Milling ---------------------------------------------------------------

def calculate_milling(args, unit_system, data):
    form = FormReader(args, unit_system)
    if form.all_blank("diameter", "flutes", "woc", "doc"):
        return None

    material = data.material(form.raw("material"))
    tool_type = form.choice("tool_type", MILL_TOOL_TYPES)
    tool_material = form.choice("tool_material", TOOL_MATERIALS)
    coating = form.choice("coating", MILL_COATINGS)
    path = form.choice("path", MILL_PATHS)
    thinning = form.choice("thinning", CHIP_THINNING)

    diameter = form.number("diameter", "Tool diameter", "length", required=True)
    flutes = form.number("flutes", "Flutes", required=True, whole=True)
    woc = form.number("woc", "Radial depth (WOC)", "length", required=True)
    doc = form.number("doc", "Axial depth (DOC)", "length", required=True)
    helix = form.number("helix", "Helix angle")
    corner_radius = form.number("corner_radius", "Corner radius", "length", allow_zero=True)
    stickout = form.number("stickout", "Stickout", "length")
    feature = form.number("feature_diameter", "Hole or boss diameter", "length",
                          required=path != "straight")
    sfm_input = form.number("sfm", "Surface speed", "speed")
    chip_input = form.number("chip_load", "Chip load", "feed_tooth")
    max_rpm = form.number("max_rpm", "Machine max RPM", required=True)
    max_feed = form.number("max_feed", "Machine max feed", "feed_rate")
    spindle_hp = form.number("spindle_hp", "Spindle power", "power")

    errors = form.errors
    if diameter and woc and woc > diameter:
        errors.append("Radial depth (WOC) can't be more than the tool diameter.")
    if diameter and corner_radius and corner_radius > diameter / 2:
        errors.append("Corner radius can't be more than half the tool diameter.")
    if path == "internal" and diameter and feature and feature <= diameter:
        errors.append("The hole has to be bigger than the tool.")
    result = Result(unit_system, errors)
    if errors:
        return result

    key = material["material_key"] if material else None
    speed_rows = data.speeds(key, "milling", tool_material, tool_type) if material else []
    feed_rows = data.feeds(key, "milling", tool_material, tool_type, diameter) if material else []
    power_rows = data.unit_power(key) if material else []
    speed_row, feed_row, power_row = _first(speed_rows), _first(feed_rows), _first(power_rows)

    sfm = _pick(sfm_input, speed_row, "sfm")
    chip_load = _pick(chip_input, feed_row, "feed")
    tool_desc = (f"a {result.show(diameter, 'length')} {tool_material} "
                 f"{dict(MILL_TOOL_TYPES)[tool_type].lower()}")
    if sfm is None:
        errors.append(_missing("surface speed", material, tool_desc))
    if chip_load is None:
        errors.append(_missing("chip load", material, tool_desc))
    if errors:
        return result

    def run(s, c):
        return _milling_numbers(s, c, diameter, flutes, woc, doc, max_rpm, path, feature, thinning)

    n = run(sfm, chip_load)
    capped = n["rpm"] < n["rpm_wanted"]

    result.add_headline("Spindle", n["rpm"], "rpm")
    result.add_headline("Feed", n["feed"], "feed_rate")

    result.add_detail("Surface speed", n["sfm"], "speed",
                      "Below target because RPM is capped" if capped else "")
    result.add_detail("Chip load (programmed)", n["chip_load"], "feed_tooth",
                      "Raised to make up for chip thinning"
                      if thinning == "apply" and n["factor"] > 1 else "")
    result.add_detail("Actual chip thickness", n["chip_thickness"], "feed_tooth")
    result.add_detail("Chip thinning factor", n["factor"], "ratio",
                      f"WOC is {woc / diameter:.0%} of the tool diameter")
    if path != "straight":
        result.add_detail("Feed at the cutting edge", n["edge_feed"], "feed_rate",
                          "The feed above is at the tool center, which is what you program")
    result.add_detail("Material removal rate", n["mrr"], "mrr")
    _check_power(result, n["mrr"], power_row, spindle_hp)
    if stickout:
        result.add_detail("Stickout ratio", stickout / diameter, "ratio", "Stickout ÷ diameter")

    result.range = _build_range(speed_row, feed_row, sfm, chip_load, run, [
        ("Spindle", "rpm", "rpm"),
        ("Feed", "feed_rate", "feed"),
        ("Surface speed", "speed", "sfm"),
        ("Chip load", "feed_tooth", "chip_load"),
    ])

    _check_capped(result, n["rpm"], n["rpm_wanted"], n["sfm"], max_rpm)
    _check_max_feed(result, n["feed"], max_feed)
    _check_rubbing(result, n["chip_thickness"], feed_row, "feed_tooth", "Actual chip thickness")
    if thinning == "ignore" and n["factor"] > 1:
        result.info(
            f"Chip thinning isn't adjusted for, so the real chip is "
            f"{result.show(n['chip_thickness'], 'feed_tooth')}, thinner than the "
            f"{result.show(n['chip_load'], 'feed_tooth')} programmed."
        )
    if stickout and stickout / diameter > LONG_STICKOUT_RATIO:
        result.warn(
            f"Stickout is {stickout / diameter:.1f}× the tool diameter. Long tools deflect "
            "and chatter; consider backing off speed, feed or depth."
        )
    _check_small_tool(result, material, diameter, "tool")
    if tool_type == "ball" and doc < diameter / 2:
        d_eff = formulas.ball_effective_diameter(doc, diameter)
        result.info(
            f"At this DOC the ball only cuts at {result.show(d_eff, 'length')} diameter, "
            f"so the real surface speed there is "
            f"{result.show(formulas.sfm_from_rpm(n['rpm'], d_eff), 'speed')}."
        )
    _note_overrides(result, material, [
        ("surface speed", sfm_input, speed_row, "sfm", "speed"),
        ("chip load", chip_input, feed_row, "feed", "feed_tooth"),
    ])

    _add_sources(result, "Surface speed", speed_rows, "sfm", "speed", sfm_input)
    _add_sources(result, "Chip load", feed_rows, "feed", "feed_tooth", chip_input)
    _add_sources(result, "Unit power", power_rows, "hp_per_in3_min", "unit_power", None)

    v = _value_formatter(unit_system)
    tool_line = f"TOOL DIA {v(diameter, 'length')} {flutes:g}FL {tool_material} {tool_type}"
    if coating != "uncoated":
        tool_line += f" {coating}"
    if corner_radius:
        tool_line += f" CR {v(corner_radius, 'length')}"
    if helix:
        tool_line += f" {helix:g} DEG HELIX"
    if stickout:
        tool_line += f" STICKOUT {v(stickout, 'length')}"
    result.copy_lines = [
        f"MILLING - {_material_name(material)}",
        tool_line,
        f"WOC {v(woc, 'length')} DOC {v(doc, 'length')} {units.label('length', unit_system)}",
        f"S{v(n['rpm'], 'rpm')} F{v(n['feed'], 'feed_rate')} {units.label('feed_rate', unit_system)}",
        f"SPEED {result.show(n['sfm'], 'speed')} CHIP LOAD {result.show(n['chip_load'], 'feed_tooth')}",
    ]
    if path != "straight":
        shape = "HOLE" if path == "internal" else "BOSS"
        result.copy_lines.append(f"{shape} DIA {v(feature, 'length')} - F IS AT TOOL CENTER")
    return result


def _milling_numbers(sfm, chip_load, diameter, flutes, woc, doc, max_rpm, path, feature, thinning):
    rpm_wanted = formulas.milling_rpm_inch(sfm, diameter)
    rpm = formulas.cap_rpm(rpm_wanted, max_rpm)
    factor = formulas.chip_thinning_factor(woc, diameter)
    programmed = chip_load * factor if thinning == "apply" else chip_load
    edge_feed = formulas.milling_feed_rate(rpm, programmed, flutes)
    if path == "internal":
        feed = formulas.circular_feed_internal(edge_feed, feature, diameter)
    elif path == "external":
        feed = formulas.circular_feed_external(edge_feed, feature, diameter)
    else:
        feed = edge_feed
    return {
        "rpm_wanted": rpm_wanted,
        "rpm": rpm,
        "sfm": formulas.sfm_from_rpm(rpm, diameter),
        "factor": factor,
        "chip_load": programmed,
        "chip_thickness": programmed / factor,
        "edge_feed": edge_feed,
        "feed": feed,
        # Material is cut at the edge, so MRR uses the edge feed.
        "mrr": formulas.milling_mrr(woc, doc, edge_feed),
    }


# --- Drilling --------------------------------------------------------------

def calculate_drilling(args, unit_system, data):
    form = FormReader(args, unit_system)
    if form.all_blank("diameter"):
        return None

    material = data.material(form.raw("material"))
    tool_material = form.choice("tool_material", TOOL_MATERIALS)
    coating = form.choice("coating", MILL_COATINGS)

    diameter = form.number("diameter", "Drill diameter", "length", required=True)
    sfm_input = form.number("sfm", "Surface speed", "speed")
    ipr_input = form.number("ipr", "Feed per rev", "feed_rev")
    max_rpm = form.number("max_rpm", "Machine max RPM", required=True)
    max_feed = form.number("max_feed", "Machine max feed", "feed_rate")
    spindle_hp = form.number("spindle_hp", "Spindle power", "power")

    errors = form.errors
    result = Result(unit_system, errors)
    if errors:
        return result

    key = material["material_key"] if material else None
    speed_rows = data.speeds(key, "drilling", tool_material, "drill") if material else []
    feed_rows = data.feeds(key, "drilling", tool_material, "drill", diameter) if material else []
    power_rows = data.unit_power(key) if material else []
    speed_row, feed_row, power_row = _first(speed_rows), _first(feed_rows), _first(power_rows)

    sfm = _pick(sfm_input, speed_row, "sfm")
    ipr = _pick(ipr_input, feed_row, "feed")
    tool_desc = f"a {result.show(diameter, 'length')} {tool_material} drill"
    if sfm is None:
        errors.append(_missing("surface speed", material, tool_desc))
    if ipr is None:
        errors.append(_missing("feed per rev", material, tool_desc))
    if errors:
        return result

    def run(s, f):
        return _drilling_numbers(s, f, diameter, max_rpm)

    n = run(sfm, ipr)
    capped = n["rpm"] < n["rpm_wanted"]

    result.add_headline("Spindle", n["rpm"], "rpm")
    result.add_headline("Feed", n["feed"], "feed_rate")
    result.add_detail("Surface speed", n["sfm"], "speed",
                      "Below target because RPM is capped" if capped else "")
    result.add_detail("Feed per rev", n["ipr"], "feed_rev")
    result.add_detail("Material removal rate", n["mrr"], "mrr")
    _check_power(result, n["mrr"], power_row, spindle_hp)

    result.range = _build_range(speed_row, feed_row, sfm, ipr, run, [
        ("Spindle", "rpm", "rpm"),
        ("Feed", "feed_rate", "feed"),
        ("Surface speed", "speed", "sfm"),
        ("Feed per rev", "feed_rev", "ipr"),
    ])

    _check_capped(result, n["rpm"], n["rpm_wanted"], n["sfm"], max_rpm)
    _check_max_feed(result, n["feed"], max_feed)
    _check_rubbing(result, n["ipr"], feed_row, "feed_rev", "Feed per rev")
    _check_small_tool(result, material, diameter, "drill")
    _note_overrides(result, material, [
        ("surface speed", sfm_input, speed_row, "sfm", "speed"),
        ("feed per rev", ipr_input, feed_row, "feed", "feed_rev"),
    ])

    _add_sources(result, "Surface speed", speed_rows, "sfm", "speed", sfm_input)
    _add_sources(result, "Feed per rev", feed_rows, "feed", "feed_rev", ipr_input)
    _add_sources(result, "Unit power", power_rows, "hp_per_in3_min", "unit_power", None)

    v = _value_formatter(unit_system)
    tool_line = f"DRILL DIA {v(diameter, 'length')} {units.label('length', unit_system)} {tool_material}"
    if coating != "uncoated":
        tool_line += f" {coating}"
    result.copy_lines = [
        f"DRILLING - {_material_name(material)}",
        tool_line,
        f"S{v(n['rpm'], 'rpm')} F{v(n['feed'], 'feed_rate')} {units.label('feed_rate', unit_system)}",
        f"SPEED {result.show(n['sfm'], 'speed')} FEED {result.show(n['ipr'], 'feed_rev')}",
    ]
    return result


def _drilling_numbers(sfm, ipr, diameter, max_rpm):
    # Same RPM formula as milling: the drill is the tool that spins.
    rpm_wanted = formulas.milling_rpm_inch(sfm, diameter)
    rpm = formulas.cap_rpm(rpm_wanted, max_rpm)
    feed = formulas.drilling_feed_rate(rpm, ipr)
    return {
        "rpm_wanted": rpm_wanted,
        "rpm": rpm,
        "sfm": formulas.sfm_from_rpm(rpm, diameter),
        "ipr": ipr,
        "feed": feed,
        "mrr": formulas.drilling_mrr(diameter, feed),
    }


# --- Turning ---------------------------------------------------------------

def calculate_turning(args, unit_system, data):
    form = FormReader(args, unit_system)
    if form.all_blank("start_diameter", "finish_diameter", "doc"):
        return None

    material = data.material(form.raw("material"))
    cut = form.choice("cut_type", TURNING_CUTS)
    tool_material = form.choice("tool_material", TOOL_MATERIALS)
    insert_shape = form.choice("insert_shape", INSERT_SHAPES)
    coating = form.choice("coating", LATHE_COATINGS)
    chipbreaker = form.choice("chipbreaker", CHIPBREAKERS)
    grade = form.text("grade")

    start = form.number("start_diameter", "Start diameter", "length", required=True)
    finish = form.number("finish_diameter", "Finish diameter", "length", allow_zero=True)
    doc = form.number("doc", "Depth of cut", "length")
    nose_radius = form.number("nose_radius", "Nose radius", "length")
    sfm_input = form.number("sfm", "Surface speed", "speed")
    ipr_input = form.number("ipr", "Feed per rev", "feed_rev")
    lead = form.number("pitch", "Thread pitch", "thread", required=cut == "thread")
    max_rpm = form.number("max_rpm", "Machine max RPM", required=True)
    chuck_max = form.number("chuck_max_rpm", "Chuck max RPM")
    max_feed = form.number("max_feed", "Machine max feed", "feed_rate")
    spindle_hp = form.number("spindle_hp", "Spindle power", "power")

    errors = form.errors
    result = Result(unit_system, errors)
    if errors:
        return result
    if finish is None:
        finish = start

    v = _value_formatter(unit_system)
    tool_line = f"INSERT {insert_shape}"
    if nose_radius:
        tool_line += f" R{v(nose_radius, 'length')}"
    tool_line += f" {grade} {tool_material}"
    if coating != "uncoated":
        tool_line += f" {coating}"
    tool_line += f" {chipbreaker}"

    if cut == "thread":
        return _threading(result, material, sfm_input, lead, start, max_rpm, chuck_max,
                          max_feed, tool_line)

    uses_data = material is not None and cut in TURNING_DATA_CUTS
    key = material["material_key"] if material else None
    speed_rows = data.speeds(key, "turning", tool_material) if uses_data else []
    feed_rows = data.feeds(key, "turning", tool_material) if uses_data else []
    power_rows = data.unit_power(key) if material else []
    speed_row, feed_row, power_row = _first(speed_rows), _first(feed_rows), _first(power_rows)

    sfm = _pick(sfm_input, speed_row, "sfm")
    ipr = _pick(ipr_input, feed_row, "feed")
    for what, value in (("surface speed", sfm), ("feed per rev", ipr)):
        if value is None:
            if material is not None and not uses_data:
                errors.append(f"Enter a {what}. Grooving and parting use your own numbers, "
                              "not the turning data.")
            else:
                errors.append(_missing(what, material, f"{tool_material} turning tools"))
    if errors:
        return result

    def run(s, f):
        return _turning_numbers(s, f, start, finish, doc, max_rpm, chuck_max)

    n = run(sfm, ipr)
    limit = n["limit"]
    start_capped = n["rpm_start"] < n["wanted_start"]
    finish_capped = n["rpm_finish"] < n["wanted_finish"]

    result.add_headline("G96 S", sfm, "speed")
    result.add_headline("Feed", ipr, "feed_rev")
    result.add_headline("G50 S", limit, "rpm")

    result.add_detail("RPM at start diameter", n["rpm_start"], "rpm",
                      "At the RPM limit" if start_capped else "")
    result.add_detail("RPM at finish diameter", n["rpm_finish"], "rpm",
                      "At the RPM limit" if finish_capped else "")
    result.add_detail("Feed at start diameter", n["feed_start"], "feed_rate")
    result.add_detail("Feed at finish diameter", n["feed_finish"], "feed_rate")
    result.add_detail("RPM limit reached below", n["clamp_diameter"], "length",
                      "Diameter where G96 hits the G50 clamp")
    if start_capped:
        result.add_detail("Surface speed at start", n["sfm_start"], "speed",
                          "Below target because RPM is capped")
    if n["mrr"] is not None:
        result.add_detail("Material removal rate", n["mrr"], "mrr", "At the start diameter")
        _check_power(result, n["mrr"], power_row, spindle_hp)

    result.range = _build_range(speed_row, feed_row, sfm, ipr, run, [
        ("G96 S", "speed", "sfm"),
        ("Feed", "feed_rev", "ipr"),
        ("RPM at start", "rpm", "rpm_start"),
        ("Feed at start", "feed_rate", "feed_start"),
    ])

    if start_capped and finish_capped:
        result.warn(
            f"The whole cut runs at the {result.show(limit, 'rpm')} limit, so surface speed "
            f"is only {result.show(n['sfm_start'], 'speed')} at the start diameter."
        )
    elif start_capped or finish_capped:
        result.info(
            f"Below {result.show(n['clamp_diameter'], 'length')} diameter the spindle sits at "
            f"the {result.show(limit, 'rpm')} limit and surface speed drops."
        )
    if chuck_max is None:
        result.info("Enter your chuck or workholding max RPM. G50 should be the lowest of the "
                    "machine, chuck and workholding limits.")
    _check_max_feed(result, max(n["feed_start"], n["feed_finish"]), max_feed)
    _check_rubbing(result, ipr, feed_row, "feed_rev", "Feed per rev")
    if material is not None and not uses_data:
        result.info("Grooving and parting use your own numbers; the turning data isn't used.")
    else:
        _note_overrides(result, material, [
            ("surface speed", sfm_input, speed_row, "sfm", "speed"),
            ("feed per rev", ipr_input, feed_row, "feed", "feed_rev"),
        ])

    _add_sources(result, "Surface speed", speed_rows, "sfm", "speed", sfm_input)
    _add_sources(result, "Feed per rev", feed_rows, "feed", "feed_rev", ipr_input)
    if n["mrr"] is not None:
        _add_sources(result, "Unit power", power_rows, "hp_per_in3_min", "unit_power", None)

    cut_name = dict(TURNING_CUTS)[cut]
    length_unit = units.label("length", unit_system)
    dims = f"DIA {v(start, 'length')} TO {v(finish, 'length')}"
    if doc:
        dims += f" DOC {v(doc, 'length')}"
    result.copy_lines = [
        f"{cut_name} - {_material_name(material)}",
        tool_line,
        f"G50 S{v(limit, 'rpm')}",
        f"G96 S{v(sfm, 'speed')} F{v(ipr, 'feed_rev')}",
        f"{dims} {length_unit}",
    ]
    return result


def _turning_numbers(sfm, ipr, start, finish, doc, max_rpm, chuck_max):
    limit = max_rpm if chuck_max is None else min(max_rpm, chuck_max)

    def rpm_at(diameter):
        if diameter == 0:
            # Facing or parting to center: CSS would need endless RPM.
            return limit, float("inf")
        wanted = formulas.turning_rpm_inch(sfm, diameter)
        return formulas.cap_rpm(wanted, max_rpm, chuck_max), wanted

    rpm_start, wanted_start = rpm_at(start)
    rpm_finish, wanted_finish = rpm_at(finish)
    sfm_start = formulas.sfm_from_rpm(rpm_start, start)
    return {
        "sfm": sfm,
        "ipr": ipr,
        "limit": limit,
        "rpm_start": rpm_start,
        "rpm_finish": rpm_finish,
        "wanted_start": wanted_start,
        "wanted_finish": wanted_finish,
        "sfm_start": sfm_start,
        "feed_start": formulas.turning_feed_rate(rpm_start, ipr),
        "feed_finish": formulas.turning_feed_rate(rpm_finish, ipr),
        "clamp_diameter": formulas.diameter_for_rpm_inch(sfm, limit),
        "mrr": formulas.turning_mrr_inch(sfm_start, ipr, doc) if doc else None,
    }


def _threading(result, material, sfm_input, lead, diameter, max_rpm, chuck_max, max_feed,
               tool_line):
    if sfm_input is None:
        result.errors.append("Enter a threading surface speed. Threading uses your own "
                             "numbers, not the turning data.")
        return result

    rpm_wanted = formulas.turning_rpm_inch(sfm_input, diameter)
    rpm = formulas.cap_rpm(rpm_wanted, max_rpm, chuck_max)
    sfm = formulas.sfm_from_rpm(rpm, diameter)
    feed = formulas.turning_feed_rate(rpm, lead)

    result.add_headline("G97 S", rpm, "rpm")
    result.add_headline("Pitch", lead, "thread")
    result.add_headline("Feed", feed, "feed_rate")
    result.add_detail("Lead per rev", lead, "feed_rev",
                      "Single-start thread. For multi-start, lead = pitch × starts")
    result.add_detail("Surface speed", sfm, "speed",
                      "Below target because RPM is capped" if rpm < rpm_wanted else "")

    result.info("Threading runs at a fixed RPM (G97), not constant surface speed, so the "
                "lead stays in step with the spindle.")
    _check_capped(result, rpm, rpm_wanted, sfm, max_rpm, chuck_max)
    _check_max_feed(result, feed, max_feed)
    _add_sources(result, "Surface speed", [], "sfm", "speed", sfm_input)

    v = _value_formatter(result.units)
    result.copy_lines = [
        f"THREADING - {_material_name(material)}",
        tool_line,
        f"G97 S{v(rpm, 'rpm')}",
        f"LEAD {result.show(lead, 'feed_rev')} - {result.show(lead, 'thread')}",
        f"MAJOR DIA {v(diameter, 'length')} {units.label('length', result.units)}",
    ]
    return result


# --- Shared helpers --------------------------------------------------------

def _first(rows):
    return rows[0] if rows else None


def _pick(user_value, row, prefix):
    """The user's value if they typed one, otherwise the data's recommended value."""
    if user_value is not None:
        return user_value
    return _data_value(row, prefix) if row else None


def _data_value(row, prefix, level="rec"):
    """Read the low, rec or high value from a speed or feed row.

    prefix is "sfm" or "feed". When the source only gives a range, the
    recommended value is the middle of it. When it only gives one number,
    low and high fall back to that number.
    """
    low, rec, high = row[f"{prefix}_low"], row[f"{prefix}_rec"], row[f"{prefix}_high"]
    if rec is None:
        rec = (low + high) / 2  # the schema makes sure low and high are both set
    return {"low": low if low is not None else rec,
            "rec": rec,
            "high": high if high is not None else rec}[level]


def _is_midpoint(row, prefix):
    return row is not None and row[f"{prefix}_rec"] is None


def _missing(what, material, tool_desc):
    """Error for a value the user didn't type and the data doesn't have.

    tool_desc says which tool was looked up, e.g. "a 0.5000 in carbide flat
    end mill", since data often only covers some tool types and sizes.
    """
    if material is None:
        return f"Enter a {what}, or pick a material that has data."
    return (f"No {what} data for {material['label']} with {tool_desc} yet. "
            f"Enter a {what}.")


def _material_name(material):
    return material["label"] if material else "MATERIAL NOT SET"


def _value_formatter(unit_system):
    return lambda value, kind: units.fmt(value, kind, unit_system)


def _build_range(speed_row, feed_row, speed, feed, run, rows):
    """Build the low / recommended / high table from the data rows.

    Where a row has no data, the value in use fills every column. Returns
    None when all three columns would be the same, since the headline
    already shows that.
    """
    if speed_row is None and feed_row is None:
        return None
    inputs = []
    for level, _ in LEVELS:
        s = _data_value(speed_row, "sfm", level) if speed_row else speed
        f = _data_value(feed_row, "feed", level) if feed_row else feed
        inputs.append((s, f))
    if len(set(inputs)) == 1:
        return None
    columns = [run(s, f) for s, f in inputs]
    table = [(label, kind, [col[key] for col in columns]) for label, kind, key in rows]
    titles = [title for _, title in LEVELS]
    if _is_midpoint(speed_row, "sfm") or _is_midpoint(feed_row, "feed"):
        titles[1] = "Middle"
    return Range(titles, table)


def _check_capped(result, rpm, rpm_wanted, sfm_actual, max_rpm, chuck_max=None):
    if rpm >= rpm_wanted:
        return
    limit = "chuck max" if chuck_max is not None and chuck_max < max_rpm else "machine max"
    result.warn(
        f"RPM capped at {result.show(rpm, 'rpm')} by the {limit}. Surface speed drops to "
        f"{result.show(sfm_actual, 'speed')}, and feed is figured from the capped RPM."
    )


def _check_max_feed(result, feed, max_feed):
    if max_feed is not None and feed > max_feed:
        result.warn(f"Feed {result.show(feed, 'feed_rate')} is over the machine max of "
                    f"{result.show(max_feed, 'feed_rate')}.")


def _check_rubbing(result, actual, feed_row, kind, what):
    low = feed_row["feed_low"] if feed_row else None
    if low is not None and actual < low:
        result.warn(f"{what} {result.show(actual, kind)} is under the low end of the data "
                    f"({result.show(low, kind)}). The tool may rub instead of cut.")


def _check_power(result, mrr, power_row, spindle_hp):
    """Add estimated cutting power, and warn if it's more than the spindle has."""
    if power_row is None:
        return
    hp = formulas.cutting_hp(mrr, power_row["hp_per_in3_min"])
    result.add_detail("Cutting power (est.)", hp, "power", "At the cutter, before machine losses")
    if spindle_hp is not None and hp > spindle_hp:
        result.warn(f"Estimated cutting power {result.show(hp, 'power')} is more than the "
                    f"{result.show(spindle_hp, 'power')} spindle. Lighten the cut.")


def _check_small_tool(result, material, diameter, tool_word):
    if (material and material["iso_group"] in HARD_ISO_GROUPS
            and diameter < SMALL_TOOL_DIAMETER_IN):
        result.warn(f"Small {tool_word} in ISO {material['iso_group']} material. Small tools "
                    "break easily in hard materials; start at the low end.")


def _note_overrides(result, material, overrides):
    """Say where the numbers came from when they aren't straight from the data."""
    if material is None:
        result.info("No material data in use, so these numbers come from your own inputs.")
        return
    for what, user_value, row, prefix, kind in overrides:
        if row is None:
            continue
        if user_value is not None:
            result.info(f"Using your {what} instead of the data's "
                        f"{result.show(_data_value(row, prefix), kind)}.")
        elif _is_midpoint(row, prefix):
            result.info(
                f"The source gives a {what} range of "
                f"{result.show(row[f'{prefix}_low'], kind)} to "
                f"{result.show(row[f'{prefix}_high'], kind)}, so this uses the middle. "
                "Start lower if your setup isn't rigid."
            )


def _row_value(row, field):
    """A row's value for display: the recommended value for speeds and feeds."""
    if f"{field}_rec" in row:
        return _data_value(row, field)
    return row[field]


def _add_sources(result, what, rows, field, kind, user_value):
    """List where each number came from, plus other sources to cross-check.

    rows is best match first. Only the best row from each source is shown.
    """
    best_per_source = []
    for row in rows:
        if all(row["source"] != seen["source"] for seen in best_per_source):
            best_per_source.append(row)

    others = best_per_source
    if user_value is not None:
        result.sources.append(SourceNote(what, user_value, kind, "Your input", "", "", ""))
    elif best_per_source:
        best = best_per_source[0]
        result.sources.append(SourceNote(what, _row_value(best, field), kind, best["source"],
                                         best["source_ref"], best["date_checked"],
                                         best["confidence"]))
        others = best_per_source[1:]
    for row in others:
        result.sources.append(SourceNote(f"{what} (cross-check)", _row_value(row, field), kind,
                                         row["source"], row["source_ref"], row["date_checked"],
                                         row["confidence"]))


# --- Unit toggle -----------------------------------------------------------

Operation = namedtuple("Operation", "title machine_type fields calculate")

OPERATIONS = {
    "milling": Operation("Milling", "mill", MILLING_FIELDS, calculate_milling),
    "drilling": Operation("Drilling", "mill", DRILLING_FIELDS, calculate_drilling),
    "turning": Operation("Turning", "lathe", TURNING_FIELDS, calculate_turning),
}


def convert_args(op, args, from_units, to_units):
    """Return the form values with every measurement converted to new units."""
    kinds = OPERATIONS[op].fields
    converted = {}
    for name, value in args.items():
        if name == "convert_to":
            continue
        kind = kinds.get(name)
        if kind and value.strip():
            try:
                value = units.convert_text(value, kind, from_units, to_units)
            except (ValueError, ZeroDivisionError):
                pass  # leave bad input alone; the form will point it out
        converted[name] = value
    converted["units"] = to_units
    return converted
