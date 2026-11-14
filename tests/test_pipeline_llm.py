"""The LLM step of a pipeline: how its prompt is compiled, what the model is asked, how answers are kept and counted (off-list, empty, failed, skipped), checked on
a small table with a model that answers by keyword; and the acceptance walk through the real service on the 45 planted tickets: a classify node is proposed, tried on a
20-row sample with the prompt shown, labelled, counted against the labels, run, run again (only the rows that failed are asked again), and its column cannot be a key or
a confirmed code until the review passed and a second person confirmed. The model is never a real one."""
import json
import sqlite3
from collections import Counter
from urllib.parse import quote

from ontology_poc_generator.pipeline_llm import LlmError, LlmRun, LlmService, check_llm_step, compile_prompt, contract_of, effective, parse_reply
from ontology_poc_generator.pipeline_ops import new_context
from ontology_poc_generator.pipelines import PipelineRunError, check_pipeline, run_pipeline
from ontology_poc_generator.recognition import ModelCompletion, RecognitionError
from ontology_poc_generator.workspace_store import open_workspace
from tests import test_workspace_store as planted
from tests.test_object_types import TABLES
from tests.test_two_person import SigningTestCase

CATEGORIES = ['质量缺陷', '物流破损', '安装调试', '使用咨询', '其他']
TICKETS = planted.planted_bundle()['sources']['售后工单']['records']
TRUTH = {r['问题描述']: r['问题类型'] for r in TICKETS}   # the type the planted ticket was written with
KEYWORDS = (('发热', '质量缺陷'), ('破损', '物流破损'), ('安装', '安装调试'), ('咨询', '使用咨询'))
PIPELINES = '/api/workspace/pipelines'


def keyword_answer(task: str) -> str:
    return next((label for word, label in KEYWORDS if word in task), '其他')


class RowModel:
    """Answers by keyword, remembers every request, and can be made to fail for rows whose task has one of the words in `fail`."""
    model = 'test-model'

    def __init__(self, fail=(), answer=None):
        self.requests, self.fail, self.answer = [], set(fail), answer or keyword_answer

    def complete_json(self, *, system_prompt, user_prompt, timeout_seconds=None):
        request = json.loads(user_prompt)
        self.requests.append(request)
        if any(word in request['task'] for word in self.fail):
            raise RecognitionError('model request failed: boom')
        return ModelCompletion('test', 'test-model', json.dumps({'basis': '看关键词', 'answer': self.answer(request['task'])}, ensure_ascii=False))


def classify_step(**more) -> dict:
    return {'id': 'c', 'type': 'llm', 'from': 't', 'model': 'test-model', 'name': '问题类别', 'template': 'classify', 'context': '售后工单', 'column': '问题描述',
            'categories': CATEGORIES, 'min_match': 17, **more}


TICKET_SPEC = {'steps': [{'id': 't', 'type': 'input', 'dataset': '售后工单'}, classify_step(),
                         {'id': 'out', 'type': 'output', 'from': 'c', 'name': '工单分类', 'key': {'columns': ['工单号']}}]}


def small_table(rows):
    """An engine with one table 评论 (列: 编号, 内容) and the workspace connection the answers are kept on."""
    engine = sqlite3.connect(':memory:')
    engine.execute('CREATE TABLE "评论" ("编号" TEXT, "内容" TEXT, "备注" TEXT)')
    engine.executemany('INSERT INTO "评论" VALUES (?, ?, ?)', rows)
    datasets = {'评论': {'table': '评论', 'rows': len(rows), 'columns': [{'name': n, 'type': 'text'} for n in ('编号', '内容', '备注')]}}
    return engine, datasets


def run_small(engine, datasets, conn, service, spec, mode='run'):
    steps = [{'id': 'i', 'type': 'input', 'dataset': '评论'}, spec]
    ctx = {**new_context(), 'llm': LlmRun(conn, service, 'pipeline:小', mode)}
    return run_pipeline(engine, {'steps': steps}, datasets, ctx=ctx), steps


def llm(**more) -> dict:
    return {'id': 'm', 'type': 'llm', 'from': 'i', 'model': 'test-model', 'name': '结果', 'template': 'empty', 'prompt': '这条评论在抱怨吗：$内容', 'output': 'choice', 'choices': ['是', '否'], **more}


import unittest


class PromptAndStepTests(unittest.TestCase):
    def test_a_field_in_the_prompt_that_is_not_a_column_fails_before_anything_runs_and_the_columns_are_named(self):
        with self.assertRaises(LlmError) as caught:
            compile_prompt('判断 $内容 和 $不存在的列', ['编号', '内容'])
        self.assertIn('没有对应的列', str(caught.exception))
        self.assertIn('编号、内容', str(caught.exception))
        parts, used = compile_prompt('价格是 $$5，看 ${内容} 再答', ['内容', '内'])
        self.assertEqual((used, parts[0]), (['内容'], ('text', '价格是 $5，看 ')))
        self.assertEqual(compile_prompt('看 $内容。', ['内', '内容'])[1], ['内容'])   # the longest name that fits
        with self.assertRaises(LlmError):
            compile_prompt('没有字段的提示', ['内容'])   # the same text for every row asks nothing about the row

    def test_the_step_is_checked_against_the_columns_it_reads_and_adds_marked_columns_and_an_error_column(self):
        columns = [{'name': '内容', 'type': 'text'}, {'name': '编号', 'type': 'text'}]
        out = check_llm_step(llm(), 'm', columns)
        self.assertEqual([(c['name'], c.get('ai'), c['type']) for c in out[2:]], [('结果', True, 'text'), ('结果_错误', True, 'text')])
        for bad, words in ((llm(choices=['是']), '至少 2 个'), (llm(name='内容'), '已经有叫'), (llm(prompt='看 $没有'), '没有对应的列'), (llm(model=''), '要记下用的模型'),
                           (llm(template='翻译'), '模板只有'), (llm(output='table'), '输出类型只有')):
            with self.assertRaises(LlmError) as caught:
                check_llm_step(bad, 'm', columns)
            self.assertIn(words, str(caught.exception))
        with self.assertRaises(LlmError) as caught:
            check_llm_step(llm(), 'm', [{**c, 'unsent': True} if c['name'] == '内容' else c for c in columns])
        self.assertIn('不发送给模型', str(caught.exception))

    def test_an_answer_off_the_list_is_not_an_answer_and_a_number_is_a_number_or_nothing(self):
        eff = effective(llm())
        self.assertEqual(parse_reply(eff, {'answer': '是'})['values'], ['是'])
        off = parse_reply(eff, {'answer': '质量问题'})
        self.assertEqual((off['status'], off['values'], off['message']), ('off_list', None, '不在列表里：质量问题'))
        number = effective(llm(output='number', choices=None))
        self.assertEqual(parse_reply(number, {'answer': 12.5})['values'], [12.5])
        self.assertEqual(parse_reply(number, {'answer': None})['status'], 'unanswered')
        self.assertEqual(parse_reply(number, {'answer': 'abc'})['status'], 'failed')
        extract = effective({'name': '抽取', 'template': 'extract', 'column': '内容', 'fields': [{'name': '型号', 'type': 'text'}, {'name': '数量', 'type': 'number'}]})
        self.assertEqual(parse_reply(extract, {'answer': {'型号': 'E-1', '数量': 3}})['values'], ['E-1', 3])
        self.assertEqual(parse_reply(extract, {'answer': {'型号': None, '数量': None}})['status'], 'unanswered')

    def test_the_contract_changes_with_the_prompt_the_model_and_the_shape_of_the_answer_and_with_nothing_else(self):
        base = contract_of(effective(llm()), 'm1')
        self.assertEqual(base, contract_of(effective(llm(name='换个列名')), 'm1'))
        self.assertNotEqual(base, contract_of(effective(llm()), 'm2'))
        self.assertNotEqual(base, contract_of(effective(llm(prompt='是不是在抱怨：$内容')), 'm1'))
        self.assertNotEqual(base, contract_of(effective(llm(choices=['是', '否', '不确定'])), 'm1'))
        self.assertNotEqual(base, contract_of(effective(llm(output='text')), 'm1'))


class RunTests(unittest.TestCase):
    ROWS = [('1', '太慢了，非常失望', 'a'), ('2', '很好用', 'b'), ('3', '  ', 'c'), ('4', None, 'd'), ('5', '太慢了，非常失望', 'e'), ('6', '一般', 'f')]

    def setUp(self):
        self.engine, self.datasets = small_table(self.ROWS)
        self.conn = open_workspace(':memory:')
        self.addCleanup(self.conn.close)

    def go(self, model, mode='run', **more):
        result, _ = run_small(self.engine, self.datasets, self.conn, LlmService(model), llm(**more), mode)
        return next(n for n in result['nodes'] if n['id'] == 'm')

    def test_rows_with_nothing_in_the_prompt_field_are_skipped_without_a_call_and_equal_rows_share_one_call(self):
        model = RowModel(answer=lambda task: '是' if '太慢' in task else '否')
        node = self.go(model)
        report = node['llm']
        self.assertEqual((report['rows'], report['skipped'], report['answered'], report['called']), (6, 2, 4, 3))
        self.assertEqual(len(model.requests), 3)   # 3 different texts; the two empty rows and the repeated text asked nothing more
        self.assertEqual(node['rows_out'], 6)
        self.assertEqual(node['columns'][-2:], ['结果', '结果_错误'])
        self.assertEqual(node['failures'], {})

    def test_only_the_fields_named_in_the_prompt_leave_the_machine(self):
        model = RowModel(answer=lambda task: '否')
        self.go(model)
        for request in model.requests:
            self.assertEqual(set(request), {'task', 'answer'})
            text = json.dumps(request, ensure_ascii=False)
            for other in ('备注', '编号', 'a', 'f'):
                self.assertNotIn(f'"{other}"', text)
        self.assertEqual({r['task'] for r in model.requests}, {'这条评论在抱怨吗：太慢了，非常失望', '这条评论在抱怨吗：很好用', '这条评论在抱怨吗：一般'})

    def test_an_answer_off_the_list_is_counted_with_what_was_said_and_asked_again_next_time(self):
        model = RowModel(answer=lambda task: '质量问题' if '很好用' in task else '否')
        report = self.go(model)['llm']
        self.assertEqual((report['off_list'], report['off_list_answers'], report['answered']), (1, {'质量问题': 1}, 3))
        again = RowModel(answer=lambda task: '否')
        self.go(again)
        self.assertEqual([r['task'] for r in again.requests], ['这条评论在抱怨吗：很好用'])   # the rows that answered are kept; the off-list one is asked again

    def test_failed_rows_are_counted_not_hidden_and_a_rerun_asks_only_them_and_leaves_the_answered_rows_as_they_were(self):
        first = RowModel(fail=('很好用',), answer=lambda task: '是' if '太慢' in task else '否')
        node = self.go(first)
        self.assertEqual((node['llm']['failed'], node['llm']['answered'], node['failures']), (1, 3, {'ai_failed': 1}))
        second = RowModel(answer=lambda task: '是' if '太慢' in task else '否')
        node = self.go(second)
        self.assertEqual([r['task'] for r in second.requests], ['这条评论在抱怨吗：很好用'])
        self.assertEqual((node['llm']['answered'], node['llm']['from_cache'], node['llm']['called'], node['llm']['failed']), (4, 3, 1, 0))
        third = RowModel(answer=lambda task: '否')
        node = self.go(third)
        self.assertEqual((third.requests, node['llm']['called'], node['llm']['from_cache']), ([], 0, 4))   # nothing left to ask

    def test_trying_a_pipeline_reads_what_is_kept_and_never_calls_the_model(self):
        model = RowModel(answer=lambda task: '否')
        node = self.go(model, mode='cache')
        self.assertEqual(model.requests, [])
        self.assertEqual((node['llm']['pending'], node['llm']['to_call'], node['llm']['answered'], node['llm']['skipped']), (4, 3, 0, 2))
        self.go(model)
        before = len(model.requests)
        node = self.go(model, mode='cache')
        self.assertEqual((len(model.requests), node['llm']['answered'], node['llm']['pending']), (before, 4, 0))

    def test_a_change_of_prompt_or_output_makes_the_kept_answers_stale_and_the_next_run_asks_every_row_again(self):
        self.go(RowModel(answer=lambda task: '否'))
        changed = RowModel(answer=lambda task: '否')
        node = self.go(changed, prompt='这条评论是不是在表扬：$内容')
        self.assertEqual((len(changed.requests), node['llm']['stale_cache'] > 0), (3, True))
        self.assertEqual(self.conn.execute('SELECT COUNT(DISTINCT contract) FROM llm_cache').fetchone()[0], 1)   # the earlier answers were dropped when the new ones were written

    def test_the_column_that_holds_the_error_says_why_a_value_is_empty(self):
        model = RowModel(fail=('一般',), answer=lambda task: '否')
        result, steps = run_small(self.engine, self.datasets, self.conn, LlmService(model), llm(), 'run')
        # run again in cache mode and read the output by a second step that keeps every column
        steps = [*steps, {'id': 'out', 'type': 'output', 'from': 'm', 'name': '结果表'}]
        rows = {}
        ctx = {**new_context(), 'llm': LlmRun(self.conn, LlmService(RowModel(answer=lambda task: '否')), 'pipeline:小', 'cache')}
        run_pipeline(self.engine, {'steps': steps}, self.datasets, ctx=ctx, after=lambda c, node, compiled: rows.update({node['id']: c.execute(f'SELECT 编号, 结果, 结果_错误 FROM {compiled["table"]} ORDER BY 编号').fetchall()}) if node['id'] == 'm' else None)
        by_row = {r[0]: r[1:] for r in rows['m']}
        self.assertEqual(by_row['3'], (None, '跳过：提示用到的列都是空的'))
        self.assertEqual(by_row['4'], (None, '跳过：提示用到的列都是空的'))
        self.assertEqual(by_row['6'], (None, '还没跑'))   # the failed row was not kept, so a read of what is kept finds nothing for it
        self.assertEqual(by_row['2'], ('否', None))

    def test_a_pipeline_run_where_no_model_is_given_says_so_in_words(self):
        with self.assertRaises(ValueError) as caught:
            run_pipeline(self.engine, {'steps': [{'id': 'i', 'type': 'input', 'dataset': '评论'}, llm()]}, self.datasets)
        self.assertIn('不能调用模型', str(caught.exception))


class TicketWalkTests(SigningTestCase):
    def team(self, base):
        team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        return team

    def make(self, client, spec=TICKET_SPEC, name='工单分类'):
        status, body = client.post(PIPELINES, {'name': name, 'description': '给售后工单分类', 'spec': spec})
        self.assertEqual(status, 200, body)
        return body

    def ask(self, client, route, payload, name='工单分类'):
        return client.post(f'{PIPELINES}/{route}', {'id': name, 'step': 'c', **payload})

    def go(self, client, name='工单分类'):
        status, body = client.post(f'{PIPELINES}/run', {'id': name})
        self.assertEqual(status, 200, body)
        return body

    def output(self, out, dataset='工单分类'):
        conn = sqlite3.connect(out / 'workspace.sqlite')
        table = conn.execute('SELECT table_name FROM dataset WHERE name = ? ORDER BY version DESC', (dataset,)).fetchone()[0]
        return {r[0]: r[1:] for r in conn.execute(f'SELECT "工单号", "问题类别", "问题类别_错误" FROM "{table}"')}

    def test_the_node_is_tried_on_a_sample_with_the_prompt_shown_labelled_counted_and_the_state_never_calls_the_model(self):
        model = RowModel()
        with self.service(gateway=model) as (base, out):
            ann = self.team(base)['ann']
            self.make(ann)
            status, state = self.ask(ann, 'llm/state', {})
            self.assertEqual(status, 200, state)
            distinct = len(set(TRUTH))
            self.assertEqual((state['report']['rows'], state['report']['pending'], state['report']['to_call'], state['model_now']), (45, 45, distinct, 'test-model'))
            self.assertEqual((model.requests, state['estimate']['calls'], state['estimate']['cost'], state['basis']), ([], distinct, None, '全部行'))
            shown = ann.post(f'{PIPELINES}/preview', {'id': '工单分类', 'node': 'c'})[1]
            self.assertEqual(model.requests, [])
            self.assertEqual({r[-1] for r in shown['rows']}, {'还没跑'})
            status, trial = self.ask(ann, 'llm/trial', {'mode': 'sample', 'n': 20, 'seed': 7})
            self.assertEqual(status, 200, trial)
            self.assertEqual((len(trial['trials']), trial['basis']), (20, '样本'))
            first = trial['trials'][0]
            self.assertEqual(json.loads(first['prompt']['user'])['task'], f'售后工单。请根据下面「问题描述」的内容分类：\n{first["fields"]["问题描述"]}')
            self.assertEqual(json.loads(first['raw'])['answer'], first['values'][0])
            self.assertIn('basis', first['raw'])
            self.assertLessEqual(len(model.requests), 20)
            labels = [{'fields': t['fields'], 'expected': TRUTH[t['fields']['问题描述']]} for t in trial['trials']]
            status, labelled = self.ask(ann, 'llm/label', {'labels': labels})
            self.assertEqual((status, labelled['saved'], labelled['review']['labelled']), (200, len({t['row_hash'] for t in trial['trials']}), len({t['row_hash'] for t in trial['trials']})), labelled)
            status, review = self.ask(ann, 'llm/review', {})
            self.assertEqual(status, 200, review)
            rows = {t['fields']['问题描述'] for t in trial['trials']}
            expected = sum(keyword_answer(d) == TRUTH[d] for d in rows)
            self.assertEqual((review['total'], review['matched']), (len(rows), expected))
            self.assertEqual(review['passed'], expected >= 17)
            self.assertEqual(review['review']['current'], True)

    def test_a_run_counts_answered_failed_and_skipped_and_a_rerun_asks_only_the_failed_rows(self):
        model = RowModel(fail=('发热',))
        with self.service(gateway=model) as (base, out):
            ann = self.team(base)['ann']
            self.make(ann)
            run = self.go(ann)
            self.assertEqual(run['status'], 'success')
            node = {n['id']: n for n in run['nodes']}['c']
            hot = [r for r in TICKETS if '发热' in r['问题描述']]
            self.assertEqual((node['llm']['failed'], node['llm']['answered'], node['llm']['skipped'], node['failures']), (len(hot), 45 - len(hot), 0, {'ai_failed': len(hot)}))
            self.assertEqual(run['failures']['c'], {'ai_failed': len(hot)})
            first = self.output(out)
            self.assertEqual({k: v for k, v in first.items() if k in {r['工单号'] for r in hot}}, {r['工单号']: (None, '失败：模型请求失败（model request failed: boom），请稍后重试') for r in hot})
            asked = len(model.requests)
            self.assertEqual(asked, len(set(TRUTH)))
            model.fail.clear()
            second_run = self.go(ann)
            second = {n['id']: n for n in second_run['nodes']}['c']
            self.assertEqual(len(model.requests) - asked, len({r['问题描述'] for r in hot}))   # only the descriptions that failed are asked again
            self.assertEqual((second['llm']['failed'], second['llm']['answered'], second['llm']['called'], second['llm']['from_cache']), (0, 45, len({r['问题描述'] for r in hot}), 45 - len(hot)))
            after = self.output(out)
            self.assertEqual({k: v for k, v in after.items() if k not in {r['工单号'] for r in hot}}, {k: v for k, v in first.items() if k not in {r['工单号'] for r in hot}})
            self.assertEqual({k: v[0] for k, v in after.items()}, {r['工单号']: keyword_answer(r['问题描述']) for r in TICKETS})
            third = self.go(ann)
            self.assertEqual(len(model.requests) - asked, len({r['问题描述'] for r in hot}))   # a third run asks nothing

    def test_clearing_the_kept_answers_makes_the_next_run_ask_every_description_again(self):
        model = RowModel()
        with self.service(gateway=model) as (base, out):
            ann = self.team(base)['ann']
            self.make(ann)
            self.go(ann)
            asked = len(model.requests)
            status, cleared = self.ask(ann, 'llm/clear-cache', {})
            self.assertEqual((status, cleared['cleared']), (200, len(set(TRUTH))))
            self.assertEqual(self.ask(ann, 'llm/state', {})[1]['report']['pending'], 45)
            self.go(ann)
            self.assertEqual(len(model.requests) - asked, len(set(TRUTH)))

    def test_a_prompt_that_names_no_column_is_refused_when_saved_and_so_is_a_node_without_a_model(self):
        with self.service(gateway=RowModel()) as (base, out):
            ann = self.team(base)['ann']
            bad = {'steps': [TICKET_SPEC['steps'][0], {**classify_step(), 'template': 'empty', 'prompt': '判断 $不存在', 'output': 'text'}, TICKET_SPEC['steps'][2]]}
            status, body = ann.post(PIPELINES, {'name': '错的', 'spec': bad})
            self.assertEqual(status, 400, body)
            self.assertIn('没有对应的列', body['error'])

    def test_someone_kept_from_the_input_can_neither_see_try_nor_label_the_node_and_a_column_switched_off_for_the_model_cannot_be_in_the_prompt(self):
        model = RowModel()
        ticket = {'english_name': 'ticket', 'name': '售后工单', 'dataset': '售后工单', 'key': ['工单号'], 'properties': [{'column': '问题描述'}]}
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            ids = {u['display_name'].lower(): u['id'] for u in admin.get('/api/users')[1]['users']}
            self.make(ann)
            self.assertEqual(ann.post('/api/workspace/types', ticket)[0], 200)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'ticket', 'visible_to': [ids['ann']]})[0], 200)
            for route, payload in (('llm/state', {}), ('llm/trial', {'mode': 'sample'}), ('llm/label', {'labels': []}), ('llm/review', {}), ('llm/clear-cache', {})):
                self.assertEqual(self.ask(bob, route, payload)[0], 404, route)
            self.assertEqual(bob.post(f'{PIPELINES}/llm/trial', {'spec': TICKET_SPEC, 'step': 'c', 'mode': 'sample'})[0], 404)   # nor on a draft of their own
            self.assertEqual(bob.post(f'{PIPELINES}/run', {'id': '工单分类'})[0], 404)
            self.assertEqual(model.requests, [])
            # the builder switches the description off for the model: the node can no longer name it
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'ticket', 'visible_to': 'everyone'})[0], 200)
            self.assertEqual(ann.post('/api/workspace/types/privacy', {'id': 'ticket', 'column': '问题描述', 'hide_values': True})[0], 200)
            status, body = ann.post(PIPELINES, {'name': '另一条', 'spec': TICKET_SPEC})
            self.assertEqual(status, 400, body)
            self.assertIn('不发送给模型', body['error'])
            status, body = self.ask(ann, 'llm/trial', {'mode': 'sample'})
            self.assertEqual(status, 400, body)
            self.assertEqual(model.requests, [])

    def test_a_viewer_gets_nothing_of_the_node(self):
        with self.service(gateway=RowModel()) as (base, out):
            team = self.team(base)
            self.make(team['ann'])
            for route in ('llm/state', 'llm/trial', 'llm/review'):
                self.assertEqual(self.ask(team['vera'], route, {'mode': 'sample'})[0], 403, route)

    def test_the_column_the_model_wrote_cannot_be_a_key_or_a_confirmed_code_until_the_review_passed_and_a_second_person_confirmed_the_pipeline(self):
        model = RowModel()
        category = {'english_name': 'ticket_class', 'name': '工单分类', 'dataset': '工单分类', 'key': ['工单号'], 'properties': [{'column': '问题类别', 'enum': True}],
                    'enums': {'问题类别': [{'value': c, 'label': c} for c in CATEGORIES if any(keyword_answer(d) == c for d in TRUTH)]}}
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.make(ann)
            self.go(ann)
            # a key made of it is refused, in words
            status, body = ann.post('/api/workspace/types', {**category, 'english_name': 'by_class', 'key': ['问题类别']})
            self.assertEqual(status, 409, body)
            self.assertIn('AI 生成', body['error'])
            made = ann.post('/api/workspace/types', category)
            self.assertEqual(made[0], 200, made)
            meanings = next(p for p in bob.get('/api/workspace/types/ticket_class')[1]['properties'] if p['column'] == '问题类别')['meanings']
            confirm = {'id': 'ticket_class', 'column': '问题类别', 'version': meanings['version'], 'seen': meanings['seen']}
            status, body = bob.post('/api/workspace/types/confirm', confirm)
            self.assertEqual(status, 409, body)
            self.assertIn('样本审核还没有通过', body['error'])
            # sample review passes
            trial = self.ask(ann, 'llm/trial', {'mode': 'sample', 'n': 20, 'seed': 3})[1]
            self.ask(ann, 'llm/label', {'labels': [{'fields': t['fields'], 'expected': keyword_answer(t['fields']['问题描述'])} for t in trial['trials']]})
            review = self.ask(ann, 'llm/review', {})[1]
            self.assertTrue(review['passed'], review)
            status, body = bob.post('/api/workspace/types/confirm', confirm)
            self.assertEqual(status, 409, body)
            self.assertIn('还没有另一位确认', body['error'])
            # a second person confirms the pipeline
            shown = bob.get(f'{PIPELINES}/{quote("工单分类")}')[1]
            self.assertEqual(shown['ai_nodes'][0]['review']['passed'], True)
            status, body = bob.post(f'{PIPELINES}/confirm', {'id': '工单分类', 'version': shown['version'], 'seen': {'inputs': shown['inputs_now']}})
            self.assertEqual(status, 200, body)
            meanings = next(p for p in bob.get('/api/workspace/types/ticket_class')[1]['properties'] if p['column'] == '问题类别')['meanings']
            status, body = bob.post('/api/workspace/types/confirm', {'id': 'ticket_class', 'column': '问题类别', 'version': meanings['version'], 'seen': meanings['seen']})
            self.assertEqual(status, 200, body)

    def test_an_edited_prompt_takes_the_review_back_to_not_current_until_the_labelled_rows_are_run_again(self):
        model = RowModel()
        with self.service(gateway=model) as (base, out):
            ann = self.team(base)['ann']
            self.make(ann)
            trial = self.ask(ann, 'llm/trial', {'mode': 'sample', 'n': 20, 'seed': 3})[1]
            self.ask(ann, 'llm/label', {'labels': [{'fields': t['fields'], 'expected': TRUTH[t['fields']['问题描述']]} for t in trial['trials']]})
            self.assertTrue(self.ask(ann, 'llm/review', {})[1]['review']['current'])
            shown = ann.get(f'{PIPELINES}/{quote("工单分类")}')[1]
            edited = {'steps': [TICKET_SPEC['steps'][0], classify_step(context='电器的售后工单'), TICKET_SPEC['steps'][2]]}
            self.assertEqual(ann.post(f'{PIPELINES}/update', {'id': '工单分类', 'version': shown['version'], 'spec': edited})[0], 200)
            state = self.ask(ann, 'llm/state', {})[1]
            self.assertEqual((state['review']['current'], state['review']['passed'], state['review']['labelled'] > 0), (False, False, True))
            self.assertEqual(state['recompute']['rows'], len(set(TRUTH)))
            self.assertIn('以前记下的', state['recompute']['why'][0])
            again = self.ask(ann, 'llm/review', {})[1]
            self.assertTrue(again['review']['current'])

    def test_drawing_the_rows_to_label_does_not_call_the_model_and_leaves_out_rows_already_labelled(self):
        model = RowModel()
        with self.service(gateway=model) as (base, out):
            ann = self.team(base)['ann']
            self.make(ann)
            status, drawn = self.ask(ann, 'llm/trial', {'mode': 'draw', 'n': 10, 'seed': 5})
            self.assertEqual(status, 200, drawn)
            self.assertEqual((len(drawn['trials']), model.requests, drawn['fields']), (10, [], ['问题描述']))
            self.assertEqual(len({t['row_hash'] for t in drawn['trials']}), 10)   # ten different descriptions
            self.ask(ann, 'llm/label', {'labels': [{'fields': t['fields'], 'expected': TRUTH[t['fields']['问题描述']]} for t in drawn['trials']]})
            more = self.ask(ann, 'llm/trial', {'mode': 'draw', 'n': 50, 'seed': 5, 'exclude_labelled': True})[1]
            self.assertEqual(len(more['trials']), len(set(TRUTH)) - 10)
            self.assertFalse({t['row_hash'] for t in more['trials']} & {t['row_hash'] for t in drawn['trials']})
            self.assertEqual(self.ask(ann, 'llm/state', {})[1]['inputs'], ['问题描述'])
