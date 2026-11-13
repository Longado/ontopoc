"""Confirmed definitions become named SQL views over the stored tables of a run: a label column for a confirmed code, a
"current" view for a repeated-key rule, and the views a person names (a row filter, the latest row per key).

The expected numbers were counted from the xlsx files in tests/fixtures/planted by a separate script, not from the code
under test: 144 of 160 orders are not cancelled, the latest stock snapshot of the 12 products adds up to 1,115, and the
latest commitment of 60 orders adds up to 552."""
import json
import unittest

from ontology_poc_generator.named_views import compile_views, compiled_views, drop_views_except, read_views, save_definition, sql_name, sync_views, view_names, views_of_run
from ontology_poc_generator.pipelines import workspace_datasets
from ontology_poc_generator.repeated_keys import latest_row
from ontology_poc_generator.workspace_store import element_contents, import_records, open_workspace, records_sha256, set_element_states
from tests.test_workspace_store import PLANTED_DRAFT, planted_bundle

KEY = 'abcdef0123456789'   # what the definitions are kept under (the file's key)
RUN = 'run00001'            # the run the views belong to
NO_TYPES = {'object_types': [], 'relations': []}
CODES = {'values': [{'value': '0', 'label': '进行中', 'description': ''}, {'value': '1', 'label': '已交付', 'description': ''},
                    {'value': '2', 'label': '已取消', 'description': ''}]}


class ViewsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = planted_bundle()

    def setUp(self):
        self.conn = open_workspace(':memory:')
        self.addCleanup(self.conn.close)
        ids = {n: import_records(self.conn, n, s['records'], 'planted', records_sha256(s['records']))['id'] for n, s in self.bundle['sources'].items()}
        self.tables = workspace_datasets(self.conn, ids)

    def confirm(self, element, content, signer='小林'):
        set_element_states(self.conn, [(f'{element}', 'confirmed', None, signer, content)])

    def views(self):
        return {v['name']: v for v in views_of_run(self.conn, KEY, RUN, PLANTED_DRAFT, self.tables)}

    def synced(self):
        """The views as the file holds them: what a definition change writes."""
        sync_views(self.conn, RUN, compiled_views(self.conn, KEY, RUN, PLANTED_DRAFT, self.tables))
        return {n for (n,) in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'")}

    def count(self, name, where='1'):
        return self.conn.execute(f'SELECT COUNT(*) FROM "{sql_name(RUN, name)}" WHERE {where}').fetchone()[0]

    def define(self, **posted):
        return save_definition(self.conn, KEY, posted, self.tables, PLANTED_DRAFT, '小林')


class NothingConfirmedTests(ViewsTestCase):
    def test_no_confirmed_definition_means_no_view(self):
        self.assertEqual(self.views(), {})
        self.assertEqual(self.synced(), set())


class LabelViewTests(ViewsTestCase):
    def setUp(self):
        super().setUp()
        self.confirm(f'property:{KEY}:订单.状态码', CODES)

    def test_a_confirmed_code_adds_a_label_column_and_keeps_every_row(self):
        view = self.views()['订单']
        self.assertEqual((view['state'], view['rows'], view['confirmed_by']), ('confirmed', 160, '小林'))
        self.assertIn('状态码_含义', view['sql'])
        self.assertEqual(self.count('订单', '"状态码_含义" = \'已取消\''), 16)
        self.assertEqual(self.count('订单', '"状态码" = \'2\''), 16)

    def test_a_code_nobody_confirmed_reads_as_unconfirmed_in_the_label_column(self):
        self.confirm(f'property:{KEY}:订单.状态码', {'values': CODES['values'][:2]})
        self.assertEqual(self.views()['订单']['rows'], 160)
        self.assertEqual(self.count('订单', '"状态码_含义" = \'（含义未确认）\''), 16)

    def test_taking_the_meaning_back_drops_the_view_from_the_file(self):
        self.assertEqual(self.synced(), {sql_name(RUN, '订单')})
        set_element_states(self.conn, [(f'property:{KEY}:订单.状态码', 'proposed', None, None)])
        self.assertEqual(self.views(), {})
        self.assertEqual(self.synced(), set())


class NamedFilterTests(ViewsTestCase):
    def setUp(self):
        super().setUp()
        self.confirm(f'property:{KEY}:订单.状态码', CODES)

    def test_valid_orders_are_the_144_that_are_not_cancelled(self):
        self.define(name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消')
        view = self.views()['有效订单']
        self.assertEqual((view['state'], view['rows'], view['confirmed_by']), ('confirmed', 144, '小林'))
        self.assertEqual(self.count('有效订单', '"状态码" = \'2\''), 0)

    def test_a_filter_follows_the_meaning_it_was_built_on(self):
        self.define(name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消')
        self.confirm(f'property:{KEY}:订单.状态码', {'values': CODES['values'][:2]})
        view = self.views()['有效订单']
        self.assertEqual(view['state'], 'unavailable')
        self.assertIn('已取消', view['why'])
        self.assertNotIn(sql_name(RUN, '有效订单'), self.synced())
        self.confirm(f'property:{KEY}:订单.状态码', CODES)
        self.assertEqual(self.views()['有效订单']['rows'], 144)   # confirming the meaning again brings it back

    def test_a_filter_needs_a_confirmed_meaning(self):
        for what, posted in (('没有已确认的含义', dict(column='客户编号', label='x')), ('不是', dict(column='状态码', label='已退货'))):
            with self.assertRaises(ValueError, msg=what) as caught:
                self.define(name='坏的', kind='filter', base='订单', op='is', **posted)
            self.assertIn(what, str(caught.exception))

    def test_a_name_is_a_name(self):
        for name in ('', '订单', '库存快照_当前', 'x' * 31, 'a"b'):
            with self.assertRaises(ValueError, msg=name):
                self.define(name=name, kind='filter', base='订单', column='状态码', op='is', label='已取消')

    def test_a_view_can_be_defined_again_and_taken_back(self):
        self.define(name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消')
        self.define(name='有效订单', kind='filter', base='订单', column='状态码', op='is', label='已取消')
        self.assertEqual(self.views()['有效订单']['rows'], 16)
        self.assertEqual(self.define(name='有效订单', remove=True), '视图「有效订单」已收回')
        self.assertNotIn('有效订单', self.views())
        with self.assertRaises(ValueError):
            self.define(name='有效订单', remove=True)


class LatestRowTests(ViewsTestCase):
    def test_the_latest_stock_snapshot_per_product_adds_up_to_1115(self):
        self.define(name='最新快照', kind='latest', base='库存快照', key=['产品编号'], order='快照月份')
        view = self.views()['最新快照']
        self.assertEqual((view['state'], view['rows']), ('confirmed', 12))
        self.assertEqual(self.conn.execute(f'SELECT SUM(CAST("库存数量" AS INTEGER)), COUNT(DISTINCT "快照月份"), MIN("快照月份") FROM "{view["sql_name"]}"').fetchone(),
                         (1115, 1, '2026-06'))

    def test_the_latest_commitment_per_order_is_60_orders_and_552_pieces(self):
        self.define(name='最新承诺', kind='latest', base='订单承诺', key=['订单号'], order='承诺版本')
        view = self.views()['最新承诺']
        self.assertEqual(view['rows'], 60)
        self.assertEqual(self.conn.execute(f'SELECT SUM(CAST("承诺数量" AS INTEGER)) FROM "{view["sql_name"]}"').fetchone()[0], 552)

    def test_the_view_keeps_the_rows_the_python_rule_keeps(self):
        self.define(name='最新承诺', kind='latest', base='订单承诺', key=['订单号'], order='承诺版本')
        records = self.bundle['sources']['订单承诺']['records']
        by_order = {}
        for i, r in enumerate(records):
            by_order.setdefault(r['订单号'], []).append(i)
        kept = {latest_row(records, rows, '承诺版本') + 1 for rows in by_order.values()}   # rowid counts from 1
        self.views()
        in_view = {r[0] for r in self.conn.execute(f'SELECT "_行号" FROM "{sql_name(RUN, "最新承诺")}"')}
        self.assertEqual(in_view, kept)

    def test_a_repeated_key_rule_gives_a_current_view(self):
        self.confirm(f'repeat_rule:{KEY}:product.库存快照', {'rule': 'keep_latest', 'column': '快照月份', 'covers': []})
        view = self.views()['库存快照_当前']
        self.assertEqual((view['state'], view['rows']), ('confirmed', 12))
        self.assertIn('快照月份', view['from'])

    def test_the_other_rules_make_no_view(self):
        for rule in ({'rule': 'keep_both', 'covers': []}, {'rule': 'data_error', 'covers': []}):
            self.confirm(f'repeat_rule:{KEY}:product.库存快照', rule)
            self.assertEqual(self.views(), {})

    def test_a_column_that_cannot_be_ordered_in_sql_is_refused_in_words(self):
        with self.assertRaises(ValueError) as caught:
            self.define(name='坏的', kind='latest', base='订单', key=['订单号'], order='产品编号')
        self.assertIn('排不出先后', str(caught.exception))
        for posted in (dict(key=[], order='数量'), dict(key=['没有'], order='数量'), dict(key=['订单号'], order='订单号'), dict(key=['订单号', '订单号'], order='数量')):
            with self.assertRaises(ValueError, msg=posted):
                self.define(name='坏的', kind='latest', base='订单', **posted)


class SmallTableTests(unittest.TestCase):
    """Ordering, ties and blanks on a table small enough to see."""
    def setUp(self):
        self.conn = open_workspace(':memory:')
        self.addCleanup(self.conn.close)
        rows = [{'编号': 'A', '版本': '9', '值': 'a9'}, {'编号': 'A', '版本': '10', '值': 'a10'}, {'编号': 'B', '版本': '2', '值': 'b2-first'},
                {'编号': 'B', '版本': '2', '值': 'b2-second'}, {'编号': 'C', '版本': None, '值': 'c-blank'}, {'编号': 'C', '版本': '1', '值': 'c1'},
                {'编号': None, '版本': '1', '值': 'no-key-1'}, {'编号': None, '版本': '1', '值': 'no-key-2'}]
        ids = {'表': import_records(self.conn, '表', rows, 't', records_sha256(rows))['id']}
        self.tables = workspace_datasets(self.conn, ids)

    def latest(self):
        save_definition(self.conn, KEY, dict(name='最新', kind='latest', base='表', key=['编号'], order='版本'), self.tables, NO_TYPES, None)
        views_of_run(self.conn, KEY, RUN, NO_TYPES, self.tables)
        return {r[0] for r in self.conn.execute(f'SELECT "值" FROM "{sql_name(RUN, "最新")}"')}

    def test_numbers_are_ordered_as_numbers_a_tie_goes_to_the_later_row_a_blank_is_oldest_and_rows_without_a_key_stay(self):
        self.assertEqual(self.latest(), {'a10', 'b2-second', 'c1', 'no-key-1', 'no-key-2'})


class RowAliasTests(unittest.TestCase):
    def test_a_table_with_a_column_called_like_the_row_position_still_breaks_ties_by_position(self):
        conn = open_workspace(':memory:')
        self.addCleanup(conn.close)
        rows = [{'编号': 'A', '版本': '1', '_行号': 'zzz', '值': 'first'}, {'编号': 'A', '版本': '1', '_行号': 'aaa', '值': 'second'}]   # a tie, and a column that sorts the other way round
        tables = workspace_datasets(conn, {'表': import_records(conn, '表', rows, 't', records_sha256(rows))['id']})
        save_definition(conn, KEY, dict(name='最新', kind='latest', base='表', key=['编号'], order='版本'), tables, NO_TYPES, None)
        views = {v['name']: v for v in views_of_run(conn, KEY, RUN, NO_TYPES, tables)}
        self.assertEqual({r[0] for r in conn.execute(f'SELECT "值" FROM "{views["最新"]["sql_name"]}"')}, {'second'})   # the later row wins, as in the rule for repeated keys
        self.assertIn('_行号', [c['name'] for c in views['最新']['columns']])            # the user's own column is still theirs
        self.assertNotEqual(views['最新']['row_alias'], '_行号')


class SyncTests(ViewsTestCase):
    def test_a_new_version_of_the_table_is_read_after_the_next_sync_and_two_files_do_not_meet(self):
        self.confirm(f'property:{KEY}:订单.状态码', CODES)
        self.assertEqual(self.views()['订单']['rows'], 160)
        rows = self.bundle['sources']['订单']['records'][:10]
        new = import_records(self.conn, '订单', rows, 'again', records_sha256(rows))['id']
        self.tables = {**self.tables, **workspace_datasets(self.conn, {'订单': new})}
        self.assertEqual(self.views()['订单']['rows'], 10)
        other = 'ffffffff00000000'
        compiled = compile_views(other, PLANTED_DRAFT, self.tables, {'订单.状态码': {**CODES, 'confirmed_by': None, 'confirmed_at': None}}, {}, {})
        self.assertNotEqual(compiled[0]['sql_name'], sql_name(RUN, '订单'))


class ConfirmedContentTests(ViewsTestCase):
    def test_what_a_person_defined_is_kept_with_the_person(self):
        self.confirm(f'property:{KEY}:订单.状态码', CODES)
        self.define(name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消')
        kept = element_contents(self.conn, f'view:{KEY}:')['有效订单']
        self.assertEqual((kept['confirmed_by'], kept['label'], kept['op']), ('小林', '已取消', 'is_not'))


class ServerViewsTests(unittest.TestCase):
    """A person confirms what 2 means, names 有效订单 and 最新快照 in the page's requests, and the open-items answer lists the views
    with their SQL and rows."""
    def setUp(self):
        from tests.test_ontology_ask_server import call
        from tests.test_ontology_server import OntologyServerTests
        from tests.test_workspace_store import PlantedDraftModel, ServerDataChecksTests
        server = OntologyServerTests().server(gateway=PlantedDraftModel())
        self.base, self.out = server.__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        self.call = call
        status, self.run = call(self.base, '/api/ontology/build', {'files': ServerDataChecksTests.files})
        self.assertEqual(status, 200, self.run)

    def post(self, path, **body):
        return self.call(self.base, path, {'saved_as': self.run['saved_as'], **body})

    def listed(self):
        from urllib.request import urlopen
        with urlopen(self.base + f"/api/ontology/runs/{self.run['saved_as']}/open-items", timeout=30) as response:
            return {v['name']: v for v in json.load(response)['views']}

    def test_the_views_follow_what_a_person_confirms(self):
        self.assertEqual(self.listed(), {})
        status, body = self.post('/api/ontology/code-meanings', id='code_meaning:订单.状态码', values=[{'value': '2', 'label': '已取消'}], confirmed_by='王工')
        self.assertEqual(status, 200, body)
        self.assertEqual({v['name']: (v['rows'], v['state']) for v in body['views']}, {'订单': (160, 'confirmed')})
        status, body = self.post('/api/ontology/views', name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消', confirmed_by='王工')
        self.assertEqual((status, body['message']), (200, '视图「有效订单」已确认'), body)
        status, body = self.post('/api/ontology/views', name='最新快照', kind='latest', base='库存快照', key=['产品编号'], order='快照月份')
        self.assertEqual(status, 200, body)
        views = {v['name']: v for v in body['views']}
        self.assertEqual({n: v['rows'] for n, v in views.items()}, {'订单': 160, '有效订单': 144, '最新快照': 12})
        self.assertEqual((views['有效订单']['confirmed_by'], views['有效订单']['sql'].startswith('SELECT')), ('王工', True))
        self.assertEqual(self.listed()['有效订单']['rows'], 144)

    def test_what_cannot_be_kept_is_refused_in_words(self):
        status, body = self.post('/api/ontology/views', name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消')
        self.assertEqual(status, 400)
        self.assertIn('还没有已确认的含义', body['error'])
        self.assertEqual(self.post('/api/ontology/views', name='x', kind='latest', base='没有这张表', key=['a'], order='b')[0], 400)
        self.assertEqual(self.post('/api/ontology/views', name='有效订单', remove=True)[0], 400)
        self.assertEqual(self.post('/api/ontology/views', name={'a': 1}, kind='latest')[0], 400)
        self.assertEqual(self.call(self.base, '/api/ontology/views', {'saved_as': '20260101T000000Z-deadbeef.json'})[0], 404)


class NamesAndScopeTests(ViewsTestCase):
    def setUp(self):
        super().setUp()
        self.confirm(f'property:{KEY}:订单.状态码', CODES)

    def test_names_that_differ_only_in_case_are_the_same_name(self):
        self.define(name='ab', kind='filter', base='订单', column='状态码', op='is', label='已取消')
        with self.assertRaises(ValueError) as caught:
            self.define(name='AB', kind='filter', base='订单', column='状态码', op='is', label='已取消')
        self.assertIn('不分大小写', str(caught.exception))
        with self.assertRaises(ValueError):
            self.define(name='库存快照_当前', kind='filter', base='订单', column='状态码', op='is', label='已取消')   # the name a keep-latest rule gives its view
        self.define(name='ab', kind='filter', base='订单', column='状态码', op='is_not', label='已取消')   # the same name again is a new definition

    def test_one_bad_definition_is_one_unavailable_row_with_a_way_to_take_it_back_and_the_others_go_on(self):
        content = {'kind': 'filter', 'base': '订单', 'column': '状态码', 'op': 'is', 'label': '已取消'}
        for name in ('ab', 'AB'):   # both kept before the check was case-blind
            self.confirm(f'view:{KEY}:{name}', content)
        self.confirm(f'view:{KEY}:坏', {'kind': 'latest', 'base': '订单'})   # a definition missing its columns
        views = self.views()
        self.assertEqual({n: v['state'] for n, v in views.items()}, {'订单': 'confirmed', 'AB': 'confirmed', 'ab': 'unavailable', '坏': 'unavailable'})
        self.assertIn('不分大小写', views['ab']['why'])
        self.assertTrue(all(views[n]['definition'] for n in ('ab', '坏')))           # a definition: the page offers 收回
        self.assertEqual(self.synced(), {sql_name(RUN, '订单'), sql_name(RUN, 'AB')})   # the file never sees the clash
        self.assertEqual(self.define(name='ab', remove=True), '视图「ab」已收回')

    def test_a_view_the_database_refuses_is_named_and_the_others_are_still_made(self):
        self.define(name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消')
        views = compiled_views(self.conn, KEY, RUN, PLANTED_DRAFT, self.tables)
        self.conn.execute(f'CREATE TABLE "{sql_name(RUN, "订单")}" (x)')        # a table in the way of the first view's name
        refused = sync_views(self.conn, RUN, views)
        self.assertEqual(list(refused), [sql_name(RUN, '订单')])
        self.assertIn(sql_name(RUN, '有效订单'), {n for (n,) in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'")})

    def test_views_belong_to_their_run_so_an_older_run_does_not_change_what_a_newer_one_reads(self):
        rows = self.bundle['sources']['订单']['records'][:10]
        new = import_records(self.conn, '订单', rows, 'again', records_sha256(rows))['id']
        newer = {**self.tables, **workspace_datasets(self.conn, {'订单': new})}
        count = lambda run, tables: {v['name']: v['rows'] for v in views_of_run(self.conn, KEY, run, PLANTED_DRAFT, tables)}['订单']
        for run, tables in (('run00001', self.tables), ('run00002', newer)):
            sync_views(self.conn, run, compiled_views(self.conn, KEY, run, PLANTED_DRAFT, tables))
        self.assertEqual((count('run00001', self.tables), count('run00002', newer), count('run00001', self.tables)), (160, 10, 160))
        file_rows = lambda run: self.conn.execute(f'SELECT COUNT(*) FROM "{sql_name(run, "订单")}"').fetchone()[0]
        self.assertEqual((file_rows('run00001'), file_rows('run00002')), (160, 10))

    def test_listing_views_writes_nothing_to_the_file_and_a_run_that_is_gone_loses_its_views(self):
        import sqlite3
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'w.sqlite'
            conn = open_workspace(path)
            ids = {n: import_records(conn, n, s['records'], 't', records_sha256(s['records']))['id'] for n, s in self.bundle['sources'].items()}
            tables = workspace_datasets(conn, ids)
            set_element_states(conn, [(f'property:{KEY}:订单.状态码', 'confirmed', None, '王工', CODES)])
            reader = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
            listed = {v['name']: v['rows'] for v in views_of_run(reader, KEY, RUN, PLANTED_DRAFT, tables)}
            self.assertEqual(listed, {'订单': 160})      # read on a connection that cannot write
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'view'").fetchone()[0], 0)
            reader.close()
            sync_views(conn, RUN, compiled_views(conn, KEY, RUN, PLANTED_DRAFT, tables))
            sync_views(conn, 'run00002', compiled_views(conn, KEY, 'run00002', PLANTED_DRAFT, tables))
            self.assertEqual(drop_views_except(conn, {RUN}), 1)
            self.assertEqual({n for (n,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'")}, {sql_name(RUN, '订单')})
            conn.close()

    def test_the_name_a_person_gave_becomes_the_stored_name_in_one_place(self):
        self.define(name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消')
        names = view_names(views_of_run(self.conn, KEY, RUN, PLANTED_DRAFT, self.tables))
        self.assertEqual(names, {'订单': sql_name(RUN, '订单'), '有效订单': sql_name(RUN, '有效订单')})


class StockQuestionModel:
    """The planted draft, and a question about the stock held: the sum of 库存数量 over every product."""
    def __init__(self):
        from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
        self.questions = QUESTION_SYSTEM_PROMPT

    def complete_json(self, *, system_prompt, user_prompt):
        from ontology_poc_generator.recognition import ModelCompletion
        reply = ({'questions': [{'question': '现在库存一共多少？', 'reasoning': 'r',
                                 'query': {'start': 'product', 'measure': {'field': '库存快照.库存数量', 'op': 'sum'}, 'group_by': None}}]}
                 if system_prompt == self.questions else PLANTED_DRAFT)
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(reply, ensure_ascii=False))


class AnswersReadViewsServerTests(unittest.TestCase):
    """The stock question is answered from the rows of 库存快照_当前 once a person has chosen "only the latest by 快照月份", and the
    answer says so; a pipeline reads views as inputs through the same service."""
    def setUp(self):
        from tests.test_ontology_ask_server import call
        from tests.test_ontology_server import OntologyServerTests
        from tests.test_workspace_store import ServerDataChecksTests
        server = OntologyServerTests().server(gateway=StockQuestionModel())
        self.base, self.out = server.__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        self.call = call
        status, self.run = call(self.base, '/api/ontology/build', {'files': ServerDataChecksTests.files, 'purpose': '现在库存一共多少？'})
        self.assertEqual(status, 200, self.run)

    def saved(self):
        from urllib.request import urlopen
        with urlopen(self.base + f"/api/ontology/runs/{self.run['saved_as']}", timeout=30) as response:
            return json.load(response)

    def post(self, path, **body):
        return self.call(self.base, path, {'saved_as': self.run['saved_as'], **body})

    def choose_latest(self):
        status, body = self.post('/api/ontology/repeat-rules', id='repeated_key:product.库存快照', rule='keep_latest', column='快照月份', confirmed_by='王工')
        self.assertEqual(status, 200, body)
        return body

    def test_the_answer_reads_the_view_and_names_it(self):
        [before] = self.saved()['evaluation']['asked'][0]['items']
        self.assertNotIn('views', before.get('evidence', {}))                     # no rule yet: the table's rows, no view
        body = self.choose_latest()
        self.assertEqual({v['name']: v['rows'] for v in body['views']}, {'库存快照_当前': 12})
        [after] = self.saved()['evaluation']['asked'][0]['items']
        self.assertEqual((after['status'], after['answer']['measure']['value'], after['answer']['measure']['counted']), ('answered', 1115, 12))
        self.assertEqual([{k: v for k, v in x.items() if k != 'from'} for x in after['evidence']['views']], [{'name': '库存快照_当前', 'kind': 'current', 'source': '库存快照', 'rows': 12}])
        self.assertIn('快照月份', after['evidence']['views'][0]['from'])

    def test_a_question_asked_later_is_answered_from_the_view_too(self):
        self.choose_latest()
        status, run = self.post('/api/ontology/ask', question='现在库存一共多少？')
        self.assertEqual(status, 200, run)
        [item] = run['evaluation']['asked'][-1]['items']
        self.assertEqual((item['answer']['measure']['value'], [v['name'] for v in item['evidence']['views']]), (1115, ['库存快照_当前']))

    def test_a_question_about_other_tables_does_not_name_the_view(self):
        from ontology_poc_generator.named_views import name_views
        self.choose_latest()
        read = [{'name': '库存快照_当前', 'kind': 'current', 'source': '库存快照', 'rows': 12, 'from': 'x'}]
        asked = lambda start: name_views({'status': 'answered'}, {'start': start}, PLANTED_DRAFT, read, None)
        self.assertEqual(asked('ticket'), {'status': 'answered'})
        self.assertEqual([v['name'] for v in asked('product')['evidence']['views']], ['库存快照_当前'])

    def test_a_pipeline_reads_a_view_as_an_input(self):
        self.post('/api/ontology/code-meanings', id='code_meaning:订单.状态码', values=[{'value': '2', 'label': '已取消'}], confirmed_by='王工')
        self.post('/api/ontology/views', name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消')
        spec = {'steps': [{'id': 'v', 'type': 'input', 'view': '有效订单'}, {'id': 't', 'type': 'input', 'dataset': '售后工单'},
                          {'id': 'j', 'type': 'join', 'left': 'v', 'right': 't', 'how': 'left', 'on': [{'left': '订单号', 'right': '订单号'}]}]}
        status, body = self.post('/api/ontology/pipelines/run', pipeline=spec)
        self.assertEqual(status, 200, body)
        nodes = {n['id']: n for n in body['nodes']}
        self.assertEqual((nodes['v']['rows_out'], nodes['v']['reads'], nodes['t']['reads']), (144, '视图 有效订单', '表 售后工单'))
        self.assertNotIn('_行号', nodes['v']['columns'])
        self.assertEqual(body['row_cap'], 1000000)
        status, body = self.post('/api/ontology/pipelines/run', pipeline={'steps': [{'id': 'v', 'type': 'input', 'view': '没有这个'}]})
        self.assertEqual(status, 400)
        self.assertIn('没有这个视图', body['error'])

    def test_a_step_that_is_not_text_is_a_400_not_a_dropped_connection(self):
        for steps in ([{'id': 'a', 'type': 'input', 'dataset': []}], [{'id': 'a', 'type': 'input', 'dataset': '订单'}, {'id': 'j', 'type': 'join', 'left': [], 'right': 'a', 'how': 'left', 'on': [{'left': 'x', 'right': 'x'}]}]):
            self.assertEqual(self.post('/api/ontology/pipelines/run', pipeline={'steps': steps})[0], 400)

    def test_listing_the_views_does_not_write_to_the_file_and_the_row_cap_is_on_the_reply(self):
        import sqlite3
        from ontology_poc_generator.workspace_store import open_workspace, set_element_states
        from urllib.request import urlopen
        conn = open_workspace(self.out / 'workspace.sqlite')
        key = self.saved()['file']['sha256']
        set_element_states(conn, [(f'property:{key}:订单.状态码', 'confirmed', None, '王工', CODES)])   # written behind the service's back: no sync happened
        in_file = lambda: conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'view'").fetchone()[0]
        self.assertEqual(in_file(), 0)
        with urlopen(self.base + f"/api/ontology/runs/{self.run['saved_as']}/open-items", timeout=30) as response:
            body = json.load(response)
        self.assertEqual(({v['name']: v['rows'] for v in body['views']}, body['row_cap']), ({'订单': 160}, 1000000))
        self.assertEqual(in_file(), 0)       # read from the same SQL, written nowhere
        conn.close()


if __name__ == '__main__':
    unittest.main()
