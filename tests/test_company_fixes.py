import base64
import unittest

from ontology_poc_generator.company_sources import load_table_file
from ontology_poc_generator.ontology_eval import data_fit
from ontology_poc_generator.recognition import RecognitionError
from tests.test_company_sources import xlsx
from tests.test_ontology_server import CSV, OntologyServerTests


class TitleRowTests(unittest.TestCase):
    def test_a_title_row_above_the_real_header_is_skipped_and_noted(self):
        bundle = load_table_file('erp.xlsx', xlsx({'采购订单': [
            ['2026年采购明细'], [None], ['采购单号', '物料编码', '数量'], ['PO1', '000123', 5], ['PO2', '000124', 7]]}))
        source = bundle['sources']['采购订单']
        self.assertEqual(source['records'], [{'采购单号': 'PO1', '物料编码': '000123', '数量': '5'},
                                             {'采购单号': 'PO2', '物料编码': '000124', '数量': '7'}])
        self.assertEqual(source['skipped_rows'], ['2026年采购明细'])

    def test_a_column_with_no_header_and_no_values_is_dropped(self):
        bundle = load_table_file('t.xlsx', xlsx({'表': [['a', None, 'b'], [1, None, 2], [3, None, 4]]}))
        self.assertEqual(bundle['sources']['表']['records'], [{'a': '1', 'b': '2'}, {'a': '3', 'b': '4'}])
        self.assertNotIn('skipped_rows', bundle['sources']['表'])


BUNDLE = {'decision': 'd', 'sources': {
    '客户': {'records': [{'客户编号': 'C1005', '名称': '甲'}, {'客户编号': 'c1005 ', '名称': '甲'}, {'客户编号': 'C1006', '名称': '乙'}], 'requests': []},
    '商品': {'records': [{'商品编号': '00106', '名称': '螺丝'}, {'商品编号': '106', '名称': '螺丝'}, {'商品编号': '200', '名称': '螺母'}], 'requests': []},
}}
PROPOSAL = {'object_types': [
    {'key': 'customer', 'label': '客户', 'populated_from': [{'source': '客户', 'identity': {'customer_id': '客户编号'}}],
     'attributes': [{'source': '客户', 'path': '名称'}]},
    {'key': 'product', 'label': '商品', 'populated_from': [{'source': '商品', 'identity': {'product_id': '商品编号'}}],
     'attributes': [{'source': '商品', 'path': '名称'}]},
], 'relations': [], 'ignored_fields': []}


class IdentitySpellingTests(unittest.TestCase):
    def setUp(self):
        self.fit = data_fit(PROPOSAL, BUNDLE)

    def test_the_same_identity_written_differently_is_reported(self):
        self.assertEqual(self.fit['identity_spellings'], [
            {'type': 'customer', 'identity': 'C1005', 'variants': ['C1005', 'c1005 ']}])
        self.assertFalse(next(c for c in self.fit['checks'] if c['key'] == 'identity_spelling')['passed'])

    def test_identities_equal_after_dropping_leading_zeros_are_suspected_duplicates(self):
        self.assertEqual(self.fit['suspected_duplicates'], [
            {'type': 'product', 'rule': 'leading_zeros', 'identities': ['00106', '106']}])


class FailingModel:
    def complete_json(self, *, system_prompt, user_prompt):
        raise RecognitionError('model request failed: <urlopen error [Errno 8] nodename nor servname provided>')


class ModelFailureTests(unittest.TestCase):
    def test_a_model_outage_is_a_retryable_error_not_a_verdict_on_the_data(self):
        server_tests = OntologyServerTests()
        with server_tests.server(gateway=FailingModel()) as (base, out):
            status, body = server_tests.post(base, {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            self.assertEqual(status, 502)
            self.assertIn('模型请求失败', body['error'])
            self.assertIn('重试', body['error'])
            self.assertEqual(list(out.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
