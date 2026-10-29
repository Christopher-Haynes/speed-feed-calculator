"""Tests for data_store.py: loading the CSVs and looking rows up."""

import pytest

import data_store
from data_store import DataError

BAD_ISO = "x,X,Y,Q,,,,,Test fixture,fake ref,2026-01-01,manufacturer"


def build(make_data_dir, tmp_path, **tables):
    db_path = tmp_path / "test.db"
    data_store.build_database(db_path, make_data_dir(**tables))
    return db_path


def count(db_path, table):
    conn = data_store.connect(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


# --- Loading ---------------------------------------------------------------

def test_real_data_folder_loads(tmp_path):
    db_path = tmp_path / "real.db"
    data_store.build_database(db_path)  # the project's own data/ folder
    for table in data_store.TABLES:
        assert count(db_path, table) >= 0


def test_fixture_data_loads(make_data_dir, tmp_path):
    db_path = build(make_data_dir, tmp_path)
    assert count(db_path, "materials") == 2
    assert count(db_path, "feeds") == 6


def test_bad_value_names_file_and_line(make_data_dir, tmp_path):
    with pytest.raises(DataError, match="materials.csv line 2"):
        build(make_data_dir, tmp_path, materials=[BAD_ISO])


def test_unquoted_comma_is_caught(make_data_dir, tmp_path):
    row = "x,X,Y,P,,,,,Some Book, 2nd ed.,p. 1,2026-01-01,handbook"
    with pytest.raises(DataError, match="more values than columns"):
        build(make_data_dir, tmp_path, materials=[row])


def test_bad_date(make_data_dir, tmp_path):
    row = "x,X,Y,P,,,,,Book,ref,10/27/2026,handbook"
    with pytest.raises(DataError, match="YYYY-MM-DD"):
        build(make_data_dir, tmp_path, materials=[row])


def test_missing_comma_is_caught(make_data_dir, tmp_path):
    row = "x,X,Y,P,,,,Book,ref,2026-01-01,handbook"
    with pytest.raises(DataError, match="fewer values than columns"):
        build(make_data_dir, tmp_path, materials=[row])


def test_text_where_a_number_belongs(make_data_dir, tmp_path):
    row = "alu-test,milling,carbide,,,fast,,,Book,ref,2026-01-01,handbook"
    with pytest.raises(DataError, match="sfm_rec must be a number"):
        build(make_data_dir, tmp_path, cutting_speeds=[row])


def test_unknown_material(make_data_dir, tmp_path):
    row = "nope,milling,carbide,,,800,,,Book,ref,2026-01-01,handbook"
    with pytest.raises(DataError, match="FOREIGN KEY"):
        build(make_data_dir, tmp_path, cutting_speeds=[row])


def test_speed_needs_a_value_or_a_range(make_data_dir, tmp_path):
    row = "alu-test,milling,carbide,,,,,,Book,ref,2026-01-01,handbook"
    with pytest.raises(DataError, match="CHECK"):
        build(make_data_dir, tmp_path, cutting_speeds=[row])


def test_missing_source(make_data_dir, tmp_path):
    row = "x,X,Y,P,,,,,,ref,2026-01-01,handbook"
    with pytest.raises(DataError, match="NOT NULL"):
        build(make_data_dir, tmp_path, materials=[row])


def test_low_above_recommended(make_data_dir, tmp_path):
    row = "alu-test,milling,carbide,,900,800,,,Book,ref,2026-01-01,handbook"
    with pytest.raises(DataError, match="CHECK"):
        build(make_data_dir, tmp_path, cutting_speeds=[row])


def test_header_mismatch(make_data_dir, tmp_path):
    data_dir = make_data_dir()
    (data_dir / "machines.csv").write_text("wrong,header\n", encoding="utf-8")
    with pytest.raises(DataError, match="header doesn't match"):
        data_store.build_database(tmp_path / "test.db", data_dir)


def test_failed_build_keeps_old_database(make_data_dir, tmp_path):
    db_path = build(make_data_dir, tmp_path)
    bad_dir = make_data_dir(name="bad", materials=[BAD_ISO])
    with pytest.raises(DataError):
        data_store.build_database(db_path, bad_dir)
    assert count(db_path, "materials") == 2
    assert list(tmp_path.glob("*.tmp")) == []


# --- Lookups ---------------------------------------------------------------

def test_speeds_best_source_first(lookup):
    rows = lookup.speeds("alu-test", "milling", "carbide")
    assert [r["confidence"] for r in rows] == ["manufacturer", "handbook"]


def test_speeds_match_tool_type(lookup):
    face = lookup.speeds("alu-test", "milling", "carbide", "face mill")
    assert [r["sfm_rec"] for r in face] == [1200, 800, 700]
    flat = lookup.speeds("alu-test", "milling", "carbide", "flat")
    assert [r["sfm_rec"] for r in flat] == [800, 700]


def test_feeds_prefer_the_specific_row(lookup):
    # flat row, then "end mill" family rows (closest size below first), then general
    rows = lookup.feeds("alu-test", "milling", "carbide", "flat", 0.5)
    assert [r["feed_rec"] for r in rows] == [0.005, 0.0045, 0.004, 0.003]


def test_feeds_outside_diameter_range_fall_back(lookup):
    rows = lookup.feeds("alu-test", "milling", "carbide", "flat", 1.0)
    assert [r["feed_rec"] for r in rows] == [0.0045, 0.003]


def test_ball_mill_uses_end_mill_rows(lookup):
    rows = lookup.feeds("alu-test", "milling", "carbide", "ball", 0.5)
    assert [r["feed_rec"] for r in rows] == [0.0045, 0.004, 0.003]


def test_face_mill_skips_end_mill_rows(lookup):
    rows = lookup.feeds("alu-test", "milling", "carbide", "face mill", 0.5)
    assert [r["feed_rec"] for r in rows] == [0.003]


def test_turning_feeds_without_tool_type(lookup):
    rows = lookup.feeds("alu-test", "turning", "carbide")
    assert [r["feed_rec"] for r in rows] == [0.008]


def test_material_without_condition(make_data_dir, tmp_path):
    row = "plain,Plain alloy,,N,,,,,Book,ref,2026-01-01,handbook"
    db_path = build(make_data_dir, tmp_path, materials=[row], cutting_speeds=[], feeds=[],
                    unit_power=[])
    conn = data_store.connect(db_path)
    try:
        assert data_store.DataLookup(conn).material("plain")["label"] == "Plain alloy"
    finally:
        conn.close()


def test_material_lookup(lookup):
    assert lookup.material("hard-test")["label"] == "Test steel Hardened (50–55 HRC)"
    assert lookup.material("missing") is None
    assert lookup.material("") is None


def test_material_groups_in_iso_order(lookup):
    groups = data_store.list_material_groups(lookup.conn)
    assert [g["code"] for g in groups] == ["N", "H"]


def test_machines_by_type(lookup):
    assert [m["name"] for m in data_store.list_machines(lookup.conn, "lathe")] == ["Test Lathe"]


def test_list_sources(lookup):
    sources = data_store.list_sources(lookup.conn)
    assert {s["source"] for s in sources} == {"Test fixture", "Other fixture"}
