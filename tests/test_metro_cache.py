import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from server import infomobility as info, metro_cache as cache


NOW = 1794044000


def rows():
    return [{'Code': f'METRO{code}', 'Type': 1, 'IsOn': True, 'Status': 1,
             'Routes': [{'Name': f'Direzione {code}', 'StatusName': 'Regolare',
                         'Schedule': {'IsOn': True}}]} for code in ('A', 'B', 'B1', 'C')]


class MetroCacheTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'metro.json'

    def metro(self, now=NOW):
        direct = Mock()
        with patch.dict(os.environ, {'ATAC_METRO_SNAPSHOT': str(self.path)}), \
             patch.object(cache.time, 'time', return_value=now), \
             patch.dict(info._sources, {'atac-metro': direct}):
            result = info.metro(refresh=True)
        direct.read.assert_not_called()
        return result

    def test_backend_reads_browser_snapshot_with_original_source_time(self):
        cache.write_snapshot(self.path, rows(), fetched_at=NOW - 15, now=NOW)
        result = self.metro()
        self.assertTrue(result['available']); self.assertFalse(result['partial'])
        self.assertEqual(result['timestamp'], NOW - 15)
        self.assertEqual(result['checkedAt'], NOW)
        self.assertEqual([line['status'] for line in result['lines']], ['regular'] * 4)
        self.assertEqual(result['lines'][0]['detail'], 'Direzione A: Regolare')
        self.assertEqual(result['sourceUrl'], 'https://www.atac.roma.it/')

    def test_api_reads_and_file_mtime_cannot_renew_an_expired_download(self):
        cache.write_snapshot(self.path, rows(), now=NOW)
        os.utime(self.path, (NOW + 999, NOW + 999))
        boundary = self.metro(NOW + cache.MAX_AGE)
        expired = self.metro(NOW + cache.MAX_AGE + 1)
        self.assertTrue(boundary['available'])
        self.assertFalse(expired['available']); self.assertTrue(expired['stale'])
        self.assertEqual(expired['timestamp'], NOW)
        self.assertTrue(all(line['status'] == 'unknown' for line in expired['lines']))
        self.assertIn('Direzione A', expired['lines'][0]['detail'])
        self.assertEqual(self.metro(NOW + 1000)['timestamp'], NOW)

    def test_failed_poll_immediately_neutralizes_recently_regular_service(self):
        cache.write_snapshot(self.path, rows(), now=NOW)
        cache.write_snapshot(self.path, now=NOW + 30)
        result = self.metro(NOW + 30)
        self.assertFalse(result['available']); self.assertTrue(result['stale'])
        self.assertEqual(result['timestamp'], NOW)
        self.assertEqual(result['checkedAt'], NOW + 30)
        self.assertTrue(all(line['status'] == 'unknown' for line in result['lines']))
        self.assertIn('Direzione A', result['lines'][0]['detail'])

    def test_new_success_recovers_after_captcha_failure(self):
        cache.write_snapshot(self.path, rows(), now=NOW)
        cache.write_snapshot(self.path, now=NOW + 10)
        updated = rows(); updated[0]['Status'] = 6
        cache.write_snapshot(self.path, updated, now=NOW + 20)
        result = self.metro(NOW + 20)
        self.assertTrue(result['available']); self.assertFalse(result['stale'])
        self.assertEqual(result['timestamp'], NOW + 20)
        self.assertEqual(result['lines'][0]['label'], 'Parzialmente non attiva')

    def test_initial_failure_or_missing_file_never_verifies_a_line(self):
        for write_failure in (False, True):
            if write_failure: cache.write_snapshot(self.path, now=NOW)
            result = self.metro()
            self.assertFalse(result['available']); self.assertFalse(result['stale'])
            self.assertIsNone(result['timestamp'])
            self.assertTrue(all(line['status'] == 'unknown' for line in result['lines']))

    def test_wrong_source_format_or_broken_json_is_not_trusted(self):
        for payload in [b'<html>CAPTCHA</html>', b'[]', b'{}', b'{"version":1,"sourceUrl":"https://other.example/"}']:
            with self.subTest(payload=payload):
                self.path.write_bytes(payload)
                self.assertFalse(self.metro()['available'])

    def test_missing_or_invalid_dates_cannot_make_a_snapshot_current(self):
        for field in ('fetchedAt', 'checkedAt'):
            for value in (None, True, '1794044000', float('nan'), float('inf'), NOW + 6, 0):
                with self.subTest(field=field, value=value):
                    document = cache.write_snapshot(self.path, rows(), now=NOW)
                    document[field] = value
                    self.path.write_text(json.dumps(document))
                    self.assertFalse(self.metro()['available'])

    def test_unrecognized_records_do_not_become_regular_from_cache_metadata(self):
        cache.write_snapshot(self.path, [{'Code': 'CENTOCELLE', 'Type': 1, 'IsOn': True, 'Status': 1}], now=NOW)
        result = self.metro()
        self.assertFalse(result['available']); self.assertIsNone(result['timestamp'])
        self.assertTrue(all(line['status'] == 'unknown' for line in result['lines']))

    def test_unknown_or_missing_lines_remain_partial_after_browser_collection(self):
        cache.write_snapshot(self.path, rows()[:1], now=NOW)
        result = self.metro()
        self.assertTrue(result['available']); self.assertTrue(result['partial'])
        self.assertEqual([line['status'] for line in result['lines']], ['regular', 'unknown', 'unknown', 'unknown'])

    def test_atomic_replace_failure_keeps_the_last_complete_snapshot(self):
        cache.write_snapshot(self.path, rows(), now=NOW)
        previous = self.path.read_bytes()
        with patch.object(cache.os, 'replace', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError): cache.write_snapshot(self.path, now=NOW + 10)
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_oversized_snapshot_is_rejected(self):
        self.path.write_bytes(b' ' * (cache.MAX_SIZE + 1))
        self.assertFalse(self.metro()['available'])
