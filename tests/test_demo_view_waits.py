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

from ontology_poc_generator import accounts, demo
from ontology_poc_generator.ontology_server import make_server
from ontology_poc_generator.workspace_store import open_workspace
from tests.test_demo_mode import a_guest, signed_in
from tests.test_derived_new_values import part
from tests.test_workspace_questions import AskModel

BUILDER_PW = 'a builder password for tests'
ALL_BUT = {'start': 'order', 'where': [{'field': 'status_code', 'not_equals': ['Cancelled', 'Refunded']}], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': 'amount', 'op': 'sum'}}
ALL_BUT_USED = [{'id': f'orders.status_code={label}', 'direction': 'exclude', 'basis': 'valid'} for label in ('Cancelled', 'Refunded')]


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

    def test_a_guests_question_naming_the_waiting_view_is_refused_before_the_model_with_its_name_and_whom_it_waits_for(self):
        for lang in ('en', 'zh-CN'):
            guest = a_guest(self.demo.base, lang)
            asked = len(self.demo.model.requests)
            status, body = guest.call('POST', '/api/workspace/ask', {'question': 'What is the total amount of valid orders?'})
            self.assertEqual(status, 200, body)
            self.assertEqual(len(self.demo.model.requests), asked, 'the model was asked')
            self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'unsettled'), body)
            [line] = body['refusal']['definitions']
            self.assertEqual((line['kind'], line['name'], line['who_can_confirm']), ('view', 'Valid orders', ['Demo builder']))
            self.assertLessEqual(set(line), {'id', 'kind', 'name', 'state', 'waiting', 'who_can_confirm', 'because', 'text', 'type'})
            self.assertIn('Demo builder', body['reason'])
            for secret in ('Paid', 'Cancelled', 'status_code', 'demo-admin'):   # what changed and who changed it is not the guest's
                self.assertNotIn(secret, said(body), lang)
            self.assertNotRegex(said(body), r'\d')

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


class UploadedOrdersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = Seeded().__enter__()
        status, body = cls.demo.admin().call('POST', '/api/workspace/datasets/upload', {'files': [part('orders_update.csv', target='orders', mode='update_by_key', key_columns=['order_id'])]})
        assert status == 200, body

    @classmethod
    def tearDownClass(cls):
        cls.demo.__exit__(None, None, None)

    def test_a_guest_with_nothing_confirmed_in_scope_is_told_what_waits_and_for_whom(self):
        guest = a_guest(self.demo.base)
        self.assertEqual(guest.call('GET', '/api/workspace/types')[1]['types'][1]['state'], 'needs_look')
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


if __name__ == '__main__':
    unittest.main()
