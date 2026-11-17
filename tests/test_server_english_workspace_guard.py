"""Guard for the workspace modules: a Chinese string constant (a sentence, a label, a unit, even a bare full-width punctuation mark) that is not written through
tr(zh, en) (or kept in a TrMap) never reaches the English page. Wider than test_server_english_guard: it reads every string constant of these modules, not only
those in a raise or under a message key.

Limits: it reads the syntax tree only, so a sentence built elsewhere and kept in a variable is seen at the place the string is written, not where it is shown.
What is Chinese on purpose goes in ALLOWED with the reason; a new Chinese string in these files fails here until it is written in both languages or listed."""
import ast
import re
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / 'src' / 'ontology_poc_generator'
FILES = ['ontology_server', 'object_actions', 'object_types', 'explorer', 'object_views', 'accounts', 'object_relations', 'named_views', 'review_queue', 'review_stack',
         'batch_confirm', 'ontology_confirm', 'code_meanings', 'ontology_card', 'workspace_sources', 'source_connect', 'sources_http', 'auth_http', 'workspace_datasets',
         'row_rules', 'type_access', 'notices', 'dashboards', 'name_checks', 'repeated_keys', 'relation_checks', 'anchors', 'use_layer', 'workspace_store', 'ontology_graph']
CJK = re.compile('[一-龥，。；：、（）“”「」？！]')
# (file, text fragment, why it stays Chinese)
ALLOWED = [
    ('ontology_server', '模型请求失败', 'matches the Chinese words of recognition.model_failure_text, which another module writes'),
    ('object_types', '对象类型', 'the kind of a reader of a dataset: a key the page matches (serverWords.js), not a sentence'),
    ('object_types', '管道', 'the kind of a reader of a dataset: a key the page matches (serverWords.js), not a sentence'),
    ('explorer', '名称', 'the words that make a column look like a name: matched against data names'),
    ('explorer', '名', 'the words that make a column look like a name: matched against data names'),
    ('object_views', '出现了新值', 'matches a stored reason written in Chinese (its English twin is matched beside it)'),
    ('ontology_graph', '要重新确认', 'matches a stored reason written in Chinese (its English twin is matched beside it)'),
    ('ontology_graph', '它用的', 'matches a stored reason written in Chinese (its English twin is matched beside it)'),
    ('ontology_graph', '需要再看', 'matches a stored reason written in Chinese (its English twin is matched beside it)'),
    ('dashboards', '没有这个对象类型', 'matches the Chinese refusal when it is read in Chinese (its English twin is matched beside it)'),
    ('workspace_store', '是', 'yes/no words that a CSV cell may hold: data'),
    ('workspace_store', '否', 'yes/no words that a CSV cell may hold: data'),
    ('workspace_sources', '、', 'splits the stored list of dataset names of a run written by the pipeline module'),
    ('workspace_sources', 'UPDATE refresh_run', 'startup recovery, with no request and so no language: the run says the service restarted'),
    ('code_meanings', '你在帮顾问', 'the prompt the model reads, not a sentence a person reads'),
    ('source_connect', '连不上这个数据源', 'GENERIC: the Chinese constant the tests and generic_failure() read; the English twin is beside it'),
    ('accounts', '账号或密码不对', 'GENERIC: the Chinese constant the tests and generic_failure() read; the English twin is beside it'),
    ('accounts', '本机', 'a signature the service writes itself: reserved as a display name'),
    ('accounts', '未署名', 'a signature the service writes itself: reserved as a display name'),
    ('auth_http', '本机', 'the signature of the one local person when sign-in is off'),
    ('named_views', '_含义', 'the suffix of a column the view adds: a data name'),
    ('named_views', '_当前', 'the suffix of a view the service names: a data name'),
    ('named_views', '_行号', 'a column the view adds: a data name'),
    ('named_views', '_排名', 'a column the view adds: a data name'),
    ('repeated_keys', '年', 'a date pattern that reads Chinese dates in the data'),
    ('name_checks', '中位', 'words a column name may use to claim a statistic: matched against data names'),
    ('name_checks', '平均', 'words a column name may use to claim a statistic: matched against data names'),
    ('name_checks', '合计', 'words a column name may use to claim a statistic: matched against data names'),
    ('name_checks', '最大', 'words a column name may use to claim a statistic: matched against data names'),
    ('name_checks', '最小', 'words a column name may use to claim a statistic: matched against data names'),
    ('name_checks', '：', 'the punctuation trimmed from the edges of a column name: matched against data names'),
]
# modules with a bare-string sentence still Chinese on purpose, with the reason: the operator's command line, startup configuration errors, files made for a Chinese platform
WHOLE_FILE_PARTS = {
    'accounts': ('的密码（至少', '个字符）', '再输一次', '两次不一样', '已建好管理员', '账号：', '没有叫“', '”的账号', '停用', '启用', '密码已重置'),   # the create-admin / reset-password command line
    'auth_http': ('--no-auth', '地址“', '”要写成', '”不是本机'),   # startup configuration errors for the operator
}


def chinese_outside_tr(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def in_tr(node):
        while node in parents:
            node = parents[node]
            if isinstance(node, ast.Call) and getattr(node.func, 'id', None) in ('tr', 'TrMap', 'WordMap'):
                return True
        return False

    def docstring_like(node):
        cur = node
        while cur in parents and not isinstance(cur, ast.Expr):
            cur = parents[cur]
        return isinstance(cur, ast.Expr)

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and CJK.search(node.value) and not docstring_like(node) and not in_tr(node):
            found.append((node.lineno, node.value))
    return sorted(set(found))


class WorkspaceEnglishGuardTest(unittest.TestCase):
    def test_no_chinese_string_in_the_workspace_modules_is_left_outside_tr(self):
        problems = []
        for name in FILES:
            for line, text in chinese_outside_tr(SRC / f'{name}.py'):
                if any(name == f and frag in text for f, frag, _ in ALLOWED) or any(frag in text for frag in WHOLE_FILE_PARTS.get(name, ())):
                    continue
                problems.append(f'{name}.py:{line}: {text[:50]}')
        self.assertEqual(problems, [], 'write these in both languages with tr(zh, en), or list them in ALLOWED with the reason:\n' + '\n'.join(problems))

    def test_every_allowed_exception_still_exists(self):
        stale = []
        for name, frag, _ in ALLOWED:
            if not any(frag in text for _, text in chinese_outside_tr(SRC / f'{name}.py')):
                stale.append(f'{name}: {frag}')
        self.assertEqual(stale, [], 'these exceptions no longer match any string: remove them')

    def test_the_net_does_catch_a_bare_chinese_label(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            sample = Path(folder) / 'sample.py'
            sample.write_text("LABELS = {'a': '数据变了'}\nTITLE = f'{x}（{y}）'\nFINE = tr('数据变了', 'Data changed')\ndef f():\n    '''文档字符串'''\n", encoding='utf-8')
            self.assertEqual([text for _, text in chinese_outside_tr(sample)], ['数据变了', '（', '）'])


if __name__ == '__main__':
    unittest.main()
