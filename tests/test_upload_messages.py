import base64
import unittest

from tests.test_document_server import DocumentModel
from tests.test_ontology_ask_server import call
from tests.test_ontology_server import OntologyServerTests


class UploadMessageTests(unittest.TestCase):
    def test_an_unknown_file_type_lists_both_tables_and_documents(self):
        with OntologyServerTests().server(gateway=DocumentModel()) as (base, _):
            status, body = call(base, '/api/ontology/jobs', {'filename': 'a.exe', 'content_base64': base64.b64encode(b'x').decode()})
        self.assertEqual(status, 400)
        for suffix in ('.csv', '.xlsx', '.md', '.docx', '.pdf'):
            self.assertIn(suffix, body['error'])


if __name__ == '__main__':
    unittest.main()
