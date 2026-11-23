"""An edit made with a token to a confirmed definition: what stays confirmed, and what the log says.

The rule: any edit made with a token to a confirmed definition sends it back to waiting for confirmation, as an edit that changes what it means does. A signed-in
person's edit of the name or the description now takes the same path (tests/test_changed_since_confirm.py); a pipeline keeps its own rule, and a signed-in edit of
its description alone keeps it confirmed. Every log line of a write made with a token says so, with the token's label."""
import sqlite3
from urllib.parse import quote

from tests.test_derived_properties import CANCELLED, ORDER, RELATIONS, DerivedTestCase
from tests.test_object_relations import CUSTOMER
from tests.test_object_types import VALID
from tests.test_notices import ACTION

PIPELINES = '/api/workspace/pipelines'
ELEMENTS = {'type': 'objtype:customer', 'meanings': 'enum:order:状态码', 'view': 'objview:有效订单', 'derived': 'derived:customer:cancelled_orders',
            'relation': 'relation:order_customer', 'pipeline': 'pipeline:客户合计', 'action': 'objaction:改交付天数'}


def bearer(token):
    return {'headers': {'Authorization': f'Bearer {token}'}, 'origin': None}


class World(DerivedTestCase):
    def world(self, team):
        """Every kind of definition, put forward by Ann and confirmed by Bob: Customer and Order with its meanings, the relation order_customer, the view 有效订单,
        the derived property 已取消订单数, the action 改交付天数 and the pipeline 客户合计."""
        from tests.test_pipeline_server import SPEC
        self.foundation(team, types=(ORDER, CUSTOMER), relations=[r for r in RELATIONS if r['english_name'] == 'order_customer'])
        ann, bob = team['ann'], team['bob']
        self.assertEqual(ann.post('/api/workspace/types/views', VALID)[0], 200)
        shown = bob.get('/api/workspace/types/order/views')[1]['views'][0]
        self.assertEqual(bob.post('/api/workspace/types/views/confirm', {'id': VALID['name'], 'version': shown['version'], 'seen': shown['seen']})[0], 200)
        self.assertEqual(ann.post('/api/workspace/types/derived', CANCELLED)[0], 200)
        self.assertEqual(self.confirm(bob, CANCELLED)[0], 200)
        self.assertEqual(ann.post('/api/workspace/actions', ACTION)[0], 200)
        shown = bob.get('/api/workspace/actions/' + quote(ACTION['name']))[1]
        self.assertEqual(bob.post('/api/workspace/actions/confirm', {'id': ACTION['name'], 'version': shown['version']})[0], 200)
        self.assertEqual(ann.post(PIPELINES, {'name': '客户合计', 'description': '每个客户的订单金额合计', 'spec': SPEC})[0], 200)
        status, body = ann.post(f'{PIPELINES}/run', {'id': '客户合计'})
        self.assertEqual((status, body.get('status')), (200, 'success'), body)
        shown = bob.get(f'{PIPELINES}/{quote("客户合计")}')[1]
        status, body = bob.post(f'{PIPELINES}/confirm', {'id': '客户合计', 'version': shown['version'], 'seen': {'inputs': shown['inputs_now']}})
        self.assertEqual(status, 200, body)
        self.assertEqual(set(self.states_now().values()), {'confirmed'}, self.states_now())

    def states_now(self):
        conn = sqlite3.connect(self.out / 'workspace.sqlite')
        try:
            return {kind: conn.execute('SELECT state FROM element_state WHERE element_id = ?', (e,)).fetchone()[0] for kind, e in ELEMENTS.items()}
        finally:
            conn.close()

    def edit(self, client, kind, field, value, **more):
        """One edit of one field of a confirmed definition, as the page sends it: the definition as it stands with that field changed."""
        if kind == 'type':
            now = client.get('/api/workspace/types/customer')[1]
            return client.post('/api/workspace/types/update', {**CUSTOMER, 'id': 'customer', 'version': now['version'], 'name': now['name'], 'description': now.get('description') or '', field: value}, **more)
        if kind == 'meanings':
            return client.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': [{'value': '2', 'label': value}]}, **more)
        if kind == 'view':
            now = next(v for v in client.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == VALID['name'])
            return client.post('/api/workspace/types/views/update', {**VALID, 'id': VALID['name'], 'version': now['version'], field: value}, **more)
        if kind == 'derived':
            now = self.line(client, 'customer', 'cancelled_orders')
            return client.post('/api/workspace/types/derived/update', {**CANCELLED, 'version': now['version'], field: value}, **more)
        if kind == 'relation':
            r = next(r for r in RELATIONS if r['english_name'] == 'order_customer')
            now = client.get('/api/workspace/relations/order_customer')[1]
            return client.post('/api/workspace/relations/update', {**r, 'id': 'order_customer', 'version': now['version'], field: value}, **more)
        if kind == 'pipeline':
            now = client.get(f'{PIPELINES}/{quote("客户合计")}')[1]
            return client.post(f'{PIPELINES}/update', {'id': '客户合计', 'version': now['version'], field: value}, **more)
        now = client.get('/api/workspace/actions/' + quote(ACTION['name']))[1]
        return client.post('/api/workspace/actions/update', {**ACTION, 'id': ACTION['name'], 'version': now['version'], field: value}, **more)


# (kind, field) for every edit of a confirmed definition that does not change what it means: the name where a definition has one apart from its id, the description
NAME_AND_DESCRIPTION = [('type', 'name'), ('type', 'description'), ('view', 'description'), ('derived', 'name'), ('derived', 'description'),
                        ('relation', 'name'), ('relation', 'description'), ('pipeline', 'description'), ('action', 'description')]


class FactsTests(World):
    def facts(self, by_token):
        """{(kind, field): the state after the edit} for each edit in NAME_AND_DESCRIPTION, and for a new label of one meaning, each on a freshly confirmed world."""
        out = {}
        for n, (kind, field) in enumerate([*NAME_AND_DESCRIPTION, ('meanings', 'label')]):
            with self.service() as (base, out_dir):
                self.out = out_dir
                team = self.team(base)
                self.world(team)
                ann = team['ann']
                more = bearer(ann.post('/api/auth/tokens', {'label': 'agent'})[1]['token']) if by_token else {}
                status, body = self.edit(ann, kind, field, f'换了的说法 {n}', **more)
                self.assertEqual(status, 200, (kind, field, body))
                out[(kind, field)] = self.states_now()[kind]
        return out

    def test_a_signed_in_persons_edit_of_the_name_or_description_sends_it_back_as_a_tokens_does_except_a_pipelines(self):
        facts = self.facts(by_token=False)
        self.assertEqual(facts, {**{k: 'checked' for k in NAME_AND_DESCRIPTION if k[0] != 'pipeline'}, ('pipeline', 'description'): 'confirmed', ('meanings', 'label'): 'checked'})

    def test_any_edit_made_with_a_token_sends_a_confirmed_definition_back(self):
        self.assertEqual(self.facts(by_token=True), {**{k: 'checked' for k in NAME_AND_DESCRIPTION}, ('meanings', 'label'): 'checked'})


class TokenWriteInTheLogTests(World):
    def test_a_write_made_with_a_token_says_so_in_the_log_and_in_the_standing_and_a_persons_does_not(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            ann = team['ann']
            token = bearer(ann.post('/api/auth/tokens', {'label': 'support agent'})[1]['token'])
            self.assertEqual(self.edit(ann, 'type', 'description', '一位同事改的')[0], 200)
            shown = team['bob'].get('/api/workspace/types/customer')[1]   # a person's edit waits for a second person too: Bob confirms it
            self.assertEqual(team['bob'].post('/api/workspace/types/confirm', {'id': 'customer', 'version': shown['version'], 'seen': shown['seen']})[0], 200)
            before = ann.get('/api/workspace/types/customer/log')[1]['log']
            self.assertTrue(before)
            self.assertTrue(all(e['with_token'] is None for e in before), before)
            status, body = self.edit(ann, 'type', 'name', '智能体起的名字', **token)
            self.assertEqual(status, 200, body)
            log = ann.get('/api/workspace/types/customer/log')[1]['log']
            new = log[:len(log) - len(before)]
            self.assertTrue(new)
            self.assertEqual({e['with_token'] for e in new}, {'support agent'}, new)
            self.assertTrue(all(e['with_token'] is None for e in log[len(new):]))
            standing = ann.get('/api/workspace/agent/standing?id=objtype%3Acustomer')[1]
            self.assertEqual((standing['state'], standing['proposed_by'], standing['proposed_with_token']), ('checked', 'Ann', 'support agent'), standing)
            self.assertNotIn('智能体起的名字', [d['name'] for d in ann.get('/api/workspace/agent/definitions', **token)[1]['types']])

    def test_a_persons_own_proposal_in_the_standing_names_no_token(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            ann = team['ann']
            self.assertEqual(self.edit(ann, 'meanings', 'label', '取消了')[0], 200)
            standing = ann.get('/api/workspace/agent/standing?id=' + quote('enum:order:状态码', safe=''))[1]
            self.assertEqual((standing['state'], standing['proposed_by'], standing['proposed_with_token']), ('checked', 'Ann', None), standing)

    def test_an_upload_made_with_a_token_is_logged_as_made_with_it(self):
        from tests.test_access import table_part
        with self.service() as (base, out):
            team = self.people(base, 'ann')
            ann = team['ann']
            token = bearer(ann.post('/api/auth/tokens', {'label': 'nightly script'})[1]['token'])
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [table_part('a.csv')]})[0], 200)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [table_part('b.csv')]}, **token)[0], 200)
            conn = sqlite3.connect(out / 'workspace.sqlite')
            try:
                marks = dict(conn.execute("SELECT element_id, via_token FROM log WHERE element_id IN ('dataset:a', 'dataset:b')").fetchall())
            finally:
                conn.close()
            self.assertEqual(marks, {'dataset:a': None, 'dataset:b': 'nightly script'})
