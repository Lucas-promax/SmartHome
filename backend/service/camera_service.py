"""Independent OV7670 reader: progressive preview and separate complete JPEG."""
import base64
import threading
import time
import uuid

import cv2
import serial
from serial.tools import list_ports

from utils.ov7670_protocol import OV7670Parser


class CameraService:
    FRESH_SECONDS = 10

    def __init__(self, serial_factory=serial.Serial):
        self._factory = serial_factory
        self._lock = threading.RLock()
        self._lifecycle = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.session = ""
        self.port = ""
        self.connected = False
        self.error = None
        self._frame = None
        self._frame_id = 0
        self._at = 0
        self._preview = None
        self._preview_id = 0
        self._preview_at = 0

    @staticmethod
    def ports():
        return [{"port": p.device, "description": p.description} for p in list_ports.comports()]

    def connect(self, port, baudrate):
        with self._lifecycle:
            self._close()
            with self._lock:
                self.session = uuid.uuid4().hex
                self.port = port
                self.error = None
                self._stop.clear()
                self._thread = threading.Thread(target=self._run, args=(port, baudrate), daemon=True)
                self._thread.start()
                return {"session": self.session}

    def _close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
            if self._thread.is_alive():
                raise ValueError("摄像头串口尚未关闭，请稍后重试")
        with self._lock:
            self._thread = None
            self.connected = False
            self.session = ""
            self.port = ""
            self._frame = None
            self._at = 0
            self._preview = None
            self._preview_at = 0

    def stop(self, session=None):
        with self._lifecycle:
            if session is None or session == self.session:
                self._close()

    def latest(self, session, after=0, preview_after=0):
        with self._lock:
            if session != self.session or not session:
                raise ValueError("摄像头连接已结束或已被其他页面替换")
            age = time.monotonic() - self._at if self._at else None
            fresh = self.connected and self._frame is not None and age < self.FRESH_SECONDS
            preview_fresh = self.connected and self._preview is not None and time.monotonic() - self._preview_at < self.FRESH_SECONDS
            return {"connected": self.connected, "fresh": bool(fresh), "error": self.error,
                    "frame_id": self._frame_id, "age_seconds": age,
                    "data_url": self._frame if fresh and self._frame_id != after else None,
                    "preview_id": self._preview_id, "preview_fresh": bool(preview_fresh),
                    "preview": self._preview if preview_fresh and self._preview_id != preview_after else None}

    @staticmethod
    def _jpeg(frame, quality=95):
        success, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii") if success else None

    def _publish_preview(self, image, rows, height):
        self._preview = {"data_url": image, "rows": rows, "height": height}
        self._preview_id += 1
        self._preview_at = time.monotonic()

    def _run(self, port, baudrate):
        try:
            with self._factory(port, baudrate=baudrate, timeout=0.05) as conn:
                with self._lock:
                    self.connected = True
                parser = OV7670Parser()
                last_preview = 0
                preview_position = None
                while not self._stop.is_set():
                    # Read binary chunks, never readline(): pixels may contain LF.
                    # Drain available bytes promptly; wait only for the first byte.
                    size = min(16384, max(1, getattr(conn, "in_waiting", 2048)))
                    for frame in parser.feed(conn.read(size)):
                        image = self._jpeg(frame)
                        if image:
                            with self._lock:
                                self._frame = image
                                self._frame_id += 1
                                self._at = time.monotonic()
                                self._publish_preview(image, frame.shape[0], frame.shape[0])
                            last_preview = time.monotonic()
                    # Limit JPEG work to ~8 updates/sec without slowing serial reads.
                    if time.monotonic() - last_preview >= 0.12:
                        preview = parser.preview()
                        if preview is not None:
                            frame, rows, height = preview
                            position = (parser.frame_number, rows)
                            if position != preview_position:
                                image = self._jpeg(frame, 85)
                                if image:
                                    with self._lock:
                                        self._publish_preview(image, rows, height)
                                    preview_position = position
                        last_preview = time.monotonic()
        except Exception as exc:
            with self._lock:
                self.error = str(exc)
        finally:
            with self._lock:
                self.connected = False
                self._frame = None
                self._preview = None


camera = CameraService()
