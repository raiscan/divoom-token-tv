"""Elnina and Lanino's personal Deltarune weather broadcast, at native 128px."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw
from token_tv.local_games import label, sprite, fit_sprite, PURPLE, CYAN, GOLD
from token_tv.weather import condition

FRAMES = 32
BATTLE_SPRITES = (*(f'weather-{host}-{i}' for host in ('lanino', 'elnina') for i in range(6)),
                  *(f'weather-symbol-{name}' for name in ('moon', 'sun', 'rain', 'snow', 'drops')),
                  *(f'weather-bullet-{name}' for name in ('moon', 'sun', 'drop', 'crystal', 'heart')),
                  *(f'weather-cloud-{i}' for i in range(4)))


def battle_available():
    from token_tv.local_art import ART_ROOT
    return all((ART_ROOT / 'sprites' / (name + '.png')).is_file() for name in BATTLE_SPRITES)


def weather_symbol(code, is_day):
    """Original battle symbols follow the real forecast, including unknowns."""
    name = condition(code, is_day)
    return {'SUNNY':'sun', 'CLEAR NIGHT':'moon', 'CLEAR':'cloud',
            'PARTLY CLOUDY':'partly', 'CLOUDY':'cloud', 'FOG':'fog',
            'DRIZZLE':'rain', 'RAIN':'rain', 'SHOWERS':'rain',
            'SNOW':'snow', 'STORM':'storm'}.get(name)


def paste(canvas, name, box):
    x, y, width, height = box
    image = fit_sprite(sprite(name), (width, height))
    canvas.paste(image, (x + (width-image.width)//2, y + (height-image.height)//2), image)


def battle_scene(canvas, symbol, phase):
    """A forecast card between the hosts, with their original attack projectiles."""
    draw = ImageDraw.Draw(canvas)
    for x in (8, 120):
        draw.line((x, 31, x, 77), fill=PURPLE)
        for y in (32, 45, 58):
            draw.point((x, y), fill=CYAN)
    frame = (phase % 16) * 6 // 16
    paste(canvas, f'weather-lanino-{frame}', (9, 29, 28, 49))
    paste(canvas, f'weather-elnina-{frame}', (91, 29, 28, 49))
    draw.rectangle((39, 30, 88, 78), fill='#150622', outline=PURPLE)
    label(draw, (64, 33), 'FORECAST', align='center', color=CYAN)
    if symbol is None:
        label(draw, (64, 51), '--', 2, align='center')
        return
    if symbol in ('cloud', 'fog', 'partly', 'storm'):
        if symbol == 'partly':
            paste(canvas, 'weather-symbol-sun', (48, 42, 26, 27))
        paste(canvas, f'weather-cloud-{(phase % 16)//4}',
              (49 if symbol == 'partly' else 45, 44, 37, 27))
        if symbol == 'fog':
            for y in (63, 67):
                draw.line((47, y, 80, y), fill='#bbaadd')
        elif symbol == 'storm':
            draw.line([(68,58),(64,64),(68,64),(64,70)], fill=GOLD, width=2)
    else:
        paste(canvas, 'weather-symbol-'+symbol, (47, 42, 34, 28))
    # The game's colliding weather attacks turn into hearts. Keep this flourish
    # beneath the condition symbol and away from all numerical readings.
    step = phase % 8
    projectile = {'sun':'sun', 'moon':'moon', 'snow':'crystal', 'rain':'drop',
                  'storm':'drop', 'partly':'sun'}.get(symbol)
    if projectile:
        if step < 5:
            paste(canvas, 'weather-bullet-'+projectile, (40+step*4, 70, 7, 7))
            paste(canvas, 'weather-bullet-'+projectile, (80-step*4, 70, 7, 7))
        else:
            paste(canvas, 'weather-bullet-heart', (60, 70, 8, 8))


def available():
    from token_tv.local_art import ART_ROOT
    return all((ART_ROOT / 'sprites' / f'weather-hosts-{i}.png').is_file() for i in range(5))


def degrees(value):
    return '--' if value is None else str(round(value))


def render_panel(weather, now, phase=0):
    # Keep forecast motion in sync with the memory-efficient native 2 fps loop.
    phase = (phase // 2) * 2
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
    battle = battle_available()
    if battle:
        battle_scene(canvas, weather_symbol(code, is_day), phase)
        draw.rectangle((5, 79, 122, 123), fill='#050008')
    else:
        hosts = fit_sprite(sprite('weather-hosts-' + str((phase % 16) * 5 // 16)), (116, 49))
        canvas.paste(hosts, ((128 - hosts.width) // 2, 30 + (49 - hosts.height) // 2), hosts)
    if tomorrow:
        label(draw, (64, 80), 'HIGH / LOW', align='center', color=CYAN)
    elif battle:
        label(draw, (64, 81), 'CURRENT TEMP', align='center', color=CYAN)
    label(draw, (64, 89 if tomorrow or battle else 83), text, 2, align='center', width=110)
    label(draw, (64, 105 if tomorrow or battle else 101), condition(code, is_day), align='center')
    rain = day.get('rain')
    label(draw, (64, 115 if tomorrow or battle else 113), 'RAIN ' + (str(round(rain)) + '%' if rain is not None else '--'),
          align='center', color=CYAN)
    if weather.get('status') == 'stale':
        draw.rectangle((60 if battle else 97, 19 if battle else 71,
                        81 if battle else 121, 28 if battle else 81), fill='#000000')
        label(draw, (80 if battle else 120, 20 if battle else 73), 'OLD', align='right', color=GOLD)
    elif weather.get('status') in ('loading', 'error'):
        draw.rectangle((7, 71, 120, 81), fill='#000000')
        label(draw, (64, 73), 'NO FORECAST', align='center', color=GOLD)
    return canvas


def render_animation(weather, now):
    from token_tv.times_gate_faces import encode
    frames = [render_panel(weather, now, phase) for phase in range(0, FRAMES, 2)]
    return encode(frames[0], frames[1:], duration=500)
