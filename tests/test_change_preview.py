"""What a pending change does to the numbers on the boards, before it is confirmed (POST /api/workspace/impact), and the receipt after (POST /api/workspace/receipt).

Walked through the real service with two builders (Ann proposes, Bob confirms), a viewer and the admin on the planted tables. The rule every test holds: what the
preview says a card shows after confirming is what the board then shows; it is worked out by running the real confirmation on a copy of the workspace, never by a
second calculation. "Now" is the card worked out on the definitions and data versions as they were last confirmed (what the board showed before the change was put forward). Expected numbers are counted
from the planted records here, not from the service."""
import sqlite3
from unittest import mock

from ontology_poc_generator import change_preview

from tests.test_access import Client
from tests import test_batch_confirm
from tests.test_dashboards import BoardCase
from tests.test_derived_properties import CANCELLED, GROSS
from tests.test_explorer import LIVE, ORDERS
from tests.test_object_types import MEANINGS, SHIFTED, VALID, orders_upload, shifted_orders_csv
from tests.test_object_types import ORDERS as PLANTED_ORDERS

VALID_COUNT = {'id': 'valid', 'title': '有效订单数', 'query': {'type': 'order', 'view': '有效订单'}, 'chart': {'kind': 'number'}}
VALID_AMOUNT = {'id': 'amount', 'title': '有效订单金额', 'query': {'type': 'order', 'view': '有效订单'}, 'chart': {'kind': 'number', 'measure': '金额', 'fn': 'sum'}}
CUSTOMERS = {'id': 'cust', 'title': '客户数', 'query': {'type': 'customer'}, 'chart': {'kind': 'number'}}
CANCELLED_SUM = {'id': 'cancelled', 'title': '已取消合计', 'query': {'type': 'customer'}, 'chart': {'kind': 'number', 'measure': 'derived:cancelled_orders', 'fn': 'sum'}}
LINKED = {'id': 'linked', 'title': '有有效订单的客户', 'query': {'type': 'customer', 'pivot': {'relation': 'order_customer', 'side': 'from', 'source': {'type': 'order', 'view': '有效订单'}}},
          'chart': {'kind': 'number'}}
BY_STATUS = {'id': 'status', 'title': '按状态', 'query': {'type': 'order'}, 'chart': {'kind': 'bar', 'group': '状态码', 'fn': 'count'}}
ALL_AMOUNT = {'id': 'all', 'title': '全部订单金额', 'query': {'type': 'order'}, 'chart': {'kind': 'number', 'measure': '金额', 'fn': 'sum'}}
SPEC = {'components': [VALID_COUNT, VALID_AMOUNT, CUSTOMERS, CANCELLED_SUM, LINKED, BY_STATUS, ALL_AMOUNT], 'filters': []}
NOT_MADE = [*VALID['filters'], {'column': '状态码', 'op': 'is_not', 'label': '生产中'}]   # 有效订单 also leaves out what is still being made


class ImpactCase(BoardCase):
    def impact(self, client, payload, expect=200):
        status, body = client.post('/api/workspace/impact', payload)
        self.assertEqual(status, expect, body)
        return body

    def queued(self, client, element):
        status, body = client.get('/api/workspace/queue')
        self.assertEqual(status, 200, body)
        return next(i for i in body['items'] if i['element'] == element)

    def ask(self, client, element):
        """What the confirm button sends for this item: the same body goes to the preview."""
        item = self.queued(client, element)
        return {'element': element, 'version': item['version'], 'seen': item.get('seen')}

    def shown(self, client, board):
        """{card id: the figure the board shows this person now}, as the preview words it."""
        return {c['id']: change_preview.figure(c) for c in self.data(client, board)['components']}

    @staticmethod
    def by_card(body):
        return {c['card']['id']: c for c in body['cards']}

    def preview_is_reality(self, client, board, preview):
        """Every card the preview lists shows, once the change is made, what the preview said it would."""
        real = self.shown(client, board)
        for card_id, row in self.by_card(preview).items():
            self.assertEqual(row['after'], real[card_id], card_id)


class ViewTests(ImpactCase):
    def test_a_changed_view_shows_each_card_that_reads_it_now_and_after_and_confirming_gives_what_it_said(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            board = self.make(ann, spec=SPEC, scope='everyone')
            before = self.shown(bob, board['id'])
            view = bob.get('/api/workspace/types/order/views')[1]['views'][0]
            self.assertEqual(ann.post('/api/workspace/types/views/update', {**VALID, 'id': '有效订单', 'version': view['version'], 'filters': NOT_MADE})[0], 200)
            payload = self.ask(bob, 'objview:有效订单')
            preview = self.impact(bob, payload)
            self.assertIsNone(preview['refused'])
            cards = self.by_card(preview)
            self.assertEqual(sorted(cards), ['amount', 'linked', 'valid'])   # what does not read the view is not listed
            made = [r for r in ORDERS if r['状态码'] == '0']
            valid = cards['valid']
            self.assertEqual((valid['board']['name'], valid['card']['title']), ('订单看板', '有效订单数'))
            self.assertEqual((valid['now']['value'], valid['after']['value']), (len(LIVE), len(made)))
            self.assertEqual(valid['now'], before['valid'])   # now: on the definition last confirmed, as the board showed it before the change was put forward
            self.assertEqual(valid['change'], {'kind': 'number', 'delta': len(made) - len(LIVE)})
            self.assertEqual(cards['amount']['change']['delta'], sum(float(r['金额']) for r in made) - sum(float(r['金额']) for r in LIVE))
            self.assertFalse(valid['after']['grey'])
            self.assertEqual(preview['checked']['capped'], False)
            # the preview wrote nothing
            self.assertEqual(self.queued(bob, 'objview:有效订单')['state'], 'checked')
            self.assertEqual(self.data(bob, board['id'])['components'][0]['status'], 'ok')
            status, body = bob.post('/api/workspace/queue/confirm', payload)
            self.assertEqual(status, 200, body)
            self.preview_is_reality(bob, board['id'], preview)

    def test_a_definition_no_board_reads_changes_nothing_on_a_board(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            self.make(ann, spec={'components': [CUSTOMERS], 'filters': []}, scope='everyone')
            self.assertEqual(ann.post('/api/workspace/types/views', {'name': '已取消订单', 'type': 'order', 'filters': [{'column': '状态码', 'op': 'is', 'label': '已取消'}]})[0], 200)
            preview = self.impact(bob, self.ask(bob, 'objview:已取消订单'))
            self.assertEqual((preview['cards'], preview['refused']), ([], None))
            self.assertEqual((preview['checked']['boards'], preview['checked']['capped']), (1, False))

    def test_a_confirmation_that_would_be_refused_says_why_and_shows_no_numbers(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            self.make(ann, spec=SPEC, scope='everyone')
            view = bob.get('/api/workspace/types/order/views')[1]['views'][0]
            self.assertEqual(ann.post('/api/workspace/types/views/update', {**VALID, 'id': '有效订单', 'version': view['version'], 'filters': NOT_MADE})[0], 200)
            payload = self.ask(ann, 'objview:有效订单')
            mine = self.impact(ann, payload)   # Ann wrote it: confirming is not hers
            self.assertTrue(mine['refused'])
            self.assertEqual(mine['cards'], [])
            stale = self.impact(bob, {**payload, 'version': payload['version'] - 1})
            self.assertIn('刷新', stale['refused'])


class OtherKindTests(ImpactCase):
    def test_a_changed_derived_property(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            board = self.make(ann, spec=SPEC, scope='everyone')
            before = self.shown(bob, board['id'])
            line = next(d for d in bob.get('/api/workspace/types/customer/derived')[1]['derived'] if d['id'] == 'cancelled_orders')
            making = {**CANCELLED, 'conditions': [{'column': '状态码', 'op': 'is', 'label': '生产中'}], 'version': line['version']}
            self.assertEqual(ann.post('/api/workspace/types/derived/update', making)[0], 200)
            element = 'derived:customer:cancelled_orders'
            payload = self.ask(bob, element)
            preview = self.impact(bob, payload)
            cards = self.by_card(preview)
            self.assertEqual(sorted(cards), ['cancelled'])
            self.assertEqual(cards['cancelled']['now'], before['cancelled'])
            self.assertNotEqual(cards['cancelled']['after']['value'], cards['cancelled']['now']['value'])
            self.assertEqual(bob.post('/api/workspace/queue/confirm', payload)[0], 200)
            self.preview_is_reality(bob, board['id'], preview)

    def test_a_changed_relation_and_what_reads_it(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            board = self.make(ann, spec=SPEC, scope='everyone')
            before = self.shown(bob, board['id'])
            detail = bob.get('/api/workspace/relations/order_customer')[1]
            rel = {'english_name': 'order_customer', 'name': '订单属于客户', 'from': 'customer', 'to': 'order', 'cardinality': 'one_to_many', 'from_column': '客户编号', 'to_column': '客户编号'}   # turned around
            status, body = ann.post('/api/workspace/relations/update', {**rel, 'id': 'order_customer', 'version': detail['version']})
            self.assertEqual(status, 200, body)
            detail = bob.get('/api/workspace/relations/order_customer')[1]
            payload = {'element': 'relation:order_customer', 'version': detail['version'], 'seen': detail['check']['signature']}
            preview = self.impact(bob, payload)
            cards = self.by_card(preview)
            self.assertEqual(cards['linked']['now'], before['linked'])
            self.assertEqual(cards['linked']['change']['kind'], 'refuses')   # the card walks it from 订单 to 客户, which is not its way any more
            self.assertEqual(cards['cancelled']['now'], before['cancelled'])   # 已取消订单数 walks it too: it went back for another look
            self.assertEqual(bob.post('/api/workspace/queue/confirm', payload)[0], 200)
            self.preview_is_reality(bob, board['id'], preview)

    def test_changed_code_meanings(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            board = self.make(ann, spec=SPEC, scope='everyone')
            before = self.shown(bob, board['id'])
            renamed = [{**m, 'label': '制造中'} if m['value'] == '1' else m for m in MEANINGS]
            self.assertEqual(ann.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': renamed})[0], 200)
            element = 'enum:order:状态码'
            payload = self.ask(bob, element)
            preview = self.impact(bob, payload)
            cards = self.by_card(preview)
            self.assertIn('status', cards)
            self.assertEqual(cards['status']['now'], before['status'])
            self.assertIn('制造中', cards['status']['after']['text'])
            self.assertEqual(bob.post('/api/workspace/queue/confirm', payload)[0], 200)
            self.preview_is_reality(bob, board['id'], preview)

    def test_a_changed_type_whose_property_a_card_measures_is_taken_out(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            board = self.make(ann, spec=SPEC, scope='everyone')
            before = self.shown(bob, board['id'])
            order = bob.get('/api/workspace/types/order')[1]
            from tests.test_derived_properties import ORDER
            fewer = {**ORDER, 'properties': [p for p in ORDER['properties'] if p['column'] != '金额'], 'id': 'order', 'version': order['version']}
            status, body = ann.post('/api/workspace/types/update', fewer)
            self.assertEqual(status, 200, body)
            payload = self.ask(bob, 'objtype:order')
            preview = self.impact(bob, payload)
            cards = self.by_card(preview)
            self.assertEqual(cards['all']['now'], before['all'])
            self.assertEqual(cards['all']['after']['status'], 'refused')
            self.assertEqual(cards['all']['change']['kind'], 'refuses')
            self.assertEqual(bob.post('/api/workspace/queue/confirm', payload)[0], 200)
            self.preview_is_reality(bob, board['id'], preview)


class UploadTests(ImpactCase):
    def test_the_upload_preview_lists_the_cards_the_new_version_moves_and_the_upload_then_does_that(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            board = self.make(ann, spec=SPEC, scope='everyone')
            before = self.shown(bob, board['id'])
            status, preview = bob.post('/api/workspace/datasets/upload/preview', {'files': [shifted_orders_csv()]})
            self.assertEqual(status, 200, preview)
            self.assertTrue(preview['moved'])   # what it sent back, as before
            boards = preview['boards']
            cards = self.by_card(boards)
            self.assertIn('valid', cards)
            self.assertEqual(cards['valid']['now'], before['valid'])
            self.assertTrue(cards['valid']['after']['grey'])   # the new version waits for a second look
            self.assertNotIn('cust', cards)
            self.assertEqual(bob.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            self.preview_is_reality(bob, board['id'], boards)


class VisibilityTests(ImpactCase):
    def test_only_boards_the_person_may_open_and_only_their_own_questions_by_text(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            self.make(ann, '安的草稿', spec={'components': [VALID_COUNT], 'filters': []})   # private: Ann's alone
            self.make(ann, '大家的', spec={'components': [VALID_COUNT], 'filters': []}, scope='everyone')
            conn = sqlite3.connect(out / 'workspace.sqlite')
            ids = {u: i for i, u in conn.execute('SELECT id, username FROM user')}
            for who, question in ((ids['ann'], '安的秘密问题：有效订单有多少'), (ids['bob'], '鲍勃问：有效订单有多少')):
                conn.execute("INSERT INTO qa_question(user_id, asked_by, question, asked_at, status, answer_json, definitions_json, dataset_versions_json, types_json) "
                             "VALUES (?, '', ?, '2026-11-20T00:00:00+00:00', 'answered', '{}', ?, '{}', ?)",
                             (who, question, '[{"id": "objview:有效订单", "name": "有效订单"}]', '[{"id": "order", "name": "订单"}]'))
            conn.commit()
            conn.close()
            view = bob.get('/api/workspace/types/order/views')[1]['views'][0]
            self.assertEqual(ann.post('/api/workspace/types/views/update', {**VALID, 'id': '有效订单', 'version': view['version'], 'filters': NOT_MADE})[0], 200)
            status, raw = bob.call('POST', '/api/workspace/impact', self.ask(bob, 'objview:有效订单'))
            self.assertEqual(status, 200, raw)
            self.assertEqual([c['board']['name'] for c in raw['cards']], ['大家的'])
            self.assertEqual(raw['answers']['mine'], [{'id': 2, 'question': '鲍勃问：有效订单有多少'}])
            self.assertEqual(raw['answers']['others'], 1)
            self.assertNotIn('安的', str(raw))   # neither Ann's private board nor her question, by name

    def test_impact_and_receipts_are_for_builders(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            vera = team['vera']
            self.assertEqual(vera.post('/api/workspace/impact', {'element': 'objview:有效订单', 'version': 1})[0], 403)
            self.assertEqual(vera.get('/api/workspace/receipt')[0], 403)
            self.assertEqual(vera.post('/api/workspace/receipt', {'elements': ['objview:有效订单']})[0], 403)
            self.assertEqual(Client(base).post('/api/workspace/impact', {})[0], 401)

    def test_the_work_is_capped_and_says_so(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            self.make(ann, spec=SPEC, scope='everyone')
            view = bob.get('/api/workspace/types/order/views')[1]['views'][0]
            self.assertEqual(ann.post('/api/workspace/types/views/update', {**VALID, 'id': '有效订单', 'version': view['version'], 'filters': NOT_MADE})[0], 200)
            with mock.patch.object(change_preview, 'MAX_CARDS', 2):
                preview = self.impact(bob, self.ask(bob, 'objview:有效订单'))
            self.assertTrue(preview['checked']['capped'])
            self.assertEqual(preview['checked']['cards'], 2)
            self.assertGreater(preview['checked']['left'], 0)
            self.assertLessEqual(len(preview['cards']), 2)


class ReceiptTests(ImpactCase):
    def test_after_confirming_the_receipt_says_what_changed_who_proposed_and_confirmed_on_which_version_and_the_numbers_from_to(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            board = self.make(ann, spec=SPEC, scope='everyone')
            view = bob.get('/api/workspace/types/order/views')[1]['views'][0]
            self.assertEqual(ann.post('/api/workspace/types/views/update', {**VALID, 'id': '有效订单', 'version': view['version'], 'filters': NOT_MADE})[0], 200)
            payload = self.ask(bob, 'objview:有效订单')
            preview = self.impact(bob, payload)
            self.assertEqual(bob.post('/api/workspace/queue/confirm', payload)[0], 200)
            status, receipt = bob.post('/api/workspace/receipt', {'elements': ['objview:有效订单']})
            self.assertEqual(status, 200, receipt)
            item = receipt['items'][0]
            self.assertEqual((item['element'], item['proposed_by'], item['confirmed_by'], item['on']), ('objview:有效订单', 'Ann', 'Bob', {'订单': 1}))
            self.assertEqual(item['before'], '订单里只留 状态码 不是「已取消」 的行')   # as the queue words a view
            self.assertEqual(item['after'], '订单里只留 状态码 不是「已取消」，且 状态码 不是「生产中」 的行')
            cards = self.by_card(receipt)
            self.assertEqual({k: (c['now'], c['after']) for k, c in cards.items()}, {k: (c['now'], c['after']) for k, c in self.by_card(preview).items()})
            self.assertEqual(cards['valid']['change']['delta'], sum(r['状态码'] == '0' for r in ORDERS) - len(LIVE))
            self.assertEqual(ann.post('/api/workspace/receipt', {'elements': ['objview:有效订单']})[0], 200)   # builders read it too
            self.assertEqual(bob.post('/api/workspace/receipt', {'elements': ['objview:nothing']})[0], 404)

    def test_the_workspace_summary_counts_definitions_checks_rows_and_who_confirmed_what(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            bob = team['bob']
            status, summary = bob.get('/api/workspace/receipt')
            self.assertEqual(status, 200, summary)
            self.assertEqual(summary['definitions']['view'], {'confirmed': 1})
            self.assertEqual(summary['definitions']['type']['confirmed'], 6)
            self.assertGreater(summary['checks']['passed'], 0)
            self.assertEqual(summary['rows']['covered'], summary['rows']['total'] - summary['rows']['uncovered'])
            confirmed = {c['element']: c for c in summary['confirmations']}
            self.assertEqual((confirmed['objview:有效订单']['by'], confirmed['objview:有效订单']['on']), ('Bob', {'订单': 1}))


class GroupTests(ImpactCase):
    """Confirming together what one upload moved (batch_confirm): the same body the page sends goes to the preview first."""
    ops_overwrite, type_of, view_of, group, request = (test_batch_confirm.BatchConfirmTests.ops_overwrite, test_batch_confirm.BatchConfirmTests.type_of, test_batch_confirm.BatchConfirmTests.view_of,
                                                       test_batch_confirm.BatchConfirmTests.group, test_batch_confirm.BatchConfirmTests.request)

    def test_the_cards_one_upload_s_group_moves_and_confirming_it_gives_what_it_said(self):
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            ann, bob = team['ann'], team['bob']
            board = self.make(ann, spec={'components': [VALID_COUNT, BY_STATUS], 'filters': []}, scope='everyone')
            shown = self.shown(bob, board['id'])   # what the board shows Bob while the group waits: the new data's number, grey
            self.assertTrue(shown['valid']['grey'])
            body = self.request(self.group(bob))
            preview = self.impact(bob, body)
            self.assertIsNone(preview['refused'])
            cards = self.by_card(preview)
            self.assertEqual(sorted(cards), ['status', 'valid'])
            # the data sent these back: "now" is the board as it is while they wait, and confirming is what lets the new data's number count
            self.assertEqual(cards['valid']['now'], shown['valid'])
            self.assertFalse(cards['valid']['after']['grey'])
            self.assertEqual(cards['valid']['change'], {'kind': 'confirmed'})
            self.assertEqual(preview['data_moved'], [{'name': '订单', 'from': 1, 'to': 2, 'accepted': True, 'edited': True}])   # this confirmation accepts the new data, and the meanings Ann wrote again while they waited
            status, done = bob.post('/api/workspace/queue/confirm-group', body)
            self.assertEqual(status, 200, done)
            self.preview_is_reality(bob, board['id'], preview)
            status, receipt = bob.post('/api/workspace/receipt', {'elements': [c['element'] for c in done['confirmed']]})
            self.assertEqual(status, 200, receipt)
            self.assertEqual(self.by_card(receipt)['valid']['change'], {'kind': 'confirmed'})
            view = next(i for i in receipt['items'] if i['element'] == 'objview:有效订单')
            self.assertEqual(view['data_moved'], [{'name': '订单', 'from': 1, 'to': 2, 'accepted': True, 'edited': False}])

    def test_a_definition_the_data_sent_back_and_then_edited_shows_the_edit_on_the_new_data(self):
        """The data sends 有效订单 back, then Ann edits it to leave out 已交付 too. "Now" is the view as last confirmed, on the new data; "after" is the edited one: the
        96 orders the edit takes out are on the table, and the data line says both that the new data is accepted and that the definition changed."""
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            ann, bob = team['ann'], team['bob']
            board = self.make(ann, spec={'components': [VALID_COUNT], 'filters': []}, scope='everyone')
            for element in ('enum:order:状态码', 'objtype:order'):   # one by one: the group asks for all that is ready, the view too
                self.assertEqual(bob.post('/api/workspace/queue/confirm', self.ask(bob, element))[0], 200, element)
            view = self.view_of(bob, 'order', '有效订单')
            edited = [*VALID['filters'], {'column': '状态码', 'op': 'is_not', 'label': '已交付'}]
            self.assertEqual(ann.post('/api/workspace/types/views/update', {**VALID, 'id': '有效订单', 'version': view['version'], 'filters': edited})[0], 200)
            shifted = [SHIFTED[r['状态码']] for r in PLANTED_ORDERS]
            was, becomes = sum(c != '2' for c in shifted), sum(c not in ('1', '2') for c in shifted)   # last confirmed: all but 已取消; edited: all but 已取消 and 已交付
            self.assertNotEqual(was, becomes)
            payload = self.ask(bob, 'objview:有效订单')
            preview = self.impact(bob, payload)
            card = self.by_card(preview)['valid']
            self.assertEqual((card['now']['value'], card['after']['value']), (was, becomes))
            self.assertEqual(card['change'], {'kind': 'number', 'delta': becomes - was})
            self.assertEqual(preview['data_moved'], [{'name': '订单', 'from': 1, 'to': 2, 'accepted': True, 'edited': True}])
            self.assertEqual(bob.post('/api/workspace/queue/confirm', payload)[0], 200)
            self.preview_is_reality(bob, board['id'], preview)
            status, receipt = bob.post('/api/workspace/receipt', {'elements': ['objview:有效订单']})
            self.assertEqual(status, 200, receipt)
            self.assertEqual({k: (c['now'], c['after'], c['change']) for k, c in self.by_card(receipt).items()}, {'valid': (card['now'], card['after'], card['change'])})
            self.assertEqual(receipt['items'][0]['data_moved'], [{'name': '订单', 'from': 1, 'to': 2, 'accepted': True, 'edited': True}])


class HiddenColumnTests(ImpactCase):
    """A column kept from a builder (column_access) is not in what the receipts tell them: for them the type is the type without it (type_access)."""

    def hide_amount_from_all_but_ann(self, team):
        ids = self.ids(team['admin'])
        status, body = team['admin'].post('/api/workspace/column-access', {'type': 'order', 'column': '金额', 'visible_to': [ids['ann']]})
        self.assertEqual(status, 200, body)

    def test_the_receipt_of_a_type_leaves_out_a_property_kept_from_the_reader(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            self.hide_amount_from_all_but_ann(team)
            self.assertNotIn('金额', [p['column'] for p in bob.get('/api/workspace/types/order')[1]['properties']])
            status, receipt = bob.post('/api/workspace/receipt', {'elements': ['objtype:order']})
            self.assertEqual(status, 200, receipt)
            self.assertNotIn('金额', str(receipt))
            status, summary = bob.get('/api/workspace/receipt')
            self.assertEqual(status, 200, summary)
            self.assertNotIn('金额', str(summary))
            self.assertIn('金额', ann.post('/api/workspace/receipt', {'elements': ['objtype:order']})[1]['items'][0]['after'])   # Ann may read it

    def test_what_a_definition_said_before_is_not_told_when_it_read_a_column_kept_from_the_reader(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)
            self.assertEqual(self.confirm(bob, GROSS)[0], 200)
            line = self.line(bob, 'order', 'gross')
            self.assertEqual(ann.post('/api/workspace/types/derived/update', {**GROSS, 'expression': '数量 * 2', 'version': line['version']})[0], 200)
            self.assertEqual(self.confirm(bob, GROSS)[0], 200)
            self.hide_amount_from_all_but_ann(team)
            status, receipt = bob.post('/api/workspace/receipt', {'elements': ['derived:order:gross']})
            self.assertEqual(status, 200, receipt)
            item = receipt['items'][0]
            self.assertIn('数量', item['after'])
            self.assertNotIn('金额 *', str(receipt))   # the old expression read 金额 (the property's own name 含税金额 is Bob's to read)
            self.assertIsNotNone(item['before'])   # it had a version before: said to be there, not what it read


def raised(r, i):
    """The 订单 table with the first order's 金额 one higher: a new version under which every confirmed check still holds."""
    return {**r, '金额': str(int(r['金额']) + 1)} if i == 0 else r


RAISED = [raised(r, i) for i, r in enumerate(ORDERS)]


class DataBetweenConfirmationsTests(ImpactCase):
    """New data between two confirmations of a definition: the preview and the receipt compare the definition only, both on the data as it is now, and say apart that the
    data moved. A card that does not read the definition is never listed."""

    def test_an_upload_between_two_confirmations_is_not_put_on_the_change(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            board = self.make(ann, spec=SPEC, scope='everyone')
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(raised)]})[0], 200)
            self.assertEqual(self.data(bob, board['id'])['headline']['grey'], [])   # every definition is still confirmed
            before = self.shown(bob, board['id'])
            self.assertEqual(before['all']['value'], sum(float(r['金额']) for r in RAISED))
            view = bob.get('/api/workspace/types/order/views')[1]['views'][0]
            self.assertEqual(ann.post('/api/workspace/types/views/update', {**VALID, 'id': '有效订单', 'version': view['version'], 'filters': NOT_MADE})[0], 200)
            payload = self.ask(bob, 'objview:有效订单')
            preview = self.impact(bob, payload)
            cards = self.by_card(preview)
            self.assertEqual(sorted(cards), ['amount', 'linked', 'valid'])   # 全部订单金额 does not read the view
            live = [r for r in RAISED if r['状态码'] != '2']
            made = [r for r in RAISED if r['状态码'] == '0']
            self.assertEqual(cards['amount']['now'], before['amount'])   # the board as it was, on the new data
            self.assertEqual(cards['amount']['change'], {'kind': 'number', 'delta': sum(float(r['金额']) for r in made) - sum(float(r['金额']) for r in live)})
            self.assertEqual(cards['valid']['change'], {'kind': 'number', 'delta': len(made) - len(live)})
            self.assertEqual(preview['data_moved'], [{'name': '订单', 'from': 1, 'to': 2, 'accepted': False, 'edited': False}])   # said apart, not put on the change: the view stayed confirmed on it
            self.assertEqual(bob.post('/api/workspace/queue/confirm', payload)[0], 200)
            self.preview_is_reality(bob, board['id'], preview)
            status, receipt = bob.post('/api/workspace/receipt', {'elements': ['objview:有效订单']})
            self.assertEqual(status, 200, receipt)
            self.assertEqual({k: (c['now'], c['after'], c['change']) for k, c in self.by_card(receipt).items()}, {k: (c['now'], c['after'], c['change']) for k, c in cards.items()})
            self.assertEqual(receipt['items'][0]['data_moved'], [{'name': '订单', 'from': 1, 'to': 2, 'accepted': False, 'edited': False}])

    def test_without_new_data_nothing_is_said_to_have_moved(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            self.make(ann, spec=SPEC, scope='everyone')
            view = bob.get('/api/workspace/types/order/views')[1]['views'][0]
            self.assertEqual(ann.post('/api/workspace/types/views/update', {**VALID, 'id': '有效订单', 'version': view['version'], 'filters': NOT_MADE})[0], 200)
            self.assertEqual(self.impact(bob, self.ask(bob, 'objview:有效订单'))['data_moved'], [])


class CostAndReachTests(ImpactCase):
    def test_a_read_token_cannot_make_the_receipt_copy_the_workspace(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            token = team['bob'].post('/api/auth/tokens', {'label': 'agent', 'scope': 'read'})[1]['token']
            agent = Client(base)
            bearer = {'headers': {'Authorization': f'Bearer {token}'}, 'origin': None}
            self.assertEqual(agent.post('/api/workspace/receipt', {'elements': ['objview:有效订单']}, **bearer)[0], 403)
            self.assertNotEqual(agent.get('/api/workspace/receipt?element=objview:%E6%9C%89%E6%95%88%E8%AE%A2%E5%8D%95', **bearer)[0], 200)   # not by a GET either
            self.assertEqual(agent.get('/api/workspace/receipt', **bearer)[0], 200)   # the summary copies nothing

    def test_one_workspace_copy_at_a_time(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            view = bob.get('/api/workspace/types/order/views')[1]['views'][0]
            self.assertEqual(ann.post('/api/workspace/types/views/update', {**VALID, 'id': '有效订单', 'version': view['version'], 'filters': NOT_MADE})[0], 200)
            payload = self.ask(bob, 'objview:有效订单')
            with mock.patch.object(change_preview, 'SLOT_WAIT', 0.05), change_preview.copy_slot(out / 'workspace.sqlite'):
                busy = self.impact(bob, payload, expect=429)
            self.assertIn('稍后', busy['error'])
            self.assertIsNone(self.impact(bob, payload)['refused'])   # free again

    def test_other_people_s_answers_on_a_definition_the_confirmer_cannot_see_are_not_counted(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            ids = self.ids(admin)
            conn = sqlite3.connect(out / 'workspace.sqlite')
            for definitions, types in (('[{"id": "derived:customer:cancelled_orders"}]', '[{"id": "customer"}]'), ('[{"id": "objtype:order"}]', '[{"id": "order"}]')):
                conn.execute("INSERT INTO qa_question(user_id, asked_by, question, asked_at, status, answer_json, definitions_json, dataset_versions_json, types_json) "
                             "VALUES (?, '', 'q', '2026-11-20T00:00:00+00:00', 'answered', '{}', ?, '{}', ?)", (ids['ann'], definitions, types))
            conn.commit()
            conn.close()
            status, body = admin.post('/api/workspace/permissions', {'type': 'customer', 'visible_to': [ids['ann']]})
            self.assertEqual(status, 200, body)
            from tests.test_derived_properties import ORDER
            order = bob.get('/api/workspace/types/order')[1]
            fewer = {**ORDER, 'properties': [p for p in ORDER['properties'] if p['column'] != '交付天数'], 'id': 'order', 'version': order['version']}
            self.assertEqual(ann.post('/api/workspace/types/update', fewer)[0], 200)
            preview = self.impact(bob, self.ask(bob, 'objtype:order'))
            self.assertEqual(preview['answers'], {'mine': [], 'others': 1})   # the answer on 订单, not the one on 客户's property that Bob cannot see


if __name__ == '__main__':
    import unittest
    unittest.main()
