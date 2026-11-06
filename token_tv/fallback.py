"""Offline fan-theme animations for import into a saved Divoom app layout.

Exports artwork with explicit OFFLINE labels, never quota readings or a frozen
clock/forecast. Exporting is not a device save or a verified persistence command.
"""
import io
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageSequence
from token_tv import times_gate_faces
from token_tv.local_games import label

INSTRUCTIONS = '''TokenTV offline fallback — not saved to the clock yet

These are five independent 128x128 GIFs, in left-to-right screen order.
They contain no live quota readings, clock time or weather forecast.
Keep your normal TokenTV service for live data when the computer is on.

1. Transfer screen-1.gif through screen-5.gif to your phone.
2. In the Divoom app, open the Times Gate's independent-screen editor.
   If your app offers custom image/GIF import, assign each file to its
   matching screen in a saved layout. Save with the app's checkmark/Save.
   Menu names and import support depend on app and firmware versions.
3. Select that saved layout as the device's normal display. Do not stop
   after merely previewing or sending a temporary animation.
4. Stop TokenTV, power-cycle the Times Gate, and confirm that the fallback
   returns while the computer is off. Restart TokenTV for live readings.

The export is not saved to the clock automatically. The LAN image-stream
API does not establish boot persistence. A successful download/play API
response alone is not proof that an animation was saved or survived reboot.
If the app has no import option, this pack is ready but installation still
requires a supported app/firmware save path. Do not reset the device.

Artwork: Undertale / Deltarune, copyright Toby Fox, Temmie Chang and the
original artists. Unofficial fan appearances; game artwork is excluded
from the software's MIT license. Credits and original source URLs:
https://github.com/raiscan/divoom-token-tv/tree/main/token_tv/assets/game-art
'''


def build_fallback(style='deltarune', city=''):
    if style not in ('undertale', 'deltarune') or style not in times_gate_faces.STYLES:
        raise ValueError('Choose an installed Undertale or Deltarune appearance')
    data = {'schema': 1, 'updated_at': 0, 'accounts': {
        f'{provider}_a': {'key': f'{provider}_a', 'alias': provider.upper() + ' A',
                         'provider': provider, 'status': 'offline', 'windows': []}
        for provider in ('claude', 'codex')}}
    if style == 'deltarune':
        from token_tv.weather_face import available
        if not available():
            raise ValueError('Deltarune offline fallback needs weather-host artwork')
        data['weather'] = {'city': city, 'status': 'offline', 'temperature': None,
                           'code': None, 'days': []}
    bodies = times_gate_faces.render_panels(data, style=style, now=0, layout='accounts')
    files = {}
    preview = Image.new('RGB', (640, 128))
    for index, body in enumerate(bodies):
        decoded = Image.open(io.BytesIO(body))
        frames = []
        for original in ImageSequence.Iterator(decoded):
            frame = original.convert('RGB')
            draw = ImageDraw.Draw(frame)
            if index in (0, 1):
                draw.rectangle((5, 16, 122, 27), fill='#050008')
                label(draw, (8, 19), 'OFFLINE', color='#ffff00')
            elif index == 2:
                draw.rectangle((6, 47, 121, 101 if style == 'deltarune' else 94), fill='#000000')
                label(draw, (64, 53), 'OFFLINE', 2, align='center', color='#ffff00')
                label(draw, (64, 77), 'START TOKEN TV', align='center')
                if style == 'deltarune':
                    draw.rectangle((80, 106, 122, 121), fill='#000000')
            elif index == 3:
                top = 77 if style == 'deltarune' else 62
                draw.rectangle((7, top, 120, 104), fill='#000000', outline='#ffffff')
                label(draw, (64, top + 5), 'PARTY WAITING', align='center')
                label(draw, (64, top + 18), 'FOR TOKEN TV', align='center', color='#7cff8b')
                draw.rectangle((5, 106, 122, 122), fill='#050008')
                label(draw, (64, 112), 'OFFLINE', align='center', color='#ffff00')
            elif style == 'deltarune':
                draw.rectangle((5, 79, 122, 123), fill='#050008')
                label(draw, (64, 84), 'HOST OFFLINE', align='center', color='#ffff00')
                label(draw, (64, 100), 'NO FORECAST', align='center')
            else:
                draw.rectangle((5, 85, 122, 122), fill='#050008')
                label(draw, (64, 93), 'OFFLINE', align='center', color='#ffff00')
                label(draw, (64, 112), 'START TOKEN TV', align='center')
            frames.append(frame)
        preview.paste(frames[0], (128 * index, 0))
        output = io.BytesIO()
        frames[0].save(output, format='GIF', save_all=True, append_images=frames[1:],
                       duration=decoded.info.get('duration', 500), loop=0)
        files[f'screen-{index + 1}.gif'] = output.getvalue()
    output = io.BytesIO()
    preview.save(output, format='PNG')
    files['preview.png'] = output.getvalue()
    files['SAVE-ON-CLOCK.txt'] = INSTRUCTIONS.encode()
    return files


def _archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def fallback_zip(style='deltarune', city=''):
    return _archive(build_fallback(style, city))


def export_fallback(destination, style='deltarune', city=''):
    files = build_fallback(style, city)
    files['times-gate-fallback.zip'] = _archive(files)
    destination = Path(destination).expanduser()
    if any((destination / name).exists() for name in files):
        raise FileExistsError('Choose a new output folder; existing fallback files are preserved')
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        with (destination / name).open('xb') as output:
            output.write(content)
    return destination
