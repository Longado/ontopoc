"""Derived properties on the workspace, walked through the real service with two builders, a viewer and an admin on the seven planted tables. The four acceptance
tests of stage 4 are here: a P50 that is a mean is refused under that name; the monthly stock snapshot added up (7,856) instead of the latest month (1,115) is refused
and 按月份取最新 is offered; a confirmed 已取消订单数 per 客户 answers in Q&A with its definition cited; a person a row rule limits gets the statistic over their rows
only. Expected numbers are counted from the planted records here, not from the service."""
from collections import Counter, defaultdict
import json
import statistics

from tests import test_workspace_store as planted
from tests.test_object_relations import CUSTOMER, customers_mended
from tests.test_object_types import COMMIT, MEANINGS, STOCK, TABLES
from tests.test_two_person import SigningTestCase
from tests.test_workspace_questions import AskModel

SOURCES = planted.planted_bundle()['sources']
ORDERS, STOCKS, COMMITS, TICKETS = SOURCES['订单']['records'], SOURCES['库存快照']['records'], SOURCES['订单承诺']['records'], SOURCES['售后工单']['records']
ORDER = {'english_name': 'order', 'name': '订单', 'dataset': '订单', 'key': ['订单号'], 'description': '客户下的一张订单',
         'properties': [{'column': '订单号'}, {'column': '客户编号'}, {'column': '产品编号'}, {'column': '数量'}, {'column': '金额'}, {'column': '状态码', 'enum': True}, {'column': '交付天数'}],
         'enums': {'状态码': MEANINGS}}
PRODUCT = {'english_name': 'product', 'name': '产品', 'dataset': '产品', 'key': ['产品编号'], 'properties': [{'column': '产品名称'}, {'column': '品类'}, {'column': '单价'}]}
TICKET = {'english_name': 'ticket', 'name': '售后工单', 'dataset': '售后工单', 'key': ['工单号'], 'properties': [{'column': '订单号'}, {'column': '问题类型'}]}
STOCK = {**STOCK, 'properties': [{'column': '库存数量'}]}
RELATIONS = [
    {'english_name': 'order_customer', 'name': '订单属于客户', 'from': 'order', 'to': 'customer', 'cardinality': 'many_to_one', 'from_column': '客户编号', 'to_column': '客户编号'},
    {'english_name': 'order_product', 'name': '订单买的产品', 'from': 'order', 'to': 'product', 'cardinality': 'many_to_one', 'from_column': '产品编号', 'to_column': '产品编号'},
    {'english_name': 'stock_product', 'name': '库存属于产品', 'from': 'stock', 'to': 'product', 'cardinality': 'many_to_one', 'from_column': '产品编号', 'to_column': '产品编号'},
    {'english_name': 'commit_order', 'name': '承诺属于订单', 'from': 'commit', 'to': 'order', 'cardinality': 'many_to_one', 'from_column': '订单号', 'to_column': '订单号'},
    {'english_name': 'ticket_order', 'name': '工单属于订单', 'from': 'ticket', 'to': 'order', 'cardinality': 'many_to_one', 'from_column': '订单号', 'to_column': '订单号'},
]
P50 = {'type': 'product', 'english_name': 'delivery_p50', 'name': '交付天数P50', 'kind': 'statistic', 'path': ['order_product'], 'measure': {'column': '交付天数'}, 'fn': 'median'}
STOCK_LATEST = {'type': 'product', 'english_name': 'stock_now', 'name': '当前库存', 'kind': 'statistic', 'path': ['stock_product'], 'measure': {'column': '库存数量'}, 'fn': 'latest',
                'latest': {'order': '快照月份'}}
CANCELLED = {'type': 'customer', 'english_name': 'cancelled_orders', 'name': '已取消订单数', 'kind': 'statistic', 'path': ['order_customer'], 'measure': {'column': None}, 'fn': 'count',
             'conditions': [{'column': '状态码', 'op': 'is', 'label': '已取消'}]}
GROSS = {'type': 'order', 'english_name': 'gross', 'name': '含税金额', 'kind': 'function', 'expression': '金额 * 1.13'}


def per_group(records, group, value, pick=None):
    out = defaultdict(list)
    for r in records:
        if pick is None or pick(r):
            out[r[group]].append(float(r[value]))
    return out


class DerivedTestCase(SigningTestCase):
    def team(self, base):
        team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
        return team

    def confirm_type(self, bob, name, enums=()):
        for column in (*enums, None):
            shown = bob.get(f'/api/workspace/types/{name}')[1]
            shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
            status, body = bob.post('/api/workspace/types/confirm', {'id': name, 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})
            self.assertEqual(status, 200, body)

    def foundation(self, team, types=(ORDER, CUSTOMER, PRODUCT, STOCK, COMMIT, TICKET), relations=RELATIONS):
        """The planted types and relations, put forward by Ann and confirmed by Bob."""
        ann, bob = team['ann'], team['bob']
        for t in types:
            self.assertEqual(ann.post('/api/workspace/types', t)[0], 200, t['english_name'])
        for t in types:
            self.confirm_type(bob, t['english_name'], ('状态码',) if t['english_name'] == 'order' else ())
        for r in relations:
            if r['from'] in {t['english_name'] for t in types} and r['to'] in {t['english_name'] for t in types}:
                self.assertEqual(ann.post('/api/workspace/relations', r)[0], 200, r['english_name'])
                detail = bob.get(f'/api/workspace/relations/{r["english_name"]}')[1]
                status, body = bob.post('/api/workspace/queue/confirm', {'element': f'relation:{r["english_name"]}', 'version': detail['version'], 'seen': detail['check']['signature']})
                self.assertEqual(status, 200, body)

    def derived(self, client, type_name):
        status, body = client.get(f'/api/workspace/types/{type_name}/derived')
        self.assertEqual(status, 200, body)
        return body

    def line(self, client, type_name, name):
        return next(d for d in self.derived(client, type_name)['derived'] if d['id'] == name)

    def confirm(self, client, payload):
        line = self.line(client, payload['type'], payload['english_name'])
        return client.post('/api/workspace/types/derived/confirm', {'type': payload['type'], 'english_name': payload['english_name'], 'version': line['version'], 'seen': line['seen']})

    def objects(self, client, type_name):
        """The first page of the type's objects as the person reads them."""
        status, body = client.get(f'/api/workspace/types/{type_name}/objects')
        self.assertEqual(status, 200, body)
        return body

    def values(self, client, type_name, key, name):
        """{the key column's value: the value of the column called `name`} over the first page of the type's objects."""
        shown = self.objects(client, type_name)
        names = [c['name'] for c in shown['columns']]
        return {row[names.index(key)]: row[names.index(name)] for row in shown['rows']}


class AcceptanceTests(DerivedTestCase):
    def test_a_p50_worked_out_as_a_mean_is_refused_under_that_name_and_the_median_is_offered(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann = team['ann']
            status, body = ann.post('/api/workspace/types/derived', {**P50, 'fn': 'avg'})
            self.assertEqual(status, 400, body)
            self.assertIn('中位数', body['error'])
            self.assertIn('平均', body['error'])
            self.assertEqual(body['offer'], [{'fn': 'median'}])
            self.assertEqual(ann.get('/api/workspace/types/product/derived')[1]['derived'], [])   # nothing was saved
            status, body = ann.post('/api/workspace/types/derived', P50)
            self.assertEqual(status, 200, body)
            self.assertEqual(self.confirm(team['bob'], P50)[0], 200)
            numbers = body['trial']['numbers']
            self.assertEqual((numbers['objects'], numbers['with_value'], numbers['rows_used']), (12, 12, 160))
            medians = {p: statistics.median(v) for p, v in per_group(ORDERS, '产品编号', '交付天数').items()}
            means = {p: statistics.fmean(v) for p, v in per_group(ORDERS, '产品编号', '交付天数').items()}
            planted_p50 = {r['产品编号']: float(r['交付天数P50']) for r in SOURCES['交付统计']['records']}
            self.assertTrue(any(abs(medians[p] - means[p]) > 0.01 for p in medians))   # the planted table's "P50" is the mean: the two differ
            self.assertTrue(all(abs(planted_p50[p] - round(means[p], 1)) < 0.06 for p in medians))
            shown = self.objects(ann, 'product')
            self.assertTrue(next(c for c in shown['columns'] if c['name'] == '交付天数P50')['derived'])   # tagged 派生
            got = {k: float(v) for k, v in self.values(ann, 'product', '产品编号', '交付天数P50').items()}
            for product, median in medians.items():
                self.assertAlmostEqual(got[product], median, places=3, msg=product)
            # other names that say a statistic are held to it too
            for name, fn, ok in (('平均交付天数', 'avg', True), ('平均交付天数', 'median', False), ('交付天数合计', 'max', False), ('交付天数P90', 'p75', False), ('交付天数P75', 'p75', True)):
                status, body = ann.post('/api/workspace/types/derived/trial', {**P50, 'english_name': 'x', 'name': name, 'fn': fn})
                self.assertEqual(status == 200, ok, (name, fn, body))

    def test_the_monthly_stock_snapshot_added_up_is_refused_and_taking_the_latest_month_is_offered(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann = team['ann']
            self.assertEqual(sum(int(r['库存数量']) for r in STOCKS), 7856)
            for fn in ('sum', 'avg', 'count', 'median'):
                status, body = ann.post('/api/workspace/types/derived', {**STOCK_LATEST, 'fn': fn, 'latest': None, 'name': '库存', 'measure': {'column': '库存数量'}})
                self.assertEqual(status, 400, (fn, body))
                self.assertIn('快照月份', body['error'])
                self.assertEqual(body['offer'][0], {'fn': 'latest', 'order': '快照月份'}, fn)
            status, body = ann.post('/api/workspace/types/derived', {**STOCK_LATEST, 'latest': {'order': '产品编号'}})   # latest by anything but the month is not "按月份取最新"
            self.assertEqual(status, 400, body)
            status, body = ann.post('/api/workspace/types/derived', STOCK_LATEST)
            self.assertEqual(status, 200, body)
            last = max(r['快照月份'] for r in STOCKS)
            latest = {r['产品编号']: int(r['库存数量']) for r in STOCKS if r['快照月份'] == last}
            self.assertEqual(sum(latest.values()), 1115)
            self.assertNotIn('当前库存', [c['name'] for c in self.objects(ann, 'product')['columns']])   # not confirmed yet: the objects page shows confirmed properties only
            self.assertEqual(self.confirm(team['bob'], STOCK_LATEST)[0], 200)
            got = {k: int(v) for k, v in self.values(ann, 'product', '产品编号', '当前库存').items()}
            self.assertEqual(got, latest)
            self.assertEqual(sum(got.values()), 1115)
            # the minimum, the maximum and a distinct count are true of a snapshot, and are allowed
            for fn in ('min', 'max'):
                self.assertEqual(ann.post('/api/workspace/types/derived/trial', {**STOCK_LATEST, 'english_name': 'y', 'name': '库存_' + fn, 'fn': fn, 'latest': None})[0], 200, fn)

    def test_a_confirmed_cancelled_order_count_per_customer_answers_in_qa_with_its_definition_cited(self):
        expected = Counter(r['客户编号'] for r in ORDERS if r['状态码'] == '2')
        query = {'start': 'customer', 'where': [{'field': '客户编号', 'equals': 'KH026'}], 'via': [], 'group_by': None, 'share': None,
                 'measure': {'field': '已取消订单数', 'op': 'sum'}}
        model = AskModel({'reasoning': '客户的已取消订单数是一个派生属性', 'query': query, 'definitions_used': []})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob = team['ann'], team['bob']
            status, body = ann.post('/api/workspace/types/derived', CANCELLED)
            self.assertEqual(status, 200, body)
            asked = '客户 KH026 的已取消订单数是多少？'
            status, refused = ann.post('/api/workspace/ask', {'question': asked})   # not confirmed: refused before the model is asked
            self.assertEqual(status, 200, refused)
            self.assertEqual(refused['status'], 'refused')
            self.assertEqual(model.requests, [])
            self.assertIn('已取消订单数', refused['reason'])
            self.assertEqual([(d['kind'], d['name'], d['state']) for d in refused['refusal']['definitions']], [('derived', '客户.已取消订单数', 'checked')])
            self.assertEqual(self.confirm(bob, CANCELLED)[0], 200)
            status, answer = ann.post('/api/workspace/ask', {'question': asked})
            self.assertEqual(status, 200, answer)
            self.assertEqual(answer['status'], 'answered', answer)
            self.assertEqual(answer['answer']['measure']['value'], expected['KH026'])
            self.assertEqual(expected['KH026'], 3)
            cited = [d for d in answer['definitions'] if d['kind'] == 'derived']
            self.assertEqual([(d['name'], d['confirmed_by'], d['state']) for d in cited], [('客户.已取消订单数', 'Bob', 'confirmed')])
            self.assertIn('已取消', cited[0]['says'])
            attribute = next(a for t in model.requests[0]['ontology']['object_types'] if t['key'] == 'customer' for a in t['attributes'] if a['path'] == '已取消订单数')
            self.assertEqual((attribute['type'], '已取消' in attribute['derived']), ('integer', True))   # the model reads the name, the type and what it says, never a value
            self.assertNotIn('values', attribute)
            self.assertEqual(self.line(ann, 'customer', 'cancelled_orders')['used_by']['answers'], 1)

    def test_a_person_a_row_rule_limits_gets_the_statistic_over_their_rows_only(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob, admin, vera = team['ann'], team['bob'], team['admin'], team['vera']
            self.assertEqual(ann.post('/api/workspace/types/derived', CANCELLED)[0], 200)
            self.assertEqual(self.confirm(bob, CANCELLED)[0], 200)
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            # a rule on the orders: vera reads the orders of KH026 and no others
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH026', 'user_ids': [ids['vera']]}]})[0], 200)
            expected = Counter(r['客户编号'] for r in ORDERS if r['状态码'] == '2')
            full, mine = (self.values(who, 'customer', '客户编号', '已取消订单数') for who in (admin, vera))
            self.assertEqual({k: int(v) for k, v in full.items()}, {k: expected.get(k, 0) for k in full})
            self.assertEqual(mine['KH026'], str(expected['KH026']))
            self.assertEqual(mine['KH015'], '0')   # KH015 has two cancelled orders; vera reads none of them
            self.assertEqual(expected['KH015'], 2)
            line = self.line(vera, 'customer', 'cancelled_orders')
            self.assertEqual((line['trial']['numbers'], line['can_confirm']), (None, False))   # no whole-data count; nothing for her to confirm
            self.assertIn('行规则', line['trial']['limited_note'])
            self.assertEqual(vera.post('/api/workspace/types/derived/confirm', {'type': 'customer', 'english_name': 'cancelled_orders', 'version': line['version'], 'seen': {}})[0], 403)   # a viewer confirms nothing
            # a rule on the customers (the owner type) limits whose values she reads
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': []})[0], 200)
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'customer', 'rules': [{'column': '客户名称', 'value': '东莞家电客户01', 'user_ids': [ids['vera']]}]})[0], 200)
            self.assertEqual(self.values(vera, 'customer', '客户编号', '已取消订单数'), {'KH001': str(expected['KH001'])})
