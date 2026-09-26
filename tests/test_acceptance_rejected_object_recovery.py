"""Rejecting an object must not destroy the query identity needed to restore acceptance later."""
import copy
import json
import unittest

from ontology_poc_generator.ontology_acceptance import check_acceptance
from tests.test_acceptance_reviewed_state import ITEM, UPLOAD, decisions
from tests.test_derived_measures import Model, ONTOLOGY, bundle
from tests.test_ontology_ask_server import call
from tests import test_ontology_server as server_helpers


class RejectedObjectRecoveryTests(unittest.TestCase):
    def exercise_restore(self, legacy_snapshot=False):
        with server_helpers.OntologyServerTests().server(gateway=Model()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            rejected = {'types': {'order_line': {'verdict': 'wrong'}, 'customer': {'verdict': 'ok'}}, 'relations': {}, 'added': []}
            call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': rejected})
            code, saved = call(base, '/api/ontology/acceptance', {'saved_as': run['saved_as'], 'items': [ITEM]})
            self.assertEqual(code, 200)
            self.assertEqual(saved['evaluation']['acceptance']['answered'], 0)
            if legacy_snapshot:
                # Simulate the incomplete snapshot written by the previous implementation.
                saved['evaluation']['acceptance']['items'][0]['snapshot'] = {'types': [], 'relations': []}
                (out / run['saved_as']).write_text(json.dumps(saved))
            else:
                snapshot = saved['evaluation']['acceptance']['items'][0]['snapshot']
                self.assertEqual({t['key'] for t in snapshot['types']}, {'order_line', 'customer'})
                self.assertEqual([r['key'] for r in snapshot['relations']], ['line_of_customer'])
            code, restored = call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions(run, 'ok')})
            self.assertEqual(code, 200)
            self.assertEqual(restored['evaluation']['acceptance']['answered'], 1)
            stored = json.loads((out / run['saved_as']).read_text())
            reference = json.loads(next((out / 'references').glob('*.json')).read_text())
            self.assertEqual(stored['confirmation']['reference'], reference['reference'])
            self.assertEqual(stored['evaluation']['acceptance']['answered'], 1)

    def test_rejected_object_keeps_identity_snapshot_and_can_be_restored(self):
        self.exercise_restore()

    def test_existing_incomplete_snapshot_is_recovered_from_the_full_run_schema(self):
        self.exercise_restore(legacy_snapshot=True)

    def test_incomplete_snapshot_with_unrecoverable_identity_reports_broken(self):
        item = {**copy.deepcopy(ITEM), 'snapshot': {'types': [], 'relations': []}}
        item['query']['start'] = 'object_no_longer_in_this_run'
        result = check_acceptance(ONTOLOGY, bundle(), [item])
        self.assertEqual(result['items'][0]['status'], 'broken')
        self.assertIn('object_no_longer_in_this_run', result['items'][0]['reason'])
