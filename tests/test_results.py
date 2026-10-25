import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import calendar_data as calendar
import race_results as results


TODAY = dt.date(2026, 10, 17)


class ResultsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cache = Path(self.directory.name) / 'podiums.json'
        self.cache_patch = patch.object(results, 'CACHE', self.cache)
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)
        self.races = calendar.seed()['races']
        self.data = results.load_results()
        self.indonesia = next(r for r in self.races if r['code'] == 'INA')

    def test_bundled_results_and_teams_at_each_race(self):
        self.assertEqual(len(self.data['races']), 17)
        thailand = results.result_for(self.data, self.races[0], TODAY)
        indonesia = results.result_for(self.data, self.indonesia, TODAY)
        self.assertEqual(thailand['podium'][2]['team'], 'Trackhouse MotoGP Team')
        self.assertEqual(indonesia['podium'][1]['team'], 'SuperFile Trackhouse MotoGP Team')
        self.assertEqual([r['rider'] for r in indonesia['podium']],
                         ['Marco Bezzecchi', 'Raul Fernandez', 'Jorge Martin'])
        for race in self.races:
            if calendar.race_date(race) < TODAY:
                result = results.result_for(self.data, race, TODAY)
                self.assertIsNotNone(result)
                self.assertEqual([r['position'] for r in result['podium']], [1, 2, 3])
            else:
                self.assertIsNone(results.result_for(self.data, race, TODAY))

    def test_results_do_not_leak_into_future_or_rescheduled_races(self):
        self.assertIsNone(results.result_for(self.data, self.indonesia, dt.date(2026, 10, 10)))
        self.assertIsNone(results.result_for(self.data, dict(self.indonesia, date='2026-10-12'), TODAY))

    def test_corrupt_or_partial_cache_keeps_official_offline_podiums(self):
        self.cache.write_text('broken')
        self.assertEqual(results.load_results(), self.data)
        bad = copy.deepcopy(self.data)
        bad['races']['INA']['podium'].pop()
        self.cache.write_text(json.dumps(bad))
        self.assertEqual(results.load_results(), self.data)
        bad = copy.deepcopy(self.data)
        bad['year'] = 2025
        with self.assertRaises(ValueError):
            results.validate(bad)
        bad = copy.deepcopy(self.data)
        bad['races']['INA']['podium'][1]['team'] = ''
        with self.assertRaises(ValueError):
            results.validate(bad)

    def test_newer_cache_merges_without_losing_bundled_rounds(self):
        fresh = copy.deepcopy(self.data['races']['INA'])
        fresh['verified'] = '2026-10-18'
        self.cache.write_text(json.dumps({'year': 2026, 'races': {'INA': fresh}}))
        loaded = results.load_results()
        self.assertEqual(len(loaded['races']), 17)
        self.assertEqual(loaded['races']['INA']['verified'], '2026-10-18')

    def classification(self):
        return {'classification': [
            {'position': p['position'], 'rider': {'full_name': p['rider']},
             'team': {'name': p['team']}}
            for p in reversed(self.data['races']['INA']['podium'])]}

    def event(self):
        return {'id': 'event', 'test': False, 'short_name': 'INA',
                'date_end': '2026-10-11', 'season': {'year': 2026}}

    def test_official_parser_sorts_positions_and_rejects_incomplete_classification(self):
        raw = self.classification()
        self.assertEqual(results.parse_classification(raw), self.data['races']['INA']['podium'])
        raw['classification'].pop()
        with self.assertRaises(ValueError):
            results.parse_classification(raw)

    def test_fetch_accepts_only_finished_grand_prix_and_matching_event(self):
        categories = [{'id': 'motogp', 'name': 'MotoGP™'}]
        sessions = [{'id': 'sprint', 'type': 'SPR', 'status': 'FINISHED'},
                    {'id': 'race', 'type': 'RAC', 'status': 'FINISHED'}]
        with patch.object(results, '_request', side_effect=[categories, sessions, self.classification()]) as request:
            result = results.fetch_result(self.event(), self.indonesia, TODAY)
        self.assertEqual(result['session_id'], 'race')
        self.assertEqual(result['podium'], self.data['races']['INA']['podium'])
        self.assertEqual(request.call_args.args[0], 'session/race/classification')
        sessions[1]['status'] = 'NOT_STARTED'
        with patch.object(results, '_request', side_effect=[categories, sessions]):
            self.assertIsNone(results.fetch_result(self.event(), self.indonesia, TODAY))
        with patch.object(results, '_request') as request:
            for event in (dict(self.event(), test=True), dict(self.event(), short_name='JPN'),
                          dict(self.event(), season={'year': 2025})):
                with self.assertRaises(ValueError):
                    results.fetch_result(event, self.indonesia, TODAY)
            request.assert_not_called()

    def test_failed_refresh_keeps_saved_podiums(self):
        self.cache.write_text(json.dumps(self.data))
        with patch.object(results, '_request', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                results.refresh_results(self.races, TODAY)
        self.assertEqual(json.loads(self.cache.read_text()), self.data)
        with patch.object(results, '_request', side_effect=[
                [{'id': 'season', 'year': 2026}], [self.event()]]), \
                patch.object(results, 'fetch_result', side_effect=OSError('classification unavailable')):
            data, errors = results.refresh_results(self.races, TODAY)
        self.assertEqual(data, self.data)
        self.assertEqual(len(errors), 1)
        self.assertEqual(json.loads(self.cache.read_text()), self.data)

    def cancelled_result(self):
        return dict(self.data['races']['INA'], status='CANCELLED', podium=[])

    def test_cancelled_grand_prix_is_saved_even_when_sprint_finished(self):
        categories = [{'id': 'motogp', 'name': 'MotoGP™'}]
        sessions = [{'id': 'sprint', 'type': 'SPR', 'status': 'FINISHED'},
                    {'id': 'race', 'type': 'RAC', 'status': 'CANCELLED'}]
        with patch.object(results, '_request', side_effect=[categories, sessions]) as request:
            result = results.fetch_result(self.event(), self.indonesia, TODAY)
        self.assertEqual(result['status'], 'CANCELLED')
        self.assertEqual(result['podium'], [])
        self.assertEqual(result['session_id'], 'race')
        self.assertEqual(request.call_count, 2)  # Cancelled races have no classification.

    def test_cancelled_sprint_does_not_cancel_grand_prix(self):
        for sessions in (
                [{'id': 'sprint', 'type': 'SPR', 'status': 'CANCELLED'}],
                [{'id': 'sprint', 'type': 'SPR', 'status': 'CANCELLED'},
                 {'id': 'race', 'type': 'RAC', 'status': 'NOT_STARTED'}]):
            with self.subTest(sessions=sessions), patch.object(results, '_request', side_effect=[
                    [{'id': 'motogp', 'name': 'MotoGP™'}], sessions]):
                self.assertIsNone(results.fetch_result(self.event(), self.indonesia, TODAY))

    def test_restarted_race_takes_precedence_over_cancelled_session(self):
        for status in ('NOT_STARTED', 'FINISHED'):
            sessions = [{'id': 'cancelled', 'type': 'RAC', 'status': 'CANCELLED'},
                        {'id': 'restart', 'type': 'RAC', 'status': status}]
            responses = [[{'id': 'motogp', 'name': 'MotoGP™'}], sessions]
            if status == 'FINISHED':
                responses.append(self.classification())
            with self.subTest(status=status), patch.object(results, '_request', side_effect=responses):
                result = results.fetch_result(self.event(), self.indonesia, TODAY)
            if status == 'FINISHED':
                self.assertEqual(result['status'], 'FINISHED')
                self.assertEqual(result['session_id'], 'restart')
                self.assertEqual(result['podium'], self.data['races']['INA']['podium'])
            else:
                self.assertIsNone(result)

    def test_cancellation_cache_survives_offline_and_respects_race_date(self):
        cancelled = self.cancelled_result()
        with patch.object(results, '_request', side_effect=[
                [{'id': 'season', 'year': 2026}], [self.event()]]), \
                patch.object(results, 'fetch_result', return_value=cancelled):
            data, errors = results.refresh_results(self.races, TODAY)
        self.assertEqual(errors, [])
        loaded = results.load_results()
        self.assertEqual(loaded, data)
        self.assertEqual(len(loaded['races']), 17)
        self.assertEqual(results.result_for(loaded, self.indonesia, TODAY), cancelled)
        self.assertIsNone(results.result_for(loaded, self.indonesia, dt.date(2026, 10, 10)))
        self.assertIsNone(results.result_for(loaded, dict(self.indonesia, date='2026-10-12'), TODAY))
        with patch.object(results, '_request', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                results.refresh_results(self.races, TODAY)
        self.assertEqual(results.load_results(), loaded)

    def test_invalid_cancellation_and_unknown_status_are_rejected(self):
        for result in (dict(self.cancelled_result(), podium=self.data['races']['INA']['podium']),
                       dict(self.cancelled_result(), podium=None),
                       dict(self.cancelled_result(), status='NOT_STARTED')):
            with self.subTest(result=result), self.assertRaises(ValueError):
                results.validate({'year': 2026, 'races': {'INA': result}})


if __name__ == '__main__':
    unittest.main()
