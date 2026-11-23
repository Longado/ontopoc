"""Whoever changed a definition since it was last confirmed cannot confirm it (D19 and the two-person hole), walked through the real service.

Ann proposes, Bob confirms, Cat is a third builder, Vera only reads. The rule, for every definition kind that has confirmation (object types with their
properties, other names and value rules; the meanings of a code column; views; derived properties; relations; actions; and the expectations of the questions
we need): each keeps the set of people who changed what it says since it was last confirmed (or since it was put forward). Nobody in that set may confirm it;
confirming empties it; nothing another person does takes a name out of it. The only ways out: what it says is again exactly what was last confirmed (the set
empties and, when nothing else sent it back, it is confirmed as before), or a person outside the set confirms. Any change of what a confirmed definition says
by a person signed in sends it back, names and descriptions included, by the path a token's edit already takes, and the person who last confirmed it is no
exception. Pipelines keep their own rule (whoever saved its steps since the last confirmation) and are not changed here.

The three ways the earlier attempt (authorship per field and per list item) could be cleared each have a test here: another field of the same property; two
conditions swapped; the same words typed again by another person."""
import base64
import csv
import io
import sqlite3
from urllib.parse import quote
from urllib.request import Request, urlopen

from tests.test_derived_properties import CANCELLED
from tests.test_needed_questions import NEEDED, NeededCase, number
from tests.test_object_relations import CUSTOMER, customers_mended, table_csv
from tests.test_object_types import TABLES, VALID
from tests.test_notices import ACTION
from tests.test_token_edit_trust import ELEMENTS, World, bearer
from tests.test_derived_properties import RELATIONS

QUEUE_CONFIRM = '/api/workspace/queue/confirm'
ORDER_CUSTOMER = next(r for r in RELATIONS if r['english_name'] == 'order_customer')
KINDS = ('action', 'derived', 'view', 'relation', 'meanings', 'type')   # leaves first: an edit of one moves what stands on it, never what comes before here
HELD_ZH, HELD_EN = '确认之后改过它', 'changed it since'


def text(client, path):
    """(status, the body as text) of a GET that answers a file, not JSON, as this person."""
    with urlopen(Request(client.base + path, headers={'Cookie': f'{client.cookie_name}={client.cookie}'}), timeout=30) as response:
        return response.status, response.read().decode()


def csv_rows(part):
    return list(csv.DictReader(io.StringIO(base64.b64decode(part['content_base64']).decode())))


def customer_properties(**changed):
    """The customer type's properties as the fixture writes them, with these fields set on the named columns ({column: {field: value}})."""
    return [{**p, **changed.get(p['column'], {})} for p in CUSTOMER['properties']]


class Team(World):
    maxDiff = None

    def team(self, base):
        """root, three builders (Ann, Bob, Cat) and a viewer, with the planted tables uploaded by Ann."""
        team = self.people(base, 'ann', 'bob', 'cat', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
        return team

    def db(self, sql, args=()):
        conn = sqlite3.connect(self.out / 'workspace.sqlite')
        try:
            found = conn.execute(sql, args).fetchall()
            conn.commit()
            return found
        finally:
            conn.close()

    def state_of(self, kind):
        return self.db('SELECT state FROM element_state WHERE element_id = ?', (ELEMENTS[kind],))[0][0]

    def put(self, client, kind, fields, **more):
        """Save the definition of `kind` as the fixture wrote it with `fields` set, at the version the client reads now (meanings: `fields` is the list of values)."""
        if kind == 'type':
            now = client.get('/api/workspace/types/customer')[1]
            return client.post('/api/workspace/types/update', {**CUSTOMER, 'id': 'customer', 'version': now['version'], 'name': '客户', 'description': '', **fields}, **more)
        if kind == 'meanings':
            return client.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': fields}, **more)
        if kind == 'view':
            now = next(v for v in client.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == VALID['name'])
            return client.post('/api/workspace/types/views/update', {**VALID, 'id': VALID['name'], 'version': now['version'], 'description': '', **fields}, **more)
        if kind == 'derived':
            now = self.line(client, 'customer', 'cancelled_orders')
            return client.post('/api/workspace/types/derived/update', {**CANCELLED, 'version': now['version'], 'description': '', **fields}, **more)
        if kind == 'relation':
            now = client.get('/api/workspace/relations/order_customer')[1]
            return client.post('/api/workspace/relations/update', {**ORDER_CUSTOMER, 'id': 'order_customer', 'version': now['version'], 'description': '', **fields}, **more)
        now = client.get('/api/workspace/actions/' + quote(ACTION['name']))[1]
        return client.post('/api/workspace/actions/update', {**ACTION, 'id': ACTION['name'], 'version': now['version'], **fields}, **more)

    def confirm_bodies(self, client, kind):
        """(the kind's own confirm route, the body it takes, the review queue's body) for what `client` reads of the definition now."""
        element = ELEMENTS[kind]
        if kind in ('type', 'meanings'):
            shown = client.get('/api/workspace/types/' + ('customer' if kind == 'type' else 'order'))[1]
            if kind == 'meanings':
                shown = next(p for p in shown['properties'] if p['column'] == '状态码')['meanings']
            own = {'id': 'customer' if kind == 'type' else 'order', 'version': shown['version'], 'seen': shown['seen'], **({'column': '状态码'} if kind == 'meanings' else {})}
            return '/api/workspace/types/confirm', own, {'element': element, 'version': shown['version'], 'seen': shown['seen']}
        if kind == 'view':
            shown = next(v for v in client.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == VALID['name'])
            return '/api/workspace/types/views/confirm', {'id': VALID['name'], 'version': shown['version'], 'seen': shown['seen']}, {'element': element, 'version': shown['version'], 'seen': shown['seen']}
        if kind == 'derived':
            shown = self.line(client, 'customer', 'cancelled_orders')
            return ('/api/workspace/types/derived/confirm', {'type': 'customer', 'english_name': 'cancelled_orders', 'version': shown['version'], 'seen': shown['seen']},
                    {'element': element, 'version': shown['version'], 'seen': shown['seen']})
        if kind == 'relation':
            shown = client.get('/api/workspace/relations/order_customer')[1]
            seen = shown['check']['signature']
            return '/api/workspace/relations/confirm', {'id': 'order_customer', 'version': shown['version'], 'seen': seen}, {'element': element, 'version': shown['version'], 'seen': seen}
        shown = client.get('/api/workspace/actions/' + quote(ACTION['name']))[1]
        return '/api/workspace/actions/confirm', {'id': ACTION['name'], 'version': shown['version']}, {'element': element, 'version': shown['version']}

    def confirm_kind(self, client, kind, **more):
        path, own, _ = self.confirm_bodies(client, kind)
        return client.post(path, own, **more)

    def queue_confirm(self, client, kind):
        return client.post(QUEUE_CONFIRM, self.confirm_bodies(client, kind)[2])

    def detail(self, client, kind):
        """What the definition's own page reads of it (the line that says who may confirm it)."""
        if kind in ('type', 'meanings'):
            shown = client.get('/api/workspace/types/' + ('customer' if kind == 'type' else 'order'))[1]
            return next(p for p in shown['properties'] if p['column'] == '状态码')['meanings'] if kind == 'meanings' else shown
        if kind == 'view':
            return next(v for v in client.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == VALID['name'])
        if kind == 'derived':
            return self.line(client, 'customer', 'cancelled_orders')
        if kind == 'relation':
            return client.get('/api/workspace/relations/order_customer')[1]
        return client.get('/api/workspace/actions/' + quote(ACTION['name']))[1]

    def two_edits(self, cases, by_token=False):
        """On the world Ann proposed and Bob confirmed: for each kind, Ann's edits, then Cat's (each a list of the fields saved in turn); then who may confirm it.
        {kind: {who: status}}, with Bob's confirmation last so the next kind starts from a confirmed world."""
        facts = {}
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            tokens = {who: bearer(team[who].post('/api/auth/tokens', {'label': f'{who} agent'})[1]['token']) for who in ('ann', 'cat')} if by_token else {}
            for kind in KINDS:
                if kind not in cases:
                    continue
                for who, edits in zip(('ann', 'cat'), cases[kind]):
                    for fields in edits:
                        status, body = self.put(team[who], kind, fields, **tokens.get(who, {}))
                        self.assertEqual(status, 200, (kind, who, fields, body))
                facts[kind] = {'ann': self.confirm_kind(team['ann'], kind)[0], 'cat': self.confirm_kind(team['cat'], kind)[0],
                               'ann_queue': self.queue_confirm(team['ann'], kind)[0], 'cat_queue': self.queue_confirm(team['cat'], kind)[0]}
                facts[kind]['bob'] = self.confirm_kind(team['bob'], kind)[0]
        return facts


BARRED = {'ann': 403, 'cat': 403, 'ann_queue': 403, 'cat_queue': 403, 'bob': 200}

# trick 1: Ann changes one field, Cat another field of the same item (a property, a meaning) or of the same definition, keeping Ann's
ANOTHER_FIELD = {
    'type': ([{'properties': customer_properties(客户名称={'name': 'ZZ安的名称'})}], [{'properties': customer_properties(客户名称={'name': 'ZZ安的名称', 'other_names': ['ZZ卡的别称']})}]),
    'meanings': ([[{'value': '1', 'label': 'ZZ安的含义'}]], [[{'value': '1', 'label': 'ZZ安的含义', 'description': 'ZZ卡的说明'}]]),
    'view': ([{'description': 'ZZ安的说明'}], [{'description': 'ZZ安的说明', 'other_names': ['ZZ卡的视图别称']}]),
    'derived': ([{'name': 'ZZ安的派生名'}], [{'name': 'ZZ安的派生名', 'description': 'ZZ卡的说明'}]),
    'relation': ([{'name': 'ZZ安的关系名'}], [{'name': 'ZZ安的关系名', 'description': 'ZZ卡的说明'}]),
    'action': ([{'description': 'ZZ安的说明'}], [{'description': 'ZZ安的说明', 'properties': ['交付天数', '数量']}]),
}
KEEP, ANN_RULE = VALID['filters'][0], {'column': '状态码', 'op': 'is_not', 'label': '生产中'}
BIG, MANY = {'column': '金额', 'op': 'gt', 'value': '100'}, {'column': '数量', 'op': 'gt', 'value': '1'}
# trick 2: Ann adds a condition, Cat swaps the two conditions
SWAPPED = {
    'view': ([{'filters': [KEEP, ANN_RULE]}], [{'filters': [ANN_RULE, KEEP]}]),
    'derived': ([{'conditions': [CANCELLED['conditions'][0], ANN_RULE]}], [{'conditions': [ANN_RULE, CANCELLED['conditions'][0]]}]),
    'action': ([{'conditions': [BIG, MANY]}], [{'conditions': [MANY, BIG]}]),
}
# trick 3: Ann writes her words, Cat writes his own and then Ann's again
RETYPED = {
    'type': ([{'description': 'ZZ安写的'}], [{'description': 'ZZ卡写的'}, {'description': 'ZZ安写的'}]),
    'meanings': ([[{'value': '1', 'label': 'ZZ安写的'}]], [[{'value': '1', 'label': 'ZZ卡写的'}], [{'value': '1', 'label': 'ZZ安写的'}]]),
    'view': ([{'description': 'ZZ安写的'}], [{'description': 'ZZ卡写的'}, {'description': 'ZZ安写的'}]),
    'derived': ([{'name': 'ZZ安写的'}], [{'name': 'ZZ卡写的'}, {'name': 'ZZ安写的'}]),
    'relation': ([{'name': 'ZZ安写的'}], [{'name': 'ZZ卡写的'}, {'name': 'ZZ安写的'}]),
    'action': ([{'description': 'ZZ安写的'}], [{'description': 'ZZ卡写的'}, {'description': 'ZZ安写的'}]),
}
# other names and value rules are part of a type: Ann adds one, Cat another
OTHER_NAMES_AND_RULES = {
    'type': ([{'other_names': ['ZZ安的类型别称'], 'rules': [{'column': '客户编号', 'check': 'not_empty'}]}],
             [{'other_names': ['ZZ安的类型别称', 'ZZ卡的类型别称'], 'rules': [{'column': '客户编号', 'check': 'not_empty'}, {'column': '城市', 'check': 'not_empty'}]}]),
}


class ClearingTrickTests(Team):
    def test_another_field_of_the_same_property_or_definition_does_not_free_the_first_writer(self):
        self.assertEqual(self.two_edits(ANOTHER_FIELD), {kind: BARRED for kind in ANOTHER_FIELD})

    def test_swapping_two_conditions_does_not_free_the_one_who_added_one(self):
        self.assertEqual(self.two_edits(SWAPPED), {kind: BARRED for kind in SWAPPED})

    def test_another_person_typing_the_same_words_again_does_not_free_their_writer(self):
        self.assertEqual(self.two_edits(RETYPED), {kind: BARRED for kind in RETYPED})

    def test_other_names_and_value_rules_hold_whoever_changed_them(self):
        self.assertEqual(self.two_edits(OTHER_NAMES_AND_RULES), {'type': BARRED})

    def test_with_tokens_the_tokens_owners_are_held_the_same_way(self):
        self.assertEqual(self.two_edits(ANOTHER_FIELD, by_token=True), {kind: BARRED for kind in ANOTHER_FIELD})


class WaitingProposalTests(Team):
    def test_bob_rewrites_anns_waiting_proposal_and_neither_may_confirm_it_cat_may(self):
        """The hole on main: Bob rewrote Ann's waiting proposal and then confirmed his own text. Every kind, put forward by Ann and changed by Bob before anyone
        confirmed it."""
        facts = {}
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            ann, bob, cat = team['ann'], team['bob'], team['cat']
            proposals = {'type': lambda: ann.post('/api/workspace/types', CUSTOMER), 'relation': lambda: ann.post('/api/workspace/relations', ORDER_CUSTOMER),
                         'view': lambda: ann.post('/api/workspace/types/views', VALID), 'derived': lambda: ann.post('/api/workspace/types/derived', CANCELLED),
                         'action': lambda: ann.post('/api/workspace/actions', ACTION)}
            from tests.test_derived_properties import ORDER
            self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)
            self.assertEqual(self.put(bob, 'meanings', [{'value': '1', 'label': '鲍勃改的'}])[0], 200)
            facts['meanings'] = {who: self.confirm_kind(team[who], 'meanings')[0] for who in ('bob', 'ann', 'cat')}
            shown = cat.get('/api/workspace/types/order')[1]
            self.assertEqual(cat.post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen']})[0], 200)
            for kind in ('type', 'relation', 'view', 'derived', 'action'):
                self.assertEqual(proposals[kind]()[0], 200, kind)
                field = {'type': {'description': '鲍勃改的'}, 'relation': {'name': '鲍勃改的'}, 'view': {'description': '鲍勃改的'}, 'derived': {'name': '鲍勃改的'},
                         'action': {'description': '鲍勃改的'}}[kind]
                self.assertEqual(self.put(bob, kind, field)[0], 200, kind)
                facts[kind] = {who: self.confirm_kind(team[who], kind)[0] for who in ('bob', 'ann', 'cat')}
        self.assertEqual(facts, {kind: {'bob': 403, 'ann': 403, 'cat': 200} for kind in facts})


# (kind, what Cat changes, what puts it back to the version Bob confirmed)
UNDO = {
    'action': ({'description': 'ZZ卡改的'}, {'description': ACTION['description']}),
    'derived': ({'name': 'ZZ卡改的'}, {'name': CANCELLED['name']}),
    'view': ({'description': 'ZZ卡改的'}, {'description': ''}),
    'relation': ({'name': 'ZZ卡改的'}, {'name': ORDER_CUSTOMER['name']}),
    'meanings': ([{'value': '1', 'label': 'ZZ卡改的'}], [{'value': '1', 'label': '生产中'}]),
    'type': ({'name': 'ZZ卡改的'}, {'name': '客户'}),
}


class UndoTests(Team):
    def undo_facts(self, undoer):
        facts = {}
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            for kind in KINDS:
                changed, back = UNDO[kind]
                self.assertEqual(self.put(team['cat'], kind, changed)[0], 200, kind)
                sent_back = self.state_of(kind)
                self.assertEqual(self.put(team[undoer], kind, back)[0], 200, kind)
                confirmed_by = self.db('SELECT confirmed_by FROM element_state WHERE element_id = ?', (ELEMENTS[kind],))[0][0]
                facts[kind] = (sent_back, self.state_of(kind), confirmed_by)
        return facts

    def test_an_edit_undone_by_its_writer_is_confirmed_again_as_before(self):
        self.assertEqual(self.undo_facts('cat'), {kind: ('checked', 'confirmed', 'Bob') for kind in KINDS})

    def test_an_edit_undone_by_someone_else_is_confirmed_again_as_before(self):
        self.assertEqual(self.undo_facts('ann'), {kind: ('checked', 'confirmed', 'Bob') for kind in KINDS})

    def test_putting_back_the_confirmed_words_while_the_data_moved_leaves_it_waiting_and_frees_who_changed_it(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            self.assertEqual(self.put(team['ann'], 'type', {'name': 'ZZ安改的'})[0], 200)
            rows = csv_rows(customers_mended())
            moved = table_csv('客户.csv', [*rows, {**rows[0], '客户编号': 'KH999', '城市': '新城'}], target='客户', mode='overwrite')
            self.assertEqual(team['bob'].post('/api/workspace/datasets/upload', {'files': [moved]})[0], 200)
            self.assertEqual(self.put(team['cat'], 'type', {'name': '客户'})[0], 200)
            self.assertEqual(self.state_of('type'), 'checked')   # the data it was confirmed on is not the data now: someone looks again
            self.assertEqual(self.confirm_kind(team['ann'], 'type')[0], 403)   # she put it forward: the proposer rule stands as before
            self.assertEqual(self.confirm_kind(team['cat'], 'type')[0], 200)   # nothing it says now is anyone's but what Bob confirmed


class ConfirmedEditTests(Team):
    def test_the_person_who_last_confirmed_it_is_no_exception_and_it_moves_what_stands_on_it_as_a_token_does(self):
        """D19: a signed-in rename sends a confirmed definition back, its last confirmer's too, by the path a token's edit takes on main."""
        facts = {}
        for editor in ('bob', 'token'):
            for kind, fields in (('type', {'name': 'ZZ改的名字'}), ('relation', {'name': 'ZZ改的名字'}), ('view', {'description': 'ZZ改的说明'})):
                with self.service() as (base, out):
                    self.out = out
                    team = self.team(base)
                    self.world(team)
                    client = team['ann' if editor == 'token' else editor]
                    more = bearer(client.post('/api/auth/tokens', {'label': 'agent'})[1]['token']) if editor == 'token' else {}
                    status, body = self.put(client, kind, fields, **more)
                    self.assertEqual(status, 200, body)
                    self.assertTrue(body['reset'], body)
                    facts[(editor, kind)] = self.states_now()
        for kind in ('type', 'relation', 'view'):
            self.assertEqual(facts[('bob', kind)], facts[('token', kind)], kind)
            self.assertEqual(facts[('bob', kind)][kind], 'checked', kind)

    def test_every_change_of_what_a_confirmed_definition_says_sends_it_back(self):
        """Names, descriptions, other names (a type's own, a property's, a meaning's, a view's, a derived property's), a property's display name and the value rules."""
        edits = [('action', {'description': 'ZZ'}), ('derived', {'description': 'ZZ'}), ('derived', {'other_names': ['ZZ取消数']}), ('view', {'other_names': ['ZZ有效']}),
                 ('relation', {'description': 'ZZ'}), ('meanings', [{'value': '1', 'label': '生产中', 'other_names': ['ZZ在产']}]),
                 ('type', {'description': 'ZZ'}), ('type', {'other_names': ['ZZ别称']}), ('type', {'properties': customer_properties(客户等级={'name': 'ZZ等级'})}),
                 ('type', {'properties': customer_properties(客户等级={'other_names': ['ZZ级别']})}), ('type', {'rules': [{'column': '客户编号', 'check': 'not_empty'}]})]
        facts = []
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            for kind, fields in edits:   # leaves first, so what an edit sends back is never edited after it
                self.assertEqual(self.state_of(kind), 'confirmed', kind)
                status, body = self.put(team['bob'], kind, fields)   # Bob confirmed all of it
                self.assertEqual(status, 200, (kind, fields, body))
                facts.append((kind, self.state_of(kind)))
                if self.state_of(kind) != 'confirmed':
                    self.assertEqual(self.confirm_kind(team['cat'], kind)[0], 200, kind)   # Cat changed nothing of it
        self.assertEqual(facts, [(kind, 'checked') for kind, _ in edits])

    def test_a_pipelines_description_counts_as_a_change_of_the_pipeline(self):
        """The Leader's ruling: a pipeline is a definition, and a new description is a change of it as a new step is (tests/test_changed_since_acceptance.py)."""
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            self.assertEqual(self.edit(team['cat'], 'pipeline', 'description', 'ZZ卡改的')[0], 200)
            self.assertEqual(self.states_now()['pipeline'], 'checked')


class TwoBuildersTests(World):
    def two(self, base):
        """Only Ann (an admin) and Bob (a builder) can confirm: root makes them, and Ann disables root."""
        team = self.people(base, 'ann', 'bob', roles={'ann': 'admin'})
        root_id = next(u['id'] for u in team['admin'].get('/api/users')[1]['users'] if u['username'] == 'root')
        self.assertEqual(team['ann'].post('/api/users/disable', {'id': root_id, 'disabled': True})[0], 200)
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
        return team

    def test_two_builders_who_both_changed_it_are_told_who_holds_it_and_the_ways_out(self):
        with self.service() as (base, out):
            self.out = out
            team = self.two(base)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types', CUSTOMER)[0], 200)
            shown = lambda client: client.get('/api/workspace/types/customer')[1]
            confirm = lambda client, **more: client.post('/api/workspace/types/confirm', {'id': 'customer', 'version': shown(client)['version'], 'seen': shown(client)['seen']}, **more)
            self.assertEqual(confirm(bob)[0], 200)
            for client, words in ((ann, 'ZZ安的说明'), (bob, 'ZZ鲍勃的说明')):
                now = shown(client)
                self.assertEqual(client.post('/api/workspace/types/update', {**CUSTOMER, 'id': 'customer', 'version': now['version'], 'description': words})[0], 200)
            for client in (ann, bob):
                status, body = confirm(client)
                self.assertEqual(status, 403, body)
                for said in ('Ann', 'Bob', HELD_ZH, '第三位', '改回'):
                    self.assertIn(said, body['error'])
                self.assertFalse(shown(client)['can_confirm'])
                self.assertIn('Ann', shown(client)['held'])
            status, body = confirm(bob, headers={'Accept-Language': 'en'})
            for said in ('Ann', 'Bob', HELD_EN, 'third person', 'put back'):
                self.assertIn(said, body['error'])
            # the way out without a third person: put back the version Bob confirmed
            now = shown(ann)
            self.assertEqual(ann.post('/api/workspace/types/update', {**CUSTOMER, 'id': 'customer', 'version': now['version'], 'description': ''})[0], 200)
            self.assertEqual(shown(ann)['state'], 'confirmed')

    def test_the_one_who_put_it_forward_alone_reads_what_they_read_before_and_a_second_writer_the_sentence(self):
        with self.service() as (base, out):
            self.out = out
            team = self.two(base)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types', CUSTOMER)[0], 200)
            shown = lambda client: client.get('/api/workspace/types/customer')[1]
            confirm = lambda client: client.post('/api/workspace/types/confirm', {'id': 'customer', 'version': shown(client)['version'], 'seen': shown(client)['seen']})
            self.assertEqual(confirm(ann), (403, {'error': '这一条是你自己提的，要另一位来确认'}))
            self.assertIsNone(shown(ann)['held'])
            now = shown(bob)
            self.assertEqual(bob.post('/api/workspace/types/update', {**CUSTOMER, 'id': 'customer', 'version': now['version'], 'description': 'ZZ鲍勃的说明'})[0], 200)
            status, body = confirm(ann)
            self.assertEqual(status, 403, body)
            for said in ('Ann', 'Bob', '第三位', '管理员可以加一位'):   # nobody else may confirm it: say so, and how to get one
                self.assertIn(said, body['error'])


class WhatOthersReadTests(Team):
    def test_the_owl_file_and_the_csv_never_carry_words_no_second_person_confirmed(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            for kind in KINDS:
                for who, edits in zip(('ann', 'cat'), ANOTHER_FIELD[kind]):
                    for fields in edits:
                        self.assertEqual(self.put(team[who], kind, fields)[0], 200, (kind, who))
            bob = team['bob']
            read = [text(bob, '/api/workspace/agent/schema?file=ontology'), text(bob, '/api/workspace/agent/schema?file=shapes'), text(bob, '/api/workspace/agent/standing?format=csv')]
            for status, body in read:
                self.assertEqual(status, 200)
                self.assertNotIn('ZZ', body)
            self.assertNotIn('ZZ', str(bob.get('/api/workspace/agent/definitions')[1]))
            self.assertEqual(self.confirm_kind(bob, 'type')[0], 200)
            self.assertIn('ZZ安的名称', text(bob, '/api/workspace/agent/schema?file=ontology')[1])   # once a second person confirmed them, they are there

    def test_a_rename_refuses_the_questions_that_stand_on_it_until_it_is_confirmed_again(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            bob, cat = team['bob'], team['cat']
            ask = lambda name: bob.post('/api/workspace/query', {'text': f'SELECT count(c) AS 数量\nFROM (c:{name})'})[1]
            self.assertEqual(ask('客户').get('status'), 'answered', ask('客户'))
            self.assertEqual(self.put(cat, 'type', {'name': 'ZZ客户'})[0], 200)
            self.assertEqual(ask('ZZ客户').get('status'), 'refused', ask('ZZ客户'))
            self.assertEqual(self.confirm_kind(bob, 'type')[0], 200)
            self.assertEqual(ask('ZZ客户').get('status'), 'answered', ask('ZZ客户'))


class OldFileTests(Team):
    def two_writers(self, team):
        self.assertEqual(self.put(team['ann'], 'type', {'description': 'ZZ安的说明'})[0], 200)
        self.assertEqual(self.put(team['cat'], 'type', {'description': 'ZZ安的说明', 'name': 'ZZ卡的名字'})[0], 200)

    def test_a_definition_with_no_record_of_who_changed_it_bars_everyone_the_log_says_changed_it(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            self.two_writers(team)
            self.db("UPDATE element_state SET changed_json = NULL WHERE element_id = 'objtype:customer'")
            self.assertEqual([self.confirm_kind(team[p], 'type')[0] for p in ('ann', 'cat', 'bob')], [403, 403, 200])

    def test_a_change_older_code_made_without_the_record_bars_whoever_the_log_names(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            self.assertEqual(self.put(team['cat'], 'type', {'description': 'ZZ卡的说明'})[0], 200)
            ann_id = next(u['id'] for u in team['admin'].get('/api/users')[1]['users'] if u['username'] == 'ann')
            self.db("UPDATE element_state SET content_json = json_set(content_json, '$.name', 'ZZ旧代码里安改的'), version = version + 1 WHERE element_id = 'objtype:customer'")
            self.db("INSERT INTO log(time, who, element_id, change, before_json, after_json, user_id) VALUES ('2026-11-21T00:00:00+00:00', 'Ann', 'objtype:customer', 'edited', '{}', '{}', ?)", (ann_id,))
            self.assertEqual([self.confirm_kind(team[p], 'type')[0] for p in ('ann', 'cat', 'bob')], [403, 403, 200])

    def test_a_definition_with_no_record_and_no_named_writer_keeps_the_proposer_rule(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.assertEqual(team['ann'].post('/api/workspace/types', CUSTOMER)[0], 200)
            self.db("UPDATE element_state SET changed_json = NULL WHERE element_id = 'objtype:customer'")
            self.db("UPDATE log SET user_id = NULL WHERE element_id = 'objtype:customer'")
            self.assertEqual([self.confirm_kind(team[p], 'type')[0] for p in ('ann', 'cat')], [403, 200])

    def test_a_file_made_before_the_record_opens_and_gains_it(self):
        from ontology_poc_generator.workspace_store import open_workspace
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'w.sqlite'
            open_workspace(path).close()
            conn = sqlite3.connect(path)
            conn.execute('ALTER TABLE element_state DROP COLUMN changed_json')
            conn.execute('ALTER TABLE needed_question DROP COLUMN changed_json')
            conn.commit()
            conn.close()
            conn = open_workspace(path)
            self.assertIn('changed_json', {r[1] for r in conn.execute('PRAGMA table_info(element_state)')})
            self.assertIn('changed_json', {r[1] for r in conn.execute('PRAGMA table_info(needed_question)')})
            conn.close()


Q = '已取消的订单有几张？'


class NeededTests(NeededCase):
    def team(self, base, valid=True):
        team = super().team(base, valid)
        admin = team['admin']
        self.assertEqual(admin.post('/api/users', {'username': 'cat', 'display_name': 'Cat', 'role': 'builder', 'password': 'first password 1'})[0], 200)
        from tests.test_access import Client
        from tests.test_two_person import GOOD
        cat = Client(base)
        cat.login('cat', 'first password 1')
        cat.post('/api/auth/password', {'current': 'first password 1', 'new': GOOD})
        team['cat'] = cat
        return team

    def change(self, client, **fields):
        found = self.item(client, Q)
        status, body = client.post(f'{NEEDED}/update', {'id': found['id'], 'version': found['version'], **fields})
        self.assertEqual(status, 200, body)
        return body

    def test_two_people_who_changed_an_expectation_cannot_confirm_it_a_third_can(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.write(team['ann'], Q, number(5))
            self.change(team['cat'], expect=number(6))
            said = self.confirm(team['ann'], Q, status=403)['error']
            for name in ('Ann', 'Cat', 'Bob'):   # who changed it, and who may confirm it
                self.assertIn(name, said)
            self.confirm(team['cat'], Q, status=403)
            self.assertEqual(self.confirm(team['bob'], Q)['state'], 'confirmed')

    def test_another_field_does_not_free_the_first_writer(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.write(team['bob'], Q, number(5))
            self.confirm(team['cat'], Q)
            self.change(team['ann'], expect=number(6))
            self.change(team['cat'], question=Q + ' ')   # cleaned to the same words: nothing changes
            self.change(team['cat'], question='已取消的订单一共有几张？')
            Q2 = '已取消的订单一共有几张？'
            found = next(q for q in self.listing(team['ann'])['questions'] if q['question'] == Q2)
            status, body = team['ann'].post(f'{NEEDED}/confirm', {'id': found['id'], 'version': found['version']})
            self.assertEqual(status, 403, body)
            status, body = team['bob'].post(f'{NEEDED}/confirm', {'id': found['id'], 'version': found['version']})
            self.assertEqual(status, 200, body)

    def test_an_expectation_put_back_is_confirmed_again_as_before(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.write(team['ann'], Q, number(5))
            self.confirm(team['bob'], Q)
            self.assertEqual(self.change(team['cat'], expect=number(6))['state'], 'proposed')
            back = self.change(team['cat'], expect=number(5))
            self.assertEqual((back['state'], back['confirmed_by']), ('confirmed', 'Bob'))


class WhatTheRuleCoversTests(NeededCase):
    def test_the_rule_covers_the_team_workspaces_definitions_and_not_pipelines_or_the_early_screens_relations(self):
        from ontology_poc_generator.workspace_store import tracked
        covered = ['objtype:order', 'enum:order:状态码', 'relation:order_customer', 'objview:有效订单', 'objaction:改交付天数', 'derived:customer:cancelled_orders']
        self.assertEqual([tracked(e) for e in covered], [True] * len(covered))
        self.assertEqual([tracked(e) for e in ('pipeline:客户合计', 'relation:run-1:订单_客户', 'view:run-1:有效订单', 'property:run-1:订单.金额')], [False] * 4)
