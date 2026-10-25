"""Official MotoGP Grand Prix podiums and cancellations, cached for offline use."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import urllib.parse
import urllib.request

import calendar_data as calendar

API = 'https://api.motogp.pulselive.com/motogp/v1/results/'
BUNDLED = Path(__file__).with_name('podiums-2026.json')
CACHE = calendar.CACHE.with_name('podiums-2026.json')
API_CODES = {'ESP': 'SPA'}


def results_url(race):
    code = API_CODES.get(race['code'], race['code'])
    return f'https://www.motogp.com/en/gp-results/{calendar.YEAR}/{code}/MotoGP/RAC/Classification'


def validate(data):
    if data['year'] != calendar.YEAR or not isinstance(data['races'], dict):
        raise ValueError('Unexpected results season.')
    known = {r['code'] for r in calendar.seed()['races']}
    for code, result in data['races'].items():
        if code not in known or dt.date.fromisoformat(result['date']).year != calendar.YEAR:
            raise ValueError('Unexpected results event.')
        dt.date.fromisoformat(result['verified'])
        status = result.get('status', 'FINISHED')
        if status not in ('FINISHED', 'CANCELLED'):
            raise ValueError('Unexpected Grand Prix status.')
        podium = result['podium']
        if status == 'CANCELLED':
            if podium != []:
                raise ValueError('A cancelled Grand Prix cannot have a podium.')
            continue
        if len(podium) != 3 or [r['position'] for r in podium] != [1, 2, 3]:
            raise ValueError('Incomplete Grand Prix podium.')
        if len({r['rider'] for r in podium}) != 3:
            raise ValueError('Duplicate podium rider.')
        for rider in podium:
            if any(not isinstance(rider[key], str) or not rider[key].strip()
                   for key in ('rider', 'team')):
                raise ValueError('Missing podium rider or team.')
    return data


def load_results():
    data = {'year': calendar.YEAR, 'races': {}}
    for path in (BUNDLED, CACHE):
        try:
            loaded = validate(json.loads(path.read_text()))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        for code, result in loaded['races'].items():
            current = data['races'].get(code)
            if current is None or result['verified'] >= current['verified']:
                data['races'][code] = result
    return data


def result_for(data, race, today=None):
    today = today or dt.date.today()
    result = data['races'].get(race['code'])
    if (result is None or result['date'] != race['date']
            or calendar.race_date(race) > today):
        return None
    return result


def parse_classification(data):
    top = sorted((r for r in data['classification'] if r.get('position') in (1, 2, 3)),
                 key=lambda r: r['position'])
    if [r['position'] for r in top] != [1, 2, 3]:
        raise ValueError('The official classification has no complete podium.')
    return [{'position': r['position'], 'rider': r['rider']['full_name'],
             'team': r['team']['name']} for r in top]


def _request(endpoint, **params):
    url = API + endpoint
    if params:
        url += '?' + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 MotoGPCalendar/1.0'})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError('Official results response was too large.')
    return json.loads(raw)


def fetch_result(event, race, today=None):
    today = today or dt.date.today()
    if (event.get('test') is not False or event['season']['year'] != calendar.YEAR
            or event['date_end'] != race['date']
            or event['short_name'] != API_CODES.get(race['code'], race['code'])
            or calendar.race_date(race) > today):
        raise ValueError('The official results do not match this Grand Prix.')
    categories = _request('categories', eventUuid=event['id'])
    category = next(c for c in categories if c['name'].rstrip('™') == 'MotoGP')
    sessions = _request('sessions', eventUuid=event['id'], categoryUuid=category['id'])
    race_sessions = [s for s in sessions if s['type'] == 'RAC']
    session = next((s for s in race_sessions if s['status'] == 'FINISHED'), None)
    if session is None and race_sessions and all(s['status'] == 'CANCELLED' for s in race_sessions):
        session = race_sessions[-1]
    if session is None:
        return None
    result = {'date': race['date'], 'verified': today.isoformat(),
              'event_id': event['id'], 'session_id': session['id'],
              'source': results_url(race), 'status': session['status'], 'podium': []}
    if session['status'] == 'FINISHED':
        classification = _request(f'session/{session["id"]}/classification', test='false')
        result['podium'] = parse_classification(classification)
    validate({'year': calendar.YEAR, 'races': {race['code']: result}})
    return result


def refresh_results(races, today=None):
    """Keep saved results if individual events fail; never cache partial podiums."""
    today = today or dt.date.today()
    data = load_results()
    season = next(s for s in _request('seasons') if s['year'] == calendar.YEAR)
    events = _request('events', seasonUuid=season['id'], isFinished='true')
    expected = {API_CODES.get(r['code'], r['code']): r for r in races
                if calendar.race_date(r) <= today}
    pending = [event for event in events if event.get('test') is False
               and event['short_name'] in expected]
    errors = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch_result, event, expected[event['short_name']], today):
                expected[event['short_name']] for event in pending}
        for job in as_completed(jobs):
            race = jobs[job]
            try:
                result = job.result()
                if result is not None:
                    data['races'][race['code']] = result
            except Exception as error:
                errors.append(f'{race["code"]}: {error}')
    validate(data)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=CACHE.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write('\n')
        os.replace(name, CACHE)
    finally:
        Path(name).unlink(missing_ok=True)
    return data, errors
