"""Value rules on the properties of an object type, walked through the real service. A builder writes rules on the type's columns (not empty; greater than, at
least, less than, at most or between numbers; one of the codes that have a meaning; one date not before another); code counts the rows that break each one,
a second person confirms the type with its rules, and new data that breaks a confirmed rule sends the type back.

Every count here is compared with a plain SQL query over the same stored rows, written in the test with its own number and date tests (Python's, registered
on the test's connection), so the service's checks are measured against an independent statement of what each rule means:
- an empty cell (no value, or only spaces) breaks "not empty" and is not judged by any other rule;
- a filled cell that is not a plain number (-12, 3.5) breaks a number rule;
- a filled cell that is not a real date (2026-02-30, "soon") breaks a date rule; a date alone is the start of its day."""
import base64
import csv
import io
import json
import re
import sqlite3
import unittest
from datetime import date, datetime, timedelta

from ontology_poc_generator import value_rules
from tests.test_object_types import MEANINGS, ORDER, TABLES, orders_upload
from tests.test_two_person import SigningTestCase
from tests.test_workspace_questions import AskModel, cancelled

EN = {'Accept-Language': 'en'}
NUMBER = re.compile(r'-?[0-9]+(\.[0-9]+)?')
LEDGER_COLUMNS = ['编号', '金额', '数量', '状态', '备注', '下单日期', '发货日期', '奇"怪']


def ledger_rows(messy: bool = False) -> list[dict]:
    """60 rows with every edge a rule meets: zero, negatives, empties, a bound itself; `messy` adds text that is not a number and dates that do not exist."""
    rows = []
    for i in range(60):
        ordered = date(2026, 1, 1) + timedelta(days=i % 28)
        delta = [-2, 0, 3, None][i % 4]
        rows.append({'编号': f'R{i:03d}', '金额': ['10.5', '0', '-3', None, '250', '1000.5', '-0.5', '7'][i % 8], '数量': ['1', '5', '100', '101', None, '50', '0'][i % 7],
                     '状态': ['A', 'B', 'C', 'A', None][i % 5], '备注': ['ok', None, 'fine'][i % 3], '下单日期': None if i % 9 == 4 else ordered.isoformat(),
                     '发货日期': None if delta is None else (ordered + timedelta(days=delta)).isoformat(), '奇"怪': ['1', '-1', None, '2'][i % 4]})
    if messy:
        for i, r in enumerate(rows):
            if i % 10 == 1:
                r['金额'] = ['abc', '1e3', '12.', '-', '5.5.5', '１２'][i // 10]   # none of them a plain number
            if i % 11 == 2:
                r['下单日期'] = ['2026-02-30', 'soon', '2026-13-01', '2026-1-5', '20260105', '2026-02-29'][i // 11]   # none of them a real date
            if i % 13 == 3:
                r['数量'] = '七'
    return rows


def ledger_upload(rows, mode=None) -> dict:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=LEDGER_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return {'filename': '账目.csv', 'content_base64': base64.b64encode(out.getvalue().encode('utf-8')).decode(), **({'target': '账目', 'mode': mode} if mode else {})}


LEDGER_RULES = [
    {'column': '备注', 'check': 'not_empty'},
    {'column': '金额', 'check': 'gt', 'value': 0},
    {'column': '金额', 'check': 'ge', 'value': 0},
    {'column': '数量', 'check': 'lt', 'value': 100},
    {'column': '数量', 'check': 'le', 'value': 100},
    {'column': '数量', 'check': 'between', 'low': 1, 'high': 50},
    {'column': '状态', 'check': 'in_codes'},
    {'column': '发货日期', 'check': 'not_before', 'other': '下单日期'},
    {'column': '金额', 'check': 'between', 'low': -1, 'high': 1000.5},
    {'column': '奇"怪', 'check': 'gt', 'value': 0},
]
LEDGER = {'english_name': 'ledger', 'name': '账目', 'dataset': '账目', 'key': ['编号'],
          'properties': [{'column': c, **({'enum': True} if c == '状态' else {})} for c in LEDGER_COLUMNS if c != '编号'],
          'enums': {'状态': [{'value': 'A', 'label': '甲'}, {'value': 'B', 'label': '乙'}]}, 'rules': LEDGER_RULES}


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def plain_number(text):
    return text is not None and NUMBER.fullmatch(text.strip()) is not None


def real_day(text):
    """The day a date (2026-01-05) or a date and time (2026-01-05 10:00, 2026-01-05T10:00:30) names, as an ordinal with the time as a fraction; None when it
    names none."""
    if text is None:
        return None
    text = text.strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?', text):
        return None
    try:
        moment = datetime.fromisoformat(text) if len(text) > 10 else datetime.combine(date.fromisoformat(text), datetime.min.time())
    except ValueError:
        return None
    return moment.toordinal() + (moment.hour * 3600 + moment.minute * 60 + moment.second) / 86400


def plain_sql(conn) -> sqlite3.Connection:
    conn.create_function('plain_number', 1, lambda v: int(plain_number(v)), deterministic=True)
    conn.create_function('number_of', 1, lambda v: float(v.strip()) if plain_number(v) else None, deterministic=True)
    conn.create_function('real_day', 1, real_day, deterministic=True)
    return conn


EMPTY = "({c} IS NULL OR trim({c}) = '')"
BY_SQL = {   # what breaks each kind of rule, written plainly
    'not_empty': lambda r: (EMPTY.format(c=q(r['column'])), []),
    'gt': lambda r: (f"NOT {EMPTY.format(c=q(r['column']))} AND NOT (plain_number({q(r['column'])}) AND number_of({q(r['column'])}) > ?)", [r['value']]),
    'ge': lambda r: (f"NOT {EMPTY.format(c=q(r['column']))} AND NOT (plain_number({q(r['column'])}) AND number_of({q(r['column'])}) >= ?)", [r['value']]),
    'lt': lambda r: (f"NOT {EMPTY.format(c=q(r['column']))} AND NOT (plain_number({q(r['column'])}) AND number_of({q(r['column'])}) < ?)", [r['value']]),
    'le': lambda r: (f"NOT {EMPTY.format(c=q(r['column']))} AND NOT (plain_number({q(r['column'])}) AND number_of({q(r['column'])}) <= ?)", [r['value']]),
    'between': lambda r: (f"NOT {EMPTY.format(c=q(r['column']))} AND NOT (plain_number({q(r['column'])}) AND number_of({q(r['column'])}) BETWEEN ? AND ?)", [r['low'], r['high']]),
    'not_before': lambda r: (f"NOT {EMPTY.format(c=q(r['column']))} AND NOT {EMPTY.format(c=q(r['other']))} AND NOT (real_day({q(r['column'])}) IS NOT NULL AND real_day({q(r['other'])}) IS NOT NULL "
                             f"AND real_day({q(r['column'])}) >= real_day({q(r['other'])}))", []),
}


def by_sql(conn, table: str, rule: dict, codes=(), where: str = '', args=()) -> tuple[int, list[str]]:
    """(rows that break the rule, the first 20 of their keys in table order) by a plain query."""
    if rule['check'] == 'in_codes':
        sql, params = f"NOT {EMPTY.format(c=q(rule['column']))} AND {q(rule['column'])} NOT IN ({','.join('?' * len(codes))})", list(codes)
    else:
        sql, params = BY_SQL[rule['check']](rule)
    count = conn.execute(f'SELECT COUNT(*) FROM {q(table)} WHERE ({sql}){where}', [*params, *args]).fetchone()[0]
    keys = [k for (k,) in conn.execute(f'SELECT {q("编号") if "编号" in table_columns(conn, table) else q("订单号")} FROM {q(table)} WHERE ({sql}){where} ORDER BY rowid LIMIT 20', [*params, *args])]
    return count, keys


def table_columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info({q(table)})')]


def current_table(out, name: str) -> str:
    conn = sqlite3.connect(out / 'workspace.sqlite')
    try:
        return conn.execute('SELECT d.table_name FROM dataset d JOIN current_dataset c ON c.dataset_id = d.id WHERE c.name = ?', (name,)).fetchone()[0]
    finally:
        conn.close()


class RuleChecksAgainstSql(unittest.TestCase):
    """The one pass over a table, on cells an upload never stores (an empty text, only spaces, spaces around a number), against the plain queries."""

    def test_each_kind_counts_what_the_plain_query_counts_on_cells_with_spaces_and_empty_text(self):
        conn = plain_sql(sqlite3.connect(':memory:'))
        conn.execute('CREATE TABLE t ("编号" TEXT, "n" TEXT, "d1" TEXT, "d2" TEXT, "s" TEXT)')
        cells = [None, '', '  ', ' 5 ', '5', '-5', '0', '0.0', '-0', '007', '5.', '.5', '1e3', 'x', '1.2.3', '--5', '100', '100.0001']
        days = [None, '', ' ', '2026-01-05', ' 2026-01-05 ', '2026-01-05 10:00', '2026-01-05T09:00:00', '2026-02-30', '2026-01-04', 'soon', '2460000', '2026-01-05abc']
        rows = [(f'K{i:03d}', cells[i % len(cells)], days[i % len(days)], days[(i * 5 + 3) % len(days)], ['A', 'B', ' A', '', None, 'a'][i % 6]) for i in range(300)]
        conn.executemany('INSERT INTO t VALUES (?, ?, ?, ?, ?)', rows)
        kinds = {'n': 'decimal', 'd1': 'datetime', 'd2': 'datetime', 's': 'text'}
        rules = [{'column': 'n', 'check': 'not_empty'}, {'column': 'n', 'check': 'gt', 'value': 0}, {'column': 'n', 'check': 'ge', 'value': 0},
                 {'column': 'n', 'check': 'lt', 'value': 100}, {'column': 'n', 'check': 'le', 'value': 100}, {'column': 'n', 'check': 'between', 'low': -5, 'high': 5.5},
                 {'column': 'd1', 'check': 'not_before', 'other': 'd2'}, {'column': 's', 'check': 'in_codes'}, {'column': 'd1', 'check': 'not_empty'}]
        found = value_rules.run(conn, 't', rules, kinds, {'s': ['A', 'B']}, ['编号'])
        for rule, result in zip(rules, found['rules']):
            count, keys = by_sql(conn, 't', rule, ['A', 'B'])
            self.assertEqual((result['broken'], [k[0] for k in result['examples']]), (count, keys), rule)
        self.assertEqual(found['rows_checked'], 300)
        self.assertTrue(all(r['broken'] for r in found['rules']))   # each kind meets rows it judges broken here

    def test_a_month_column_is_read_as_months(self):
        conn = plain_sql(sqlite3.connect(':memory:'))
        conn.execute('CREATE TABLE t ("编号" TEXT, "a" TEXT, "b" TEXT)')
        conn.executemany('INSERT INTO t VALUES (?, ?, ?)', [('1', '2026-03', '2026-02'), ('2', '2026-02', '2026-03'), ('3', '2026-13', '2026-01'), ('4', None, '2026-01'), ('5', '2026-03', '2026-03')])
        found = value_rules.run(conn, 't', [{'column': 'a', 'check': 'not_before', 'other': 'b'}], {'a': 'month', 'b': 'month'}, {}, ['编号'])
        self.assertEqual([k[0] for k in found['rules'][0]['examples']], ['2', '3'])

    def test_one_pass_reads_the_table_once_for_all_rules(self):
        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE t ("编号" TEXT, "n" TEXT)')
        conn.executemany('INSERT INTO t VALUES (?, ?)', [(str(i), str(i)) for i in range(50)])
        statements = []
        conn.set_trace_callback(statements.append)
        rules = [{'column': 'n', 'check': 'gt', 'value': v} for v in range(10)]
        value_rules.run(conn, 't', rules, {'n': 'integer'}, {}, ['编号'], examples=0)
        self.assertEqual(len([s for s in statements if 'FROM "t"' in s]), 1, statements)


class ValueRuleTests(SigningTestCase):
    def team(self, base, *more, roles=None):
        team = self.people(base, 'ann', 'bob', *more, roles=roles)
        status, body = team['ann'].post('/api/workspace/datasets/upload', {'files': [*TABLES, ledger_upload(ledger_rows())]})
        self.assertEqual(status, 200, body)
        return team

    def page(self, client, name='ledger', **more):
        status, body = client.get(f'/api/workspace/types/{name}', **more)
        self.assertEqual(status, 200, body)
        return body

    def confirm(self, client, name='order', column=None, expect=200):
        shown = self.page(client, name)
        shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
        status, body = client.post('/api/workspace/types/confirm', {'id': name, 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})
        self.assertEqual(status, expect, body)
        return body

    def assert_counts_match_sql(self, out, readout, rules, where='', args=()):
        conn = plain_sql(sqlite3.connect(out / 'workspace.sqlite'))
        try:
            table = current_table(out, '账目')
            for rule, shown in zip(rules, readout):
                self.assertEqual({k: shown[k] for k in rule}, rule)
                count, keys = by_sql(conn, table, rule, ['A', 'B'], where, args)
                self.assertEqual((shown['broken'], [k[0] for k in shown['examples']]), (count, keys), rule)
            self.assertEqual(len(readout), len(rules))
        finally:
            conn.close()

    def test_each_rule_kind_counts_exactly_what_sql_counts_on_clean_and_on_messy_rows(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            status, body = ann.post('/api/workspace/types', LEDGER)
            self.assertEqual(status, 200, body)
            self.assertEqual(len(body['rules']), 10)
            self.assert_counts_match_sql(out, self.page(ann)['rules'], LEDGER_RULES)
            self.assertTrue(any(r['broken'] > 20 for r in self.page(ann)['rules']))   # the examples stop at 20
            status, body = ann.post('/api/workspace/datasets/upload', {'files': [ledger_upload(ledger_rows(messy=True), 'overwrite')]})
            self.assertEqual(status, 200, body)
            self.assert_counts_match_sql(out, self.page(ann)['rules'], LEDGER_RULES)
            conn = plain_sql(sqlite3.connect(out / 'workspace.sqlite'))
            table = current_table(out, '账目')
            self.assertGreater(conn.execute(f"SELECT COUNT(*) FROM {q(table)} WHERE \"金额\" IS NOT NULL AND NOT plain_number(\"金额\")").fetchone()[0], 0)   # the messy version has what it says
            self.assertGreater(conn.execute(f"SELECT COUNT(*) FROM {q(table)} WHERE \"下单日期\" IS NOT NULL AND real_day(\"下单日期\") IS NULL").fetchone()[0], 0)
            conn.close()

    def test_how_a_rule_is_stored_says_column_comparison_and_bound(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            given = [{'column': '金额', 'check': 'gt', 'value': '0', 'note': 'dropped'}, {'column': '数量', 'check': 'between', 'low': 1, 'high': '50.50'},
                     {'column': '发货日期', 'check': 'not_before', 'other': '下单日期'}, {'column': '状态', 'check': 'in_codes'}, {'column': '备注', 'check': 'not_empty'}]
            self.assertEqual(ann.post('/api/workspace/types', {**LEDGER, 'rules': given})[0], 200)
            conn = sqlite3.connect(out / 'workspace.sqlite')
            content = json.loads(conn.execute("SELECT content_json FROM element_state WHERE element_id = 'objtype:ledger'").fetchone()[0])
            conn.close()
            self.assertEqual(content['rules'], [{'column': '金额', 'check': 'gt', 'value': 0}, {'column': '数量', 'check': 'between', 'low': 1, 'high': 50.5},
                                                {'column': '发货日期', 'check': 'not_before', 'other': '下单日期'}, {'column': '状态', 'check': 'in_codes'}, {'column': '备注', 'check': 'not_empty'}])

    def test_rule_input_never_becomes_sql_and_what_does_not_fit_a_property_is_refused(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            refused = {
                'a column name that is not a property': [{'column': '金额" > 0 OR "1', 'check': 'gt', 'value': 0}],
                'a bound that is not a number': [{'column': '金额', 'check': 'gt', 'value': '0; DROP TABLE "dataset"'}],
                'a bound that is yes or no': [{'column': '金额', 'check': 'gt', 'value': True}],
                'a bound that is not finite': [{'column': '金额', 'check': 'lt', 'value': 'Infinity'}],
                'a missing bound': [{'column': '金额', 'check': 'gt'}],
                'an unknown check': [{'column': '金额', 'check': 'gt; DELETE'}],
                'a comparison on a text column': [{'column': '备注', 'check': 'gt', 'value': 0}],
                'codes on a column that is not a code column': [{'column': '备注', 'check': 'in_codes'}],
                'a date order on a number column': [{'column': '金额', 'check': 'not_before', 'other': '下单日期'}],
                'a date order on itself': [{'column': '下单日期', 'check': 'not_before', 'other': '下单日期'}],
                'a date order on a column that is not a property': [{'column': '下单日期', 'check': 'not_before', 'other': 'x"y'}],
                'a range upside down': [{'column': '金额', 'check': 'between', 'low': 10, 'high': 1}],
                'the same rule twice': [{'column': '金额', 'check': 'gt', 'value': 0}, {'column': '金额', 'check': 'gt', 'value': '0'}],
                'more than 20 rules': [{'column': '金额', 'check': 'gt', 'value': v} for v in range(21)],
                'rules that are not a list': {'column': '金额'},
                'a rule that is not an object': ['金额 > 0'],
            }
            for case, rules in refused.items():
                status, body = ann.post('/api/workspace/types', {**LEDGER, 'rules': rules})
                self.assertEqual(status, 400, (case, body))
            conn = sqlite3.connect(out / 'workspace.sqlite')
            self.assertIsNone(conn.execute("SELECT 1 FROM element_state WHERE element_id = 'objtype:ledger'").fetchone())
            self.assertIsNotNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'dataset'").fetchone())
            conn.close()
            status, body = ann.post('/api/workspace/types', {**LEDGER, 'rules': [{'column': '奇"怪', 'check': 'gt', 'value': 0}]})   # a column whose name has a quote in it is read as its name
            self.assertEqual(status, 200, body)
            self.assert_counts_match_sql(out, self.page(ann)['rules'], [{'column': '奇"怪', 'check': 'gt', 'value': 0}])

    def test_a_rule_broken_now_can_be_proposed_and_the_type_cannot_be_confirmed_until_none_is(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            high = {**ORDER, 'rules': [{'column': '金额', 'check': 'gt', 'value': 3000}]}
            status, body = ann.post('/api/workspace/types', high)
            self.assertEqual(status, 200, body)
            conn = plain_sql(sqlite3.connect(out / 'workspace.sqlite'))
            broken = conn.execute(f'SELECT COUNT(*) FROM {q(current_table(out, "订单"))} WHERE CAST("金额" AS REAL) <= 3000').fetchone()[0]
            conn.close()
            self.assertGreater(broken, 0)
            self.assertEqual(body['rules'][0]['broken'], broken)
            self.assertIn(f'{broken} 行', body['warnings'][-1])
            self.confirm(bob, column='状态码')
            page = self.page(bob, 'order')
            self.assertEqual((page['can_confirm'], page['rules'][0]['broken']), (False, broken))
            refusal = self.confirm(bob, expect=409)
            self.assertIn('“金额”要大于 3000', refusal['error'])
            self.assertIn(f'{broken} 行', refusal['error'])
            page = self.page(ann, 'order')
            status, body = ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': page['version'], 'rules': [{'column': '金额', 'check': 'gt', 'value': 0}]})
            self.assertEqual(status, 200, body)
            self.assertEqual(self.page(bob, 'order')['rules'][0]['broken'], 0)
            self.confirm(bob)
            self.assertEqual(self.page(bob, 'order')['state'], 'confirmed')

    def test_rules_are_part_of_the_type_adding_changing_or_removing_one_puts_it_forward_again(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            rule = {'column': '金额', 'check': 'gt', 'value': 0}
            self.assertEqual(ann.post('/api/workspace/types', {**ORDER, 'rules': [rule]})[0], 200)
            self.confirm(bob, column='状态码')
            self.confirm(bob)
            page = self.page(ann, 'order')
            status, body = ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': page['version'], 'description': '改了说明'})   # no rules in the request: they stay
            self.assertEqual((status, body['state'], body['reset']), (200, 'confirmed', []))
            self.assertEqual([r['check'] for r in self.page(ann, 'order')['rules']], ['gt'])
            for rules in ([rule, {'column': '金额', 'check': 'le', 'value': 9999}], [{'column': '金额', 'check': 'ge', 'value': 0}], []):
                page = self.page(ann, 'order')
                status, body = ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': page['version'], 'rules': rules})
                self.assertEqual((status, body['state'], body['reset']), (200, 'checked', ['值规则']), body)
                self.assertEqual(self.page(bob, 'order')['proposed_by'], 'Ann')
                self.assertEqual(self.confirm(ann, expect=403)['error'], '这一条是你自己提的，要另一位来确认')
                self.confirm(bob)
            self.assertNotIn('rules', self.page(ann, 'order'))
            conn = sqlite3.connect(out / 'workspace.sqlite')
            self.assertNotIn('rules', json.loads(conn.execute("SELECT content_json FROM element_state WHERE element_id = 'objtype:order'").fetchone()[0]))
            conn.close()
            page = self.page(ann, 'order')
            status, body = ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': page['version'], 'properties': [{'column': '订单号'}, {'column': '状态码', 'enum': True}],
                                                                     'rules': [rule]})
            self.assertEqual(status, 400, body)   # a rule on a column that is not a property

    def test_a_negative_amount_sends_the_confirmed_order_type_back_naming_the_rule_and_the_count_and_questions_wait_until_it_is_confirmed_again(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base, 'vera', roles={'vera': 'viewer'})
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types', {**ORDER, 'rules': [{'column': '金额', 'check': 'gt', 'value': 0}]})[0], 200)
            self.confirm(bob, column='状态码')
            self.confirm(bob)
            self.assertEqual(self.ask(ann)['status'], 'answered')
            asked = len(model.requests)
            status, body = ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(lambda r, i: {**r, '金额': '-5'} if i in (3, 40, 99) else r)]})
            self.assertEqual(status, 200, body)
            page = self.page(bob, 'order')
            self.assertEqual((page['state'], page['cause']), ('needs_look', 'data'))
            self.assertIn('值规则“金额”要大于 0', page['reason'])
            self.assertIn('有 3 行不满足', page['reason'])
            self.assertEqual((page['rules'][0]['broken'], [k[0] for k in page['rules'][0]['examples']]), (3, ['DD20260004', 'DD20260041', 'DD20260100']))
            en = self.page(bob, 'order', headers=EN)
            self.assertEqual(en['rules'][0]['says'], '"金额" must be greater than 0')
            # the question is refused before the model is asked, naming the rule to a builder, and only that it waits to a viewer
            refused = self.ask(ann)
            self.assertEqual(refused['status'], 'refused')
            self.assertEqual(len(model.requests), asked)
            self.assertIn('值规则“金额”要大于 0', refused['reason'])
            self.assertIn('有 3 行不满足', refused['reason'])
            told = self.ask(vera)
            self.assertEqual(told['status'], 'refused')
            self.assertNotIn('金额', json.dumps(told, ensure_ascii=False))
            self.assertEqual(self.page(vera, 'order'), {'id': 'order', 'name': '订单', 'state': 'needs_look', 'waiting': True, 'waiting_for': ['Bob', '管理员']})
            # the standing and the queue say which rule and how many; who can confirm is told once
            standing = next(d for d in ann.get('/api/workspace/agent/standing')[1]['definitions'] if d['id'] == 'objtype:order')
            self.assertIn('有 3 行不满足', standing['reason'])
            item = next(i for i in bob.get('/api/workspace/queue')[1]['items'] if i.get('kind') == 'type')
            self.assertIn('“金额”要大于 0：现在有 3 行不满足', [line['text'] for line in item['lines']])
            for person in (bob, admin):
                notices = [n for n in person.get('/api/workspace/notices')[1]['notices'] if '退回' in n['text']]
                self.assertEqual(len(notices), 1, notices)
                self.assertIn('有 3 行不满足', notices[0]['text'])
            self.assertEqual([n for n in ann.get('/api/workspace/notices')[1]['notices'] if '退回' in n['text']], [])   # neither a confirmer nor its last confirmer
            # mending the data does not confirm it again by itself; a second look does
            status, body = ann.post('/api/workspace/datasets/upload', {'files': [orders_upload()]})
            self.assertEqual(status, 200, body)
            page = self.page(bob, 'order')
            self.assertEqual((page['state'], page['rules'][0]['broken'], page['can_confirm']), ('needs_look', 0, True))
            self.assertEqual(self.ask(ann)['status'], 'refused')
            self.confirm(bob)
            self.assertEqual(self.ask(ann)['status'], 'answered')

    def ask(self, client):
        status, body = client.post('/api/workspace/ask', {'question': '取消的订单有多少？'})
        self.assertEqual(status, 200, body)
        return body

    def test_a_row_limited_builder_sees_counts_and_keys_of_their_own_rows_only(self):
        with self.service() as (base, out):
            team = self.team(base, 'carl')
            ann, admin, carl = team['ann'], team['admin'], team['carl']
            rules = [{'column': '金额', 'check': 'lt', 'value': 3000}, {'column': '数量', 'check': 'between', 'low': 5, 'high': 30}]
            self.assertEqual(ann.post('/api/workspace/types', {**ORDER, 'properties': [*ORDER['properties'], {'column': '数量'}], 'rules': rules})[0], 200)
            carl_id = next(u['id'] for u in admin.get('/api/users')[1]['users'] if u['username'] == 'carl')
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH022', 'user_ids': [carl_id]}]})[0], 200)
            conn = plain_sql(sqlite3.connect(out / 'workspace.sqlite'))
            table = current_table(out, '订单')
            for who, where, args in ((carl, ' AND "客户编号" = ?', ('KH022',)), (ann, '', ())):
                shown = self.page(who, 'order')['rules']
                for rule, readout in zip(rules, shown):
                    count, keys = by_sql(conn, table, rule, where=where, args=args)
                    self.assertEqual((readout['broken'], [k[0] for k in readout['examples']]), (count, keys), (who, rule))
            mine = conn.execute(f'SELECT COUNT(*) FROM {q(table)} WHERE "客户编号" = ?', ('KH022',)).fetchone()[0]
            conn.close()
            limited = self.page(carl, 'order')
            self.assertTrue(limited['rows_limited'])
            self.assertEqual(limited['rows'], mine)
            self.assertLess(limited['rules'][0]['broken'], self.page(ann, 'order')['rules'][0]['broken'])
            item = next(i for i in carl.get('/api/workspace/queue')[1]['items'] if i.get('kind') == 'type')
            self.assertIn(f'“金额”要小于 3000：你能看到的行里现在有 {limited["rules"][0]["broken"]} 行不满足', [line['text'] for line in item['lines']])

    def test_a_rule_on_a_hidden_column_is_absent_for_someone_kept_from_that_column(self):
        def walk(rules):
            with self.service() as (base, out):
                team = self.team(base, 'carl', 'vera', roles={'vera': 'viewer'})
                ann, bob, admin, carl, vera = team['ann'], team['bob'], team['admin'], team['carl'], team['vera']
                self.assertEqual(ann.post('/api/workspace/types', {**ORDER, 'properties': [*ORDER['properties'], {'column': '数量'}], 'rules': rules})[0], 200)
                ann_id = next(u['id'] for u in admin.get('/api/users')[1]['users'] if u['username'] == 'ann')
                self.confirm(bob, column='状态码')
                self.confirm(bob)
                self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'order', 'column': '金额', 'visible_to': [ann_id]})[0], 200)
                seen = {}
                for name, who in (('carl', carl), ('vera', vera)):
                    seen[name] = {'page': who.get('/api/workspace/types/order'), 'list': who.get('/api/workspace/types'), 'definitions': who.get('/api/workspace/agent/definitions'),
                                  'standing': who.get('/api/workspace/agent/standing'), 'log': who.get('/api/workspace/types/order/log')}
                seen['ann'] = self.page(ann, 'order')['rules']
            return json.loads(re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\+00:00)?', '<time>', json.dumps(seen, ensure_ascii=False)))
        kept = {'column': '金额', 'check': 'gt', 'value': 0}
        shown = {'column': '数量', 'check': 'ge', 'value': 1}
        both, one = walk([kept, shown]), walk([shown])
        self.assertEqual([r['column'] for r in both['ann']], ['金额', '数量'])   # someone who may see the column sees its rule
        for person in ('carl', 'vera'):
            self.assertEqual(both[person], one[person], person)
            self.assertEqual([r['column'] for r in both[person]['page'][1]['rules']], ['数量'])
            self.assertNotIn('金额', json.dumps(both[person], ensure_ascii=False))

    def test_describe_definitions_says_each_rule_as_a_sentence_in_both_languages(self):
        with self.service() as (base, out):
            team = self.team(base, 'vera', roles={'vera': 'viewer'})
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            self.assertEqual(ann.post('/api/workspace/types', LEDGER)[0], 200)
            self.confirm(bob, 'ledger', '状态')
            refusal = self.confirm(bob, 'ledger', expect=409)   # the ledger breaks most of its rules
            self.assertIn('值规则', refusal['error'])
            fit = [{'column': '编号', 'check': 'not_empty'}, {'column': '金额', 'check': 'ge', 'value': -3}, {'column': '金额', 'check': 'le', 'value': 1000.5},
                   {'column': '数量', 'check': 'between', 'low': 0, 'high': 101}, {'column': '状态', 'check': 'in_codes'}, {'column': '奇"怪', 'check': 'lt', 'value': 3}]
            page = self.page(ann)
            self.assertEqual(ann.post('/api/workspace/types/update', {**LEDGER, 'id': 'ledger', 'version': page['version'], 'enums': {'状态': [{'value': 'C', 'label': '丙'}]}, 'rules': fit})[0], 200)
            self.confirm(bob, 'ledger', '状态')
            self.confirm(bob, 'ledger')
            zh = next(t for t in vera.get('/api/workspace/agent/definitions')[1]['types'] if t['id'] == 'ledger')
            en = next(t for t in vera.get('/api/workspace/agent/definitions', headers=EN)[1]['types'] if t['id'] == 'ledger')
            self.assertEqual(zh['rules'], ['“编号”不能为空', '“金额”要至少是 -3', '“金额”要最多是 1000.5', '“数量”要在 0 到 101 之间（含两端）', '“状态”要是写了含义的代码之一', '“奇"怪”要小于 3'])
            self.assertEqual(en['rules'], ['"编号" must not be empty', '"金额" must be at least -3', '"金额" must be at most 1000.5', '"数量" must be between 0 and 101, both included',
                                           '"状态" must be one of the codes that have a meaning', '"奇"怪" must be less than 3'])
            self.assertEqual(self.page(vera)['rules'][0]['says'], '“编号”不能为空')
            self.assertIn('空着的格子', self.page(vera)['rules_note'])
            self.assertIn('empty cell', self.page(vera, headers=EN)['rules_note'])
            dates = [{'column': '发货日期', 'check': 'not_before', 'other': '下单日期'}]
            page = self.page(ann)
            self.assertEqual(ann.post('/api/workspace/types/update', {**LEDGER, 'id': 'ledger', 'version': page['version'], 'rules': dates})[0], 200)
            self.assertEqual(self.page(ann)['rules'][0]['says'], '“发货日期”不能早于“下单日期”')
            self.assertEqual(self.page(ann, headers=EN)['rules'][0]['says'], '"发货日期" must not be before "下单日期"')

    def test_a_type_stored_before_value_rules_takes_rules_with_nothing_added_to_the_file(self):
        """A rule is part of the type's definition (its content), so the file gains no table or column: a type written with no rules takes them on its next edit."""
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)
            shape = lambda: sqlite3.connect(out / 'workspace.sqlite').execute("SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'ds_%' ORDER BY name").fetchall()
            before = shape()
            page = self.page(ann, 'order')
            status, body = ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': page['version'], 'rules': [{'column': '金额', 'check': 'gt', 'value': 0}]})
            self.assertEqual((status, body['reset']), (200, ['值规则']))
            self.assertEqual(shape(), before)


if __name__ == '__main__':
    unittest.main()
