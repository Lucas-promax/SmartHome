"""Legacy firmware protocol and control failure tests; no physical port used."""
import asyncio
import tempfile
import threading
import time
import unittest
import queue
from pathlib import Path
from unittest.mock import patch

from service.hardware_service import HardwareService, HardwareError
from service import home_service, vision_service
from utils import db
from utils.arduino_protocol import ArduinoParser, command_for
from utils.db_init import init_db


class ParserTests(unittest.TestCase):
    def test_auto_temperature_commands_and_feedback(self):
        from utils.simulated_arduino import SimulatedArduino
        simulator = SimulatedArduino()
        parser = ArduinoParser()
        self.assertEqual(command_for('fan_main', 'auto_on', None, {}), (b'v', {'auto_enabled': True}))
        self.assertEqual(command_for('fan_main', 'auto_off', None, {}), (b'V', {'auto_enabled': False}))
        simulator.write(b'Vf')
        events = parser.feed(simulator.read(256))
        fan = next(p['state'] for kind, p in events if kind == 'device' and p['device_id'] == 'fan_main')
        self.assertEqual(fan, {'power': True, 'auto_enabled': False, 'auto_threshold': 25.0})
        simulator.write(b'v')
        events = parser.feed(simulator.snapshot())
        self.assertTrue(next(p['state']['auto_enabled'] for kind, p in events if kind == 'device' and p['device_id'] == 'fan_main'))

    def test_builtin_simulator_uses_original_protocol(self):
        from utils.simulated_arduino import SimulatedArduino
        simulator = SimulatedArduino()
        parser = ArduinoParser()
        events = parser.feed(simulator.read(256))
        self.assertIn('environment', [kind for kind, _ in events])
        simulator.write(b'dCs')
        events = []
        while not simulator.queue.empty():
            events.extend(parser.feed(simulator.read(256)))
        self.assertTrue(any(p.get('device_id') == 'door_main' and p['state']['open'] for _, p in events))
        self.assertTrue(any(p.get('device_id') == 'light_main' and p['state']['brightness'] == 255 for _, p in events))
    def test_chunked_sensor_concatenated_with_action(self):
        parser = ArduinoParser()
        self.assertEqual(parser.feed(b'Temp: 28.0  Hu'), [])
        events = parser.feed(b'mi: 56.0  Light: BRIGHTACTION: fan OFF\r\n')
        self.assertEqual([kind for kind, _ in events], ['environment', 'device'])
        self.assertEqual(events[0][1]['temperature'], 28)
        self.assertEqual(events[1][1]['state'], {'power': False})

    def test_status_rfid_and_noise(self):
        parser = ArduinoParser()
        data = b'[Sensor] Temp: 28.0 C  Humi: 56.0 %  Light: DARK\n[Light]  On: true  Brightness: 140\n[Door]   Main: OPEN  Garage: CLOSED\nCard UID: 90 7D 5D 54\nRFID Access Granted\n'
        events = parser.feed(data)
        self.assertFalse(events[0][1]['sample'])
        self.assertEqual(events[-1], ('rfid', {'uid': '907D5D54', 'granted': True}))
        self.assertEqual(parser.feed(b'[RFID] LastCard: 90 7D 5D 54 Authorized: YES\n'), [])
        self.assertEqual(parser.feed(b'Temp: -1 Humi: -1 Light: DARK\n'), [])
        parser.feed(b'x' * 3000)
        self.assertLessEqual(len(parser.buffer), 2048)

    def test_exact_command_whitelist(self):
        self.assertEqual(command_for('door_main', 'open', None, {})[0], b'd')
        self.assertEqual(command_for('garage_main', 'close', None, {})[0], b'G')
        self.assertEqual(command_for('light_main', 'brighter', None, {'brightness': 70})[1]['brightness'], 140)
        for device, action, value in [('window_main', 'open', None), ('fan_main', 'set_speed', 2), ('light_main', 'set_brightness', 50), ('light_main', 'set_level', []), ('light_main', 'brighter', None)]:
            with self.assertRaises(ValueError):
                command_for(device, action, value, {})


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_patch = patch.object(db, 'DB_PATH', Path(self.temp.name) / 'test.db')
        self.database_patch.start()
        init_db()
        with db.get_connection() as conn:
            conn.execute("INSERT INTO persons (name,created_at,updated_at) VALUES ('Test','2026-11-14','2026-11-14')")
        self.hardware = HardwareService()
        self.hardware._connected = True
        self.parser = ArduinoParser()
        self.feed(b'[Light] On: false Brightness: 0\n[Fan] Running: false\n[Door] Main: CLOSED Garage: CLOSED\n')

    def tearDown(self):
        self.database_patch.stop()
        self.temp.cleanup()

    def feed(self, data):
        for kind, payload in self.parser.feed(data):
            self.hardware._consume(kind, payload)

    def count(self, table):
        with db.get_connection() as conn:
            return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def test_telemetry_no_get_sampling_or_duplicate_state_logs(self):
        self.feed(b'Temp: 25.0 Humi: 50.0 Light: DARKACTION: fan OFF\n')
        self.feed(b'[Sensor] Temp: 25.0 C Humi: 50.0 % Light: DARK\n')
        with patch.object(home_service, 'hardware', self.hardware):
            for _ in range(3):
                data = home_service.get_home_status()
                self.assertEqual(data['environment']['temperature'], 25)
        self.assertEqual(self.count('sensor_records'), 1)
        self.assertEqual(self.count('device_logs'), 0)

    def test_confirmed_control_and_no_speculative_update(self):
        service = self.hardware
        test = self
        class FakeSerial:
            def write(self, data):
                test.assertEqual(data, b'ds')
                def respond():
                    time.sleep(.02)
                    test.feed(b'ACTION: main door OPEN\n')
                self.worker = threading.Thread(target=respond)
                self.worker.start()
                return len(data)
        service._serial = FakeSerial()
        result = service.control('door_main', 'open', timeout=.5)
        service._serial.worker.join()
        self.assertTrue(result['state']['open'])
        self.assertEqual(result['feedback'], 'board_state')

    def test_timeout_does_not_change_state_or_retry(self):
        writes = []
        class SilentSerial:
            def write(self, data):
                writes.append(data)
                return len(data)
        self.hardware._serial = SilentSerial()
        with self.assertRaises(HardwareError):
            self.hardware.control('door_main', 'open', timeout=.02)
        self.assertEqual(writes, [b'ds'])
        self.assertFalse(self.hardware._states['door_main']['state']['open'])
        self.assertEqual(self.count('device_logs'), 0)

    def test_batch_one_write_and_preflight_validation(self):
        writes = []
        commands = [{'device_id': device, 'action': action, 'value': value} for device, action, value in [('door_main', 'open', None), ('garage_main', 'open', None), ('fan_main', 'turn_on', None), ('light_main', 'set_level', 'low')]]
        test = self
        class BatchSerial:
            def write(self, data):
                writes.append(data)
                self.worker = threading.Thread(target=lambda: test.feed(b'ACTION: main door OPEN\nACTION: garage OPEN\nACTION: fan ON\nACTION: light ON brightness=8\n'))
                self.worker.start()
                return len(data)
        self.hardware._serial = BatchSerial()
        result = self.hardware.control_batch(commands, timeout=.5)
        self.hardware._serial.worker.join()
        self.assertEqual(writes, [b'dgfAs'])
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['results']), 4)
        with self.assertRaises(ValueError):
            self.hardware.control_batch([commands[0], {'device_id': 'fan_main', 'action': 'set_speed', 'value': 2}])
        self.assertEqual(writes, [b'dgfAs'])

    def test_batch_partial_timeout_no_retry(self):
        writes = []
        class SilentSerial:
            def write(self, data):
                writes.append(data)
                return len(data)
        self.hardware._serial = SilentSerial()
        result = self.hardware.control_batch([{'device_id': 'door_main', 'action': 'open'}, {'device_id': 'garage_main', 'action': 'close'}], timeout=.02)
        self.assertFalse(result['complete'])
        self.assertEqual(writes, [b'dGs'])
        self.assertFalse(any(item['confirmed'] for item in result['results']))

    def test_offline_stale_and_reset_block_control(self):
        self.hardware._states['door_main']['at'] = time.monotonic() - 20
        with self.assertRaises(HardwareError):
            self.hardware.control('door_main', 'open')
        self.feed(b'  Smart Home System (TaskScheduler)\n')
        self.assertFalse(self.hardware.status()['ready'])
        with self.assertRaises(HardwareError):
            self.hardware.control('door_main', 'open')
        self.hardware.stop()
        self.assertFalse(self.hardware.status()['connected'])

    def test_rfid_local_event_does_not_send_another_open(self):
        self.feed(b'Card UID: 90 7D 5D 54\nRFID Access Granted\nACTION: main door OPEN\n')
        self.feed(b'[RFID] LastCard: 90 7D 5D 54 Authorized: YES\n')
        self.assertEqual(self.count('access_logs'), 1)
        self.assertTrue(self.hardware.status()['last_rfid']['granted'])
        self.assertTrue(self.hardware._states['door_main']['state']['open'])

    def test_face_authorized_but_serial_failure_not_reported_as_open(self):
        from fastapi import UploadFile
        import io
        reference = {'id': 1, 'name': 'Test', 'role': 'resident', 'enabled': True, 'authorized': True, 'source': 'test', 'similarity': .9}
        with patch.object(vision_service, '_load_face_app', return_value=object()), patch.object(vision_service, '_extract_face_embedding', return_value=object()), patch.object(vision_service, '_load_face_references', return_value=[reference]), patch.object(vision_service, '_match_face', return_value=reference), patch.object(vision_service, '_unlock_door_by_face', side_effect=HardwareError('offline')), patch.object(vision_service, 'save_snapshot', return_value={'image_path': 'test.jpg'}):
            result = asyncio.run(vision_service.face_recognize(UploadFile(io.BytesIO(b'test'), filename='test.jpg')))
        self.assertFalse(result['opened_door'])
        self.assertEqual(result['result'], 'control_failed')

    def test_serial_worker_connect_control_disconnect(self):
        packets = queue.Queue()
        writes = []
        closed = threading.Event()
        class FakeSerial:
            def __init__(self, *args, **kwargs):
                pass
            def write(self, data):
                writes.append(data)
                if data == b's':
                    packets.put(b'[Light] On: false Brightness: 0\n[Fan] Running: false\n[Door] Main: CLOSED Garage: CLOSED\n')
                elif data == b'ds':
                    packets.put(b'ACTION: main door OPEN\n')
                return len(data)
            def read(self, size):
                try:
                    return packets.get(timeout=.01)
                except queue.Empty:
                    return b''
            def close(self):
                closed.set()
        worker = HardwareService(FakeSerial)
        worker.BOOT_SECONDS = .01
        try:
            with patch.object(worker, 'ports', return_value=[{'port': 'SIM1'}]):
                worker.configure('SIM1', True)
            deadline = time.monotonic() + 1
            while not worker.status()['ready'] and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(worker.status()['ready'])
            self.assertTrue(worker.control('door_main', 'open')['state']['open'])
        finally:
            worker.stop()
        self.assertTrue(closed.is_set())
        self.assertEqual(writes, [b's', b'ds'])
        self.assertFalse(worker.status()['connected'])


if __name__ == '__main__':
    unittest.main()
