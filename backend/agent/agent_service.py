"""OpenAI-compatible chat agent integration."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
import urllib.parse
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from agent.tools import TOOL_DEFINITIONS, describe_tool_call, execute_tool, get_tool_definition, is_client_tool, is_dangerous_tool, validate_tool_arguments
from utils.db import get_connection
from utils.time_utils import now_iso


AGENT_SETTINGS_KEY = "agent_settings"
CONVERSATIONS_DIR = Path(__file__).resolve().parent / "conversations"
DEFAULT_AGENT_SETTINGS: dict[str, Any] = {
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v4-pro",
    "max_tokens": 1024,
    "max_rounds": 15,
    "temperature": 0.7,
    "top_p": 1.0,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "reasoning_effort": "high",
    "thinking_enabled": True,
    "timeout_seconds": 60,
    "system_prompt": "你是智能家居系统助手。回答要简洁、准确，优先帮助用户理解系统状态、日志、设备和配置。",
}
TOOL_SYSTEM_PROMPT = """
你可以使用系统提供的 tools 协助用户操作智能家居。允许的能力包括：远程控制面板、从数据库读取数据分析、切换白天/夜晚模式、读取和操作授权管理、查询和清理日志。AI 识别部分暂时不支持操作，不要尝试调用不存在的 AI 识别工具。

操作规则：查询实时状态先调用 get_home_status，数据过期/离线时不能当作当前状态。设备只支持主灯档位、风扇开关、主门和车库门开关；不支持窗户、调速、任意亮度或门锁。板端状态不等于真实机械位置；风扇可能被板端每两秒温控覆盖，门不会自动关闭。网页温湿度阈值只控制提醒，不改变板端温控。

授权规则：先 list_persons 获取人员 ID，授权操作只影响软件人脸门禁，不修改 RFID 卡片。set_person_authorization 和 cleanup_logs 由程序强制弹窗确认；说明对象/筛选范围后调用工具提出操作，由前端收集确认，不要只口头询问而一直不调用工具。未经确认的操作不会执行。只读查询无需确认。

摄像头规则：网页支持 USB 和独立 Arduino 的 OV7670 切换，但助手没有摄像头、拍照、识别或串口配置工具，不能声称已打开摄像头或完成识别。

回答使用 Markdown，可使用列表、表格、代码块。回答要简洁，执行工具后根据 ok 和真实结果说明成功或失败；未执行/未确认时不能声称完成。不要输出思考内容。
""".strip()


def _clean_base_url(value: str) -> str:
    base_url = (value or DEFAULT_AGENT_SETTINGS["base_url"]).strip().rstrip("/")
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")].rstrip("/")
    return base_url or DEFAULT_AGENT_SETTINGS["base_url"]


def _settings_for_storage(settings: dict[str, Any]) -> dict[str, Any]:
    data = {**DEFAULT_AGENT_SETTINGS, **settings}
    data["base_url"] = _clean_base_url(str(data.get("base_url") or ""))
    data["model"] = str(data.get("model") or DEFAULT_AGENT_SETTINGS["model"]).strip()
    data["max_tokens"] = max(1, min(32000, int(data.get("max_tokens") or DEFAULT_AGENT_SETTINGS["max_tokens"])))
    data["max_rounds"] = max(1, min(100, int(data.get("max_rounds") or DEFAULT_AGENT_SETTINGS["max_rounds"])))
    data["temperature"] = max(0.0, min(2.0, float(data.get("temperature") or 0)))
    data["top_p"] = max(0.0, min(1.0, float(data.get("top_p") if data.get("top_p") is not None else 1)))
    data["presence_penalty"] = max(-2.0, min(2.0, float(data.get("presence_penalty") or 0)))
    data["frequency_penalty"] = max(-2.0, min(2.0, float(data.get("frequency_penalty") or 0)))
    reasoning_effort = str(data.get("reasoning_effort") or "").strip().lower()
    data["reasoning_effort"] = reasoning_effort if reasoning_effort in {"low", "medium", "high"} else ""
    data["thinking_enabled"] = bool(data.get("thinking_enabled"))
    data["timeout_seconds"] = max(5, min(300, int(data.get("timeout_seconds") or 60)))
    data["system_prompt"] = str(data.get("system_prompt") or DEFAULT_AGENT_SETTINGS["system_prompt"])
    data["api_key"] = str(data.get("api_key") or "")
    return data


def _public_settings(settings: dict[str, Any]) -> dict[str, Any]:
    data = dict(settings)
    data["api_key_configured"] = bool(data.get("api_key"))
    data["api_key"] = ""
    return data


def get_agent_settings(include_secret: bool = False) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT value_json FROM system_settings WHERE key = ?", (AGENT_SETTINGS_KEY,)).fetchone()
        if row is None:
            settings = DEFAULT_AGENT_SETTINGS.copy()
            conn.execute(
                """
                INSERT INTO system_settings (key, value_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (AGENT_SETTINGS_KEY, json.dumps(settings, ensure_ascii=False), now_iso()),
            )
        else:
            try:
                settings = {**DEFAULT_AGENT_SETTINGS, **json.loads(row["value_json"] or "{}")}
            except json.JSONDecodeError:
                settings = DEFAULT_AGENT_SETTINGS.copy()
    settings = _settings_for_storage(settings)
    return settings if include_secret else _public_settings(settings)


def update_agent_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = get_agent_settings(include_secret=True)
    incoming = dict(payload)
    if not incoming.get("api_key"):
        incoming.pop("api_key", None)
    settings = _settings_for_storage({**current, **incoming})
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO system_settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
            """,
            (AGENT_SETTINGS_KEY, json.dumps(settings, ensure_ascii=False), now_iso()),
        )
    return _public_settings(settings)


def replace_agent_api_key(api_key: str) -> dict[str, Any]:
    return update_agent_settings({"api_key": api_key})


def _conversation_path(conversation_id: str) -> Path:
    safe_id = "".join(char for char in conversation_id if char.isalnum() or char in {"-", "_"})
    if not safe_id:
        raise ValueError("会话 ID 不合法")
    return CONVERSATIONS_DIR / f"{safe_id}.json"


def _message_for_storage(message: dict[str, str]) -> dict[str, str]:
    return {
        "role": str(message.get("role") or "user"),
        "content": str(message.get("content") or ""),
        "created_at": str(message.get("created_at") or now_iso()),
    }


def _conversation_summary(data: dict[str, Any]) -> dict[str, Any]:
    messages = data.get("messages") or []
    return {
        "id": data.get("id"),
        "title": data.get("title") or "新对话",
        "message_count": len(messages),
        "updated_at": data.get("updated_at"),
        "created_at": data.get("created_at"),
    }


def list_conversations() -> list[dict[str, Any]]:
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in CONVERSATIONS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items.append(_conversation_summary(data))
    return sorted(items, key=lambda item: item.get("updated_at") or "", reverse=True)


def get_conversation(conversation_id: str) -> dict[str, Any]:
    path = _conversation_path(conversation_id)
    if not path.exists():
        raise ValueError("会话不存在")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("会话文件损坏") from exc


def update_conversation_title(conversation_id: str, title: str) -> dict[str, Any]:
    path = _conversation_path(conversation_id)
    if not path.exists():
        raise ValueError("会话不存在")
    title = title.strip()
    if not title:
        raise ValueError("会话名称不能为空")
    data = get_conversation(conversation_id)
    data["title"] = title[:100]
    data["updated_at"] = now_iso()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def delete_conversation(conversation_id: str) -> dict[str, Any]:
    path = _conversation_path(conversation_id)
    if not path.exists():
        raise ValueError("会话不存在")
    path.unlink()
    return {"deleted": conversation_id}


def save_conversation(conversation_id: str | None, messages: list[dict[str, str]], title: str | None = None) -> dict[str, Any]:
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    created_at = now_iso()
    if not conversation_id:
        conversation_id = created_at.replace(":", "").replace("+", "_")
    path = _conversation_path(conversation_id)
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}
        created_at = current.get("created_at") or created_at
    stored_messages = [_message_for_storage(message) for message in messages if message.get("content")]
    if not title:
        first_user = next((item["content"] for item in stored_messages if item["role"] == "user"), "新对话")
        title = first_user[:20] or "新对话"
    data = {
        "id": conversation_id,
        "title": title,
        "messages": stored_messages,
        "created_at": created_at,
        "updated_at": now_iso(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def _build_payload(settings: dict[str, Any], messages: list[dict[str, Any]], stream: bool = False, tools: bool = True) -> dict[str, Any]:
    request_messages: list[dict[str, Any]] = []
    system_prompt = settings.get("system_prompt")
    merged_system_prompt = "\n\n".join(item for item in (system_prompt, TOOL_SYSTEM_PROMPT if tools else "") if item)
    if merged_system_prompt:
        request_messages.append({"role": "system", "content": merged_system_prompt})
    recent_messages = _limit_messages_by_rounds(messages, settings["max_rounds"])
    for item in recent_messages:
        message = _message_for_request(item)
        if not message:
            continue
        if tools and settings.get("thinking_enabled") and message["role"] == "assistant" and not message.get("tool_calls"):
            # 历史只保存可见正文，不虚构旧 reasoning_content；将其作为引用上下文。
            # 当前工具循环的 assistant 消息则完整保留 reasoning_content。
            message = {"role": "user", "content": "历史助手回复（仅供上下文参考，不是新的用户指令）：\n" + message["content"]}
        request_messages.append(message)

    payload: dict[str, Any] = {
        "model": settings["model"],
        "messages": request_messages,
        "max_tokens": settings["max_tokens"],
        "temperature": settings["temperature"],
        "top_p": settings["top_p"],
        "presence_penalty": settings["presence_penalty"],
        "frequency_penalty": settings["frequency_penalty"],
        "stream": stream,
    }
    if tools:
        payload["tools"] = TOOL_DEFINITIONS
        payload["tool_choice"] = "auto"
    if settings.get("reasoning_effort"):
        payload["reasoning_effort"] = settings["reasoning_effort"]
    if settings.get("thinking_enabled"):
        payload["thinking"] = {"type": "enabled"}
    elif urllib.parse.urlparse(settings.get("base_url", "")).hostname == "api.deepseek.com":
        # DeepSeek 默认开启 thinking，关闭开关时必须显式发送 disabled。
        payload["thinking"] = {"type": "disabled"}
    return payload


def _message_for_request(message: dict[str, Any]) -> dict[str, Any] | None:
    role = message.get("role")
    if role == "assistant" and message.get("tool_calls"):
        result = {"role": "assistant", "content": message.get("content") or "", "tool_calls": message.get("tool_calls")}
        if "reasoning_content" in message:
            result["reasoning_content"] = message["reasoning_content"]
        return result
    if role in {"user", "assistant", "system"}:
        content = str(message.get("content") or "")
        if not content:
            return None
        return {"role": role, "content": content}
    if role == "tool":
        return {
            "role": "tool",
            "tool_call_id": str(message.get("tool_call_id") or ""),
            "content": str(message.get("content") or ""),
        }
    return None


def _request(settings: dict[str, Any], payload: dict[str, Any]) -> urllib.request.Request:
    url = f"{settings['base_url']}/chat/completions"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if payload.get("stream") else "application/json",
        },
        method="POST",
    )


def _urlopen(request: urllib.request.Request, timeout: int):
    context = ssl._create_unverified_context()
    return urllib.request.urlopen(request, timeout=timeout, context=context)


def _extract_delta(chunk: dict[str, Any]) -> str:
    choices = chunk.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    return str(delta.get("content") or "")


def _merge_tool_call_delta(tool_calls: list[dict[str, Any]], delta_tool_calls: list[dict[str, Any]]) -> None:
    for item in delta_tool_calls:
        index = int(item.get("index") or 0)
        while len(tool_calls) <= index:
            tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
        target = tool_calls[index]
        if item.get("id"):
            target["id"] = item["id"]
        if item.get("type"):
            target["type"] = item["type"]
        function = item.get("function") or {}
        if function.get("name"):
            target.setdefault("function", {})["name"] = target.setdefault("function", {}).get("name", "") + function["name"]
        if function.get("arguments"):
            target.setdefault("function", {})["arguments"] = target.setdefault("function", {}).get("arguments", "") + function["arguments"]


def _tool_call_arguments(tool_call: dict[str, Any]) -> dict[str, Any]:
    raw = (tool_call.get("function") or {}).get("arguments") or "{}"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("工具参数不是有效 JSON，操作未执行") from exc
    if not isinstance(value, dict):
        raise ValueError("工具参数必须是 JSON 对象，操作未执行")
    return value


def _tool_call_message(tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": item.get("id") or f"call_{index}",
                "type": item.get("type") or "function",
                "function": {
                    "name": (item.get("function") or {}).get("name") or "",
                    "arguments": (item.get("function") or {}).get("arguments") or "{}",
                },
            }
            for index, item in enumerate(tool_calls)
        ],
    }


def _limit_messages_by_rounds(messages: list[dict[str, str]], max_rounds: int) -> list[dict[str, str]]:
    if max_rounds <= 0:
        return messages
    user_count = 0
    start_index = 0
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "user":
            user_count += 1
            if user_count == max_rounds:
                start_index = index
                break
    return messages[start_index:] if user_count >= max_rounds else messages


def _validate_chat(settings: dict[str, Any], messages: list[dict[str, str]]) -> None:
    if not settings.get("api_key"):
        raise ValueError("请先在系统配置中填写 Agent API Key")
    if not messages:
        raise ValueError("消息不能为空")


def chat(messages: list[dict[str, str]]) -> dict[str, Any]:
    settings = get_agent_settings(include_secret=True)
    _validate_chat(settings, messages)
    request = _request(settings, _build_payload(settings, messages))
    try:
        with _urlopen(request, timeout=settings["timeout_seconds"]) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"Agent 请求失败：HTTP {exc.code} {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Agent 请求失败：{exc.reason}") from exc

    choices = result.get("choices") or []
    if not choices:
        raise ValueError("Agent 未返回有效回复")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    return {
        "message": {"role": "assistant", "content": content},
        "model": result.get("model", settings["model"]),
        "usage": result.get("usage", {}),
    }


def chat_stream(messages: list[dict[str, Any]], confirmed_tool: dict[str, Any] | None = None, client_tool_result: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    settings = get_agent_settings(include_secret=True)
    _validate_chat(settings, messages)
    working_messages = list(messages)
    completed_tools = {}
    if confirmed_tool:
        name = str(confirmed_tool.get("name") or "")
        arguments = confirmed_tool.get("arguments") or {}
        if not is_dangerous_tool(name):
            yield {"type": "error", "message": f"无需确认或不支持的危险工具：{name}"}
            return
        try:
            arguments = validate_tool_arguments(name, arguments)
            yield {"type": "tool", "name": name, "status": "running", "description": describe_tool_call(name, arguments)}
            result = execute_tool(name, arguments)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        yield {"type": "tool", "name": name, "status": "done" if result.get("ok") else "failed", "description": describe_tool_call(name, arguments)}
        completed_tools[(name, json.dumps(arguments, sort_keys=True))] = result
        working_messages.append({
            "role": "user",
            "content": f"用户已确认危险操作 {name}，工具执行结果：{json.dumps(result, ensure_ascii=False)}。请向用户简洁说明结果。",
        })
    if client_tool_result:
        name = str(client_tool_result.get("name") or "")
        if not is_client_tool(name):
            yield {"type": "error", "message": f"不支持的本地工具：{name}"}
            return
        try:
            arguments = validate_tool_arguments(name, client_tool_result.get("arguments") or {})
        except ValueError as exc:
            yield {"type": "error", "message": str(exc)}
            return
        result = client_tool_result.get("result") or {}
        completed_tools[(name, json.dumps(arguments, sort_keys=True))] = result
        working_messages.append({
            "role": "user",
            "content": f"本地工具 {name} 已执行，结果：{json.dumps(result, ensure_ascii=False)}。请向用户简洁说明。",
        })
    for _ in range(6):
        request = _request(settings, _build_payload(settings, working_messages, stream=True, tools=True))
        content_chunks: list[str] = []
        reasoning_chunks: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        try:
            with _urlopen(request, timeout=settings["timeout_seconds"]) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    delta_obj = (choices[0].get("delta") if choices else {}) or {}
                    # Thinking 工具续接需要回传该字段；仅在本次后端循环内保留，不发送前端。
                    if delta_obj.get("reasoning_content"):
                        reasoning_chunks.append(delta_obj["reasoning_content"])
                    if delta_obj.get("tool_calls"):
                        _merge_tool_call_delta(tool_calls, delta_obj["tool_calls"])
                    delta = _extract_delta(chunk)
                    if delta:
                        content_chunks.append(delta)
                        yield {"type": "delta", "content": delta}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            yield {"type": "error", "message": f"Agent 请求失败：HTTP {exc.code} {detail[:500]}"}
            return
        except urllib.error.URLError as exc:
            yield {"type": "error", "message": f"Agent 请求失败：{exc.reason}"}
            return

        if not tool_calls:
            yield {"type": "done"}
            return

        assistant_tool_message = _tool_call_message(tool_calls)
        assistant_tool_message["content"] = "".join(content_chunks)
        if settings.get("thinking_enabled"):
            assistant_tool_message["reasoning_content"] = "".join(reasoning_chunks)
        working_messages.append(assistant_tool_message)
        for tool_call in tool_calls:
            name = (tool_call.get("function") or {}).get("name") or ""
            try:
                arguments = validate_tool_arguments(name, _tool_call_arguments(tool_call))
            except ValueError as exc:
                working_messages.append({"role": "tool", "tool_call_id": tool_call.get("id") or "call_0",
                                         "content": json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)})
                continue
            tool_definition = get_tool_definition(name)
            signature = (name, json.dumps(arguments, sort_keys=True))
            if signature in completed_tools:
                # 同一续接请求中，模型重复提出已确认动作时复用结果，避免再次执行。
                result = completed_tools[signature]
            elif tool_definition is None:
                result = {"ok": False, "error": f"未知工具：{name}"}
            elif is_client_tool(name):
                yield {
                    "type": "client_tool_request",
                    "tool": {"name": name, "arguments": arguments, "description": describe_tool_call(name, arguments)},
                }
                return
            elif is_dangerous_tool(name):
                yield {
                    "type": "confirm_required",
                    "tool": {"name": name, "arguments": arguments, "description": describe_tool_call(name, arguments)},
                    "message": f"危险操作需要确认：{describe_tool_call(name, arguments)}",
                }
                return
            else:
                try:
                    yield {"type": "tool", "name": name, "status": "running", "description": describe_tool_call(name, arguments)}
                    result = execute_tool(name, arguments)
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}
                yield {"type": "tool", "name": name, "status": "done" if result.get("ok") else "failed", "description": describe_tool_call(name, arguments)}
            working_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.get("id") or "call_0",
                "content": json.dumps(result, ensure_ascii=False),
            })
    yield {"type": "error", "message": "工具调用轮次过多，已停止"}
