"""Action drafts (ops/cards/oag-action-drafts.md, rule 8) held against main itself, not against the same code with the switch the other way.

golden/action_drafts_main.json is what main gave (the code of a0de22fe, before action drafts), on the planted orders with confirmed actions, to two builders
(Ann in Chinese and in English, Carl) and a viewer (Vera), for questions whose scripted replies are a count, a draft of an action (edit, create, delete, one
the asker may not submit, one that is not confirmed, one named by the question), "no action can do this" and a miss; each as the response, the record kept for
it and the answer reopened. Times are blanked; the rest is kept as a digest beside a few fields to read. It is walked twice on fresh workspaces:
- phase "none": the only confirmed action may be submitted by Bob alone, and 改订单状态 is put forward but not confirmed: nobody who asks has a confirmed action
  they may submit;
- phase "some": 改订单状态, 新建订单 and 删除取消的订单 are confirmed, open to every builder; Vera, a viewer, may submit none.

- Switch off (action_drafts.DRAFTS = False): every case is main's, byte for byte.
- Switch on: every case of phase "none", every case of the viewer, and every reply that drafts nothing (a count, a miss) is main's, byte for byte.

To record it again, on a checkout of the base commit with this file copied into its tests folder: ONTOPOC_RECORD_GOLDEN=1 python -m unittest
tests.test_action_drafts_main (the file is then written next to that copy; copy it back here). Only when main itself changes these answers."""
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from ontology_poc_generator import ask_budget
from ontology_poc_generator.recognition import ModelCompletion
from tests.test_action_kinds import DROP_ORDER, NEW_ORDER
from tests.test_object_types import ORDER_WITH_CUSTOMER, ORDERS, STATUS_ACTION, TABLES, ActionTests

GOLDEN = Path(__file__).parent / 'golden' / 'action_drafts_main.json'
TIME = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?')
RECORD = os.environ.get('ONTOPOC_RECORD_GOLDEN') == '1'

IN_PRODUCTION = next(r for r in ORDERS if r['状态码'] == '1')['订单号']   # DD20260003
DELIVERED = next(r for r in ORDERS if r['状态码'] == '0')['订单号']
CANCELLED = next(r for r in ORDERS if r['状态码'] == '2')['订单号']
FRESH = 'DD29990001'
BOB_ONLY = {'name': '改金额', 'type': 'order', 'properties': ['金额'], 'description': '补差价'}   # its submitters are set to Bob when it is made


def draft(name, key, values=None, reason='客户来电', reasoning='这是要改数据'):
    """The model's reply that drafts an action."""
    return {'reasoning': reasoning, 'query': {'action': {'name': name, 'key': key, 'values': values or {}, 'reason': reason}}}


COUNT = {'reasoning': 'test', 'query': {'start': 'order', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None}}
NONE_CAN = {'reasoning': '没有行为能改客户编号', 'query': {'action': {'name': None, 'type': 'order'}}}
MISS = {'reasoning': '本体里没有', 'query': None, 'missing': 'ontology'}
ASKS = [   # (question, the model's reply, a reply that drafts nothing: main's with the switch on in either phase)
    ('订单有多少？', COUNT, True),
    (f'把订单 {IN_PRODUCTION} 标成已交付', draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}), False),
    (f'用改订单状态把订单 {IN_PRODUCTION} 标成已交付', draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}), False),
    (f'把订单 {DELIVERED} 标成已交付', draft('改订单状态', {'订单号': DELIVERED}, {'状态码': '0'}), False),
    (f'把订单 {IN_PRODUCTION} 的金额改成 5', draft('改金额', {'订单号': IN_PRODUCTION}, {'金额': '5'}), False),
    (f'新建订单 {FRESH}，金额 1200，客户 KH001', draft('新建订单', {'订单号': FRESH}, {'金额': '1200', '状态码': '1', '客户编号': 'KH001'}, '电话下单'), False),
    (f'删掉订单 {CANCELLED}', draft('删除取消的订单', {'订单号': CANCELLED}, {}, '客户撤单'), False),
    (f'把订单 {IN_PRODUCTION} 的客户改成 KH002', NONE_CAN, False),
    ('天气怎么样？', MISS, True),
]


def load_tests(loader, standard, pattern):   # Workspace lends its helpers; its own tests are run where it is defined
    return loader.loadTestsFromTestCase(AgainstMain)


class Model:
    """Replies with what it is given (a dict is the item for the question asked), and keeps every system prompt and request it was sent."""

    def __init__(self):
        self.replies, self.requests, self.systems = [], [], []

    def complete_json(self, *, system_prompt, user_prompt, timeout_seconds=None):
        request = json.loads(user_prompt)
        self.requests.append(request)
        self.systems.append(system_prompt)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, str):
            return ModelCompletion('test', 'test-model', reply)
        return ModelCompletion('test', 'test-model', json.dumps({'questions': [{'question': request.get('asked'), **reply}]}, ensure_ascii=False))


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


def seen(status, body, record=None, reopened=None) -> dict:
    whole = blank_times({'status': status, 'body': without_ids(body), 'kept': record, 'reopen': reopened})
    body = body if isinstance(body, dict) else {}
    return {'status': body.get('status'), 'reason': body.get('reason'), 'error': body.get('error'), 'draft': 'draft' in body,
            'digest': hashlib.sha256(json.dumps(whole, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}


class Workspace(ActionTests):
    """The planted orders, Order confirmed (with 客户编号), and the actions of a phase; Ann, Bob and Carl build, Vera views."""

    def runTest(self):   # used for its helpers only
        pass

    def setup(self, base, phase):
        team = self.people(base, 'ann', 'bob', 'carl', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        self.assertEqual(team['ann'].post('/api/workspace/types', ORDER_WITH_CUSTOMER)[0], 200)
        for column in ('状态码', None):
            shown = team['bob'].get('/api/workspace/types/order')[1]
            shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
            self.assertEqual(team['bob'].post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})[0], 200)
        bob = self.user_id(team['admin'], 'bob')
        self.confirmed_action(team, {**BOB_ONLY, 'submitters': [bob]})
        if phase == 'none':
            self.assertEqual(team['ann'].post('/api/workspace/actions', STATUS_ACTION)[0], 200)   # put forward, not confirmed
        else:
            for action in (STATUS_ACTION, NEW_ORDER, DROP_ORDER):
                self.confirmed_action(team, action)
        return team

    @staticmethod
    def user_id(admin, username):
        return next(u['id'] for u in admin.get('/api/users')[1]['users'] if u['username'] == username)


def _switch(flag):
    if flag is None:
        return nullcontext()
    from ontology_poc_generator import action_drafts
    return mock.patch.object(action_drafts, 'DRAFTS', flag)


def walk(flag) -> list[dict]:
    """Every case asked on a fresh workspace of each phase, as main would be read with `flag` (None: the code on the path is main's, which has no switch)."""
    out = []
    kept_limits = (ask_budget.PERSON_LIMIT, ask_budget.TOKEN_LIMIT)
    ask_budget.PERSON_LIMIT = ask_budget.TOKEN_LIMIT = 10000
    try:
        for phase in ('none', 'some'):
            case = Workspace()
            case.setUp()
            model = Model()
            try:
                with _switch(flag), case.service(gateway=model) as (base, folder):
                    team = case.setup(base, phase)
                    for who_name, who, headers in (('ann', team['ann'], None), ('ann_en', team['ann'], {'Accept-Language': 'en'}), ('carl', team['carl'], None),
                                                   ('vera', team['vera'], None)):
                        for question, reply, _ in ASKS:
                            model.replies = [reply]
                            status, body = who.call('POST', '/api/workspace/ask', {'question': question}, headers=headers)
                            answer_id = body.get('id') if status == 200 else None
                            record = kept(folder, answer_id) if answer_id else None
                            reopened = list(who.call('GET', f'/api/workspace/ask/{answer_id}', headers=headers)) if answer_id else None
                            if reopened:
                                reopened[1] = without_ids(reopened[1])
                            out.append({'phase': phase, 'who': who_name, 'ask': question, 'reply': reply, **seen(status, body, record, reopened)})
            finally:
                case.doCleanups()
    finally:
        ask_budget.PERSON_LIMIT, ask_budget.TOKEN_LIMIT = kept_limits
    return out


def same_on() -> list[bool]:
    """Which cases, in walk order, the switch on must answer as main."""
    return [phase == 'none' or who == 'vera' or plain for phase in ('none', 'some') for who in ('ann', 'ann_en', 'carl', 'vera') for *_, plain in ASKS]


class AgainstMain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        drafts = importlib.util.find_spec('ontology_poc_generator.action_drafts') is not None
        if RECORD and drafts:
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
            with self.subTest(phase=now['phase'], who=now['who'], case=now['ask']):
                self.assertEqual({k: v for k, v in now.items() if k != 'digest'}, {k: v for k, v in then.items() if k != 'digest'})
                self.assertEqual(now['digest'], then['digest'])

    def test_switched_off_every_answer_kept_record_and_reopened_answer_is_mains(self):
        self.compare(walk(False), [True] * len(self.main))

    def test_switched_on_with_no_confirmed_action_the_asker_may_submit_and_for_every_reply_that_drafts_nothing_it_is_mains(self):
        which = same_on()
        got = walk(True)
        self.compare(got, which)
        self.assertGreaterEqual(sum(which), len(ASKS) * 4 + 2 * 3 + len(ASKS))
        self.assertTrue(any(g['draft'] for g in got))   # and with the switch on, a builder who may submit one is given drafts


if __name__ == '__main__':
    unittest.main()
