import copy
import io
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image

from token_tv import times_gate
from token_tv.display import STYLES
from token_tv.live import DisplayPreferences, handler
from token_tv.sample import snapshot
from token_tv.sources import load_config
from token_tv.state import UsageStore

NOW = 1791079200


class PanelAppearanceTests(unittest.TestCase):
    def test_retro_sky_objects_stay_round_and_near_centre(self):
        from token_tv.times_gate_faces import retro_backdrop
        for provider, color in [('claude', (255, 158, 79)), ('codex', (217, 255, 233))]:
            image = retro_backdrop(provider)
            points = [(x, y) for y in range(image.height) for x in range(image.width)
                      if image.getpixel((x, y))[:3] == color]
            self.assertTrue(points)
            xs, ys = zip(*points)
            width, height = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
            self.assertLessEqual(abs(width - height), 2)
            self.assertTrue(45 <= (min(xs) + max(xs)) / 2 <= 73)

    def test_all_appearances_show_unknown_zero_and_old_as_distinct_states(self):
        self.assertIn('gameboy', STYLES)
        current = snapshot(NOW, [('c', 'CLAUDE A', 'claude', [('5H', 72, 3600)])])
        unknown, zero, old = [copy.deepcopy(current) for _ in range(3)]
        unknown['accounts']['c'].update(status='auth_required', windows=[])
        zero['accounts']['c']['windows'][0]['used_percent'] = 0
        old['accounts']['c']['status'] = 'stale'
        outputs = []
        for style in STYLES:
            frames = [times_gate.render_panels(d, style, now=NOW)[0] for d in (current, unknown, zero, old)]
            self.assertEqual(len(set(frames)), 4, style)
            outputs.append(frames[0])
            for body in frames:
                with Image.open(io.BytesIO(body)) as image:
                    self.assertEqual(image.size, (128, 128), style)
        self.assertEqual(len(set(outputs)), len(STYLES))

    def test_gameboy_keeps_four_lcd_shades_before_transport(self):
        from token_tv.times_gate_faces import render_images
        palette = {(15, 56, 15), (48, 98, 48), (139, 172, 15), (155, 188, 15)}
        images = render_images(snapshot(NOW), 'gameboy', now=NOW)
        for image in images:
            self.assertLessEqual({pixel for count, pixel in image.getcolors()}, palette)
        self.assertTrue(any(len(image.getcolors()) == 4 for image in images))

    def test_space_preview_keeps_animation_and_five_screen_geometry(self):
        body = times_gate.render_preview(snapshot(NOW), 'space')
        with Image.open(io.BytesIO(body)) as image:
            self.assertEqual((image.format, image.size), ('GIF', (640, 128)))
            self.assertGreater(image.n_frames, 1)

    def test_gameboy_can_be_previewed_and_applied_through_dashboard(self):
        account = {'key': 'c', 'provider': 'claude', 'alias': 'CLAUDE A', 'email': 'test@example.com'}
        store = UsageStore([account])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            config = {'accounts': [account], 'device_type': 'times-gate', 'display_style': 'retro'}
            path.write_text(json.dumps(config))
            prefs = DisplayPreferences(path, config)
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler(store, prefs))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            root = f'http://127.0.0.1:{server.server_port}'
            try:
                with urlopen(root + '/themes') as r:
                    themes = json.load(r)['themes']
                self.assertTrue(any(t['id'] == 'gameboy' and t['installed'] for t in themes))
                with urlopen(root + '/frame/0.jpg?style=gameboy') as r:
                    self.assertEqual(Image.open(io.BytesIO(r.read())).size, (640, 128))
                with urlopen(Request(root + '/display/style', data=b'{"style":"gameboy"}',
                                     headers={'Content-Type': 'application/json'})) as r:
                    self.assertEqual(json.load(r)['style'], 'gameboy')
                self.assertEqual(load_config(path)['display_style'], 'gameboy')
            finally:
                server.shutdown(); server.server_close(); thread.join()
