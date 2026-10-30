import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from server import web


class WebTests(unittest.TestCase):
    def test_spa_assets_api_and_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'dist'
            root.mkdir()
            (root / 'index.html').write_text('<html>app</html>')
            (root / 'manifest.webmanifest').write_text('{"display":"standalone"}')
            (Path(folder) / 'private.txt').write_text('secret')
            with patch.object(web, 'ROOT', root), patch.object(web.APIHandler, 'log_message'), patch.object(web.APIHandler, 'respond') as respond, patch('server.transit.status', return_value={'ok': True}):
                server = ThreadingHTTPServer(('127.0.0.1', 0), web.Handler)
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    def request(path, method='GET'):
                        connection = HTTPConnection(*server.server_address)
                        connection.request(method, path)
                        response = connection.getresponse()
                        result = response.status, response.getheader('Content-Type'), response.read()
                        connection.close()
                        return result
                    self.assertEqual(request('/line/706/direction')[2], b'<html>app</html>')
                    self.assertEqual(request('/manifest.webmanifest')[1], 'application/manifest+json')
                    self.assertEqual(request('/missing.js')[0], 404)
                    self.assertEqual(request('/_expo/missing')[0], 404)
                    self.assertEqual(request('/%2e%2e/private.txt')[0], 404)
                    self.assertEqual(request('/', 'HEAD')[2], b'')
                    # Dispatch is checked independently because respond is mocked.
                    handler = object.__new__(web.Handler)
                    handler.path = '/api/status'
                    handler.handle_request()
                    respond.assert_called_once_with(200, {'ok': True})
                finally:
                    server.shutdown()
                    server.server_close()
                    worker.join()
