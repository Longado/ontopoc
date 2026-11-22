"""Questions we need (要回答的问题), walked through the real service with a scripted model on the planted tables.

A builder writes a question the team needs answered and, when known, what it should give: a number, or that it must be refused. A second person confirms that
expectation. A builder who sees every row and every type runs the list: each question is asked through the same path a person's question takes, up to five
times, and each comes back as one of: passes, differs (expected and got), refused (with the definitions that block it and who can confirm them), no
expectation yet (the answer is shown, to be checked and adopted), needs another look (the data or a definition it read moved since the expectation was
confirmed), or not run (the model could not be reached). Nothing in it changes the answer a person gets from asking."""
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ontology_poc_generator import needed_questions, workspace_questions, workspace_store
from ontology_poc_generator.recognition import ModelCompletion, RecognitionError
from ontology_poc_generator.workspace_store import open_workspace
from tests.test_access import Client
from tests.test_object_types import ORDER, TABLES, VALID, orders_upload
from tests.test_two_person import SigningTestCase
from tests.test_workspace_questions import ALL_ORDERS, CANCELLED, CANCELLED_QUERY, ORDERS, cancelled

NEEDED = '/api/workspace/needed'
DELIVERED = sum(1 for r in ORDERS if r['状态码'] == '0')
MAKING = sum(1 for r in ORDERS if r['状态码'] == '1')
FIRST_DELIVERED = next(i for i, r in enumerate(ORDERS) if r['状态码'] == '0')


def code_query(code):
    return {**CANCELLED_QUERY, 'where': [{'field': '状态码', 'equals': code}]}


def said(query, label=None):
    return {'reasoning': 'test', 'query': query, 'definitions_used': [{'id': f'订单.状态码={label}', 'direction': 'include', 'basis': label}] if label else []}


Q_CANCELLED = '取消的订单有多少？'
Q_ALL = '订单一共有多少？'
Q_VALID = '有效订单有多少？'
Q_VALID_AMOUNT = '有效订单的金额合计是多少？'
Q_MAKING = '生产中的订单有多少？'
Q_DELIVERED = '已交付的订单有多少？'
Q_HOW_MUCH = '订单有多少？'   # how many, or how much: read one way, then the other
AMOUNT = {**ALL_ORDERS, 'measure': {'field': '金额', 'op': 'sum'}}
TOTAL_AMOUNT = sum(float(r['金额']) for r in ORDERS)
SCRIPT = {Q_CANCELLED: [cancelled()], Q_ALL: [said(ALL_ORDERS)], Q_MAKING: [said(code_query('1'), '生产中')], Q_DELIVERED: [said(code_query('0'), '已交付')],
          Q_HOW_MUCH: [said(ALL_ORDERS), said(AMOUNT), said(ALL_ORDERS)]}   # one question, two numbers in three asks


def one_more_cancelled(record, i):
    """The same orders, one delivered order now cancelled: the codes and their meanings stay, the counts move."""
    return {**record, '状态码': '2'} if i == FIRST_DELIVERED else record


class ByQuestion:
    """A scripted model: for each question asked, the replies to give in turn (the last one again once the others are used). An exception is raised instead of
    replying, as a model that cannot be reached; a str is sent as it is (text that is not JSON, or JSON of another shape). Every request is kept. `hold`: an
    event each call waits for, so a run can be caught while it goes."""

    def __init__(self, script, hold=None):
        self.script, self.requests, self.hold = {q: list(items) for q, items in script.items()}, [], hold

    def complete_json(self, *, system_prompt, user_prompt, timeout_seconds=None):
        if self.hold is not None:
            self.hold.wait(10)
        request = json.loads(user_prompt)
        self.requests.append(request)
        items = self.script[request['asked']]
        reply = items.pop(0) if len(items) > 1 else items[0]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, str):
            return ModelCompletion('test', 'test-model', reply)
        return ModelCompletion('test', 'test-model', json.dumps({'questions': [{'question': request['asked'], **reply}]}, ensure_ascii=False))


ENGLISH = {'headers': {'Accept-Language': 'en'}}


class NeededCase(SigningTestCase):
    def team(self, base, valid=True):
        """Ann (builder) uploads the planted tables and proposes 订单, Bob (builder) confirms it and its meanings; Ann proposes the view 有效订单, which nobody
        confirms; Vera is a viewer."""
        team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        ann, bob = team['ann'], team['bob']
        self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)
        for column in ('状态码', None):
            shown = bob.get('/api/workspace/types/order')[1]
            shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
            status, body = bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})
            self.assertEqual(status, 200, body)
        if valid:
            self.assertEqual(ann.post('/api/workspace/types/views', VALID)[0], 200)
        return team

    def write(self, client, question, expect=None, note=None, status=200, **more):
        got, body = client.post(NEEDED, {'question': question, **({'expect': expect} if expect is not None else {}), **({'note': note} if note else {})}, **more)
        self.assertEqual(got, status, body)
        return body

    def item(self, client, question):
        return next(q for q in self.listing(client)['questions'] if q['question'] == question)

    def listing(self, client, status=200, **more):
        got, body = client.get(NEEDED, **more)
        self.assertEqual(got, status, body)
        return body

    def confirm(self, client, question, status=200, **more):
        found = self.item(client, question)
        got, body = client.post(f'{NEEDED}/confirm', {'id': found['id'], 'version': found['version']}, **more)
        self.assertEqual(got, status, body)
        return body

    def run_list(self, client, repeats=None, status=200, wait=True, **more):
        """Start a run; it goes on in the service after the answer, so wait (by default) until the list says it is done and return the list then."""
        got, body = client.post(f'{NEEDED}/run', {'repeats': repeats} if repeats is not None else {}, **more)
        self.assertEqual(got, status, body)
        if status != 200 or not wait:
            return body
        for _ in range(500):
            if body.get('running') is None:
                return body
            time.sleep(0.02)
            body = self.listing(client, **more)
        self.fail('the run did not finish')

    def results(self, listing):
        return {q['question']: q['result'] for q in listing['questions']}

    def user_id(self, out, username):
        conn = sqlite3.connect(out / 'workspace.sqlite')
        try:
            return conn.execute('SELECT id FROM user WHERE username = ?', (username,)).fetchone()[0]
        finally:
            conn.close()


def number(value):
    return {'kind': 'number', 'value': value}


REFUSED = {'kind': 'refused'}


class OutcomeTests(NeededCase):
    def test_one_run_shows_each_outcome_and_keeps_the_asks_out_of_the_runners_history(self):
        model = ByQuestion(SCRIPT)
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            for question, expect in ((Q_CANCELLED, number(CANCELLED)), (Q_ALL, number('999')), (Q_VALID, number(144)), (Q_VALID_AMOUNT, REFUSED), (Q_MAKING, None),
                                     (Q_HOW_MUCH, number(len(ORDERS)))):
                self.write(ann, question, expect, note='财务 10 月报表' if expect else None)
            for question in (Q_CANCELLED, Q_ALL, Q_VALID, Q_VALID_AMOUNT, Q_HOW_MUCH):
                self.confirm(bob, question)
            before = self.listing(bob)
            self.assertEqual((before['limits'], before['budget']['left'], before['can_run']), ({'questions': 30, 'repeats': 5}, 300, {'ok': True, 'why': None}))
            body = self.run_list(bob, 3)
            results = self.results(body)
            self.assertEqual({q: r['outcome'] for q, r in results.items()},
                             {Q_CANCELLED: 'passes', Q_ALL: 'differs', Q_VALID: 'refused', Q_VALID_AMOUNT: 'passes', Q_MAKING: 'no_expectation', Q_HOW_MUCH: 'differs'})
            self.assertEqual((results[Q_CANCELLED]['right'], results[Q_CANCELLED]['asked'], results[Q_CANCELLED]['distinct']), (3, 3, [{'number': CANCELLED, 'status': 'answered', 'times': 3}]))
            self.assertEqual((results[Q_ALL]['expected'], results[Q_ALL]['right'], results[Q_ALL]['distinct']), (number(999), 0, [{'number': len(ORDERS), 'status': 'answered', 'times': 3}]))
            # the question that gave two different numbers in three asks
            self.assertEqual((results[Q_HOW_MUCH]['right'], results[Q_HOW_MUCH]['asked']), (2, 3))
            self.assertEqual(results[Q_HOW_MUCH]['distinct'], [{'number': len(ORDERS), 'status': 'answered', 'times': 2}, {'number': TOTAL_AMOUNT, 'status': 'answered', 'times': 1}])
            # an unexpected refusal is its own outcome: the definition that blocks it, its state and who can confirm it; never "differs"
            refused = results[Q_VALID]
            self.assertEqual([(b['kind'], b['name'], b['state'], b['who_can_confirm']) for b in refused['blocking']], [('view', '有效订单', 'checked', ['Bob', '管理员'])])
            self.assertEqual((refused['right'], refused['distinct']), (0, [{'number': None, 'status': 'refused', 'times': 3}]))
            # an expected refusal passes when the answer is a refusal
            self.assertEqual((results[Q_VALID_AMOUNT]['right'], results[Q_VALID_AMOUNT]['asked']), (3, 3))
            # no expectation yet: the answer is shown, with the query, for a person to check and adopt
            making = results[Q_MAKING]
            self.assertEqual((making['answer']['number'], making['expected']), (MAKING, None))
            self.assertIn('生产中', making['answer']['query_text'])
            # what the run made: the asks that reached the model, against at most questions x asks
            run = body['last_run']
            self.assertEqual((run['by'], run['repeats'], run['planned'], run['calls'], run['status']), ('Bob', 3, 18, 12, 'done'))
            self.assertEqual(len(model.requests), 12)   # the two questions a check stops are refused before the model is asked
            self.assertEqual(body['budget']['left'], 300 - 12)
            # the asks stay out of Bob's own questions, and every call the run made is marked as the run's in the model call log
            self.assertEqual(bob.get('/api/workspace/ask')[1]['history'], [])
            conn = sqlite3.connect(out / 'workspace.sqlite')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM qa_question').fetchone()[0], 0)
            conn.close()
            lines = [json.loads(l) for l in (out / 'model_calls.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(lines), 12)
            self.assertEqual({(l.get('suite'), l.get('run')) for l in lines}, {(True, run['id'])})
            # the results are stored once: another builder reads the same
            self.assertEqual(self.results(self.listing(ann)), results)

    def test_when_the_data_moves_an_expectation_that_no_longer_holds_needs_another_look_and_goes_back_for_confirming(self):
        model = ByQuestion(SCRIPT)
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.write(ann, Q_CANCELLED, number(CANCELLED))
            self.write(ann, Q_ALL, number(len(ORDERS)))
            for question in (Q_CANCELLED, Q_ALL):
                self.confirm(bob, question)
            self.assertEqual({q: r['outcome'] for q, r in self.results(self.run_list(bob)).items()}, {Q_CANCELLED: 'passes', Q_ALL: 'passes'})
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(one_more_cancelled)]})[0], 200)   # one delivered order cancelled
            body = self.run_list(bob)
            results = self.results(body)
            moved = results[Q_CANCELLED]
            self.assertEqual((moved['outcome'], moved['distinct'][0]['number'], moved['moved']), ('needs_look', CANCELLED + 1, [{'kind': 'dataset', 'name': '订单', 'from': 1, 'to': 2}]))
            self.assertEqual(results[Q_ALL]['outcome'], 'passes')   # what still holds on the new data still passes
            item = next(q for q in body['questions'] if q['question'] == Q_CANCELLED)
            self.assertEqual((item['state'], item['look'], item['confirmed_by']), ('needs_look', [{'kind': 'dataset', 'name': '订单', 'from': 1, 'to': 2}], 'Bob'))
            # back for a person: the next run has no confirmed expectation to hold it against
            self.assertEqual(self.results(self.run_list(bob))[Q_CANCELLED]['outcome'], 'no_expectation')
            # Ann writes the new number, Bob confirms it on the new data, and it passes again
            found = self.item(ann, Q_CANCELLED)
            status, body = ann.post(f'{NEEDED}/update', {'id': found['id'], 'version': found['version'], 'expect': number(CANCELLED + 1)})
            self.assertEqual((status, body['state'], body['confirmed_by'], body['look']), (200, 'proposed', None, []))
            self.confirm(bob, Q_CANCELLED)
            self.assertEqual(self.results(self.run_list(bob))[Q_CANCELLED]['outcome'], 'passes')

    def test_when_a_definition_the_expectation_was_confirmed_on_moves_a_number_that_no_longer_holds_needs_another_look(self):
        model = ByQuestion({Q_ALL: [said(ALL_ORDERS, None), said(AMOUNT)]})   # the count, then (after the definition moved) the amount
        with self.service(gateway=model) as (base, out):
            team = self.team(base, valid=False)
            ann, bob = team['ann'], team['bob']
            self.write(ann, Q_ALL)
            self.assertEqual(self.results(self.run_list(bob))[Q_ALL]['outcome'], 'no_expectation')   # the answer is shown, adopted and confirmed: it read 订单
            found = self.item(ann, Q_ALL)
            self.assertEqual(ann.post(f'{NEEDED}/update', {'id': found['id'], 'version': found['version'], 'expect': number(len(ORDERS))})[0], 200)
            self.confirm(bob, Q_ALL)
            shown = bob.get('/api/workspace/types/order')[1]   # 订单 gets a new description: it stays confirmed, at a new version
            self.assertEqual(ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': shown['version'], 'description': '一张订单'})[0], 200)
            self.assertEqual(bob.get('/api/workspace/types/order')[1]['state'], 'confirmed')
            moved = self.results(self.run_list(bob))[Q_ALL]
            self.assertEqual(moved['outcome'], 'needs_look')
            self.assertEqual([(m['kind'], m['name']) for m in moved['moved']], [('definition', '订单')])

    def test_a_model_that_cannot_be_reached_stops_the_run_and_says_which_questions_were_not_asked(self):
        model = ByQuestion({**SCRIPT, Q_ALL: [RecognitionError('connection refused')]})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            for question in (Q_CANCELLED, Q_ALL, Q_MAKING):
                self.write(ann, question, number(1))
                self.confirm(bob, question)
            body = self.run_list(bob, 2)
            self.assertEqual({q: r['outcome'] for q, r in self.results(body).items()}, {Q_CANCELLED: 'differs', Q_ALL: 'not_run', Q_MAKING: 'not_run'})
            self.assertEqual((body['last_run']['status'], body['last_run']['calls']), ('stopped', 3))
            self.assertIn('connection refused', body['last_run']['note'])
            self.assertEqual(len(model.requests), 3)

    def test_without_a_model_the_run_is_refused_before_anything_is_counted(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.write(team['ann'], Q_CANCELLED, number(CANCELLED))
            listing = self.listing(team['bob'])
            self.assertFalse(listing['can_run']['ok'])
            self.assertIn('模型', listing['can_run']['why'])
            self.assertIn('model', self.run_list(team['bob'], status=503, **ENGLISH)['error'])
            self.assertIsNone(self.listing(team['bob'])['last_run'])

    def test_a_run_says_when_the_question_prompt_changed_since(self):
        with self.service(gateway=ByQuestion(SCRIPT)) as (base, out):
            team = self.team(base)
            self.write(team['ann'], Q_CANCELLED, number(CANCELLED))
            self.run_list(team['bob'])
            self.assertFalse(self.listing(team['bob'])['last_run']['stale_prompt'])
            with mock.patch.object(needed_questions, 'QUESTION_PROMPT_VERSION', 'company_questions.next'):
                self.assertTrue(self.listing(team['bob'])['last_run']['stale_prompt'])


class ExpectationTests(NeededCase):
    def test_an_expectation_is_proposed_by_one_person_and_confirmed_by_another_and_a_change_puts_it_back(self):
        with self.service(gateway=ByQuestion(SCRIPT)) as (base, out):
            team = self.team(base)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            made = self.write(ann, Q_CANCELLED, number('1,234'), note='财务 10 月报表')
            self.assertEqual((made['state'], made['expect'], made['written_by'], made['confirmed_by'], made['note']), ('proposed', number(1234), 'Ann', None, '财务 10 月报表'))
            self.assertIn('另一位', self.confirm(ann, Q_CANCELLED, status=403)['error'])   # her own: someone else confirms it
            self.assertIn('someone else', self.confirm(ann, Q_CANCELLED, status=403, **ENGLISH)['error'])
            stale = self.item(bob, Q_CANCELLED)
            done = self.confirm(bob, Q_CANCELLED)
            self.assertEqual((done['state'], done['confirmed_by'], done['self_confirmed']), ('confirmed', 'Bob', False))
            status, body = bob.post(f'{NEEDED}/confirm', {'id': stale['id'], 'version': stale['version']})   # confirmed on a version that is gone
            self.assertEqual(status, 409, body)
            self.assertIn('已经确认', self.confirm(bob, Q_CANCELLED, status=400)['error'])
            # a new source alone keeps it confirmed; new words or a new number put it back to proposed
            found = self.item(ann, Q_CANCELLED)
            status, body = ann.post(f'{NEEDED}/update', {'id': found['id'], 'version': found['version'], 'note': '财务 11 月报表'})
            self.assertEqual((status, body['state'], body['note']), (200, 'confirmed', '财务 11 月报表'))
            status, body = ann.post(f'{NEEDED}/update', {'id': body['id'], 'version': body['version'], 'question': '已取消的订单有多少？'})
            self.assertEqual((status, body['state'], body['confirmed_by'], body['written_by']), (200, 'proposed', None, 'Ann'))
            self.confirm(bob, '已取消的订单有多少？')
            found = self.item(bob, '已取消的订单有多少？')
            status, body = bob.post(f'{NEEDED}/update', {'id': found['id'], 'version': found['version'], 'expect': REFUSED})
            self.assertEqual((status, body['state'], body['written_by'], body['expect']), (200, 'proposed', 'Bob', REFUSED))
            self.assertIn('另一位', self.confirm(bob, '已取消的订单有多少？', status=403)['error'])   # now Bob's own
            status, body = bob.post(f'{NEEDED}/update', {'id': body['id'], 'version': body['version'], 'expect': None})
            self.assertEqual((status, body['state'], body['expect']), (200, 'none', None))
            self.assertIn('先写', self.confirm(ann, '已取消的订单有多少？', status=400)['error'])   # nothing to confirm
            # with two-person confirmation off, a person may confirm their own, and it says so
            self.assertEqual(admin.post('/api/settings', {'two_person': False})[0], 200)
            self.write(ann, Q_ALL, number(160))
            done = self.confirm(ann, Q_ALL)
            self.assertEqual((done['state'], done['self_confirmed']), ('confirmed', True))
            # a question goes from the list
            found = self.item(ann, Q_ALL)
            status, body = bob.post(f'{NEEDED}/delete', {'id': found['id'], 'version': found['version']})
            self.assertEqual(status, 200, body)
            self.assertEqual([q['question'] for q in self.listing(bob)['questions']], ['已取消的订单有多少？'])
            conn = sqlite3.connect(out / 'workspace.sqlite')
            changes = [c for (c,) in conn.execute("SELECT change FROM log WHERE element_id LIKE 'needed:%' ORDER BY rowid")]
            conn.close()
            self.assertEqual(changes, ['written', 'confirmed', 'changed', 'changed', 'confirmed', 'changed', 'changed', 'written', 'confirmed', 'deleted'])

    def test_what_cannot_be_written_or_run_is_refused_in_words_in_both_languages(self):
        with self.service(gateway=ByQuestion(SCRIPT)) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.assertIn('写下', self.write(ann, '  ', status=400)['error'])
            self.assertIn('Write the question', self.write(ann, '  ', status=400, **ENGLISH)['error'])
            self.assertIn('300', self.write(ann, '问' * 301, status=400)['error'])
            self.assertIn('数字', self.write(ann, Q_CANCELLED, {'kind': 'number', 'value': '很多'}, status=400)['error'])
            self.assertIn('must be a number', self.write(ann, Q_CANCELLED, {'kind': 'number', 'value': True}, status=400, **ENGLISH)['error'])
            self.assertIn('refused', self.write(ann, Q_CANCELLED, {'kind': 'maybe'}, status=400, **ENGLISH)['error'])
            self.assertIn('120', self.write(ann, Q_CANCELLED, number(1), note='来' * 121, status=400)['error'])
            self.assertIn('列表里还没有问题', self.run_list(bob, status=400)['error'])
            self.assertIn('The list has no question', self.run_list(bob, status=400, **ENGLISH)['error'])
            self.write(ann, Q_CANCELLED)
            self.assertIn('已经在', self.write(bob, Q_CANCELLED, status=400)['error'])
            self.assertIn('already', self.write(bob, Q_CANCELLED, status=400, **ENGLISH)['error'])
            for repeats in (0, 6, '2', True):
                self.assertIn('1 to 5', self.run_list(bob, repeats, status=400, **ENGLISH)['error'])
            self.assertIn('1 到 5', self.run_list(bob, 6, status=400)['error'])
            for n in range(29):
                self.write(ann, f'第 {n} 个问题有多少？')
            self.assertIn('30', self.write(ann, Q_ALL, status=400)['error'])   # at most 30 questions in the list
            self.assertIn('at most 30', self.write(ann, Q_ALL, status=400, **ENGLISH)['error'])
            listing = self.listing(bob)
            self.assertEqual(len(listing['questions']), 30)
            self.assertEqual(self.post_missing(bob, 'update'), (404, '没有这个问题'))
            self.assertEqual(self.post_missing(bob, 'confirm'), (404, '没有这个问题'))
            self.assertEqual(self.post_missing(bob, 'delete'), (404, '没有这个问题'))

    def post_missing(self, client, act):
        status, body = client.post(f'{NEEDED}/{act}', {'id': 999, 'version': 1})
        return status, body['error']

    def test_the_comparison_is_exact_on_the_number_the_answer_states(self):
        self.assertTrue(needed_questions.same_number(16, 16.0))
        self.assertFalse(needed_questions.same_number(1234.57, 1234.5678))
        self.assertFalse(needed_questions.same_number(16, None))


class BudgetTests(NeededCase):
    def test_a_run_has_its_own_budget_line_and_does_not_spend_the_persons_hourly_questions(self):
        model = ByQuestion(SCRIPT)
        with self.service(gateway=model) as (base, out), mock.patch.object(needed_questions, 'SUITE_LIMIT', 5):
            team = self.team(base, valid=False)
            ann, bob = team['ann'], team['bob']
            for question in (Q_CANCELLED, Q_ALL, Q_MAKING):
                self.write(ann, question)
            self.assertEqual(self.listing(bob)['budget'], {'calls': 5, 'hours': 24, 'used': 0, 'left': 5})
            refused = self.run_list(bob, 2, status=429, **ENGLISH)   # 3 questions x 2 asks could make 6 calls: refused before the first
            self.assertIn('6', refused['error'])
            self.assertIn('5', refused['error'])
            self.assertEqual(model.requests, [])
            self.assertEqual(self.run_list(bob, 1)['budget'], {'calls': 5, 'hours': 24, 'used': 3, 'left': 2})
            self.assertIn('模型调用', self.run_list(bob, 1, status=429)['error'])
            conn = sqlite3.connect(out / 'workspace.sqlite')
            asked = conn.execute("SELECT name FROM sqlite_master WHERE name = 'ask_budget'").fetchone() and conn.execute('SELECT COUNT(*) FROM ask_budget').fetchone()[0]
            conn.close()
            self.assertFalse(asked)   # nothing counted against Bob's (or anyone's) questions an hour
            status, body = bob.post('/api/workspace/ask', {'question': Q_CANCELLED})   # and Bob still asks as before
            self.assertEqual((status, body['status']), (200, 'answered'))

    def test_one_run_at_a_time(self):
        hold = threading.Event()
        with self.service(gateway=ByQuestion(SCRIPT, hold=hold)) as (base, out):
            team = self.team(base, valid=False)
            self.write(team['ann'], Q_CANCELLED)
            started = self.run_list(team['ann'], wait=False)   # the answer comes as the run starts; it goes on in the service
            self.assertEqual((started['running']['by'], started['running']['planned']), ('Ann', 1))
            self.assertIn('正在跑', self.run_list(team['bob'], status=409)['error'])
            self.assertFalse(self.listing(team['bob'])['can_run']['ok'])
            hold.set()
            done = self.run_list(team['bob'])   # once the first is done, the next one starts
            self.assertEqual(done['last_run']['by'], 'Bob')


def raw(client, method, path, payload=None, headers=None):
    """(status, the body's bytes) as the service sent them."""
    head = {'Content-Type': 'application/json', **(headers or {})}
    if method == 'POST':
        head['Origin'] = client.base
    if client.cookie:
        head['Cookie'] = f'{client.cookie_name}={client.cookie}'
    request = Request(client.base + path, data=json.dumps(payload or {}).encode() if method == 'POST' else None, headers=head, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


class WhoMayTests(NeededCase):
    def limit(self, team, out, how):
        bob = self.user_id(out, 'bob')
        if how == 'rows':
            self.assertEqual(team['admin'].post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '状态码', 'value': '0', 'user_ids': [bob]}]})[0], 200)
        else:
            self.assertEqual(team['admin'].post('/api/workspace/permissions', {'type': 'order', 'visible_to': [self.user_id(out, 'ann')]})[0], 200)

    def test_a_viewer_and_a_limited_builder_get_the_same_refusal_whatever_the_list_holds(self):
        """The refusals say nothing of the list: the bytes are the same with the list empty, and with a question, an expectation and a run's results in it; a
        builder limited by a row rule and one limited by a type list are told the same."""
        def answers(team):
            vera, bob = team['vera'], team['bob']
            return [raw(vera, 'GET', NEEDED), raw(vera, 'POST', f'{NEEDED}/run'), raw(bob, 'GET', NEEDED), raw(bob, 'POST', f'{NEEDED}/run', {'repeats': 1}),
                    raw(bob, 'POST', NEEDED, {'question': Q_ALL}), raw(bob, 'GET', NEEDED, headers={'Accept-Language': 'en'})]
        seen = {}
        for how in ('rows', 'types'):
            for filled in (False, True):
                with self.service(gateway=ByQuestion(SCRIPT)) as (base, out):
                    team = self.team(base)
                    if filled:
                        self.write(team['ann'], Q_CANCELLED, number(CANCELLED))
                        self.confirm(team['bob'], Q_CANCELLED)
                        self.run_list(team['bob'])
                    self.limit(team, out, how)
                    seen[how, filled] = answers(team)
                    if filled:   # a limited builder cannot run: nothing was asked
                        conn = sqlite3.connect(out / 'workspace.sqlite')
                        self.assertEqual(conn.execute('SELECT COUNT(*) FROM needed_run').fetchone()[0], 1)
                        conn.close()
        first = seen['rows', False]
        self.assertEqual([s for s, _ in first], [403] * 6)
        for key, got in seen.items():
            self.assertEqual(got, first, key)
        bob_get = json.loads(first[2][1])['error']
        self.assertIn('行规则', bob_get)
        self.assertNotIn('订单', bob_get)
        self.assertIn('row rule', json.loads(first[5][1])['error'])

    def test_a_limited_builder_cannot_run_and_an_unlimited_one_can(self):
        for how in ('rows', 'types'):
            with self.service(gateway=ByQuestion(SCRIPT)) as (base, out):
                team = self.team(base)
                self.write(team['ann'], Q_CANCELLED, number(CANCELLED))
                self.limit(team, out, how)
                self.assertIn('行规则', self.run_list(team['bob'], status=403)['error'])
                if how == 'types':   # a type list that names Ann leaves her every type; a row rule limits every builder it does not give all rows
                    self.assertEqual(self.results(self.run_list(team['ann']))[Q_CANCELLED]['outcome'], 'no_expectation')
                else:
                    self.run_list(team['ann'], status=403)
                self.assertEqual(self.results(self.run_list(team['admin']))[Q_CANCELLED]['outcome'], 'no_expectation')   # an admin is never limited

    def test_a_token_cannot_write_confirm_or_run_and_the_refusal_is_the_same_whether_the_question_exists(self):
        from tests.test_token_no_confirm import bearer
        with self.service(gateway=ByQuestion(SCRIPT)) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            made = self.write(ann, Q_CANCELLED, number(CANCELLED))
            full = bob.post('/api/auth/tokens', {'label': 'agent', 'scope': 'all'})[1]['token']
            read = bob.post('/api/auth/tokens', {'label': 'reader', 'scope': 'read'})[1]['token']
            agent = Client(base)
            for path, payload in ((NEEDED, {'question': Q_ALL}), (f'{NEEDED}/update', {'id': made['id'], 'version': made['version'], 'note': 'x'}),
                                  (f'{NEEDED}/delete', {'id': made['id'], 'version': made['version']}), (f'{NEEDED}/confirm', {'id': made['id'], 'version': made['version']}),
                                  (f'{NEEDED}/run', {})):
                status, body = agent.post(path, payload, **bearer(full))
                self.assertEqual((status, body.get('needs_person')), (403, True), path)
                self.assertIn('本人登录页面', body['error'])
                self.assertIn('要回答的问题', body['error'])
                status, body = agent.post(path, payload, **bearer(full, english=True))
                self.assertIn('signed in to the page', body['error'])
                self.assertIn('Questions we need', body['error'])
                status, body = agent.post(path, payload, **bearer(read))
                self.assertEqual(status, 403, path)
                self.assertIn('这个令牌只能读和提问', body['error'])
            there = raw(agent, 'POST', f'{NEEDED}/confirm', {'id': made['id'], 'version': made['version']}, headers={'Authorization': f'Bearer {full}'})
            missing = raw(agent, 'POST', f'{NEEDED}/confirm', {'id': 999, 'version': 1}, headers={'Authorization': f'Bearer {full}'})
            self.assertEqual(there, missing)
            self.assertEqual(self.item(ann, Q_CANCELLED)['state'], 'proposed')   # nothing a token sent was kept
            self.assertEqual(len(self.listing(ann)['questions']), 1)
            self.assertIsNone(self.listing(ann)['last_run'])
            status, body = agent.get(NEEDED, **bearer(read))   # a token reads the list as its person, like any page it may read
            self.assertEqual((status, [q['question'] for q in body['questions']]), (200, [Q_CANCELLED]))

    def test_a_guest_on_the_demo_cannot_start_a_run(self):
        with self.service(gateway=ByQuestion(SCRIPT), demo=True) as (base, out):
            guest = Client(base)
            self.assertEqual(guest.post('/api/auth/demo')[0], 200)
            self.assertEqual(guest.post(f'{NEEDED}/run', {})[0], 403)
            self.assertEqual(guest.get(NEEDED)[0], 403)

    def test_the_run_itself_refuses_a_token_a_demo_guest_and_a_viewer_whatever_called_it(self):
        conn = open_workspace(':memory:')
        try:
            for user in ({'id': 5, 'role': 'builder', 'display_name': 'A', 'token_id': 3, 'provider': 'password'},
                         {'id': 6, 'role': 'builder', 'display_name': 'G', 'provider': 'demo'},
                         {'id': 7, 'role': 'viewer', 'display_name': 'V', 'provider': 'password'}):
                with self.assertRaises(workspace_questions.QaRefused) as caught:
                    needed_questions.run(conn, ByQuestion(SCRIPT), user, {})
                self.assertEqual(caught.exception.status, 403, user)
        finally:
            conn.close()


VIEWED = {'reasoning': 'test', 'query': ALL_ORDERS, 'definitions_used': [{'id': '有效订单', 'direction': 'include', 'basis': '有效订单'}]}   # all orders read as the valid ones
Q_UNREADABLE = '订单的数是多少？'
Q_EMPTY = '订单数是多少？'
Q_GAP = '订单颜色有几种？'
Q_WRONG_BLOCKER = '有效订单一共有几张？'


class VerdictTests(NeededCase):
    def confirm_view(self, client):
        shown = next(v for v in client.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == '有效订单')
        self.assertEqual(client.post('/api/workspace/types/views/confirm', {'id': '有效订单', 'version': shown['version'], 'seen': shown['seen']})[0], 200)

    def test_must_be_refused_passes_only_on_a_refusal_the_gate_made_and_a_reply_that_cannot_be_read_is_no_answer(self):
        """The gate's refusals are the ones a check makes: a definition that is not confirmed or waits (or nothing in scope, or a relation that cannot be followed),
        a query that left out a confirmed definition, a measure that waits for confirming. A reply that is not JSON, an empty one, or the model saying the
        question is outside what it knows is no answer: never a pass, and never a refusal."""
        model = ByQuestion({Q_UNREADABLE: ['this is not JSON'], Q_EMPTY: [json.dumps({'questions': []})], Q_GAP: [{'reasoning': 'no', 'query': None, 'missing': 'ontology'}],
                            Q_ALL: ['not JSON either']})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            for question in (Q_UNREADABLE, Q_EMPTY, Q_GAP, Q_VALID):
                self.write(ann, question, REFUSED)
            made = self.write(ann, Q_VALID_AMOUNT, {'kind': 'refused', 'blocker': '有效订单'})
            self.assertEqual(made['expect'], {'kind': 'refused', 'blocker': '有效订单'})
            self.write(ann, Q_WRONG_BLOCKER, {'kind': 'refused', 'blocker': '客户'})
            self.write(ann, Q_ALL, number(len(ORDERS)))
            for question in (Q_UNREADABLE, Q_EMPTY, Q_GAP, Q_VALID, Q_VALID_AMOUNT, Q_WRONG_BLOCKER, Q_ALL):
                self.confirm(bob, question)
            results = self.results(self.run_list(bob, 2))
            self.assertEqual({q: (r['outcome'], r['right']) for q, r in results.items()},
                             {Q_UNREADABLE: ('no_answer', 0), Q_EMPTY: ('no_answer', 0), Q_GAP: ('no_answer', 0), Q_VALID: ('passes', 2), Q_VALID_AMOUNT: ('passes', 2),
                              Q_WRONG_BLOCKER: ('refused', 0), Q_ALL: ('no_answer', 0)})
            self.assertEqual(results[Q_UNREADABLE]['distinct'], [{'number': None, 'status': 'no_query', 'times': 2}])
            self.assertEqual(results[Q_GAP]['distinct'], [{'number': None, 'status': 'ontology_gap', 'times': 2}])
            self.assertTrue(results[Q_UNREADABLE]['reason'])
            self.assertEqual([b['name'] for b in results[Q_WRONG_BLOCKER]['blocking']], ['有效订单'])   # refused, but not by the definition it should have been
            self.assertIn('120', self.write(ann, '另一个问题？', {'kind': 'refused', 'blocker': '定' * 121}, status=400)['error'])

    def test_a_wrong_number_is_a_failure_unless_what_the_expected_answer_read_has_moved(self):
        """What the expected answer read is recorded when it passes; a data change that leaves the number right moves that record on. A later misreading on the
        new data is a failure, and its other reading is said."""
        model = ByQuestion({Q_ALL: [said(ALL_ORDERS), said(ALL_ORDERS), VIEWED]})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.confirm_view(bob)
            self.write(ann, Q_ALL, number(len(ORDERS)))
            self.confirm(bob, Q_ALL)
            self.assertEqual(self.results(self.run_list(bob))[Q_ALL]['outcome'], 'passes')
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(lambda r, i: {**r, '金额': str(int(float(r['金额'])) + 1)} if i == 0 else r)]})[0], 200)
            self.assertEqual(self.results(self.run_list(bob))[Q_ALL]['outcome'], 'passes')   # the data moved, the number still holds
            wrong = self.results(self.run_list(bob))[Q_ALL]
            self.assertEqual((wrong['outcome'], wrong['distinct'][0]['number'], wrong.get('moved')), ('differs', 144, []))
            self.assertEqual(wrong['reads_otherwise'], {'now': ['有效订单'], 'not_now': []})
            self.assertEqual(self.item(bob, Q_ALL)['state'], 'confirmed')

    def test_an_expectation_confirmed_on_an_answer_records_what_that_answer_read(self):
        model = ByQuestion({Q_CANCELLED: [cancelled()]})
        with self.service(gateway=model) as (base, out):
            team = self.team(base, valid=False)
            ann, bob = team['ann'], team['bob']
            self.write(ann, Q_CANCELLED)
            self.run_list(bob)
            found = self.item(ann, Q_CANCELLED)
            self.assertEqual(ann.post(f'{NEEDED}/update', {'id': found['id'], 'version': found['version'], 'expect': number(CANCELLED)})[0], 200)
            self.confirm(bob, Q_CANCELLED)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(one_more_cancelled)]})[0], 200)
            moved = self.results(self.run_list(bob))[Q_CANCELLED]   # no run passed since the confirmation: what it read is the adopted answer's
            self.assertEqual((moved['outcome'], moved['moved']), ('needs_look', [{'kind': 'dataset', 'name': '订单', 'from': 1, 'to': 2}]))

    def test_typed_numbers_are_read_only_as_they_are_plainly_written(self):
        with self.service(gateway=ByQuestion(SCRIPT)) as (base, out):
            ann = self.team(base, valid=False)['ann']
            for typed in ('1.234,5', '1,2,3', '12,34', '1 234'):
                self.assertIn('must be a number', self.write(ann, Q_ALL, number(typed), status=400, **ENGLISH)['error'], typed)
            self.assertEqual(self.write(ann, Q_ALL, number('1,234.5'))['expect'], number(1234.5))


class ChargingTests(NeededCase):
    def test_each_call_is_charged_as_it_goes_out(self):
        seen = []

        class Watching(ByQuestion):
            def complete_json(self, **request):
                conn = sqlite3.connect(self.out / 'workspace.sqlite')
                seen.append(conn.execute("SELECT calls FROM needed_run WHERE status = 'running'").fetchone()[0])
                conn.close()
                return super().complete_json(**request)
        model = Watching(SCRIPT)
        with self.service(gateway=model) as (base, out):
            model.out = out
            team = self.team(base, valid=False)
            for question in (Q_CANCELLED, Q_ALL, Q_MAKING):
                self.write(team['ann'], question)
            self.assertEqual(self.run_list(team['bob'])['last_run']['calls'], 3)
            self.assertEqual(seen, [1, 2, 3])

    def test_a_run_cut_off_is_closed_as_stopped_on_the_next_request_with_the_calls_it_made_charged(self):
        with self.service(gateway=ByQuestion(SCRIPT)) as (base, out):
            team = self.team(base, valid=False)
            self.write(team['ann'], Q_CANCELLED)
            conn = open_workspace(out / 'workspace.sqlite')
            conn.execute("INSERT INTO needed_run(by_name, by_user_id, started_at, status, repeats, planned, calls, owner) VALUES ('Ann', 2, ?, 'running', 5, 150, 7, 'a service that stopped')",
                         (workspace_store.now_text(),))
            conn.close()
            listing = self.listing(team['bob'], **ENGLISH)
            self.assertEqual((listing['running'], listing['last_run']['status'], listing['last_run']['calls'], listing['budget']['used']), (None, 'stopped', 7, 7))
            self.assertIn('did not finish', listing['last_run']['note'])
            self.assertTrue(listing['can_run']['ok'])
            done = self.run_list(team['bob'])
            self.assertEqual((done['last_run']['status'], done['budget']['used']), ('done', 8))

    def test_an_error_during_a_run_closes_it_as_stopped_and_charges_what_it_made(self):
        with self.service(gateway=ByQuestion({**SCRIPT, Q_ALL: [ValueError('boom')]})) as (base, out):
            team = self.team(base, valid=False)
            for question in (Q_CANCELLED, Q_ALL, Q_MAKING):
                self.write(team['ann'], question)
            body = self.run_list(team['bob'], **ENGLISH)
            self.assertEqual((body['last_run']['status'], body['last_run']['calls']), ('stopped', 2))
            self.assertIn('stopped on an error', body['last_run']['note'])
            self.assertEqual({q: r['outcome'] for q, r in self.results(body).items()}, {Q_CANCELLED: 'no_expectation', Q_ALL: 'not_run', Q_MAKING: 'not_run'})

    def test_a_model_that_cannot_be_reached_is_said_in_the_runners_language(self):
        with self.service(gateway=ByQuestion({Q_ALL: [RecognitionError('connection refused')]})) as (base, out):
            team = self.team(base, valid=False)
            self.write(team['ann'], Q_ALL)
            note = self.run_list(team['bob'], **ENGLISH)['last_run']['note']
            self.assertTrue(note.startswith('The model could not be reached'), note)
            self.assertIn('connection refused', note)
            self.assertTrue(self.run_list(team['bob'])['last_run']['note'].startswith('模型连不上'))


class SignedInTests(NeededCase):
    def test_the_page_is_told_whether_a_rule_limits_the_person_so_it_can_leave_the_list_out(self):
        with self.service(gateway=ByQuestion(SCRIPT)) as (base, out):
            team = self.team(base)
            self.assertEqual(team['admin'].post('/api/workspace/permissions', {'type': 'order', 'visible_to': [self.user_id(out, 'ann')]})[0], 200)
            self.assertEqual([team[n].get('/api/auth/me')[1]['limited'] for n in ('admin', 'ann', 'bob', 'vera')], [False, False, True, True])


class UnchangedAnswersTests(NeededCase):
    def test_a_persons_answers_and_what_is_kept_of_them_are_the_same_byte_for_byte_whether_the_list_is_used_or_not(self):
        """The same scripted asks in two workspaces: in one nobody touches the list; in the other a question is written, confirmed and run between the asks.
        Every answer, the history, a saved answer reopened, the tally and the rows kept are the same, byte for byte."""
        fixed = '2026-11-22T00:00:00+00:00'
        kept = {}
        steady = {Q_CANCELLED: [cancelled()], Q_DELIVERED: [said(code_query('0'), '已交付')]}
        for used in (False, True):
            model = ByQuestion(steady)
            with self.service(gateway=model) as (base, out), mock.patch.object(workspace_questions, '_now', lambda: fixed), mock.patch.object(workspace_store, '_now', lambda: fixed):
                team = self.team(base)
                ann, bob, vera = team['ann'], team['bob'], team['vera']
                seen = [raw(ann, 'POST', '/api/workspace/ask', {'question': Q_CANCELLED})]
                before = len(model.requests)
                if used:
                    for question, expect in ((Q_CANCELLED, number(CANCELLED)), (Q_VALID, number(1)), (Q_DELIVERED, number(DELIVERED))):
                        self.write(ann, question, expect)
                        self.confirm(bob, question)
                    self.run_list(bob, 3)
                after = len(model.requests)
                seen += [raw(ann, 'POST', '/api/workspace/ask', {'question': Q_VALID}), raw(vera, 'POST', '/api/workspace/ask', {'question': Q_DELIVERED}),
                         raw(ann, 'POST', '/api/workspace/ask', {'question': Q_DELIVERED}, headers={'Accept-Language': 'en'}),
                         raw(ann, 'GET', '/api/workspace/ask'), raw(ann, 'GET', '/api/workspace/ask/1'), raw(bob, 'GET', '/api/workspace/ask'), raw(ann, 'GET', '/api/workspace/ask/tally')]
                conn = sqlite3.connect(out / 'workspace.sqlite')
                rows = conn.execute('SELECT * FROM qa_question ORDER BY id').fetchall()
                conn.close()
                asked = model.requests[:before] + model.requests[after:]
                kept[used] = (seen, rows, asked)
        self.assertEqual([s for s, _ in kept[False][0]], [200] * 8)
        self.assertEqual(kept[True][0], kept[False][0])
        self.assertEqual(kept[True][1], kept[False][1])
        self.assertEqual(len(kept[False][1]), 4)
        self.assertEqual(kept[True][2], kept[False][2])   # what the model was sent for the person's asks


class StoreTests(unittest.TestCase):
    def test_a_workspace_file_made_before_the_list_opens_and_gains_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'workspace.sqlite'
            conn = open_workspace(path)
            for table in ('needed_question', 'needed_result', 'needed_run'):
                conn.execute(f'DROP TABLE {table}')
            conn.close()
            conn = open_workspace(path)
            try:
                self.assertEqual(needed_questions.listing(conn, None, True)['questions'], [])
                made = needed_questions.write(conn, None, {'question': Q_CANCELLED, 'expect': number(16)})
                self.assertEqual((made['state'], made['expect']), ('proposed', number(16)))
            finally:
                conn.close()


if __name__ == '__main__':
    unittest.main()
