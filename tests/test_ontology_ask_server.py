import base64
import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
from ontology_poc_generator.recognition import ModelCompletion
from tests.test_ontology_server import CSV, PROPOSAL, OntologyServerTests

QUESTIONS = {'questions': [{'reasoning': 'r', 'question': '哪个客户订单最多？',
                            'query': {'start': 'order', 'where': [], 'via': ['order_customer'], 'group_by': None}}]}


class QuestionModel:
    def complete_json(self, *, system_prompt, user_prompt):
        content = QUESTIONS if system_prompt == QUESTION_SYSTEM_PROMPT else PROPOSAL
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(content))


def call(base, path, payload):
    request = Request(base + path, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


class AskServerTests(unittest.TestCase):
    def test_questions_are_asked_about_an_earlier_upload_and_saved_with_it(self):
        helper = OntologyServerTests()
        with helper.server(gateway=QuestionModel()) as (base, out):
            status, run = call(base, '/api/ontology/build', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            self.assertEqual(status, 200)
            self.assertTrue((out / run['saved_as'].replace('.json', '.bundle.json')).exists())
            status, updated = call(base, '/api/ontology/ask', {'saved_as': run['saved_as']})
            self.assertEqual(status, 200, updated)
            self.assertEqual(updated['evaluation']['questions']['items'][0]['answer'], {'total': 2})
            status, updated = call(base, '/api/ontology/ask', {'saved_as': run['saved_as'], 'question': '哪个客户订单最多？'})
            self.assertEqual(updated['evaluation']['asked'][0]['items'][0]['asked'], True)
            saved = json.loads((out / run['saved_as']).read_text(encoding='utf-8'))
            self.assertEqual(len(saved['evaluation']['asked']), 1)

    def test_only_known_runs_can_be_asked_about(self):
        helper = OntologyServerTests()
        with helper.server(gateway=QuestionModel()) as (base, _):
            for saved_as, code in (('../../etc/passwd', 400), ('20260101T000000Z-deadbeef.json', 404)):
                with self.subTest(saved_as=saved_as):
                    self.assertEqual(call(base, '/api/ontology/ask', {'saved_as': saved_as})[0], code)


if __name__ == '__main__':
    unittest.main()
