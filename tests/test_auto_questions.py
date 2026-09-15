import base64
import unittest

from tests.test_company_documents import TEXT
from tests.test_document_server import DocumentModel
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_jobs import wait
from tests.test_ontology_server import CSV, OntologyServerTests


class AutoQuestionTests(unittest.TestCase):
    def test_a_table_build_answers_one_round_of_questions_on_its_own(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            _, started = call(base, '/api/ontology/jobs', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            job = wait(base, started['job_id'])
        self.assertEqual(job['state'], 'done')
        stages = [e['stage'] for e in job['events']]
        self.assertLess(stages.index('evaluate'), stages.index('questions'))
        round_ = job['result']['evaluation']['questions']
        self.assertGreater(round_['total'], 0)
        self.assertIsNone(round_['error'])

    def test_documents_skip_the_question_round(self):
        with OntologyServerTests().server(gateway=DocumentModel()) as (base, _):
            _, started = call(base, '/api/ontology/jobs', {'filename': '流程.md', 'content_base64': base64.b64encode(TEXT.encode()).decode()})
            job = wait(base, started['job_id'])
        self.assertNotIn('questions', [e['stage'] for e in job['events']])
        self.assertNotIn('questions', job['result']['evaluation'])


if __name__ == '__main__':
    unittest.main()
