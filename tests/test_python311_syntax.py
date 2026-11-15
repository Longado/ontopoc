"""The package says it runs on Python 3.11 and CI runs 3.11, but people develop on 3.12 or later,
where an f-string may reuse its own quote inside a replacement field (PEP 701). On 3.11 that line is a
SyntaxError and every module importing the file fails. This reads the 3.12+ tokenizer's f-string tokens
and names each such line, so the mistake is caught where it is written, not only in CI."""
import io
import sys
import tokenize
import unittest
from pathlib import Path

SOURCES = Path(__file__).resolve().parents[1] / 'src'


def _quote(text):
    bare = text.lstrip('rRbBuUfF')
    return bare[:3] if bare[:3] in ('"""', "'''") else bare[:1]


def lines_python311_rejects(source):
    """(line, why) for each construct in `source` that 3.11 cannot parse."""
    found = []
    open_fstrings = []   # [quote, depth of {} inside it]
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        inside = bool(open_fstrings) and open_fstrings[-1][1] > 0
        if tok.type == tokenize.FSTRING_START:
            if inside and any(_quote(tok.string)[0] == q[0] for q, _ in open_fstrings):
                found.append((tok.start[0], 'an f-string inside a replacement field reuses an enclosing quote'))
            open_fstrings.append([_quote(tok.string), 0])
        elif not open_fstrings:
            continue
        elif tok.type == tokenize.FSTRING_END:
            open_fstrings.pop()
        elif tok.type == tokenize.OP and tok.string == '{':
            open_fstrings[-1][1] += 1
        elif tok.type == tokenize.OP and tok.string == '}':
            open_fstrings[-1][1] = max(0, open_fstrings[-1][1] - 1)
        elif inside and tok.type == tokenize.STRING:
            if any(_quote(tok.string)[0] == q[0] for q, _ in open_fstrings):
                found.append((tok.start[0], 'a string inside a replacement field reuses an enclosing quote'))
            if '\\' in tok.string:
                found.append((tok.start[0], 'a backslash inside a replacement field'))
        elif inside and tok.type == tokenize.COMMENT:
            found.append((tok.start[0], 'a comment inside a replacement field'))
    return found


@unittest.skipIf(sys.version_info < (3, 12), 'on 3.11 importing the package already fails on such a line')
class Python311SyntaxTests(unittest.TestCase):
    def test_the_checker_names_a_reused_quote_and_passes_a_different_one(self):
        self.assertEqual([1], [line for line, _ in lines_python311_rejects("x = f'{d['k']}'\n")])
        self.assertEqual([], lines_python311_rejects("x = f'{d[\"k\"]}'\n"))
        self.assertEqual({1}, {line for line, _ in lines_python311_rejects('x = f"{", ".join(f"{w["n"]}" for w in ws)}"\n')})

    def test_no_source_file_uses_f_string_syntax_that_python_3_11_rejects(self):
        problems = [f'{path.relative_to(SOURCES)}:{line}: {why}'
                    for path in sorted(SOURCES.rglob('*.py'))
                    for line, why in lines_python311_rejects(path.read_text(encoding='utf-8'))]
        self.assertEqual([], problems)


if __name__ == '__main__':
    unittest.main()
