"""Lists and lookups meeting a figure a join repeated. The lines of an order carry their order's amount once per line (tests.test_fan_sum): adding that column
up is refused. A list or a lookup adds nothing up: it shows each line as it is stored, its order's amount on it, and is answered. A list written beside a sum
of the repeated figure does not make the sum answerable: it is refused exactly as the sum alone is."""
import json
import unittest

from tests.test_fan_sum import LINE_PIPELINE, LINE_SPEC, LINE_TYPE, LINES, ORDERS, PER_LINE, FanSumTests, asks
from tests.test_workspace_questions import AskModel

AMOUNT = {o['order_id']: o['amount'] for o in ORDERS}


def reply(query):
    return {'reasoning': 'test', 'query': query, 'definitions_used': []}


def cells(body, *columns):
    objects = body['answer']['objects']
    at = [[c['column'] for c in objects['columns']].index(name) for name in columns]
    return [tuple(str(row[i]) for i in at) for row in objects['rows']]


def load_tests(loader, standard, pattern):
    return unittest.TestSuite(ListsOnARepeatedFigure(name) for name in vars(ListsOnARepeatedFigure) if name.startswith('test_'))


class ListsOnARepeatedFigure(FanSumTests):
    def world(self, base):
        team = self.team(base)
        self.pipeline(team, LINE_PIPELINE, LINE_SPEC)
        self.typed(team, LINE_TYPE)
        return team

    def ask(self, client, model, query):
        model.item = reply(query)
        status, body = client.post('/api/workspace/ask', {'question': '订单行有哪些？'})
        self.assertEqual(status, 200, body)
        return body

    def test_a_list_shows_each_line_with_its_orders_amount_and_adds_nothing_up(self):
        model = AskModel(reply({'start': 'order_line', 'where': [], 'list': {}}))
        with self.service(gateway=model) as (base, out):
            ann = self.world(base)['ann']
            body = self.ask(ann, model, {'start': 'order_line', 'where': [], 'list': {'properties': ['order_id', 'amount']}})
            self.assertEqual((body['status'], body['answer']['total']), ('answered', len(LINES)), body)
            self.assertEqual(dict(cells(body, 'line_id', 'amount')), {l['line_id']: AMOUNT[l['order_id']] for l in LINES})   # the stored rows: O1's 100 is on both of its lines
            self.assertNotIn(str(PER_LINE), json.dumps(body['answer'], ensure_ascii=False))   # no total of the repeated figure anywhere in the answer
            self.assertNotIn('refusal', body)

    def test_a_lookup_shows_one_line_with_its_orders_amount(self):
        model = AskModel(reply({'start': 'order_line', 'lookup': {'line_id': 'L2'}}))
        with self.service(gateway=model) as (base, out):
            ann = self.world(base)['ann']
            body = self.ask(ann, model, {'start': 'order_line', 'lookup': {'line_id': 'L2'}})
            self.assertEqual((body['status'], body['answer']['total']), ('answered', 1), body)
            self.assertEqual(cells(body, 'line_id', 'amount'), [('L2', '100')])

    def test_a_list_beside_a_sum_of_the_repeated_figure_is_refused_as_the_sum_alone_is(self):
        alone = asks('order_line', 'amount')['query']
        model = AskModel(reply(alone))
        with self.service(gateway=model) as (base, out):
            ann = self.world(base)['ann']
            plain = self.ask(ann, model, alone)
            beside = self.ask(ann, model, {**alone, 'list': {}})
            self.refused_naming(beside, LINE_PIPELINE, PER_LINE)
            self.assertEqual((beside['status'], beside['reason'], beside['refusal']), (plain['status'], plain['reason'], plain['refusal']))
            self.assertNotIn('objects', beside.get('answer') or {})   # and no rows go out with the refusal
            looked = self.ask(ann, model, {**alone, 'lookup': {'line_id': 'L1'}})
            self.assertNotEqual(looked['status'], 'answered', looked)   # a lookup beside an aggregate is refused, as on main
