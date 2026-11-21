"""Derived properties on the workspace, walked through the real service with two builders, a viewer and an admin on the seven planted tables. The four acceptance
tests of stage 4 are here: a P50 that is a mean is refused under that name; the monthly stock snapshot added up (7,856) instead of the latest month (1,115) is refused
and 按月份取最新 is offered; a confirmed 已取消订单数 per 客户 answers in Q&A with its definition cited; a person a row rule limits gets the statistic over their rows
only. Expected numbers are counted from the planted records here, not from the service."""
from collections import Counter, defaultdict
import json
import statistics
import unittest
from unittest import mock

from tests import test_workspace_store as planted
from tests.test_object_relations import CUSTOMER, CUSTOMERS, customers_mended, table_csv
from tests.test_object_types import COMMIT, MEANINGS, STOCK, TABLES, orders_upload
from tests.test_two_person import SigningTestCase
from ontology_poc_generator import workspace_questions
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
INCLUDES_CANCELLED = [{'id': '订单.状态码=已取消', 'direction': 'include', 'basis': '已取消订单数'}]
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

    def objects(self, client, type_name, page=1):
        """One page of the type's objects as the person reads them."""
        status, body = client.get(f'/api/workspace/types/{type_name}/objects?page={page}')
        self.assertEqual(status, 200, body)
        return body

    def values(self, client, type_name, key, name):
        """{the key column's value: the value of the column called `name`} over every page of the type's objects."""
        out, page = {}, 1
        while True:
            shown = self.objects(client, type_name, page)
            names = [c['name'] for c in shown['columns']]
            out.update({row[names.index(key)]: row[names.index(name)] for row in shown['rows']})
            if page >= shown['pages']:
                return out
            page += 1


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
            self.assertNotIn('当前库存', [c['name'] for c in self.objects(team['vera'], 'product')['columns']])   # not confirmed yet: a viewer does not see it
            self.assertEqual([c['confirmed'] for c in self.objects(ann, 'product')['columns'] if c.get('derived')], [False])   # a builder sees it marked as not confirmed
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
        model = AskModel({'reasoning': '客户的已取消订单数是一个派生属性', 'query': query, 'definitions_used': INCLUDES_CANCELLED})   # the model says the question includes 已取消 (no name exception)
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
            self.assertEqual((attribute['type'], '已取消' in attribute['computed_as'], 'derived' in attribute), ('integer', True, False))   # the model reads the name, the type and what it says, never a value
            self.assertNotIn('values', attribute)
            self.assertEqual(self.line(ann, 'customer', 'cancelled_orders')['used_by']['answers'], 1)

    def test_one_customer_s_count_answers_but_a_total_over_all_customers_is_refused_saying_why_when_some_orders_reach_no_customer(self):
        """The planted orders do not all reach exactly one customer. One customer's own count (a filter by its key) is that customer's rows and answers; a total over
        every customer is not the total of the cancelled orders, and the refusal says so (not that the query reads no property that counts only them)."""
        total = {'start': 'customer', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': '已取消订单数', 'op': 'sum'}}
        model = AskModel({'reasoning': '已取消订单数加起来', 'query': total, 'definitions_used': INCLUDES_CANCELLED})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/derived', CANCELLED)[0], 200)
            self.assertEqual(self.confirm(bob, CANCELLED)[0], 200)
            status, answer = ann.post('/api/workspace/ask', {'question': '已取消订单一共有多少？'})
            self.assertEqual((status, answer['status']), (200, 'definition_unmet'), answer)
            self.assertIn('不是每一行都正好连上一个对象', answer['reason'])
            self.assertNotIn('也没有读只算它的派生属性', answer['reason'])

    def test_one_object_s_count_through_a_hop_toward_the_one_side_is_refused_because_its_rows_are_counted_more_than_once(self):
        """Stock rows reach their product, and the product's orders: every cancelled order of CP01 is counted once for each stock row of CP01. Picking CP01 does not
        make those counts add up to CP01's cancelled orders, so the per-object answer is refused, not 6 where there is 1."""
        per_stock = {'type': 'stock', 'english_name': 'product_cancelled', 'name': '产品已取消订单数', 'kind': 'statistic', 'path': ['stock_product', 'order_product'],
                     'measure': {'column': None}, 'fn': 'count', 'conditions': [{'column': '状态码', 'op': 'is', 'label': '已取消'}]}
        query = {'start': 'stock', 'where': [{'field': '产品编号', 'equals': 'CP01'}], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': '产品已取消订单数', 'op': 'sum'}}
        model = AskModel({'reasoning': '产品的已取消订单数', 'query': query, 'definitions_used': INCLUDES_CANCELLED})
        self.assertGreater(sum(r['产品编号'] == 'CP01' for r in STOCKS), 1)   # more than one stock row reaches CP01
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/derived', per_stock)[0], 200)
            self.assertEqual(self.confirm(bob, per_stock)[0], 200)
            status, answer = ann.post('/api/workspace/ask', {'question': '产品 CP01 的已取消订单有多少？'})
            self.assertEqual((status, answer['status']), (200, 'definition_unmet'), answer)
            self.assertIn('不是每一行都正好连上一个对象', answer['reason'])

    def ask_by_country(self, extra=(), moved=()):
        """已取消订单数 summed over the customers whose 国家 is CN, on a customer table where every customer is CN except those in `moved` (US), plus `extra`
        customers (US, with no orders). The orders that reach no customer (KH099) are in no customer's count."""
        rows = [{**r, '国家': 'US' if r['客户编号'] in moved else 'CN'} for r in {r['客户编号']: r for r in reversed(CUSTOMERS)}.values()]
        customers = table_csv('客户.csv', [*rows, *({**rows[0], '客户编号': k, '客户名称': k, '国家': 'US'} for k in extra)], target='客户', mode='overwrite')
        customer = {**CUSTOMER, 'properties': [*CUSTOMER['properties'], {'column': '国家'}]}
        total = {'start': 'customer', 'where': [{'field': '国家', 'equals': 'CN'}], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': '已取消订单数', 'op': 'sum'}}
        model = AskModel({'reasoning': '中国客户的已取消订单数加起来', 'query': total, 'definitions_used': INCLUDES_CANCELLED})
        self.assertTrue(any(r['客户编号'] not in {c['客户编号'] for c in CUSTOMERS} for r in ORDERS))   # some orders reach no customer
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [customers]})[0], 200)
            self.foundation(team, types=(ORDER, customer, PRODUCT, STOCK, COMMIT, TICKET))
            self.assertEqual(ann.post('/api/workspace/types/derived', CANCELLED)[0], 200)
            self.assertEqual(self.confirm(bob, CANCELLED)[0], 200)
            status, answer = ann.post('/api/workspace/ask', {'question': '已取消订单一共有多少？'})
            self.assertEqual(status, 200, answer)
            return answer

    def test_a_total_written_with_a_filter_every_customer_matches_is_still_refused_when_some_orders_reach_no_customer(self):
        """国家 = CN keeps every customer, so the query is a total over all of them, not particular customers: the orders that reach no customer (KH099) would be
        left out without a word. It is refused as the total without the filter is."""
        answer = self.ask_by_country()
        self.assertEqual(answer['status'], 'definition_unmet', answer)
        self.assertIn('不是每一行都正好连上一个对象', answer['reason'])

    def test_a_filter_that_leaves_out_only_customers_with_no_orders_is_still_a_total(self):
        """KH900 is US and has no orders: leaving it out leaves no row out, so the filter keeps every row a customer is counted from and the query is still a total."""
        answer = self.ask_by_country(extra=('KH900',))
        self.assertEqual(answer['status'], 'definition_unmet', answer)
        self.assertIn('不是每一行都正好连上一个对象', answer['reason'])

    def test_a_filter_that_leaves_out_a_customer_with_cancelled_orders_answers_for_the_customers_it_keeps(self):
        mine = Counter(r['客户编号'] for r in ORDERS if r['状态码'] == '2')
        known = {r['客户编号'] for r in CUSTOMERS}
        moved = next(k for k in sorted(mine) if k in known)
        answer = self.ask_by_country(moved=(moved,))
        self.assertEqual(answer['status'], 'answered', answer)
        self.assertEqual(answer['answer']['measure']['value'], sum(n for k, n in mine.items() if k in known and k != moved))

    def test_a_filter_the_query_language_cannot_read_is_said_so_not_a_failure(self):
        """The model's reply is not trusted: a value that is a dict or a nested list, or a range that is not a number, is a query the language cannot read."""
        model = AskModel({})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann = team['ann']
            for where in ([{'field': '状态码', 'equals': {'a': 1}}], [{'field': '状态码', 'equals': ['2', ['3']]}],
                          [{'field': '状态码', 'equals': '2'}, {'field': '状态码', 'not_equals': {'a': 1}}], [{'field': '交付天数', 'equals': '1', 'at_least': 'abc'}]):
                model.item = {'reasoning': '订单', 'query': {'start': 'order', 'where': where, 'via': [], 'group_by': None, 'share': None, 'measure': None}, 'definitions_used': []}
                status, answer = ann.post('/api/workspace/ask', {'question': '订单有多少？'})
                self.assertEqual((status, answer.get('status')), (200, 'query_limit'), (where, answer))

    def test_a_confirmed_property_the_model_writes_as_a_derived_measure_is_still_cited(self):
        query = {'start': 'customer', 'where': [{'field': '客户编号', 'equals': 'KH026'}], 'via': [], 'group_by': None, 'share': None,
                 'measure': {'derived': '已取消订单数', 'op': 'sum'}}   # how DeepSeek V4.1 Flash wrote it in a real run
        model = AskModel({'reasoning': '客户的已取消订单数是一个派生属性', 'query': query, 'definitions_used': INCLUDES_CANCELLED})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/derived', CANCELLED)[0], 200)
            self.assertEqual(self.confirm(bob, CANCELLED)[0], 200)
            status, answer = ann.post('/api/workspace/ask', {'question': '客户 KH026 的已取消订单数是多少？'})
            self.assertEqual((status, answer['status'], answer['answer']['measure']['value']), (200, 'answered', 3), answer)
            self.assertEqual([(d['name'], d['confirmed_by']) for d in answer['definitions'] if d['kind'] == 'derived'], [('客户.已取消订单数', 'Bob')])

    def test_a_property_that_counts_rows_by_a_column_kept_from_the_model_is_left_out_of_what_the_model_is_told(self):
        query = {'start': 'customer', 'where': [{'field': '客户编号', 'equals': 'KH026'}], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': '已取消订单数', 'op': 'sum'}}
        model = AskModel({'reasoning': '客户的已取消订单数是一个派生属性', 'query': query, 'definitions_used': []})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/derived', CANCELLED)[0], 200)
            self.assertEqual(self.confirm(bob, CANCELLED)[0], 200)
            ann.post('/api/workspace/ask', {'question': '客户 KH026 的已取消订单数是多少？'})
            paths = lambda: [a['path'] for t in model.requests[-1]['ontology']['object_types'] if t['key'] == 'customer' for a in t['attributes']]
            self.assertIn('已取消订单数', paths())   # as it stands, the model reads the name and what it says
            self.assertEqual(ann.post('/api/workspace/types/privacy', {'id': 'order', 'column': '状态码', 'hide_values': True})[0], 200)   # "已取消" is a meaning of that column
            ann.post('/api/workspace/ask', {'question': '客户 KH026 的已取消订单数是多少？'})
            self.assertNotIn('已取消订单数', paths())

    def test_working_out_the_derived_properties_of_a_request_stops_after_a_few_seconds_and_says_so_in_words(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/derived', CANCELLED)[0], 200)
            self.assertEqual(self.confirm(bob, CANCELLED)[0], 200)
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)   # one nobody confirmed yet waits in the queue, with its trial
            self.assertEqual(ann.get('/api/workspace/types/customer/derived')[0], 200)
            with mock.patch('ontology_poc_generator.derived_properties.DERIVED_SECONDS', 0.0):   # no time at all: the first statement is stopped
                for path in ('/api/workspace/types/customer/derived', '/api/workspace/types/customer/objects', '/api/workspace/queue'):
                    status, body = ann.get(path)
                    self.assertEqual(status, 409, (path, body))
                    self.assertIn('派生属性', body['error'])
                    self.assertIn('已经停下', body['error'])
            self.assertEqual(ann.get('/api/workspace/types/customer/derived')[0], 200)   # and nothing was left stopped

    def test_a_statistic_through_a_relation_says_how_many_rows_it_left_out_because_they_find_no_owner(self):
        total = {**CANCELLED, 'english_name': 'order_total', 'name': '订单金额', 'measure': {'column': '金额'}, 'fn': 'sum', 'conditions': []}
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann = team['ann']
            self.assertEqual(ann.post('/api/workspace/types/derived', total)[0], 200)
            lines = [l['text'] for l in self.line(ann, 'customer', 'order_total')['trial']['lines']]
            lost = [r for r in ORDERS if r['客户编号'] not in {c['客户编号'] for c in planted.planted_bundle()['sources']['客户']['records']}]
            self.assertIn(f'有 {len(lost)} 行订单因为找不到客户没算进来（KH099）', lines)
            self.assertEqual(len(lost), 3)

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
            self.assertIsNone(mine['KH015'])   # KH015 has two cancelled orders and vera reads none of them: no value, "not in the rows you can see", and never a 0
            self.assertEqual(expected['KH015'], 2)
            table = vera.post('/api/workspace/explore/table', {'query': {'type': 'customer'}})[1]
            column = [c['column'] for c in table['columns']].index('derived:cancelled_orders')
            key = [c['name'] for c in table['columns']].index('客户编号')
            flagged = {table['rows'][r][key] for r, cells in enumerate(table['outside']) if column in cells}
            self.assertIn('KH015', flagged)   # the table says which cells are not in her rows, so the page can write why they are empty
            self.assertNotIn('KH026', flagged)
            mine_rows = sum(r['客户编号'] == 'KH026' for r in ORDERS)
            self.assertEqual(vera.get('/api/workspace/types/customer')[1]['limited_reads'], [{'name': '已取消订单数', 'types': [{'name': '订单', 'rows': mine_rows}]}])   # the customer page can say whose rows its numbers are
            self.assertEqual(admin.get('/api/workspace/types/customer')[1]['limited_reads'], [])
            line = self.line(vera, 'customer', 'cancelled_orders')
            self.assertEqual((line['trial']['numbers'], line['can_confirm']), (None, False))   # no whole-data count; nothing for her to confirm
            self.assertIn('行规则', line['trial']['limited_note'])
            self.assertEqual(vera.post('/api/workspace/types/derived/confirm', {'type': 'customer', 'english_name': 'cancelled_orders', 'version': line['version'], 'seen': {}})[0], 403)   # a viewer confirms nothing
            # a rule on the customers (the owner type) limits whose values she reads
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': []})[0], 200)
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'customer', 'rules': [{'column': '客户名称', 'value': '东莞家电客户01', 'user_ids': [ids['vera']]}]})[0], 200)
            self.assertEqual(self.values(vera, 'customer', '客户编号', '已取消订单数'), {'KH001': str(expected['KH001'])})

    def test_the_words_why_a_property_needs_another_look_do_not_quote_whole_data_counts_to_a_person_a_row_rule_limits(self):
        per_day = {**GROSS, 'english_name': 'per_day', 'name': '每天金额', 'expression': '金额 / 交付天数'}
        with self.service() as (base, out):
            team = self.people(base, 'ann', 'bob', 'lim')
            self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
            self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
            self.foundation(team)
            ann, bob, admin, lim = team['ann'], team['bob'], team['admin'], team['lim']
            self.assertEqual(ann.post('/api/workspace/types/derived', per_day)[0], 200)
            self.assertEqual(self.confirm(bob, per_day)[0], 200)
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH026', 'user_ids': [ids['lim']]}]})[0], 200)
            self.assertEqual(admin.post('/api/workspace/datasets/upload', {'files': [orders_upload(lambda r, i: {**r, '交付天数': '0' if i in (3, 4, 5) else r['交付天数']})]})[0], 200)   # three orders now have no per-day value
            whole = self.line(admin, 'order', 'per_day')
            self.assertIn('确认时 0 个，现在 3 个', whole['reason'])   # whoever reads all the data reads the counts
            mine = self.line(lim, 'order', 'per_day')
            self.assertEqual((mine['state'], mine['reason'], mine['stale_word']), ('needs_look', None, '数据变了'))
            self.assertIn('受行规则限制', mine['reason_hidden'])
            queued = next(i for i in lim.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'derived')
            self.assertNotIn('确认时', json.dumps(queued, ensure_ascii=False))
            self.assertIn('受行规则限制', json.dumps(queued, ensure_ascii=False))
            logged = lim.get('/api/workspace/types/order/derived/per_day/log')[1]['log']
            self.assertNotIn('确认时', json.dumps(logged, ensure_ascii=False))
            self.assertTrue(any(e['to'] == 'needs_look' and '受行规则限制' in e['reason'] for e in logged))
            self.assertIn('确认时 0 个，现在 3 个', json.dumps(admin.get('/api/workspace/types/order/derived/per_day/log')[1]['log'], ensure_ascii=False))


class ConfirmAndVersionTests(DerivedTestCase):
    def test_a_derived_property_is_confirmed_by_the_other_builder_and_an_edit_makes_a_new_version_the_old_confirmation_stays_as_history(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)
            line = self.line(ann, 'order', 'gross')
            self.assertEqual((line['state'], line['proposed_by'], line['can_confirm'], line['kind_name']), ('checked', 'Ann', False, '函数'))
            self.assertEqual(line['trial']['sample']['label'], '样本')   # the formula tried on one row is labelled as a sample
            status, body = ann.post('/api/workspace/types/derived/confirm', {'type': 'order', 'english_name': 'gross', 'version': line['version'], 'seen': line['seen']})
            self.assertEqual((status, body['error']), (403, '这一条是你自己提的，要另一位来确认'))
            line = self.line(bob, 'order', 'gross')
            self.assertEqual((line['can_confirm'], line['confirmers']), (True, ['Bob', '管理员']))
            status, stale = bob.post('/api/workspace/types/derived/confirm', {'type': 'order', 'english_name': 'gross', 'version': line['version'] - 1, 'seen': line['seen']})
            self.assertEqual(status, 409, stale)
            status, wrong = bob.post('/api/workspace/types/derived/confirm', {'type': 'order', 'english_name': 'gross', 'version': line['version'], 'seen': {**line['seen'], 'objects': 1}})
            self.assertEqual(status, 409, wrong)
            self.assertEqual(self.confirm(bob, GROSS)[0], 200)
            line = self.line(bob, 'order', 'gross')
            self.assertEqual((line['state'], line['confirmed_by']), ('confirmed', 'Bob'))
            first_version = line['version']
            # the display name and the description are not what was confirmed
            status, body = bob.post('/api/workspace/types/derived/update', {**GROSS, 'name': '含税金额（元）', 'description': '按 13% 税率', 'version': first_version})
            self.assertEqual((status, body['state'], body['reset']), (200, 'confirmed', []), body)
            # a change to what it computes is a new version that is put forward again, as the editor's own
            line = self.line(bob, 'order', 'gross')
            status, body = bob.post('/api/workspace/types/derived/update', {**GROSS, 'name': '含税金额（元）', 'expression': '金额 * 1.13 + 数量', 'version': line['version']})
            self.assertEqual((status, body['state'], body['reset']), (200, 'checked', ['算式', '输入的列']), body)
            line = self.line(bob, 'order', 'gross')
            self.assertEqual((line['state'], line['proposed_by'], line['can_confirm']), ('checked', 'Bob', False))   # the one who edited it does not confirm it
            self.assertGreater(line['version'], first_version)
            shown = {c['name']: c for c in self.objects(ann, 'order')['columns']}   # unconfirmed again: a builder still sees it, but marked as not confirmed
            self.assertEqual(shown['含税金额（元）']['confirmed'], False)
            self.assertNotIn('含税金额（元）', [c['name'] for c in self.objects(team['vera'], 'order')['columns']])
            self.assertEqual(self.confirm(ann, {**GROSS, 'english_name': 'gross'})[0], 200)
            status, history = ann.get('/api/workspace/types/order/derived/gross/log')
            self.assertEqual(status, 200, history)
            self.assertEqual([h['confirmed_by'] for h in history['confirmations']], ['Ann', 'Bob'])   # newest first: the first confirmation stays
            self.assertIn('金额 * 1.13', history['confirmations'][1]['says'])
            self.assertNotIn('数量', history['confirmations'][1]['says'])
            self.assertTrue(history['confirmations'][1]['trial']['lines'])   # the trial they read is kept with it

    def test_an_added_input_and_a_changed_output_type_reset_the_confirmation_and_a_renamed_display_name_does_not(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)
            self.assertEqual(self.confirm(bob, GROSS)[0], 200)
            for expression, reset in (("金额 * 1.13", []), ("金额 * 1.13 + 数量", ['算式', '输入的列']), ("concat(订单号, '-', 客户编号)", ['算式', '输入的列', '输出类型'])):
                line = self.line(ann, 'order', 'gross')
                status, body = ann.post('/api/workspace/types/derived/update', {**GROSS, 'expression': expression, 'version': line['version']})
                self.assertEqual((status, body['reset']), (200, reset), (expression, body))
                if reset:
                    self.assertEqual(self.confirm(bob, {**GROSS, 'expression': expression})[0], 200)

    def test_a_property_stands_on_confirmed_relations_only_and_cannot_be_confirmed_before_what_it_reads_is(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.foundation(team, types=(ORDER, CUSTOMER), relations=[])
            status, body = ann.post('/api/workspace/relations', RELATIONS[0])
            self.assertEqual(status, 200, body)
            status, body = ann.post('/api/workspace/types/derived', CANCELLED)   # the relation is only put forward
            self.assertEqual(status, 409, body)
            self.assertIn('还没有确认', body['error'])

    def test_a_viewer_reads_confirmed_properties_only_and_the_queue_lists_the_unconfirmed_one_for_the_other_builder(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            self.assertEqual(ann.post('/api/workspace/types/derived', CANCELLED)[0], 200)
            self.assertEqual(vera.get('/api/workspace/types/customer/derived')[1]['derived'], [])
            self.assertIsNone(vera.get('/api/workspace/types/customer/derived')[1]['form'])
            queue = bob.get('/api/workspace/queue')[1]
            item = next(i for i in queue['items'] if i['element'] == 'derived:customer:cancelled_orders')
            self.assertEqual((item['kind'], item['can_confirm'], item['title']), ('derived', True, '已取消订单数（客户的派生属性）'))
            self.assertTrue(any('订单' in l['text'] and '已取消' in l['text'] for l in item['lines']))
            self.assertFalse(any(i['element'] == 'derived:customer:cancelled_orders' and i['can_confirm'] for i in ann.get('/api/workspace/queue')[1]['items']))
            status, body = bob.post('/api/workspace/queue/confirm', {'element': item['element'], 'version': item['version'], 'seen': item['seen']})
            self.assertEqual(status, 200, body)
            self.assertEqual([d['name'] for d in vera.get('/api/workspace/types/customer/derived')[1]['derived']], ['已取消订单数'])
            # sent back with a reason: the editor's to fix
            self.assertEqual(ann.post('/api/workspace/types/derived', {**CANCELLED, 'english_name': 'other', 'name': '已取消单数'})[0], 200)
            item = next(i for i in bob.get('/api/workspace/queue')[1]['items'] if i['element'] == 'derived:customer:other')
            status, body = bob.post('/api/workspace/queue/send-back', {'element': item['element'], 'version': item['version'], 'reason': '名字和已取消订单数重复'})
            self.assertEqual((status, body), (200, {'state': 'rejected'}))
            self.assertEqual(self.line(ann, 'customer', 'other')['state'], 'rejected')

    def test_the_objects_page_puts_a_property_nobody_has_confirmed_after_the_confirmed_ones_and_only_for_builders(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            self.assertEqual(ann.post('/api/workspace/types/derived', {**CANCELLED, 'english_name': 'a_waiting', 'name': 'A 待确认'})[0], 200)   # sorts before the confirmed one by id
            self.assertEqual(ann.post('/api/workspace/types/derived', CANCELLED)[0], 200)
            self.assertEqual(self.confirm(bob, CANCELLED)[0], 200)
            derived = lambda client: [(c['name'], c['confirmed']) for c in self.objects(client, 'customer')['columns'] if c.get('derived')]
            self.assertEqual(derived(bob), [('已取消订单数', True), ('A 待确认', False)])
            self.assertEqual(derived(vera), [('已取消订单数', True)])

    def test_the_drawer_and_the_type_page_list_the_derived_properties_tagged_and_confirmed_ones_first(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/derived', {**CANCELLED, 'english_name': 'a_proposed', 'name': '待确认订单数'})[0], 200)
            self.assertEqual(ann.post('/api/workspace/types/derived', CANCELLED)[0], 200)
            self.assertEqual(self.confirm(bob, CANCELLED)[0], 200)
            node = next(n for n in ann.get('/api/workspace/graph/relations')[1]['nodes'] if n['key'] == 'customer')
            self.assertEqual([(d['name'], d['state'], d['tag']) for d in node['derived']], [('已取消订单数', 'confirmed', '派生'), ('待确认订单数', 'checked', '派生')])
            uses = ann.get('/api/workspace/types/customer/uses')[1]
            self.assertEqual([(u['kind'], u['count']) for u in uses['used_by'] if u['kind'] == 'derived'], [('derived', 2)])


    def test_the_lineage_draws_a_derived_property_after_the_types_and_relations_it_reads_and_a_viewer_sees_only_confirmed_ones(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            self.assertEqual(ann.post('/api/workspace/types/derived', CANCELLED)[0], 200)
            self.assertEqual(self.confirm(bob, CANCELLED)[0], 200)
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)   # put forward, not confirmed
            graph = ann.get('/api/workspace/graph/lineage')[1]
            nodes = {n['id']: n for n in graph['nodes']}
            count, gross = nodes['derived:customer:cancelled_orders'], nodes['derived:order:gross']
            self.assertEqual((count['kind'], count['derived_kind'], count['type'], count['type_name'], count['name'], count['state']),
                             ('derived', 'statistic', 'customer', '客户', '已取消订单数', 'confirmed'))
            self.assertEqual((gross['kind'], gross['derived_kind'], gross['state']), ('derived', 'function', 'checked'))
            edges = {(e['from'], e['to']) for e in graph['edges']}
            self.assertTrue({('objtype:customer', count['id']), ('objtype:order', count['id']), ('relation:order_customer', count['id'])} <= edges, edges)
            self.assertIn(('objtype:order', gross['id']), edges)
            self.assertFalse([e for e in edges if e[1].startswith('derived:') and e[0].startswith('dataset:')])   # the data comes in through the types
            seen = {n['id'] for n in vera.get('/api/workspace/graph/lineage')[1]['nodes']}
            self.assertIn(count['id'], seen)
            self.assertNotIn(gross['id'], seen)   # a viewer reads confirmed properties only

class DefinitionChecksTests(DerivedTestCase):
    def test_a_version_table_counted_or_added_up_is_refused_and_the_latest_version_or_a_distinct_count_is_offered(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann = team['ann']
            version_count = {'type': 'order', 'english_name': 'promised', 'name': '承诺次数', 'kind': 'statistic', 'path': ['commit_order'], 'measure': {'column': None}, 'fn': 'count'}
            status, body = ann.post('/api/workspace/types/derived', version_count)
            self.assertEqual(status, 400, body)
            self.assertIn('承诺版本', body['error'])
            self.assertEqual(body['offer'], [{'fn': 'latest', 'order': '承诺版本'}, {'fn': 'count_distinct', 'column': '订单号'}])
            self.assertGreater(len(COMMITS), len({r['订单号'] for r in COMMITS}))   # the planted fact: more commitment rows than orders
            status, body = ann.post('/api/workspace/types/derived', {**version_count, 'measure': {'column': '承诺数量'}, 'fn': 'sum', 'name': '承诺数量合计'})
            self.assertEqual(status, 400, body)
            self.assertEqual(ann.post('/api/workspace/types/derived', {**version_count, 'measure': {'column': '订单号'}, 'fn': 'count_distinct', 'name': '承诺过的订单'})[0], 200)
            status, body = ann.post('/api/workspace/types/derived', {**version_count, 'measure': {'column': '承诺数量'}, 'fn': 'latest', 'latest': {'order': '承诺版本'}, 'name': '最新承诺数量', 'english_name': 'latest_commit'})
            self.assertEqual(status, 200, body)
            latest = {}
            for r in COMMITS:
                if r['订单号'] not in latest or int(r['承诺版本']) > int(latest[r['订单号']]['承诺版本']):
                    latest[r['订单号']] = r
            numbers = body['trial']['numbers']
            self.assertEqual((numbers['objects'], numbers['with_value'], numbers['no_value']['no_rows']), (160, len(latest), 160 - len(latest)))   # an order with no commitment has no value, not 0
            self.assertEqual(numbers['rows_used'], len(COMMITS))
            self.assertTrue(any('没有可以统计' in l['text'] for l in body['trial']['lines']))

    def test_an_order_lines_style_key_is_not_a_layer_and_a_one_side_read_through_a_many_side_is_not_added_up(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann = team['ann']
            price = {'type': 'customer', 'english_name': 'price_sum', 'name': '买过的产品单价', 'kind': 'statistic', 'path': ['order_customer', 'order_product'], 'measure': {'column': '单价'}, 'fn': 'sum'}
            status, body = ann.post('/api/workspace/types/derived', price)
            self.assertEqual(status, 400, body)
            self.assertIn('重复', body['error'])
            self.assertEqual([o['fn'] for o in body['offer']], ['count_distinct', 'min', 'max', 'latest'])
            ok = {**price, 'fn': 'count_distinct', 'measure': {'column': '产品编号'}, 'name': '买过几种产品', 'english_name': 'kinds'}
            status, body = ann.post('/api/workspace/types/derived', ok)
            self.assertEqual(status, 200, body)
            kinds = defaultdict(set)
            for r in ORDERS:
                kinds[r['客户编号']].add(r['产品编号'])
            self.assertEqual(self.confirm(team['bob'], ok)[0], 200)
            got = self.values(ann, 'customer', '客户编号', '买过几种产品')
            self.assertEqual({k: int(v) for k, v in got.items()}, {k: len(kinds.get(k, ())) for k in got})   # a customer with no orders has 0 kinds: a count of nothing is 0

    def test_an_aggregation_is_required_across_a_many_side_and_has_no_place_on_a_lookup(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann = team['ann']
            status, body = ann.post('/api/workspace/types/derived', {**CANCELLED, 'fn': None})
            self.assertEqual(status, 400, body)
            self.assertIn('统计方式', body['error'])
            lookup = {'type': 'order', 'english_name': 'unit_price', 'name': '产品单价', 'kind': 'statistic', 'path': ['order_product'], 'measure': {'column': '单价'}, 'fn': None}
            status, body = ann.post('/api/workspace/types/derived', {**lookup, 'fn': 'sum'})
            self.assertEqual(status, 400, body)
            self.assertIn('不用选统计方式', body['error'])
            status, body = ann.post('/api/workspace/types/derived', lookup)
            self.assertEqual(status, 200, body)
            self.assertEqual(body['trial']['numbers']['no_value']['ambiguous'], 0)
            self.assertEqual(self.confirm(team['bob'], lookup)[0], 200)
            prices = {r['产品编号']: r['单价'] for r in SOURCES['产品']['records']}
            got = self.values(ann, 'order', '订单号', '产品单价')
            self.assertEqual(got, {r['订单号']: prices[r['产品编号']] for r in ORDERS})
            # what a person sees offered after choosing a path
            status, shape = ann.post('/api/workspace/types/derived/shape', {'type': 'product', 'path': ['order_product']})
            self.assertEqual((status, shape['many'], [h['toward'] for h in shape['hops']]), (200, True, ['many']), shape)
            status, shape = ann.post('/api/workspace/types/derived/shape', {'type': 'product', 'path': ['stock_product']})
            self.assertEqual(shape['measured']['layers'], [{'column': '快照月份', 'kind': 'snapshot'}])
            self.assertEqual(next(c for c in shape['measured']['columns'] if c['name'] == '库存数量')['fns'], ['sum', 'count', 'count_distinct', 'avg', 'min', 'max', 'median', 'p25', 'p75', 'latest'])
            status, shape = ann.post('/api/workspace/types/derived/shape', {'type': 'order', 'path': ['order_product']})
            self.assertEqual((shape['many'], shape['hops'][0]['toward']), (False, 'one'))

    def test_a_code_column_is_not_added_up_and_a_path_is_three_hops_at_most(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann = team['ann']
            code_sum = {**CANCELLED, 'measure': {'column': '状态码'}, 'fn': 'sum', 'conditions': [], 'name': '状态码合计值'}
            status, body = ann.post('/api/workspace/types/derived', code_sum)
            self.assertEqual(status, 400, body)
            self.assertIn('代码列', body['error'])
            status, body = ann.post('/api/workspace/types/derived', {**CANCELLED, 'path': ['order_customer', 'order_customer', 'order_customer', 'order_customer']})
            self.assertEqual(status, 400, body)
            status, body = ann.post('/api/workspace/types/derived', {**CANCELLED, 'conditions': [{'column': '状态码', 'op': 'is', 'label': '没有这个含义'}]})
            self.assertEqual(status, 400, body)

    def test_the_function_trial_counts_empty_inputs_and_failed_results_and_a_name_cannot_be_a_column_of_the_dataset(self):
        from tests.test_object_types import orders_upload

        def change(record, i):
            return {**record, '交付天数': '' if i == 0 else '0' if i == 1 else record['交付天数']}
        with self.service() as (base, out):
            team = self.team(base)
            self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [orders_upload(change)]})[0], 200)
            self.foundation(team)
            ann = team['ann']
            status, body = ann.post('/api/workspace/types/derived', {**GROSS, 'english_name': 'per_day', 'name': '每天金额', 'expression': '金额 / 交付天数'})
            self.assertEqual(status, 200, body)
            numbers = body['trial']['numbers']
            self.assertEqual((numbers['objects'], numbers['failed'], numbers['no_value']['empty_input'], numbers['with_value']), (160, 1, 1, 158))
            texts = [l['text'] for l in body['trial']['lines']]
            self.assertTrue(any('1 个订单的输入里有空的' in t for t in texts), texts)
            self.assertTrue(any('算不出结果' in t for t in texts), texts)
            status, body = ann.post('/api/workspace/types/derived', {**GROSS, 'name': '金额'})
            self.assertEqual(status, 409, body)
            status, body = ann.post('/api/workspace/types/derived', {**GROSS, 'expression': '金额 *'})
            self.assertEqual(status, 400, body)
            status, form = ann.get('/api/workspace/types/order/derived')[0], ann.get('/api/workspace/types/order/derived')[1]['form']
            self.assertIn('建议在管道里做', form['hint'])
            self.assertEqual(next(c for c in form['columns'] if c['name'] == '金额')['sample'], ORDERS[0]['金额'])


class DataMovesTests(DerivedTestCase):
    def test_a_new_version_that_removes_a_column_it_reads_sends_it_back_and_one_that_only_moves_the_values_does_not(self):
        from tests.test_object_types import orders_upload
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/derived', P50)[0], 200)
            self.assertEqual(self.confirm(bob, P50)[0], 200)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(lambda r, i: {**r, '交付天数': str(int(r['交付天数']) + 1)})]})[0], 200)
            self.assertEqual(self.line(bob, 'product', 'delivery_p50')['state'], 'confirmed')   # its values follow the data
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(drop=('交付天数',))]})[0], 200)
            line = self.line(bob, 'product', 'delivery_p50')
            self.assertEqual(line['state'], 'needs_look')
            self.assertIn(line['stale_word'], ('上一步过时', '更上游过时'))   # the types and relations it stands on moved first

    def test_a_new_version_with_more_objects_it_cannot_compute_a_value_for_sends_it_back_with_the_counts(self):
        from tests.test_object_types import orders_upload
        per_day = {**GROSS, 'english_name': 'per_day', 'name': '每天金额', 'expression': '金额 / 交付天数'}
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/derived', per_day)[0], 200)
            self.assertEqual(self.confirm(bob, per_day)[0], 200)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(lambda r, i: {**r, '交付天数': '0' if i == 3 else r['交付天数']})]})[0], 200)   # one division by zero
            line = self.line(bob, 'order', 'per_day')
            self.assertEqual(line['state'], 'needs_look')
            self.assertIn('算不出值的对象变了：确认时 0 个，现在 1 个', line['reason'])
            self.assertEqual(line['stale_word'], '数据变了')

    def test_a_question_that_names_a_property_that_needs_another_look_is_refused_not_answered_from_the_old_definition(self):
        from tests.test_object_types import orders_upload
        query = {'start': 'product', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': '交付天数P50', 'op': 'average'}}
        model = AskModel({'reasoning': '产品的交付天数P50', 'query': query, 'definitions_used': []})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/derived', P50)[0], 200)
            self.assertEqual(self.confirm(bob, P50)[0], 200)
            status, answer = ann.post('/api/workspace/ask', {'question': '产品的交付天数P50平均是多少？'})
            self.assertEqual((status, answer['status']), (200, 'answered'), answer)
            self.assertEqual(answer['datasets'], {'产品': 1, '订单': 1})   # it stands on the data of the types its path crosses too
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(drop=('交付天数',))]})[0], 200)
            asked = len(model.requests)
            status, refused = ann.post('/api/workspace/ask', {'question': '产品的交付天数P50平均是多少？'})
            self.assertEqual(refused['status'], 'refused', refused)
            self.assertEqual(len(model.requests), asked)
            self.assertIn('交付天数P50', refused['reason'])
            status, reopened = ann.get(f'/api/workspace/ask/{answer["id"]}')
            self.assertEqual(reopened['stale'], [{'dataset': '订单', 'read': 1, 'now': 2}])
            self.assertEqual([(c['name'], c['state']) for c in reopened['changed'] if c['id'].startswith('derived:')], [('产品.交付天数P50', 'needs_look')])


class ExpressionCheckTests(DerivedTestCase):
    def test_the_expression_check_names_an_unknown_column_and_a_type_that_does_not_fit_before_anything_runs(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team)
            ann = team['ann']
            status, body = ann.post('/api/workspace/types/derived/expression', {'type': 'order', 'expression': '金额 * 数量'})
            self.assertEqual((status, body['ok'], body['column_type']), (200, True, 'decimal'))
            status, body = ann.post('/api/workspace/types/derived/expression', {'type': 'order', 'expression': '金额 * 重量'})
            self.assertEqual((status, body['ok']), (200, False))
            self.assertIn('重量', body['errors'][0]['message'])
            status, body = ann.post('/api/workspace/types/derived/expression', {'type': 'order', 'expression': '订单号 * 2'})
            self.assertFalse(body['ok'])


class RowsCountedOnceTests(unittest.TestCase):
    """_each_row_once by the relation checks it reads: a repeated key on the one side, or rows a join multiplies, count a row for more than one object; a row
    that reaches no object only keeps the values from adding up to every row."""
    SC = {'user': None, 'relations': {'order_customer': {'content': {'from': 'order', 'to': 'customer', 'cardinality': 'many_to_one'}}}}
    COUNT = {'kind': 'statistic', 'type': 'customer', 'path': ['order_customer']}

    def counted(self, **numbers):
        found = {'problems': [], 'numbers': {'rows': 10, 'matched': 10, 'fan_keys': 0, 'extra_rows': 0, **numbers}}
        with mock.patch.object(workspace_questions, 'check_relation', return_value=found):
            return workspace_questions._each_row_once(None, self.SC, self.COUNT)

    def test_every_row_reaching_one_object_is_counted_once_and_exactly(self):
        self.assertEqual(self.counted(), {'once': True, 'exact': True})

    def test_a_row_that_reaches_no_object_is_still_counted_once(self):
        self.assertEqual(self.counted(matched=9), {'once': True, 'exact': False})

    def test_a_repeated_key_on_the_one_side_counts_a_row_for_more_than_one_object(self):
        self.assertEqual(self.counted(fan_keys=1), {'once': False, 'exact': False})

    def test_rows_a_join_multiplies_are_counted_for_more_than_one_object(self):
        self.assertEqual(self.counted(extra_rows=2), {'once': False, 'exact': False})
