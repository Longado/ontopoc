import base64
import json
import time
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from tests.test_document_server import DocumentModel
from tests.test_company_documents import TEXT
from tests.test_ontology_ask_server import call
from tests.test_ontology_server import CSV, OntologyServerTests


def wait(base, job_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with urlopen(f'{base}/api/ontology/jobs/{job_id}') as response:
            job = json.load(response)
        if job['state'] != 'running':
            return job
        time.sleep(0.05)
    raise AssertionError('job did not finish')


class JobTests(unittest.TestCase):
    def test_a_build_runs_in_the_background_and_reports_its_steps(self):
        helper = OntologyServerTests()
        with helper.server(gateway=DocumentModel()) as (base, out):
            status, started = call(base, '/api/ontology/jobs', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            self.assertEqual(status, 202, started)
            job = wait(base, started['job_id'])
            self.assertEqual(job['state'], 'done')
            stages = [e['stage'] for e in job['events']]
            self.assertEqual(stages[0], 'read')
            self.assertIn('propose', stages)
            self.assertIn('verify', stages)
            self.assertEqual(stages[-2:], ['evaluate', 'done'])
            self.assertEqual(job['result']['ontology']['status'], 'auto_built_verified')
            self.assertTrue((out / job['result']['saved_as']).exists())

    def test_documents_report_each_chunk(self):
        helper = OntologyServerTests()
        with helper.server(gateway=DocumentModel()) as (base, _):
            _, started = call(base, '/api/ontology/jobs', {'filename': '流程.md', 'content_base64': base64.b64encode(TEXT.encode()).decode()})
            job = wait(base, started['job_id'])
            chunks = [e for e in job['events'] if e['stage'] == 'chunk']
            self.assertEqual([(e['detail']['index'], e['detail']['total']) for e in chunks], [(1, 1)])
            self.assertEqual(job['result']['file']['kind'], 'document')

    def test_bad_files_fail_at_once_and_unknown_jobs_are_404(self):
        helper = OntologyServerTests()
        with helper.server(gateway=DocumentModel()) as (base, _):
            status, body = call(base, '/api/ontology/jobs', {'filename': 'a.exe', 'content_base64': base64.b64encode(b'x').decode()})
            self.assertEqual(status, 400)
            self.assertIn('不支持', body['error'])
            with self.assertRaises(HTTPError) as missing:
                urlopen(f'{base}/api/ontology/jobs/nope')
            self.assertEqual(missing.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
