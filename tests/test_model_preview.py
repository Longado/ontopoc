import base64
import unittest

from ontology_poc_generator.company_documents import MAX_CHUNKS
from ontology_poc_generator.company_sources import load_table_file
from ontology_poc_generator.model_preview import model_preview
from ontology_poc_generator.public_ontology import field_catalog
from tests.test_company_documents import TEXT
from tests.test_ontology_ask_server import call
from tests.test_ontology_server import OntologyServerTests

ROWS = '订单号,状态,备注\n' + '\n'.join(f'O{i},{"延期" if i % 3 else "按时"},第{i}单' for i in range(1, 21)) + '\n'


class PreviewTests(unittest.TestCase):
    def test_a_table_preview_is_what_the_modeler_sees_plus_full_value_lists_of_small_fields(self):
        bundle = load_table_file('订单.csv', ROWS.encode('utf-8'))
        preview = model_preview(bundle)
        self.assertEqual(preview['kind'], 'table')
        catalog = field_catalog(bundle)
        source = preview['sources'][0]
        self.assertEqual((source['name'], source['record_count']), ('订单', 20))
        self.assertEqual({f['path']: f['examples'] for f in source['fields']}, catalog['订单']['fields'])
        values = {f['path']: f.get('values') for f in source['fields']}
        self.assertEqual(values['状态'], ['延期', '按时'])
        self.assertIsNone(values['备注'])   # 20 distinct values: only the three examples can be sent

    def test_a_document_preview_says_the_text_is_sent_in_parts(self):
        from ontology_poc_generator.company_documents import load_document_file
        preview = model_preview(load_document_file('流程.md', TEXT.encode('utf-8')))
        self.assertEqual(preview['kind'], 'document')
        self.assertEqual((preview['chunks_sent'], preview['chunks_total'], preview['paragraphs']), (1, 1, 3))
        self.assertLessEqual(preview['chunks_sent'], MAX_CHUNKS)

    def test_the_service_previews_without_calling_the_model(self):
        with OntologyServerTests().server(gateway=None) as (base, _):
            status, body = call(base, '/api/ontology/preview', {'filename': '订单.csv', 'content_base64': base64.b64encode(ROWS.encode()).decode()})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['sources'][0]['record_count'], 20)


if __name__ == '__main__':
    unittest.main()
