import copy
import importlib
import json
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile

from ontology_poc_generator.recall_scope import load_catalog
from ontology_poc_generator.recognition import ModelCompletion


class RecallExtractionTests(unittest.TestCase):
    def test_benchmark_defaults_to_current_official_flash_model(self):
        from scripts.check_recall_deepseek import main
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'offline-test'}, clear=True), \
                patch('scripts.check_recall_deepseek.OpenAICompatibleGateway') as gateway, \
                patch('scripts.check_recall_deepseek.extract_record', return_value={'accepted': True}):
            self.assertEqual(main(['--output', str(Path(directory) / 'report.json')]), 0)
            self.assertEqual(gateway.call_args.kwargs['model'], 'deepseek-flash')

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('ontology_poc_generator.recall_extraction'),
                             'DeepSeek extraction comparison is not implemented')
        return importlib.import_module('ontology_poc_generator.recall_extraction')

    def setUp(self):
        self.catalog = load_catalog()
        self.expected = {'products': [
            {'product_key': p['product_key'], 'lots': p['lots']}
            for p in self.catalog['products'] if p['recall_number'] == 'F-0367-2025']}

    def test_exact_extraction_is_accepted_independent_of_order(self):
        candidate = copy.deepcopy(self.expected)
        candidate['products'].reverse()
        for p in candidate['products']:
            p['lots'].reverse()
        result = self.api().compare_extraction(json.dumps(candidate), self.catalog, 'F-0367-2025')
        self.assertTrue(result['accepted'])
        self.assertEqual(result['differences'], [])

    def test_cross_product_swap_is_rejected(self):
        candidate = copy.deepcopy(self.expected)
        a, b = candidate['products'][:2]
        a['lots'][0], b['lots'][0] = b['lots'][0], a['lots'][0]
        result = self.api().compare_extraction(json.dumps(candidate), self.catalog, 'F-0367-2025')
        self.assertFalse(result['accepted'])
        self.assertEqual(len(result['differences']), 2)

    def test_omissions_additions_duplicates_and_invalid_json_are_rejected(self):
        candidates = []
        for kind in ['omit_lot', 'add_lot', 'repeat_lot', 'omit_product', 'repeat_product', 'extra_field']:
            p = copy.deepcopy(self.expected)
            if kind == 'omit_lot': p['products'][0]['lots'].pop()
            if kind == 'add_lot': p['products'][0]['lots'].append('X0000000')
            if kind == 'repeat_lot': p['products'][0]['lots'].append(p['products'][0]['lots'][0])
            if kind == 'omit_product': p['products'].pop()
            if kind == 'repeat_product': p['products'].append(p['products'][0])
            if kind == 'extra_field': p['safe'] = True
            candidates.append(json.dumps(p))
        candidates += ['not json', '{}', '{"products":null}', '{"products":[{"product_key":[],"lots":[]}]}']
        for content in candidates:
            with self.subTest(content=content[:60]):
                self.assertFalse(self.api().compare_extraction(content, self.catalog, 'F-0367-2025')['accepted'])

    def test_live_gateway_receives_raw_source_without_reference_answer(self):
        expected = self.expected
        outer = self
        class Gateway:
            def complete_json(self, *, system_prompt, user_prompt):
                payload = json.loads(user_prompt)
                outer.assertEqual(set(payload), {'recall_number', 'product_description', 'code_info'})
                outer.assertNotIn('expected', user_prompt)
                return ModelCompletion(provider='offline_test', model='fake', content=json.dumps(expected))
        result = self.api().extract_record(self.catalog, 'F-0367-2025', Gateway())
        self.assertTrue(result['accepted'])
        self.assertEqual(result['provider'], 'offline_test')
        self.assertEqual(result['model'], 'fake')
        self.assertGreaterEqual(result['elapsed_seconds'], 0)


if __name__ == '__main__':
    unittest.main()
