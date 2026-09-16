import copy
import unittest

from ontology_poc_generator.ontology_acceptance import check_acceptance, parse_acceptance
from tests.test_company_ontology import BUNDLE, PROPOSAL

QUERY = {'start': 'order', 'where': [], 'via': [], 'group_by': [{'via': ['order_customer'], 'field': '客户.名称'}]}
ITEM = {'question': '每个客户有多少订单？', 'query': QUERY, 'note': '按订单号计数'}


def saved_once(ontology=PROPOSAL, bundle=BUNDLE):
    """An acceptance question as it is stored after one run: with the snapshot of what its query pointed at."""
    return check_acceptance(ontology, bundle, parse_acceptance([ITEM]))['items']


def renamed(proposal, keys=None, relations=None):
    """The same ontology as the model would write it next time: other keys, same tables and identity fields."""
    out = copy.deepcopy(proposal)
    for t in out['object_types']:
        t['key'] = (keys or {}).get(t['key'], t['key'])
    for r in out['relations']:
        r['key'] = (relations or {}).get(r['key'], r['key'])
        r['from'] = (keys or {}).get(r['from'], r['from'])
        r['to'] = (keys or {}).get(r['to'], r['to'])
    return out


class RemapTests(unittest.TestCase):
    def test_a_relation_the_model_renamed_is_found_again_and_the_answer_is_unchanged(self):
        first = saved_once()
        again = check_acceptance(renamed(PROPOSAL, relations={'order_customer': 'order_belongs_to_customer'}), BUNDLE, first)
        self.assertEqual(again['items'][0]['status'], 'answered')
        self.assertEqual(again['items'][0]['answer'], first[0]['answer'])
        self.assertIs(again['items'][0]['changed'], False)

    def test_an_object_the_model_renamed_is_found_again(self):
        again = check_acceptance(renamed(PROPOSAL, keys={'customer': 'client', 'order': 'sales_order'}), BUNDLE, saved_once())
        self.assertEqual(again['items'][0]['status'], 'answered')

    def test_the_remapped_query_is_kept_so_the_next_run_starts_from_the_current_names(self):
        again = check_acceptance(renamed(PROPOSAL, keys={'order': 'sales_order'}), BUNDLE, saved_once())
        self.assertEqual(again['items'][0]['query']['start'], 'sales_order')

    def test_an_object_that_is_really_gone_breaks_and_is_named(self):
        gone = {**PROPOSAL, 'object_types': [t for t in PROPOSAL['object_types'] if t['key'] != 'customer'], 'relations': []}
        out = check_acceptance(gone, BUNDLE, saved_once())
        self.assertEqual(out['items'][0]['status'], 'broken')
        self.assertIn('客户', out['items'][0]['reason'])

    def test_a_relation_that_is_really_gone_breaks_and_is_named(self):
        gone = {**PROPOSAL, 'relations': []}
        out = check_acceptance(gone, BUNDLE, saved_once())
        self.assertEqual(out['items'][0]['status'], 'broken')
        self.assertIn('订单', out['items'][0]['reason'])

    def test_two_relations_between_the_same_ends_are_not_guessed(self):
        twins = copy.deepcopy(PROPOSAL)
        twins['relations'].append({'key': 'order_refunds_customer', 'from': 'order', 'to': 'customer', 'source': '订单', 'meaning': '退款给客户'})
        out = check_acceptance(twins, BUNDLE, saved_once())
        self.assertEqual(out['items'][0]['status'], 'broken')
        self.assertIn('分不清', out['items'][0]['reason'])

    def test_a_question_saved_before_snapshots_existed_still_runs_by_its_keys(self):
        old = [{**item, 'snapshot': None} for item in saved_once()]
        self.assertEqual(check_acceptance(PROPOSAL, BUNDLE, old)['items'][0]['status'], 'answered')

    def test_what_is_stored_carries_the_snapshot_its_query_points_at(self):
        snapshot = saved_once()[0]['snapshot']
        self.assertEqual({t['key'] for t in snapshot['types']}, {'order', 'customer'})
        self.assertEqual([r['key'] for r in snapshot['relations']], ['order_customer'])
        kept = {t['key']: t['populated_from'] for t in snapshot['types']}
        self.assertEqual(kept, {t['key']: t['populated_from'] for t in PROPOSAL['object_types']})


if __name__ == '__main__':
    unittest.main()
