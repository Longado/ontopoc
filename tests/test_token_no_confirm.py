"""A token may not vouch for anything: on the team workspace, confirming a definition, approving a submitted change and recording a checked number need a signed-in person's session. A request that carries a token is refused,
whatever the token's scope, with a sentence that says a person does it on the page and where. Proposing, editing, sending back and the early screen are not touched."""
import ast
import base64
import importlib
import itertools
from pathlib import Path
import unittest
from unittest import mock

from ontology_poc_generator import access, demo
from ontology_poc_generator.object_types import TypeRefused
from ontology_poc_generator.workspace_store import open_workspace
from tests.test_access import Client, GateTestCase

try:
    import re._parser as regex_parser
    import re._constants as regex_codes
except ImportError:   # before 3.11
    import sre_parse as regex_parser
    import sre_constants as regex_codes

COVERED = ('/api/workspace/types/confirm', '/api/workspace/types/views/confirm', '/api/workspace/types/derived/confirm', '/api/workspace/relations/confirm',
           '/api/workspace/pipelines/confirm', '/api/workspace/actions/confirm', '/api/workspace/actions/decide', '/api/workspace/queue/confirm',
           '/api/workspace/queue/confirm-group', '/api/workspace/checked', '/api/workspace/needed/confirm', '/api/workspace/documents/confirm')
REFUSED_ZH = '确认和批准要由本人登录页面来做'
REFUSED_EN = 'Confirming and approving are done by a person signed in to the page'
CHECKED = '/api/workspace/checked'   # a checked number is recorded on a board card or a saved answer, not in the review queue: its own sentence
CHECKED_ZH = '核对过的数要由本人登录页面来记'
CHECKED_EN = 'A checked number is recorded by a person signed in to the page'
NEEDED = '/api/workspace/needed/confirm'   # an expected answer on the list of questions we need: its own sentence, which names the list
NEEDED_ZH = '要回答的问题由本人登录页面来写、确认和运行'
NEEDED_EN = 'Questions we need are written, confirmed and run by a person signed in to the page'


def refusal(path, english=False):
    """The start of the sentence a token is refused with on this route."""
    if path == CHECKED:
        return CHECKED_EN if english else CHECKED_ZH
    if path == NEEDED:
        return NEEDED_EN if english else NEEDED_ZH
    return REFUSED_EN if english else REFUSED_ZH


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
        """The finding: before tokens were kept from confirming, this token confirmed Order's meanings and Order itself, and the log said the builder did."""
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
                    self.assertEqual((status, refusal(path) in body['error']), (403, True), (path, body))
                    status, body = agent.post(path, {}, **bearer(token, english=True))
                    self.assertEqual((status, refusal(path, english=True) in body['error']), (403, True), (path, body))
                status, body = team['builder'].post(path, {})   # a session reaches the route's own checks: an empty body is refused there, not for the token
                self.assertNotIn(refusal(path), body.get('error', ''), path)
                self.assertFalse(body.get('needs_person'), path)

    def test_the_refusal_of_a_checked_number_says_where_a_person_records_one(self):
        with self.service() as (base, _):
            _, full, _ = self.workspace(base)
            agent = Client(base)
            status, body = agent.post(CHECKED, {}, **bearer(full))
            self.assertEqual(status, 403)
            self.assertTrue(body['needs_person'])
            self.assertIn('看板', body['error'])
            self.assertIn('核对过', body['error'])
            self.assertNotIn('待确认', body['error'])
            status, body = agent.post(CHECKED, {}, **bearer(full, english=True))
            self.assertIn('board card', body['error'])
            self.assertIn('Mark as checked', body['error'])
            self.assertNotIn('Review queue', body['error'])

    def test_a_token_of_any_scope_is_refused_even_one_nobody_has_made_yet(self):
        """The gate refuses a token, not a scope: a token whose scope is some new word (a future "propose", say) is refused the same way."""
        with self.service() as (base, out):
            team, full, _ = self.workspace(base)
            conn = open_workspace(out / 'workspace.sqlite')
            try:
                conn.execute("UPDATE api_token SET scope = 'propose' WHERE label = 'agent'")
                conn.commit()
            finally:
                conn.close()
            agent = Client(base)
            self.assertEqual(agent.get('/api/auth/me', **bearer(full))[1]['user']['token_scope'], 'propose')
            for path in COVERED:
                status, body = agent.post(path, {}, **bearer(full))
                self.assertEqual((status, body.get('needs_person'), refusal(path) in body.get('error', '')), (403, True, True), path)
            status, body = agent.post('/api/workspace/types', {}, **bearer(full))   # what such a token may otherwise do is not this rule's
            self.assertFalse(body.get('needs_person'))

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


PACKAGE = Path(access.__file__).parent
# where a person's name is written as the one who vouches: a confirmation of any definition, an approved change, a checked number, an expected answer confirmed
SINKS = {('object_types', 'write_confirmation'), ('object_actions', 'decide'), ('checked_numbers', 'record'), ('needed_questions', 'confirm')}
ROUTERS = {('ontology_server', 'make_server'), ('ontology_server', 'main'), ('demo', 'seed'), ('demo', 'main'), ('use_layer', 'post')}   # they reach everything: the server, the demo seed, the use layer's dispatch
ON_A_COPY = {'/api/workspace/impact': 'what confirming would do to the boards, worked out on a copy of the workspace that is thrown away (change_preview.impact)'}


def callers_of_sinks() -> set:
    """Every function of the package that can reach a sink, from the source: a call by name (defined in the module or imported, at the top or inside a function) or
    through a module (checked_numbers.record). Loose on purpose: a function counted that cannot really reach one costs a line in ROUTERS or ON_A_COPY, never a miss."""
    edges = {}
    for f in PACKAGE.glob('*.py'):
        module, tree = f.stem, ast.parse(f.read_text(encoding='utf-8'))
        names, modules = {}, {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == 'ontology_poc_generator':
                modules.update({a.asname or a.name: a.name for a in node.names})
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('ontology_poc_generator.'):
                names.update({a.asname or a.name: (node.module.split('.')[-1], a.name) for a in node.names})
            elif isinstance(node, ast.Import):
                modules.update({a.asname or a.name.split('.')[-1]: a.name.split('.')[-1] for a in node.names if a.name.startswith('ontology_poc_generator.')})
        defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
            calls = set()
            for node in ast.walk(fn):
                if isinstance(node, ast.Name):
                    calls |= {(module, node.id)} if node.id in defined else {names[node.id]} if node.id in names else set()
                elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in modules:
                    calls.add((modules[node.value.id], node.attr))
            edges[(module, fn.name)] = calls
    reach = set(SINKS)
    while True:
        more = {fn for fn, calls in edges.items() if fn not in reach and calls & reach}
        if not more:
            return reach
        reach |= more


def paths(pattern: str) -> list:
    """Every path a route pattern of the table matches, with one sample for a repeated or open part ([0-9]+, .+)."""
    def expand(items):
        parts = []
        for op, arg in items:
            if op == regex_codes.LITERAL:
                parts.append([chr(arg)])
            elif op == regex_codes.SUBPATTERN:
                parts.append(expand(arg[-1]))
            elif op == regex_codes.BRANCH:
                parts.append([p for alternative in arg[1] for p in expand(alternative)])
            elif op in (regex_codes.MAX_REPEAT, regex_codes.MIN_REPEAT):
                low, high, inner = arg
                parts.append(([''] if low == 0 else []) + expand(inner) if high == 1 else expand(inner))
            elif op == regex_codes.IN:
                parts.append([chr(a) for o, a in arg if o == regex_codes.LITERAL] if all(o == regex_codes.LITERAL for o, _ in arg) else ['1'])
            else:
                parts.append(['x'])
        return [''.join(p) for p in itertools.product(*parts)]
    return expand(regex_parser.parse(pattern))


class Reached(TypeRefused):
    """A refusal like any other, so each route answers it as a 400 and the service goes on."""


class EveryVouchingWriteIsPersonOnlyTests(GateTestCase):
    def test_every_route_that_reaches_a_confirmation_an_approval_or_a_checked_number_is_in_the_list(self):
        """Ties PERSON_ONLY_POSTS to the code, not to a copy of it: each function that can write a person's name as the one who vouches is replaced by one that
        notes the route it was called from, and every POST of the team workspace is called by a signed-in admin with an empty body. Taking a route out of the list
        (and out of COVERED) fails here, and so does a new route that confirms."""
        reach = callers_of_sinks() - ROUTERS
        self.assertTrue(SINKS <= reach)
        self.assertGreaterEqual(len(reach), 10)
        hit, calling = set(), []
        def stand_in(*args, **kwargs):
            hit.add(calling[-1])
            raise Reached('reached')
        patches = []
        for module, name in reach:
            original = getattr(importlib.import_module(f'ontology_poc_generator.{module}'), name)
            for loaded in [importlib.import_module(f'ontology_poc_generator.{f.stem}') for f in PACKAGE.glob('*.py') if f.stem != '__main__']:
                for attr, value in list(vars(loaded).items()):
                    if value is original:
                        patches.append(mock.patch.object(loaded, attr, stand_in))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        candidates = sorted({p for method, pattern, _ in access.ROUTES if method == 'POST' and pattern.startswith('/api/workspace/') for p in paths(pattern)})
        self.assertIn('/api/workspace/types/derived/confirm', candidates)
        self.assertGreater(len(candidates), 60)
        with self.service() as (base, _):
            admin = Client(base)
            self.assertEqual(admin.login('root')[0], 200)
            for path in candidates:
                calling.append(path)
                try:
                    admin.post(path, {})
                except OSError:   # a route that does not answer a ValueError as a 400 dropped the connection; what it reached is noted all the same
                    pass
        self.assertEqual(hit - set(ON_A_COPY), set(access.PERSON_ONLY_POSTS))
        self.assertEqual(hit & set(ON_A_COPY), set(ON_A_COPY))   # still on a copy: if impact stops reaching a writer, this line goes


if __name__ == '__main__':
    unittest.main()
