"""The old internal documents are gone from the repo, nothing points at them, and every relative link still reaches a file."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'docs' / 'archive'

TEXT = {'.md', '.html', '.css', '.js', '.jsx', '.mjs', '.py', '.json', '.toml', '.yml', '.yaml', '.txt', '.xml'}
SKIP_DIRS = {'.git', 'node_modules', '.venv', '__pycache__', 'dist', 'build'}
LINK = re.compile(r'\]\(([^)\s]+)\)|href="([^"]+)"|src="([^"]+)"')
OLD_REFERENCE = re.compile(r'docs/archive|(?<![\w.])archive/(?:PRD_|FEATURES_|HANDOFF_|RETRO_|SEMANTIC_|NHTSA_|PLAYGROUND_|README|superpowers)')


def tracked():
    try:
        names = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
        paths = [ROOT / name for name in names]
    except (OSError, subprocess.CalledProcessError):
        paths = [p for p in ROOT.rglob('*') if not SKIP_DIRS & set(p.relative_to(ROOT).parts)]
    return [p for p in paths if p.suffix in TEXT and p.is_file()]


class DocsArchiveTests(unittest.TestCase):
    def test_the_archive_folder_is_gone(self):
        self.assertFalse(ARCHIVE.exists())

    def test_nothing_in_the_repo_points_at_the_archive(self):
        here = Path(__file__).resolve()
        found = []
        for path in tracked():
            if path == here:
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
            found += [f'{path.relative_to(ROOT)}: {m.group(0)}' for m in OLD_REFERENCE.finditer(text)]
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
