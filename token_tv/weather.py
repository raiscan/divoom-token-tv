"""Cached, credential-free forecasts from Open-Meteo; never invent missing values."""
import copy
import json
import math
import threading
import time
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


def number(value, minimum=-100, maximum=100):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        return None
    return value


def condition(code, is_day=True):
    if type(code) is not int:
        return 'UNKNOWN'
    if code == 0:
        return 'SUNNY' if is_day is True else 'CLEAR NIGHT' if is_day is False else 'CLEAR'
    if code in (1, 2):
        return 'PARTLY CLOUDY'
    if code == 3:
        return 'CLOUDY'
    if code in (45, 48):
        return 'FOG'
    if code in (51, 53, 55, 56, 57):
        return 'DRIZZLE'
    if code in (61, 63, 65, 66, 67):
        return 'RAIN'
    if code in (71, 73, 75, 77, 85, 86):
        return 'SNOW'
    if code in (80, 81, 82):
        return 'SHOWERS'
    if code in (95, 96, 99):
        return 'STORM'
    return 'UNKNOWN'


def fetch_weather(latitude, longitude, timezone):
    query = urlencode({'latitude': latitude, 'longitude': longitude, 'timezone': timezone,
                       'current': 'temperature_2m,weather_code,is_day',
                       'daily': 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
                       'forecast_days': 3, 'temperature_unit': 'celsius', 'timeformat': 'unixtime'})
    request = Request('https://api.open-meteo.com/v1/forecast?' + query,
                      headers={'User-Agent': 'TokenTV/1.0 personal weather display'})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def normalize(payload, timezone, now):
    if not isinstance(payload, dict):
        raise ValueError('Expected a forecast object')
    current = payload.get('current') or {}
    daily = payload.get('daily') or {}
    if not isinstance(current, dict) or not isinstance(daily, dict):
        raise ValueError('Expected current and daily forecasts')
    if payload.get('current_units', {}).get('temperature_2m') != '°C':
        raise ValueError('Expected Celsius forecast')
    zone = ZoneInfo(timezone)
    days = []
    for index, timestamp in enumerate(daily.get('time', [])):
        if number(timestamp, 1, 4102444800) is None:
            continue
        def value(key):
            values = daily.get(key) or []
            return values[index] if index < len(values) else None
        days.append({'date': datetime.fromtimestamp(timestamp, zone).date().isoformat(),
                     'code': value('weather_code'), 'high': number(value('temperature_2m_max')),
                     'low': number(value('temperature_2m_min')),
                     'rain': number(value('precipitation_probability_max'), 0, 100)})
    temperature = number(current.get('temperature_2m'))
    if temperature is None and not days:
        raise ValueError('Forecast has no readings')
    return {'status': 'ok', 'fetched_at': now,
            'observed_at': number(current.get('time'), 1, 4102444800),
            'temperature': temperature, 'code': current.get('weather_code'),
            'is_day': {0: False, 1: True}.get(current.get('is_day')), 'days': days}


class WeatherStore:
    def __init__(self, city, latitude, longitude, timezone='Europe/London', cache_path=None,
                 fetch=fetch_weather):
        if not city or number(latitude, -90, 90) is None or number(longitude, -180, 180) is None:
            raise ValueError('A city and valid coordinates are required')
        ZoneInfo(timezone)
        self.city, self.latitude, self.longitude, self.timezone = city, latitude, longitude, timezone
        self.cache_path, self.fetch = cache_path, fetch
        self.lock = threading.Lock()
        self.data = {'status': 'loading', 'temperature': None, 'days': [], 'fetched_at': 0}
        if cache_path and cache_path.is_file():
            try:
                cache = json.loads(cache_path.read_text())
                if cache.get('location') == [city, latitude, longitude, timezone]:
                    self.data = dict(cache['data'], status='stale')
            except (ValueError, KeyError, TypeError):
                pass

    def refresh(self, now=None):
        now = time.time() if now is None else now
        try:
            data = normalize(self.fetch(self.latitude, self.longitude, self.timezone), self.timezone, now)
            if self.cache_path:
                from token_tv.live import write_json
                write_json(self.cache_path, {'location': [self.city, self.latitude, self.longitude, self.timezone],
                                            'data': data})
        except (OSError, ValueError, KeyError, TypeError):
            with self.lock:
                self.data['status'] = 'stale' if self.data.get('fetched_at') else 'error'
            return
        with self.lock:
            self.data = data

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        with self.lock:
            data = copy.deepcopy(self.data)
        if data['status'] == 'ok' and (now - data['fetched_at'] > 1800 or
                data.get('observed_at') and now - data['observed_at'] > 3600):
            data['status'] = 'stale'
        # Old forecast dates never masquerade as today's or tomorrow's forecast.
        data.update(city=self.city, timezone=self.timezone, source='Open-Meteo', units='C')
        return data
