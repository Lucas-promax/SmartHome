import json
from typing import Any

from utils.db import get_connection, rows_to_dicts
from service.hardware_service import hardware
from utils.arduino_protocol import DEVICE_NAMES
from fastapi import HTTPException
from utils.time_utils import now_iso


ALERT_SETTINGS_KEY = "alert_settings"
DEFAULT_ALERT_SETTINGS = {
    "banner_enabled": True,
    "banner_stay_seconds": 5,
    "temperature_high": 30,
    "temperature_low": 16,
    "humidity_high": 75,
    "humidity_low": 30,
    "door_open_seconds": 300,
}


def get_home_status() -> dict[str, Any]:
    environment = sample_environment()
    devices = list_devices()
    settings = get_alert_settings()
    alerts = build_alerts(environment, devices, settings)
    events = list_recent_events(10)
    return {"environment": environment, "devices": devices, "hardware": hardware.status(), "alerts": alerts, "alert_settings": settings, "events": events, "timestamp": now_iso()}


def sample_environment() -> dict[str, Any]:
    # GET requests never create sensor samples; only incoming serial data does.
    return hardware.status()["environment"]


def list_devices() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM device_states ORDER BY device_id").fetchall()
    devices = [row for row in rows_to_dicts(rows) if row["device_id"] in DEVICE_NAMES]
    fresh = hardware.status()["fresh_devices"]
    for device in devices:
        device["state"] = json.loads(device.pop("state_json"))
        device["name"] = DEVICE_NAMES[device["device_id"]]
        device["fresh"] = fresh.get(device["device_id"], False)
    return devices


def get_alert_settings() -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT value_json FROM system_settings WHERE key = ?", (ALERT_SETTINGS_KEY,)).fetchone()
        if row is None:
            settings = DEFAULT_ALERT_SETTINGS.copy()
            conn.execute(
                """
                INSERT INTO system_settings (key, value_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (ALERT_SETTINGS_KEY, json.dumps(settings, ensure_ascii=False), now_iso()),
            )
            return settings
    try:
        saved = json.loads(row["value_json"] or "{}")
    except json.JSONDecodeError:
        saved = {}
    return {**DEFAULT_ALERT_SETTINGS, **saved}


def update_alert_settings(payload: dict[str, Any]) -> dict[str, Any]:
    settings = {**DEFAULT_ALERT_SETTINGS, **payload}
    if settings["temperature_low"] >= settings["temperature_high"]:
        raise ValueError("温度下限必须小于温度上限")
    if settings["humidity_low"] >= settings["humidity_high"]:
        raise ValueError("湿度下限必须小于湿度上限")
    settings["banner_stay_seconds"] = max(1, int(settings["banner_stay_seconds"]))
    settings["door_open_seconds"] = max(10, int(settings["door_open_seconds"]))
    updated_at = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO system_settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (ALERT_SETTINGS_KEY, json.dumps(settings, ensure_ascii=False), updated_at),
        )
    return {**settings, "updated_at": updated_at}


def build_alerts(environment: dict[str, Any], devices: list[dict[str, Any]], settings: dict[str, Any]) -> list[dict[str, str]]:
    if not settings.get("banner_enabled", True):
        return []
    alerts = []
    device_by_id = {device["device_id"]: device for device in devices}
    temperature = environment["temperature"]
    humidity = environment["humidity"]
    if not environment.get("fresh"):
        alerts.append({"type": "warning", "message": "硬件未连接或温湿度数据已过期，请在系统配置连接设备控制串口"})
    elif temperature is not None and temperature > settings["temperature_high"]:
        alerts.append({"type": "warning", "message": f"室内温度偏高：当前 {temperature}°C，已超过 {settings['temperature_high']}°C"})
    elif temperature is not None and temperature < settings["temperature_low"]:
        alerts.append({"type": "warning", "message": f"室内温度偏低：当前 {temperature}°C，低于 {settings['temperature_low']}°C"})
    if environment.get("fresh") and humidity is not None and humidity > settings["humidity_high"]:
        alerts.append({"type": "warning", "message": f"室内湿度偏高：当前 {humidity}%，已超过 {settings['humidity_high']}%"})
    elif environment.get("fresh") and humidity is not None and humidity < settings["humidity_low"]:
        alerts.append({"type": "warning", "message": f"室内湿度偏低：当前 {humidity}%，低于 {settings['humidity_low']}%"})
    door = device_by_id.get("door_main", {})
    if door.get("fresh") and door.get("state", {}).get("open") and is_device_open_too_long("door_main", int(settings["door_open_seconds"])):
        alerts.append({"type": "warning", "message": f"入户门打开超时警告：已超过 {_format_duration(int(settings['door_open_seconds']))}，请及时确认门锁状态"})
    return alerts


def _format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} 秒"
    minutes = seconds // 60
    if seconds % 60 == 0:
        return f"{minutes} 分钟"
    return f"{minutes} 分 {seconds % 60} 秒"


def is_device_open_too_long(device_id: str, seconds: int) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT updated_at FROM device_states WHERE device_id = ?", (device_id,)).fetchone()
    if row is None:
        return False
    from datetime import datetime

    try:
        updated_at = datetime.fromisoformat(row["updated_at"])
        current = datetime.fromisoformat(now_iso())
    except ValueError:
        return False
    return (current - updated_at).total_seconds() >= seconds


def list_recent_events(limit: int = 10) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), 100)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, level, module, message, created_at
            FROM operation_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    events = rows_to_dicts(rows)
    for event in events:
        event["timestamp"] = event.pop("created_at")
    return events


def control_device(device_id: str, action: str, value: Any, account_id: int | None = None) -> dict[str, Any]:
    return hardware.control(device_id, action, value)


def record_hardware_event(device_id: str, action: str, value: Any) -> dict[str, Any]:
    raise HTTPException(status_code=410, detail="硬件状态现由后端串口接收，不能通过 HTTP 模拟写入设备状态")


def describe_device_event(device_id: str, action: str, value: Any, source: str = "remote") -> str:
    source_text = "物理调节" if source == "hardware" else "远程控制"
    device_name = {
        "light_main": "灯光",
        "fan_main": "风扇",
        "door_main": "入户门",
        "garage_main": "车库门",
    }.get(device_id, device_id)
    action_text = {
        "turn_on": "开启",
        "turn_off": "关闭",
        "lock": "锁定",
        "unlock": "解锁",
        "open": "开启",
        "close": "关闭",
        "set_brightness": f"亮度调节至 {value}%",
        "set_speed": f"档位调节至 {value}",
        "set_level": f"设置灯光档位 {value}",
        "brighter": "灯光调亮一档",
        "darker": "灯光调暗一档",
    }.get(action, action)
    return f"{source_text}：{device_name}{action_text}"


def list_device_logs(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM device_logs ORDER BY id DESC LIMIT ?",
            (min(max(limit, 1), 500),),
        ).fetchall()
    logs = rows_to_dicts(rows)
    for log in logs:
        log["value"] = json.loads(log.pop("value_json") or "null")
    return logs

