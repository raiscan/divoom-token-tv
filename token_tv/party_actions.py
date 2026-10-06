"""Original game animations from bundled fan art or a local artwork override."""
import functools
import hashlib
import json
import random

from PIL import Image
from token_tv import local_art

FRAMES = 48


@functools.lru_cache(maxsize=4)
def _manifest(root, filename='party-actions.json'):
    path = root / filename
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            return {}
        for actions in data.values():
            if not isinstance(actions, dict):
                return {}
            for frames in actions.values():
                if not isinstance(frames, list) or not frames:
                    return {}
                if any(not isinstance(name, str) or not name or
                       any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name) or
                       not (root / 'sprites' / (name + '.png')).is_file() for name in frames):
                    return {}
        return data
    except (OSError, ValueError):
        return {}


def available():
    data = _manifest(local_art.ART_ROOT)
    return all(len(data.get(name, {})) >= 2 for name in ('kris', 'susie', 'ralsei'))


def sequence(character, identity, now):
    actions = list(_manifest(local_art.ART_ROOT).get(character, {}))
    seed = hashlib.sha256(f'{character}:{identity}:{int(now)//60}'.encode()).digest()
    random.Random(seed).shuffle(actions)
    return actions[:3]


def put_character(canvas, character, identity, now, phase, box, *, downed=False):
    """Healthy ACT clips, or a held DOWN pose, shared by device and preview."""
    from token_tv.local_games import sprite
    if downed:
        action = 'downed'
        names = _manifest(local_art.ART_ROOT, 'party-downed.json').get(character, {}).get(action, [])
        if not names:
            return False
    else:
        actions = sequence(character, identity, now)
        if not actions:
            return False
        action = actions[(phase // 16) % len(actions)]
        names = _manifest(local_art.ART_ROOT)[character][action]
    index = min(len(names) - 1, (phase % 16) * len(names) // 16)
    image = sprite(names[index])
    x, y, width, height = box
    # Every frame in a clip has the same source canvas. Scale once uniformly,
    # preserving the artist's motion and allowing a larger-than-source sprite.
    scale = min(width / image.width, height / image.height) if downed else height / image.height
    image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                         Image.Resampling.NEAREST)
    if image.width > width:
        # Keep the character large; only overflowing weapon/spell effects are
        # clipped to the portrait area, never stretched across the quota text.
        focus = {('susie','idle'): .68, ('susie','act'): .42,
                 ('kris','act'): .30, ('ralsei','act'): .26}.get((character,action), .5)
        left = max(0, min(image.width - width, round(image.width * focus - width / 2)))
        image = image.crop((left, 0, left + width, height))
    canvas.paste(image, (x + (width - image.width) // 2, y + height - image.height), image)
    return True
