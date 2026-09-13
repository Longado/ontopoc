import contextlib
import copy
import importlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from ontology_poc_generator.public_ontology import auto_build_ontology
from ontology_poc_generator.public_scope import check_candidates, scope
from ontology_poc_generator.recognition import ModelCompletion

FIXTURES = Path(__file__).resolve().parent / 'fixtures/nhtsa'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class Reply:
    def __init__(self, content):
        self.content = content

    def complete_json(self, *, system_prompt, user_prompt):
        content = self.content(user_prompt) if callable(self.content) else self.content
        return ModelCompletion(provider='fake', model='deepseek-flash', content=content)


def matcher(user_prompt):
    items = json.loads(user_prompt)['complaints']
    return json.dumps({'results': [
        {'id': i['id'], 'reasoning': 'r', 'verdict': 'yes' if i['id'] == '11600123' else 'no',
         'evidence': 'smoke coming from under the driver side seat' if i['id'] == '11600123' else ''}
        for i in items]})


def make_report(bundle):
    ontology = auto_build_ontology(bundle, Reply(json.dumps(load('reference_proposal.json'))))
    checked = check_candidates(scope(ontology, bundle, {'campaign_number': '21V650000'}),
                               ontology, bundle, Reply(matcher))
    return {'schema': 'public_ontology_run.v1', 'requested_model': 'deepseek-flash',
            'started_at': '2026-09-13T04:20:48+00:00', 'ontology': ontology,
            'scopes': {'21V650000': checked}, 'errors': [], 'finished': True}


class ReviewPackTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('ontology_poc_generator.public_review_pack'),
                             'review pack builder is not implemented')
        return importlib.import_module('ontology_poc_generator.public_review_pack')

    def setUp(self):
        self.bundle = load('mini_bundle.json')
        self.report = make_report(self.bundle)

    def pack(self):
        return self.api().build_review_pack(self.report, self.bundle)

    def recall(self, pack, campaign):
        return next(r for r in pack['recalls'] if r['id'] == campaign)

    def test_every_recall_gets_a_deterministic_scope(self):
        pack = self.pack()
        self.assertEqual(pack['schema'], 'public_review_pack.v1')
        self.assertEqual([r['id'] for r in pack['recalls']], ['20V701000', '21V517000', '21V650000'])
        battery = self.recall(pack, '21V650000')
        self.assertEqual(battery['counts'], {'inside_scope': 1, 'covered_by_other_event': 1, 'outside_all': 1})
        self.assertEqual(battery['covered'], ['CHEVROLET BOLT EUV 2022', 'CHEVROLET BOLT EV 2020',
                                              'CHEVROLET BOLT EV 2021', 'CHEVROLET BOLT EV 2022'])
        self.assertTrue(battery['text_checked'])
        self.assertIn('could catch fire when charged', ' '.join(f['value'] for f in battery['fields']))
        airbag = self.recall(pack, '21V517000')
        self.assertFalse(airbag['text_checked'])
        self.assertIsNone(airbag['candidates'][0]['text_check'])
        self.assertEqual(set(pack['signals']), {'11429891', '11429913', '11600123', '11492459'})

    def test_candidate_carries_what_a_reviewer_needs(self):
        pack = self.pack()
        c = next(c for c in self.recall(pack, '21V650000')['candidates'] if c['id'] == '11600123')
        self.assertEqual(c['bucket'], 'outside_all')
        signal = pack['signals']['11600123']
        self.assertEqual(signal['objects'], ['CHEVROLET BOLT EV 2023'])
        self.assertIn('ELECTRICAL SYSTEM', signal['parts'])
        self.assertIn('smoke coming from under the driver side seat',
                      next(f['value'] for f in signal['fields'] if f['path'] == 'summary'))
        self.assertEqual(c['text_check']['verdict'], 'yes')
        self.assertEqual(c['text_check']['evidence'], 'smoke coming from under the driver side seat')
        other = next(c for c in self.recall(self.pack(), '21V650000')['candidates'] if c['id'] == '11429913')
        self.assertEqual(other['other_events'], ['20V701000'])

    def test_ontology_summary_for_confirmation(self):
        o = self.pack()['ontology']
        self.assertEqual(o['status'], 'auto_built_verified')
        self.assertEqual(o['human_review'], 'pending')
        self.assertEqual({t['role'] for t in o['object_types']},
                         {'event', 'affected_object', 'mechanism', 'signal', 'context'})
        self.assertRegex(o['hash'], r'^[0-9a-f]{64}$')
        self.assertEqual(o['data_gaps'], load('reference_proposal.json')['open_questions'])

    def test_refuses_blocked_ontology_or_report_that_disagrees_with_recomputation(self):
        api = self.api()
        blocked = copy.deepcopy(self.report)
        blocked['ontology']['status'] = 'blocked'
        with self.assertRaises(api.PackError):
            api.build_review_pack(blocked, self.bundle)
        tampered = copy.deepcopy(self.report)
        tampered['scopes']['21V650000']['candidates'].pop()
        with self.assertRaises(api.PackError):
            api.build_review_pack(tampered, self.bundle)

    def test_pack_is_deterministic_and_has_no_local_paths(self):
        a, b = self.pack(), self.pack()
        self.assertEqual(a, b)
        text = json.dumps(a, ensure_ascii=False)
        self.assertNotIn('/Users/', text)
        self.assertNotIn(str(FIXTURES), text)


class ReviewPackScriptTests(unittest.TestCase):
    def test_check_mode_detects_stale_pack(self):
        from scripts.build_public_review_pack import main
        bundle = load('mini_bundle.json')
        with tempfile.TemporaryDirectory() as d:
            report, snapshot, out = Path(d) / 'r.json', Path(d) / 's.json', Path(d) / 'p.json'
            report.write_text(json.dumps(make_report(bundle)), encoding='utf-8')
            snapshot.write_text(json.dumps(bundle), encoding='utf-8')
            args = ['--report', str(report), '--snapshot', str(snapshot), '--output', str(out)]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 0)
                self.assertEqual(main(args + ['--check']), 0)
                out.write_text('{}', encoding='utf-8')
                self.assertEqual(main(args + ['--check']), 1)


if __name__ == '__main__':
    unittest.main()
