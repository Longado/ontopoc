import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_ontology_server import CSV, FakeModel


class RunCompanyOntologyScriptTests(unittest.TestCase):
    def run_main(self, argv, env):
        from scripts.run_company_ontology import main
        err = io.StringIO()
        with patch.dict('os.environ', env, clear=True), \
                patch('scripts.run_company_ontology.gateway_from_env', return_value=FakeModel() if env else None), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            return main(argv), err.getvalue()

    def test_writes_the_same_result_the_page_shows(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / 'orders.csv', Path(tmp) / 'run.json'
            src.write_bytes(CSV)
            code, _ = self.run_main(['--file', str(src), '--output', str(out)], {'DEEPSEEK_API_KEY': 'offline-test'})
            self.assertEqual(code, 0)
            result = json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual((result['schema'], result['ontology']['status']), ('company_ontology_run.v1', 'auto_built_verified'))

    def test_refuses_without_a_key_or_with_an_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / 'orders.csv', Path(tmp) / 'run.json'
            src.write_bytes(CSV)
            code, err = self.run_main(['--file', str(src), '--output', str(out)], {})
            self.assertEqual(code, 2)
            self.assertIn('DEEPSEEK_API_KEY', err)
            out.write_text('{}')
            self.assertEqual(self.run_main(['--file', str(src), '--output', str(out)], {'DEEPSEEK_API_KEY': 'k'})[0], 2)


if __name__ == '__main__':
    unittest.main()
