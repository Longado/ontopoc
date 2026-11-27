"""R10 step 3: ranges and time rollups. `o.金额 > 1000`, `o.下单日期 BETWEEN '2026-01-01' AND '2026-03-31'` and `GROUP BY month(o.下单日期)`, in the
language and in the engine. A value is compared as a number when both sides read as numbers, as a date when both read as dates; anything else is not
quietly matched or dropped: a value that cannot be read is counted and said, and a bound that is neither is refused before anything is counted."""
import copy
import sqlite3
import unittest

from ontology_poc_generator.ontology_questions import run_query
from ontology_poc_generator.ontopoc_query import QueryError, canonical, compile_query, to_text
from tests.test_company_ontology import BUNDLE, PROPOSAL
from tests.test_ontopoc_query import CATALOG, q
from tests.test_query_value import ORDERS, QueryCase, sql_db

ROWS = [   # 订单: amounts and dates as an export gives them, one of each kind of trouble
    {'订单号': 'O1', '客户编号': 'C1', '金额': '100', '下单日期': '2026-01-02'},
    {'订单号': 'O2', '客户编号': 'C1', '金额': '2,500', '下单日期': '2026-01-31'},
    {'订单号': 'O3', '客户编号': 'C2', '金额': '900', '下单日期': '2026/2/5'},
    {'订单号': 'O4', '客户编号': 'C2', '金额': '1200', '下单日期': '2026-03-01 09:30:00'},
    {'订单号': 'O5', '客户编号': 'C3', '金额': '待定', '下单日期': '待定'},
]


def bundle():
    b = copy.deepcopy(BUNDLE)
    b['sources']['订单']['records'] = copy.deepcopy(ROWS)
    return b


def run(**parts):
    return run_query(PROPOSAL, bundle(), {'start': 'order', **parts})


class CompileTests(unittest.TestCase):
    def test_ranges_compile_into_one_condition_each(self):
        cases = {
            "o.金额 > 1000": {'field': '金额', 'more_than': '1000'},
            "o.金额 >= 1000": {'field': '金额', 'at_least': '1000'},
            "o.金额 < 1000": {'field': '金额', 'less_than': '1000'},
            "o.金额 <= 1000": {'field': '金额', 'at_most': '1000'},
            "o.下单日期 BETWEEN '2026-01-01' AND '2026-03-31'": {'field': '下单日期', 'at_least': '2026-01-01', 'at_most': '2026-03-31'},
            "o.下单日期 BETWEEN $start AND $end": {'field': '下单日期', 'at_least': '2026-01-01', 'at_most': '2026-01-31'},
        }
        for cond, want in cases.items():
            got = compile_query(f'SELECT count(o) FROM (o:订单) WHERE {cond}', CATALOG, {'start': '2026-01-01', 'end': '2026-01-31'})
            self.assertEqual(got['where'], [want], cond)
        both = compile_query("SELECT count(o) FROM (o:订单) WHERE o.下单日期 >= '2026-01-01' AND o.下单日期 < '2026-02-01' AND o.状态码 <> '已取消'", CATALOG)
        self.assertEqual(both['where'], [{'field': '下单日期', 'at_least': '2026-01-01'}, {'field': '下单日期', 'less_than': '2026-02-01'}, {'field': '状态码', 'not_equals': '已取消'}])

    def test_month_and_year_group_by_a_date(self):
        text = "SELECT month(o.下单日期), sum(o.金额) AS 合计 FROM (o:订单) GROUP BY month(o.下单日期) ORDER BY 合计 DESC"
        self.assertEqual(compile_query(text, CATALOG), q(start='order', group_by=[{'via': [], 'field': '下单日期', 'by': 'month'}], measure={'field': '金额', 'op': 'sum'}, order='largest'))
        text = 'SELECT c.城市, year(o.下单日期), count(o) FROM (o:订单)-[:订单属于客户]->(c:客户) GROUP BY c.城市, year(o.下单日期)'
        self.assertEqual(compile_query(text, CATALOG)['group_by'], [{'via': ['order_customer'], 'field': '城市'}, {'via': [], 'field': '下单日期', 'by': 'year'}])

    def test_what_still_cannot_be_said_is_refused_in_words(self):
        for text, word in (
                ('SELECT month(o.下单日期), count(o) FROM (o:订单) GROUP BY o.下单日期', 'GROUP BY'),
                ('SELECT count(o) FROM (o:订单) GROUP BY week(o.下单日期)', 'month'),
                ("SELECT count(o) FROM (o:订单) WHERE o.金额 > '1000' AND o.金额 > '2000' OR o.金额 < '5'", 'OR'),
                ("SELECT count(o) FROM (o:订单) WHERE o.下单日期 BETWEEN '2026-01-01'", 'AND'),
                ("SELECT count(o) FROM (o:订单) WHERE o.下单日期 LIKE '2026%'", '模糊匹配'),
                ('SELECT count(o) FROM (o:订单) WHERE o.下单日期 >= 2026-01-01', "加引号")):
            with self.assertRaises(QueryError, msg=text) as caught:
                compile_query(text, CATALOG)
            self.assertIn(word, str(caught.exception), text)

    def test_ranges_and_rollups_read_back_as_text(self):
        for query in ({'start': 'order', 'where': [{'field': '下单日期', 'at_least': '2026-01-01', 'at_most': '2026-03-31'}, {'field': '金额', 'more_than': '1000'}]},
                      {'start': 'order', 'where': [{'field': '金额', 'less_than': '5'}, {'field': '金额', 'at_most': '9'}]},
                      {'start': 'order', 'group_by': [{'via': [], 'field': '下单日期', 'by': 'month'}], 'measure': {'field': '金额', 'op': 'sum'}, 'top': 2},
                      {'start': 'ticket', 'group_by': [{'via': ['ticket_order'], 'field': '下单日期', 'by': 'year'}]}):
            text = to_text(query, CATALOG)
            self.assertEqual(compile_query(text, CATALOG), canonical(query), text)
        self.assertIn("BETWEEN '2026-01-01' AND '2026-03-31'", to_text({'start': 'order', 'where': [{'field': '下单日期', 'at_least': '2026-01-01', 'at_most': '2026-03-31'}]}, CATALOG))


class EngineTests(unittest.TestCase):
    def test_a_number_range_reads_numbers_as_numbers_and_counts_what_it_cannot_read(self):
        result = run(where=[{'field': '订单.金额', 'more_than': '1000'}])
        self.assertEqual((result['status'], result['answer']['total']), ('answered', 2))   # 2,500 and 1200; not "900" > "1000" as text would say, not 待定
        f = result['evidence']['filters'][0]
        self.assertEqual((f['range'], f['unreadable'], f['unreadable_examples']), ('金额 > 1000', 1, ['待定']))
        self.assertIn('金额 > 1000', result['path'])
        self.assertEqual(run(where=[{'field': '订单.金额', 'at_least': '100', 'at_most': '900'}])['answer']['total'], 2)

    def test_a_date_range_reads_the_usual_ways_a_date_is_written(self):
        result = run(where=[{'field': '订单.下单日期', 'at_least': '2026-01-01', 'at_most': '2026-02-28'}])
        self.assertEqual(result['answer']['total'], 3)   # 01-02, 01-31 and 2026/2/5
        self.assertEqual(run(where=[{'field': '订单.下单日期', 'at_least': '2026-03-01'}])['answer']['total'], 1)   # a date and time on the day counts
        self.assertEqual(run(where=[{'field': '订单.下单日期', 'less_than': '2026-02'}])['answer']['total'], 2)   # a month is its first day

    def test_a_month_bound_covers_the_whole_month_on_either_edge(self):
        self.assertEqual(run(where=[{'field': '订单.下单日期', 'at_most': '2026-01'}])['answer']['total'], 2)   # all of January
        self.assertEqual(run(where=[{'field': '订单.下单日期', 'at_least': '2026-01', 'at_most': '2026-02'}])['answer']['total'], 3)   # January and February
        self.assertEqual(run(where=[{'field': '订单.下单日期', 'more_than': '2026-02'}])['answer']['total'], 1)   # after February: March
        self.assertEqual(run(where=[{'field': '订单.下单日期', 'less_than': '2026-02'}])['answer']['total'], 2)   # before February
        self.assertEqual(run(where=[{'field': '订单.下单日期', 'at_least': '2026-02'}])['answer']['total'], 2)

    def test_only_one_way_of_writing_a_date_at_a_time_reads_as_a_date(self):
        from ontology_poc_generator.ontology_questions import as_date
        self.assertEqual([as_date(v) for v in ('2026-01-02', '2026/1/2', '2026.01.02', '2026年1月2日', '2026-03-01 09:30:00', '2026-01-31T23:30:00-05:00', '2026-02', '2026年2月')],
                         [(2026, 1, 2), (2026, 1, 2), (2026, 1, 2), (2026, 1, 2), (2026, 3, 1), (2026, 1, 31), (2026, 2, 1), (2026, 2, 1)])
        self.assertEqual([as_date(v) for v in ('2026.5', '1999.12', '2026-01/02', '2026-13-01', '12/31/2026', '20260102', '2026', '', None, '２０２６-01-02')], [None] * 10)

    def test_bounds_the_wrong_way_round_are_refused(self):
        for cond in ({'field': '订单.金额', 'at_least': '9', 'at_most': '1'}, {'field': '订单.下单日期', 'more_than': '2026-03-01', 'less_than': '2026-01-01'}):
            result = run(where=[cond])
            self.assertEqual(result['status'], 'query_limit', cond)
            self.assertIn('下限', result['reason'])

    def test_a_bound_that_is_neither_a_number_nor_a_date_or_two_kinds_at_once_is_refused_before_counting(self):
        for cond in ({'field': '订单.金额', 'more_than': '很多'}, {'field': '订单.下单日期', 'at_least': '2026-01-01', 'at_most': '5'},
                     {'field': '订单.金额', 'more_than': ['1']}, {'field': '订单.金额', 'more_than': '1', 'equals': '2'}):
            result = run(where=[cond])
            self.assertEqual(result['status'], 'query_limit', cond)

    def test_month_and_year_group_dates_and_say_what_had_no_date(self):
        result = run(group_by=[{'via': [], 'field': '订单.下单日期', 'by': 'month'}])
        self.assertEqual(result['answer']['groups'], [['2026-01', 2], ['2026-02', 1], ['2026-03', 1]])
        self.assertEqual(result['answer']['without_value'], 1)
        self.assertEqual(result['answer']['unreadable'], {'field': '下单日期', 'count': 1, 'unreadable_examples': ['待定']})   # not a missing date: one that does not read as a date
        self.assertIn('按月', result['path'])
        self.assertEqual(run(group_by=[{'via': [], 'field': '订单.下单日期', 'by': 'year'}], measure={'field': '订单.金额', 'op': 'sum'})['answer']['groups'], [['2026', 4700, 4]])
        self.assertEqual(run(group_by=[{'via': [], 'field': '订单.下单日期', 'by': 'week'}])['status'], 'query_limit')


class ViewerTests(unittest.TestCase):
    def test_a_viewer_reads_how_many_values_a_range_could_not_read_but_not_the_values(self):
        from ontology_poc_generator.workspace_questions import _strip_rows
        result = {'evidence': {'filters': [{'range': '金额 > 1000', 'unreadable': 1, 'unreadable_examples': ['待定'], 'examples': ['O1']}]}}
        self.assertEqual(_strip_rows(result), {'evidence': {'filters': [{'range': '金额 > 1000', 'unreadable': 1}]}})


class ServiceTests(QueryCase):
    """On the planted workspace, against SQL on the same rows: the same numbers where SQL is written with care, and the trap of text columns."""

    def team(self, base):
        from unittest import mock
        from tests import test_derived_properties as planted_types
        with_date = {**planted_types.ORDER, 'properties': [*planted_types.ORDER['properties'], {'column': '下单日期'}]}
        with mock.patch.object(planted_types, 'ORDER', with_date):   # the planted 订单 with its order date as a property
            return super().team(base)

    def test_a_quarter_and_a_monthly_rollup_match_sql_and_a_text_column_compared_as_text_does_not(self):
        db = sql_db()
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            ann = team['ann']
            got = self.query(ann, "SELECT count(o) FROM (o:订单) WHERE o.下单日期 BETWEEN $start AND $end", start='2026-01-01', end='2026-03-31')[1]
            self.assertEqual(got['answer']['total'], db.execute("SELECT count(*) FROM 订单 WHERE 下单日期 BETWEEN '2026-01-01' AND '2026-03-31'").fetchone()[0])
            monthly = self.query(ann, 'SELECT month(o.下单日期), sum(o.金额) AS 合计 FROM (o:订单) GROUP BY month(o.下单日期) ORDER BY 合计 DESC')[1]
            want = db.execute('SELECT substr(下单日期, 1, 7) AS m, sum(CAST(金额 AS INTEGER)) AS s FROM 订单 GROUP BY m ORDER BY s DESC').fetchall()
            self.assertEqual([g[:2] for g in monthly['answer']['groups']], [list(r) for r in want])
            big = self.query(ann, 'SELECT count(o) FROM (o:订单) WHERE o.金额 > 20000')[1]['answer']['total']
            self.assertEqual(big, sum(int(r['金额']) > 20000 for r in ORDERS))
            self.assertEqual(big, db.execute('SELECT count(*) FROM 订单 WHERE CAST(金额 AS INTEGER) > 20000').fetchone()[0])
            careless = db.execute('SELECT count(*) FROM 订单 WHERE 金额 > 20000').fetchone()[0]   # the columns are text, as some platforms keep them: text sorts above any number
            self.assertNotEqual(careless, big)
            self.assertEqual(careless, len(ORDERS))
            # a bound that is no number or date is the writer's mistake: a 400 with the reason, not a refusal about what is in scope
            status, body = self.query(ann, "SELECT count(o) FROM (o:订单) WHERE o.金额 > '很多'")
            self.assertEqual(status, 400, body)
            self.assertIn('都是数字或都是日期', body['error'])


def load_tests(loader, standard, pattern):
    suite = unittest.TestSuite()
    for cls in (CompileTests, EngineTests, ViewerTests, ServiceTests):
        suite.addTests(cls(name) for name in vars(cls) if name.startswith('test_'))
    return suite


if __name__ == '__main__':
    unittest.main()
