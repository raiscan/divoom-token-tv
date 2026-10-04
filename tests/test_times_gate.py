import base64
import io
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen, Request
from urllib.error import HTTPError

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
        delay = patch('token_tv.times_gate.time.sleep')
        delay.start()
        self.addCleanup(delay.stop)
        self.calls = []
        self.current_id = 20
        self.error = 0
        self.reject_offset = None
        self.frame_errors = []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.calls.append((self.path, data))
                reply = {'error_code': owner.error}
                if data['Command'] == 'Draw/SendHttpGif' and data['PicOffset'] == owner.reject_offset:
                    reply['error_code'] = 'busy'
                if data['Command'] == 'Draw/SendHttpGif' and owner.frame_errors:
                    reply['error_code'] = owner.frame_errors.pop(0)
                if data['Command'] == 'Channel/GetIndex':
                    reply['SelectIndex'] = [0, 1, 0, 2, 0]
                if data['Command'] == 'Draw/GetHttpGifId':
                    reply['PicId'] = owner.current_id
                if data['Command'] == 'Draw/SendHttpGif' and reply['error_code'] == 0:
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

    def test_animation_uses_one_id_per_panel_and_retries_partial_upload(self):
        output = io.BytesIO()
        Image.new('RGB', (128, 128), 'red').save(output, format='GIF', save_all=True,
            append_images=[Image.new('RGB', (128, 128), 'blue')], duration=200, loop=0)
        frames = times_gate.render_panels(fixture(), now=1791079200)
        frames[0] = output.getvalue()
        device = times_gate.TimesGateDisplay(self.url)
        self.reject_offset = 1
        with self.assertRaises(ValueError):
            device.publish(frames)
        self.reject_offset = None
        self.calls.clear()
        self.assertEqual(len(device.publish(frames)), 5)
        uploads = [d for _, d in self.calls if d['Command'] == 'Draw/SendHttpGif']
        self.assertEqual(len(uploads), 6)
        self.assertEqual([d['PicOffset'] for d in uploads[:2]], [0, 1])
        self.assertEqual([d['PicNum'] for d in uploads[:2]], [2, 2])
        self.assertEqual([d['PicSpeed'] for d in uploads[:2]], [200, 200])
        self.assertEqual(uploads[0]['PicID'], uploads[1]['PicID'])
        self.assertGreater(uploads[2]['PicID'], uploads[1]['PicID'])
        self.assertEqual(device.publish(frames), [])

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

    def test_transient_frame_retries_keep_exact_payload_and_require_numeric_ack(self):
        frames = times_gate.render_panels(fixture(), now=1791079200)
        device = times_gate.TimesGateDisplay(self.url)
        self.frame_errors = ['Request data illegal json', 0]
        with patch('token_tv.times_gate.time.sleep') as pause:
            self.assertEqual(len(device.publish(frames)), 5)
        self.assertEqual([call.args for call in pause.call_args_list],[(.25,), *[(.1,)]*5])
        uploads = [data for _, data in self.calls if data['Command'] == 'Draw/SendHttpGif']
        self.assertEqual(uploads[0], uploads[1])
        self.assertEqual(len(uploads), 6)
        device = times_gate.TimesGateDisplay(self.url)
        original = device.request
        sent = []
        def interrupted(path, data=None, headers=None):
            if json.loads(data)['Command'] == 'Draw/SendHttpGif':
                sent.append(data)
                if len(sent) == 1:
                    raise ConnectionResetError('synthetic interruption')
                if len(sent) == 2:
                    raise TimeoutError('synthetic timeout')
            return original(path, data, headers)
        with patch.object(device, 'request', side_effect=interrupted), patch('token_tv.times_gate.time.sleep'):
            self.assertEqual(len(device.publish(frames)), 5)
        self.assertEqual(sent[0], sent[1])
        self.assertEqual(sent[0], sent[2])

    def test_frame_retries_are_bounded_and_never_cache_a_partial_animation(self):
        frames = times_gate.render_panels(fixture(), now=1791079200)
        device = times_gate.TimesGateDisplay(self.url)
        self.frame_errors = ['Request data illegal json'] * 3
        with patch('token_tv.times_gate.time.sleep') as pause:
            with self.assertRaises(ValueError):
                device.publish(frames)
        uploads = [data for _, data in self.calls if data['Command'] == 'Draw/SendHttpGif']
        self.assertEqual(len(uploads), 3)
        self.assertEqual(pause.call_count, 2)
        self.assertEqual(device.sent, {})
        self.assertEqual(len(device.publish(frames)), 5)
        # Authentication errors and unknown responses stay hard failures.
        for error in ('DeviceToken is err', 'busy', '0', False):
            self.frame_errors = [error]
            with patch('token_tv.times_gate.time.sleep') as pause:
                with self.assertRaises(ValueError):
                    times_gate.TimesGateDisplay(self.url).publish(frames)
                pause.assert_not_called()

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

    def test_four_screens_reserve_fifth_across_animation_reboot_and_refresh(self):
        device = times_gate.TimesGateDisplay(self.url, panels=(1, 2, 3, 4),
                                            weather_clock=182, independence=189009)
        frames = times_gate.render_panels(fixture(), 'space', now=1791079200)
        for now, reset in ((100, None), (101, None), (102, 1), (403, None)):
            self.calls.clear()
            if reset is not None:
                self.current_id = reset
            receipts = device.publish(frames, now=now)
            uploads = [d for _, d in self.calls if d['Command'] == 'Draw/SendHttpGif']
            self.assertTrue(all(d['LcdArray'][4] == 0 and sum(d['LcdArray']) == 1 for d in uploads))
            self.assertTrue(all(r['panel'] in (1, 2, 3, 4) for r in receipts))
            weather = [d for _, d in self.calls if d['Command'] == 'Channel/SetClockSelectId']
            self.assertEqual(len(weather), int(now != 101))
            if weather:
                self.assertEqual(weather[0], {'Command': 'Channel/SetClockSelectId', 'ClockId': 182,
                                             'LcdIndex': 4, 'LcdIndependence': 189009})
        with self.assertRaises(ValueError):
            times_gate.TimesGateDisplay(self.url, weather_clock=182, independence=189009)

    def test_local_token_is_validated_saved_privately_and_omitted_from_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'token.json'
            device = times_gate.TimesGateDisplay(self.url, panels=(1, 2, 3, 4), token_file=path)
            device.save_token(123456)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            reloaded = times_gate.TimesGateDisplay(self.url, token_file=path)
            reloaded.capture()
            self.assertEqual(self.calls[-1][1]['LocalToken'], 123456)
            receipts = device.publish(times_gate.render_panels(fixture()))
            self.assertNotIn('LocalToken', json.dumps(receipts))
            self.error = 'DeviceToken is err'
            with self.assertRaises(times_gate.LocalTokenRequired):
                device.save_token(987654)
            self.assertEqual(device.local_token, 123456)
            self.assertEqual(json.loads(path.read_text()), {'local_token': 123456})
            for bad in (True, '123456', -1, 2147483648, None):
                with self.assertRaises(ValueError):
                    device.save_token(bad)

    def test_token_entry_endpoint_never_exposes_secret_and_rejects_cross_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            device = times_gate.TimesGateDisplay(self.url, panels=(1, 2, 3, 4),
                                                token_file=Path(directory) / 'secret.json')
            prefs = DisplayPreferences(Path(directory) / 'metadata.json',
                                       {'device_type': 'times-gate', 'device_url': self.url}, device)
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler(UsageStore([]), prefs))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            root = f'http://127.0.0.1:{server.server_port}'
            try:
                headers = {'Content-Type': 'application/json', 'Origin': 'https://other.example'}
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(root + '/display/token', b'{"local_token":654321}', headers))
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
                self.assertFalse(device.token_file.exists())
                headers.update(Origin='http://other.example', Host='other.example')
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(root + '/display/token', b'{"local_token":654321}', headers))
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
                headers.pop('Host')
                headers['Origin'] = root
                with urlopen(Request(root + '/display/token', b'{"local_token":654321}', headers)) as reply:
                    result = reply.read().decode()
                self.assertNotIn('654321', result)
                self.assertTrue(json.loads(result)['token_configured'])
                self.assertEqual(json.loads(result)['panels'], [1, 2, 3, 4])
                self.assertTrue(prefs.changed.is_set())
                for endpoint in ('/snapshot', '/display'):
                    with urlopen(root + endpoint) as reply:
                        self.assertNotIn('654321', reply.read().decode())
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_preview_keeps_weather_placeholder_consistent_across_styles(self):
        fifth = []
        for style in ('pixel', 'retro', 'gameboy', 'space'):
            image = Image.open(io.BytesIO(times_gate.render_preview(fixture(), style,
                               now=1791079200, panels=(1, 2, 3, 4))))
            self.assertEqual(image.size, (640, 128))
            fifth.append(image.convert('RGB').crop((512, 0, 640, 128)))
        # Lossless GIF preview uses the exact same device placeholder image.
        other = Image.open(io.BytesIO(times_gate.render_preview(fixture(), 'space',
                           now=1791079201, panels=(1, 2, 3, 4))))
        self.assertEqual(fifth[-1].tobytes(), other.convert('RGB').crop((512, 0, 640, 128)).tobytes())
        for bad in ('', '1,1', '0,2', '1,6', 'all'):
            with self.assertRaises(ValueError):
                times_gate.screen_selection(bad)


if __name__ == '__main__':
    unittest.main()
