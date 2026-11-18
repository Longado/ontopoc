"""Objects created through the assistant's Apply carry a marker (who applied it, when, and that the assistant drafted it), kept in the definition like its other metadata and shown
on the object's page and in the review queue. An object a person made by hand has none, and a later ordinary edit keeps the marker."""
from tests.test_object_types import ORDER, Suggester, TABLES
from tests.test_two_person import SigningTestCase

REPLY = {'object_types': [{'name': '订单', 'english_name': 'order', 'dataset': '订单', 'key': ['订单号'], 'basis': '一行一张订单', 'properties': [{'column': '订单号', 'needed_for': '数订单'}]}]}
SPEC = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}]}
BIGGER = {'steps': [*SPEC['steps'], {'id': 't', 'type': 'transform', 'from': 'o', 'operators': []}]}


class ProvenanceTests(SigningTestCase):
    def setup(self, base):
        team = self.people(base, 'ann', 'bob')
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        return team

    def test_a_type_proposed_through_the_assistant_says_who_applied_it_when_and_that_the_assistant_drafted_it(self):
        with self.service(gateway=Suggester(REPLY)) as (base, out):
            team = self.setup(base)
            ann = team['ann']
            self.assertEqual(ann.post('/api/workspace/types/suggest', {'datasets': ['订单'], 'purpose': 'x'})[0], 200)
            shown = ann.get('/api/workspace/types/order')[1]
            self.assertIsNone(shown['drafted'])   # the model's draft is not applied by anyone yet
            save = {'id': 'order', 'version': shown['version'], 'name': '订单', 'english_name': 'order', 'dataset': '订单', 'key': ['订单号'], 'properties': [{'column': '订单号'}]}
            status, body = ann.post('/api/workspace/types/update', {**save, 'assistant': True})
            self.assertEqual(status, 200, body)
            drafted = ann.get('/api/workspace/types/order')[1]['drafted']
            self.assertEqual((drafted['by'], drafted['how']), ('Ann', 'assistant'))
            self.assertRegex(drafted['at'], r'^\d{4}-\d\d-\d\d')
            self.assertEqual(ann.get('/api/workspace/types')[1]['types'][0]['drafted'], drafted)
            queued = next(i for i in team['bob'].get('/api/workspace/queue')[1]['items'] if i['element'] == 'objtype:order')
            self.assertEqual(queued['drafted'], drafted)
            # an ordinary edit afterwards keeps it
            version = ann.get('/api/workspace/types/order')[1]['version']
            self.assertEqual(ann.post('/api/workspace/types/update', {**save, 'version': version, 'properties': [{'column': '订单号'}, {'column': '金额'}]})[0], 200)
            self.assertEqual(ann.get('/api/workspace/types/order')[1]['drafted'], drafted)

    def test_a_type_a_person_made_has_no_marker_and_the_flag_must_be_exactly_true(self):
        with self.service() as (base, out):
            ann = self.setup(base)['ann']
            self.assertEqual(ann.post('/api/workspace/types', {**ORDER, 'assistant': 'yes'})[0], 200)
            self.assertIsNone(ann.get('/api/workspace/types/order')[1]['drafted'])

    def test_a_pipeline_saved_from_the_assistants_draft_carries_the_marker_and_keeps_it(self):
        with self.service() as (base, out):
            team = self.setup(base)
            ann = team['ann']
            self.assertEqual(ann.post('/api/workspace/pipelines', {'name': '汇总', 'description': '', 'spec': SPEC})[0], 200)
            self.assertIsNone(ann.get('/api/workspace/pipelines/汇总')[1]['drafted'])
            version = ann.get('/api/workspace/pipelines/汇总')[1]['version']
            status, body = ann.post('/api/workspace/pipelines/update', {'id': '汇总', 'version': version, 'spec': BIGGER, 'assistant': True})
            self.assertEqual(status, 200, body)
            drafted = ann.get('/api/workspace/pipelines/汇总')[1]['drafted']
            self.assertEqual((drafted['by'], drafted['how']), ('Ann', 'assistant'))
            self.assertEqual(ann.get('/api/workspace/pipelines')[1]['pipelines'][0]['drafted'], drafted)
            self.assertEqual(next(i for i in team['bob'].get('/api/workspace/queue')[1]['items'] if i['element'] == 'pipeline:汇总')['drafted'], drafted)
            version = ann.get('/api/workspace/pipelines/汇总')[1]['version']
            self.assertEqual(ann.post('/api/workspace/pipelines/update', {'id': '汇总', 'version': version, 'spec': SPEC})[0], 200)
            self.assertEqual(ann.get('/api/workspace/pipelines/汇总')[1]['drafted'], drafted)
