"""The pipeline requirements (编排需求单): what the data check, the open items, the data-meaning card, the derived measures
and the adopted rules already say about how the data has to be prepared, gathered into one document for whoever builds
the data pipeline. Code only: no model is called, and every entry says where it comes from."""
import io
import json
import unittest
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen
import zipfile

from ontology_poc_generator.derived_measures import parse_derived
from ontology_poc_generator.ontology_card import build_card
from ontology_poc_generator.ontology_eval import data_fit
from ontology_poc_generator.pipeline_spec import pipeline_files, pipeline_markdown, pipeline_spec
from ontology_poc_generator.public_ontology import build_graph
from ontology_poc_generator.rule_discovery import check_rules
from tests.test_card_server import CardModel, UPLOAD, call, mark
from tests.test_ontology_server import OntologyServerTests

AT = '2026-10-27T09:00:00+00:00'
NOW = '2026-10-27T12:00:00+00:00'
SAVED = '20261027T090000Z-0a1b2c3d.json'
COLUMNS = ('row_no', 'batch', 'vendor_uei', 'dept_code', 'project_id', 'office_code', 'paid_on', 'booked_at', 'posted',
           'paid', 'tax', 'running', 'ytd', 'balance', 'grade_no', 'fee', 'status')
LEDGER_ROWS = [   # rows 2 and 3 are one entry once case is folded; the vendor and department of some rows are in no table
    ('1', 'B1', 'V1', '00106', 'P1', 'O1', '2024-11-30', '2024-12-01 09:30:00', '2024/1/5', '100.5', '5.5', '100.5', '500', '900', '4012', '1,200', 'OPEN'),
    ('2', 'B1', 'V1', '00106', 'P1', 'O1', '2024-12-31', '2024-12-02 10:00:00', '3/4/2024', '20', '1', '120.5', '520', '880', '4012', 'n/a', 'OPEN'),
    ('2', 'b1', 'V2', '107', 'P2', 'O2', '', '2024-12-02 11:00:00', '2024年5月6日', '5', '0.5', '125.5', '525', '875', '4013', '-', 'CLOSED'),
    ('3', 'B2', 'V9', '999', 'P7', 'O1', '2024-12-15', '2024-12-01 08:00:00', '2024.7.8', '', '', '', '', '', '4013', '980.5', 'OPEN'),
    ('4', 'B2', 'V1', '999', 'P2', 'O2', '2024-12-20', '2024-12-03 08:00:00', '', '30', '2', '155.5', '550', '850', '4014', '3,000', 'OPEN'),
    ('5', 'B3', '', '107', 'P1', 'O1', '2024-12-21', '2024-12-03 09:00:00', '2024/2/9', '12', '0', '167.5', '560', '840', '4014', '', 'OPEN'),
]
BUNDLE = {
    'schema': 'company_source_bundle.v1', 'decision': '看支出', 'file': {'name': 'ledger.xlsx', 'sha256': 'a' * 64, 'kind': 'table'},
    'sources': {
        'ledger': {'records': [dict(zip(COLUMNS, row)) for row in LEDGER_ROWS], 'requests': [], 'skipped_rows': ['2026 年度支出明细', '单位：元', '制表：财务部']},
        'vendors': {'records': [{'uei': 'V1', 'name': 'Acme'}, {'uei': 'V2', 'name': 'Bolt'}, {'uei': 'v1', 'name': 'Acme Corp'}], 'requests': []},
        'depts': {'records': [{'code': '00106', 'name': '规划'}, {'code': '106', 'name': '规划发展'}, {'code': '107', 'name': '采购'}], 'requests': []},
        'projects': {'records': [{'pid': 'P1', 'title': '一期'}, {'pid': 'P2', 'title': '二期'}], 'requests': []},
        'offices': {'records': [{'code': 'O1', 'city': '北京'}, {'code': 'O2', 'city': '上海'}], 'requests': []},
    }}
ENTRY = {'key': 'entry', 'label': '支出行', 'populated_from': [{'source': 'ledger', 'identity': {'row_no': 'row_no', 'batch': 'batch'}}],
         'attributes': [{'source': 'ledger', 'path': p} for p in ('paid_on', 'booked_at', 'paid', 'tax', 'running', 'ytd', 'balance', 'fee', 'status')]}
ONTOLOGY = {
    'status': 'auto_built_verified',
    'object_types': [
        ENTRY,
        {'key': 'vendor', 'label': '供应商', 'populated_from': [{'source': 'vendors', 'identity': {'uei': 'uei'}}], 'attributes': [{'source': 'vendors', 'path': 'name'}]},
        {'key': 'dept', 'label': '部门', 'populated_from': [{'source': 'depts', 'identity': {'code': 'code'}}], 'attributes': [{'source': 'depts', 'path': 'name'}]},
        {'key': 'project', 'label': '项目', 'populated_from': [{'source': 'projects', 'identity': {'pid': 'pid'}}], 'attributes': [{'source': 'projects', 'path': 'title'}]},
        {'key': 'office', 'label': '办公室', 'populated_from': [{'source': 'offices', 'identity': {'code': 'code'}}], 'attributes': [{'source': 'offices', 'path': 'city'}]}],
    'relations': [
        {'key': 'entry_vendor', 'from': 'entry', 'to': 'vendor', 'source': 'ledger', 'to_identity': {'uei': 'vendor_uei'}},
        {'key': 'entry_dept', 'from': 'entry', 'to': 'dept', 'source': 'ledger', 'to_identity': {'code': 'dept_code'}},
        {'key': 'entry_project', 'from': 'entry', 'to': 'project', 'source': 'ledger', 'to_identity': {'pid': 'project_id'}},
        {'key': 'entry_office', 'from': 'entry', 'to': 'office', 'source': 'ledger', 'to_identity': {'code': 'office_code'}}],
    'value_aliases': [{'type': 'dept', 'source': 'depts', 'value': 'PLAN & DEV', 'target_source': 'ledger', 'target_value': 'PLANNING AND DEVELOPMENT'}],
    'ignored_fields': []}
GRAIN, ENTRY_COMPLETE = 'grain:ledger', 'complete:ledger|batch,row_no'
CONFIRMATION = {'confirmed_at': '2026-10-27T10:00:00+00:00', 'confirmed_by': '李四', 'decisions': {
    'types': {k: {'verdict': 'ok'} for k in ('entry', 'vendor', 'dept', 'project', 'office')}, 'relations': {},
    'variants': [{'type': 'vendor', 'values': ['ACME Corp', 'Acme']}]},
    'reference': {'name_variants': [{'type': 'vendor', 'values': ['ACME Corp', 'Acme']}]}}


def said(value, note='', basis='10-27 会议', by='张三', at=AT):
    return {'value': value, 'note': note, 'by': by, 'basis': basis, 'at': at}


CELLS = {
    GRAIN: said('event'), 'grain:depts': said('one_object', by='李四', basis=''),
    'amount:ledger.running': said('running'), 'amount:ledger.balance': said('latest'), 'amount:ledger.ytd': said('period_to_date'),
    'amount:ledger.paid': said('flow'), 'amount:ledger.tax': said('flow', by='李四', basis='电话', at='2026-10-28T08:00:00+00:00'),
    'amount:ledger.grade_no': said('not_amount'),
    'date:ledger.paid_on': said('business'), 'range:ledger.paid_on': said({'from': '2024-10-01', 'to': '2024-12-31'}),
    'date:ledger.booked_at': said('system'),
    ENTRY_COMPLETE: said('partial', note='只导了 Q4'), 'complete:vendors|uei': said('full')}
ITEMS = {'unlinked:entry_vendor': {'choice': 'expected', 'text': '', 'by': '王五', 'basis': '周会', 'at': '2026-10-27T11:00:00+00:00', 'asked': 'x'},
         'unlinked:entry_dept': {'choice': 'incomplete', 'text': '部门表只导了一半', 'by': '王五', 'basis': '', 'at': '2026-10-27T11:30:00+00:00', 'asked': 'x'}}
FORMULA = {**parse_derived(ONTOLOGY, {'type': 'entry', 'label': '净额', 'terms': [{'sign': 1, 'factors': [{'field': 'paid'}]},
                                                                                {'sign': -1, 'factors': [{'field': 'tax'}]}]})[0],
           'confirmed_at': '2026-10-27T10:30:00+00:00'}
RULES = [{'id': 'required:entry:paid', 'kind': 'required', 'type': 'entry', 'field': 'paid', 'holds': 5},
         {'id': 'order:entry:paid_on:booked_at', 'kind': 'order', 'type': 'entry', 'before': 'paid_on', 'after': 'booked_at', 'holds': 5},
         {'id': 'required:entry:gone', 'kind': 'required', 'type': 'entry', 'field': 'gone', 'holds': 5},
         {'id': 'required:vanished:code', 'kind': 'required', 'type': 'vanished', 'field': 'code', 'holds': 5}]
# a vendor and a project read from the ledger's own columns as well as from their tables: a vendor named only on the ledger
# is an object of the graph, but no row of the vendors table
VENDOR_TWICE = {'key': 'vendor', 'label': '供应商', 'attributes': [],
                'populated_from': [{'source': 'vendors', 'identity': {'uei': 'uei'}}, {'source': 'ledger', 'identity': {'uei': 'vendor_uei'}}]}
PROJECT_TWICE = {'key': 'project', 'label': '项目', 'attributes': [],
                 'populated_from': [{'source': 'projects', 'identity': {'pid': 'pid'}}, {'source': 'ledger', 'identity': {'pid': 'project_id'}}]}
READ_TWICE = {**ONTOLOGY, 'object_types': [ENTRY, VENDOR_TWICE, PROJECT_TWICE], 'value_aliases': [],
              'relations': [{'key': 'entry_vendor', 'from': 'entry', 'to': 'vendor', 'source': 'ledger'}]}
# orders with lines; the sku of a line is an object read from the orders and from the sku list
LINES_BUNDLE = {
    'schema': 'company_source_bundle.v1', 'decision': '看订单', 'file': {'name': 'orders.xlsx', 'sha256': 'b' * 64, 'kind': 'table'},
    'sources': {'orders': {'records': [{'order_no': 'O1', 'lines': [{'sku': 'S1'}, {'sku': 's2'}]},
                                       {'order_no': 'O2', 'lines': [{'sku': 'S1'}, {'sku': 'S9'}]},
                                       {'order_no': 'O3', 'lines': []},
                                       {'order_no': 'O4', 'lines': [{'sku': ''}]},
                                       {'order_no': 'O5', 'lines': [{'sku': 'S2'}]}], 'requests': []},
                'skus': {'records': [{'sku': 'S1'}, {'sku': 'S2'}], 'requests': []}}}
LINES_ONTOLOGY = {
    'status': 'auto_built_verified', 'value_aliases': [], 'ignored_fields': [],
    'object_types': [{'key': 'order', 'label': '订单', 'attributes': [], 'populated_from': [{'source': 'orders', 'identity': {'order_no': 'order_no'}}]},
                     {'key': 'sku', 'label': '货品', 'attributes': [],
                      'populated_from': [{'source': 'skus', 'identity': {'sku': 'sku'}}, {'source': 'orders', 'identity': {'sku': 'lines[].sku'}}]}],
    'relations': [{'key': 'order_sku', 'from': 'order', 'to': 'sku', 'source': 'orders'}]}


def make_run(ontology=ONTOLOGY, bundle=BUNDLE, confirmation=CONFIRMATION):
    return {'file': bundle['file'], 'saved_as': SAVED, 'ontology': ontology,
            'evaluation': {'data_fit': data_fit(ontology, bundle)}, **({'confirmation': confirmation} if confirmation else {})}


def make_spec(cells=CELLS, items=ITEMS, derived=(FORMULA,), rules=RULES, **over):
    run = make_run(**over)
    bundle = over.get('bundle', BUNDLE)
    graph = build_graph(run['ontology'], bundle)
    decisions = (run.get('confirmation') or {}).get('decisions')
    card = build_card(run['ontology'], bundle, cells, graph, decisions)
    checked = check_rules(run['ontology'], bundle, list(rules), graph)
    return pipeline_spec(run, bundle, graph, card, {'cells': cells, 'items': items, 'history': []}, list(derived), checked, NOW)


def entries(spec, source, kind=None):
    table = next(t for t in spec['tables'] if t['source'] == source)
    return [e for e in table['items'] if kind is None or e['kind'] == kind]


def entry(spec, source, kind, containing=''):
    [found] = [e for e in entries(spec, source, kind) if containing in e['text']]
    return found


class ShapeTests(unittest.TestCase):
    SPEC = make_spec()

    def test_the_document_names_the_run_and_every_table_with_its_rows_and_objects(self):
        spec = self.SPEC
        self.assertEqual((spec['file'], spec['saved_as'], spec['generated_at']), ('ledger.xlsx', SAVED, NOW))
        self.assertEqual([(t['source'], t['rows'], t['objects']) for t in spec['tables']],
                         [('ledger', 6, ['支出行']), ('vendors', 3, ['供应商']), ('depts', 3, ['部门']), ('projects', 2, ['项目']), ('offices', 2, ['办公室'])])
        self.assertEqual(sorted(spec), ['derived', 'file', 'generated_at', 'open', 'relations', 'rules', 'saved_as', 'tables'])
        json.dumps(spec, ensure_ascii=False)   # plain data: it is written to a file as it is

    def test_every_entry_has_the_same_few_fields_and_says_where_it_comes_from(self):
        spec = self.SPEC
        everything = [e for t in spec['tables'] for e in t['items']] + spec['relations'] + spec['derived'] + spec['rules'] + spec['open']
        for e in everything:
            with self.subTest(kind=e['kind'], text=e['text']):
                self.assertTrue(set(e) <= {'kind', 'text', 'source', 'by', 'basis', 'at', 'refs'})
                self.assertIn(e['source'], ('code', 'client', 'person'))
                self.assertTrue(e['text'])
                self.assertIsInstance(e['refs'], list)
                if e['source'] == 'code':
                    self.assertTrue(not {'by', 'basis', 'at'} & set(e))   # a fact read from the data has nobody who said it
                if e['source'] == 'client':
                    self.assertTrue({'by', 'basis', 'at'} <= set(e))

    def test_a_table_lists_its_kinds_in_the_fixed_order(self):
        order = ['title_rows', 'grain', 'dedupe', 'latest', 'period', 'sum_ok', 'not_amount', 'number_clean', 'keep_text_id', 'date_format',
                 'date_meaning', 'code_mapping', 'complete']
        kinds = [e['kind'] for e in entries(self.SPEC, 'ledger')]
        self.assertEqual(kinds, sorted(kinds, key=order.index))
        self.assertEqual(set(kinds), set(order))   # the ledger has every kind there is

    def test_no_model_is_involved_and_the_input_is_left_alone(self):
        cells, items = json.loads(json.dumps(CELLS)), json.loads(json.dumps(ITEMS))
        before = json.dumps([cells, items, BUNDLE, ONTOLOGY], sort_keys=True)
        make_spec(cells=cells, items=items)
        self.assertEqual(json.dumps([cells, items, BUNDLE, ONTOLOGY], sort_keys=True), before)


class TableEntryTests(unittest.TestCase):
    SPEC = make_spec()

    def test_title_rows_above_the_header_are_skipped_on_the_way_in(self):
        e = entry(self.SPEC, 'ledger', 'title_rows')
        self.assertEqual(e['source'], 'code')
        for said_so in ('跳过表头上方 3 行', '2026 年度支出明细', '单位：元'):
            self.assertIn(said_so, e['text'])
        self.assertNotIn('制表', e['text'])   # the first two rows are shown
        self.assertEqual(entries(self.SPEC, 'vendors', 'title_rows'), [])

    def test_the_grain_is_the_clients_answer_beside_what_the_data_says_about_its_identity_columns(self):
        e = entry(self.SPEC, 'ledger', 'grain')
        self.assertEqual((e['source'], e['by'], e['basis'], e['at'], e['refs']), ('client', '张三', '10-27 会议', AT, [GRAIN]))
        for said_so in ('一行是一次事件或一次修改', 'batch、row_no', '5 种组合', '1 组重复', '0 行'):
            self.assertIn(said_so, e['text'])

    def test_a_grain_nobody_answered_is_said_so_and_is_a_fact_from_the_data(self):
        e = entry(self.SPEC, 'projects', 'grain')
        self.assertEqual((e['source'], e['refs']), ('code', ['grain:projects']))
        self.assertIn('还没说清', e['text'])
        self.assertTrue(not {'by', 'basis', 'at'} & set(e))
        self.assertIn('2 种组合', e['text'])
        unsure = make_spec(cells={**CELLS, 'grain:projects': said('unsure')})
        self.assertIn('还没说清', entry(unsure, 'projects', 'grain')['text'])

    def test_a_row_whose_identity_columns_are_blank_is_counted(self):
        rows = [dict(zip(COLUMNS, row)) for row in LEDGER_ROWS]
        rows[4] = {**rows[4], 'batch': ''}
        bundle = {**BUNDLE, 'sources': {**BUNDLE['sources'], 'ledger': {**BUNDLE['sources']['ledger'], 'records': rows}}}
        self.assertIn('1 行的识别字段为空', entry(make_spec(bundle=bundle), 'ledger', 'grain')['text'])

    def test_repeated_identity_values_are_to_be_settled_when_the_pipeline_is_built(self):
        e = entry(self.SPEC, 'ledger', 'dedupe')
        self.assertEqual((e['source'], e['refs']), ('code', [GRAIN]))
        for said_so in ('1 组', '重复', '保留哪一行', 'B1 · 2'):
            self.assertIn(said_so, e['text'])
        self.assertEqual(len(entries(self.SPEC, 'vendors', 'dedupe')), 1)   # V1 and v1 are one vendor
        self.assertEqual([e['kind'] for e in entries(self.SPEC, 'projects')], ['grain'])

    def test_a_running_or_latest_figure_is_kept_as_the_latest_row_of_its_object_before_it_is_added_up(self):
        running, latest = entry(self.SPEC, 'ledger', 'latest', 'running'), entry(self.SPEC, 'ledger', 'latest', 'balance')
        self.assertEqual((running['source'], running['by'], running['refs']), ('client', '张三', ['amount:ledger.running', 'date:ledger.paid_on']))
        for e, says in ((running, '每次事件后的累计值'), (latest, '截至最近一次的值')):
            for said_so in (says, '最新一行', '不能跨行相加', 'paid_on'):
                self.assertIn(said_so, e['text'])
        self.assertEqual(len(entries(self.SPEC, 'ledger', 'latest')), 2)

    def test_a_latest_figure_on_a_table_with_one_row_per_object_is_added_up_across_objects(self):
        spec = make_spec(cells={**CELLS, GRAIN: said('one_object')})
        latest, running = entry(spec, 'ledger', 'latest', 'balance'), entry(spec, 'ledger', 'latest', 'running')
        for said_so in ('截至最近一次的值', '一行一个对象', '按对象直接相加'):
            self.assertIn(said_so, latest['text'])
        self.assertNotIn('保留最新一行', latest['text'])
        self.assertIn('保留最新一行', running['text'])   # a running total is still not added row by row

    def test_without_a_business_date_column_the_sort_column_is_left_open(self):
        spec = make_spec(cells={k: v for k, v in CELLS.items() if k not in ('date:ledger.paid_on',)})
        e = entry(spec, 'ledger', 'latest', 'running')
        self.assertIn('排序列待定', e['text'])
        self.assertEqual(e['refs'], ['amount:ledger.running'])
        spec = make_spec(cells={**CELLS, 'date:ledger.paid_on': said('system')})
        self.assertIn('排序列待定', entry(spec, 'ledger', 'latest', 'running')['text'])   # the system time is not a business date

    def test_a_period_to_date_figure_is_fixed_on_one_period_before_it_is_added_up(self):
        e = entry(self.SPEC, 'ledger', 'period')
        self.assertEqual((e['source'], e['refs']), ('client', ['amount:ledger.ytd', 'date:ledger.paid_on']))
        for said_so in ('ytd', '期初到期末的累计值', '固定一期', '跨期不能相加', 'paid_on'):
            self.assertIn(said_so, e['text'])

    def test_figures_said_to_be_flows_are_one_entry_that_names_them_all_and_everyone_who_said_so(self):
        e = entry(self.SPEC, 'ledger', 'sum_ok')
        for said_so in ('paid', 'tax', '直接汇总'):
            self.assertIn(said_so, e['text'])
        self.assertEqual((e['by'], e['basis'], e['at']), ('张三、李四', '10-27 会议；电话', '2026-10-28T08:00:00+00:00'))
        self.assertEqual(e['refs'], ['amount:ledger.paid', 'amount:ledger.tax'])

    def test_a_figure_that_is_a_code_is_kept_as_text_and_left_out_of_sums(self):
        e = entry(self.SPEC, 'ledger', 'not_amount')
        self.assertEqual((e['source'], e['refs']), ('client', ['amount:ledger.grade_no']))
        for said_so in ('grade_no', '编码', '文本', '不参与汇总'):
            self.assertIn(said_so, e['text'])

    def test_a_column_of_figures_with_noise_is_converted_to_numbers(self):
        e = entry(self.SPEC, 'ledger', 'number_clean')
        self.assertEqual((e['source'], e['refs']), ('code', ['amount:ledger.fee']))
        for said_so in ('fee', '转成数值', '千分位（2 个值）', "'n/a' 1 个", "'-' 1 个", '转成空'):
            self.assertIn(said_so, e['text'])

    def test_a_noisy_column_the_client_called_a_code_is_text_not_numbers(self):
        spec = make_spec(cells={**CELLS, 'amount:ledger.fee': said('not_amount')})
        self.assertEqual(entries(spec, 'ledger', 'number_clean'), [])
        self.assertEqual(len(entries(spec, 'ledger', 'not_amount')), 2)

    def test_a_column_of_ids_with_leading_zeros_is_kept_as_text(self):
        for source, column in (('ledger', 'dept_code'), ('depts', 'code')):
            e = entry(self.SPEC, source, 'keep_text_id')
            with self.subTest(source=source):
                self.assertEqual(e['source'], 'code')
                for said_so in (column, '文本', '前导 0', '00106'):
                    self.assertIn(said_so, e['text'])
        self.assertEqual(entries(self.SPEC, 'projects', 'keep_text_id'), [])

    def test_a_date_that_looks_like_a_date_but_not_in_the_iso_way_is_to_be_rewritten(self):
        [e] = entries(self.SPEC, 'ledger', 'date_format')
        self.assertEqual(e['source'], 'code')
        for said_so in ('posted', 'YYYY-MM-DD', 'YYYY/M/D', '2024/1/5', 'M/D/YYYY', '3/4/2024', 'YYYY年M月D日', '2024年5月6日', 'YYYY.M.D', '2024.7.8'):
            self.assertIn(said_so, e['text'])
        self.assertNotIn('paid_on', e['text'])   # already written that way

    def test_only_dates_in_the_written_ways_count_and_only_when_every_value_is_one(self):
        def rows_with(posted):
            rows = [{**dict(zip(COLUMNS, row)), 'posted': posted[i]} for i, row in enumerate(LEDGER_ROWS)]
            return {**BUNDLE, 'sources': {**BUNDLE['sources'], 'ledger': {**BUNDLE['sources']['ledger'], 'records': rows}}}
        good = ['2024/1/5', '3/4/2024', '2024.7.8', '2024年5月6日', '', '2024-12-31']
        self.assertEqual(len(entries(make_spec(bundle=rows_with(good)), 'ledger', 'date_format')), 1)   # ISO dates may be mixed in
        for bad in (['2024/1/5', '3/4/2024', '2024.7.8', 'soon', '', ''],     # a word
                    ['2024/1/5', '13/45/2024', '', '', '', ''],              # not a day
                    ['20240105', '20240106', '', '', '', ''],                # eight digits are not read as a date
                    ['2024-1-5', '2024-1-6', '', '', '', ''],                # a way the list does not know
                    ['2024-12-31', '2024-12-30', '', '', '', '']):           # all ISO: nothing to rewrite
            with self.subTest(posted=bad):
                self.assertEqual(entries(make_spec(bundle=rows_with(bad)), 'ledger', 'date_format'), [])

    def test_what_a_date_column_means_comes_with_the_declared_period_and_who_said_it(self):
        e = entry(self.SPEC, 'ledger', 'date_meaning', 'paid_on')
        self.assertEqual((e['source'], e['by'], e['basis'], e['at'], e['refs']), ('client', '张三', '10-27 会议', AT, ['date:ledger.paid_on', 'range:ledger.paid_on']))
        for said_so in ('业务发生的日期', '声明覆盖 2024-10-01 至 2024-12-31'):
            self.assertIn(said_so, e['text'])
        self.assertNotIn('不能当业务期次', e['text'])

    def test_the_time_of_entry_or_fetching_is_not_a_business_period(self):
        e = entry(self.SPEC, 'ledger', 'date_meaning', 'booked_at')
        for said_so in ('系统录入或修改的时间', '不能当业务期次'):
            self.assertIn(said_so, e['text'])
        spec = make_spec(cells={**CELLS, 'date:ledger.booked_at': said('fetched')})
        self.assertIn('取数的时间', entry(spec, 'ledger', 'date_meaning', 'booked_at')['text'])
        self.assertIn('不能当业务期次', entry(spec, 'ledger', 'date_meaning', 'booked_at')['text'])

    def test_a_date_column_nobody_answered_has_no_meaning_entry_and_goes_to_the_open_list(self):
        spec = make_spec(cells={k: v for k, v in CELLS.items() if 'booked_at' not in k})
        self.assertFalse([e for e in entries(spec, 'ledger', 'date_meaning') if 'booked_at' in e['text']])
        self.assertTrue([e for e in spec['open'] if 'booked_at' in e['text']])

    def test_a_declared_period_without_an_answer_to_the_date_itself_is_still_written_down(self):
        spec = make_spec(cells={k: v for k, v in CELLS.items() if k != 'date:ledger.paid_on'})
        e = entry(spec, 'ledger', 'date_meaning', 'paid_on')
        self.assertIn('声明覆盖 2024-10-01 至 2024-12-31', e['text'])
        self.assertIn('还没说清', e['text'])

    def test_an_object_only_partly_in_the_data_needs_the_rest_and_one_said_to_be_whole_is_confirmed(self):
        partial, full = entry(self.SPEC, 'ledger', 'complete'), entry(self.SPEC, 'vendors', 'complete')
        self.assertEqual((partial['source'], partial['by'], partial['refs']), ('client', '张三', [ENTRY_COMPLETE]))
        for said_so in ('支出行', '只有一部分', '补', '只导了 Q4'):
            self.assertIn(said_so, partial['text'])
        for said_so in ('供应商', '全'):
            self.assertIn(said_so, full['text'])
        self.assertNotIn('补', full['text'])
        self.assertEqual(entries(self.SPEC, 'depts', 'complete'), [])   # nobody answered

    def test_an_object_judged_wrong_leaves_nothing_behind_in_its_table(self):
        wrong = {**CONFIRMATION, 'decisions': {**CONFIRMATION['decisions'], 'types': {**CONFIRMATION['decisions']['types'], 'vendor': {'verdict': 'wrong'}}},
                 'reference': {'name_variants': []}}   # a type judged wrong cannot hold confirmed spellings
        spec = make_spec(confirmation=wrong)
        [vendors] = [t for t in spec['tables'] if t['source'] == 'vendors']
        self.assertEqual(vendors['objects'], [])
        self.assertEqual([e['kind'] for e in vendors['items']], ['grain', 'dedupe'])   # the table is still there: its rows and identity columns are
        self.assertFalse([e for e in spec['relations'] if 'vendors' in e['text']])


class CodeMappingTests(unittest.TestCase):
    SPEC = make_spec()

    def test_spellings_and_ids_that_differ_only_in_leading_zeros_are_found_by_code(self):
        e = entry(self.SPEC, 'depts', 'code_mapping', '00106')
        self.assertEqual(e['source'], 'code')
        for said_so in ('编码对照', '00106', '106', '前导 0'):
            self.assertIn(said_so, e['text'])
        spelled = entry(self.SPEC, 'ledger', 'code_mapping')   # entry 2 of batch B1 is also written b1
        self.assertEqual(spelled['source'], 'code')
        self.assertIn('b1|2', spelled['text'])
        mapping = entries(self.SPEC, 'vendors', 'code_mapping')
        self.assertEqual([m['source'] for m in mapping], ['code', 'person'])
        self.assertIn('V1', mapping[0]['text'])
        self.assertIn('v1', mapping[0]['text'])

    def test_what_a_person_confirmed_is_written_as_theirs(self):
        [person] = [e for e in entries(self.SPEC, 'vendors', 'code_mapping') if e['source'] == 'person']
        self.assertEqual((person['by'], person['at']), ('李四', '2026-10-27T10:00:00+00:00'))
        for said_so in ('ACME Corp', 'Acme', '供应商'):
            self.assertIn(said_so, person['text'])
        [alias] = [e for e in entries(self.SPEC, 'depts', 'code_mapping') if e['source'] == 'person']   # a value alias in the confirmed ontology
        for said_so in ('PLAN & DEV', 'PLANNING AND DEVELOPMENT'):
            self.assertIn(said_so, alias['text'])

    def test_before_anyone_confirmed_the_ontology_an_alias_is_only_what_code_found(self):
        spec = make_spec(confirmation=None)
        self.assertEqual([e['source'] for e in entries(spec, 'vendors', 'code_mapping')], ['code'])
        self.assertEqual([e['source'] for e in entries(spec, 'depts', 'code_mapping')], ['code'])
        self.assertIn('PLAN & DEV', entries(spec, 'depts', 'code_mapping')[0]['text'])

    def test_a_table_no_such_object_is_read_from_has_none(self):
        for source in ('projects', 'offices'):
            self.assertEqual(entries(self.SPEC, source, 'code_mapping'), [])


class RelationTests(unittest.TestCase):
    SPEC = make_spec()

    def join(self, key):
        [e] = [e for e in self.SPEC['relations'] if key in e['refs'] or f'ledger.{key}' in e['text']]
        return e

    def test_every_relation_is_one_join_with_its_columns_and_row_counts(self):
        self.assertEqual([e['kind'] for e in self.SPEC['relations']], ['join'] * 4)
        e = self.join('vendor_uei')
        for said_so in ('ledger.vendor_uei', 'vendors.uei', 'ledger 6 行', 'vendors 3 行', '连上 4 行', '2 行连不上', '1 行用来连的编号是空的'):
            self.assertIn(said_so, e['text'])

    def test_rows_that_did_not_link_and_were_said_to_be_expected_keep_the_left_side(self):
        e = self.join('vendor_uei')
        self.assertEqual((e['source'], e['by'], e['basis'], e['at'], e['refs']), ('client', '王五', '周会', '2026-10-27T11:00:00+00:00', ['unlinked:entry_vendor']))
        self.assertIn('左关联', e['text'])
        self.assertIn('保留没对上的行', e['text'])

    def test_rows_that_did_not_link_because_the_data_is_incomplete_wait_for_the_data(self):
        e = self.join('dept_code')
        self.assertEqual((e['source'], e['by']), ('client', '王五'))
        for said_so in ('先补数据', '部门表只导了一半', '2 行连不上'):
            self.assertIn(said_so, e['text'])

    def test_rows_that_did_not_link_and_nobody_said_why_are_left_open(self):
        e = self.join('project_id')
        self.assertEqual((e['source'], e['refs']), ('code', ['unlinked:entry_project']))
        self.assertTrue(not {'by', 'basis', 'at'} & set(e))
        self.assertIn('连不上的行怎么处理还没说清', e['text'])
        self.assertIn('1 行连不上', e['text'])

    def test_a_relation_that_links_every_row_has_nothing_to_settle(self):
        e = self.join('office_code')
        self.assertEqual((e['source'], e['refs']), ('code', []))
        self.assertIn('连上 6 行', e['text'])
        for left_out in ('连不上', '还没说清', '左关联', '先补数据'):
            self.assertNotIn(left_out, e['text'])

    def test_a_relation_between_two_objects_read_from_one_table_is_not_a_join(self):
        ontology = {**ONTOLOGY, 'object_types': [ENTRY, {'key': 'vendor', 'label': '供应商', 'attributes': [],
                                                          'populated_from': [{'source': 'ledger', 'identity': {'uei': 'vendor_uei'}}]}],
                    'relations': [{'key': 'entry_vendor', 'from': 'entry', 'to': 'vendor', 'source': 'ledger'}]}
        spec = make_spec(ontology=ontology, items={}, confirmation=None)
        [e] = spec['relations']
        self.assertIn('ledger.vendor_uei', e['text'])
        self.assertNotIn('ledger.vendor_uei 对 ledger.vendor_uei', e['text'])
        self.assertIn('5 行', e['text'])   # five of six rows name a vendor

    def test_a_table_that_holds_neither_end_joins_both(self):
        link = {'key': 'dept_project', 'from': 'dept', 'to': 'project', 'source': 'ledger',
                'from_identity': {'code': 'dept_code'}, 'to_identity': {'pid': 'project_id'}}
        spec = make_spec(ontology={**ONTOLOGY, 'relations': [link]}, items={}, confirmation=None)
        [e] = spec['relations']
        for said_so in ('ledger.dept_code 对 depts.code：ledger 6 行，depts 3 行，连上 4 行；2 行连不上',
                        'ledger.project_id 对 projects.pid：ledger 6 行，projects 2 行，连上 5 行；1 行连不上'):
            self.assertIn(said_so, e['text'])   # each pair has the counts of its own two tables
        self.assertNotIn('两头都连上才算', e['text'])

    def test_the_counts_are_for_the_two_tables_named_not_for_any_table_that_reads_the_object(self):
        [e] = make_spec(ontology=READ_TWICE, items={}, confirmation=None)['relations']
        for said_so in ('ledger.vendor_uei 对 vendors.uei', 'ledger 6 行', 'vendors 3 行', '连上 4 行', '2 行连不上', '1 行用来连的编号是空的'):
            self.assertIn(said_so, e['text'])
        self.assertNotIn('连上 5 行', e['text'])   # V9 is named on the ledger only: reading it there does not put it in the vendors table
        self.assertEqual((e['source'], e['refs']), ('code', ['unlinked:entry_vendor']))

    def test_an_answer_about_the_rows_that_did_not_link_goes_with_the_counts_of_the_pair(self):
        e = make_spec(ontology=READ_TWICE, confirmation=None)['relations'][0]
        self.assertEqual((e['source'], e['by'], e['refs']), ('client', '王五', ['unlinked:entry_vendor']))
        self.assertIn('2 行连不上', e['text'])
        self.assertIn('左关联', e['text'])

    def test_rows_the_pair_cannot_link_are_counted_even_when_the_data_check_found_nothing_to_ask(self):
        rows = [dict(zip(COLUMNS, row)) for row in LEDGER_ROWS]
        rows[5] = {**rows[5], 'vendor_uei': 'V1'}   # every row names a vendor, so the data check sees every row linked
        bundle = {**BUNDLE, 'sources': {**BUNDLE['sources'], 'ledger': {**BUNDLE['sources']['ledger'], 'records': rows}}}
        spec = make_spec(ontology=READ_TWICE, bundle=bundle, items={}, confirmation=None)
        [e] = spec['relations']
        self.assertIn('连上 5 行', e['text'])
        self.assertIn('1 行连不上', e['text'])
        self.assertIn('连不上的行怎么处理还没说清', e['text'])
        self.assertEqual((e['source'], e['refs']), ('code', []))   # there is no item to point at: nobody was asked
        [unasked] = [o for o in spec['open'] if 'ledger.vendor_uei' in o['text']]   # so it is among what is not settled
        self.assertIn('1 行', unasked['text'])
        self.assertIn(f'{len(spec["open"])} 条还没说清', pipeline_markdown(spec))

    def test_a_value_inside_a_list_is_read_one_per_element_and_a_row_links_when_every_value_does(self):
        [e] = make_spec(ontology=LINES_ONTOLOGY, bundle=LINES_BUNDLE, items={}, confirmation=None)['relations']
        for said_so in ('orders.lines[].sku 对 skus.sku', 'orders 5 行', 'skus 2 行', '连上 2 行', '3 行连不上', '2 行用来连的编号是空的', '每个值都对上才算连上'):
            self.assertIn(said_so, e['text'])   # O1 links (S1 and s2), O2 does not (S9), O3 has no line and O4 a blank one, O5 links

    def test_the_object_the_table_is_about_is_not_the_one_joined_whichever_way_the_relation_is_written(self):
        for ends in ({'from': 'entry', 'to': 'vendor'}, {'from': 'vendor', 'to': 'entry'}):
            with self.subTest(**ends):
                ontology = {**READ_TWICE, 'relations': [{'key': 'entry_vendor', 'source': 'ledger', **ends}]}
                [e] = make_spec(ontology=ontology, items={}, confirmation=None)['relations']
                self.assertIn('ledger.vendor_uei 对 vendors.uei', e['text'])   # the ledger is about entries: the vendor is what is joined
                self.assertNotIn('batch', e['text'])

    def test_a_table_about_a_third_object_joins_both_ends_even_when_it_reads_both(self):
        ontology = {**READ_TWICE, 'relations': [{'key': 'vendor_project', 'from': 'vendor', 'to': 'project', 'source': 'ledger'}]}
        [e] = make_spec(ontology=ontology, items={}, confirmation=None)['relations']
        for said_so in ('ledger.vendor_uei 对 vendors.uei', 'ledger.project_id 对 projects.pid'):
            self.assertIn(said_so, e['text'])

    def test_an_object_read_from_two_other_tables_links_a_row_found_in_either(self):
        bundle = {**BUNDLE, 'sources': {**BUNDLE['sources'], 'suppliers': {'records': [{'sid': 'V9'}], 'requests': []}}}
        vendor = {'key': 'vendor', 'label': '供应商', 'attributes': [],
                  'populated_from': [{'source': 'vendors', 'identity': {'uei': 'uei'}}, {'source': 'suppliers', 'identity': {'uei': 'sid'}}]}
        ontology = {**ONTOLOGY, 'object_types': [ENTRY, vendor], 'relations': [ONTOLOGY['relations'][0]], 'value_aliases': []}
        [e] = make_spec(ontology=ontology, bundle=bundle, items={}, confirmation=None)['relations']
        for said_so in ('ledger.vendor_uei 对 vendors.uei 或 suppliers.sid', 'vendors 3 行', 'suppliers 1 行', '连上 5 行；1 行连不上',
                        '1 行用来连的编号是空的'):
            self.assertIn(said_so, e['text'])

    def test_a_row_naming_an_object_its_table_leaves_out_by_a_condition_does_not_link(self):
        vendor = {'key': 'vendor', 'label': '供应商', 'attributes': [],
                  'populated_from': [{'source': 'vendors', 'identity': {'uei': 'uei'}, 'where': [{'path': 'name', 'equals': 'Acme'}]}]}
        ontology = {**ONTOLOGY, 'object_types': [ENTRY, vendor], 'relations': [ONTOLOGY['relations'][0]], 'value_aliases': []}
        [e] = make_spec(ontology=ontology, items={}, confirmation=None)['relations']
        self.assertIn('连上 3 行；3 行连不上', e['text'])   # V2 is Bolt, which the vendors table does not count as a vendor

    def test_values_split_by_commas_link_one_by_one(self):
        rows = [dict(zip(COLUMNS, row)) for row in LEDGER_ROWS]
        rows[0] = {**rows[0], 'vendor_uei': 'V1, V2'}
        bundle = {**BUNDLE, 'sources': {**BUNDLE['sources'], 'ledger': {**BUNDLE['sources']['ledger'], 'records': rows}}}
        split = {**VENDOR_TWICE, 'populated_from': [VENDOR_TWICE['populated_from'][0], {**VENDOR_TWICE['populated_from'][1], 'transform': 'split_comma'}]}
        [e] = make_spec(ontology={**READ_TWICE, 'object_types': [ENTRY, split, PROJECT_TWICE]}, bundle=bundle, items={}, confirmation=None)['relations']
        self.assertIn('连上 4 行；2 行连不上', e['text'])   # V1 and V2 are both vendors; V9 is not, and one row names none

    def test_a_value_a_person_mapped_to_another_links_as_that_one(self):
        alias = {'type': 'vendor', 'source': 'ledger', 'value': 'V9', 'target_source': 'vendors', 'target_value': 'V1'}
        ontology = {**ONTOLOGY, 'relations': [ONTOLOGY['relations'][0]], 'value_aliases': [alias]}
        [e] = make_spec(ontology=ontology, items={}, confirmation=None)['relations']
        self.assertIn('连上 5 行；1 行连不上（其中 1 行用来连的编号是空的）', e['text'])

    def test_a_row_whose_own_object_is_not_made_out_does_not_link_and_says_so(self):
        rows = [dict(zip(COLUMNS, row)) for row in LEDGER_ROWS]
        rows[0] = {**rows[0], 'row_no': ''}
        bundle = {**BUNDLE, 'sources': {**BUNDLE['sources'], 'ledger': {**BUNDLE['sources']['ledger'], 'records': rows}}}
        ontology = {**ONTOLOGY, 'relations': [ONTOLOGY['relations'][0]], 'value_aliases': []}
        [e] = make_spec(ontology=ontology, bundle=bundle, items={}, confirmation=None)['relations']
        self.assertIn('连上 3 行；3 行连不上（其中 1 行用来连的编号是空的，1 行认不出是哪一个支出行）', e['text'])
        self.assertEqual(e['refs'], ['unlinked:entry_vendor'])   # the same rows the open item counts

    def test_two_objects_as_many_in_the_table_join_the_one_read_from_another_table_whichever_way_written(self):
        bundle = {**BUNDLE, 'sources': {'ledger': {'records': [{'no': '1', 'vid': 'V1'}, {'no': '2', 'vid': 'V2'}, {'no': '3', 'vid': 'V3'}], 'requests': []},
                                        'vendors': {'records': [{'id': 'V1'}, {'id': 'V2'}], 'requests': []}}}
        entry = {'key': 'entry', 'label': '支出行', 'attributes': [], 'populated_from': [{'source': 'ledger', 'identity': {'no': 'no'}}]}
        vendor = {'key': 'vendor', 'label': '供应商', 'attributes': [],
                  'populated_from': [{'source': 'vendors', 'identity': {'id': 'id'}}, {'source': 'ledger', 'identity': {'id': 'vid'}}]}
        for ends in ({'from': 'entry', 'to': 'vendor'}, {'from': 'vendor', 'to': 'entry'}):
            with self.subTest(**ends):
                ontology = {'status': 'auto_built_verified', 'value_aliases': [], 'ignored_fields': [], 'object_types': [entry, vendor],
                            'relations': [{'key': 'entry_vendor', 'source': 'ledger', **ends}]}
                [e] = make_spec(ontology=ontology, bundle=bundle, cells={}, items={}, derived=(), rules=(), confirmation=None)['relations']
                self.assertIn('ledger.vid 对 vendors.id：ledger 3 行，vendors 2 行，连上 2 行；1 行连不上', e['text'])
                self.assertNotIn('同一张表', e['text'])

    def test_a_relation_judged_wrong_is_not_a_requirement(self):
        wrong = {**CONFIRMATION, 'decisions': {**CONFIRMATION['decisions'], 'relations': {'entry_dept': {'verdict': 'wrong'}}}}
        spec = make_spec(confirmation=wrong)
        self.assertEqual(len(spec['relations']), 3)
        self.assertFalse([e for e in spec['relations'] if 'dept_code' in e['text']])


class DerivedRuleAndOpenTests(unittest.TestCase):
    SPEC = make_spec()

    def test_a_confirmed_measure_is_a_computed_column(self):
        [e] = self.SPEC['derived']
        self.assertEqual((e['kind'], e['source'], e['at']), ('computed', 'person', '2026-10-27T10:30:00+00:00'))
        self.assertNotIn('by', e)   # the file keeps when it was confirmed, not by whom
        for said_so in ('支出行', '净额', 'paid − tax', '计算列'):
            self.assertIn(said_so, e['text'])

    def test_a_measure_over_a_column_this_version_no_longer_has_says_so(self):
        rows = [{k: v for k, v in dict(zip(COLUMNS, row)).items() if k != 'tax'} for row in LEDGER_ROWS]   # the new version of the ledger has no tax
        bundle = {**BUNDLE, 'sources': {**BUNDLE['sources'], 'ledger': {**BUNDLE['sources']['ledger'], 'records': rows}}}
        entry_ = {**ENTRY, 'attributes': [a for a in ENTRY['attributes'] if a['path'] != 'tax']}
        [e] = make_spec(ontology={**ONTOLOGY, 'object_types': [entry_, *ONTOLOGY['object_types'][1:]]}, bundle=bundle)['derived']
        for said_so in ('净额', 'paid − tax', '这一版数据里没有「tax」，编排前先核对'):
            self.assertIn(said_so, e['text'])
        self.assertEqual((e['source'], e['at']), ('person', '2026-10-27T10:30:00+00:00'))   # still what a person confirmed
        self.assertNotIn('没有', self.SPEC['derived'][0]['text'])   # nothing is said where every column is there

    def test_an_adopted_rule_is_a_check_after_the_pipeline_with_the_number_that_break_it_now(self):
        required, order, missing = self.SPEC['rules']   # the rule on an object the ontology no longer has is not a requirement
        broken = {r['id']: r['violations']['count'] for r in check_rules(ONTOLOGY, BUNDLE, RULES) if r['violations']}
        self.assertEqual(broken['required:entry:paid'], 1)   # entry 3 of batch B2 has no amount
        self.assertEqual([e['kind'] for e in self.SPEC['rules']], ['check'] * 3)
        self.assertEqual((required['source'], required['refs']), ('person', ['required:entry:paid']))
        for said_so in ('支出行', 'paid', '1 个对象不满足'):
            self.assertIn(said_so, required['text'])
        for said_so in ('paid_on', 'booked_at', f'{broken["order:entry:paid_on:booked_at"]} 个对象不满足'):
            self.assertIn(said_so, order['text'])
        self.assertIn('gone', missing['text'])
        self.assertIn('没法检查', missing['text'])

    def test_the_open_list_has_the_cells_nobody_answered_table_by_table(self):
        spec = self.SPEC
        blank = {e['text'].partition('：')[0]: e for e in spec['open'] if e['kind'] == 'card_blank'}
        self.assertEqual(list(blank), ['ledger', 'vendors', 'depts', 'projects', 'offices'])
        projects = blank['projects']
        for said_so in ('一行是什么', '项目'):
            self.assertIn(said_so, projects['text'])
        self.assertEqual(projects['refs'], ['grain:projects', 'complete:projects|pid'])
        ledger = blank['ledger']
        self.assertIn('fee', ledger['text'])   # the one figure column nobody answered
        for answered_or_not_on_the_card in ('paid_on', 'booked_at', 'posted', 'running'):
            self.assertNotIn(answered_or_not_on_the_card, ledger['text'])
        self.assertEqual(ledger['refs'], ['amount:ledger.fee'])
        self.assertTrue(all(e['source'] == 'code' and not {'by', 'basis', 'at'} & set(e) for e in spec['open']))

    def test_items_that_can_be_answered_and_are_not_are_listed_and_the_answered_ones_are_not(self):
        open_items_ = [e for e in self.SPEC['open'] if e['kind'] == 'open_item']
        refs = {r for e in open_items_ for r in e['refs']}
        self.assertIn('unlinked:entry_project', refs)
        self.assertIn('check_finding:identity_spellings', refs)
        self.assertNotIn('unlinked:entry_vendor', refs)
        self.assertNotIn('unlinked:entry_dept', refs)
        self.assertNotIn('unjudged', refs)       # settled by doing something, not by an answer
        self.assertNotIn('card_blank', refs)     # the cells are listed one table at a time
        self.assertTrue(any('没连上' in e['text'] for e in open_items_))


class MarkdownTests(unittest.TestCase):
    SPEC = make_spec()
    TEXT = pipeline_markdown(SPEC)

    def test_the_title_the_one_sentence_and_the_counts(self):
        lines = self.TEXT.splitlines()
        self.assertEqual(lines[0], '# 编排需求单：ledger.xlsx')
        self.assertIn('这份清单由 OntoPoc 按数据和客户答复生成，只描述要做什么，不执行加工', self.TEXT)
        asked = sum(len(t['items']) for t in self.SPEC['tables']) + len(self.SPEC['relations']) + len(self.SPEC['derived']) + len(self.SPEC['rules'])
        self.assertIn(f'共 5 张表，{asked} 条要求，{len(self.SPEC["open"])} 条还没说清', self.TEXT)

    def test_a_section_per_table_then_the_four_others_in_order(self):
        headings = [l for l in self.TEXT.splitlines() if l.startswith('## ')]
        self.assertEqual(headings, ['## ledger（6 行）', '## vendors（3 行）', '## depts（3 行）', '## projects（2 行）', '## offices（2 行）',
                                    '## 表之间怎么关联', '## 计算列', '## 编排后的校验', '## 还没说清的'])

    def test_each_entry_ends_with_where_it_comes_from(self):
        bullets = [l for l in self.TEXT.splitlines() if l.startswith('- ')]
        title = next(l for l in bullets if '跳过表头上方' in l)
        self.assertTrue(title.endswith('（代码查出）'), title)
        grain = next(l for l in bullets if l.startswith('- 一行是什么：一行是一次事件'))
        self.assertTrue(grain.endswith('（客户答复：张三，10-27 会议，10-27）'), grain)
        no_basis = next(l for l in bullets if '一行就是一个对象' in l)
        self.assertTrue(no_basis.endswith('（客户答复：李四，10-27）'), no_basis)   # no basis: no empty slot between the commas
        person = next(l for l in bullets if 'ACME Corp' in l)
        self.assertTrue(person.endswith('（人确认：李四）'), person)
        rule = next(l for l in bullets if '编排后检查' in l and 'paid' in l)
        self.assertTrue(rule.endswith('（人确认）'), rule)   # nobody is named for a rule or a formula

    def test_sections_without_content_are_left_out(self):
        bare = {'file': 'a.csv', 'saved_as': SAVED, 'generated_at': NOW, 'relations': [], 'derived': [], 'rules': [], 'open': [],
                'tables': [{'source': 't', 'rows': 1234, 'objects': [], 'items': [{'kind': 'grain', 'text': '一行是什么：还没说清', 'source': 'code', 'refs': ['grain:t']}]}]}
        text = pipeline_markdown(bare)
        self.assertEqual([l for l in text.splitlines() if l.startswith('## ')], ['## t（1,234 行）'])
        self.assertIn('共 1 张表，1 条要求，0 条还没说清', text)
        some = {**bare, 'rules': [{'kind': 'check', 'text': '编排后检查甲', 'source': 'person', 'refs': ['r']}]}
        self.assertEqual([l for l in pipeline_markdown(some).splitlines() if l.startswith('## ')], ['## t（1,234 行）', '## 编排后的校验'])

    def test_the_files_are_the_markdown_and_the_json_of_the_same_document(self):
        files = pipeline_files(self.SPEC)
        self.assertEqual(sorted(files), ['编排需求单.json', '编排需求单.md'])
        self.assertEqual(files['编排需求单.md'], self.TEXT)
        self.assertEqual(json.loads(files['编排需求单.json']), self.SPEC)


class ExportRouteTests(unittest.TestCase):
    def fetch(self, base, path):
        try:
            with urlopen(base + path, timeout=30) as response:
                return response.status, response.headers, response.read()
        except HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def test_a_kept_table_run_downloads_as_a_zip_with_the_document_in_both_forms(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            mark(base, run, 'grain:orders', 'event', basis='10-27 会议')
            status, headers, body = self.fetch(base, f"/api/ontology/runs/{run['saved_as']}/export/pipeline")
            self.assertEqual((status, headers['Content-Type']), (200, 'application/zip'))
            self.assertIn("filename*=UTF-8''", headers['Content-Disposition'])
            self.assertIn(quote('编排需求单'), headers['Content-Disposition'])
            z = zipfile.ZipFile(io.BytesIO(body))
            self.assertEqual(sorted(z.namelist()), ['编排需求单.json', '编排需求单.md'])
            spec = json.loads(z.read('编排需求单.json'))
            self.assertEqual((spec['file'], spec['saved_as'], [t['source'] for t in spec['tables']]), ('orders.csv', run['saved_as'], ['orders']))
            grain = next(e for e in spec['tables'][0]['items'] if e['kind'] == 'grain')
            self.assertEqual((grain['source'], grain['by'], grain['basis']), ('client', '张三', '10-27 会议'))   # what was saved on the card is in it
            self.assertTrue(spec['generated_at'])
            self.assertIn('# 编排需求单：orders.csv', z.read('编排需求单.md').decode('utf-8'))
            self.assertEqual(len(spec['relations']), 1)   # the order without a customer is a row that does not link

    def test_the_files_can_also_be_asked_for_as_json(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            status, _, body = self.fetch(base, f"/api/ontology/runs/{run['saved_as']}/export/pipeline?format=json")
            self.assertEqual(status, 200)
            self.assertEqual(sorted(json.loads(body)['files']), ['编排需求单.json', '编排需求单.md'])

    def test_a_document_or_an_ontology_that_did_not_pass_has_no_requirements_and_the_reason_is_said(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            path = out / run['saved_as']
            saved = json.loads(path.read_text(encoding='utf-8'))
            for change, reason in (({'file': {**saved['file'], 'kind': 'document'}}, '文档'),
                                   ({'ontology': {**saved['ontology'], 'status': 'rejected'}}, '核验')):
                with self.subTest(reason=reason):
                    path.write_text(json.dumps({**saved, **change}, ensure_ascii=False), encoding='utf-8')
                    status, _, body = self.fetch(base, f"/api/ontology/runs/{run['saved_as']}/export/pipeline")
                    self.assertEqual(status, 400)
                    self.assertIn(reason, json.loads(body)['error'])

    def test_a_run_that_did_not_pass_is_refused_even_when_its_proposal_names_a_table_the_data_does_not_have(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            path = out / run['saved_as']
            saved = json.loads(path.read_text(encoding='utf-8'))
            invented = json.loads(json.dumps(saved))
            invented['ontology']['status'] = 'blocked'
            invented['ontology']['object_types'][0]['populated_from'][0]['source'] = 'no_such_table'
            path.write_text(json.dumps(invented, ensure_ascii=False), encoding='utf-8')
            status, _, body = self.fetch(base, f"/api/ontology/runs/{run['saved_as']}/export/pipeline")
            self.assertEqual(status, 400)
            self.assertIn('核验', json.loads(body)['error'])

    def test_an_unknown_run_is_not_found(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            for name in ('20260101T000000Z-deadbeef.json', 'not-a-run.json'):
                with self.subTest(name=name):
                    status, _, body = self.fetch(base, f'/api/ontology/runs/{name}/export/pipeline')
                    self.assertEqual(status, 404)
                    self.assertIn('找不到这次运行', json.loads(body)['error'])


if __name__ == '__main__':
    unittest.main()
