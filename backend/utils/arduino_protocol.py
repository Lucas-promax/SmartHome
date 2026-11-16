"""Decoder and command table for the unmodified sketch_jul6b firmware."""
import re
from typing import Any


DEVICE_NAMES = {"light_main": "主灯", "fan_main": "风扇", "door_main": "主门", "garage_main": "车库门"}
LEVELS = (8, 25, 70, 140, 255)


def command_for(device_id: str, action: str, value: Any, state: dict) -> tuple[bytes, dict]:
    if action != 'set_level' and value is not None:
        raise ValueError('此动作不接受 value；请设为 null 或省略')
    if action != 'set_level' and value is not None:
        raise ValueError('此动作不接受 value；请设为 null 或省略')
    table = {
        "light_main": {"turn_on": (b"l", {"power": True, "brightness": 70}), "turn_off": (b"L", {"power": False, "brightness": 0})},
        "fan_main": {"auto_on": (b"v", {"auto_enabled": True}), "auto_off": (b"V", {"auto_enabled": False}), "turn_on": (b"f", {"power": True}), "turn_off": (b"F", {"power": False})},
        "door_main": {"open": (b"d", {"open": True}), "close": (b"D", {"open": False})},
        "garage_main": {"open": (b"g", {"open": True}), "close": (b"G", {"open": False})},
    }
    if device_id not in table:
        raise ValueError("当前固件只支持主灯、风扇、主门和车库门")
    if device_id == "light_main":
        if action == "set_level":
            presets = {"low": (b"A", 8), "middle": (b"B", 70), "high": (b"C", 255)}
            if not isinstance(value, str) or value not in presets:
                raise ValueError("灯档位只能为 low/middle/high")
            command, brightness = presets[value]
            return command, {"power": True, "brightness": brightness}
        if action in {"brighter", "darker"}:
            # Off() retains a hidden level in the firmware; establish a known
            # preset before relative adjustment when that hidden level is unknown.
            if state.get("brightness") not in LEVELS:
                raise ValueError("请先选择低、中或高档，再逐档调节")
            index = LEVELS.index(state["brightness"])
            index = max(0, min(len(LEVELS) - 1, index + (1 if action == "brighter" else -1)))
            return (b"+" if action == "brighter" else b"-"), {"power": True, "brightness": LEVELS[index]}
    if action not in table[device_id]:
        raise ValueError("当前固件不支持此动作；灯光使用档位，风扇仅支持开关，门使用 open/close")
    return table[device_id][action]


class ArduinoParser:
    def __init__(self):
        self.buffer = b""
        self.card_uid = None

    def feed(self, data: bytes) -> list[tuple[str, dict]]:
        self.buffer += data
        events = []
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if len(line) <= 2048:
                events.extend(self.parse_line(line.decode("ascii", errors="replace").strip()))
        if len(self.buffer) > 2048:
            self.buffer = b""  # Bound noise and recover at the next line.
        return events

    def parse_line(self, line: str) -> list[tuple[str, dict]]:
        events = []
        if "Smart Home System (TaskScheduler)" in line:
            self.card_uid = None
            events.append(("reset", {}))
        sensor = re.search(r"Temp:\s*(-?\d+(?:\.\d+)?)\s*(?:C\s*)?Humi:\s*(-?\d+(?:\.\d+)?)\s*(?:%\s*)?Light:\s*(BRIGHT|DARK)", line)
        if sensor:
            temp, humidity = float(sensor[1]), float(sensor[2])
            if -40 <= temp <= 80 and 0 <= humidity <= 100:
                # The stock firmware does not expose the DHT error code.
                events.append(("environment", {"temperature": temp, "humidity": humidity, "light_bright": sensor[3] == "BRIGHT", "sensor_validity": "unreported", "sample": "[Sensor]" not in line}))
        light = re.search(r"\[Light\]\s+On:\s*(true|false)\s+Brightness:\s*(\d+)", line)
        action_light = re.search(r"ACTION: light (ON brightness=(\d+)|OFF)", line)
        if light:
            power, brightness = light[1] == "true", int(light[2])
            if brightness in (0, *LEVELS):
                events.append(("device", {"device_id": "light_main", "state": {"power": power, "brightness": brightness}}))
        elif action_light:
            brightness = int(action_light[2] or 0)
            if brightness in (0, *LEVELS):
                events.append(("device", {"device_id": "light_main", "state": {"power": action_light[1] != "OFF", "brightness": brightness}}))
        fan = re.search(r"ACTION: fan (ON|OFF)|\[Fan\]\s+Running:\s*(true|false)", line)
        if fan:
            events.append(("device", {"device_id": "fan_main", "state": {"power": fan[1] == "ON" or fan[2] == "true"}}))
        mode = re.search(r"\[Fan\].*Auto:\s*(true|false)\s+AutoOnAt:\s*(\d+(?:\.\d+)?)C", line)
        if mode:
            for kind, payload in events:
                if kind == "device" and payload.get("device_id") == "fan_main":
                    payload["state"].update(auto_enabled=mode[1] == "true", auto_threshold=float(mode[2]))
        doors = re.search(r"\[Door\]\s+Main:\s*(OPEN|CLOSED)\s+Garage:\s*(OPEN|CLOSED)", line)
        if doors:
            for device, position in (("door_main", doors[1]), ("garage_main", doors[2])):
                events.append(("device", {"device_id": device, "state": {"open": position == "OPEN"}}))
        action_door = re.search(r"ACTION: (main door|garage) (OPEN|CLOSE)", line)
        if action_door:
            events.append(("device", {"device_id": "door_main" if action_door[1] == "main door" else "garage_main", "state": {"open": action_door[2] == "OPEN"}}))
        uid = re.search(r"^Card UID:((?:\s+[0-9A-Fa-f]{2})+)$", line)
        if uid:
            self.card_uid = "".join(uid[1].split()).upper()
        if line in {"RFID Access Granted", "RFID Access Denied"}:
            events.append(("rfid", {"uid": self.card_uid, "granted": line.endswith("Granted")}))
            self.card_uid = None
        return events
