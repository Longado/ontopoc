"""A relation's cardinality is written with its direction, in the objects' own names: how many of the "to" end one
"from" object reaches (most_from) and how many "from" objects one "to" object has (most_to)."""
import copy
import unittest

from ontology_poc_generator import mcp_server
from tests.test_ontology_server import PROPOSAL


class Session(mcp_server.LocalService):
    def __init__(self, most_from, most_to, labels=('订单', '客户'), card=True):
        ontology = copy.deepcopy(PROPOSAL)
        for t, label in zip(ontology['object_types'], labels):
            t['label'] = label
        # the handover form's own string says one_to_many whenever either end has more than one, whichever end it is
        cards = [{'key': 'order_customer', 'from': 'order', 'to': 'customer', 'cardinality': 'one_to_many',
                  'most_from': most_from, 'most_to': most_to}] if card else []
        self.data = {'saved_as': 'r.json', 'ontology': ontology, 'confirmation': None, 'evaluation': {'handover': {'relations': cards}}}

    def request(self, path, payload=None):
        return self.data


def relation(most_from, most_to, **kw):
    [r] = mcp_server.list_relations(Session(most_from, most_to, **kw), {'saved_as': 'r.json'})['relations']
    return r


class CardinalityTests(unittest.TestCase):
    def test_many_actions_to_one_award_reads_many_to_one_and_not_the_one_to_many_the_form_says(self):
        r = relation(1, 6, labels=('合同动作', '合同授标'))
        self.assertEqual(r['cardinality'], 'many_to_one')
        self.assertEqual(r['reads'], '多对一：一个合同授标最多对应 6 个合同动作，一个合同动作只对应一个合同授标')
        self.assertEqual((r['most_from'], r['most_to']), (1, 6))

    def test_one_order_reaching_several_customers_is_one_to_many(self):
        r = relation(3, 1)
        self.assertEqual(r['cardinality'], 'one_to_many')
        self.assertEqual(r['reads'], '一对多：一个订单最多对应 3 个客户，一个客户只对应一个订单')

    def test_one_each_way_is_one_to_one(self):
        r = relation(1, 1)
        self.assertEqual(r['cardinality'], 'one_to_one')
        self.assertEqual(r['reads'], '一对一：一个订单只对应一个客户，一个客户只对应一个订单')

    def test_several_each_way_is_many_to_many(self):
        r = relation(4, 6)
        self.assertEqual(r['cardinality'], 'many_to_many')
        self.assertEqual(r['reads'], '多对多：一个订单最多对应 4 个客户，一个客户最多对应 6 个订单')

    def test_a_relation_the_data_never_joins_says_so(self):
        r = relation(0, 0)
        self.assertIsNone(r['cardinality'])
        self.assertEqual(r['reads'], '没有连上')

    def test_a_run_without_the_handover_form_has_no_cardinality_to_read(self):
        r = relation(1, 1, card=False)
        self.assertEqual((r['cardinality'], r['reads'], r['most_from'], r['most_to']), (None, None, None, None))


if __name__ == '__main__':
    unittest.main()
