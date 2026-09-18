"""Rules found in the data, for a person to adopt: a field every object has, and two dates always in the same order.
No thresholds: a rule holds on every object or it is not offered. An adopted rule is checked again on every run."""
import base64
import json
import unittest

from ontology_poc_generator.rule_discovery import check_rules, discover_rules
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import OntologyServerTests


def table(*rows):
    header, *data = rows
    return {'records': [dict(zip(header, r)) for r in data], 'requests': []}


ROWS = [('合同号', '供应商', '签订日期', '到期日期', '备注', '登记'),
        ('H1', '甲', '2024-01-05', '2024-06-30', '', '2024/1/5'),
        ('H2', '乙', '2024-02-01', '2025-01-31', '续签', '2024-02-01'),
        ('H3', '甲', '2024-03-10', '2024-03-10', '', '2024-03-10')]
ONTOLOGY = {'object_types': [{'key': 'contract', 'label': '合同', 'populated_from': [{'source': 'contracts', 'identity': {'id': '合同号'}}],
                              'attributes': [{'source': 'contracts', 'path': p} for p in ('供应商', '签订日期', '到期日期', '备注', '登记')]}],
            'relations': [], 'ignored_fields': [], 'open_questions': []}


class DiscoveryTests(unittest.TestCase):
    def test_a_field_every_object_has_and_two_dates_always_in_order_are_offered(self):
        rules = discover_rules(ONTOLOGY, {'sources': {'contracts': table(*ROWS)}})
        self.assertEqual(sorted((r['kind'], r['type'], r.get('field') or f"{r['before']}<={r['after']}") for r in rules),
                         [('order', 'contract', '签订日期<=到期日期'), ('required', 'contract', '供应商'), ('required', 'contract', '到期日期'),
                          ('required', 'contract', '登记'), ('required', 'contract', '签订日期')])
        self.assertTrue(all(r['holds'] == 3 and r['id'] for r in rules))

    def test_an_adopted_rule_names_the_objects_that_break_it_on_new_data(self):
        rules = discover_rules(ONTOLOGY, {'sources': {'contracts': table(*ROWS)}})
        broken = table(*ROWS[:3], ('H3', '', '2024-03-10', '2023-12-31', '', '2024-03-10'))
        checked = {r['id']: r for r in check_rules(ONTOLOGY, {'sources': {'contracts': broken}}, rules)}
        self.assertEqual(checked['required:contract:供应商']['violations'], {'count': 1, 'examples': ['H3']})
        self.assertEqual(checked['order:contract:签订日期:到期日期']['violations'], {'count': 1, 'examples': ['H3']})
        self.assertEqual(checked['required:contract:签订日期']['violations'], {'count': 0, 'examples': []})


class RuleServerTests(unittest.TestCase):
    def test_rules_are_offered_with_a_run_and_adopted_ones_are_checked_on_the_next(self):
        csv = '\n'.join(','.join(r) for r in ROWS).encode('utf-8')
        upload = {'filename': 'contracts.csv', 'content_base64': base64.b64encode(csv).decode()}
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', upload)
            offered = run['evaluation']['rules']['candidates']
            self.assertTrue(offered)
            keep = [offered[0]['id']]
            status, updated = call(base, '/api/ontology/rules', {'saved_as': run['saved_as'], 'adopted': keep, 'declined': [offered[-1]['id']]})
            self.assertEqual(status, 200, updated)
            self.assertEqual([r['id'] for r in updated['evaluation']['rules']['adopted']], keep)
            _, again = call(base, '/api/ontology/build', upload)
            self.assertEqual([r['id'] for r in again['evaluation']['rules']['adopted']], keep)
            self.assertEqual(again['evaluation']['rules']['adopted'][0]['violations']['count'], 0)
            self.assertNotIn(offered[-1]['id'], [r['id'] for r in again['evaluation']['rules']['candidates']])   # declined stays declined


if __name__ == '__main__':
    unittest.main()
