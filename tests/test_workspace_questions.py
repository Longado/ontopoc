"""Q&A on the workspace, walked through the real service on the seven planted tables with a model that writes the query it is told to write: it answers only from
confirmed definitions, names the definition when it refuses, never sends a row to the model, and keeps what each answer stood on. Expected numbers come from the
planted records counted here (16 cancelled orders out of 160, 3 orders naming KH099 which the customer table lacks)."""
import json
import sqlite3

from ontology_poc_generator.recognition import ModelCompletion
from tests import test_workspace_store as planted
from tests.test_object_relations import CUSTOMER, RELATION, customers_mended
from tests.test_object_types import COMMIT, LATEST_COMMIT, LATEST_STOCK, MEANINGS, ORDER, STOCK, TABLES, VALID, shifted_orders_csv
from tests.test_two_person import SigningTestCase

ORDERS = planted.planted_bundle()['sources']['订单']['records']
CANCELLED = sum(1 for r in ORDERS if r['状态码'] == '2')
QUESTION = '取消的订单有多少？'
CANCELLED_QUERY = {'start': 'order', 'where': [{'field': '状态码', 'equals': '2'}], 'via': [], 'group_by': None, 'share': None, 'measure': None}
USED = [{'id': '订单.状态码=已取消', 'direction': 'include', 'basis': '取消的订单'}]
ALL_ORDERS = {'start': 'order', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None}


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

    def confirm_view(self, client, type_name, name):
        shown = next(v for v in client.get(f'/api/workspace/types/{type_name}/views')[1]['views'] if v['name'] == name)
        status, body = client.post('/api/workspace/types/views/confirm', {'id': name, 'version': shown['version'], 'seen': shown['seen']})
        self.assertEqual(status, 200, body)

    def test_a_confirmed_view_answers_valid_orders_naming_the_view_and_who_confirmed_it_and_the_question_is_refused_once_the_codes_shift(self):
        model = AskModel(cancelled(query=ALL_ORDERS, used=[{'id': '有效订单', 'direction': 'include', 'basis': '有效订单'}]))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            self.confirmed_orders(team)
            self.assertEqual(ann.post('/api/workspace/types/views', VALID)[0], 200)
            # put forward and not yet confirmed: the question that names the view is refused before the model is asked, with its state and who could confirm
            status, refused = self.ask(ann, '有效订单有多少？')
            self.assertEqual((status, refused['status'], len(model.requests)), (200, 'refused', 0))
            self.assertEqual([(d['kind'], d['name'], d['state'], d['who_can_confirm']) for d in refused['refusal']['definitions']], [('view', '有效订单', 'checked', ['Bob', '管理员'])])
            self.assertIn('视图「有效订单」', refused['reason'])
            self.confirm_view(bob, 'order', '有效订单')
            status, body = self.ask(ann, '有效订单有多少？')
            self.assertEqual((status, body['status'], body['answer']['total']), (200, 'answered', 144))
            self.assertEqual((CANCELLED, len(ORDERS)), (16, 160))   # 160 planted orders, 16 cancelled: 144 are left
            self.assertEqual([(d['kind'], d['name'], d['confirmed_by'], d['state']) for d in body['definitions']], [('type', '订单', 'Bob', 'confirmed'), ('view', '有效订单', 'Bob', 'confirmed')])
            self.assertEqual(body['evidence']['views'], [{'name': '有效订单', 'kind': 'filter', 'source': '订单', 'rows': 144, 'from': '订单里只留 状态码 不是「已取消」 的行', 'confirmed_by': 'Bob'}])
            self.assertEqual([u['how'] for u in body['understood']], ['读视图 有效订单'])
            told = model.requests[0]['definitions']
            self.assertIn({'id': '有效订单', 'name': '有效订单', 'kind': 'view', 'means': '订单里只留 状态码 不是「已取消」 的行'}, told)
            self.assertEqual(vera.get('/api/workspace/ask')[1]['views'], [{'id': '有效订单', 'name': '有效订单', 'type': 'order'}])
            # the model may also say the question leaves out the meaning: the view that leaves it out is read, and nothing else
            model.item = cancelled(query=ALL_ORDERS, used=[{'id': '订单.状态码=已取消', 'direction': 'exclude', 'basis': '不算已取消'}])
            status, body = self.ask(ann, '不算已取消的订单有多少？')
            self.assertEqual((body['status'], body['answer']['total'], [u['how'] for u in body['understood']]), ('answered', 144, ['读视图 有效订单']))
            self.assertEqual([d['name'] for d in body['definitions'] if d['kind'] == 'view'], ['有效订单'])
            model.item = cancelled(query=ALL_ORDERS, used=[{'id': '有效订单', 'direction': 'include', 'basis': '有效订单'}])
            saved = self.ask(ann, '有效订单有多少？')[1]['id']
            # the codes shift: the meaning, the type and the view need a look; the question is refused naming all three and nobody is asked
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            asked_before = len(model.requests)
            status, refused = self.ask(ann, '有效订单有多少？')
            self.assertEqual((status, refused['status'], len(model.requests)), (200, 'refused', asked_before))
            self.assertEqual([(d['kind'], d['name'], d['state']) for d in refused['refusal']['definitions']],
                             [('meaning', '订单.状态码', 'needs_look'), ('type', '订单', 'needs_look'), ('view', '有效订单', 'needs_look')])
            self.assertIn('视图「有效订单」', refused['reason'])
            reopened = ann.get(f'/api/workspace/ask/{saved}')[1]
            self.assertEqual({(c['name'], c['state']) for c in reopened['changed']}, {('订单', 'needs_look'), ('有效订单', 'needs_look')})
            self.assertEqual(reopened['answer']['total'], 144)   # what it said then
            self.assertEqual(ann.get('/api/workspace/ask')[1]['views'], [])   # nothing in scope any more

    def test_latest_views_answer_the_latest_snapshot_and_the_latest_commitment_and_the_numbers_are_those_counted_by_hand(self):
        stock_query = {'start': 'stock', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': '库存数量', 'op': 'sum'}}
        commit_query = {'start': 'commit', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': '承诺数量', 'op': 'sum'}}
        model = AskModel(cancelled(query=stock_query, used=[{'id': '最新快照', 'direction': 'include', 'basis': '最新快照'}]))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            for t, view in ((STOCK, LATEST_STOCK), (COMMIT, LATEST_COMMIT)):
                self.assertEqual(ann.post('/api/workspace/types', t)[0], 200)
                self.confirm(bob, t['english_name'])
                self.assertEqual(ann.post('/api/workspace/types/views', view)[0], 200)
                self.confirm_view(bob, t['english_name'], view['name'])
            # by hand from the planted rows: the greatest month of each product, and the greatest version of each order
            snapshots = planted.planted_bundle()['sources']['库存快照']['records']
            newest_month = {}
            for r in snapshots:
                newest_month[r['产品编号']] = max(newest_month.get(r['产品编号'], ''), r['快照月份'])
            stock_now = sum(int(r['库存数量']) for r in snapshots if r['快照月份'] == newest_month[r['产品编号']])
            commitments = planted.planted_bundle()['sources']['订单承诺']['records']
            newest_version = {}
            for r in commitments:
                newest_version[r['订单号']] = max(newest_version.get(r['订单号'], 0), int(r['承诺版本']))
            commit_now = sum(int(r['承诺数量']) for r in commitments if int(r['承诺版本']) == newest_version[r['订单号']])
            self.assertEqual((stock_now, commit_now), (1115, 552))
            status, body = self.ask(ann, '最新快照的库存数量一共多少？')
            self.assertEqual((status, body['status'], body['answer']['measure']['value'], body['answer']['total']), (200, 'answered', 1115, 12), body)   # 1115 over 12 rows
            self.assertEqual([(v['name'], v['rows']) for v in body['evidence']['views']], [('最新快照', 12)])
            model.item = cancelled(query=commit_query, used=[{'id': '最新承诺', 'direction': 'include', 'basis': '最新承诺'}])
            status, body = self.ask(ann, '最新承诺的承诺数量一共多少？')
            self.assertEqual((body['status'], body['answer']['measure']['value'], body['answer']['total']), ('answered', 552, 60))
            self.assertEqual([(v['name'], v['rows'], v['confirmed_by']) for v in body['evidence']['views']], [('最新承诺', 60, 'Bob')])
            # the same measure without the view adds up every snapshot: the view is what makes it "latest"
            model.item = cancelled(query=stock_query, used=[])
            status, body = self.ask(ann, '库存数量一共多少？')
            self.assertEqual((body['answer']['measure']['value'], body['answer']['total']), (sum(int(r['库存数量']) for r in snapshots), 72))
            self.assertNotIn('views', body.get('evidence') or {})

    def test_a_view_on_a_column_marked_not_to_send_values_is_not_offered_to_the_model(self):
        model = AskModel(cancelled(query=ALL_ORDERS, used=[]))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.confirmed_orders(team)
            self.assertEqual(ann.post('/api/workspace/types/views', VALID)[0], 200)
            self.confirm_view(bob, 'order', '有效订单')
            self.assertEqual(ann.post('/api/workspace/types/privacy', {'id': 'order', 'column': '状态码', 'hide_values': True})[0], 200)
            self.assertEqual(ann.get('/api/workspace/ask')[1]['views'], [])
            self.ask(ann, '订单有多少？')
            self.assertNotIn('definitions', model.requests[0])   # neither the meaning nor the view that would tell it

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

    def test_a_refusal_saved_before_the_type_was_restricted_shows_no_name_when_reopened(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)   # proposed, not confirmed
            status, refused = self.ask(bob, '订单有多少？')
            self.assertEqual((refused['status'], refused['refusal']['kind']), ('refused', 'unsettled'))
            self.assertIn('订单', [d['name'] for d in bob.get(f'/api/workspace/ask/{refused["id"]}')[1]['refusal']['definitions']])   # still there while Bob may see it
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': [2]})[0], 200)   # Ann only
            status, withheld = bob.get(f'/api/workspace/ask/{refused["id"]}')
            self.assertEqual((status, withheld['withheld']), (200, {'types': []}))
            self.assertNotIn('订单', json.dumps({k: v for k, v in withheld.items() if k != 'question'}, ensure_ascii=False))
            self.assertNotIn('refusal', withheld)

    def test_the_definitions_an_answer_records_are_the_ones_it_was_read_from_even_when_one_is_changed_while_the_model_works(self):
        class Slow(AskModel):
            def complete_json(self, **kw):
                done = super().complete_json(**kw)
                conn = sqlite3.connect(self.out / 'workspace.sqlite')
                conn.execute("UPDATE element_state SET version = version + 1 WHERE element_id IN ('objtype:order', 'enum:order:状态码')")
                conn.commit()
                conn.close()
                return done
        model = Slow(cancelled())
        with self.service(gateway=model) as (base, out):
            model.out = out
            team = self.team(base)
            self.confirmed_orders(team)
            before = {e: v for e, v in sqlite3.connect(out / 'workspace.sqlite').execute("SELECT element_id, version FROM element_state WHERE element_id IN ('objtype:order', 'enum:order:状态码')")}
            status, body = self.ask(team['ann'])
            self.assertEqual((status, body['status']), (200, 'answered'))
            self.assertEqual({d['id']: d['version'] for d in body['definitions']}, before)   # what it stood on, not what is on file after the call
            reopened = team['ann'].get(f'/api/workspace/ask/{body["id"]}')[1]
            self.assertEqual({c['id'] for c in reopened['changed']}, set(before))

    def test_a_person_made_a_viewer_since_asking_reads_the_saved_answer_without_its_rows(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            saved = self.ask(team['bob'])[1]
            self.assertIn('examples', json.dumps(saved))   # a builder reads the orders behind the count
            conn = sqlite3.connect(out / 'workspace.sqlite')
            conn.execute("UPDATE user SET role = 'viewer' WHERE username = 'bob'")
            conn.commit()
            conn.close()
            status, reopened = team['bob'].get(f'/api/workspace/ask/{saved["id"]}')
            self.assertEqual(status, 200, reopened)
            self.assertEqual(reopened['answer']['total'], CANCELLED)
            self.assertNotIn('examples', json.dumps(reopened))

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

    def test_a_short_master_table_does_not_go_to_the_model_whole_only_the_columns_whose_values_come_back(self):
        model = AskModel(cancelled(query={'start': 'product', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None}, used=[]))
        product = {'english_name': 'product', 'name': '产品', 'dataset': '产品', 'key': ['产品编号'], 'properties': [{'column': '产品名称'}, {'column': '品类'}, {'column': '单价'}]}
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.assertEqual(team['ann'].post('/api/workspace/types', product)[0], 200)
            self.confirm(team['bob'], 'product')
            self.assertEqual(self.ask(team['ann'], '产品有多少？')[0], 200)
            sent = json.dumps(model.requests[0], ensure_ascii=False)
            planted_products = planted.planted_bundle()['sources']['产品']['records']
            for r in planted_products:
                self.assertNotIn(r['产品名称'], sent)   # twelve products, twelve different names and prices: the table minus its key
                self.assertNotIn(r['单价'], sent)
            columns = {a['path']: a for a in model.requests[0]['ontology']['object_types'][0]['attributes']}
            self.assertNotIn('values', columns['产品名称'])
            self.assertEqual(columns['品类']['values'], sorted({r['品类'] for r in planted_products}))   # four categories over twelve rows come back

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

    def test_a_row_rule_limits_what_a_question_counts_and_a_relation_shows_the_answer_says_so_and_a_saved_answer_is_withheld_when_the_rule_changes(self):
        orders = {**ORDER, 'properties': [*ORDER['properties'], {'column': '客户编号'}]}
        kh001 = sum(1 for r in ORDERS if r['客户编号'] == 'KH001')
        model = AskModel(cancelled(query=ALL_ORDERS, used=[]))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types', orders)[0], 200)
            self.assertEqual(ann.post('/api/workspace/types', CUSTOMER)[0], 200)
            self.assertEqual(ann.post('/api/workspace/relations', RELATION)[0], 200)
            self.confirm(bob, 'order', '状态码')
            for name in ('order', 'customer'):
                self.confirm(bob, name)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
            shown = bob.get('/api/workspace/relations/order_customer')[1]
            self.assertEqual(bob.post('/api/workspace/queue/confirm', {'element': 'relation:order_customer', 'version': shown['version'], 'seen': shown['check']['signature']})[0], 200)
            self.assertEqual(kh001, 5)
            status, everything = self.ask(vera, '一共有多少订单？')
            self.assertEqual((status, everything['status'], everything['answer']['total'], 'limited_by_rule' in everything), (200, 'answered', 160, False))
            vera_id = next(u['id'] for u in admin.get('/api/users')[1]['users'] if u['username'] == 'vera')
            rule = {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH001', 'user_ids': [vera_id]}]}
            self.assertEqual(admin.post('/api/workspace/row-rules', rule)[0], 200)
            # the count is of her rows only, and the answer says rows were limited
            status, limited = self.ask(vera, '一共有多少订单？')
            self.assertEqual((status, limited['status'], limited['answer']['total']), (200, 'answered', kh001))
            self.assertEqual(limited['limited_by_rule'], [{'type': 'order', 'name': '订单', 'rule': '客户编号 = KH001'}])
            # the other people who may read the type: a builder no rule names sees none of its rows, an admin all of them
            self.assertEqual(self.ask(admin, '一共有多少订单？')[1]['answer']['total'], 160)
            status, none = self.ask(ann, '一共有多少订单？')
            self.assertEqual((none['status'], none['limited_by_rule'][0]['rule']), ('no_data', '没有一条规则让你看到行'))
            # the relation: connected rows and unmatched ones are counted over the orders she may read (all five name a customer the table has)
            numbers = vera.get('/api/workspace/relations/order_customer')[1]['check']['numbers']
            self.assertEqual((numbers['rows'], numbers['matched'], numbers['unmatched']), (kh001, kh001, 0))
            self.assertEqual(admin.get('/api/workspace/relations/order_customer')[1]['check']['numbers']['rows'], 160)
            model.item = {'reasoning': '客户在客户表里找不到的订单', 'query': None, 'missing': 'query_language', 'definitions_used': [],
                          'unmatched_relation': {'relation': 'order_customer', 'direction': 'many_without_one', 'other_conditions': False}}
            status, gap = self.ask(vera, '有多少订单的客户在客户表里找不到？')
            self.assertEqual((gap['status'], gap['answer']['total']), ('answered', 0))   # not the 3 KH099 orders: she may not read them
            self.assertEqual(self.ask(admin, '有多少订单的客户在客户表里找不到？')[1]['answer']['total'], 3)
            # what she asked under one rule is not shown under another
            self.assertEqual(vera.get(f'/api/workspace/ask/{limited["id"]}')[1]['answer']['total'], kh001)
            rule['rules'][0]['value'] = 'KH002'
            self.assertEqual(admin.post('/api/workspace/row-rules', rule)[0], 200)
            status, withheld = vera.get(f'/api/workspace/ask/{limited["id"]}')
            self.assertEqual((status, withheld['withheld']), (200, {'types': ['订单']}))
            self.assertIn('行规则后来变了', withheld['reason'])
            self.assertNotIn('answer', withheld)
