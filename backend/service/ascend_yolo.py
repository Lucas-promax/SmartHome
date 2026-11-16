"""Ascend OM inference adapted from the existing OrangePi deployment."""
import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from utils.db import BACKEND_ROOT


MODEL_ROOT = BACKEND_ROOT / "models"


FIRE_DRONE_OM_MODEL = MODEL_ROOT / "best.om"


GENERAL_OM_MODEL = MODEL_ROOT / "yolov8s.om"


GENERAL_LIGHT_OM_MODEL = MODEL_ROOT / "yolov8n.om"


YOLO_INPUT_SIZE = (640, 640)


YOLO_CONF_THRESHOLD = 0.35


FIRE_DRONE_CONF_THRESHOLD = 0.6


YOLO_IOU_THRESHOLD = 0.5


_MODEL_CACHE: dict[str, Any] = {}


DISPLAY_NAMES = {
    "drone": "无人机",
    "fire_extinguisher": "灭火器",
    "fire extinguisher": "灭火器",
}


COCO_NAMES = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane", 5: "bus", 6: "train", 7: "truck", 8: "boat",
    9: "traffic light", 10: "fire hydrant", 11: "stop sign", 12: "parking meter", 13: "bench", 14: "bird", 15: "cat",
    16: "dog", 17: "horse", 18: "sheep", 19: "cow", 20: "elephant", 21: "bear", 22: "zebra", 23: "giraffe",
    24: "backpack", 25: "umbrella", 26: "handbag", 27: "tie", 28: "suitcase", 29: "frisbee", 30: "skis",
    31: "snowboard", 32: "sports ball", 33: "kite", 34: "baseball bat", 35: "baseball glove", 36: "skateboard",
    37: "surfboard", 38: "tennis racket", 39: "bottle", 40: "wine glass", 41: "cup", 42: "fork", 43: "knife",
    44: "spoon", 45: "bowl", 46: "banana", 47: "apple", 48: "sandwich", 49: "orange", 50: "broccoli", 51: "carrot",
    52: "hot dog", 53: "pizza", 54: "donut", 55: "cake", 56: "chair", 57: "couch", 58: "potted plant", 59: "bed",
    60: "dining table", 61: "toilet", 62: "tv", 63: "laptop", 64: "mouse", 65: "remote", 66: "keyboard",
    67: "cell phone", 68: "microwave", 69: "oven", 70: "toaster", 71: "sink", 72: "refrigerator", 73: "book",
    74: "clock", 75: "vase", 76: "scissors", 77: "teddy bear", 78: "hair drier", 79: "toothbrush",
}


def _detect_with_om(mode: str, image_path: Path) -> tuple[list[dict[str, Any]], int | None, int | None]:
    model_path = FIRE_DRONE_OM_MODEL if mode == "fire_drone" else GENERAL_OM_MODEL
    if not model_path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"NPU 模型文件不存在: {model_path}。请先将 .pt 导出 ONNX 后用 atc 转换为 .om。",
        )

    detector = _load_om_yolo_model(mode, model_path)
    return detector.detect(image_path)


def _load_om_yolo_model(mode: str, model_path: Path) -> Any:
    cache_key = f"om:{mode}:{model_path.as_posix()}"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]
    detector = AscendYoloDetector(model_path, names=_yolo_names(mode))
    _MODEL_CACHE[cache_key] = detector
    return detector


def _yolo_names(mode: str) -> dict[int, str]:
    names_path = FIRE_DRONE_OM_MODEL.with_suffix(".names") if mode == "fire_drone" else GENERAL_OM_MODEL.with_suffix(".names")
    if names_path.exists():
        names = [line.strip() for line in names_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return {index: name for index, name in enumerate(names)}
    return {} if mode == "fire_drone" else COCO_NAMES


class AscendYoloDetector:
    def __init__(self, model_path: Path, names: dict[int, str]) -> None:
        self.model_path = model_path
        try:
            from ais_bench.infer.interface import InferSession
            self.session = InferSession(0, model_path.as_posix())
            self.session_type = "ais_bench"
        except Exception as exc:
            self.session = NativeAclSession(model_path)
            self.session_type = f"acl ({exc})"
        self.names = names

    def detect(self, image_path: Path) -> tuple[list[dict[str, Any]], int | None, int | None]:
        try:
            import cv2
        except ImportError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="后端环境缺少 opencv-python，无法读取识别图片。") from exc

        image = cv2.imread(image_path.as_posix())
        if image is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图片读取失败")

        tensor, ratio, pad = _preprocess_yolo_image(image)
        try:
            output = self.session.infer([tensor])[0]
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"NPU 推理失败: {exc}") from exc

        boxes = _postprocess_yolo_output(output, image.shape[:2], ratio, pad, _yolo_conf_threshold(self.model_path))
        detections = _boxes_to_detections(boxes, self.names, image.shape[1], image.shape[0])
        return detections, int(image.shape[1]), int(image.shape[0])


class NativeAclSession:
    ACL_SUCCESS = 0
    ACL_MEM_MALLOC_HUGE_FIRST = 0
    ACL_MEMCPY_HOST_TO_DEVICE = 1
    ACL_MEMCPY_DEVICE_TO_HOST = 2

    def __init__(self, model_path: Path, device_id: int = 0) -> None:
        try:
            import acl
            import numpy as np
        except ImportError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="后端环境缺少 Ascend acl，无法加载 .om NPU 模型。") from exc

        self.acl = acl
        self.np = np
        self.device_id = device_id
        self.context = None
        self.model_id = None
        self.model_desc = None
        self.input_dataset = None
        self.output_dataset = None
        self.input_data: list[dict[str, Any]] = []
        self.output_data: list[dict[str, Any]] = []
        self.output_shapes: list[tuple[int, ...]] = []
        self.output_dtypes: list[Any] = []
        self._init_resource(model_path)

    def infer(self, inputs: list[Any]) -> list[Any]:
        tensor = self.np.ascontiguousarray(inputs[0])
        if tensor.nbytes > self.input_data[0]["size"]:
            raise RuntimeError(f"输入数据过大: {tensor.nbytes} > {self.input_data[0]['size']}")

        ptr = self.acl.util.bytes_to_ptr(tensor.tobytes())
        ret = self.acl.rt.memcpy(self.input_data[0]["buffer"], self.input_data[0]["size"], ptr, tensor.nbytes, self.ACL_MEMCPY_HOST_TO_DEVICE)
        self._check("acl.rt.memcpy input", ret)
        ret = self.acl.mdl.execute(self.model_id, self.input_dataset, self.output_dataset)
        self._check("acl.mdl.execute", ret)

        results = []
        for index, item in enumerate(self.output_data):
            host_buffer, ret = self.acl.rt.malloc_host(item["size"])
            self._check("acl.rt.malloc_host", ret)
            try:
                ret = self.acl.rt.memcpy(host_buffer, item["size"], item["buffer"], item["size"], self.ACL_MEMCPY_DEVICE_TO_HOST)
                self._check("acl.rt.memcpy output", ret)
                data = self.acl.util.ptr_to_bytes(host_buffer, item["size"])
                results.append(self.np.frombuffer(data, dtype=self.output_dtypes[index]).reshape(self.output_shapes[index]))
            finally:
                self.acl.rt.free_host(host_buffer)
        return results

    def _init_resource(self, model_path: Path) -> None:
        ret = self.acl.init()
        if ret not in (self.ACL_SUCCESS, 100002):
            self._check("acl.init", ret)
        ret = self.acl.rt.set_device(self.device_id)
        self._check("acl.rt.set_device", ret)
        self.context, ret = self.acl.rt.create_context(self.device_id)
        self._check("acl.rt.create_context", ret)

        self.model_id, ret = self.acl.mdl.load_from_file(model_path.as_posix())
        self._check("acl.mdl.load_from_file", ret)
        self.model_desc = self.acl.mdl.create_desc()
        ret = self.acl.mdl.get_desc(self.model_desc, self.model_id)
        self._check("acl.mdl.get_desc", ret)
        self._prepare_inputs()
        self._prepare_outputs()

    def _prepare_inputs(self) -> None:
        self.input_dataset = self.acl.mdl.create_dataset()
        input_count = self.acl.mdl.get_num_inputs(self.model_desc)
        for index in range(input_count):
            buffer_size = self.acl.mdl.get_input_size_by_index(self.model_desc, index)
            buffer, ret = self.acl.rt.malloc(buffer_size, self.ACL_MEM_MALLOC_HUGE_FIRST)
            self._check("acl.rt.malloc input", ret)
            data = self.acl.create_data_buffer(buffer, buffer_size)
            _, ret = self.acl.mdl.add_dataset_buffer(self.input_dataset, data)
            self._check("acl.mdl.add_dataset_buffer input", ret)
            self.input_data.append({"buffer": buffer, "size": buffer_size})

    def _prepare_outputs(self) -> None:
        self.output_dataset = self.acl.mdl.create_dataset()
        output_count = self.acl.mdl.get_num_outputs(self.model_desc)
        for index in range(output_count):
            dims, ret = self.acl.mdl.get_output_dims(self.model_desc, index)
            self._check("acl.mdl.get_output_dims", ret)
            self.output_shapes.append(tuple(int(dim) for dim in dims["dims"]))
            data_type = self.acl.mdl.get_output_data_type(self.model_desc, index)
            self.output_dtypes.append(_acl_dtype(data_type))
            buffer_size = self.acl.mdl.get_output_size_by_index(self.model_desc, index)
            buffer, ret = self.acl.rt.malloc(buffer_size, self.ACL_MEM_MALLOC_HUGE_FIRST)
            self._check("acl.rt.malloc output", ret)
            data = self.acl.create_data_buffer(buffer, buffer_size)
            _, ret = self.acl.mdl.add_dataset_buffer(self.output_dataset, data)
            self._check("acl.mdl.add_dataset_buffer output", ret)
            self.output_data.append({"buffer": buffer, "size": buffer_size})

    def _check(self, label: str, ret: int) -> None:
        if ret != self.ACL_SUCCESS:
            raise RuntimeError(f"{label} failed ret={ret}")


def _acl_dtype(data_type: int) -> Any:
    import numpy as np

    dtype_map = {
        0: np.float32,
        1: np.float16,
        2: np.int8,
        3: np.int32,
        4: np.uint8,
        6: np.int16,
        7: np.uint16,
        8: np.uint32,
        9: np.int64,
        10: np.uint64,
        11: np.float64,
        12: np.bool_,
    }
    return dtype_map.get(data_type, np.float32)


def _preprocess_yolo_image(image: Any) -> tuple[Any, tuple[float, float], tuple[float, float]]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="后端环境缺少 opencv-python 或 numpy，无法预处理图片。") from exc

    input_height, input_width = YOLO_INPUT_SIZE
    height, width = image.shape[:2]
    scale = min(input_width / width, input_height / height)
    resized_width = int(round(width * scale))
    resized_height = int(round(height * scale))
    pad_x = (input_width - resized_width) / 2
    pad_y = (input_height - resized_height) / 2

    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
    top = int(round(pad_y - 0.1))
    bottom = int(round(pad_y + 0.1))
    left = int(round(pad_x - 0.1))
    right = int(round(pad_x + 0.1))
    padded = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    rgb = padded[:, :, ::-1]
    tensor = rgb.transpose(2, 0, 1) / 255.0
    tensor = np.expand_dims(np.ascontiguousarray(tensor, dtype=np.float32), axis=0)
    return tensor, (scale, scale), (pad_x, pad_y)


def _postprocess_yolo_output(output: Any, image_shape: tuple[int, int], ratio: tuple[float, float], pad: tuple[float, float], conf_threshold: float) -> Any:
    try:
        import numpy as np
    except ImportError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="后端环境缺少 numpy，无法处理识别结果。") from exc

    prediction = np.asarray(output)
    if prediction.ndim == 3:
        prediction = prediction[0]
    if prediction.ndim != 2:
        return np.zeros((0, 6), dtype=np.float32)

    if prediction.shape[0] < prediction.shape[1] and prediction.shape[0] <= 256:
        prediction = prediction.T

    if prediction.shape[1] < 6:
        return np.zeros((0, 6), dtype=np.float32)

    # These OM models are raw YOLOv8 exports: xywh plus one score per class.
    # In particular, six columns means TWO classes, not post-NMS xyxy/conf/id.
    boxes = _decode_yolo_scores(prediction.astype(np.float32), conf_threshold)

    if boxes.size == 0:
        return np.zeros((0, 6), dtype=np.float32)

    boxes[:, :4] = _xywh_to_xyxy(boxes[:, :4])
    boxes[:, [0, 2]] -= pad[0]
    boxes[:, [1, 3]] -= pad[1]
    boxes[:, :4] /= ratio[0]
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, image_shape[1])
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, image_shape[0])
    return _numpy_nms(boxes, YOLO_IOU_THRESHOLD)


def _decode_yolo_scores(prediction: Any, conf_threshold: float) -> Any:
    import numpy as np

    if prediction.shape[1] > 85:
        candidate = prediction[prediction[:, 4] >= conf_threshold]
        if candidate.size == 0:
            return np.zeros((0, 6), dtype=np.float32)
        class_scores = candidate[:, 5:]
        class_ids = class_scores.argmax(axis=1)
        confidences = candidate[:, 4] * class_scores[np.arange(candidate.shape[0]), class_ids]
        keep = confidences >= conf_threshold
        return np.column_stack((candidate[keep, :4], confidences[keep], class_ids[keep])).astype(np.float32)

    class_scores = prediction[:, 4:]
    class_ids = class_scores.argmax(axis=1)
    confidences = class_scores[np.arange(prediction.shape[0]), class_ids]
    keep = confidences >= conf_threshold
    return np.column_stack((prediction[keep, :4], confidences[keep], class_ids[keep])).astype(np.float32)


def _yolo_conf_threshold(model_path: Path | None = None) -> float:
    env_name = "SMARTHOME_FIRE_DRONE_CONF" if model_path == FIRE_DRONE_OM_MODEL else "SMARTHOME_YOLO_CONF"
    default = FIRE_DRONE_CONF_THRESHOLD if model_path == FIRE_DRONE_OM_MODEL else YOLO_CONF_THRESHOLD
    try:
        return float(os.getenv(env_name, str(default)))
    except ValueError:
        return default


def _xywh_to_xyxy(boxes: Any) -> Any:
    import numpy as np

    converted = np.copy(boxes)
    converted[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
    converted[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
    converted[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
    converted[:, 3] = boxes[:, 1] + boxes[:, 3] / 2
    return converted


def _numpy_nms(boxes: Any, iou_threshold: float) -> Any:
    import numpy as np

    if boxes.size == 0:
        return boxes
    order = boxes[:, 4].argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        index = int(order[0])
        keep.append(index)
        if order.size == 1:
            break

        current = boxes[index]
        others = boxes[order[1:]]
        xx1 = np.maximum(current[0], others[:, 0])
        yy1 = np.maximum(current[1], others[:, 1])
        xx2 = np.minimum(current[2], others[:, 2])
        yy2 = np.minimum(current[3], others[:, 3])
        intersection = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        current_area = max(0.0, current[2] - current[0]) * max(0.0, current[3] - current[1])
        other_area = np.maximum(0.0, others[:, 2] - others[:, 0]) * np.maximum(0.0, others[:, 3] - others[:, 1])
        union = current_area + other_area - intersection
        iou = intersection / np.maximum(union, 1e-6)
        same_class = others[:, 5] == current[5]
        order = order[1:][~((iou > iou_threshold) & same_class)]
    return boxes[keep]


def _boxes_to_detections(boxes: Any, names: dict[int, str], image_width: int, image_height: int) -> list[dict[str, Any]]:
    detections: list[dict[str, Any]] = []
    for box in boxes:
        x1, y1, x2, y2, confidence, cls_id = [float(value) for value in box[:6]]
        class_id = int(cls_id)
        raw_name = str(names.get(class_id, class_id))
        display_name = DISPLAY_NAMES.get(raw_name, raw_name)
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
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
