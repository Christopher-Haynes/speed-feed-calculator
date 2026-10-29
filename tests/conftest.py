"""Shared test fixtures.

The CSV rows below are FAKE numbers made up to test the code. They are not
cutting data or machine specs and must never be copied into data/.
"""

import shutil
from pathlib import Path

import pytest

import data_store
from app import create_app

ROOT = Path(__file__).resolve().parent.parent
FAKE = "Test fixture,fake ref,2026-01-01"

FIXTURE_ROWS = {
    "materials": [
        f"alu-test,Test alloy,T6,N,,,,,{FAKE},manufacturer",
        f"hard-test,Test steel,Hardened,H,50,55,HRC,,{FAKE},manufacturer",
    ],
    "machines": [
        f"test-mill,Test Mill,mill,10000,20,500,CAT40,,{FAKE},manufacturer",
        f"test-lathe,Test Lathe,lathe,4000,15,,,,{FAKE},manufacturer",
    ],
    "cutting_speeds": [
        f"alu-test,milling,carbide,,600,800,1000,,{FAKE},manufacturer",
        "alu-test,milling,carbide,,,700,,,Other fixture,fake ref,2026-01-01,handbook",
        f"alu-test,milling,carbide,face mill,,1200,,,{FAKE},manufacturer",
        f"alu-test,drilling,carbide,drill,250,,350,,{FAKE},manufacturer",  # range only
        f"alu-test,turning,carbide,,400,500,600,,{FAKE},manufacturer",
    ],
    "feeds": [
        f"alu-test,milling,carbide,,,,0.002,0.003,0.004,,{FAKE},manufacturer",
        f"alu-test,milling,carbide,flat,0.25,0.5,0.004,0.005,0.006,,{FAKE},manufacturer",
        f"alu-test,milling,carbide,end mill,0.25,0.5,,0.004,,,{FAKE},manufacturer",
        f"alu-test,milling,carbide,end mill,0.5,1.0,,0.0045,,,{FAKE},manufacturer",
        f"alu-test,drilling,carbide,drill,,,,0.004,,,{FAKE},manufacturer",
        f"alu-test,turning,carbide,,,,0.006,0.008,0.010,,{FAKE},manufacturer",
    ],
    "unit_power": [
        f"alu-test,0.3,,{FAKE},manufacturer",
    ],
}


def write_data_dir(target, rows):
    """Make a data folder with the real schema and headers, plus test rows."""
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "data" / "schema.sql", target / "schema.sql")
    for table in data_store.TABLES:
        real_csv = (ROOT / "data" / f"{table}.csv").read_text(encoding="utf-8")
        header = real_csv.splitlines()[0]
        lines = [header] + rows.get(table, [])
        (target / f"{table}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


@pytest.fixture
def make_data_dir(tmp_path):
    """make_data_dir(materials=[...]) swaps in different rows for a table."""
    def make(name="data", **tables):
        return write_data_dir(tmp_path / name, {**FIXTURE_ROWS, **tables})
    return make


@pytest.fixture
def lookup(make_data_dir, tmp_path):
    db_path = tmp_path / "lookup.db"
    data_store.build_database(db_path, make_data_dir())
    conn = data_store.connect(db_path)
    yield data_store.DataLookup(conn)
    conn.close()


@pytest.fixture
def app(make_data_dir, tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "app.db"),
        "REPORTS_DATABASE": str(tmp_path / "reports.db"),
        "DATA_DIR": str(make_data_dir()),
    })


@pytest.fixture
def client(app):
    return app.test_client()
