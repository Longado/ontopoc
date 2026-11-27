"""Answers from confirmed documents (ops/cards/doc-answers.md) held against main itself: with no confirmed document the asker may read, every prompt, answer,
refusal, kept record and reopened answer is main's, byte for byte, for the same model reply.

golden/doc_answers_main.json is what the base of this branch (a0de22fe: lists and lookups, with main eaf0aaa merged in; no documents) gave on the seeded demo to a
guest (a viewer), to demo-admin in English and to demo-admin in Chinese, for:
- every question of the one-number tests with its scripted reply, and questions a document could answer with replies that write no query, that carry a
  `document_answer` (main reads none) and that carry both a query and a `document_answer`;
- written queries (POST /api/workspace/query) and questions answered by a written query (writes=query);
each as the response, the record kept for it and the answer reopened (`digest`), and what the model was sent for it, system prompt and request (`told`).

Walked again on this code with:
- no document at all: everything is main's, for everyone;
- a document a builder put forward and nobody confirmed (it waits): the guest gets main's everything; a builder is sent main's prompt and request (nothing
  waiting goes to the model) and gets main's answer for every reply that has a data query. Only a reply with no query may differ: the refusal names the
  document that waits (card rule 6);
- a confirmed document marked builders only: for the guest it does not exist, so everything is main's; a builder may be sent its passages, and gets main's
  answer for every reply with a data query (card rule 5);
- a confirmed document while FTS5 is missing: the feature is off, everything is main's for everyone.

To record it again, on a checkout of the base with this file copied into its tests folder: ONTOPOC_RECORD_GOLDEN=1 python -m unittest tests.test_doc_answers_main
(the file is written next to that copy; copy it back here). Only when the base itself changes these answers."""
import base64
import hashlib
import importlib.util
import json
import os
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

from tests import test_one_number as one
from tests import test_which_ones_main as which
from tests.test_demo_mode import a_guest
from tests.test_demo_view_waits import Seeded

GOLDEN = Path(__file__).parent / 'golden' / 'doc_answers_main.json'
RECORD = os.environ.get('ONTOPOC_RECORD_GOLDEN') == '1'
ON_BASE = importlib.util.find_spec('ontology_poc_generator.document_answers') is None

CONTRACT = '''# 供货合同

第五条 逾期交货：供方逾期交货的，每逾期一日，按逾期部分货款的0.5%支付违约金；违约金总额不超过合同总价的10%。

第六条 订单与付款：每一笔订单的金额以订单为准，需方在收到货物后30日内支付货款。

Orders: the amount of each order is the amount on the order; payment is due within 30 days of delivery. Late delivery costs 0.5% of the late part per day.
'''
CLAIM = {'text': '逾期交货每逾期一日按逾期部分货款的0.5%支付违约金', 'quotes': [{'passage': 'p1', 'quote': '每逾期一日，按逾期部分货款的0.5%支付违约金'}]}
NO_QUERY = {'reasoning': 'test', 'query': None, 'missing': 'ontology'}
DOC_REPLY = {**NO_QUERY, 'document_answer': {'claims': [CLAIM]}}
ASKS = [   # (question, the model's reply)
    *((q, r) for q, r, _ in which.ASKS[:len(one.DEMO_PAIRS)]),
    ('逾期交货怎么罚？', NO_QUERY),
    ('逾期交货怎么罚？', {'reasoning': 'test', 'query': None, 'missing': 'query_language'}),
    ('逾期交货怎么罚？', DOC_REPLY),
    ('逾期交货怎么罚？', json.dumps({'document_answer': {'claims': [CLAIM]}}, ensure_ascii=False)),
    ('逾期交货怎么罚？', 'not json'),
    ('What does the contract say about late delivery?', NO_QUERY),
    ('What does the contract say about late delivery?', DOC_REPLY),
    ('How many orders are there?', {**one.item(which.P), 'document_answer': {'claims': [CLAIM]}}),
    ('订单的金额一共是多少？', {**one.item(one.SUM_AMOUNT), 'document_answer': {'claims': [CLAIM]}}),
    ('订单的金额一共是多少？', one.item(one.SUM_AMOUNT)),
]
QUERIES = [t for t, params, _ in which.QUERIES if params is None][:6]
TEXT_ASKS = [(q, w) for q, w, _ in which.TEXT_ASKS[:3]]


def has_query(reply) -> bool:
    """A reply with a data query: its answer is main's whatever documents there are (card rule 5)."""
    return isinstance(reply, dict) and isinstance(reply.get('query'), dict)


class Recording(one.Scripted):
    def complete_json(self, *, system_prompt, user_prompt, timeout_seconds=None):
        self.told.append(hashlib.sha256(json.dumps([system_prompt, json.loads(user_prompt)], ensure_ascii=False, sort_keys=True).encode()).hexdigest())
        return super().complete_json(system_prompt=system_prompt, user_prompt=user_prompt, timeout_seconds=timeout_seconds)


def upload(who, builders_only=False):
    status, body = who.call('POST', '/api/workspace/documents/upload', {'filename': '供货合同.md', 'content_base64': base64.b64encode(CONTRACT.encode()).decode(),
                                                                        'builders_only': builders_only})
    assert status == 200, body
    return body


def confirm(who, document):
    status, body = who.call('POST', '/api/workspace/documents/confirm', {'id': document['id'], 'version': document['version']})
    assert status == 200, body


SETUPS = {   # what is in the workspace before the walk, and what stands while it is walked
    'none': lambda demo: nullcontext(),
    'waiting': lambda demo: (upload(demo.admin()), nullcontext())[1],
    'builders_only': lambda demo: (confirm(demo.builder(), upload(demo.admin(), builders_only=True)), nullcontext())[1],
    'fts_off': lambda demo: (confirm(demo.builder(), upload(demo.admin())), mock.patch('ontology_poc_generator.document_answers.fts5_available', lambda: False))[1],
}


def walk(setup: str | None) -> list[dict]:
    one.setUpModule()
    out = []
    try:
        with Seeded() as demo:
            demo.model.__class__ = Recording
            demo.model.replies, demo.model.told = [NO_QUERY], []
            standing = SETUPS[setup](demo) if setup else nullcontext()
            with standing:
                for who_name, who in (('guest', a_guest(demo.base)), ('admin_en', demo.admin('en')), ('admin', demo.admin())):
                    for question, reply in ASKS:
                        out.append({'who': who_name, 'ask': question, 'reply': reply, **asked(demo, who, {'question': question}, reply)})
                    for text in QUERIES:
                        status, body = who.call('POST', '/api/workspace/query', {'text': text})
                        out.append({'who': who_name, 'query': text, **which.seen(status, body)})
                    for question, written in TEXT_ASKS:
                        out.append({'who': who_name, 'ask': question, 'written': written, **asked(demo, who, {'question': question, 'writes': 'query'}, written)})
    finally:
        one.tearDownModule()
    return out


def asked(demo, who, payload, reply) -> dict:
    demo.model.replies = [reply]
    before = len(demo.model.told)
    status, body = who.call('POST', '/api/workspace/ask', payload)
    answer_id = body.get('id') if status == 200 else None
    record, reopened = (which.kept(demo.folder, answer_id), list(who.call('GET', f'/api/workspace/ask/{answer_id}'))) if answer_id else (None, None)
    if reopened:
        reopened[1] = which.without_ids(reopened[1])
    return {**which.seen(status, body, record, reopened), 'told': demo.model.told[before:]}


class AgainstMain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if RECORD and not ON_BASE:
            raise unittest.SkipTest('the record is made on the base only')
        if RECORD:
            GOLDEN.parent.mkdir(exist_ok=True)
            GOLDEN.write_text(json.dumps(walk(None), ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        cls.main = json.loads(GOLDEN.read_text(encoding='utf-8'))

    def setUp(self):
        if RECORD:
            self.skipTest('recorded')

    def compare(self, got, answers, told):
        """`answers(case)`, `told(case)`: whether this case's answer (and kept record and reopened answer), and what the model was sent for it, must be main's."""
        self.assertEqual(len(got), len(self.main))
        compared = 0
        for now, then in zip(got, self.main):
            with self.subTest(who=now['who'], case=now.get('ask') or now.get('query'), reply=json.dumps(now.get('reply') or now.get('written'), ensure_ascii=False)[:120]):
                self.assertEqual((now['who'], now.get('ask'), now.get('query')), (then['who'], then.get('ask'), then.get('query')))
                if told(now):
                    self.assertEqual(now.get('told'), then.get('told'))
                if answers(now):
                    compared += 1
                    self.assertEqual({k: v for k, v in now.items() if k not in ('digest', 'told')}, {k: v for k, v in then.items() if k not in ('digest', 'told')})
                    self.assertEqual(now['digest'], then['digest'])
        return compared

    def test_with_no_document_everything_is_mains(self):
        self.assertEqual(self.compare(walk('none'), lambda c: True, lambda c: True), len(self.main))

    def test_with_fts5_missing_a_confirmed_document_changes_nothing(self):
        self.assertEqual(self.compare(walk('fts_off'), lambda c: True, lambda c: True), len(self.main))

    def test_a_document_that_waits_is_never_sent_and_changes_nothing_for_a_guest_or_for_a_data_question(self):
        guest_or_data = lambda c: c['who'] == 'guest' or 'reply' not in c or has_query(c['reply'])
        compared = self.compare(walk('waiting'), guest_or_data, lambda c: True)
        self.assertGreater(compared, len(self.main) // 2)

    def test_a_builders_only_document_does_not_exist_for_a_guest_and_changes_no_builders_data_answer(self):
        guest_or_data = lambda c: c['who'] == 'guest' or 'reply' not in c or has_query(c['reply'])
        compared = self.compare(walk('builders_only'), guest_or_data, lambda c: c['who'] == 'guest' or 'reply' not in c)
        self.assertGreater(compared, len(self.main) // 2)


if __name__ == '__main__':
    unittest.main()
