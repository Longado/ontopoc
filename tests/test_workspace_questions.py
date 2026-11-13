"""Q&A on the workspace, walked through the real service on the seven planted tables with a model that writes the query it is told to write: it answers only from
confirmed definitions, names the definition when it refuses, never sends a row to the model, and keeps what each answer stood on. Expected numbers come from the
planted records counted here (16 cancelled orders out of 160, 3 orders naming KH099 which the customer table lacks)."""
import json

from ontology_poc_generator.recognition import ModelCompletion
from tests import test_workspace_store as planted
from tests.test_object_relations import CUSTOMER, RELATION, customers_mended
from tests.test_object_types import MEANINGS, ORDER, TABLES, shifted_orders_csv
from tests.test_two_person import SigningTestCase

ORDERS = planted.planted_bundle()['sources']['订单']['records']
CANCELLED = sum(1 for r in ORDERS if r['状态码'] == '2')
QUESTION = '取消的订单有多少？'
CANCELLED_QUERY = {'start': 'order', 'where': [{'field': '状态码', 'equals': '2'}], 'via': [], 'group_by': None, 'share': None, 'measure': None}
USED = [{'id': '订单.状态码=已取消', 'direction': 'include', 'basis': '取消的订单'}]


class AskModel:
    """Writes the item it was given for the question it is asked, and keeps every request it received."""

    def __init__(self, item):
        self.item, self.requests = item, []

    def complete_json(self, *, system_prompt, user_prompt, timeout_seconds=None):
        request = json.loads(user_prompt)
        self.requests.append(request)
        return ModelCompletion('test', 'test-model', json.dumps({'questions': [{'question': request['asked'], **self.item}]}, ensure_ascii=False))


def cancelled(query=CANCELLED_QUERY, used=USED):
    return {'reasoning': '订单里状态码为 2 的是已取消', 'query': query, 'definitions_used': used}


class QuestionTests(SigningTestCase):
    def team(self, base):
        team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        return team

    def confirm(self, client, name, column=None):
        shown = client.get(f'/api/workspace/types/{name}')[1]
        shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
        status, body = client.post('/api/workspace/types/confirm', {'id': name, 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})
        self.assertEqual(status, 200, body)

    def confirmed_orders(self, team):
        self.assertEqual(team['ann'].post('/api/workspace/types', ORDER)[0], 200)
        self.confirm(team['bob'], 'order', '状态码')
        self.confirm(team['bob'], 'order')

    def ask(self, client, question=QUESTION):
        return client.post('/api/workspace/ask', {'question': question})

    def test_cancelled_orders_are_answered_with_their_definitions_and_versions_and_refused_once_the_codes_shift(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.confirmed_orders(team)
            status, body = self.ask(ann)
            self.assertEqual(status, 200, body)
            self.assertEqual((body['status'], body['answer']['total'], body['reasoning']), ('answered', CANCELLED, '订单里状态码为 2 的是已取消'))
            self.assertEqual(CANCELLED, 16)
            self.assertEqual([(d['kind'], d['name'], d['confirmed_by'], d['state']) for d in body['definitions']],
                            [('type', '订单', 'Bob', 'confirmed'), ('meaning', '订单.状态码', 'Bob', 'confirmed')])
            self.assertEqual(body['datasets'], {'订单': 1})
            self.assertEqual([s['name'] for s in body['steps']], ['理解问题', '找对象类型', '找关系', '改写成查询', '核对定义', '结果'])
            self.assertIn('已取消', body['path'])
            # the model was told the catalog and the meanings, and read no row: no order number, no amount
            sent = json.dumps(model.requests[0], ensure_ascii=False)
            self.assertIn('已取消', sent)
            self.assertNotIn(ORDERS[0]['订单号'], sent)
            state_column = next(a for a in model.requests[0]['ontology']['object_types'][0]['attributes'] if a['path'] == '状态码')
            self.assertEqual((state_column['values'], state_column['type'], state_column['meanings']), (['0', '1', '2'], 'integer', {'0': '已交付', '1': '生产中', '2': '已取消'}))
            order_number = next(a for a in model.requests[0]['ontology']['object_types'][0]['attributes'] if a['path'] == '订单号')
            self.assertNotIn('values', order_number)   # a key identifies objects: its values are not catalog
            # the same question after the codes shift: refused before the model is asked, naming the meaning, the reason and who could confirm it
            saved = body['id']
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            asked_before = len(model.requests)
            status, refused = self.ask(ann)
            self.assertEqual(status, 200, refused)
            self.assertEqual(refused['status'], 'refused')
            self.assertEqual(len(model.requests), asked_before)
            names = [d['name'] for d in refused['refusal']['definitions']]
            self.assertEqual(names, ['订单.状态码', '订单'])
            meaning = refused['refusal']['definitions'][0]
            self.assertEqual((meaning['state'], meaning['who_can_confirm']), ('needs_look', ['Bob', '管理员']))
            self.assertIn('取值变了', meaning['reason'])
            self.assertIn('订单.状态码', refused['reason'])
            self.assertIn(meaning['reason'], refused['reason'])
            # the answer saved before says its data has a newer version and that its definitions are not as they were
            status, reopened = ann.get(f'/api/workspace/ask/{saved}')
            self.assertEqual(status, 200, reopened)
            self.assertEqual(reopened['stale'], [{'dataset': '订单', 'read': 1, 'now': 2}])
            self.assertEqual({(c['name'], c['state']) for c in reopened['changed']}, {('订单', 'needs_look'), ('订单.状态码', 'needs_look')})
            self.assertEqual(reopened['answer']['total'], CANCELLED)   # what it said then, unchanged
            scope = ann.get('/api/workspace/ask')[1]
            self.assertEqual(scope['types'], [])   # nothing in scope: 订单 waits for another look
            self.assertEqual([d['name'] for d in scope['left_out']], ['订单'])
            self.assertEqual([h['question'] for h in scope['history']], [QUESTION, QUESTION])

    def test_a_viewers_scope_leaves_out_unconfirmed_and_hidden_types_and_questions_are_each_persons_own(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            self.confirmed_orders(team)
            self.assertEqual(ann.post('/api/workspace/types', CUSTOMER)[0], 200)   # proposed, not confirmed
            self.assertEqual(vera.get('/api/workspace/ask')[1]['types'], [{'id': 'order', 'name': '订单'}])
            self.assertEqual(vera.get('/api/workspace/ask')[1]['left_out'], [])   # a viewer is not told what waits
            self.assertEqual([t['id'] for t in bob.get('/api/workspace/ask')[1]['types']], ['order'])
            self.assertEqual([d['name'] for d in bob.get('/api/workspace/ask')[1]['left_out']], ['客户'])
            status, answered = self.ask(vera)
            self.assertEqual((status, answered['answer']['total']), (200, CANCELLED))
            # a question that names the unconfirmed 客户 is refused, with who could confirm it
            status, refused = self.ask(bob, '客户有多少？')
            self.assertEqual((refused['status'], refused['refusal']['definitions'][0]['name'], refused['refusal']['definitions'][0]['who_can_confirm']), ('refused', '客户', ['Bob', '管理员']))
            self.assertIn('还没有另一位确认', refused['reason'])
            # a viewer's question is saved for that viewer only
            self.assertEqual([h['id'] for h in vera.get('/api/workspace/ask')[1]['history']], [answered['id']])
            self.assertEqual(ann.get(f'/api/workspace/ask/{answered["id"]}')[0], 404)
            self.assertEqual(admin.get(f'/api/workspace/ask/{answered["id"]}')[0], 404)
            self.assertEqual(vera.get(f'/api/workspace/ask/{answered["id"]}')[0], 200)
            # the type is restricted to Bob: Vera's scope is empty and what she asked before is withheld; nothing is said about the type to a question she asks now
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': [3]})[0], 200)
            self.assertEqual(vera.get('/api/workspace/ask')[1]['types'], [])
            asked_before = len(model.requests)
            status, nothing = self.ask(vera)
            self.assertEqual((nothing['status'], nothing['refusal']['kind'], nothing['refusal']['left_out']), ('refused', 'not_in_scope', []))
            self.assertEqual(len(model.requests), asked_before)
            self.assertNotIn('订单', json.dumps({k: v for k, v in nothing.items() if k != 'question'}, ensure_ascii=False))
            status, withheld = vera.get(f'/api/workspace/ask/{answered["id"]}')
            self.assertEqual((status, withheld['withheld']), (200, {'types': ['订单']}))
            self.assertNotIn('answer', withheld)

    def test_a_filter_the_model_claims_but_the_query_does_not_apply_is_refused(self):
        model = AskModel(cancelled(query={'start': 'order', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None},
                                   used=[{'id': '订单.状态码=已取消', 'direction': 'exclude', 'basis': '不算已取消'}]))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            status, body = self.ask(team['ann'], '不算已取消的订单有多少？')
            self.assertEqual((status, body['status']), (200, 'definition_unmet'))
            self.assertNotIn('answer', body)
            self.assertEqual(body['refusal']['definitions'][0]['definition'], '已取消')

    def test_a_column_marked_not_to_send_values_goes_to_the_model_without_its_values_or_meanings(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            self.assertEqual(team['vera'].post('/api/workspace/types/privacy', {'id': 'order', 'column': '状态码', 'hide_values': True})[0], 403)
            status, body = team['ann'].post('/api/workspace/types/privacy', {'id': 'order', 'column': '状态码', 'hide_values': True})
            self.assertEqual((status, body), (200, {'hide_values': True}))
            detail = team['bob'].get('/api/workspace/types/order')[1]
            self.assertEqual({p['column']: p['hide_values'] for p in detail['properties']}, {'订单号': False, '金额': False, '状态码': True})
            self.assertEqual(detail['state'], 'confirmed')   # the switch is not part of the definition
            self.assertIn('不再把取值发给模型', team['bob'].get('/api/workspace/types/order/log')[1]['log'][0]['text'])
            self.assertEqual(team['ann'].post('/api/workspace/types/privacy', {'id': 'order', 'column': '没有这一列', 'hide_values': True})[0], 400)
            self.ask(team['ann'])
            request = model.requests[0]
            state_column = next(a for a in request['ontology']['object_types'][0]['attributes'] if a['path'] == '状态码')
            self.assertEqual(state_column, {'path': '状态码', 'type': 'integer'})
            self.assertNotIn('definitions', request)   # the meaning of a column marked this way is not told either

    def test_orders_whose_customer_is_missing_are_answered_from_the_relation_check_and_the_answer_stands_on_both_types_and_the_relation(self):
        unmatched = {'reasoning': '问的是订单里客户编号在客户表里找不到的', 'query': None, 'missing': 'query_language', 'definitions_used': [],
                     'unmatched_relation': {'relation': 'order_customer', 'direction': 'many_without_one', 'other_conditions': False}}
        model = AskModel(unmatched)
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types', {k: v for k, v in ORDER.items() if k != 'enums'} | {'properties': [{'column': '订单号'}, {'column': '金额'}]})[0], 200)
            self.assertEqual(ann.post('/api/workspace/types', CUSTOMER)[0], 200)
            self.assertEqual(ann.post('/api/workspace/relations', RELATION)[0], 200)
            for name in ('order', 'customer'):
                self.confirm(bob, name)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
            shown = bob.get('/api/workspace/relations/order_customer')[1]
            self.assertEqual(bob.post('/api/workspace/queue/confirm', {'element': 'relation:order_customer', 'version': shown['version'], 'seen': shown['check']['signature']})[0], 200)
            question = '有多少订单的客户在客户表里找不到？'
            status, body = self.ask(ann, question)
            self.assertEqual(status, 200, body)
            self.assertEqual(body['status'], 'answered', body)
            self.assertEqual(body['answer']['total'], 3)
            self.assertEqual(body['answer']['relation_gap']['keys'], ['KH099'])
            self.assertEqual(sorted(d['name'] for d in body['definitions']), ['客户', '订单', '订单属于客户'])
            self.assertEqual(body['datasets'], {'订单': 1, '客户': 2})
            status, viewer_body = self.ask(team['vera'], question)
            self.assertEqual(viewer_body['answer']['relation_gap'].get('keys'), None)   # a viewer reads the count, not which customers
            self.assertEqual(viewer_body['answer']['total'], 3)
