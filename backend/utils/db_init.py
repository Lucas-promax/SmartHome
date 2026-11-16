import json

from utils.db import get_connection
from utils.security import hash_password
from utils.time_utils import now_iso


def init_db() -> None:
    """Create required tables and seed demo accounts/devices."""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS persons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'resident',
                face_image_path TEXT,
                face_vector_path TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS device_states (
                device_id TEXT PRIMARY KEY,
                device_type TEXT NOT NULL,
                name TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sensor_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                temperature REAL NOT NULL,
                humidity REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS device_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                action TEXT NOT NULL,
                value_json TEXT,
                source TEXT NOT NULL,
                account_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER,
                person_name TEXT,
                result TEXT NOT NULL,
                confidence REAL,
                snapshot_path TEXT,
                opened_door INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(person_id) REFERENCES persons(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS vision_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL,
                image_path TEXT,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                module TEXT NOT NULL,
                message TEXT NOT NULL,
                detail_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        seed_accounts(conn)
        seed_devices(conn)
        seed_settings(conn)


def seed_accounts(conn) -> None:
    created_at = now_iso()
    for username, password, role in (("admin", "admin123", "admin"), ("user", "user123", "user")):
        conn.execute(
            """
            INSERT OR IGNORE INTO accounts (username, password_hash, role, enabled, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (username, hash_password(password), role, created_at),
        )


def seed_devices(conn) -> None:
    updated_at = now_iso()
    devices = [
        ("light_main", "light", "主灯", {}),
        ("fan_main", "fan", "风扇", {}),
        ("door_main", "door", "主门", {}),
        ("garage_main", "garage", "车库门", {}),
    ]
    for device_id, device_type, name, state in devices:
        conn.execute(
            """
            INSERT OR IGNORE INTO device_states (device_id, device_type, name, state_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (device_id, device_type, name, json.dumps(state, ensure_ascii=False), updated_at),
        )


def seed_settings(conn) -> None:
    updated_at = now_iso()
    alert_settings = {
        "banner_enabled": True,
        "banner_stay_seconds": 5,
        "temperature_high": 30,
        "temperature_low": 16,
        "humidity_high": 75,
        "humidity_low": 30,
        "door_open_seconds": 300,
    }
    conn.execute(
        """
        INSERT OR IGNORE INTO system_settings (key, value_json, updated_at)
        VALUES (?, ?, ?)
        """,
        ("alert_settings", json.dumps(alert_settings, ensure_ascii=False), updated_at),
    )
