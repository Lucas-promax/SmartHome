"""Check the local runtime without changing the database or running inference."""
import importlib
import sys

from utils.db import BACKEND_ROOT, DB_PATH
from utils.runtime import configure_runtime


def main() -> int:
    configure_runtime()
    failed = False
    print(f"Python: {sys.version.split()[0]}")
    for name in (
        "fastapi", "uvicorn", "pydantic", "numpy", "cv2", "torch",
        "torchvision", "ultralytics", "insightface", "onnxruntime", "serial",
    ):
        try:
            module = importlib.import_module(name)
            print(f"OK {name}: {getattr(module, '__version__', 'installed')}")
        except Exception as exc:
            failed = True
            print(f"FAIL {name}: {exc}")
    try:
        from app.main import app
        print(f"OK app: {app.title}")
    except Exception as exc:
        failed = True
        print(f"FAIL app: {exc}")
    print(f"Database: {DB_PATH.relative_to(BACKEND_ROOT).as_posix()} (exists={DB_PATH.exists()})")
    for relative in (
        "models/best.pt", "models/yolov8s.pt", "models/yolov8n.pt",
        "models/buffalo_l/1k3d68.onnx", "models/buffalo_l/2d106det.onnx",
        "models/buffalo_l/det_10g.onnx", "models/buffalo_l/genderage.onnx",
        "models/buffalo_l/w600k_r50.onnx",
    ):
        exists = (BACKEND_ROOT / relative).is_file()
        failed |= not exists
        print(f"{'OK' if exists else 'MISSING'} {relative}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
