"""A derived property whose conditions name code meanings asks, like a view, whether a value the data did not have when it was confirmed counts, and is not
confirmed until someone answers. Walked through the real service on the pilot sample (docs/pilot/sample): 有效订单金额 per customer leaves out 新建, 已取消 and
已退款; orders_update.csv brings a new status 6 (暂停), one order of 855 for C024. Left unanswered, the property used to count it and could be confirmed in
the group with the rest (C024 read 4,755 while the view and the board read 3,900 for the same idea). Expected numbers are counted from the CSV files here."""
import base64
import csv
import json
from pathlib import Path
from urllib.parse import quote

from ontology_poc_generator.derived_properties import evaluate
from ontology_poc_generator.object_types import element_row
from ontology_poc_generator.workspace_store import current_dataset, open_workspace
from tests.test_two_person import SigningTestCase

SAMPLE = Path(__file__).resolve().parents[1] / 'docs' / 'pilot' / 'sample'
LABELS = {'0': '新建', '1': '已付款', '2': '已发货', '3': '已送达', '4': '已取消', '5': '已退款'}
LEFT_OUT = ('新建', '已取消', '已退款')
ORDER = {'english_name': 'order', 'name': '订单', 'dataset': 'orders', 'key': ['order_id'],
         'properties': [{'column': 'customer_id'}, {'column': 'order_date'}, {'column': 'amount'}, {'column': 'status_code', 'enum': True}],
         'enums': {'status_code': [{'value': v, 'label': l} for v, l in LABELS.items()]}}
CUSTOMER = {'english_name': 'customer', 'name': '客户', 'dataset': 'customers', 'key': ['customer_id'], 'properties': [{'column': 'name'}, {'column': 'city'}, {'column': 'tier'}]}
RELATION = {'english_name': 'order_customer', 'name': '订单属于客户', 'from': 'order', 'to': 'customer', 'cardinality': 'many_to_one', 'from_column': 'customer_id', 'to_column': 'customer_id'}
CONDITIONS = [{'column': 'status_code', 'op': 'is_not', 'label': label} for label in LEFT_OUT]
VIEW = {'name': '有效订单', 'type': 'order', 'filters': CONDITIONS}
VALID_AMOUNT = {'type': 'customer', 'english_name': 'valid_amount', 'name': '有效订单金额', 'kind': 'statistic', 'path': ['order_customer'], 'measure': {'column': 'amount'}, 'fn': 'sum',
                'conditions': CONDITIONS}
DERIVED = 'derived:customer:valid_amount'
REWRITTEN = [*({'value': v, 'label': l} for v, l in LABELS.items()), {'value': '6', 'label': '暂停'}]


def part(name: str, **more) -> dict:
    return {'filename': name, 'content_base64': base64.b64encode((SAMPLE / name).read_bytes()).decode(), **more}


def truth() -> dict:
    """{customer: valid amount} after the update, with 6 left out and with it counted, from the CSV files."""
    orders = {r['order_id']: r for r in csv.DictReader((SAMPLE / 'orders.csv').open(encoding='utf-8'))}
    orders |= {r['order_id']: r for r in csv.DictReader((SAMPLE / 'orders_update.csv').open(encoding='utf-8'))}
    out = {'without': {}, 'with': {}}
    for r in orders.values():
        if r['status_code'] in ('0', '4', '5'):
            continue
        out['with'][r['customer_id']] = out['with'].get(r['customer_id'], 0) + int(r['amount'])
        if r['status_code'] != '6':
            out['without'][r['customer_id']] = out['without'].get(r['customer_id'], 0) + int(r['amount'])
    return out


TRUTH = truth()
NEW_ROWS = sum(1 for r in csv.DictReader((SAMPLE / 'orders_update.csv').open(encoding='utf-8')) if r['status_code'] == '6')


class PilotFoundation(SigningTestCase):
    """The pilot sample with its definitions confirmed (no tests of its own)."""

    def foundation(self, base, derived=(VALID_AMOUNT,)):
        """Ann puts forward the two types, the relation, the view and the derived properties; Bob confirms them."""
        team = self.people(base, 'ann', 'bob')
        ann, bob = team['ann'], team['bob']
        self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [part('orders.csv'), part('customers.csv')]})[0], 200)
        for payload in (ORDER, CUSTOMER):
            self.assertEqual(ann.post('/api/workspace/types', payload)[0], 200, payload['english_name'])
        meanings = next(p for p in bob.get('/api/workspace/types/order')[1]['properties'] if p['column'] == 'status_code')['meanings']
        self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order', 'column': 'status_code', 'version': meanings['version'], 'seen': meanings['seen']})[0], 200)
        for name in ('order', 'customer'):
            shown = bob.get(f'/api/workspace/types/{name}')[1]
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': name, 'version': shown['version'], 'seen': shown['seen']})[0], 200, name)
        self.assertEqual(ann.post('/api/workspace/relations', RELATION)[0], 200)
        relation = bob.get('/api/workspace/relations/order_customer')[1]
        self.assertEqual(bob.post('/api/workspace/relations/confirm', {'id': 'order_customer', 'version': relation['version'], 'seen': relation['check']['signature']})[0], 200)
        self.assertEqual(ann.post('/api/workspace/types/views', VIEW)[0], 200)
        view = self.view(bob)
        self.assertEqual(bob.post('/api/workspace/types/views/confirm', {'id': '有效订单', 'version': view['version'], 'seen': view['seen']})[0], 200)
        for payload in derived:
            status, body = ann.post('/api/workspace/types/derived', payload)
            self.assertEqual(status, 200, body)
            line = self.line(bob, payload['english_name'])
            self.assertEqual(bob.post('/api/workspace/types/derived/confirm', {'type': 'customer', 'english_name': payload['english_name'], 'version': line['version'], 'seen': line['seen']})[0], 200)
        return team

    def view(self, client):
        return next(v for v in client.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == '有效订单')

    def line(self, client, name='valid_amount'):
        status, body = client.get('/api/workspace/types/customer/derived')
        self.assertEqual(status, 200, body)
        return next(d for d in body['derived'] if d['id'] == name)


class DerivedNewValueTests(PilotFoundation):
    def pilot(self, base):
        """The foundation; then Ann uploads orders_update.csv by key and writes the meanings again with 6 = 暂停."""
        team = self.foundation(base)
        ann = team['ann']
        status, body = ann.post('/api/workspace/datasets/upload', {'files': [part('orders_update.csv', target='orders', mode='update_by_key', key_columns=['order_id'])]})
        self.assertEqual(status, 200, body)
        self.assertEqual(ann.post('/api/workspace/types/meanings', {'id': 'order', 'column': 'status_code', 'values': REWRITTEN})[0], 200)
        return team

    def group(self, client):
        status, body = client.get(f'/api/workspace/queue/group?dataset={quote("orders")}&version=2')
        self.assertEqual(status, 200, body)
        return body

    def request(self, group, choice='in', answer_derived=True):
        items = []
        for item in group['items']:
            if not item['ready']:
                continue
            body = {'element': item['element'], 'version': item['version'], 'seen': item['seen']}
            if item.get('new_values') and (item['kind'] != 'derived' or answer_derived):
                body['new_values'] = [{'column': n['column'], 'value': n['value'], 'choice': choice} for n in item['new_values']]
            items.append(body)
        return {'dataset': group['dataset'], 'version': group['version'], 'items': items}

    def values(self, out) -> dict:
        """{customer: the derived property's value} as the property stands now, worked out by the service's own code on the stored data."""
        conn = open_workspace(out / 'workspace.sqlite')
        try:
            result = evaluate(conn, json.loads(element_row(conn, DERIVED)['content_json']))
            table = current_dataset(conn, 'customers')['table_name']
            ids = dict(conn.execute(f'SELECT rowid, customer_id FROM "{table}"').fetchall())
            return {ids[i]: v for i, v in result['values'].items() if v is not None}
        finally:
            conn.close()

    def test_the_derived_property_is_asked_about_the_new_value_like_the_view_and_its_reason_says_so(self):
        with self.service() as (base, out):
            bob = self.pilot(base)['bob']
            group = self.group(bob)
            derived = next(i for i in group['items'] if i['element'] == DERIVED)
            view = next(i for i in group['items'] if i['kind'] == 'view')
            self.assertEqual(view['new_values'], [{'column': 'status_code', 'value': '6', 'label': '暂停', 'rows': NEW_ROWS}])
            self.assertEqual(derived['new_values'], view['new_values'])   # the same question the view gets
            self.assertIn('新值 6 算不算进来', derived['lines'][0]['text'])   # the reason it came back is the question, as for the view
            self.assertEqual(self.line(bob)['new_values'], view['new_values'])   # and on its own page

    def test_the_group_is_not_confirmed_while_the_derived_property_question_is_unanswered(self):
        with self.service() as (base, out):
            bob = self.pilot(base)['bob']
            before = {i['element']: i['state'] for i in bob.get('/api/workspace/queue')[1]['items']}
            status, body = bob.post('/api/workspace/queue/confirm-group', self.request(self.group(bob), answer_derived=False))
            self.assertEqual(status, 409, body)
            self.assertIn('有效订单金额', body['error'])
            self.assertIn('新值 6', body['error'])
            self.assertEqual({i['element']: i['state'] for i in bob.get('/api/workspace/queue')[1]['items']}, before)   # all or nothing
            self.assertEqual(self.values(out)['C024'], TRUTH['with']['C024'])   # (what it would read if confirmed as is: 4,755)

    def test_the_derived_property_alone_is_not_confirmed_without_the_answer(self):
        with self.service() as (base, out):
            bob = self.pilot(base)['bob']
            for item in self.group(bob)['items']:   # everything it stands on first, one at a time
                if item['element'] == DERIVED:
                    continue
                body = {'element': item['element'], 'version': item['version'], 'seen': item['seen'], **({'new_values': [{'column': n['column'], 'value': n['value'], 'choice': 'out'} for n in item['new_values']]} if item.get('new_values') else {})}
                self.assertEqual(bob.post('/api/workspace/queue/confirm', body)[0], 200, item['element'])
            line = self.line(bob)
            status, body = bob.post('/api/workspace/types/derived/confirm', {'type': 'customer', 'english_name': 'valid_amount', 'version': line['version'], 'seen': line['seen']})
            self.assertEqual(status, 409, body)
            self.assertIn('新值 6', body['error'])
            self.assertEqual(self.line(bob)['state'], 'needs_look')

    def test_leaving_the_new_value_out_adds_the_condition_and_the_other_builder_confirms_the_number_the_view_gives(self):
        with self.service() as (base, out):
            team = self.pilot(base)
            bob, ann = team['bob'], team['ann']
            status, body = bob.post('/api/workspace/queue/confirm-group', self.request(self.group(bob), choice='out'))
            self.assertEqual(status, 200, body)
            self.assertIn(DERIVED, [s['element'] for s in body['sent_on']])   # changed, so it is Bob's proposal now
            line = self.line(ann)
            self.assertEqual(line['definition']['conditions'], [*CONDITIONS, {'column': 'status_code', 'op': 'is_not', 'label': '暂停'}])
            status, body = ann.post('/api/workspace/types/derived/confirm', {'type': 'customer', 'english_name': 'valid_amount', 'version': line['version'], 'seen': line['seen']})
            self.assertEqual(status, 200, body)
            values = self.values(out)
            self.assertEqual(values['C024'], 3900)
            self.assertEqual(values, TRUTH['without'])
            self.assertEqual(sum(values.values()), 122200)

    def test_counting_the_new_value_in_is_a_choice_kept_with_the_confirmation(self):
        with self.service() as (base, out):
            bob = self.pilot(base)['bob']
            status, body = bob.post('/api/workspace/queue/confirm-group', self.request(self.group(bob), choice='in'))
            self.assertEqual(status, 200, body)
            self.assertIn(DERIVED, [c['element'] for c in body['confirmed']])
            self.assertEqual(self.values(out)['C024'], TRUTH['with']['C024'])
            conn = self.db(out)
            snapshot = json.loads(conn.execute('SELECT snapshot_json FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 1', (DERIVED,)).fetchone()[0])
            conn.close()
            self.assertEqual(snapshot['new_values'], [{'column': 'status_code', 'value': '6', 'label': '暂停', 'rows': NEW_ROWS, 'choice': 'in'}])
