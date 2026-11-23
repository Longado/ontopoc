"""A release is one tag: the workflow puts the wheel on PyPI and server.json in the official MCP Registry. These pin
what that needs from the repository: one version everywhere (the tag, pyproject.toml, server.json, the package and the
MCP serverInfo), an `ontopoc` command that starts the MCP server, a server.json the registry accepts, and the
`mcp-name:` line the registry looks for on the PyPI page to prove the package is ours."""
import io
import json
import re
import subprocess
import sys
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_NAME = 'io.github.Longado/ontopoc'
SCHEMA = 'https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json'


def pyproject() -> dict:
    return tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))


def server_json() -> dict:
    return json.loads((ROOT / 'server.json').read_text(encoding='utf-8'))


def pypi_package() -> dict:
    [package] = [p for p in server_json()['packages'] if p['registryType'] == 'pypi']
    return package


def entry(spec: str):
    module, _, attr = spec.partition(':')
    return getattr(import_module(module), attr)


class OneVersionTests(unittest.TestCase):
    def test_pyproject_server_json_and_the_package_name_one_version(self):
        from ontology_poc_generator import __version__
        version = pyproject()['project']['version']
        self.assertEqual(server_json()['version'], version)
        self.assertEqual(pypi_package()['version'], version)
        self.assertEqual(__version__, version)

    def test_the_mcp_server_reports_the_package_version(self):
        from ontology_poc_generator import __version__, mcp_server
        reply = mcp_server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}}, service=None)
        self.assertEqual(reply['result']['serverInfo'], {'name': 'ontopoc', 'version': __version__})

    def check(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts' / 'check_release_version.py'), *args],
                              capture_output=True, text=True, cwd=ROOT, timeout=60)

    def test_the_release_check_passes_for_the_tag_of_this_version(self):
        done = self.check('v' + pyproject()['project']['version'])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_the_release_check_fails_for_another_tag_and_names_what_differs(self):
        done = self.check('v9.9.9')
        self.assertEqual(done.returncode, 1)
        self.assertIn('9.9.9', done.stdout + done.stderr)

    def test_the_release_check_wants_a_v_tag(self):
        self.assertEqual(self.check(pyproject()['project']['version']).returncode, 1)


class CommandTests(unittest.TestCase):
    def test_the_ontopoc_command_and_the_old_ones_resolve_to_callables(self):
        scripts = pyproject()['project']['scripts']
        self.assertEqual(scripts['ontopoc'], 'ontology_poc_generator.cli:main')
        for name in ('ontopoc', 'ontopoc-mcp'):
            self.assertTrue(callable(entry(scripts[name])), name)

    def test_version_prints_the_package_version(self):
        from ontology_poc_generator import __version__, cli
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(['--version']), 0)
        self.assertEqual(out.getvalue().strip(), f'ontopoc {__version__}')

    def test_an_unknown_command_is_refused(self):
        from ontology_poc_generator import cli
        with self.assertRaises(SystemExit) as stop, redirect_stderr(io.StringIO()):
            cli.main(['serve'])
        self.assertEqual(stop.exception.code, 2)

    def smoke(self, *args):
        cmd = [sys.executable, '-m', 'ontology_poc_generator.cli', *args]
        return subprocess.run([sys.executable, str(ROOT / 'scripts' / 'check_mcp_stdio.py'), '--', *cmd],
                              capture_output=True, text=True, cwd=ROOT, timeout=60,
                              env={'PYTHONPATH': str(ROOT / 'src'), 'PATH': '/usr/bin:/bin', 'ONTOPOC_URL': 'http://127.0.0.1:9'})

    def test_ontopoc_mcp_answers_initialize_and_tools_list_over_stdio(self):
        done = self.smoke('mcp')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('6 tools', done.stdout)   # no token and no ONTOPOC_TOOLSET: the six read tools

    def test_ontopoc_with_no_arguments_is_the_mcp_server_too(self):
        done = self.smoke()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('6 tools', done.stdout)


class ServerJsonTests(unittest.TestCase):
    def test_it_names_the_server_and_the_current_schema(self):
        s = server_json()
        self.assertEqual(s['$schema'], SCHEMA)
        self.assertEqual(s['name'], SERVER_NAME)
        self.assertLessEqual(len(s['description']), 100)   # the registry's limit
        self.assertEqual(s['repository'], {'url': 'https://github.com/Longado/ontopoc', 'source': 'github'})

    def test_its_pypi_package_is_this_project_run_with_the_mcp_subcommand(self):
        p = pypi_package()
        self.assertEqual(p['identifier'], pyproject()['project']['name'])
        self.assertEqual(p['transport'], {'type': 'stdio'})
        self.assertEqual(p['runtimeHint'], 'uvx')
        self.assertEqual(p['packageArguments'], [{'type': 'positional', 'value': 'mcp'}])

    def test_its_environment_variables_are_the_ones_the_server_reads(self):
        source = (ROOT / 'src' / 'ontology_poc_generator' / 'mcp_server.py').read_text(encoding='utf-8')
        variables = {v['name']: v for v in pypi_package()['environmentVariables']}
        self.assertEqual(set(variables), {'ONTOPOC_URL', 'ONTOPOC_TOKEN', 'ONTOPOC_TOOLSET'})
        for name in variables:
            self.assertIn(f"'{name}'", source)
        self.assertTrue(variables['ONTOPOC_TOKEN']['isSecret'])


class PyPIPageTests(unittest.TestCase):
    def test_the_metadata_a_pypi_page_needs_is_there(self):
        project = pyproject()['project']
        self.assertEqual(project['license'], 'AGPL-3.0-only')
        self.assertEqual(project['requires-python'], '>=3.11')
        self.assertEqual(project['urls']['Source'], 'https://github.com/Longado/ontopoc')
        self.assertTrue((ROOT / project['readme']).is_file())

    def test_the_pypi_readme_carries_the_mcp_name_the_registry_checks(self):
        text = (ROOT / pyproject()['project']['readme']).read_text(encoding='utf-8')
        # the name must be followed by a boundary: a newline, whitespace, a tag or the comment close
        self.assertRegex(text, r'mcp-name: ' + re.escape(server_json()['name']) + r'(\s|<|-->)')


class WorkflowTests(unittest.TestCase):
    text = (ROOT / '.github' / 'workflows' / 'release.yml').read_text(encoding='utf-8') if (ROOT / '.github' / 'workflows' / 'release.yml').is_file() else ''

    def test_a_v_tag_starts_it_and_it_checks_the_versions_first(self):
        self.assertRegex(self.text, r'tags:\s*\["v\*"\]')
        self.assertIn('scripts/check_release_version.py "$GITHUB_REF_NAME"', self.text)
        self.assertLess(self.text.index('check_release_version.py'), self.text.index('gh-action-pypi-publish'))

    def test_pypi_by_trusted_publishing_and_the_registry_by_github_oidc(self):
        pypi = self.text[self.text.index('\n  pypi:'):self.text.index('\n  registry:')]
        self.assertIn('environment:', pypi)
        self.assertIn('name: pypi', pypi)
        self.assertIn('id-token: write', pypi)
        self.assertIn('pypa/gh-action-pypi-publish@release/v1', pypi)
        self.assertNotIn('secrets.', self.text)   # no stored token anywhere
        registry = self.text[self.text.index('\n  registry:'):]
        self.assertIn('needs: pypi', registry)
        self.assertIn('id-token: write', registry)
        self.assertIn('mcp-publisher login github-oidc', registry)
        self.assertIn('mcp-publisher publish', registry)

    def test_the_registry_tool_is_pinned_and_its_signature_checked(self):
        self.assertRegex(self.text, r'MCP_PUBLISHER_VERSION: v\d+\.\d+\.\d+')
        self.assertIn('cosign verify-blob', self.text)
        self.assertNotIn('releases/latest', self.text)


if __name__ == '__main__':
    unittest.main()
