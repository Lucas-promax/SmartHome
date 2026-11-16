import json
from typing import Any

from utils.db import get_connection, rows_to_dicts
from utils.time_utils import now_iso


SOURCE_TABLES = {
    "operation": "operation_logs",
    "device": "device_logs",
    "access": "access_logs",
    "vision": "vision_logs",
}

DEVICE_NAMES = {
    "light_main": "灯光",
    "fan_main": "风扇",
    "door_main": "入户门",
    "window_main": "窗户",
    "garage_main": "车库门",
}

DEVICE_TYPES = {
    "light_main": "light",
    "fan_main": "fan",
    "door_main": "door",
    "window_main": "window",
    "garage_main": "garage",
}

ACTION_TEXT = {
    "turn_on": "开启",
    "turn_off": "关闭",
    "lock": "锁定",
    "unlock": "解锁",
    "open": "开启",
    "close": "关闭",
    "set_brightness": "调节亮度",
    "set_speed": "调节档位",
    "set_level": "设置灯光档位",
    "brighter": "调亮一档",
    "darker": "调暗一档",
    "state_report": "板端状态变化",
}

VISION_MODE_LABELS = {
    "general": "通用识别",
    "fire_drone": "物体识别",
    "face": "人脸识别",
}


def add_operation_log(module: str, message: str, level: str = "info", detail: dict[str, Any] | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO operation_logs (level, module, message, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (level, module, message, json.dumps(detail, ensure_ascii=False) if detail else None, now_iso()),
        )


def list_operation_logs(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM operation_logs ORDER BY id DESC LIMIT ?",
            (min(max(limit, 1), 500),),
        ).fetchall()
    logs = rows_to_dicts(rows)
    for log in logs:
        log["detail"] = json.loads(log.pop("detail_json") or "null")
    return logs


def list_logs(filters: dict[str, Any]) -> dict[str, Any]:
    limit = _clamp_int(filters.get("limit"), 100, 1, 1000)
    offset = _clamp_int(filters.get("offset"), 0, 0, 1000000)
    all_logs: list[dict[str, Any]] = []

    with get_connection() as conn:
        if _source_enabled(filters, "operation"):
            rows = conn.execute("SELECT * FROM operation_logs ORDER BY id DESC LIMIT 1000").fetchall()
            all_logs.extend(_normalize_operation_log(row) for row in rows)
        if _source_enabled(filters, "device"):
            rows = conn.execute("SELECT * FROM device_logs ORDER BY id DESC LIMIT 1000").fetchall()
            all_logs.extend(_normalize_device_log(row) for row in rows)
        if _source_enabled(filters, "access"):
            rows = conn.execute("SELECT * FROM access_logs ORDER BY id DESC LIMIT 1000").fetchall()
            all_logs.extend(_normalize_access_log(row) for row in rows)
        if _source_enabled(filters, "vision"):
            rows = conn.execute("SELECT * FROM vision_logs ORDER BY id DESC LIMIT 1000").fetchall()
            all_logs.extend(_normalize_vision_log(row) for row in rows)

    filtered = [log for log in all_logs if _matches_filters(log, filters)]
    filtered.sort(key=lambda item: item["timestamp"], reverse=True)
    return {
        "items": filtered[offset: offset + limit],
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
    }


def cleanup_logs(filters: dict[str, Any]) -> dict[str, int]:
    delete_ids: dict[str, list[int]] = {source: [] for source in SOURCE_TABLES}
    logs = list_logs({**filters, "limit": 1000, "offset": 0})["items"]
    for log in logs:
        source = log["source"]
        if source in delete_ids:
            delete_ids[source].append(int(log["raw_id"]))

    deleted: dict[str, int] = {source: 0 for source in SOURCE_TABLES}
    with get_connection() as conn:
        for source, ids in delete_ids.items():
            if not ids:
                continue
            placeholders = ",".join("?" for _ in ids)
            table = SOURCE_TABLES[source]
            cursor = conn.execute(f"DELETE FROM {table} WHERE id IN ({placeholders})", ids)
            deleted[source] = cursor.rowcount
    deleted["total"] = sum(deleted.values())
    return deleted


def _source_enabled(filters: dict[str, Any], source: str) -> bool:
    selected = filters.get("source")
    return not selected or selected == source


def _normalize_operation_log(row) -> dict[str, Any]:
    detail = json.loads(row["detail_json"] or "null")
    return {
        "id": f"operation-{row['id']}",
        "raw_id": row["id"],
        "source": "operation",
        "type": row["module"],
        "level": row["level"],
        "message": row["message"],
        "timestamp": row["created_at"],
        "detail": detail,
    }


def _normalize_device_log(row) -> dict[str, Any]:
    value = json.loads(row["value_json"] or "null")
    device_name = DEVICE_NAMES.get(row["device_id"], row["device_id"])
    action_text = ACTION_TEXT.get(row["action"], row["action"])
    source_text = "板端上报" if row["source"] == "hardware" else "人脸控制" if row["source"] == "face" else "远程控制"
    suffix = f"：{value}" if value is not None and row["action"] not in {"turn_on", "turn_off", "lock", "unlock", "open", "close"} else ""
    return {
        "id": f"device-{row['id']}",
        "raw_id": row["id"],
        "source": "device",
        "type": DEVICE_TYPES.get(row["device_id"], "device"),
        "level": "info",
        "message": f"{source_text}：{device_name}{action_text}{suffix}",
        "timestamp": row["created_at"],
        "detail": {"device_id": row["device_id"], "action": row["action"], "value": value, "source": row["source"]},
    }


def _normalize_access_log(row) -> dict[str, Any]:
    result = row["result"]
    person_name = row["person_name"] or "未知人员"
    confidence = row["confidence"]
    opened_door = bool(row["opened_door"])
    is_rfid = result.startswith("rfid_")
    level = "info" if opened_door or result == "rfid_granted" else "warning"
    score_text = f"，相似度 {confidence:.2f}" if confidence is not None else ""
    door_text = "，板端报告开门（无机械反馈）" if opened_door else "，开门未确认"
    if is_rfid:
        door_text = "，板端授权通过并发出开门动作" if result == "rfid_granted" else "，板端拒绝授权"
    return {
        "id": f"access-{row['id']}",
        "raw_id": row["id"],
        "source": "access",
        "type": "rfid" if is_rfid else "face",
        "level": level,
        "message": f"{'RFID' if is_rfid else '人脸识别'}：{person_name}，结果 {result}{score_text}{door_text}",
        "timestamp": row["created_at"],
        "detail": {"person_id": row["person_id"], "result": result, "confidence": confidence, "opened_door": opened_door},
    }


def _normalize_vision_log(row) -> dict[str, Any]:
    result = json.loads(row["result_json"] or "{}")
    mode = row["mode"]
    detections = result.get("detections") or []
    if detections:
        names = "、".join(item.get("name") or item.get("class") or "目标" for item in detections[:3])
        message = f"{VISION_MODE_LABELS.get(mode, mode)}：识别到 {len(detections)} 个目标（{names}）"
        level = "warning" if any((item.get("name") in {"无人机", "灭火器"} or item.get("class") in {"drone", "fire_extinguisher"}) for item in detections) else "info"
    else:
        message = f"{VISION_MODE_LABELS.get(mode, mode)}：未识别到目标"
        level = "info"
    return {
        "id": f"vision-{row['id']}",
        "raw_id": row["id"],
        "source": "vision",
        "type": "yolo" if mode != "face" else "face",
        "level": level,
        "message": message,
        "timestamp": row["created_at"],
        "detail": {"mode": mode, "image_path": row["image_path"], "result": result},
    }


def _matches_filters(log: dict[str, Any], filters: dict[str, Any]) -> bool:
    log_type = filters.get("log_type")
    level = filters.get("level")
    keyword = (filters.get("keyword") or "").strip().lower()
    after = filters.get("after")
    before = filters.get("before")
    if log_type and log["type"] != log_type:
        return False
    if level and log["level"] != level:
        return False
    if after and log["timestamp"] < after:
        return False
    if before and log["timestamp"] > before:
        return False
    if keyword:
        haystack = f"{log['message']} {log['type']} {log['source']} {json.dumps(log.get('detail'), ensure_ascii=False)}".lower()
        if keyword not in haystack:
            return False
    return True


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)
