import base64
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ontology_poc_generator.recognition import ModelCompletion

CSV = '订单号,客户编号,金额\nO1,C1,100\nO2,C2,50\n'.encode('utf-8')
PROPOSAL = {
    'reasoning': 'r',
    'object_types': [
        {'key': 'order', 'label': '订单', 'populated_from': [{'source': 'orders', 'identity': {'order_id': '订单号'}}],
         'attributes': [{'source': 'orders', 'path': '金额'}]},
        {'key': 'customer', 'label': '客户', 'populated_from': [{'source': 'orders', 'identity': {'customer_id': '客户编号'}}],
         'attributes': []},
    ],
    'relations': [{'key': 'order_customer', 'from': 'order', 'to': 'customer', 'source': 'orders', 'meaning': '订单属于客户'}],
    'ignored_fields': [], 'open_questions': [],
}


class FakeModel:
    def complete_json(self, *, system_prompt, user_prompt):
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(PROPOSAL))


class OntologyServerTests(unittest.TestCase):
    @contextmanager
    def server(self, gateway=FakeModel()):
        from ontology_poc_generator.ontology_server import make_server
        with tempfile.TemporaryDirectory() as out:
            server = make_server(port=0, gateway=gateway, output_dir=Path(out))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                yield f'http://127.0.0.1:{server.server_port}', Path(out)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def post(self, base, payload, headers=None):
        request = Request(base + '/api/ontology/build', data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urlopen(request, timeout=30) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def test_upload_returns_the_ontology_and_its_evaluation_and_keeps_a_local_copy(self):
        with self.server() as (base, out):
            with urlopen(base + '/api/ontology/health') as response:
                self.assertEqual(json.load(response)['model_ready'], True)
            status, result = self.post(base, {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            self.assertEqual(status, 200, result)
            self.assertEqual(result['schema'], 'company_ontology_run.v1')
            self.assertEqual(result['ontology']['status'], 'auto_built_verified')
            self.assertEqual(result['sources'], [{'name': 'orders', 'rows': 2, 'fields': 3}])
            self.assertEqual({c['key'] for c in result['evaluation']['data_fit']['checks']},
                             {'fields_accounted', 'identity_consistent', 'relations_link', 'references_resolve', 'sources_connected'})
            saved = out / result['saved_as']
            self.assertEqual(json.loads(saved.read_text(encoding='utf-8'))['ontology']['status'], 'auto_built_verified')
            self.assertNotIn('O1', json.dumps(result['sources']))

    def test_bad_uploads_are_refused_with_a_reason(self):
        with self.server() as (base, _):
            for payload, headers, code, message in (
                    ({'filename': 'a.exe', 'content_base64': base64.b64encode(b'x').decode()}, {}, 400, '不支持'),
                    ({'filename': 'a.csv', 'content_base64': '***'}, {}, 400, 'base64'),
                    ({'filename': 'a.csv'}, {}, 400, 'content_base64'),
                    ({'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()},
                     {'Origin': 'https://evil.example'}, 403, '本机')):
                with self.subTest(code=code, message=message):
                    status, body = self.post(base, payload, headers)
                    self.assertEqual(status, code)
                    self.assertIn(message, body['error'])

    def test_without_a_model_key_the_page_is_told_how_to_fix_it(self):
        with self.server(gateway=None) as (base, _):
            with urlopen(base + '/api/ontology/health') as response:
                self.assertEqual(json.load(response)['model_ready'], False)
            status, body = self.post(base, {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            self.assertEqual(status, 503)
            self.assertIn('DEEPSEEK_API_KEY', body['error'])


if __name__ == '__main__':
    unittest.main()
