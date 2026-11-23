"""The invariant: a definition's own name is never muted. Everything main hears through names, a question is heard to say with other names present too; other names
can only add hearing, and a longer name can only take away hearing that an other name added (the other name inside it, at that place, of a definition the asker
may see). So the definitions heard through names alone are the same with other names present and absent, for any question.

Numbers are those of docs/pilot/sample: every order 162,960 (150), valid orders 119,810."""
import itertools
import json
import sqlite3
import unittest

from ontology_poc_generator import accounts, other_names, workspace_questions
from ontology_poc_generator.workspace_store import open_workspace
from tests import test_derived_new_values as pilot
from tests.test_demo_mode import a_guest
from tests.test_demo_view_waits import Seeded
from tests.test_derived_properties import TICKET
from tests.test_object_types import ORDER
from tests.test_one_number import SUM_AMOUNT, Planted, Scripted, item, setUpModule, tearDownModule  # noqa: F401  (the caps of the module)
from tests.test_other_names import DemoAsker
from tests.test_workspace_questions import ALL_ORDERS
from unittest import mock

PILOT_SUM = {**SUM_AMOUNT, 'start': 'order'}


class PilotWithOtherNames(pilot.PilotFoundation):
    """The pilot's definitions with other names that hold their names inside them: 有效订单总额 on the derived property 有效订单金额 (the view's name 有效订单 inside),
    已取消标记 on status_code (the meaning's name 已取消 inside), 客户号 on customer_id (the type's name 客户 inside), and a few more."""

    def named(self, base):
        team = self.foundation(base)
        ann = team['ann']
        line = self.line(ann)
        status, body = ann.post('/api/workspace/types/derived/update', {**pilot.VALID_AMOUNT, 'version': line['version'], 'other_names': ['有效订单总额']})
        self.assertEqual((status, body.get('state')), (200, 'checked'), body)   # new other names wait for a second person, as any change does
        now = ann.get('/api/workspace/types/order')[1]
        others = {'customer_id': ['客户号'], 'status_code': ['已取消标记']}
        props = [{'column': p['column'], **({'enum': True} if p['enum'] else {}), **({'other_names': others[p['column']]} if p['column'] in others else {})} for p in now['properties'] if p['column'] != 'order_id']
        status, body = ann.post('/api/workspace/types/update', {**pilot.ORDER, 'id': 'order', 'version': now['version'], 'properties': props, 'other_names': ['销售单']})
        self.assertEqual((status, body.get('state')), (200, 'checked'), body)
        view = self.view(ann)
        self.assertEqual(ann.post('/api/workspace/types/views/update', {**pilot.VIEW, 'id': '有效订单', 'version': view['version'], 'other_names': ['好订单']})[0], 200)
        reconfirm(self, team['bob'])
        return team

    def ask(self, client, model, question, reply):
        model.replies = [reply]
        status, body = client.post('/api/workspace/ask', {'question': question})
        self.assertEqual(status, 200, body)
        return body


def reconfirm(case, bob):
    """Bob, who changed none of it, confirms again what Ann's other names sent back, and what stands on it: the order type, the relation, the view, the derived property."""
    shown = bob.get('/api/workspace/types/order')[1]
    case.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen']})[0], 200)
    relation = bob.get('/api/workspace/relations/order_customer')[1]
    if relation['state'] != 'confirmed':
        case.assertEqual(bob.post('/api/workspace/relations/confirm', {'id': 'order_customer', 'version': relation['version'], 'seen': relation['check']['signature']})[0], 200)
    view = case.view(bob)
    case.assertEqual(bob.post('/api/workspace/types/views/confirm', {'id': '有效订单', 'version': view['version'], 'seen': view['seen']})[0], 200)
    line = case.line(bob)
    case.assertEqual(bob.post('/api/workspace/types/derived/confirm', {'type': 'customer', 'english_name': 'valid_amount', 'version': line['version'], 'seen': line['seen']})[0], 200)


class AcceptanceCaseTests(PilotWithOtherNames):
    def test_a_name_inside_a_longer_other_name_is_heard_as_main_hears_it(self):
        model = Scripted(item(PILOT_SUM))
        with self.service(gateway=model) as (base, out):
            ann = self.named(base)['ann']
            body = self.ask(ann, model, '有效订单总额是多少？', item(PILOT_SUM))   # the view's name 有效订单 inside the derived property's other name
            self.assertEqual((body['status'], [u['definition'] for u in body['unmet']]), ('definition_unmet', ['有效订单']))
            body = self.ask(ann, model, '已取消标记的订单有多少？', item({**ALL_ORDERS}))   # the meaning's name 已取消 inside the property's other name
            self.assertEqual((body['status'], [u['definition'] for u in body['unmet']]), ('definition_unmet', ['已取消']))
            body = self.ask(ann, model, '有效订单金额是多少？', item(PILOT_SUM))   # two names, one inside the other, with other names about: heard as on main
            self.assertEqual(body['status'], 'definition_unmet')
            with mock.patch.object(other_names, 'HEARD', False):
                for question in ('有效订单总额是多少？', '有效订单金额是多少？'):
                    self.assertEqual(self.ask(ann, model, question, item(PILOT_SUM))['status'], 'definition_unmet', question)

    def test_the_names_heard_alone_are_the_same_with_other_names_present_and_absent(self):
        model = Scripted(item(PILOT_SUM))
        with self.service(gateway=model) as (base, out):
            self.named(base)
            conn = open_workspace(out / 'workspace.sqlite')
            try:
                ann = accounts.get_user(conn, conn.execute("SELECT id FROM user WHERE username = 'ann'").fetchone()[0])
                seen = workspace_questions._seen_names(conn, ann)
                texts = sorted({e['text'] for e in seen})
                self.assertTrue({'有效订单总额', '已取消标记', '客户号', '销售单', '好订单', '有效订单', '已取消', '客户', '订单'} <= set(texts))
                chinese = [t for t in texts if not t.isascii()]
                questions = [*texts, *(a + b for a, b in itertools.permutations(chinese, 2)), *(f'{a}的{b}有多少？' for a, b in itertools.permutations(chinese, 2))]

                def by_names(question):
                    muted = workspace_questions._muted(conn, ann, question)
                    return {e['key'] for e in seen if not e['other'] and workspace_questions._named(question, e['text']) and (e['key'], e['text']) not in muted}
                for question in questions:
                    with mock.patch.object(other_names, 'HEARD', False):
                        absent = by_names(question)
                    self.assertEqual(by_names(question), absent, question)
                    self.assertFalse([t for k, t in workspace_questions._muted(conn, ann, question) if (k, t) in {(e['key'], e['text']) for e in seen if not e['other']}], question)
                self.assertGreater(len(questions), 300)
            finally:
                conn.close()


class OverlapTests(unittest.TestCase, DemoAsker):
    """Two names that overlap without one holding the other mute nothing: 有效订单号 holds 有效订单 (the view's other name) and 订单号 (a property's), neither inside the
    other, so the view is heard."""

    def test_overlapping_names_both_stay(self):
        demo = Seeded().__enter__()
        try:
            body = self.ask(demo, a_guest(demo.base), '有效订单号有多少个？', item(ALL_ORDERS))[1]
            self.assertEqual((body['status'], [u['definition'] for u in body['unmet']]), ('definition_unmet', ['Valid orders']))
        finally:
            demo.__exit__(None, None, None)


class VisibilityOfMutingTests(Planted):
    """Only a longer name of a definition the asker may see mutes: a type kept from Bob, or a column kept from him, takes away nothing he would hear."""

    def test_a_longer_name_of_a_type_kept_from_the_asker_mutes_nothing(self):
        model = Scripted(item(ALL_ORDERS))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, admin = team['ann'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types', {**ORDER, 'other_names': ['单据']})[0], 200)   # put forward, not confirmed
            ticket = {**TICKET, 'properties': [{'column': '订单号'}, {'column': '问题类型', 'other_names': ['售后单据']}]}
            self.assertEqual(ann.post('/api/workspace/types', ticket)[0], 200)
            ann_id = next(u['id'] for u in admin.get('/api/users')[1]['users'] if u['username'] == 'ann')
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'ticket', 'visible_to': [ann_id]})[0], 200)
            kind = lambda body: (body.get('refusal') or {}).get('kind')   # nothing is confirmed yet: the scope is empty; what matters is whether 单据 names the order type
            self.assertNotEqual(kind(self.ask(ann, '售后单据有多少？')[1]), 'unsettled')   # Ann sees the ticket's 售后单据: 单据 there is its
            self.assertEqual(kind(self.ask(team['bob'], '售后单据有多少？')[1]), 'unsettled')   # Bob does not: 单据 names the order type, which is not confirmed

    def test_a_property_in_a_column_kept_from_the_asker_mutes_nothing(self):
        model = Scripted(item(ALL_ORDERS))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, admin = team['ann'], team['admin']
            order = {**ORDER, 'other_names': ['单据'], 'properties': [{'column': '订单号'}, {'column': '金额', 'name': '单据金额'}, {'column': '状态码', 'enum': True}]}
            self.assertEqual(ann.post('/api/workspace/types', order)[0], 200)
            ann_id = next(u['id'] for u in admin.get('/api/users')[1]['users'] if u['username'] == 'ann')
            self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'order', 'column': '金额', 'visible_to': [ann_id]})[0], 200)
            kind = lambda body: (body.get('refusal') or {}).get('kind')
            self.assertNotEqual(kind(self.ask(ann, '单据金额是多少？')[1]), 'unsettled')
            self.assertEqual(kind(self.ask(team['bob'], '单据金额是多少？')[1]), 'unsettled')


class SavedBeforeTests(unittest.TestCase, DemoAsker):
    """A workspace saved by an earlier build may hold a pair refused when saved now (here the meaning Cancelled also called 有效订单, the view's other name): it opens
    and answers; a question that says the shared name names both; an edit that leaves the view's other names as they are saves; saving the meanings with the clash
    in them is refused, saying it; taking it away saves."""

    def test_it_opens_answers_and_says_the_clash_on_save(self):
        demo = Seeded().__enter__()
        try:
            conn = sqlite3.connect(demo.folder / 'workspace.sqlite')
            content = json.loads(conn.execute("SELECT content_json FROM element_state WHERE element_id = 'enum:order:status_code'").fetchone()[0])
            content['values'] = [{**v, 'other_names': ['已取消', '有效订单']} if v['label'] == 'Cancelled' else v for v in content['values']]
            conn.execute("UPDATE element_state SET content_json = ? WHERE element_id = 'enum:order:status_code'", (json.dumps(content, ensure_ascii=False, sort_keys=True),))
            conn.commit()
            conn.close()
            admin, guest = demo.admin('en'), a_guest(demo.base, 'en')
            status, page = admin.call('GET', '/api/workspace/types/order')
            self.assertEqual(status, 200)
            self.assertEqual(next(v for v in next(p for p in page['properties'] if p['column'] == 'status_code')['meanings']['values'] if v['label'] == 'Cancelled')['other_names'], ['已取消', '有效订单'])
            body = self.ask(demo, guest, 'Valid orders 的总金额是多少？', item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': 'x'}]))[1]
            self.assertEqual((body['status'], body['answer']['measure']['value']), ('answered', 119810))
            body = self.ask(demo, guest, '有效订单有多少？', item(ALL_ORDERS))[1]
            self.assertEqual((body['status'], sorted(u['definition'] for u in body['unmet'])), ('definition_unmet', ['Cancelled', 'Valid orders']))
            view = next(v for v in admin.call('GET', '/api/workspace/types/order/views')[1]['views'] if v['name'] == 'Valid orders')
            status, body = admin.call('POST', '/api/workspace/types/views/update', {'id': 'Valid orders', 'version': view['version'], 'type': 'order', 'filters': view['filters'], 'description': 'changed'})
            self.assertEqual((status, body.get('state')), (200, 'checked'), body)   # saved; a new description waits for a second person, as any change does
            status, body = admin.call('POST', '/api/workspace/types/meanings', {'id': 'order', 'column': 'status_code', 'values': [{'value': '1', 'label': 'Paid', 'other_names': ['已付款', '付清']}]})
            self.assertEqual(status, 409, body)
            self.assertIn('有效订单', body['error'])
            values = [{'value': '4', 'label': 'Cancelled', 'other_names': ['已取消']}]
            self.assertEqual(admin.call('POST', '/api/workspace/types/meanings', {'id': 'order', 'column': 'status_code', 'values': values})[0], 200)
        finally:
            demo.__exit__(None, None, None)


if __name__ == '__main__':
    unittest.main()
