import copy
import importlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples/recalls/95876.scope.json'


class RecallScopeTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('ontology_poc_generator.recall_scope'),
                             'public recall matching module is not implemented')
        return importlib.import_module('ontology_poc_generator.recall_scope')

    def check(self, query):
        api = self.api()
        return api.match_recall(api.load_catalog(FIXTURE), query)

    def test_exact_product_and_lot_match_with_original_evidence(self):
        result = self.check({'product': 'F-0369-2025/1', 'lot': 'X7547814'})
        self.assertEqual(result['status'], 'matched')
        self.assertEqual(result['evidence_scope'], 'public_recall')
        self.assertIn('X7547814', result['evidence'][0]['code_quote'])
        self.assertEqual(result['query']['lot'], 'X7547814')

    def test_cross_product_lot_is_conflict(self):
        self.assertEqual(self.check({'product': 'F-0368-2025/1', 'lot': 'X7547814'})['status'], 'conflict')

    def test_lot_alone_does_not_confirm_identity(self):
        self.assertEqual(self.check({'lot': 'X7547814'})['status'], 'insufficient')

    def test_missing_lot_is_insufficient(self):
        self.assertEqual(self.check({'product': 'F-0369-2025/1'})['status'], 'insufficient')

    def test_unknown_lot_and_prefix_do_not_match(self):
        for lot in ['X754781', 'X75478140', 'X0000000', 'prefixX7547814']:
            with self.subTest(lot=lot):
                r = self.check({'product': 'F-0369-2025/1', 'lot': lot})
                self.assertEqual(r['status'], 'not_matched')
                self.assertIn('不代表安全', r['boundary'])

    def test_upc_resolves_identity_and_conflicting_upc_blocks(self):
        self.assertEqual(self.check({'upc': '7 95631-81038 7', 'lot': 'X7547814'})['status'], 'matched')
        for lot in ['X7547814', '']:
            self.assertEqual(self.check({'product': 'F-0369-2025/1', 'upc': '795631811490', 'lot': lot})['status'], 'conflict')

    def test_unverifiable_extra_identity_is_not_ignored(self):
        self.assertEqual(self.check({'product': 'unknown wrap', 'upc': '795631810387', 'lot': 'X7547814'})['status'], 'conflict')
        self.assertEqual(self.check({'product': 'F-0367-2025/1', 'upc': '000000000000', 'lot': 'X7544915'})['status'], 'insufficient')

    def test_label_date_range_boundaries_and_missing_date(self):
        for date in ['2024-11-05', '2024-11-15', '']:
            self.assertEqual(self.check({'product': 'F-0369-2025/1', 'lot': 'X7547814', 'label_date': date})['status'], 'matched')
        self.assertEqual(self.check({'product': 'F-0369-2025/1', 'lot': 'X7547814', 'label_date': '2024-11-16'})['status'], 'conflict')
        with self.assertRaises(ValueError):
            self.check({'product': 'F-0369-2025/1', 'lot': 'X7547814', 'label_date': '2024-13-01'})

    def test_grouped_products_never_share_another_subproducts_lots(self):
        self.assertEqual(self.check({'product': 'F-0367-2025/7', 'lot': 'X7568580'})['status'], 'matched')
        self.assertEqual(self.check({'product': 'F-0367-2025/1', 'lot': 'X7568580'})['status'], 'conflict')

    def test_original_source_and_catalog_are_bound(self):
        api = self.api()
        catalog = json.loads(FIXTURE.read_text())
        source = json.loads(FIXTURE.with_name('95876.openfda.json').read_text())
        api.validate_catalog(catalog, source)
        broken = copy.deepcopy(catalog)
        broken['products'][0]['lots'].append('X9999999')
        with self.assertRaises(ValueError):
            api.validate_catalog(broken, source)
        broken = copy.deepcopy(catalog)
        broken['products'][0]['code_quote'] = catalog['products'][1]['code_quote']
        broken['products'][0]['lots'] = catalog['products'][1]['lots']
        with self.assertRaises(ValueError):
            api.validate_catalog(broken, source)

    def test_unknown_input_fields_and_non_text_rejected(self):
        for query in [{'lot': ['X7547814']}, {'safe': True}, None]:
            with self.assertRaises(ValueError):
                self.check(query)

    def test_cli_prints_match(self):
        self.api()
        run = subprocess.run([sys.executable, '-m', 'ontology_poc_generator.recall_cli',
                              '--product', 'F-0369-2025/1', '--lot', 'X7547814'],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['status'], 'matched')


if __name__ == '__main__':
    unittest.main()
