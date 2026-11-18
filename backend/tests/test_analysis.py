"""Relative analytics ranges must follow the board clock, not the browser clock."""
import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from service import analysis_service
from utils import db
from utils.db_init import init_db


BOARD_NOW = datetime.fromisoformat('2026-07-10T16:40:00+08:00')


class BoardClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return BOARD_NOW if tz is None else BOARD_NOW.astimezone(tz)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.database_patch = patch.object(db, 'DB_PATH', Path(folder.name) / 'analysis.db')
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        init_db()
        clock = patch.object(analysis_service, 'datetime', BoardClock)
        clock.start()
        self.addCleanup(clock.stop)
        with db.get_connection() as conn:
            for age in [timedelta(minutes=10), timedelta(hours=1), timedelta(hours=26), timedelta(days=8)]:
                timestamp = (BOARD_NOW - age).isoformat(timespec='seconds')
                conn.execute('INSERT INTO sensor_records (temperature,humidity,created_at) VALUES (25,50,?)', (timestamp,))
                conn.execute("INSERT INTO device_logs (device_id,action,source,created_at) VALUES ('door_main','open','remote',?)", (timestamp,))
                conn.execute("INSERT INTO access_logs (person_name,result,created_at) VALUES ('Test','granted',?)", (timestamp,))
                conn.execute("INSERT INTO vision_logs (mode,result_json,created_at) VALUES ('fire_drone','{}',?)", (timestamp,))

    def test_presets_share_board_clock_and_filter_each_dataset(self):
        for window, expected in [(1800, 1), (21600, 2), (86400, 2), (604800, 3)]:
            with self.subTest(window=window):
                result = analysis_service.overview(window_seconds=window)
                self.assertEqual(result['sensors']['raw_count'], expected)
                self.assertEqual(result['devices']['operation_counts']['door_main'], expected)
                self.assertEqual(result['access']['granted'], expected)
                self.assertEqual(result['vision']['mode_counts']['fire_drone'], expected)
                self.assertEqual(datetime.fromisoformat(result['range']['before']), BOARD_NOW)
                self.assertEqual(datetime.fromisoformat(result['range']['after']), BOARD_NOW - timedelta(seconds=window))
                self.assertEqual(result['sensors']['range'], result['devices']['range'])
                self.assertEqual(datetime.fromisoformat(result['server_time']), BOARD_NOW)

    def test_custom_range_remains_explicit_and_data_is_not_rewritten(self):
        result = analysis_service.overview(after='2026-11-17T00:00:00+08:00', before='2026-11-18T00:00:00+08:00', window_seconds=21600)
        self.assertEqual(result['sensors']['raw_count'], 0)
        self.assertEqual(result['summary']['device_logs'], 4)
        result = analysis_service.overview(after='2026-07-10T16:00:00+08:00', before='2026-07-10T17:00:00+08:00')
        self.assertEqual(result['sensors']['raw_count'], 1)
        self.assertEqual(analysis_service.overview()['sensors']['raw_count'], 2)

    def test_api_validates_relative_window(self):
        from app.main import app

        async def request(query):
            messages = []

            async def receive():
                return {'type': 'http.request', 'body': b'', 'more_body': False}

            async def send(message):
                messages.append(message)

            path = '/api/analysis/overview'
            await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                       'method': 'GET', 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
                       'query_string': query.encode(), 'headers': [],
                       'server': ('test', 80), 'client': ('test', 123)}, receive, send)
            return messages[0]['status'], json.loads(b''.join(m.get('body', b'') for m in messages))

        for value in ['-1', '0', '59', '2678401', 'invalid']:
            self.assertEqual(asyncio.run(request('window_seconds='+value))[0], 422)
        status, result = asyncio.run(request('window_seconds=1800'))
        self.assertEqual(status, 200)
        self.assertEqual(result['data']['sensors']['raw_count'], 1)


if __name__ == '__main__':
    unittest.main()
