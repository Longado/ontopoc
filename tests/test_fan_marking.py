"""How a pipeline decides that a figure was repeated by a join, and what the mark does after that (the review of tests/test_fan_sum.py).

The mark is decided by structure, not by comparing totals: a column that comes from one side of a join is marked as soon as one row of that side was copied onto
more than one output row, whatever the values are (a total can come out right by accident: 100 twice and -100 twice add up to the same as once each, while
every group and the average are wrong). The mark follows the column through the later steps of the pipeline (cast, calculated column, fill, filter, union) and
into a pipeline that reads it. It comes off by measurement: while the join's hidden row columns are there, the output is measured again, and the mark goes only
when no row of that side is on more than one output row; where a step loses them (an aggregate), only a grouping by exactly that side's join key, measured unique
on that side, with max, min or count distinct takes it off. It is read on the version a number reads: a later clean run is answered again. Every aggregate that repeats
distort is refused (sum, average, median, percentiles, a histogram, a statistics table); a count of objects, a count distinct, a min and a max are not. Only a
person who may open pipelines is told which pipeline; the refusal says nothing of rows or columns the asker may not see."""
import json
import unittest

from tests.test_fan_sum import FAN_NOTE, LINES, ORDERS, PIPELINES, FanSumTests, asks
from tests.test_object_relations import table_csv
from tests.test_workspace_questions import AskModel

P1 = 'P1订单行'


def spec(*middle, last='j', out='line_amounts', left='l', right='o', extra=()):
    """The lines joined to their orders (lines on the left), then `middle`, then an output one row per line."""
    return {'steps': [{'id': 'l', 'type': 'input', 'dataset': 'lines'}, {'id': 'o', 'type': 'input', 'dataset': 'orders'}, *extra,
                      {'id': 'j', 'type': 'join', 'left': left, 'right': right, 'how': 'left', 'on': [{'left': 'order_id', 'right': 'order_id'}]}, *middle,
                      {'id': 'out', 'type': 'output', 'from': last, 'name': out, 'key': {'columns': ['line_id']}}]}


def transform(*ops, source='j'):
    return {'id': 't', 'type': 'transform', 'from': source, 'operators': list(ops)}


def line_type(*columns, dataset='line_amounts', name='订单行', english='order_line'):
    return {'english_name': english, 'name': name, 'dataset': dataset, 'key': ['line_id'], 'properties': [{'column': c} for c in ('line_id', 'order_id', 'customer', *columns)]}


def load_tests(loader, standard, pattern):
    return unittest.TestSuite(MarkingTests(name) for name in vars(MarkingTests) if name.startswith('test_'))


class MarkingTests(FanSumTests):
    def world(self, base, pipeline_spec, t, orders=ORDERS, lines=LINES, people=('ann', 'bob'), roles=None, name=P1):
        team = self.people(base, *people, roles=roles)
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [table_csv('orders.csv', orders), table_csv('lines.csv', lines)]})[0], 200)
        self.pipeline(team, name, pipeline_spec)
        self.typed(team, t)
        return team

    def query(self, client, text, **more):
        return client.post('/api/workspace/query', {'text': text}, **more)

    def refused(self, client, text, pipeline=P1, **more):
        status, body = self.query(client, text, **more)
        self.assertEqual(status, 400, (text, body))
        if pipeline:
            self.assertIn(pipeline, body['error'], text)
        return body['error']

    def answered(self, client, text, value):
        status, body = self.query(client, text)
        self.assertEqual((status, body.get('status'), (body.get('answer') or {}).get('measure', {}).get('value')), (200, 'answered', value), (text, body))

    def marks(self, client, dataset='line_amounts'):
        return {c['name']: c.get('fan') for c in client.get(f'/api/workspace/datasets/{dataset}')[1]['columns']}

    def test_a_copied_row_marks_its_side_even_when_the_totals_come_out_right(self):
        # 100 on two lines and -100 on two lines: every line together adds up to 30, the right total, while C1 gives 200 (true 100), C2 -200 (true -100), and the average 6 (true 10)
        orders = [{'order_id': 'O1', 'customer': 'C1', 'amount': '100'}, {'order_id': 'O2', 'customer': 'C2', 'amount': '-100'}, {'order_id': 'O3', 'customer': 'C3', 'amount': '30'}]
        lines = [{'line_id': 'L1', 'order_id': 'O1', 'product': 'P1'}, {'line_id': 'L2', 'order_id': 'O1', 'product': 'P2'}, {'line_id': 'L3', 'order_id': 'O2', 'product': 'P1'},
                 {'line_id': 'L4', 'order_id': 'O2', 'product': 'P2'}, {'line_id': 'L5', 'order_id': 'O3', 'product': 'P3'}]
        with self.service(gateway=AskModel(asks('order_line', 'amount'))) as (base, out):
            ann = self.world(base, spec(), line_type('amount'), orders, lines)['ann']
            self.assertEqual(self.marks(ann)['amount'], FAN_NOTE)
            self.refused(ann, 'SELECT l.customer, sum(l.amount) AS s FROM (l:订单行) GROUP BY l.customer')
            self.refused(ann, 'SELECT avg(l.amount) FROM (l:订单行)')
            self.refused(ann, 'SELECT sum(l.amount) FROM (l:订单行)')
            status, body = self.chart(ann, 'order_line', {'kind': 'number', 'measure': 'amount', 'fn': 'max'})
            self.assertEqual((status, body.get('value')), (200, 100), body)
        # an order of 0 on two lines: the average over the lines is 20, over the orders 26.67
        zero = [{**ORDERS[0], 'amount': '0'}, *ORDERS[1:]]
        with self.service() as (base, out):
            ann = self.world(base, spec(), line_type('amount'), zero)['ann']
            self.refused(ann, 'SELECT avg(l.amount) FROM (l:订单行)')

    def test_the_mark_follows_the_column_through_later_steps_and_comes_off_only_at_a_step_that_goes_back_to_one_row_per_order(self):
        carried = transform({'op': 'cast', 'column': 'amount', 'to': 'decimal'}, {'op': 'fill_null', 'columns': ['amount'], 'with': {'constant': 0}},
                            {'op': 'calc', 'name': 'gross', 'expression': 'amount * 1.13'}, {'op': 'filter', 'where': {'column': 'product', 'cmp': 'ne', 'value': 'P9'}})
        with self.service() as (base, out):
            ann = self.world(base, spec(carried, last='t'), line_type('amount', 'gross'))['ann']
            self.assertEqual({k: v for k, v in self.marks(ann).items() if v}, {'amount': FAN_NOTE, 'gross': FAN_NOTE})
            self.refused(ann, 'SELECT sum(l.gross) FROM (l:订单行)')   # was 316.4: 280 x 1.13
            self.refused(ann, 'SELECT sum(l.amount) FROM (l:订单行)')
        # through a union with rows of another branch
        union = spec({'id': 'j2', 'type': 'join', 'left': 'l', 'right': 'o', 'how': 'left', 'on': [{'left': 'order_id', 'right': 'order_id'}]},
                     transform({'op': 'filter', 'where': {'column': 'product', 'cmp': 'eq', 'value': 'NONE'}}, source='j2'), {'id': 'u', 'type': 'union', 'inputs': ['j', 't']}, last='u')
        with self.service() as (base, out):
            ann = self.world(base, union, line_type('amount'))['ann']
            self.refused(ann, 'SELECT sum(l.amount) FROM (l:订单行)')
        # a dedupe on the order key, or an aggregate grouped by it with max, goes back to one row per order: no mark, and 180 is answered
        with self.service() as (base, out):
            ann = self.world(base, spec(transform({'op': 'dedupe', 'keys': ['order_id'], 'order_by': 'line_id'}), last='t'), line_type('amount'))['ann']
            self.assertEqual(self.marks(ann)['amount'], None)
            self.answered(ann, 'SELECT sum(l.amount) FROM (l:订单行)', 180)
        per_order = {'steps': [*spec()['steps'][:3], transform({'op': 'aggregate', 'group_by': ['order_id'], 'aggregations': [{'fn': 'max', 'column': 'amount', 'as': 'amount'},
                                                                                                                             {'fn': 'sum', 'column': 'amount', 'as': 'summed'}]}),
                               {'id': 'out', 'type': 'output', 'from': 't', 'name': 'per_order', 'key': {'columns': ['order_id']}}]}
        with self.service() as (base, out):
            ann = self.world(base, per_order, {'english_name': 'per_order', 'name': '每单', 'dataset': 'per_order', 'key': ['order_id'],
                                               'properties': [{'column': 'order_id'}, {'column': 'amount'}, {'column': 'summed'}]})['ann']
            self.assertEqual(self.marks(ann, 'per_order'), {'order_id': None, 'amount': None, 'summed': FAN_NOTE})   # the max is one order's amount; the sum per order adds the copies
            self.answered(ann, 'SELECT sum(p.amount) FROM (p:每单)', 180)
            self.refused(ann, 'SELECT sum(p.summed) FROM (p:每单)')
        # the mark comes off by measurement: a filter that leaves every order on one line leaves no copy, and the true 180 is answered
        with self.service() as (base, out):
            ann = self.world(base, spec(transform({'op': 'filter', 'where': {'column': 'line_id', 'cmp': 'ne', 'value': 'L2'}}), last='t'), line_type('amount'))['ann']
            self.assertEqual(self.marks(ann)['amount'], None)
            self.answered(ann, 'SELECT sum(l.amount) FROM (l:订单行)', 180)

    def test_a_pipeline_that_reads_a_marked_column_keeps_the_mark_and_the_refusal_names_the_pipeline_whose_join_repeated_it(self):
        copy = {'steps': [{'id': 'i', 'type': 'input', 'dataset': 'line_amounts'}, {'id': 'out', 'type': 'output', 'from': 'i', 'name': 'line_copy', 'key': {'columns': ['line_id']}}]}
        with self.service() as (base, out):
            team = self.world(base, spec(), line_type('amount'))
            self.pipeline(team, 'P2副本', copy)
            self.typed(team, line_type('amount', dataset='line_copy', name='订单行副本', english='order_line2'))
            said = self.refused(team['ann'], 'SELECT sum(l.amount) FROM (l:订单行副本)')
            self.assertNotIn('P2副本', said)

    def test_the_mark_is_read_on_the_current_version_so_a_clean_rerun_and_a_pipeline_reading_it_answer_again(self):
        one_each = [l for l in LINES if l['line_id'] != 'L2']
        copy = {'steps': [{'id': 'i', 'type': 'input', 'dataset': 'line_amounts'}, {'id': 'out', 'type': 'output', 'from': 'i', 'name': 'line_copy', 'key': {'columns': ['line_id']}}]}
        with self.service() as (base, out):
            team = self.world(base, spec(), line_type('amount'))
            ann, bob = team['ann'], team['bob']
            self.refused(ann, 'SELECT sum(l.amount) FROM (l:订单行)')
            # the data is put right: every order on one line; P1 runs again and its new version carries no mark
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [table_csv('lines.csv', one_each, target='lines', mode='overwrite')]})[0], 200)
            self.confirm_pipeline(bob, P1)
            self.assertEqual(ann.post(f'{PIPELINES}/run', {'id': P1})[1]['status'], 'success')
            shown = bob.get('/api/workspace/types/order_line')[1]
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order_line', 'version': shown['version'], 'seen': shown['seen']})[0], 200)
            self.answered(ann, 'SELECT sum(l.amount) FROM (l:订单行)', 180)
            # a pipeline that copies it now reads the clean version: no mark from the old one
            self.pipeline(team, 'P2副本', copy)
            self.assertEqual(self.marks(ann, 'line_copy')['amount'], None)
            self.typed(team, line_type('amount', dataset='line_copy', name='订单行副本', english='order_line2'))
            self.answered(ann, 'SELECT sum(l.amount) FROM (l:订单行副本)', 180)

    def test_every_aggregate_that_repeats_distort_is_refused_and_count_count_distinct_min_and_max_are_not(self):
        with self.service() as (base, out):
            team = self.world(base, spec(), line_type('amount'))
            ann = team['ann']
            for chart in ({'kind': 'number', 'measure': 'amount', 'fn': fn} for fn in ('sum', 'avg', 'median', 'p25', 'p75')):
                status, body = self.chart(ann, 'order_line', chart)
                self.assertEqual(status, 400, (chart, body))
                self.assertIn(P1, body['error'])
            for chart in ({'kind': 'histogram', 'measure': 'amount'}, {'kind': 'table', 'measure': 'amount'}, {'kind': 'bar', 'group': 'customer', 'measure': 'amount', 'fn': 'median'}):
                self.assertEqual(self.chart(ann, 'order_line', chart)[0], 400, chart)
            for fn, value in (('count', len(LINES)), ('count_distinct', 3), ('min', 30), ('max', 100)):
                status, body = self.chart(ann, 'order_line', {'kind': 'number', 'measure': 'amount', 'fn': fn})
                self.assertEqual((status, body.get('value')), (200, value), (fn, body))
            # a derived statistic: a median of the copies per customer is refused, a max is not
            self.typed(team, {'english_name': 'customer', 'name': '客户', 'dataset': 'orders', 'key': ['order_id'], 'properties': [{'column': 'order_id'}, {'column': 'customer'}]})
            self.relation(team, {'english_name': 'line_order', 'name': '订单行属于订单', 'from': 'order_line', 'to': 'customer', 'cardinality': 'many_to_one',
                                 'from_column': 'order_id', 'to_column': 'order_id'})
            stat = {'type': 'customer', 'english_name': 'line_median', 'name': '行金额中位数', 'kind': 'statistic', 'path': ['line_order'], 'measure': {'column': 'amount'}, 'fn': 'median'}
            status, body = ann.post('/api/workspace/types/derived', stat)
            self.assertEqual(status, 409, body)
            self.assertIn(P1, body['error'])
            self.assertEqual(ann.post('/api/workspace/types/derived', {**stat, 'english_name': 'line_max', 'name': '行金额最大', 'fn': 'max'})[0], 200)

    def test_only_a_person_who_may_open_pipelines_is_told_which_and_nothing_is_said_of_hidden_columns_or_rows(self):
        model = AskModel(asks('order_line', 'amount'))
        with self.service(gateway=model) as (base, out):
            team = self.world(base, spec(), line_type('amount'), people=('ann', 'bob', 'vera', 'rita'), roles={'vera': 'viewer', 'rita': 'viewer'})
            ann, vera, rita, admin = team['ann'], team['vera'], team['rita'], team['admin']
            text = 'SELECT sum(l.amount) FROM (l:订单行)'
            builder = self.refused(ann, text)
            viewer = self.refused(vera, text, pipeline=None)
            self.assertNotIn(P1, viewer)
            self.assertEqual(viewer, builder.replace(f'管道“{P1}”', '一个管道'))
            model.item = asks('order_line', 'amount')
            asked = vera.post('/api/workspace/ask', {'question': '订单金额合计？'})[1]
            self.assertEqual((asked['status'], asked['reason']), ('query_limit', viewer))
            # a viewer limited to some rows is refused with the very same sentence: it says nothing about the rows they cannot see
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order_line', 'rules': [{'column': 'customer', 'value': 'C2', 'user_ids': [ids['rita']]}]})[0], 200)
            self.assertEqual(self.refused(rita, text, pipeline=None), viewer)
            # a column kept from a person is not there for them, in the same words as one that does not exist: no word of the pipeline or of a repeat
            self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'order_line', 'column': 'amount', 'visible_to': [ids['ann']]})[0], 200)
            status, hidden = self.query(vera, text)
            status_none, missing = self.query(vera, 'SELECT sum(l.nothing_here) FROM (l:订单行)')
            self.assertEqual((status, hidden['error']), (status_none, missing['error'].replace('nothing_here', 'amount')))
            self.assertNotIn(P1, json.dumps(hidden, ensure_ascii=False))

    def test_the_english_refusal_is_english_even_when_a_type_is_called_order(self):
        with self.service() as (base, out):
            team = self.world(base, spec(), line_type('amount'))
            self.typed(team, {'english_name': 'order', 'name': '订单', 'dataset': 'orders', 'key': ['order_id'], 'properties': [{'column': 'order_id'}, {'column': 'amount'}]})
            said = self.refused(team['ann'], 'SELECT sum(l.amount) FROM (l:订单行)', headers={'Accept-Language': 'en'})
            self.assertIn('one row per order', said)
            self.assertNotIn('订单', said.replace(P1, ''))


if __name__ == '__main__':
    unittest.main()
