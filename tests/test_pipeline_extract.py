"""The extract operator: split a text column on a literal separator and take one part into a new text column. A row without the separator, or with fewer parts than
asked, gets an empty value, and the trial run and the run say how many; nothing is guessed. Expected values are worked out here with str.split, row by row, not by
the code under test.

The walk of the card's example: 100 injection statements, 63 written as "<variable>=<value>" and 37 not; extract part 1 on "=", write it out, and a relation from the
statement to a variables table (60 of the 63 names are in it) says how many rows did not connect."""
from collections import Counter
from urllib.parse import quote

from ontology_poc_generator.pipeline_ops import new_context
from ontology_poc_generator.pipelines import run_pipeline
from tests.test_object_relations import table_csv
from tests.test_pipeline_ops import Workspace, store
from tests.test_two_person import SigningTestCase

PIPELINES = '/api/workspace/pipelines'
ENGLISH = {'headers': {'Accept-Language': 'en'}}

INJECTIONS = [{'id': f'I{i:03d}', 'statement': f'Var{i}_set={i % 4}' if i <= 63 else f'set Var{i} to {i % 4}'} for i in range(1, 101)]
VARIABLES = [{'name': f'Var{i}_set', 'unit': 'flag'} for i in range(1, 61)]
EXTRACT = {'op': 'extract', 'column': 'statement', 'separator': '=', 'part': 1, 'as': 'variable'}
SPEC = {'steps': [{'id': 'in', 'type': 'input', 'dataset': 'injections'}, {'id': 't', 'type': 'transform', 'from': 'in', 'operators': [EXTRACT]},
                  {'id': 'out', 'type': 'output', 'from': 't', 'name': 'injection_vars', 'key': {'columns': ['id']}}]}
INJECTION = {'english_name': 'injection', 'name': '注入', 'dataset': 'injection_vars', 'key': ['id'], 'properties': [{'column': 'statement'}, {'column': 'variable'}]}
VARIABLE = {'english_name': 'variable', 'name': '变量', 'dataset': 'variables', 'key': ['name'], 'properties': [{'column': 'unit'}]}
RELATION = {'english_name': 'injection_variable', 'name': '注入的变量', 'from': 'injection', 'to': 'variable', 'cardinality': 'many_to_one',
            'from_column': 'variable', 'to_column': 'name'}


def part_of(value, separator, part):
    """What the card says a row gets, worked out with str.split: None without the separator or past the end."""
    if value is None or separator not in value:
        return None
    pieces = value.split(separator)
    if part == 'last':
        return pieces[-1]
    return pieces[part - 1] if part <= len(pieces) else None


class ExtractOperatorTests(Workspace):
    ROWS = [{'id': '1', 'v': 'a=b=c'}, {'id': '2', 'v': 'plain'}, {'id': '3', 'v': None}, {'id': '4', 'v': 'x=y'}, {'id': '5', 'v': ''}, {'id': '6', 'v': '=lead'},
            {'id': '7', 'v': 'k::v::w'}, {'id': '8', 'v': 'p.q|r'}, {'id': '9', 'v': 'u[=]w'}, {'id': '10', 'v': 'Var1_set=3'}]

    def setUp(self):
        self.tables = store(self.conn, {'t': self.ROWS})

    def values(self, op):
        rows = self.rows([op], 't', self.tables)
        return [r[-1] for r in rows]

    def report(self, op, tables=None):
        return self.run_ops([op], 't', tables=tables or self.tables)['t']['operators'][0]

    def expected(self, separator, part):
        return [part_of(r['v'], separator, part) for r in self.ROWS]

    def test_part_one_of_the_cards_example_is_the_variable_name(self):
        values = self.values({**EXTRACT, 'column': 'v'})
        self.assertEqual(values[-1], 'Var1_set')
        self.assertEqual(values, self.expected('=', 1))

    def test_part_two_the_last_part_and_a_part_past_the_end_which_is_empty(self):
        for part in (2, 3, 'last', 4, 9):
            with self.subTest(part=part):
                self.assertEqual(self.values({'op': 'extract', 'column': 'v', 'separator': '=', 'part': part, 'as': 'p'}), self.expected('=', part))
        self.assertEqual(self.values({'op': 'extract', 'column': 'v', 'separator': '=', 'part': 2, 'as': 'p'})[0], 'b')
        self.assertEqual(self.values({'op': 'extract', 'column': 'v', 'separator': '=', 'part': 'last', 'as': 'p'})[0], 'c')
        self.assertEqual(self.values({'op': 'extract', 'column': 'v', 'separator': '=', 'part': 4, 'as': 'p'})[0], None)   # a=b=c has three parts

    def test_a_row_without_the_separator_gets_an_empty_value_even_for_the_last_part(self):
        for part in (1, 'last'):
            values = self.values({'op': 'extract', 'column': 'v', 'separator': '=', 'part': part, 'as': 'p'})
            self.assertEqual((values[1], values[2], values[4]), (None, None, None))   # plain, empty, missing: never the whole value

    def test_a_multi_character_separator(self):
        self.assertEqual(self.values({'op': 'extract', 'column': 'v', 'separator': '::', 'part': 2, 'as': 'p'}), self.expected('::', 2))
        self.assertEqual(self.values({'op': 'extract', 'column': 'v', 'separator': '::', 'part': 2, 'as': 'p'})[6], 'v')
        self.assertEqual(self.values({'op': 'extract', 'column': 'v', 'separator': 'set=', 'part': 'last', 'as': 'p'})[9], '3')

    def test_a_separator_that_looks_like_a_pattern_is_taken_literally(self):
        for separator in ('.', '|', '[=]', '.*', '\\', '(', 'a|='):
            with self.subTest(separator=separator):
                self.assertEqual(self.values({'op': 'extract', 'column': 'v', 'separator': separator, 'part': 1, 'as': 'p'}), self.expected(separator, 1))
        self.assertEqual(self.values({'op': 'extract', 'column': 'v', 'separator': '.', 'part': 2, 'as': 'p'})[7], 'q|r')   # '.' is a dot, not any character
        self.assertEqual(self.values({'op': 'extract', 'column': 'v', 'separator': '[=]', 'part': 1, 'as': 'p'})[8], 'u')
        self.assertEqual(self.values({'op': 'extract', 'column': 'v', 'separator': '.*', 'part': 1, 'as': 'p'}), [None] * len(self.ROWS))   # no row holds ".*"
        with self.assertRaises(ValueError) as caught:   # a request for a pattern is refused, not quietly read as text
            self.run_ops([{'op': 'extract', 'column': 'v', 'separator': '=+', 'part': 1, 'as': 'p', 'regex': True}], 't', tables=self.tables)
        self.assertIn('不支持正则', str(caught.exception))

    def test_the_rows_without_the_separator_and_the_rows_past_the_end_are_counted(self):
        rows = [r['v'] for r in self.ROWS]
        without = sum(1 for v in rows if v is None or '=' not in v)
        blank = sum(1 for v in rows if not v)
        report = self.report({'op': 'extract', 'column': 'v', 'separator': '=', 'part': 3, 'as': 'p'})
        short = sum(1 for v in rows if v and '=' in v and len(v.split('=')) < 3)
        self.assertEqual((report['rows_in'], report['without_separator'], report['empty_source'], report['short']), (len(rows), without, blank, short))
        self.assertEqual((without, blank, short), (5, 2, 4))
        self.assertEqual(report['affected'], sum(1 for v in rows if part_of(v, '=', 3) is not None))
        self.assertIn(f'{len(rows)} 行里有 {without} 行没有“=”', report['text'])
        self.assertIn(f'{short} 行', report['text'])
        self.assertEqual([e['row'] for e in report['without_examples']], [2, 3, 5, 7, 8])
        self.assertEqual(report['without_examples'][0]['value'], 'plain')
        whole = self.report({'op': 'extract', 'column': 'v', 'separator': '=', 'part': 1, 'as': 'p'})
        self.assertEqual((whole['without_separator'], whole['short']), (without, 0))

    def test_the_new_column_is_text_new_and_keeps_the_source_columns_lineage_and_marks(self):
        found = {}
        spec = {'steps': [{'id': 'in', 'type': 'input', 'dataset': 't'}, {'id': 'x', 'type': 'transform', 'from': 'in', 'operators': [{'op': 'extract', 'column': 'v', 'separator': '=', 'part': 1, 'as': 'p'}]}]}
        origin = 't.v'
        ctx = new_context(unsent={origin}, ai={origin})
        run_pipeline(self.conn, spec, self.tables, ctx=ctx, after=lambda conn, node, compiled: found.update({node['id']: compiled['columns']}))
        new = next(c for c in found['x'] if c['name'] == 'p')
        self.assertEqual((new['type'], new['badge'], new.get('unsent'), new.get('ai')), ('text', 'new', True, True))   # what may not go to the model stays so
        self.assertEqual(new['extracted'], {'column': 'v', 'origin': origin, 'separator': '=', 'part': 1})
        self.assertNotIn('origin', new)   # not read as the stored column itself: its confirmed meanings and code list stay with the source
        self.assertEqual([c['name'] for c in found['x']], [c['name'] for c in found['in']] + ['p'])
        self.assertEqual([c for c in found['x'] if c['name'] != 'p'], found['in'])   # the other columns are untouched

    def test_a_repeated_column_s_copy_mark_goes_with_the_part(self):
        tables = store(self.conn, {'orders': [{'oid': 'O1', 'code': 'A-1'}, {'oid': 'O2', 'code': 'B-2'}], 'lines': [{'lid': 'L1', 'oid': 'O1'}, {'lid': 'L2', 'oid': 'O1'}, {'lid': 'L3', 'oid': 'O2'}]})
        spec = {'steps': [{'id': 'l', 'type': 'input', 'dataset': 'lines'}, {'id': 'o', 'type': 'input', 'dataset': 'orders'},
                          {'id': 'j', 'type': 'join', 'left': 'l', 'right': 'o', 'how': 'left', 'on': [{'left': 'oid', 'right': 'oid'}]},
                          {'id': 'x', 'type': 'transform', 'from': 'j', 'operators': [{'op': 'extract', 'column': 'code', 'separator': '-', 'part': 1, 'as': 'letter'}]}]}
        found = {}
        result = run_pipeline(self.conn, spec, tables, after=lambda conn, node, compiled: found.update({node['id']: compiled['columns']}))
        code = next(c for c in found['x'] if c['name'] == 'code')
        letter = next(c for c in found['x'] if c['name'] == 'letter')
        self.assertTrue(code.get('rep'))
        self.assertEqual(letter.get('rep'), code.get('rep'))   # O1 stands on two lines: its letter is copied as its code is
        self.assertEqual(next(n for n in result['nodes'] if n['id'] == 'x')['rows_out'], 3)

    def test_what_cannot_be_run_is_refused_in_words(self):
        bad = [({'separator': ''}, '1 到 10 个字'), ({'separator': 'x' * 11}, '1 到 10 个字'), ({'separator': 3}, '1 到 10 个字'), ({'part': 0}, '第几段'), ({'part': 'first'}, '第几段'),
               ({'part': True}, '第几段'), ({'part': 1.5}, '第几段'), ({'part': 101}, '第几段'), ({'as': 'id'}, '已经有叫「id」的列'), ({'as': 'v'}, '已经有叫「v」的列'), ({'as': ''}, '新列的名字'),
               ({'column': 'nope'}, '没有列「nope」'), ({'column': None}, '没选列')]
        for change, words in bad:
            with self.subTest(change=change):
                with self.assertRaises(ValueError) as caught:
                    self.run_ops([{**EXTRACT, 'column': 'v', 'as': 'p', **change}], 't', tables=self.tables)
                self.assertIn(words, str(caught.exception))
        numbers = store(self.conn, {'n': [{'id': '1', 'amount': '12'}]})
        with self.assertRaises(ValueError) as caught:
            self.run_ops([{'op': 'extract', 'column': 'amount', 'separator': '1', 'part': 1, 'as': 'p'}], 'n', tables=numbers)
        self.assertIn('只用在文本列上', str(caught.exception))
        self.assertEqual(self.values({'op': 'extract', 'column': 'v', 'separator': ' ', 'part': 1, 'as': 'p'}), self.expected(' ', 1))   # a space is a separator like any other


class ExtractThroughTheServiceTests(SigningTestCase):
    def team(self, base):
        team = self.people(base, 'ann', 'bob')
        status, body = team['ann'].post('/api/workspace/datasets/upload', {'files': [table_csv('injections.csv', INJECTIONS), table_csv('variables.csv', VARIABLES)]})
        self.assertEqual(status, 200, body)
        return team

    def confirm(self, bob, name):
        shown = bob.get(f'{PIPELINES}/{quote(name)}')[1]
        status, body = bob.post(f'{PIPELINES}/confirm', {'id': name, 'version': shown['version'], 'seen': {'inputs': shown['inputs_now']}})
        self.assertEqual(status, 200, body)

    def typed(self, team, t):
        status, body = team['ann'].post('/api/workspace/types', t)
        self.assertEqual(status, 200, body)
        shown = team['bob'].get(f'/api/workspace/types/{t["english_name"]}')[1]
        status, body = team['bob'].post('/api/workspace/types/confirm', {'id': t['english_name'], 'version': shown['version'], 'seen': shown['seen']})
        self.assertEqual(status, 200, body)

    def test_the_cards_example_through_a_trial_a_run_and_a_relation_that_says_how_many_rows_did_not_connect(self):
        names = [part_of(r['statement'], '=', 1) for r in INJECTIONS]
        without = names.count(None)
        known = {v['name'] for v in VARIABLES}
        unmatched = sum(1 for n in names if n is not None and n not in known)
        self.assertEqual((len(INJECTIONS), without, unmatched), (100, 37, 3))
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            status, body = ann.post(PIPELINES, {'name': '注入变量', 'description': '注入语句里的变量名', 'spec': SPEC})
            self.assertEqual(status, 200, body)
            # the trial run, in both languages
            status, trial = ann.post(f'{PIPELINES}/summary', {'id': '注入变量'})
            self.assertEqual(status, 200, trial)
            op = next(n for n in trial['nodes'] if n['id'] == 't')['operators'][0]
            self.assertEqual((op['without_separator'], op['rows_in']), (without, 100))
            self.assertIn('100 行里有 37 行没有“=”', op['text'])
            status, trial = ann.post(f'{PIPELINES}/summary', {'id': '注入变量'}, **ENGLISH)
            self.assertIn('37 of 100 rows had no "="', next(n for n in trial['nodes'] if n['id'] == 't')['operators'][0]['text'])
            status, preview = ann.post(f'{PIPELINES}/preview', {'id': '注入变量', 'node': 't', 'operator': 0})
            self.assertEqual(status, 200, preview)
            at = [c['name'] for c in preview['columns']].index('variable')
            self.assertEqual([r[at] for r in preview['rows']], names[:len(preview['rows'])])
            self.assertEqual(preview['columns'][at]['type'], 'text')
            self.assertEqual((preview['columns'][at]['badge'], preview['columns'][at]['extracted']), ('new', {'column': 'statement', 'origin': 'injections.statement', 'separator': '=', 'part': 1}))
            # the run, its record, the dataset
            self.confirm(bob, '注入变量')
            status, run = ann.post(f'{PIPELINES}/run', {'id': '注入变量'})
            self.assertEqual((status, run['status']), (200, 'success'), run)
            op = next(n for n in run['nodes'] if n['id'] == 't')['operators'][0]
            self.assertEqual((op['without_separator'], op['affected']), (without, 100 - without))
            self.assertIn('100 行里有 37 行没有“=”', op['text'])
            kept = ann.get(f'{PIPELINES}/{quote("注入变量")}/runs/{run["id"]}')[1]
            self.assertEqual(next(n for n in kept['nodes'] if n['id'] == 't')['operators'][0]['without_separator'], without)
            page = ann.get('/api/workspace/datasets/injection_vars')[1]
            self.assertEqual((page['rows'], [c['name'] for c in page['columns']]), (100, ['id', 'statement', 'variable']))
            conn = self.db(out)
            table = conn.execute("SELECT d.table_name FROM dataset d JOIN current_dataset c ON c.dataset_id = d.id WHERE c.name = 'injection_vars'").fetchone()[0]
            stored = dict(conn.execute(f'SELECT "id", "variable" FROM "{table}"').fetchall())
            conn.close()
            self.assertEqual(stored, {r['id']: n for r, n in zip(INJECTIONS, names)})
            # a relation on the new column: how many rows did not connect
            self.typed(team, VARIABLE)
            self.typed(team, INJECTION)
            status, body = ann.post('/api/workspace/relations', RELATION)
            self.assertEqual(status, 200, body)
            self.assertEqual((body['numbers']['rows'], body['numbers']['matched'], body['numbers']['unmatched']), (100, 100 - without - unmatched, unmatched))
            detail = ann.get('/api/workspace/relations/injection_variable')[1]
            self.assertEqual(detail['check']['empty'], without)
            self.assertEqual(Counter(s['key'] for s in detail['check']['samples']), Counter({'Var61_set': 1, 'Var62_set': 1, 'Var63_set': 1}))
            self.assertIn('3 行注入找不到变量', ' '.join(e['text'] for e in detail['lines']))

    def test_the_editor_is_offered_extract_in_both_languages(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            zh = {o['op']: o for o in ann.get(f'{PIPELINES}/options')[1]['operators']}
            en = {o['op']: o for o in ann.get(f'{PIPELINES}/options', **ENGLISH)[1]['operators']}
            self.assertEqual((zh['extract']['name'], en['extract']['name']), ('拆分取段', 'Extract part'))
            self.assertIn('原样', zh['extract']['text'])
            self.assertIn('literal', en['extract']['text'])
