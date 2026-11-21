"""The assistant's Meanings mode on the server: POST /api/workspace/types/meanings-draft drafts meanings for the code columns of one workspace object type with a fake
model gateway, and saves nothing. Counts come from the planted 订单 table (状态码 0/1/2 on 96/48/16 of 160 rows)."""
import base64
import json

from ontology_poc_generator.workspace_store import open_workspace
from tests.test_object_types import MEANINGS, ORDER, STOCK, Suggester, TABLES, shifted_orders_csv
from tests.test_two_person import SigningTestCase

COLUMN = 'code_meaning:订单.状态码'
DRAFT = {'columns': [{'id': COLUMN, 'values': [
    {'value': '0', 'basis': '数据里没看出规律', 'label': '已交付', 'description': ''},
    {'value': '1', 'basis': '数据里没看出规律', 'label': '生产中', 'description': ''},
    {'value': '7', 'basis': '编的', 'label': '不存在', 'description': ''}]}]}   # 7 is not a code of the column: dropped by the checks
URL = '/api/workspace/types/meanings-draft'
BARE = {**ORDER, 'enums': {}}


class MeaningsDraftTests(SigningTestCase):
    def team(self, base, *names, roles=None):
        team = self.people(base, *names, roles=roles)
        self.assertEqual(team[names[0]].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        return team

    def enum_rows(self, out):
        conn = open_workspace(out / 'workspace.sqlite')
        try:
            return conn.execute("SELECT COUNT(*) FROM element_state WHERE element_id LIKE 'enum:%'").fetchone()[0]
        finally:
            conn.close()

    def test_a_builder_gets_a_draft_per_code_column_with_checks_and_nothing_is_saved(self):
        model = Suggester(DRAFT)
        with self.service(gateway=model) as (base, out):
            ann = self.team(base, 'ann')['ann']
            self.assertEqual(ann.post('/api/workspace/types', BARE)[0], 200)
            status, body = ann.post(URL, {'id': 'order'})
            self.assertEqual(status, 200, body)
            self.assertEqual((body['type'], body['dataset'], len(model.asked)), ('order', '订单', 1))   # one call
            column = body['columns'][0]
            self.assertEqual((column['column'], column['confirmed'], column['rows']), ('状态码', False, 160))
            self.assertEqual([(v['value'], v['rows'], (v['draft'] or {}).get('label')) for v in column['values']], [('0', 96, '已交付'), ('1', 48, '生产中'), ('2', 16, None)])
            self.assertEqual(column['checks'], {'confirmed': False, 'no_meaning': ['2'], 'never_seen': []})   # 2 occurs with no meaning; 7 was dropped
            self.assertEqual([r['item'] for r in body['rejected']], [f'{COLUMN}=7'])
            self.assertEqual(self.enum_rows(out), 0)   # drafting saves nothing
            asked = json.loads(model.asked[0])
            self.assertNotIn('订单号', json.dumps(asked, ensure_ascii=False))   # the model sees counts and facts, no rows
            self.assertEqual([c['id'] for c in asked['columns']], [COLUMN])
            self.assertTrue(any(a['status'] == 'open' for a in body['assumptions']))
            self.assertIn('saved', [x['key'] for x in body['self_check']['not_done']])

    def test_only_the_types_own_code_columns_are_described_to_the_model(self):
        rows = ['工单号,状态,备注,内部批注'] + [f'T{i},{i % 3},{"" if i % 3 == 0 else "有"},{"" if i % 3 == 1 else "密"}' for i in range(60)]
        csv = {'filename': '工单.csv', 'content_base64': base64.b64encode('\n'.join(rows).encode('utf-8')).decode()}
        model = Suggester({'columns': []})
        with self.service(gateway=model) as (base, out):
            ann = self.people(base, 'ann')['ann']
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [csv]})[0], 200)
            ticket = {'english_name': 'ticket', 'name': '工单', 'dataset': '工单', 'key': ['工单号'], 'properties': [{'column': '工单号'}, {'column': '状态', 'enum': True}]}
            self.assertEqual(ann.post('/api/workspace/types', ticket)[0], 200)
            self.assertEqual(ann.post(URL, {'id': 'ticket'})[0], 200)
            asked = model.asked[0] if isinstance(model.asked[0], str) else json.dumps(model.asked[0], ensure_ascii=False)
            self.assertIn('状态', asked)
            for other in ('备注', '内部批注'):   # columns the type does not read: not their names, not their blanks
                self.assertNotIn(other, asked)

    def test_the_draft_applies_through_the_ordinary_meanings_path(self):
        with self.service(gateway=Suggester(DRAFT)) as (base, out):
            ann = self.team(base, 'ann')['ann']
            self.assertEqual(ann.post('/api/workspace/types', BARE)[0], 200)
            column = ann.post(URL, {'id': 'order'})[1]['columns'][0]
            values = [{'value': v['value'], 'label': v['draft']['label']} for v in column['values'] if v['draft']]
            status, body = ann.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': values})
            self.assertEqual((status, body), (200, {'changed': True}))
            self.assertEqual(self.enum_rows(out), 1)

    def test_confirmed_meanings_are_not_drafted_and_never_overwritten(self):
        model = Suggester(DRAFT)
        with self.service(gateway=model) as (base, out):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)
            detail = bob.get('/api/workspace/types/order')[1]
            shown = next(p for p in detail['properties'] if p['column'] == '状态码')['meanings']
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen'], 'column': '状态码'})[0], 200)
            status, body = ann.post(URL, {'id': 'order'})
            self.assertEqual(status, 200, body)
            self.assertEqual(model.asked, [])   # nothing left to ask the model about
            column = body['columns'][0]
            self.assertTrue(column['confirmed'])
            self.assertEqual([(v['value'], v['current'], v['draft']) for v in column['values']], [(m['value'], m['label'], None) for m in MEANINGS])
            self.assertEqual(body['assumptions'][0]['status'], 'confirmed')

    def test_codes_the_data_lost_or_gained_are_flagged_by_code(self):
        reply = {'columns': [{'id': COLUMN, 'values': [{'value': '1', 'basis': 'x', 'label': '已交付', 'description': ''}]}]}
        with self.service(gateway=Suggester(reply)) as (base, out):
            ann = self.team(base, 'ann')['ann']
            self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)   # meanings for 0, 1, 2
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)   # now the data has 1, 2, 3
            column = ann.post(URL, {'id': 'order'})[1]['columns'][0]
            self.assertFalse(column['confirmed'])
            self.assertEqual(column['checks'], {'confirmed': False, 'no_meaning': ['3'], 'never_seen': ['0']})
            self.assertEqual([(v['value'], v['current']) for v in column['values']], [('1', '生产中'), ('2', '已取消'), ('3', '')])

    def test_who_may_draft_and_what_is_refused(self):
        with self.service(gateway=Suggester(DRAFT)) as (base, out):
            team = self.team(base, 'ann', 'bob', 'vic', roles={'vic': 'viewer'})
            ann, bob, vic, admin = team['ann'], team['bob'], team['vic'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types', BARE)[0], 200)
            self.assertEqual(ann.post('/api/workspace/types', STOCK)[0], 200)
            self.assertEqual(vic.post(URL, {'id': 'order'})[0], 403)   # builders only
            self.assertEqual(ann.post(URL, {'id': 'nothing'})[0], 404)
            self.assertEqual(ann.post(URL, {'id': 'stock'})[0], 400)   # no code columns
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'order', 'column': '金额', 'visible_to': [ids['ann']]})[0], 200)
            status, body = bob.post(URL, {'id': 'order'})
            self.assertEqual(status, 403)   # a property bob cannot see: the same rule as writing the type
            self.assertIn('不让你看', body['error'])
            self.assertEqual(ann.post(URL, {'id': 'order'})[0], 200)

    def test_without_model_credentials_it_says_so_and_a_failed_model_is_a_502(self):
        with self.service() as (base, out):
            ann = self.team(base, 'ann')['ann']
            self.assertEqual(ann.post('/api/workspace/types', BARE)[0], 200)
            status, body = ann.post(URL, {'id': 'order'})
            self.assertEqual(status, 503)
            self.assertIn('模型凭据', body['error'])
        with self.service(gateway=Suggester(['not', 'columns'])) as (base, out):
            ann = self.team(base, 'ann')['ann']
            self.assertEqual(ann.post('/api/workspace/types', BARE)[0], 200)
            self.assertEqual(ann.post(URL, {'id': 'order'})[0], 502)


class MeaningsDraftHintTests(SigningTestCase):
    """What the person typed in the assistant's Meanings mode is sent with the draft request (the product audit of 2026-11-20 found only the id was sent, so the
    model knew no more than the type's name); a value the model was not sure of is dropped with that reason, not as "not a short piece of text"."""
    HINT = '这是电商订单的状态码：0 新建、1 已付款、2 已发货'

    def setup(self, base, reply):
        ann = self.people(base, 'ann')['ann']
        self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        self.assertEqual(ann.post('/api/workspace/types', BARE)[0], 200)
        return ann

    def test_the_words_the_person_typed_go_to_the_model_with_the_type(self):
        model = Suggester(DRAFT)
        with self.service(gateway=model) as (base, out):
            ann = self.setup(base, DRAFT)
            status, body = ann.post(URL, {'id': 'order', 'hint': self.HINT})
            self.assertEqual(status, 200, body)
            purpose = json.loads(model.asked[0])['purpose']
            self.assertIn(self.HINT, purpose)
            self.assertIn('订单', purpose.replace(self.HINT, ''))   # the type is still named
            self.assertEqual(ann.post(URL, {'id': 'order', 'hint': 'x' * 2001})[0], 400)   # a hint is a few lines, not a document

    def test_a_value_the_model_left_without_a_meaning_is_said_to_be_unsure_and_a_long_one_too_long(self):
        reply = {'columns': [{'id': COLUMN, 'values': [{'value': '0', 'basis': '没有事实', 'label': '', 'description': ''},
                                                      {'value': '1', 'basis': 'x', 'label': '很' * 41, 'description': ''}]}]}
        with self.service(gateway=Suggester(reply)) as (base, out):
            ann = self.setup(base, reply)
            status, body = ann.post(URL, {'id': 'order', 'hint': self.HINT})
            self.assertEqual(status, 200, body)
            reasons = {r['item']: r['reason'] for r in body['rejected']}
            self.assertIn('没把握', reasons[f'{COLUMN}=0'])
            self.assertIn('太长', reasons[f'{COLUMN}=1'])
            self.assertFalse(any('不是一段短文字' in r for r in reasons.values()))
