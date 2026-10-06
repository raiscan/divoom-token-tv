"""Check fresh-install fan art, provenance integrity, and existing local overrides."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from token_tv import local_art


class BundledArtworkTests(unittest.TestCase):
    def test_fresh_install_has_both_complete_game_faces(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = local_art.resolve_art_root({}, Path(temporary) / 'missing')
        self.assertEqual(root, local_art.BUNDLED_ROOT)
        self.assertEqual(local_art.installed_styles(root), ('undertale', 'deltarune'))

    def test_explicit_override_is_respected_even_when_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / 'my-art'
            root = local_art.resolve_art_root({'TOKEN_TV_LOCAL_ART': str(missing)}, temporary)
            self.assertEqual(root, missing)
            self.assertEqual(local_art.installed_styles(root), ())

    def test_complete_legacy_installation_keeps_its_art(self):
        with tempfile.TemporaryDirectory() as temporary:
            legacy = Path(temporary)
            sprites = legacy / 'sprites'
            sprites.mkdir()
            for names in local_art.REQUIRED.values():
                for name in names:
                    Image.new('RGBA', (1, 1)).save(sprites / (name + '.png'))
            self.assertEqual(local_art.resolve_art_root({}, legacy), legacy)
            (sprites / 'sans.png').unlink()
            self.assertEqual(local_art.resolve_art_root({}, legacy), local_art.BUNDLED_ROOT)

    def test_bundled_animation_graph_and_checksums_are_complete(self):
        from token_tv.local_games import GERSON_FRAMES
        from token_tv.weather_face import BATTLE_SPRITES
        root = local_art.BUNDLED_ROOT
        sprites = root / 'sprites'
        checksums = json.loads((root / 'sprite-checksums.json').read_text())
        self.assertEqual(set(checksums), {p.name for p in sprites.glob('*.png')})
        for name, digest in checksums.items():
            with self.subTest(sprite=name):
                path = sprites / name
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
                with Image.open(path) as image:
                    self.assertEqual(image.format, 'PNG')
                    image.verify()
        for filename in ('party-actions.json', 'party-downed.json'):
            manifest = json.loads((root / filename).read_text())
            self.assertEqual(set(manifest), {'kris', 'susie', 'ralsei'})
            for actions in manifest.values():
                for frames in actions.values():
                    self.assertTrue(frames)
                    for name in frames:
                        self.assertIn(name + '.png', checksums)
        for name in (*GERSON_FRAMES, *BATTLE_SPRITES,
                     *(f'weather-hosts-{i}' for i in range(5))):
            self.assertIn(name + '.png', checksums)
        self.assertIn('does **not**', (root / 'NOTICE.md').read_text())
