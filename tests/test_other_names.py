"""Other names: a definition (an object type, a property, a code meaning, a view, a derived property) can carry up to five other names, for example in another
language. A question that uses one is treated as if it used the name: the refusal before the model for a definition that is not confirmed or that waits, the check
that a named view or meaning was used, and the line that says whether a filter's value is in the question. Nothing else changes: code never picks the rows of an
answer because a question names something; the model still says which view it reads.

The differential tests ask the same questions with the same scripted replies with other names heard and not heard (other_names.HEARD), on the demo seeded
without other names and on the pilot fixture, and require every answer, refusal, stored record and request to the model to be the same. With the demo's other
names in place, they name exactly the answers that change, each a question that now names the definition its other name belongs to. Numbers are those of
docs/pilot/sample."""
import csv
import io
import json
import re
import sqlite3
import unittest
import zipfile
from unittest import mock

from ontology_poc_generator import demo as demo_mode, other_names
from tests import test_derived_new_values as pilot
from tests.test_demo_mode import a_guest
from tests.test_demo_view_waits import Seeded, change_the_view
from tests.test_one_number import ALL_AMOUNT, ALL_COUNT, DEMO_PAIRS, VALID_AMOUNT, VALID_COUNT, Planted, PilotTests, Scripted, item, setUpModule, tearDownModule  # noqa: F401  (the caps of the module)
from tests.test_object_types import ORDER, VALID
from tests.test_token_edit_trust import World, bearer
from tests.test_workspace_questions import ALL_ORDERS

DELIVERED = {**ALL_ORDERS, 'where': [{'field': 'status_code', 'equals': 'Delivered'}]}
CANCELLED = {**ALL_ORDERS, 'where': [{'field': 'status_code', 'equals': 'Cancelled'}]}
EXTRA_PAIRS = [   # questions in the words of the demo's other names
    ('订单有多少？', item(ALL_ORDERS)), ('订单的总金额是多少？', item()),
    ('已送达的订单有几笔？', item(DELIVERED, [{'id': 'orders.status_code=Delivered', 'direction': 'include', 'basis': '已送达'}])),
    ('已送达的订单有几笔？', item(DELIVERED)), ('已送达的订单有几笔？', item(ALL_ORDERS)),
    ('按客户城市看有效订单金额', item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': '有效订单'}])),
    ('有效订单有多少？', item(ALL_ORDERS, [{'id': 'Valid orders', 'direction': 'include', 'basis': '有效订单'}])), ('有效订单有多少？', item(ALL_ORDERS)),
    ('新建状态的订单有多少？', item({**ALL_ORDERS, 'where': [{'field': 'status_code', 'equals': 'New'}]})),
    ('有效订单的总金额是多少？', 'not json'),
]
PAIRS = [*DEMO_PAIRS, *EXTRA_PAIRS]

# (question, the index of the reply among those asked with it in PAIRS): the answers that change once the demo's other names are heard, for a guest and a builder
CHANGED = {
    ('有效订单的总金额是多少？', 0),   # the model left Cancelled and Refunded out on its own: the question names Valid orders, which it did not say it read
    ('有效订单的总金额是多少？', 2),   # the same with New too
    ('已取消的订单有多少？', 0),   # Cancelled included: the filter's value is in the question now (已取消), so it is no longer marked as added by the model
    ('已取消的订单有多少？', 1),   # a filter on Cancelled the model gave no direction for: the refusal now says the question mentions it
    ('已取消的订单有多少？', 2),   # every order, while the question says 已取消: refused, the model did not say how it used Cancelled
    ('已送达的订单有几笔？', 0), ('已送达的订单有几笔？', 1), ('已送达的订单有几笔？', 2),   # the same three for Delivered (已送达)
    ('按客户城市看有效订单金额', 0),   # Customer waits for a second look: refused before the model
    ('有效订单有多少？', 1),   # every order, while the question names Valid orders
    ('新建状态的订单有多少？', 0),   # 新建 is two characters: heard with its column named, here by the property's other name 状态
}


def asked_with(pairs):
    """[(question, n, reply)]: each pair with the index of its reply among the pairs with the same question."""
    seen, out = {}, []
    for question, reply in pairs:
        out.append((question, seen.get(question, 0), reply))
        seen[question] = seen.get(question, 0) + 1
    return out


def whole(body):
    return json.dumps({k: v for k, v in body.items() if k not in ('id', 'asked_at')}, ensure_ascii=False, sort_keys=True)


def steady(text: str) -> str:
    """For two workspaces built a moment apart: the times written in them left out."""
    return re.sub(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:[+-]\d\d:\d\d|Z)?', '<time>', text)


def last_record(folder):
    """The stored row of the last question, without its id and time."""
    conn = sqlite3.connect(folder / 'workspace.sqlite')
    try:
        row = conn.execute('SELECT user_id, asked_by, question, status, answer_json, definitions_json, dataset_versions_json, types_json FROM qa_question ORDER BY id DESC LIMIT 1').fetchone()
        return json.dumps(row, ensure_ascii=False)
    finally:
        conn.close()


class DemoAsker:
    """Asks on a seeded demo with a scripted model, heard or not, and returns (the answer, the stored record, what the model was sent)."""

    def ask(self, demo, who, question, reply, heard=True):
        demo.model.__class__ = Scripted
        demo.model.replies, demo.model.requests = [reply], []
        with mock.patch.object(other_names, 'HEARD', heard):
            status, body = who.call('POST', '/api/workspace/ask', {'question': question})
        return status, body, last_record(demo.folder), json.dumps(demo.model.requests, ensure_ascii=False, sort_keys=True)


class WithoutOtherNamesTests(unittest.TestCase, DemoAsker):
    """The demo as it was seeded before other names: hearing them or not changes nothing at all."""

    @classmethod
    def setUpClass(cls):
        with mock.patch.object(demo_mode, 'OTHER_NAMES', {}):
            cls.demo = Seeded().__enter__()
        cls.guest = a_guest(cls.demo.base)

    @classmethod
    def tearDownClass(cls):
        cls.demo.__exit__(None, None, None)

    def test_with_no_other_names_every_answer_refusal_record_and_request_is_the_same_heard_or_not(self):
        compared = 0
        for who in (self.guest, self.demo.admin('en'), self.demo.admin()):
            for question, n, reply in asked_with(PAIRS):
                with self.subTest(question=question, n=n):
                    on, off = self.ask(self.demo, who, question, reply, True), self.ask(self.demo, who, question, reply, False)
                    self.assertEqual((on[0], whole(on[1]), on[2], on[3]), (off[0], whole(off[1]), off[2], off[3]))
                    compared += 1
        self.assertGreaterEqual(compared, 144)

    def test_the_seed_without_other_names_stores_none(self):
        conn = sqlite3.connect(self.demo.folder / 'workspace.sqlite')
        try:
            self.assertFalse([e for (e, c) in conn.execute('SELECT element_id, content_json FROM element_state') if c and 'other_names' in c])
        finally:
            conn.close()

    def test_a_workspace_seeded_before_other_names_keeps_answering_and_takes_them_later(self):
        admin, builder = self.demo.admin('en'), self.demo.builder('en')
        status, body, _, _ = self.ask(self.demo, self.guest, 'Valid orders 的总金额是多少？', item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': 'Valid orders'}]))
        self.assertEqual((status, body['answer']['measure']['value']), (200, VALID_AMOUNT))
        view = next(v for v in admin.call('GET', '/api/workspace/types/order/views')[1]['views'] if v['name'] == 'Valid orders')
        status, body = admin.call('POST', '/api/workspace/types/views/update', {'id': 'Valid orders', 'version': view['version'], 'type': 'order', 'filters': view['filters'], 'other_names': ['有效订单']})
        try:
            self.assertEqual((status, body.get('state')), (200, 'checked'), body)   # a person's edit of the other names waits for a second person, as any change does
            view = next(v for v in builder.call('GET', '/api/workspace/types/order/views')[1]['views'] if v['name'] == 'Valid orders')
            self.assertEqual(builder.call('POST', '/api/workspace/types/views/confirm', {'id': 'Valid orders', 'version': view['version'], 'seen': view['seen']})[0], 200)
            status, body, _, _ = self.ask(self.demo, self.guest, '有效订单的总金额是多少？', item())
            self.assertEqual((status, body['status']), (200, 'definition_unmet'), body)
        finally:   # the seed as it was, confirmed by the builder: what the other tests of this class read
            view = next(v for v in builder.call('GET', '/api/workspace/types/order/views')[1]['views'] if v['name'] == 'Valid orders')
            self.assertEqual(admin.call('POST', '/api/workspace/types/views/update', {'id': 'Valid orders', 'version': view['version'], 'type': 'order', 'filters': view['filters'], 'other_names': []})[0], 200)
            view = next(v for v in builder.call('GET', '/api/workspace/types/order/views')[1]['views'] if v['name'] == 'Valid orders')
            if view['state'] != 'confirmed':
                self.assertEqual(builder.call('POST', '/api/workspace/types/views/confirm', {'id': 'Valid orders', 'version': view['version'], 'seen': view['seen']})[0], 200)


class PilotWithoutOtherNamesTests(pilot.PilotFoundation):
    """The pilot sample, its view and derived property named in Chinese, no other names: hearing them or not changes nothing."""

    def test_with_no_other_names_every_answer_record_and_request_is_the_same_heard_or_not(self):
        from tests.test_derived_view_exact import with_orphan
        pairs = [*PilotTests.PAIRS, ('订单有多少？', item({'start': 'order', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None})),
                 ('已送达的订单有几笔？', item({'start': 'order', 'where': [{'field': 'status_code', 'equals': '已送达'}], 'via': [], 'group_by': None, 'share': None, 'measure': None}))]
        compared = 0
        for orders in (None, with_orphan()):
            model = Scripted(item())
            with self.service(gateway=model) as (base, out):
                ann = self.foundation(base, orders=orders)['ann']
                for question, reply in pairs:
                    with self.subTest(question=question, reply=str(reply)[:80], orphan=orders is not None):
                        got = []
                        for heard in (True, False):
                            model.replies, model.requests = [reply], []
                            with mock.patch.object(other_names, 'HEARD', heard):
                                status, body = ann.post('/api/workspace/ask', {'question': question})
                            got.append((status, whole(body), last_record(out), json.dumps(model.requests, ensure_ascii=False, sort_keys=True)))
                        self.assertEqual(got[0], got[1])
                        compared += 1
        self.assertGreaterEqual(compared, 26)


class SeededDemoTests(unittest.TestCase, DemoAsker):
    """The demo seed with its Chinese other names: Order 订单, its properties, its status meanings (已送达 for Delivered…), the view Valid orders 有效订单, Customer 客户."""

    @classmethod
    def setUpClass(cls):
        cls.demo = Seeded().__enter__()
        cls.guest = a_guest(cls.demo.base)

    @classmethod
    def tearDownClass(cls):
        cls.demo.__exit__(None, None, None)

    def test_the_seed_ends_with_the_same_confirmed_and_waiting_states_as_without_other_names(self):
        def states(folder):
            conn = sqlite3.connect(folder / 'workspace.sqlite')
            try:
                return dict(conn.execute("SELECT element_id, state FROM element_state WHERE element_id NOT LIKE 'dataset:%' AND element_id NOT LIKE 'column:%'"))
            finally:
                conn.close()
        with mock.patch.object(demo_mode, 'OTHER_NAMES', {}):
            plain = Seeded().__enter__()
        try:
            self.assertEqual(states(self.demo.folder), states(plain.folder))
        finally:
            plain.__exit__(None, None, None)
        self.assertEqual({k: v for k, v in states(self.demo.folder).items() if k.startswith(('objtype:', 'enum:', 'objview:', 'relation:'))},
                         {'objtype:order': 'confirmed', 'enum:order:status_code': 'confirmed', 'objview:Valid orders': 'confirmed', 'objtype:customer': 'needs_look', 'relation:order_customer': 'needs_look'})

    def test_the_definitions_carry_their_other_names_on_the_pages(self):
        admin = self.demo.admin()
        order = admin.call('GET', '/api/workspace/types/order')[1]
        self.assertEqual(order['other_names'], ['订单'])
        props = {p['column']: p for p in order['properties']}
        self.assertEqual(props['status_code']['other_names'], ['状态'])
        self.assertEqual({v['label']: v.get('other_names') for v in props['status_code']['meanings']['values']}['Delivered'], ['已送达'])
        view = admin.call('GET', '/api/workspace/types/order/views')[1]['views'][0]
        self.assertEqual(view['other_names'], ['有效订单'])
        self.assertEqual(admin.call('GET', '/api/workspace/types/customer')[1]['other_names'], ['客户'])

    def test_on_the_demo_the_valid_order_question_in_chinese_gives_the_view_with_every_row_beside_it(self):
        for who in (self.guest, self.demo.admin()):
            status, body, _, _ = self.ask(self.demo, who, '有效订单的总金额是多少？', item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': 'the view'}]))
            self.assertEqual((status, body['status'], body['answer']['measure']['value'], body['answer']['total']), (200, 'answered', VALID_AMOUNT, VALID_COUNT))
            self.assertEqual([(v.get('all_rows'), v['answer']['measure']['value'], v['answer']['total']) for v in body['beside']['views']], [(True, ALL_AMOUNT, ALL_COUNT)])
            english = self.ask(self.demo, who, 'Valid orders 的总金额是多少？', item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': 'the view'}]))[1]
            self.assertEqual({k: v for k, v in json.loads(whole(body)).items() if k != 'question'}, {k: v for k, v in json.loads(whole(english)).items() if k != 'question'})

    def test_the_chinese_question_is_heard_as_naming_the_view_when_the_model_does_not_read_it(self):
        status, body, _, _ = self.ask(self.demo, self.guest, '有效订单的总金额是多少？', item())
        self.assertEqual((status, body['status']), (200, 'definition_unmet'), body)
        self.assertEqual([(u['definition'], u['kind']) for u in body['unmet']], [('Valid orders', 'view')])
        status, body, _, _ = self.ask(self.demo, self.guest, '有效订单的总金额是多少？', item(), heard=False)
        self.assertEqual((body['status'], body['answer']['measure']['value']), ('answered', ALL_AMOUNT))   # as before other names: every row, the view beside it

    def test_a_question_saying_only_the_types_other_name_is_not_heard_as_naming_the_view(self):
        status, body, _, _ = self.ask(self.demo, self.guest, '订单的总金额是多少？', item())
        self.assertEqual((status, body['status'], body['answer']['measure']['value']), (200, 'answered', ALL_AMOUNT))
        self.assertEqual([v['name'] for v in body['beside']['views']], ['Valid orders'])

    def test_a_guests_question_naming_the_waiting_customer_in_chinese_is_refused_before_the_model_saying_only_that_it_waits(self):
        for question in ('按客户城市看有效订单金额', '按 Customer 城市看有效订单金额'):
            status, body, _, requests = self.ask(self.demo, self.guest, question, item())
            self.assertEqual((status, body['status'], body['refusal']['kind'], requests), (200, 'refused', 'unsettled', '[]'), question)
            [line] = body['refusal']['definitions']
            self.assertEqual((line['kind'], line['waiting']), ('type', True))
            said = json.dumps({k: body[k] for k in ('reason', 'refusal', 'steps')}, ensure_ascii=False)
            for word in ('Customer', 'customer', '客户', 'demo-admin'):
                self.assertNotIn(word, said)

    def test_the_model_is_told_the_other_names_of_what_it_is_told_about(self):
        _, _, _, sent = self.ask(self.demo, self.demo.admin(), '订单有多少？', item(ALL_ORDERS))
        [request] = json.loads(sent)
        order = next(t for t in request['ontology']['object_types'] if t['key'] == 'order')
        self.assertEqual(order['also_called'], ['订单'])
        self.assertEqual({a['path']: a.get('also_called') for a in order['attributes']},
                         {'order_id': ['订单号'], 'customer_id': ['客户号'], 'order_date': ['下单日期'], 'amount': ['金额'], 'status_code': ['状态']})
        by_id = {d['id']: d for d in request['definitions']}
        self.assertEqual(by_id['orders.status_code=Delivered']['also_called'], ['已送达'])
        self.assertEqual(by_id['Valid orders']['also_called'], ['有效订单'])
        self.assertNotIn('customer', [t['key'] for t in request['ontology']['object_types']])   # Customer waits: neither it nor its other name is told
        self.assertNotIn('客户名称', sent)
        _, _, _, plain = self.ask(self.demo, self.demo.admin(), '订单有多少？', item(ALL_ORDERS), heard=False)
        self.assertNotIn('also_called', plain)

    def test_a_question_naming_the_waiting_view_by_its_other_name_is_refused_as_its_name_would_be(self):
        fresh = Seeded().__enter__()
        try:
            admin = fresh.admin('en')
            change_the_view(admin)
            for who in (admin, fresh.builder('en'), a_guest(fresh.base, 'en')):
                chinese = self.ask(fresh, who, '有效订单的总金额是多少？', item())
                english = self.ask(fresh, who, 'Valid orders 的总金额是多少？', item())
                self.assertEqual((chinese[1]['status'], chinese[3]), ('refused', '[]'))   # before the model
                self.assertEqual({k: chinese[1][k] for k in ('reason', 'refusal', 'steps')}, {k: english[1][k] for k in ('reason', 'refusal', 'steps')})
                self.assertEqual(self.ask(fresh, who, '订单有多少？', item(ALL_ORDERS))[1]['status'], 'answered')   # 订单 alone does not name the view
        finally:
            fresh.__exit__(None, None, None)

    def test_with_the_demos_other_names_exactly_the_questions_that_name_a_definition_by_one_change(self):
        changed = set()
        for who in (self.guest, self.demo.admin()):
            for question, n, reply in asked_with(PAIRS):
                on, off = self.ask(self.demo, who, question, reply, True), self.ask(self.demo, who, question, reply, False)
                if whole(on[1]) != whole(off[1]):
                    changed.add((question, n))
                    self.assertNotEqual(on[2], off[2])   # what is kept says the same as what was returned
        self.assertEqual(changed, CHANGED)

    def test_a_meaning_said_by_its_other_name_is_not_marked_as_a_filter_the_question_never_says(self):
        reply = item(DELIVERED, [{'id': 'orders.status_code=Delivered', 'direction': 'include', 'basis': '已送达'}])
        on = self.ask(self.demo, self.guest, '已送达的订单有几笔？', reply)[1]
        off = self.ask(self.demo, self.guest, '已送达的订单有几笔？', reply, heard=False)[1]
        self.assertEqual((on['answer']['total'], off['answer']['total']), (off['answer']['total'], 63))
        self.assertEqual([f.get('not_in_question') for f in on['evidence']['filters']], [None])
        self.assertEqual([f.get('not_in_question') for f in off['evidence']['filters']], [True])

    def test_the_readouts_carry_the_other_names(self):
        admin = self.demo.admin()
        d = admin.call('GET', '/api/workspace/agent/definitions')[1]
        order = next(t for t in d['types'] if t['id'] == 'order')
        self.assertEqual(order['other_names'], ['订单'])
        self.assertEqual({p['column']: p.get('other_names') for p in order['properties']}['amount'], ['金额'])
        self.assertEqual(order['meanings']['status_code']['other_names']['Delivered'], ['已送达'])
        self.assertEqual([v.get('other_names') for v in d['views']], [['有效订单']])
        standing = {e['id']: e for e in admin.call('GET', '/api/workspace/agent/standing')[1]['definitions']}
        self.assertEqual((standing['objtype:order']['other_names'], standing['objview:Valid orders']['other_names']), (['订单'], ['有效订单']))
        self.assertEqual(standing['enum:order:status_code']['other_names']['Cancelled'], ['已取消'])
        sheet = self.raw(admin, '/api/workspace/agent/standing?format=csv')
        rows = {r['id']: r for r in csv.DictReader(io.StringIO(sheet.decode('utf-8-sig')))}
        self.assertEqual((rows['objtype:order']['other_names'], rows['objview:Valid orders']['other_names']), ('订单', '有效订单'))
        self.assertIn('已送达', rows['enum:order:status_code']['other_names'])
        with zipfile.ZipFile(io.BytesIO(self.raw(admin, '/api/workspace/agent/skill'))) as z:
            files = {n.partition('/')[2]: z.read(n).decode('utf-8') for n in z.namelist()}
        self.assertIn('订单', files['definitions/order.md'])
        self.assertIn('已送达', files['definitions/order.md'])
        self.assertIn('有效订单', files['definitions/views.md'])

    def raw(self, who, path):
        from urllib.request import Request
        request = Request(self.demo.base + path, headers={'Origin': self.demo.base, 'Accept-Language': who.lang})
        with who.opener.open(request) as response:
            return response.read()


class ClashTests(Planted):
    """What may be saved: at most five other names of at most 40 characters each, none equal (ignoring case and width) to a name or other name in its scope, and a
    name in Chinese is matched as a substring, so none contains or is contained in another in its scope. Across scopes, a type's name may be inside a view's
    (订单 inside 有效订单: a question about valid orders is about orders), never the other way round."""

    def setUp(self):
        self.model = Scripted(item(ALL_ORDERS))

    def world(self, base):
        team = self.team(base)
        self.confirmed_orders(team)
        self.assertEqual(team['ann'].post('/api/workspace/types/views', VALID)[0], 200)
        self.confirm_view(team['bob'], 'order', '有效订单')
        return team

    def update_type(self, client, **change):
        now = client.get('/api/workspace/types/order')[1]
        return client.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': now['version'], **change})

    def update_view(self, client, **change):
        now = next(v for v in client.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == '有效订单')
        return client.post('/api/workspace/types/views/update', {**VALID, 'id': '有效订单', 'version': now['version'], **change})

    def test_the_limits_on_count_and_length(self):
        with self.service(gateway=self.model) as (base, out):
            ann = self.world(base)['ann']
            self.assertEqual(self.update_type(ann, other_names=['a1', 'a2', 'a3', 'a4', 'a5', 'a6'])[0], 400)
            self.assertEqual(self.update_type(ann, other_names=['x' * 41])[0], 400)
            self.assertEqual(self.update_type(ann, other_names=['Sales order', 'sales ORDER'])[0], 400)   # the same name twice, ignoring case
            self.assertEqual(self.update_type(ann, other_names=['line\nbreak'])[0], 400)
            status, body = self.update_type(ann, other_names=['  Sales order ', 'x' * 40, 'a3', 'a4', 'a5'])
            self.assertEqual(status, 200, body)
            self.assertEqual(ann.get('/api/workspace/types/order')[1]['other_names'], ['Sales order', 'x' * 40, 'a3', 'a4', 'a5'])

    def test_a_type_name_clash_is_refused_ignoring_case_and_width_and_in_chinese_by_containment(self):
        from tests.test_derived_properties import CUSTOMER as PLANTED_CUSTOMER
        with self.service(gateway=self.model) as (base, out):
            ann = self.world(base)['ann']
            self.assertEqual(ann.post('/api/workspace/types', {**PLANTED_CUSTOMER, 'other_names': ['buyer']})[0], 200)
            for refused in (['客户'], ['ＢＵＹＥＲ'], ['Customer'], ['大客户'], ['客']):   # its name, the other's other name in full width, its English name; 客户 inside 大客户, 客 inside 客户
                with self.subTest(refused=refused):
                    status, body = self.update_type(ann, other_names=refused)
                    self.assertEqual(status, 409, body)
                    self.assertIn(refused[0], body['error'])
            self.assertEqual(self.update_type(ann, other_names=['订单'])[0], 409)   # its own name: already what it is called
            self.assertEqual(self.update_type(ann, other_names=['Sales order', '销售单'])[0], 200)

    def test_property_and_meaning_clashes_are_refused_within_their_scope(self):
        with self.service(gateway=self.model) as (base, out):
            ann = self.world(base)['ann']
            props = lambda names: [{'column': '订单号', 'other_names': names.get('订单号', [])}, {'column': '金额', 'other_names': names.get('金额', [])}, {'column': '状态码', 'enum': True}]
            self.assertEqual(self.update_type(ann, properties=props({'订单号': ['金额']}))[0], 409)   # another property's name
            self.assertEqual(self.update_type(ann, properties=props({'订单号': ['单号'], '金额': ['单号']}))[0], 409)
            self.assertEqual(self.update_type(ann, properties=props({'订单号': ['单号'], '金额': ['订单号码']}))[0], 409)   # 订单号 inside 订单号码
            status, body = self.update_type(ann, properties=props({'订单号': ['单号'], '金额': ['amount']}))
            self.assertEqual(status, 200, body)
            meanings = lambda **o: {'id': 'order', 'column': '状态码', 'values': [{'value': '0', 'label': '已交付', 'other_names': o.get('d', [])}, {'value': '2', 'label': '已取消', 'other_names': o.get('c', [])}]}
            self.assertEqual(ann.post('/api/workspace/types/meanings', meanings(c=['已交付']))[0], 409)
            self.assertEqual(ann.post('/api/workspace/types/meanings', meanings(c=['取消'], d=['取消了的']))[0], 409)
            status, body = ann.post('/api/workspace/types/meanings', meanings(c=['作废'], d=['delivered']))
            self.assertEqual(status, 200, body)

    def test_a_view_takes_no_other_name_inside_a_types_name_and_a_type_takes_none_containing_a_views(self):
        with self.service(gateway=self.model) as (base, out):
            ann = self.world(base)['ann']
            self.assertEqual(self.update_view(ann, other_names=['订单'])[0], 409)   # the type's name: a question about orders would be heard as naming the view
            self.assertEqual(self.update_view(ann, other_names=['单'])[0], 409)   # inside it
            status, body = self.update_view(ann, other_names=['好订单'])   # the type's name inside the view's: allowed
            self.assertEqual(status, 200, body)
            self.assertEqual(self.update_type(ann, other_names=['好订单表'])[0], 409)   # a type's other name holding a view's other name
            self.assertEqual(self.update_type(ann, other_names=['有效订单'])[0], 409)
            self.assertEqual(self.update_type(ann, other_names=['Purchase'])[0], 200)

    def test_views_and_derived_properties_of_one_type_share_a_scope(self):
        with self.service(gateway=self.model) as (base, out):
            ann = self.world(base)['ann']
            gross = {'type': 'order', 'english_name': 'gross', 'name': '含税金额', 'kind': 'function', 'expression': '金额 * 1.13'}
            self.assertEqual(ann.post('/api/workspace/types/derived', {**gross, 'other_names': ['有效订单']})[0], 409)
            self.assertEqual(ann.post('/api/workspace/types/derived', {**gross, 'other_names': ['税后']})[0], 200)
            self.assertEqual(self.update_view(ann, other_names=['税后'])[0], 409)


class EditTests(World):
    """Adding, changing or removing other names behaves as changing the name of that kind does: any edit, signed in or with a token, puts a confirmed type,
    property, view, derived property or meaning forward again for a second person (tests/test_changed_since_confirm.py)."""

    def states_after(self, by_token):
        out = {}
        for kind in ('type', 'property', 'view', 'derived', 'meanings'):
            with self.service() as (base, out_dir):
                self.out = out_dir
                team = self.team(base)
                self.world(team)
                ann = team['ann']
                more = bearer(ann.post('/api/auth/tokens', {'label': 'agent'})[1]['token']) if by_token else {}
                if kind == 'property':
                    from tests.test_object_relations import CUSTOMER
                    props = [{**p, 'other_names': ['客户号码']} if p['column'] == CUSTOMER['key'][0] else p for p in CUSTOMER['properties']]
                    status, body = self.edit(ann, 'type', 'properties', props if any(p['column'] == CUSTOMER['key'][0] for p in props) else [*props, {'column': CUSTOMER['key'][0], 'other_names': ['客户号码']}], **more)
                elif kind == 'meanings':
                    status, body = ann.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': [{'value': '2', 'label': '已取消', 'other_names': ['作废']}]}, **more)
                else:
                    status, body = self.edit(ann, kind, 'other_names', ['又一个名字'], **more)
                self.assertEqual(status, 200, (kind, body))
                out[kind] = self.states_now()['meanings' if kind == 'meanings' else 'type' if kind == 'property' else kind]
                if kind == 'type' and not by_token:
                    self.assertIn('checked', [e['change'] for e in ann.get('/api/workspace/types/customer/log')[1]['log'][:3]])
        return out

    def test_a_persons_edit_puts_each_back_as_a_tokens_does(self):
        self.assertEqual(self.states_after(by_token=False), {'type': 'checked', 'property': 'checked', 'view': 'checked', 'derived': 'checked', 'meanings': 'checked'})

    def test_an_edit_with_a_token_puts_each_back(self):
        self.assertEqual(self.states_after(by_token=True), {'type': 'checked', 'property': 'checked', 'view': 'checked', 'derived': 'checked', 'meanings': 'checked'})


class VisibilityTests(Planted):
    """A definition the asker may not see is not matched by its other names, and nothing in the answer says it exists: the whole response is the same with the
    other name and without it."""

    def test_a_type_kept_from_the_asker_changes_nothing_through_its_other_name(self):
        from tests.test_derived_properties import TICKET
        for asker in ('bob', 'vera'):
            bodies = []
            for names in ([], ['维修单']):
                model = Scripted(item(ALL_ORDERS))
                with self.service(gateway=model) as (base, out):
                    team = self.team(base)
                    self.confirmed_orders(team)
                    self.assertEqual(team['ann'].post('/api/workspace/types', {**TICKET, 'other_names': names} if names else TICKET)[0], 200)
                    self.confirm(team['bob'], 'ticket')
                    ann_id = next(u['id'] for u in team['admin'].get('/api/users')[1]['users'] if u['username'] == 'ann')
                    self.assertEqual(team['admin'].post('/api/workspace/permissions', {'type': 'ticket', 'visible_to': [ann_id]})[0], 200)
                    model.requests = []
                    status, body = self.ask(team[asker], '维修单和订单有多少？')
                    bodies.append((status, steady(whole(body)), steady(json.dumps(model.requests, ensure_ascii=False, sort_keys=True))))
            self.assertEqual(bodies[0], bodies[1], asker)
            self.assertNotIn('维修单', bodies[1][2].replace('维修单和订单有多少？', ''))

    def test_a_view_a_viewer_may_not_see_changes_nothing_through_its_other_name(self):
        bodies = []
        for names in ([], ['在产']):
            model = Scripted(item(ALL_ORDERS))
            with self.service(gateway=model) as (base, out):
                team = self.team(base)
                self.confirmed_orders(team)
                self.assertEqual(team['ann'].post('/api/workspace/types/views', {'name': '生产中订单', 'type': 'order', 'filters': [{'column': '状态码', 'op': 'is', 'label': '生产中'}],
                                                                               **({'other_names': names} if names else {})})[0], 200)   # proposed: not a viewer's
                status, body = self.ask(team['vera'], '在产的订单有多少？')
                bodies.append((status, steady(whole(body)), steady(json.dumps(model.requests, ensure_ascii=False, sort_keys=True))))
        self.assertEqual(bodies[0], bodies[1])
        self.assertNotIn('生产中订单', bodies[1][1] + bodies[1][2])

    def test_other_names_of_a_hidden_column_and_of_meanings_kept_from_models_are_not_sent(self):
        model = Scripted(item(ALL_ORDERS))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, admin = team['ann'], team['admin']
            order = {**ORDER, 'properties': [{'column': '订单号'}, {'column': '金额', 'other_names': ['货款']}, {'column': '状态码', 'enum': True, 'other_names': ['状态']}],
                     'enums': {'状态码': [{**m, 'other_names': [f'{m["label"]}了']} for m in ORDER['enums']['状态码']]}}
            self.assertEqual(ann.post('/api/workspace/types', order)[0], 200)
            self.confirm(team['bob'], 'order', '状态码')
            self.confirm(team['bob'], 'order')
            self.ask(ann, '订单有多少？')
            told = json.dumps(model.requests[-1], ensure_ascii=False)
            self.assertIn('货款', told)
            self.assertIn('已取消了', told)
            self.assertEqual(ann.post('/api/workspace/types/privacy', {'id': 'order', 'column': '状态码', 'hide_values': True})[0], 200)
            self.ask(ann, '订单有多少？')
            told = json.dumps(model.requests[-1], ensure_ascii=False)
            self.assertNotIn('已取消了', told)   # the meanings are not sent, nor their other names
            self.assertIn('状态', told)   # the property's own other name is a name, sent as its name is
            ann_id = next(u['id'] for u in admin.get('/api/users')[1]['users'] if u['username'] == 'ann')
            self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'order', 'column': '金额', 'visible_to': [ann_id]})[0], 200)
            self.ask(team['bob'], '订单有多少？')
            self.assertNotIn('货款', json.dumps(model.requests[-1], ensure_ascii=False))


class CrossScopeTests(unittest.TestCase, DemoAsker):
    """On the demo, 订单 (Order) inside 有效订单 (Valid orders): a question saying 有效订单 names the view and, through the words it contains, the type; a question
    saying only 订单 names the type and not the view."""

    def test_both_directions_while_the_type_and_the_view_wait(self):
        fresh = Seeded().__enter__()
        try:
            admin, builder = fresh.admin('en'), fresh.builder('en')
            now = admin.call('GET', '/api/workspace/types/order')[1]
            payload = {'id': 'order', 'version': now['version'], 'english_name': 'order', 'name': now['name'], 'description': now.get('description') or '', 'dataset': 'orders',
                       'key': now['key'], 'properties': [{'column': p['column'], 'type': 'text' if p['column'] == 'amount' else p['type'], 'enum': p['enum']} for p in now['properties']]}
            status, body = admin.call('POST', '/api/workspace/types/update', payload)   # a property type changes: Order is put forward again, the view goes back with it
            self.assertEqual((status, body.get('state')), (200, 'checked'), body)
            valid = self.ask(fresh, builder, '有效订单的总金额是多少？', item())[1]
            self.assertEqual(valid['status'], 'refused')
            self.assertEqual({(d['kind'], d['name']) for d in valid['refusal']['definitions']} >= {('type', 'Order'), ('view', 'Valid orders')}, True, valid['refusal'])
            orders = self.ask(fresh, builder, '订单有多少？', item(ALL_ORDERS))[1]
            self.assertEqual(orders['status'], 'refused')
            self.assertNotIn('Valid orders', {d['name'] for d in orders['refusal']['definitions']})
        finally:
            fresh.__exit__(None, None, None)


if __name__ == '__main__':
    unittest.main()
