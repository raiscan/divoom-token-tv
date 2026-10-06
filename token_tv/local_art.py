"""Bundled fan-theme artwork with explicit and legacy local overrides; no downloads."""
import os
from pathlib import Path

BUNDLED_ROOT = Path(__file__).parent / 'assets' / 'game-art'
REQUIRED = {
    'undertale': ('sans', 'papyrus', 'toriel', 'blook', 'dog', 'dog-bark'),
    'deltarune': ('kris', 'susie', 'ralsei', *(f'fountain-{i}' for i in range(5))),
}


def installed_styles(root=None):
    sprites = Path(root or ART_ROOT) / 'sprites'
    return tuple(style for style, names in REQUIRED.items()
                 if all((sprites / (name + '.png')).is_file() for name in names))


def resolve_art_root(environ=None, legacy_root=None):
    """Keep existing complete installations, and enable both themes on a fresh install."""
    environ = os.environ if environ is None else environ
    if 'TOKEN_TV_LOCAL_ART' in environ:
        return Path(environ['TOKEN_TV_LOCAL_ART']).expanduser()
    legacy = Path(legacy_root) if legacy_root is not None else Path.home() / '.local/share/token-tv/local-games'
    if installed_styles(legacy) == tuple(REQUIRED):
        return legacy
    return BUNDLED_ROOT


ART_ROOT = resolve_art_root()
