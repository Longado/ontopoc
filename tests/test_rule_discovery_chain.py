"""Chicago's business licences have a chain of dates: applied, paid, issued, expires. Every pair in order was offered,
15 rules for one chain; the ones implied by two others say nothing new."""
import unittest

from ontology_poc_generator.rule_discovery import discover_rules
from tests.test_rule_discovery import table


class ChainTests(unittest.TestCase):
    def test_an_order_implied_by_two_others_is_left_out(self):
        rows = [('号', '申请', '付款', '发证'), ('L1', '2024-01-01', '2024-01-05', '2024-02-01'), ('L2', '2024-03-01', '2024-03-02', '2024-03-20')]
        ontology = {'object_types': [{'key': 'lic', 'label': '执照', 'populated_from': [{'source': 's', 'identity': {'id': '号'}}],
                                      'attributes': [{'source': 's', 'path': p} for p in ('申请', '付款', '发证')]}],
                    'relations': [], 'ignored_fields': [], 'open_questions': []}
        orders = [(r['before'], r['after']) for r in discover_rules(ontology, {'sources': {'s': table(*rows)}}) if r['kind'] == 'order']
        self.assertEqual(sorted(orders), [('付款', '发证'), ('申请', '付款')])


if __name__ == '__main__':
    unittest.main()
