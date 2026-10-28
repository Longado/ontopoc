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

    def test_tables_whose_keys_are_all_called_id_do_not_link_to_each_other(self):
        from ontology_poc_generator.company_sources import load_table_files
        from ontology_poc_generator.public_ontology import field_catalog
        catalog = field_catalog(load_table_files([
            ('customers.csv', b'id,name\n1,A\n2,B\n3,C\n4,D\n'), ('products.csv', b'id,title\n1,x\n2,y\n3,z\n'),
            ('orders.csv', b'id,customer_id,product_id\n1,1,2\n2,2,3\n3,3,1\n4,1,1\n')]))
        links = [(name, l['field'], l['to_table'], l['to_field']) for name, e in catalog.items() for l in e.get('links', [])]
        self.assertEqual(sorted(links), [('orders', 'customer_id', 'customers', 'id'), ('orders', 'product_id', 'products', 'id')])

    def test_a_stray_word_among_numbers_does_not_make_them_a_link(self):
        from ontology_poc_generator.company_sources import load_table_files
        from ontology_poc_generator.public_ontology import field_catalog
        catalog = field_catalog(load_table_files([('products.csv', TABLES['products.csv'].encode('utf-8')),
                                                  ('lines.csv', '订单号,数量\nO1,1\nO2,2\nO3,3\nO4,待定\n'.encode('utf-8'))]))
        self.assertNotIn('links', catalog['lines'])   # the numbers it shares with 产品编号 are still plain numbers

    def test_dates_with_a_zone_or_slashes_are_not_a_link_either(self):
        from ontology_poc_generator.company_sources import load_table_file
        from ontology_poc_generator.public_ontology import field_catalog
        rows = '编号,开始,结束\n' + '\n'.join(f'V{i},{i}/5/2024,{i + 1}/5/2024' for i in range(1, 6)) + '\n'
        zoned = '编号,创建,修改\n' + '\n'.join(f'V{i},2024-01-0{i}T10:00:00Z,2024-01-0{i + 1}T10:00:00Z' for i in range(1, 6)) + '\n'
        for text in (rows, zoned):
            self.assertNotIn('links', field_catalog(load_table_file('events.csv', text.encode('utf-8')))['events'])

    def test_version_and_outline_numbers_are_keys_not_dates(self):
        from ontology_poc_generator.company_sources import load_table_files
        from ontology_poc_generator.public_ontology import field_catalog
        versions = [f'1.{i // 4}.{i % 4}' for i in range(12)]
        catalog = field_catalog(load_table_files([
            ('releases.csv', ('版本,发布人\n' + ''.join(f'{v},P{i % 3}\n' for i, v in enumerate(versions))).encode('utf-8')),
            ('issues.csv', ('问题,发现版本\n' + ''.join(f'I{i},{versions[i % 12]}\n' for i in range(30))).encode('utf-8'))]))
        self.assertEqual(catalog['releases']['unique_columns'], ['版本'])
        self.assertIn({'field': '发现版本', 'to_table': 'releases', 'to_field': '版本', 'found': 12, 'of': 12}, catalog['issues']['links'])

    def test_more_date_spellings_are_not_a_link(self):
        from ontology_poc_generator.company_sources import load_table_file
        from ontology_poc_generator.public_ontology import field_catalog
        spellings = [lambda d: f'1/{d}/2024 12:00:00 AM', lambda d: f'2024-01-0{d} 10:00:00 +08:00',
                     lambda d: f'2024-01-0{d} 10:00:00 UTC', lambda d: f'2024年1月{d}日', lambda d: f'0{d}-01-2024',
                     lambda d: f'1/{d}/2024 3:00 p.m.', lambda d: f'2024-01-0{d} 10:00 CST', lambda d: f'2024年1月{d}号 上午10:00',
                     lambda d: f'0{d}-Jan-2024', lambda d: f'Jan {d}, 2024']
        for spell in spellings:
            text = '编号,开始,结束\n' + ''.join(f'V{d},"{spell(d)}","{spell(d + 1)}"\n' for d in range(1, 6))
            self.assertNotIn('links', field_catalog(load_table_file('events.csv', text.encode('utf-8')))['events'], spell(1))

    def test_structured_codes_are_keys_and_links_not_dates(self):
        from ontology_poc_generator.company_sources import load_table_files
        from ontology_poc_generator.public_ontology import field_catalog
        for codes in [[f'1001.0{i % 3 + 1}.0{i // 3 + 1}' for i in range(12)], [f'01.0{i % 3 + 1}.000{i // 3 + 1}' for i in range(12)],
                      [f'8501.{10 + i}.00' for i in range(12)], [f'2024-05-10-000{i}' for i in range(10)],
                      [f'{10 + i}-JUN-0045' for i in range(12)], [f'6001-01-{10 + i}' for i in range(12)]]:
            catalog = field_catalog(load_table_files([
                ('master.csv', ('编码,名称\n' + ''.join(f'{c},N{i}\n' for i, c in enumerate(codes))).encode('utf-8')),
                ('lines.csv', ('单据,编码\n' + ''.join(f'L{i},{codes[i % len(codes)]}\n' for i in range(30))).encode('utf-8'))]))
            self.assertEqual(catalog['master']['unique_columns'], ['编码', '名称'], codes[0])
            self.assertIn({'field': '编码', 'to_table': 'master', 'to_field': '编码', 'found': len(codes), 'of': len(codes)},
                          catalog['lines']['links'], codes[0])

    def test_amounts_hide_no_key_whatever_the_column_is_called(self):
        from ontology_poc_generator.company_sources import load_table_file
        from ontology_poc_generator.public_ontology import field_catalog
        amounts = [['100.00', '250.00', '1200.00', '75.50', '300.00', '410.00'], ['100', '250', '1200', '75.5', '300', '410'],
                   ['¥1,200.50', '¥980.00', '¥45.10', '¥3,000.00', '¥12.80', '¥640.00']]
        for name in ['amount', 'amount_paid', 'Bid', 'Valid', '实付金额']:
            for values in amounts:
                text = f'order_no,line_no,{name}\n' + ''.join(f'O{i // 2},{i % 2 + 1},{v}\n' for i, v in enumerate(values))
                entry = field_catalog(load_table_file('lines.csv', text.encode('utf-8')))['lines']
                self.assertEqual((entry['unique_columns'], entry.get('unique_pairs')), ([], [['order_no', 'line_no']]), (name, values[0]))

    def test_a_code_named_so_stays_a_key_in_either_language(self):
        from ontology_poc_generator.company_sources import load_table_file
        from ontology_poc_generator.public_ontology import field_catalog
        for name in ['科目编码', '科目代码', 'account_code', 'AccountNo', 'acct id']:
            text = f'{name},科目名称\n' + ''.join(f'{1001 + i}.0{i % 9 + 1},科目{i}\n' for i in range(8))
            self.assertIn(name, field_catalog(load_table_file('accounts.csv', text.encode('utf-8')))['accounts']['unique_columns'], name)

    def test_one_long_name_or_a_float_written_id_still_tells_rows_apart(self):
        from ontology_poc_generator.company_sources import load_table_file
        from ontology_poc_generator.public_ontology import field_catalog
        long = 'Department of Strategic Planning and International Cooperation Affairs (Shanghai Branch)'
        text = '部门,编号,科目代码\n' + ''.join(f'{long if i == 0 else f"D{i}"},{1000 + i}.0,{1000 + i}.0{i + 1}\n' for i in range(6))
        self.assertEqual(field_catalog(load_table_file('dept.csv', text.encode('utf-8')))['dept']['unique_columns'],
                         ['部门', '编号', '科目代码'])

    def test_a_category_with_more_than_twelve_spellings_is_not_sent_whole(self):
        from ontology_poc_generator.company_sources import load_table_file
        from ontology_poc_generator.public_ontology import field_catalog
        states = [w for s in ['Open', 'Closed', 'Done', 'New', 'Held', 'Lost', 'Won'] for w in (s, s.upper())]
        text = '编号,状态\n' + ''.join(f'T{i},{states[i % 14]}\n' for i in range(28))
        fact = field_catalog(load_table_file('t.csv', text.encode('utf-8')))['t']['facts']['状态']
        self.assertEqual(fact, {'filled': 28, 'distinct': 7})   # the preview lists at most 12, so the modeler does too

    def test_counts_fold_case_and_spaces_as_identities_do(self):
        from ontology_poc_generator.company_sources import load_table_file
        from ontology_poc_generator.public_ontology import field_catalog
        facts = field_catalog(load_table_file('t.csv', 'k,v\nO1,1\no1,2\nO2,3\n'.encode('utf-8')))['t']['facts']
        self.assertEqual(facts['k'], {'filled': 3, 'distinct': 2})

    def test_amounts_dates_and_long_text_do_not_count_as_telling_rows_apart(self):
        from ontology_poc_generator.company_sources import load_table_file
        from ontology_poc_generator.public_ontology import field_catalog
        text = '订单号,行号,金额,日期\nO1,1,10.5,2024-01-01\nO1,2,20.25,2024-01-02\nO2,1,30.75,2024-01-03\n'
        entry = field_catalog(load_table_file('lines.csv', text.encode('utf-8')))['lines']
        self.assertEqual(entry['unique_columns'], [])
        self.assertEqual(entry['unique_pairs'], [['订单号', '行号']])

    def test_a_one_row_table_says_nothing_about_telling_rows_apart(self):
        from ontology_poc_generator.company_sources import load_table_file
        from ontology_poc_generator.public_ontology import field_catalog
        entry = field_catalog(load_table_file('one.csv', b'a,b\n1,2\n'))['one']
        self.assertNotIn('unique_columns', entry)
        self.assertNotIn('unique_pairs', entry)

    def test_a_pair_search_cut_short_keeps_the_pairs_it_found(self):
        from ontology_poc_generator import public_ontology
        from ontology_poc_generator.company_sources import load_table_file
        text = 'a,b,c,d,e\n' + '\n'.join(f'{i % 8},{i % 9},{i % 2},x{i % 3},y{i % 5}' for i in range(40)) + '\n'
        old, public_ontology.PAIR_BUDGET = public_ontology.PAIR_BUDGET, 45
        try:
            entry = public_ontology.field_catalog(load_table_file('t.csv', text.encode('utf-8')))['t']
        finally:
            public_ontology.PAIR_BUDGET = old
        self.assertEqual(entry['unique_pairs'], [['a', 'b']])

    def test_a_pair_search_cut_short_claims_no_pairs(self):
        from ontology_poc_generator import public_ontology
        from ontology_poc_generator.company_sources import load_table_file
        text = 'a,b,c,d\n' + '\n'.join(f'{i % 8},{i % 9},{i % 2},x{i % 3}' for i in range(40)) + '\n'   # only a+b tells rows apart
        old, public_ontology.PAIR_BUDGET = public_ontology.PAIR_BUDGET, 10
        try:
            entry = public_ontology.field_catalog(load_table_file('t.csv', text.encode('utf-8')))['t']
        finally:
            public_ontology.PAIR_BUDGET = old
        self.assertNotIn('unique_pairs', entry)

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


EVENT = {'object_types': [{'key': 'event', 'label': '事件', 'rationale': '一行一个事件',
                           'populated_from': [{'source': 'events', 'identity': {'id': '编号'}}],
                           'time_field': {'source': 'events', 'path': '创建时间'},
                           'attributes': [{'source': 'events', 'path': '修改时间'}]}],
         'relations': [], 'ignored_fields': []}


class TimeFieldTests(unittest.TestCase):
    """A date named as an object's time field is a use of that column, as the data check already counts it. The built
    ontology keeps it as an attribute too, so questions can still filter on it."""

    def bundle(self):
        from ontology_poc_generator.company_sources import load_table_file
        return load_table_file('events.csv', TABLES['events.csv'].encode('utf-8'))

    def test_a_time_field_counts_as_using_its_column(self):
        from ontology_poc_generator.company_ontology import verify_company_proposal
        errors = verify_company_proposal(EVENT, self.bundle())['errors']
        self.assertEqual([e for e in errors if e['code'] == 'field_unaccounted'], [])

    def test_a_list_where_a_field_name_goes_is_sent_back_not_a_crash(self):
        from ontology_poc_generator.company_ontology import verify_company_proposal
        t = EVENT['object_types'][0]
        for bad in [{**EVENT, 'object_types': [{**t, 'time_field': {'source': 'events', 'path': ['创建时间']}}]},
                    {**EVENT, 'object_types': [{**t, 'attributes': [{'source': ['events'], 'path': '创建时间'}]}]},
                    {**EVENT, 'ignored_fields': [{'source': ['events'], 'path': '创建时间', 'reason': 'x'}]}]:
            codes = {e['code'] for e in verify_company_proposal(bad, self.bundle())['errors']}
            self.assertIn('invalid_response', codes)

    def test_a_malformed_source_or_list_is_sent_back_not_a_crash(self):
        from ontology_poc_generator.company_ontology import verify_company_proposal
        t = EVENT['object_types'][0]
        for bad in [{**EVENT, 'object_types': [{**t, 'populated_from': [{**t['populated_from'][0], 'source': ['events']}]}]},
                    {**EVENT, 'object_types': [{**t, 'populated_from': [{**t['populated_from'][0], 'source': {'name': 'events'}}]}]},
                    {**EVENT, 'object_types': [{**t, 'attributes': 5}]},
                    {**EVENT, 'ignored_fields': 5}]:
            codes = {e['code'] for e in verify_company_proposal(bad, self.bundle())['errors']}
            self.assertIn('invalid_response', codes)

    def test_the_built_ontology_keeps_the_time_field_as_an_attribute(self):
        from ontology_poc_generator.company_ontology import build_company_ontology
        o = build_company_ontology(self.bundle(), FakeGateway([EVENT]))
        self.assertEqual(o['status'], 'auto_built_verified')
        self.assertIn({'source': 'events', 'path': '创建时间'}, o['object_types'][0]['attributes'])


if __name__ == '__main__':
    unittest.main()
