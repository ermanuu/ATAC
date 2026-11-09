from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from server import app, infomobility as info, transit as t


NOW = 1794010000


def snapshot(data, **extra):
    return {'data': data, 'available': True, 'stale': False, 'refreshing': False,
            'timestamp': NOW, 'checkedAt': NOW, 'error': '', **extra}


def feed(items, build=NOW):
    date = f'<lastBuildDate>{format_datetime(datetime.fromtimestamp(build, timezone.utc))}</lastBuildDate>' if build else ''
    return ('<rss version="2.0"><channel>' + date + ''.join(
        f'<item><guid>{i}</guid><title>{title}</title><description><![CDATA[{text}]]></description><link>https://www.atac.roma.it/stato-del-servizio</link></item>'
        for i, (title, text) in enumerate(items)) + '</channel></rss>').encode()


def article(line='303', article_id=1, title=None):
    return {'id': article_id, 'title': {'rendered': title or f'Linea {line}, percorso modificato'},
            'content': {'rendered': f'<p>Deviata la linea {line}.<br>Leggi le informazioni.</p>'},
            'excerpt': {'rendered': ''}, 'date_gmt': '2026-11-06T20:56:40', 'modified_gmt': '2026-11-06T20:56:52',
            'link': 'https://romamobilita.it/infomobilita/avviso/'}


def metro_line(code='A', status=1, **extra):
    # Core fields were confirmed by the user's browser response on the VM.
    # Route details follow the widget's supplied HTML, not a full live capture.
    return {'Code': f'METRO{code}', 'Name': f'METRO {code}', 'Type': 1,
            'IsOn': True, 'Status': status, 'Routes': [], **extra}


class ParserTests(unittest.TestCase):
    def test_html_is_text_with_paragraphs_and_entities_without_active_content(self):
        self.assertEqual(info.plain_text('<p>Novità &amp; orari</p><script>doBad()</script><style>bad</style><p>Linea <b>303</b><br>Deviazione</p>'), 'Novità & orari\nLinea 303\nDeviazione')

    def test_explicit_line_lists_preserve_zeros_suffixes_and_night_codes(self):
        text = 'Linee bus 05, 05P e 05B. La linea nMB è deviata. Linee del trasporto pubblico C3, H, 75 e 075. Dalle 12 alle 18, 77960 e 80378 sono fermate.'
        self.assertEqual(set(info.line_mentions(text)), {'05', '05P', '05B', 'NMB', 'C3', 'H', '75', '075'})

    def test_dates_stop_codes_and_unrelated_numbers_are_not_line_references(self):
        self.assertEqual(info.line_mentions('Dal 17 novembre, alle 18:30, chiusura al civico 303. Fermata 74354. Il numero 75.'), [])
        self.assertEqual(info.line_mentions('Linea 12345 non presente. Linea FL1 e metro B1.'), [])

    def test_service_feed_titles_can_be_a_bare_line_code_or_prefix(self):
        self.assertEqual(info.line_mentions('nMB\nServizio deviato'), ['NMB'])
        self.assertEqual(info.line_mentions('075: percorso modificato'), ['075'])
        self.assertEqual(info.line_mentions('75 - percorso modificato'), ['75'])
        self.assertEqual(info.line_mentions('Bus 75 e 117 in deviazione'), ['117', '75'])

    def test_malformed_or_official_looking_external_links_are_not_forwarded(self):
        for url in ['javascript:alert(1)', 'http://romamobilita.it/', 'https://romamobilita.it.evil.test/', 'https://romamobilita.it@evil.test/', 'https://user@romamobilita.it/']:
            self.assertEqual(info.official_url(url), info.RSM)
        self.assertEqual(info.official_url('https://romamobilita.it/infomobilita/avviso/'), 'https://romamobilita.it/infomobilita/avviso/')

    def test_articles_keep_source_dates_category_and_exact_line_association(self):
        result = info.parse_articles([article('075')], 'Infomobilità')[0]
        self.assertEqual(result['lines'], ['075'])
        self.assertEqual(result['source'], 'Roma Mobilità')
        self.assertEqual(result['category'], 'Deviazione')
        self.assertFalse(result['live'])
        self.assertGreater(result['updatedAt'], result['publishedAt'])
        self.assertNotIn('<p>', result['text'])

    def test_bad_article_shapes_or_missing_publication_do_not_become_fake_news(self):
        self.assertEqual(info.parse_articles([None, {}, article() | {'date_gmt': ''}], 'News'), [])
        with self.assertRaises(ValueError): info.parse_articles({'error': 'unavailable'}, 'News')

    def test_rss_without_items_is_valid_but_html_and_entity_definitions_are_not(self):
        self.assertEqual(info.rss_entries(feed([]))['entries'], [])
        for body in [b'<html>Blocked</html>', b'<!DOCTYPE rss [<!ENTITY e "x">]><rss><channel/></rss>']:
            with self.assertRaises(ValueError): info.rss_entries(body)

    def test_utc_and_rss_dates_are_timezone_independent(self):
        self.assertEqual(info.timestamp('2026-11-06T20:00:00'), info.timestamp('Fri, 06 Nov 2026 21:00:00 +0100'))
        self.assertIsNone(info.timestamp('not a date'))


class MetroTests(unittest.TestCase):
    def metro(self, rows, **changes):
        source = Mock(read=Mock(return_value=snapshot(info.parse_metro_lines(rows), **changes)))
        rss = Mock()
        with patch.dict(info._sources, {'atac-metro': source, 'atac': rss}):
            result = info.metro(refresh=True)
        source.read.assert_called_once_with(True)
        rss.read.assert_not_called()
        return result

    def test_each_line_uses_its_own_home_status_in_fixed_order(self):
        result = self.metro([metro_line('C', 6), metro_line('B1', 4), metro_line('A'), metro_line('B', 2)])
        self.assertEqual([row['code'] for row in result['lines']], ['A', 'B', 'B1', 'C'])
        self.assertEqual([row['status'] for row in result['lines']], ['regular', 'delays', 'suspended', 'modified'])
        self.assertEqual([row['label'] for row in result['lines']], ['Regolare', 'Rallentata', 'Non attiva', 'Parzialmente non attiva'])
        self.assertTrue(result['available']); self.assertFalse(result['partial'])
        self.assertEqual(result['sourceUrl'], 'https://www.atac.roma.it/')
        self.assertTrue(all(row['url'] == result['sourceUrl'] and row['publishedAt'] is None for row in result['lines']))
        self.assertIsNone(result['sourceTimestamp'])

    def test_home_status_ids_preserve_partial_interruptions_and_planned_work(self):
        for value, status, label in [(1, 'regular', 'Regolare'), (2, 'delays', 'Rallentata'),
                                     (3, 'modified', 'Servizio modificato'), (4, 'suspended', 'Non attiva'),
                                     (5, 'suspended', 'Chiusa'), (6, 'modified', 'Parzialmente non attiva'),
                                     (7, 'modified', 'Riprogrammata'), (8, 'modified', 'Lavori programmati')]:
            with self.subTest(value=value):
                row = self.metro([metro_line(status=value)])['lines'][0]
                self.assertEqual((row['status'], row['label']), (status, label))

    def test_bus_tram_and_other_rail_records_cannot_set_a_metro_status(self):
        result = self.metro([None, {}, metro_line('B'), metro_line('A', Type=2),
                             metro_line('C', Type=3), metro_line(Code='CENTOCELLE'), metro_line(Code='nMA')])
        self.assertEqual([row['status'] for row in result['lines']], ['unknown', 'regular', 'unknown', 'unknown'])
        self.assertTrue(result['partial'])

    def test_missing_inactive_and_unknown_lines_are_never_assumed_regular(self):
        for changes in [{'IsOn': False}, {'IsOn': None}, {'IsOn': 'true'}, {'Status': 99},
                        {'Status': None}, {'Status': True}, {'Status': 1.0}]:
            with self.subTest(changes=changes):
                result = self.metro([metro_line(**changes)])
                self.assertTrue(all(row['status'] == 'unknown' for row in result['lines']))
                self.assertTrue(result['partial'])

    def test_conflicting_duplicate_lines_do_not_verify_regular_service(self):
        for rows in [[metro_line(), metro_line(status=4)], [metro_line(status=4), metro_line(), metro_line()]]:
            self.assertEqual(self.metro(rows)['lines'][0]['status'], 'unknown')

    def test_only_active_route_details_are_shown_as_plain_text(self):
        routes = [{'Name': '<b>Anagnina &amp; Battistini</b>', 'StatusName': 'Regolare',
                   'Description': '-', 'Schedule': {'IsOn': True}},
                  {'Name': 'Direzione opposta', 'StatusName': 'Servizio modificato',
                   'Description': '<p>Stazione chiusa</p><script>bad()</script>', 'Schedule': {'IsOn': True}},
                  {'Name': 'Percorso non attivo', 'StatusName': 'Non attiva', 'Schedule': {'IsOn': False}},
                  None, {'Schedule': None}]
        row = self.metro([metro_line(Routes=routes)])['lines'][0]
        self.assertEqual(row['detail'], 'Anagnina & Battistini: Regolare\n\nDirezione opposta: Servizio modificato\nStazione chiusa')

    def test_bad_top_level_and_empty_or_unrelated_data_are_source_errors(self):
        for rows in [None, {}, {'ErrorId': 'upstream-error'}, [], [None, {}], [metro_line(Code='CENTOCELLE')]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError): info.parse_metro_lines(rows)

    def test_public_home_request_is_a_bounded_json_post_in_italian(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps([metro_line()]).encode()
        with patch.object(info, 'urlopen', return_value=response) as fetch:
            result = info.fetch_metro()
        request = fetch.call_args.args[0]
        self.assertEqual(request.full_url, 'https://www.atac.roma.it/Service/WebService.asmx/GetPrimaryLinesData')
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.get_header('Content-type'), 'application/json')
        self.assertEqual(json.loads(request.data), {'languageName': 'it'})
        self.assertEqual(fetch.call_args.kwargs['timeout'], 8)
        response.read.assert_called_once_with(4 * 1024 * 1024 + 1)
        self.assertEqual(result[0]['status'], 'regular')

    def test_failed_verification_removes_current_status_without_mutating_cache(self):
        result = self.metro([metro_line()], available=False, stale=True)
        self.assertFalse(result['available']); self.assertTrue(result['stale'])
        self.assertTrue(all(row['status'] == 'unknown' for row in result['lines']))

    def test_captcha_or_server_errors_do_not_turn_a_failed_source_into_live_status(self):
        for body in [b'<html><title>Radware Captcha Page</title></html>', b'{"ErrorId":"failed"}', b'[]']:
            with self.subTest(body=body), patch.object(info, 'download', return_value=body):
                source = info.OfficialSource(info.fetch_metro)
                with patch.dict(info._sources, {'atac-metro': source}): result = info.metro()
                self.assertFalse(result['available']); self.assertTrue(result['error'])
                self.assertIsNone(result['timestamp'])
                self.assertTrue(all(row['status'] == 'unknown' for row in result['lines']))

    def test_failed_refresh_retains_details_and_original_time_but_not_green_status(self):
        route = {'Name': 'Direzione Battistini', 'StatusName': 'Regolare', 'Schedule': {'IsOn': True}}
        with patch.object(info, 'download', return_value=json.dumps([metro_line(Routes=[route])]).encode()) as fetch:
            source = info.OfficialSource(info.fetch_metro)
            with patch.dict(info._sources, {'atac-metro': source}):
                first = info.metro()
                source.attempt -= 3
                fetch.return_value = b'<html>CAPTCHA</html>'
                failed = info.metro(refresh=True)
            self.assertEqual(failed['timestamp'], first['timestamp'])
            self.assertEqual(failed['lines'][0]['detail'], first['lines'][0]['detail'])
            self.assertFalse(failed['available']); self.assertTrue(failed['stale'])
            self.assertEqual(failed['lines'][0]['status'], 'unknown')
            self.assertEqual(source.value[0]['status'], 'regular')


class BulletinStatusTests(unittest.TestCase):

    def test_station_closure_does_not_claim_the_whole_line_is_suspended(self):
        for text in ['Servizio regolare. Stazione Spagna chiusa per lavori', 'Chiusa la stazione Spagna. Servizio regolare sulla linea']:
            self.assertEqual(info.metro_status(text)[0], 'modified')

    def test_explicitly_irregular_service_is_never_green(self):
        for text in ['Servizio non regolare', 'Circolazione irregolare', 'Servizio perturbato']:
            self.assertEqual(info.metro_status(text)[0], 'modified')

    def test_a_verified_service_bulletin_persists_until_the_publisher_changes_it(self):
        with patch.object(info.time, 'time', return_value=NOW):
            self.assertTrue(info.service_feed_fresh(snapshot(info.rss_entries(feed([], build=NOW - 86400)))))
            self.assertFalse(info.service_feed_fresh(snapshot(info.rss_entries(feed([], build=NOW + 61)))))


class SourceTests(unittest.TestCase):
    def test_downloads_are_shared_and_cached(self):
        loader = Mock(return_value=[])
        source = info.OfficialSource(loader)
        source.read(); source.read(); source.read(refresh=True)
        loader.assert_called_once()

    def test_failures_are_explicit_and_retried_after_backoff(self):
        loader = Mock(side_effect=OSError('source offline'))
        source = info.OfficialSource(loader)
        result = source.read()
        self.assertFalse(result['available']); self.assertIsNone(result['timestamp'])
        self.assertTrue(result['error']); source.read(); loader.assert_called_once()
        source.deadline = 0
        loader.side_effect = None; loader.return_value = []
        self.assertTrue(source.read()['available'])

    def test_a_failed_refresh_keeps_dated_cache_and_marks_it_stale(self):
        loader = Mock(return_value=['old'])
        source = info.OfficialSource(loader)
        first = source.read()
        source.attempt -= 3
        loader.side_effect = OSError('down')
        failed = source.read(refresh=True)
        self.assertEqual(failed['data'], ['old']); self.assertEqual(failed['timestamp'], first['timestamp'])
        self.assertFalse(failed['available']); self.assertTrue(failed['stale'])

    def test_inflight_download_does_not_block_other_readers_or_start_duplicates(self):
        entered, release = threading.Event(), threading.Event()
        def load():
            entered.set(); self.assertTrue(release.wait(3)); return ['data']
        source = info.OfficialSource(Mock(side_effect=load))
        worker = threading.Thread(target=source.read); worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertTrue(source.read()['refreshing'])
            self.assertFalse(source.read()['available'])
            source.loader.assert_called_once()
        finally: release.set(); worker.join(3)
        self.assertTrue(source.read()['available'])

    def test_expired_cached_data_is_served_while_a_single_refresh_runs(self):
        source = info.OfficialSource(Mock(return_value=['old']))
        source.read(); source.deadline = 0
        entered, release = threading.Event(), threading.Event()
        def load(): entered.set(); release.wait(3); return ['new']
        source.loader.side_effect = load
        try:
            result = source.read()
            self.assertEqual(result['data'], ['old'])
            self.assertTrue(entered.wait(2)); self.assertEqual(source.read()['data'], ['old'])
        finally: release.set()
        for _ in range(100):
            if not source.pending: break
            time.sleep(.01)
        self.assertEqual(source.read()['data'], ['new'])


class NewsAndLineTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'transit.sqlite'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE routes(route_id TEXT,name TEXT)')
            db.executemany('INSERT INTO routes VALUES(?,?)', [('id-75', '75'), ('id-075', '075'), ('night', 'nMB')])
        context = patch.object(t, 'DB', path); context.start(); self.addCleanup(context.stop)

    def sources(self, one=None, two=None, rss=None):
        return patch.dict(info._sources, {'rsm-info': Mock(read=Mock(return_value=one or snapshot(info.parse_articles([article('75')], 'Infomobilità')))),
                                         'rsm-news': Mock(read=Mock(return_value=two or snapshot(info.parse_articles([article('075', 2)], 'News')))),
                                         'atac': Mock(read=Mock(return_value=rss or snapshot(info.rss_entries(feed([])))) )})

    def test_rsm_news_are_merged_and_deduplicated_by_official_article_id(self):
        rows = info.parse_articles([article()], 'News')
        with self.sources(one=snapshot(rows), two=snapshot(rows)):
            result = info.news(); self.assertTrue(result['available']); self.assertEqual(len(result['articles']), 1)

    def test_one_unavailable_news_source_keeps_the_other_with_partial_status(self):
        with self.sources(one=snapshot(None, available=False, error='offline')):
            result = info.news(); self.assertFalse(result['available']); self.assertTrue(result['partial']); self.assertEqual(len(result['articles']), 1)

    def test_line_alerts_match_public_names_exactly_not_route_ids_or_substrings(self):
        with self.sources(), patch.object(info.time, 'time', return_value=NOW):
            for route, line in [('id-75', '75'), ('id-075', '075')]:
                result = info.line_alerts(route)
                self.assertEqual(result['line'], line); self.assertEqual(len(result['items']), 1)
                self.assertEqual(result['items'][0]['lines'], [line])

    def test_bus_and_night_alerts_include_only_current_official_bulletins(self):
        rss = snapshot(info.rss_entries(feed([('nMB', 'Percorso deviato'), ('75', 'Servizio regolare')])))
        with self.sources(rss=rss), patch.object(info.time, 'time', return_value=NOW):
            night = info.line_alerts('night')['items']; self.assertEqual(len(night), 1); self.assertTrue(night[0]['live'])
            self.assertFalse(any(row['live'] for row in info.line_alerts('id-75')['items']))

    def test_unverifiable_cached_bulletins_do_not_reappear_as_current_diversions(self):
        rss = snapshot(info.rss_entries(feed([('nMB', 'Percorso deviato')], build=NOW - 1000)), available=False, stale=True)
        with self.sources(rss=rss), patch.object(info.time, 'time', return_value=NOW):
            result = info.line_alerts('night'); self.assertEqual(result['items'], []); self.assertFalse(result['available']); self.assertTrue(result['partial'])

    def test_missing_line_is_an_actionable_error(self):
        with self.assertRaisesRegex(ValueError, 'Linea non trovata'): info.line_alerts('no-such-line')

    def test_http_endpoints_support_manual_refresh_and_do_not_require_a_gtfs_database_for_news_or_metro(self):
        with patch.object(info, 'metro', return_value={'lines': []}) as metro, patch.object(info, 'news', return_value={'articles': []}) as news, patch.object(info, 'line_alerts', return_value={'items': []}) as alerts:
            self.assertEqual(app.api_response('/api/metro?fresh=1').code, 200); metro.assert_called_once_with(refresh=True)
            self.assertEqual(app.api_response('/api/news?fresh=1').code, 200); news.assert_called_once_with(refresh=True)
            self.assertEqual(app.api_response('/api/routes/id-75/alerts?fresh=1').code, 200); alerts.assert_called_once_with('id-75', refresh=True)
