"""Rules that cite their requirement, and a conflict check (ops/cards/cited-rules.md), walked through the real service on made-up fixtures: a test-case table
of a building's door controller and a specification whose three sentences demand three different lock states after the same fault.

- A conditional value rule: "when column A is a (and up to two more such conditions), column X must be v (or one of a list of codes)", counted on every row
  and on every data change like every value rule.
- A citation on a rule: a passage of a confirmed document and a quote code finds in it word for word (at least 4 characters that are not punctuation or
  space). It is part of the rule's definition; when the document is sent back, removed or replaced, the type goes to needs another look and the quote is no
  longer shown. A person who may not read the document sees no trace of the citation.
- A rule may be "report only": its broken rows are counted and listed (with the quote when cited) but never stop the type from being confirmed and never
  make a question refuse. The default is "must hold", as every rule was before.
- A conflict finding: two conditional rules on the same column whose conditions can hold together (no column required equal to two values) and whose required
  values differ. Each finding shows both rules, both quotes and how many rows meet both conditions now, on the type's page and in the review queue. It does
  not block confirming; it is listed until a rule changes or a note "known: asked <who>" is confirmed by a second person."""
import base64
import csv
import io
import json
import sqlite3
import unittest

from ontology_poc_generator import value_rules
from tests.test_workspace_questions import AskModel
from ontology_poc_generator.lang import speaking
from tests.test_two_person import SigningTestCase

EN = {'Accept-Language': 'en'}
CASE_COLUMNS = ['event_id', 'fault', 'mode', 'lock_state']
CASES = [   # (fault, mode, lock state): five power_loss rows, each with a state at most one requirement allows
    ('none', 'day', '0'), ('none', 'night', '1'), ('power_loss', 'day', '1'), ('sensor_fault', 'day', '5'), ('power_loss', 'night', '4'), ('none', 'day', '0'),
    ('power_loss', 'day', '6'), ('sensor_fault', 'night', '5'), ('none', 'night', '1'), ('power_loss', 'night', '0'), ('none', 'day', '0'), ('power_loss', 'day', '5'),
    ('sensor_fault', 'day', '4'), ('none', 'night', '6'), ('none', 'day', '0'),
]
POWER_LOSS_KEYS = [f'EV{i + 1:02d}' for i, c in enumerate(CASES) if c[0] == 'power_loss']
HELD = [c if c[0] != 'power_loss' else (*c[:2], '1') for c in CASES]   # every power_loss row in state 1; 4 and 6 still in the data
SPEC = '''# 门禁控制器规格

DS-1 掉电（power_loss）发生后，门锁状态 lock_state 必须置为 1，门保持上锁。

DS-2 控制器失去供电时，lock_state 应保持为 4，维持掉电前的位置。

DS-3 一旦检测到 power_loss，门锁状态改为 6，等待人工复位。
'''
QUOTES = {'1': '门锁状态 lock_state 必须置为 1', '4': 'lock_state 应保持为 4，维持掉电前的位置', '6': '门锁状态改为 6，等待人工复位'}
STATE_CODES = [{'value': v, 'label': l} for v, l in (('0', '开着'), ('1', '上锁'), ('4', '保持原状'), ('5', '报警'), ('6', '锁死待查'))]


def cases_upload(rows=CASES, name='door_events.csv', overwrite=False) -> dict:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CASE_COLUMNS)
    writer.writerows([f'EV{i + 1:02d}', *r] for i, r in enumerate(rows))
    return {'filename': name, 'content_base64': base64.b64encode(out.getvalue().encode('utf-8')).decode(), **({'target': 'door_events', 'mode': 'overwrite'} if overwrite else {})}


def doc_upload(text=SPEC, name='door-spec.md', builders_only=False) -> dict:
    return {'filename': name, 'content_base64': base64.b64encode(text.encode()).decode(), 'builders_only': builders_only}


def when(value=None, one_of=None, cite=None, conditions=(('fault', 'power_loss'),), report_only=None) -> dict:
    return {'column': 'lock_state', 'check': 'when', 'when': [{'column': c, 'equals': v} for c, v in conditions],
            **({'equals': value} if value is not None else {}), **({'one_of': one_of} if one_of is not None else {}), **({'cite': cite} if cite else {}),
            **({'report_only': report_only} if report_only is not None else {})}


COUNT = {'reasoning': 'test', 'query': {'start': 'door_event', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None}, 'definitions_used': []}


def case_type(rules) -> dict:
    return {'english_name': 'door_event', 'name': '门禁事件', 'dataset': 'door_events', 'key': ['event_id'],
            'properties': [{'column': 'fault'}, {'column': 'mode'}, {'column': 'lock_state', 'name': '门锁状态', 'enum': True}], 'enums': {'lock_state': STATE_CODES}, 'rules': rules}


class CitedCase(SigningTestCase):
    """A service with ann and bob (builders) and vera (a viewer), the test-case table, and the requirements document put forward by ann and confirmed by bob."""

    def start(self, confirm_doc=True, builders_only=False):
        self.model = AskModel(COUNT)
        ctx = self.service(gateway=self.model)
        self.base, self.out = ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        team = self.people(self.base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        self.admin, self.ann, self.bob, self.vera = team['admin'], team['ann'], team['bob'], team['vera']
        self.assertEqual(self.ann.post('/api/workspace/datasets/upload', {'files': [cases_upload()]})[0], 200)
        self.doc = self.put_doc(builders_only=builders_only, confirm=confirm_doc)

    def put_doc(self, text=SPEC, name='door-spec.md', builders_only=False, confirm=True):
        status, doc = self.ann.post('/api/workspace/documents/upload', doc_upload(text, name, builders_only))
        self.assertEqual(status, 200, doc)
        if confirm:
            status, doc = self.bob.post('/api/workspace/documents/confirm', {'id': doc['id'], 'version': doc['version']})
            self.assertEqual(status, 200, doc)
        return doc

    def passage(self, quote, doc=None):
        doc = doc or self.doc
        found = self.ann.get(f'/api/workspace/documents/{doc["id"]}')[1]
        return next(p for p in found['passages'] if quote in p['text'])

    def cite(self, value, doc=None, quote=None):
        quote = quote or QUOTES[value]
        return {'document': (doc or self.doc)['id'], 'passage': self.passage(QUOTES[value], doc)['id'], 'quote': quote}

    def power_loss_rules(self, report_only=None):
        return [when(v, cite=self.cite(v), report_only=report_only) for v in ('1', '4', '6')]

    def ask(self, who=None, **item):
        self.model.item = {**COUNT, **item}
        status, body = (who or self.ann).post('/api/workspace/ask', {'question': '门禁事件有多少？'})
        self.assertEqual(status, 200, body)
        return body

    def page(self, who=None, **more):
        status, body = (who or self.bob).get('/api/workspace/types/door_event', **more)
        self.assertEqual(status, 200, body)
        return body

    def confirm_type(self, who=None):
        page = self.page()
        meanings = next(p for p in page['properties'] if p['column'] == 'lock_state')['meanings']
        if meanings['state'] != 'confirmed':
            status, body = (who or self.bob).post('/api/workspace/types/confirm', {'id': 'door_event', 'column': 'lock_state', 'version': meanings['version'], 'seen': meanings['seen']})
            self.assertEqual(status, 200, body)
            page = self.page()
        return (who or self.bob).post('/api/workspace/types/confirm', {'id': 'door_event', 'version': page['version'], 'seen': page['seen']})

    def db(self):
        conn = sqlite3.connect(self.out / 'workspace.sqlite')
        self.addCleanup(conn.close)
        return conn

    def state(self):
        return self.db().execute("SELECT state, reason FROM element_state WHERE element_id = 'objtype:door_event'").fetchone()


class SameFaultTests(CitedCase):
    def test_three_cited_requirements_on_one_fault_are_three_conflicts_with_both_quotes_and_every_power_loss_row_breaks_two(self):
        self.start()
        status, made = self.ann.post('/api/workspace/types', case_type(self.power_loss_rules(report_only=True)))
        self.assertEqual(status, 200, made)
        self.assertTrue(all('只报告' in w for w in made['warnings'] if '值规则' in w), made['warnings'])
        status, body = self.confirm_type()   # report only: the broken rows are listed, the type is confirmed
        self.assertEqual(status, 200, body)
        page = self.page()
        self.assertEqual(page['state'], 'confirmed')
        self.assertEqual([r['check'] for r in page['rules']], ['when'] * 3)
        self.assertEqual([r['report_only'] for r in page['rules']], [True] * 3)
        for rule, value in zip(page['rules'], ('1', '4', '6')):
            self.assertEqual(rule['says'], f'当“fault”是 power_loss 时，“门锁状态”要是 {value}（只报告）')
            self.assertEqual(rule['cite']['quote'], QUOTES[value])   # the quoted sentence beside the broken rows
            self.assertEqual(rule['cite']['name'], 'door-spec.md')
            self.assertEqual(rule['cite']['passage'], self.passage(QUOTES[value])['id'])
            self.assertRegex(rule['cite']['where'], r'^第 \d+ 段$')
            self.assertEqual(rule['broken'], 4)   # of the five power_loss rows, one has this rule's value
            self.assertTrue(set(map(tuple, rule['examples'])) <= {(k,) for k in POWER_LOSS_KEYS})
        for key in POWER_LOSS_KEYS:
            self.assertGreaterEqual(sum(1 for r in page['rules'] if [key] in r['examples']), 2, key)
        conflicts = page['conflicts']
        self.assertEqual(len(conflicts), 3)
        self.assertEqual(sorted(tuple(c['rules'][i]['index'] for i in (0, 1)) for c in conflicts), [(0, 1), (0, 2), (1, 2)])
        for c in conflicts:
            self.assertEqual(c['rows'], 5)   # the five power_loss rows meet both conditions now
            self.assertEqual(c['column'], 'lock_state')
            a, b = c['rules']
            self.assertEqual({a['cite']['quote'], b['cite']['quote']}, {QUOTES[page['rules'][a['index']]['equals']], QUOTES[page['rules'][b['index']]['equals']]})
            self.assertIn('“门锁状态”', c['says'])
            self.assertIsNone(c['note'])
        # the review queue lists the same three findings, with both quotes and the row count
        queue = self.bob.get('/api/workspace/queue')[1]
        found = [i for i in queue['items'] if i['kind'] == 'conflict']
        self.assertEqual(len(found), 3)
        for item in found:
            text = json.dumps(item, ensure_ascii=False)
            self.assertEqual(item['id'], 'door_event')
            self.assertEqual(item['conflict']['rows'], 5)
            self.assertEqual(sum(1 for q in QUOTES.values() if q in text), 2)
            self.assertFalse(item['can_confirm'])   # nothing to confirm until a note is recorded
        # English
        page_en = self.page(headers=EN)
        self.assertEqual(page_en['rules'][0]['says'], 'When "fault" is power_loss, "门锁状态" must be 1 (report only)')
        self.assertRegex(page_en['rules'][0]['cite']['where'], r'^paragraph \d+$')
        self.assertIn('"门锁状态"', page_en['conflicts'][0]['says'])
        # a count over the type, and a list of its objects, still answer for a builder and a viewer
        for who in (self.ann, self.vera):
            self.assertEqual(self.ask(who)['status'], 'answered', who)
            self.assertEqual(self.ask(who, query={**COUNT['query'], 'list': {}})['status'], 'answered')
        # new data that breaks them more does not send the type back
        self.assertEqual(self.ann.post('/api/workspace/datasets/upload', {'files': [cases_upload(CASES + [('power_loss', 'day', '0')], overwrite=True)]})[0], 200)
        self.assertEqual(self.state()[0], 'confirmed')
        self.assertEqual(self.page()['rules'][0]['broken'], 5)
        self.assertEqual(self.ask()['status'], 'answered')

    def test_report_only_rules_broken_beside_a_must_hold_rule_that_holds_never_make_a_question_refuse(self):
        self.start()
        rules = [*self.power_loss_rules(report_only=True), {'column': 'fault', 'check': 'not_empty'}]
        self.assertEqual(self.ann.post('/api/workspace/types', case_type(rules))[0], 200)
        status, body = self.confirm_type()
        self.assertEqual(status, 200, body)
        self.assertEqual(self.ask()['status'], 'answered')
        self.assertEqual(self.ann.post('/api/workspace/datasets/upload', {'files': [cases_upload(CASES + [('power_loss', 'day', '0')], overwrite=True)]})[0], 200)
        self.assertEqual(self.state()[0], 'confirmed')
        for who in (self.ann, self.vera):
            self.assertEqual(self.ask(who)['status'], 'answered')
            self.assertEqual(self.ask(who, query={**COUNT['query'], 'list': {}})['status'], 'answered')
        item = next(i for i in self.bob.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'conflict')
        self.assertEqual(item['conflict']['rows'], 6)

    def test_a_must_hold_rule_beside_report_only_rules_still_blocks_and_refuses(self):
        self.start()
        rules = [*self.power_loss_rules(report_only=True), {'column': 'mode', 'check': 'not_empty'}]
        self.assertEqual(self.ann.post('/api/workspace/types', case_type(rules))[0], 200)
        status, body = self.confirm_type()
        self.assertEqual(status, 200, body)
        self.assertEqual(self.ann.post('/api/workspace/datasets/upload', {'files': [cases_upload(CASES + [('none', '', '0')], overwrite=True)]})[0], 200)
        state, reason = self.state()
        self.assertEqual(state, 'needs_look')
        self.assertIn('“mode”不能为空', reason)
        self.assertNotIn('只报告', reason)   # only the rule that must hold is a reason
        self.assertEqual(self.ask()['status'], 'refused')
        page = self.page()
        status, body = self.bob.post('/api/workspace/types/confirm', {'id': 'door_event', 'version': page['version'], 'seen': page['seen']})
        self.assertEqual(status, 409, body)
        self.assertNotIn('power_loss', body['error'])
        # the same rule marked report only: the type confirms with the row listed, and the question answers
        rules[-1] = {**rules[-1], 'report_only': True}
        self.assertEqual(self.ann.post('/api/workspace/types/update', {**case_type(rules), 'id': 'door_event', 'version': page['version']})[0], 200)
        status, body = self.confirm_type()
        self.assertEqual(status, 200, body)
        self.assertEqual(self.page()['rules'][-1]['broken'], 1)
        self.assertEqual(self.ask()['status'], 'answered')
        status, body = self.ann.post('/api/workspace/types/update', {**case_type([{**rules[-1], 'report_only': 'yes'}]), 'id': 'door_event', 'version': self.page()['version']})
        self.assertEqual(status, 400, body)
        self.assertIn('report_only', body['error'])

    def test_a_conflict_does_not_block_confirming_when_no_row_breaks_a_rule(self):
        self.start()
        rows = [c if c[0] != 'power_loss' else ('none', *c[1:]) for c in CASES]
        self.assertEqual(self.ann.post('/api/workspace/datasets/upload', {'files': [cases_upload(rows, overwrite=True)]})[0], 200)
        self.assertEqual(self.ann.post('/api/workspace/types', case_type(self.power_loss_rules()))[0], 200)
        self.assertEqual([c['rows'] for c in self.page()['conflicts']], [0, 0, 0])
        status, body = self.confirm_type()
        self.assertEqual(status, 200, body)
        self.assertEqual(len(self.page()['conflicts']), 3)   # still listed once confirmed
        self.assertEqual(len([i for i in self.bob.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'conflict']), 3)

    def test_rows_that_break_a_conditional_rule_block_confirming_and_new_data_that_breaks_it_sends_the_type_back(self):
        self.start()
        self.assertEqual(self.ann.post('/api/workspace/datasets/upload', {'files': [cases_upload(HELD, overwrite=True)]})[0], 200)
        self.assertEqual(self.ann.post('/api/workspace/types', case_type([when('1', cite=self.cite('1'))]))[0], 200)
        self.assertNotIn('conflicts', self.page())
        status, body = self.confirm_type()
        self.assertEqual(status, 200, body)
        self.assertEqual(self.ann.post('/api/workspace/datasets/upload', {'files': [cases_upload(overwrite=True)]})[0], 200)
        state, reason = self.state()
        self.assertEqual(state, 'needs_look')
        self.assertIn('当“fault”是 power_loss 时，“门锁状态”要是 1', reason)
        self.assertIn('4 行不满足', reason)
        page = self.page()
        status, body = self.bob.post('/api/workspace/types/confirm', {'id': 'door_event', 'version': page['version'], 'seen': page['seen']})
        self.assertEqual(status, 409, body)


class CitationRefusedTests(CitedCase):
    def refused(self, cite, who=None):
        status, body = (who or self.ann).post('/api/workspace/types', case_type([when('1', cite=cite)]))
        self.assertEqual(status, 400, body)
        self.assertIsNone(self.db().execute("SELECT 1 FROM element_state WHERE element_id = 'objtype:door_event'").fetchone())
        return body['error']

    def test_a_quote_that_is_not_word_for_word_is_refused(self):
        self.start()
        good = self.cite('1')
        for quote in ('门锁状态 lock_state 必须置为 2', '门锁状态  lock_state 必须置为 1', '门锁状态lock_state必须置为1', 'lock_state 应保持为 4，维持掉电前的位置'):   # changed, a space more, spaces squashed, another passage's words
            self.assertIn('原文', self.refused({**good, 'quote': quote}))
        self.assertIn('至少', self.refused({**good, 'quote': '1，门保'}))   # fewer than 4 characters that are not punctuation or space
        self.assertIn('段落', self.refused({**good, 'passage': 'p99'}))
        self.assertIn('一条规则最多引用一处', self.refused([good, good]))
        status, body = self.ann.post('/api/workspace/types', case_type([when('1', cite={**good, 'quote': '门锁状态 lock_state 必须置为 2'})]), headers=EN)
        self.assertEqual(status, 400)
        self.assertIn('word for word', body['error'])
        status, made = self.ann.post('/api/workspace/types', case_type([when('1', cite=good)]))
        self.assertEqual(status, 200, made)
        kept = json.loads(self.db().execute("SELECT content_json FROM element_state WHERE element_id = 'objtype:door_event'").fetchone()[0])['rules'][0]['cite']
        self.assertEqual({k: kept[k] for k in ('document', 'passage', 'quote')}, good)

    def test_a_citation_to_a_waiting_document_is_refused(self):
        self.start(confirm_doc=False)
        error = self.refused(self.cite('1'))
        self.assertIn('还没有确认', error)
        status, body = self.ann.post('/api/workspace/types', case_type([when('1', cite=self.cite('1'))]), headers=EN)
        self.assertIn('not confirmed', body['error'])
        self.assertIn('没有这份文档', self.refused({**self.cite('1'), 'document': 'document:0000000000000000'}))

    def test_a_citation_to_a_document_sent_back_or_removed_is_refused(self):
        self.start()
        good = self.cite('1')
        status, back = self.bob.post('/api/workspace/documents/send-back', {'id': self.doc['id'], 'version': self.doc['version'], 'reason': '版本旧了'})
        self.assertEqual(status, 200, back)
        self.assertIn('还没有确认', self.refused(good))
        self.assertEqual(self.bob.post('/api/workspace/documents/remove', {'id': back['id'], 'version': back['version'], 'reason': '作废'})[0], 200)
        self.assertIn('没有这份文档', self.refused(good))

    def test_a_citation_on_every_kind_of_rule_and_the_rule_limits(self):
        self.start()
        good = self.cite('1')
        status, made = self.ann.post('/api/workspace/types', case_type([{'column': 'fault', 'check': 'not_empty', 'cite': good}]))
        self.assertEqual(status, 200, made)
        self.assertEqual(self.page()['rules'][0]['cite']['quote'], QUOTES['1'])
        four = [('fault', 'power_loss'), ('mode', 'day'), ('event_id', 'EV01'), ('fault', 'x')]
        for rules, words in (([when('1', conditions=four)], '最多 3 个条件'), ([when('1', conditions=(('lock_state', '1'),))], '不能是它自己'),
                             ([when('1', one_of=['1'])], '只能写一个'), ([when()], '要写'), ([when('1', conditions=())], '至少要有一个条件'),
                             ([when('1', conditions=(('fault', 'power_loss'), ('fault', 'none')))], '写了两次'), ([when('1', conditions=(('没有', 'x'),))], '不是这个对象类型的属性'),
                             ([when(one_of=[])], '要写'), ([when('1'), when('1')], '写了两次')):
            status, body = self.ann.post('/api/workspace/types/update', {**case_type(rules), 'id': 'door_event', 'version': self.page()['version']})
            self.assertEqual(status, 400, (rules, body))
            self.assertIn(words, body['error'], rules)


class CitedDocumentMovesTests(CitedCase):
    def confirmed(self, builders_only=False):
        self.start(builders_only=builders_only)
        self.assertEqual(self.ann.post('/api/workspace/types', case_type([when('1', cite=self.cite('1'))]))[0], 200)
        self.assertEqual(self.ann.post('/api/workspace/datasets/upload', {'files': [cases_upload(HELD, overwrite=True)]})[0], 200)
        status, body = self.confirm_type()
        self.assertEqual(status, 200, body)
        self.assertEqual(self.state()[0], 'confirmed')

    def test_sending_back_the_cited_document_sends_the_rule_to_needs_another_look_and_hides_the_quote(self):
        self.confirmed()
        status, back = self.bob.post('/api/workspace/documents/send-back', {'id': self.doc['id'], 'version': self.doc['version'], 'reason': '版本旧了'})
        self.assertEqual(status, 200, back)
        state, reason = self.state()
        self.assertEqual(state, 'needs_look')
        self.assertEqual(reason, '它的定义依据的内容变了，要重新确认')   # the stored reason names no document: every reader of the type's state reads it (a board, an answer)
        rule = self.page()['rules'][0]
        self.assertEqual(rule['cite']['name'], 'door-spec.md')   # the type's page names it, to whoever may read it
        self.assertNotIn('quote', rule['cite'])   # its check result stops showing the quote
        self.assertTrue(rule['cite']['stale'])
        self.assertNotIn(QUOTES['1'], json.dumps(self.page(), ensure_ascii=False))
        page = self.page()
        status, body = self.bob.post('/api/workspace/types/confirm', {'id': 'door_event', 'version': page['version'], 'seen': page['seen']})
        self.assertEqual(status // 100, 4, body)   # not while the document waits
        # the document confirmed again as it was: the quote is back, and a second person confirms the type again
        status, again = self.bob.post('/api/workspace/documents/confirm', {'id': back['id'], 'version': back['version']})
        self.assertEqual(status, 200, again)
        self.assertEqual(self.page()['rules'][0]['cite']['quote'], QUOTES['1'])
        page = self.page()
        status, body = self.bob.post('/api/workspace/types/confirm', {'id': 'door_event', 'version': page['version'], 'seen': page['seen']})
        self.assertEqual(status, 200, body)

    def test_removing_or_replacing_the_cited_document_sends_the_rule_to_needs_another_look(self):
        self.confirmed()
        newer = self.put_doc(SPEC.replace('DS-3', 'DS-4'), confirm=False)   # a new version of the same file
        self.assertEqual(self.state()[0], 'needs_look')
        self.assertNotIn('quote', self.page()['rules'][0]['cite'])
        self.bob.post('/api/workspace/documents/confirm', {'id': newer['id'], 'version': newer['version']})
        self.assertNotIn('quote', self.page()['rules'][0]['cite'])   # written against the old words: the rule is cited again by saving it
        self.assertEqual(self.ann.post('/api/workspace/types/update', {**case_type([when('1', cite=self.cite('1'))]), 'id': 'door_event', 'version': self.page()['version']})[0], 200)
        self.assertEqual(self.page()['rules'][0]['cite']['quote'], QUOTES['1'])
        status, body = self.confirm_type()
        self.assertEqual(status, 200, body)
        doc = self.ann.get(f'/api/workspace/documents/{self.doc["id"]}')[1]
        self.assertEqual(self.bob.post('/api/workspace/documents/remove', {'id': doc['id'], 'version': doc['version'], 'reason': '作废'})[0], 200)
        self.assertEqual(self.state()[0], 'needs_look')
        rule = self.page()['rules'][0]
        self.assertTrue(rule['cite']['stale'])
        self.assertNotIn('quote', rule['cite'])

    def test_a_viewer_who_may_not_read_the_document_sees_no_citation_at_all(self):
        self.confirmed(builders_only=True)
        never = when('4', cite=self.cite('4'), conditions=(('fault', 'power_loss'), ('mode', 'maintenance')))   # no row is in maintenance: it disagrees with the first rule and no row breaks it
        self.assertEqual(self.ann.post('/api/workspace/types/update', {**case_type([when('1', cite=self.cite('1')), never]), 'id': 'door_event', 'version': self.page()['version']})[0], 200)
        status, body = self.confirm_type()
        self.assertEqual(status, 200, body)
        self.assertEqual(self.page()['rules'][0]['cite']['quote'], QUOTES['1'])   # a builder reads it
        for headers in ({}, EN):
            status, page = self.vera.get('/api/workspace/types/door_event', headers=headers)
            self.assertEqual(status, 200, page)
            self.assertEqual(len(page['rules']), 2)
            self.assertEqual(len(page['conflicts']), 1)
            text = json.dumps(page, ensure_ascii=False)
            for trace in ('cite', 'door-spec.md', 'document:', QUOTES['1'], QUOTES['4'], '引用', 'quote', 'citation'):
                self.assertNotIn(trace, text, (trace, headers))
            for c in page['conflicts']:
                self.assertEqual(set(c['rules'][0]), set(c['rules'][1]))
            for path in ('/api/workspace/agent/definitions', '/api/workspace/agent/standing', '/api/workspace/types', '/api/workspace/types/door_event/log'):
                text = json.dumps(self.vera.get(path, headers=headers)[1], ensure_ascii=False)
                for trace in ('door-spec.md', QUOTES['1'], 'document:'):
                    self.assertNotIn(trace, text, (path, trace))
        # after a send-back and a new confirmation, the viewer's log still names no document
        doc = self.ann.get(f'/api/workspace/documents/{self.doc["id"]}')[1]
        status, back = self.bob.post('/api/workspace/documents/send-back', {'id': doc['id'], 'version': doc['version'], 'reason': '版本旧了'})
        self.assertEqual(status, 200)
        self.bob.post('/api/workspace/documents/confirm', {'id': back['id'], 'version': back['version']})
        status, body = self.confirm_type()
        self.assertEqual(status, 200, body)
        log = json.dumps(self.vera.get('/api/workspace/types/door_event/log')[1], ensure_ascii=False)
        self.assertNotIn('door-spec.md', log)
        self.assertIn('door-spec.md', json.dumps(self.bob.get('/api/workspace/types/door_event/log')[1], ensure_ascii=False))

    def test_a_viewer_who_may_read_the_document_sees_the_citation(self):
        self.confirmed()
        status, page = self.vera.get('/api/workspace/types/door_event')
        self.assertEqual(status, 200)
        self.assertEqual(page['rules'][0]['cite']['quote'], QUOTES['1'])
        self.assertNotIn('stale', page['rules'][0]['cite'])


class KnownNoteTests(CitedCase):
    def conflicted(self):
        self.start()
        self.assertEqual(self.ann.post('/api/workspace/types', case_type(self.power_loss_rules()))[0], 200)
        return self.page()['conflicts'][0]

    def test_a_known_note_needs_a_second_person_and_then_the_finding_is_no_longer_listed(self):
        finding = self.conflicted()
        self.assertEqual(self.vera.post('/api/workspace/types/conflict-note', {'id': 'door_event', 'key': finding['key'], 'asked': '王工'})[0], 403)
        for asked in ('', ' ', 'x' * 81, '王工\n李工'):
            self.assertEqual(self.ann.post('/api/workspace/types/conflict-note', {'id': 'door_event', 'key': finding['key'], 'asked': asked})[0], 400, asked)
        self.assertEqual(self.ann.post('/api/workspace/types/conflict-note', {'id': 'door_event', 'key': 'nope', 'asked': '王工'})[0], 404)
        status, body = self.ann.post('/api/workspace/types/conflict-note', {'id': 'door_event', 'key': finding['key'], 'asked': '王工'})
        self.assertEqual(status, 200, body)
        listed = next(c for c in self.page()['conflicts'] if c['key'] == finding['key'])   # still listed while the note waits
        self.assertEqual(listed['note']['asked'], '王工')
        self.assertEqual(listed['note']['proposed_by'], 'Ann')
        self.assertEqual(listed['note']['state'], 'checked')
        self.assertFalse(self.page(self.ann)['conflicts'][[c['key'] for c in self.page(self.ann)['conflicts']].index(finding['key'])]['note']['may_confirm'])
        self.assertTrue(listed['note']['may_confirm'])
        status, body = self.ann.post('/api/workspace/types/conflict-note/confirm', {'id': 'door_event', 'key': finding['key']})
        self.assertEqual(status, 403, body)   # whoever wrote the note cannot confirm it
        queue = self.bob.get('/api/workspace/queue')[1]
        item = next(i for i in queue['items'] if i['kind'] == 'conflict' and i['key'] == finding['key'])
        self.assertTrue(item['can_confirm'])
        status, body = self.bob.post('/api/workspace/types/conflict-note/confirm', {'id': 'door_event', 'key': finding['key']})
        self.assertEqual(status, 200, body)
        self.assertEqual(len(self.page()['conflicts']), 2)
        self.assertNotIn(finding['key'], [c['key'] for c in self.page()['conflicts']])
        self.assertEqual(len([i for i in self.bob.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'conflict']), 2)
        log = self.bob.get('/api/workspace/types/door_event/log')[1]['log']
        self.assertEqual([e['change'] for e in log if e['change'].startswith('conflict_note')], ['conflict_note_confirmed', 'conflict_note'])
        # a rule changed: the pair is another one, listed again
        rules = self.power_loss_rules()
        rules[0] = when('1', cite=self.cite('1'), conditions=(('fault', 'power_loss'), ('mode', 'day')))
        self.assertEqual(self.ann.post('/api/workspace/types/update', {**case_type(rules), 'id': 'door_event', 'version': self.page()['version']})[0], 200)
        self.assertEqual(len(self.page()['conflicts']), 3)

    def test_with_two_person_confirmation_off_the_note_still_needs_a_second_person(self):
        finding = self.conflicted()
        self.assertEqual(self.admin.post('/api/settings', {'two_person': False})[0], 200)
        self.assertEqual(self.ann.post('/api/workspace/types/conflict-note', {'id': 'door_event', 'key': finding['key'], 'asked': '王工'})[0], 200)
        self.assertEqual(self.ann.post('/api/workspace/types/conflict-note/confirm', {'id': 'door_event', 'key': finding['key']})[0], 403)
        self.assertEqual(self.bob.post('/api/workspace/types/conflict-note/confirm', {'id': 'door_event', 'key': finding['key']})[0], 200)


class ConflictLogicTests(unittest.TestCase):
    """What "can hold together" and "required values differ" mean, on the rules alone."""

    def rule(self, conditions, value=None, one_of=None, column='X'):
        return {'column': column, 'check': 'when', 'when': [{'column': c, 'equals': v} for c, v in conditions], **({'equals': value} if value is not None else {}),
                **({'one_of': one_of} if one_of is not None else {})}

    def found(self, *rules):
        return [(i, j) for i, j, _ in value_rules.conflicts(list(rules))]

    def test_conditions_that_can_hold_together_with_different_values_conflict(self):
        self.assertEqual(self.found(self.rule([('A', 'a')], '1'), self.rule([('A', 'a')], '2')), [(0, 1)])
        self.assertEqual(self.found(self.rule([('A', 'a')], '1'), self.rule([('B', 'b')], '2')), [(0, 1)])   # other columns: both can hold on one row
        self.assertEqual(self.found(self.rule([('A', 'a'), ('B', 'b')], '1'), self.rule([('A', 'a'), ('C', 'c')], '2')), [(0, 1)])
        self.assertEqual(self.found(self.rule([('A', 'a')], '1'), self.rule([('A', 'a')], one_of=['1', '2'])), [(0, 1)])   # the required values differ
        self.assertEqual(self.found(self.rule([('A', 'a')], one_of=['2', '1']), self.rule([('A', 'a')], one_of=['1'])), [(0, 1)])
        merged = value_rules.conflicts([self.rule([('A', 'a')], '1'), self.rule([('B', 'b'), ('A', 'a')], '2')])[0][2]
        self.assertEqual(merged, [{'column': 'A', 'equals': 'a'}, {'column': 'B', 'equals': 'b'}])

    def test_conditions_that_cannot_both_hold_or_the_same_values_are_no_conflict(self):
        self.assertEqual(self.found(self.rule([('A', 'a')], '1'), self.rule([('A', 'b')], '2')), [])   # A cannot be a and b
        self.assertEqual(self.found(self.rule([('A', 'a'), ('B', 'b')], '1'), self.rule([('B', 'c')], '2')), [])
        self.assertEqual(self.found(self.rule([('A', 'a')], '1'), self.rule([('B', 'b')], '1')), [])   # the same value
        self.assertEqual(self.found(self.rule([('A', 'a')], one_of=['1', '2']), self.rule([('A', 'a')], one_of=['2', '1'])), [])   # the same list
        self.assertEqual(self.found(self.rule([('A', 'a')], '1'), self.rule([('A', 'a')], '2', column='Y')), [])   # another column
        self.assertEqual(self.found(self.rule([('A', 'a')], '1'), {'column': 'X', 'check': 'not_empty'}), [])   # only conditional rules have a required value

    def test_three_rules_on_one_condition_are_three_pairs(self):
        self.assertEqual(self.found(*(self.rule([('F', 'power_loss')], v) for v in '146')), [(0, 1), (0, 2), (1, 2)])

    def test_what_breaks_a_conditional_rule(self):
        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE t (k, a, b, x)')
        conn.executemany('INSERT INTO t VALUES (?, ?, ?, ?)', [('1', 'a', 'b', '1'), ('2', ' a ', 'b', '2'), ('3', 'a', 'c', '2'), ('4', 'a', 'b', None), ('5', None, 'b', '2'),
                                                                 ('6', 'a', 'b', ' 1 '), ('7', 'A', 'b', '2'), ('8', 'a', 'b', '')])
        rule = self.rule([('a', 'a'), ('b', 'b')], '1', column='x')
        found = value_rules.run(conn, 't', [rule, self.rule([('a', 'a')], one_of=['1', '2'], column='x')], {}, {}, ['k'])
        self.assertEqual(found['rules'][0], {'broken': 3, 'examples': [['2'], ['4'], ['8']]})   # blanks trimmed; an empty value in the situation breaks it; case counts
        self.assertEqual(found['rules'][1], {'broken': 2, 'examples': [['4'], ['8']]})
        with speaking('en'):
            self.assertEqual(value_rules.says(self.rule([('a', 'a'), ('b', 'b')], one_of=['1', '2'], column='x')), 'When "a" is a and "b" is b, "x" must be one of 1, 2')
        with speaking('zh'):
            self.assertEqual(value_rules.says(self.rule([('a', 'a'), ('b', 'b')], one_of=['1', '2'], column='x')), '当“a”是 a、“b”是 b 时，“x”要是 1、2 之一')


if __name__ == '__main__':
    unittest.main()
