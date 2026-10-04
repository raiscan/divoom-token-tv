"""Five native LCD panels over the Times Gate local HTTP API.

JPEG transport follows https://github.com/adiastra/divoom-gaming-gate.
Only pictures leave this module; account credentials never go to the clock.
"""
import base64
import hashlib
import io
import json
import os
import time
from pathlib import Path

from PIL import Image, ImageSequence

from token_tv.device import PhotoDisplay
# Public rendering helpers retained for callers of the device module.
from token_tv.times_gate_faces import panel_data, render_panels, render_preview


class LocalTokenRequired(ValueError):
    """The device requires its app-provided local credential."""


def screen_selection(value):
    try:
        panels = tuple(int(part) for part in value.split(','))
    except (ValueError, AttributeError):
        raise ValueError('Choose screen numbers 1 to 5') from None
    if not panels or len(set(panels)) != len(panels) or any(i not in range(1, 6) for i in panels):
        raise ValueError('Choose distinct screen numbers 1 to 5')
    return panels


class TimesGateDisplay(PhotoDisplay):
    def __init__(self, base_url, panels=(1, 2, 3, 4, 5), token_file=None,
                 local_token=None, weather_clock=None, independence=None):
        super().__init__(base_url)
        self.panels = screen_selection(','.join(map(str, panels)))
        self.token_file = Path(token_file) if token_file else None
        self.local_token = local_token
        if self.token_file and self.token_file.is_file():
            self.local_token = self.validate_token(json.loads(self.token_file.read_text()).get('local_token'))
        if weather_clock is not None and (5 in self.panels or type(weather_clock) is not int or
                weather_clock <= 0 or type(independence) is not int or independence <= 0):
            raise ValueError('Weather requires screen 5 reserved and a saved independent layout ID')
        self.weather_clock = weather_clock
        self.independence = independence
        self.weather_sent = None
        self.pic_id = None
        self.sent = {}

    @staticmethod
    def validate_token(value):
        if type(value) is not int or not 0 <= value <= 2147483647:
            raise ValueError('Local Token must be a number')
        return value

    def save_token(self, value):
        if not self.token_file:
            raise ValueError('Local token storage is not configured')
        value = self.validate_token(value)
        # Validate with a read-only device command before saving or changing the live credential.
        probe = TimesGateDisplay(self.base_url, local_token=value)
        probe.command('Draw/GetHttpGifId')
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.token_file.with_suffix('.tmp')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'w') as file:
            os.fchmod(file.fileno(), 0o600)
            json.dump({'local_token': value}, file)
        temporary.replace(self.token_file)
        self.local_token = value
        self.sent.clear()
        self.weather_sent = None

    def command(self, name, **fields):
        if self.local_token is not None:
            fields['LocalToken'] = self.local_token
        _, raw = self.request('/post', json.dumps(dict(Command=name, **fields)).encode(),
                              {'Content-Type': 'application/json'})
        reply = json.loads(raw)
        if isinstance(reply, dict) and reply.get('error_code') == 'DeviceToken is err':
            raise LocalTokenRequired('Enter Local Token from the Times Gate device settings')
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
            raise ValueError('Five Times Gate panel images are required')
        prepared = []
        for body in frames:
            with Image.open(io.BytesIO(body)) as image:
                if image.format not in ('JPEG', 'GIF') or image.size != (128, 128):
                    raise ValueError('Times Gate frames must be native JPEGs or GIFs')
                if image.format == 'JPEG':
                    prepared.append(([body], 1000))
                else:
                    if not 1 <= image.n_frames <= 100:
                        raise ValueError('Times Gate animations require 1 to 100 frames')
                    speed = max(20, min(10000, int(image.info.get('duration', 250))))
                    animation = []
                    for frame in ImageSequence.Iterator(image):
                        output = io.BytesIO()
                        frame.convert('RGB').save(output, format='JPEG', quality=95, subsampling=0)
                        animation.append(output.getvalue())
                    prepared.append((animation, speed))
        now = time.monotonic() if now is None else now
        current = self.command('Draw/GetHttpGifId').get('PicId')
        if type(current) is not int or not 0 <= current < 2147483647:
            raise ValueError('Times Gate did not report a valid picture ID')
        # A reboot or another controller invalidates our view of the display.
        if current != self.pic_id:
            self.sent.clear()
            self.weather_sent = None
        self.pic_id = max(self.pic_id or 0, current)
        if self.weather_clock is not None and (self.weather_sent is None or now - self.weather_sent >= 300):
            self.command('Channel/SetClockSelectId', ClockId=self.weather_clock, LcdIndex=4,
                         LcdIndependence=self.independence)
            self.weather_sent = now
        receipts = []
        for panel, body in enumerate(frames):
            if panel + 1 not in self.panels:
                continue
            digest = hashlib.sha256(body).hexdigest()
            previous = self.sent.get(panel)
            if previous and previous[0] == digest and now - previous[1] < 300:
                continue
            if self.pic_id >= 2147483646:
                raise ValueError('Times Gate picture ID exhausted; restart the display')
            self.pic_id += 1
            animation, speed = prepared[panel]
            for offset, frame in enumerate(animation):
                self.command('Draw/SendHttpGif', LcdArray=[int(i == panel) for i in range(5)],
                             PicNum=len(animation), PicOffset=offset, PicID=self.pic_id, PicSpeed=speed,
                             PicWidth=128, PicData=base64.b64encode(frame).decode('ascii'))
            # A partial animation never counts as a delivered panel.
            self.sent[panel] = (digest, now)
            receipts.append({'panel': panel + 1, 'pic_id': self.pic_id, 'bytes': len(body),
                             'frames': len(animation), 'sha256': digest})
        return receipts
