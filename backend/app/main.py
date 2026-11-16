from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import router
from utils.db_init import init_db
from service.hardware_service import hardware, HardwareError
from service.camera_service import camera


app = FastAPI(title="SmartHome Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    hardware.restore()


@app.on_event("shutdown")
def on_shutdown() -> None:
    camera.stop()
    hardware.stop()


@app.exception_handler(HardwareError)
async def hardware_exception_handler(request: Request, exc: HardwareError):
    return JSONResponse(status_code=503, content={"ok": False, "message": str(exc), "data": None})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "message": str(exc.detail), "data": None})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"ok": False, "message": "服务器内部错误", "data": None})


@app.get("/health")
def health():
    return {"ok": True, "message": "healthy", "data": None}


app.include_router(router)
