import re
import shutil
from pathlib import Path
from typing import Any

from utils.db import get_connection, row_to_dict, rows_to_dicts
from utils.time_utils import now_iso


BACKEND_ROOT = Path(__file__).resolve().parents[1]
FACE_INFO_DIR = BACKEND_ROOT / "database" / "face_info"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def list_persons() -> list[dict[str, Any]]:
    sync_face_info_persons()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM persons ORDER BY id DESC").fetchall()
    persons = rows_to_dicts(rows)
    return [_normalize_person(person) for person in persons]


def create_person(name: str, role: str, enabled: bool) -> dict[str, Any]:
    ts = now_iso()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO persons (name, role, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, role, int(enabled), ts, ts),
        )
        person_id = cursor.lastrowid
        person = row_to_dict(conn.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone())
    return _normalize_person(person)


def create_person_with_face(name: str, role: str, enabled: bool, filename: str, content: bytes) -> dict[str, Any]:
    suffix = Path(filename or "0.jpg").suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        suffix = ".jpg"
    person = create_person(name, role, enabled)
    folder_name = f"{int(person['id']):02d}_{_safe_folder_name(name)}"
    person_dir = FACE_INFO_DIR / folder_name
    person_dir.mkdir(parents=True, exist_ok=True)
    image_path = person_dir / f"0{suffix}"
    image_path.write_bytes(content)
    rel_path = image_path.relative_to(BACKEND_ROOT).as_posix()
    return update_person(int(person["id"]), {"face_image_path": rel_path}) or person


def update_person(person_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {"name", "role", "enabled", "face_image_path", "face_vector_path"}
    updates = {k: v for k, v in changes.items() if k in allowed and v is not None}
    if "enabled" in updates:
        updates["enabled"] = int(updates["enabled"])
    updates["updated_at"] = now_iso()
    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [person_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE persons SET {assignments} WHERE id = ?", values)
        person = row_to_dict(conn.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone())
    if person:
        return _normalize_person(person)
    return None


def delete_person(person_id: int) -> bool:
    return revoke_person(person_id) is not None


def revoke_person(person_id: int) -> dict[str, Any] | None:
    return update_person(person_id, {"enabled": False, "role": "blocked"})


def hard_delete_person(person_id: int) -> dict[str, Any] | None:
    sync_face_info_persons()
    with get_connection() as conn:
        person = row_to_dict(conn.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone())
        if not person:
            return None
        conn.execute("UPDATE access_logs SET person_id = NULL WHERE person_id = ?", (person_id,))
        conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))

    face_dir = _face_dir_from_path(person.get("face_image_path"))
    if face_dir and face_dir.exists() and face_dir.is_dir():
        shutil.rmtree(face_dir, ignore_errors=True)
    return _normalize_person(person)


def restore_person(person_id: int, role: str = "resident") -> dict[str, Any] | None:
    if role not in {"resident", "guest"}:
        role = "resident"
    return update_person(person_id, {"enabled": True, "role": role})


def get_face_image_path(person_id: int) -> Path | None:
    sync_face_info_persons()
    with get_connection() as conn:
        row = conn.execute("SELECT face_image_path FROM persons WHERE id = ?", (person_id,)).fetchone()
    if not row or not row["face_image_path"]:
        return None
    path = BACKEND_ROOT / row["face_image_path"]
    if not path.exists() or not path.is_file():
        return None
    return path


def list_authorized_face_references() -> list[dict[str, Any]]:
    sync_face_info_persons()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM persons
            WHERE enabled = 1
              AND role != 'blocked'
              AND face_image_path IS NOT NULL
            ORDER BY id
            """
        ).fetchall()
    return [_normalize_person(row_to_dict(row)) for row in rows]


def list_face_references() -> list[dict[str, Any]]:
    sync_face_info_persons()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM persons
            WHERE face_image_path IS NOT NULL
            ORDER BY id
            """
        ).fetchall()
    return [_normalize_person(row_to_dict(row)) for row in rows]


def sync_face_info_persons() -> None:
    FACE_INFO_DIR.mkdir(parents=True, exist_ok=True)
    ts = now_iso()
    with get_connection() as conn:
        existing_rows = conn.execute("SELECT id, face_image_path FROM persons").fetchall()
        existing_dirs = set()
        for row in existing_rows:
            face_image_path = row["face_image_path"]
            if face_image_path:
                parts = Path(face_image_path).parts
                if "face_info" in parts:
                    index = parts.index("face_info")
                    if index + 1 < len(parts):
                        existing_dirs.add(parts[index + 1])

        for person_dir in sorted(path for path in FACE_INFO_DIR.iterdir() if path.is_dir()):
            if person_dir.name in existing_dirs:
                continue
            standard_image = _find_standard_image(person_dir)
            if standard_image is None:
                continue
            name = _display_face_name(person_dir.name)
            rel_path = standard_image.relative_to(BACKEND_ROOT).as_posix()
            conn.execute(
                """
                INSERT INTO persons (name, role, face_image_path, enabled, created_at, updated_at)
                VALUES (?, 'resident', ?, 1, ?, ?)
                """,
                (name, rel_path, ts, ts),
            )


def list_access_logs(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM access_logs ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 500),)).fetchall()
    logs = rows_to_dicts(rows)
    for log in logs:
        log["opened_door"] = bool(log["opened_door"])
    return logs


def _normalize_person(person: dict[str, Any]) -> dict[str, Any]:
    person["enabled"] = bool(person["enabled"])
    person["authorized"] = person["enabled"] and person.get("role") != "blocked"
    person["face_image_url"] = f"/api/persons/{person['id']}/face-image" if person.get("face_image_path") else None
    return person


def _find_standard_image(person_dir: Path) -> Path | None:
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        image = person_dir / f"0{suffix}"
        if image.exists():
            return image
    return None


def _display_face_name(folder_name: str) -> str:
    return folder_name.split("_", 1)[1] if "_" in folder_name else folder_name


def _safe_folder_name(name: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_\-]+", "_", name.strip())
    return safe.strip("_") or "person"


def _face_dir_from_path(face_image_path: str | None) -> Path | None:
    if not face_image_path:
        return None
    path = (BACKEND_ROOT / face_image_path).resolve()
    try:
        path.relative_to(FACE_INFO_DIR.resolve())
    except ValueError:
        return None
    return path.parent
