"""OntoPoc as a Claude Code plugin: the repository is the plugin and its own marketplace. The MCP launcher finds a
Python the way a Mac actually has one (python3, often no python), says so plainly when there is none, and a session
start check stays silent while the modelling service answers and says one line when it does not."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_ontology_server import OntologyServerTests

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'bin' / 'ontopoc-mcp'
INIT = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}}) + '\n'


def launch(path, extra=None, args=(), stdin=''):
    env = {'PATH': path, 'HOME': os.environ.get('HOME', ''), **(extra or {})}
    return subprocess.run(['/bin/bash', str(LAUNCHER), *args], input=stdin, capture_output=True, text=True, env=env, timeout=60)


class ManifestTests(unittest.TestCase):
    def test_the_plugin_and_its_marketplace_are_declared(self):
        plugin = json.loads((ROOT / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8'))
        market = json.loads((ROOT / '.claude-plugin' / 'marketplace.json').read_text(encoding='utf-8'))
        self.assertEqual(plugin['name'], 'ontopoc')
        self.assertEqual(plugin['mcpServers']['ontopoc']['command'], '${CLAUDE_PLUGIN_ROOT}/bin/ontopoc-mcp')
        self.assertEqual([(p['name'], p['source']) for p in market['plugins']], [('ontopoc', './')])
        commands = ROOT / plugin['commands']
        self.assertEqual(sorted(p.name for p in commands.glob('*.md')), ['ontopoc-build.md', 'ontopoc-review.md'])
        hooks = json.loads((ROOT / plugin['hooks']).read_text(encoding='utf-8'))
        [start] = hooks['hooks']['SessionStart']
        self.assertIn('--check', start['hooks'][0]['command'])

    def test_the_review_command_leaves_every_verdict_to_the_person(self):
        text = (ROOT / 'plugin' / 'commands' / 'ontopoc-review.md').read_text(encoding='utf-8')
        self.assertIn('confirm_ontology', text)
        self.assertIn('不要替', text)


class LauncherTests(unittest.TestCase):
    def test_it_finds_python3_when_there_is_no_python(self):
        with tempfile.TemporaryDirectory() as d:
            os.symlink(sys.executable, Path(d) / 'python3')
            done = launch(d, stdin=INIT)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('serverInfo', json.loads(done.stdout.splitlines()[0])['result'])

    def test_a_python_named_in_ontopoc_python_is_used_first(self):
        with tempfile.TemporaryDirectory() as d:
            done = launch(d, {'ONTOPOC_PYTHON': sys.executable}, stdin=INIT)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_without_any_python_it_says_so_and_stops(self):
        with tempfile.TemporaryDirectory() as d:
            done = launch(d, stdin=INIT)
        self.assertEqual(done.returncode, 127)
        self.assertIn('Python', done.stderr)


class CheckTests(unittest.TestCase):
    def test_silent_while_the_service_answers(self):
        with OntologyServerTests().server() as (base, _):
            done = launch(os.environ['PATH'], {'ONTOPOC_URL': base}, args=('--check',))
        self.assertEqual((done.returncode, done.stdout), (0, ''), done.stderr)

    def test_one_line_when_it_does_not_and_the_session_still_starts(self):
        done = launch(os.environ['PATH'], {'ONTOPOC_URL': 'http://127.0.0.1:9'}, args=('--check',))
        self.assertEqual(done.returncode, 0)
        self.assertEqual(len(done.stdout.strip().splitlines()), 1)
        self.assertIn('建模服务', done.stdout)


if __name__ == '__main__':
    unittest.main()
