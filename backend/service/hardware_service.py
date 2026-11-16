"""One serial owner for the stock 9600-baud Arduino firmware.

Reports are board software states, not physical position feedback or correlated
ACKs. Commands are never replayed after disconnect/restart.
"""
import json
import os
import logging
import threading
import time
from typing import Any

import serial
from serial.tools import list_ports

from utils.arduino_protocol import ArduinoParser, DEVICE_NAMES, command_for
from utils.db import get_connection
from utils.time_utils import now_iso


class HardwareError(RuntimeError):
    pass


class HardwareService:
    STALE_SECONDS = 12
    BOOT_SECONDS = 2

    def __init__(self, serial_factory=serial.Serial):
        self._factory = serial_factory
        self._condition = threading.Condition(threading.RLock())
        self._command_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._serial = None
        self._port = ""
        self._error = None
        self._connected = False
        self._generation = 0
        self._states = {}
        self._environment = None
        self._last_sample = 0
        self._last_report = None
        self._last_rfid = None

    @staticmethod
    def ports() -> list[dict]:
        if os.environ.get("SMART_HOME_SIMULATOR") == "1":
            return [{"port": "SIMULATOR", "description": "内置 Arduino 模拟器，不连接真实硬件"}]
        return [{"port": p.device, "description": p.description} for p in list_ports.comports()]

    def status(self) -> dict:
        with self._condition:
            fresh = {device: self._connected and time.monotonic() - entry["at"] < self.STALE_SECONDS for device, entry in self._states.items()}
            environment = dict(self._environment or {"temperature": None, "humidity": None, "created_at": None, "light_bright": None})
            environment["fresh"] = bool(self._connected and self._environment and time.monotonic() - self._environment["at"] < self.STALE_SECONDS)
            environment.pop("at", None)
            return {"mode": "simulator" if os.environ.get("SMART_HOME_SIMULATOR") == "1" else "serial", "port": self._port, "baudrate": 9600, "connected": self._connected,
                    "ready": all(fresh.get(device, False) for device in DEVICE_NAMES),
                    "fresh_devices": fresh, "error": self._error, "last_report_at": self._last_report,
                    "environment": environment, "last_rfid": self._last_rfid,
                    "feedback": "board_state", "fan_mode": ("auto" if self._states.get("fan_main", {}).get("state", {}).get("auto_enabled") else "manual") if "auto_enabled" in self._states.get("fan_main", {}).get("state", {}) else "unknown", "fan_threshold": self._states.get("fan_main", {}).get("state", {}).get("auto_threshold"),
                    "auto_close": False}

    def configure(self, port: str, enabled: bool) -> dict:
        if enabled and port not in {entry["port"] for entry in self.ports()}:
            raise ValueError("请选择当前枚举到的设备控制串口；不要选择摄像头串口")
        with self._lifecycle_lock:
            self.stop()
            self._port = port
            self._error = None
            with get_connection() as conn:
                conn.execute("INSERT INTO system_settings (key,value_json,updated_at) VALUES ('serial_settings',?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                             (json.dumps({"port": port, "enabled": enabled}), now_iso()))
            if enabled:
                self._start()
        return self.status()

    def restore(self) -> None:
        if os.environ.get("SMART_HOME_SIMULATOR") == "1":
            self._port = "SIMULATOR"
            self._start()
            return
        with get_connection() as conn:
            row = conn.execute("SELECT value_json FROM system_settings WHERE key='serial_settings'").fetchone()
        if row:
            config = json.loads(row[0])
            self._port = config.get("port", "")
            if config.get("enabled") and self._port:
                self._start()

    def _start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="arduino-serial", daemon=True)
        self._thread.start()

    def _invalidate(self) -> None:
        self._states.clear()
        self._environment = None
        self._last_report = None
        self._generation += 1
        self._condition.notify_all()

    def stop(self) -> None:
        self._stop.set()
        with self._condition:
            self._connected = False
            self._invalidate()
        if self._thread:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise HardwareError("串口线程尚未停止，请稍后重试")
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            port = None
            try:
                port = self._factory(self._port, baudrate=9600, timeout=0.2, write_timeout=1)
                parser = ArduinoParser()
                with self._condition:
                    self._serial = port
                    self._invalidate()
                    self._error = None
                # Many UNO boards reset when the USB port opens. No actuator
                # command is sent while waiting for the board to boot.
                if self._stop.wait(self.BOOT_SECONDS):
                    break
                with self._condition:
                    self._connected = True
                    port.write(b"s")
                while not self._stop.is_set():
                    data = port.read(256)
                    for kind, payload in parser.feed(data):
                        self._consume(kind, payload)
            except Exception as exc:
                logging.getLogger(__name__).warning("Arduino serial: %s", exc)
                with self._condition:
                    self._error = str(exc)
            finally:
                with self._condition:
                    self._connected = False
                    self._serial = None
                    self._invalidate()
                if port:
                    port.close()
            if self._stop.wait(3):
                break

    def _consume(self, kind: str, payload: dict) -> None:
        with self._condition:
            ts = now_iso()
            if kind == "reset":
                self._invalidate()
                return
            self._last_report = ts
            if kind == "environment":
                payload = dict(payload)
                is_sample = payload.pop("sample", True)
                self._environment = {**payload, "created_at": ts, "at": time.monotonic()}
                # Status queries repeat cached sensor values. Sample once per
                # firmware interval, independently of browser polling frequency.
                if is_sample and time.monotonic() - self._last_sample >= 1.9:
                    with get_connection() as conn:
                        conn.execute("INSERT INTO sensor_records (temperature,humidity,created_at) VALUES (?,?,?)", (payload["temperature"], payload["humidity"], ts))
                    self._last_sample = time.monotonic()
            elif kind == "device":
                device_id, state = payload["device_id"], payload["state"]
                previous = self._states.get(device_id)
                if device_id == "fan_main" and previous:
                    state = {**previous["state"], **state}
                with get_connection() as conn:
                    row = conn.execute("SELECT state_json FROM device_states WHERE device_id=?", (device_id,)).fetchone()
                    changed = not row or json.loads(row[0]) != state
                    if changed or not previous:
                        conn.execute("UPDATE device_states SET state_json=?,updated_at=? WHERE device_id=?", (json.dumps(state), ts, device_id))
                    if previous and previous["state"] != state:
                        conn.execute("INSERT INTO device_logs (device_id,action,value_json,source,created_at) VALUES (?,'state_report',?,'hardware',?)", (device_id, json.dumps(state), ts))
                self._states[device_id] = {"state": state, "at": time.monotonic(), "revision": (previous or {}).get("revision", 0) + 1, "updated_at": ts}
            elif kind == "rfid":
                self._last_rfid = {**payload, "created_at": ts}
                granted = payload["granted"]
                with get_connection() as conn:
                    conn.execute("INSERT INTO access_logs (person_name,result,opened_door,created_at) VALUES (?,?,0,?)", (f"RFID {payload['uid'] or '未知卡'}", "rfid_granted" if granted else "rfid_denied", ts))
                    conn.execute("INSERT INTO operation_logs (level,module,message,detail_json,created_at) VALUES (?,'rfid',?,?,?)", ("info" if granted else "warning", "RFID 授权通过，板端执行开门" if granted else "RFID 授权拒绝", json.dumps(payload), ts))
            self._condition.notify_all()

    def control(self, device_id: str, action: str, value: Any = None, source: str = "user", timeout: float = 4) -> dict:
        # One outstanding command makes the legacy unnumbered reports usable.
        if not self._command_lock.acquire(timeout=1):
            raise HardwareError("另一个控制操作正在等待板端状态，请稍后重试")
        try:
            with self._condition:
                entry = self._states.get(device_id, {})
                command, expected = command_for(device_id, action, value, entry.get("state", {}))
                if not self._connected or not entry or time.monotonic() - entry["at"] >= self.STALE_SECONDS:
                    raise HardwareError("硬件离线或尚未收到此设备的新状态，请先在系统配置连接设备控制串口")
                revision, generation = entry["revision"], self._generation
                try:
                    if self._serial.write(command + b"s") != 2:
                        raise HardwareError("串口未完整写入；执行结果未知，请查询板端状态")
                except (serial.SerialException, OSError) as exc:
                    raise HardwareError(f"串口写入失败：{exc}") from exc
                deadline = time.monotonic() + timeout
                while True:
                    if not self._connected or self._generation != generation:
                        raise HardwareError("等待期间硬件断开或重启；执行结果未知，不自动重发")
                    current = self._states.get(device_id, {})
                    if current.get("revision", 0) > revision and all(current["state"].get(key) == val for key, val in expected.items()):
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise HardwareError("未在时限内收到匹配状态；指令可能已执行，请查看板端状态，不自动重发")
                    self._condition.wait(remaining)
                state = dict(current["state"])
                ts = current["updated_at"]
            with get_connection() as conn:
                conn.execute("INSERT INTO device_logs (device_id,action,value_json,source,created_at) VALUES (?,?,?,?,?)", (device_id, action, json.dumps(value), source, ts))
            return {"device_id": device_id, "action": action, "state": state, "updated_at": ts, "command": command.decode(), "feedback": "board_state", "message": "板端状态已更新"}
        finally:
            self._command_lock.release()

    def control_batch(self, commands: list, timeout: float = 5) -> dict:
        """Validate everything before a single write; never retry a batch."""
        if not isinstance(commands, list) or not 1 <= len(commands) <= 4:
            raise ValueError("commands 必须包含 1 至 4 条设备指令")
        seen = set()
        for item in commands:
            if not isinstance(item, dict) or set(item) - {"device_id", "action", "value"}:
                raise ValueError("每条指令仅允许 device_id、action、value 字段")
            device = item.get("device_id")
            if not isinstance(device, str) or not isinstance(item.get("action"), str) or device in seen:
                raise ValueError("设备和动作必须是字符串，且每台设备只能出现一次")
            seen.add(device)
        if not self._command_lock.acquire(timeout=1):
            raise HardwareError("其他操作正在等待状态，请稍后重试")
        try:
            with self._condition:
                prepared = []
                for item in commands:
                    entry = self._states.get(item["device_id"], {})
                    command, expected = command_for(item["device_id"], item["action"], item.get("value"), entry.get("state", {}))
                    if not self._connected or not entry or time.monotonic() - entry["at"] >= self.STALE_SECONDS:
                        raise HardwareError(f"{item['device_id']} 未同步，整组未发送")
                    prepared.append((item, command, expected, entry["revision"]))
                wire = b"".join(item[1] for item in prepared) + b"s"
                generation = self._generation
                written = None
                error = None
                try:
                    written = self._serial.write(wire)
                    if written != len(wire):
                        error = "串口未完整写入，部分动作可能已执行，不自动重发"
                except (serial.SerialException, OSError) as exc:
                    error = f"串口写入异常，执行结果未知：{exc}"
                deadline = time.monotonic() + timeout
                results = []
                while True:
                    connected = self._connected and self._generation == generation
                    results = []
                    for item, command, expected, revision in prepared:
                        current = self._states.get(item["device_id"], {})
                        matched = bool(connected and current.get("revision", 0) > revision and all(current["state"].get(k) == v for k, v in expected.items()))
                        results.append({**item, "command": command.decode(), "confirmed": matched, "state": dict(current.get("state", {}))})
                    if error or not connected or all(item["confirmed"] for item in results):
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        error = "部分设备状态未确认；动作可能已执行，不自动重发"
                        break
                    self._condition.wait(remaining)
                if not connected:
                    error = "等待期间硬件断开或重启，执行结果未知，不自动重发"
                complete = not error and all(item["confirmed"] for item in results)
            with get_connection() as conn:
                for item in results:
                    if item["confirmed"]:
                        conn.execute("INSERT INTO device_logs (device_id,action,value_json,source,created_at) VALUES (?,?,?,'user',?)", (item["device_id"], item["action"], json.dumps(item.get("value")), now_iso()))
            return {"command": wire[:written].decode() if isinstance(written, int) else None,
                    "requested_command": wire.decode(), "bytes_written": written,
                    "complete": complete, "results": results, "feedback": "board_state",
                    "message": "整组板端状态已确认" if complete else error}
        finally:
            self._command_lock.release()


if os.environ.get("SMART_HOME_SIMULATOR") == "1":
    from utils.simulated_arduino import SimulatedArduino
    hardware = HardwareService(SimulatedArduino)
    hardware.BOOT_SECONDS = .05
else:
    hardware = HardwareService()
