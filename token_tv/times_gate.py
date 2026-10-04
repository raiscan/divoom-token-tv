"""Five native LCD panels over the Times Gate local HTTP API.

JPEG transport follows https://github.com/adiastra/divoom-gaming-gate.
Only pictures leave this module; account credentials never go to the clock.
"""
import base64
import hashlib
import io
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from token_tv.device import PhotoDisplay
from token_tv.display import (BACKGROUND, TEXT, TRACK, STATUS, STYLES, PROVIDER_INK,
                              gauge_color, pixel_text)
from token_tv.themes import ACCENT, Canvas, band, bot_sprite, mix, pixel_scene


class TimesGateDisplay(PhotoDisplay):
    def __init__(self, base_url):
        super().__init__(base_url)
        self.pic_id = None
        self.sent = {}

    def command(self, name, **fields):
        _, raw = self.request('/post', json.dumps(dict(Command=name, **fields)).encode(),
                              {'Content-Type': 'application/json'})
        reply = json.loads(raw)
        if not isinstance(reply, dict) or type(reply.get('error_code')) is not int or reply['error_code'] != 0:
            raise ValueError('Times Gate rejected the command')
        return reply

    @staticmethod
    def selections(value):
        if (not isinstance(value, list) or len(value) != 5 or
                any(type(index) is not int or not 0 <= index <= 255 for index in value)):
            raise ValueError('Five Times Gate channel selections are required')
        return value

    def capture(self):
        indices = self.selections(self.command('Channel/GetIndex').get('SelectIndex'))
        return {'device_type': 'times-gate', 'device_url': self.base_url, 'SelectIndex': indices}

    def restore(self, original):
        if original.get('device_type') != 'times-gate' or original.get('device_url') != self.base_url:
            raise ValueError('The backup belongs to another display')
        indices = self.selections(original.get('SelectIndex'))
        self.command('Channel/SetIndex', SelectIndex=indices)
        self.sent.clear()

    def publish(self, frames, now=None):
        if len(frames) != 5:
            raise ValueError('Five Times Gate JPEG frames are required')
        for body in frames:
            with Image.open(io.BytesIO(body)) as image:
                if image.format != 'JPEG' or image.size != (128, 128):
                    raise ValueError('Times Gate frames must be 128 by 128 JPEGs')
        now = time.monotonic() if now is None else now
        current = self.command('Draw/GetHttpGifId').get('PicId')
        if type(current) is not int or not 0 <= current < 2147483647:
            raise ValueError('Times Gate did not report a valid picture ID')
        # A reboot or another controller invalidates our view of the display.
        if current != self.pic_id:
            self.sent.clear()
        self.pic_id = max(self.pic_id or 0, current)
        receipts = []
        for panel, body in enumerate(frames):
            digest = hashlib.sha256(body).hexdigest()
            previous = self.sent.get(panel)
            if previous and previous[0] == digest and now - previous[1] < 300:
                continue
            if self.pic_id >= 2147483646:
                raise ValueError('Times Gate picture ID exhausted; restart the display')
            self.pic_id += 1
            self.command('Draw/SendHttpGif', LcdArray=[int(i == panel) for i in range(5)],
                         PicNum=1, PicOffset=0, PicID=self.pic_id, PicSpeed=1000,
                         PicWidth=128, PicData=base64.b64encode(body).decode('ascii'))
            self.sent[panel] = (digest, now)
            receipts.append({'panel': panel + 1, 'pic_id': self.pic_id, 'bytes': len(body), 'sha256': digest})
        return receipts


def panel_data(snapshot, now=None):
    """Each window owns its percentage and reset; overflow rotates every five minutes."""
    now = time.time() if now is None else now
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
    scene = Canvas(outline)
    pixel_scene(scene, provider, 0)
    image = Image.new('RGB', (128, 128), '#0a0f2c')
    # Reuse the original scene as a backdrop; draw all information at native size.
    backdrop = scene.base.crop((6, 2, 234, 76)).resize((118, 75), Image.Resampling.NEAREST)
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
        from token_tv.themes import face
        draw.text((64, 42), date.strftime('%H:%M'), font=face('press-start-2p.ttf', 18),
                  fill=cream, stroke_width=1, stroke_fill=outline, anchor='mt')
        centre(75, date.strftime('%a %d %b').upper())
        centre(94, date.tzname() or 'LOCAL', color='#b9d2ff')
        for x in range(12, 119, 12):
            draw.rectangle((x, 115, x + 5, 119), fill='#b388ff')
    elif panel['kind'] == 'status':
        centre(11, 'LIVE STATUS')
        rows = list(snapshot['accounts'].values())
        reporting = sum(row['status'] == 'ok' for row in rows)
        # A slash is rendered by the bundled pixel font.
        from token_tv.themes import face
        draw.text((64, 40), f'{reporting}/{len(rows)}', font=face('press-start-2p.ttf', 24),
                  fill=cream, stroke_width=1, stroke_fill=outline, anchor='mt')
        centre(74, 'ACCOUNTS LIVE', color='#b9d2ff')
        updated = snapshot.get('updated_at')
        centre(91, 'UPDATED', color='#b9d2ff')
        draw.text((64, 105), datetime.fromtimestamp(updated, date.tzinfo).strftime('%H:%M') if updated else '--',
                  font=face('press-start-2p.ttf', 9), fill=cream, anchor='mt')
    else:
        centre(11, 'TOKEN TV')
        sprite('grok', (44, 36, 40, 40))
        centre(93, 'NO ACCOUNT')
    return image


def render_panels(snapshot, style='digital', timezone='Europe/London', now=None):
    if style not in STYLES:
        raise ValueError('Unknown display style')
    now = time.time() if now is None else now
    date = datetime.fromtimestamp(now, ZoneInfo(timezone))
    backgrounds = {'digital': BACKGROUND, 'pixel': '#101721', 'neon': '#100a20',
                   'retro': '#141d52', 'hud': '#06101a', 'space': '#060a18'}
    frames = []
    for panel in panel_data(snapshot, now):
        if style == 'retro':
            image = retro_panel(panel, snapshot, date, now)
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=95, subsampling=0)
            frames.append(output.getvalue())
            continue
        image = Image.new('RGB', (128, 128), backgrounds[style])
        draw = ImageDraw.Draw(image)
        def text(y, value, size=12, color=TEXT, bold=False):
            face = ImageFont.truetype(str(Path(__file__).with_name('web') / 'manrope.ttf'), size)
            face.set_variation_by_axes([700 if bold else 500])
            # Aliases are user text; fit them without clipping at the panel edges.
            while draw.textlength(value, font=face) > 116 and size > 8:
                size -= 1
                face = ImageFont.truetype(str(Path(__file__).with_name('web') / 'manrope.ttf'), size)
                face.set_variation_by_axes([700 if bold else 500])
            draw.text((64, y), value, font=face, fill=color, anchor='mt')
        if panel['kind'] == 'clock':
            text(8, 'TOKEN TV', 12, '#93c9b9', True)
            text(36, date.strftime('%H:%M'), 32, bold=True)
            text(81, date.strftime('%a %d %b'), 13)
            text(105, date.tzname() or timezone, 10)
        elif panel['kind'] == 'status':
            rows = list(snapshot['accounts'].values())
            reporting = sum(row['status'] == 'ok' for row in rows)
            text(8, 'LIVE STATUS', 12, '#93c9b9', True)
            text(37, f'{reporting}/{len(rows)}', 32, bold=True)
            text(80, 'accounts reporting', 10)
            updated = snapshot.get('updated_at')
            label = datetime.fromtimestamp(updated, ZoneInfo(timezone)).strftime('%H:%M') if updated else '—'
            text(106, 'Updated ' + label, 10)
        elif panel['kind'] == 'empty':
            text(40, 'TOKEN TV', 15, '#7a8999', True)
            text(76, 'No account', 11, '#7a8999')
        else:
            row, window = panel['row'], panel['window']
            ink = PROVIDER_INK[row['provider']]
            draw.rectangle((0, 0, 127, 2), fill=ink)
            text(8, row['alias'], 12, ink, True)
            label = window['label'] if window else STATUS.get(row['status'], 'NO DATA')
            text(28, label + (' / OLD' if row['status'] == 'stale' else ''), 11)
            used = window['used_percent'] if window else None
            text(45, f'{used:.0f}%' if used is not None else '—', 33, bold=True)
            text(83, 'USED' if used is not None else 'UNKNOWN', 9, '#9ba6b4')
            draw.rounded_rectangle((8, 98, 119, 105), radius=3, fill=TRACK)
            if used is not None and used > 0:
                width = max(1, round(min(used, 100) / 100 * 111))
                draw.rectangle((8, 98, 8 + width, 105), fill=gauge_color(used))
            reset = window.get('resets_at') if window else None
            if reset:
                minutes = max(0, int((reset - now + 59) // 60))
                remaining = f'{minutes // 1440}d {minutes % 1440 // 60}h' if minutes >= 1440 else f'{minutes // 60}h {minutes % 60}m'
                text(113, 'Reset ' + remaining, 9)
            else:
                text(113, 'Reset —', 9)
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=90, subsampling=0)
        frames.append(output.getvalue())
    return frames


def render_preview(snapshot, style='digital', timezone='Europe/London'):
    image = Image.new('RGB', (640, 128))
    for index, body in enumerate(render_panels(snapshot, style, timezone)):
        with Image.open(io.BytesIO(body)) as panel:
            image.paste(panel, (index * 128, 0))
    output = io.BytesIO()
    image.save(output, format='JPEG', quality=90, subsampling=0)
    return output.getvalue()
