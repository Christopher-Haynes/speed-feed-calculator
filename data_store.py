"""Material, machine and cutting data.

The CSV files in data/ are the source of truth. build_database() loads
them into SQLite and checks every row, so a typo fails loudly with the
file name and line number instead of quietly showing a wrong number.
"""

import csv
import os
import re
import sqlite3
import tempfile
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# Load order matters: materials must exist before the rows that point to them.
TABLES = ("materials", "machines", "cutting_speeds", "feeds", "unit_power")

ISO_GROUPS = [
    ("P", "Steel"),
    ("M", "Stainless steel"),
    ("K", "Cast iron"),
    ("N", "Non-ferrous"),
    ("S", "Superalloys and titanium"),
    ("H", "Hardened steel"),
]

# Best source first when more than one row covers the same cut.
CONFIDENCE_RANK = (
    "CASE confidence WHEN 'shop-verified' THEN 0 WHEN 'manufacturer' THEN 1 ELSE 2 END"
)

# A tool type also matches rows written for its family, so a ball end
# mill uses "end mill" rows when there's no "ball" row.
TOOL_FAMILIES = {"flat": "end mill", "ball": "end mill", "bull nose": "end mill"}

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DataError(Exception):
    """A CSV file or row that can't be loaded."""


# --- Building the database -------------------------------------------------

def build_database(db_path, data_dir=DATA_DIR):
    """Build a fresh SQLite database at db_path from the CSV files in data_dir."""
    db_path = Path(db_path)
    data_dir = Path(data_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Build into a temp file and swap it in at the end, so a bad row never
    # leaves a half-built database behind.
    fd, tmp_name = tempfile.mkstemp(dir=db_path.parent, suffix=".tmp")
    os.close(fd)
    try:
        conn = sqlite3.connect(tmp_name)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript((data_dir / "schema.sql").read_text(encoding="utf-8"))
            for table in TABLES:
                _load_csv(conn, table, data_dir / f"{table}.csv")
            conn.commit()
        finally:
            conn.close()
        os.replace(tmp_name, db_path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def _load_csv(conn, table, csv_path):
    # Table names come from TABLES above, never from user input.
    columns = {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info({table})")}

    # utf-8-sig skips the invisible marker Excel puts at the start of a file.
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        if set(header) != set(columns):
            missing = sorted(set(columns) - set(header)) or "none"
            extra = sorted(set(header) - set(columns)) or "none"
            raise DataError(
                f"{csv_path.name}: header doesn't match the {table} table "
                f"(missing: {missing}, unexpected: {extra})"
            )

        names = ", ".join(columns)
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO {table} ({names}) VALUES ({placeholders})"

        for row in reader:
            line = reader.line_num
            if None in row:
                raise DataError(
                    f"{csv_path.name} line {line}: more values than columns. "
                    "Wrap values that contain a comma in double quotes."
                )
            if None in row.values():
                raise DataError(f"{csv_path.name} line {line}: fewer values than columns. "
                                "Check for a missing comma.")
            if not any((value or "").strip() for value in row.values()):
                continue  # blank line
            try:
                values = [_convert(row[name], col_type, name) for name, col_type in columns.items()]
                conn.execute(sql, values)
            except (ValueError, sqlite3.IntegrityError) as e:
                raise DataError(f"{csv_path.name} line {line}: {e}") from e


def _convert(raw, col_type, name):
    text = (raw or "").strip()
    if not text:
        return None
    if col_type == "REAL":
        try:
            return float(text)
        except ValueError:
            raise ValueError(f"{name} must be a number, got {text!r}") from None
    if name == "date_checked" and not _is_date(text):
        raise ValueError(f"date_checked must be YYYY-MM-DD, got {text!r}")
    return text


def _is_date(text):
    if not _DATE.match(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


# --- Reading ---------------------------------------------------------------

def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def list_material_groups(conn):
    """Return materials grouped by ISO group, in P, M, K, N, S, H order."""
    rows = [dict(r) for r in conn.execute("SELECT * FROM materials ORDER BY name, condition")]
    for row in rows:
        row["label"] = _material_label(row)

    groups = []
    for code, name in ISO_GROUPS:
        members = [row for row in rows if row["iso_group"] == code]
        if members:
            groups.append({"code": code, "name": name, "materials": members})
    return groups


def _material_label(row):
    """e.g. "4140 Annealed (175–225 HB)"."""
    text = row["name"]
    if row["condition"]:
        text += f" {row['condition']}"
    values = [v for v in (row["hardness_min"], row["hardness_max"]) if v is not None]
    if values:
        hardness = "–".join(f"{v:g}" for v in values)
        if row["hardness_scale"]:
            hardness += f" {row['hardness_scale']}"
        text += f" ({hardness})"
    return text


def list_machines(conn, machine_type):
    rows = conn.execute(
        "SELECT * FROM machines WHERE machine_type = ? ORDER BY name", (machine_type,)
    )
    return [dict(r) for r in rows]


def list_sources(conn):
    """Return every source used, with how many rows cite it."""
    parts = " UNION ALL ".join(
        f"SELECT source, confidence, date_checked, '{table}' AS tbl FROM {table}"
        for table in TABLES
    )
    rows = conn.execute(f"""
        SELECT source, confidence, COUNT(*) AS row_count,
               MAX(date_checked) AS last_checked,
               GROUP_CONCAT(DISTINCT tbl) AS tables
        FROM ({parts})
        GROUP BY source, confidence
        ORDER BY source
    """)
    return [dict(r) for r in rows]


class DataLookup:
    """Finds the data rows the calculator needs. Best match comes first."""

    def __init__(self, conn):
        self.conn = conn

    def material(self, material_key):
        if not material_key:
            return None
        row = self.conn.execute(
            "SELECT * FROM materials WHERE material_key = ?", (material_key,)
        ).fetchone()
        if row is None:
            return None
        material = dict(row)
        material["label"] = _material_label(material)
        return material

    def speeds(self, material_key, operation, tool_material, tool_type=None):
        """Speed rows that fit this tool. The most specific tool type wins."""
        where, where_params, rank, rank_params = _tool_type_filter(tool_type)
        return self._all(f"""
            SELECT * FROM cutting_speeds
            WHERE material_key = ? AND operation = ? AND tool_material = ? AND {where}
            ORDER BY {rank}, {CONFIDENCE_RANK}, date_checked DESC
        """, [material_key, operation, tool_material, *where_params, *rank_params])

    def feeds(self, material_key, operation, tool_material, tool_type=None, diameter_in=None):
        """Feed rows that fit this tool.

        The most specific tool type wins, then rows with a diameter range
        over rows without one, then the best source, then the range that
        starts closest below the tool diameter. Passing None for
        diameter_in only matches rows without a diameter range.
        """
        where, where_params, rank, rank_params = _tool_type_filter(tool_type)
        return self._all(f"""
            SELECT * FROM feeds
            WHERE material_key = ? AND operation = ? AND tool_material = ? AND {where}
              AND (diameter_min_in IS NULL OR diameter_min_in <= ?)
              AND (diameter_max_in IS NULL OR diameter_max_in >= ?)
            ORDER BY {rank},
                     (diameter_min_in IS NULL AND diameter_max_in IS NULL),
                     {CONFIDENCE_RANK},
                     diameter_min_in DESC,
                     date_checked DESC
        """, [material_key, operation, tool_material, *where_params,
              diameter_in, diameter_in, *rank_params])

    def unit_power(self, material_key):
        return self._all(f"""
            SELECT * FROM unit_power WHERE material_key = ?
            ORDER BY {CONFIDENCE_RANK}, date_checked DESC
        """, (material_key,))

    def _all(self, sql, params):
        return [dict(r) for r in self.conn.execute(sql, params)]


def _tool_type_filter(tool_type):
    """SQL pieces that match rows for this tool type, its family, or any tool.

    Returns (where, where_params, rank, rank_params). rank sorts the exact
    type first, then the family, then rows that leave tool_type blank.
    """
    if tool_type is None:
        # Every row matched has a blank tool_type, so the rank is a constant.
        # (A bare number in ORDER BY would mean a column number to SQLite.)
        return "tool_type IS NULL", [], "NULL", []
    types = [tool_type]
    if tool_type in TOOL_FAMILIES:
        types.append(TOOL_FAMILIES[tool_type])
    placeholders = ", ".join("?" for _ in types)
    where = f"(tool_type IS NULL OR tool_type IN ({placeholders}))"
    rank = "CASE WHEN tool_type = ? THEN 0 WHEN tool_type IS NOT NULL THEN 1 ELSE 2 END"
    return where, types, rank, [tool_type]
