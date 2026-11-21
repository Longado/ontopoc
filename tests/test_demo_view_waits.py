"""The demo workspace after a person changes the confirmed view Valid orders, and after an upload sends Order back for a second look: what a guest and a builder
are told. A question that names a view which is not confirmed now is refused before the model, naming it and who it waits for (a viewer only for a view that was
confirmed once); a question that names no view is answered from the model's own filter on the confirmed meanings, and nothing in the answer says a view was used;
the board says the view waits and for whom; a guest whose scope is empty after an upload is told what waits and for whom; a type whose key check fails is not
counted or offered as one a builder can confirm now. Numbers are those of docs/pilot/sample/orders.csv."""
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from ontology_poc_generator import accounts, demo, workspace_questions
from ontology_poc_generator.ontology_server import make_server
from ontology_poc_generator.workspace_store import open_workspace
from tests.test_demo_mode import a_guest, signed_in
from tests.test_derived_new_values import part
from tests.test_workspace_questions import AskModel

BUILDER_PW = 'a builder password for tests'
ALL_BUT = {'start': 'order', 'where': [{'field': 'status_code', 'not_equals': ['Cancelled', 'Refunded']}], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': 'amount', 'op': 'sum'}}
ALL_BUT_USED = [{'id': f'orders.status_code={label}', 'direction': 'exclude', 'basis': 'valid'} for label in ('Cancelled', 'Refunded')]


_PER_ADDRESS = demo.GUEST_PER_ADDRESS


def setUpModule():   # every guest here comes from 127.0.0.1: the hourly cap per address is not what these tests are about
    demo.GUEST_PER_ADDRESS = 100


def tearDownModule():
    demo.GUEST_PER_ADDRESS = _PER_ADDRESS


class Seeded:
    """A seeded demo served in demo mode with a fake model (`model.item` is what it writes), Demo builder signed in again with a known password."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / 'demo'
        self.password = demo.seed(self.folder)['password']
        conn = open_workspace(self.folder / 'workspace.sqlite')
        try:   # the seed leaves Demo builder disabled; the walk-through confirms as them
            builder = conn.execute("SELECT id FROM user WHERE username = 'demo-builder'").fetchone()[0]
            conn.execute('UPDATE user SET disabled = 0 WHERE id = ?', (builder,))
            accounts.reset_password(conn, 'test', builder, BUILDER_PW, must_change=False)
            conn.commit()
        finally:
            conn.close()
        self.model = AskModel({'reasoning': 'test'})
        self.server = make_server(port=0, gateway=self.model, output_dir=self.folder, demo=True)
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def admin(self, lang='zh-CN'):
        return signed_in(self.base, self.password, lang=lang)

    def builder(self, lang='zh-CN'):
        return signed_in(self.base, BUILDER_PW, name='demo-builder', lang=lang)


def change_the_view(admin):
    """demo-admin also leaves Paid out of Valid orders: the view is put forward again, waiting for Demo builder."""
    view = next(v for v in admin.call('GET', '/api/workspace/types/order/views')[1]['views'] if v['name'] == 'Valid orders')
    filters = [*view['filters'], {'column': 'status_code', 'op': 'is_not', 'label': 'Paid'}]
    status, body = admin.call('POST', '/api/workspace/types/views/update', {'id': 'Valid orders', 'version': view['version'], 'type': 'order', 'filters': filters})
    assert status == 200 and body['state'] == 'checked', body


def said(body) -> str:
    return json.dumps({k: body.get(k) for k in ('reason', 'refusal', 'steps', 'definitions', 'types', 'datasets')}, ensure_ascii=False)


class ChangedViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = Seeded().__enter__()
        change_the_view(cls.demo.admin())

    @classmethod
    def tearDownClass(cls):
        cls.demo.__exit__(None, None, None)

    def test_a_guests_question_naming_the_waiting_view_is_refused_before_the_model_told_only_that_it_waits(self):
        for lang in ('en', 'zh-CN'):
            guest = a_guest(self.demo.base, lang)
            asked = len(self.demo.model.requests)
            status, body = guest.call('POST', '/api/workspace/ask', {'question': 'What is the total amount of valid orders?'})
            self.assertEqual(status, 200, body)
            self.assertEqual(len(self.demo.model.requests), asked, 'the model was asked')
            self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'unsettled'), body)
            [line] = body['refusal']['definitions']
            self.assertEqual((line['kind'], line['waiting']), ('view', True))
            self.assertLessEqual(set(line), {'kind', 'state', 'waiting', 'text'})   # a viewer is not told names: no id, no name, nobody it waits for
            for secret in ('Valid orders', 'Demo builder', 'Paid', 'Cancelled', 'status_code', 'demo-admin'):
                self.assertNotIn(secret, said(body), lang)
            self.assertNotRegex(said(body), r'\d')

    def test_with_viewers_told_what_waits_the_guest_hears_the_view_and_whom_it_waits_for(self):
        with mock.patch.object(workspace_questions, 'VIEWERS_TOLD_WHAT_WAITS', True):
            status, body = a_guest(self.demo.base, 'en').call('POST', '/api/workspace/ask', {'question': 'What is the total amount of valid orders?'})
        self.assertEqual(status, 200, body)
        [line] = body['refusal']['definitions']
        self.assertEqual((line['kind'], line['name'], line['who_can_confirm']), ('view', 'Valid orders', ['Demo builder']))
        self.assertLessEqual(set(line), {'id', 'kind', 'name', 'state', 'waiting', 'who_can_confirm', 'because', 'text', 'type'})
        self.assertIn('Demo builder', body['reason'])
        for secret in ('Paid', 'Cancelled', 'status_code', 'demo-admin'):   # what changed and who changed it is not the guest's
            self.assertNotIn(secret, said(body))

    def test_a_builders_question_naming_the_view_is_refused_naming_it_and_who_can_confirm(self):
        asked = len(self.demo.model.requests)
        status, body = self.demo.admin('en').call('POST', '/api/workspace/ask', {'question': 'What is the total amount of valid orders?'})
        self.assertEqual(status, 200, body)
        self.assertEqual(len(self.demo.model.requests), asked)
        self.assertEqual(body['refusal']['kind'], 'unsettled', body)
        line = next(d for d in body['refusal']['definitions'] if d['kind'] == 'view')
        self.assertEqual((line['name'], line['who_can_confirm']), ('Valid orders', ['Demo builder']))

    def test_a_question_that_names_no_view_is_answered_from_the_models_filter_and_claims_no_view(self):
        self.demo.model.item = {'reasoning': 'not cancelled or refunded', 'query': ALL_BUT, 'definitions_used': ALL_BUT_USED}
        try:
            status, body = a_guest(self.demo.base).call('POST', '/api/workspace/ask', {'question': '有效订单的总金额是多少？'})
        finally:
            self.demo.model.item = {'reasoning': 'test'}
        self.assertEqual(status, 200, body)
        self.assertEqual((body['status'], body['answer']['measure']['value']), ('answered', 124790), body.get('reason'))   # 114 orders: neither 119,810 nor 109,040
        self.assertNotIn('view', [d['kind'] for d in body['definitions']])
        self.assertFalse((body.get('evidence') or {}).get('views'))
        self.assertIn('NOT IN', body['query_text'])   # the filter the caliber line quotes as the model's

    def test_a_view_nobody_ever_confirmed_is_not_named_to_a_guest(self):
        admin = self.demo.admin()
        self.assertEqual(admin.call('POST', '/api/workspace/types/views', {'name': 'Big orders', 'type': 'order', 'filters': [{'column': 'status_code', 'op': 'is', 'label': 'Delivered'}]})[0], 200)
        asked = len(self.demo.model.requests)
        status, body = a_guest(self.demo.base, 'en').call('POST', '/api/workspace/ask', {'question': 'Total of big orders?'})
        self.assertEqual(status, 200, body)
        self.assertEqual(len(self.demo.model.requests), asked + 1)   # on to the model: nothing said of it
        self.assertNotIn('Big orders', said(body))

    def test_a_name_with_latin_letters_and_chinese_is_matched_whatever_the_case(self):
        admin, builder = self.demo.admin(), self.demo.builder()
        status, body = admin.call('POST', '/api/workspace/types/views', {'name': 'VIP大单', 'type': 'order', 'filters': [{'column': 'status_code', 'op': 'is', 'label': 'Delivered'}]})
        self.assertEqual(status, 200, body)
        view = next(v for v in builder.call('GET', '/api/workspace/types/order/views')[1]['views'] if v['name'] == 'VIP大单')
        self.assertEqual(builder.call('POST', '/api/workspace/types/views/confirm', {'id': 'VIP大单', 'version': view['version'], 'seen': view['seen']})[0], 200)
        view = next(v for v in admin.call('GET', '/api/workspace/types/order/views')[1]['views'] if v['name'] == 'VIP大单')
        status, body = admin.call('POST', '/api/workspace/types/views/update', {'id': 'VIP大单', 'version': view['version'], 'type': 'order', 'filters': [{'column': 'status_code', 'op': 'is', 'label': 'Shipped'}]})
        self.assertEqual((status, body.get('state')), (200, 'checked'), body)
        for question in ('VIP大单的总金额？', 'vip大单的总金额？', 'Vip大单的总金额？'):
            asked = len(self.demo.model.requests)
            with mock.patch.object(workspace_questions, 'VIEWERS_TOLD_WHAT_WAITS', True):   # so the refusal says which view it matched
                status, body = a_guest(self.demo.base).call('POST', '/api/workspace/ask', {'question': question})
            self.assertEqual(status, 200, body)
            self.assertEqual(len(self.demo.model.requests), asked, question)
            self.assertEqual([(d['kind'], d['name']) for d in body['refusal']['definitions']], [('view', 'VIP大单')], question)

    def test_the_board_says_the_definition_was_changed_not_that_the_data_moved(self):
        guest = a_guest(self.demo.base)
        board = guest.call('GET', '/api/workspace/dashboards')[1]['dashboards'][0]
        body = guest.call('POST', '/api/workspace/dashboards/data', {'id': board['id'], 'bar': {}})[1]
        message = next(c for c in body['components'] if c['id'] == 'valid_amount')['message']
        self.assertTrue(message.startswith('定义改了'), message)

    def test_the_guests_board_says_the_view_waits_and_for_whom(self):
        guest = a_guest(self.demo.base)
        board = guest.call('GET', '/api/workspace/dashboards')[1]['dashboards'][0]
        body = guest.call('POST', '/api/workspace/dashboards/data', {'id': board['id'], 'bar': {}})[1]
        by_id = {c['id']: c for c in body['components']}
        for key in ('valid_amount', 'valid_count', 'by_status'):
            self.assertEqual(by_id[key]['status'], 'waiting', by_id[key])
            self.assertIn('Demo builder', by_id[key]['message'])
            self.assertNotIn('没有叫', by_id[key]['message'])
        self.assertEqual((by_id['all_amount']['status'], by_id['all_amount']['result']['value']), ('ok', 162960))


class NotTheViewersViewTests(unittest.TestCase):
    """A changed view is named to a viewer only when it would be theirs to read once confirmed: not when it reads a column kept from them, not when its type
    is not open to them."""

    def ask_after(self, change):
        with Seeded() as demo:
            admin = demo.admin()
            change_the_view(admin)
            ids = {u['username']: u['id'] for u in admin.call('GET', '/api/users')[1]['users']}
            change(admin, ids)
            status, body = a_guest(demo.base, 'en').call('POST', '/api/workspace/ask', {'question': 'What is the total amount of valid orders?'})
            self.assertEqual(status, 200, body)
            return body

    def test_a_view_that_reads_a_column_kept_from_the_viewer_is_not_named(self):
        body = self.ask_after(lambda admin, ids: self.assertEqual(admin.call('POST', '/api/workspace/column-access', {'type': 'order', 'column': 'status_code', 'visible_to': [ids['demo-builder']]})[0], 200))
        self.assertNotIn('Valid orders', said(body))

    def test_a_view_whose_type_is_not_open_to_the_viewer_is_not_named(self):
        body = self.ask_after(lambda admin, ids: self.assertEqual(admin.call('POST', '/api/workspace/permissions', {'type': 'order', 'visible_to': [ids['demo-builder']]})[0], 200))
        self.assertNotIn('Valid orders', said(body))


class UploadedOrdersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = Seeded().__enter__()
        status, body = cls.demo.admin().call('POST', '/api/workspace/datasets/upload', {'files': [part('orders_update.csv', target='orders', mode='update_by_key', key_columns=['order_id'])]})
        assert status == 200, body

    @classmethod
    def tearDownClass(cls):
        cls.demo.__exit__(None, None, None)

    def test_a_guest_with_nothing_confirmed_in_scope_is_told_only_that_definitions_wait(self):
        guest = a_guest(self.demo.base)
        self.assertEqual(guest.call('GET', '/api/workspace/types')[1]['types'][1]['state'], 'needs_look')
        status, body = guest.call('POST', '/api/workspace/ask', {'question': '有效订单的总金额是多少？'})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['status'], 'refused', body)
        self.assertIn('在等再确认', body['reason'])
        for secret in ('Demo builder', 'Order', 'Valid orders'):
            self.assertNotIn(secret, said(body))
        self.assertTrue(all(set(d) <= {'kind', 'state', 'waiting', 'text'} for d in body['refusal']['left_out']), body['refusal']['left_out'])
        self.assertNotRegex(said(body), r'\d')

    def test_with_viewers_told_what_waits_a_guest_with_nothing_in_scope_hears_what_waits_and_for_whom(self):
        guest = a_guest(self.demo.base)
        with mock.patch.object(workspace_questions, 'VIEWERS_TOLD_WHAT_WAITS', True):
            status, body = guest.call('POST', '/api/workspace/ask', {'question': '有效订单的总金额是多少？'})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['status'], 'refused', body)
        self.assertIn('Demo builder', body['reason'])
        named = {(d['kind'], d['name']): d.get('who_can_confirm') for d in body['refusal']['left_out']}
        self.assertEqual(named[('type', 'Order')], ['Demo builder'])
        self.assertNotRegex(said(body), r'\d')   # no count, no code, no version


class FailingKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = Seeded().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.demo.__exit__(None, None, None)

    def test_a_type_whose_key_check_fails_is_not_counted_or_offered_as_confirmable_now(self):
        builder = self.demo.builder()
        queue = builder.call('GET', '/api/workspace/queue')[1]
        customer = next(i for i in queue['items'] if i['element'] == 'objtype:customer')
        self.assertFalse(customer['can_confirm'], customer)
        self.assertEqual(queue['count'], sum(1 for i in queue['items'] if i['can_confirm']))
        self.assertEqual(builder.call('GET', '/api/workspace/queue?count=1')[1]['count'], 0)
        listed = {t['id']: t for t in builder.call('GET', '/api/workspace/types')[1]['types']}
        self.assertFalse(listed['customer']['can_confirm'])
        shown = builder.call('GET', '/api/workspace/types/customer')[1]
        self.assertFalse(shown['can_confirm'])
        status, body = builder.call('POST', '/api/workspace/types/confirm', {'id': 'customer', 'version': shown['version'], 'seen': shown['seen']})
        self.assertEqual(status, 409, body)   # the confirm path refuses it too
        self.assertIn('C012', body['error'] if 'error' in body else json.dumps(body, ensure_ascii=False))

    def test_the_upload_group_does_not_plan_a_type_whose_checks_fail_or_what_stands_on_it(self):
        builder = self.demo.builder()
        status, group = builder.call('GET', '/api/workspace/queue/group?dataset=customers&version=2')
        self.assertEqual(status, 200, group)
        by = {i['element']: i for i in group['items']}
        customer, relation = by['objtype:customer'], by['relation:order_customer']
        self.assertFalse(customer['ready'], customer)
        self.assertIn('C012', customer['why_not'])   # why: the check it fails, as confirming would say
        self.assertFalse(relation['ready'], relation)
        self.assertIn('Customer', relation['why_not'])   # it waits on Customer
        items = [{'element': i['element'], 'version': i['version'], 'seen': i['seen']} for i in group['items']]
        status, body = builder.call('POST', '/api/workspace/queue/confirm-group', {'dataset': 'customers', 'version': 2, 'items': items})
        self.assertEqual(status, 409, body)
        self.assertNotIn('你也能确认', body.get('error', ''))   # nothing here is the builder's to confirm now, and it does not say otherwise

    def test_reading_whether_a_type_can_be_confirmed_writes_no_check(self):
        count = lambda: sqlite3.connect(self.demo.folder / 'workspace.sqlite').execute('SELECT COUNT(*) FROM check_result').fetchone()[0]
        before = count()
        builder = self.demo.builder()
        for path in ('/api/workspace/queue', '/api/workspace/queue?count=1', '/api/workspace/types', '/api/workspace/types/customer'):
            self.assertEqual(builder.call('GET', path)[0], 200, path)
        self.assertEqual(count(), before)   # a page read keeps no check result


if __name__ == '__main__':
    unittest.main()
