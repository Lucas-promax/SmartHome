from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    ok: bool = True
    message: str = "success"
    data: Any = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class DeviceControlRequest(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    value: Any = None


class HardwareEventRequest(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    value: Any = None


class SerialSettingsRequest(BaseModel):
    port: str = Field(default="", max_length=100)
    enabled: bool = False


class AlertSettingsRequest(BaseModel):
    banner_enabled: bool = True
    banner_stay_seconds: int = Field(5, ge=1, le=3600)
    temperature_high: float = Field(30, ge=-50, le=80)
    temperature_low: float = Field(16, ge=-50, le=80)
    humidity_high: float = Field(75, ge=0, le=100)
    humidity_low: float = Field(30, ge=0, le=100)
    door_open_seconds: int = Field(300, ge=10, le=86400)


class PersonCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    role: Literal["resident", "guest", "blocked"] = "resident"
    enabled: bool = True


class PersonUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    role: Literal["resident", "guest", "blocked"] | None = None
    enabled: bool | None = None


class FrontendLogRequest(BaseModel):
    level: Literal["info", "warning", "error"] = "info"
    module: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=500)
    detail: dict[str, Any] | None = None


class LogCleanupRequest(BaseModel):
    source: Literal["operation", "device", "access", "vision"] | None = None
    log_type: str | None = Field(default=None, max_length=64)
    level: Literal["info", "warning", "error"] | None = None
    keyword: str | None = Field(default=None, max_length=200)
    before: str | None = Field(default=None, max_length=64)
    after: str | None = Field(default=None, max_length=64)


class AgentSettingsRequest(BaseModel):
    api_key: str | None = Field(default=None, max_length=4096)
    base_url: str = Field("https://api.deepseek.com", min_length=1, max_length=500)
    model: str = Field("deepseek-v4-pro", min_length=1, max_length=128)
    max_tokens: int = Field(1024, ge=1, le=32000)
    max_rounds: int = Field(15, ge=1, le=100)
    temperature: float = Field(0.7, ge=0, le=2)
    top_p: float = Field(1.0, ge=0, le=1)
    presence_penalty: float = Field(0.0, ge=-2, le=2)
    frequency_penalty: float = Field(0.0, ge=-2, le=2)
    reasoning_effort: Literal["", "low", "medium", "high"] = ""
    thinking_enabled: bool = False
    timeout_seconds: int = Field(60, ge=5, le=300)
    system_prompt: str = Field(default="", max_length=4000)


class AgentMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class AgentToolConfirmation(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentClientToolResult(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)


class AgentChatRequest(BaseModel):
    messages: list[AgentMessage] = Field(min_length=1, max_length=100)
    conversation_id: str | None = Field(default=None, max_length=128)
    title: str | None = Field(default=None, max_length=100)
    confirmed_tool: AgentToolConfirmation | None = None
    client_tool_result: AgentClientToolResult | None = None


class CameraConnectRequest(BaseModel):
    port: str = Field(min_length=1, max_length=128)
    baudrate: Literal[115200, 250000, 500000, 1000000, 2000000] = 500000


class UsbCameraConnectRequest(BaseModel):
    device: str = Field(min_length=1, max_length=128)


class AgentConversationUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
