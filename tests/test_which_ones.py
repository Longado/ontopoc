"""Which ones, not only how many: a question or a query may ask for the objects themselves.

  a list      the objects a count of the same query counts (the same conditions, the same confirmed views, the same rows the asker may read), one page of at
              most 50, ordered by the key, with the asker's own total
  a lookup    one object by its whole key: its confirmed properties, code columns with their confirmed meanings; a key the asker may not read is answered
              exactly as a key nobody has
  a view      may compare a confirmed per-row formula (a derived property of kind function) with a number, and waits while that formula waits
  today       a range bound on a date property, the date the query runs on, said in the answer

The sample here is a small one with orders (urgency, amount, promised date) and handling measures with an approval status. Expected rows are worked out in
Python from the same rows. The model is scripted: it never sees a row, and no request it is sent holds one."""
import base64
import json
import re
import sqlite3
import time
from unittest import mock

from ontology_poc_generator import mcp_server, workspace_questions, workspace_store
from ontology_poc_generator.recognition import ModelCompletion
from tests.test_two_person import SigningTestCase

ORDER_ROWS = [{'订单号': f'DD2026{i:04d}', '客户编号': f'KH00{i % 4 + 1}', '紧急程度': '1' if i % 3 == 0 else '0', '金额': str(20000 + i * 7919 % 60000),
               '承诺日期': f'2026-06-{i % 28 + 1:02d}'} for i in range(1, 41)]
MEASURE_ROWS = [{'措施编号': f'M-{i:02d}', '订单号': f'DD2026{i:04d}', '审批状态': str((i + 2) % 3)} for i in range(1, 21)]
URGENCY = [{'value': '0', 'label': '普通'}, {'value': '1', 'label': '加急'}]
APPROVAL = [{'value': '0', 'label': '待审批'}, {'value': '1', 'label': '已批准'}, {'value': '2', 'label': '已驳回'}]
ORDER = {'english_name': 'order', 'name': '订单', 'dataset': 'orders', 'key': ['订单号'],
         'properties': [{'column': '订单号'}, {'column': '客户编号'}, {'column': '紧急程度', 'enum': True}, {'column': '金额'}, {'column': '承诺日期'}], 'enums': {'紧急程度': URGENCY}}
MEASURE = {'english_name': 'measure', 'name': '处置措施', 'dataset': 'measures', 'key': ['措施编号'],
           'properties': [{'column': '措施编号'}, {'column': '订单号'}, {'column': '审批状态', 'enum': True}], 'enums': {'审批状态': APPROVAL}}
HIGH_RISK = {'type': 'order', 'english_name': 'high_risk', 'name': '高风险', 'kind': 'function', 'expression': 'if(金额 > 50000, 1, 0)'}
VIEW = {'name': '高风险加急订单', 'type': 'order', 'filters': [{'column': '紧急程度', 'op': 'is', 'label': '加急'}], 'derived': [{'property': 'high_risk', 'op': 'equals', 'value': 1}]}
URGENT_HIGH = sorted(r['订单号'] for r in ORDER_ROWS if r['紧急程度'] == '1' and int(r['金额']) > 50000)
URGENT = sorted(r['订单号'] for r in ORDER_ROWS if r['紧急程度'] == '1')
LIST_VIEW = {'start': 'order', 'where': [], 'list': {}}
VIEW_USED = [{'id': '高风险加急订单', 'direction': 'include', 'basis': '高风险的加急订单'}]


def csv_part(name: str, rows: list[dict]) -> dict:
    text = ','.join(rows[0]) + '\n' + ''.join(','.join(r.values()) + '\n' for r in rows)
    return {'filename': name, 'content_base64': base64.b64encode(text.encode('utf-8')).decode()}


class Scripted:
    """Replies with what it is given, in turn (the last one again once the rest are used), and keeps every request: the system prompt and the user message."""

    def __init__(self, *replies):
        self.replies, self.requests, self.prompts = list(replies), [], []

    def complete_json(self, *, system_prompt, user_prompt, timeout_seconds=None):
        request = json.loads(user_prompt)
        self.requests.append(request)
        self.prompts.append(system_prompt + '\n' + user_prompt)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, str):
            return ModelCompletion('test', 'test-model', reply)
        if 'text' in reply:   # the model writes OntoPoc Query
            return ModelCompletion('test', 'test-model', json.dumps({'reasoning': 'test', 'query': reply['text'], 'views': reply.get('views', [])}, ensure_ascii=False))
        return ModelCompletion('test', 'test-model', json.dumps({'questions': [{'question': request['asked'], **reply}]}, ensure_ascii=False))


def item(query, used=()):
    return {'reasoning': 'test', 'query': query, 'definitions_used': list(used)}


def keys(body) -> list[str]:
    objects = body['answer']['objects']
    at = [c['column'] for c in objects['columns']].index(objects['order_by'][0])
    return [r[at] for r in objects['rows']]


def without_moments(body):
    """A response with the moments it was made at taken out (they differ between two services), so two whole responses can be compared."""
    text = json.dumps({k: v for k, v in body.items() if k not in ('id', 'asked_at')}, ensure_ascii=False, sort_keys=True)
    return re.sub(r'"(confirmed_at|imported_at|asked_at)": "[^"]*"', r'"\1": ""', text)


class Sample(SigningTestCase):
    """The sample with its definitions confirmed: Ann puts them forward, Bob confirms them; Vera is a viewer."""

    def setup(self, base, view=True, orders=ORDER_ROWS, order_type=ORDER, formula=True):
        team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        ann, bob = team['ann'], team['bob']
        self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [csv_part('orders.csv', orders), csv_part('measures.csv', MEASURE_ROWS)]})[0], 200)
        for payload in (order_type, MEASURE):
            self.assertEqual(ann.post('/api/workspace/types', payload)[0], 200, payload['english_name'])
            column = next(p['column'] for p in payload['properties'] if p.get('enum'))
            self.confirm(bob, payload['english_name'], column)
            self.confirm(bob, payload['english_name'])
        if formula:
            status, body = ann.post('/api/workspace/types/derived', HIGH_RISK)
            self.assertEqual(status, 200, body)
            self.confirm_formula(bob)
        if view:
            status, body = ann.post('/api/workspace/types/views', VIEW)
            self.assertEqual(status, 200, body)
            self.confirm_view(bob)
        return team

    def confirm(self, client, name, column=None):
        shown = client.get(f'/api/workspace/types/{name}')[1]
        shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
        status, body = client.post('/api/workspace/types/confirm', {'id': name, 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})
        self.assertEqual(status, 200, body)

    def formula(self, client):
        return next(d for d in client.get('/api/workspace/types/order/derived')[1]['derived'] if d['id'] == 'high_risk')

    def confirm_formula(self, client):
        line = self.formula(client)
        status, body = client.post('/api/workspace/types/derived/confirm', {'type': 'order', 'english_name': 'high_risk', 'version': line['version'], 'seen': line['seen']})
        self.assertEqual(status, 200, body)

    def view(self, client):
        return next(v for v in client.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == VIEW['name'])

    def confirm_view(self, client):
        shown = self.view(client)
        status, body = client.post('/api/workspace/types/views/confirm', {'id': VIEW['name'], 'version': shown['version'], 'seen': shown['seen']})
        self.assertEqual(status, 200, body)

    def ask(self, client, model, question, reply, writes='json'):
        model.replies = [reply]
        status, body = client.post('/api/workspace/ask', {'question': question, **({'writes': writes} if writes != 'json' else {})})
        self.assertEqual(status, 200, body)
        return body

    def query(self, client, text, **more):
        return client.post('/api/workspace/query', {'text': text, **more})

    def user_id(self, admin, username):
        return next(u['id'] for u in admin.get('/api/users')[1]['users'] if u['username'] == username)


class WhichOnes(Sample):
    def test_which_urgent_orders_are_high_risk_lists_the_orders_of_the_confirmed_view(self):
        model = Scripted(item(LIST_VIEW, VIEW_USED))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base)
            body = self.ask(team['ann'], model, '哪些加急订单是高风险的？', item(LIST_VIEW, VIEW_USED))
            self.assertEqual((body['status'], body['answer']['total']), ('answered', len(URGENT_HIGH)), body)
            self.assertEqual(keys(body), URGENT_HIGH)
            self.assertGreater(len(URGENT_HIGH), 2)
            objects = body['answer']['objects']
            self.assertEqual([c['column'] for c in objects['columns']], ['订单号', '客户编号', '紧急程度', '金额', '承诺日期'])   # the key, then the first properties
            self.assertEqual(next(c for c in objects['columns'] if c['column'] == '紧急程度')['meanings'], {'0': '普通', '1': '加急'})
            self.assertEqual((objects['page'], objects['pages'], objects['page_size']), (1, 1, 50))
            self.assertEqual([(d['kind'], d['name']) for d in body['definitions'] if d['kind'] in ('view', 'derived')], [('view', '高风险加急订单')])
            self.assertEqual([v['name'] for v in body['evidence']['views']], ['高风险加急订单'])   # the line under it names the view that chose the rows
            self.assertIn('列出', body['path'])
            self.assertEqual(body['query_text'].splitlines()[0], 'SELECT LIST o')
            counted = self.ask(team['ann'], model, '高风险加急订单有多少？', item({'start': 'order', 'where': []}, VIEW_USED))
            self.assertEqual(body['beside'], counted['beside'])   # what is beside the count is beside the list of what it counts
            # the same question written as a query by the model, and by a person: the same orders
            text = self.ask(team['ann'], model, '哪些加急订单是高风险的？', {'text': 'SELECT LIST o FROM (o:订单)', 'views': ['高风险加急订单']}, writes='query')
            self.assertEqual((text['status'], keys(text)), ('answered', URGENT_HIGH), text)
            status, written = self.query(team['ann'], "SELECT LIST o.金额 FROM (o:订单) WHERE o.紧急程度 = '加急' AND o.金额 > 50000")
            self.assertEqual((status, keys(written), written['answer']['total']), (200, URGENT_HIGH, len(URGENT_HIGH)), written)
            self.assertEqual([c['column'] for c in written['answer']['objects']['columns']], ['订单号', '金额'])

    def test_the_approval_status_of_measure_m17_is_one_confirmed_status(self):
        lookup = {'start': 'measure', 'lookup': {'措施编号': 'M-17'}}
        model = Scripted(item(lookup))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base, view=False)
            body = self.ask(team['vera'], model, '措施 M-17 的审批状态是什么？', item(lookup))
            self.assertEqual((body['status'], body['answer']['total'], body['answer']['lookup']), ('answered', 1, {'措施编号': 'M-17'}), body)
            objects = body['answer']['objects']
            row = dict(zip([c['column'] for c in objects['columns']], objects['rows'][0]))
            status = next(c for c in objects['columns'] if c['column'] == '审批状态')
            self.assertEqual((row['审批状态'], status['meanings'][row['审批状态']]), ('1', '已批准'))
            self.assertEqual([(d['kind'], d['name']) for d in body['definitions']], [('type', '处置措施'), ('meaning', '处置措施.审批状态')])
            status, written = self.query(team['vera'], "SELECT ONE m FROM (m:处置措施) WHERE m.措施编号 = 'M-17'")
            self.assertEqual((status, written['answer']['objects']['rows']), (200, objects['rows']), written)

    def test_a_lookup_must_give_the_whole_key(self):
        model = Scripted(item({'start': 'measure', 'lookup': {'订单号': 'DD20260017'}}))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base)
            status, body = self.query(team['ann'], "SELECT ONE m FROM (m:处置措施) WHERE m.订单号 = 'DD20260017'")
            self.assertEqual(status, 400)
            self.assertIn('措施编号', body['error'])
            body = self.ask(team['ann'], model, 'DD20260017 的措施？', item({'start': 'measure', 'lookup': {'订单号': 'DD20260017'}}))
            self.assertEqual(body['status'], 'query_limit')
            body = self.ask(team['ann'], model, '加急的 DD20260003？', item({'start': 'order', 'lookup': {'订单号': 'DD20260003'}}, [{'id': 'orders.紧急程度=加急', 'direction': 'include', 'basis': '加急'}]))
            self.assertEqual(body['status'], 'query_limit')   # a meaning is not a condition a lookup can apply: it is not answered, and the meaning is not dropped

    def test_a_lookup_with_a_view_named_applies_the_view_and_an_object_outside_it_answers_as_a_key_nobody_has(self):
        inside, outside, missing = URGENT_HIGH[0], next(r['订单号'] for r in ORDER_ROWS if r['订单号'] not in URGENT_HIGH), 'DD20269999'
        lookup = lambda key, used=VIEW_USED: item({'start': 'order', 'lookup': {'订单号': key}}, used)
        model = Scripted(lookup(inside))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base)
            for who in ('ann', 'vera'):
                asks = {'json': lambda key: self.ask(team[who], model, f'高风险加急订单里的 {key}？', lookup(key)),
                        'text': lambda key: self.ask(team[who], model, f'高风险加急订单里的 {key}？', {'text': f"SELECT ONE o FROM (o:订单) WHERE o.订单号 = '{key}'", 'views': [VIEW['name']]}, writes='query')}
                for how, ask in asks.items():
                    with self.subTest(who=who, how=how):
                        found = ask(inside)
                        self.assertEqual((found['status'], found['answer']['total'], keys(found)), ('answered', 1, [inside]), found)
                        self.assertIn(VIEW['name'], found['path'])   # the line under it names the view
                        self.assertIn(('view', VIEW['name']), [(d['kind'], d['name']) for d in found['definitions']])
                        hidden, nobody = ask(outside), ask(missing)
                        self.assertEqual(hidden['status'], 'no_data', hidden)
                        self.assertIn(VIEW['name'], hidden['path'])
                        self.assertEqual(without_moments(hidden).replace(outside, 'KEY'), without_moments(nobody).replace(missing, 'KEY'))
                        reopened = team[who].get(f'/api/workspace/ask/{found["id"]}')[1]
                        self.assertEqual((reopened['again'], keys(reopened)), (True, [inside]), reopened)
                plain = self.ask(team[who], model, f'订单 {outside}？', lookup(outside, []))
                self.assertEqual((plain['status'], keys(plain)), ('answered', [outside]), plain)   # without the view, the object is there
                unsaid = self.ask(team[who], model, f'高风险加急订单里的 {outside}？', lookup(outside, []))
                self.assertEqual(unsaid['status'], 'definition_unmet', unsaid)   # the question names the view and the model did not read it: refused, as for a number

    def test_a_list_pages_by_its_key_and_a_page_of_more_than_fifty_is_refused(self):
        with self.service(gateway=Scripted('not json')) as (base, out):
            ann = self.setup(base, view=False)['ann']
            pages = []
            for page in range(1, 8):
                status, body = self.query(ann, 'SELECT LIST o FROM (o:订单) LIMIT 7', page=page)
                self.assertEqual((status, body['answer']['total'], body['answer']['objects']['pages']), (200, 40, 6), body)
                pages.append(keys(body))
            self.assertEqual([k for p in pages[:6] for k in p], sorted(r['订单号'] for r in ORDER_ROWS))   # every object once, in the order of the key
            self.assertEqual(pages[6], pages[5])   # past the last page: the last page, as the objects tab pages
            self.assertEqual(self.query(ann, 'SELECT LIST o FROM (o:订单)')[1]['answer']['objects']['page_size'], 50)
            status, body = self.query(ann, 'SELECT LIST o FROM (o:订单) LIMIT 51')
            self.assertEqual(status, 400)
            self.assertIn('50', body['error'])
            for page in (0, -1, 'x', True, 1.5):
                self.assertEqual(self.query(ann, 'SELECT LIST o FROM (o:订单)', page=page)[0], 400, page)
            status, count = self.query(ann, "SELECT count(o) FROM (o:订单) WHERE o.紧急程度 = '加急'")
            status, listed = self.query(ann, "SELECT LIST o FROM (o:订单) WHERE o.紧急程度 = '加急'")
            self.assertEqual((count['answer']['total'], listed['answer']['total'], keys(listed)), (len(URGENT), len(URGENT), URGENT))
            self.assertEqual(count['path'], listed['path'].rsplit('，', 1)[0])   # the same line under it as the number, and that it lists them

    def test_a_list_page_size_above_fifty_from_the_model_is_refused(self):
        reply = item({'start': 'order', 'where': [], 'list': {'limit': 60}})
        model = Scripted(reply)
        with self.service(gateway=model) as (base, out):
            ann = self.setup(base, view=False)['ann']
            body = self.ask(ann, model, '列出全部订单', reply)
            self.assertEqual(body['status'], 'query_limit')
            self.assertIn('50', body['reason'])

    def test_a_view_on_a_derived_flag_is_refused_while_the_flag_waits(self):
        model = Scripted(item(LIST_VIEW, VIEW_USED))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base, view=False, formula=False)
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            self.assertEqual(ann.post('/api/workspace/types/derived', HIGH_RISK)[0], 200)
            status, body = ann.post('/api/workspace/types/views', VIEW)
            self.assertEqual(status, 200, body)
            shown = self.view(bob)
            self.assertEqual((shown['rows'], shown['of']), (len(URGENT_HIGH), 40))   # counted on the formula's values
            self.assertIn('高风险 = 1', shown['says'])
            self.assertEqual(bob.post('/api/workspace/types/views/confirm', {'id': VIEW['name'], 'version': shown['version'], 'seen': shown['seen']})[0], 409)   # the formula is not confirmed yet
            self.confirm_formula(bob)
            self.confirm_view(bob)
            self.assertEqual(keys(self.ask(ann, model, '哪些加急订单是高风险的？', item(LIST_VIEW, VIEW_USED))), URGENT_HIGH)
            # the formula is changed: it waits for confirming, and the view waits with it
            line = self.formula(ann)
            status, body = ann.post('/api/workspace/types/derived/update', {**HIGH_RISK, 'expression': 'if(金额 > 60000, 1, 0)', 'version': line['version']})
            self.assertEqual(status, 200, body)
            self.assertEqual(self.view(ann)['state'], 'needs_look')
            refused = self.ask(ann, model, '哪些是高风险加急订单？', item(LIST_VIEW, VIEW_USED))
            self.assertEqual(refused['status'], 'refused', refused)
            self.assertEqual([d['name'] for d in refused['refusal']['definitions']], ['订单.高风险', '高风险加急订单'])
            told = self.ask(vera, model, '哪些是高风险加急订单？', item(LIST_VIEW, VIEW_USED))
            self.assertEqual((told['status'], [d.get('waiting') for d in told['refusal']['definitions']]), ('refused', [True]), told)
            self.assertNotIn('高风险 =', json.dumps(told, ensure_ascii=False))

    def test_a_waiting_view_is_refused_for_a_list_as_for_a_number(self):
        model = Scripted(item(LIST_VIEW, VIEW_USED))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base)
            line = self.formula(team['ann'])
            self.assertEqual(team['ann'].post('/api/workspace/types/derived/update', {**HIGH_RISK, 'expression': 'if(金额 > 60000, 1, 0)', 'version': line['version']})[0], 200)
            for who in ('ann', 'vera'):
                listed = self.ask(team[who], model, '哪些是高风险加急订单？', item(LIST_VIEW, VIEW_USED))
                counted = self.ask(team[who], model, '哪些是高风险加急订单？', item({'start': 'order', 'where': []}, VIEW_USED))
                self.assertEqual(without_moments({k: v for k, v in listed.items() if k != 'query'}), without_moments({k: v for k, v in counted.items() if k != 'query'}), who)

    def test_today_is_the_date_the_query_runs_on_and_the_answer_says_which(self):
        with self.service(gateway=Scripted('not json')) as (base, out), mock.patch.object(workspace_questions, '_today', lambda: ('2026-06-15', 'UTC+08:00')):
            ann = self.setup(base, view=False)['ann']
            status, body = self.query(ann, "SELECT LIST o FROM (o:订单) WHERE o.紧急程度 = '加急' AND o.承诺日期 < today")
            due = sorted(r['订单号'] for r in ORDER_ROWS if r['紧急程度'] == '1' and r['承诺日期'] < '2026-06-15')
            self.assertEqual((status, keys(body), body['today']), (200, due, {'date': '2026-06-15', 'time_zone': 'UTC+08:00'}), body)
            self.assertIn('2026-06-15', body['path'])
            self.assertIn('today', body['text'])
            status, count = self.query(ann, 'SELECT count(o) FROM (o:订单) WHERE o.承诺日期 >= today')
            self.assertEqual((status, count['answer']['total'], count['today']['date']), (200, sum(r['承诺日期'] >= '2026-06-15' for r in ORDER_ROWS), '2026-06-15'))
            status, body = self.query(ann, 'SELECT LIST o FROM (o:订单) WHERE o.金额 < today')
            self.assertEqual(status, 400)
            self.assertIn('today', body['error'])
            for word in ('yesterday', "'tomorrow'", 'now()'):
                self.assertEqual(self.query(ann, f'SELECT LIST o FROM (o:订单) WHERE o.承诺日期 < {word}')[0], 400, word)

    def test_today_is_read_only_as_the_bare_word_on_a_date_and_anything_else_is_what_it_was(self):
        plain = {'start': 'order', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None}
        model = Scripted('not json')
        with self.service(gateway=model) as (base, out), mock.patch.object(workspace_questions, '_today', lambda: ('2026-06-15', 'UTC+08:00')):
            ann = self.setup(base, view=False)['ann']
            read = self.ask(ann, model, '承诺日期早于今天的订单有多少？', item({**plain, 'where': [{'field': '承诺日期', 'less_than': 'today'}]}))
            self.assertEqual((read['status'], read['today']['date']), ('answered', '2026-06-15'), read)
            for bound, field in (('Today ', '承诺日期'), ('TODAY', '承诺日期'), (' today', '承诺日期'), ('today', '金额'), ('today', '订单号')):
                with self.subTest(bound=bound, field=field):
                    got = self.ask(ann, model, '今天之前的订单有多少？', item({**plain, 'where': [{'field': field, 'less_than': bound}]}))
                    with mock.patch.object(workspace_questions, 'ROW_ANSWERS', False):
                        was = self.ask(ann, model, '今天之前的订单有多少？', item({**plain, 'where': [{'field': field, 'less_than': bound}]}))
                    self.assertEqual(without_moments(got), without_moments(was))
                    self.assertNotIn('today', got)
            for text, params in (("SELECT count(o) FROM (o:订单) WHERE o.承诺日期 < 'today'", None), ("SELECT LIST o FROM (o:订单) WHERE o.承诺日期 < 'today'", None),
                                 ('SELECT count(o) FROM (o:订单) WHERE o.承诺日期 < $d', {'d': 'today'}), ("SELECT count(o) FROM (o:订单) WHERE o.承诺日期 BETWEEN 'today' AND today", None),
                                 ('SELECT count(o) FROM (o:订单) WHERE o.金额 < today', None)):
                with self.subTest(text=text):
                    status, body = self.query(ann, text, **({'params': params} if params else {}))
                    self.assertEqual(status, 400, body)
                    if 'LIST' not in text and 'BETWEEN' not in text and '金额' not in text:
                        with mock.patch.object(workspace_questions, 'ROW_ANSWERS', False):
                            self.assertEqual(self.query(ann, text, **({'params': params} if params else {})), (status, body))
            written = self.ask(ann, model, '今天之前的订单有多少？', {'text': "SELECT count(o) FROM (o:订单) WHERE o.承诺日期 < 'today'"}, writes='query')
            self.assertEqual(written['status'], 'query_limit', written)
            self.assertNotIn('today', written)
            bare = self.ask(ann, model, '今天之前的订单有多少？', {'text': 'SELECT count(o) FROM (o:订单) WHERE o.承诺日期 < today'}, writes='query')
            self.assertEqual((bare['status'], bare['today']['date']), ('answered', '2026-06-15'), bare)
            conn = workspace_store.open_workspace(out / 'workspace.sqlite')
            try:   # a board's query reads no today: a quoted 'today' is refused as it always was
                with self.assertRaises(workspace_questions.QaRefused):
                    workspace_questions.run_text(conn, None, "SELECT count(o) FROM (o:订单) WHERE o.承诺日期 < 'today'")
            finally:
                conn.close()

    def test_a_saved_list_keeps_no_rows_and_is_worked_out_again_for_the_person_reopening_it(self):
        model = Scripted(item(LIST_VIEW, VIEW_USED))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base)
            ann, admin = team['ann'], team['admin']
            saved = self.ask(ann, model, '哪些加急订单是高风险的？', item(LIST_VIEW, VIEW_USED))
            kept = sqlite3.connect(out / 'workspace.sqlite').execute('SELECT answer_json FROM qa_question WHERE id = ?', (saved['id'],)).fetchone()[0]
            self.assertNotIn('rows', json.loads(kept)['answer']['objects'])
            for key in URGENT_HIGH:
                self.assertNotIn(key, kept)
            reopened = ann.get(f'/api/workspace/ask/{saved["id"]}')[1]
            self.assertEqual((reopened['again'], keys(reopened)), (True, URGENT_HIGH), reopened)
            # a row rule given to Ann since: reopened, it says the rows she could see then are not the ones now (as a number does), and asked again she gets her rows
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH001', 'user_ids': [self.user_id(admin, 'ann')]}]})[0], 200)
            self.assertIn('withheld', ann.get(f'/api/workspace/ask/{saved["id"]}')[1])
            mine = self.ask(ann, model, '哪些加急订单是高风险的？', item(LIST_VIEW, VIEW_USED))
            self.assertEqual(keys(mine), sorted(k for k in URGENT_HIGH if next(r for r in ORDER_ROWS if r['订单号'] == k)['客户编号'] == 'KH001'))

    def test_a_reopened_list_pages(self):
        reply = item({'start': 'order', 'where': [], 'list': {'limit': 10}})
        model = Scripted(reply)
        with self.service(gateway=model) as (base, out):
            ann = self.setup(base, view=False)['ann']
            saved = self.ask(ann, model, '列出全部订单', reply)
            self.assertEqual(keys(saved), sorted(r['订单号'] for r in ORDER_ROWS)[:10])
            second = ann.get(f'/api/workspace/ask/{saved["id"]}?page=2')[1]
            self.assertEqual((second['answer']['objects']['page'], keys(second)), (2, sorted(r['订单号'] for r in ORDER_ROWS)[10:20]))
            self.assertEqual(ann.get(f'/api/workspace/ask/{saved["id"]}?page=x')[0], 400)


class ListBesideANumber(Sample):
    """A list never takes away what main answers. A reply that, without its list or lookup, is a sum, an average, a share, a grouping, a ranking or a walk is
    answered exactly as that reply (the list or lookup is let be); a plain count with a list keeps its count as the headline, with what is beside it, and the
    rows come with it."""

    def without(self, body):
        """The response without what echoes the model's query (kept as it wrote it) and without query_text (see QueryText)."""
        return without_moments({k: [{n: v for n, v in s.items() if n != 'query'} for s in v] if k == 'steps' else v for k, v in body.items() if k not in ('query', 'query_text')})

    def test_a_list_beside_a_sum_a_share_a_grouping_or_a_ranking_is_let_be_and_a_lookup_beside_one_is_refused(self):
        urgent = [{'field': '紧急程度', 'equals': '加急'}]
        plain = {'start': 'order', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None}
        replies = [({**plain, 'measure': {'field': '金额', 'op': 'sum'}}, VIEW_USED), ({**plain, 'measure': {'field': '金额', 'op': 'average'}, 'where': urgent}, [{'id': 'orders.紧急程度=加急', 'direction': 'include', 'basis': '加急'}]),
                   ({**plain, 'share': {'field': '紧急程度', 'equals': '加急'}}, [{'id': 'orders.紧急程度=加急', 'direction': 'mention', 'basis': '加急'}]),
                   ({**plain, 'group_by': ['紧急程度']}, [{'id': f'orders.紧急程度={l}', 'direction': 'mention', 'basis': '紧急程度'} for l in ('普通', '加急')]),
                   ({**plain, 'group_by': ['客户编号'], 'measure': {'field': '金额', 'op': 'sum'}, 'top': 2, 'order': 'largest'}, [])]
        model = Scripted(item(LIST_VIEW))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base)
            for who in ('ann', 'vera'):
                for query, used in replies:
                    asked = '高风险加急订单的金额？' if used == VIEW_USED else '订单的金额？'
                    plain_answer = self.ask(team[who], model, asked, item(query, used))
                    self.assertEqual(plain_answer['status'], 'answered', plain_answer)
                    for extra in ({'list': {}}, {'list': {'properties': ['金额']}}, {'list': True}, {'list': {'limit': 99}}):
                        with self.subTest(who=who, query=query, extra=extra):
                            got = self.ask(team[who], model, asked, item({**query, **extra}, used))
                            self.assertEqual(self.without(got), self.without(plain_answer))
                            self.assertEqual(got['query'], {**query, **extra})   # what the model wrote is kept as it wrote it
                    for extra in ({'lookup': {'订单号': 'DD20260003'}}, {'lookup': {'订单号': 'DD20260003'}, 'list': {}}):   # a lookup is a condition: never dropped to give a number
                        with self.subTest(who=who, query=query, extra=extra):
                            got = self.ask(team[who], model, asked, item({**query, **extra}, used))
                            self.assertEqual(got['status'], 'query_limit', got)
                            self.assertIn('lookup', got['reason'])
                            self.assertNotIn('answer', got)

    def test_a_count_with_a_list_keeps_its_count_and_what_is_beside_it_and_the_rows_come_with_it(self):
        model = Scripted(item(LIST_VIEW))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base)
            for who in ('ann', 'vera'):
                for asked, used, total in (('高风险加急订单有多少？', VIEW_USED, len(URGENT_HIGH)), ('订单有多少？', [], len(ORDER_ROWS))):
                    counted = self.ask(team[who], model, asked, item({'start': 'order', 'where': []}, used))
                    listed = self.ask(team[who], model, asked, item({'start': 'order', 'where': [], 'list': {'properties': ['金额']}}, used))
                    self.assertEqual((listed['status'], (listed.get('answer') or {}).get('total')), ('answered', total), listed)
                    self.assertEqual({k: v for k, v in listed['answer'].items() if k != 'objects'}, counted['answer'])
                    self.assertEqual(listed['beside'], counted['beside'])
                    self.assertEqual(len(keys(listed)), min(total, 50))
                    from ontology_poc_generator.checked_numbers import answer_number
                    self.assertEqual(answer_number(listed), total)   # held against a number, a list is its count
            lookup = self.ask(team['ann'], model, 'DD20260003？', item({'start': 'order', 'lookup': {'订单号': 'DD20260003'}}))
            from ontology_poc_generator.checked_numbers import answer_number
            self.assertIsNone(answer_number(lookup))   # one object is no number


class LookupIsACondition(Sample):
    """A lookup is a condition: a reply that carries one never gives a number, whatever else it says (main refuses every non-empty lookup as a shape the
    query format cannot express; with the switch on, only a lookup alone is answered, and its answer is one object, never a number)."""

    def test_no_reply_carrying_a_lookup_ever_gives_a_number(self):
        from ontology_poc_generator.checked_numbers import answer_number
        plain = {'start': 'order', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None}
        urgent_used = [{'id': 'orders.紧急程度=加急', 'direction': 'include', 'basis': '加急'}]
        shapes = [{}, {'measure': {'field': '金额', 'op': 'sum'}}, {'measure': {'field': '金额', 'op': 'average'}}, {'share': {'field': '紧急程度', 'equals': '加急'}},
                  {'group_by': ['紧急程度']}, {'group_by': [{'via': [], 'field': '客户编号'}], 'measure': {'field': '金额', 'op': 'sum'}, 'top': 1, 'order': 'largest'},
                  {'where': [{'field': '紧急程度', 'equals': '加急'}]}, {'list': {}}, {'list': True}, {'where': [{'field': '承诺日期', 'less_than': 'today'}]}]
        lookups = [{'订单号': 'DD20260003'}, {'订单号': 'DD20269999'}, {'客户编号': 'KH001'}, {'订单号': 'DD20260003', '金额': '1'}, 'DD20260003', ['DD20260003']]
        model = Scripted('not json')
        from ontology_poc_generator import ask_budget
        with self.service(gateway=model) as (base, out), mock.patch.object(ask_budget, 'PERSON_LIMIT', 10000):   # many asks here: the hourly cap is not what this is about
            team = self.setup(base)
            for who in ('ann', 'vera'):
                for shape in shapes:
                    for key in lookups:
                        for used in ([], VIEW_USED, urgent_used):
                            with self.subTest(who=who, shape=shape, key=key, used=used):
                                body = self.ask(team[who], model, '订单 DD20260003 的金额？', item({**plain, **shape, 'lookup': key}, used))
                                self.assertIsNone(answer_number(body), body)
                                answer = body.get('answer')
                                self.assertTrue(answer is None or ('lookup' in answer and set(answer) == {'total', 'lookup', 'objects'}), body)
                                if shape and not (set(shape) <= {'where', 'list'}):
                                    self.assertEqual(body['status'], 'query_limit', body)   # beside a number: refused, as main refuses it


class QueryText(Sample):
    """query_text is written by code from the query that was run, never taken from what the model wrote: run again as a written query, it gives the same answer."""

    def test_query_text_is_the_query_that_ran(self):
        plain = {'start': 'order', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None}
        urgent = {'field': '紧急程度', 'equals': '加急'}
        urgent_used = [{'id': 'orders.紧急程度=加急', 'direction': 'include', 'basis': '加急'}]
        by_urgency = [{'id': f'orders.紧急程度={l}', 'direction': 'mention', 'basis': '紧急程度'} for l in ('普通', '加急')]
        replies = [
            ('订单有哪些？', {**plain, 'list': {}}, []), ('订单有哪些？', {**plain, 'list': True}, []), ('加急订单有哪些？', {**plain, 'where': [urgent], 'list': {'properties': ['orders.金额']}}, urgent_used),
            ('订单有哪些？', {'start': 'order', 'where': [], 'list': {'limit': 5}}, []), ('订单的金额合计？', {**plain, 'measure': {'field': '金额', 'op': 'sum'}, 'list': {}}, []),
            ('订单的金额合计？', {**plain, 'measure': {'field': '金额', 'op': 'sum'}, 'list': True}, []),
            ('各紧急程度的订单？', {**plain, 'group_by': [{'via': [], 'field': '紧急程度'}], 'list': {'properties': ['金额']}}, by_urgency),
            ('订单 DD20260003？', {'start': 'order', 'lookup': {'订单号': 'DD20260003'}}, []), ('订单 DD20260003？', {**plain, 'lookup': {'订单号': 'DD20260003'}}, []),
            ('承诺日期早于今天的订单有哪些？', {**plain, 'where': [{'field': '承诺日期', 'less_than': 'today'}], 'list': True}, []),
            ('承诺日期早于今天的订单有多少？', {**plain, 'where': [{'field': '承诺日期', 'less_than': 'today'}]}, []),
        ]
        model = Scripted('not json')
        with self.service(gateway=model) as (base, out), mock.patch.object(workspace_questions, '_today', lambda: ('2026-06-15', 'UTC+08:00')):
            ann = self.setup(base, view=False)['ann']
            for asked, query, used in replies:
                with self.subTest(query=query):
                    body = self.ask(ann, model, asked, item(query, used))
                    self.assertEqual(body['status'], 'answered', body)
                    status, again = self.query(ann, body['query_text'])
                    self.assertEqual((status, again['answer']), (200, body['answer']), body['query_text'])
                    self.assertEqual(body['query'], query)   # the model's query is kept as it wrote it
            summed = self.ask(ann, model, '订单的金额合计？', item({**plain, 'measure': {'field': '金额', 'op': 'sum'}}))
            for extra in ({'list': {}}, {'list': True}):
                self.assertEqual(self.ask(ann, model, '订单的金额合计？', item({**plain, 'measure': {'field': '金额', 'op': 'sum'}, **extra}))['query_text'], summed['query_text'])
            self.assertTrue(self.ask(ann, model, '订单有哪些？', item({**plain, 'list': True}))['query_text'].startswith('SELECT LIST o\n'))


class Privacy(Sample):
    """What a person who may not see a row, a column or a definition is told, compared as whole responses with what they would be told if it did not exist."""

    def test_a_key_outside_the_askers_row_rule_answers_as_a_key_nobody_has(self):
        lookup = lambda key: item({'start': 'order', 'lookup': {'订单号': key}})
        model = Scripted(lookup('x'))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base, view=False)
            admin, vera = team['admin'], team['vera']
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH001', 'user_ids': [self.user_id(admin, 'vera')]}]})[0], 200)
            theirs = next(r['订单号'] for r in ORDER_ROWS if r['客户编号'] == 'KH002')
            mine = next(r['订单号'] for r in ORDER_ROWS if r['客户编号'] == 'KH001')
            for ask in (lambda key: self.query(vera, f"SELECT ONE o FROM (o:订单) WHERE o.订单号 = '{key}'")[1],
                        lambda key: self.query(vera, 'SELECT ONE o FROM (o:订单) WHERE o.订单号 = $k', params={'k': key})[1],
                        lambda key: self.ask(vera, model, f'订单 {key} 的金额？', lookup(key))):
                hidden, missing = ask(theirs), ask('DD20269999')
                self.assertEqual(hidden['status'], 'no_data', hidden)
                self.assertEqual(without_moments(hidden).replace(theirs, 'KEY'), without_moments(missing).replace('DD20269999', 'KEY'))
                self.assertEqual(ask(mine)['answer']['total'], 1)
            self.assertEqual(self.query(admin, f"SELECT ONE o FROM (o:订单) WHERE o.订单号 = '{theirs}'")[1]['answer']['total'], 1)   # an admin sees every row

    def test_rows_outside_the_askers_row_rule_answer_as_rows_that_are_not_there(self):
        texts = ("SELECT LIST o FROM (o:订单) WHERE o.紧急程度 = '加急'", 'SELECT LIST o.金额 FROM (o:订单) LIMIT 3', "SELECT count(o) FROM (o:订单) WHERE o.紧急程度 = '加急'")
        got = []
        for rows in (ORDER_ROWS, [r for r in ORDER_ROWS if r['客户编号'] == 'KH001']):
            with self.service(gateway=Scripted('not json')) as (base, out):
                team = self.setup(base, view=False, orders=rows)
                admin = team['admin']
                self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH001', 'user_ids': [self.user_id(admin, 'vera')]}]})[0], 200)
                got.append([without_moments(self.query(team['vera'], t)[1]) for t in texts])
        self.assertEqual(got[0], got[1])
        listed = json.loads(got[0][0])
        self.assertEqual((listed['answer']['total'], [l['name'] for l in listed['limited_by_rule']]), (sum(r['客户编号'] == 'KH001' and r['紧急程度'] == '1' for r in ORDER_ROWS), ['订单']))

    def test_a_hidden_column_answers_as_a_column_the_type_does_not_have(self):
        texts = ("SELECT LIST o FROM (o:订单) WHERE o.紧急程度 = '加急'", "SELECT ONE o FROM (o:订单) WHERE o.订单号 = 'DD20260003'")
        without = {**ORDER, 'properties': [p for p in ORDER['properties'] if p['column'] != '承诺日期']}
        got = []
        for hidden in (True, False):
            with self.service(gateway=Scripted('not json')) as (base, out):
                team = self.setup(base, view=False, formula=False, order_type=ORDER if hidden else without)
                admin, bob = team['admin'], team['bob']
                if hidden:
                    self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'order', 'column': '承诺日期', 'visible_to': [self.user_id(admin, 'ann')]})[0], 200)
                responses = [without_moments(self.query(bob, t)[1]) for t in texts]
                named, other = self.query(bob, 'SELECT LIST o.承诺日期 FROM (o:订单)'), self.query(bob, 'SELECT LIST o.承诺时间 FROM (o:订单)')
                self.assertEqual((named[0], other[0]), (400, 400))
                responses.append(named[1]['error'].replace('承诺日期', 'X') == other[1]['error'].replace('承诺时间', 'X'))
                got.append(responses)
        self.assertEqual(got[0], got[1])
        self.assertTrue(got[0][-1])
        self.assertNotIn('承诺日期', got[0][0] + got[0][1])

    def test_nothing_sent_to_the_model_holds_a_row_value(self):
        lookup = item({'start': 'measure', 'lookup': {'措施编号': 'M-17'}})
        model = Scripted(item(LIST_VIEW, VIEW_USED))
        with self.service(gateway=model) as (base, out), mock.patch.object(workspace_questions, '_today', lambda: ('2026-06-15', 'UTC+08:00')):
            team = self.setup(base)
            for who in ('ann', 'vera'):
                self.ask(team[who], model, '哪些加急订单是高风险的？', item(LIST_VIEW, VIEW_USED))
                self.ask(team[who], model, '措施 M-17 的审批状态是什么？', lookup)
                self.ask(team[who], model, '承诺日期早于今天的加急订单有哪些？', item({'start': 'order', 'where': [{'field': '紧急程度', 'equals': '1'}, {'field': '承诺日期', 'less_than': 'today'}], 'list': {}}))
                self.ask(team[who], model, '哪些加急订单是高风险的？', {'text': 'SELECT LIST o FROM (o:订单)', 'views': ['高风险加急订单']}, writes='query')
                self.ask(team[who], model, '措施 M-17 的审批状态是什么？', {'text': "SELECT ONE m FROM (m:处置措施) WHERE m.措施编号 = 'M-17'"}, writes='query')
            values = {v for r in ORDER_ROWS for c, v in r.items() if c in ('订单号', '金额', '承诺日期')} | {r['订单号'] for r in MEASURE_ROWS} | {r['措施编号'] for r in MEASURE_ROWS if r['措施编号'] != 'M-17'}
            self.assertEqual(len(model.prompts), 10)
            for sent in model.prompts:
                found = sorted(v for v in values if v in sent)
                self.assertEqual(found, [], sent[sent.find(found[0]) - 300:sent.find(found[0]) + 100] if found else '')
            self.assertTrue(all('M-17' not in p or '"asked": "措施 M-17' in p for p in model.prompts))   # only where the person's question says it


class Hostile(Sample):
    KEYS = ("' OR '1'='1", "DD20260001'; DROP TABLE qa_question; --", 'DD20260001" OR "1"="1', '订单号一', 'x\x00y', 'DD' + '9' * 3000, '%', '_', 'DD2026000%')

    def test_a_key_value_is_data_never_sql(self):
        model = Scripted('not json')
        with self.service(gateway=model) as (base, out):
            team = self.setup(base, view=False)
            ann = team['ann']
            for key in self.KEYS:
                with self.subTest(key=key[:20]):
                    status, body = self.query(ann, 'SELECT ONE o FROM (o:订单) WHERE o.订单号 = $k', params={'k': key})
                    self.assertEqual((status, body['status']), (200, 'no_data'), body)
                    status, body = self.query(ann, 'SELECT LIST o FROM (o:订单) WHERE o.客户编号 = $k', params={'k': key})
                    self.assertEqual((status, body['status']), (200, 'no_data'), body)
                    if len(key) < 100 and '\x00' not in key:
                        literal = key.replace("'", "''")
                        self.assertEqual(self.query(ann, f"SELECT ONE o FROM (o:订单) WHERE o.订单号 = '{literal}'")[1]['status'], 'no_data')
                    body = self.ask(ann, model, '这个订单的金额？', item({'start': 'order', 'lookup': {'订单号': key}}))
                    self.assertEqual(body['status'], 'no_data', body)
            self.assertEqual(self.query(ann, 'SELECT count(o) FROM (o:订单)')[1]['answer']['total'], 40)
            self.assertEqual(self.query(ann, "SELECT ONE o FROM (o:订单) WHERE o.订单号 = 'DD20260001'")[1]['answer']['total'], 1)
            self.assertEqual(sqlite3.connect(out / 'workspace.sqlite').execute('SELECT COUNT(*) FROM qa_question').fetchone()[0], len(self.KEYS))   # the table is there, one row per question

    def test_a_lookup_reads_only_the_rows_that_have_the_key(self):
        with self.service(gateway=Scripted('not json')) as (base, out):
            team = self.setup(base, view=False)
            admin = team['admin']
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH001', 'user_ids': [self.user_id(admin, 'vera')]}]})[0], 200)
            self.query(team['vera'], 'SELECT count(o) FROM (o:订单)')   # whatever is counted once (the value rules) is counted before
            real = workspace_store.dataset_records
            calls = []
            with mock.patch.object(workspace_questions, 'dataset_records', lambda *a: calls.append(a) or real(*a)):
                for who in ('admin', 'vera'):
                    status, body = self.query(team[who], "SELECT ONE o FROM (o:订单) WHERE o.订单号 = 'DD20260004'")
                    self.assertEqual((status, body['answer']['total'], calls), (200, 1, []), body)   # a lookup reads no dataset whole
                    self.query(team[who], "SELECT LIST o FROM (o:订单) WHERE o.订单号 = 'DD20260004'")
                    self.assertGreater(len(calls), 0)   # a list reads every row it may, as a count does
                    calls.clear()


class Tools(Sample):
    def test_the_mcp_tools_give_a_page_of_objects_with_the_total_and_say_their_limits(self):
        sent = []

        class Session:
            def request(self, path, payload=None):
                sent.append((path, payload))
                return {'status': 'answered', 'answer': {'total': 60, 'objects': {'columns': [{'column': '订单号'}], 'rows': [['DD1']], 'page': 2, 'pages': 2, 'page_size': 50}},
                        'definitions': [], 'text': 'SELECT LIST o FROM (o:订单)', 'today': {'date': '2026-06-15', 'time_zone': 'UTC+08:00'}, 'query_text': 'SELECT LIST o FROM (o:订单)'}
        got = mcp_server.ontopoc_query(Session(), {'text': 'SELECT LIST o FROM (o:订单)', 'page': 2})
        self.assertEqual(sent[-1], ('/api/workspace/query', {'text': 'SELECT LIST o FROM (o:订单)', 'page': 2}))
        self.assertEqual((got['answer']['total'], got['answer']['objects']['rows'], got['today']['date']), (60, [['DD1']], '2026-06-15'))
        asked = mcp_server.ask(Session(), {'question': '哪些订单？'})
        self.assertEqual(asked['answer']['objects']['page_size'], 50)
        tool = mcp_server.BY_NAME['ontopoc_query']
        self.assertIn('page', tool['inputSchema']['properties'])
        self.assertIn('SELECT LIST', tool['description'])
        self.assertIn('50', tool['description'])
        for name in ('ontopoc_query', 'ask'):
            self.assertEqual(mcp_server.BY_NAME[name]['annotations']['destructiveHint'], False)
        self.assertTrue(mcp_server.BY_NAME['ontopoc_query']['annotations']['readOnlyHint'])

    def test_a_token_gets_what_its_person_gets(self):
        with self.service(gateway=Scripted('not json')) as (base, out):
            team = self.setup(base, view=False)
            admin, vera = team['admin'], team['vera']
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH001', 'user_ids': [self.user_id(admin, 'vera')]}]})[0], 200)
            status, made = vera.post('/api/auth/tokens', {'label': 'agent'})
            self.assertEqual(status, 200, made)
            from tests.test_access import Client
            text = "SELECT LIST o FROM (o:订单) WHERE o.紧急程度 = '加急'"
            by_token = Client(base).post('/api/workspace/query', {'text': text}, origin=None, headers={'Authorization': f'Bearer {made["token"]}'})
            by_person = self.query(vera, text)
            self.assertEqual((by_token[0], keys(by_token[1])), (200, keys(by_person[1])), by_token)


class Shapes(Sample):
    """With the new shapes switched off, a reply that asks for them is answered as before; on, it gets objects."""

    def test_switched_off_a_list_a_lookup_today_and_a_view_formula_are_read_as_before(self):
        model = Scripted('not json')
        with self.service(gateway=model) as (base, out):
            team = self.setup(base, view=False)
            ann = team['ann']
            with mock.patch.object(workspace_questions, 'ROW_ANSWERS', False):
                for text in ('SELECT LIST o FROM (o:订单)', "SELECT ONE o FROM (o:订单) WHERE o.订单号 = 'DD20260001'", 'SELECT count(o) FROM (o:订单) WHERE o.承诺日期 < today'):
                    self.assertEqual(self.query(ann, text)[0], 400, text)
                counted = self.ask(ann, model, '哪些订单？', item(LIST_VIEW))   # an empty part is let be, as it always was: a count
                self.assertEqual((counted['status'], counted['answer']), ('answered', {'total': 40}))
                for reply in (item({'start': 'order', 'where': [], 'list': {'properties': ['金额']}}), item({'start': 'order', 'lookup': {'订单号': 'DD20260001'}})):
                    self.assertEqual(self.ask(ann, model, '哪些订单？', reply)['status'], 'query_limit')
                status, body = ann.post('/api/workspace/types/views', {**VIEW, 'name': '没有派生条件'})
                self.assertEqual(status, 200, body)
                self.assertNotIn('derived', next(v for v in ann.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == '没有派生条件'))
            self.assertEqual(self.query(ann, 'SELECT LIST o FROM (o:订单)')[1]['answer']['total'], 40)


class WithOtherNames(Sample):
    """Lists and lookups beside other names, value rules and the list of questions we need."""

    def test_a_view_named_by_its_other_name_lists_its_objects_and_is_refused_while_it_waits(self):
        model = Scripted(item(LIST_VIEW, VIEW_USED))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base, view=False)
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            self.assertEqual(ann.post('/api/workspace/types/views', {**VIEW, 'other_names': ['危险急单']})[0], 200)
            self.confirm_view(bob)
            body = self.ask(ann, model, '危险急单有哪些？', item(LIST_VIEW, [{'id': '高风险加急订单', 'direction': 'include', 'basis': '危险急单'}]))
            self.assertEqual((body['status'], keys(body)), ('answered', URGENT_HIGH), body)
            self.assertIn('危险急单', json.dumps(model.requests[-1], ensure_ascii=False))   # the model is told the other name, as for a number
            line = self.formula(ann)
            self.assertEqual(ann.post('/api/workspace/types/derived/update', {**HIGH_RISK, 'expression': 'if(金额 > 60000, 1, 0)', 'version': line['version']})[0], 200)
            for who in ('ann', 'vera'):
                asked = len(model.requests)
                refused = self.ask(team[who], model, '危险急单有哪些？', item(LIST_VIEW, VIEW_USED))
                counted = self.ask(team[who], model, '危险急单有哪些？', item({'start': 'order', 'where': []}, VIEW_USED))
                self.assertEqual((refused['status'], len(model.requests)), ('refused', asked), who)   # refused before the model is asked
                self.assertEqual(without_moments({k: v for k, v in refused.items() if k != 'query'}), without_moments({k: v for k, v in counted.items() if k != 'query'}), who)

    def test_a_view_on_a_derived_property_with_other_names_keeps_the_same_rows(self):
        model = Scripted(item(LIST_VIEW, VIEW_USED))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base, view=False, formula=False)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/derived', {**HIGH_RISK, 'other_names': ['风险高', '大额']})[0], 200)
            self.confirm_formula(bob)
            status, body = ann.post('/api/workspace/types/views', VIEW)
            self.assertEqual(status, 200, body)
            self.confirm_view(bob)
            self.assertEqual(keys(self.ask(ann, model, '哪些加急订单是高风险的？', item(LIST_VIEW, VIEW_USED))), URGENT_HIGH)
            line = self.formula(ann)   # another other name only: the formula stays confirmed, and so does the view on it
            self.assertEqual(ann.post('/api/workspace/types/derived/update', {**HIGH_RISK, 'other_names': ['风险高'], 'version': line['version']})[0], 200)
            self.assertEqual((self.formula(ann)['state'], self.view(ann)['state']), ('confirmed', 'confirmed'))
            self.assertEqual(keys(self.ask(ann, model, '哪些加急订单是高风险的？', item(LIST_VIEW, VIEW_USED))), URGENT_HIGH)

    def test_a_list_or_lookup_of_a_type_whose_value_rules_are_not_known_to_hold_is_refused_as_a_number_is(self):
        model = Scripted(item(LIST_VIEW))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base, view=False, formula=False, order_type={**ORDER, 'rules': [{'column': '金额', 'check': 'not_empty'}], 'other_names': ['单据']})
            bob = team['bob']
            conn = sqlite3.connect(out / 'workspace.sqlite')   # what an older version leaves: a count kept on this version that shows a broken row
            element, dataset, rows, kept = conn.execute("SELECT element_id, dataset_id, rows_checked, samples_json FROM check_result WHERE element_id = 'objtype:order' "
                                                        "AND check_type = 'value_rules' ORDER BY id DESC LIMIT 1").fetchone()
            conn.execute("INSERT INTO check_result(element_id, check_type, query, rows_checked, violations, samples_json, status, checked_at, dataset_id, null_key_rows) "
                         "VALUES (?, 'value_rules', '', ?, 1, ?, 'failed', '2026-11-22T00:00:00+00:00', ?, NULL)", (element, rows, json.dumps({**json.loads(kept), 'broken': [1]}), dataset))
            conn.commit()
            conn.close()
            counted = self.query(bob, 'SELECT count(o) FROM (o:订单)')[1]
            self.assertEqual(counted['status'], 'refused', counted)
            for text in ('SELECT LIST o FROM (o:订单)', "SELECT ONE o FROM (o:订单) WHERE o.订单号 = 'DD20260001'"):
                listed = self.query(bob, text)[1]
                self.assertEqual({k: v for k, v in listed.items() if k != 'text'}, {k: v for k, v in counted.items() if k != 'text'}, text)
            asked = len(model.requests)
            for reply in (item(LIST_VIEW), item({'start': 'order', 'lookup': {'订单号': 'DD20260001'}})):
                refused = self.ask(bob, model, '单据有哪些？', reply)
                self.assertEqual((refused['status'], refused['refusal']['kind']), ('refused', 'unsettled'))
            self.assertEqual(len(model.requests), asked)

    def test_a_list_given_to_a_question_we_need_that_expects_a_number_is_held_by_its_count(self):
        model = Scripted(item(LIST_VIEW, VIEW_USED))
        with self.service(gateway=model) as (base, out):
            team = self.setup(base)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            status, body = ann.post('/api/workspace/needed', {'question': '高风险加急订单有多少？', 'expect': {'kind': 'number', 'value': len(URGENT_HIGH)}})
            self.assertEqual(status, 200, body)
            found = next(q for q in bob.get('/api/workspace/needed')[1]['questions'] if q['question'] == '高风险加急订单有多少？')
            self.assertEqual(bob.post('/api/workspace/needed/confirm', {'id': found['id'], 'version': found['version']})[0], 200)
            status, body = admin.post('/api/workspace/needed/run', {'repeats': 1})
            self.assertEqual(status, 200, body)
            for _ in range(500):
                if body.get('running') is None:
                    break
                time.sleep(0.02)
                body = admin.get('/api/workspace/needed')[1]
            result = next(q for q in body['questions'] if q['question'] == '高风险加急订单有多少？')['result']
            self.assertEqual((result['outcome'], result['distinct']), ('passes', [{'number': len(URGENT_HIGH), 'status': 'answered', 'times': 1}]), result)   # the count stays the headline of a list
