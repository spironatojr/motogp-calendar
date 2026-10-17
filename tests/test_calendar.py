import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import calendar_data as model


class CalendarTests(unittest.TestCase):
    def test_next_race_and_season_boundary(self):
        races = model.seed()['races']
        self.assertEqual(model.next_race(races, dt.date(2026, 10, 17))['country'], 'Australia')
        self.assertEqual(model.next_race(races, dt.date(2026, 10, 25))['country'], 'Australia')
        self.assertEqual(model.next_race(races, dt.date(2026, 10, 26))['country'], 'Malaysia')
        self.assertIsNone(model.next_race(races, dt.date(2026, 11, 30)))
        self.assertIn('season complete', model.status(today=dt.date(2027, 1, 1))['label'])

    def test_cross_month_weekend_and_revised_dates(self):
        races = model.seed()['races']
        self.assertEqual(model.date_range(races[18]), '30 Oct – 1 Nov')
        self.assertEqual([r['date'] for r in races[-3:]], ['2026-11-08', '2026-11-22', '2026-11-29'])
        self.assertEqual(model.weekend_start(races[0]), dt.date(2026, 2, 27))

    def official_table(self):
        rows = ''.join(f'<tr><td>{r["round"]}</td><td>{model.race_date(r):%d %B}</td>'
                       f'<td><span>{r["country"]}</span></td><td>{r["circuit"]}</td></tr>'
                       for r in model.seed()['races'])
        return '<table><tr><th></th><th>Date</th><th>Grand Prix</th><th>Circuit</th></tr>' + rows + '</table>'

    def test_official_refresh_parser_and_invalid_source(self):
        parsed = model.parse_official(self.official_table())
        self.assertEqual(parsed['races'], model.seed()['races'])
        with self.assertRaises(ValueError):
            model.parse_official('<html>Access denied</html>')
        with self.assertRaises(ValueError):
            model.parse_official(self.official_table().replace('29 November', '08 November'))
        with self.assertRaises(ValueError):
            model.parse_official(self.official_table().replace('Valencia', 'Unrecognized'))

    def test_corrupt_cache_falls_back_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '2026.json'
            with patch.object(model, 'CACHE', path):
                self.assertEqual(model.load_calendar(), model.seed())
                path.write_text('broken')
                self.assertEqual(model.load_calendar(), model.seed())
                path.write_text(json.dumps({'year': 2026, 'races': []}))
                self.assertEqual(model.load_calendar(), model.seed())

    def test_ics_has_exclusive_end_stable_uids_crlf_and_octet_folding(self):
        data = model.seed()
        text = model.export_ics(data)
        self.assertEqual(text.count('BEGIN:VEVENT'), 22)
        self.assertIn('DTSTART;VALUE=DATE:20261030\r\nDTEND;VALUE=DATE:20261102', text)
        self.assertIn('UID:2026-mal@motogp-calendar.local', text)
        self.assertNotIn('\n', text.replace('\r\n', ''))
        self.assertTrue(all(len(line.encode('utf-8')) <= 75 for line in text.split('\r\n')))
        self.assertEqual(model._escape('a,b;c\\d\ne'), 'a\\,b\\;c\\\\d\\ne')

    def test_failed_refresh_keeps_saved_calendar(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '2026.json'
            original = json.dumps(model.seed())
            path.write_text(original)
            with patch.object(model, 'CACHE', path), patch('urllib.request.urlopen', side_effect=OSError('offline')):
                with self.assertRaises(OSError):
                    model.refresh_calendar()
            self.assertEqual(path.read_text(), original)


if __name__ == '__main__':
    unittest.main()
