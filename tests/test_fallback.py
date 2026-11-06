import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from token_tv.sample import snapshot


class OfflineFallbackTests(unittest.TestCase):
    def test_export_has_five_native_animations_without_provider_or_network_access(self):
        from token_tv.fallback import build_fallback
        from token_tv import times_gate_faces
        for style in ('undertale', 'deltarune'):
            with self.subTest(style=style), \
                 patch('urllib.request.urlopen', side_effect=AssertionError('No network in an offline export')), \
                 patch.object(times_gate_faces, 'render_panels', wraps=times_gate_faces.render_panels) as render:
                files = build_fallback(style, city='Poole')
            data = render.call_args.args[0]
            self.assertEqual(data['updated_at'], 0)
            for row in data['accounts'].values():
                self.assertEqual(row['status'], 'offline')
                self.assertFalse(row['windows'])
            self.assertEqual(set(files), {*(f'screen-{i}.gif' for i in range(1, 6)), 'preview.png', 'SAVE-ON-CLOCK.txt'})
            for i in range(1, 6):
                image = Image.open(io.BytesIO(files[f'screen-{i}.gif']))
                self.assertEqual((image.size, image.format), ((128, 128), 'GIF'))
            preview = Image.open(io.BytesIO(files['preview.png']))
            self.assertEqual(preview.size, (640, 128))
            instructions = files['SAVE-ON-CLOCK.txt'].decode()
            self.assertIn('not saved to the clock', instructions)
            self.assertIn('power-cycle', instructions)

    def test_zip_is_complete_and_unsupported_styles_fail_clearly(self):
        from token_tv.fallback import fallback_zip
        with zipfile.ZipFile(io.BytesIO(fallback_zip('deltarune'))) as archive:
            self.assertEqual(len(archive.namelist()), 7)
            self.assertEqual(Image.open(io.BytesIO(archive.read('screen-5.gif'))).size, (128, 128))
        with self.assertRaises(ValueError):
            fallback_zip('invalid')
        with patch('token_tv.weather_face.available', return_value=False), self.assertRaises(ValueError):
            fallback_zip('deltarune')

    def test_cli_exports_without_a_config_and_preserves_existing_files(self):
        from token_tv.cli import main
        with tempfile.TemporaryDirectory() as temporary, \
             patch('token_tv.cli.read_config', side_effect=AssertionError('No account configuration needed')):
            target = Path(temporary) / 'fallback'
            self.assertEqual(main(['fallback', '--style', 'deltarune', '--city', 'Poole', '--out', str(target)]), 0)
            self.assertTrue((target / 'screen-1.gif').is_file())
            with zipfile.ZipFile(target / 'times-gate-fallback.zip') as archive:
                self.assertEqual(archive.read('screen-1.gif'), (target / 'screen-1.gif').read_bytes())
            marker = target / 'screen-1.gif'
            marker.write_bytes(b'user file')
            self.assertEqual(main(['fallback', '--out', str(target)]), 1)
            self.assertEqual(marker.read_bytes(), b'user file')

    def test_dashboard_download_is_an_attachment_and_does_not_touch_the_device(self):
        import threading
        from http.server import ThreadingHTTPServer
        from urllib.error import HTTPError
        from urllib.request import urlopen
        from token_tv.live import DisplayPreferences, handler
        from token_tv.state import UsageStore
        from token_tv.times_gate import TimesGateDisplay
        with tempfile.TemporaryDirectory() as temporary:
            device = TimesGateDisplay('http://127.0.0.1:9', local_token=654321)
            prefs = DisplayPreferences(Path(temporary) / 'metadata.json',
                                       {'device_type': 'times-gate', 'device_url': device.base_url,
                                        'display_style': 'deltarune', 'forecast_city': 'Poole'}, device)
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler(UsageStore([]), prefs))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with patch.object(device, 'command', side_effect=AssertionError('Download must not write to clock')):
                    root = f'http://127.0.0.1:{server.server_port}'
                    with urlopen(root + '/display/fallback.zip?style=deltarune') as response:
                        self.assertEqual(response.headers['Content-Type'], 'application/zip')
                        self.assertIn('attachment;', response.headers['Content-Disposition'])
                        archive = response.read()
                    self.assertNotIn(b'654321', archive)
                    with zipfile.ZipFile(io.BytesIO(archive)) as files:
                        self.assertEqual(len(files.namelist()), 7)
                    for style in ('invalid', '../../private'):
                        with self.assertRaises(HTTPError) as error:
                            urlopen(root + '/display/fallback.zip?style=' + style)
                        self.assertEqual(error.exception.code, 400)
                        error.exception.close()
                self.assertFalse(prefs.changed.is_set())
                self.assertIsNone(prefs.applied_style)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_runtime_address_override_keeps_saved_metadata_unchanged(self):
        import contextlib
        import json
        from token_tv import live
        config = {'accounts': [], 'device_url': 'http://192.168.0.50',
                  'display_style': 'digital', 'device_type': 'photo'}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'metadata.json'
            original = json.dumps(config)
            path.write_text(original)
            with patch('sys.argv', ['token-tv run', '--config', str(path), '--once',
                                   '--device-url', 'http://192.168.0.51', '--state-dir', temporary]), \
                 patch('token_tv.live.load_config', return_value=dict(config)), \
                 patch('token_tv.live.UsageStore.refresh'), \
                 patch('token_tv.live.DisplayPreferences', wraps=live.DisplayPreferences) as preferences, \
                 patch('urllib.request.urlopen', side_effect=AssertionError('No live calls')), \
                 contextlib.redirect_stdout(io.StringIO()):
                live.main()
            self.assertEqual(preferences.call_args.args[2].base_url, 'http://192.168.0.51')
            self.assertEqual(path.read_text(), original)
