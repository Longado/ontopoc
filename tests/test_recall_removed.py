"""The public recall example (NHTSA vehicle recalls, openFDA event 95876) is gone; the shared ontology core it was built on stays."""
import importlib
import os
import re
import subprocess
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODULES = ('public_review_pack', 'public_scope', 'recall_cli', 'recall_extraction', 'recall_scope', 'recall_server',
           'nhtsa_sources', 'review_labels')
SCRIPTS = ('build_public_review_pack', 'check_recall_deepseek', 'check_stability', 'compare_judgments', 'fetch_nhtsa_snapshot',
           'import_reviews', 'run_public_ontology')
PATHS = ('examples/nhtsa', 'examples/recalls', 'experiments/nhtsa_auto_ontology', 'docs/RECALL_EXAMPLE.md',
         'landing-page/public/data/index.json', 'landing-page/src/legacy/PublicRecallReview.jsx',
         'landing-page/src/legacy/PublicRecallReview.css', 'landing-page/src/legacy/RecallWorkspace.jsx',
         'landing-page/src/legacy/RecallWorkspace.css', 'landing-page/src/legacy/publicReviewModel.js',
         'landing-page/src/legacy/recallWorkspaceModel.js')
# Names only the recall line used. Saying any of them now points a reader at something that is not there.
GONE = re.compile(r'\b(?:' + '|'.join(MODULES + SCRIPTS) + r')\b|PublicRecallReview|RecallWorkspace|publicReview|recallWorkspace'
                  r'|RECALL_EXAMPLE|examples/nhtsa|examples/recalls|ontopoc-recall|/api/recall|\bNHTSA\b|\bopenFDA\b|95876')
# The plans, hand-offs and retros of September and October are history: they say what was tried then, gone features included.
HISTORY = re.compile(r'^docs/(?:archive/|superpowers/|PRD_ITERATION_\d\.md|FEATURES_2026-|HANDOFF_|RETRO_|SEMANTIC_MODELING_|'
                     r'NHTSA_AUTO_ONTOLOGY_PLAN\.md|PLAYGROUND_INTERNALIZATION\.md)')
TEXT = {'.md', '.html', '.css', '.js', '.jsx', '.mjs', '.py', '.json', '.toml', '.yml', '.yaml', '.txt', '.xml', '.sh', ''}


def files():
    """The tracked files; outside a git checkout (an unpacked source archive), every file but build output and installs."""
    listed = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, text=True)
    if listed.returncode == 0 and listed.stdout:
        return [name for name in listed.stdout.split('\0') if name]
    skip = {'.git', 'node_modules', 'dist', '.venv', '__pycache__', 'output', 'build'}
    found = []
    for top, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in skip]
        found += [str((Path(top) / name).relative_to(ROOT)) for name in names]
    return found


class RecallLineRemovedTests(unittest.TestCase):
    def test_the_recall_modules_and_scripts_are_gone(self):
        for name in MODULES:
            self.assertIsNone(importlib.util.find_spec(f'ontology_poc_generator.{name}'), name)
        for name in SCRIPTS:
            self.assertFalse((ROOT / 'scripts' / f'{name}.py').exists(), name)
        for path in PATHS:
            self.assertFalse((ROOT / path).exists(), path)
        self.assertEqual(sorted(p.name for p in (ROOT / 'landing-page/public/data').glob('nhtsa-*')), [])

    def test_the_package_installs_only_the_mcp_command(self):
        project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
        self.assertEqual(project['scripts'], {'ontopoc': 'ontology_poc_generator.cli:main', 'ontopoc-mcp': 'ontology_poc_generator.mcp_server:main'})   # both start the MCP server; no recall command

    def test_no_service_route_and_no_mcp_tool_is_about_recalls(self):
        from ontology_poc_generator import mcp_server
        self.assertEqual([t['name'] for t in mcp_server.TOOLS if 'recall' in t['name']], [])
        for name in ('access.py', 'ontology_server.py', 'auth_http.py', 'use_layer.py', 'mcp_server.py'):
            text = (ROOT / 'src/ontology_poc_generator' / name).read_text(encoding='utf-8')
            self.assertNotRegex(text, r'/api/recall|recall_server|nhtsa', name)

    def test_the_shared_core_still_imports_and_answers(self):
        core = importlib.import_module('ontology_poc_generator.public_ontology')
        for name in ('build_graph', 'normalize_proposal', 'resolve', 'verify_proposal', 'auto_build_ontology', 'bundle_content_hash'):
            self.assertTrue(callable(getattr(core, name)), name)
        for name in ('ALIAS_SYSTEM_PROMPT', 'ALIAS_PROMPT_VERSION', 'alias_catalog', 'propose_value_aliases',   # only the recall run asked for name pairs
                     'ontology_content_hash'):   # only the recall pack and scope pinned an ontology by hash
            self.assertFalse(hasattr(core, name), name)
        self.assertEqual(core.resolve({'a': [{'b': 1}, {'b': 2}]}, 'a[].b'), [1, 2])

    def test_no_doc_page_or_code_outside_the_history_names_the_recall_line(self):
        names = files()
        here = Path(__file__).resolve()
        found = []
        for name in names:
            path = ROOT / name
            if (HISTORY.match(name) or name.startswith('tests/fixtures/') or path == here or Path(name).suffix not in TEXT
                    or not path.is_file()):
                continue
            for number, line in enumerate(path.read_text(encoding='utf-8', errors='ignore').splitlines(), 1):
                found += [f'{name}:{number}: {m.group(0)}' for m in GONE.finditer(line)]
        self.assertEqual(found, [])


if __name__ == '__main__':
    unittest.main()
