"""Guard: a Chinese sentence in a raise or in an 'error' / 'reason' / 'why' / ... entry of the question, query, pipeline, derived-value and AI modules must be written
through tr(zh, en), so the English page never shows it.

Limits (it is a pragmatic net, not a proof): it reads the syntax tree only. It sees a Chinese string constant that sits directly in a raise, or a dict value under
one of the message keys below. It does not see a sentence built in one place, kept in a variable or a module constant, and raised somewhere else, nor a Chinese
word that is data (a type name, a query keyword). Deliberate exceptions go in ALLOWED with the reason."""
import ast
import re
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / 'src' / 'ontology_poc_generator'
FILES = ['derived_properties', 'derived_measures', 'ontopoc_query', 'ontology_questions', 'workspace_questions', 'answer_checks', 'caliber',
         'pipeline_ops', 'pipeline_llm', 'pipeline_llm_review', 'pipeline_spec', 'pipeline_assist', 'pipeline_expr', 'pipeline_funcs', 'pipelines',
         'workspace_pipelines', 'workspace_schedules', 'workspace_ai', 'workspace_llm', 'object_type_suggest', 'field_descriptions', 'ask_budget', 'recall_scope']
KEYS = {'error', 'reason', 'why', 'message', 'line', 'summary', 'explain', 'explanation', 'note', 'warning', 'problem', 'detail', 'refusal'}
CJK = re.compile('[一-龥]')
# (file, text fragment): Chinese on purpose, and why
ALLOWED = set()


def chinese_outside_tr(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def in_tr(node):
        while node in parents:
            node = parents[node]
            if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'tr':
                return True
        return False

    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str) and CJK.search(node.value)) or isinstance(parents.get(node), ast.Expr) or in_tr(node):
            continue
        flagged, cur = False, node
        while cur in parents:
            parent = parents[cur]
            if isinstance(parent, ast.Raise):
                flagged = True
            if isinstance(parent, ast.Dict) and cur in parent.values:
                key = parent.keys[parent.values.index(cur)]
                if isinstance(key, ast.Constant) and key.value in KEYS:
                    flagged = True
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module, ast.ClassDef)):
                break
            cur = parent
        if flagged:
            found.append((node.lineno, node.value[:40]))
    return found


class ServerEnglishGuardTest(unittest.TestCase):
    def test_no_chinese_sentence_is_raised_or_returned_as_a_message_outside_tr(self):
        problems = []
        for name in FILES:
            for line, text in chinese_outside_tr(SRC / f'{name}.py'):
                if not any(name == f and frag in text for f, frag in ALLOWED):
                    problems.append(f'{name}.py:{line}: {text}')
        self.assertEqual(problems, [], 'wrap these in tr(zh, en):\n' + '\n'.join(problems))

    def test_the_net_does_catch_a_bare_chinese_sentence(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            sample = Path(folder) / 'sample.py'
            sample.write_text("def f(x):\n    if x:\n        raise ValueError('不行')\n    ok = {'error': '坏了'}\n    fine = {'error': tr('坏了', 'broken')}\n    return ok, fine\n", encoding='utf-8')
            self.assertEqual(sorted(text for _, text in chinese_outside_tr(sample)), sorted(['不行', '坏了']))


if __name__ == '__main__':
    unittest.main()
