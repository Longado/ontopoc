import base64
import unittest

from ontology_poc_generator.ontology_compare import compare_ontologies, parse_reference
from ontology_poc_generator.ontology_confirm import ConfirmError, confirmed_reference
from tests.test_company_ontology import PROPOSAL
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_jobs import wait
from tests.test_ontology_server import CSV, OntologyServerTests

DECISIONS = {'types': {'customer': {'verdict': 'ok', 'label': '客户主体'}, 'order': {'verdict': 'ok'}},
             'relations': {'order_customer': {'verdict': 'ok'}}, 'added': ['发票']}


class ConfirmedReferenceTests(unittest.TestCase):
    def test_kept_items_renames_and_additions_become_a_reference(self):
        ref = confirmed_reference(PROPOSAL, DECISIONS)
        self.assertEqual([t['label'] for t in ref['object_types']], ['客户主体', '订单', '发票'])
        self.assertEqual(ref['relations'], [{'key': 'order_customer', 'from': 'order', 'to': 'customer'}])
        diff = compare_ontologies(parse_reference(ref), PROPOSAL)
        self.assertEqual(diff['types']['matched'], [['客户主体', '客户'], ['订单', '订单']])   # renamed, still matched by table and identity
        self.assertEqual(diff['types']['only_reference'], ['发票'])

    def test_wrong_and_unjudged_items_are_left_out(self):
        ref = confirmed_reference(PROPOSAL, {'types': {'customer': {'verdict': 'wrong'}, 'order': {'verdict': 'ok'}}, 'relations': {}, 'added': []})
        self.assertEqual([t['label'] for t in ref['object_types']], ['订单'])
        self.assertEqual(ref['relations'], [])

    def test_decisions_that_do_not_fit_the_ontology_are_refused(self):
        for decisions, message in (
                ({'types': {'invoice': {'verdict': 'ok'}}}, 'invoice'),
                ({'types': {'order': {'verdict': 'maybe'}}}, 'verdict'),
                ({'types': {'order': {'verdict': 'ok', 'label': 'x' * 41}}}, '40'),
                ({'types': {'order': {'verdict': 'ok'}, 'customer': {'verdict': 'wrong'}}, 'relations': {'order_customer': {'verdict': 'ok'}}}, '客户'),
                ({'types': {'order': {'verdict': 'ok'}}, 'added': ['订单']}, '订单'),
                ({'types': {}, 'relations': {}, 'added': []}, '至少')):
            with self.subTest(message=message), self.assertRaisesRegex(ConfirmError, message):
                confirmed_reference(PROPOSAL, decisions)


class ConfirmServerTests(unittest.TestCase):
    def test_confirming_compares_now_and_the_next_upload_of_the_same_file_is_compared_on_its_own(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            upload = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}
            _, first = call(base, '/api/ontology/build', upload)
            keys = {'types': {t['key']: {'verdict': 'ok'} for t in first['ontology']['object_types']},
                    'relations': {r['key']: {'verdict': 'ok'} for r in first['ontology']['relations']}, 'added': ['发票']}
            status, confirmed = call(base, '/api/ontology/confirm', {'saved_as': first['saved_as'], 'decisions': keys})
            self.assertEqual(status, 200, confirmed)
            self.assertEqual(confirmed['confirmation']['decisions'], keys)
            ref = confirmed['evaluation']['reference']
            self.assertTrue(ref['confirmed'])
            self.assertEqual(ref['diff']['types']['only_reference'], ['发票'])
            self.assertTrue((out / 'references').is_dir())
            _, again = call(base, '/api/ontology/build', upload)
            self.assertTrue(again['evaluation']['reference']['confirmed'])
            self.assertEqual(again['evaluation']['reference']['diff']['types']['only_reference'], ['发票'])
            job = call(base, '/api/ontology/jobs', upload)[1]
            self.assertTrue(wait(base, job['job_id'])['result']['evaluation']['reference']['confirmed'])
            status, body = call(base, '/api/ontology/confirm', {'saved_as': first['saved_as'], 'decisions': {'types': {'nope': {'verdict': 'ok'}}}})
            self.assertEqual(status, 400)
            self.assertIn('nope', body['error'])


if __name__ == '__main__':
    unittest.main()
