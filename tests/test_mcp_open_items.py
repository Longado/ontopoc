"""What a consultant has to settle with the client comes back with the overview, from the service's own list of open
items (not recomputed here). A service that predates the route answers 404: the overview still comes, with no list and
a note saying why."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from ontology_poc_generator import mcp_server
from ontology_poc_generator.mcp_server import LocalService, ToolError

ITEMS = [{'kind': 'unlinked', 'ask': '财务支出行（financial_rows）1,921 行里有 1,308 行没连上“财务支出行 对应 合同授标”。', 'facts': [],
          'from_model': False, 'target': {'tab': 'graph', 'relation': 'rows_to_award'}, 'relation': 'rows_to_award'}]
RUN = {'saved_as': 'exam.json', 'file': {'name': 'exam.csv', 'kind': 'table'}, 'purpose': None,
       'ontology': {'status': 'auto_built_verified', 'object_types': [{}, {}], 'relations': [{}]},
       'evaluation': {'data_fit': {'checks': [{'passed': True}] * 6 + [{'passed': False}]}, 'asked': []}}
RUN_PATH = '/api/ontology/runs/exam.json'


@contextmanager
def serving(routes):
    """A stand-in for the local service: path -> (status, body); any other path is the 404 an older service gives."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def answer(self):
            if self.command == 'POST':
                self.rfile.read(int(self.headers.get('Content-Length') or 0))
            status, body = routes.get(self.path, (404, {'error': 'Unknown ontology endpoint'}))
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = answer

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class OverviewTests(unittest.TestCase):
    def test_the_overview_brings_the_open_items_beside_the_counts(self):
        with serving({RUN_PATH: (200, RUN), RUN_PATH + '/open-items': (200, {'items': ITEMS})}) as base:
            out = mcp_server.run_overview(LocalService(base), {'saved_as': 'exam.json'})
        self.assertEqual(out['open_items'], ITEMS)
        self.assertEqual((out['checks_passed'], out['objects'], out['relations']), ('6 / 7', 2, 1))
        self.assertNotIn('note', out)

    def test_nothing_to_settle_is_an_empty_list_not_a_missing_one(self):
        with serving({RUN_PATH: (200, RUN), RUN_PATH + '/open-items': (200, {'items': []})}) as base:
            out = mcp_server.run_overview(LocalService(base), {'saved_as': 'exam.json'})
        self.assertEqual(out['open_items'], [])
        self.assertNotIn('note', out)

    def test_a_service_without_the_route_gives_null_and_says_it_is_an_older_version(self):
        with serving({RUN_PATH: (200, RUN)}) as base:
            out = mcp_server.run_overview(LocalService(base), {'saved_as': 'exam.json'})
        self.assertIsNone(out['open_items'])
        self.assertIn('旧版本', out['note'])
        self.assertEqual(out['checks_passed'], '6 / 7')

    def test_other_failures_of_the_route_are_not_taken_for_an_old_service(self):
        with serving({RUN_PATH: (200, RUN), RUN_PATH + '/open-items': (500, {'error': '读不了这次运行'})}) as base:
            with self.assertRaisesRegex(ToolError, '读不了这次运行'):
                mcp_server.run_overview(LocalService(base), {'saved_as': 'exam.json'})

    def test_a_404_that_says_the_run_is_missing_is_an_error_not_an_old_service(self):
        for text in ('找不到这次运行，可能已经被删掉了', '找不到这次运行'):
            with self.subTest(text=text), serving({RUN_PATH: (200, RUN), RUN_PATH + '/open-items': (404, {'error': text})}) as base:
                with self.assertRaisesRegex(ToolError, text):
                    mcp_server.run_overview(LocalService(base), {'saved_as': 'exam.json'})


def asked(*rounds):
    return {**RUN, 'evaluation': {**RUN['evaluation'], 'asked': [{'items': [{'question': q, 'status': s} for q, s in r]} for r in rounds]}}


class QuestionCountTests(unittest.TestCase):
    def test_a_question_asked_again_counts_once_at_its_latest_answer(self):
        run = asked([('A', 'answered'), ('B', 'no_data')], [('A', 'answered')], [('B', 'answered')])   # the second and third rounds are drop_filter reruns
        self.assertEqual(mcp_server._overview(run)['questions_answered'], '2 / 2')

    def test_the_latest_ask_decides_even_when_it_is_the_worse_one(self):
        self.assertEqual(mcp_server._overview(asked([('A', 'answered')], [('A', 'no_data')]))['questions_answered'], '0 / 1')

    def test_the_models_own_round_still_counts_but_a_question_asked_by_a_person_is_not_counted_twice(self):
        base = asked([('A', 'no_data'), ('B', 'answered')])
        models = {'items': [{'question': 'A', 'status': 'answered'}, {'question': 'C', 'status': 'query_limit'}, {'question': 'D', 'status': 'answered'}]}
        run = {**base, 'evaluation': {**base['evaluation'], 'questions': models}}
        self.assertEqual(mcp_server._overview(run)['questions_answered'], '2 / 4')   # A (asked later: no_data), B, C, D


class BuildTests(unittest.TestCase):
    def build(self, routes):
        with serving(routes) as base, tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'exam.csv'
            path.write_text('a,b\n1,2\n', encoding='utf-8')
            return mcp_server.build_ontology(LocalService(base, poll_seconds=0.01), {'files': [str(path)], 'purpose': '看清合同'})

    def test_a_finished_build_returns_the_overview_with_the_open_items(self):
        out = self.build({'/api/ontology/jobs': (200, {'job_id': 'j1'}), '/api/ontology/jobs/j1': (200, {'state': 'done', 'result': RUN}),
                          RUN_PATH + '/open-items': (200, {'items': ITEMS})})
        self.assertEqual(out['saved_as'], 'exam.json')
        self.assertEqual(out['open_items'], ITEMS)

    def test_a_finished_build_on_an_old_service_still_returns_the_overview(self):
        out = self.build({'/api/ontology/jobs': (200, {'job_id': 'j1'}), '/api/ontology/jobs/j1': (200, {'state': 'done', 'result': RUN})})
        self.assertIsNone(out['open_items'])
        self.assertIn('旧版本', out['note'])
        self.assertEqual(out['status'], 'auto_built_verified')


if __name__ == '__main__':
    unittest.main()
