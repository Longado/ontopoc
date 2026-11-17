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


if __name__ == '__main__':
    unittest.main()
