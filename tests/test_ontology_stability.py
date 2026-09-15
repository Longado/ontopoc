import unittest

from ontology_poc_generator.ontology_stability import STABILITY_RUNS, stability_of


def ontology(types, relations, status='auto_built_verified'):
    return {'status': status,
            'object_types': [{'key': k, 'label': label, 'populated_from': [{'source': src, 'identity': {'id': field}}]} for k, label, src, field in types],
            'relations': [{'key': k, 'from': a, 'to': b} for k, a, b in relations]}


CUSTOMER, ORDER, ENGINEER = ('customer', '客户', '客户', '客户编号'), ('order', '订单', '订单', '订单号'), ('engineer', '售后工程师', '工单', '负责工程师')
FIRST = ontology([CUSTOMER, ORDER], [('order_customer', 'order', 'customer')])


class StabilityTests(unittest.TestCase):
    def test_three_runs_are_the_product_choice(self):
        self.assertEqual(STABILITY_RUNS, 3)

    def test_each_type_and_relation_of_the_shown_run_counts_the_runs_that_have_it(self):
        renamed = ontology([('client', '顾客', '客户', '客户编号'), ORDER], [('belongs', 'order', 'client')])
        extra = ontology([CUSTOMER, ORDER, ENGINEER], [('order_customer', 'order', 'customer'), ('ticket_engineer', 'order', 'engineer')])
        result = stability_of(FIRST, [renamed, extra])
        self.assertEqual((result['runs'], result['failed']), (3, 0))
        self.assertEqual(result['types'], {'customer': 3, 'order': 3})
        self.assertEqual(result['relations'], {'order_customer': 3})
        self.assertEqual(result['elsewhere']['types'], [{'label': '售后工程师', 'count': 1}])
        self.assertEqual(result['elsewhere']['relations'], [{'label': '订单 — 售后工程师', 'count': 1}])

    def test_something_missing_from_the_shown_run_but_in_both_others_counts_two(self):
        with_engineer = ontology([CUSTOMER, ORDER, ENGINEER], [('order_customer', 'order', 'customer')])
        result = stability_of(FIRST, [with_engineer, with_engineer])
        self.assertEqual(result['elsewhere']['types'], [{'label': '售后工程师', 'count': 2}])

    def test_runs_that_did_not_pass_verification_are_left_out_and_counted(self):
        blocked = ontology([CUSTOMER], [], status='blocked')
        result = stability_of(FIRST, [blocked, FIRST])
        self.assertEqual((result['runs'], result['failed']), (2, 1))
        self.assertEqual(result['types'], {'customer': 2, 'order': 2})


if __name__ == '__main__':
    unittest.main()
