import base64
import json
import unittest

from ontology_poc_generator.company_documents import DOCUMENT_SYSTEM_PROMPT
from ontology_poc_generator.recognition import ModelCompletion
from tests.test_company_documents import REPLY, TEXT
from tests.test_ontology_ask_server import call
from tests.test_ontology_server import OntologyServerTests, PROPOSAL


class DocumentModel:
    def complete_json(self, *, system_prompt, user_prompt):
        content = REPLY if system_prompt == DOCUMENT_SYSTEM_PROMPT else PROPOSAL
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(content))


class DocumentServerTests(unittest.TestCase):
    def test_a_document_upload_returns_quoted_concepts_and_document_checks(self):
        helper = OntologyServerTests()
        with helper.server(gateway=DocumentModel()) as (base, _):
            status, run = call(base, '/api/ontology/build', {'filename': '流程.md', 'content_base64': base64.b64encode(TEXT.encode()).decode()})
            self.assertEqual(status, 200, run)
            self.assertEqual(run['file']['kind'], 'document')
            self.assertEqual(run['sources'], [{'name': '流程.md', 'paragraphs': 3, 'chars': sum(len(p) for p in TEXT.split('\n\n'))}])
            self.assertEqual([t['label'] for t in run['ontology']['object_types']], ['售后工单', '售后工程师', '订单'])
            self.assertEqual(run['evaluation']['data_fit'], None)
            self.assertEqual(run['evaluation']['document_fit']['rejected'], 3)
            status, body = call(base, '/api/ontology/ask', {'saved_as': run['saved_as']})
            self.assertEqual(status, 400)
            self.assertIn('数据表', body['error'])


if __name__ == '__main__':
    unittest.main()
