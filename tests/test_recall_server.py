from contextlib import contextmanager
import importlib
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class RecallServerTests(unittest.TestCase):
    @contextmanager
    def server(self):
        self.assertIsNotNone(importlib.util.find_spec('ontology_poc_generator.recall_server'),
                             'local recall API is not implemented')
        api = importlib.import_module('ontology_poc_generator.recall_server')
        server = api.make_server(port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}'
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_catalog_and_match_are_live_python_results(self):
        with self.server() as base:
            with urlopen(base + '/api/recall/catalog') as response:
                catalog = json.load(response)
            self.assertEqual(len(catalog['products']), 12)
            request = Request(base + '/api/recall/match', data=json.dumps({
                'product': 'F-0369-2025/1', 'lot': 'X7547814'}).encode(),
                headers={'Content-Type': 'application/json'})
            with urlopen(request) as response:
                self.assertEqual(json.load(response)['status'], 'matched')

    def test_invalid_body_unknown_path_and_external_origin_fail(self):
        with self.server() as base:
            cases = [('/api/recall/match', b'not json', {}, 400),
                     ('/api/recall/match', b'{}', {'Origin': 'https://evil.example'}, 403),
                     ('/api/recall/match', b'{}', {'Host': 'evil.example'}, 403),
                     ('/api/recall/match', b'x' * 5000, {}, 413),
                     ('/api/recall/unknown', None, {}, 404)]
            for path, data, headers, status in cases:
                with self.subTest(path=path, status=status):
                    request = Request(base + path, data=data, headers={'Content-Type': 'application/json', **headers})
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(request)
                    self.assertEqual(caught.exception.code, status)


if __name__ == '__main__':
    unittest.main()
