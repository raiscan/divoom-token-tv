"""Native 128px TokenTV appearances and complete five-screen previews."""
import functools
import io
import math
import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageOps

from token_tv.display import STYLES, STATUS, PROVIDER_INK, pixel_text
from token_tv.gameboy import DARKEST, DARK, LIGHT, LIGHTEST, to_four_shades
from token_tv.themes import (ACCENT, Canvas, band, bot_sprite, face, gauge, ghost,
                             mix, pixel_scene, place_bot, scanlined)

ANIMATION_FRAMES = 16
ANIMATION_SPEED = 250


@functools.lru_cache(maxsize=3)
def retro_backdrop(provider):
    scene = Canvas('#0a0d26')
    pixel_scene(scene, provider, 0)
    # Uniform scaling, followed by a crop centred on the sun/moon at source x=132.
    # The artwork remains circular instead of stretching a 228x74 strip to 118x75.
    return ImageOps.fit(scene.base.crop((6, 2, 234, 76)), (118, 75),
                        method=Image.Resampling.NEAREST, centering=(.6, .5)).convert('RGB')


def panel_data(snapshot, now=None, layout='windows'):
    """Each window owns its percentage and reset; overflow rotates every five minutes."""
    now = time.time() if now is None else now
    if layout == 'accounts':
        capacity = 3 if snapshot.get('weather') is not None else 4
        entries = [{'kind': 'account', 'row': row} for row in snapshot['accounts'].values()]
        if len(entries) > capacity:
            offset = (int(now) // 300 * capacity) % len(entries)
            entries = (entries + entries)[offset:offset + capacity]
        if len(entries) < capacity:
            entries.append({'kind': 'status'})
        entries += [{'kind': 'empty'}] * (4 - len(entries))
        return entries[:2] + [{'kind': 'clock'}] + entries[2:]
    if layout != 'windows':
        raise ValueError('Unknown Times Gate panel layout')
    entries = []
    for row in snapshot['accounts'].values():
        windows = row.get('windows', []) if row['status'] in ('ok', 'stale') else []
        # Keep provider outages and identity mismatches visible as unknown.
        for value in windows or [None]:
            entries.append({'kind': 'usage', 'row': row, 'window': value})
    if len(entries) > 4:
        offset = (int(now) // 300 * 4) % len(entries)
        entries = (entries + entries)[offset:offset + 4]
    if len(entries) < 4:
        entries.append({'kind': 'status'})
    entries += [{'kind': 'empty'}] * (4 - len(entries))
    return entries[:2] + [{'kind': 'clock'}] + entries[2:]


def retro_panel(panel, snapshot, date, now):
    """TokenTV's Pixel Retro art, arranged directly on a 128px panel."""
    cream, outline = '#fff3d6', '#0a0d26'
    provider = panel.get('row', {}).get('provider', 'grok')
    accent = ACCENT['retro'][provider][0]
    image = Image.new('RGB', (128, 128), '#0a0f2c')
    # Reuse the original scene as a backdrop; draw all information at native size.
    backdrop = retro_backdrop(provider)
    image.paste(backdrop.convert('RGB'), (5, 26))
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, 125, 125), outline=accent, width=2)
    draw.rectangle((5, 5, 122, 24), fill=outline)
    draw.line((5, 24, 122, 24), fill=accent)

    def label(x, y, value, scale=1, color=cream, align='left', stroke=False):
        if stroke:
            for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
                pixel_text(draw, (x + dx, y + dy), value, scale, outline, align)
        pixel_text(draw, (x, y), value, scale, color, align)

    def centre(y, value, scale=1, color=cream):
        width = (len(value) * 6 - 1) * scale
        label((128 - width) // 2, y, value, scale, color)

    def sprite(provider, box):
        x, y, width, height = box
        art = bot_sprite(provider, width, height)
        image.paste(art, (x + (width - art.width) // 2, y + (height - art.height) // 2), art)

    if panel['kind'] == 'usage':
        row, window = panel['row'], panel['window']
        sprite(provider, (7, 7, 20, 15))
        label(32, 11, row['alias'][:15])
        period = window['label'] if window else STATUS.get(row['status'], 'NO DATA')
        label(9, 30, period, color='#b9d2ff')
        old = row['status'] == 'stale'
        if old:
            label(119, 30, 'OLD', color='#ff9a9a', align='right')
        draw.rectangle((8, 43, 46, 83), fill=outline, outline=accent, width=2)
        sprite(provider, (11, 47, 32, 32))
        used = window['used_percent'] if window else None
        number = f'{used:.0f}%' if used is not None else '--'
        label(120, 49, number, 3, align='right', stroke=True)
        label(119, 77, 'USED' if used is not None else 'UNKNOWN', color='#b9d2ff', align='right')
        draw.rectangle((7, 87, 120, 109), fill=outline, outline=accent)
        label(11, 90, 'RESET IN', color='#a9bdf0')
        reset = window.get('resets_at') if window else None
        remaining = '--'
        if reset:
            minutes = max(0, int((reset - now + 59) // 60))
            remaining = f'{minutes // 1440}D {minutes % 1440 // 60}H' if minutes >= 1440 else f'{minutes // 60}H {minutes % 60}M'
        label(116, 100, remaining, align='right')
        start, tip = band('retro', used or 0)
        for cell in range(10):
            x = 8 + cell * 11
            draw.rectangle((x, 114, x + 9, 121), fill='#19235f', outline='#3a4fb0')
            if used is not None:
                filled = round(max(0, min(1, used / 10 - cell)) * 9)
                if filled:
                    draw.rectangle((x, 114, x + filled - 1, 121), fill=mix(start, tip, (cell + 1) / max(1, used / 10)))
                    draw.line((x, 114, x + filled - 1, 114), fill='#e2ffc4')
                    if old:
                        draw.line((x, 120, x + filled - 1, 114), fill=outline)
    elif panel['kind'] == 'clock':
        centre(11, 'TOKEN TV')
        # Colon uses the original bundled block font; other labels use a crisp 5x7 grid.
        draw.text((64, 61), date.strftime('%H:%M'), font=face('press-start-2p.ttf', 18),
                  fill=cream, stroke_width=1, stroke_fill=outline, anchor='mt')
        centre(88, date.strftime('%a %d %b').upper())
        centre(105, date.tzname() or 'LOCAL', color='#b9d2ff')
        for x in range(12, 119, 12):
            draw.rectangle((x, 115, x + 5, 119), fill='#b388ff')
    elif panel['kind'] == 'status':
        centre(11, 'LIVE STATUS')
        rows = list(snapshot['accounts'].values())
        reporting = sum(row['status'] == 'ok' for row in rows)
        # A slash is rendered by the bundled pixel font.
        draw.text((64, 62), f'{reporting}/{len(rows)}', font=face('press-start-2p.ttf', 24),
                  fill=cream, stroke_width=1, stroke_fill=outline, anchor='mt')
        centre(94, 'ACCOUNTS LIVE', color='#b9d2ff')
        updated = snapshot.get('updated_at')
        draw.text((64, 110), datetime.fromtimestamp(updated, date.tzinfo).strftime('%H:%M') if updated else '--',
                  font=face('press-start-2p.ttf', 9), fill=cream, anchor='mt')
    else:
        centre(11, 'TOKEN TV')
        sprite('grok', (44, 36, 40, 40))
        centre(93, 'NO ACCOUNT')
    return image


def reset_text(window, now):
    reset = window.get('resets_at') if window else None
    if not reset:
        return '--'
    minutes = max(0, int((reset - now + 59) // 60))
    return (f'{minutes // 1440}d {minutes % 1440 // 60}h' if minutes >= 1440
            else f'{minutes // 60}h {minutes % 60}m')


def text_fit(cv, xy, value, name, size, color, *, anchor='lt', width=112, glow=None, weight=None):
    """Fit user aliases without squeezing letters or drawing outside their panel."""
    value = str(value)
    while size > 7 and cv.draw.textlength(value, font=face(name, size, weight)) > width:
        size -= 1
    while value and cv.draw.textlength(value, font=face(name, size, weight)) > width:
        value = value[:-1]
    cv.text(xy, value, face(name, size, weight), color, anchor=anchor, glow=glow)


def space_sky(cv, phase):
    rng = random.Random(7)
    for index in range(40):
        x, y = rng.randrange(5, 123), rng.randrange(26, 123)
        color = '#ecf4ff' if (index + phase) % 8 == 0 else '#5c6896'
        cv.back.point((x, y), fill=color)
    # A native circular crescent; its position and proportions are never resized.
    cv.back.ellipse((51, 28, 77, 54), fill='#e9e2c8')
    cv.back.ellipse((60, 25, 81, 50), fill='#080c1e')


def instrument_panel(panel, snapshot, date, now, style, phase=0):
    """Digital, Neon, HUD, Pixel, Space and Game Boy each use their own drawing language."""
    provider = panel.get('row', {}).get('provider', 'grok')
    backgrounds = {'digital': '#020906', 'neon': '#04030a', 'hud': '#03080e',
                   'pixel': '#0b0e12', 'space': '#080c1e', 'gameboy': LIGHTEST}
    cv = Canvas(backgrounds[style], size=128)
    accent = (ACCENT[style][provider][0] if style in ('neon', 'hud') else
              '#7dffd0' if style == 'digital' else DARKEST if style == 'gameboy' else
              '#96b6e8' if style == 'space' else PROVIDER_INK[provider])
    text = '#fff3d6' if style == 'space' else DARKEST if style == 'gameboy' else '#7dffd0' if style == 'digital' else '#d9dde1'
    dim = DARK if style == 'gameboy' else '#4dbb92' if style == 'digital' else '#a9bdf0'
    title_font = {'digital': 'vt323.woff2', 'neon': 'orbitron.ttf', 'hud': 'chakra-petch-700.woff2',
                  'gameboy': 'press-start-2p.ttf', 'space': 'press-start-2p.ttf', 'pixel': 'press-start-2p.ttf'}[style]
    title_size = {'digital': 18, 'neon': 9, 'hud': 12}.get(style, 8)
    number_font = {'digital': 'dseg7-classic-bold.woff2', 'neon': 'oxanium.woff2',
                   'hud': 'chakra-petch-700.woff2'}.get(style, 'press-start-2p.ttf')
    number_size = {'digital': 29, 'neon': 36, 'hud': 32}.get(style, 22)
    glow = accent if style == 'neon' else None
    if style == 'digital':
        for y in range(0, 128, 3):
            cv.back.line((0, y, 127, y), fill='#04130d')
        cv.back.rectangle((2, 2, 125, 125), outline='#22694f')
        cv.back.line((3, 25, 124, 25), fill='#0f3a2c')
    elif style == 'neon':
        for y in range(4, 125, 8):
            for x in range(4, 125, 8):
                cv.back.point((x, y), fill='#0e0b1c')
        cv.glow.rounded_rectangle((3, 3, 124, 124), radius=10, outline=accent, width=3)
        cv.draw.rounded_rectangle((3, 3, 124, 124), radius=10, outline=mix(accent, '#ffffff', .45))
    elif style == 'hud':
        for pos in range(0, 128, 12):
            cv.back.line((pos, 0, pos, 127), fill='#0b1a28')
            cv.back.line((0, pos, 127, pos), fill='#0b1a28')
        corners = [(3, 3), (112, 3), (124, 15), (124, 124), (15, 124), (3, 112), (3, 3)]
        cv.draw.line(corners, fill=accent)
        cv.draw.line((7, 8, 20, 8), fill=accent, width=2)
    elif style == 'space':
        space_sky(cv, phase)
        cv.draw.rectangle((2, 2, 125, 125), outline='#26305a')
    elif style == 'gameboy':
        cv.draw.rectangle((2, 2, 125, 125), outline=DARKEST, width=2)
        cv.draw.rectangle((5, 5, 122, 122), outline=DARK)
        cv.draw.line((5, 25, 122, 25), fill=DARK)
    else:
        cv.draw.rectangle((2, 2, 125, 125), outline='#28313a')
        cv.draw.line((3, 25, 124, 25), fill='#202730')

    def label(x, y, value, size=title_size, color=text, anchor='lt', width=112):
        text_fit(cv, (x, y), value, title_font, size, color, anchor=anchor, width=width, glow=glow, weight=700)

    def bot(box):
        tint = accent if style in ('digital', 'neon', 'hud', 'gameboy') else None
        detail = LIGHTEST if style == 'gameboy' else backgrounds[style]
        art = bot_sprite(provider, box[2], box[3], tint, detail)
        if style == 'hud':
            art = scanlined(art)
        place_bot(cv.ink, art, box)
        if style == 'neon':
            place_bot(cv.bloom, bot_sprite(provider, box[2], box[3], accent), box)

    if panel['kind'] == 'usage':
        row, window = panel['row'], panel['window']
        bot((7, 7, 18, 15))
        label(30, 9, row['alias'], width=89)
        period = window['label'] if window else STATUS.get(row['status'], 'NO DATA')
        label(9, 29, period, color=dim)
        old = row['status'] == 'stale'
        if old:
            label(118, 29, 'OLD', color='#ffcf5a' if style == 'digital' else DARK if style == 'gameboy' else '#ff9a9a', anchor='rt')
        used = window['used_percent'] if window else None
        if style == 'space':
            drift = round(2 * math.sin(phase * 2 * math.pi / ANIMATION_FRAMES))
            cx, cy = 27 + drift, 64
            cv.draw.ellipse((cx - 19, cy - 19, cx + 19, cy + 19), fill='#404e8c' if provider == 'grok' else '#161e40', outline='#96b6e8')
            cv.draw.arc((cx - 15, cy - 15, cx + 15, cy + 15), 200, 250, fill='#ecf4ff')
            bot((cx - 16, cy - 14, 32, 28))
        else:
            bot((8, 46, 34, 31))
        number = str(round(used)) if used is not None else '--'
        size = number_size
        available = 71 if used is None else 58
        while cv.draw.textlength(number, font=face(number_font, size, 800 if style == 'neon' else None)) > available:
            size -= 1
        number_face = face(number_font, size, 800 if style == 'neon' else None)
        right = 107 if used is not None else 118
        if style == 'digital':
            cv.text((right, 47), ghost(number), number_face, '#0d3326', anchor='rt')
        cv.text((right, 47), number, number_face, text, anchor='rt', glow=glow)
        if used is not None:
            label(118, 61, '%', size=12, anchor='rt')
        label(118, 79, 'USED' if used is not None else 'UNKNOWN', size=8, color=dim, anchor='rt')
        label(9, 92, 'RESET', size=9, color=dim)
        label(118, 101, reset_text(window, now).upper() if style in ('pixel', 'space', 'gameboy') else reset_text(window, now),
              size=title_size, anchor='rt', color='#ffcf5a' if style == 'digital' else text)
        if style == 'gameboy':
            colors, track, empty = (DARKEST, DARK), LIGHT, DARK
        elif style == 'pixel':
            colors, track, empty = band('retro', used or 0), '#28313a', '#6c7a87'
        elif style == 'space':
            colors, track, empty = band('retro', used or 0), '#26305a', '#808cb2'
        else:
            colors = band(style, used or 0)
            track = {'digital': '#0b2a1f', 'neon': '#15122a', 'hud': '#0c1c2b'}[style]
            empty = {'digital': '#2a6b52', 'neon': '#4a4170', 'hud': '#22476a'}[style]
        gauge(cv, (9, 114, 118, 121), used, colors, gap=2, stale=old, track=track, empty=empty,
              shape='round' if style == 'neon' else 'skew' if style == 'hud' else 'rect',
              skew=2 if style == 'hud' else 0, glow=style in ('digital', 'neon', 'hud'),
              shade=style == 'pixel', stepped=style in ('pixel', 'gameboy'))
    elif panel['kind'] == 'clock':
        label(64, 10, 'TOKEN TV', anchor='mt')
        text_fit(cv, (64, 62 if style == 'space' else 48), date.strftime('%H:%M'), number_font, 30 if style in ('digital', 'neon', 'hud') else 19,
                 text, anchor='mt', glow=glow)
        label(64, 91 if style == 'space' else 86, date.strftime('%a %d %b').upper(), size=title_size, anchor='mt')
        label(64, 109 if style == 'space' else 106, date.tzname() or 'LOCAL', color=dim, anchor='mt')
    elif panel['kind'] == 'status':
        label(64, 10, 'LIVE STATUS', anchor='mt')
        rows = list(snapshot['accounts'].values())
        reporting = sum(row['status'] == 'ok' for row in rows)
        # DSEG lacks a slash; use the style's label face for this count.
        count_font = title_font if style == 'digital' else number_font
        text_fit(cv, (64, 61 if style == 'space' else 46), f'{reporting}/{len(rows)}', count_font, 32 if style == 'digital' else 22 if style == 'space' else 26,
                 text, anchor='mt', glow=glow)
        label(64, 92 if style == 'space' else 83, 'ACCOUNTS LIVE', size=title_size, anchor='mt', color=dim)
        updated = snapshot.get('updated_at')
        label(64, 110 if style == 'space' else 102, datetime.fromtimestamp(updated, date.tzinfo).strftime('%H:%M') if updated else '--',
              size=title_size, anchor='mt')
    else:
        label(64, 10, 'TOKEN TV', anchor='mt')
        bot((42, 43, 44, 38))
        label(64, 98, 'NO ACCOUNT', color=dim, anchor='mt')
    image = cv.finish(blur=2)
    return to_four_shades(image) if style == 'gameboy' else image


def render_images(snapshot, style='digital', timezone='Europe/London', now=None, phase=0, layout='windows'):
    if style not in STYLES:
        raise ValueError('Unknown display style')
    now = time.time() if now is None else now
    date = datetime.fromtimestamp(now, ZoneInfo(timezone))
    if style in ('undertale', 'deltarune'):
        from token_tv.local_games import render_panel
        images = [render_panel(p, snapshot, style, now, phase % ANIMATION_FRAMES, timezone) for p in panel_data(snapshot, now, layout)]
    else:
        from token_tv.local_games import render_account
        images = [(render_account(p['row'], now, phase if style == 'space' else 0, style) if p['kind'] == 'account'
                   else retro_panel(p, snapshot, date, now) if style == 'retro'
                   else instrument_panel(p, snapshot, date, now, style,
                                         phase % ANIMATION_FRAMES if style == 'space' else 0))
                  for p in panel_data(snapshot, now, layout)]
    if snapshot.get('weather') is not None:
        from token_tv.weather_face import render_panel
        images[4] = render_panel(snapshot['weather'], now, phase)
    return images


def encode(image, animated=None):
    output = io.BytesIO()
    if animated:
        image.save(output, format='GIF', save_all=True, append_images=animated, loop=0,
                   duration=ANIMATION_SPEED, disposal=2, optimize=False)
    else:
        image.save(output, format='JPEG', quality=95, subsampling=0)
    return output.getvalue()


def render_panels(snapshot, style='digital', timezone='Europe/London', now=None, layout='windows'):
    now = time.time() if now is None else now
    images = render_images(snapshot, style, timezone, now, layout=layout)
    if style not in ('space', 'undertale', 'deltarune'):
        result = [encode(image) for image in images]
    else:
        phases = [images] + [render_images(snapshot, style, timezone, now, phase, layout)
                             for phase in range(1, ANIMATION_FRAMES)]
        result = [encode(images[i], [phase[i] for phase in phases[1:]]) for i in range(5)]
    if snapshot.get('weather') is not None:
        from token_tv.weather_face import render_animation
        result[4] = render_animation(snapshot['weather'], now)
    return result


def render_preview(snapshot, style='digital', timezone='Europe/London', now=None, panels=(1, 2, 3, 4, 5), layout='windows'):
    now = time.time() if now is None else now
    phases = ANIMATION_FRAMES if style in ('space', 'undertale', 'deltarune') else 1
    if snapshot.get('weather') is not None:
        from token_tv.weather_face import FRAMES
        phases = FRAMES
    images = []
    for phase in range(phases):
        preview = Image.new('RGB', (640, 128))
        for i, panel in enumerate(render_images(snapshot, style, timezone, now, phase, layout)):
            if i + 1 not in panels:
                panel = Image.new('RGB', (128, 128), '#101822')
                draw = ImageDraw.Draw(panel)
                draw.rectangle((3, 3, 124, 124), outline='#607485')
                for y, text in ((33, 'DIVOOM'), (53, 'WEATHER' if i == 4 else 'DEVICE FACE'),
                                (83, 'DEVICE MANAGED')):
                    pixel_text(draw, ((128 - (len(text) * 6 - 1)) // 2, y), text, 1, '#b1c6d7')
            preview.paste(panel, (i * 128, 0))
        images.append(preview)
    return encode(images[0], images[1:] if phases > 1 else None)
