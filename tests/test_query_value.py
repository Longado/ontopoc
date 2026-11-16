"""Why OntoPoc Query and not plain SQL: the same questions on the same planted rows, written both ways, run through the real service as different people.

Each test is a case where hand-written SQL over the tables gives a number with no warning, and the query gives the right one, or refuses and says why:
  - a row rule: SQL counts every row whoever asks; the query counts the asker's rows and says they were limited;
  - a code that changed meaning: SQL's `状态码 = '2'` keeps counting after the codes shift; the query, written with the meaning, is refused;
  - a join that doubles rows: 客户 has KH012 twice, so SQL's JOIN adds those orders twice; the query refuses to walk that relation and says why;
  - a hidden type or property: SQL reads it; for the query it is not there, in the same words as one that does not exist.
The numbers SQL gives are computed here, on the planted rows loaded into SQLite, so the comparison is with SQL as a person would write it."""
import base64
import csv
import io
import sqlite3
import unittest

from scripts.real_model_check import build_workspace
from tests import test_workspace_store as planted
from tests.test_derived_properties import CUSTOMER, ORDER, RELATIONS, TABLES
from tests.test_object_relations import customers_mended
from tests.test_object_types import shifted_orders_csv
from tests.test_two_person import SigningTestCase

SOURCES = planted.planted_bundle()['sources']
ORDERS = SOURCES['订单']['records']


def sql_db(customers=None, orders=None) -> sqlite3.Connection:
    """The planted 订单 and 客户 tables in SQLite, as an analyst with database access would query them."""
    db = sqlite3.connect(':memory:')
    for name, rows in (('订单', orders or ORDERS), ('客户', customers or SOURCES['客户']['records'])):
        cols = list(rows[0])
        db.execute(f'CREATE TABLE {name} ({", ".join(cols)})')
        db.executemany(f'INSERT INTO {name} VALUES ({", ".join("?" * len(cols))})', [[r[c] for c in cols] for r in rows])
    return db


def mended_customers() -> list[dict]:
    return list(csv.DictReader(io.StringIO(base64.b64decode(customers_mended()['content_base64']).decode('utf-8'))))


def load_tests(loader, standard, pattern):
    """Only the tests written here: the classes borrow the signing tests' service and people, not their tests."""
    return unittest.TestSuite(cls(name) for cls in (QueryServiceTests, SqlComparisonTests) for name in vars(cls) if name.startswith('test_'))


class QueryCase(SigningTestCase):
    def team(self, base):
        team = self.people(base, 'ann', 'bob', 'vera', 'carl', roles={'vera': 'viewer'})
        build_workspace(team['ann'], team['bob'])
        return team

    def query(self, client, text, **params):
        return client.post('/api/workspace/query', {'text': text, **({'params': params} if params else {})})

    def user_id(self, admin, name):
        return next(u['id'] for u in admin.get('/api/users')[1]['users'] if u['username'] == name)


class QueryServiceTests(QueryCase):

    def test_a_query_runs_with_no_model_and_answers_what_the_rows_say_with_the_definitions_it_stood_on(self):
        names = {r['客户编号']: r['客户名称'] for r in mended_customers()}
        totals = {}
        for r in ORDERS:
            if r['状态码'] != '2':
                totals[r['客户编号']] = totals.get(r['客户编号'], 0) + int(r['金额'])
        top3 = [[names[k], v] for k, v in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            text = ("SELECT c.客户名称, sum(o.金额) AS 合计 FROM (o:订单)-[:订单属于客户]->(c:客户) "
                    "WHERE o.状态码 <> '已取消' GROUP BY c.客户名称 ORDER BY 合计 DESC LIMIT 3")
            status, body = self.query(team['ann'], text)
            self.assertEqual((status, body['status']), (200, 'answered'), body)
            self.assertEqual([g[:2] for g in body['answer']['groups']], top3)
            self.assertEqual(body['query']['start'], 'order')
            self.assertEqual(sorted((d['kind'], d['name']) for d in body['definitions']),
                             [('meaning', '订单.状态码'), ('relation', '订单属于客户'), ('type', '客户'), ('type', '订单')])
            self.assertTrue(all(d['confirmed_by'] == 'Bob' for d in body['definitions']))
            self.assertIn('ORDER BY 合计 DESC', body['text'])   # the text as the service reads it back
            # the same query written with a $parameter
            status, again = self.query(team['ann'], text.replace("'已取消'", '$state'), state='已取消')
            self.assertEqual([g[:2] for g in again['answer']['groups']], top3)

    def test_a_structured_query_reads_back_as_text_in_the_askers_names(self):
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            status, body = team['ann'].post('/api/workspace/query/text', {'query': {'start': 'order', 'measure': {'field': '金额', 'op': 'sum'},
                                                                                    'group_by': [{'via': ['order_customer'], 'field': '客户名称'}], 'top': 1}})
            self.assertEqual(status, 200, body)
            self.assertEqual(body['text'], 'SELECT c.客户名称, sum(o.金额) AS 合计\nFROM (o:订单)-[:订单属于客户]->(c:客户)\nGROUP BY c.客户名称\nLIMIT 1')

    def test_a_mistake_is_a_400_that_says_what_is_there(self):
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            status, body = self.query(team['ann'], 'SELECT count(o) FROM (o:订单)-[:下单]->(c:客户)')
            self.assertEqual(status, 400, body)
            self.assertIn('订单属于客户（订单→客户）', body['error'])
            self.assertEqual(self.query(team['ann'], 'SELECT count(o) FROM (o:订单) WHERE o.客户编号 = $who')[0], 400)


class SqlComparisonTests(QueryCase):
    def test_a_row_rule_sql_counts_every_row_the_query_counts_the_askers_rows_and_says_so(self):
        sql = sql_db().execute('SELECT count(*) FROM 订单').fetchone()[0]
        mine = sum(1 for r in ORDERS if r['客户编号'] == 'KH001')
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            admin, vera = team['admin'], team['vera']
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH001', 'user_ids': [self.user_id(admin, 'vera')]}]})[0], 200)
            text = 'SELECT count(o) FROM (o:订单)'
            limited = self.query(vera, text)[1]
            self.assertEqual((sql, limited['answer']['total'], mine), (160, 5, 5))
            self.assertEqual(limited['limited_by_rule'], [{'type': 'order', 'name': '订单', 'rule': '客户编号 = KH001'}])
            self.assertEqual(self.query(admin, text)[1]['answer']['total'], 160)
            # grouping by a related type reads only her rows too: one customer, five orders
            grouped = self.query(vera, 'SELECT c.客户名称, count(o) FROM (o:订单)-[:订单属于客户]->(c:客户) GROUP BY c.客户名称')[1]
            self.assertEqual([g[1] for g in grouped['answer']['groups']], [5])

    def test_a_code_that_changed_meaning_sql_keeps_counting_the_query_is_refused(self):
        shifted = list(csv.DictReader(io.StringIO(base64.b64decode(shifted_orders_csv()['content_base64']).decode('utf-8'))))
        before = sql_db().execute("SELECT count(*) FROM 订单 WHERE 状态码 = '2'").fetchone()[0]
        after = sql_db(orders=shifted).execute("SELECT count(*) FROM 订单 WHERE 状态码 = '2'").fetchone()[0]
        self.assertEqual((before, after), (16, sum(1 for r in ORDERS if r['状态码'] == '1')))   # after the shift '2' is what used to be 生产中
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            text = "SELECT count(o) FROM (o:订单) WHERE o.状态码 = '已取消'"
            self.assertEqual(self.query(team['ann'], text)[1]['answer']['total'], 16)
            self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            status, body = self.query(team['ann'], text)
            self.assertEqual(status, 200, body)
            self.assertNotEqual(body['status'], 'answered', body)
            self.assertNotIn('answer', body)
            self.assertIn('订单', body['reason'])

    def test_a_join_that_doubles_rows_sql_adds_them_twice_the_query_refuses_and_says_why(self):
        truth = sum(int(r['金额']) for r in ORDERS)
        doubled = sql_db().execute('SELECT sum(o.金额) FROM 订单 o JOIN 客户 c ON o.客户编号 = c.客户编号').fetchone()[0]
        twice = sum(int(r['金额']) for r in ORDERS if r['客户编号'] == 'KH012')
        missing = sum(int(r['金额']) for r in ORDERS if r['客户编号'] == 'KH099')   # an inner join also drops the orders whose customer is not in the table
        self.assertEqual(doubled, truth + twice - missing)
        self.assertGreater(twice, 0)
        with self.service(gateway=None) as (base, out):
            people = self.people(base, 'ann', 'bob')
            ann, bob = people['ann'], people['bob']
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
            for t in (ORDER, CUSTOMER):   # 客户 keyed on 客户编号 + 城市, as the table needs while KH012 is there twice
                self.assertEqual(ann.post('/api/workspace/types', t)[0], 200)
                for column in (('状态码',) if t is ORDER else ()) + (None,):   # the meanings of 状态码 first, then the type
                    shown = bob.get(f'/api/workspace/types/{t["english_name"]}')[1]
                    shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
                    status, body = bob.post('/api/workspace/types/confirm', {'id': t['english_name'], 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})
                    self.assertEqual(status, 200, body)
            relation = RELATIONS[0]
            self.assertEqual(ann.post('/api/workspace/relations', relation)[0], 200)
            detail = bob.get('/api/workspace/relations/order_customer')[1]
            status, body = bob.post('/api/workspace/queue/confirm', {'element': 'relation:order_customer', 'version': detail['version'], 'seen': detail['check']['signature']})
            self.assertEqual(status, 409, body)   # the relation check sees what the JOIN would do, and the relation is not confirmed
            self.assertIn('KH012', body['error'])
            self.assertIn('重复算', body['error'])
            status, body = self.query(ann, 'SELECT c.客户等级, sum(o.金额) FROM (o:订单)-[:订单属于客户]->(c:客户) GROUP BY c.客户等级')
            self.assertEqual(status, 200, body)
            self.assertEqual(body['status'], 'refused', body)
            self.assertNotIn('answer', body)
            self.assertIn('订单属于客户', body['reason'])
            # KH012 once: the relation is confirmed, but 客户 is still keyed on 客户编号 + 城市, so a walk could still meet two customers for one number
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
            detail = bob.get('/api/workspace/relations/order_customer')[1]
            self.assertEqual(bob.post('/api/workspace/queue/confirm', {'element': 'relation:order_customer', 'version': detail['version'], 'seen': detail['check']['signature']})[0], 200)
            status, body = self.query(ann, 'SELECT c.客户等级, sum(o.金额) FROM (o:订单)-[:订单属于客户]->(c:客户) GROUP BY c.客户等级')
            self.assertEqual((status, body['status']), (200, 'refused'), body)
            self.assertIn('客户编号 + 城市', body['reason'])
            self.assertEqual(body['refusal']['definitions'][0]['id'], 'relation:order_customer')
            self.assertEqual(self.query(ann, 'SELECT sum(o.金额) FROM (o:订单)')[1]['answer']['measure']['value'], truth)

    def test_a_hidden_type_or_property_reads_like_one_that_does_not_exist(self):
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            admin, carl = team['admin'], team['carl']
            self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'order', 'column': '金额', 'visible_to': [self.user_id(admin, 'ann')]})[0], 200)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'customer', 'visible_to': [self.user_id(admin, 'ann')]})[0], 200)
            hidden = self.query(carl, 'SELECT sum(o.金额) FROM (o:订单)')
            absent = self.query(carl, 'SELECT sum(o.利润) FROM (o:订单)')
            self.assertEqual((hidden[0], absent[0]), (400, 400))
            self.assertEqual(hidden[1]['error'], absent[1]['error'].replace('利润', '金额'))
            self.assertNotIn('金额」。', absent[1]['error'].split('它的属性')[1])
            gone = self.query(carl, 'SELECT count(c) FROM (c:客户)')[1]['error']
            never = self.query(carl, 'SELECT count(c) FROM (c:供应商)')[1]['error']
            self.assertEqual(gone, never.replace('供应商', '客户'))
            self.assertNotIn('订单属于客户', self.query(carl, 'SELECT count(o) FROM (o:订单)-[:下单]->(x:订单)')[1]['error'])
            self.assertEqual(self.query(team['ann'], 'SELECT sum(o.金额) FROM (o:订单)')[1]['answer']['measure']['value'], sum(int(r['金额']) for r in ORDERS))
