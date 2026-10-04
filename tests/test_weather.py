import copy
import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from PIL import Image
from token_tv.weather import WeatherStore, condition, normalize
from token_tv.weather_face import available, render_animation, render_panel
from token_tv.sample import snapshot

NOW = datetime(2026, 10, 4, 12, tzinfo=ZoneInfo('Europe/London')).timestamp()


def payload():
    return {'current_units': {'temperature_2m': '°C'},
            'current': {'time': NOW, 'temperature_2m': 0, 'weather_code': 0, 'is_day': 1},
            'daily': {'time': [NOW, NOW + 86400, NOW + 172800],
                      'weather_code': [0, 61, 71], 'temperature_2m_max': [10, 12, 8],
                      'temperature_2m_min': [0, -1, 2], 'precipitation_probability_max': [0, 80, None]}}


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        sprites = self.root / 'sprites'
        sprites.mkdir()
        for name in ('kris', 'susie', 'ralsei'):
            Image.new('RGBA', (20, 30), '#ffffff').save(sprites / (name + '.png'))
        for i in range(5):
            Image.new('RGBA', (40, 20), (50 + i * 25, 90, 170)).save(sprites / f'weather-hosts-{i}.png')
            Image.new('RGB', (40, 40), (0, i * 30, 180)).save(sprites / f'fountain-{i}.png')
        self.fetch = Mock(return_value=payload())
        self.store = WeatherStore('Poole', 50.7, -1.98, cache_path=self.root / 'cache.json', fetch=self.fetch)

    def test_real_zero_and_missing_values_stay_distinct_and_codes_are_classified(self):
        self.store.refresh(NOW)
        data = self.store.snapshot(NOW)
        self.assertEqual(data['temperature'], 0)
        self.assertEqual(data['days'][0]['rain'], 0)
        broken = payload()
        broken['current']['temperature_2m'] = None
        broken['daily']['temperature_2m_min'][0] = None
        broken['daily']['precipitation_probability_max'][0] = float('nan')
        data = normalize(broken, 'Europe/London', NOW)
        self.assertIsNone(data['temperature'])
        self.assertIsNone(data['days'][0]['low'])
        self.assertIsNone(data['days'][0]['rain'])
        self.assertEqual(condition(0, False), 'CLEAR NIGHT')
        self.assertEqual(condition(0, None), 'CLEAR')
        for code, expected in ((61, 'RAIN'), (71, 'SNOW'), (95, 'STORM'), (None, 'UNKNOWN'), (True, 'UNKNOWN')):
            self.assertEqual(condition(code), expected)

    def test_outage_and_aged_readings_are_old_and_cache_is_bound_to_location(self):
        self.store.refresh(NOW)
        self.fetch.side_effect = OSError('unavailable')
        self.store.refresh(NOW + 300)
        data = self.store.snapshot(NOW + 300)
        self.assertEqual((data['status'], data['temperature']), ('stale', 0))
        reloaded = WeatherStore('Poole', 50.7, -1.98, cache_path=self.root / 'cache.json')
        self.assertEqual(reloaded.snapshot(NOW)['status'], 'stale')
        other = WeatherStore('London', 51.5, 0, cache_path=self.root / 'cache.json')
        self.assertIsNone(other.snapshot(NOW)['temperature'])
        self.fetch.side_effect = None
        self.store.refresh(NOW)
        self.assertEqual(self.store.snapshot(NOW + 1801)['status'], 'stale')
        self.assertEqual(self.store.cache_path.stat().st_mode & 0o777, 0o600)

    def test_invalid_location_units_and_empty_payload_do_not_invent_a_forecast(self):
        for lat, lon in ((91, 0), (0, 181), (None, 0), (float('nan'), 0)):
            with self.assertRaises(ValueError):
                WeatherStore('Poole', lat, lon)
        wrong = payload()
        wrong['current_units']['temperature_2m'] = '°F'
        for data in ({}, [], {'current': []}, wrong):
            self.fetch.return_value = data
            self.store.refresh(NOW)
            self.assertEqual(self.store.snapshot(NOW)['status'], 'error')
            self.assertIsNone(self.store.snapshot(NOW)['temperature'])

    def test_rendering_is_local_and_today_tomorrow_old_and_unknown_are_distinct(self):
        self.store.refresh(NOW)
        weather = self.store.snapshot(NOW)
        with patch('token_tv.local_art.ART_ROOT', self.root), patch('urllib.request.urlopen', side_effect=AssertionError('network')):
            self.assertTrue(available())
            images = [render_panel(weather, NOW, phase) for phase in (0, 16)]
            images.append(render_panel(dict(weather, status='stale'), NOW, 0))
            images.append(render_panel({'city':'Poole', 'status':'error', 'days':[]}, NOW, 0))
            self.assertEqual(len({image.tobytes() for image in images}), 4)
            self.assertTrue(all(image.size == (128, 128) for image in images))
            # Tomorrow selects the date, not a fixed array index left over from yesterday.
            shifted = render_panel(weather, NOW + 86400, 16)
            self.assertNotEqual(shifted.tobytes(), images[1].tobytes())
            (self.root / 'sprites/weather-hosts-4.png').unlink()
            self.assertFalse(available())

    def test_forecast_and_usage_share_five_screen_preview_and_correct_animation_timing(self):
        from token_tv.times_gate_faces import render_panels, render_preview
        self.store.refresh(NOW)
        data = snapshot(NOW, [('claude_a', 'CLAUDE A', 'claude', [('WEEK', 38, 86400)])])
        data['weather'] = self.store.snapshot(NOW)
        with patch('token_tv.local_art.ART_ROOT', self.root):
            panels = render_panels(data, 'deltarune', now=NOW)
            weather = Image.open(io.BytesIO(panels[4]))
            preview = Image.open(io.BytesIO(render_preview(data, 'deltarune', now=NOW)))
            self.assertEqual((weather.n_frames, preview.n_frames), (32, 32))
            self.assertEqual(preview.size, (640, 128))
            for phase in range(32):
                weather.seek(phase)
                preview.seek(phase)
                self.assertEqual(weather.info['duration'], 250)
                self.assertEqual(preview.info['duration'], 250)
                expected = render_panel(data['weather'], NOW, phase)
                self.assertEqual(weather.convert('RGB').tobytes(), expected.tobytes())
                self.assertEqual(preview.convert('RGB').crop((512, 0, 640, 128)).tobytes(), expected.tobytes())
            for body in panels[:4]:
                self.assertEqual(Image.open(io.BytesIO(body)).n_frames, 16)
            # Other clock styles still retain the live weather presenter on screen 5.
            self.assertEqual(Image.open(io.BytesIO(render_panels(data, 'digital', now=NOW)[4])).n_frames, 32)

    def test_usage_store_caches_weather_and_does_not_fetch_in_http_snapshot(self):
        from token_tv.state import UsageStore
        account = {'key':'c','provider':'claude','alias':'C'}
        row = dict(account, status='ok', windows=[], fetched_at=NOW)
        store = UsageStore([account], fetch=lambda _: row, weather=self.store)
        with patch('token_tv.weather.time.time', return_value=NOW):
            store.refresh()
            data = store.snapshot()
        self.assertEqual(data['weather']['city'], 'Poole')
        self.fetch.assert_called_once()
        self.assertNotIn('latitude', data['weather'])

    def test_subscription_layout_keeps_both_windows_and_rotates_whole_accounts(self):
        from token_tv.times_gate_faces import panel_data, render_panels
        data = snapshot(NOW, [('c', 'CLAUDE A', 'claude', [('5H', 12, 3600), ('WEEK', 38, 86400)]),
                              ('x', 'CODEX A', 'codex', [('WEEK', 55, 7200)])])
        self.store.refresh(NOW)
        data['weather'] = self.store.snapshot(NOW)
        panels = panel_data(data, NOW, 'accounts')
        self.assertEqual([panel['kind'] for panel in panels], ['account', 'account', 'clock', 'status', 'empty'])
        self.assertEqual([window['label'] for window in panels[0]['row']['windows']], ['5H', 'WEEK'])
        self.assertEqual(panels[1]['row']['windows'][0]['label'], 'WEEK')
        with patch('token_tv.local_art.ART_ROOT', self.root):
            baseline = render_panels(data, 'deltarune', now=NOW, layout='accounts')
            for window in (0, 1):
                changed = copy.deepcopy(data)
                changed['accounts']['c']['windows'][window]['used_percent'] = 90
                rendered = render_panels(changed, 'deltarune', now=NOW, layout='accounts')
                self.assertNotEqual(rendered[0], baseline[0])
                self.assertEqual(rendered[1], baseline[1])
            stale = copy.deepcopy(data)
            stale['accounts']['c']['status'] = 'stale'
            self.assertNotEqual(render_panels(stale, 'deltarune', now=NOW, layout='accounts')[0], baseline[0])
        for i in range(3):
            data['accounts'][f'other{i}'] = dict(data['accounts']['c'], key=f'other{i}')
        seen = set()
        for tick in range(5):
            panels = panel_data(data, NOW + tick * 300, 'accounts')
            account_panels = [panel for i, panel in enumerate(panels) if i != 4 and panel['kind'] == 'account']
            self.assertEqual(len(account_panels), 3)
            seen.update(panel['row']['key'] for panel in account_panels)
        self.assertEqual(seen, set(data['accounts']))

    def test_subscription_layout_renders_all_existing_appearances_at_native_size(self):
        from token_tv.times_gate_faces import render_panels
        data = snapshot(NOW, [('c', 'CLAUDE A', 'claude', [('5H', 12, 3600), ('WEEK', 38, 86400)])])
        with patch('token_tv.local_art.ART_ROOT', self.root):
            for style in ('pixel', 'digital', 'neon', 'retro', 'hud', 'space', 'gameboy', 'deltarune'):
                for body in render_panels(data, style, now=NOW, layout='accounts'):
                    self.assertEqual(Image.open(io.BytesIO(body)).size, (128, 128))
