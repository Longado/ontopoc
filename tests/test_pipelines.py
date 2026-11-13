"""A pipeline is a list of typed steps (input dataset, join, output) compiled to SQL over the workspace tables. Each node
says its rows in and out; a join that makes more rows than its left input says why and which sums it would inflate.
The numbers are the planted fixtures': 160 orders, 45 tickets, 9 orders with two tickets."""
import tempfile
import unittest
from pathlib import Path

from ontology_poc_generator.pipelines import check_pipeline, compile_pipeline, run_pipeline, workspace_datasets, workspace_views
from ontology_poc_generator.workspace_store import import_records, open_workspace, records_sha256
from tests.test_workspace_store import planted_bundle

ORDERS_TICKETS = {'steps': [
    {'id': 'orders', 'type': 'input', 'dataset': '订单'},
    {'id': 'tickets', 'type': 'input', 'dataset': '售后工单'},
    {'id': 'joined', 'type': 'join', 'left': 'orders', 'right': 'tickets', 'how': 'left', 'on': [{'left': '订单号', 'right': '订单号'}]},
    {'id': 'out', 'type': 'output', 'from': 'joined', 'name': '订单带工单'}]}


def with_how(how):
    return {'steps': [{**s, 'how': how} if s['type'] == 'join' else s for s in ORDERS_TICKETS['steps']]}


class PipelineTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.conn = open_workspace(Path(cls.dir.name) / 'workspace.sqlite')
        ids = {name: import_records(cls.conn, name, s['records'], 'test', records_sha256(s['records']))['id'] for name, s in planted_bundle()['sources'].items()}
        cls.datasets = workspace_datasets(cls.conn, ids)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cls.dir.cleanup()

    def nodes(self, spec):
        return {n['id']: n for n in run_pipeline(self.conn, spec, self.datasets)['nodes']}


class DatasetTests(PipelineTestCase):
    def test_a_dataset_is_its_table_rows_and_typed_columns(self):
        orders = self.datasets['订单']
        self.assertEqual(orders['rows'], 160)
        self.assertEqual({c['name']: c['type'] for c in orders['columns']}['金额'], 'integer')
        self.assertEqual({c['name']: c['type'] for c in orders['columns']}['订单号'], 'text')


class RowCountsTests(PipelineTestCase):
    def test_a_left_join_of_orders_and_tickets_makes_169_rows_from_160(self):
        n = self.nodes(ORDERS_TICKETS)
        self.assertEqual([(n[i]['rows_in'], n[i]['rows_out']) for i in ('orders', 'tickets', 'joined', 'out')],
                         [([160], 160), ([45], 45), ([160, 45], 169), ([169], 169)])

    def test_an_inner_join_keeps_the_45_tickets_and_still_repeats_orders(self):
        n = self.nodes(with_how('inner'))
        self.assertEqual((n['joined']['rows_in'], n['joined']['rows_out']), ([160, 45], 45))
        self.assertEqual(n['joined']['join']['matched_left'], 36)        # 36 orders have a ticket; 9 of them have two
        self.assertEqual(n['joined']['join']['extra_rows'], 9)


class FanOutTests(PipelineTestCase):
    def join(self, how='left'):
        return self.nodes(with_how(how))['joined']['join']

    def test_the_rows_beyond_the_left_input_are_counted_for_both_kinds_of_join(self):
        for how in ('left', 'inner'):
            self.assertEqual(self.join(how)['extra_rows'], 9, how)

    def test_the_keys_that_repeat_on_the_right_are_named_with_their_rows_on_each_side(self):
        fan = self.join()['fan_out']
        self.assertEqual(fan['repeated_keys'], 9)
        self.assertEqual(fan['columns'], ['订单号'])
        self.assertEqual(len(fan['examples']), 3)
        self.assertTrue(all(e['right_rows'] == 2 and e['left_rows'] == 1 and list(e['key']) == ['订单号'] for e in fan['examples']))

    def test_the_numeric_columns_a_sum_would_double_count_say_what_they_sum_to_before_and_after(self):
        amounts = {c['column']: c for c in self.join()['fan_out']['double_counted']}
        self.assertEqual((amounts['金额']['without'], amounts['金额']['with']), (2726470, 2883740))     # +157,270 over 160 orders
        inner = {c['column']: c for c in self.join('inner')['fan_out']['double_counted']}
        self.assertEqual((inner['金额']['without'], inner['金额']['with']), (689490, 846760))           # the 36 orders that have tickets
        self.assertNotIn('订单号', amounts)                                                              # a key is not a sum

    def test_a_join_that_makes_no_extra_rows_is_not_flagged(self):
        spec = {'steps': [{'id': 'tickets', 'type': 'input', 'dataset': '售后工单'}, {'id': 'orders', 'type': 'input', 'dataset': '订单'},
                          {'id': 'j', 'type': 'join', 'left': 'tickets', 'right': 'orders', 'how': 'left', 'on': [{'left': '订单号', 'right': '订单号'}]}]}
        join = self.nodes(spec)['j']
        self.assertEqual((join['rows_out'], join['join']['extra_rows'], join['join']['fan_out']), (45, 0, None))

    def test_repeats_on_the_right_that_no_left_row_matches_do_not_count(self):
        spec = {'steps': [{'id': 'customers', 'type': 'input', 'dataset': '客户'}, {'id': 'stock', 'type': 'input', 'dataset': '库存快照'},
                          {'id': 'j', 'type': 'join', 'left': 'customers', 'right': 'stock', 'how': 'left', 'on': [{'left': '客户编号', 'right': '产品编号'}]}]}
        join = self.nodes(spec)['j']
        self.assertIsNone(join['join']['fan_out'])      # stock repeats 产品编号 six times each, but no customer number is a product number


class CompileTests(PipelineTestCase):
    def test_each_step_is_one_statement_over_the_workspace_tables_and_the_join_prefixes_clashing_columns(self):
        steps = compile_pipeline(check_pipeline(ORDERS_TICKETS, self.datasets), self.datasets)
        self.assertEqual([s['id'] for s in steps], ['orders', 'tickets', 'joined', 'out'])
        joined = next(s for s in steps if s['id'] == 'joined')
        self.assertIn('LEFT JOIN', joined['sql'])
        self.assertIn('ON l."订单号" = r."订单号"', joined['sql'])
        names = [c['name'] for c in joined['columns']]
        self.assertEqual(names.count('订单号'), 1)                       # the key written the same on both sides is kept once
        two = {'steps': [ORDERS_TICKETS['steps'][0], {'id': 'b', 'type': 'input', 'dataset': '订单'},
                         {'id': 'j', 'type': 'join', 'left': 'orders', 'right': 'b', 'how': 'inner', 'on': [{'left': '订单号', 'right': '订单号'}]}]}
        names = [c['name'] for c in compile_pipeline(check_pipeline(two, self.datasets), self.datasets)[2]['columns']]
        self.assertIn('left_金额', names)
        self.assertIn('right_金额', names)
        self.assertNotIn('金额', names)


class CheckTests(PipelineTestCase):
    def bad(self, spec):
        with self.assertRaises(ValueError) as caught:
            check_pipeline(spec, self.datasets)
        return str(caught.exception)

    def test_what_cannot_be_run_is_refused_in_words(self):
        steps = ORDERS_TICKETS['steps']
        self.assertIn('要有 steps', self.bad({}))
        self.assertIn('没有这张表', self.bad({'steps': [{'id': 'a', 'type': 'input', 'dataset': '没有'}]}))
        self.assertIn('不认识的步骤类型', self.bad({'steps': [{'id': 'a', 'type': 'magic'}]}))
        self.assertIn('编号重复', self.bad({'steps': [steps[0], steps[0]]}))
        self.assertIn('还没有定义', self.bad({'steps': [steps[2]]}))                         # a join before its inputs
        self.assertIn('只能是 inner 或 left', self.bad({'steps': [*steps[:2], {**steps[2], 'how': 'outer'}]}))
        self.assertIn('关联字段', self.bad({'steps': [*steps[:2], {**steps[2], 'on': []}]}))
        self.assertIn('读的步骤 orders 里没有列 没有这列', self.bad({'steps': [*steps[:2], {**steps[2], 'on': [{'left': '没有这列', 'right': '订单号'}]}]}))
        self.assertIn('读的步骤 tickets 里没有列 没有这列', self.bad({'steps': [*steps[:2], {**steps[2], 'on': [{'left': '订单号', 'right': '没有这列'}]}]}))
        self.assertIn('输出要写名字', self.bad({'steps': [*steps[:3], {'id': 'o', 'type': 'output', 'from': 'joined'}]}))

    def test_a_pipeline_is_plain_json_data_and_checking_it_changes_nothing(self):
        import copy
        before = copy.deepcopy(ORDERS_TICKETS)
        check_pipeline(ORDERS_TICKETS, self.datasets)
        self.assertEqual(ORDERS_TICKETS, before)


class ReadOnlyTests(PipelineTestCase):
    def test_a_run_on_a_read_only_connection_works_and_leaves_the_workspace_as_it_was(self):
        import sqlite3
        path = Path(self.dir.name) / 'workspace.sqlite'
        tables = lambda c: sorted(r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'"))
        reader = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        before = tables(reader)
        nodes = {n['id']: n for n in run_pipeline(reader, ORDERS_TICKETS, self.datasets)['nodes']}
        self.assertEqual(nodes['joined']['rows_out'], 169)
        self.assertEqual(tables(reader), before)
        self.assertEqual(reader.execute("SELECT COUNT(*) FROM sqlite_temp_master").fetchone()[0], 0)    # the steps' temporary tables are gone
        reader.close()

    def test_two_joins_in_a_row_count_each_against_its_own_left_input(self):
        spec = {'steps': [*ORDERS_TICKETS['steps'][:3], {'id': 'customers', 'type': 'input', 'dataset': '客户'},
                          {'id': 'again', 'type': 'join', 'left': 'joined', 'right': 'customers', 'how': 'left', 'on': [{'left': '客户编号', 'right': '客户编号'}]}]}
        n = self.nodes(spec)
        self.assertEqual((n['joined']['rows_out'], n['again']['rows_in'], n['again']['rows_out']), (169, [169, 31], 171))   # KH012 is on two rows of the customer table and 2 orders name it
        self.assertEqual(n['again']['join']['extra_rows'], 2)
        self.assertEqual(n['again']['join']['fan_out']['examples'][0]['key'], {'客户编号': 'KH012'})


COMMITMENTS_ORDERS = {'steps': [
    {'id': 'commitments', 'type': 'input', 'dataset': '订单承诺'}, {'id': 'orders', 'type': 'input', 'dataset': '订单'},
    {'id': 'joined', 'type': 'join', 'left': 'commitments', 'right': 'orders', 'how': 'left', 'on': [{'left': '订单号', 'right': '订单号'}]}]}


class OtherDirectionTests(PipelineTestCase):
    def join(self, **kwargs):
        return run_pipeline(self.conn, COMMITMENTS_ORDERS, self.datasets, **kwargs)['nodes'][2]['join']

    def test_a_left_side_that_repeats_a_key_repeats_the_right_sides_numbers_and_says_so(self):
        join = self.join()
        self.assertEqual((join['extra_rows'], join['fan_out']), (0, None))       # 121 commitments in, 121 rows out: the left side did not grow
        fan = join['right_fan_out']
        self.assertEqual(fan['repeated_keys'], 37)                              # 60 orders have a commitment; 37 have a second version, 24 of those a third
        orders = {r['订单号']: r for r in planted_bundle()['sources']['订单']['records']}
        commitments = planted_bundle()['sources']['订单承诺']['records']
        amounts = {c['column']: c for c in fan['double_counted']}
        self.assertEqual(amounts['金额']['with'], sum(int(orders[c['订单号']]['金额']) for c in commitments))                   # every version repeats the order's amount
        self.assertEqual(amounts['金额']['without'], sum(int(orders[k]['金额']) for k in {c['订单号'] for c in commitments}))   # counted once per order

    def test_a_code_column_is_not_reported_as_a_sum(self):
        self.assertIn('状态码', {c['column'] for c in self.join()['right_fan_out']['double_counted']})
        counted = {c['column'] for c in self.join(skip={'订单.状态码'})['right_fan_out']['double_counted']}
        self.assertNotIn('状态码', counted)
        self.assertIn('金额', counted)
        with_commitments = {'steps': [ORDERS_TICKETS['steps'][0], {'id': 'c', 'type': 'input', 'dataset': '订单承诺'},
                                      {'id': 'j', 'type': 'join', 'left': 'orders', 'right': 'c', 'how': 'left', 'on': [{'left': '订单号', 'right': '订单号'}]}]}
        columns = lambda skip: {c['column'] for c in run_pipeline(self.conn, with_commitments, self.datasets, skip=skip)['nodes'][2]['join']['fan_out']['double_counted']}
        self.assertIn('状态码', columns(frozenset()))                      # the noise the review found: 80 -> 109
        self.assertNotIn('状态码', columns({'订单.状态码'}))
        self.assertIn('金额', columns({'订单.状态码'}))


class KeyTextTests(unittest.TestCase):
    def setUp(self):
        self.conn = open_workspace(':memory:')
        self.addCleanup(self.conn.close)
        left = [{'k': ' 2', 'v': 'a'}, {'k': '1.0', 'v': 'b'}, {'k': '3', 'v': 'c'}, {'k': '', 'v': 'blank-left'}, {'k': None, 'v': 'null-left'}, {'k': '2026-01', 'v': 'month'}]
        right = [{'k': '2', 'w': 'x'}, {'k': '1', 'w': 'y'}, {'k': '3', 'w': 'z'}, {'k': '', 'w': 'blank-right'}, {'k': '', 'w': 'blank-right-2'}, {'k': '2026-02', 'w': 'other month'}]
        ids = {n: import_records(self.conn, n, rows, 't', records_sha256(rows))['id'] for n, rows in (('左', left), ('右', right))}
        self.datasets = workspace_datasets(self.conn, ids)
        spec = {'steps': [{'id': 'l', 'type': 'input', 'dataset': '左'}, {'id': 'r', 'type': 'input', 'dataset': '右'},
                          {'id': 'j', 'type': 'join', 'left': 'l', 'right': 'r', 'how': 'left', 'on': [{'left': 'k', 'right': 'k'}]}]}
        self.node = run_pipeline(self.conn, spec, self.datasets)['nodes'][2]

    def test_keys_are_compared_as_written_and_the_report_counts_the_ones_that_would_match_if_read_as_numbers_or_trimmed(self):
        join = self.node['join']
        self.assertEqual(self.node['rows_out'], 6)                           # only "3" matches as written
        self.assertEqual(join['matched_left'], 1)
        self.assertEqual(join['near_matches'], [{'left': 'k', 'right': 'k', 'count': 2, 'examples': [' 2', '1.0']}])   # not 2026-01 against 2026-02

    def test_an_empty_key_matches_nothing_and_is_counted(self):
        self.assertEqual((self.node['join']['left_blank'], self.node['join']['right_blank']), (2, 2))   # a missing left key is blank too
        self.assertIsNone(self.node['join']['fan_out'])                      # two empty right keys are not a "repeated key"


class CapAndSpeedTests(unittest.TestCase):
    def test_a_join_that_would_make_too_many_rows_is_refused_before_it_runs_and_says_how_many(self):
        conn = open_workspace(':memory:')
        self.addCleanup(conn.close)
        rows = [{'k': 'same', 'v': str(i)} for i in range(50)]
        ids = {n: import_records(conn, n, rows, 't', records_sha256(rows))['id'] for n in ('甲', '乙')}
        spec = {'steps': [{'id': 'a', 'type': 'input', 'dataset': '甲'}, {'id': 'b', 'type': 'input', 'dataset': '乙'},
                          {'id': 'j', 'type': 'join', 'left': 'a', 'right': 'b', 'how': 'inner', 'on': [{'left': 'k', 'right': 'k'}]}]}
        datasets = workspace_datasets(conn, ids)
        self.assertEqual(run_pipeline(conn, spec, datasets, row_cap=2500)['nodes'][2]['rows_out'], 2500)
        with self.assertRaises(ValueError) as caught:
            run_pipeline(conn, spec, datasets, row_cap=2499)
        self.assertIn('2,500 行，超过一次最多 2,499 行，没有运行', str(caught.exception))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM sqlite_temp_master").fetchone()[0], 0)

    def test_the_fan_out_report_grows_with_the_inputs_not_with_the_square_of_them(self):
        import time
        conn = open_workspace(':memory:')
        self.addCleanup(conn.close)
        left = [{'k': f'K{i % 10000}', 'v': '1'} for i in range(20000)]        # every key twice on both sides: 40,000 rows made
        right = [{'k': f'K{i % 10000}', 'w': '1'} for i in range(20000)]
        ids = {n: import_records(conn, n, rows, 't', records_sha256(rows))['id'] for n, rows in (('左', left), ('右', right))}
        spec = {'steps': [{'id': 'l', 'type': 'input', 'dataset': '左'}, {'id': 'r', 'type': 'input', 'dataset': '右'},
                          {'id': 'j', 'type': 'join', 'left': 'l', 'right': 'r', 'how': 'left', 'on': [{'left': 'k', 'right': 'k'}]}]}
        started = time.monotonic()
        join = run_pipeline(conn, spec, workspace_datasets(conn, ids))['nodes'][2]
        self.assertEqual((join['rows_out'], join['join']['fan_out']['repeated_keys']), (40000, 10000))
        self.assertLess(time.monotonic() - started, 4)      # the correlated version took 24 s at this size


class StepReferenceTests(PipelineTestCase):
    def test_a_step_that_points_at_a_list_or_an_object_is_refused_in_words(self):
        steps = ORDERS_TICKETS['steps']
        for bad in ({'steps': [{'id': 'a', 'type': 'input', 'dataset': {}}]}, {'steps': [{'id': 'a', 'type': 'input', 'dataset': ['订单']}]},
                    {'steps': [*steps[:2], {**steps[2], 'left': []}]}, {'steps': [*steps[:2], {**steps[2], 'right': {'x': 1}}]},
                    {'steps': [*steps[:3], {'id': 'o', 'type': 'output', 'from': [], 'name': 'x'}]},
                    {'steps': [*steps[:2], {**steps[2], 'on': [{'left': [], 'right': '订单号'}]}]},
                    {'steps': [{'id': 'a', 'type': 'input', 'view': 1}]}):
            with self.assertRaises(ValueError, msg=bad):
                check_pipeline(bad, self.datasets)


class ViewInputTests(unittest.TestCase):
    """A pipeline reads 有效订单 (a view) as an input: 144 rows, not the 160 of the table."""
    def setUp(self):
        from ontology_poc_generator.named_views import save_definition, views_of_run
        from ontology_poc_generator.workspace_store import set_element_states
        self.conn = open_workspace(':memory:')
        self.addCleanup(self.conn.close)
        bundle = planted_bundle()
        ids = {n: import_records(self.conn, n, s['records'], 't', records_sha256(s['records']))['id'] for n, s in bundle['sources'].items()}
        self.datasets = workspace_datasets(self.conn, ids)
        set_element_states(self.conn, [('property:K:订单.状态码', 'confirmed', None, '王工',
                                        {'values': [{'value': '0', 'label': '进行中'}, {'value': '1', 'label': '已交付'}, {'value': '2', 'label': '已取消'}]})])
        save_definition(self.conn, 'K', dict(name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消'), self.datasets, {'object_types': [], 'relations': []}, '王工')
        from tests.test_workspace_store import PLANTED_DRAFT
        self.views = workspace_views(views_of_run(self.conn, 'K', 'R', PLANTED_DRAFT, self.datasets))

    def test_a_view_is_an_input_with_its_rows_and_without_the_row_number_column(self):
        spec = {'steps': [{'id': 'v', 'type': 'input', 'view': '有效订单'}, {'id': 't', 'type': 'input', 'dataset': '订单'},
                          {'id': 'j', 'type': 'join', 'left': 'v', 'right': 't', 'how': 'left', 'on': [{'left': '订单号', 'right': '订单号'}]}]}
        nodes = {n['id']: n for n in run_pipeline(self.conn, spec, self.datasets, self.views)['nodes']}
        self.assertEqual((nodes['v']['rows_in'], nodes['v']['rows_out'], nodes['v']['reads']), ([144], 144, '视图 有效订单'))
        self.assertEqual(nodes['t']['reads'], '表 订单')
        self.assertNotIn('_行号', nodes['v']['columns'])
        self.assertIn('状态码_含义', nodes['v']['columns'])
        self.assertNotIn('_行号', nodes['j']['columns'])
        self.assertEqual(nodes['j']['rows_out'], 144)                      # two inputs that share every column but one side lacks the cancelled ones
        self.assertEqual(nodes['t']['columns'], [c['name'] for c in self.datasets['订单']['columns']])

    def test_a_view_that_is_not_there_is_refused_in_words_and_a_name_cannot_be_both(self):
        for step, said in (({'id': 'v', 'type': 'input', 'view': '没有'}, '没有这个视图 没有'), ({'id': 'v', 'type': 'input', 'view': '有效订单', 'dataset': '订单'}, '不能两个都写'),
                           ({'id': 'v', 'type': 'input', 'dataset': '有效订单'}, '没有这张表 有效订单')):
            with self.assertRaises(ValueError) as caught:
                check_pipeline({'steps': [step]}, self.datasets, self.views)
            self.assertIn(said, str(caught.exception))


class ServerTests(unittest.TestCase):
    def test_the_pipeline_is_run_on_the_tables_of_a_kept_run_and_a_bad_one_is_refused_in_words(self):
        from tests.test_ontology_ask_server import call
        from tests.test_ontology_server import OntologyServerTests
        from tests.test_workspace_store import PlantedDraftModel, ServerDataChecksTests
        with OntologyServerTests().server(gateway=PlantedDraftModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', {'files': ServerDataChecksTests.files})
            status, body = call(base, '/api/ontology/pipelines/run', {'saved_as': run['saved_as'], 'pipeline': ORDERS_TICKETS})
            self.assertEqual(status, 200, body)
            self.assertEqual([(n['id'], n['rows_in'], n['rows_out']) for n in body['nodes']],
                             [('orders', [160], 160), ('tickets', [45], 45), ('joined', [160, 45], 169), ('out', [169], 169)])
            self.assertEqual(body['nodes'][2]['join']['extra_rows'], 9)
            status, body = call(base, '/api/ontology/pipelines/run', {'saved_as': run['saved_as'], 'pipeline': {'steps': [{'id': 'a', 'type': 'input', 'dataset': '没有'}]}})
            self.assertEqual(status, 400)
            self.assertIn('没有这张表', body['error'])
            self.assertEqual(call(base, '/api/ontology/pipelines/run', {'saved_as': '20260101T000000Z-deadbeef.json', 'pipeline': {}})[0], 404)
            self.assertEqual(call(base, '/api/ontology/pipelines/run', {'saved_as': run['saved_as'], 'pipeline': 'x'})[0], 400)


if __name__ == '__main__':
    unittest.main()
