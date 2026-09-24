"""A person's "wrong" is a correction like any other: the confirmed reference keeps it, the next run of the same file
starts with it already judged wrong, and the page is told which of them the model has proposed again."""
import base64
import copy
import unittest

from ontology_poc_generator.ontology_confirm import confirmed_reference, prefill_from_reference
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, PROPOSAL, OntologyServerTests

DECISIONS = {'types': {'order': {'verdict': 'ok', 'label': '销售订单'}, 'customer': {'verdict': 'wrong'}},
             'relations': {'order_customer': {'verdict': 'wrong'}}}


class ReferenceTests(unittest.TestCase):
    def test_the_reference_keeps_what_was_judged_wrong_with_what_it_was_read_from(self):
        reference = confirmed_reference(copy.deepcopy(PROPOSAL), DECISIONS)
        self.assertEqual([t['label'] for t in reference['object_types']], ['销售订单'])
        self.assertEqual([(t['key'], t['label'], t['populated_from'][0]['source']) for t in reference['rejected_types']],
                         [('customer', '客户', 'orders')])
        self.assertEqual([(r['from'], r['to']) for r in reference['rejected_relations']], [('order', 'customer')])

    def test_the_next_run_starts_with_that_object_already_judged_wrong(self):
        reference = confirmed_reference(copy.deepcopy(PROPOSAL), DECISIONS)
        suggested = prefill_from_reference(copy.deepcopy(PROPOSAL), reference)
        self.assertEqual(suggested['types']['customer'], {'verdict': 'wrong'})
        self.assertEqual(suggested['types']['order'], {'verdict': 'ok', 'label': '销售订单'})
        self.assertEqual(suggested['relations']['order_customer'], {'verdict': 'wrong'})
        self.assertEqual(suggested['returned'], ['客户'])   # the model proposed again what the person had thrown out

    def test_nothing_is_returned_when_the_model_leaves_it_out_this_time(self):
        reference = confirmed_reference(copy.deepcopy(PROPOSAL), DECISIONS)
        without = {**copy.deepcopy(PROPOSAL), 'object_types': [t for t in PROPOSAL['object_types'] if t['key'] == 'order'], 'relations': []}
        suggested = prefill_from_reference(without, reference)
        self.assertEqual(suggested['returned'], [])
        self.assertEqual(list(suggested['types']), ['order'])

    def test_an_old_reference_without_the_lists_still_reads(self):
        old = confirmed_reference(copy.deepcopy(PROPOSAL), DECISIONS)
        old.pop('rejected_types'), old.pop('rejected_relations')
        suggested = prefill_from_reference(copy.deepcopy(PROPOSAL), old)
        self.assertEqual((list(suggested['types']), suggested['returned']), (['order'], []))


class ServerTests(unittest.TestCase):
    def test_a_rerun_of_the_file_carries_the_correction_and_names_what_came_back(self):
        upload = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', upload)
            self.assertEqual(call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': DECISIONS})[0], 200)
            _, again = call(base, '/api/ontology/build', upload)
        suggested = again['evaluation']['reference']['suggested']
        self.assertEqual(suggested['types']['customer'], {'verdict': 'wrong'})
        self.assertEqual(suggested['returned'], ['客户'])


if __name__ == '__main__':
    unittest.main()
