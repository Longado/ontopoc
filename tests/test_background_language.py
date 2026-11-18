"""Work that moves to another thread on behalf of a request keeps the request's language: a modeling job started with Accept-Language: en writes its error in English;
without the header it stays Chinese. The reply for an unknown workspace endpoint follows the language too."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ontology_poc_generator import lang
from tests.test_job_persistence import UPLOAD, serving
from tests.test_ontology_jobs import wait

EN = {'Accept-Language': 'en-US,en;q=0.9'}


class Broken:
    model = 'broken'

    def complete_json(self, **kwargs):
        raise RuntimeError('the model is down')


def post(base, path, payload, headers=None):
    request = Request(base + path, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', **(headers or {})})
    with urlopen(request, timeout=30) as response:
        return response.status, json.load(response)


def get(base, path, headers=None):
    try:
        with urlopen(Request(base + path, headers=headers or {}), timeout=30) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


class BackgroundLanguageTests(unittest.TestCase):
    def failed_job(self, headers):
        with tempfile.TemporaryDirectory() as out:
            with serving(Path(out), Broken()) as base:
                _, started = post(base, '/api/ontology/jobs', UPLOAD, headers)
                return wait(base, started['job_id'])

    def test_a_job_started_in_english_writes_its_error_in_english(self):
        job = self.failed_job(EN)
        self.assertEqual(job['state'], 'failed')
        self.assertIn('An error happened while modeling', job['error'])

    def test_a_job_started_without_the_header_stays_chinese(self):
        job = self.failed_job({})
        self.assertEqual(job['state'], 'failed')
        self.assertIn('建模时出错', job['error'])

    def test_carry_keeps_the_language_it_was_made_in_and_can_run_again_and_in_threads(self):
        seen = []
        token = lang.use('en')
        try:
            work = lang.carry(lambda: seen.append(lang.tr('中', 'en')))
        finally:
            lang._LANG.reset(token)
        threads = [threading.Thread(target=work) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        work()
        self.assertEqual(seen, ['en'] * 4)
        self.assertEqual(lang.tr('中', 'en'), '中')

    def test_unknown_workspace_endpoint_follows_the_language(self):
        with tempfile.TemporaryDirectory() as out:
            with serving(Path(out), None) as base:
                self.assertEqual(get(base, '/api/workspace/nothing-here', EN), (404, {'error': 'Unknown workspace endpoint'}))
                self.assertEqual(get(base, '/api/workspace/nothing-here'), (404, {'error': '没有这个工作区接口'}))


if __name__ == '__main__':
    unittest.main()
