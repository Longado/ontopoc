"""Pipelines through the real service on the seven planted tables, two builders and a viewer: a pipeline is put forward, tried (preview, review), run, confirmed by
someone who did not write it, and when a step is edited after a run the output, the type on it and a saved answer that used it go to "needs another look" because the
definition changed. Expected numbers are counted here from the planted records (160 orders, 45 tickets, a left join gives 169 rows)."""
import base64
import csv
import io
from collections import Counter
from urllib.parse import quote

from tests import test_workspace_store as planted
from tests.test_object_types import ORDER, TABLES, orders_upload
from tests.test_two_person import SigningTestCase
from tests.test_workspace_questions import AskModel, cancelled

RECORDS = {name: s['records'] for name, s in planted.planted_bundle()['sources'].items()}
TICKETS = Counter(r['订单号'] for r in RECORDS['售后工单'])
EXTRA = sum(max(1, TICKETS[r['订单号']]) - 1 for r in RECORDS['订单'])   # orders with more than one ticket count once per ticket
INNER_ROWS = sum(TICKETS[r['订单号']] for r in RECORDS['订单'])
TRUE, DOUBLED = Counter(), Counter()
for _order in RECORDS['订单']:
    TRUE[_order['客户编号']] += int(_order['金额'])
    DOUBLED[_order['客户编号']] += int(_order['金额']) * max(1, TICKETS[_order['订单号']])
WRONG = {k for k in TRUE if TRUE[k] != DOUBLED[k]}

JOIN = {'id': 'j', 'type': 'join', 'left': 'o', 'right': 't', 'how': 'left', 'on': [{'left': '订单号', 'right': '订单号'}]}
TOTALS = {'id': 'g', 'type': 'transform', 'from': 'j', 'operators': [{'op': 'aggregate', 'group_by': ['客户编号'],
                                                                      'aggregations': [{'fn': 'sum', 'column': '金额', 'as': '合计'}, {'fn': 'count', 'column': '订单号', 'as': '行数'}]}]}
SPEC = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}, {'id': 't', 'type': 'input', 'dataset': '售后工单'}, JOIN, TOTALS,
                  {'id': 'out', 'type': 'output', 'from': 'g', 'name': '客户合计', 'key': {'columns': ['客户编号']}}]}
TOTAL_TYPE = {'english_name': 'customer_total', 'name': '客户合计', 'dataset': '客户合计', 'key': ['客户编号'], 'properties': [{'column': '合计'}]}
TOTAL_QUERY = {'start': 'customer_total', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None}
PIPELINES = '/api/workspace/pipelines'


def csv_part(name: str, rows: list[dict]) -> dict:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return {'filename': f'{name}.csv', 'content_base64': base64.b64encode(out.getvalue().encode('utf-8')).decode()}


class PipelineServerTests(SigningTestCase):
    def team(self, base):
        team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        return team

    def make(self, client, spec=SPEC, name='客户合计'):
        status, body = client.post(PIPELINES, {'name': name, 'description': '每个客户的订单金额合计', 'spec': spec})
        self.assertEqual(status, 200, body)
        return body

    def detail(self, client, name='客户合计'):
        status, body = client.get(f'{PIPELINES}/{quote(name)}')
        self.assertEqual(status, 200, body)
        return body

    def confirm(self, client, name='客户合计'):
        shown = self.detail(client, name)
        return client.post(f'{PIPELINES}/confirm', {'id': name, 'version': shown['version'], 'seen': {'inputs': shown['inputs_now']}})

    def go(self, client, name='客户合计'):   # not `run`: that is unittest's
        status, body = client.post(f'{PIPELINES}/run', {'id': name})
        self.assertEqual(status, 200, body)
        return body

    def nodes(self, run):
        return {n['id']: n for n in run['nodes']}

    def test_a_left_join_of_orders_to_tickets_has_169_rows_and_the_run_names_the_customer_whose_total_is_counted_twice(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            self.make(ann)
            status, joined = ann.post(f'{PIPELINES}/preview', {'id': '客户合计', 'node': 'j'})
            self.assertEqual(status, 200, joined)
            self.assertEqual((joined['node']['rows_in'], joined['node']['rows_out']), ([160, 45], 169))
            self.assertEqual(169 - 160, EXTRA)
            self.assertEqual(joined['node']['join']['left_unmatched'], 160 - len([r for r in RECORDS['订单'] if TICKETS[r['订单号']]]))
            self.assertLessEqual(len(joined['rows']), 100)
            self.assertEqual({c['name'] for c in joined['columns']} >= {'订单号', '金额', '工单号'}, True)
            run = self.go(ann)
            self.assertEqual(run['status'], 'success')
            self.assertEqual({'订单': 1, '售后工单': 1}, run['input_versions'])
            self.assertEqual(self.nodes(run)['j']['rows_out'], 169)
            found = self.nodes(run)['g']['operators'][0]['double_counted']
            self.assertEqual((found[0]['column'], found[0]['fn'], found[0]['groups']), ('金额', 'sum', len(WRONG)))
            by_group = {e['group']['客户编号']: (e['with'], e['true']) for e in found[0]['examples']}
            self.assertEqual(by_group['KH099'], (52620, 49470))
            self.assertEqual(by_group, {k: (DOUBLED[k], TRUE[k]) for k in WRONG})
            totals = ann.get(f'/api/workspace/datasets/{quote("客户合计")}')[1]
            self.assertEqual((totals['rows'], totals['versions'][0]['pipeline']['run'], totals['versions'][0]['pipeline']['inputs']), (len(TRUE), run['id'], {'订单': 1, '售后工单': 1}))

    def test_with_cancelled_orders_left_out_the_run_still_names_the_customer_whose_total_is_counted_twice(self):
        live = [r for r in RECORDS['订单'] if r['状态码'] != '2']
        true, doubled = Counter(), Counter()
        for r in live:
            true[r['客户编号']] += int(r['金额'])
            doubled[r['客户编号']] += int(r['金额']) * max(1, TICKETS[r['订单号']])
        wrong = {k for k in true if true[k] != doubled[k]}
        spec = {'steps': [SPEC['steps'][0], SPEC['steps'][1], JOIN,
                          {**TOTALS, 'operators': [{'op': 'filter', 'where': {'column': '状态码', 'cmp': 'ne', 'value': 2}}, *TOTALS['operators']]},
                          SPEC['steps'][4]]}
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            self.make(ann, spec)
            run = self.go(ann)
            filtered, grouped = self.nodes(run)['g']['operators']
            self.assertEqual((filtered['dropped_false'], filtered['dropped_null']), (16, 0))   # the 16 cancelled orders, none of which has a ticket
            found = grouped['double_counted'][0]
            by_group = {e['group']['客户编号']: (e['with'], e['true']) for e in found['examples']}
            self.assertEqual((found['groups'], by_group['KH099']), (len(wrong), (15820, 12670)))
            self.assertEqual(by_group, {k: (doubled[k], true[k]) for k in wrong})

    def test_the_summary_gives_every_card_its_counts_and_the_column_form_lists_what_an_operator_may_pick(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            self.make(ann)
            status, body = ann.post(f'{PIPELINES}/summary', {'id': '客户合计'})
            self.assertEqual(status, 200, body)
            nodes = {n['id']: n for n in body['nodes']}
            self.assertEqual([(i, n['rows_in'], n['rows_out']) for i, n in nodes.items()], [('o', [160], 160), ('t', [45], 45), ('j', [160, 45], 169), ('g', [169], len(TRUE)), ('out', [len(TRUE)], len(TRUE))])
            self.assertEqual(nodes['out']['output']['status']['state'], 'match')
            self.assertIn('金额', [c['name'] for c in nodes['j']['column_types']])
            status, columns = ann.post(f'{PIPELINES}/columns', {'id': '客户合计', 'step': 'g', 'operator': 0})
            self.assertEqual(status, 200, columns)
            by_name = {c['name']: c for c in columns['columns']}
            self.assertEqual(by_name['金额']['aggregations'][:2], ['sum', 'count'])
            self.assertEqual(ann.post(f'{PIPELINES}/summary', {'spec': {'steps': [{'id': 'o', 'type': 'input', 'dataset': '没有这个'}]}})[0], 404)
            # a draft whose join has no key pair yet still shows the steps before it, and says what is wrong
            draft = {'steps': [SPEC['steps'][0], SPEC['steps'][1], {**JOIN, 'on': [{'left': '', 'right': ''}]}, SPEC['steps'][3]]}
            status, partial = ann.post(f'{PIPELINES}/summary', {'spec': draft})
            self.assertEqual((status, partial['checked_steps'], [n['id'] for n in partial['nodes']]), (200, 2, ['o', 't']))
            self.assertIn('订单号', ann.post(f'{PIPELINES}/summary', {'id': '客户合计'})[1]['nodes'][0]['columns'])
            self.assertIn('列', partial['error'])
            self.assertIsNone(body['error'])
            self.assertEqual(self.go(ann)['status'], 'success')
            review = ann.post(f'{PIPELINES}/review', {'id': '客户合计'})[1]
            self.assertEqual(review['rows_before'], None)   # never confirmed

    def test_the_output_type_waits_for_the_pipeline_and_an_edited_join_sends_output_type_and_saved_answer_back_for_a_new_definition(self):
        model = AskModel(cancelled(query=TOTAL_QUERY, used=[]))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.make(ann)
            self.go(ann)
            self.assertEqual(ann.post('/api/workspace/types', TOTAL_TYPE)[0], 200)
            shown = bob.get('/api/workspace/types/customer_total')[1]
            self.assertEqual(shown['pipelines_blocking'], ['客户合计'])
            status, body = bob.post('/api/workspace/types/confirm', {'id': 'customer_total', 'version': shown['version'], 'seen': shown['seen']})
            self.assertEqual(status, 409)
            self.assertIn('客户合计', body['error'])
            status, body = self.confirm(ann)   # the one who wrote the pipeline may not confirm it
            self.assertEqual((status, body['error']), (403, '这条管道的定义你改过，要另一位来确认'))
            status, body = self.confirm(bob)
            self.assertEqual((status, body), (200, {'state': 'confirmed'}))
            shown = bob.get('/api/workspace/types/customer_total')[1]
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'customer_total', 'version': shown['version'], 'seen': shown['seen']})[0], 200)
            status, answer = ann.post('/api/workspace/ask', {'question': '每个客户的订单金额合计有几行？'})
            self.assertEqual(status, 200, answer)
            self.assertEqual(answer['status'], 'answered', answer)
            self.assertEqual(self.detail(ann)['outputs'][0]['stale'], False)
            # edit the join: left → inner. The pipeline is the editor's again; everything that stood on it is sent back, saying the definition changed
            now = self.detail(ann)
            inner = {'steps': [{**s, 'how': 'inner'} if s['id'] == 'j' else s for s in SPEC['steps']]}
            status, body = ann.post(f'{PIPELINES}/update', {'id': '客户合计', 'version': now['version'], 'spec': inner})
            self.assertEqual((status, body['definition_version'], body['changed']), (200, 2, True), body)
            output = self.detail(bob)['outputs'][0]
            self.assertEqual((output['dataset'], output['stale'], output['cause'], output['word']), ('客户合计', True, 'definition', '定义改了'))
            total = bob.get('/api/workspace/types/customer_total')[1]
            self.assertEqual((total['state'], total['cause'], total['cause_word'], total['via'], total['stale_word']), ('needs_look', 'definition', '定义改了', 'parent', '上一步过时'))
            self.assertIn('定义改了', total['reason'])
            reopened = ann.get(f'/api/workspace/ask/{answer["id"]}')[1]
            changed = {c['name']: c for c in reopened['changed']}
            self.assertEqual((changed['客户合计']['cause'], changed['客户合计']['cause_word'], changed['客户合计']['stale_word']), ('definition', '定义改了', '上一步过时'))
            # the queue shows the pipeline again, for someone other than the editor
            queue = bob.get('/api/workspace/queue')[1]
            waiting = next(i for i in queue['items'] if i['kind'] == 'pipeline')
            self.assertEqual((waiting['id'], waiting['state'], waiting['can_confirm'], waiting['title']), ('客户合计', 'checked', True, '客户合计'))
            self.assertIn('第 2 版定义', waiting['lines'][0]['text'])
            self.assertFalse(next(i for i in ann.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'pipeline')['can_confirm'])   # not for the one who edited it

    def test_an_inner_join_is_the_rows_that_have_a_ticket_and_the_run_says_so(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            self.make(ann, {'steps': [{**s, 'how': 'inner'} if s['id'] == 'j' else s for s in SPEC['steps']]})
            joined = ann.post(f'{PIPELINES}/preview', {'id': '客户合计', 'node': 'j'})[1]
            self.assertEqual(joined['node']['rows_out'], INNER_ROWS)

    def test_a_week_start_shifted_by_seven_days_is_flagged_against_its_source_in_the_trial_and_the_preview(self):
        draft = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}, {'id': 'c', 'type': 'transform', 'from': 'o', 'operators': []}]}
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            shifted = "date_add(date_trunc('week', 下单日期), 7, 'day')"
            status, trial = ann.post(f'{PIPELINES}/expression/trial', {'spec': draft, 'step': 'c', 'expression': shifted})
            self.assertEqual(status, 200, trial)
            self.assertEqual((trial['basis'], trial['errors'], [n['kind'] for n in trial['notices']]), ('样本', 0, ['later_than_source']))
            self.assertIn('不可能晚于原日期', trial['notices'][0]['text'])
            right = ann.post(f'{PIPELINES}/expression/trial', {'spec': draft, 'step': 'c', 'expression': "date_trunc('week', 下单日期)"})[1]
            self.assertEqual(right['notices'], [])
            bad = ann.post(f'{PIPELINES}/expression/check', {'spec': draft, 'step': 'c', 'expression': '下单日 + 1'})[1]
            self.assertFalse(bad['ok'])
            self.assertIn('下单日期', bad['errors'][0]['message'])   # the field that was meant is named
            # as an operator in the pipeline the same notice is on the preview of the step
            spec = {'steps': [draft['steps'][0], {'id': 'c', 'type': 'transform', 'from': 'o', 'operators': [{'op': 'calc', 'name': '周起始', 'expression': shifted}]}]}
            node = ann.post(f'{PIPELINES}/preview', {'spec': spec, 'node': 'c'})[1]['node']
            self.assertEqual([n['kind'] for n in node['operators'][0]['notices']], ['later_than_source'])

    def test_a_group_statistic_offers_count_and_average_and_not_only_the_sum_and_never_sums_a_code(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            self.make(ann)
            columns = {c['name']: c for c in ann.post(f'{PIPELINES}/preview', {'id': '客户合计', 'node': 'j'})[1]['columns']}
            self.assertEqual(columns['金额']['aggregations'], ['sum', 'count', 'count_distinct', 'avg', 'min', 'max', 'median', 'p25', 'p75'])
            self.assertEqual(columns['订单号']['aggregations'], ['count', 'count_distinct', 'min', 'max'])
            offered = ann.get(f'{PIPELINES}/options')[1]
            self.assertEqual([a['fn'] for a in offered['aggregations']][:2], ['sum', 'count'])
            self.assertIn('filter', [o['op'] for o in offered['operators']])
            self.assertTrue(any(g['group'] for g in offered['functions']))

    def test_a_text_amount_column_with_three_bad_values_reports_three_failures_and_lists_them(self):
        amounts = ['100', '2,500', '88.5', 'abc', '1 200元', '17', '--']
        rows = [{'编号': f'R{i}', '金额文本': v} for i, v in enumerate(amounts)]
        spec = {'steps': [{'id': 'i', 'type': 'input', 'dataset': '流水'},
                          {'id': 'c', 'type': 'transform', 'from': 'i', 'operators': [{'op': 'cast', 'column': '金额文本', 'to': 'decimal', 'as': '金额', 'thousands': True}]},
                          {'id': 'out', 'type': 'output', 'from': 'c', 'name': '流水金额', 'key': {'columns': ['编号']}}]}
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [csv_part('流水', rows)]})[0], 200)
            self.make(ann, spec, '流水金额')
            op = ann.post(f'{PIPELINES}/preview', {'id': '流水金额', 'node': 'c'})[1]['node']['operators'][0]
            self.assertEqual((op['failures'], [(f['row'], f['value']) for f in op['failed']]), (3, [(4, 'abc'), (5, '1 200元'), (7, '--')]))   # rows count from 1
            run = self.go(ann, '流水金额')
            self.assertEqual((run['status'], run['failures']['c']), ('success', {'cast_failures': 3}))
            self.assertEqual([f['value'] for f in self.nodes(run)['c']['operators'][0]['failed']], ['abc', '1 200元', '--'])

    def test_a_key_that_repeats_stops_the_run_and_lists_the_keys_and_nothing_is_written(self):
        spec = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}, {'id': 't', 'type': 'input', 'dataset': '售后工单'}, JOIN,
                          {'id': 'out', 'type': 'output', 'from': 'j', 'name': '订单工单', 'key': {'columns': ['订单号']}}]}
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            self.make(ann, spec, '订单工单')
            repeated = sorted(k for k in TICKETS if TICKETS[k] > 1)
            run = self.go(ann, '订单工单')
            self.assertEqual(run['status'], 'failed')
            self.assertIn(f'主键有 {len(repeated)} 个重复', run['error'])
            self.assertIn(repeated[0], run['error'])
            self.assertEqual(ann.get(f'/api/workspace/datasets/{quote("订单工单")}')[0], 404)
            node = ann.post(f'{PIPELINES}/preview', {'id': '订单工单', 'node': 'out'})[1]['node']['output']
            self.assertEqual(node['duplicate_keys']['count'], len(repeated))

    def test_new_data_in_an_input_makes_the_confirmed_pipeline_need_a_look_for_new_data_and_a_rerun_writes_a_new_version_naming_the_run(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.make(ann)
            first = self.go(ann)
            self.assertEqual(self.confirm(bob)[0], 200)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(lambda r, i: {**r, '金额': '1'} if i == 0 else r)]})[0], 200)
            shown = bob.get(f'{PIPELINES}/{quote("客户合计")}')[1]
            self.assertEqual((shown['state'], shown['cause'], shown['stale_word']), ('needs_look', 'data', '数据变了'))
            self.assertTrue(shown['outputs'][0]['stale'])
            self.assertEqual(shown['outputs'][0]['cause'], 'data')
            second = self.go(bob)
            self.assertEqual((second['input_versions'], [(o['dataset'], o['version'], o['created_version']) for o in second['outputs']]), ({'订单': 2, '售后工单': 1}, [('客户合计', 2, True)]))
            versions = ann.get(f'/api/workspace/datasets/{quote("客户合计")}')[1]['versions']
            self.assertEqual([(v['version'], v['pipeline']['run'], v['pipeline']['inputs']) for v in versions], [(2, second['id'], {'订单': 2, '售后工单': 1}), (1, first['id'], {'订单': 1, '售后工单': 1})])
            runs = ann.get(f'{PIPELINES}/{quote("客户合计")}/runs')[1]['runs']
            self.assertEqual([(r['id'], r['status'], r['who']) for r in runs], [(second['id'], 'success', 'Bob'), (first['id'], 'success', 'Ann')])
            self.assertEqual(ann.get(f'{PIPELINES}/{quote("客户合计")}/runs/{first["id"]}')[1]['nodes'][0]['rows_out'], 160)

    def test_definition_versions_are_kept_and_the_changed_steps_are_listed_between_two(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            self.make(ann)
            now = self.detail(ann)
            inner = {'steps': [{**s, 'how': 'inner'} if s['id'] == 'j' else s for s in SPEC['steps']]}
            self.assertEqual(ann.post(f'{PIPELINES}/update', {'id': '客户合计', 'version': now['version'], 'spec': inner})[0], 200)
            kept = ann.get(f'{PIPELINES}/{quote("客户合计")}/versions?from=1&to=2')[1]
            self.assertEqual([(v['version'], v['saved_by']) for v in kept['versions']], [(2, 'Ann'), (1, 'Ann')])
            self.assertEqual([(c['id'], c['change'], c['before']['how'], c['after']['how']) for c in kept['changes']], [('j', 'MOD', 'left', 'inner')])
            stale = ann.post(f'{PIPELINES}/update', {'id': '客户合计', 'version': now['version'], 'spec': SPEC})   # saved from the page that was open before
            self.assertEqual(stale[0], 409)

    def test_a_viewer_reads_and_runs_nothing_and_a_dataset_a_pipeline_reads_is_listed_before_it_is_deleted(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, vera = team['ann'], team['vera']
            self.make(ann)
            self.assertEqual(vera.get(PIPELINES)[0], 403)
            self.assertEqual(vera.post(f'{PIPELINES}/run', {'id': '客户合计'})[0], 403)
            readers = ann.get(f'/api/workspace/datasets/{quote("订单")}')[1]['readers']
            self.assertIn('管道', [r['kind'] for r in readers])
            status, body = ann.post('/api/workspace/datasets/delete', {'name': '订单'})
            self.assertEqual(status, 409, body)
            self.assertIn('客户合计', body['error'])

    def test_a_dataset_whose_rows_are_held_back_from_someone_cannot_be_an_input_because_the_output_would_carry_those_rows_elsewhere(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, admin = team['ann'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            rules = [{'column': '状态码', 'value': '0', 'user_ids': [ids['vera']]}, {'user_ids': [ids['ann']]}]   # vera sees the delivered orders, Ann sees all
            status, body = admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': rules})
            self.assertEqual(status, 200, body)
            status, body = ann.post(PIPELINES, {'name': '客户合计', 'spec': SPEC})
            self.assertEqual(status, 409, body)
            self.assertIn('行规则', body['error'])
            self.assertEqual(team['bob'].post(PIPELINES, {'name': '客户合计', 'spec': SPEC})[0], 404)   # a builder the rule does not name does not see the dataset at all
            self.assertEqual(ann.get(PIPELINES)[1]['pipelines'], [])

    # --- what a pipeline's output inherits from what it reads ------------------------------------------------------------------------------------------

    COPY = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}, {'id': 'out', 'type': 'output', 'from': 'o', 'name': '订单副本', 'key': {'columns': ['订单号']}}]}

    def ids(self, admin):
        return {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}

    def readable(self, client, name='订单副本'):
        """Whether this person gets the dataset's rows or detail, and whether it is in their list."""
        listed = name in [d['name'] for d in client.get('/api/workspace/datasets')[1]['datasets']]
        return client.get(f'/api/workspace/datasets/{quote(name)}')[0], listed

    def test_a_copy_of_a_dataset_hidden_from_someone_is_hidden_from_them_too_and_so_is_a_copy_of_the_copy(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            ids = self.ids(admin)
            self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': [ids['ann']]})[0], 200)   # only Ann sees the type, so the dataset
            self.make(ann, self.COPY, '订单副本')
            self.go(ann, '订单副本')
            self.assertEqual(self.readable(ann), (200, True))
            self.assertEqual(self.readable(admin), (200, True))
            self.assertEqual(self.readable(bob), (404, False))
            self.assertEqual(self.readable(vera), (404, False))
            self.assertEqual(bob.get(f'/api/workspace/datasets/{quote("订单副本")}?format=csv')[0], 404)
            self.assertEqual(bob.get(f'{PIPELINES}/{quote("订单副本")}')[0], 404)
            # the same for a copy of a copy
            second = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单副本'}, {'id': 'out', 'type': 'output', 'from': 'o', 'name': '订单副本二', 'key': {'columns': ['订单号']}}]}
            self.make(ann, second, '再抄一份')
            self.go(ann, '再抄一份')
            self.assertEqual(self.readable(bob, '订单副本二'), (404, False))
            self.assertEqual(self.readable(ann, '订单副本二'), (200, True))

    def test_a_row_rule_added_after_a_run_hides_the_output_from_the_people_it_limits(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            ids = self.ids(admin)
            self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)
            self.make(ann, self.COPY, '订单副本')
            self.go(ann, '订单副本')
            self.assertEqual(self.readable(bob), (200, True))                                                       # nothing holds the rows back yet
            rules = [{'column': '状态码', 'value': '0', 'user_ids': [ids['vera']]}, {'user_ids': [ids['ann']]}]
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': rules})[0], 200)
            self.assertEqual(self.readable(bob), (404, False))                                                      # the existing output has every row, so it is theirs no longer
            self.assertEqual(self.readable(vera), (404, False))
            self.assertEqual(self.readable(ann), (200, True))                                                       # Ann is named for all rows
            self.assertEqual(self.readable(admin), (200, True))

    def test_a_pipeline_that_reads_a_view_of_a_type_someone_may_not_see_is_not_theirs_to_see_nor_is_what_it_wrote(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            ids = self.ids(admin)
            self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)
            for column in ('状态码', None):
                detail = bob.get('/api/workspace/types/order')[1]
                shown = next(p for p in detail['properties'] if p['column'] == column)['meanings'] if column else detail
                self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})[0], 200)
            self.assertEqual(ann.post('/api/workspace/types/views', {'name': '有效订单', 'type': 'order', 'filters': [{'column': '状态码', 'op': 'is_not', 'label': '已取消'}]})[0], 200)
            shown = bob.get('/api/workspace/types/order/views')[1]['views'][0]
            self.assertEqual(bob.post('/api/workspace/types/views/confirm', {'id': '有效订单', 'version': shown['version'], 'seen': shown['seen']})[0], 200)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': [ids['ann']]})[0], 200)
            spec = {'steps': [{'id': 'v', 'type': 'input', 'view': '有效订单'}, {'id': 'out', 'type': 'output', 'from': 'v', 'name': '订单副本', 'key': {'columns': ['订单号']}}]}
            self.make(ann, spec, '看视图')
            run = self.go(ann, '看视图')
            self.assertEqual(bob.get(PIPELINES)[1]['pipelines'], [])
            for path in ('', '/runs', f'/runs/{run["id"]}', '/log', '/versions'):
                self.assertEqual(bob.get(f'{PIPELINES}/{quote("看视图")}{path}')[0], 404, path)
            self.assertEqual(bob.post(f'{PIPELINES}/preview', {'id': '看视图', 'node': 'out'})[0], 404)
            self.assertEqual(self.readable(bob), (404, False))
            self.assertEqual(self.readable(ann), (200, True))
