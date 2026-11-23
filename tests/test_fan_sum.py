"""A figure a join repeated, added up by a question. Orders (one amount each) are joined to their lines in a pipeline: every line row carries its order's
amount, so adding that column up counts an order once per line. The service is driven end to end: tables uploaded, the pipeline put forward, confirmed and
run, a type on its output confirmed, then the sum asked in Q&A (a scripted model reply), in OntoPoc Query and through the MCP tool an outside agent uses.

Three orders, 100 + 50 + 30 = 180; O1 has two lines, so the lines carry 100 + 100 + 50 + 30 = 280. A question that answers 280 for "the order amount" is the
wrong number this file guards against: a sum or an average of a column the pipeline marked as repeated by a join is refused, naming the pipeline."""
import json
import time
import unittest
from urllib.parse import quote

from tests.test_agent_access import AgentCase
from tests.test_object_relations import table_csv
from tests.test_workspace_questions import AskModel

ORDERS = [{'order_id': 'O1', 'customer': 'C1', 'amount': '100'}, {'order_id': 'O2', 'customer': 'C1', 'amount': '50'}, {'order_id': 'O3', 'customer': 'C2', 'amount': '30'}]
LINES = [{'line_id': 'L1', 'order_id': 'O1', 'product': 'P1'}, {'line_id': 'L2', 'order_id': 'O1', 'product': 'P2'},
         {'line_id': 'L3', 'order_id': 'O2', 'product': 'P1'}, {'line_id': 'L4', 'order_id': 'O3', 'product': 'P3'}]
TRUE_TOTAL = sum(int(o['amount']) for o in ORDERS)                                                         # 180: each order once
PER_LINE = sum(int(next(o for o in ORDERS if o['order_id'] == l['order_id'])['amount']) for l in LINES)   # 280: each order once per line
PIPELINES = '/api/workspace/pipelines'
FAN_NOTE = '含重复计算：关联后一行变多行'

# case A, the one read in the code: the lines with their order's amount, one row per line
LINE_PIPELINE = '订单行带金额'
LINE_SPEC = {'steps': [{'id': 'l', 'type': 'input', 'dataset': 'lines'}, {'id': 'o', 'type': 'input', 'dataset': 'orders'},
                       {'id': 'j', 'type': 'join', 'left': 'l', 'right': 'o', 'how': 'left', 'on': [{'left': 'order_id', 'right': 'order_id'}]},
                       {'id': 'out', 'type': 'output', 'from': 'j', 'name': 'line_amounts', 'key': {'columns': ['line_id']}}]}
LINE_TYPE = {'english_name': 'order_line', 'name': '订单行', 'dataset': 'line_amounts', 'key': ['line_id'],
             'properties': [{'column': 'line_id'}, {'column': 'order_id'}, {'column': 'customer'}, {'column': 'amount'}]}

# case B: the pipeline adds the repeated amount up per customer (C1: 100 + 100 + 50 = 250, not 150), and the run marks that column
TOTAL_PIPELINE = '客户金额合计'
TOTAL_SPEC = {'steps': [{'id': 'o', 'type': 'input', 'dataset': 'orders'}, {'id': 'l', 'type': 'input', 'dataset': 'lines'},
                        {'id': 'j', 'type': 'join', 'left': 'o', 'right': 'l', 'how': 'left', 'on': [{'left': 'order_id', 'right': 'order_id'}]},
                        {'id': 'g', 'type': 'transform', 'from': 'j', 'operators': [{'op': 'aggregate', 'group_by': ['customer'], 'aggregations': [{'fn': 'sum', 'column': 'amount', 'as': 'total'}]}]},
                        {'id': 'out', 'type': 'output', 'from': 'g', 'name': 'customer_totals', 'key': {'columns': ['customer']}}]}
TOTAL_TYPE = {'english_name': 'customer_total', 'name': '客户合计', 'dataset': 'customer_totals', 'key': ['customer'], 'properties': [{'column': 'customer'}, {'column': 'total'}]}


def asks(start, field, op='sum'):
    return {'reasoning': '把金额加起来', 'query': {'start': start, 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': field, 'op': op}}, 'definitions_used': []}


def counts(start):
    return {'reasoning': '数一数', 'query': {'start': start, 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None}, 'definitions_used': []}


def load_tests(loader, standard, pattern):
    """Only the tests written here (the agent case brings the signing tests' own)."""
    return unittest.TestSuite(FanSumTests(name) for name in vars(FanSumTests) if name.startswith('test_'))


class FanSumTests(AgentCase):
    def team(self, base):
        team = self.people(base, 'ann', 'bob')
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [table_csv('orders.csv', ORDERS), table_csv('lines.csv', LINES)]})[0], 200)
        return team

    def pipeline(self, team, name, spec):
        """Ann puts it forward, Bob confirms it, Ann runs it."""
        ann, bob = team['ann'], team['bob']
        status, body = ann.post(PIPELINES, {'name': name, 'description': '订单和订单行', 'spec': spec})
        self.assertEqual(status, 200, body)
        self.confirm_pipeline(bob, name)
        status, run = ann.post(f'{PIPELINES}/run', {'id': name})
        self.assertEqual((status, run.get('status')), (200, 'success'), run)
        return run

    def confirm_pipeline(self, bob, name):
        shown = bob.get(f'{PIPELINES}/{quote(name)}')[1]
        status, body = bob.post(f'{PIPELINES}/confirm', {'id': name, 'version': shown['version'], 'seen': {'inputs': shown['inputs_now']}})
        self.assertEqual(status, 200, body)

    def typed(self, team, t):
        ann, bob = team['ann'], team['bob']
        status, body = ann.post('/api/workspace/types', t)
        self.assertEqual(status, 200, body)
        shown = bob.get(f'/api/workspace/types/{t["english_name"]}')[1]
        status, body = bob.post('/api/workspace/types/confirm', {'id': t['english_name'], 'version': shown['version'], 'seen': shown['seen']})
        self.assertEqual(status, 200, body)
        return shown

    def refused_naming(self, body, pipeline, wrong):
        """Not the wrong number, and a refusal that names the pipeline (`reason` of a kept answer, `error` of a refused query)."""
        said = json.dumps(body, ensure_ascii=False)
        if wrong is not None:
            self.assertNotEqual(((body.get('answer') or {}).get('measure') or {}).get('value'), wrong, said)
        self.assertNotEqual(body.get('status'), 'answered', said)
        self.assertIn(pipeline, body.get('reason') or body.get('error') or '', said)   # Q&A keeps a refused answer; OntoPoc Query says it as an error (400)

    def test_the_sum_of_an_order_amount_on_order_lines_is_not_answered_as_one_amount_per_line(self):
        self.assertEqual((TRUE_TOTAL, PER_LINE), (180, 280))
        model = AskModel(asks('order_line', 'amount'))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.pipeline(team, LINE_PIPELINE, LINE_SPEC)
            ann = team['ann']
            shown = ann.get(f'/api/workspace/datasets/{quote("line_amounts")}')[1]
            self.assertEqual({c['name']: c.get('fan') for c in shown['columns']}, {'line_id': None, 'order_id': None, 'product': None, 'customer': None, 'amount': FAN_NOTE})   # the run marks the repeated amount, and only it
            self.typed(team, LINE_TYPE)
            status, body = ann.post('/api/workspace/ask', {'question': '订单金额合计是多少？'})
            self.assertEqual(status, 200, body)
            self.refused_naming(body, LINE_PIPELINE, PER_LINE)
            status, ran = ann.post('/api/workspace/query', {'text': 'SELECT sum(l.amount) FROM (l:订单行)'})
            self.refused_naming(ran, LINE_PIPELINE, PER_LINE)
            status, ran = ann.post('/api/workspace/query', {'text': 'SELECT avg(l.amount) FROM (l:订单行)'})
            self.refused_naming(ran, LINE_PIPELINE, PER_LINE / len(LINES))
            # a count of the line objects is not a sum of the repeated figure: it is answered
            model.item = counts('order_line')
            status, body = ann.post('/api/workspace/ask', {'question': '有多少订单行？'})
            self.assertEqual((body['status'], body['answer']['total']), ('answered', len(LINES)), body)

    def test_the_sum_of_a_total_the_pipeline_added_up_over_the_repeated_join_is_refused_in_q_and_a_query_and_mcp(self):
        model = AskModel(asks('customer_total', 'total'))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.pipeline(team, TOTAL_PIPELINE, TOTAL_SPEC)
            self.typed(team, TOTAL_TYPE)
            ann = team['ann']
            status, body = ann.post('/api/workspace/ask', {'question': '客户金额合计加起来是多少？'})
            self.assertEqual(status, 200, body)
            self.refused_naming(body, TOTAL_PIPELINE, PER_LINE)
            status, ran = ann.post('/api/workspace/query', {'text': 'SELECT sum(c.total) FROM (c:客户合计)'})
            self.refused_naming(ran, TOTAL_PIPELINE, PER_LINE)
            replies = self.mcp(base, self.token_for(team['admin'], 'ann')['token'], [('ontopoc_query', {'text': 'SELECT sum(c.total) FROM (c:客户合计)'})])
            said = json.dumps(replies[10], ensure_ascii=False)
            self.assertNotIn(str(PER_LINE), said)
            self.assertIn(TOTAL_PIPELINE, said)

    def relation(self, team, r):
        ann, bob = team['ann'], team['bob']
        status, body = ann.post('/api/workspace/relations', r)
        self.assertEqual(status, 200, body)
        detail = bob.get(f'/api/workspace/relations/{r["english_name"]}')[1]
        status, body = bob.post('/api/workspace/queue/confirm', {'element': f'relation:{r["english_name"]}', 'version': detail['version'], 'seen': detail['check']['signature']})
        self.assertEqual(status, 200, body)

    def chart(self, client, type_name, chart):
        return client.post('/api/workspace/explore/chart', {'query': {'type': type_name}, 'chart': chart})

    def test_derived_properties_group_totals_and_charts_that_add_up_or_average_the_repeated_amount_refuse_and_counts_still_answer(self):
        model = AskModel(asks('order_line', 'amount'))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.pipeline(team, LINE_PIPELINE, LINE_SPEC)
            self.pipeline(team, TOTAL_PIPELINE, TOTAL_SPEC)
            # confirming a type on the repeated amount is not blocked; the confirm screen says it, as for a total the pipeline added up
            self.assertEqual(ann.post('/api/workspace/types', LINE_TYPE)[0], 200)
            item = next(i for i in bob.get('/api/workspace/queue')[1]['items'] if i['element'] == 'objtype:order_line')
            self.assertIn((False, f'“amount”{FAN_NOTE}（只提醒，不拦着确认）'), [(l['ok'], l['text']) for l in item['lines']])
            shown = bob.get('/api/workspace/types/order_line')[1]
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order_line', 'version': shown['version'], 'seen': shown['seen']})[0], 200)
            self.typed(team, TOTAL_TYPE)
            self.relation(team, {'english_name': 'line_customer', 'name': '订单行属于客户', 'from': 'order_line', 'to': 'customer_total', 'cardinality': 'many_to_one',
                                 'from_column': 'customer', 'to_column': 'customer'})
            # a derived statistic that adds up or averages the repeated amount per customer is refused, naming the pipeline; a count of the lines is not
            stat = {'type': 'customer_total', 'english_name': 'line_amount', 'name': '行金额合计', 'kind': 'statistic', 'path': ['line_customer'], 'measure': {'column': 'amount'}, 'fn': 'sum'}
            for fn in ('sum', 'avg'):
                status, body = ann.post('/api/workspace/types/derived', {**stat, 'fn': fn})
                self.assertEqual(status, 409, body)
                self.assertIn(f'管道“{LINE_PIPELINE}”', body['error'])
            status, body = ann.post('/api/workspace/types/derived', {**stat, 'english_name': 'line_count', 'name': '订单行数', 'measure': {'column': None}, 'fn': 'count'})
            self.assertEqual(status, 200, body)
            # a derived function of the repeated amount is a copy of it: it can be confirmed, and adding it up is refused like the amount
            gross = {'type': 'order_line', 'english_name': 'gross', 'name': '含税金额', 'kind': 'function', 'expression': 'amount * 1.13'}
            self.assertEqual(ann.post('/api/workspace/types/derived', gross)[0], 200)
            line = next(d for d in bob.get('/api/workspace/types/order_line/derived')[1]['derived'] if d['id'] == 'gross')
            status, body = bob.post('/api/workspace/types/derived/confirm', {'type': 'order_line', 'english_name': 'gross', 'version': line['version'], 'seen': line['seen']})
            self.assertEqual(status, 200, body)
            model.item = asks('order_line', '含税金额')
            self.refused_naming(ann.post('/api/workspace/ask', {'question': '含税金额合计是多少？'})[1], LINE_PIPELINE, round(PER_LINE * 1.13, 2))
            # a total per group is refused too, in Q&A and in OntoPoc Query
            model.item = {**asks('order_line', 'amount'), 'query': {**asks('order_line', 'amount')['query'], 'group_by': [{'via': [], 'field': 'customer'}]}}
            self.refused_naming(ann.post('/api/workspace/ask', {'question': '每个客户的订单金额合计？'})[1], LINE_PIPELINE, None)
            status, ran = ann.post('/api/workspace/query', {'text': 'SELECT l.customer, sum(l.amount) AS 合计 FROM (l:订单行) GROUP BY l.customer'})
            self.assertEqual(status, 400, ran)
            self.assertIn(LINE_PIPELINE, ran['error'])
            # the explorer (and the boards drawn from it): a sum, an average or a statistics table of the amount or of the copy refuse; a max or a count does not
            for chart in ({'kind': 'number', 'measure': 'amount', 'fn': 'sum'}, {'kind': 'bar', 'group': 'customer', 'measure': 'amount', 'fn': 'avg'},
                          {'kind': 'table', 'measure': 'amount'}, {'kind': 'number', 'measure': 'derived:gross', 'fn': 'sum'}):
                status, body = self.chart(ann, 'order_line', chart)
                self.assertEqual(status, 400, (chart, body))
                self.assertIn(f'管道“{LINE_PIPELINE}”', body['error'])
            status, body = self.chart(ann, 'order_line', {'kind': 'number', 'measure': 'amount', 'fn': 'max'})
            self.assertEqual((status, body['value']), (200, 100))
            self.assertIn(f'“amount”{FAN_NOTE}', [l['line'] for l in body['standing']['lines']])
            status, body = self.chart(ann, 'order_line', {'kind': 'bar', 'group': 'customer', 'fn': 'count'})
            self.assertEqual((status, sum(i['value'] for i in body['groups'])), (200, len(LINES)), body)
            # an average in Q&A is refused as well
            model.item = asks('order_line', 'amount', 'average')
            self.refused_naming(ann.post('/api/workspace/ask', {'question': '订单金额平均是多少？'})[1], LINE_PIPELINE, PER_LINE / len(LINES))

    def test_the_mark_is_read_on_the_version_a_number_reads_so_a_board_card_and_a_checked_number_refuse_once_a_new_run_repeats_the_amount(self):
        one_line_each = [l for l in LINES if l['line_id'] != 'L2']   # every order on one line: nothing repeats yet
        with self.service(gateway=AskModel(asks('order_line', 'amount'))) as (base, out):
            team = self.people(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [table_csv('orders.csv', ORDERS), table_csv('lines.csv', one_line_each)]})[0], 200)
            self.pipeline(team, LINE_PIPELINE, LINE_SPEC)
            self.typed(team, LINE_TYPE)
            spec = {'components': [{'id': 'amount', 'title': '订单金额', 'query': {'type': 'order_line'}, 'chart': {'kind': 'number', 'measure': 'amount', 'fn': 'sum'}},
                                   {'id': 'card', 'title': '金额（查询）', 'text': 'SELECT sum(l.amount) FROM (l:订单行)', 'chart': {'kind': 'query'}},
                                   {'id': 'lines', 'title': '订单行数', 'text': 'SELECT count(l) FROM (l:订单行)', 'chart': {'kind': 'query'}}], 'filters': []}
            status, board = ann.post('/api/workspace/dashboards', {'name': '订单金额看板', 'spec': spec, 'scope': 'everyone'})
            self.assertEqual(status, 200, board)
            shown = {c['id']: c for c in ann.post('/api/workspace/dashboards/data', {'id': board['id']})[1]['components']}
            self.assertEqual((shown['amount']['result']['value'], shown['card']['result']['answer']['measure']['value']), (TRUE_TOTAL, TRUE_TOTAL))   # one line per order: right
            for component in ('amount', 'card'):
                status, made = bob.post('/api/workspace/checked', {'board': board['id'], 'component': component, 'note': '财务报表'})
                self.assertEqual((status, made['status']), (200, 'same'), made)
            # L2 arrives: O1 now has two lines, the run marks the amount on the new version, and the same cards refuse instead of showing 280
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [table_csv('lines.csv', LINES, target='lines', mode='overwrite')]})[0], 200)
            self.confirm_pipeline(bob, LINE_PIPELINE)   # its input moved: it is looked at again before it writes
            self.assertEqual(ann.post(f'{PIPELINES}/run', {'id': LINE_PIPELINE})[1]['status'], 'success')
            shown = bob.get('/api/workspace/types/order_line')[1]   # new data on a confirmed type waits for another look first
            status, again = bob.post('/api/workspace/types/confirm', {'id': 'order_line', 'version': shown['version'], 'seen': shown['seen']})
            self.assertEqual(status, 200, again)
            body = ann.post('/api/workspace/dashboards/data', {'id': board['id']})[1]
            shown = {c['id']: c for c in body['components']}
            said = json.dumps(body, ensure_ascii=False)
            self.assertNotIn(str(PER_LINE), said)
            for component in ('amount', 'card'):
                self.assertEqual(shown[component]['status'], 'unavailable', said)
                self.assertIn(LINE_PIPELINE, shown[component]['message'])
                self.assertEqual(shown[component]['check']['status'], 'refused', said)
            self.assertEqual((shown['lines']['status'], shown['lines']['result']['answer']['total']), ('ok', len(LINES)))   # a count of the line objects still answers
            status, refused = bob.post('/api/workspace/checked', {'board': board['id'], 'component': 'amount', 'note': '财务报表'})
            self.assertNotEqual(status, 200, refused)
            self.assertIn(LINE_PIPELINE, refused['error'])

    def test_a_needed_question_whose_answer_would_add_up_the_repeated_amount_comes_back_refused(self):
        with self.service(gateway=AskModel(asks('order_line', 'amount'))) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.pipeline(team, LINE_PIPELINE, LINE_SPEC)
            self.typed(team, LINE_TYPE)
            question = '订单金额合计是多少？'
            status, made = ann.post('/api/workspace/needed', {'question': question, 'expect': {'kind': 'number', 'value': PER_LINE}})
            self.assertEqual(status, 200, made)
            found = next(q for q in bob.get('/api/workspace/needed')[1]['questions'] if q['question'] == question)
            self.assertEqual(bob.post('/api/workspace/needed/confirm', {'id': found['id'], 'version': found['version']})[0], 200)
            status, body = bob.post('/api/workspace/needed/run', {'repeats': 1})
            self.assertEqual(status, 200, body)
            for _ in range(500):
                if body.get('running') is None:
                    break
                time.sleep(0.02)
                body = bob.get('/api/workspace/needed')[1]
            result = next(q for q in body['questions'] if q['question'] == question)['result']
            self.assertEqual((result['outcome'], result['distinct']), ('no_answer', [{'number': None, 'status': 'query_limit', 'times': 1}]), result)   # never "passes" on 280
            self.assertIn(LINE_PIPELINE, result['reason'])


if __name__ == '__main__':
    unittest.main()
