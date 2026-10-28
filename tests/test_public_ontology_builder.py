import importlib
import json
from pathlib import Path
import unittest

from ontology_poc_generator.nhtsa_sources import bundle_content_hash
from ontology_poc_generator.recognition import ModelCompletion, RecognitionError

FIXTURES = Path(__file__).resolve().parent / 'fixtures/nhtsa'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class FakeGateway:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete_json(self, *, system_prompt, user_prompt):
        self.calls.append({'system': system_prompt, 'user': user_prompt})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return ModelCompletion(provider='fake', model='deepseek-flash', content=content)


class AutoBuildOntologyTests(unittest.TestCase):
    def api(self):
        module = importlib.import_module('ontology_poc_generator.public_ontology')
        self.assertTrue(hasattr(module, 'auto_build_ontology'), 'auto ontology builder is not implemented')
        return module

    def setUp(self):
        self.bundle = load('mini_bundle.json')
        self.recorded = load('recorded_modeler_attempts.json')

    def test_code_errors_are_sent_back_and_second_attempt_passes(self):
        gw = FakeGateway(self.recorded)
        o = self.api().auto_build_ontology(self.bundle, gw)
        self.assertEqual(o['schema'], 'public_ontology.v1')
        self.assertEqual(o['status'], 'auto_built_verified')
        self.assertEqual(o['human_review'], 'pending')
        self.assertEqual([[e['code'] for e in a['errors']] for a in o['attempts']], [['role_relation_missing'], []])
        retry = json.loads(gw.calls[1]['user'])
        self.assertEqual([e['code'] for e in retry['errors_found_by_code']], ['role_relation_missing'])
        self.assertEqual(retry['previous_proposal'], self.recorded[0])
        self.assertEqual(o['verification']['errors'], [])
        self.assertEqual(o['verification']['metrics']['shared_across_sources']['vehicle_model_year'], 2)

    def test_output_carries_provenance(self):
        o = self.api().auto_build_ontology(self.bundle, FakeGateway(self.recorded))
        self.assertEqual(o['source_bundle_hash'], bundle_content_hash(self.bundle))
        self.assertEqual(o['model'], 'deepseek-flash')
        self.assertEqual(o['prompt_version'], 'public_ontology_modeler.v4')
        self.assertEqual(o['evidence_scope'], 'public_data')
        self.assertEqual([t['key'] for t in o['object_types']], [t['key'] for t in self.recorded[1]['object_types']])
        self.assertEqual(o['data_gaps'], self.recorded[1]['open_questions'])

    def test_stops_when_errors_do_not_shrink(self):
        gw = FakeGateway([self.recorded[0], self.recorded[0], self.recorded[1]])
        o = self.api().auto_build_ontology(self.bundle, gw)
        self.assertEqual(o['status'], 'blocked')
        self.assertEqual(len(gw.calls), 2)
        self.assertEqual([e['code'] for e in o['verification']['errors']], ['role_relation_missing'])

    def test_non_json_and_model_failure_block_without_raising(self):
        o = self.api().auto_build_ontology(self.bundle, FakeGateway(['not json', 'still not json']))
        self.assertEqual(o['status'], 'blocked')
        self.assertEqual(o['attempts'][0]['errors'][0]['code'], 'invalid_response')
        failing = FakeGateway([RecognitionError('timeout'), RecognitionError('timeout')])
        o = self.api().auto_build_ontology(self.bundle, failing)
        self.assertEqual(o['status'], 'blocked')
        self.assertEqual(o['attempts'][0]['errors'][0]['code'], 'model_request_failed')

    def test_model_sees_field_catalog_not_full_records(self):
        gw = FakeGateway(self.recorded)
        self.api().auto_build_ontology(self.bundle, gw)
        first = json.loads(gw.calls[0]['user'])
        self.assertEqual(set(first), {'decision', 'sources'})
        self.assertIn('summary', first['sources']['complaints']['fields'])
        late = next(r for r in self.bundle['sources']['complaints']['records'] if r['odiNumber'] == 11600123)
        self.assertNotIn(late['summary'][:60], gw.calls[0]['user'])

    def test_model_cannot_mark_its_own_ontology_reviewed(self):
        tampered = [dict(self.recorded[1], human_review='confirmed', status='published')]
        o = self.api().auto_build_ontology(self.bundle, FakeGateway(tampered))
        self.assertEqual(o['human_review'], 'pending')
        self.assertEqual(o['status'], 'auto_built_verified')


TABLES = {
    'orders.csv': '订单号,客户,状态,金额\nO1,C1,已发货,10\nO2,C2,已发货,20\nO3,C1,待发货,30\nO4,,已发货,40\n',
    'customers.csv': '客户编号,名称\nC1,甲\nC2,乙\nC3,丙\n',
    'lines.csv': '订单号,行号,数量,产品编号\nO1,1,2,1\nO1,2,1,2\nO2,1,3,1\nO3,1,1,3\n',
    'products.csv': '产品编号,品名\n1,螺丝\n2,螺母\n3,垫片\n4,弹簧\n',
    'staff.csv': '员工号,姓名,上级\nE1,张,\nE2,李,E1\nE3,王,E1\nE4,赵,E2\n',
    'invoices.csv': '发票,商品,数量\nA,x,1\nA,x,1\nB,y,2\n',
    'events.csv': '编号,创建时间,修改时间\nV1,2024-01-01,2024-01-02\nV2,2024-01-02,2024-01-03\nV3,2024-01-03,2024-01-04\n',
}


class CatalogFactsTests(unittest.TestCase):
    """What code works out on every row before the model drafts: counts per column, the columns that tell rows
    apart, and the columns whose values turn up in another column's unique values."""

    def catalog(self):
        from ontology_poc_generator.company_sources import load_table_files
        from ontology_poc_generator.public_ontology import field_catalog
        return field_catalog(load_table_files([(name, text.encode('utf-8')) for name, text in TABLES.items()]))

    def test_each_column_carries_its_counts_and_a_category_its_values(self):
        facts = self.catalog()['orders']['facts']
        self.assertEqual(facts['状态'], {'filled': 4, 'distinct': 2, 'values': ['已发货', '待发货']})
        # few values, but not a category: listing them would send a small table whole
        self.assertEqual(facts['订单号'], {'filled': 4, 'distinct': 4, 'unique': True})
        self.assertEqual(facts['客户'], {'filled': 3, 'distinct': 2})

    def test_examples_stay_what_they_were(self):
        self.assertEqual(self.catalog()['orders']['fields']['订单号'], ['O1', 'O2', 'O3'])

    def test_a_table_lists_the_columns_that_tell_its_rows_apart(self):
        catalog = self.catalog()
        self.assertEqual(catalog['customers']['unique_columns'], ['客户编号', '名称'])
        self.assertNotIn('unique_pairs', catalog['customers'])
        self.assertEqual(catalog['orders']['unique_columns'], ['订单号', '金额'])   # 客户 has a blank row

    def test_without_such_a_column_it_lists_pairs_or_says_there_are_none(self):
        catalog = self.catalog()
        self.assertEqual(catalog['lines']['unique_columns'], [])
        self.assertIn(['订单号', '行号'], catalog['lines']['unique_pairs'])
        self.assertLessEqual(len(catalog['lines']['unique_pairs']), 5)
        self.assertEqual(catalog['invoices']['unique_pairs'], [])

    def test_a_column_whose_values_sit_in_another_columns_unique_values_is_a_likely_link(self):
        links = self.catalog()['lines']['links']
        self.assertIn({'field': '订单号', 'to_table': 'orders', 'to_field': '订单号', 'found': 3, 'of': 3}, links)
        self.assertIn({'field': '产品编号', 'to_table': 'products', 'to_field': '产品编号', 'found': 3, 'of': 3}, links)
        self.assertIn({'field': '客户', 'to_table': 'customers', 'to_field': '客户编号', 'found': 2, 'of': 2},
                      self.catalog()['orders']['links'])

    def test_small_numbers_under_unrelated_names_are_not_a_link(self):
        linked = {l['field'] for l in self.catalog()['lines']['links']}
        self.assertNotIn('数量', linked)   # 1-3 sit inside 产品编号 1-4 by chance
        self.assertNotIn('行号', linked)

    def test_dates_that_happen_to_match_are_not_a_link(self):
        self.assertNotIn('links', self.catalog()['events'])   # 修改时间 shares two days with 创建时间

    def test_a_column_pointing_into_its_own_table_is_a_link_too(self):
        self.assertIn({'field': '上级', 'to_table': 'staff', 'to_field': '员工号', 'found': 2, 'of': 2},
                      self.catalog()['staff']['links'])

    def test_the_first_request_to_the_modeler_carries_the_facts(self):
        from ontology_poc_generator.company_ontology import build_company_ontology
        from ontology_poc_generator.company_sources import load_table_files
        gw = FakeGateway(['not json', 'still not json'])
        build_company_ontology(load_table_files([(name, text.encode('utf-8')) for name, text in TABLES.items()]), gw)
        sent = json.loads(gw.calls[0]['user'])['sources']
        self.assertEqual(sent['lines']['unique_columns'], [])
        self.assertIn('links', sent['lines'])
        self.assertEqual(sent['orders']['facts']['订单号']['distinct'], 4)


if __name__ == '__main__':
    unittest.main()
