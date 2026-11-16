from __future__ import annotations

from typing import Any, Literal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from service import analysis_service, home_service, log_service, person_service


CLIENT_TOOL_NAMES = {"set_theme"}
DANGEROUS_TOOL_NAMES = {"set_person_authorization", "cleanup_logs"}


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ControlArgs(ToolArgs):
    device_id: Literal["light_main", "fan_main", "door_main", "garage_main"]
    action: Literal["turn_on", "turn_off", "set_level", "brighter", "darker", "open", "close"]
    value: Literal["low", "middle", "high"] | None = None

    @model_validator(mode="after")
    def check_action(self):
        allowed = {"light_main": {"turn_on", "turn_off", "set_level", "brighter", "darker"},
                   "fan_main": {"turn_on", "turn_off"},
                   "door_main": {"open", "close"}, "garage_main": {"open", "close"}}
        if self.action not in allowed[self.device_id]:
            raise ValueError("此设备不支持该动作")
        if (self.action == "set_level") != (self.value is not None):
            raise ValueError("仅 set_level 必须提供 low/middle/high，其余动作不接受 value")
        return self


class TimeArgs(ToolArgs):
    after: str | None = Field(None, description="ISO 时间起点，含时区，例如 2026-11-15T00:00:00+08:00")
    before: str | None = Field(None, description="ISO 时间终点，含时区")

    @field_validator("after", "before")
    @classmethod
    def check_time(cls, value):
        if value is not None and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("时间必须包含时区")
        return value

    @model_validator(mode="after")
    def check_range(self):
        if self.after and self.before and datetime.fromisoformat(self.after.replace("Z", "+00:00")) >= datetime.fromisoformat(self.before.replace("Z", "+00:00")):
            raise ValueError("时间起点必须早于终点")
        return self


class AnalysisArgs(TimeArgs):
    bucket_seconds: int | None = Field(None, ge=10)


class ThemeArgs(ToolArgs):
    theme: Literal["light", "dark"]


class AuthorizationArgs(ToolArgs):
    person_id: int = Field(gt=0)
    action: Literal["revoke", "restore"]
    role: Literal["resident", "guest"] = "resident"


class LogFilters(TimeArgs):
    source: Literal["operation", "device", "access", "vision"] | None = None
    log_type: str | None = None
    level: Literal["info", "warning", "error"] | None = None
    keyword: str | None = None


class ListLogsArgs(LogFilters):
    limit: int = Field(20, ge=1, le=100)


TOOL_ARGUMENT_MODELS = {
    "get_home_status": ToolArgs, "control_device": ControlArgs,
    "get_data_analysis": AnalysisArgs, "set_theme": ThemeArgs,
    "list_persons": ToolArgs, "set_person_authorization": AuthorizationArgs,
    "list_logs": ListLogsArgs, "cleanup_logs": LogFilters,
}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": TOOL_ARGUMENT_MODELS[name].model_json_schema(),
    }}
    for name, description in [
        ('get_home_status', '读取智能家居首页状态，包括温湿度、设备状态、告警和最近事件。'),
        ('control_device', '通过 Arduino 串口控制主灯、风扇、主门和车库门；等待板端状态。离线不能控制。风扇每两秒会被板端温控覆盖，门无机械反馈且不会自动关闭。AI识别功能暂不支持操作。'),
        ('get_data_analysis', '从数据库读取真实数据分析结果，包含温湿度、设备、门禁、视觉识别和汇总统计。'),
        ('set_theme', '切换前端白天/夜晚模式。该工具由浏览器本地执行，保存到 localStorage。'),
        ('list_persons', '读取全部人员及人脸授权状态，包含未授权人员。此授权不修改 Arduino 中固定的 RFID 卡片授权。'),
        ('set_person_authorization', '修改人员的人脸门禁授权，不影响板端 RFID 卡片。先查询人员 ID，再提出操作；前端会弹窗，用户确认后后端执行。'),
        ('list_logs', '查询系统日志，支持来源、类型、级别、关键词、时间范围和数量限制。'),
        ('cleanup_logs', '清理系统日志，每次最多处理匹配的 1000 条。先说明筛选范围并提出操作，前端弹窗确认后执行；无筛选条件会匹配全部来源。'),
    ]
]


def validate_tool_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOL_ARGUMENT_MODELS:
        raise ValueError(f"未知工具：{name}")
    return TOOL_ARGUMENT_MODELS[name].model_validate(arguments).model_dump(exclude_none=True)


def get_tool_definition(name: str) -> dict[str, Any] | None:
    for tool in TOOL_DEFINITIONS:
        if tool.get("function", {}).get("name") == name:
            return tool
    return None


def is_client_tool(name: str) -> bool:
    return name in CLIENT_TOOL_NAMES


def is_dangerous_tool(name: str) -> bool:
    return name in DANGEROUS_TOOL_NAMES


def describe_tool_call(name: str, arguments: dict[str, Any]) -> str:
    if name == "set_person_authorization":
        action_text = "撤销授权" if arguments.get("action") == "revoke" else "恢复授权"
        return f"{action_text}人员 ID {arguments.get('person_id')} 的门禁权限"
    if name == "cleanup_logs":
        parts = []
        for key in ("source", "log_type", "level", "keyword", "after", "before"):
            if arguments.get(key):
                parts.append(f"{key}={arguments[key]}")
        return "清理系统日志" + (f"（{', '.join(parts)}）" if parts else "（未设置筛选条件，将匹配大量日志）")
    if name == "control_device":
        return f"控制设备 {arguments.get('device_id')} 执行 {arguments.get('action')}"
    if name == "set_theme":
        return "切换到夜晚模式" if arguments.get("theme") == "dark" else "切换到白天模式"
    return name


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    arguments = validate_tool_arguments(name, arguments)
    if name == "get_home_status":
        return {"ok": True, "data": home_service.get_home_status()}

    if name == "control_device":
        device_id = str(arguments.get("device_id") or "")
        action = str(arguments.get("action") or "")
        value = arguments.get("value")
        data = home_service.control_device(device_id, action, value, None)
        log_service.add_operation_log("agent_tool", home_service.describe_device_event(device_id, action, value, "remote"), detail={"tool": name, "value": value})
        return {"ok": True, "data": data}

    if name == "get_data_analysis":
        data = analysis_service.overview(arguments.get("after"), arguments.get("before"), arguments.get("bucket_seconds"))
        return {"ok": True, "data": data}

    if name == "list_persons":
        return {"ok": True, "data": person_service.list_persons()}

    if name == "set_person_authorization":
        person_id = int(arguments.get("person_id"))
        action = str(arguments.get("action") or "")
        if action == "revoke":
            person = person_service.revoke_person(person_id)
            action_text = "撤销授权"
        elif action == "restore":
            person = person_service.restore_person(person_id, str(arguments.get("role") or "resident"))
            action_text = "恢复授权"
        else:
            raise ValueError("授权操作不合法")
        if not person:
            raise ValueError("人员不存在")
        log_service.add_operation_log("agent_tool", f"智能助手{action_text}：{person['name']}", "warning", {"tool": name, "person_id": person_id})
        return {"ok": True, "data": person}

    if name == "list_logs":
        filters = {key: value for key, value in arguments.items() if value not in (None, "")}
        filters.setdefault("limit", 20)
        return {"ok": True, "data": log_service.list_logs(filters)}

    if name == "cleanup_logs":
        filters = {key: value for key, value in arguments.items() if value not in (None, "")}
        data = log_service.cleanup_logs(filters)
        log_service.add_operation_log("agent_tool", f"智能助手清理日志 {data['total']} 条", "warning", {"tool": name, "filters": filters, "deleted": data})
        return {"ok": True, "data": data}

    raise ValueError(f"未知工具：{name}")
