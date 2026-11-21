"""The historical plans, hand-offs and retros live in docs/archive/, and nothing points at where they used to be."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'docs' / 'archive'

MOVED = [
    *[f'PRD_ITERATION_{n}.md' for n in range(2, 10)],
    'FEATURES_2026-09-13.md',
    'FEATURES_2026-09-16.md',
    'HANDOFF_2026-09-13.md',
    'HANDOFF_ACCEPTANCE_REPAIR_2026-10-01.md',
    'HANDOFF_NAVIGATION_FUNCTIONS_2026-10-01.md',
    'RETRO_2026-09-18.md',
    'RETRO_2026-09-19.md',
    'SEMANTIC_MODELING_2026-10-01.md',
    'NHTSA_AUTO_ONTOLOGY_PLAN.md',
    'PLAYGROUND_INTERNALIZATION.md',
]
TEXT = {'.md', '.html', '.css', '.js', '.jsx', '.mjs', '.py', '.json', '.toml', '.yml', '.yaml', '.txt', '.xml'}
LINK = re.compile(r'\]\(([^)\s]+)\)|href="([^"]+)"|src="([^"]+)"')


def tracked():
    names = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    return [ROOT / name for name in names if Path(name).suffix in TEXT and (ROOT / name).is_file()]


class DocsArchiveTests(unittest.TestCase):
    def test_each_historical_doc_is_in_the_archive_and_not_at_its_old_place(self):
        for name in MOVED:
            self.assertTrue((ARCHIVE / name).is_file(), name)
            self.assertFalse((ROOT / 'docs' / name).exists(), name)
        self.assertTrue((ARCHIVE / 'superpowers' / 'plans').is_dir())
        self.assertFalse((ROOT / 'docs' / 'superpowers').exists())

    def test_the_archive_says_what_it_is(self):
        readme = (ARCHIVE / 'README.md').read_text(encoding='utf-8')
        self.assertIn('history', readme.casefold())
        self.assertIn('PRODUCT.md', readme)

    def test_nothing_outside_the_archive_names_an_archived_doc_at_its_old_path(self):
        names = '|'.join(re.escape(name) for name in MOVED) + r'|superpowers/plans'
        old = re.compile(rf'(?<!archive/)(?<![\w/])(?:docs/)?(?:{names})')
        here = Path(__file__).resolve()
        found = []
        for path in tracked():
            if path == here or ARCHIVE in path.parents:
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
            found += [f'{path.relative_to(ROOT)}: {m.group(0)}' for m in old.finditer(text)]
        self.assertEqual(found, [])

    def test_inside_the_archive_a_repo_path_to_an_archived_doc_says_archive(self):
        names = '|'.join(re.escape(name) for name in MOVED) + r'|superpowers/'
        old = re.compile(rf'docs/(?:{names})')
        found = []
        for path in ARCHIVE.rglob('*.md'):
            found += [f'{path.relative_to(ROOT)}: {m.group(0)}' for m in old.finditer(path.read_text(encoding='utf-8'))]
        self.assertEqual(found, [])

    def test_every_relative_link_in_the_docs_and_readmes_reaches_a_file(self):
        broken = []
        for path in tracked():
            if path.suffix not in {'.md', '.html'} or path.parts[len(ROOT.parts)] in {'examples', 'experiments', 'landing-page'}:
                continue
            for match in LINK.finditer(path.read_text(encoding='utf-8', errors='ignore')):
                target = next(group for group in match.groups() if group)
                if re.match(r'^(?:[a-z]+:|#|/|\{|\$|<)', target):
                    continue
                target = target.split('#')[0].split('?')[0]
                if target and not (path.parent / target).exists():
                    broken.append(f'{path.relative_to(ROOT)} -> {target}')
        self.assertEqual(broken, [])


if __name__ == '__main__':
    unittest.main()
