"""F3: an approval card says how many confirmed definitions read the dataset it would write a new version of, so the page can warn before 批准."""
import unittest

from tests.test_action_kinds import NEW_ORDER, KindTests


def load_tests(loader, standard, pattern):
    return unittest.TestSuite(ReaderTests(name) for name in vars(ReaderTests) if name.startswith('test_'))


class ReaderTests(KindTests):
    def test_the_approval_card_counts_the_confirmed_definitions_that_read_the_dataset(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.confirmed_action(team, NEW_ORDER)
            status, body = self.create(ann)
            self.assertEqual(status, 200, body)
            card = next(i for i in bob.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'approval' and i['record'] == body['record'])
            self.assertEqual(card['dataset'], '订单')
            self.assertIsInstance(card['readers'], int)
            self.assertGreaterEqual(card['readers'], 1)   # at least the confirmed object type reads it


    def test_the_count_leaves_out_definitions_this_person_may_not_see(self):
        # review of #90: a builder kept from a type should not learn, even as a number, that it reads the dataset
        from ontology_poc_generator.object_actions import open_records
        from ontology_poc_generator.review_queue import approval_item
        from ontology_poc_generator.workspace_store import open_workspace
        with self.service() as (base, out):
            team = self.team(base)
            ann, admin = team['ann'], team['admin']
            self.confirmed_action(team, NEW_ORDER)
            self.assertEqual(self.create(ann)[0], 200)
            people = {p['name']: p['id'] for p in admin.get('/api/workspace/permissions')[1]['people']}
            conn = open_workspace(out / 'workspace.sqlite')
            try:
                rec = open_records(conn, None)[0]
                everyone = approval_item(rec, conn, None)['readers']
                self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': [people['Ann']]})[0], 200)
                self.assertEqual(approval_item(rec, conn, {'id': people['Ann'], 'role': 'builder'})['readers'], everyone)
                self.assertLess(approval_item(rec, conn, {'id': people['Bob'], 'role': 'builder'})['readers'], everyone)
            finally:
                conn.close()


if __name__ == '__main__':
    unittest.main()
