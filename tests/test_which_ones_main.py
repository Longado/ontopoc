"""The answer shapes of which-ones (lists, a lookup by key, today) held against main itself, not against the same code with the switch the other way.

golden/which_ones_main.json is what main (a9d6a76, before these shapes) gave, on the seeded demo, to a guest (a viewer) and to demo-admin in English, for:
- every question of the one-number tests with its scripted reply, and replies that carry `list`, `lookup` or a range bound `today` (main reads none of them);
- written queries (POST /api/workspace/query), with and without SELECT LIST, SELECT ONE, a bare today and a quoted 'today';
- questions answered by a written query (writes=query);
each as the response, the record kept for it and the answer reopened. Times are blanked; the rest is kept as a digest beside a few fields to read.

- Switch off (workspace_questions.ROW_ANSWERS = False): every one of them is main's, byte for byte.
- Switch on: every one that asks for no objects and writes no bare today is main's, byte for byte (only what the model is told differs, see
  test_which_ones.PromptTests). That includes a list key beside a sum, a grouping or a share, which main answered and which the list leaves alone, a list key that is
  empty or false, a quoted 'today', 'Today ' and a today on a column that is not a date.

To record it again, on a checkout of main with this file copied into its tests folder: ONTOPOC_RECORD_GOLDEN=1 python -m unittest tests.test_which_ones_main
(the file is then written next to that copy; copy it back here). Only when main itself changes these answers."""
import hashlib
import json
import os
import re
import sqlite3
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from ontology_poc_generator import workspace_questions
from tests import test_one_number as one
from tests.test_demo_mode import a_guest
from tests.test_demo_view_waits import Seeded

GOLDEN = Path(__file__).parent / 'golden' / 'which_ones_main.json'
TIME = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?')
RECORD = os.environ.get('ONTOPOC_RECORD_GOLDEN') == '1'

P = {'start': 'order', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None}
S = one.SUM_AMOUNT
V = one.VALID_INCLUDE
CANCELLED = [{'id': 'orders.status_code=Cancelled', 'direction': 'include', 'basis': 'cancelled'}]
BY_STATUS = [{'id': f'orders.status_code={l}', 'direction': 'mention', 'basis': '状态'} for l in ('New', 'Paid', 'Shipped', 'Delivered', 'Cancelled', 'Refunded')]
BEFORE = lambda bound, field='order_date': [{'field': field, 'less_than': bound}]

ASKS = [   # (question, the model's reply, the same as main with the switch on)
    *((q, r, True) for q, r in one.DEMO_PAIRS),
    ('How many orders are there?', one.item({**P, 'list': {}}), False),
    ('How many orders are there?', one.item({**P, 'list': True}), False),
    ('有效订单有多少？', one.item({**P, 'list': {}}, V), False),
    ('Which orders were cancelled?', one.item({**P, 'where': [{'field': 'status_code', 'equals': 'Cancelled'}], 'list': {}}, CANCELLED), False),
    ('Which valid orders are there?', one.item({**P, 'list': {'properties': ['amount']}}, V), False),
    ('有效订单的总金额是多少？', one.item({**S, 'list': {'properties': ['amount']}}, V), False),
    ('What is order O0001?', one.item({'start': 'order', 'lookup': {'order_id': 'O0001'}}), False),
    ('What is order O0001?', one.item({**P, 'lookup': {'order_id': 'O0001'}}), False),
    ('What is valid order O0001?', one.item({'start': 'order', 'lookup': {'order_id': 'O0001'}}, V), False),
    ('How many orders before today?', one.item({**P, 'where': BEFORE('today')}), False),
    ('Which orders before today?', one.item({**P, 'where': BEFORE('today'), 'list': {}}), False),
    ('What is the total amount?', one.item({**S, 'list': {}}), True),
    ('有效订单的总金额是多少？', one.item({**S, 'list': {}}, V), True),
    ('各状态的订单金额', one.item({**S, 'group_by': ['status_code'], 'list': {}}, BY_STATUS), True),
    ('各状态的订单数', one.item({**P, 'group_by': ['status_code'], 'list': {}}, BY_STATUS), True),
    ('The two biggest statuses by amount', one.item({**S, 'group_by': ['status_code'], 'top': 2, 'order': 'largest', 'list': {}}, BY_STATUS), True),
    ('What share of orders is cancelled?', one.item({**P, 'share': {'field': 'status_code', 'equals': 'Cancelled'}, 'list': {}}), True),
    ('How many orders?', one.item({**P, 'list': None, 'lookup': None}), True),
    ('How many orders?', one.item({**P, 'list': False}), True),
    ('How many orders?', one.item({**P, 'list': [], 'lookup': {}}), True),
    ('How many orders before Today?', one.item({**P, 'where': BEFORE('Today ')}), True),
    ('How many orders before TODAY?', one.item({**P, 'where': BEFORE('TODAY')}), True),
    ('How many orders with an amount below today?', one.item({**P, 'where': BEFORE('today', 'amount')}), True),
]
QUERIES = [   # (text, params, the same as main with the switch on)
    *((t, None, True) for t in ('SELECT count(o) FROM (o:Order)', "SELECT count(o) FROM (o:Order) WHERE o.status_code = 'Cancelled'", 'SELECT sum(o.amount) FROM (o:Order)',
                                'SELECT o.status_code, count(o) FROM (o:Order) GROUP BY o.status_code', 'SELECT month(o.order_date), sum(o.amount) FROM (o:Order) GROUP BY month(o.order_date)',
                                'SELECT count(o) FROM (o:Order) WHERE o.amount BETWEEN 9 AND 1', 'SELECT count(o) FROM (o:Order) WHERE o.nope = 1', 'SELECT o FROM (o:Order)',
                                "SELECT count(o) FROM (o:Order) WHERE o.order_date < 'yesterday'", 'SELECT GRAPH FROM (o:Order) LIMIT 3',
                                'SELECT count(o) FROM (o:Order) WHERE o.status_code = 1 OR o.amount > 3',
                                "SELECT count(o) FROM (o:Order) WHERE o.order_date < 'today'", "SELECT count(o) FROM (o:Order) WHERE o.order_date < 'Today'",
                                "SELECT count(o) FROM (o:Order) WHERE o.order_date BETWEEN '2026-01-01' AND 'today'")),
    ('SELECT count(o) FROM (o:Order) WHERE o.order_date < $day', {'day': 'today'}, True),
    ('SELECT count(o) FROM (o:Order) WHERE o.order_date < today', None, False),
    ('SELECT LIST o FROM (o:Order)', None, False),
    ("SELECT ONE o FROM (o:Order) WHERE o.order_id = 'O0001'", None, False),
]
WRITTEN = lambda text, **more: json.dumps({'reasoning': 'test', 'query': text, **more}, ensure_ascii=False)
TEXT_ASKS = [   # (question, what the model writes, the same as main with the switch on)
    ('How many orders are there?', WRITTEN('SELECT count(o) FROM (o:Order)'), True),
    ('有效订单的总金额是多少？', WRITTEN('SELECT sum(o.amount) FROM (o:Order)', views=['Valid orders']), True),
    ('How many orders before today?', WRITTEN("SELECT count(o) FROM (o:Order) WHERE o.order_date < 'today'"), True),
    ('Today, how many orders are there?', WRITTEN("SELECT count(o) FROM (o:Order) WHERE o.order_date < 'Today'"), True),
    ('How many orders before today?', WRITTEN('SELECT count(o) FROM (o:Order) WHERE o.order_date < today'), False),
    ('Which orders are there?', WRITTEN('SELECT LIST o FROM (o:Order)'), False),
]


def blank_times(value):
    return json.loads(TIME.sub('<time>', json.dumps(value, ensure_ascii=False)))


def without_ids(body):
    return {k: v for k, v in (body or {}).items() if k not in ('id', 'asked_at')} if isinstance(body, dict) else body


def kept(folder, answer_id):
    conn = sqlite3.connect(folder / 'workspace.sqlite')
    try:
        row = conn.execute('SELECT question, status, answer_json, definitions_json, dataset_versions_json, types_json FROM qa_question WHERE id = ?', (answer_id,)).fetchone()
        return [row[0], row[1], *(json.loads(v) for v in row[2:])]
    finally:
        conn.close()


def headline(body):
    """A few fields to read when a digest differs."""
    body = body if isinstance(body, dict) else {}
    answer = body.get('answer') if isinstance(body.get('answer'), dict) else {}
    return {'status': body.get('status'), 'total': answer.get('total'), 'value': (answer.get('measure') or {}).get('value'), 'groups': len(answer.get('groups') or []) or None,
            'objects': 'objects' in answer, 'beside': [v.get('name') for v in (body.get('beside') or {}).get('views', [])], 'query_text': body.get('query_text'), 'today': 'today' in body}


def seen(status, body, record=None, reopened=None) -> dict:
    whole = blank_times({'status': status, 'body': without_ids(body), 'kept': record, 'reopen': reopened})
    return {**headline(body), 'digest': hashlib.sha256(json.dumps(whole, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}


def walk(flag) -> list[dict]:
    """Every case asked on a fresh seeded demo, as main would be read with `flag` (None: the code on the path is main's, which has no switch)."""
    one.setUpModule()
    out = []
    try:
        with (mock.patch.object(workspace_questions, 'ROW_ANSWERS', flag) if flag is not None else nullcontext()), Seeded() as demo:
            demo.model.__class__ = one.Scripted
            for who_name, who in (('guest', a_guest(demo.base)), ('admin_en', demo.admin('en'))):
                for question, reply, _ in ASKS:
                    demo.model.replies = [reply]
                    status, body = who.call('POST', '/api/workspace/ask', {'question': question})
                    answer_id = body.get('id') if status == 200 else None
                    record, reopened = (kept(demo.folder, answer_id), list(who.call('GET', f'/api/workspace/ask/{answer_id}'))) if answer_id else (None, None)
                    if reopened:
                        reopened[1] = without_ids(reopened[1])
                    out.append({'who': who_name, 'ask': question, 'reply': reply, **seen(status, body, record, reopened)})
                for text, params, _ in QUERIES:
                    status, body = who.call('POST', '/api/workspace/query', {'text': text, **({'params': params} if params else {})})
                    out.append({'who': who_name, 'query': text, 'params': params, **seen(status, body)})
                for question, written, _ in TEXT_ASKS:
                    demo.model.replies = [written]
                    status, body = who.call('POST', '/api/workspace/ask', {'question': question, 'writes': 'query'})
                    answer_id = body.get('id') if status == 200 else None
                    record, reopened = (kept(demo.folder, answer_id), list(who.call('GET', f'/api/workspace/ask/{answer_id}'))) if answer_id else (None, None)
                    if reopened:
                        reopened[1] = without_ids(reopened[1])
                    out.append({'who': who_name, 'ask': question, 'written': written, **seen(status, body, record, reopened)})
    finally:
        one.tearDownModule()
    return out


def same_on() -> list[bool]:
    """Which cases, in walk order, the switch on must answer as main."""
    return [same for _ in range(2) for same in [*(s for *_, s in ASKS), *(s for *_, s in QUERIES), *(s for *_, s in TEXT_ASKS)]]


class AgainstMain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if RECORD and hasattr(workspace_questions, 'ROW_ANSWERS'):
            raise unittest.SkipTest('the record is made on main only')
        if RECORD:   # on main: what it gives, kept for the tests below
            GOLDEN.parent.mkdir(exist_ok=True)
            GOLDEN.write_text(json.dumps(walk(None), ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        cls.main = json.loads(GOLDEN.read_text(encoding='utf-8'))

    def setUp(self):
        if RECORD:
            self.skipTest('recorded')

    def compare(self, got, which):
        self.assertEqual(len(got), len(self.main))
        for now, then, wanted in zip(got, self.main, which):
            if not wanted:
                continue
            with self.subTest(who=now['who'], case=now.get('ask') or now.get('query'), reply=json.dumps(now.get('reply') or now.get('written') or now.get('params'), ensure_ascii=False)[:120]):
                self.assertEqual({k: v for k, v in now.items() if k != 'digest'}, {k: v for k, v in then.items() if k != 'digest'})
                self.assertEqual(now['digest'], then['digest'])

    def test_switched_off_every_answer_kept_record_and_reopened_answer_is_mains_also_for_replies_with_list_lookup_or_today(self):
        self.compare(walk(False), [True] * len(self.main))

    def test_switched_on_every_answer_that_asks_for_no_objects_and_writes_no_bare_today_is_mains(self):
        which = same_on()
        self.compare(walk(True), which)
        self.assertGreaterEqual(sum(which), 2 * (len(one.DEMO_PAIRS) + 12))


if __name__ == '__main__':
    unittest.main()
