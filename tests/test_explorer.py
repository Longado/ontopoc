"""The object explorer on the workspace, walked through the real service with two builders, a viewer and an admin on the seven planted tables: filters, charts of every
kind, a single object with its related objects, "转到关联的 X", the grey of what is not confirmed (also after a shifted upload), and what a row rule or type visibility hides.
Expected numbers are counted from the planted records here, not from the service."""
from collections import Counter
import statistics

from tests import test_workspace_store as planted
from tests.test_derived_properties import CANCELLED, DerivedTestCase, GROSS
from tests.test_object_types import VALID, orders_upload, shifted_orders_csv

ORDERS = planted.planted_bundle()['sources']['订单']['records']
CUSTOMERS = list({r['客户编号']: r for r in reversed(planted.planted_bundle()['sources']['客户']['records'])}.values())   # KH012 once: the team uploads the mended table
BY_STATUS = Counter(r['状态码'] for r in ORDERS)
LIVE = [r for r in ORDERS if r['状态码'] != '2']
ORDER_Q = {'type': 'order'}


def query(**more):
    return {'type': 'order', **more}


class UseLayerCase(DerivedTestCase):
    """The planted world with a confirmed view 有效订单 (剔除 状态码 = 2) and a confirmed derived property 已取消订单数 on 客户."""

    def world(self, team):
        self.foundation(team)
        ann, bob = team['ann'], team['bob']
        self.assertEqual(ann.post('/api/workspace/types/views', VALID)[0], 200)
        shown = bob.get('/api/workspace/types/order/views')[1]['views'][0]
        self.assertEqual(bob.post('/api/workspace/types/views/confirm', {'id': VALID['name'], 'version': shown['version'], 'seen': shown['seen']})[0], 200)
        self.assertEqual(ann.post('/api/workspace/types/derived', CANCELLED)[0], 200)
        self.assertEqual(self.confirm(bob, CANCELLED)[0], 200)

    def table(self, client, q, page=1, expect=200):
        status, body = client.post('/api/workspace/explore/table', {'query': q, 'page': page})
        self.assertEqual(status, expect, body)
        return body

    def chart(self, client, q, chart, expect=200):
        status, body = client.post('/api/workspace/explore/chart', {'query': q, 'chart': chart})
        self.assertEqual(status, expect, body)
        return body

    def meta(self, client, name='order', expect=200):
        status, body = client.get(f'/api/workspace/explore/{name}')
        self.assertEqual(status, expect, body)
        return body


class TableTests(UseLayerCase):
    def test_instances_are_filtered_by_value_by_text_and_by_number_and_a_view_keeps_its_rows(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            bob = team['bob']
            everything = self.table(bob, ORDER_Q)
            self.assertEqual((everything['total'], len(everything['rows']), everything['pages']), (160, 50, 4))
            self.assertEqual(self.table(bob, ORDER_Q, page=4)['numbers'][-1], 160)
            cancelled = self.table(bob, query(filters=[{'field': '状态码', 'op': 'eq', 'value': '2'}]))
            self.assertEqual(cancelled['total'], BY_STATUS['2'])
            self.assertEqual(self.table(bob, query(filters=[{'field': '状态码', 'op': 'ne', 'value': '2'}]))['total'], len(LIVE))
            self.assertEqual(self.table(bob, query(filters=[{'field': '订单号', 'op': 'contains', 'value': '0007'}]))['total'], sum('0007' in r['订单号'] for r in ORDERS))
            big = self.table(bob, query(filters=[{'field': '金额', 'op': 'gt', 'value': '50000'}]))
            self.assertEqual(big['total'], sum(float(r['金额']) > 50000 for r in ORDERS))
            two = self.table(bob, query(filters=[{'field': '金额', 'op': 'gt', 'value': '50000'}, {'field': '状态码', 'op': 'eq', 'value': '2'}]))
            self.assertEqual(two['total'], sum(float(r['金额']) > 50000 and r['状态码'] == '2' for r in ORDERS))
            viewed = self.table(bob, query(view='有效订单'))
            self.assertEqual(viewed['total'], len(LIVE))
            self.assertTrue(viewed['standing']['confirmed'])
            self.assertEqual([l['line'] for l in viewed['standing']['lines']], ['状态码 不是 2（已取消）：算进 0 已交付、1 生产中，Bob 确认于 订单 v1'])   # the acceptance sentence, from the definitions
            both = self.table(bob, query(view='有效订单', filters=[{'field': '金额', 'op': 'gt', 'value': '50000'}]))
            self.assertEqual(both['total'], sum(float(r['金额']) > 50000 for r in LIVE))
            # what the page needs to draw its filter bar
            fields = {f['key']: f for f in self.meta(bob)['fields']}
            self.assertEqual({o['value']: o['label'] for o in fields['状态码']['options']}, {'0': '已交付', '1': '生产中', '2': '已取消'})
            self.assertEqual((fields['金额']['numeric'], fields['状态码']['numeric'], fields['订单号']['options']), (True, False, None))

    def test_a_filter_that_cannot_mean_anything_is_refused_in_words(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            bob = team['bob']
            self.assertIn('没有“重量”', self.table(bob, query(filters=[{'field': '重量', 'op': 'eq', 'value': '1'}]), expect=400)['error'])
            self.assertIn('不能比大小', self.table(bob, query(filters=[{'field': '订单号', 'op': 'gt', 'value': '1'}]), expect=400)['error'])
            self.assertIn('要写成数字', self.table(bob, query(filters=[{'field': '金额', 'op': 'gt', 'value': 'abc'}]), expect=400)['error'])
            self.assertIn('没有叫“不存在”的视图', self.table(bob, query(view='不存在'), expect=404)['error'])
            self.assertEqual(self.table(bob, {'type': 'nothing'}, expect=404)['error'], '没有这个对象类型')


class ChartTests(UseLayerCase):
    def test_every_chart_kind_gives_what_the_planted_rows_count_to(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            bob = team['bob']
            bar = self.chart(bob, ORDER_Q, {'kind': 'bar', 'group': '状态码', 'fn': 'count'})
            self.assertEqual({g['key']: g['value'] for g in bar['groups']}, dict(BY_STATUS))
            self.assertEqual([g['label'] for g in bar['groups']], ['0 已交付', '1 生产中', '2 已取消'])   # the meanings, since they are confirmed
            self.assertEqual((bar['standing']['confirmed'], bar['rows']), (True, 160))
            by_customer = self.chart(bob, query(view='有效订单'), {'kind': 'bar', 'group': '客户编号', 'measure': '金额', 'fn': 'sum'})
            expected = Counter()
            for r in LIVE:
                expected[r['客户编号']] += float(r['金额'])
            for g in by_customer['groups']:
                self.assertAlmostEqual(float(g['value']), expected[g['key']], places=4)
            self.assertEqual(len(by_customer['groups']) + by_customer['groups_hidden'], len(expected))   # a group past the cap is counted, never dropped quietly
            number = self.chart(bob, query(view='有效订单'), {'kind': 'number', 'measure': '金额', 'fn': 'sum'})
            self.assertEqual(float(number['value']), sum(float(r['金额']) for r in LIVE))
            self.assertEqual(self.chart(bob, ORDER_Q, {'kind': 'number'})['value'], 160)   # no measure: the rows
            self.assertEqual(self.chart(bob, ORDER_Q, {'kind': 'number', 'measure': '客户编号', 'fn': 'count_distinct'})['value'], len({r['客户编号'] for r in ORDERS}))
            pie = self.chart(bob, ORDER_Q, {'kind': 'pie', 'group': '状态码', 'fn': 'count'})
            self.assertEqual(sum(g['value'] for g in pie['groups']), 160)
            hist = self.chart(bob, ORDER_Q, {'kind': 'histogram', 'measure': '金额', 'bins': 8})
            self.assertEqual((len(hist['bins']), sum(b['count'] for b in hist['bins']) + hist['missing']), (8, 160))
            self.assertEqual((hist['bins'][0]['from'], hist['bins'][-1]['to']), (min(float(r['金额']) for r in ORDERS), max(float(r['金额']) for r in ORDERS)))
            stats = self.chart(bob, ORDER_Q, {'kind': 'table', 'measure': '交付天数', 'group': '状态码'})
            for row in stats['table']:
                days = [float(r['交付天数']) for r in ORDERS if r['状态码'] == row['key'] and r['交付天数']]
                got = dict(zip([c['fn'] for c in stats['columns']], row['values']))
                self.assertEqual((got['count'], round(got['avg'], 6), got['median'], got['min'], got['max']), (len(days), round(statistics.mean(days), 6), statistics.median(days), min(days), max(days)))
            whole = self.chart(bob, ORDER_Q, {'kind': 'table', 'measure': '金额'})
            self.assertEqual([r['label'] for r in whole['table']], ['全部'])

    def test_only_the_top_n_and_a_sort_order_for_bars_pies_and_the_statistics_table_and_what_is_left_out_is_named(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            bob = team['bob']
            totals = Counter()
            rows = Counter()
            for r in LIVE:
                totals[r['客户编号']] += float(r['金额'])
                rows[r['客户编号']] += 1
            ranked = sorted(totals, key=lambda k: (-totals[k], k))
            top = self.chart(bob, query(view='有效订单'), {'kind': 'bar', 'group': '客户编号', 'measure': '金额', 'fn': 'sum', 'top': 5})
            self.assertEqual([g['key'] for g in top['groups']], ranked[:5])   # the biggest five, the biggest first
            self.assertEqual(top['groups_hidden'], len(totals) - 5)
            self.assertEqual([h['label'] for h in top['hidden_groups']], ranked[5:15])   # what was left out is named (the first ten), with its rows and its sum
            first = top['hidden_groups'][0]
            self.assertEqual((first['rows'], float(first['value'])), (rows[ranked[5]], totals[ranked[5]]))
            small = self.chart(bob, query(view='有效订单'), {'kind': 'bar', 'group': '客户编号', 'measure': '金额', 'fn': 'sum', 'order': 'asc'})
            self.assertEqual([g['key'] for g in small['groups']][:3], sorted(ranked[:30], key=lambda k: (totals[k], k))[:3])   # the cap keeps the biggest 30, then they are drawn from the smallest
            pie = self.chart(bob, query(view='有效订单'), {'kind': 'pie', 'group': '客户编号', 'measure': '金额', 'fn': 'sum', 'top': 3})
            self.assertEqual([g['key'] for g in pie['groups']], ranked[:3])
            table = self.chart(bob, query(view='有效订单'), {'kind': 'table', 'measure': '金额', 'group': '客户编号', 'top': 2})
            self.assertEqual([r['key'] for r in table['table']], sorted(rows, key=lambda k: (-rows[k], k))[:2])   # a statistics table ranks its groups by their rows
            self.assertEqual(table['groups_hidden'], len(rows) - 2)
            self.assertIn('最多', self.chart(bob, ORDER_Q, {'kind': 'bar', 'group': '状态码', 'top': 99}, expect=400)['error'])
            self.assertIn('从大到小', self.chart(bob, ORDER_Q, {'kind': 'bar', 'group': '状态码', 'order': 'sideways'}, expect=400)['error'])

    def test_rows_a_chart_cannot_place_are_named_with_their_rows_and_their_measure(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            bob = team['bob']
            lost = [r for r in ORDERS if r['客户编号'] == 'KH099']
            chart = self.chart(bob, ORDER_Q, {'kind': 'bar', 'group': 'via:order_customer:客户名称', 'measure': '金额', 'fn': 'sum'})
            self.assertEqual(chart['unplaced'], [{'label': 'KH099', 'rows': len(lost), 'value': sum(float(r['金额']) for r in lost)}])
            names = {c['客户编号']: c['客户名称'] for c in CUSTOMERS}
            expected = Counter()
            for r in ORDERS:
                if r['客户编号'] in names:
                    expected[names[r['客户编号']]] += float(r['金额'])
            self.assertEqual(len(expected), 30)
            self.assertEqual({g['key']: float(g['value']) for g in chart['groups']}, dict(expected))
            self.assertEqual(sum(g['rows'] for g in chart['groups']), len(ORDERS) - len(lost))   # every other row is in a group
            self.assertEqual(chart['group'], '客户的客户名称')
            self.assertIn('订单属于客户', [l['name'] for l in chart['standing']['lines']])   # the relation it went through is in the caliber
            reach = {f['key']: f for f in self.meta(bob)['reach']}
            self.assertEqual(reach['via:order_customer:客户名称']['name'], '客户的客户名称')
            self.assertNotIn('via:order_customer:客户名称', {f['key'] for f in self.meta(bob, 'customer')['reach']})   # the one side does not reach the many
            self.assertIn('不是从', self.chart(bob, {'type': 'customer'}, {'kind': 'bar', 'group': 'via:order_customer:客户名称'}, expect=400)['error'])

    def test_a_chart_that_would_lie_is_refused_the_way_the_pipelines_refuse_it(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            bob = team['bob']
            self.assertIn('不能求和', self.chart(bob, ORDER_Q, {'kind': 'number', 'measure': '状态码', 'fn': 'sum'}, expect=400)['error'])   # a code is not an amount
            self.assertIn('不能求和', self.chart(bob, ORDER_Q, {'kind': 'bar', 'group': '状态码', 'measure': '订单号', 'fn': 'sum'}, expect=400)['error'])
            self.assertIn('要指定哪一列', self.chart(bob, ORDER_Q, {'kind': 'number', 'fn': 'sum'}, expect=400)['error'])
            self.assertIn('只能用计数或求和', self.chart(bob, ORDER_Q, {'kind': 'pie', 'group': '状态码', 'measure': '金额', 'fn': 'avg'}, expect=400)['error'])
            self.assertIn('要选按哪一列分组', self.chart(bob, ORDER_Q, {'kind': 'bar'}, expect=400)['error'])
            self.assertIn('要选一个数字列', self.chart(bob, ORDER_Q, {'kind': 'histogram', 'measure': '订单号'}, expect=400)['error'])
            self.assertIn('要选一个数字列', self.chart(bob, ORDER_Q, {'kind': 'histogram', 'measure': '状态码'}, expect=400)['error'])   # a code's size means nothing
            self.assertIn('种类', self.chart(bob, ORDER_Q, {'kind': 'radar'}, expect=400)['error'])

    def test_empty_values_are_a_group_of_their_own_and_a_derived_property_charts_beside_the_columns(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            by_city = self.chart(bob, {'type': 'customer'}, {'kind': 'bar', 'group': '客户等级', 'fn': 'count'})
            self.assertEqual({g['key']: g['value'] for g in by_city['groups']}, dict(Counter(r['客户等级'] or None for r in CUSTOMERS)))
            self.assertEqual(self.table(bob, {'type': 'customer', 'filters': [{'field': '客户等级', 'op': 'empty', 'value': ''}]})['total'], sum(not r['客户等级'] for r in CUSTOMERS))
            # the confirmed derived property is a field like the others, in colour
            mine = Counter(r['客户编号'] for r in ORDERS if r['状态码'] == '2')
            per = self.chart(bob, {'type': 'customer'}, {'kind': 'bar', 'group': 'derived:cancelled_orders', 'fn': 'count'})
            self.assertEqual({g['key']: g['value'] for g in per['groups']}, dict(Counter(str(mine.get(r['客户编号'], 0)) for r in CUSTOMERS)))
            self.assertTrue(per['standing']['confirmed'])
            # one nobody has confirmed draws grey with the reason, for a builder; a viewer is not shown it at all
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)
            grey = self.chart(ann, ORDER_Q, {'kind': 'number', 'measure': 'derived:gross', 'fn': 'sum'})
            self.assertFalse(grey['standing']['confirmed'])
            self.assertIn('含税金额', grey['standing']['reasons'][0])
            self.assertIn('还没有另一位确认', grey['standing']['reasons'][0])
            self.assertEqual(self.chart(team['vera'], ORDER_Q, {'kind': 'number', 'measure': 'derived:gross', 'fn': 'sum'}, expect=400)['error'], '这个对象类型里没有“derived:gross”这个字段')
            self.assertNotIn('derived:gross', {f['key'] for f in self.meta(team['vera'])['fields']})


class GreyTests(UseLayerCase):
    def test_a_shifted_upload_turns_what_stands_on_the_codes_grey_with_the_reason(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            before = self.chart(bob, query(view='有效订单'), {'kind': 'bar', 'group': '状态码', 'fn': 'count'})
            self.assertTrue(before['standing']['confirmed'])
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            after = self.chart(bob, query(view='有效订单'), {'kind': 'bar', 'group': '状态码', 'fn': 'count'})
            self.assertFalse(after['standing']['confirmed'])
            reasons = '；'.join(after['standing']['reasons'])
            self.assertIn('视图「有效订单」', reasons)
            self.assertIn('含义「订单.状态码」', reasons)
            self.assertIn('需要再看', reasons)
            self.assertEqual([g['label'] for g in after['groups']], ['1', '3'])   # the meanings are not trusted any more: the codes show as the data has them, and the view still drops code 2, which is now 生产中
            view_line = next(l for l in after['standing']['lines'] if l['kind'] == 'view')
            self.assertFalse(view_line['confirmed'])
            self.assertIn('订单 第 2 版', after['standing']['why'])   # the reason at the bottom of the chain, not the pointers above it
            self.assertEqual(after['standing']['why'].split('：')[0], '含义「订单.状态码」')
            # a plain table of a type that needs a look is grey too, and a viewer is not shown the type at all
            self.assertFalse(self.table(bob, ORDER_Q)['standing']['confirmed'])
            self.assertEqual(self.meta(vera, expect=404)['error'], '没有这个对象类型')


class CaliberWordsTests(UseLayerCase):
    def test_a_view_says_which_code_values_are_in_and_out_and_a_new_value_asks_whether_it_comes_in(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            line = self.table(bob, query(view='有效订单'))['standing']['lines'][0]
            self.assertEqual(line['line'], '状态码 不是 2（已取消）：算进 0 已交付、1 生产中，Bob 确认于 订单 v1')   # what is in as well as what is out, from the confirmed meanings
            self.assertEqual(self.view_page(bob)['caliber'], '状态码 不是 2（已取消）：算进 0 已交付、1 生产中')   # the confirm screen of the view reads the same
            # an upload in which four orders carry a code nobody has given a meaning
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(lambda r, i: {**r, '状态码': '3'} if i % 40 == 0 else r)]})[0], 200)
            view = next(l for l in self.table(bob, query(view='有效订单'))['standing']['lines'] if l['kind'] == 'view')
            self.assertFalse(view['confirmed'])
            self.assertIn('新值 3 算不算进来', view['reason'])
            self.assertIn('4 行', view['reason'])
            self.assertIn('按现在的写法', view['reason'])
            self.assertIn('不是 2（已取消）', view['reason'])   # what the view says now, so the confirmer sees what the new value would do under it

    def view_page(self, client):
        status, body = client.get('/api/workspace/types/order/views')
        self.assertEqual(status, 200, body)
        return body['views'][0]


class UploadPreviewTests(UseLayerCase):
    def test_before_an_overwrite_the_service_says_what_would_go_back_to_needs_another_look_and_changes_nothing(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            status, body = ann.post('/api/workspace/datasets/upload/preview', {'files': [shifted_orders_csv()]})
            self.assertEqual(status, 200, body)
            kinds = {(m['kind'], m['title']) for m in body['moved']}
            self.assertIn(('type', '订单'), kinds)
            self.assertIn(('view', '有效订单（订单的视图）'), kinds)
            self.assertIn(('meaning', '订单.状态码'), kinds)
            self.assertTrue(all(m['reason'] for m in body['moved']))   # each says why it would need another look
            self.assertEqual(body['datasets'], ['订单'])
            # nothing was written: the orders are still version 1 and everything is still confirmed
            self.assertEqual(self.meta(bob)['dataset_version'], 1)
            self.assertTrue(self.table(bob, query(view='有效订单'))['standing']['confirmed'])
            # an upload of a new dataset sends nothing back, and a viewer may not even ask
            fresh = {**shifted_orders_csv(), 'target': None, 'mode': None, 'name': '另一张表'}
            fresh = {k: v for k, v in fresh.items() if v is not None}
            self.assertEqual(ann.post('/api/workspace/datasets/upload/preview', {'files': [fresh]})[1]['moved'], [])
            self.assertEqual(vera.post('/api/workspace/datasets/upload/preview', {'files': [shifted_orders_csv()]})[0], 403)
            # what the preview said is what the upload then does
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            self.assertFalse(self.table(bob, query(view='有效订单'))['standing']['confirmed'])

class VisibilityTests(UseLayerCase):
    def test_a_row_rule_limits_every_table_chart_and_pivot_to_the_rows_the_person_may_read(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            admin, vera = team['admin'], team['vera']
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH026', 'user_ids': [ids['vera']]}]})[0], 200)
            mine = [r for r in ORDERS if r['客户编号'] == 'KH026']
            table = self.table(vera, ORDER_Q)
            self.assertEqual((table['total'], table['rows_limited']), (len(mine), True))
            self.assertEqual(self.chart(vera, ORDER_Q, {'kind': 'number'})['value'], len(mine))   # a count of their rows, never of the whole data
            bar = self.chart(vera, ORDER_Q, {'kind': 'bar', 'group': '客户编号', 'fn': 'count'})
            self.assertEqual({g['key']: g['value'] for g in bar['groups']}, {'KH026': len(mine)})
            self.assertEqual(self.table(vera, query(view='有效订单'))['total'], sum(r['状态码'] != '2' for r in mine))
            options = {f['key']: f for f in self.meta(vera)['fields']}['客户编号']['options']
            self.assertEqual([o['value'] for o in options], ['KH026'])   # the values to pick from are the ones in their rows, not the whole data's
            self.assertEqual(self.meta(vera)['rows'], len(mine))
            # the pivot reads the rows they may read on both ends
            pivot = self.table(vera, {'type': 'customer', 'pivot': {'relation': 'order_customer', 'side': 'from', 'source': ORDER_Q}})
            self.assertEqual(pivot['total'], sum(c['客户编号'] == 'KH026' for c in CUSTOMERS))

    def test_a_type_a_person_may_not_see_is_not_there_for_them_in_the_explorer(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            admin, ann, bob = team['admin'], team['ann'], team['bob']
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'customer', 'visible_to': [ids['bob']]})[0], 200)
            self.assertEqual(self.meta(ann, 'customer', expect=404)['error'], '没有这个对象类型')
            self.assertEqual(self.table(ann, {'type': 'customer'}, expect=404)['error'], '没有这个对象类型')
            self.assertEqual(self.chart(ann, {'type': 'customer'}, {'kind': 'number'}, expect=404)['error'], '没有这个对象类型')
            self.assertNotIn('order_customer', [r['id'] for r in self.meta(ann)['relations']])   # nor the way across to it
            pivot = {'type': 'customer', 'pivot': {'relation': 'order_customer', 'side': 'from', 'source': ORDER_Q}}
            self.assertEqual(self.table(ann, pivot, expect=404)['error'], '没有这个对象类型')
            self.assertEqual(self.table(bob, pivot)['total'], sum(c['客户编号'] in {r['客户编号'] for r in ORDERS} for c in CUSTOMERS))
            self.assertIn('order_customer', [r['id'] for r in self.meta(bob)['relations']])


class ObjectTests(UseLayerCase):
    def test_an_object_page_lists_what_is_related_and_the_pivot_opens_the_whole_set(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            bob = team['bob']
            seen = self.table(bob, {'type': 'customer', 'filters': [{'field': '客户编号', 'op': 'eq', 'value': 'KH022'}]})
            n = seen['numbers'][0]
            status, page = bob.get(f'/api/workspace/explore/customer/object/{n}')
            self.assertEqual(status, 200, page)
            self.assertEqual((page['key'], page['text']), ({'客户编号': 'KH022', '城市': page['key']['城市']}, f'KH022 + {page["key"]["城市"]}'))
            names = [c['name'] for c in page['columns']]
            self.assertEqual(names[0], '已取消订单数')   # the derived property, first, as on the objects tab
            related = {r['id']: r for r in page['related']}
            orders = [r for r in ORDERS if r['客户编号'] == 'KH022']
            self.assertEqual(related['order_customer']['count'], len(orders))
            self.assertEqual((related['order_customer']['other'], related['order_customer']['side'], related['order_customer']['confirmed']), ('order', 'to', True))
            self.assertEqual([o['text'] for o in related['order_customer']['objects']], [r['订单号'] for r in orders][:5])
            opened = self.table(bob, related['order_customer']['query'])   # 转到关联的订单
            self.assertEqual(sorted(opened['rows'][i][[c['name'] for c in opened['columns']].index('订单号')] for i in range(opened['total'])), sorted(r['订单号'] for r in orders))
            # and from an order back to its customer
            order_n = self.table(bob, query(filters=[{'field': '订单号', 'op': 'eq', 'value': orders[0]['订单号']}]))['numbers'][0]
            back = {r['id']: r for r in bob.get(f'/api/workspace/explore/order/object/{order_n}')[1]['related']}
            self.assertEqual((back['order_customer']['count'], back['order_customer']['side'], back['order_customer']['other']), (1, 'from', 'customer'))
            self.assertEqual(bob.get('/api/workspace/explore/customer/object/9999')[0], 404)
            self.assertEqual(bob.get('/api/workspace/explore/customer/object/x')[0], 404)

    def test_a_search_word_keeps_the_rows_where_the_key_or_any_column_holds_it(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            bob = team['bob']
            word = ORDERS[7]['订单号'][-4:]
            by_key = self.table(bob, query(search=word))
            self.assertEqual(by_key['total'], sum(word in ' '.join(str(v) for v in r.values()) for r in ORDERS))
            self.assertGreaterEqual(by_key['total'], 1)
            order_no = by_key['columns'].index(next(c for c in by_key['columns'] if c['name'] == '订单号'))
            self.assertTrue(all(word in ' '.join(str(v) for v in row if v is not None) for row in by_key['rows']))
            self.assertIn(ORDERS[7]['订单号'], [row[order_no] for row in by_key['rows']])
            customer = CUSTOMERS[0]['客户名称']
            named = self.table(bob, {'type': 'customer', 'search': customer[:2].upper()})
            self.assertEqual(named['total'], sum(customer[:2].upper().casefold() in ' '.join(str(v) for v in r.values()).casefold() for r in CUSTOMERS))
            narrowed = self.table(bob, query(search=word, filters=[{'field': '状态码', 'op': 'eq', 'value': '2'}]))
            self.assertLessEqual(narrowed['total'], by_key['total'])
            self.assertEqual(self.table(bob, query(search='  '))['total'], 160)   # blank is no search
            self.assertEqual(self.table(bob, query(search='zzz-nobody'))['total'], 0)
            status, body = bob.post('/api/workspace/explore/table', {'query': query(search=5), 'page': 1})
            self.assertEqual(status, 400, body)

    def test_a_related_object_carries_a_name_when_its_type_has_a_name_column(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            bob = team['bob']
            order = ORDERS[0]
            order_n = self.table(bob, query(filters=[{'field': '订单号', 'op': 'eq', 'value': order['订单号']}]))['numbers'][0]
            related = {r['id']: r for r in bob.get(f'/api/workspace/explore/order/object/{order_n}')[1]['related']}
            [customer] = related['order_customer']['objects']
            self.assertTrue(customer['text'].startswith(order['客户编号']))
            self.assertEqual(customer['name'], next(c['客户名称'] for c in CUSTOMERS if c['客户编号'] == order['客户编号']))
            product = related['order_product']['objects'][0] if 'order_product' in related else None
            if product:
                self.assertEqual(product['name'], next(p['产品名称'] for p in planted.planted_bundle()['sources']['产品']['records'] if p['产品编号'] == product['text']))
            cn = self.table(bob, {'type': 'customer', 'filters': [{'field': '客户编号', 'op': 'eq', 'value': order['客户编号']}]})['numbers'][0]
            back = {r['id']: r for r in bob.get(f'/api/workspace/explore/customer/object/{cn}')[1]['related']}
            self.assertIsNone(back['order_customer']['objects'][0]['name'])   # an order has no name column: the key says it all

    def test_a_pivot_goes_from_a_filtered_set_to_the_set_it_links_to(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            bob = team['bob']
            pivot = {'type': 'customer', 'pivot': {'relation': 'order_customer', 'side': 'from',
                                                 'source': query(filters=[{'field': '状态码', 'op': 'eq', 'value': '2'}])}}
            got = self.table(bob, pivot)
            linked = {r['客户编号'] for r in ORDERS if r['状态码'] == '2'}
            self.assertEqual(got['total'], sum(c['客户编号'] in linked for c in CUSTOMERS))   # customers, a row for each (KH012 has two)
            self.assertTrue(got['standing']['lines'][0]['line'].startswith('订单属于客户：订单 → 客户'))
            self.assertEqual([l['kind'] for l in got['standing']['lines']], ['relation'])
            wrong = self.table(bob, {'type': 'product', 'pivot': pivot['pivot']}, expect=400)
            self.assertIn('不是从“order”连到“product”的', wrong['error'])
            twice = {'type': 'order', 'pivot': {'relation': 'order_customer', 'side': 'to', 'source': {**pivot, 'type': 'customer'}}}
            self.assertIn('只能转一次', self.table(bob, twice, expect=400)['error'])
