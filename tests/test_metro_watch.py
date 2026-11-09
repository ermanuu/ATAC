from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from server import metro_cache

script = Path(__file__).resolve().parents[1] / 'scripts/watch-atac-metro.py'
spec = importlib.util.spec_from_file_location('metro_watch', script)
watcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher)
HAS_BROWSER = importlib.util.find_spec('playwright') is not None and shutil.which('chromium')


@unittest.skipUnless(HAS_BROWSER, 'Optional: Playwright and local Chromium are required')
class MetroWatchTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.profile = Path(self.folder.name) / 'profile'
        self.output = Path(self.folder.name) / 'metro.json'
        self.responses = [200, 200]
        self.home_redirect = False
        self.html_reply = False
        self.interval = True
        self.requests, self.cookies, self.launches, self.homes = [], [], 0, 0
        case = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/': case.homes += 1
                self.send_response(302 if case.home_redirect and self.path == '/' else 200)
                self.send_header('Content-Type', 'text/html')
                if case.home_redirect:
                    self.send_header('Location', f'http://localhost:{case.server.server_port}/fixture')
                self.end_headers()
                html = '''<script>
                    function refresh() {fetch('/Service/WebService.asmx/GetPrimaryLinesData', {
                      method: 'POST', headers: {'Content-Type': 'application/json'},
                      body: JSON.stringify({languageName: 'it'})
                    });}
                    refresh();
                ''' + ('setInterval(refresh, 350);' if case.interval else '') + '</script>'
                if not case.home_redirect: self.wfile.write(html.encode())

            def do_POST(self):
                case.requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                case.cookies.append(self.headers.get('Cookie', ''))
                status = case.responses[min(len(case.requests) - 1, len(case.responses) - 1)]
                self.send_response(status)
                self.send_header('Content-Type', 'text/html' if case.html_reply else 'application/json')
                self.send_header('Set-Cookie', 'session=fixture; Path=/; HttpOnly')
                if status == 302: self.send_header('Location', f'http://localhost:{case.server.server_port}/fixture')
                self.end_headers()
                rows = [{'Code': code, 'Type': 1, 'IsOn': True,
                         'Status': 2 if code == 'METROB' and len(case.requests) > 1 else 1}
                        for code in watcher.CODES]
                self.wfile.write(json.dumps(rows).encode())

            def log_message(self, *args): pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join()
        self.folder.cleanup()

    def watch(self, limit=2):
        from playwright.sync_api import sync_playwright
        case = self
        with sync_playwright() as playwright, patch.object(watcher, 'VERIFY_HOST', 'localhost'):
            class Browser:
                def launch_persistent_context(self, *args, **kwargs):
                    case.launches += 1
                    context = playwright.chromium.launch_persistent_context(*args, **kwargs)
                    return context
            home = f'http://127.0.0.1:{self.server.server_port}/'
            return watcher.watch_widget(Browser(), self.profile, self.output, executable=shutil.which('chromium'),
                                        home=home, endpoint=home + 'Service/WebService.asmx/GetPrimaryLinesData',
                                        startup_timeout=1200, update_timeout=1200, limit=limit)

    def test_multiple_widget_updates_share_one_browser_and_one_page(self):
        with patch.object(watcher, 'notify') as notify:
            self.assertEqual(self.watch(), 2)
        self.assertEqual(self.launches, 1); self.assertEqual(self.homes, 1)
        self.assertEqual(self.requests, [{'languageName': 'it'}] * 2)
        self.assertEqual(self.cookies, ['', 'session=fixture'])
        state = metro_cache.read_snapshot(self.output)
        self.assertTrue(state['available'])
        self.assertEqual(state['data'][1]['Status'], 2)
        self.assertEqual(sum('READY=1' in call.args[0] for call in notify.call_args_list), 1)

    def test_temporary_error_recovers_without_reopening_browser(self):
        self.responses = [200, 503, 200]
        states = []
        original = metro_cache.write_snapshot
        def record(*args, **kwargs):
            result = original(*args, **kwargs)
            states.append(metro_cache.read_snapshot(self.output))
            return result
        with patch.object(watcher, 'write_snapshot', side_effect=record), patch.object(watcher, 'notify'):
            self.assertEqual(self.watch(), 2)
        self.assertEqual(self.launches, 1); self.assertEqual(self.homes, 1)
        self.assertEqual([state['available'] for state in states], [True, False, True])
        self.assertEqual(states[0]['timestamp'], states[1]['timestamp'])
        self.assertGreater(states[2]['timestamp'], states[0]['timestamp'])

    def test_new_verification_stops_collection_and_preserves_original_date(self):
        self.responses = [200, 302]
        states = []
        original = metro_cache.write_snapshot
        def record(*args, **kwargs):
            result = original(*args, **kwargs)
            states.append(metro_cache.read_snapshot(self.output))
            return result
        with patch.object(watcher, 'write_snapshot', side_effect=record), patch.object(watcher, 'notify'):
            with self.assertRaises(watcher.ManualCheck): self.watch()
        self.assertEqual(self.launches, 1); self.assertEqual(len(self.requests), 2)
        self.assertFalse(states[-1]['available']); self.assertTrue(states[-1]['stale'])
        self.assertEqual(states[0]['timestamp'], states[-1]['timestamp'])

    def test_initial_verification_page_is_detected_without_exporting_its_url(self):
        self.home_redirect = True
        with self.assertRaisesRegex(watcher.ManualCheck, 'verifica manuale'):
            self.watch()
        self.assertFalse(metro_cache.read_snapshot(self.output)['available'])
        self.assertEqual(self.requests, [])

    def test_html_is_not_published_as_successful_json(self):
        self.html_reply = True
        with self.assertRaises(watcher.ManualCheck): self.watch()
        self.assertFalse(metro_cache.read_snapshot(self.output)['available'])

    def test_missing_refresh_neutralizes_cache_without_renewing_its_date(self):
        self.interval = False
        with patch.object(watcher, 'notify'), self.assertRaises(watcher.TemporaryResponse): self.watch()
        state = metro_cache.read_snapshot(self.output)
        self.assertFalse(state['available']); self.assertTrue(state['stale'])
        self.assertLess(state['timestamp'], state['checkedAt'])


@unittest.skipUnless(sys.platform.startswith('linux'), 'systemd notification uses Unix sockets')
class NotifyTests(unittest.TestCase):
    def test_readiness_packet_reaches_systemd_socket(self):
        with tempfile.TemporaryDirectory() as folder:
            address = str(Path(folder) / 'notify.sock')
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as receiver:
                receiver.bind(address); receiver.settimeout(2)
                with patch.dict(os.environ, {'NOTIFY_SOCKET': address}): watcher.notify('READY=1\nWATCHDOG=1')
                self.assertEqual(receiver.recv(128), b'READY=1\nWATCHDOG=1')
