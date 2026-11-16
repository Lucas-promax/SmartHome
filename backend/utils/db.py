import sqlite3
import os
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_ROOT / "database" / "smarthome.db"
if os.environ.get("SMART_HOME_SIMULATOR") == "1":
    DB_PATH = BACKEND_ROOT / "database" / "smarthome.simulator.db"


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        # sqlite3's context manager commits/rolls back but does not close.
        # Explicit closing prevents leaked handles during serial updates on Windows.
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
