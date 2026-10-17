"""Official 2026 MotoGP weekend dates, offline cache, and iCalendar export."""
from __future__ import annotations

import calendar
import datetime as dt
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import tempfile
import urllib.request

YEAR = 2026
SOURCE = 'https://www.motogp.com/en/news/2026/01/01/2026-motogp-calendar/755478'
CALENDAR_URL = 'https://www.motogp.com/en/calendar/2026'
VERIFIED = '2026-10-17'
CACHE = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'motogp-calendar' / '2026.json'

# Dates are circuit-local calendar dates, never assumed session start times.
_ROUNDS = [
    ('03-01', 'Thailand', 'Buriram', 'TH', 'THA'),
    ('03-22', 'Brazil', 'Goiania', 'BR', 'BRA'),
    ('03-29', 'USA', 'Austin', 'US', 'USA'),
    ('04-26', 'Spain', 'Jerez', 'ES', 'ESP'),
    ('05-10', 'France', 'Le Mans', 'FR', 'FRA'),
    ('05-17', 'Catalonia', 'Barcelona', 'ES', 'CAT'),
    ('05-31', 'Italy', 'Mugello', 'IT', 'ITA'),
    ('06-07', 'Hungary', 'Balaton', 'HU', 'HUN'),
    ('06-21', 'Czechia', 'Brno', 'CZ', 'CZE'),
    ('06-28', 'Netherlands', 'Assen', 'NL', 'NED'),
    ('07-12', 'Germany', 'Sachsenring', 'DE', 'GER'),
    ('08-09', 'Great Britain', 'Silverstone', 'GB', 'GBR'),
    ('08-30', 'Aragon', 'MotorLand', 'ES', 'ARA'),
    ('09-13', 'San Marino', 'Misano', 'SM', 'RSM'),
    ('09-20', 'Austria', 'Spielberg', 'AT', 'AUT'),
    ('10-04', 'Japan', 'Motegi', 'JP', 'JPN'),
    ('10-11', 'Indonesia', 'Mandalika', 'ID', 'INA'),
    ('10-25', 'Australia', 'Phillip Island', 'AU', 'AUS'),
    ('11-01', 'Malaysia', 'Sepang', 'MY', 'MAL'),
    ('11-08', 'Qatar', 'Lusail', 'QA', 'QAT'),
    ('11-22', 'Portugal', 'Portimao', 'PT', 'POR'),
    ('11-29', 'Valencia', 'Cheste', 'ES', 'VAL'),
]


def seed():
    return {'year': YEAR, 'verified': VERIFIED, 'source': SOURCE, 'races': [
        {'round': i, 'date': f'{YEAR}-{date}', 'country': country, 'circuit': circuit,
         'flag': flag, 'code': code}
        for i, (date, country, circuit, flag, code) in enumerate(_ROUNDS, 1)
    ]}


def race_date(race):
    return dt.date.fromisoformat(race['date'])


def weekend_start(race):
    return race_date(race) - dt.timedelta(days=2)


def next_race(races, today=None):
    today = today or dt.date.today()
    return next((r for r in races if race_date(r) >= today), None)


def date_range(race):
    start, end = weekend_start(race), race_date(race)
    if start.month == end.month:
        return f'{start.day}–{end.day} {end:%b}'
    return f'{start.day} {start:%b} – {end.day} {end:%b}'


def validate(data):
    races = data['races']
    if data['year'] != YEAR or len(races) != len(_ROUNDS):
        raise ValueError('The source no longer contains the expected 22-round 2026 calendar.')
    known = {r['country']: r for r in seed()['races']}
    seen = set()
    previous = dt.date(YEAR, 1, 1)
    for i, race in enumerate(races, 1):
        date = race_date(race)
        if (race['round'] != i or race['country'] not in known or race['country'] in seen
                or date.year != YEAR or date <= previous):
            raise ValueError('The updated calendar has invalid or unexpected race dates.')
        if any(race[key] != known[race['country']][key] for key in ('code', 'flag')):
            raise ValueError('Unexpected calendar metadata.')
        if not isinstance(race['circuit'], str) or not race['circuit'].strip():
            raise ValueError('Missing circuit.')
        seen.add(race['country'])
        previous = date
    dt.date.fromisoformat(data['verified'])
    return data


def load_calendar():
    try:
        return validate(json.loads(CACHE.read_text()))
    except (OSError, ValueError, KeyError, TypeError):
        return seed()


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.table = []
        elif tag == 'tr' and self.table is not None:
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []

    def handle_data(self, text):
        if self.cell is not None:
            self.cell.append(text)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == 'table' and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def parse_official(html):
    parser = TableParser()
    parser.feed(html)
    known = {r['country']: r for r in seed()['races']}
    months = {name: number for number, name in enumerate(calendar.month_name) if name}
    for table in parser.tables:
        rows = [row for row in table if len(row) == 4 and row[0].isdigit()]
        if not rows:
            continue
        data = seed()
        data['races'] = []
        for number, date_text, country, circuit in rows:
            if country not in known:
                raise ValueError('The official source has an unfamiliar round. Keeping your saved calendar.')
            day, month = date_text.split()
            date = dt.date(YEAR, months[month], int(day))
            data['races'].append(dict(known[country], round=int(number), date=date.isoformat(), circuit=circuit))
        data['verified'] = dt.date.today().isoformat()
        return validate(data)
    raise ValueError('The official calendar table could not be read. Keeping your saved calendar.')


def refresh_calendar():
    request = urllib.request.Request(SOURCE, headers={'User-Agent': 'Mozilla/5.0 MotoGPDesktop/1.0'})
    with urllib.request.urlopen(request, timeout=20) as response:
        html = response.read(4_000_001)
    if len(html) > 4_000_000:
        raise ValueError('Official calendar response was too large.')
    data = parse_official(html.decode('utf-8'))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=CACHE.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as file:
            json.dump(data, file, indent=2)
            file.write('\n')
        os.replace(name, CACHE)
    finally:
        Path(name).unlink(missing_ok=True)
    return data


def status(data=None, today=None):
    data = data or load_calendar()
    today = today or dt.date.today()
    race = next_race(data['races'], today)
    if race is None:
        return {'label': 'MotoGP · season complete', 'tooltip': '2026 season complete. Click to browse the calendar.'}
    active = weekend_start(race) <= today
    date = race_date(race)
    return {
        'label': f'MotoGP · {race["code"]} {date.day} {date:%b}',
        'tooltip': f'{"Race weekend" if active else "Up next"}: {race["country"]} · {race["circuit"]}\n'
                   f'{date_range(race)} {YEAR} · circuit-local dates\nClick: calendar · Right-click: official schedule',
    }


def _escape(value):
    return value.replace('\\', '\\\\').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')


def _fold(line):
    result, part, size = [], '', 0
    for char in line:
        length = len(char.encode('utf-8'))
        if size + length > 75:
            result.append(part)
            part, size = ' ', 1
        part += char
        size += length
    return '\r\n'.join(result + [part])


def export_ics(data, races=None):
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//MotoGP Calendar for Omarchy//EN',
             'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'X-WR-CALNAME:MotoGP 2026 race weekends']
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for race in data['races'] if races is None else races:
        end = race_date(race)
        lines += ['BEGIN:VEVENT', f'UID:2026-{race["code"].lower()}@motogp-calendar.local',
                  f'DTSTAMP:{stamp}', f'DTSTART;VALUE=DATE:{weekend_start(race):%Y%m%d}',
                  f'DTEND;VALUE=DATE:{end + dt.timedelta(days=1):%Y%m%d}',
                  'SUMMARY:' + _escape(f'MotoGP · {race["country"]} GP'),
                  'LOCATION:' + _escape(race['circuit']),
                  'DESCRIPTION:' + _escape('Race weekend in circuit-local dates. '
                  f'Grand Prix: {end:%d %B %Y}. Check MotoGP.com for confirmed session times. '
                  f'Dates verified {data["verified"]}. ' + CALENDAR_URL),
                  'URL:' + CALENDAR_URL, 'TRANSP:TRANSPARENT', 'END:VEVENT']
    return '\r\n'.join(_fold(line) for line in lines + ['END:VCALENDAR']) + '\r\n'
