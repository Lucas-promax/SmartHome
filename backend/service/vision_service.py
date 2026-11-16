import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status

from service import person_service
from utils.db import BACKEND_ROOT, get_connection
from utils.time_utils import now_iso
from utils.runtime import configure_runtime
from service.hardware_service import hardware, HardwareError
from starlette.concurrency import run_in_threadpool


configure_runtime()


MODEL_ROOT = BACKEND_ROOT / "models"
FIRE_DRONE_MODEL = MODEL_ROOT / "best.pt"
GENERAL_MODEL = MODEL_ROOT / "yolov8s.pt"
GENERAL_LIGHT_MODEL = MODEL_ROOT / "yolov8n.pt"
FACE_MODEL_DIR = MODEL_ROOT / "buffalo_l"
FACE_INFO_DIR = BACKEND_ROOT / "database" / "face_info"
FACE_THRESHOLD = 0.4

_MODEL_CACHE: dict[str, Any] = {}
_FACE_REFERENCE_CACHE: list[dict[str, Any]] | None = None

DISPLAY_NAMES = {
    "drone": "无人机",
    "fire_extinguisher": "灭火器",
    "fire extinguisher": "灭火器",
}


def clear_face_reference_cache() -> None:
    global _FACE_REFERENCE_CACHE
    _FACE_REFERENCE_CACHE = None


async def save_snapshot(file: UploadFile, mode: str = "snapshot") -> dict[str, Any]:
    date_dir = now_iso()[:10].replace("-", "")
    target_dir = BACKEND_ROOT / "database" / "vision" / date_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "snapshot.jpg").suffix or ".jpg"
    filename = f"{mode}_{now_iso().replace(':', '').replace('-', '')}{suffix}"
    target = target_dir / filename
    content = await file.read()
    target.write_bytes(content)
    rel_path = target.relative_to(BACKEND_ROOT).as_posix()
    return {"image_path": rel_path, "size": len(content)}


async def detect(file: UploadFile, mode: str) -> dict[str, Any]:
    snapshot = await save_snapshot(file, mode)
    image_path = BACKEND_ROOT / snapshot["image_path"]
    model_path = FIRE_DRONE_MODEL if mode == "fire_drone" else GENERAL_MODEL

    if not model_path.exists():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"模型文件不存在: {model_path}")

    model = _load_yolo_model(mode, model_path)
    results = model(source=str(image_path), conf=0.35, verbose=False)
    result = results[0] if results else None
    image_height, image_width = _get_result_shape(result)
    detections = _parse_yolo_detections(result, model, image_width, image_height)

    result = {
        "mode": mode,
        "image_path": snapshot["image_path"],
        "image_width": image_width,
        "image_height": image_height,
        "detections": detections,
        "model_status": get_model_status(),
    }
    _write_vision_log(mode, snapshot["image_path"], result)
    _remove_file(image_path)
    return result


async def face_recognize(file: UploadFile) -> dict[str, Any]:
    snapshot = await save_snapshot(file, "face")
    image_path = BACKEND_ROOT / snapshot["image_path"]
    app = _load_face_app()
    embedding = _extract_face_embedding(app, image_path, "抓拍图片")
    references = _load_face_references(app)

    if not references:
        result = {
            "result": "unknown",
            "person": None,
            "confidence": None,
            "opened_door": False,
            "image_path": snapshot["image_path"],
            "model_status": get_model_status(),
            "message": "未找到已录入人脸标准照",
        }
        _write_vision_log("face", snapshot["image_path"], result)
        _write_access_log(None, "未知人员", "unknown", None, snapshot["image_path"], False)
        return result

    best_match = _match_face(embedding, references)
    matched = bool(best_match and best_match["similarity"] >= FACE_THRESHOLD)
    person = None
    if matched:
        person = {
            "id": best_match["id"],
            "name": best_match["name"],
            "role": best_match["role"],
            "enabled": best_match["enabled"],
            "authorized": best_match["authorized"],
            "source": best_match["source"],
        }
    granted = bool(person and person["authorized"])

    result = {
        "result": "granted" if granted else ("matched_no_permission" if matched else "unknown"),
        "person": person,
        "best_match": person,
        "confidence": round(best_match["similarity"], 4) if best_match else None,
        "opened_door": False,
        "image_path": snapshot["image_path"],
        "model_status": get_model_status(),
        "threshold": FACE_THRESHOLD,
        "message": _face_result_message(matched, granted, person),
    }
    if granted:
        try:
            feedback = await run_in_threadpool(_unlock_door_by_face, person)
            result["opened_door"] = True
            result["door_feedback"] = feedback
            result["message"] = f"匹配到 {person['name']}，板端已报告开门；无机械位置反馈"
        except HardwareError as exc:
            result["result"] = "control_failed"
            result["message"] = f"人员授权通过，但开门未确认：{exc}"
    _write_access_log(
        person["id"] if granted and person else None,
        person["name"] if person else "未知人员",
        result["result"],
        result["confidence"],
        snapshot["image_path"],
        result["opened_door"],
    )
    _write_vision_log("face", snapshot["image_path"], result)
    return result


def get_model_status() -> dict[str, Any]:
    return {
        "model_root": MODEL_ROOT.as_posix(),
        "fire_drone_model": FIRE_DRONE_MODEL.exists(),
        "general_model": GENERAL_MODEL.exists(),
        "general_light_model": GENERAL_LIGHT_MODEL.exists(),
        "face_model_dir": FACE_MODEL_DIR.exists(),
        "face_info_dir": FACE_INFO_DIR.exists(),
    }


def _load_yolo_model(mode: str, model_path: Path) -> Any:
    cache_key = f"{mode}:{model_path.as_posix()}"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="后端环境缺少 ultralytics，请先安装 YOLO 推理依赖。",
        ) from exc

    try:
        model = YOLO(str(model_path))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"模型加载失败: {exc}") from exc

    _MODEL_CACHE[cache_key] = model
    return model


def _load_face_app() -> Any:
    cache_key = f"face:{MODEL_ROOT.as_posix()}"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    try:
        from insightface.app import FaceAnalysis
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="后端环境缺少 insightface，请先安装 ArcFace 人脸识别依赖。",
        ) from exc

    try:
        app = FaceAnalysis(name="buffalo_l", root=BACKEND_ROOT.as_posix())
        app.prepare(ctx_id=-1, det_size=(640, 640))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"人脸模型加载失败: {exc}") from exc

    _MODEL_CACHE[cache_key] = app
    return app


def _extract_face_embedding(app: Any, image_path: Path, label: str) -> Any:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="后端环境缺少 opencv-python 或 numpy，无法进行人脸识别。",
        ) from exc

    image = cv2.imread(image_path.as_posix())
    if image is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"图片读取失败: {label}")
    faces = app.get(image)
    if not faces:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"未检测到人脸: {label}")
    embedding = faces[0].embedding
    norm = np.linalg.norm(embedding)
    if not norm:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"人脸向量无效: {label}")
    return embedding / norm


def _load_face_references(app: Any) -> list[dict[str, Any]]:
    global _FACE_REFERENCE_CACHE
    if _FACE_REFERENCE_CACHE is not None:
        return _FACE_REFERENCE_CACHE

    references: list[dict[str, Any]] = []
    if not FACE_INFO_DIR.exists():
        _FACE_REFERENCE_CACHE = references
        return references

    for person in person_service.list_face_references():
        face_image_path = person.get("face_image_path")
        if not face_image_path:
            continue
        standard_image = BACKEND_ROOT / face_image_path
        try:
            embedding = _extract_face_embedding(app, standard_image, person["name"])
        except HTTPException:
            continue
        references.append({
            "id": person["id"],
            "name": person["name"],
            "role": person["role"],
            "enabled": person["enabled"],
            "authorized": person["authorized"],
            "source": str(Path(face_image_path).parent),
            "embedding": embedding,
        })

    _FACE_REFERENCE_CACHE = references
    return references


def _display_face_name(folder_name: str) -> str:
    return folder_name.split("_", 1)[1] if "_" in folder_name else folder_name


def _match_face(embedding: Any, references: list[dict[str, Any]]) -> dict[str, Any] | None:
    best_match = None
    for reference in references:
        similarity = float(embedding.dot(reference["embedding"]))
        if best_match is None or similarity > best_match["similarity"]:
            best_match = {k: v for k, v in reference.items() if k != "embedding"}
            best_match["similarity"] = similarity
    return best_match


def _face_result_message(matched: bool, granted: bool, person: dict[str, Any] | None) -> str:
    if not matched:
        return "未匹配到已录入人员"
    if granted and person:
        return f"匹配到 {person['name']}，有门禁权限"
    if person:
        return f"匹配到 {person['name']}，但无门禁权限"
    return "未匹配到已录入人员"


def _unlock_door_by_face(person: dict[str, Any] | None) -> dict:
    return hardware.control("door_main", "open", source="face")


def _write_access_log(
    person_id: int | None,
    person_name: str,
    result: str,
    confidence: float | None,
    snapshot_path: str,
    opened_door: bool,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO access_logs (person_id, person_name, result, confidence, snapshot_path, opened_door, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (person_id, person_name, result, confidence, snapshot_path, int(opened_door), now_iso()),
        )


def _get_result_shape(result: Any) -> tuple[int | None, int | None]:
    shape = getattr(result, "orig_shape", None)
    if shape and len(shape) >= 2:
        return int(shape[0]), int(shape[1])
    return None, None


def _parse_yolo_detections(result: Any, model: Any, image_width: int | None, image_height: int | None) -> list[dict[str, Any]]:
    if result is None or getattr(result, "boxes", None) is None:
        return []

    detections: list[dict[str, Any]] = []
    names = getattr(model, "names", {}) or {}
    for box in result.boxes:
        cls_id = int(box.cls[0].item())
        raw_name = str(names.get(cls_id, cls_id))
        confidence = float(box.conf[0].item())
        x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        display_name = DISPLAY_NAMES.get(raw_name, raw_name)

        detections.append({
            "class": raw_name,
            "name": display_name,
            "confidence": round(confidence, 4),
            "bbox": [round(x1, 2), round(y1, 2), round(width, 2), round(height, 2)],
            "xyxy": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
            "image_width": image_width,
            "image_height": image_height,
        })
    return detections


def _write_vision_log(mode: str, image_path: str, result: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO vision_logs (mode, image_path, result_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (mode, image_path, json.dumps(result, ensure_ascii=False), now_iso()),
        )


def _remove_file(path: Path) -> None:
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        pass
