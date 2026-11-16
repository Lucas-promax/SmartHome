import json
from datetime import datetime, timedelta
from typing import Any

from utils.db import get_connection, rows_to_dicts


DEFAULT_WINDOW_HOURS = 6
MAX_BUCKETS = 240


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _default_range(after: str | None, before: str | None) -> tuple[datetime, datetime]:
    before_dt = _parse_time(before) or datetime.now().astimezone()
    after_dt = _parse_time(after) or (before_dt - timedelta(hours=DEFAULT_WINDOW_HOURS))
    if after_dt >= before_dt:
        after_dt = before_dt - timedelta(hours=DEFAULT_WINDOW_HOURS)
    return after_dt, before_dt


def _choose_bucket_seconds(after: datetime, before: datetime, requested: int | None = None) -> int:
    if requested:
        return max(10, int(requested))
    span = max(1, int((before - after).total_seconds()))
    if span <= 30 * 60:
        return 10
    if span <= 12 * 60 * 60:
        return 60
    if span <= 3 * 24 * 60 * 60:
        return 5 * 60
    return 60 * 60


def _bucket_start(value: str, bucket_seconds: int) -> str:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    timestamp = int(dt.timestamp())
    bucket_timestamp = timestamp - (timestamp % bucket_seconds)
    return datetime.fromtimestamp(bucket_timestamp, tz=dt.tzinfo).isoformat(timespec="seconds")


def _parse_brightness_value(value_json: str | None) -> int | None:
    try:
        value = json.loads(value_json or "null")
    except json.JSONDecodeError:
        return None
    if isinstance(value, dict):
        value = value.get("brightness")
    try:
        brightness = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(255, brightness))


def _range_sql(after: datetime, before: datetime) -> tuple[str, str]:
    return after.astimezone().isoformat(timespec="seconds"), before.astimezone().isoformat(timespec="seconds")


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def summary() -> dict[str, Any]:
    with get_connection() as conn:
        persons = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
        device_logs = conn.execute("SELECT COUNT(*) FROM device_logs").fetchone()[0]
        vision_logs = conn.execute("SELECT COUNT(*) FROM vision_logs").fetchone()[0]
        access_logs = conn.execute("SELECT COUNT(*) FROM access_logs").fetchone()[0]
    return {
        "persons": persons,
        "device_logs": device_logs,
        "vision_logs": vision_logs,
        "access_logs": access_logs,
    }


def sensors(after: str | None = None, before: str | None = None, bucket_seconds: int | None = None) -> dict[str, Any]:
    """Return real environment series aggregated from sensor_records."""
    after_dt, before_dt = _default_range(after, before)
    bucket = _choose_bucket_seconds(after_dt, before_dt, bucket_seconds)
    start, end = _range_sql(after_dt, before_dt)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM sensor_records
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY created_at ASC
            """,
            (start, end),
        ).fetchall()
    records = rows_to_dicts(rows)
    buckets: dict[str, dict[str, Any]] = {}
    for row in records:
        key = _bucket_start(row["created_at"], bucket)
        item = buckets.setdefault(key, {"time": key, "temperatures": [], "humidity_values": [], "count": 0})
        item["temperatures"].append(float(row["temperature"]))
        item["humidity_values"].append(float(row["humidity"]))
        item["count"] += 1
    series = [
        {
            "time": item["time"],
            "temperature": _avg(item["temperatures"]),
            "humidity": _avg(item["humidity_values"]),
            "count": item["count"],
        }
        for item in buckets.values()
    ]
    temperatures = [float(row["temperature"]) for row in records]
    humidity = [float(row["humidity"]) for row in records]
    return {
        "series": series[-MAX_BUCKETS:],
        "raw_count": len(records),
        "bucket_seconds": bucket,
        "range": {"after": start, "before": end},
        "temperature_avg": round(sum(temperatures) / len(temperatures), 1) if temperatures else None,
        "humidity_avg": round(sum(humidity) / len(humidity), 1) if humidity else None,
        "temperature_min": round(min(temperatures), 1) if temperatures else None,
        "temperature_max": round(max(temperatures), 1) if temperatures else None,
        "humidity_min": round(min(humidity), 1) if humidity else None,
        "humidity_max": round(max(humidity), 1) if humidity else None,
        "high_temperature_count": len([value for value in temperatures if value >= 30]),
    }


def devices(after: str | None = None, before: str | None = None, bucket_seconds: int | None = None) -> dict[str, Any]:
    """Aggregate device state and operation logs for charts."""
    after_dt, before_dt = _default_range(after, before)
    bucket = _choose_bucket_seconds(after_dt, before_dt, bucket_seconds)
    start, end = _range_sql(after_dt, before_dt)
    with get_connection() as conn:
        device_rows = conn.execute("SELECT * FROM device_states ORDER BY device_id").fetchall()
        log_rows = conn.execute(
            """
            SELECT * FROM device_logs
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY created_at ASC
            """,
            (start, end),
        ).fetchall()
    states = [row for row in rows_to_dicts(device_rows) if row['device_id'] != 'window_main']
    for state in states:
        state["state"] = json.loads(state.pop("state_json"))
    logs = rows_to_dicts(log_rows)
    counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    timeline: dict[str, dict[str, Any]] = {}
    brightness_series: list[dict[str, Any]] = []
    for log in logs:
        counts[log["device_id"]] = counts.get(log["device_id"], 0) + 1
        source_counts[log["source"]] = source_counts.get(log["source"], 0) + 1
        key = _bucket_start(log["created_at"], bucket)
        item = timeline.setdefault(key, {"time": key, "door_lock": 0, "door_unlock": 0, "window_open": 0, "window_close": 0, "light": 0, "fan": 0})
        if log["device_id"] == "door_main" and log["action"] in {"lock", "close"}:
            item["door_lock"] += 1
        elif log["device_id"] == "door_main" and log["action"] in {"unlock", "open"}:
            item["door_unlock"] += 1
        elif log["device_id"] == "garage_main" and log["action"] == "open":
            item["window_open"] += 1
        elif log["device_id"] == "garage_main" and log["action"] == "close":
            item["window_close"] += 1
        elif log["device_id"] == "light_main":
            item["light"] += 1
        elif log["device_id"] == "fan_main":
            item["fan"] += 1
        if log["device_id"] == "light_main" and log["action"] in {"set_brightness", "state_report"}:
            brightness = _parse_brightness_value(log["value_json"])
            if brightness is not None:
                brightness_series.append({"time": log["created_at"], "value": brightness, "source": log["source"]})
    return {
        "states": states,
        "operation_counts": counts,
        "source_counts": source_counts,
        "timeline": list(timeline.values())[-MAX_BUCKETS:],
        "brightness_series": brightness_series[-MAX_BUCKETS:],
        "recent_logs": list(reversed(logs))[:20],
        "bucket_seconds": bucket,
        "range": {"after": start, "before": end},
    }


def access(after: str | None = None, before: str | None = None, bucket_seconds: int | None = None) -> dict[str, Any]:
    """Aggregate access logs while keeping empty data stable for frontend rendering."""
    after_dt, before_dt = _default_range(after, before)
    bucket = _choose_bucket_seconds(after_dt, before_dt, bucket_seconds)
    start, end = _range_sql(after_dt, before_dt)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM access_logs
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY created_at ASC
            """,
            (start, end),
        ).fetchall()
    logs = rows_to_dicts(rows)
    granted = len([row for row in logs if row["result"] in {"granted", "rfid_granted"}])
    denied = len(logs) - granted
    person_counts: dict[str, int] = {}
    timeline: dict[str, dict[str, Any]] = {}
    for row in logs:
        person_name = row["person_name"] or "未知人员"
        person_counts[person_name] = person_counts.get(person_name, 0) + 1
        key = _bucket_start(row["created_at"], bucket)
        item = timeline.setdefault(key, {"time": key, "granted": 0, "denied": 0, "unknown": 0})
        if row["result"] in {"granted", "rfid_granted"}:
            item["granted"] += 1
        elif row["result"] == "unknown":
            item["unknown"] += 1
        else:
            item["denied"] += 1
    return {"granted": granted, "denied": denied, "person_counts": person_counts, "timeline": list(timeline.values())[-MAX_BUCKETS:], "recent_logs": list(reversed(logs))[:20], "bucket_seconds": bucket}


def vision(after: str | None = None, before: str | None = None, bucket_seconds: int | None = None) -> dict[str, Any]:
    """Aggregate vision logs by mode for the analysis page."""
    after_dt, before_dt = _default_range(after, before)
    bucket = _choose_bucket_seconds(after_dt, before_dt, bucket_seconds)
    start, end = _range_sql(after_dt, before_dt)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM vision_logs
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY created_at ASC
            """,
            (start, end),
        ).fetchall()
    logs = rows_to_dicts(rows)
    mode_counts: dict[str, int] = {}
    object_counts: dict[str, int] = {}
    timeline: dict[str, dict[str, Any]] = {}
    for row in logs:
        mode_counts[row["mode"]] = mode_counts.get(row["mode"], 0) + 1
        key = _bucket_start(row["created_at"], bucket)
        item = timeline.setdefault(key, {"time": key, "face": 0, "object": 0, "total": 0})
        item["total"] += 1
        if row["mode"] == "face":
            item["face"] += 1
        else:
            item["object"] += 1
        try:
            result = json.loads(row["result_json"] or "{}")
        except json.JSONDecodeError:
            result = {}
        detections = result.get("detections") if isinstance(result, dict) else None
        if isinstance(detections, list):
            for det in detections:
                label = det.get("label") or det.get("class_name") or det.get("name") or "未知目标"
                object_counts[label] = object_counts.get(label, 0) + 1
    return {"mode_counts": mode_counts, "object_counts": object_counts, "timeline": list(timeline.values())[-MAX_BUCKETS:], "recent_logs": list(reversed(logs))[:20], "bucket_seconds": bucket}


def overview(after: str | None = None, before: str | None = None, bucket_seconds: int | None = None) -> dict[str, Any]:
    sensor_data = sensors(after, before, bucket_seconds)
    device_data = devices(after, before, bucket_seconds)
    access_data = access(after, before, bucket_seconds)
    vision_data = vision(after, before, bucket_seconds)
    return {
        "summary": summary(),
        "sensors": sensor_data,
        "devices": device_data,
        "access": access_data,
        "vision": vision_data,
        "bucket_seconds": sensor_data["bucket_seconds"],
        "range": sensor_data["range"],
    }
