"""Protocol fixtures match LiveOV7670's wire bytes; no physical serial port."""
import base64
import asyncio
import json
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
import queue
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from service.camera_service import CameraService
from utils.ov7670_protocol import OV7670Parser


def command(payload):
    checksum = 0
    for b in payload:
        checksum ^= b
    return bytes([0, len(payload), *payload, checksum])


def header(w=2, h=1, fmt=1):
    return command([0x11, w & 255, h & 255,
                    ((w >> 8) & 3) | ((h >> 6) & 12) | (fmt << 4)])


# RGB565 modified by firmware parity bits: red then blue.
RGB = header() + bytes([0xF0, 0x01, 0x08, 0x3F])


class ParserTests(unittest.TestCase):
    def test_rgb_all_split_positions(self):
        for split in range(len(RGB) + 1):
            parser = OV7670Parser()
            frames = parser.feed(RGB[:split]) + parser.feed(RGB[split:])
            self.assertEqual(len(frames), 1)
            np.testing.assert_array_equal(frames[0], [[[8, 0, 240], [248, 4, 8]]])

    def test_gray_byte_by_byte_and_debug(self):
        parser = OV7670Parser()
        frames = []
        wire = header(fmt=2) + command([0x13, 65, 66]) + bytes([10, 255])
        for b in wire:
            frames.extend(parser.feed(bytes([b])))
        np.testing.assert_array_equal(frames[0], [[10, 255]])

    def test_corruption_truncation_and_resync(self):
        parser = OV7670Parser()
        bad_checksum = bytearray(header())
        bad_checksum[-1] ^= 1
        self.assertEqual(parser.feed(bad_checksum + b'noise'), [])
        self.assertEqual(parser.feed(header() + b'\xF0'), [])
        self.assertEqual(parser.feed(header() + b'\x01\x01\x01\x01'), [])
        self.assertEqual(len(parser.feed(RGB + RGB)), 2)
        self.assertEqual(parser.feed(header(1023, 1023) + b'noise'), [])

    def test_large_frame_random_chunks(self):
        wire = header(320, 240) + bytes([0xF0, 0x01]) * (320 * 240)
        parser = OV7670Parser()
        frames = []
        for i in range(0, len(wire), 137):
            frames.extend(parser.feed(wire[i:i + 137]))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].shape, (240, 320, 3))

    def test_progressive_rows_are_not_complete_frames(self):
        parser = OV7670Parser()
        row = bytes([0xF0, 0x01, 0x08, 0x3F])
        self.assertEqual(parser.feed(header(2, 3) + row + row[:1]), [])
        image, rows, height = parser.preview()
        self.assertEqual((rows, height), (1, 3))
        np.testing.assert_array_equal(image[0], [[8, 0, 240], [248, 4, 8]])
        self.assertFalse(image[1:].any())
        self.assertEqual(parser.feed(row[1:]), [])
        self.assertEqual(parser.preview()[1], 2)
        frames = parser.feed(row)
        self.assertEqual(len(frames), 1)
        self.assertIsNone(parser.preview())
        self.assertTrue(frames[0][2].any())

    def test_gray_preview_and_corrupted_row(self):
        parser = OV7670Parser()
        self.assertEqual(parser.feed(header(2, 2, 2) + bytes([10, 255])), [])
        np.testing.assert_array_equal(parser.preview()[0], [[10, 255], [0, 0]])
        self.assertEqual(parser.feed(bytes([11, 254])), [])
        self.assertIsNone(parser.preview())
        self.assertEqual(len(parser.feed(RGB)), 1)


class ServiceTests(unittest.TestCase):
    def test_progressive_preview_keeps_capture_complete(self):
        chunks = queue.Queue()

        class Serial:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, size):
                try:
                    return chunks.get(timeout=0.03)
                except queue.Empty:
                    return b''

        camera = CameraService(Serial)
        session = camera.connect('CAM', 500000)['session']

        def wait_for(predicate):
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                result = camera.latest(session)
                if predicate(result):
                    return result
                time.sleep(0.01)
            self.fail('Timed out waiting for preview/frame')

        row = bytes([0xF0, 0x01, 0x08, 0x3F])
        try:
            chunks.put(header(2, 3) + row)
            partial = wait_for(lambda r: r['preview'] and r['preview']['rows'] == 1)
            self.assertFalse(partial['fresh'])
            self.assertIsNone(partial['data_url'])
            self.assertIsNone(camera.latest(session, preview_after=partial['preview_id'])['preview'])
            chunks.put(row)
            wait_for(lambda r: r['preview'] and r['preview']['rows'] == 2)
            self.assertIsNone(camera.latest(session)['data_url'])
            chunks.put(row)
            complete = wait_for(lambda r: r['fresh'])
            chunks.put(header(2, 3) + row)
            next_partial = wait_for(lambda r: r['preview'] and r['preview']['rows'] == 1)
            self.assertEqual(next_partial['frame_id'], complete['frame_id'])
            self.assertEqual(next_partial['data_url'], complete['data_url'])
            camera._preview_at -= 11
            self.assertFalse(camera.latest(session)['preview_fresh'])
            self.assertIsNone(camera.latest(session)['preview'])
        finally:
            camera.stop(session)

    def test_jpeg_freshness_disconnect_and_session_ownership(self):
        closed = threading.Event()

        class Serial:
            def __init__(self, *args, **kwargs):
                self.data = RGB

            def __enter__(self):
                return self

            def __exit__(self, *args):
                closed.set()

            def read(self, size):
                time.sleep(0.01)
                data, self.data = self.data, b''
                return data

        camera = CameraService(Serial)
        session = camera.connect('CAM', 500000)['session']
        try:
            deadline = time.monotonic() + 2
            while not camera.latest(session)['fresh'] and time.monotonic() < deadline:
                time.sleep(0.01)
            frame = camera.latest(session)
            self.assertTrue(frame['fresh'])
            jpeg = base64.b64decode(frame['data_url'].split(',')[1])
            self.assertEqual(cv2.imdecode(np.frombuffer(jpeg, np.uint8), 1).shape, (1, 2, 3))
            self.assertIsNone(camera.latest(session, frame['frame_id'])['data_url'])
            camera._at -= 11
            self.assertFalse(camera.latest(session)['fresh'])
            self.assertIsNone(camera.latest(session)['data_url'])
            camera.stop('old-session')
            self.assertTrue(camera.connected)
        finally:
            camera.stop(session)
        self.assertTrue(closed.is_set())
        with self.assertRaises(ValueError):
            camera.latest(session)

    def test_open_failure(self):
        def fail(*args, **kwargs):
            raise OSError('unplugged')
        camera = CameraService(fail)
        session = camera.connect('CAM', 500000)['session']
        camera._thread.join(2)
        self.assertFalse(camera.latest(session)['connected'])
        self.assertEqual(camera.latest(session)['error'], 'unplugged')
        camera.stop()


class ApiTests(unittest.TestCase):
    def test_ports_control_conflict_validation_and_database_init(self):
        from app.main import app
        from app import routers
        from utils import db
        from utils.db_init import init_db
        with tempfile.TemporaryDirectory() as folder, patch.object(db, 'DB_PATH', Path(folder) / 'test.db'):
            init_db()
            # Exercise the ASGI app without adding an httpx test dependency.
            class Client:
                def get(self, path):
                    return self.request("GET", path)

                def post(self, path, json):
                    return self.request("POST", path, json)

                def request(self, method, path, payload=None):
                    async def invoke():
                        messages = []
                        async def receive():
                            return {"type": "http.request", "body": json.dumps(payload).encode() if payload else b"", "more_body": False}
                        async def send(message):
                            messages.append(message)
                        url, _, query = path.partition("?")
                        await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                                   "method": method, "scheme": "http", "path": url, "raw_path": url.encode(),
                                   "query_string": query.encode(), "headers": [(b"content-type", b"application/json")],
                                   "server": ("test", 80), "client": ("test", 123)}, receive, send)
                        body = b"".join(m.get("body", b"") for m in messages)
                        return SimpleNamespace(status_code=messages[0]["status"], json=lambda: json.loads(body))
                    return asyncio.run(invoke())
            client = Client()
            with patch.object(routers.hardware, 'status', return_value={'port': 'COM1'}), \
                 patch.object(routers.camera, 'ports', return_value=[{'port': 'COM1'}, {'port': 'COM2'}]):
                self.assertEqual(client.get('/api/camera/ports').json()['data'], [{'port': 'COM2'}])
                self.assertEqual(client.post('/api/camera/connect', json={'port': 'COM1'}).status_code, 400)
                self.assertEqual(client.post('/api/camera/connect', json={'port': 'COM3'}).status_code, 400)
                self.assertEqual(client.post('/api/camera/connect', json={'port': 'COM2', 'baudrate': 9600}).status_code, 422)
                with patch.object(routers.camera, 'connect', return_value={'session': 'abc'}) as connect:
                    response = client.post('/api/camera/connect', json={'port': 'COM2'})
                    self.assertEqual(response.json()['data']['session'], 'abc')
                    connect.assert_called_once_with('COM2', 500000)
                self.assertEqual(client.get('/api/camera/frame?session=missing').status_code, 409)


if __name__ == '__main__':
    unittest.main()
