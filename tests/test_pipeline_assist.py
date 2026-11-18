"""The assistant in the pipeline editor, through the real service on the planted orders with a model that writes what it is told to write: a sentence over a selected node is a
draft of steps whose code column is filtered by a confirmed meaning (and says which), or, when nobody confirmed the codes, by a question with the values seen and no recommended answer
(even when the model wrote a code); the draft is checked and tried on the data before it is shown, reads only what was selected, and writes nothing. Expected numbers are counted
here from the planted orders (160, 16 of them cancelled)."""
import json
import sqlite3
from collections import Counter
from urllib.parse import quote

from ontology_poc_generator.pipeline_assist import column_facts, disclosure, settle, values_seen
from ontology_poc_generator.pipeline_ops import new_context
from ontology_poc_generator.recognition import ModelCompletion
from tests import test_workspace_store as planted
from tests.test_object_types import MEANINGS, ORDER, TABLES
from tests.test_two_person import SigningTestCase
import unittest

ORDERS = planted.planted_bundle()['sources']['订单']['records']
LIVE = [r for r in ORDERS if r['状态码'] != '2']
CUSTOMERS = len({r['客户编号'] for r in LIVE})
STATUS = Counter(r['状态码'] for r in ORDERS)
SENTENCE = '按客户汇总订单金额，剔除已取消订单'
PIPELINES = '/api/workspace/pipelines'
DRAFT_SPEC = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}]}
AGGREGATE = {'op': 'aggregate', 'group_by': ['客户编号'], 'aggregations': [{'fn': 'sum', 'column': '金额', 'as': '订单金额合计'}]}


class Assistant:
    """Writes the draft a careful model would, from what it is shown: by meaning when it is shown meanings, by a concept when it is not (`careless`: by the code 1, which nobody told it)."""
    model = 'test-model'

    def __init__(self, careless=False, steps=None, explain='先剔除已取消的订单，再按客户汇总金额。'):
        self.requests, self.careless, self.steps, self.explain = [], careless, steps, explain

    def complete_json(self, *, system_prompt, user_prompt, timeout_seconds=None):
        request = json.loads(user_prompt)
        self.requests.append(request)
        if 'steps' in request and 'sentence' not in request:
            return self.reply({'basis': '看了两步', 'text': self.explain})
        if request.get('task') == 'filter':
            return self.reply({'basis': '剔除已取消', 'where': {'all': [self.condition(request['columns'])]}})
        if request.get('task') == 'calc':
            return self.reply({'basis': '金额乘数量', 'name': '折后金额', 'expression': '[金额] * [不存在的列]'})
        status = next(c for c in request['selected'][0]['columns'] if c['name'] == '状态码')
        steps = self.steps or [{'summary': '剔除已取消的订单', 'step': {'type': 'transform', 'from': 'o', 'operators': [{'op': 'filter', 'where': {'all': [self.condition(request['selected'][0]['columns'])]}}]}},
                               {'summary': '按客户汇总订单金额', 'step': {'type': 'transform', 'from': '$1', 'operators': [AGGREGATE]}}]
        return self.reply({'basis': '先过滤再汇总', 'steps': steps})

    def condition(self, columns):
        status = next(c for c in columns if c['name'] == '状态码')
        if 'meanings' in status:
            return {'column': '状态码', 'cmp': 'ne', 'meaning': '已取消'}
        return {'column': '状态码', 'cmp': 'ne', 'value': '1'} if self.careless else {'column': '状态码', 'cmp': 'ne', 'concept': '已取消'}

    @staticmethod
    def reply(body):
        return ModelCompletion('test', 'test-model', json.dumps(body, ensure_ascii=False))


class AssistantTests(SigningTestCase):
    def team(self, base, confirmed=True):
        team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        self.assertEqual(team['ann'].post('/api/workspace/types', ORDER)[0], 200)
        if confirmed:
            shown = team['bob'].get('/api/workspace/types/order')[1]
            meanings = next(p for p in shown['properties'] if p['column'] == '状态码')['meanings']
            status, body = team['bob'].post('/api/workspace/types/confirm', {'id': 'order', 'column': '状态码', 'version': meanings['version'], 'seen': meanings['seen']})
            self.assertEqual(status, 200, body)
        return team

    def draft(self, client, text=SENTENCE, **more):
        return client.post(f'{PIPELINES}/ai/draft', {'spec': DRAFT_SPEC, 'selected': ['o'], 'text': text, **more})

    def test_with_the_codes_confirmed_the_draft_filters_by_the_meaning_cites_it_and_is_tried_on_the_data_before_it_is_shown(self):
        model = Assistant()
        with self.service(gateway=model) as (base, out):
            ann = self.team(base)['ann']
            status, draft = self.draft(ann)
            self.assertEqual(status, 200, draft)
            first, second = draft['steps']
            self.assertEqual(first['step']['operators'][0]['where'], {'all': [{'column': '状态码', 'cmp': 'ne', 'meaning': '已取消'}]})
            self.assertEqual((first['summary'], first['rows_in'], first['rows_out']), ('剔除已取消的订单', [160], len(LIVE)))
            self.assertEqual((second['rows_in'], second['rows_out']), ([len(LIVE)], CUSTOMERS))
            self.assertEqual((first['id'], second['id'], second['step']['from']), ('ai1', 'ai2', 'ai1'))
            self.assertEqual(draft['questions'], [])
            self.assertEqual(draft['check']['ok'], True)
            self.assertEqual([c['text'] for c in draft['cites']], ['「状态码」的含义“已取消”是代码 2（已确认，Bob）'])
            self.assertEqual(draft['label'], 'AI 写的草稿，用不用由你定')
            [cited] = draft['assumptions']   # a confirmed meaning is a confirmed assumption that links to its definition
            self.assertEqual((cited['status'], cited['definition'], cited['text']), ('confirmed', 'enum:order:状态码', draft['cites'][0]['text']))
            self.assertEqual([x['key'] for x in draft['self_check']['done']], ['columns', 'dry', 'counts', 'cites'])
            seen = model.requests[0]['selected'][0]['columns']
            status_column = next(c for c in seen if c['name'] == '状态码')
            self.assertEqual((status_column['code'], status_column['meanings']), (True, {m['label']: [m['value']] for m in MEANINGS}))
            self.assertIn('状态码', draft['sees']['values_sent'])
            self.assertNotIn('金额', draft['sees']['values_sent'])   # a figure column has too many values to be shown
            self.assertIn('每个取值和行数', draft['sees']['text'])
            self.assertEqual(ann.get(PIPELINES)[1]['pipelines'], [])   # nothing was written

    def test_with_the_codes_not_confirmed_it_asks_which_code_with_the_values_seen_and_recommends_none(self):
        model = Assistant()
        with self.service(gateway=model) as (base, out):
            ann = self.team(base, confirmed=False)['ann']
            status, draft = self.draft(ann)
            self.assertEqual(status, 200, draft)
            asked = next(c for c in model.requests[0]['selected'][0]['columns'] if c['name'] == '状态码')
            self.assertEqual((asked['code'], 'meanings' in asked, 'values_seen' in asked), (True, False, False))   # nothing for it to guess from
            [question] = draft['questions']
            self.assertEqual((question['column'], question['concept'], question['recommended']), ('状态码', '已取消', None))
            self.assertEqual(question['evidence'], f'未确认：见过 0、1、2（{STATUS["0"]} 行、{STATUS["1"]} 行、{STATUS["2"]} 行）')
            self.assertEqual([o['value'] for o in question['options']], ['0', '1', '2'])
            self.assertEqual(draft['steps'][0]['step']['operators'], [])   # the filter is not written until a code is chosen
            self.assertEqual(draft['steps'][0]['rows_out'], 160)
            self.assertEqual(draft['cites'], [])
            self.assertEqual([(x['status'], x['question']) for x in draft['assumptions']], [('open', question['id'])])
            self.assertEqual([x['key'] for x in draft['self_check']['not_done']], ['open', 'fullRun', 'saved'])
            # answering re-checks with code and calls no model: the answer is now a confirmed assumption
            calls = len(model.requests)
            again = self.draft(ann, raw=draft['raw'], answers={question['id']: ['2']})[1]
            self.assertEqual(len(model.requests), calls)
            self.assertEqual([(x['status'], x['by']) for x in again['assumptions']], [('confirmed', 'you')])
            self.assertNotIn('open', [x['key'] for x in again['self_check']['not_done']])

    def test_a_code_the_model_wrote_that_the_sentence_does_not_say_is_not_used(self):
        model = Assistant(careless=True)
        with self.service(gateway=model) as (base, out):
            ann = self.team(base, confirmed=False)['ann']
            draft = self.draft(ann)[1]
            self.assertEqual(draft['steps'][0]['step']['operators'], [])
            self.assertEqual((draft['questions'][0]['recommended'], draft['questions'][0]['concept']), (None, None))
            self.assertIn('未确认：见过 0、1、2', draft['questions'][0]['evidence'])
            # but a code the person wrote is theirs
            written = self.draft(ann, '剔除状态码是 1 的订单')[1]
            self.assertEqual(written['steps'][0]['step']['operators'][0]['where'], {'all': [{'column': '状态码', 'cmp': 'ne', 'value': '1'}]})
            self.assertEqual(written['steps'][0]['rows_out'], 160 - STATUS['1'])

    def test_a_digit_the_sentence_happens_to_contain_is_not_the_person_writing_the_code(self):
        model = Assistant(careless=True)   # writes the code 1 whatever it is told
        with self.service(gateway=model) as (base, out):
            ann = self.team(base, confirmed=False)['ann']
            draft = self.draft(ann, '剔除近 12 个月里已取消的订单')[1]
            self.assertEqual(draft['steps'][0]['step']['operators'], [])   # nothing is written for a guessed code
            self.assertEqual([q['column'] for q in draft['questions']], ['状态码'])
            self.assertEqual(draft['questions'][0]['recommended'], None)
            self.assertIn('未确认：见过 0、1、2', draft['questions'][0]['evidence'])

    def test_answering_the_question_writes_the_filter_without_asking_the_model_again(self):
        model = Assistant()
        with self.service(gateway=model) as (base, out):
            ann = self.team(base, confirmed=False)['ann']
            first = self.draft(ann)[1]
            asked = len(model.requests)
            status, second = self.draft(ann, raw=first['raw'], answers={first['questions'][0]['id']: ['2']})
            self.assertEqual(status, 200, second)
            self.assertEqual(len(model.requests), asked)
            self.assertEqual(second['steps'][0]['step']['operators'][0]['where'], {'all': [{'column': '状态码', 'cmp': 'ne', 'value': '2'}]})
            self.assertEqual((second['steps'][0]['rows_out'], second['steps'][1]['rows_out'], second['questions']), (len(LIVE), CUSTOMERS, []))

    def test_a_step_that_reads_a_node_that_was_not_selected_or_a_column_that_is_not_there_does_not_stand_and_the_words_say_why(self):
        outside = [{'summary': '读别处', 'step': {'type': 'transform', 'from': '另一个', 'operators': []}}]
        wrong = [{'summary': '汇总', 'step': {'type': 'transform', 'from': 'o', 'operators': [{**AGGREGATE, 'group_by': ['不存在']}]}}]
        with self.service(gateway=Assistant(steps=outside)) as (base, out):
            ann = self.team(base)['ann']
            draft = self.draft(ann)[1]
            self.assertEqual((draft['steps'], draft['check']['ok']), ([], False))
            self.assertIn('读了没有选中的节点「另一个」', draft['check']['error'])
        with self.service(gateway=Assistant(steps=wrong)) as (base, out):
            ann = self.team(base)['ann']
            draft = self.draft(ann)[1]
            self.assertEqual(draft['check']['ok'], False)
            self.assertIn('没有列「不存在」', draft['check']['error'])
            self.assertEqual([s['id'] for s in draft['steps']], ['ai1'])   # still shown, with why it cannot be applied
        with self.service(gateway=Assistant()) as (base, out):
            ann = self.team(base)['ann']
            self.assertEqual(ann.post(f'{PIPELINES}/ai/draft', {'spec': DRAFT_SPEC, 'selected': [], 'text': SENTENCE})[0], 400)
            self.assertEqual(ann.post(f'{PIPELINES}/ai/draft', {'spec': DRAFT_SPEC, 'selected': ['nope'], 'text': SENTENCE})[0], 400)

    def test_a_column_a_builder_keeps_from_the_model_is_shown_by_name_and_type_only(self):
        model = Assistant()
        with self.service(gateway=model) as (base, out):
            ann = self.team(base)['ann']
            self.assertEqual(ann.post('/api/workspace/types/privacy', {'id': 'order', 'column': '状态码', 'hide_values': True})[0], 200)
            self.draft(ann)
            asked = next(c for c in model.requests[0]['selected'][0]['columns'] if c['name'] == '状态码')
            self.assertEqual(asked, {'name': '状态码', 'type': 'integer', 'values_withheld': True})

    def test_a_sentence_becomes_a_filter_or_an_expression_for_the_columns_the_operator_reads_and_the_expression_is_checked(self):
        model = Assistant()
        spec = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}, {'id': 't', 'type': 'transform', 'from': 'o', 'operators': []}]}
        with self.service(gateway=model) as (base, out):
            ann = self.team(base)['ann']
            status, got = ann.post(f'{PIPELINES}/ai/parse', {'spec': spec, 'step': 't', 'operator': 0, 'kind': 'filter', 'text': '剔除已取消订单'})
            self.assertEqual(status, 200, got)
            self.assertEqual((got['where'], got['check']), ({'all': [{'column': '状态码', 'cmp': 'ne', 'meaning': '已取消'}]}, {'ok': True}))
            self.assertEqual(got['cites'][0]['codes'], ['2'])
            status, got = ann.post(f'{PIPELINES}/ai/parse', {'spec': spec, 'step': 't', 'operator': 0, 'kind': 'calc', 'text': '金额乘数量'})
            self.assertEqual(status, 200, got)
            self.assertEqual((got['name'], got['check']['ok']), ('折后金额', False))
            self.assertIn('不存在的列', got['check']['error'])

    def test_with_the_codes_not_confirmed_a_filter_sentence_asks_instead_of_choosing(self):
        with self.service(gateway=Assistant(careless=True)) as (base, out):
            ann = self.team(base, confirmed=False)['ann']
            spec = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}, {'id': 't', 'type': 'transform', 'from': 'o', 'operators': []}]}
            got = ann.post(f'{PIPELINES}/ai/parse', {'spec': spec, 'step': 't', 'operator': 0, 'kind': 'filter', 'text': '剔除已取消订单'})[1]
            self.assertEqual((got['where'], got['questions'][0]['recommended']), (None, None))
            self.assertEqual(got['check']['ok'], False)
            answered = ann.post(f'{PIPELINES}/ai/parse', {'spec': spec, 'step': 't', 'operator': 0, 'kind': 'filter', 'text': '剔除已取消订单', 'raw': got['raw'], 'answers': {got['questions'][0]['id']: ['2']}})[1]
            self.assertEqual((answered['where'], answered['check']), ({'all': [{'column': '状态码', 'cmp': 'ne', 'value': '2'}]}, {'ok': True}))

    def test_the_explanation_is_labelled_ai_written_and_comes_from_the_settings(self):
        model = Assistant()
        with self.service(gateway=model) as (base, out):
            ann = self.team(base)['ann']
            spec = {'steps': [*DRAFT_SPEC['steps'], {'id': 't', 'type': 'transform', 'from': 'o', 'operators': [AGGREGATE]}]}
            status, got = ann.post(f'{PIPELINES}/ai/explain', {'spec': spec, 'selected': ['t']})
            self.assertEqual(status, 200, got)
            self.assertEqual((got['text'], got['label']), ('先剔除已取消的订单，再按客户汇总金额。', 'AI 写的说明，供读的人参考；以步骤的设置为准'))
            sent = model.requests[-1]['steps']
            self.assertEqual([s['id'] for s in sent], ['t'])
            self.assertNotIn('160', json.dumps(sent))   # settings, not rows

    def test_the_explanation_says_what_it_sends_and_a_raw_that_is_not_what_the_last_answer_returned_is_refused_in_words(self):
        model = Assistant()
        with self.service(gateway=model) as (base, out):
            ann = self.team(base, confirmed=False)['ann']
            spec = {'steps': [*DRAFT_SPEC['steps'], {'id': 't', 'type': 'transform', 'from': 'o', 'operators': [AGGREGATE]}]}
            said = ann.post(f'{PIPELINES}/ai/explain', {'spec': spec, 'selected': ['t']})[1]
            self.assertIn('具体取值', said['sees']['text'])   # a filter's settings can hold a customer's name: that goes too
            self.assertIn('不发数据行', said['sees']['text'])
            node = {'spec': {'steps': [*DRAFT_SPEC['steps'], {'id': 't', 'type': 'transform', 'from': 'o', 'operators': []}]}, 'step': 't', 'operator': 0, 'kind': 'filter', 'text': '剔除已取消订单'}
            for raw in ({'where': {'column': '状态码', 'cmp': 'in', 'values': 5}}, {'where': {'column': ['x'], 'cmp': 'eq'}}, {'where': {'column': {'a': 1}, 'cmp': 'eq'}}):
                status, body = ann.post(f'{PIPELINES}/ai/parse', {**node, 'raw': raw})
                self.assertEqual(status, 400, (raw, body))
                self.assertIn('上一次返回的', body['error'])
            for raw in ({'steps': 'x'}, {'steps': [5]}):
                self.assertLess(self.draft(ann, raw=raw)[0], 500, raw)   # said in the draft's own words
            bad = {'steps': [{'step': {'type': 'transform', 'from': 'o', 'operators': [{'op': 'filter', 'where': {'column': '状态码', 'cmp': 'in', 'values': 5}}]}}]}
            status, body = self.draft(ann, raw=bad)
            self.assertEqual(status, 400, body)
            self.assertIn('上一次返回的', body['error'])

    def test_someone_kept_from_the_input_gets_no_draft_no_filter_and_no_explanation_and_the_model_is_not_asked(self):
        model = Assistant()
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ids = {u['display_name'].lower(): u['id'] for u in team['admin'].get('/api/users')[1]['users']}
            self.assertEqual(team['admin'].post('/api/workspace/permissions', {'type': 'order', 'visible_to': [ids['ann']]})[0], 200)
            bob = team['bob']
            spec = {'steps': [*DRAFT_SPEC['steps'], {'id': 't', 'type': 'transform', 'from': 'o', 'operators': []}]}
            self.assertEqual(bob.post(f'{PIPELINES}/ai/draft', {'spec': DRAFT_SPEC, 'selected': ['o'], 'text': SENTENCE})[0], 404)
            self.assertEqual(bob.post(f'{PIPELINES}/ai/parse', {'spec': spec, 'step': 't', 'operator': 0, 'kind': 'filter', 'text': '剔除已取消订单'})[0], 404)
            self.assertEqual(bob.post(f'{PIPELINES}/ai/explain', {'spec': spec, 'selected': ['t']})[0], 404)
            self.assertEqual(model.requests, [])
            self.assertEqual(team['vera'].post(f'{PIPELINES}/ai/draft', {'spec': DRAFT_SPEC, 'selected': ['o'], 'text': SENTENCE})[0], 403)

    def test_without_a_model_the_assistant_says_so(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            status, body = self.draft(ann)
            self.assertEqual(status, 409)
            self.assertIn('没有模型凭据', body['error'])


class SettleTests(unittest.TestCase):
    """What stands of a code the model wrote, with no server: a confirmed meaning behind it, the person's answer, or the sentence saying it next to the column's name."""
    SEEN = {'状态码': [{'value': '1', 'rows': 100}, {'value': '2', 'rows': 16}]}

    def settle(self, sentence, node, meanings=None, answers=None):
        facts = {'状态码': {'name': '状态码', 'type': 'integer', 'code': True, **({'meanings': meanings} if meanings else {})}}
        questions, cites = {}, []
        got = settle(node, facts, self.SEEN, sentence, answers or {}, questions, cites, {'状态码': 'Bob'})
        return got, questions, cites

    def test_a_code_stands_when_the_sentence_states_it_next_to_the_column_and_not_when_the_same_digits_turn_up_elsewhere(self):
        node = {'column': '状态码', 'cmp': 'ne', 'value': '2'}
        for sentence in ('剔除状态码≠2的订单', '状态码 是 2 的留下', '状态码为2', '状态码 != 2', '「状态码」等于2'):
            self.assertEqual(self.settle(sentence, node)[0], node, sentence)
        for sentence in ('剔除近 12 个月里已取消的订单', '第 2 批里状态码不对的订单', '状态码是 22 的订单', '2 月的订单，状态码不看'):
            got, questions, _ = self.settle(sentence, node)
            self.assertEqual((got, list(questions)), (None, ['状态码|']), sentence)
        self.assertEqual(self.settle('近 12 个月', {'column': '状态码', 'cmp': 'ne', 'value': '1'})[0], None)

    def test_a_code_behind_a_confirmed_meaning_stands_by_the_meaning_and_a_person_answer_stands(self):
        got, questions, cites = self.settle('剔除已取消的订单', {'column': '状态码', 'cmp': 'ne', 'value': '2'}, meanings={'已取消': ['2'], '已发货': ['1']})
        self.assertEqual((got, questions, [c['meaning'] for c in cites]), ({'column': '状态码', 'cmp': 'ne', 'meaning': '已取消'}, {}, ['已取消']))
        got, questions, _ = self.settle('剔除已取消的订单', {'column': '状态码', 'cmp': 'ne', 'concept': '已取消'}, answers={'状态码|已取消': ['2']})
        self.assertEqual((got, questions), ({'column': '状态码', 'cmp': 'ne', 'value': '2'}, {}))

    def test_a_question_recommends_the_confirmed_meaning_that_looks_like_what_was_asked_for_and_nothing_when_none_does(self):
        meanings = {'已取消': ['2'], '已发货': ['1']}
        got, questions, _ = self.settle('剔除取消的订单', {'column': '状态码', 'cmp': 'ne', 'concept': '取消'}, meanings=meanings)
        self.assertIsNone(got)
        recommended = questions['状态码|取消']['recommended']
        self.assertEqual((recommended['meaning'], recommended['value'], recommended['text']), ('已取消', ['2'], '“已取消”：代码 2（已确认，Bob）'))
        _, questions, _ = self.settle('剔除退款的订单', {'column': '状态码', 'cmp': 'ne', 'concept': '退款'}, meanings=meanings)
        self.assertIsNone(questions['状态码|退款']['recommended'])
        _, questions, _ = self.settle('剔除取消的订单', {'column': '状态码', 'cmp': 'ne', 'concept': '取消'})
        self.assertIsNone(questions['状态码|取消']['recommended'])   # nothing confirmed, nothing to recommend


class WhatTheModelIsShownTests(unittest.TestCase):
    """The values of a column that go to the model with the assistant's request: only a short list of short values, and only from a column nobody keeps from the model."""

    def facts(self, columns, values, ctx=None):
        engine = sqlite3.connect(':memory:')
        engine.execute('CREATE TABLE t (' + ', '.join(f'"{c["name"]}" TEXT' for c in columns) + ')')
        engine.executemany('INSERT INTO t VALUES (' + ', '.join('?' * len(columns)) + ')', values)
        ctx = ctx or new_context()
        return column_facts(columns, ctx, values_seen(engine, 't', columns, ctx))

    def test_at_most_twelve_values_of_at_most_forty_characters_go_and_a_column_with_a_longer_value_goes_by_name_and_type_only(self):
        columns = [{'name': '地区', 'type': 'text'}, {'name': '客户', 'type': 'text'}, {'name': '备注', 'type': 'text'}, {'name': '手机', 'type': 'text', 'unsent': True}]
        rows = [(f'地区{i % 12}', f'客户{i}', '很长的备注' * 9 if i == 3 else '短', f'138{i:08d}') for i in range(24)]
        by_name = {f['name']: f for f in self.facts(columns, rows)}
        self.assertEqual(len(by_name['地区']['values_seen']), 12)   # twelve different values, each short
        self.assertNotIn('values_seen', by_name['客户'])   # twenty-four different values
        self.assertEqual(by_name['备注'], {'name': '备注', 'type': 'text'})   # one value of 45 characters keeps the whole column back
        self.assertEqual(by_name['手机'], {'name': '手机', 'type': 'text', 'values_withheld': True})

    def test_a_code_column_with_more_than_twelve_values_sends_none_though_the_person_is_still_shown_the_first_twelve_to_choose_from(self):
        columns = [{'name': '状态码', 'type': 'text', 'origin': '订单.状态码'}]
        ctx = new_context({'订单.状态码': {'已取消': ['2']}}, {'订单.状态码'})
        engine = sqlite3.connect(':memory:')
        engine.execute('CREATE TABLE t ("状态码" TEXT)')
        engine.executemany('INSERT INTO t VALUES (?)', [(str(i),) for i in range(20)])
        seen = values_seen(engine, 't', columns, ctx)
        self.assertEqual(len(seen['状态码']), 12)
        self.assertNotIn('values_seen', column_facts(columns, ctx, seen)[0])

    def test_the_screen_says_how_few_and_how_short(self):
        text = disclosure([])['text']
        self.assertIn('最多 12 个', text)
        self.assertIn('40 个字', text)
