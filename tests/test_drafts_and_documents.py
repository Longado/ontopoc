"""Action drafts and answers from documents in one workspace (ops/cards/doc-answers.md, "Merging action drafts in"): a confirmed action Ann may submit and a
confirmed document she may read, with a scripted model. One reply is one kind, a draft (or its refusal) first, then a data query, then a document answer; once
passages were sent, a sentence of the model's reaches the person only under a draft whose action and values code checked, never under a refusal."""
import base64
import json
import sqlite3
import unittest

from ontology_poc_generator import action_drafts, document_answers, mcp_server
from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
from tests.test_action_drafts import DraftTests
from tests.test_action_drafts_main import COUNT, DELIVERED, IN_PRODUCTION, NONE_CAN, draft

RULE = '订单交付规则：订单标成已交付之前，要有客户签收的回单。'
DOCUMENT = f'# 订单交付规则\n\n{RULE}\n\n退货的订单不能再标成已交付。\n'
MARK = 'ZZREASONING'   # the model's reasoning, which must reach nobody once passages were sent and nothing was drafted
WHY = 'ZZWHY'   # the reason the model wrote inside its draft


def load_tests(loader, standard, pattern):
    return unittest.TestSuite(Together(name) for name in vars(Together) if name.startswith('test_'))


def quotes(request, quote=RULE):
    passage = next(p for p in request['documents'] if quote in p['text'])
    return {'quotes': [{'passage': passage['id'], 'quote': quote}]}


class Replying:
    """The model: `reply(request)` gives the item for the question asked; keeps every request and system prompt."""

    def __init__(self):
        self.reply, self.requests, self.systems = None, [], []

    def complete_json(self, *, system_prompt, user_prompt, timeout_seconds=None):
        from ontology_poc_generator.recognition import ModelCompletion
        request = json.loads(user_prompt)
        self.requests.append(request)
        self.systems.append(system_prompt)
        return ModelCompletion('test', 'test-model', json.dumps({'questions': [{'question': request.get('asked'), **self.reply(request)}]}, ensure_ascii=False))


class Together(DraftTests):
    def started(self, phase='some', model=None):
        self.model = Replying()
        return self.service(gateway=self.model)

    def workspace(self, base):
        team = self.setup(base, 'some')
        status, body = team['ann'].post('/api/workspace/documents/upload', {'filename': '订单交付规则.md', 'content_base64': base64.b64encode(DOCUMENT.encode()).decode()})
        self.assertEqual(status, 200, body)
        status, body = team['bob'].post('/api/workspace/documents/confirm', {'id': body['id'], 'version': body['version']})
        self.assertEqual(status, 200, body)
        return team

    def asking(self, who, question, reply):
        """Ask over HTTP; the response, and the request the model got (which must carry both the actions and the passages)."""
        self.model.reply = reply
        status, body = who.post('/api/workspace/ask', {'question': question})
        self.assertEqual(status, 200, body)
        request = self.model.requests[-1]
        self.assertTrue(request.get('documents'), request)   # passages were sent
        self.assertTrue(request['ontology'].get('actions'), request)   # and actions were offered
        return body

    def kept_text(self, folder, answer_id):
        conn = sqlite3.connect(folder / 'workspace.sqlite')
        try:
            return conn.execute('SELECT answer_json FROM qa_question WHERE id = ?', (answer_id,)).fetchone()[0]
        finally:
            conn.close()

    def mcp(self, body):
        class Session:
            def request(self, path, payload=None):
                return body
        return mcp_server.ask(Session(), {'question': 'x'})

    # --- 1. a draft while passages were sent: the draft, no quote ---------------------------------------------------------------------------------------

    def test_a_draft_while_passages_were_sent_is_shown_with_no_quote(self):
        with self.started() as (base, folder):
            team = self.workspace(base)
            body = self.asking(team['ann'], f'把订单 {IN_PRODUCTION} 标成已交付', lambda r: draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}, '客户已签收'))
            self.assertEqual(body['status'], 'draft', body)
            self.assertNotIn('documents', body)
            self.assertNotIn(RULE, json.dumps(body, ensure_ascii=False))
            self.assertEqual(body['draft']['reason'], '客户已签收')   # under a draft code checked, the model's words stand
            reopened = team['ann'].get(f'/api/workspace/ask/{body["id"]}')[1]
            self.assertEqual((reopened['status'], reopened['draft']['current']), ('draft', {'状态码': '1'}))
            got = self.mcp(body)
            self.assertEqual((got['status'], got['draft']['submit']), ('draft', body['draft']['submit']))
            self.assertNotIn('documents', got)

    # --- 2. a draft refusal while passages were sent: the service's sentence, the model's reasoning nowhere ----------------------------------------------

    def test_a_draft_refusal_while_passages_were_sent_says_the_services_sentence_and_the_models_reasoning_appears_nowhere(self):
        with self.started() as (base, folder):
            team = self.workspace(base)
            self.assertEqual(team['ann'].post('/api/workspace/actions', {'name': '加急交付', 'type': 'order', 'properties': ['状态码'], 'description': '还没有人确认'})[0], 200)
            said = document_answers._unused()
            cases = [   # (question, reply, refusal kind, its check)
                (f'把订单 {IN_PRODUCTION} 的客户改成 KH002', {**NONE_CAN, 'reasoning': MARK}, 'no_action', None),
                (f'把订单 {DELIVERED} 标成已交付', draft('改订单状态', {'订单号': DELIVERED}, {'状态码': '0'}, WHY, reasoning=MARK), 'action_check', 'condition'),
                (f'把订单 {IN_PRODUCTION} 标成已交付', draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '9'}, WHY, reasoning=MARK), 'action_check', None),
                ('把订单都标成已交付', {'reasoning': MARK, 'query': {'action': f'{WHY} 改订单状态'}}, 'action_check', 'not_a_draft'),
                ('把订单都标成已交付', {'reasoning': MARK, 'query': {'action': [{'name': '改订单状态', 'reason': WHY}, {'name': '删除取消的订单'}]}}, 'action_check', 'one_draft'),
                (f'把订单 {IN_PRODUCTION} 标成已交付', {'reasoning': MARK, 'query': {'action': {'name': '改订单状态', 'key': {'订单号': IN_PRODUCTION}, 'values': {'状态码': '0'}, 'colour': WHY}}},
                 'action_check', 'not_a_draft'),
                (f'把订单 {IN_PRODUCTION} 交付', draft('加急交付', {'订单号': IN_PRODUCTION}, {'状态码': '0'}, WHY, reasoning=MARK), 'unsettled', None),
            ]
            for question, reply, kind, check in cases:
                with self.subTest(kind=kind, check=check):
                    body = self.asking(team['ann'], question, lambda r, reply=reply: {**reply, 'document_answer': quotes(r)})
                    self.assertEqual((body['status'], body['refusal']['kind']), ('refused', kind), body)
                    if check:
                        self.assertEqual(body['refusal']['check'], check)
                    self.assertTrue(body['reason'].endswith('\n' + said), body['reason'])
                    self.assertEqual(body['documents'], {'found': True, 'line': said})
                    reopened = team['ann'].get(f'/api/workspace/ask/{body["id"]}')[1]
                    self.assertEqual((reopened['status'], reopened['refusal']['kind'], reopened['refusal'].get('check')), ('refused', kind, body['refusal'].get('check')), reopened)
                    for where, text in (('response', json.dumps(body, ensure_ascii=False)), ('record', self.kept_text(folder, body['id'])),
                                        ('reopen', json.dumps(reopened, ensure_ascii=False)), ('mcp', json.dumps(self.mcp(body), ensure_ascii=False))):
                        self.assertNotIn(MARK, text, where)
                        self.assertNotIn(WHY, text, where)
                        self.assertNotIn(RULE, text, where)   # no quote either
            # without passages (a question no document speaks of), a refusal is as on the drafts' own branch: the model's reasoning stays where it was
            self.model.reply = lambda r: {**NONE_CAN, 'reasoning': MARK}
            body = team['ann'].post('/api/workspace/ask', {'question': '把 KH001 的编号换掉'})[1]
            self.assertFalse(self.model.requests[-1].get('documents'))
            self.assertEqual((body['refusal']['kind'], body['reasoning']), ('no_action', MARK), body)
            self.assertNotIn('documents', body)

    # --- round 2: the reviewer's probe, a marker in each field the model writes ---------------------------------------------------------------------------

    def test_a_draft_refusal_while_passages_were_sent_echoes_no_value_key_name_column_or_type_the_model_wrote(self):
        from unittest import mock
        from ontology_poc_generator import workspace_questions
        from tests.test_drafts_without_passages import CASES, MK
        with self.started() as (base, folder):
            team = self.workspace(base)
            expected = {   # case: (kind, check, the service's sentence, the ids code matched)
                'action name': ('action_check', 'action', '没有已确认的行为能做这个改动', []),
                'key value': ('action_check', 'object', '没有这个对象，或者你看不到它', ['objaction:改订单状态', 'objtype:order']),
                'value': ('action_check', 'value', '有一个值不合它的属性的类型或已确认的含义', ['objaction:改订单状态', 'objtype:order']),
                'key column': ('action_check', 'key', '没有用完整的主键指定是哪一个对象', ['objaction:改订单状态', 'objtype:order']),
                'value column': ('action_check', 'value', '有一个值不合它的属性的类型或已确认的含义', ['objaction:改订单状态', 'objtype:order']),
                'type': ('no_action', None, '没有已确认的行为能做这个改动', []),
                'condition': ('action_check', 'condition', '对象现在不满足「改订单状态」的条件', ['objaction:改订单状态', 'objtype:order']),
            }
            for label, question, reply in CASES:
                if label not in expected:
                    continue
                kind, check, said, matched = expected[label]
                with self.subTest(case=label):
                    body = self.asking(team['ann'], question, lambda r, reply=reply: {**reply, 'document_answer': quotes(r)})
                    self.assertEqual((body['status'], body['refusal']['kind'], body['refusal'].get('check')), ('refused', kind, check), body)
                    self.assertIn(said, body['reason'])
                    self.assertEqual(body['refusal'].get('matched'), matched)
                    self.assertIsNone(body['query'])
                    reopened = team['ann'].get(f'/api/workspace/ask/{body["id"]}')[1]
                    self.assertEqual(reopened['reason'], body['reason'])   # the fixed sentence, as kept
                    for where, text in (('response', json.dumps(body, ensure_ascii=False)), ('record', self.kept_text(folder, body['id'])),
                                        ('reopen', json.dumps(reopened, ensure_ascii=False)), ('mcp', json.dumps(self.mcp(body), ensure_ascii=False))):
                        self.assertNotIn(MK, text, where)
                        self.assertNotIn('ZZMK', text, where)
                    if matched:   # reopening checks the matched ids against what the asker may see now
                        seen = workspace_questions._may_see
                        with mock.patch.object(workspace_questions, '_may_see', lambda conn, user, e: e != 'objaction:改订单状态' and seen(conn, user, e)):
                            hidden = team['ann'].get(f'/api/workspace/ask/{body["id"]}')[1]
                        self.assertIn('withheld', hidden)
                        self.assertNotIn('改订单状态', hidden['reason'])

    # --- 3. a document answer while actions were offered: quotes only, no draft ---------------------------------------------------------------------------

    def test_a_document_answer_while_actions_were_offered_is_quotes_only(self):
        with self.started() as (base, folder):
            team = self.workspace(base)
            body = self.asking(team['ann'], '订单标成已交付之前要有什么？', lambda r: {'reasoning': MARK, 'query': None, 'missing': 'ontology', 'document_answer': quotes(r)})
            self.assertEqual(body['status'], 'from_documents', body)
            self.assertEqual([q['quote'] for q in body['documents']['quotes']], [RULE])
            self.assertNotIn('draft', body)
            self.assertNotIn(MARK, json.dumps(body, ensure_ascii=False))
            self.assertNotIn(MARK, self.kept_text(folder, body['id']))
            got = self.mcp(body)
            self.assertEqual((got['status'], got['documents']), ('from_documents', body['documents']))
            self.assertNotIn('draft', got)

    # --- 4. a reply with a draft and quotes: the draft only; a data query with quotes: the data answer -----------------------------------------------------

    def test_a_reply_carrying_a_draft_and_quotes_is_the_draft_only(self):
        with self.started() as (base, folder):
            team = self.workspace(base)
            body = self.asking(team['ann'], f'把订单 {IN_PRODUCTION} 标成已交付',
                               lambda r: {**draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}, '客户已签收'), 'missing': 'ontology', 'document_answer': quotes(r)})
            self.assertEqual(body['status'], 'draft', body)
            self.assertNotIn('documents', body)
            for text in (json.dumps(body, ensure_ascii=False), self.kept_text(folder, body['id']), json.dumps(team['ann'].get(f'/api/workspace/ask/{body["id"]}')[1], ensure_ascii=False)):
                self.assertNotIn(RULE, text)
                self.assertNotIn('document_answer', text)
            data = self.asking(team['ann'], '订单交付了多少？', lambda r: {**COUNT, 'document_answer': quotes(r)})
            self.assertEqual(data['status'], 'answered', data)   # a data query comes before a document answer, as before
            self.assertNotIn(RULE, json.dumps(data, ensure_ascii=False))

    # --- prompts: the rows addition, then the drafts', then the documents' ---------------------------------------------------------------------------------

    def test_with_both_the_prompt_is_the_rows_addition_then_the_drafts_then_the_documents(self):
        with self.started() as (base, folder):
            team = self.workspace(base)
            self.asking(team['ann'], f'把订单 {IN_PRODUCTION} 标成已交付', lambda r: draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}))
            from ontology_poc_generator.workspace_questions import ROWS_PROMPT, ROWS_PROMPT_VERSION
            self.assertEqual(self.model.systems[-1], QUESTION_SYSTEM_PROMPT + ROWS_PROMPT + action_drafts.PROMPT + document_answers.DOC_PROMPT)
            self.assertEqual(document_answers.asking({'passages': [{'id': '1-p1', 'document': 'x', 'text': 'x'}]}, action_drafts.prompt((ROWS_PROMPT_VERSION, ROWS_PROMPT)))['more'][0],
                             f'{ROWS_PROMPT_VERSION}+{action_drafts.PROMPT_VERSION}+{document_answers.DOC_PROMPT_VERSION}')


if __name__ == '__main__':
    unittest.main()
