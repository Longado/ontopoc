"""The expression language and the operators of a transform step, on the planted tables. Expected numbers are counted from the records with their own
loops, not by the code under test."""
from collections import Counter, defaultdict
from datetime import date, timedelta
import json
import statistics
import unittest

from ontology_poc_generator.pipeline_expr import compile_expression
from ontology_poc_generator.pipeline_funcs import guess_formats, register
from ontology_poc_generator.pipeline_ops import aggregation_options, new_context
from ontology_poc_generator.pipelines import check_pipeline, run_pipeline, workspace_datasets
from ontology_poc_generator.workspace_store import import_records, open_workspace, records_sha256
from tests.test_workspace_store import planted_bundle

RECORDS = {name: s['records'] for name, s in planted_bundle()['sources'].items()}
ORDERS_COLUMNS = [{'name': '订单号', 'type': 'text'}, {'name': '客户编号', 'type': 'text'}, {'name': '数量', 'type': 'integer'}, {'name': '金额', 'type': 'integer'},
                  {'name': '下单日期', 'type': 'date'}, {'name': '状态码', 'type': 'integer'}, {'name': '交付天数', 'type': 'integer'}]


def store(conn, tables: dict) -> dict:
    return workspace_datasets(conn, {n: import_records(conn, n, rows, 't', records_sha256(rows))['id'] for n, rows in tables.items()})


class Workspace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = open_workspace(':memory:')
        cls.datasets = store(cls.conn, RECORDS)
        register(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def run_ops(self, operators, dataset='订单', ctx=None, tables=None, extra_steps=()):
        """The node of a transform with these operators over one dataset."""
        spec = {'steps': [{'id': 'in', 'type': 'input', 'dataset': dataset}, {'id': 't', 'type': 'transform', 'from': 'in', 'operators': operators}, *extra_steps]}
        return {n['id']: n for n in run_pipeline(self.conn, spec, tables or self.datasets, ctx=ctx)['nodes']}

    def rows(self, operators, dataset, tables):
        """The rows the transform ends in, in order."""
        found = []
        spec = {'steps': [{'id': 'in', 'type': 'input', 'dataset': dataset}, {'id': 't', 'type': 'transform', 'from': 'in', 'operators': operators}]}
        run_pipeline(self.conn, spec, tables, after=lambda conn, node, compiled: found.extend(conn.execute(f'SELECT * FROM {compiled["table"]} ORDER BY rowid')) if node['id'] == 't' else None)
        return found


class ExpressionTests(Workspace):
    def value(self, text, table='ds_x'):
        """The expression on the first row of a table made for it: one row, a date and a few numbers."""
        result = compile_expression(text, [{'name': 'd', 'type': 'date'}, {'name': 'n', 'type': 'integer'}, {'name': 'm', 'type': 'integer'}, {'name': 's', 'type': 'text'}, {'name': 'dt', 'type': 'datetime'}])
        self.assertTrue(result['ok'], result['errors'])
        conn = open_workspace(':memory:')
        self.addCleanup(conn.close)
        register(conn)
        conn.execute('CREATE TABLE t(d TEXT, n TEXT, m TEXT, s TEXT, dt TEXT)')
        conn.execute("INSERT INTO t VALUES ('2026-05-06', '7', '2', 'abc', '2026-05-06 14:30:00')")
        return conn.execute(f'SELECT {result["sql"]} FROM t', result['params']).fetchone()[0]

    def test_arithmetic_is_not_integer_division_and_a_zero_divisor_is_empty(self):
        self.assertEqual(self.value('n / m'), 3.5)
        self.assertEqual(self.value('round(n / 3, 2)'), 2.33)
        self.assertIsNone(self.value('n / (m - 2)'))
        self.assertEqual(self.value('abs(m - n) * 2'), 10)

    def test_conditions_and_defaults(self):
        self.assertEqual(self.value("if(n > 5, 'big', 'small')"), 'big')
        self.assertEqual(self.value("case(n < 3, 'a', n < 8, 'b', 'c')"), 'b')
        self.assertEqual(self.value("coalesce(null, s)"), 'abc')
        self.assertEqual(self.value("concat(s, '-', n)"), 'abc-7')
        self.assertEqual(self.value("substring(s, 2, 2)"), 'bc')
        self.assertEqual(self.value("if(n > 5 and not (m = 3), 1, 0)"), 1)

    def test_dates_a_week_starts_on_monday(self):
        self.assertEqual(self.value("date_trunc('week', d)"), '2026-05-04')      # 2026-05-06 is a Wednesday
        self.assertEqual(self.value("date_trunc('month', d)"), '2026-05-01')
        self.assertEqual(self.value("date_trunc('week', dt)"), '2026-05-04')
        self.assertEqual(self.value("date_diff('day', date_trunc('week', d), d)"), 2)
        self.assertEqual(self.value("date_diff('week', date_add(d, -15, 'day'), d)"), 2)
        self.assertEqual(self.value("date_diff('month', date_add(d, -3, 'month'), d)"), 3)
        self.assertEqual(self.value("date_add(d, 2, 'week')"), '2026-05-20')
        self.assertEqual(self.value("date_add(dt, 1, 'day')"), '2026-05-07 14:30:00')
        self.assertEqual((self.value('year(d)'), self.value('month(d)')), (2026, 5))

    def test_a_field_that_is_not_there_is_named_with_the_one_that_was_meant(self):
        result = compile_expression('金额 * 数目', ORDERS_COLUMNS)
        self.assertFalse(result['ok'])
        self.assertIn('没有字段「数目」，是不是「数量」', result['errors'][0]['message'])
        self.assertEqual(result['errors'][0]['pos'], 5)

    def test_types_that_do_not_fit_are_refused_before_anything_runs_and_each_is_named(self):
        said = lambda text: [e['message'] for e in compile_expression(text, ORDERS_COLUMNS)['errors']]
        self.assertIn('只能算数字', said('金额 + 订单号')[0])
        self.assertIn('date_add', said('下单日期 + 7')[0])
        self.assertIn('类型不同', said('金额 = 订单号')[0])
        self.assertIn('要是日期或日期时间', said("date_trunc('week', 金额)")[0])
        self.assertIn("'week' 或 'month'", said("date_trunc('year', 下单日期)")[0])
        self.assertIn('要 3 个参数', said('if(1 = 1, 2)')[0])
        self.assertEqual(len(said('金额 + 订单号 + 订单号 * 状态码 + 没有')), 3)     # all of them, not only the first
        self.assertIn('几个值类型不一样：数字、文本', said("if(金额 > 1, 'a', 2)")[0])
        self.assertIn('要写成 2026-05-03', said("下单日期 > '昨天'")[0])
        self.assertTrue(compile_expression("下单日期 > '2026-05-01'", ORDERS_COLUMNS)['ok'])

    def test_nothing_a_person_writes_is_run_as_code_and_a_name_is_quoted(self):
        for text in ("__import__('os').system('x')", "open('/etc/passwd')", 'eval(1)', "金额; DROP TABLE x"):
            result = compile_expression(text, ORDERS_COLUMNS)
            self.assertFalse(result['ok'], text)
        hostile = [{'name': 'a"b', 'type': 'integer'}]
        result = compile_expression('[a"b] + 1', hostile)
        self.assertTrue(result['ok'])
        self.assertIn('"a""b"', result['sql'])
        self.assertEqual(result['params'], [1.0])                  # a literal is a bound value, never SQL text
        result = compile_expression("'x''); DROP TABLE t; --'", [])
        self.assertEqual(result['params'], ["x'); DROP TABLE t; --"])

    def test_a_parse_error_names_where_and_full_width_punctuation_is_said_so(self):
        self.assertIn('全角', compile_expression('round（金额, 2）', ORDERS_COLUMNS)['errors'][0]['message'])
        self.assertIn('没写完', compile_expression('金额 +', ORDERS_COLUMNS)['errors'][0]['message'])
        self.assertIn('括号', compile_expression('(金额', ORDERS_COLUMNS)['errors'][0]['message'])
        self.assertFalse(compile_expression('(' * 200 + '1' + ')' * 200, ORDERS_COLUMNS)['ok'])
        self.assertFalse(compile_expression('+'.join(['1'] * 600), ORDERS_COLUMNS)['ok'])        # too long: refused, not a crash

    def test_a_field_is_the_type_its_column_was_read_as_and_a_yes_no_column_is_a_condition(self):
        conn = open_workspace(':memory:')
        self.addCleanup(conn.close)
        register(conn)
        conn.execute('CREATE TABLE t(flag TEXT)')
        conn.executemany('INSERT INTO t VALUES (?)', [('是',), ('否',), (None,)])
        result = compile_expression("if(flag, 'y', 'n')", [{'name': 'flag', 'type': 'boolean'}])
        self.assertEqual([r[0] for r in conn.execute(f'SELECT {result["sql"]} FROM t', result['params'])], ['y', 'n', 'n'])    # an empty condition takes the else branch


class FilterTests(Workspace):
    def test_a_filter_counts_the_rows_dropped_because_false_apart_from_those_dropped_because_empty(self):
        tables = store(self.conn, {'空': [{'k': 'a', 'v': '1'}, {'k': 'b', 'v': '5'}, {'k': 'c', 'v': None}, {'k': 'd', 'v': '9'}, {'k': 'e', 'v': None}]})
        op = self.run_ops([{'op': 'filter', 'where': {'column': 'v', 'cmp': 'gt', 'value': 2}}], '空', tables=tables)['t']['operators'][0]
        self.assertEqual((op['rows_in'], op['rows_out'], op['dropped_false'], op['dropped_null'], op['affected']), (5, 2, 1, 2, 3))
        self.assertIn('条件为空删掉 2 行', op['text'])

    def test_a_code_column_is_chosen_by_a_confirmed_meaning_not_by_its_raw_value(self):
        ctx = new_context(meanings={'订单.状态码': {'已取消': ['2'], '已交付': ['0'], '生产中': ['1']}})
        node = self.run_ops([{'op': 'filter', 'where': {'column': '状态码', 'cmp': 'ne', 'meaning': '已取消'}}], ctx=ctx)['t']
        self.assertEqual(node['rows_out'], sum(1 for r in RECORDS['订单'] if r['状态码'] != '2'))
        self.assertEqual(node['rows_out'], 144)
        self.assertEqual(ctx['used'], {'订单.状态码'})                                       # the meaning it read: the workspace records it as a dependency
        with self.assertRaises(ValueError) as caught:
            self.run_ops([{'op': 'filter', 'where': {'column': '状态码', 'cmp': 'eq', 'meaning': '已取消'}}], ctx=new_context())
        self.assertIn('还没有已确认的含义', str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            self.run_ops([{'op': 'filter', 'where': {'column': '状态码', 'cmp': 'eq', 'meaning': '退货'}}], ctx=ctx)
        self.assertIn('已确认的含义里没有「退货」', str(caught.exception))

    def test_groups_all_and_any_and_between(self):
        orders = RECORDS['订单']
        both = self.run_ops([{'op': 'filter', 'where': {'all': [{'column': '金额', 'cmp': 'between', 'low': 1000, 'high': 5000},
                                                                {'any': [{'column': '状态码', 'cmp': 'eq', 'value': 0}, {'column': '状态码', 'cmp': 'eq', 'value': 1}]}]}}])['t']
        self.assertEqual(both['rows_out'], sum(1 for r in orders if 1000 <= int(r['金额']) <= 5000 and r['状态码'] in ('0', '1')))
        self.assertEqual(self.run_ops([{'op': 'filter', 'where': {'column': '金额', 'cmp': 'in', 'values': [2520, 24000]}}])['t']['rows_out'],
                         sum(1 for r in orders if r['金额'] in ('2520', '24000')))
        self.assertEqual(self.run_ops([{'op': 'filter', 'where': {'column': '交付天数', 'cmp': 'is_null'}}])['t']['rows_out'], sum(1 for r in orders if r['交付天数'] in (None, '')))

    def test_a_value_that_does_not_fit_the_column_is_refused_in_words(self):
        with self.assertRaises(ValueError) as caught:
            self.run_ops([{'op': 'filter', 'where': {'column': '金额', 'cmp': 'gt', 'value': '很多'}}])
        self.assertIn('「很多」不是数字', str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            self.run_ops([{'op': 'filter', 'where': {'column': '下单日期', 'cmp': 'gt', 'value': '昨天'}}])
        self.assertIn('2026-05-03', str(caught.exception))


class CleanAndFillTests(Workspace):
    def setUp(self):
        self.tables = store(self.conn, {'脏': [{'id': '1', 'name': '  ab  cd ', 'note': 'x-1'}, {'id': '2', 'name': 'AB', 'note': ''}, {'id': '3', 'name': None, 'note': 'y_22'},
                                              {'id': '4', 'name': 'ok', 'note': 'x-3'}]})

    def test_text_cleaning_counts_the_rows_it_changed(self):
        operators = [{'op': 'text_clean', 'columns': ['name'], 'steps': [{'do': 'trim'}, {'do': 'whitespace'}, {'do': 'lower'}]},
                     {'op': 'text_clean', 'columns': ['note'], 'steps': [{'do': 'replace', 'find': '-', 'with': ''}]}]
        first, second = self.run_ops(operators, '脏', tables=self.tables)['t']['operators']
        self.assertEqual((first['rows_out'], first['affected']), (4, 2))             # "  ab  cd " and "AB"; "ok" and the missing one stay
        self.assertEqual(second['affected'], 2)                                      # "x-1" and "x-3" lose the dash; "y_22" has none
        self.assertEqual([r[1:] for r in self.rows(operators, '脏', self.tables)], [('ab cd', 'x1'), ('ab', ''), (None, 'y_22'), ('ok', 'x3')])

    def test_a_find_text_that_looks_like_a_pattern_is_taken_literally(self):
        tables = store(self.conn, {'p': [{'id': '1', 'v': 'a' * 45 + '!'}, {'id': '2', 'v': 'x[-_]\\d+y'}, {'id': '3', 'v': 'x-1y'}]})
        for pattern, expected in (('(a|aa)+$', ['a' * 45 + '!', 'x[-_]\\d+y', 'x-1y']), ('[-_]\\d+', ['a' * 45 + '!', 'xy', 'x-1y'])):
            op = [{'op': 'text_clean', 'columns': ['v'], 'steps': [{'do': 'replace', 'find': pattern, 'with': ''}]}]
            self.assertEqual([r[1] for r in self.rows(op, 'p', tables)], expected, pattern)   # only the exact text is replaced
        with self.assertRaises(ValueError) as caught:                                          # and a request for a pattern is refused, not quietly read as text
            self.run_ops([{'op': 'text_clean', 'columns': ['v'], 'steps': [{'do': 'replace', 'find': 'a+', 'with': '', 'regex': True}]}], 'p', tables=tables)
        self.assertIn('不支持正则', str(caught.exception))

    def test_a_text_column_only(self):
        with self.assertRaises(ValueError) as caught:
            self.run_ops([{'op': 'text_clean', 'columns': ['金额'], 'steps': [{'do': 'trim'}]}])
        self.assertIn('只用在文本列上', str(caught.exception))

    def test_filling_empty_values_counts_what_it_replaced_and_empty_text_counts_only_when_asked(self):
        plain = self.run_ops([{'op': 'fill_null', 'columns': ['name', 'note'], 'with': {'constant': '无'}}], '脏', tables=self.tables)['t']['operators'][0]
        self.assertEqual((plain['by_column'], plain['affected']), ({'name': 1, 'note': 0}, 1))
        asked = self.run_ops([{'op': 'fill_null', 'columns': ['name', 'note'], 'with': {'constant': '无'}, 'empty_as_null': True}], '脏', tables=self.tables)['t']['operators'][0]
        self.assertEqual((asked['by_column'], asked['affected']), ({'name': 1, 'note': 1}, 2))
        from_column = self.run_ops([{'op': 'fill_null', 'columns': ['name'], 'with': {'column': 'note'}}], '脏', tables=self.tables)['t']['operators'][0]
        self.assertEqual(from_column['affected'], 1)
        with self.assertRaises(ValueError) as caught:
            self.run_ops([{'op': 'fill_null', 'columns': ['交付天数'], 'with': {'constant': 'abc'}}])
        self.assertIn('不是数字', str(caught.exception))


class CastTests(Workspace):
    def setUp(self):
        amounts = ['100', '2,500', '88.5', 'abc', '1 200元', '', None, '17', '--', '3.0']
        self.tables = store(self.conn, {'流水': [{'编号': f'R{i}', '金额文本': v} for i, v in enumerate(amounts)]})

    def cast(self, **op):
        return self.run_ops([{'op': 'cast', 'column': '金额文本', **op}], '流水', tables=self.tables)['t']['operators'][0]

    def test_values_that_cannot_be_converted_are_counted_and_listed_never_silently_empty(self):
        op = self.cast(to='decimal', **{'as': '金额'})
        self.assertEqual(op['failures'], 4)                                  # 2,500 (no thousands option), abc, 1 200元, --
        self.assertEqual([(f['row'], f['value']) for f in op['failed']], [(2, '2,500'), (4, 'abc'), (5, '1 200元'), (9, '--')])
        self.assertEqual(op['text'], '4 行无法转成小数，这些行的「金额」是空的')
        self.assertEqual(op['affected'], 4)                                  # 100, 88.5, 17 and 3.0; the empty cell and the missing one are not values to convert
        thousands = self.cast(to='decimal', thousands=True)
        self.assertEqual([f['value'] for f in thousands['failed']], ['abc', '1 200元', '--'])    # 2,500 reads once told

    def test_a_conversion_set_to_stop_stops_the_run(self):
        with self.assertRaises(ValueError) as caught:
            self.cast(to='integer', on_failure='stop')
        self.assertIn('无法转成整数', str(caught.exception))

    def test_dates_by_a_format_and_a_format_guessed_from_examples(self):
        tables = store(self.conn, {'日期': [{'d': '2026/5/3'}, {'d': '2026/12/31'}, {'d': '2026/13/1'}, {'d': 'n/a'}]})
        op = self.run_ops([{'op': 'cast', 'column': 'd', 'to': 'date', 'format': 'YYYY/M/D'}], '日期', tables=tables)['t']['operators'][0]
        self.assertEqual((op['failures'], [f['value'] for f in op['failed']]), (2, ['2026/13/1', 'n/a']))
        guess = guess_formats(['2026/5/3', '2026/12/31', '2025/1/9'])
        self.assertEqual((guess[0]['format'], guess[0]['parsed'], guess[0]['of']), ('YYYY/M/D', 3, 3))
        self.assertEqual(next(g for g in guess if g['format'] == 'YYYY/MM/DD')['parsed'], 1)       # 2026/12/31
        with self.assertRaises(ValueError):
            self.run_ops([{'op': 'cast', 'column': 'd', 'to': 'date', 'format': 'YYYY-MM'}], '日期', tables=tables)

    def test_the_converted_column_has_its_new_type_and_a_new_badge(self):
        node = self.run_ops([{'op': 'cast', 'column': '金额文本', 'to': 'decimal', 'as': '金额'}], '流水', tables=self.tables)['t']
        self.assertEqual([(c['name'], c['type'], c.get('badge')) for c in node['column_types']], [('编号', 'text', None), ('金额文本', 'text', None), ('金额', 'decimal', 'new')])


class CalcTests(Workspace):
    def test_a_computed_column_counts_the_rows_it_could_not_compute(self):
        tables = store(self.conn, {'除': [{'a': '10', 'b': '2'}, {'a': '9', 'b': '0'}, {'a': '8', 'b': None}, {'a': '6', 'b': '3'}]})
        op = self.run_ops([{'op': 'calc', 'name': '比', 'expression': 'a / b'}], '除', tables=tables)['t']['operators'][0]
        self.assertEqual((op['errors'], op['error_rows']), (1, [2]))               # row 2 divides by zero; row 3 has an empty field and is expected to be empty
        self.assertEqual(op['affected'], 3)

    def test_the_week_start_is_checked_against_the_orders_it_came_from(self):
        right = self.run_ops([{'op': 'calc', 'name': '周起始', 'expression': "date_trunc('week', 下单日期)"}])['t']['operators'][0]
        self.assertEqual(right['notices'], [])
        shifted = self.run_ops([{'op': 'calc', 'name': '周起始', 'expression': "date_add(date_trunc('week', 下单日期), 7, 'day')"}])['t']['operators'][0]
        self.assertEqual([n['kind'] for n in shifted['notices']], ['later_than_source'])
        self.assertEqual(shifted['notices'][0]['rows'], 160)
        self.assertIn('不可能晚于原日期', shifted['notices'][0]['text'])
        constant = self.run_ops([{'op': 'calc', 'name': '下周', 'expression': "date_add(下单日期, 7, 'day')"}])['t']['operators'][0]
        self.assertEqual([(n['kind'], n['days'], n['rows']) for n in constant['notices']], [('date_shift', 7, 160)])
        self.assertIn('每行都比来源「下单日期」晚 7 天', constant['notices'][0]['text'])

    def test_the_computed_values_are_what_an_independent_calculation_gives(self):
        spec = {'steps': [{'id': 'in', 'type': 'input', 'dataset': '订单'},
                          {'id': 't', 'type': 'transform', 'from': 'in', 'operators': [{'op': 'calc', 'name': '周起始', 'expression': "date_trunc('week', 下单日期)"},
                                                                                       {'op': 'calc', 'name': '单价', 'expression': 'round(金额 / 数量, 2)'}]}]}
        rows = {}

        def take(conn, node, compiled):
            if node['id'] == 't':
                rows['t'] = conn.execute(f'SELECT 订单号, 周起始, 单价 FROM {compiled["table"]} ORDER BY rowid').fetchall()
        run_pipeline(self.conn, spec, self.datasets, after=take)
        for record, (key, week, unit) in zip(RECORDS['订单'], rows['t']):
            day = date.fromisoformat(record['下单日期'][:10])
            self.assertEqual((key, week), (record['订单号'], (day - timedelta(days=day.weekday())).isoformat()))
            self.assertEqual(unit, round(int(record['金额']) / int(record['数量']), 2))

    def test_a_name_that_exists_is_replaced_only_when_asked_and_a_bad_expression_is_refused_with_its_place(self):
        with self.assertRaises(ValueError) as caught:
            self.run_ops([{'op': 'calc', 'name': '金额', 'expression': '金额 * 2'}])
        self.assertIn('已经有叫「金额」的列', str(caught.exception))
        replaced = self.run_ops([{'op': 'calc', 'name': '金额', 'expression': '金额 * 2', 'replace': True}])['t']
        self.assertEqual([(c['name'], c.get('badge')) for c in replaced['column_types'] if c['name'] == '金额'], [('金额', 'replaced')])
        with self.assertRaises(ValueError) as caught:
            self.run_ops([{'op': 'calc', 'name': '新', 'expression': '金额 * 数目'}])
        self.assertIn('没有字段「数目」', str(caught.exception))


class AggregateTests(Workspace):
    def test_a_group_statistic_offers_count_and_average_and_not_only_the_sum(self):
        columns = [{'name': c['name'], 'type': c['type'], 'origin': f'订单.{c["name"]}'} for c in ORDERS_COLUMNS]
        offered = aggregation_options(columns, codes={'订单.状态码'})
        self.assertEqual(offered['金额'], ['sum', 'count', 'count_distinct', 'avg', 'min', 'max', 'median', 'p25', 'p75'])
        self.assertEqual(offered['订单号'], ['count', 'count_distinct', 'min', 'max'])
        self.assertEqual(offered['状态码'], ['count', 'count_distinct', 'min', 'max'])          # a code is counted, never added

    def test_a_code_column_is_not_summed(self):
        with self.assertRaises(ValueError) as caught:
            self.run_ops([{'op': 'aggregate', 'group_by': ['客户编号'], 'aggregations': [{'fn': 'sum', 'column': '状态码'}]}], ctx=new_context(codes={'订单.状态码'}))
        self.assertIn('是代码列，把代码求和没有意义', str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            self.run_ops([{'op': 'aggregate', 'group_by': ['客户编号'], 'aggregations': [{'fn': 'avg', 'column': '订单号'}]}])
        self.assertIn('不能平均', str(caught.exception))

    def test_every_aggregation_is_exact_and_nulls_are_ignored(self):
        by_customer = defaultdict(list)
        for r in RECORDS['订单']:
            by_customer[r['客户编号']].append(int(r['金额']))
        node = self.run_ops([{'op': 'aggregate', 'group_by': ['客户编号'], 'aggregations': [
            {'fn': 'sum', 'column': '金额', 'as': '合计'}, {'fn': 'count', 'as': '行数'}, {'fn': 'avg', 'column': '金额', 'as': '平均'},
            {'fn': 'median', 'column': '金额', 'as': '中位'}, {'fn': 'p25', 'column': '金额', 'as': 'P25'}, {'fn': 'p75', 'column': '金额', 'as': 'P75'},
            {'fn': 'count_distinct', 'column': '产品编号', 'as': '产品数'}, {'fn': 'min', 'column': '下单日期', 'as': '最早'}]}])
        self.assertEqual(node['t']['rows_out'], len(by_customer))
        self.assertEqual([c['type'] for c in node['t']['column_types']][:3], ['text', 'integer', 'integer'])
        rows = {}

        def take(conn, n, compiled):
            if n['id'] == 't':
                rows.update({r[0]: r for r in conn.execute(f'SELECT * FROM {compiled["table"]}')})
        spec = {'steps': [{'id': 'in', 'type': 'input', 'dataset': '订单'}, {'id': 't', 'type': 'transform', 'from': 'in', 'operators': [
            {'op': 'aggregate', 'group_by': ['客户编号'], 'aggregations': [
                {'fn': 'sum', 'column': '金额', 'as': '合计'}, {'fn': 'count', 'as': '行数'}, {'fn': 'avg', 'column': '金额', 'as': '平均'},
                {'fn': 'median', 'column': '金额', 'as': '中位'}, {'fn': 'p25', 'column': '金额', 'as': 'P25'}, {'fn': 'p75', 'column': '金额', 'as': 'P75'}]}]}]}
        run_pipeline(self.conn, spec, self.datasets, after=take)
        for customer, amounts in by_customer.items():
            _, total, count, mean, median, p25, p75 = rows[customer]
            self.assertEqual((total, count), (sum(amounts), len(amounts)))
            self.assertAlmostEqual(mean, sum(amounts) / len(amounts))
            self.assertAlmostEqual(median, statistics.median(amounts))
            if len(amounts) > 1:
                q = statistics.quantiles(amounts, n=4, method='inclusive')
                self.assertAlmostEqual(p25, q[0])
                self.assertAlmostEqual(p75, q[2])

    def test_a_group_of_only_empty_values_has_an_empty_sum_but_a_count_of_zero(self):
        tables = store(self.conn, {'空组': [{'g': 'a', 'v': '4'}, {'g': 'a', 'v': '6'}, {'g': 'b', 'v': None}]})
        spec = {'steps': [{'id': 'in', 'type': 'input', 'dataset': '空组'}, {'id': 't', 'type': 'transform', 'from': 'in', 'operators': [
            {'op': 'aggregate', 'group_by': ['g'], 'aggregations': [{'fn': 'sum', 'column': 'v', 'as': 's'}, {'fn': 'count', 'column': 'v', 'as': 'n'}, {'fn': 'avg', 'column': 'v', 'as': 'm'}]}]}]}
        rows = {}
        run_pipeline(self.conn, spec, tables, after=lambda c, n, comp: rows.update({r[0]: r[1:] for r in c.execute(f'SELECT * FROM {comp["table"]}')}) if n['id'] == 't' else None)
        self.assertEqual(rows, {'a': (10, 2, 5.0), 'b': (None, 0, None)})


class DedupeAndLabelTests(Workspace):
    def latest(self, keep, **op):
        spec = {'steps': [{'id': 'in', 'type': 'input', 'dataset': '订单承诺'}, {'id': 't', 'type': 'transform', 'from': 'in', 'operators': [
            {'op': 'dedupe', 'keys': ['订单号'], 'keep': keep, 'order_by': '承诺版本', **op},
            {'op': 'aggregate', 'group_by': [], 'aggregations': [{'fn': 'sum', 'column': '承诺数量', 'as': '合计'}, {'fn': 'count', 'as': '行数'}]}]}]}
        rows = []
        nodes = {n['id']: n for n in run_pipeline(self.conn, spec, self.datasets, after=lambda c, n, comp: rows.extend(c.execute(f'SELECT * FROM {comp["table"]}')) if n['id'] == 't' else None)['nodes']}
        return nodes['t'], rows[0]

    def test_the_latest_version_of_each_order_is_kept_and_what_was_dropped_is_counted(self):
        latest = {}
        for r in RECORDS['订单承诺']:
            if r['订单号'] not in latest or int(r['承诺版本']) > int(latest[r['订单号']]['承诺版本']):
                latest[r['订单号']] = r
        node, row = self.latest('last')
        self.assertEqual(row, (sum(int(r['承诺数量']) for r in latest.values()), len(latest)))     # the 552 over 60 orders of the views
        self.assertEqual(row, (552, 60))
        dedupe = node['operators'][0]
        self.assertEqual((dedupe['rows_in'], dedupe['rows_out'], dedupe['dropped']), (121, 60, 61))
        first_node, first = self.latest('first')
        self.assertEqual(first[1], 60)
        self.assertNotEqual(first[0], 552)                                       # the first version of each order is another set of rows: no silent default

    def test_an_order_column_is_required_and_a_row_with_no_key_is_kept(self):
        with self.assertRaises(ValueError) as caught:
            self.run_ops([{'op': 'dedupe', 'keys': ['订单号']}], '订单承诺')
        self.assertIn('指定按哪一列排先后', str(caught.exception))
        tables = store(self.conn, {'键': [{'k': 'a', 'v': '1'}, {'k': 'a', 'v': '2'}, {'k': None, 'v': '3'}, {'k': '', 'v': '4'}, {'k': 'b', 'v': '5'}]})
        op = self.run_ops([{'op': 'dedupe', 'keys': ['k'], 'keep': 'last', 'order_by': 'v'}], '键', tables=tables)['t']['operators'][0]
        self.assertEqual((op['rows_out'], op['dropped'], op['blank_key_rows_kept']), (4, 1, 2))
        self.assertEqual(op['examples'], [{'key': {'k': 'a'}, 'rows': 2}])

    def test_the_whole_row_is_the_key_when_no_key_is_given(self):
        tables = store(self.conn, {'行': [{'a': '1', 'b': 'x'}, {'a': '1', 'b': 'x'}, {'a': '2', 'b': 'x'}]})
        self.assertEqual(self.run_ops([{'op': 'dedupe'}], '行', tables=tables)['t']['rows_out'], 2)

    def test_codes_are_labelled_from_the_confirmed_meanings_and_the_codes_without_one_are_counted(self):
        ctx = new_context(meanings={'订单.状态码': {'已取消': ['2'], '已交付': ['0'], '生产中': ['1']}})
        node = self.run_ops([{'op': 'label', 'column': '状态码', 'as': '状态', 'from_meaning': True}], ctx=ctx)['t']
        counts = Counter(r['状态码'] for r in RECORDS['订单'])
        self.assertEqual((node['operators'][0]['unmapped_rows'], counts['0'], counts['1'], counts['2']), (0, 96, 48, 16))
        partial = self.run_ops([{'op': 'label', 'column': '状态码', 'as': '状态', 'mapping': [{'value': 0, 'label': '已交付'}]}])['t']['operators'][0]
        self.assertEqual((partial['unmapped_rows'], partial['unmapped_values']), (64, [{'value': '1', 'rows': 48}, {'value': '2', 'rows': 16}]))
        with self.assertRaises(ValueError) as caught:
            self.run_ops([{'op': 'label', 'column': '状态码', 'as': '状态', 'from_meaning': True}])
        self.assertIn('还没有已确认的含义', str(caught.exception))


class JoinTests(Workspace):
    def join(self, how, **extra):
        spec = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}, {'id': 't', 'type': 'input', 'dataset': '售后工单'},
                          {'id': 'j', 'type': 'join', 'left': 'o', 'right': 't', 'how': how, 'on': [{'left': '订单号', 'right': '订单号'}], **extra}]}
        return {n['id']: n for n in run_pipeline(self.conn, spec, self.datasets)['nodes']}['j']

    def test_anti_and_semi_joins_split_the_orders_by_whether_they_have_a_ticket(self):
        with_ticket = {r['订单号'] for r in RECORDS['售后工单']}
        mine = sum(1 for r in RECORDS['订单'] if r['订单号'] in with_ticket)
        self.assertEqual(mine, 36)
        semi, anti = self.join('semi'), self.join('anti')
        self.assertEqual((semi['rows_out'], anti['rows_out']), (36, 160 - 36))                 # a semi join does not repeat an order that has two tickets
        self.assertEqual(anti['join']['left_unmatched'], 124)
        self.assertEqual(anti['columns'], [c['name'] for c in self.datasets['订单']['columns']])
        self.assertEqual(self.join('left')['join']['left_unmatched'], 124)

    def test_the_right_side_columns_that_come_along_can_be_chosen(self):
        node = self.join('left', right_columns=['问题类型'])
        self.assertEqual(node['columns'][-1], '问题类型')
        self.assertNotIn('工单号', node['columns'])
        self.assertEqual(node['rows_out'], 169)                                              # the fan-out report stays
        self.assertEqual(node['join']['fan_out']['repeated_keys'], 9)
        with self.assertRaises(ValueError):
            self.join('left', right_columns=['没有这列'])

    def test_empty_keys_match_nothing_by_default_and_match_each_other_when_asked(self):
        tables = store(self.conn, {'左': [{'k': 'a'}, {'k': None}, {'k': ''}], '右': [{'k': 'a', 'w': '1'}, {'k': None, 'w': '2'}, {'k': '', 'w': '3'}]})
        for mode, expected in (('no_match', (1, 2)), ('equal', (3, 0))):
            spec = {'steps': [{'id': 'l', 'type': 'input', 'dataset': '左'}, {'id': 'r', 'type': 'input', 'dataset': '右'},
                              {'id': 'j', 'type': 'join', 'left': 'l', 'right': 'r', 'how': 'left', 'null_keys': mode, 'on': [{'left': 'k', 'right': 'k'}]}]}
            report = run_pipeline(self.conn, spec, tables)['nodes'][2]['join']
            self.assertEqual((report['matched_left'], report['left_unmatched']), expected, mode)
        with self.assertRaises(ValueError):
            check_pipeline({'steps': [{'id': 'l', 'type': 'input', 'dataset': '左'}, {'id': 'r', 'type': 'input', 'dataset': '右'},
                                      {'id': 'j', 'type': 'join', 'left': 'l', 'right': 'r', 'how': 'left', 'null_keys': 'x', 'on': [{'left': 'k', 'right': 'k'}]}]}, tables)

    def test_the_join_names_the_customer_whose_total_a_group_statistic_would_count_twice(self):
        """Orders left-joined to tickets: 160 become 169; summing 金额 by customer afterwards counts an order once per ticket. The group statistic says which customers."""
        tickets = Counter(r['订单号'] for r in RECORDS['售后工单'])
        true, doubled = Counter(), Counter()
        for r in RECORDS['订单']:
            true[r['客户编号']] += int(r['金额'])
            doubled[r['客户编号']] += int(r['金额']) * max(1, tickets[r['订单号']])
        wrong = {k for k in true if true[k] != doubled[k]}
        spec = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}, {'id': 't', 'type': 'input', 'dataset': '售后工单'},
                          {'id': 'j', 'type': 'join', 'left': 'o', 'right': 't', 'how': 'left', 'on': [{'left': '订单号', 'right': '订单号'}]},
                          {'id': 'g', 'type': 'transform', 'from': 'j', 'operators': [{'op': 'filter', 'where': {'column': '金额', 'cmp': 'gt', 'value': 0}},
                                                                                       {'op': 'aggregate', 'group_by': ['客户编号'], 'aggregations': [{'fn': 'sum', 'column': '金额', 'as': '合计'}]}]}]}
        nodes = {n['id']: n for n in run_pipeline(self.conn, spec, self.datasets)['nodes']}
        self.assertEqual((nodes['j']['rows_in'], nodes['j']['rows_out']), ([160, 45], 169))
        found = nodes['g']['operators'][1]['double_counted']
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]['column'], found[0]['fn'], found[0]['groups']), ('金额', 'sum', len(wrong)))
        by_group = {e['group']['客户编号']: (e['with'], e['true']) for e in found[0]['examples']}
        self.assertEqual(by_group['KH099'], (doubled['KH099'], true['KH099']))
        self.assertEqual(by_group['KH099'], (52620, 49470))                                    # one of its orders has a ticket: +3,150, as the fan-out counted
        self.assertEqual({k: v for k, v in by_group.items()}, {k: (doubled[k], true[k]) for k in wrong})
        # the figure that would be wrong is named before it is used; a customer nothing doubled is not listed
        self.assertNotIn('KH002', by_group)


class OutputTests(Workspace):
    def output(self, **step):
        spec = {'steps': [{'id': 'in', 'type': 'input', 'dataset': '订单承诺'}, {'id': 'out', 'type': 'output', 'from': 'in', 'name': '结果', **step}]}
        return {n['id']: n for n in run_pipeline(self.conn, spec, self.datasets)['nodes']}['out']['output']

    def test_a_key_is_built_from_columns_and_repeated_keys_are_listed(self):
        built = self.output(key={'columns': ['订单号', '承诺版本'], 'separator': '#', 'as': '键'})
        self.assertEqual(built['key'], ['键'])
        self.assertIsNone(built['duplicate_keys'])
        self.assertEqual(built['columns'][-1], {'name': '键', 'type': 'text'})
        repeated = self.output(key={'columns': ['订单号']})
        counts = Counter(r['订单号'] for r in RECORDS['订单承诺'])
        many = {k: n for k, n in counts.items() if n > 1}
        self.assertEqual((repeated['duplicate_keys']['count'], repeated['duplicate_keys']['extra_rows']), (len(many), sum(n - 1 for n in many.values())))
        top = repeated['duplicate_keys']['examples'][0]
        self.assertEqual(top['rows'], max(many.values()))
        self.assertEqual(repeated['empty_keys'], 0)

    def test_the_columns_an_output_keeps_and_the_ones_it_drops(self):
        kept = self.output(columns=['订单号', '承诺数量'])
        self.assertEqual(([c['name'] for c in kept['columns']], kept['dropped']), (['订单号', '承诺数量'], ['承诺版本', '承诺交付日期']))
        with self.assertRaises(ValueError) as caught:
            self.output(columns=['没有这列'])
        self.assertIn('没有列 没有这列', str(caught.exception))

    def test_two_outputs_cannot_write_the_same_dataset(self):
        steps = [{'id': 'in', 'type': 'input', 'dataset': '订单承诺'}, {'id': 'a', 'type': 'output', 'from': 'in', 'name': 'X'}, {'id': 'b', 'type': 'output', 'from': 'in', 'name': 'X'}]
        with self.assertRaises(ValueError) as caught:
            check_pipeline({'steps': steps}, self.datasets)
        self.assertIn('两个输出不能写到同一个数据集', str(caught.exception))


class SafetyTests(Workspace):
    def test_a_column_or_dataset_name_that_looks_like_sql_is_only_a_name(self):
        name = 'a"; DROP TABLE dataset; --'
        tables = store(self.conn, {'带引号': [{name: '1', 'v': '2'}, {name: '3', 'v': '4'}]})
        node = self.run_ops([{'op': 'filter', 'where': {'column': name, 'cmp': 'gt', 'value': 1}}, {'op': 'calc', 'name': 'x"y', 'expression': f'[{name}] + v'}], '带引号', tables=tables)['t']
        self.assertEqual(node['rows_out'], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM dataset").fetchone()[0] > 0, True)

    OPS = [{'op': 'filter', 'where': {'all': [{'column': '金额', 'cmp': 'between', 'low': 1000, 'high': 5000}, {'column': '金额', 'cmp': 'in', 'values': [2520, 24000]},
                                              {'any': [{'column': '交付天数', 'cmp': 'is_null'}, {'column': '状态码', 'cmp': 'ne', 'meaning': '已取消'}]}]}},
           {'op': 'fill_null', 'columns': ['交付天数'], 'with': {'constant': 0}, 'empty_as_null': True}, {'op': 'fill_null', 'columns': ['交付天数'], 'with': {'column': '数量'}},
           {'op': 'text_clean', 'columns': ['订单号'], 'steps': [{'do': 'trim'}, {'do': 'replace', 'find': 'a', 'with': 'b'}]},
           {'op': 'cast', 'column': '订单号', 'to': 'date', 'format': 'YYYY-MM-DD', 'as': '日期'}, {'op': 'calc', 'name': '比', 'expression': '金额 / 数量', 'type': 'decimal'},
           {'op': 'dedupe', 'keys': ['订单号'], 'keep': 'last', 'order_by': '金额'},
           {'op': 'label', 'column': '状态码', 'as': '状态', 'mapping': [{'value': 0, 'label': '已交付'}], 'unmapped': 'other', 'other': '其他'},
           {'op': 'aggregate', 'group_by': ['客户编号'], 'aggregations': [{'fn': 'sum', 'column': '金额', 'as': '合计'}, {'fn': 'count', 'column': None, 'as': 'n'}]}]

    def test_a_value_of_the_wrong_kind_anywhere_in_a_definition_is_refused_in_words_and_never_crashes(self):
        """Every field of a definition that uses all the operators, a join and an output is set in turn to a list, an object, a number, null, true and text, and left out:
        the answer is a ValueError (what a person reads), never a TypeError from looking a list up in a dict."""
        spec = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}, {'id': 't', 'type': 'input', 'dataset': '售后工单'},
                          {'id': 'j', 'type': 'join', 'left': 'o', 'right': 't', 'how': 'left', 'on': [{'left': '订单号', 'right': '订单号'}], 'null_keys': 'equal', 'right_columns': ['问题类型']},
                          *({'id': f'x{i}', 'type': 'transform', 'from': 'o', 'operators': [op]} for i, op in enumerate(self.OPS)),
                          {'id': 'out', 'type': 'output', 'from': 'j', 'name': '输出', 'key': {'columns': ['订单号', '问题类型']}, 'mode': 'new'}]}
        ctx = new_context(meanings={'订单.状态码': {'已取消': ['2']}}, codes={'订单.状态码'})

        def paths(node, path=()):
            for k, v in (node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else ()):
                yield path + (k,)
                yield from paths(v, path + (k,))

        def changed(path, value=None, remove=False):
            copy = json.loads(json.dumps(spec))
            holder = copy
            for p in path[:-1]:
                holder = holder[p]
            if remove:
                del holder[path[-1]]
            else:
                holder[path[-1]] = value
            return copy
        for path in paths(spec):
            for variant in [changed(path, v) for v in ([], {}, [[]], 1, 2.5, None, True, {'a': []}, '没有')] + ([changed(path, remove=True)] if isinstance(path[-1], str) else []):
                try:
                    check_pipeline(variant, self.datasets, {}, new_context(meanings=ctx['meanings'], codes=ctx['codes']))
                except ValueError:
                    pass   # said in words
                except Exception as exc:
                    self.fail(f'{path}: {type(exc).__name__}: {exc}')


if __name__ == '__main__':
    unittest.main()
