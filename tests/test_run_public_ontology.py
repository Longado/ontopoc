import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ontology_poc_generator.public_ontology import MODELER_SYSTEM_PROMPT
from ontology_poc_generator.recognition import ModelCompletion

FIXTURES = Path(__file__).resolve().parent / 'fixtures/nhtsa'
MINI = str(FIXTURES / 'mini_bundle.json')
KEY = 'offline-test-key-123'


class FakeModel:
    def complete_json(self, *, system_prompt, user_prompt):
        if system_prompt == MODELER_SYSTEM_PROMPT:
            content = (FIXTURES / 'reference_proposal.json').read_text(encoding='utf-8')
        else:
            items = json.loads(user_prompt)['complaints']
            content = json.dumps({'results': [{'id': i['id'], 'reasoning': 'r', 'verdict': 'no', 'evidence': ''}
                                              for i in items]})
        return ModelCompletion(provider='fake', model='deepseek-flash', content=content)


def run(argv, env):
    from scripts.run_public_ontology import main
    err = io.StringIO()
    with patch.dict('os.environ', env, clear=True), \
            patch('scripts.run_public_ontology.OpenAICompatibleGateway', return_value=FakeModel()) as gateway, \
            contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        code = main(argv)
    return code, gateway, err.getvalue()


class RunPublicOntologyScriptTests(unittest.TestCase):
    def test_missing_key_is_blocked_before_any_output(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'r.json'
            code, gateway, err = run(['--snapshot', MINI, '--campaign', '21V650000', '--output', str(out)], {})
            self.assertEqual(code, 2)
            self.assertIn('DEEPSEEK_API_KEY', err)
            self.assertFalse(out.exists())
            gateway.assert_not_called()

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'r.json'
            out.write_text('keep', encoding='utf-8')
            code, _, _ = run(['--snapshot', MINI, '--campaign', '21V650000', '--output', str(out)],
                             {'DEEPSEEK_API_KEY': KEY})
            self.assertEqual(code, 2)
            self.assertEqual(out.read_text(encoding='utf-8'), 'keep')

    def test_full_run_writes_report_without_the_key(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'r.json'
            code, gateway, _ = run(['--snapshot', MINI, '--campaign', '21V650000', '--campaign', '21V517000',
                                    '--output', str(out)], {'DEEPSEEK_API_KEY': KEY})
            self.assertEqual(code, 0)
            self.assertEqual(gateway.call_args.kwargs['model'], 'deepseek-flash')
            text = out.read_text(encoding='utf-8')
            self.assertNotIn(KEY, text)
            self.assertNotIn(d, text)
            report = json.loads(text)
            self.assertEqual(report['schema'], 'public_ontology_run.v1')
            self.assertTrue(report['finished'])
            self.assertEqual(report['ontology']['status'], 'auto_built_verified')
            self.assertEqual(sorted(report['scopes']), ['21V517000', '21V650000'])
            self.assertTrue(all(c['text_check']['verdict'] == 'no' for c in report['scopes']['21V650000']['candidates']))

    def test_unknown_campaign_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'r.json'
            code, _, err = run(['--snapshot', MINI, '--campaign', '99V999000', '--output', str(out)],
                               {'DEEPSEEK_API_KEY': KEY})
            self.assertEqual(code, 1)
            self.assertIn('99V999000', json.loads(out.read_text(encoding='utf-8'))['errors'][0])


class FetchSnapshotScriptTests(unittest.TestCase):
    def test_fetch_writes_bundle_and_refuses_overwrite(self):
        from scripts.fetch_nhtsa_snapshot import main
        bundle = json.loads(Path(MINI).read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d, \
                patch('scripts.fetch_nhtsa_snapshot.fetch_nhtsa_bundle', return_value=bundle) as fetch, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            out = Path(d) / 's.json'
            argv = ['--make', 'chevrolet', '--model', 'bolt ev', '--years', '2020-2022', '--output', str(out)]
            self.assertEqual(main(argv), 0)
            self.assertEqual(fetch.call_args.args[:3], ('chevrolet', ['bolt ev'], [2020, 2021, 2022]))
            self.assertEqual(json.loads(out.read_text(encoding='utf-8')), bundle)
            self.assertEqual(main(argv), 2)


if __name__ == '__main__':
    unittest.main()
