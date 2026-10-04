"""Optional personal artwork stored outside the checkout; never fetched at runtime."""
import os
from pathlib import Path

ART_ROOT = Path(os.environ.get('TOKEN_TV_LOCAL_ART',
                Path.home() / '.local/share/token-tv/local-games')).expanduser()
REQUIRED = {
    'undertale': ('sans', 'papyrus', 'toriel', 'blook', 'dog', 'dog-bark'),
    'deltarune': ('kris', 'susie', 'ralsei', *(f'fountain-{i}' for i in range(5))),
}


def installed_styles(root=None):
    sprites = Path(root or ART_ROOT) / 'sprites'
    return tuple(style for style, names in REQUIRED.items()
                 if all((sprites / (name + '.png')).is_file() for name in names))
