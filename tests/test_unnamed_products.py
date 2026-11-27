"""The repository does not name the platform OntoPoc was compared with during its design.

The name is kept here only as the SHA-256 of its lower-case letters, so this file does not carry it either. Checked:
- every tracked text file, for the name written as a capitalised word (an ordinary lower-case English word with the same letters is allowed);
- the MCP tools' names (any case) and descriptions (capitalised), which the old check in test_mcp_form covered.
To compare with another product in a comment, a test title or the docs, describe what it does instead of naming it.
"""
import hashlib
import re
import subprocess
import unittest
from pathlib import Path

from ontology_poc_generator.mcp_server import handle

ROOT = Path(__file__).resolve().parents[1]
NAME_SHA256 = 'b6813f3af2d45fbfc768b3966d5de7f665d648958610362bebb63372052d0f0d'
WORD = re.compile(r'[A-Za-z]+')


def is_name(word, any_case=False):
    return (any_case or word.isupper()) and hashlib.sha256(word.lower().encode()).hexdigest() == NAME_SHA256


def tracked_files():
    try:
        out = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return [ROOT / p.decode() for p in out.split(b'\0') if p]


class UnnamedProductTests(unittest.TestCase):
    def test_no_tracked_text_file_names_the_platform(self):
        files = tracked_files()
        if files is None:
            self.skipTest('not a git checkout')
        found = []
        for path in files:
            try:
                text = path.read_bytes().decode('utf-8')
            except (OSError, UnicodeDecodeError):
                continue   # binary or gone from the working tree
            if not any(is_name(w) for w in set(WORD.findall(text))):
                continue
            found += [f'{path.relative_to(ROOT)}:{n}' for n, line in enumerate(text.splitlines(), 1) if any(is_name(w) for w in WORD.findall(line))]
        self.assertEqual(found, [], 'describe the platform instead of naming it')

    def test_no_mcp_tool_names_the_platform(self):
        tools = handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']
        self.assertGreater(len(tools), 0)
        self.assertEqual([t['name'] for t in tools if any(is_name(w, any_case=True) for w in WORD.findall(t['name']))
                          or any(is_name(w) for w in WORD.findall(t['description']))], [])

    def test_the_check_finds_the_name_and_leaves_the_ordinary_word(self):
        name = bytes.fromhex('444950').decode()   # the name's capitals, spelled out as bytes so a search of the repository does not find them
        self.assertTrue(is_name(name))
        self.assertTrue(is_name(name.lower(), any_case=True))
        self.assertFalse(is_name(name.lower()))
        self.assertFalse(is_name(name.capitalize()))
        self.assertFalse(is_name(name + 'S'))


if __name__ == '__main__':
    unittest.main()
