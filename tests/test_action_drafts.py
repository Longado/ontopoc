"""The assistant drafts an action (ops/cards/oag-action-drafts.md): a question that asks for a change gets a draft of a confirmed action, which the person submits
through the existing route and another builder approves. A scripted model writes the draft; code checks it with the same checks a submit makes, and writes
nothing. See tests/test_action_drafts_main.py for the switch held against main."""
import hashlib
import json
import sqlite3
import unittest
from unittest import mock
from urllib.parse import quote

from ontology_poc_generator import accounts, action_drafts, mcp_server, workspace_questions
from ontology_poc_generator.workspace_store import open_workspace
from tests.test_action_drafts_main import (CANCELLED, COUNT, DELIVERED, FRESH, IN_PRODUCTION, NONE_CAN, Model, Workspace, draft)
from tests.test_object_types import ORDERS

AMOUNT = {'name': '调金额', 'type': 'order', 'properties': ['金额'], 'description': '任何时候都能改金额'}
UNCONFIRMED = {'name': '加急改金额', 'type': 'order', 'properties': ['金额'], 'description': '还没有人确认'}
GUARDED = {'name': '锁定大单', 'type': 'order', 'properties': ['状态码'], 'description': '只给几张指定的大单',
           'conditions': [{'column': '订单号', 'op': 'in', 'value': [IN_PRODUCTION, 'DD20260004']}, {'column': '金额', 'op': 'gt', 'value': '45678'}]}
MAIN_ASK_DESCRIPTION = '4a6216ac04295dd8a7066479be26a70bcebff5735243d91da8e69637625c38db'   # sha256 of the ask tool's description at a0de22fe (main's)
PICK = {'name': '转客户', 'type': 'order', 'properties': ['客户编号'], 'choices': {'客户编号': {'type': 'order', 'column': '客户编号'}}, 'description': '换一个已有的客户'}
KH001_IN_PRODUCTION = next(r for r in ORDERS if r['客户编号'] == 'KH001' and r['状态码'] == '1')['订单号']   # DD20260136
HIDDEN_IN_PRODUCTION = next(r for r in ORDERS if r['客户编号'] != 'KH001' and r['状态码'] == '1')['订单号']
NOBODY = 'DD20269999'
ROW_VALUES = {str(r[c]) for r in ORDERS for c in ('订单号', '客户编号', '金额', '产品编号', '下单日期') if len(str(r[c])) >= 3}   # what a row holds and a code meaning does not


def load_tests(loader, standard, pattern):
    return unittest.TestSuite(DraftTests(name) for name in vars(DraftTests) if name.startswith('test_'))   # not the tests DraftTests inherits


def tables(path) -> dict:
    """Every table of the workspace file, each as its sorted rows."""
    conn = sqlite3.connect(path)
    try:
        names = [n for (n,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        return {n: sorted(map(repr, conn.execute(f'SELECT * FROM "{n}"').fetchall())) for n in names}
    finally:
        conn.close()


def records(path) -> list[dict]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute('SELECT * FROM action_record ORDER BY id')]
    finally:
        conn.close()


class DraftTests(Workspace):
    def runTest(self):
        pass

    def started(self, phase='some', model=None):
        """A service with the workspace of `phase` (test_action_drafts_main.Workspace.setup); the caller enters it."""
        self.model = model or Model()
        return self.service(gateway=self.model)

    def ask(self, who, question, reply, lang=None):
        self.model.replies = [reply]
        return who.call('POST', '/api/workspace/ask', {'question': question}, headers={'Accept-Language': lang} if lang else None)

    def ask_here(self, folder, username, question, reply):
        """workspace_questions.ask called in-process, keeping nothing: what asking alone does to the file."""
        self.model.replies = [reply]
        conn = open_workspace(folder / 'workspace.sqlite')
        try:
            user = next(u for u in accounts.list_users(conn) if u['username'] == username)
            return workspace_questions.ask(conn, self.model, accounts.get_user(conn, user['id']), question, keep=False)
        finally:
            conn.close()

    # --- a draft ------------------------------------------------------------------------------------------------------------------------------------------

    def test_an_edit_is_drafted_with_the_action_the_whole_key_the_values_the_reason_and_the_current_values_and_asking_writes_nothing(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            question = f'把订单 {IN_PRODUCTION} 标成已交付'
            before = tables(folder / 'workspace.sqlite')
            got = self.ask_here(folder, 'ann', question, draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}, reason='客户已签收'))
            self.assertEqual(tables(folder / 'workspace.sqlite'), before)   # every table, every row: nothing at all was written
            self.assertEqual(got['status'], 'draft', got)
            d = got['draft']
            self.assertEqual((d['action']['name'], d['action']['kind'], d['action']['type']), ('改订单状态', 'edit', 'order'))
            self.assertEqual((d['key'], d['params'], d['reason'], d['object']), ({'订单号': IN_PRODUCTION}, {'状态码': '0'}, '客户已签收', f'订单 {IN_PRODUCTION}'))
            self.assertEqual(d['current'], {'状态码': '1'})   # filled in by code, for the person
            self.assertEqual(d['asked'], {'状态码': '0'})
            self.assertEqual(d['submit'], {'action': '改订单状态', 'key': {'订单号': IN_PRODUCTION}, 'params': {'状态码': '0'}, 'reason': '客户已签收'})
            self.assertEqual([p['column'] for p in d['action']['parameters']], ['状态码'])   # the action's own form
            self.assertEqual(d['values'], {'状态码': '0'})   # what the form is prefilled with
            self.assertIn('生产中', d['current_text'])
            self.assertIn('已交付', d['asked_text'])
            self.assertEqual([x['id'] for x in got['definitions']][:2], ['objaction:改订单状态', 'objtype:order'])
            self.assertEqual(got['types'], [{'id': 'order', 'name': '订单'}])
            # over HTTP the asked question is kept, as every question is; nothing else changes but the hourly ask count
            before = tables(folder / 'workspace.sqlite')
            status, body = self.ask(team['ann'], question, draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '已交付'}))
            self.assertEqual((status, body['status']), (200, 'draft'), body)
            self.assertEqual(body['draft']['params'], {'状态码': '0'})   # a meaning written as its label is the one code that has it
            after = tables(folder / 'workspace.sqlite')
            changed = {n for n in after if after[n] != before.get(n)}
            self.assertLessEqual(changed, {'qa_question', 'sqlite_sequence', 'ask_budget', 'session'}, changed)
            self.assertEqual(len(after['qa_question']), len(before['qa_question']) + 1)
            self.assertEqual(records(folder / 'workspace.sqlite'), [])
            kept = json.loads(sqlite3.connect(folder / 'workspace.sqlite').execute('SELECT answer_json FROM qa_question WHERE id = ?', (body['id'],)).fetchone()[0])
            self.assertNotIn('current', kept['draft'])   # the object's values are not kept with the question
            self.assertEqual({'current', 'current_text', 'change_text'} & set(kept['draft']), set())
            status, again = team['ann'].get(f'/api/workspace/ask/{body["id"]}')
            self.assertEqual((status, again['status'], again['draft']['current']), (200, 'draft', {'状态码': '1'}), again)   # read again when it is reopened

    def test_a_create_and_a_delete_are_drafted_and_write_nothing(self):
        with self.started() as (base, folder):
            self.setup(base, 'some')
            before = tables(folder / 'workspace.sqlite')
            made = self.ask_here(folder, 'ann', f'新建订单 {FRESH}', draft('新建订单', {'订单号': FRESH}, {'金额': '1200', '状态码': '生产中', '客户编号': 'KH001'}, '电话下单'))
            dropped = self.ask_here(folder, 'ann', f'删掉订单 {CANCELLED}', draft('删除取消的订单', {'订单号': CANCELLED}, {}, '客户撤单'))
            self.assertEqual(tables(folder / 'workspace.sqlite'), before)
            self.assertEqual((made['status'], made['draft']['action']['kind']), ('draft', 'create'), made)
            self.assertEqual(made['draft']['current'], {})   # nothing there yet
            self.assertEqual(made['draft']['values'], {'订单号': FRESH, '金额': '1200', '状态码': '1', '客户编号': 'KH001'})   # the form asks for the key first
            self.assertEqual(made['draft']['submit'], {'action': '新建订单', 'key': {'订单号': FRESH}, 'params': {'金额': '1200', '状态码': '1', '客户编号': 'KH001'}, 'reason': '电话下单'})
            self.assertEqual((dropped['status'], dropped['draft']['action']['kind']), ('draft', 'delete'), dropped)
            row = next(r for r in ORDERS if r['订单号'] == CANCELLED)
            self.assertEqual(dropped['draft']['current']['金额'], row['金额'])   # what would be removed
            self.assertEqual(dropped['draft']['submit'], {'action': '删除取消的订单', 'key': {'订单号': CANCELLED}, 'params': {}, 'reason': '客户撤单'})
            no_reason = self.ask_here(folder, 'ann', f'删掉订单 {CANCELLED}', draft('删除取消的订单', {'订单号': CANCELLED}, {}, ''))
            self.assertEqual(no_reason['draft']['reason'], f'删掉订单 {CANCELLED}')   # no reason written: the question is the reason

    def test_submitting_a_draft_through_the_existing_route_makes_the_record_the_form_would(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            ann, bob = team['ann'], team['bob']
            cases = [(f'把订单 {IN_PRODUCTION} 标成已交付', draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}, '客户已签收')),
                     (f'新建订单 {FRESH}', draft('新建订单', {'订单号': FRESH}, {'金额': '1200', '状态码': '1', '客户编号': 'KH001'}, '电话下单')),
                     (f'删掉订单 {CANCELLED}', draft('删除取消的订单', {'订单号': CANCELLED}, {}, '客户撤单'))]
            for question, reply in cases:
                with self.subTest(question=question):
                    d = self.ask(ann, question, reply)[1]['draft']
                    status, by_draft = ann.post('/api/workspace/actions/submit', d['submit'])
                    self.assertEqual(status, 200, by_draft)
                    key = {c: d['values'][c] for c in d['key']} if d['action']['kind'] == 'create' else d['key']   # a create's key is in its form; else the object's
                    form = {'action': d['action']['id'], 'key': key, 'params': {p['column']: d['values'][p['column']] for p in d['action']['parameters'] if not p['key']}, 'reason': d['reason']}
                    status, by_form = ann.post('/api/workspace/actions/submit', form)   # what RunAction sends (actionModel.runPayload)
                    self.assertEqual(status, 200, by_form)
                    made = {r['id']: r for r in records(folder / 'workspace.sqlite')}
                    a, b = ({k: v for k, v in made[i].items() if k not in ('id', 'submitted_at')} for i in (by_draft['record'], by_form['record']))
                    self.assertEqual(a, b)
                    self.assertEqual(a['state'], 'pending')   # it waits for another builder, as today
                    self.assertEqual(bob.post('/api/workspace/actions/withdraw', {'id': by_draft['record']})[0], 403)   # only the submitter takes it back
                    self.assertEqual(ann.post('/api/workspace/actions/withdraw', {'id': by_form['record']})[0], 200)

    # --- refusals -------------------------------------------------------------------------------------------------------------------------------------------

    def test_each_failed_check_is_refused_in_the_words_a_submit_uses_and_nothing_is_logged(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            ann = team['ann']
            cases = [   # (the check, the draft the model writes, what the existing route is sent)
                ('condition', draft('改订单状态', {'订单号': DELIVERED}, {'状态码': '0'}), None),
                ('value', draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '9'}), None),
                ('nothing_to_change', draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '1'}), None),
                ('value', draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0', '金额': '5'}), None),
                ('key', draft('改订单状态', {'单号': IN_PRODUCTION}, {'状态码': '0'}), None),
                ('object', draft('改订单状态', {'订单号': NOBODY}, {'状态码': '0'}), None),
                ('key_taken', draft('新建订单', {'订单号': DELIVERED}, {'金额': '1200', '状态码': '1', '客户编号': 'KH001'}), None),
                ('value', draft('新建订单', {'订单号': FRESH}, {'金额': 'abc', '状态码': '1', '客户编号': 'KH001'}), None),
                ('condition', draft('删除取消的订单', {'订单号': IN_PRODUCTION}, {}, '清掉'), None),
                ('submitter', draft('改金额', {'订单号': IN_PRODUCTION}, {'金额': '5'}), None),
                ('action', draft('没有的行为', {'订单号': IN_PRODUCTION}, {'金额': '5'}), None),
            ]
            refused = []
            for check, reply, _ in cases:
                status, body = self.ask(ann, '把这张订单改一下', reply)
                self.assertEqual((status, body['status']), (200, 'refused'), body)
                self.assertEqual((body['refusal']['kind'], body['refusal']['check']), ('action_check', check), body['refusal'])
                self.assertNotIn('draft', body)
                refused.append(body)
            self.assertEqual(records(folder / 'workspace.sqlite'), [])
            conn = sqlite3.connect(folder / 'workspace.sqlite')
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM log WHERE change LIKE 'action_%'").fetchone()[0], 0)   # a refused draft is no refused submit
            conn.close()
            for (check, reply, _), body in zip(cases, refused):
                with self.subTest(check=check):
                    a = reply['query']['action']
                    status, said = ann.post('/api/workspace/actions/submit', {'action': a['name'], 'key': a['key'], 'params': a['values'], 'reason': a['reason']})
                    self.assertGreaterEqual(status, 400)
                    self.assertEqual(body['refusal']['said'], said['error'])   # the submit's own words
                    self.assertIn(said['error'], body['reason'])
            status, body = self.ask(ann, '把这张订单改一下', draft('改订单状态', {'订单号': DELIVERED}, {'状态码': '0'}), lang='en')
            self.assertTrue(body['reason'].startswith('Not drafted: The condition is not met'), body['reason'])

    def test_a_key_the_asker_may_not_read_is_answered_exactly_as_a_key_nobody_has(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            ann, admin = team['ann'], team['admin']
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH001', 'user_ids': [self.user_id(admin, 'ann')]}]})[0], 200)
            plain = lambda body, key: json.loads(json.dumps({k: v for k, v in body.items() if k not in ('id', 'asked_at')}, ensure_ascii=False).replace(key, '<key>'))
            for name, values, hidden in (('改订单状态', {'状态码': '0'}, HIDDEN_IN_PRODUCTION), ('新建订单', {'金额': '1200', '状态码': '1', '客户编号': 'KH001'}, DELIVERED)):
                with self.subTest(action=name):
                    seen = [plain(self.ask(ann, '改这张订单', draft(name, {'订单号': key}, values))[1], key) for key in (hidden, NOBODY)]
                    self.assertEqual(seen[0], seen[1])
            self.assertEqual(seen[0]['status'], 'draft')   # a create on a key nobody has is a draft; so is one on a key she may not read
            body = self.ask(ann, '改这张订单', draft('改订单状态', {'订单号': HIDDEN_IN_PRODUCTION}, {'状态码': '0'}))[1]
            self.assertEqual(body['refusal']['said'], '没有这个对象，或者你看不到它')
            mine = self.ask(ann, '改这张订单', draft('改订单状态', {'订单号': KH001_IN_PRODUCTION}, {'状态码': '0'}))[1]
            self.assertEqual(mine['status'], 'draft', mine)   # one the rule lets her read

    def test_a_viewer_gets_no_draft_and_the_model_is_told_no_action(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            before = tables(folder / 'workspace.sqlite')
            reply = draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'})
            got = self.ask_here(folder, 'vera', f'把订单 {IN_PRODUCTION} 标成已交付', reply)
            self.assertEqual(tables(folder / 'workspace.sqlite'), before)
            self.assertNotEqual(got['status'], 'draft')
            self.assertNotIn('draft', got)
            self.assertNotIn('actions', self.model.requests[-1]['ontology'])
            with mock.patch('ontology_poc_generator.action_drafts.DRAFTS', False):
                self.ask_here(folder, 'vera', f'把订单 {IN_PRODUCTION} 标成已交付', reply)
            self.assertEqual(self.model.systems[-2], self.model.systems[-1])   # the prompt a viewer gets is the one with no drafts at all
            self.assertEqual(self.model.requests[-2], self.model.requests[-1])
            status, body = self.ask(team['vera'], f'把订单 {IN_PRODUCTION} 标成已交付', reply)
            self.assertEqual(status, 200)
            self.assertNotIn('draft', body)
            self.assertIn(team['vera'].post('/api/workspace/actions/submit', {'action': '改订单状态', 'key': {'订单号': IN_PRODUCTION}, 'params': {'状态码': '0'}})[0], (403, 404))   # as a submit refuses her

    def test_the_model_is_told_only_the_confirmed_actions_the_asker_may_submit_and_never_a_row_value(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')   # 改订单状态, 新建订单, 删除取消的订单 for everyone; 改金额 for Bob alone
            self.confirmed_action(team, PICK)
            self.assertEqual(team['ann'].post('/api/workspace/actions', UNCONFIRMED)[0], 200)
            told = []
            for flag in (False, True):
                with mock.patch('ontology_poc_generator.action_drafts.DRAFTS', flag):
                    self.ask(team['ann'], '订单有多少？', COUNT)
                told.append((self.model.systems[-1], self.model.requests[-1]))
            (off, off_request), (on, on_request) = told
            actions = on_request['ontology'].pop('actions')
            self.assertEqual(on_request, off_request)   # the request differs by the actions alone
            self.assertTrue(on.startswith(off))   # every word of the prompt as it was, then the addition
            self.assertLessEqual(len(on) - len(off), 1600)
            self.assertEqual(sorted(a['name'] for a in actions), sorted(['改订单状态', '新建订单', '删除取消的订单', '转客户']))   # not 改金额 (Bob's), not 加急改金额 (not confirmed)
            sent = json.dumps(actions, ensure_ascii=False)
            self.assertEqual([v for v in ROW_VALUES if v in sent], [])   # no value of a row: not the choices of 转客户 either
            status_action = next(a for a in actions if a['name'] == '改订单状态')
            self.assertEqual(status_action['key'], ['订单号'])
            self.assertEqual(status_action['properties'][0]['meanings'], {'0': '已交付', '1': '生产中', '2': '已取消'})
            self.assertIn('生产中', status_action['conditions'])
            self.assertIn('客户编号', next(a for a in actions if a['name'] == '转客户')['properties'][0]['picked_from'])
            # and in every request a draft makes, the actions carry no row value
            self.ask(team['ann'], f'把订单 {IN_PRODUCTION} 标成已交付', draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}))
            self.ask(team['bob'], f'把订单 {IN_PRODUCTION} 的金额改成 5', draft('改金额', {'订单号': IN_PRODUCTION}, {'金额': '5'}))
            for request in self.model.requests:
                self.assertEqual([v for v in ROW_VALUES if v in json.dumps(request['ontology'].get('actions', []), ensure_ascii=False)], [])

    def test_an_action_that_is_not_confirmed_is_refused_naming_it_and_who_can_confirm_it(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            ann = team['ann']
            self.confirmed_action(team, AMOUNT)
            self.assertEqual(ann.post('/api/workspace/actions', UNCONFIRMED)[0], 200)
            asked = len(self.model.requests)
            status, body = self.ask(ann, f'用加急改金额把订单 {IN_PRODUCTION} 的金额改成 5', draft('加急改金额', {'订单号': IN_PRODUCTION}, {'金额': '5'}))
            self.assertEqual((status, body['status'], body['refusal']['kind']), (200, 'refused', 'unsettled'), body)
            self.assertEqual(len(self.model.requests), asked)   # refused before the model is asked
            line = body['refusal']['definitions'][0]
            self.assertEqual((line['kind'], line['name'], line['id']), ('action', '加急改金额', 'objaction:加急改金额'))
            self.assertIn('Bob', line['who_can_confirm'])
            self.assertIn('加急改金额', body['reason'])
            status, body = self.ask(ann, f'把订单 {IN_PRODUCTION} 的金额改成 5', draft('加急改金额', {'订单号': IN_PRODUCTION}, {'金额': '5'}))   # the model names it
            self.assertEqual((body['status'], body['refusal']['kind'], body['refusal']['definitions'][0]['name']), ('refused', 'unsettled', '加急改金额'), body)
            # one that needs another look: its meanings changed
            self.assertEqual(ann.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': [{'value': '1', 'label': '制造中'}]})[0], 200)
            for column in ('状态码', None):   # Bob confirms the new meaning and the type again; the action itself still needs another look
                shown = team['bob'].get('/api/workspace/types/order')[1]
                shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
                self.assertEqual(team['bob'].post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})[0], 200)
            shown = team['bob'].get('/api/workspace/actions/' + quote(AMOUNT['name']))[1]   # every action on the type needs another look now; Bob confirms 调金额 again
            self.assertEqual(team['bob'].post('/api/workspace/actions/confirm', {'id': AMOUNT['name'], 'version': shown['version']})[0], 200)
            status, body = self.ask(ann, f'把订单 {IN_PRODUCTION} 标成已交付', draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}))
            self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'unsettled'), body)
            self.assertEqual((body['refusal']['definitions'][-1]['name'], body['refusal']['definitions'][-1]['state']), ('改订单状态', 'needs_look'))
            self.assertEqual(records(folder / 'workspace.sqlite'), [])

    def test_a_change_no_confirmed_action_can_make_is_answered_with_the_actions_the_person_may_submit(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            status, body = self.ask(team['ann'], f'把订单 {IN_PRODUCTION} 的客户改成 KH002', NONE_CAN)
            self.assertEqual((status, body['status'], body['refusal']['kind']), (200, 'refused', 'no_action'), body)
            self.assertEqual([a['name'] for a in body['refusal']['actions']], ['删除取消的订单', '改订单状态', '新建订单'])   # not Bob's 改金额
            self.assertIn('改订单状态', body['reason'])
            self.assertNotIn('draft', body)
            status, body = self.ask(team['bob'], '把客户 KH002 的名字改一下', {'reasoning': '没有客户类型', 'query': {'action': {'name': None, 'type': 'customer'}}}, lang='en')
            self.assertEqual(body['refusal']['kind'], 'no_action', body)
            self.assertIn('改金额', [a['name'] for a in body['refusal']['actions']])   # no such type in scope: every action they may submit
            self.assertTrue(body['reason'].startswith('No confirmed action'), body['reason'])
            self.assertEqual(records(folder / 'workspace.sqlite'), [])

    def test_one_draft_per_question(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            two = json.dumps({'questions': [{'question': 'x', **draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'})},
                                            {'question': 'y', **draft('删除取消的订单', {'订单号': CANCELLED}, {}, '撤单')}]}, ensure_ascii=False)
            asked = len(self.model.requests)
            status, body = self.ask(team['ann'], f'把订单 {IN_PRODUCTION} 标成已交付，再删掉 {CANCELLED}', two)
            self.assertEqual((status, body['status'], body['draft']['action']['name']), (200, 'draft', '改订单状态'), body)
            self.assertEqual(len(self.model.requests), asked + 1)   # one call, one draft, no chain of steps
            chained = draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'})
            chained['query']['action']['then'] = {'name': '删除取消的订单', 'key': {'订单号': CANCELLED}}
            status, body = self.ask(team['ann'], '先改再删', chained)
            self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'action_check'), body)
            self.assertEqual(body['refusal']['check'], 'one_draft')

    def test_mcp_ask_returns_the_draft_and_stays_a_read_tool(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            body = self.ask(team['ann'], f'把订单 {IN_PRODUCTION} 标成已交付', draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}))[1]

            class Session:
                def request(self, path, payload=None):
                    assert path == '/api/workspace/ask'
                    return body
            got = mcp_server.ask(Session(), {'question': 'x'})
            self.assertEqual(got['draft'], body['draft'])
            self.assertEqual(got['status'], 'draft')
            self.assertIn('ask', mcp_server.READ_TOOLS)
            self.assertFalse(any('submit' in t for t in mcp_server.READ_TOOLS))

    # --- round 2 (ops/inbox/leader.md, 2026-11-26) ----------------------------------------------------------------------------------------------------------

    def kept_answer(self, folder, answer_id) -> str:
        conn = sqlite3.connect(folder / 'workspace.sqlite')
        try:
            return conn.execute('SELECT answer_json FROM qa_question WHERE id = ?', (answer_id,)).fetchone()[0]
        finally:
            conn.close()

    def test_a_kept_refusal_keeps_no_value_of_the_object_and_is_checked_again_when_reopened(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            ann, admin = team['ann'], team['admin']
            status, body = self.ask(ann, f'删掉订单 {IN_PRODUCTION}', draft('删除取消的订单', {'订单号': IN_PRODUCTION}, {}, '客户撤单'))   # DD20260003, of KH011, in production
            self.assertEqual((body['status'], body['refusal']['check']), ('refused', 'condition'), body)
            self.assertIn('现在是“生产中”', body['reason'])   # said to the person who asked, now
            self.assertNotIn('生产中”', self.kept_answer(folder, body['id']))   # never kept
            reopened = ann.get(f'/api/workspace/ask/{body["id"]}')[1]
            self.assertIn('现在是“生产中”', reopened['reason'])   # checked again on reopening
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH001', 'user_ids': [self.user_id(admin, 'ann')]}]})[0], 200)
            reopened = ann.get(f'/api/workspace/ask/{body["id"]}')[1]
            self.assertNotIn('生产中”', json.dumps(reopened, ensure_ascii=False))
            self.assertNotEqual(reopened.get('status'), 'draft')

    def test_a_kept_draft_keeps_no_options_read_from_rows_and_reopening_fills_them_again(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            self.confirmed_action(team, PICK)
            status, body = self.ask(team['ann'], f'把订单 {IN_PRODUCTION} 的客户改成 KH002', draft('转客户', {'订单号': IN_PRODUCTION}, {'客户编号': 'KH002'}))
            self.assertEqual(body['status'], 'draft', body)
            self.assertTrue(body['draft']['action']['parameters'][0]['options'])   # the form offers the customers she may read
            kept = self.kept_answer(folder, body['id'])
            self.assertNotIn('"options"', kept)
            self.assertNotIn('KH001', kept)   # no customer id but the one asked for
            reopened = team['ann'].get(f'/api/workspace/ask/{body["id"]}')[1]
            self.assertEqual(len(reopened['draft']['action']['parameters'][0]['options']), len(body['draft']['action']['parameters'][0]['options']))

    def test_a_kept_draft_reopened_after_the_data_changed_is_refused_as_it_would_be_now(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            ann, bob = team['ann'], team['bob']
            body = self.ask(ann, f'把订单 {IN_PRODUCTION} 标成已交付', draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}))[1]
            record = ann.post('/api/workspace/actions/submit', body['draft']['submit'])[1]['record']
            self.assertEqual(bob.post('/api/workspace/actions/decide', {'id': record, 'decision': 'approve'})[1]['state'], 'approved')
            reopened = ann.get(f'/api/workspace/ask/{body["id"]}')[1]
            self.assertEqual((reopened['status'], reopened['refusal']['check']), ('refused', 'condition'), reopened)
            self.assertIn('现在是“已交付”', reopened['reason'])
            self.assertNotIn('draft', reopened)

    def test_a_question_naming_an_action_that_needs_another_look_is_refused_before_the_model(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            ann = team['ann']
            self.confirmed_action(team, AMOUNT)
            self.assertEqual(ann.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': [{'value': '1', 'label': '制造中'}]})[0], 200)
            for column in ('状态码', None):
                shown = team['bob'].get('/api/workspace/types/order')[1]
                shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
                self.assertEqual(team['bob'].post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})[0], 200)
            shown = team['bob'].get('/api/workspace/actions/' + quote(AMOUNT['name']))[1]
            self.assertEqual(team['bob'].post('/api/workspace/actions/confirm', {'id': AMOUNT['name'], 'version': shown['version']})[0], 200)
            asked = len(self.model.requests)
            body = self.ask(ann, f'用改订单状态把订单 {IN_PRODUCTION} 标成已交付', draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}))[1]
            self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'unsettled'), body)
            self.assertEqual(len(self.model.requests), asked)   # the question names it: refused before the model
            self.assertIn(('改订单状态', 'needs_look'), [(d['name'], d['state']) for d in body['refusal']['definitions']])

    def test_an_action_that_reads_a_column_whose_values_are_kept_from_the_model_is_not_told(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            self.confirmed_action(team, AMOUNT)
            self.ask(team['ann'], '订单有多少？', COUNT)
            self.assertIn('调金额', [a['name'] for a in self.model.requests[-1]['ontology']['actions']])
            self.assertEqual(team['ann'].post('/api/workspace/types/privacy', {'id': 'order', 'column': '金额', 'hide_values': True})[0], 200)
            self.ask(team['ann'], '订单有多少？', COUNT)
            told = [a['name'] for a in self.model.requests[-1]['ontology']['actions']]
            self.assertNotIn('调金额', told)   # writes 金额
            self.assertNotIn('新建订单', told)   # fills in 金额
            self.assertIn('改订单状态', told)

    def test_a_label_two_codes_share_is_not_turned_into_either_code(self):
        with mock.patch.object(action_drafts, 'meaning_labels', lambda conn, english, column: {'0': '已交付', '1': '生产中', '2': '已交付'}):
            self.assertEqual(action_drafts._code(None, 'order', '状态码', True, '已交付'), '已交付')   # checked as written, and refused as no code
            self.assertEqual(action_drafts._code(None, 'order', '状态码', True, '生产中'), '1')
            self.assertEqual(action_drafts._code(None, 'order', '状态码', True, '2'), '2')

    def test_a_condition_value_is_told_only_for_a_column_whose_values_the_model_already_gets(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            self.confirmed_action(team, GUARDED)
            self.ask(team['ann'], '订单有多少？', COUNT)
            self.ask(team['ann'], '把那张大单锁定', draft('锁定大单', {'订单号': IN_PRODUCTION}, {'状态码': '0'}))
            for request in self.model.requests:
                sent = json.dumps({k: v for k, v in request.items() if k != 'asked'}, ensure_ascii=False)
                for value in ('45678', 'DD20260004', IN_PRODUCTION):
                    self.assertNotIn(value, sent)
            guarded = next(a for a in self.model.requests[-1]['ontology']['actions'] if a['name'] == '锁定大单')
            self.assertIn('订单号', guarded['conditions'])
            self.assertIn('金额', guarded['conditions'])
            status_action = next(a for a in self.model.requests[-1]['ontology']['actions'] if a['name'] == '改订单状态')
            self.assertIn('生产中', status_action['conditions'])   # a code column's meanings go to the model already
            body = self.ask(team['ann'], '把那张大单锁定', draft('锁定大单', {'订单号': DELIVERED}, {'状态码': '0'}))[1]
            self.assertEqual(body['refusal']['check'], 'condition')   # code checks the whole condition

    def test_a_reason_over_300_characters_is_left_for_the_person_to_write(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            long = '客户来电' * 80
            for reply in (draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}, long), draft('删除取消的订单', {'订单号': CANCELLED}, {}, long)):
                body = self.ask(team['ann'], '改一下', reply)[1]
                self.assertEqual(body['status'], 'draft', body)
                self.assertEqual((body['draft']['reason'], body['draft']['submit']['reason'], body['draft']['reason_too_long']), ('', '', True))
            self.assertNotIn('reason_too_long', self.ask(team['ann'], '改一下', draft('改订单状态', {'订单号': IN_PRODUCTION}, {'状态码': '0'}, '签收'))[1]['draft'])

    def test_a_reply_that_is_not_a_drafts_shape_is_refused_as_such(self):
        with self.started() as (base, folder):
            team = self.setup(base, 'some')
            for reply, check in ((json.dumps({'questions': [{'question': 'x', 'reasoning': 'r', 'query': {'action': '改订单状态'}}]}, ensure_ascii=False), 'not_a_draft'),
                                 (json.dumps({'questions': [{'question': 'x', 'reasoning': 'r', 'query': {'action': {'name': '改订单状态', 'colour': 'red'}}}]}, ensure_ascii=False), 'not_a_draft'),
                                 (json.dumps({'questions': [{'question': 'x', 'reasoning': 'r', 'query': {'action': [{'name': '改订单状态'}, {'name': '删除取消的订单'}]}}]}, ensure_ascii=False), 'one_draft')):
                body = self.ask(team['ann'], '改一下', reply)[1]
                self.assertEqual((body['status'], body['refusal']['check']), ('refused', check), body)
            body = self.ask(team['ann'], '改一下', json.dumps({'questions': [{'question': 'x', 'query': {'action': 'x'}}]}), lang='en')[1]
            self.assertIn('not a draft', body['reason'])

    def test_the_mcp_ask_description_is_mains_with_drafts_off_and_tells_of_drafts_with_them_on(self):
        listed = lambda: {t['name']: t for t in mcp_server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        with mock.patch.object(action_drafts, 'DRAFTS', False):
            off = listed()['ask']['description']
        self.assertEqual(hashlib.sha256(off.encode()).hexdigest(), MAIN_ASK_DESCRIPTION)
        on = listed()['ask']['description']
        self.assertTrue(on.startswith(off))
        self.assertIn('draft', on[len(off):])


if __name__ == '__main__':
    unittest.main()
