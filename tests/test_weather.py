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
        from token_tv import times_gate_faces
        # Tests supply synthetic art; no personal game assets are required.
        styles = tuple(dict.fromkeys((*times_gate_faces.STYLES, 'deltarune')))
        self.styles = patch.object(times_gate_faces, 'STYLES', styles)
        self.styles.start()
        self.addCleanup(self.styles.stop)
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
            self.assertEqual((weather.n_frames, preview.n_frames), (16, 32))
            self.assertEqual(preview.size, (640, 128))
            for phase in range(32):
                weather.seek(phase//2)
                preview.seek(phase)
                self.assertEqual(weather.info['duration'], 500)
                self.assertEqual(preview.info['duration'], 250)
                expected = render_panel(data['weather'], NOW, phase)
                self.assertEqual(weather.convert('RGB').tobytes(), expected.tobytes())
                self.assertEqual(preview.convert('RGB').crop((512, 0, 640, 128)).tobytes(), expected.tobytes())
            for body in panels[:4]:
                self.assertEqual(Image.open(io.BytesIO(body)).n_frames, 16)
            # Other clock styles still retain the live weather presenter on screen 5.
            self.assertEqual(Image.open(io.BytesIO(render_panels(data, 'digital', now=NOW)[4])).n_frames, 16)

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

    def test_original_action_clips_change_over_time_and_preview_matches_native_loops(self):
        import json
        from token_tv.party_actions import available as actions_available, sequence
        from token_tv.times_gate_faces import render_panels, render_preview
        manifest = {}
        for name in ('kris','susie','ralsei'):
            manifest[name] = {}
            for action in ('idle','act','defend'):
                names = []
                for frame in range(3):
                    filename = f'{name}-{action}-{frame}'
                    Image.new('RGBA', (20, 30), (50 + frame * 50, 50 + len(action) * 20, 150)).save(self.root / 'sprites' / (filename + '.png'))
                    names.append(filename)
                manifest[name][action] = names
        (self.root / 'party-actions.json').write_text(json.dumps(manifest))
        self.store.refresh(NOW)
        data = snapshot(NOW,[('c','CLAUDE A','claude',[('5H',12,3600),('WEEK',38,86400)])])
        data['weather'] = self.store.snapshot(NOW)
        with patch('token_tv.local_art.ART_ROOT', self.root):
            self.assertTrue(actions_available())
            chosen = sequence('susie','c',NOW)
            self.assertEqual(chosen, sequence('susie','c',NOW))
            self.assertEqual(set(chosen), {'idle','act','defend'})
            self.assertGreater(len({tuple(sequence('susie','c',NOW+i*60)) for i in range(12)}), 1)
            panels = render_panels(data,'deltarune',now=NOW,layout='accounts')
            native = Image.open(io.BytesIO(panels[0]))
            weather = Image.open(io.BytesIO(panels[4]))
            preview = Image.open(io.BytesIO(render_preview(data,'deltarune',now=NOW,layout='accounts')))
            self.assertEqual((native.n_frames, weather.n_frames, preview.n_frames),(24,16,48))
            self.assertEqual(Image.open(io.BytesIO(panels[2])).n_frames,8)
            self.assertLessEqual(sum(Image.open(io.BytesIO(body)).n_frames for body in panels),96)
            for phase in (0, 5, 8, 16, 23, 24, 32, 47):
                native.seek(phase % 24); weather.seek(phase % 16);preview.seek(phase)
                self.assertEqual(preview.convert('RGB').crop((0,0,128,128)).tobytes(), native.convert('RGB').tobytes())
                self.assertEqual(preview.convert('RGB').crop((512,0,640,128)).tobytes(), weather.convert('RGB').tobytes())
                self.assertEqual(preview.info['duration'], 500)

    def test_battle_weather_symbols_follow_forecast_without_animating_over_readings(self):
        from token_tv.weather_face import BATTLE_SPRITES, battle_available, weather_symbol
        for code, is_day, expected in ((0,True,'sun'), (0,False,'moon'), (0,None,'cloud'),
                (2,True,'partly'), (3,True,'cloud'), (45,True,'fog'), (61,True,'rain'),
                (71,True,'snow'), (95,True,'storm'), (None,True,None), (True,True,None)):
            self.assertEqual(weather_symbol(code, is_day), expected)
        for i, name in enumerate(BATTLE_SPRITES):
            Image.new('RGBA',(25,30),(80+i*3,120,180,255)).save(self.root/'sprites'/(name+'.png'))
        self.store.refresh(NOW)
        weather = self.store.snapshot(NOW)
        with patch('token_tv.local_art.ART_ROOT',self.root):
            self.assertTrue(battle_available())
            frames = [render_panel(weather, NOW, phase) for phase in range(32)]
            for start in (0,16):
                # The entire forecast stays readable while the arena animates.
                readings = {frame.crop((5,80,123,124)).tobytes() for frame in frames[start:start+16]}
                self.assertEqual(len(readings),1)
            self.assertGreater(len({frame.crop((5,29,123,79)).tobytes() for frame in frames}),1)
            old = render_panel(dict(weather,status='stale'),NOW)
            self.assertNotEqual(old.crop((5,5,123,18)).tobytes(),frames[0].crop((5,5,123,18)).tobytes())
            (self.root/'sprites'/('weather-symbol-snow.png')).unlink()
            self.assertFalse(battle_available())
            fallback = render_panel(weather,NOW)
            self.assertNotEqual(fallback.tobytes(),frames[0].tobytes())

    def test_stale_weather_replaces_both_hosts_but_preserves_the_cached_forecast(self):
        from token_tv import weather_face,local_games
        self.store.refresh(NOW)
        weather=self.store.snapshot(NOW)
        for name in weather_face.BATTLE_SPRITES:
            Image.new('RGBA',(25,30),'#bb77dd').save(self.root/'sprites'/(name+'.png'))
        for i,name in enumerate(local_games.GERSON_FRAMES):
            Image.new('RGBA',(20,30),(50+i*40,170,50)).save(self.root/'sprites'/(name+'.png'))
        with patch('token_tv.local_art.ART_ROOT',self.root):
            for phase in (0,16):
                current=render_panel(weather,NOW,phase)
                with patch.object(weather_face,'label',wraps=weather_face.label) as labels:
                    old=render_panel(dict(weather,status='stale'),NOW,phase)
                self.assertIn("I'M OLD!",[call.args[2] for call in labels.call_args_list])
                self.assertEqual(current.crop((5,80,123,124)).tobytes(),old.crop((5,80,123,124)).tobytes())
                self.assertNotEqual(current.crop((5,29,123,79)).tobytes(),old.crop((5,29,123,79)).tobytes())
            frames=[render_panel(dict(weather,status='stale'),NOW,phase) for phase in (0,2,4,6)]
            self.assertEqual(len({frame.crop((9,30,64,78)).tobytes() for frame in frames}),4)
            # A request failure without cached data keeps NO FORECAST and unknowns.
            with patch.object(weather_face,'put_gerson',wraps=weather_face.put_gerson) as gerson:
                render_panel(dict(weather,status='error',temperature=None,days=[]),NOW)
            gerson.assert_not_called()
