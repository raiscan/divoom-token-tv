"""Elnina and Lanino's personal Deltarune weather broadcast, at native 128px."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw
from token_tv.local_games import label, sprite, fit_sprite, PURPLE, CYAN, GOLD
from token_tv.weather import condition

FRAMES = 32


def available():
    from token_tv.local_art import ART_ROOT
    return all((ART_ROOT / 'sprites' / f'weather-hosts-{i}.png').is_file() for i in range(5))


def degrees(value):
    return '--' if value is None else str(round(value))


def render_panel(weather, now, phase=0):
    canvas = Image.new('RGB', (128, 128), '#050008')
    draw = ImageDraw.Draw(canvas)
    for pos in range(-16, 145, 16):
        draw.line((pos + phase % 16, 29, pos + phase % 16, 81), fill='#240024')
        if 29 <= pos + phase % 16 <= 81:
            draw.line((5, pos + phase % 16, 122, pos + phase % 16), fill='#240024')
    draw.rectangle((2, 2, 125, 125), outline=PURPLE, width=2)
    label(draw, (64, 8), 'LANINO + ELNINA', align='center', color=CYAN)
    tomorrow = phase % FRAMES >= 16
    title = 'TOMORROW' if tomorrow else 'NOW'
    label(draw, (8, 20), title, color=GOLD)
    label(draw, (120, 20), weather.get('city', '')[:8], align='right', width=47)
    hosts = fit_sprite(sprite('weather-hosts-' + str((phase % 16) * 5 // 16)), (116, 49))
    canvas.paste(hosts, ((128 - hosts.width) // 2, 30 + (49 - hosts.height) // 2), hosts)
    date = datetime.fromtimestamp(now, ZoneInfo(weather.get('timezone', 'Europe/London'))).date()
    target = (date + timedelta(days=int(tomorrow))).isoformat()
    day = next((day for day in weather.get('days', []) if day['date'] == target), {})
    if tomorrow:
        text = degrees(day.get('high')) + '/' + degrees(day.get('low')) + 'C'
        code = day.get('code')
        is_day = True
    else:
        text = degrees(weather.get('temperature')) + 'C'
        code, is_day = weather.get('code'), weather.get('is_day', True)
    if tomorrow:
        label(draw, (64, 80), 'HIGH / LOW', align='center', color=CYAN)
    label(draw, (64, 89 if tomorrow else 83), text, 2, align='center', width=110)
    label(draw, (64, 105 if tomorrow else 101), condition(code, is_day), align='center')
    rain = day.get('rain')
    label(draw, (64, 115 if tomorrow else 113), 'RAIN ' + (str(round(rain)) + '%' if rain is not None else '--'),
          align='center', color=CYAN)
    if weather.get('status') == 'stale':
        draw.rectangle((97, 71, 121, 81), fill='#000000')
        label(draw, (120, 73), 'OLD', align='right', color=GOLD)
    elif weather.get('status') in ('loading', 'error'):
        draw.rectangle((7, 71, 120, 81), fill='#000000')
        label(draw, (64, 73), 'NO FORECAST', align='center', color=GOLD)
    return canvas


def render_animation(weather, now):
    from token_tv.times_gate_faces import encode
    frames = [render_panel(weather, now, phase) for phase in range(FRAMES)]
    return encode(frames[0], frames[1:])
