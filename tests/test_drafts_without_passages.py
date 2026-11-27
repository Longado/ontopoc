"""A draft and its refusals when no passage goes to the model are exactly what codex/oag-action-drafts 08b4d96e gives (ops/cards/doc-answers.md, "Ruling
after the merge's acceptance", item 3). The golden file is recorded from 08b4d96e's code with ONTOPOC_RECORD_GOLDEN=1, in a scratch worktree of that commit
(it has no documents); here every case is asked again with no document, and with a confirmed document whose words the questions do not share."""
import base64
import hashlib
import json
import os
import unittest
from pathlib import Path

from ontology_poc_generator import ask_budget, mcp_server
from tests.test_action_drafts_main import DELIVERED, IN_PRODUCTION, Model, Workspace, blank_times, draft, kept, without_ids

GOLDEN = Path(__file__).parent / 'golden' / 'drafts_without_passages.json'
RECORD = os.environ.get('ONTOPOC_RECORD_GOLDEN') == '1'
MK = 'ZZMK违约方不需要支付违约金'   # a sentence the model wrote, put in one field at a time
ELSEWHERE = '# 仓库盘点\n\n每季度末盘点一次库存，盘点表由仓管员签字。\n'   # shares no term with the questions below
CHANGE = f'把订单 {IN_PRODUCTION} 标成已交付'
CASES = [   # (label, question, the model's reply): the reviewer's probe, a marker in each field
    ('action name', CHANGE, {'reasoning': 'r', 'query': {'action': {'name': MK, 'key': {'订单号': IN_PRODUCTION}, 'values': {'状态码': '0'}, 'reason': 'x'}}}),
    ('key value', CHANGE, draft('改订单状态', {'订单号': MK}, {'状态码': '0'}, 'x')),
    ('value', CHANGE, draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': MK}, 'x')),
    ('key column', CHANGE, draft('改订单状态', {MK: IN_PRODUCTION}, {'状态码': '0'}, 'x')),
    ('value column', CHANGE, draft('改订单状态', {'订单号': IN_PRODUCTION}, {MK: '0'}, 'x')),
    ('type', f'把订单 {IN_PRODUCTION} 的客户改成 KH002', {'reasoning': 'r', 'query': {'action': {'name': None, 'type': MK}}}),
    ('condition', f'把订单 {DELIVERED} 标成已交付', draft('改订单状态', {'订单号': DELIVERED}, {'状态码': '0'}, 'x', reasoning=MK)),
    ('draft, reason', CHANGE, draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}, MK)),
    ('draft, reasoning', CHANGE, draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}, 'x', reasoning=MK)),
]


def load_tests(loader, standard, pattern):   # not the tests of the Workspace it borrows
    return loader.loadTestsFromTestCase(AsOnTheDraftsBranch)


class Session:
    def __init__(self, body):
        self.body = body

    def request(self, path, payload=None):
        return self.body


def walk(document: bool) -> list[dict]:
    """Every case asked by Ann on a fresh workspace (orders, the drafts' confirmed actions; with `document`, a confirmed document no question matches)."""
    out = []
    limits = (ask_budget.PERSON_LIMIT, ask_budget.TOKEN_LIMIT)
    ask_budget.PERSON_LIMIT = ask_budget.TOKEN_LIMIT = 10000
    case = Workspace()
    case.setUp()
    model = Model()
    try:
        with case.service(gateway=model) as (base, folder):
            team = case.setup(base, 'some')
            ann = team['ann']
            if document:
                status, body = ann.post('/api/workspace/documents/upload', {'filename': '仓库盘点.md', 'content_base64': base64.b64encode(ELSEWHERE.encode()).decode()})
                assert status == 200, body
                assert team['bob'].post('/api/workspace/documents/confirm', {'id': body['id'], 'version': body['version']})[0] == 200
            for label, question, reply in CASES:
                model.replies = [reply]
                status, body = ann.post('/api/workspace/ask', {'question': question})
                assert status == 200, body
                assert not model.requests[-1].get('documents'), label   # no passage went to the model
                reopened = without_ids(ann.get(f'/api/workspace/ask/{body["id"]}')[1])
                whole = blank_times({'body': without_ids(body), 'kept': kept(folder, body['id']), 'reopen': reopened, 'mcp': without_ids(mcp_server.ask(Session(body), {'question': question}))})
                out.append({'case': label, 'status': body['status'], 'refusal': (body.get('refusal') or {}).get('kind'), 'marker': MK in json.dumps(whole, ensure_ascii=False),
                            'digest': hashlib.sha256(json.dumps(whole, ensure_ascii=False, sort_keys=True).encode()).hexdigest()})
    finally:
        case.doCleanups()
        ask_budget.PERSON_LIMIT, ask_budget.TOKEN_LIMIT = limits
    return out


class AsOnTheDraftsBranch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if RECORD:
            from importlib.util import find_spec
            if find_spec('ontology_poc_generator.document_answers') is not None:
                raise unittest.SkipTest('the record is made on 08b4d96e only')
            GOLDEN.write_text(json.dumps(walk(False), ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        cls.then = json.loads(GOLDEN.read_text(encoding='utf-8'))

    def test_with_no_passage_sent_every_draft_and_refusal_is_as_on_08b4d96e(self):
        if RECORD:
            self.skipTest('recorded')
        self.assertTrue(any(c['marker'] for c in self.then))   # on that branch the model's words did come back: what this file holds is not empty of them
        for document in (False, True):
            self.assertEqual(walk(document), self.then, f'document={document}')


if __name__ == '__main__':
    unittest.main()
