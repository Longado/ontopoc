import copy
import unittest

from ontology_poc_generator.company_ontology import verify_company_proposal
from ontology_poc_generator.ontology_acceptance import check_acceptance
from test_company_ontology import BUNDLE, PROPOSAL


class AcceptanceRelationBindingTests(unittest.TestCase):
    def setUp(self):
        self.bundle = copy.deepcopy(BUNDLE)
        for row in self.bundle['sources']['订单']['records']:
            row['BillToId'] = row['客户编号']
        self.proposal = copy.deepcopy(PROPOSAL)
        self.proposal['object_types'][1]['attributes'].append({'source': '订单', 'path': 'BillToId'})
        self.proposal['relations'][0].update(from_identity={'order_id': '订单号'}, to_identity={'customer_id': '客户编号'})
        self.assertEqual(verify_company_proposal(self.proposal, self.bundle)['errors'], [])
        self.item = {'question': '订单涉及多少客户？', 'note': '按购买客户编号',
                     'query': {'start': 'order', 'via': ['order_customer']}}

    def test_changed_reference_column_requires_reconfirmation_even_if_count_is_equal(self):
        saved = check_acceptance(self.proposal, self.bundle, [self.item])['items']
        changed = copy.deepcopy(self.proposal)
        changed['relations'][0]['to_identity'] = {'customer_id': 'BillToId'}
        self.assertEqual(verify_company_proposal(changed, self.bundle)['errors'], [])
        out = check_acceptance(changed, self.bundle, saved)['items'][0]
        self.assertEqual(out['status'], 'broken')
        self.assertIn('重新确认', out['reason'])

    def test_same_binding_can_follow_a_relation_key_rename(self):
        saved = check_acceptance(self.proposal, self.bundle, [self.item])['items']
        self.assertEqual(saved[0]['snapshot']['relations'][0].get('to_identity'), {'customer_id': '客户编号'})
        renamed = copy.deepcopy(self.proposal)
        renamed['relations'][0]['key'] = 'purchased_by'
        out = check_acceptance(renamed, self.bundle, saved)['items'][0]
        self.assertEqual(out['status'], 'answered')
        self.assertEqual(out['query']['via'], ['purchased_by'])
        self.assertFalse(out['changed'])
