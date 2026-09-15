import base64
import unittest

from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_jobs import wait
from tests.test_ontology_server import CSV, OntologyServerTests


class StabilityServerTests(unittest.TestCase):
    def test_a_table_build_is_run_three_times_and_labelled_by_how_often_each_part_appears(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            _, started = call(base, '/api/ontology/jobs', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            job = wait(base, started['job_id'])
        self.assertEqual(job['state'], 'done')
        self.assertIn('stability', [e['stage'] for e in job['events']])
        result = job['result']
        stability = result['evaluation']['stability']
        self.assertEqual((stability['runs'], stability['failed']), (3, 0))
        self.assertEqual(set(stability['types']), {t['key'] for t in result['ontology']['object_types']})
        self.assertEqual(set(stability['types'].values()), {3})


if __name__ == '__main__':
    unittest.main()
