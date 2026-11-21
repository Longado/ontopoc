"""D17: on the team workspace, confirming a definition and approving a submitted action need a signed-in person's session. A request that carries a token is refused,
whatever the token's scope, with a sentence that says a person confirms on the page and where. Proposing, editing, sending back and the early screen are not touched."""
import base64
import unittest

from ontology_poc_generator import demo
from tests.test_access import Client, GateTestCase

COVERED = ('/api/workspace/types/confirm', '/api/workspace/types/views/confirm', '/api/workspace/types/derived/confirm', '/api/workspace/relations/confirm',
           '/api/workspace/pipelines/confirm', '/api/workspace/actions/confirm', '/api/workspace/actions/decide', '/api/workspace/queue/confirm',
           '/api/workspace/queue/confirm-group')
REFUSED_ZH = '确认和批准要由本人登录页面来做'
REFUSED_EN = 'Confirming and approving are done by a person signed in to the page'


def part(name):
    return {'filename': name, 'content_base64': base64.b64encode((demo.sample_dir() / name).read_bytes()).decode()}


def bearer(token, english=False):
    headers = {'Authorization': f'Bearer {token}'}
    if english:
        headers['Accept-Language'] = 'en'
    return {'headers': headers, 'origin': None}


class TokenMayNotConfirmTests(GateTestCase):
    def workspace(self, base):
        """root (an admin) uploads orders and proposes Order with its status meanings; the builder has a token of scope all and one of scope read."""
        team = self.team(base)
        admin = team['admin']
        self.assertEqual(admin.post('/api/workspace/datasets/upload', {'files': [part('orders.csv')]})[0], 200)
        meanings = [{'value': v, 'label': l} for v, l in (('0', 'New'), ('1', 'Paid'), ('2', 'Shipped'), ('3', 'Delivered'), ('4', 'Cancelled'), ('5', 'Refunded'))]
        status, body = admin.post('/api/workspace/types', {'english_name': 'order', 'name': 'Order', 'dataset': 'orders', 'key': ['order_id'],
                                                           'properties': [{'column': c} for c in ('order_id', 'customer_id', 'order_date', 'amount')] + [{'column': 'status_code', 'enum': True}],
                                                           'enums': {'status_code': meanings}})
        self.assertEqual(status, 200, body)
        full = team['builder'].post('/api/auth/tokens', {'label': 'agent', 'scope': 'all'})[1]['token']
        read = team['builder'].post('/api/auth/tokens', {'label': 'reader', 'scope': 'read'})[1]['token']
        return team, full, read

    def confirm_body(self, client, column=None):
        t = client.get('/api/workspace/types/order')[1]
        node = next(p for p in t['properties'] if p['column'] == column)['meanings'] if column else t
        return {'id': 'order', 'version': node['version'], 'seen': node['seen'], **({'column': column} if column else {})}

    def test_a_full_scope_token_of_another_builder_cannot_confirm_what_the_admin_proposed(self):
        """The finding: before D17 this token confirmed Order's meanings and Order itself, and the log said the builder did."""
        with self.service() as (base, _):
            team, full, _ = self.workspace(base)
            agent, builder = Client(base), team['builder']
            for column in ('status_code', None):
                status, body = agent.post('/api/workspace/types/confirm', self.confirm_body(builder, column), **bearer(full))
                self.assertEqual(status, 403, body)
                self.assertIn(REFUSED_ZH, body['error'])
                self.assertTrue(body.get('needs_person'))
            self.assertEqual(builder.get('/api/workspace/types/order')[1]['state'], 'checked')   # checked by code, waiting for a person
            for column in ('status_code', None):   # the same person, signed in on the page, still confirms
                status, body = builder.post('/api/workspace/types/confirm', self.confirm_body(builder, column))
                self.assertEqual(status, 200, body)
            self.assertEqual(builder.get('/api/workspace/types/order')[1]['state'], 'confirmed')

    def test_a_view_is_proposed_by_token_and_confirmed_only_by_a_session(self):
        with self.service() as (base, _):
            team, full, _ = self.workspace(base)
            builder, admin, agent = team['builder'], team['admin'], Client(base)
            for column in ('status_code', None):
                self.assertEqual(builder.post('/api/workspace/types/confirm', self.confirm_body(builder, column))[0], 200)
            admin_token = admin.post('/api/auth/tokens', {'label': 'admin agent'})[1]['token']
            status, body = agent.post('/api/workspace/types/views', {'name': 'Valid orders', 'type': 'order',
                                                                     'filters': [{'column': 'status_code', 'op': 'is_not', 'label': 'Cancelled'}]}, **bearer(admin_token))
            self.assertEqual(status, 200, body)   # proposing by token stays
            view = next(v for v in builder.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == 'Valid orders')
            confirm = {'id': 'Valid orders', 'version': view['version'], 'seen': view['seen']}
            status, body = agent.post('/api/workspace/types/views/confirm', confirm, **bearer(full, english=True))
            self.assertEqual(status, 403, body)
            self.assertIn(REFUSED_EN, body['error'])
            self.assertIn('Review queue', body['error'])
            self.assertEqual(builder.post('/api/workspace/types/views/confirm', confirm)[0], 200)

    def test_every_covered_route_is_refused_to_a_full_token_of_any_role_and_left_to_a_session(self):
        with self.service() as (base, _):
            team, full, _ = self.workspace(base)
            admin_token = team['admin'].post('/api/auth/tokens', {'label': 'admin agent'})[1]['token']
            agent = Client(base)
            for path in COVERED:
                for token in (full, admin_token):
                    status, body = agent.post(path, {}, **bearer(token))
                    self.assertEqual((status, REFUSED_ZH in body['error']), (403, True), (path, body))
                    status, body = agent.post(path, {}, **bearer(token, english=True))
                    self.assertEqual((status, REFUSED_EN in body['error']), (403, True), (path, body))
                status, body = team['builder'].post(path, {})   # a session reaches the route's own checks: an empty body is refused there, not for the token
                self.assertNotIn(REFUSED_ZH, body.get('error', ''), path)
                self.assertFalse(body.get('needs_person'), path)

    def test_proposing_editing_and_sending_back_by_token_are_not_refused_for_the_token(self):
        with self.service() as (base, _):
            _, full, _ = self.workspace(base)
            agent = Client(base)
            for path in ('/api/workspace/types', '/api/workspace/types/update', '/api/workspace/types/meanings', '/api/workspace/types/views', '/api/workspace/relations',
                         '/api/workspace/relations/update', '/api/workspace/queue/send-back', '/api/workspace/pipelines', '/api/workspace/actions', '/api/workspace/actions/submit',
                         '/api/workspace/actions/withdraw', '/api/workspace/actions/undo'):
                status, body = agent.post(path, {}, **bearer(full))
                self.assertFalse(body.get('needs_person'), path)
                self.assertNotIn(REFUSED_ZH, body.get('error', ''), path)

    def test_the_early_screen_is_unchanged_for_a_token(self):
        with self.service() as (base, _):
            _, full, _ = self.workspace(base)
            agent = Client(base)
            for path in ('/api/ontology/confirm', '/api/ontology/views', '/api/ontology/derived', '/api/ontology/review/confirm', '/api/ontology/bulk-approve', '/api/ontology/reference/confirm'):
                status, body = agent.post(path, {}, **bearer(full))
                self.assertFalse(body.get('needs_person'), path)
                self.assertNotIn(REFUSED_ZH, body.get('error', ''), path)

    def test_a_read_token_gets_the_refusal_it_always_got(self):
        with self.service() as (base, _):
            _, _, read = self.workspace(base)
            agent = Client(base)
            for path in COVERED:
                status, body = agent.post(path, {}, **bearer(read))
                self.assertEqual(status, 403, path)
                self.assertIn('这个令牌只能读和提问', body['error'])
            self.assertEqual(agent.get('/api/workspace/types/order', **bearer(read))[0], 200)

    def test_the_refusal_says_nothing_about_whether_the_definition_exists_or_may_be_seen(self):
        with self.service() as (base, _):
            team, full, _ = self.workspace(base)
            admin, agent = team['admin'], Client(base)
            me = admin.get('/api/auth/me')[1]['user']['id']
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': [me]})[0], 200)   # the builder may no longer see Order
            answers = [agent.post('/api/workspace/types/confirm', {'id': name, 'version': 1, 'seen': 'x'}, **bearer(full)) for name in ('order', 'no_such_type')]
            self.assertEqual(answers[0], answers[1])
            self.assertEqual(answers[0][0], 403)
            self.assertNotIn('order', answers[0][1]['error'].lower())


class PersonOnlyListTests(unittest.TestCase):
    def test_one_list_names_the_acts_and_none_of_them_is_on_the_early_screen(self):
        from ontology_poc_generator.access import PERSON_ONLY_POSTS, required_role, token_allows
        self.assertEqual(sorted(PERSON_ONLY_POSTS), sorted(COVERED))
        for path in PERSON_ONLY_POSTS:
            self.assertFalse(token_allows('POST', path), path)
            self.assertTrue(token_allows('GET', path), path)
            self.assertEqual(required_role('POST', path), 'builder', path)   # each is a real route of the table, for builders
        for path in ('/api/workspace/queue/send-back', '/api/workspace/types', '/api/ontology/confirm', '/api/ontology/views'):
            self.assertTrue(token_allows('POST', path), path)


if __name__ == '__main__':
    unittest.main()
