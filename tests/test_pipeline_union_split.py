"""合并 (union) and 拆分 (split) pipeline steps, held to the rules of the other steps: nothing lost and nothing counted twice without the run saying so.

A union stacks the rows of several steps, matching columns by name. It refuses what would mix two things under one name: a column whose type differs between the
inputs, a missing column (unless the person says to leave it empty, and then it counts the rows left empty), and a code column whose confirmed meanings differ
between inputs (2 is 已取消 in one and 生产中 in the other). It counts the rows that appear in more than one input, the double count a union makes.

A split sends each row to the first branch whose condition holds, and the rest to a 其余 branch when there is one. Every row is in at most one branch, the
branches and the rows in no branch add up to the rows in, a row whose condition field is empty is counted (it is not "false"), and a row that met a branch's
condition but went to an earlier one is counted on that branch. Each branch has its own id that later steps read."""
import unittest
from urllib.parse import quote

from ontology_poc_generator.pipeline_ops import new_context
from ontology_poc_generator.pipelines import check_pipeline, needed_steps, run_pipeline, workspace_datasets
from ontology_poc_generator.workspace_store import import_records, records_sha256
from tests.test_object_types import TABLES
from tests.test_pipeline_server import PIPELINES
from tests.test_pipelines import PipelineTestCase
from tests.test_two_person import SigningTestCase
from tests.test_workspace_questions import AskModel, cancelled
from tests.test_workspace_store import planted_bundle

ORDERS = planted_bundle()['sources']['订单']['records']
BIG = sum(int(r['金额']) >= 20000 for r in ORDERS)
HUGE = sum(int(r['金额']) >= 50000 for r in ORDERS)
SHIFT = {'0': '1', '1': '2', '2': '3'}
MEANINGS = {'已交付': ['0'], '生产中': ['1'], '已取消': ['2']}
SHIFTED_MEANINGS = {'已交付': ['1'], '生产中': ['2'], '已取消': ['3']}


def amount(cmp, value):
    return {'all': [{'column': '金额', 'cmp': cmp, 'value': value}]}


def orders(sid='orders'):
    return {'id': sid, 'type': 'input', 'dataset': '订单'}


def keep(sid, src, where):
    return {'id': sid, 'type': 'transform', 'from': src, 'operators': [{'op': 'filter', 'where': where}]}


class UnionSplitCase(PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        extra = {'旧订单': [{**r, '状态码': SHIFT[r['状态码']]} for r in ORDERS[:20]],
                 '外部订单': [{'订单号': f'W{i}', '金额': f'{i},200'} for i in range(5)],   # 金额 written with a thousands comma: text
                 '小表': [{'编号': '1', '值': '5'}, {'编号': '2', '值': None}, {'编号': '3', '值': '20'}]}
        ids = {name: import_records(cls.conn, name, rows, 'test', records_sha256(rows))['id'] for name, rows in extra.items()}
        cls.datasets = {**cls.datasets, **workspace_datasets(cls.conn, ids)}

    def run_spec(self, steps, ctx=None):
        return {n['id']: n for n in run_pipeline(self.conn, {'steps': steps}, self.datasets, ctx=ctx)['nodes']}

    def refused(self, steps, ctx=None):
        with self.assertRaises(ValueError) as caught:
            check_pipeline({'steps': steps}, self.datasets, ctx=ctx or new_context())
        return str(caught.exception)


class UnionTests(UnionSplitCase):
    def test_two_parts_of_the_same_rows_stack_back_to_all_of_them_with_nothing_repeated(self):
        n = self.run_spec([orders(), keep('big', 'orders', amount('ge', '20000')), keep('small', 'orders', amount('lt', '20000')),
                           {'id': 'all', 'type': 'union', 'inputs': ['big', 'small']}, {'id': 'out', 'type': 'output', 'from': 'all', 'name': '合并后'}])
        self.assertEqual((n['all']['rows_in'], n['all']['rows_out']), ([BIG, 160 - BIG], 160))
        self.assertEqual(n['all']['union']['same_rows']['count'], 0)
        self.assertEqual(n['all']['columns'], n['orders']['columns'])

    def test_rows_that_are_in_two_inputs_are_counted_and_shown(self):
        n = self.run_spec([orders('a'), orders('b'), {'id': 'twice', 'type': 'union', 'inputs': ['a', 'b']}])
        self.assertEqual(n['twice']['rows_out'], 320)
        same = n['twice']['union']['same_rows']
        self.assertEqual(same['count'], 160)   # every order is in both: a sum after this counts it twice
        self.assertEqual(len(same['examples']), 3)
        self.assertIn('订单号', same['examples'][0])

    def test_a_missing_column_is_refused_unless_it_is_left_empty_and_then_the_empty_rows_are_counted(self):
        steps = [orders(), {'id': 'w', 'type': 'input', 'dataset': '小表'}]
        words = self.refused([*steps, {'id': 'u', 'type': 'union', 'inputs': ['orders', 'w']}])
        self.assertIn('没有列', words)
        self.assertIn('订单号', words)
        self.assertIn('empty', words)   # says how to leave it empty
        n = self.run_spec([*steps, {'id': 'u', 'type': 'union', 'inputs': ['orders', 'w'], 'missing': 'empty'}])
        self.assertEqual(n['u']['rows_out'], 163)
        self.assertEqual(n['u']['union']['filled_empty']['订单号'], 3)
        self.assertEqual(n['u']['union']['filled_empty']['编号'], 160)

    def test_a_column_of_two_types_is_refused_with_the_types_and_the_fix(self):
        words = self.refused([orders(), {'id': 'w', 'type': 'input', 'dataset': '外部订单'},
                              {'id': 'u', 'type': 'union', 'inputs': ['orders', 'w'], 'missing': 'empty'}])
        self.assertIn('金额', words)
        self.assertIn('整数', words)
        self.assertIn('文本', words)
        self.assertIn('字段转换', words)

    def test_a_code_column_whose_meanings_differ_between_inputs_is_refused(self):
        ctx = lambda old: new_context(meanings={'订单.状态码': MEANINGS, '旧订单.状态码': old}, codes={'订单.状态码', '旧订单.状态码'})
        steps = [orders(), {'id': 'old', 'type': 'input', 'dataset': '旧订单'}, {'id': 'u', 'type': 'union', 'inputs': ['orders', 'old']}]
        words = self.refused(steps, ctx(SHIFTED_MEANINGS))
        self.assertIn('状态码', words)
        self.assertIn('打标签', words)
        n = self.run_spec(steps, ctx(MEANINGS))   # the same meanings on both sides: one column, still read by its meanings
        self.assertEqual(n['u']['rows_out'], 180)
        self.assertIn('状态码', self.refused(steps, new_context(meanings={'订单.状态码': MEANINGS}, codes={'订单.状态码', '旧订单.状态码'})))   # one side has no confirmed meanings

    def test_the_source_column_says_which_input_a_row_came_from(self):
        n = self.run_spec([orders('a'), {'id': 'w', 'type': 'input', 'dataset': '旧订单'},
                           {'id': 'u', 'type': 'union', 'inputs': ['a', 'w'], 'source_column': '来源'}])
        self.assertEqual(n['u']['columns'][-1], '来源')

    def test_a_union_names_two_or_more_different_steps_written_before_it(self):
        self.assertIn('至少两个', self.refused([orders(), {'id': 'u', 'type': 'union', 'inputs': ['orders']}]))
        self.assertIn('至少两个', self.refused([orders(), {'id': 'u', 'type': 'union', 'inputs': ['orders', 'orders']}]))
        self.assertIn('还没有定义', self.refused([orders(), {'id': 'u', 'type': 'union', 'inputs': ['orders', 'later']}, orders('later')]))
        self.assertIn('来源', self.refused([orders(), orders('b'), {'id': 'u', 'type': 'union', 'inputs': ['orders', 'b'], 'source_column': '金额'}]))


class SplitTests(UnionSplitCase):
    def split(self, *branches, src='orders'):
        return {'id': 's', 'type': 'split', 'from': src, 'branches': list(branches)}

    def test_every_row_goes_to_one_branch_and_the_branches_add_up_to_the_rows_in(self):
        n = self.run_spec([orders(), self.split({'id': 'big', 'where': amount('ge', '20000')}, {'id': 'rest', 'rest': True}),
                           {'id': 'out_big', 'type': 'output', 'from': 'big', 'name': '大单'}, {'id': 'out_rest', 'type': 'output', 'from': 'rest', 'name': '其余单'}])
        report = n['s']['split']
        self.assertEqual([(b['id'], b['rows']) for b in report['branches']], [('big', BIG), ('rest', 160 - BIG)])
        self.assertEqual(report['unassigned'], 0)
        self.assertEqual((n['out_big']['rows_out'], n['out_rest']['rows_out']), (BIG, 160 - BIG))

    def test_a_row_that_meets_two_conditions_goes_to_the_first_and_is_counted_on_the_second(self):
        n = self.run_spec([orders(), self.split({'id': 'big', 'where': amount('ge', '20000')}, {'id': 'huge', 'where': amount('ge', '50000')})])
        branches = {b['id']: b for b in n['s']['split']['branches']}
        self.assertEqual((branches['huge']['rows'], branches['huge']['also_matched']), (0, HUGE))
        self.assertEqual(n['s']['split']['unassigned'], 160 - BIG)   # no 其余 branch: these rows go nowhere, and the run says how many

    def test_a_row_whose_condition_field_is_empty_is_counted_and_goes_to_the_rest(self):
        n = self.run_spec([{'id': 't', 'type': 'input', 'dataset': '小表'},
                           self.split({'id': 'high', 'where': {'all': [{'column': '值', 'cmp': 'gt', 'value': '10'}]}}, {'id': 'other', 'rest': True}, src='t')])
        branches = {b['id']: b for b in n['s']['split']['branches']}
        self.assertEqual((branches['high']['rows'], branches['high']['empty_condition'], branches['other']['rows']), (1, 1, 2))

    def test_later_steps_read_a_branch_and_the_steps_a_branch_needs_run_for_it(self):
        spec = {'steps': [orders(), self.split({'id': 'big', 'where': amount('ge', '20000')}, {'id': 'rest', 'rest': True}),
                          {'id': 'u', 'type': 'union', 'inputs': ['big', 'rest']}, {'id': 'out', 'type': 'output', 'from': 'u', 'name': '再合起来'}]}
        self.assertEqual(needed_steps(spec, ['out']), {'orders', 's', 'u', 'out'})
        self.assertEqual(self.run_spec(spec['steps'])['out']['rows_out'], 160)

    def test_a_split_is_read_by_its_branches_and_its_branches_are_named_once(self):
        base = [orders()]
        self.assertIn('分支', self.refused([*base, self.split({'id': 'big', 'where': amount('ge', '1')}, {'id': 'r', 'rest': True}),
                                            {'id': 'o', 'type': 'output', 'from': 's', 'name': 'x'}]))
        self.assertIn('重复', self.refused([*base, self.split({'id': 'orders', 'where': amount('ge', '1')}, {'id': 'r', 'rest': True})]))
        self.assertIn('最后', self.refused([*base, self.split({'id': 'r', 'rest': True}, {'id': 'big', 'where': amount('ge', '1')})]))
        self.assertIn('条件', self.refused([*base, self.split({'id': 'big'}, {'id': 'r', 'rest': True})]))
        self.assertIn('至少', self.refused([*base, self.split({'id': 'r', 'rest': True})]))
        self.assertIn('没有列', self.refused([*base, self.split({'id': 'big', 'where': {'all': [{'column': '颜色', 'cmp': 'eq', 'value': '1'}]}}, {'id': 'r', 'rest': True})]))


if __name__ == '__main__':
    unittest.main()


class OddValueTests(UnionSplitCase):
    def test_a_value_of_the_wrong_kind_in_a_union_or_a_split_is_refused_in_words(self):
        base = [orders(), orders('b')]
        for odd in (None, 3, 'x', {'a': 1}, [1, 2], [['orders'], 'b']):
            self.refused([*base, {'id': 'u', 'type': 'union', 'inputs': odd}])
            self.refused([*base, {'id': 's', 'type': 'split', 'from': 'orders', 'branches': odd}])
            if not isinstance(odd, str):   # any text is a name a branch may have
                self.refused([*base, {'id': 's', 'type': 'split', 'from': 'orders', 'branches': [{'id': odd, 'where': amount('ge', '1')}, {'id': 'r', 'rest': True}]}])
            self.refused([*base, {'id': 's', 'type': 'split', 'from': 'orders', 'branches': [{'id': 'a', 'where': odd}, {'id': 'r', 'rest': True}]}])
            if odd is not None and not isinstance(odd, str):   # any text is a column name it may add
                self.refused([*base, {'id': 'u', 'type': 'union', 'inputs': ['orders', 'b'], 'source_column': odd}])
        self.assertIn('missing', self.refused([*base, {'id': 'u', 'type': 'union', 'inputs': ['orders', 'b'], 'missing': 'drop'}]))


class ServiceTests(SigningTestCase):
    def test_a_pipeline_with_a_split_and_a_union_is_saved_previewed_and_run_through_the_service(self):
        spec = {'steps': [orders(), {'id': 's', 'type': 'split', 'from': 'orders', 'branches': [{'id': 'big', 'where': amount('ge', '20000')}, {'id': 'rest', 'rest': True}]},
                          {'id': 'u', 'type': 'union', 'inputs': ['big', 'rest'], 'source_column': '来源'},
                          {'id': 'out', 'type': 'output', 'from': 'u', 'name': '分开又合起来', 'key': {'columns': ['订单号']}}]}
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            ann = self.people(base, 'ann', 'bob')['ann']
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
            status, body = ann.post(PIPELINES, {'name': '拆了又合', 'description': '试拆分和合并', 'spec': spec})
            self.assertEqual(status, 200, body)
            status, split = ann.post(f'{PIPELINES}/preview', {'id': '拆了又合', 'node': 's'})
            self.assertEqual(status, 200, split)
            self.assertEqual([(b['id'], b['rows']) for b in split['node']['split']['branches']], [('big', BIG), ('rest', 160 - BIG)])
            self.assertNotIn('__branch', [c['name'] for c in split['columns']])
            status, run = ann.post(f'{PIPELINES}/run', {'id': '拆了又合'})
            self.assertEqual((status, run['status']), (200, 'success'), run)
            written = ann.get(f'/api/workspace/datasets/{quote("分开又合起来")}')[1]
            self.assertEqual(written['rows'], 160)
