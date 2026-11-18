"""F3: a new relation shows how many rows would connect before it is saved: POST /api/workspace/relations/preview reads the same check the save runs, writes nothing."""
import unittest

from tests.test_object_relations import RELATION, RelationTests

PICK = {k: RELATION[k] for k in ('from', 'to', 'cardinality', 'from_column', 'to_column')}


def load_tests(loader, standard, pattern):
    return unittest.TestSuite(PreviewTests(name) for name in vars(PreviewTests) if name.startswith('test_'))


class PreviewTests(RelationTests):
    def test_the_preview_counts_157_of_160_and_names_the_missing_key_and_saves_nothing(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            self.propose_types(ann)
            status, body = ann.post('/api/workspace/relations/preview', PICK)
            self.assertEqual(status, 200, body)
            self.assertEqual((body['rows'], body['matched'], body['unmatched']), (160, 157, 3))
            self.assertEqual(body['samples'], [{'key': 'KH099', 'rows': 3}])
            self.assertEqual((body['many_name'], body['one_name']), ('订单', '客户'))
            self.assertEqual(ann.get('/api/workspace/relations')[1]['relations'], [])   # nothing was saved

    def test_a_column_that_is_not_there_is_said_and_a_viewer_may_not_preview(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.propose_types(team['ann'])
            status, body = team['ann'].post('/api/workspace/relations/preview', {**PICK, 'from_column': '没有这列'})
            self.assertEqual(status, 409, body)
            self.assertIn('没有“没有这列”', body['error'])
            self.assertEqual(team['vera'].post('/api/workspace/relations/preview', PICK)[0], 403)


if __name__ == '__main__':
    unittest.main()
