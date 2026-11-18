import json

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from agent import agent_service
from app.schemas import AgentChatRequest, AgentConversationUpdateRequest, AgentSettingsRequest, AlertSettingsRequest, DeviceControlRequest, FrontendLogRequest, HardwareEventRequest, LogCleanupRequest, LoginRequest, PersonUpdateRequest
from app.schemas import SerialSettingsRequest, CameraConnectRequest, UsbCameraConnectRequest
from service.camera_service import camera
from service.hardware_service import hardware
from service import analysis_service, auth_service, home_service, log_service, person_service, vision_service


router = APIRouter(prefix="/api")


def ok(data=None, message: str = "success") -> dict:
    return {"ok": True, "message": message, "data": data}


@router.post("/auth/login")
def login(payload: LoginRequest):
    data = auth_service.login(payload.username, payload.password)
    log_service.add_operation_log("auth", f"账号 {payload.username} 登录成功")
    return ok(data)


@router.post("/auth/logout")
def logout():
    return ok({"logged_out": True})


@router.get("/auth/me")
def me():
    return ok({"username": "local", "role": "local"})


@router.get("/home/status")
def home_status():
    return ok(home_service.get_home_status())


@router.get("/settings/alerts")
def get_alert_settings():
    return ok(home_service.get_alert_settings())


@router.put("/settings/alerts")
def update_alert_settings(payload: AlertSettingsRequest):
    try:
        data = home_service.update_alert_settings(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_service.add_operation_log("settings", "更新横幅告警配置")
    return ok(data)


@router.get("/devices")
def devices():
    return ok(home_service.list_devices())


@router.get("/hardware/status")
def hardware_status():
    return ok(hardware.status())


@router.get("/hardware/ports")
def hardware_ports():
    return ok(hardware.ports())


@router.post("/hardware/command")
def send_hardware_command(payload: dict):
    if "commands" in payload:
        if set(payload) != {"commands"}:
            raise HTTPException(status_code=400, detail="批量请求顶层仅允许 commands 字段")
        try:
            return ok(hardware.control_batch(payload["commands"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    unknown = set(payload) - {"device_id", "action", "value"}
    if unknown:
        raise HTTPException(status_code=400, detail="不支持的字段：" + ", ".join(sorted(unknown)))
    if not isinstance(payload.get("device_id"), str) or not isinstance(payload.get("action"), str):
        raise HTTPException(status_code=400, detail="device_id 和 action 必须是字符串")
    try:
        data = home_service.control_device(payload["device_id"], payload["action"], payload.get("value"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(data)


@router.put("/hardware/serial")
def configure_serial(payload: SerialSettingsRequest):
    try:
        if payload.enabled and payload.port == camera.port:
            raise ValueError("此串口正在用于 OV7670，请选择另一块家居主控板")
        return ok(hardware.configure(payload.port, payload.enabled))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/camera/ports")
def camera_ports():
    main_port = hardware.status()["port"]
    return ok([p for p in camera.ports() if p["port"] != main_port])


@router.get("/camera/usb/devices")
def usb_camera_devices():
    return ok(camera.usb_devices())


@router.post("/camera/usb/connect")
def connect_usb_camera(payload: UsbCameraConnectRequest):
    if payload.device not in {d["device"] for d in camera.usb_devices()}:
        raise HTTPException(status_code=400, detail="板端 USB 摄像头不存在，请刷新设备")
    try:
        return ok(camera.connect_usb(payload.device))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/camera/connect")
def connect_camera(payload: CameraConnectRequest):
    if payload.port == hardware.status()["port"]:
        raise HTTPException(status_code=400, detail="请选择独立摄像头板的串口，不能使用家居主控串口")
    if payload.port not in {p["port"] for p in camera.ports()}:
        raise HTTPException(status_code=400, detail="摄像头串口不存在，请刷新设备")
    try:
        return ok(camera.connect(payload.port, payload.baudrate))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/camera/connection")
def disconnect_camera(session: str):
    try:
        camera.stop(session)
        return ok()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/camera/frame")
def camera_frame(session: str, after: int = 0, preview_after: int = 0):
    try:
        return ok(camera.latest(session, after, preview_after))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/devices/{device_id}/control")
def control_device(device_id: str, payload: DeviceControlRequest):
    try:
        data = home_service.control_device(device_id, payload.action, payload.value, None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_service.add_operation_log("device", home_service.describe_device_event(device_id, payload.action, payload.value, "remote"), detail={"value": payload.value})
    return ok(data)


@router.post("/devices/{device_id}/hardware-event")
def record_hardware_event(device_id: str, payload: HardwareEventRequest):
    try:
        data = home_service.record_hardware_event(device_id, payload.action, payload.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_service.add_operation_log("device", home_service.describe_device_event(device_id, payload.action, payload.value, "hardware"), detail={"value": payload.value})
    return ok(data)


@router.get("/devices/logs")
def device_logs(limit: int = 100):
    return ok(home_service.list_device_logs(limit))


@router.get("/persons")
def persons():
    return ok(person_service.list_persons())


@router.post("/persons")
async def create_person(
    name: str = Form(...),
    role: str = Form("resident"),
    enabled: bool = Form(True),
    file: UploadFile = File(...),
):
    if role not in {"resident", "guest", "blocked"}:
        raise HTTPException(status_code=400, detail="人员角色不合法")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="人脸照片为空")
    person = person_service.create_person_with_face(name, role, enabled, file.filename or "0.jpg", content)
    vision_service.clear_face_reference_cache()
    log_service.add_operation_log("person", f"新增授权人员 {name}", detail={"role": role})
    return ok(person)


@router.get("/persons/{person_id}/face-image")
def person_face_image(person_id: int):
    path = person_service.get_face_image_path(person_id)
    if path is None:
        raise HTTPException(status_code=404, detail="人脸照片不存在")
    return FileResponse(path)


@router.patch("/persons/{person_id}")
def update_person(person_id: int, payload: PersonUpdateRequest):
    person = person_service.update_person(person_id, payload.model_dump(exclude_unset=True))
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    vision_service.clear_face_reference_cache()
    return ok(person)


@router.delete("/persons/{person_id}")
def delete_person(person_id: int):
    if not person_service.delete_person(person_id):
        raise HTTPException(status_code=404, detail="人员不存在")
    vision_service.clear_face_reference_cache()
    return ok({"deleted": person_id})


@router.delete("/persons/{person_id}/hard-delete")
def hard_delete_person(person_id: int):
    person = person_service.hard_delete_person(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    vision_service.clear_face_reference_cache()
    log_service.add_operation_log("person", f"删除人员 {person['name']}", detail={"id": person_id})
    return ok({"deleted": person_id})


@router.post("/persons/{person_id}/restore")
def restore_person(person_id: int, role: str = "resident"):
    person = person_service.restore_person(person_id, role)
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    vision_service.clear_face_reference_cache()
    log_service.add_operation_log("person", f"恢复授权人员 {person['name']}", detail={"role": person["role"]})
    return ok(person)


@router.get("/access/logs")
def access_logs(limit: int = 100):
    return ok(person_service.list_access_logs(limit))


@router.post("/vision/snapshot")
async def snapshot(file: UploadFile = File(...)):
    return ok(await vision_service.save_snapshot(file))


@router.post("/vision/detect")
async def detect(file: UploadFile = File(...)):
    return ok(await vision_service.detect(file, "general"))


@router.post("/vision/fire-drone-detect")
async def fire_drone_detect(file: UploadFile = File(...)):
    return ok(await vision_service.detect(file, "fire_drone"))


@router.post("/vision/face-recognize")
async def face_recognize(file: UploadFile = File(...)):
    return ok(await vision_service.face_recognize(file))


@router.get("/vision/logs")
def vision_logs():
    from utils.db import get_connection, rows_to_dicts

    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM vision_logs ORDER BY id DESC LIMIT 100").fetchall()
    logs = rows_to_dicts(rows)
    for log in logs:
        log["result"] = json.loads(log.pop("result_json") or "{}")
    return ok(logs)


@router.get("/vision/model-status")
def vision_model_status():
    return ok(vision_service.get_model_status())


@router.get("/analysis/summary")
def analysis_summary():
    return ok(analysis_service.summary())


@router.get("/analysis/overview")
def analysis_overview(after: str | None = None, before: str | None = None, bucket_seconds: int | None = None,
                      window_seconds: int | None = Query(default=None, ge=60, le=31 * 24 * 60 * 60)):
    return ok(analysis_service.overview(after, before, bucket_seconds, window_seconds))


@router.get("/analysis/sensors")
def analysis_sensors(after: str | None = None, before: str | None = None, bucket_seconds: int | None = None):
    return ok(analysis_service.sensors(after, before, bucket_seconds))


@router.get("/analysis/devices")
def analysis_devices(after: str | None = None, before: str | None = None, bucket_seconds: int | None = None):
    return ok(analysis_service.devices(after, before, bucket_seconds))


@router.get("/analysis/access")
def analysis_access(after: str | None = None, before: str | None = None, bucket_seconds: int | None = None):
    return ok(analysis_service.access(after, before, bucket_seconds))


@router.get("/analysis/vision")
def analysis_vision(after: str | None = None, before: str | None = None, bucket_seconds: int | None = None):
    return ok(analysis_service.vision(after, before, bucket_seconds))


@router.get("/logs")
def logs(
    source: str | None = None,
    log_type: str | None = None,
    level: str | None = None,
    keyword: str | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    return ok(log_service.list_logs({
        "source": source,
        "log_type": log_type,
        "level": level,
        "keyword": keyword,
        "after": after,
        "before": before,
        "limit": limit,
        "offset": offset,
    }))


@router.delete("/logs")
def cleanup_logs(payload: LogCleanupRequest):
    deleted = log_service.cleanup_logs(payload.model_dump(exclude_none=True))
    log_service.add_operation_log("logs", f"清理日志 {deleted['total']} 条", detail=deleted)
    return ok(deleted)


@router.post("/logs/frontend")
def frontend_log(payload: FrontendLogRequest):
    log_service.add_operation_log(payload.module, payload.message, payload.level, payload.detail)
    return ok({"recorded": True})


@router.get("/agent/status")
def agent_status():
    settings = agent_service.get_agent_settings()
    status = "ready" if settings["api_key_configured"] else "not_configured"
    return ok({"status": status, "settings": settings})


@router.get("/agent/settings")
def get_agent_settings():
    return ok(agent_service.get_agent_settings())


@router.get("/agent/conversations")
def agent_conversations():
    return ok(agent_service.list_conversations())


@router.get("/agent/conversations/{conversation_id}")
def agent_conversation(conversation_id: str):
    try:
        return ok(agent_service.get_conversation(conversation_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/agent/conversations/{conversation_id}")
def update_agent_conversation(conversation_id: str, payload: AgentConversationUpdateRequest):
    try:
        data = agent_service.update_conversation_title(conversation_id, payload.title)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ok(data)


@router.delete("/agent/conversations/{conversation_id}")
def delete_agent_conversation(conversation_id: str):
    try:
        data = agent_service.delete_conversation(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ok(data)


@router.put("/agent/settings")
def update_agent_settings(payload: AgentSettingsRequest):
    data = agent_service.update_agent_settings(payload.model_dump())
    log_service.add_operation_log("agent", "更新智能助手配置")
    return ok(data)


@router.post("/agent/chat/stream")
def agent_chat_stream(payload: AgentChatRequest):
    messages = [message.model_dump() for message in payload.messages]
    confirmed_tool = payload.confirmed_tool.model_dump() if payload.confirmed_tool else None
    client_tool_result = payload.client_tool_result.model_dump() if payload.client_tool_result else None

    def event_stream():
        assistant_content = ""
        try:
            for event in agent_service.chat_stream(messages, confirmed_tool, client_tool_result):
                if event.get("type") == "delta":
                    assistant_content += event.get("content") or ""
                if event.get("type") == "done":
                    conversation = agent_service.save_conversation(
                        payload.conversation_id,
                        [*messages, {"role": "assistant", "content": assistant_content}],
                        payload.title,
                    )
                    event = {"type": "done", "conversation": {"id": conversation["id"], "title": conversation["title"]}}
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except ValueError as exc:
            event = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
