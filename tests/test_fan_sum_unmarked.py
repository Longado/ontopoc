"""The refusal of a sum over a figure a join repeated changes nothing for a column without that mark: every answer, refusal and stored row below is the one
main gave before the refusal existed (origin/main a9d6a76), recorded in golden/fan_sum_unmarked.json. This is a walk against main's own output, not the new
code with the check switched off.

The walk: orders and their lines; a pipeline joins the lines to the orders' customer (a text the join repeats, no number), types on the uploaded orders and on
the pipeline's lines, a relation, a derived statistic and a derived function; then sums, averages, group totals, counts and refusals through Q&A, OntoPoc Query
(in both languages), the explorer, a board, checked numbers and a needed-question run, and every row the file keeps. A second walk is the repeated-amount world
of tests/test_fan_sum.py: what it says about the columns there that carry no mark (a line's quantity, the count of lines, a median of the quantity) is main's
answer too. A third is a join that is one-to-one on today's data (one payment per order): nothing is copied, so its answers, charts and stored rows are main's. Times are
blanked: they are the only thing that may differ between two walks.

To record it again from main (only when an intended change to these routes lands), from the repository root with main's source at <main>/src:
ONTOPOC_RECORD_GOLDEN=1 PYTHONPATH=<main>/src python -m unittest tests.test_fan_sum_unmarked"""
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import unittest

from tests.test_fan_sum import LINE_PIPELINE, LINE_SPEC, ORDERS, PIPELINES, FanSumTests, asks, counts
from tests.test_object_relations import table_csv
from tests.test_workspace_questions import AskModel

GOLDEN = Path(__file__).parent / 'golden' / 'fan_sum_unmarked.json'
TIME = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(\+00:00|Z)?')
OWNER = re.compile(r'^[0-9a-f]{32}$')
LINES = [{'line_id': 'L1', 'order_id': 'O1', 'product': 'P1', 'qty': '2'}, {'line_id': 'L2', 'order_id': 'O1', 'product': 'P2', 'qty': '1'},
         {'line_id': 'L3', 'order_id': 'O2', 'product': 'P1', 'qty': '5'}, {'line_id': 'L4', 'order_id': 'O3', 'product': 'P3', 'qty': '3'}]
ROWS_SPEC = {'steps': [{'id': 'l', 'type': 'input', 'dataset': 'lines'}, {'id': 'o', 'type': 'input', 'dataset': 'orders'},
                       {'id': 'j', 'type': 'join', 'left': 'l', 'right': 'o', 'how': 'left', 'on': [{'left': 'order_id', 'right': 'order_id'}], 'right_columns': ['customer']},
                       {'id': 'out', 'type': 'output', 'from': 'j', 'name': 'line_rows', 'key': {'columns': ['line_id']}}]}
ORDER = {'english_name': 'order', 'name': '订单', 'dataset': 'orders', 'key': ['order_id'], 'properties': [{'column': 'order_id'}, {'column': 'customer'}, {'column': 'amount'}]}
LINE = {'english_name': 'line', 'name': '订单行', 'dataset': 'line_rows', 'key': ['line_id'],
        'properties': [{'column': 'line_id'}, {'column': 'order_id'}, {'column': 'customer'}, {'column': 'product'}, {'column': 'qty'}]}
RELATION = {'english_name': 'line_order', 'name': '订单行属于订单', 'from': 'line', 'to': 'order', 'cardinality': 'many_to_one', 'from_column': 'order_id', 'to_column': 'order_id'}
QTY_SUM = {'type': 'order', 'english_name': 'qty_sum', 'name': '件数合计', 'kind': 'statistic', 'path': ['line_order'], 'measure': {'column': 'qty'}, 'fn': 'sum'}
DOUBLE = {'type': 'line', 'english_name': 'double_qty', 'name': '双倍件数', 'kind': 'function', 'expression': 'qty * 2'}
SKIPPED = ('user', 'session', 'api_token', 'sign_in_limit', 'setting', 'llm_cache', 'demo_guest', 'sqlite_sequence')   # who signed in and their secrets: random each walk
ENGLISH = {'headers': {'Accept-Language': 'en'}}
PAYMENTS = [{'payment_id': 'Y1', 'order_id': 'O1', 'paid': '100'}, {'payment_id': 'Y2', 'order_id': 'O2', 'paid': '40'}, {'payment_id': 'Y3', 'order_id': 'O3', 'paid': '30'}]
PAID_SPEC = {'steps': [{'id': 'o', 'type': 'input', 'dataset': 'orders'}, {'id': 'y', 'type': 'input', 'dataset': 'payments'},
                       {'id': 'j', 'type': 'join', 'left': 'o', 'right': 'y', 'how': 'left', 'on': [{'left': 'order_id', 'right': 'order_id'}]},
                       {'id': 'out', 'type': 'output', 'from': 'j', 'name': 'paid_orders', 'key': {'columns': ['order_id']}}]}
PAID = {'english_name': 'paid_order', 'name': '付款订单', 'dataset': 'paid_orders', 'key': ['order_id'],
        'properties': [{'column': 'order_id'}, {'column': 'customer'}, {'column': 'amount'}, {'column': 'paid'}]}


def grouped(start, field, by, op='sum'):
    item = asks(start, field, op)
    return {**item, 'query': {**item['query'], 'group_by': [{'via': [], 'field': by}]}}


def blank(value):
    """Times, durations, the clock of the question budget and the random owner of a needed run: what two walks never share."""
    if isinstance(value, str):
        return OWNER.sub('<owner>', TIME.sub('<time>', value))
    if isinstance(value, (list, tuple)):
        return [blank(v) for v in value]
    if isinstance(value, dict):
        return {k: '<ms>' if k in ('duration_ms', 'took_ms') else '<clock>' if k == 'at' and isinstance(v, float) else blank(v) for k, v in value.items()}
    return value


def stored(out: Path) -> dict:
    """Every row the walk left in the file, table by table (the data tables of the datasets too), but the accounts and their sessions."""
    conn = sqlite3.connect(out / 'workspace.sqlite')
    try:
        found = {}
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall():
            if name in SKIPPED:
                continue
            cursor = conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid' if name != 'current_dataset' else f'SELECT * FROM "{name}" ORDER BY name')
            names = [c[0] for c in cursor.description]
            found[name] = [dict(zip(names, (json.loads(v) if isinstance(v, str) and v[:1] in '[{' and _json(v) else v for v in r))) for r in cursor]
        return found
    finally:
        conn.close()


def _json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except ValueError:
        return False


def load_tests(loader, standard, pattern):
    return unittest.TestSuite(UnmarkedTests(name) for name in vars(UnmarkedTests) if name.startswith('test_'))


class UnmarkedTests(FanSumTests):
    def ask(self, model, client, item, question):
        model.item = item
        return client.post('/api/workspace/ask', {'question': question})

    def walk(self) -> dict:
        seen = {}
        model = AskModel(asks('order', 'amount'))
        with self.service(gateway=model) as (base, out):
            team = self.people(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            seen['upload'] = ann.post('/api/workspace/datasets/upload', {'files': [table_csv('orders.csv', ORDERS), table_csv('lines.csv', LINES)]})
            seen['run'] = self.pipeline(team, '订单行客户', ROWS_SPEC)
            seen['line_rows'] = ann.get('/api/workspace/datasets/line_rows')
            self.typed(team, ORDER)
            self.typed(team, LINE)
            self.relation(team, RELATION)
            for d in (QTY_SUM, DOUBLE):
                seen[f'derived_{d["english_name"]}'] = ann.post('/api/workspace/types/derived', d)
                line = next(x for x in bob.get(f'/api/workspace/types/{d["type"]}/derived')[1]['derived'] if x['id'] == d['english_name'])
                seen[f'derived_confirm_{d["english_name"]}'] = bob.post('/api/workspace/types/derived/confirm', {'type': d['type'], 'english_name': d['english_name'], 'version': line['version'], 'seen': line['seen']})
            seen['ask'] = {
                'sum_amount': self.ask(model, ann, asks('order', 'amount'), '订单金额合计是多少？'),
                'avg_amount': self.ask(model, ann, asks('order', 'amount', 'average'), '订单金额平均是多少？'),
                'by_customer': self.ask(model, ann, grouped('order', 'amount', 'customer'), '每个客户的订单金额合计？'),
                'derived_stat': self.ask(model, ann, asks('order', '件数合计'), '件数合计加起来是多少？'),
                'derived_function': self.ask(model, ann, asks('line', '双倍件数'), '双倍件数合计是多少？'),
                'count_lines': self.ask(model, ann, counts('line'), '有多少订单行？'),
                'unknown': self.ask(model, ann, asks('order', 'profit'), '利润合计是多少？'),
                'over_lines': self.ask(model, ann, {**asks('order', 'amount'), 'query': {**asks('order', 'amount')['query'], 'group_by': [{'via': ['line_order'], 'field': 'product'}]}},
                                       '每个产品的订单金额合计？')}
            model.item = asks('line', 'qty')
            seen['ask']['english'] = ann.post('/api/workspace/ask', {'question': 'What is the total quantity?'}, **ENGLISH)
            seen['query'] = [ann.post('/api/workspace/query', {'text': text}, **more) for text, more in (
                ('SELECT sum(o.amount) FROM (o:订单)', {}), ('SELECT l.customer, avg(l.qty) AS 平均 FROM (l:订单行) GROUP BY l.customer', {}),
                ('SELECT sum(o.利润) FROM (o:订单)', {}), ('SELECT sum(l.qty) FROM (l:订单行)', ENGLISH), ('SELECT sum(o.件数合计) FROM (o:订单)', {}))]
            seen['charts'] = [self.chart(ann, t, c) for t, c in (
                ('order', {'kind': 'number', 'measure': 'amount', 'fn': 'sum'}), ('line', {'kind': 'bar', 'group': 'customer', 'measure': 'qty', 'fn': 'sum'}),
                ('line', {'kind': 'table', 'measure': 'qty'}), ('line', {'kind': 'number', 'measure': 'derived:double_qty', 'fn': 'sum'}),
                ('order', {'kind': 'number', 'measure': 'derived:qty_sum', 'fn': 'avg'}), ('line', {'kind': 'pie', 'group': 'product', 'measure': 'qty', 'fn': 'avg'}))]
            spec = {'components': [{'id': 'amount', 'title': '订单金额', 'query': {'type': 'order'}, 'chart': {'kind': 'number', 'measure': 'amount', 'fn': 'sum'}},
                                   {'id': 'qty', 'title': '件数（查询）', 'text': 'SELECT sum(l.qty) FROM (l:订单行)', 'chart': {'kind': 'query'}},
                                   {'id': 'lines', 'title': '订单行数', 'text': 'SELECT count(l) FROM (l:订单行)', 'chart': {'kind': 'query'}}], 'filters': []}
            status, board = ann.post('/api/workspace/dashboards', {'name': '订单看板', 'spec': spec, 'scope': 'everyone'})
            seen['board'] = (status, board)
            seen['checked'] = [bob.post('/api/workspace/checked', {'board': board['id'], 'component': c, 'note': '财务报表'}) for c in ('amount', 'qty')]
            seen['checked_answer'] = ann.post('/api/workspace/checked', {'question': seen['ask']['sum_amount'][1]['id'], 'note': '周报'})
            seen['board_data'] = ann.post('/api/workspace/dashboards/data', {'id': board['id']})
            model.item = asks('order', 'amount')
            seen['needed_write'] = ann.post('/api/workspace/needed', {'question': '订单金额合计是多少？', 'expect': {'kind': 'number', 'value': 180}})
            found = next(q for q in bob.get('/api/workspace/needed')[1]['questions'])
            seen['needed_confirm'] = bob.post('/api/workspace/needed/confirm', {'id': found['id'], 'version': found['version']})
            body = bob.post('/api/workspace/needed/run', {'repeats': 1})[1]
            for _ in range(500):
                if body.get('running') is None:
                    break
                time.sleep(0.02)
                body = bob.get('/api/workspace/needed')[1]
            seen['needed'] = body
            seen['history'] = ann.get('/api/workspace/ask')
            seen['stored'] = stored(out)
        # the repeated-amount world: its amount carries the mark (or, on main, nothing); what is said about its other columns is main's
        model = AskModel(counts('order_line'))
        with self.service(gateway=model) as (base, out):
            team = self.people(base, 'ann', 'bob')
            ann = team['ann']
            ann.post('/api/workspace/datasets/upload', {'files': [table_csv('orders.csv', ORDERS), table_csv('lines.csv', LINES)]})
            self.pipeline(team, LINE_PIPELINE, LINE_SPEC)
            self.typed(team, {'english_name': 'order_line', 'name': '订单行', 'dataset': 'line_amounts', 'key': ['line_id'],
                              'properties': [{'column': 'line_id'}, {'column': 'customer'}, {'column': 'qty'}, {'column': 'amount'}]})
            seen['marked_world'] = {
                'count': self.ask(model, ann, counts('order_line'), '有多少订单行？'),
                'sum_qty': self.ask(model, ann, asks('order_line', 'qty'), '件数合计是多少？'),
                'qty_by_customer': self.ask(model, ann, grouped('order_line', 'qty', 'customer', 'average'), '每个客户平均件数？'),
                'query': ann.post('/api/workspace/query', {'text': 'SELECT l.customer, sum(l.qty) AS 合计 FROM (l:订单行) GROUP BY l.customer'}),
                'chart': self.chart(ann, 'order_line', {'kind': 'number', 'measure': 'qty', 'fn': 'sum'}),
                'count_chart': self.chart(ann, 'order_line', {'kind': 'bar', 'group': 'customer', 'fn': 'count'}),
                'median_qty': self.chart(ann, 'order_line', {'kind': 'number', 'measure': 'qty', 'fn': 'median'}),
                'qty_table': self.chart(ann, 'order_line', {'kind': 'table', 'measure': 'qty'})}
        # a join that is one-to-one on today's data (one payment per order): nothing is copied, so every figure of it is main's, and so is every row it leaves
        model = AskModel(asks('paid_order', 'paid'))
        with self.service(gateway=model) as (base, out):
            team = self.people(base, 'ann', 'bob')
            ann = team['ann']
            seen['one_to_one_upload'] = ann.post('/api/workspace/datasets/upload', {'files': [table_csv('orders.csv', ORDERS), table_csv('payments.csv', PAYMENTS)]})
            seen['one_to_one_run'] = self.pipeline(team, '订单付款', PAID_SPEC)
            self.typed(team, PAID)
            seen['one_to_one'] = {
                'sum_paid': self.ask(model, ann, asks('paid_order', 'paid'), '付款合计是多少？'),
                'avg_amount': self.ask(model, ann, asks('paid_order', 'amount', 'average'), '订单金额平均是多少？'),
                'query': ann.post('/api/workspace/query', {'text': 'SELECT p.customer, sum(p.paid) AS 合计 FROM (p:付款订单) GROUP BY p.customer'}),
                'median': self.chart(ann, 'paid_order', {'kind': 'number', 'measure': 'amount', 'fn': 'median'}),
                'histogram': self.chart(ann, 'paid_order', {'kind': 'histogram', 'measure': 'paid'}),
                'page': ann.get('/api/workspace/datasets/paid_orders')}
            seen['one_to_one_stored'] = stored(out)
        return blank(json.loads(json.dumps(seen, ensure_ascii=False)))

    def as_main(self, walked: dict) -> dict:
        """The walk with exactly what this change adds to the file taken out, after checking it is that and nothing more. Main's file has neither:
        - column_fan_measured, one row per version a pipeline wrote whose copies were measured (here the one version each walk's pipeline wrote);
        - in the first walk, the mark on `customer`: a text column of the orders' side, which the join copies (O1 is on two lines). The mark is kept for
          every type, so that no cast or numeric reading escapes it; it shows no note (pages are main's, compared above), and nothing here aggregates it.
        Nothing else may differ: every answer, refusal, page and every other row is main's."""
        out = json.loads(json.dumps(walked))
        line_rows = next(d['id'] for d in out['stored']['dataset'] if d['name'] == 'line_rows')
        self.assertEqual(out['stored'].pop('column_fan_measured'), [{'dataset_id': line_rows}])
        self.assertEqual(out['stored']['column_fan'], [{'dataset_id': line_rows, 'column_name': 'customer', 'origin': '订单行客户'}])
        out['stored']['column_fan'] = []
        paid = next(d['id'] for d in out['one_to_one_stored']['dataset'] if d['name'] == 'paid_orders')
        self.assertEqual(out['one_to_one_stored'].pop('column_fan_measured'), [{'dataset_id': paid}])
        self.assertEqual(out['one_to_one_stored']['column_fan'], [])
        return out

    def test_without_the_mark_every_answer_refusal_and_stored_row_is_main_s(self):
        walked = self.walk()
        if os.environ.get('ONTOPOC_RECORD_GOLDEN'):
            GOLDEN.write_text(json.dumps(walked, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        if not os.environ.get('ONTOPOC_RECORD_GOLDEN'):
            walked = self.as_main(walked)
        for part in golden:
            self.assertEqual(walked[part], golden[part], part)
        self.assertEqual(set(walked), set(golden))
        # the walk reached what it is about: real numbers, real refusals, a needed run that passed
        self.assertEqual(walked['ask']['sum_amount'][1]['answer']['measure']['value'], 180)
        self.assertEqual(walked['ask']['unknown'][1]['status'], 'ontology_gap')
        self.assertEqual(walked['charts'][0][1]['value'], 180)
        self.assertEqual(next(iter(walked['needed']['questions']))['result']['outcome'], 'passes')
        self.assertEqual(walked['stored']['column_fan'], [])   # after as_main: the text mark was checked there and taken out
        self.assertEqual(walked['one_to_one']['sum_paid'][1]['answer']['measure']['value'], 170)
        self.assertEqual(walked['one_to_one_stored']['column_fan'], [])


if __name__ == '__main__':
    unittest.main()
