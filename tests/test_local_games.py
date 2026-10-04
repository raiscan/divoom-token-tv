"""Local artwork is optional; tests use synthetic assets, never downloaded game art."""
import copy
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from token_tv.sample import snapshot

NOW = 1791079200


class LocalGameFacesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        sprites = self.root / 'sprites'
        sprites.mkdir()
        for name in ['sans', 'papyrus', 'toriel', 'blook', 'dog', 'dog-bark', 'kris', 'susie', 'ralsei']:
            Image.new('RGBA', (20, 30), '#ffffff').save(sprites / (name + '.png'))
        for i in range(5):
            Image.new('RGB', (40, 40), (0, i*30, 180)).save(sprites / f'fountain-{i}.png')
        self.addCleanup(self.temp.cleanup)
        self.data = snapshot(NOW, [('claude_a', 'CLAUDE A', 'claude', [('5H', 72, 3600), ('WEEK', 38, 86400)]),
                                   ('codex_a', 'CODEX A', 'codex', [('WEEK', 55, 7200)])])

    def test_only_complete_local_asset_sets_enable_their_styles(self):
        from token_tv.local_art import installed_styles
        self.assertEqual(installed_styles(self.root), ('undertale', 'deltarune'))
        (self.root / 'sprites/sans.png').unlink()
        self.assertEqual(installed_styles(self.root), ('deltarune',))
        self.assertEqual(installed_styles(self.root / 'missing'), ())

    def test_native_appearances_animate_and_preserve_reading_states(self):
        from token_tv.local_games import render_panel
        from token_tv.times_gate_faces import panel_data
        with patch('token_tv.local_art.ART_ROOT', self.root):
            for style in ('undertale', 'deltarune'):
                outputs = []
                for state in ('current', 'unknown', 'zero', 'stale'):
                    data = copy.deepcopy(self.data)
                    row = data['accounts']['claude_a']
                    if state == 'unknown':row.update(status='auth_required', windows=[])
                    if state == 'zero':row['windows'][0]['used_percent'] = 0
                    if state == 'stale':row['status'] = 'stale'
                    image = render_panel(panel_data(data, NOW)[0], data, style, NOW, 0)
                    self.assertEqual((image.size, image.mode), ((128, 128), 'RGB'))
                    outputs.append(image.tobytes())
                self.assertEqual(len(set(outputs)), 4, style)
                panel = panel_data(self.data, NOW)[0]
                self.assertNotEqual(render_panel(panel, self.data, style, NOW, 0).tobytes(),
                                    render_panel(panel, self.data, style, NOW, 5).tobytes())

    def test_artwork_loads_locally_and_all_panel_roles_render(self):
        from token_tv.local_games import render_panel
        from token_tv.times_gate_faces import panel_data
        with patch('token_tv.local_art.ART_ROOT', self.root), patch('urllib.request.urlopen', side_effect=AssertionError('network access')):
            for style in ('undertale', 'deltarune'):
                for data in (self.data, snapshot(NOW, [])):
                    for panel in panel_data(data, NOW):
                        self.assertEqual(render_panel(panel, data, style, NOW, 3).size, (128, 128))

    def test_one_reported_limit_reclaims_the_unused_meter_in_every_appearance(self):
        from token_tv import local_games
        for style in ('undertale', 'deltarune', 'pixel', 'digital', 'neon', 'retro', 'hud', 'space', 'gameboy'):
            with self.subTest(style=style), patch('token_tv.local_art.ART_ROOT', self.root):
                with patch.object(local_games, 'used_bar', wraps=local_games.used_bar) as meters:
                    local_games.render_account(self.data['accounts']['claude_a'], NOW, style=style)
                    self.assertEqual([call.args[2] for call in meters.call_args_list], [72, 38])
                    dual_height = meters.call_args.args[1][3] - meters.call_args.args[1][1]
                for period in ('WEEK', '5H'):
                    row = copy.deepcopy(self.data['accounts']['codex_a'])
                    row['windows'][0]['label'] = period
                    with patch.object(local_games, 'used_bar', wraps=local_games.used_bar) as meters, \
                         patch.object(local_games, 'label', wraps=local_games.label) as labels:
                        image = local_games.render_account(row, NOW, style=style)
                    self.assertEqual(image.size, (128, 128))
                    self.assertEqual(meters.call_count, 1)
                    self.assertEqual(meters.call_args.args[2], 55)
                    box = meters.call_args.args[1]
                    self.assertGreater(box[3] - box[1], dual_height)
                    texts = [call.args[2] for call in labels.call_args_list]
                    self.assertIn('1W' if period == 'WEEK' else '5H', texts)
                    self.assertNotIn('5H' if period == 'WEEK' else '1W', texts)

    def test_single_limit_keeps_unknown_zero_old_and_failed_accounts_honest(self):
        from token_tv import local_games
        images = []
        for status, used in (('ok', None), ('ok', 0), ('stale', 55), ('auth_required', 55)):
            row = copy.deepcopy(self.data['accounts']['codex_a'])
            row.update(status=status)
            row['windows'][0]['used_percent'] = used
            with patch('token_tv.local_art.ART_ROOT', self.root), \
                 patch.object(local_games, 'used_bar', wraps=local_games.used_bar) as meters, \
                 patch.object(local_games, 'label', wraps=local_games.label) as labels:
                images.append(local_games.render_account(row, NOW).tobytes())
            self.assertEqual([call.args[2] for call in meters.call_args_list],
                             [None, None] if status == 'auth_required' else [used])
            self.assertTrue(all(call.args[4] == (status == 'stale') for call in meters.call_args_list))
            texts = [call.args[2] for call in labels.call_args_list]
            if status == 'stale': self.assertIn('OLD', texts)
            if used is None or status == 'auth_required': self.assertIn('--', texts)
            if used == 0: self.assertIn('0', texts)
        self.assertEqual(len(set(images)), 4)
        row = dict(self.data['accounts']['codex_a'], windows=[])
        with patch('token_tv.local_art.ART_ROOT', self.root), \
             patch.object(local_games, 'used_bar', wraps=local_games.used_bar) as meters:
            local_games.render_account(row, NOW)
        self.assertEqual([call.args[2] for call in meters.call_args_list], [None, None])

    def test_single_budget_and_larger_original_actor_use_the_same_adaptive_layout(self):
        from token_tv import local_games
        row = copy.deepcopy(self.data['accounts']['codex_a'])
        with patch('token_tv.local_art.ART_ROOT', self.root), \
             patch('token_tv.party_actions.put_character', return_value=True) as actor:
            local_games.render_account(self.data['accounts']['claude_a'], NOW)
            dual_height = actor.call_args.args[-1][3]
            local_games.render_account(row, NOW)
            self.assertGreater(actor.call_args.args[-1][3], dual_height)
        row.update(provider='grok', alias='GROK A')
        row['windows'][0]['label'] = 'BUDGET'
        with patch('token_tv.local_art.ART_ROOT', self.root), \
             patch.object(local_games, 'used_bar', wraps=local_games.used_bar) as meters:
            local_games.render_account(row, NOW)
        self.assertEqual(meters.call_count, 1)
        self.assertEqual(meters.call_args.args[2], 55)

    def test_full_strips_use_native_animated_payloads_and_stock_faces_stay_240px(self):
        from token_tv import times_gate_faces
        from token_tv.local_games import render_stock
        with patch('token_tv.local_art.ART_ROOT', self.root), patch.object(times_gate_faces, 'STYLES', ('undertale', 'deltarune')):
            for style in ('undertale', 'deltarune'):
                self.assertEqual(render_stock(self.data, style).size, (240, 240))
                for data in (self.data, snapshot(NOW, [])):
                    frames = times_gate_faces.render_panels(data, style, now=NOW)
                    self.assertEqual(len(frames), 5)
                    for body in frames + [times_gate_faces.render_preview(data, style, now=NOW)]:
                        with Image.open(io.BytesIO(body)) as image:
                            self.assertEqual(image.format, 'GIF')
                            self.assertIn(image.size, [(128, 128), (640, 128)])
                            # Device API uses one speed per panel: deduplicated GIF
                            # frames would change timing. Every loop is 16 x 250ms.
                            self.assertEqual(image.n_frames, 16)
                            for frame in range(image.n_frames):
                                image.seek(frame)
                                self.assertEqual(image.info['duration'], 250)
