import base64
import io
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from PIL import Image

from token_tv import times_gate
from token_tv.live import DisplayPreferences, handler
from token_tv.sources import load_config
from token_tv.state import UsageStore


def fixture():
    return {'accounts': {
        'c': {'key': 'c', 'provider': 'claude', 'alias': 'CLAUDE A', 'status': 'ok',
              'windows': [{'label': '5H', 'used_percent': 12, 'resets_at': None},
                          {'label': 'WEEK', 'used_percent': 74, 'resets_at': None}]},
        'x': {'key': 'x', 'provider': 'codex', 'alias': 'CODEX A', 'status': 'stale',
              'windows': [{'label': '5H', 'used_percent': 24, 'resets_at': None},
                          {'label': 'WEEK', 'used_percent': 58, 'resets_at': None}]}}}


class TimesGateTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.current_id = 20
        self.error = 0
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.calls.append((self.path, data))
                reply = {'error_code': owner.error}
                if data['Command'] == 'Channel/GetIndex':
                    reply['SelectIndex'] = [0, 1, 0, 2, 0]
                if data['Command'] == 'Draw/GetHttpGifId':
                    reply['PicId'] = owner.current_id
                if data['Command'] == 'Draw/SendHttpGif' and owner.error == 0:
                    owner.current_id = data['PicID']
                body = json.dumps(reply).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_upload_sends_native_jpeg_to_each_screen_with_increasing_ids(self):
        device = times_gate.TimesGateDisplay(self.url)
        original = device.capture()
        frames = times_gate.render_panels(fixture(), now=1791079200)
        receipts = device.publish(frames, now=100)
        uploads = [d for _, d in self.calls if d['Command'] == 'Draw/SendHttpGif']
        self.assertEqual(len(receipts), 5)
        self.assertEqual([d['PicID'] for d in uploads], [21, 22, 23, 24, 25])
        self.assertTrue(all(path == '/post' for path, _ in self.calls))
        for i, upload in enumerate(uploads):
            self.assertEqual(upload['LcdArray'], [int(j == i) for j in range(5)])
            self.assertEqual((upload['PicNum'], upload['PicOffset'], upload['PicWidth']), (1, 0, 128))
            frame = base64.b64decode(upload['PicData'])
            self.assertEqual(frame, frames[i])
            self.assertEqual(Image.open(io.BytesIO(frame)).size, (128, 128))
        self.assertEqual(device.publish(frames, now=101), [])
        device.restore(original)
        self.assertEqual(self.calls[-1][1], {'Command': 'Channel/SetIndex', 'SelectIndex': [0, 1, 0, 2, 0]})

    def test_reboot_and_periodic_reassertion_recover_unchanged_frames(self):
        device = times_gate.TimesGateDisplay(self.url)
        frames = times_gate.render_panels(fixture(), now=1791079200)
        device.publish(frames, now=100)
        self.current_id = 1  # a real reboot forgets uploaded panels
        self.assertEqual(len(device.publish(frames, now=101)), 5)
        self.assertEqual(len(device.publish(frames, now=402)), 5)
        # Another controller advanced the ID: re-send using a fresh ID.
        self.current_id = 500
        self.assertEqual(len(device.publish(frames, now=403)), 5)
        self.assertGreater(self.current_id, 500)

    def test_device_error_is_not_cached_as_success_and_wrong_backup_is_rejected(self):
        device = times_gate.TimesGateDisplay(self.url)
        original = device.capture()
        self.error = 'busy'
        with self.assertRaises(ValueError):
            device.publish(times_gate.render_panels(fixture()))
        self.error = 0
        self.assertEqual(len(device.publish(times_gate.render_panels(fixture()))), 5)
        with self.assertRaises(ValueError):
            device.restore(dict(original, device_url='http://other-device'))
        for bad in ({}, {'SelectIndex': [0]}, {'SelectIndex': [False] * 5}):
            with self.assertRaises(ValueError):
                device.restore(dict(original, **bad) if bad else {})

    def test_selection_preserves_missing_stale_and_overflow_windows(self):
        data = fixture()
        panels = times_gate.panel_data(data, now=0)
        self.assertEqual([p.get('window', {}).get('used_percent') for p in panels], [12, 74, None, 24, 58])
        self.assertEqual(panels[2]['kind'], 'clock')
        self.assertEqual(panels[3]['row']['status'], 'stale')
        data['accounts']['c'].update(status='identity_mismatch', windows=[])
        panels = times_gate.panel_data(data, now=0)
        self.assertEqual(panels[0]['row']['status'], 'identity_mismatch')
        self.assertIsNone(panels[0].get('window'))
        for key in ('y', 'z'):
            data['accounts'][key] = dict(data['accounts']['x'], key=key, alias=key)
        seen = set()
        for now in (0, 300):
            seen.update(p['row']['key'] for p in times_gate.panel_data(data, now=now) if 'row' in p)
        self.assertEqual(seen, {'c', 'x', 'y', 'z'})

    def test_preview_is_the_same_five_panels_and_config_selects_adapter(self):
        account = {'key': 'c', 'provider': 'claude', 'alias': 'CLAUDE A', 'email': 'test@example.com'}
        store = UsageStore([account])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            config = {'accounts': [account], 'device_type': 'times-gate', 'timezone': 'Europe/London'}
            path.write_text(json.dumps(config))
            prefs = DisplayPreferences(path, load_config(path))
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler(store, prefs))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                root = f'http://127.0.0.1:{server.server_port}'
                with urlopen(root + '/frame/0.jpg') as response:
                    self.assertEqual(Image.open(io.BytesIO(response.read())).size, (640, 128))
                self.assertEqual(prefs.snapshot()['device_type'], 'times-gate')
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
            config['device_type'] = 'wrong'
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                load_config(path)

    def test_renderer_keeps_unknown_distinct_from_zero_and_old_visible(self):
        data = fixture()
        missing = fixture()
        missing['accounts']['c'].update(status='auth_required', windows=[])
        zero = fixture()
        zero['accounts']['c']['windows'][0]['used_percent'] = 0
        old = fixture()
        old['accounts']['c']['status'] = 'stale'
        frames = [times_gate.render_panels(d, style, now=1791079200)[0]
                  for style in ('digital', 'retro') for d in (data, missing, zero, old)]
        self.assertEqual(len(set(frames)), 8)
        for frame in frames:
            image = Image.open(io.BytesIO(frame))
            self.assertEqual((image.format, image.size), ('JPEG', (128, 128)))


if __name__ == '__main__':
    unittest.main()
