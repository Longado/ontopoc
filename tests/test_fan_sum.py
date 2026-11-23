"""A figure a join repeated, added up by a question. Orders (one amount each) are joined to their lines in a pipeline: every line row carries its order's
amount, so adding that column up counts an order once per line. The service is driven end to end: tables uploaded, the pipeline put forward, confirmed and
run, a type on its output confirmed, then the sum asked in Q&A (a scripted model reply), in OntoPoc Query and through the MCP tool an outside agent uses.

Three orders, 100 + 50 + 30 = 180; O1 has two lines, so the lines carry 100 + 100 + 50 + 30 = 280. A question that answers 280 for "the order amount" is the
wrong number this file guards against: a sum or an average of a column the pipeline marked as repeated by a join is refused, naming the pipeline."""
import json
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
        shown = bob.get(f'{PIPELINES}/{quote(name)}')[1]
        status, body = bob.post(f'{PIPELINES}/confirm', {'id': name, 'version': shown['version'], 'seen': {'inputs': shown['inputs_now']}})
        self.assertEqual(status, 200, body)
        status, run = ann.post(f'{PIPELINES}/run', {'id': name})
        self.assertEqual((status, run.get('status')), (200, 'success'), run)
        return run

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


if __name__ == '__main__':
    unittest.main()
