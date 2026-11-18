"""Objects applied from the assistant's draft carry a marker (who applied it, when, and that the assistant drafted it), kept in the definition like its other metadata and shown
on the object's page and in the review queue. The server decides: it issues a draft_receipt with each draft, and only a save that carries a live receipt issued to the same person,
for the same kind and target, once, is marked. `assistant: true` alone marks nothing; a bad receipt is ignored and the save still works."""
import json
import sqlite3
from urllib.parse import quote

from tests.test_object_types import ORDER, Suggester, TABLES
from tests.test_pipeline_assist import Assistant, DRAFT_SPEC, SENTENCE
from tests.test_two_person import SigningTestCase

REPLY = {'object_types': [{'name': '订单', 'english_name': 'order', 'dataset': '订单', 'key': ['订单号'], 'basis': '一行一张订单', 'properties': [{'column': '订单号', 'needed_for': '数订单'}]}]}
SHOWN = '/api/workspace/pipelines/' + quote('汇总')
SPEC = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}]}
SAVE = {'name': '订单', 'english_name': 'order', 'dataset': '订单', 'key': ['订单号'], 'properties': [{'column': '订单号'}]}


class Both:
    """The suggester for a type request, the pipeline assistant for a draft."""

    def __init__(self):
        self.types, self.steps = Suggester(REPLY), Assistant()

    def complete_json(self, *, system_prompt, user_prompt, timeout_seconds=None):
        who = self.types if 'purpose' in json.loads(user_prompt) else self.steps
        return who.complete_json(system_prompt=system_prompt, user_prompt=user_prompt, timeout_seconds=timeout_seconds)


class ProvenanceTests(SigningTestCase):
    def setup(self, base):
        team = self.people(base, 'ann', 'bob')
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        return team

    def confirmed(self, base):
        """The planted orders with a confirmed type, so that the assistant can draft by meaning."""
        team = self.setup(base)
        self.assertEqual(team['ann'].post('/api/workspace/types', ORDER)[0], 200)
        shown = team['bob'].get('/api/workspace/types/order')[1]
        meanings = next(p for p in shown['properties'] if p['column'] == '状态码')['meanings']
        self.assertEqual(team['bob'].post('/api/workspace/types/confirm', {'id': 'order', 'version': meanings['version'], 'column': '状态码', 'seen': meanings['seen']})[0], 200)
        return team

    def suggest(self, client):
        status, body = client.post('/api/workspace/types/suggest', {'datasets': ['订单'], 'purpose': 'x'})
        self.assertEqual(status, 200, body)
        return body['proposed'][0]['draft_receipt']

    def type_save(self, client, receipt=None, **more):
        shown = client.get('/api/workspace/types/order')[1]
        return client.post('/api/workspace/types/update', {'id': 'order', 'version': shown['version'], **SAVE, **more, **({'draft_receipt': receipt} if receipt else {})})

    def how(self, client):
        drafted = client.get('/api/workspace/types/order')[1]['drafted']
        return drafted and drafted['how']

    def test_a_type_applied_with_the_servers_receipt_says_who_applied_it_when_and_that_the_assistant_drafted_it(self):
        with self.service(gateway=Both()) as (base, out):
            team = self.setup(base)
            ann = team['ann']
            receipt = self.suggest(ann)
            self.assertIsNone(ann.get('/api/workspace/types/order')[1]['drafted'])   # the model's draft is not applied by anyone yet
            status, body = self.type_save(ann, receipt)
            self.assertEqual(status, 200, body)
            drafted = ann.get('/api/workspace/types/order')[1]['drafted']
            self.assertEqual((drafted['by'], drafted['how']), ('Ann', 'assistant'))
            self.assertRegex(drafted['at'], r'^\d{4}-\d\d-\d\d')
            self.assertEqual(ann.get('/api/workspace/types')[1]['types'][0]['drafted'], drafted)
            queued = next(i for i in team['bob'].get('/api/workspace/queue')[1]['items'] if i['element'] == 'objtype:order')
            self.assertEqual(queued['drafted'], drafted)
            # an ordinary edit afterwards keeps it
            self.assertEqual(self.type_save(ann, properties=[{'column': '订单号'}, {'column': '金额'}])[0], 200)
            self.assertEqual(ann.get('/api/workspace/types/order')[1]['drafted'], drafted)

    def test_the_flag_alone_marks_nothing_and_neither_does_a_made_up_receipt(self):
        with self.service(gateway=Both()) as (base, out):
            ann = self.setup(base)['ann']
            self.suggest(ann)
            self.assertEqual(self.type_save(ann, assistant=True)[0], 200)
            self.assertIsNone(self.how(ann))
        with self.service() as (base, out):
            ann = self.setup(base)['ann']
            self.assertEqual(ann.post('/api/workspace/types', {**ORDER, 'assistant': True, 'draft_receipt': 'made-up'})[0], 200)
            self.assertIsNone(self.how(ann))
            self.assertEqual(self.type_save(ann, 'made-up', assistant=True)[0], 200)
            self.assertIsNone(self.how(ann))

    def test_another_persons_receipt_marks_nothing_and_does_not_refuse_the_save(self):
        with self.service(gateway=Both()) as (base, out):
            team = self.setup(base)
            receipt = self.suggest(team['ann'])
            self.assertEqual(self.type_save(team['bob'], receipt)[0], 200)   # Bob saves what Ann was given
            self.assertIsNone(self.how(team['bob']))
            db = sqlite3.connect(str(out / 'workspace.sqlite'))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM draft_receipt WHERE id = ?', (receipt,)).fetchone()[0], 1)   # Bob's attempt did not use it up
            db.close()

    def test_a_receipt_works_once_and_not_after_a_day(self):
        with self.service(gateway=Both()) as (base, out):
            ann = self.setup(base)['ann']
            receipt = self.suggest(ann)
            self.assertEqual(self.type_save(ann, receipt)[0], 200)
            marked = ann.get('/api/workspace/types/order')[1]['drafted']
            self.assertEqual(self.type_save(ann, receipt, description='again')[0], 200)   # used up: the marker stays as it was
            self.assertEqual(ann.get('/api/workspace/types/order')[1]['drafted'], marked)
        with self.service(gateway=Both()) as (base, out):
            ann = self.setup(base)['ann']
            receipt = self.suggest(ann)
            db = sqlite3.connect(str(out / 'workspace.sqlite'))
            db.execute('UPDATE draft_receipt SET expires = 1')
            db.commit()
            db.close()
            self.assertEqual(self.type_save(ann, receipt)[0], 200)
            self.assertIsNone(self.how(ann))

    def test_a_type_saved_with_other_columns_than_drafted_is_marked_edited(self):
        with self.service(gateway=Both()) as (base, out):
            ann = self.setup(base)['ann']
            receipt = self.suggest(ann)
            self.assertEqual(self.type_save(ann, receipt, properties=[{'column': '订单号'}, {'column': '金额'}])[0], 200)
            self.assertEqual(self.how(ann), 'assistant-edited')

    def test_a_pipelines_receipt_does_not_mark_a_type(self):
        with self.service(gateway=Both()) as (base, out):
            ann = self.confirmed(base)['ann']
            draft = self.draft(ann)
            self.assertEqual(self.type_save(ann, draft['draft_receipt'], description='new')[0], 200)
            self.assertIsNone(self.how(ann))

    def test_a_type_a_person_made_has_no_marker(self):
        with self.service() as (base, out):
            ann = self.setup(base)['ann']
            self.assertEqual(ann.post('/api/workspace/types', {**ORDER, 'assistant': 'yes'})[0], 200)
            self.assertIsNone(self.how(ann))

    def draft(self, client, name=None):
        status, body = client.post('/api/workspace/pipelines/ai/draft', {'spec': DRAFT_SPEC, 'selected': ['o'], 'text': SENTENCE, **({'id': name} if name else {})})
        self.assertEqual(status, 200, body)
        return body

    def pipe_save(self, client, spec, receipt=None, **more):
        version = client.get(SHOWN)[1]['version']
        return client.post('/api/workspace/pipelines/update', {'id': '汇总', 'version': version, 'spec': spec, **more, **({'draft_receipt': receipt} if receipt else {})})

    def whole(self, draft):
        return {'steps': [*SPEC['steps'], *[s['step'] for s in draft['steps']]]}

    def test_a_pipeline_saved_from_the_assistants_draft_carries_the_marker_and_keeps_it(self):
        with self.service(gateway=Both()) as (base, out):
            team = self.confirmed(base)
            ann = team['ann']
            self.assertEqual(ann.post('/api/workspace/pipelines', {'name': '汇总', 'description': '', 'spec': SPEC})[0], 200)
            self.assertIsNone(ann.get(SHOWN)[1]['drafted'])
            draft = self.draft(ann, '汇总')
            status, body = self.pipe_save(ann, self.whole(draft), draft['draft_receipt'])
            self.assertEqual(status, 200, body)
            drafted = ann.get(SHOWN)[1]['drafted']
            self.assertEqual((drafted['by'], drafted['how']), ('Ann', 'assistant'))
            self.assertEqual(ann.get('/api/workspace/pipelines')[1]['pipelines'][0]['drafted'], drafted)
            self.assertEqual(next(i for i in team['bob'].get('/api/workspace/queue')[1]['items'] if i['element'] == 'pipeline:汇总')['drafted'], drafted)
            self.assertEqual(self.pipe_save(ann, SPEC)[0], 200)
            self.assertEqual(ann.get(SHOWN)[1]['drafted'], drafted)

    def test_a_new_pipeline_created_from_a_draft_for_a_dataset_carries_the_marker(self):
        with self.service(gateway=Both()) as (base, out):
            ann = self.confirmed(base)['ann']
            draft = self.draft(ann)
            status, body = ann.post('/api/workspace/pipelines', {'name': '汇总', 'description': '', 'spec': self.whole(draft), 'draft_receipt': draft['draft_receipt']})
            self.assertEqual(status, 200, body)
            self.assertEqual(ann.get(SHOWN)[1]['drafted']['how'], 'assistant')

    def test_a_save_that_fails_leaves_the_receipt_for_the_retry(self):
        with self.service(gateway=Both()) as (base, out):
            ann = self.confirmed(base)['ann']
            self.assertEqual(ann.post('/api/workspace/pipelines', {'name': '汇总', 'description': '', 'spec': SPEC})[0], 200)
            draft = self.draft(ann)
            taken = {'name': '汇总', 'description': '', 'spec': self.whole(draft), 'draft_receipt': draft['draft_receipt']}
            self.assertEqual(ann.post('/api/workspace/pipelines', taken)[0], 409)   # the name is taken: nothing was written
            self.assertEqual(ann.post('/api/workspace/pipelines', {**taken, 'name': '汇总二'})[0], 200)
            self.assertEqual(ann.get('/api/workspace/pipelines/' + quote('汇总二'))[1]['drafted']['how'], 'assistant')

    def test_a_pipeline_flag_alone_or_a_foreign_or_reused_receipt_marks_nothing(self):
        with self.service(gateway=Both()) as (base, out):
            team = self.confirmed(base)
            ann = team['ann']
            self.assertEqual(ann.post('/api/workspace/pipelines', {'name': '汇总', 'description': '', 'spec': SPEC})[0], 200)
            draft = self.draft(ann, '汇总')
            whole = self.whole(draft)
            self.assertEqual(self.pipe_save(ann, whole, assistant=True)[0], 200)
            self.assertIsNone(ann.get(SHOWN)[1]['drafted'])
            self.assertEqual(self.pipe_save(team['bob'], SPEC, draft['draft_receipt'])[0], 200)   # Bob's save with Ann's receipt
            self.assertIsNone(ann.get(SHOWN)[1]['drafted'])
            self.assertEqual(self.pipe_save(ann, whole, draft['draft_receipt'])[0], 200)
            self.assertEqual(ann.get(SHOWN)[1]['drafted']['how'], 'assistant')
            self.assertEqual(self.pipe_save(ann, SPEC, draft['draft_receipt'], description='x')[0], 200)   # used already: the marker is the old one
            self.assertEqual(ann.get(SHOWN)[1]['drafted']['how'], 'assistant')

    def test_a_pipeline_receipt_is_for_the_pipeline_it_was_issued_for_and_edited_steps_say_edited(self):
        with self.service(gateway=Both()) as (base, out):
            ann = self.confirmed(base)['ann']
            self.assertEqual(ann.post('/api/workspace/pipelines', {'name': '汇总', 'description': '', 'spec': SPEC})[0], 200)
            self.assertEqual(ann.post('/api/workspace/pipelines', {'name': '别的', 'description': '', 'spec': SPEC})[0], 200)
            draft = self.draft(ann, '别的')
            self.assertEqual(self.pipe_save(ann, self.whole(draft), draft['draft_receipt'])[0], 200)   # issued for another pipeline
            self.assertIsNone(ann.get(SHOWN)[1]['drafted'])
            draft = self.draft(ann, '汇总')
            edited = {'steps': [*SPEC['steps'], {**draft['steps'][0]['step'], 'operators': []}, draft['steps'][1]['step']]}
            self.assertEqual(self.pipe_save(ann, edited, draft['draft_receipt'])[0], 200)
            self.assertEqual(ann.get(SHOWN)[1]['drafted']['how'], 'assistant-edited')
