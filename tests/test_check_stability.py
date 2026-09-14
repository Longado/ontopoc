import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ontology_poc_generator.recognition import ModelCompletion
from tests.test_public_review_pack import load, make_report


class AlwaysYes:
    def complete_json(self, *, system_prompt, user_prompt):
        items = json.loads(user_prompt)['complaints']
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps({'results': [
            {'id': i['id'], 'reasoning': 'r', 'verdict': 'yes', 'evidence': i['text'][:20]} for i in items]}))


class CheckStabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        bundle = load('mini_bundle.json')
        self.report, self.snapshot, self.out = root / 'run.json', root / 'snap.json', root / 'stability.json'
        self.report.write_text(json.dumps(make_report(bundle)), encoding='utf-8')
        self.snapshot.write_text(json.dumps(bundle), encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, argv, env=None):
        from scripts.check_stability import main
        err = io.StringIO()
        with patch.dict('os.environ', env if env is not None else {'DEEPSEEK_API_KEY': 'offline-test'}, clear=True), \
                patch('scripts.check_stability.OpenAICompatibleGateway', return_value=AlwaysYes()), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            return main(argv), err.getvalue()

    def argv(self, *extra):
        return ['--report', str(self.report), '--snapshot', str(self.snapshot), '--output', str(self.out), *extra]

    def test_counts_how_many_first_calls_change_on_the_same_inputs(self):
        code, _ = self.run_main(self.argv())
        self.assertEqual(code, 0)
        result = json.loads(self.out.read_text(encoding='utf-8'))
        recorded = make_report(load('mini_bundle.json'))['scopes']['21V650000']['candidates']
        before = {'|'.join(str(v) for v in c['signal'].values()): c['text_check']['verdict'] for c in recorded}
        campaign = result['campaigns']['21V650000']
        self.assertEqual(campaign['candidates'], len(before))
        self.assertEqual(campaign['same'], sum(v == 'yes' for v in before.values()))
        self.assertEqual(sorted(c['id'] for c in campaign['changed']), sorted(i for i, v in before.items() if v != 'yes'))
        self.assertTrue(all(c['after'] == 'yes' for c in campaign['changed']))
        self.assertEqual(result['totals'], {'candidates': campaign['candidates'], 'same': campaign['same'],
                                            'changed': len(campaign['changed'])})
        self.assertEqual(result['prompt_version'], 'public_defect_match.v3')

    def test_refuses_without_a_key_an_existing_output_or_an_unrecorded_campaign(self):
        self.assertEqual(self.run_main(self.argv(), env={})[0], 2)
        self.out.write_text('{}', encoding='utf-8')
        self.assertEqual(self.run_main(self.argv())[0], 2)
        self.out.unlink()
        code, err = self.run_main(self.argv('--campaign', '99V999000'))
        self.assertEqual(code, 2)
        self.assertIn('99V999000', err)


if __name__ == '__main__':
    unittest.main()
