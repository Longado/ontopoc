import base64
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import urlopen

from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_jobs import wait
from tests.test_ontology_server import CSV

UPLOAD = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}


@contextmanager
def serving(out, gateway):
    from ontology_poc_generator.ontology_server import make_server
    server = make_server(port=0, gateway=gateway, output_dir=out)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def status_of(base, job_id):
    with urlopen(f'{base}/api/ontology/jobs/{job_id}') as response:
        return json.load(response)


class Held(QuestionModel):
    """Answers like QuestionModel, but the chosen kind of call waits until the test lets it go."""

    def __init__(self, hold_questions):
        self.hold_questions, self.entered, self.release = hold_questions, threading.Event(), threading.Event()

    def complete_json(self, *, system_prompt, user_prompt):
        if (system_prompt == QUESTION_SYSTEM_PROMPT) == self.hold_questions:
            self.entered.set()
            self.release.wait(20)
        return super().complete_json(system_prompt=system_prompt, user_prompt=user_prompt)


class JobPersistenceTests(unittest.TestCase):
    def test_a_finished_job_can_still_be_read_after_the_service_restarts(self):
        with tempfile.TemporaryDirectory() as out:
            with serving(Path(out), QuestionModel()) as base:
                _, started = call(base, '/api/ontology/jobs', UPLOAD)
                done = wait(base, started['job_id'])
            with serving(Path(out), QuestionModel()) as base:
                again = status_of(base, started['job_id'])
        self.assertEqual(again['state'], 'done')
        self.assertEqual(again['result']['saved_as'], done['result']['saved_as'])
        self.assertEqual([e['stage'] for e in again['events']], [e['stage'] for e in done['events']])

    def test_a_job_cut_off_by_a_restart_says_so_instead_of_running_forever(self):
        held = Held(hold_questions=False)
        try:
            with tempfile.TemporaryDirectory() as out:
                with serving(Path(out), held) as base:
                    _, started = call(base, '/api/ontology/jobs', UPLOAD)
                    self.assertTrue(held.entered.wait(10))
                    self.assertEqual(status_of(base, started['job_id'])['state'], 'running')
                with serving(Path(out), QuestionModel()) as base:
                    after = status_of(base, started['job_id'])
                # in a real restart the old process is gone; here its thread lives on, so let it finish inside this folder
                held.release.set()
                kept = Path(out) / 'jobs' / f"{started['job_id']}.json"
                for _ in range(400):
                    if json.loads(kept.read_text(encoding='utf-8'))['state'] != 'running':
                        break
                    threading.Event().wait(0.05)
        finally:
            held.release.set()
        self.assertEqual(after['state'], 'interrupted')
        self.assertIn('重启', after['error'])
        self.assertEqual(after['events'][0]['stage'], 'read')   # what it had got through is still shown


class RunWriteTests(unittest.TestCase):
    def test_a_confirmation_saved_while_a_question_is_answered_is_not_lost(self):
        held = Held(hold_questions=True)
        with tempfile.TemporaryDirectory() as out:
            with serving(Path(out), QuestionModel()) as base:
                _, run = call(base, '/api/ontology/build', UPLOAD)
            try:
                with serving(Path(out), held) as base:
                    asked = {}
                    asking = threading.Thread(target=lambda: asked.update(zip(('status', 'body'), call(
                        base, '/api/ontology/ask', {'saved_as': run['saved_as'], 'question': '哪个客户订单最多？'}))))
                    asking.start()
                    self.assertTrue(held.entered.wait(10))
                    decisions = {'types': {t['key']: {'verdict': 'ok'} for t in run['ontology']['object_types']},
                                 'relations': {}, 'added': []}
                    status, _ = call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions})
                    self.assertEqual(status, 200)
                    held.release.set()
                    asking.join(20)
            finally:
                held.release.set()
            self.assertEqual(asked['status'], 200, asked.get('body'))
            kept = json.loads((Path(out) / run['saved_as']).read_text(encoding='utf-8'))
        self.assertIn('confirmation', kept)       # written while the question was out with the model
        self.assertEqual(len(kept['evaluation']['asked']), 1)
        self.assertIn('confirmation', asked['body'])   # and the page is handed the run with both


if __name__ == '__main__':
    unittest.main()
