"""Stores "report a bad number" submissions.

Reports live in their own SQLite file, apart from the cutting data, which
is rebuilt from the CSV files every time the app starts.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id         INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    operation  TEXT,
    context    TEXT,
    message    TEXT NOT NULL,
    contact    TEXT
)
"""


def init(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def save(db_path, operation, context, message, contact):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO reports (created_at, operation, context, message, contact) "
            "VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),
             operation, context, message, contact),
        )
        conn.commit()
    finally:
        conn.close()


def list_all(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM reports ORDER BY id DESC")]
    finally:
        conn.close()
