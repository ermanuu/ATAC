"""Optional real-browser checks for the standalone VM diagnostic."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
import io
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


script = Path(__file__).resolve().parents[1] / 'scripts/check-atac-browser.py'
spec = importlib.util.spec_from_file_location('atac_browser_check', script)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
HAS_BROWSER = importlib.util.find_spec('playwright') is not None and shutil.which('chromium')


@unittest.skipUnless(HAS_BROWSER, 'Optional: Playwright and local Chromium are required')
class BrowserProbeTests(unittest.TestCase):
    def setUp(self):
        self.payload = [{'Code': code, 'Type': 1, 'IsOn': True, 'Status': 1} for code in probe.CODES]
        self.code, self.content_type = 200, 'application/json; charset=utf-8'
        self.requests, self.load_widget = [], True
        self.session_cookies = []
        self.redirect = None
        self.interval = False
        self.reject_reopen = False
        self.delay_first = 0
        self.status_after_first = None
        self.first_request = threading.Event()
        case = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/': case.session_cookies.append(self.headers.get('Cookie', ''))
                if self.path == '/' and case.reject_reopen and len(case.session_cookies) > 1:
                    self.send_response(302)
                    self.send_header('Location', f'http://localhost:{case.server.server_port}/challenge')
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.send_header('Set-Cookie', 'probe-session=local-fixture; Path=/; HttpOnly')
                self.end_headers()
                html = '<title>Local test fixture</title>'
                if self.path == '/' and case.redirect:
                    html += f'<script>setTimeout(() => location.href = {json.dumps(case.redirect)}, 100);</script>'
                if self.path == '/' and case.load_widget:
                    html += '''<script>function refresh() {fetch('/Service/WebService.asmx/GetPrimaryLinesData', {
                      method: 'POST', headers: {'Content-Type': 'application/json'},
                      body: JSON.stringify({languageName: 'it'})
                    });} refresh();''' + ('setInterval(refresh, 350);' if case.interval else '') + '</script>'
                self.wfile.write(html.encode())

            def do_POST(self):
                case.requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                request_index = len(case.requests)
                payload = json.loads(json.dumps(case.payload))
                if request_index > 1 and case.status_after_first is not None:
                    payload[1]['Status'] = case.status_after_first
                case.first_request.set()
                if request_index == 1 and case.delay_first:
                    time.sleep(case.delay_first)
                self.send_response(case.code)
                self.send_header('Content-Type', case.content_type)
                if case.code == 302: self.send_header('Location', '/challenge')
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

            def log_message(self, *args): pass

        self.folder = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join()
        self.folder.cleanup()

    def read(self, **options):
        from playwright.sync_api import sync_playwright
        home = f'http://127.0.0.1:{self.server.server_port}/'
        with sync_playwright() as playwright:
            return probe.read_widget(playwright.chromium, Path(self.folder.name) / 'profile',
                                     executable=shutil.which('chromium'), home=home,
                                     endpoint=home + 'Service/WebService.asmx/GetPrimaryLinesData',
                                     timeout=1200, manual_timeout=1200, **options)

    def test_observes_actual_widget_post_without_replaying_it_or_exporting_state(self):
        self.payload += [{'Code': '75', 'Type': 2, 'IsOn': True, 'Status': 1}]
        result = self.read()
        self.assertEqual(result['http'], 200)
        self.assertEqual([row['Code'] for row in result['lines']], list(probe.CODES))
        self.assertEqual(self.requests, [{'languageName': 'it'}])
        self.assertEqual(set(result), {'http', 'type', 'lines'})

    def test_redirects_are_not_reported_as_success(self):
        self.code, self.content_type = 302, 'text/html'
        with self.assertRaisesRegex(ValueError, 'HTTP 302'): self.read()

    def test_json_content_type_does_not_make_an_error_object_valid(self):
        self.payload = {'ErrorId': 'unavailable'}
        with self.assertRaisesRegex(ValueError, 'Formato JSON inatteso'): self.read()

    def test_a_page_without_widget_does_not_report_live_data(self):
        self.load_widget = False
        with self.assertRaisesRegex(ValueError, 'Nessuna risposta del widget'): self.read()

    def test_manual_gate_waits_for_native_refresh_without_new_tabs_or_reloading(self):
        self.interval, self.reject_reopen = True, True
        self.status_after_first = 2
        def confirm(prompt):
            self.assertIn('Invio', prompt)
            self.assertTrue(self.first_request.wait(1))
            return ''
        with patch('builtins.input', side_effect=confirm) as entered:
            result = self.read(manual=True)
        entered.assert_called_once()
        self.assertEqual(result['http'], 200)
        self.assertGreaterEqual(len(self.requests), 2)
        self.assertTrue(all(body == {'languageName': 'it'} for body in self.requests))
        self.assertEqual(result['lines'][1]['Status'], 2)
        self.assertEqual(self.session_cookies, [''])
        self.assertEqual(set(result), {'http', 'type', 'lines'})

    def test_manual_gate_ignores_a_response_started_before_confirmation_but_delivered_later(self):
        self.interval, self.delay_first, self.status_after_first = True, .2, 2
        with patch('builtins.input', side_effect=lambda _: self.first_request.wait(1)):
            result = self.read(manual=True)
        self.assertEqual(result['lines'][1]['Status'], 2)
        self.assertEqual(self.session_cookies, [''])

    def test_manual_gate_does_not_reuse_an_old_success_when_the_widget_stops(self):
        def confirm(_):
            self.assertTrue(self.first_request.wait(1))
            time.sleep(.15)
            return ''
        with patch('builtins.input', side_effect=confirm), self.assertRaisesRegex(ValueError, 'Nessuna risposta del widget'):
            self.read(manual=True)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.session_cookies, [''])

    def test_visible_home_does_not_verify_a_widget_redirected_to_a_challenge(self):
        self.interval, self.code, self.content_type = True, 302, 'text/html'
        with patch('builtins.input', return_value=''), self.assertRaisesRegex(ValueError, 'HTTP 302'):
            self.read(manual=True)
        self.assertEqual(self.session_cookies, [''])

    def test_manual_cancellation_does_not_attempt_to_read_or_report_live_data(self):
        self.load_widget = False
        with patch('builtins.input', side_effect=EOFError), self.assertRaises(EOFError):
            self.read(manual=True)
        self.assertEqual(self.requests, [])

    def test_a_challenge_page_still_open_after_manual_wait_is_not_accepted(self):
        self.load_widget = False
        self.redirect = f'http://localhost:{self.server.server_port}/challenge'
        with patch('builtins.input', side_effect=lambda _: time.sleep(.5)):
            with self.assertRaisesRegex(ValueError, 'verifica manuale non completata'):
                self.read(manual=True)
        self.assertEqual(self.requests, [])

    def test_browser_response_reaches_the_api_through_the_public_snapshot(self):
        from server import app, metro_cache
        self.payload[1]['Status'] = 2
        captured = self.read(include_rows=True)
        path = Path(self.folder.name) / 'metro.json'
        metro_cache.write_snapshot(path, captured['rows'], fetched_at=captured['fetchedAt'])
        with patch.dict(os.environ, {'ATAC_METRO_SNAPSHOT': str(path)}):
            response = app.api_response('/api/metro?fresh=1')
        self.assertEqual(response.code, 200)
        self.assertTrue(response.result['available'])
        self.assertEqual([line['status'] for line in response.result['lines']], ['regular', 'delays', 'regular', 'regular'])
        self.assertEqual(response.result['timestamp'], captured['fetchedAt'])

    def test_collector_command_records_failure_without_renewing_last_success(self):
        from server import metro_cache
        path = Path(self.folder.name) / 'metro.json'
        original_time = time.time() - 10
        metro_cache.write_snapshot(path, self.payload, fetched_at=original_time)
        argv = [str(script), '--profile', str(Path(self.folder.name) / 'profile'), '--output', str(path)]
        with patch.object(sys, 'argv', argv), patch('playwright.sync_api.sync_playwright'), \
             patch.object(probe, 'read_widget', side_effect=ValueError('HTTP 302')), \
             patch('sys.stderr', new_callable=io.StringIO):
            self.assertEqual(probe.main(), 1)
        source = metro_cache.read_snapshot(path)
        self.assertFalse(source['available']); self.assertTrue(source['stale'])
        self.assertEqual(source['timestamp'], original_time)
