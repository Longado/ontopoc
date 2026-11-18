"""The assistant's builder-mode turns are kept per person with a compact card, checked against what the reader may still see when opened, and can be deleted."""
import json

from ontology_poc_generator import assistant_history
from ontology_poc_generator.workspace_store import open_workspace
from tests import test_workspace_questions as questions   # the module, so its test classes are not collected a second time here
from tests.test_two_person import SigningTestCase

PROPOSAL = {'proposed': [{'id': 'order', 'name': '订单', 'dataset': '订单', 'key': ['订单号']}], 'rejected': [], 'self_check': {'done': [{'key': 'checked'}], 'not_done': []},
            'raw': 'the model said this word for word'}
PLAN = {'steps': [{'id': 's1', 'summary': 'keep', 'step': {'type': 'input', 'dataset': '订单'}, 'rows_in': [3], 'rows_out': 2, 'samples': [{'订单号': 'X1'}]}],
        'assumptions': [{'text': 'a', 'status': 'confirmed'}], 'self_check': {'done': [], 'not_done': []}, 'raw': {'x': 1}}


def turn(mode='model', message='suggest types', scope=None, card=None):
    return {'mode': mode, 'message': message, 'scope': scope if scope is not None else {'datasets': ['订单']}, 'card': card if card is not None else PROPOSAL}


class AssistantHistoryTests(SigningTestCase):
    team, confirm, confirmed_orders = questions.QuestionTests.team, questions.QuestionTests.confirm, questions.QuestionTests.confirmed_orders

    def test_a_turn_is_the_persons_own_with_a_compact_card_and_can_be_marked_and_deleted(self):
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.confirmed_orders(team)
            status, made = ann.post('/api/workspace/assistant/turns', turn())
            self.assertEqual(status, 200, made)
            status, plan = ann.post('/api/workspace/assistant/turns', turn('pipeline', 'filter', {'target': {'kind': 'dataset', 'name': '订单', 'label': '订单'}}, PLAN))
            self.assertEqual(status, 200, plan)
            listed = ann.get('/api/workspace/assistant/turns')[1]['turns']
            self.assertEqual([(t['mode'], t['message'], t['outcome']) for t in listed], [('pipeline', 'filter', None), ('model', 'suggest types', None)])
            self.assertNotIn('card', listed[0])
            status, shown = ann.get(f'/api/workspace/assistant/turns/{made["id"]}')
            self.assertEqual(status, 200, shown)
            self.assertNotIn('raw', json.dumps(shown))   # the model's own words are not kept
            self.assertEqual(shown['card']['proposed'][0]['id'], 'order')
            self.assertEqual(shown['scope'], {'datasets': [{'kind': 'datasets', 'name': '订单'}]})
            status, shown = ann.get(f'/api/workspace/assistant/turns/{plan["id"]}')
            self.assertNotIn('samples', json.dumps(shown))   # nor the rows behind a count
            # nobody else reads it, whatever the role; a viewer has none of this
            for other in (bob, team['admin']):
                self.assertEqual(other.get('/api/workspace/assistant/turns')[1]['turns'], [])
                self.assertEqual(other.get(f'/api/workspace/assistant/turns/{made["id"]}')[0], 404)
                self.assertEqual(other.post(f'/api/workspace/assistant/turns/{made["id"]}/delete', {})[0], 404)
                self.assertEqual(other.post(f'/api/workspace/assistant/turns/{made["id"]}/outcome', {'state': 'applied'})[0], 404)
            self.assertEqual(team['vera'].get('/api/workspace/assistant/turns')[0], 403)
            self.assertEqual(team['vera'].post('/api/workspace/assistant/turns', turn())[0], 403)
            # what happened next
            self.assertEqual(ann.post(f'/api/workspace/assistant/turns/{plan["id"]}/outcome', {'state': 'saved', 'name': 'orders_clean'})[0], 200)
            self.assertEqual(ann.post(f'/api/workspace/assistant/turns/{plan["id"]}/outcome', {'state': 'bogus'})[0], 400)
            self.assertEqual(ann.get(f'/api/workspace/assistant/turns/{plan["id"]}')[1]['outcome']['state'], 'saved')
            # refused turns: ask is kept by ask, a card and a message are needed
            self.assertEqual(ann.post('/api/workspace/assistant/turns', turn('ask'))[0], 400)
            self.assertEqual(ann.post('/api/workspace/assistant/turns', turn(message=' '))[0], 400)
            self.assertEqual(ann.post('/api/workspace/assistant/turns', {**turn(), 'card': 'x'})[0], 400)
            # delete
            self.assertEqual(ann.post(f'/api/workspace/assistant/turns/{made["id"]}/delete', {})[0], 200)
            self.assertEqual(ann.get(f'/api/workspace/assistant/turns/{made["id"]}')[0], 404)
            self.assertEqual([t['id'] for t in ann.get('/api/workspace/assistant/turns')[1]['turns']], [plan['id']])

    def test_a_card_that_names_what_the_reader_can_no_longer_see_is_withheld_and_the_scope_shows_hidden(self):
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            ann, admin = team['ann'], team['admin']
            self.confirmed_orders(team)
            model = ann.post('/api/workspace/assistant/turns', turn())[1]
            plan = ann.post('/api/workspace/assistant/turns', turn('pipeline', 'filter', {'target': {'kind': 'dataset', 'name': '订单', 'label': '订单'}}, PLAN))[1]
            self.assertIn('card', ann.get(f'/api/workspace/assistant/turns/{model["id"]}')[1])
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': [3]})[0], 200)   # the type (and so its dataset) is Bob's now
            for made, message in ((model, 'suggest types'), (plan, 'filter')):
                status, shown = ann.get(f'/api/workspace/assistant/turns/{made["id"]}')
                self.assertEqual(status, 200)
                self.assertNotIn('card', shown)
                self.assertTrue(shown['withheld'])
                self.assertEqual(shown['message'], message)   # their own words stay
                self.assertNotIn('订单', json.dumps({k: v for k, v in shown.items() if k != 'message'}, ensure_ascii=False))
            self.assertEqual(ann.get(f'/api/workspace/assistant/turns/{model["id"]}')[1]['scope'], {'datasets': [{'kind': 'datasets', 'hidden': True}]})
            self.assertEqual(ann.get(f'/api/workspace/assistant/turns/{plan["id"]}')[1]['scope'], {'target': {'kind': 'dataset', 'hidden': True}})

    def test_a_column_kept_from_the_reader_later_withholds_the_card(self):
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            ann, admin = team['ann'], team['admin']
            self.confirmed_orders(team)
            card = {'proposed': [{'id': 'order', 'name': '订单', 'key': ['订单号'], 'properties': [{'column': '状态码'}]}]}
            made = ann.post('/api/workspace/assistant/turns', turn(scope={}, card=card))[1]
            self.assertIn('card', ann.get(f'/api/workspace/assistant/turns/{made["id"]}')[1])
            self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'order', 'column': '状态码', 'visible_to': [3]})[0], 200)
            shown = ann.get(f'/api/workspace/assistant/turns/{made["id"]}')[1]
            self.assertEqual(shown['withheld'], {'columns': 1})
            self.assertNotIn('card', shown)

    def test_only_the_newest_turns_are_kept(self):
        with self.service(gateway=None) as (base, out):
            conn = open_workspace(out / 'workspace.sqlite')
            try:
                me, other = {'id': 7}, {'id': 8}
                assistant_history.record(conn, other, 'query', 'theirs', {}, {'query_text': 'x'})
                for i in range(assistant_history.HISTORY_LIMIT + 5):
                    assistant_history.record(conn, me, 'query', f'q{i}', {}, {'query_text': 'x'})
                mine = assistant_history.listing(conn, me)
                self.assertEqual(len(mine), assistant_history.HISTORY_LIMIT)
                self.assertEqual(mine[0]['message'], f'q{assistant_history.HISTORY_LIMIT + 4}')
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM assistant_turn WHERE user_id = 7').fetchone()[0], assistant_history.HISTORY_LIMIT)
                self.assertEqual([t['message'] for t in assistant_history.listing(conn, other)], ['theirs'])   # another person's turns are not trimmed by mine
            finally:
                conn.close()
