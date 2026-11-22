"""The new answer shapes change no existing answer. The same questions with the same scripted replies, and the same written queries, are worked out with the
shapes switched on and off (workspace_questions.ROW_ANSWERS); off, the code is the earlier code. Every answer, refusal, label and kept record must be the same,
except for a reply or a query that asks for objects (a list, a lookup) or uses today: those, and only those, change, and each gets what it asked for.

The questions are those of the one-number tests: the demo sample asked by a guest (a viewer) and by demo-admin, and the pilot sample with and without an orphan
order, and written queries on both."""
import json
import sqlite3
import unittest
from unittest import mock

from ontology_poc_generator import workspace_questions
from tests import test_one_number as one
from tests.test_demo_mode import a_guest
from tests.test_demo_view_waits import Seeded
from tests.test_derived_view_exact import with_orphan
from tests.test_workspace_questions import ALL_ORDERS

ORDERS_PLAIN = {'start': 'order', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None}
DEMO_NEW = [   # (question, the model's reply) asking for objects or using today: these, and only these, change with the shapes on
    ('Which orders were cancelled?', one.item({**ORDERS_PLAIN, 'where': [{'field': 'status_code', 'equals': 'Cancelled'}], 'list': {}}, [{'id': 'orders.status_code=Cancelled', 'direction': 'include', 'basis': 'cancelled'}])),
    ('Which valid orders are there?', one.item({**ORDERS_PLAIN, 'list': {'properties': ['amount']}}, one.VALID_INCLUDE)),
    ('List the big orders', one.item({**ORDERS_PLAIN, 'where': [{'field': 'amount', 'at_least': 1000}], 'list': {'limit': 5}})),
    ('What is order O0001?', one.item({'start': 'order', 'lookup': {'order_id': 'O0001'}})),
    ('What is order O9999?', one.item({'start': 'order', 'lookup': {'order_id': 'O9999'}})),
    ('How many orders before today?', one.item({**ORDERS_PLAIN, 'where': [{'field': 'order_date', 'less_than': 'today'}]})),
    ('Which orders before today?', one.item({**ORDERS_PLAIN, 'where': [{'field': 'order_date', 'less_than': 'today'}], 'list': {}})),
]
QUERY_TEXTS = [   # written queries: numbers, refusals and the new shapes
    'SELECT count(o) FROM (o:Order)', "SELECT count(o) FROM (o:Order) WHERE o.status_code = 'Cancelled'", 'SELECT sum(o.amount) FROM (o:Order)',
    "SELECT o.status_code, count(o) FROM (o:Order) GROUP BY o.status_code", 'SELECT month(o.order_date), sum(o.amount) FROM (o:Order) GROUP BY month(o.order_date)',
    "SELECT count(o) FROM (o:Order) WHERE o.amount BETWEEN 9 AND 1", 'SELECT count(o) FROM (o:Order) WHERE o.nope = 1', 'SELECT o FROM (o:Order)',
    "SELECT count(o) FROM (o:Order) WHERE o.order_date < 'yesterday'", 'SELECT GRAPH FROM (o:Order) LIMIT 3', 'SELECT LIST.amount FROM (o:Order)', 'SELECT count(o) FROM (o:Order) WHERE o.status_code = 1 OR o.amount > 3',
]
QUERY_NEW = ['SELECT LIST o FROM (o:Order)', "SELECT ONE o FROM (o:Order) WHERE o.order_id = 'O0001'", 'SELECT count(o) FROM (o:Order) WHERE o.order_date < today',
             "SELECT count(o) FROM (o:Order) WHERE o.order_date < 'today'",
             "SELECT LIST o.amount FROM (o:Order) WHERE o.status_code <> 'Cancelled' LIMIT 3"]


def asked_new(reply) -> bool:
    """Does the reply ask for objects or use today?"""
    text = json.dumps(reply, ensure_ascii=False)
    return '"list"' in text or '"lookup"' in text or '"today"' in text


def kept(folder, answer_id) -> tuple:
    """The record kept for one answer, as stored."""
    conn = sqlite3.connect(folder / 'workspace.sqlite')
    try:
        return conn.execute('SELECT question, status, answer_json, definitions_json, dataset_versions_json, types_json FROM qa_question WHERE id = ?', (answer_id,)).fetchone()
    finally:
        conn.close()


class DemoSwitch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        one.setUpModule()
        cls.demo = Seeded().__enter__()
        cls.guest = a_guest(cls.demo.base)

    @classmethod
    def tearDownClass(cls):
        cls.demo.__exit__(None, None, None)
        one.tearDownModule()

    def ask(self, who, question, reply, flag):
        self.demo.model.__class__ = one.Scripted
        self.demo.model.replies = [reply]
        with mock.patch.object(workspace_questions, 'ROW_ANSWERS', flag):
            status, body = who.call('POST', '/api/workspace/ask', {'question': question})
        self.assertEqual(status, 200, body)
        return body

    def test_switched_off_every_answer_and_kept_record_is_the_one_given_with_it_on_except_where_objects_or_today_were_asked_for(self):
        changed, same = [], 0
        for who in (self.guest, self.demo.admin('en'), self.demo.admin()):
            for question, reply in [*one.DEMO_PAIRS, *DEMO_NEW]:
                with self.subTest(question=question, reply=str(reply)[:80]):
                    on, off = self.ask(who, question, reply, True), self.ask(who, question, reply, False)
                    if one.stripped(on) == one.stripped(off) and kept(self.demo.folder, on['id'])[1:] == kept(self.demo.folder, off['id'])[1:]:
                        same += 1
                        self.assertFalse(asked_new(reply) and ('objects' in (on.get('answer') or {}) or 'today' in on), question)
                        continue
                    changed.append(question)
                    self.assertTrue(asked_new(reply), question)   # only a reply that asks for objects or uses today changes
                    self.assertTrue(on['status'] in ('answered', 'no_data') and ('objects' in (on.get('answer') or {}) or 'today' in on or 'lookup' in reply['query']), on)
        self.assertEqual(sorted(set(changed)), sorted({q for q, _ in DEMO_NEW}))
        self.assertGreaterEqual(same, 3 * len(one.DEMO_PAIRS))

    def test_switched_off_every_written_query_is_answered_or_refused_as_with_it_on_except_the_new_shapes(self):
        for who in (self.guest, self.demo.admin('en')):
            for text in [*QUERY_TEXTS, *QUERY_NEW]:
                with self.subTest(text=text):
                    got = []
                    for flag in (True, False):
                        with mock.patch.object(workspace_questions, 'ROW_ANSWERS', flag):
                            got.append(who.call('POST', '/api/workspace/query', {'text': text}))
                    if text in QUERY_NEW:
                        self.assertEqual((got[0][0], got[1][0]), (200, 400), got)
                    else:
                        self.assertEqual(got[0], got[1])


class PilotSwitch(one.PilotTests):
    NEW = [('哪些客户在成都？', one.item({'start': 'customer', 'where': [{'field': 'city', 'equals': 'Chengdu'}], 'via': [], 'group_by': None, 'share': None, 'measure': None, 'list': {}})),
           ('有效订单有哪些？', one.item({**ORDERS_PLAIN, 'list': {}}, [{'id': '有效订单', 'direction': 'include', 'basis': '有效订单'}])),
           ('客户 C009 是谁？', one.item({'start': 'customer', 'lookup': {'customer_id': 'C009'}}))]

    def test_switched_off_every_answer_and_kept_record_is_the_one_given_with_it_on_except_where_objects_were_asked_for(self):
        for orders in (None, with_orphan()):
            model = one.Scripted(one.item())
            with self.service(gateway=model) as (base, out):
                ann = self.foundation(base, orders=orders)['ann']
                for question, reply in [*self.PAIRS, *self.NEW]:
                    with self.subTest(question=question, reply=str(reply)[:80], orphan=orders is not None):
                        got = []
                        for flag in (True, False):
                            model.replies = [reply]
                            with mock.patch.object(workspace_questions, 'ROW_ANSWERS', flag):
                                got.append(ann.post('/api/workspace/ask', {'question': question})[1])
                        on, off = got
                        if asked_new(reply):
                            self.assertNotEqual(one.stripped(on), one.stripped(off))
                            self.assertIn('objects', on['answer'], on)
                            continue
                        self.assertEqual(one.stripped(on), one.stripped(off))
                        self.assertEqual(kept(out, on['id'])[1:], kept(out, off['id'])[1:])


if __name__ == '__main__':
    unittest.main()
