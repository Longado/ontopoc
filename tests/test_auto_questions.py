"""An upload does what the person needs to judge the draft: build it, build it twice more to show where the model is
unsure, and answer the question the person wrote as the purpose. The model's own round of questions is asked for on
the questions page, not spent on every upload."""
import base64
import json
import unittest

from ontology_poc_generator.mcp_server import _overview
from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
from tests.test_company_documents import TEXT
from tests.test_document_server import DocumentModel
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_jobs import wait
from tests.test_ontology_server import CSV, OntologyServerTests


class Counting(QuestionModel):
    def __init__(self):
        self.calls = []

    def complete_json(self, *, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return super().complete_json(system_prompt=system_prompt, user_prompt=user_prompt)

    def question_calls(self):
        return [json.loads(u) for s, u in self.calls if s == QUESTION_SYSTEM_PROMPT]


def upload(model, purpose=None):
    with OntologyServerTests().server(gateway=model) as (base, _):
        payload = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode(), **({'purpose': purpose} if purpose else {})}
        _, started = call(base, '/api/ontology/jobs', payload)
        return wait(base, started['job_id'])


class PurposeFirstTests(unittest.TestCase):
    def test_a_build_answers_the_question_in_its_purpose_and_nothing_else(self):
        model = Counting()
        job = upload(model, '哪个客户订单最多？')
        self.assertEqual(job['state'], 'done')
        [sent] = model.question_calls()
        self.assertEqual((sent['purpose'], sent.get('only_purpose')), ('哪个客户订单最多？', True))
        self.assertEqual(len(model.calls), 4)   # the draft, two more for stability, the person's question
        evaluation = job['result']['evaluation']
        self.assertNotIn('questions', evaluation)   # no round the person did not ask for
        [entry] = evaluation['asked']
        self.assertEqual([(i['status'], i.get('from_purpose')) for i in entry['items']], [('answered', True)])

    def test_without_a_purpose_no_question_is_written(self):
        model = Counting()
        job = upload(model)
        self.assertEqual(job['state'], 'done')
        self.assertEqual((model.question_calls(), len(model.calls)), ([], 3))
        self.assertNotIn('asked', job['result']['evaluation'])
        self.assertNotIn('questions', [e['stage'] for e in job['events']])

    def test_the_prompt_says_to_answer_only_the_purposes_questions(self):
        self.assertIn('only_purpose', QUESTION_SYSTEM_PROMPT)

    def test_documents_skip_the_question_round(self):
        with OntologyServerTests().server(gateway=DocumentModel()) as (base, _):
            _, started = call(base, '/api/ontology/jobs', {'filename': '流程.md', 'content_base64': base64.b64encode(TEXT.encode()).decode(), 'purpose': '哪些环节要审批？'})
            job = wait(base, started['job_id'])
        self.assertNotIn('questions', [e['stage'] for e in job['events']])
        self.assertNotIn('questions', job['result']['evaluation'])

    def test_an_agent_sees_the_purpose_answers_counted_too(self):
        run = {'file': {'name': 'orders.csv'}, 'ontology': {'status': 'auto_built_verified', 'object_types': [], 'relations': []},
               'evaluation': {'asked': [{'items': [{'status': 'answered', 'from_purpose': True}]}]}}
        self.assertEqual(_overview(run)['questions_answered'], '1 / 1')


if __name__ == '__main__':
    unittest.main()
