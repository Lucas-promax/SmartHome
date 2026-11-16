"""Keep library configuration and caches inside the project."""
import os
from pathlib import Path


def configure_runtime() -> None:
    project_root = Path(__file__).resolve().parents[2]
    # Respect explicit overrides while avoiding machine-specific user directories.
    for name, folder in (
        ("YOLO_CONFIG_DIR", "ultralytics"),
        ("MPLCONFIGDIR", "matplotlib"),
    ):
        directory = os.environ.setdefault(name, str(project_root / ".tools" / folder))
        Path(directory).mkdir(parents=True, exist_ok=True)
