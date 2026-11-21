"""A model's draft has no proposer of its own, but the person who asked for it counts as its proposer for the two-person rule: they cannot confirm it straight
away, on its page or in the queue, and another builder can. (The product audit of 2026-11-20 found the draft page offered the asker "confirm"; nobody had
clicked it.) With one person who can confirm, the rule is off and the log marks the self-confirmation, as for any definition. Walked through the real
service with a fake model on the planted tables."""
import sqlite3

from tests.test_object_types import TABLES, Suggester
from tests.test_two_person import SigningTestCase

REPLY = {'object_types': [{'name': '订单', 'english_name': 'order', 'dataset': '订单', 'key': ['订单号'], 'basis': '一行一张订单',
                           'properties': [{'column': '订单号', 'needed_for': '数订单'}, {'column': '金额', 'needed_for': '加总金额'}]}]}


class ModelDraftProposerTests(SigningTestCase):
    def suggested(self, client):
        self.assertEqual(client.post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        status, body = client.post('/api/workspace/types/suggest', {'datasets': ['订单'], 'purpose': '订单的金额'})
        self.assertEqual(status, 200, body)
        self.assertEqual([p['id'] for p in body['proposed']], ['order'])

    def detail(self, client):
        status, body = client.get('/api/workspace/types/order')
        self.assertEqual(status, 200, body)
        return body

    def confirm(self, client):
        shown = self.detail(client)
        return client.post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen']})

    def test_the_person_who_asked_for_the_draft_cannot_confirm_it_and_another_builder_can(self):
        with self.service(gateway=Suggester(REPLY)) as (base, out):
            team = self.people(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.suggested(ann)
            mine = self.detail(ann)
            self.assertEqual((mine['state'], mine['proposed_by'], mine['model_draft'], mine['can_confirm']), ('proposed', None, True, False))   # still the model's draft
            self.assertNotIn('Ann', mine['confirmers'])
            self.assertEqual(self.confirm(ann)[0], 403)
            item = next(i for i in ann.get('/api/workspace/queue')[1]['items'] if i['element'] == 'objtype:order')
            self.assertFalse(item['can_confirm'])
            status, body = ann.post('/api/workspace/queue/confirm', {'element': 'objtype:order', 'version': item['version'], 'seen': item['seen']})
            self.assertEqual(status, 403, body)
            self.assertEqual(self.detail(ann)['state'], 'proposed')
            self.assertTrue(self.detail(bob)['can_confirm'])
            status, body = self.confirm(bob)
            self.assertEqual(status, 200, body)
            conn = sqlite3.connect(out / 'workspace.sqlite')
            self.assertEqual(conn.execute("SELECT confirmed_by, self_confirmed FROM confirmation WHERE element_id = 'objtype:order'").fetchall(), [('Bob', 0)])
            conn.close()

    def test_a_draft_another_builder_asked_for_is_not_theirs_to_confirm_either_once_they_save_it_it_is_theirs(self):
        with self.service(gateway=Suggester(REPLY)) as (base, out):
            team = self.people(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.suggested(ann)
            shown = self.detail(bob)   # Bob opens Ann's draft and saves it: his proposal now, so Ann confirms it
            status, saved = bob.post('/api/workspace/types/update', {'id': 'order', 'version': shown['version'], 'name': '订单', 'english_name': 'order', 'dataset': '订单',
                                                                     'key': ['订单号'], 'properties': [{'column': '订单号'}, {'column': '金额'}]})
            self.assertEqual((status, saved['state']), (200, 'checked'))
            self.assertEqual(self.confirm(bob)[0], 403)
            self.assertEqual(self.confirm(ann)[0], 200)

    def test_with_one_person_who_can_confirm_the_asker_confirms_and_the_log_marks_it(self):
        with self.service(gateway=Suggester(REPLY)) as (base, out):
            admin = self.people(base)['admin']
            self.suggested(admin)
            self.assertTrue(self.detail(admin)['can_confirm'])
            self.assertEqual(self.confirm(admin)[0], 200)
            log = admin.get('/api/workspace/types/order/log')[1]['log']
            self.assertEqual([e['self_confirmed'] for e in log if e['element'] == 'type' and e['to'] == 'confirmed'], [True])
