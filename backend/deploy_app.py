"""Serve the built frontend and API together on the board, over one SSH tunnel."""
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.main import app


FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
# API routes are registered before the static mount. Vue uses hash routing.
app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
