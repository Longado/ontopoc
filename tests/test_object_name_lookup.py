from tests.test_dashboards import BoardCase
from tests.test_workspace_datasets import part


class NameLookupTests(BoardCase):
    def test_board_and_explorer_match_declared_names_without_promoting_mentions(self):
        with self.service() as (base, _out):
            team = self.team(base)
            client = team['admin']
            csv = ("key,names,comparison\n"
                   "a,North Pier；Nora’s Co-op,East County\n"
                   "b,East County|East County Foods,North Pier\n"
                   "c,Other Holding;Shared label,North Pier\n"
                   "d,Shared label,Other Holding\n")
            status, data = client.post('/api/workspace/datasets/upload', {'files': [part('names.csv', csv.encode())]})
            self.assertEqual(status, 200, data)
            definition = {'english_name': 'firm', 'name': 'Firm', 'dataset': 'names', 'key': ['key'],
                          'properties': [{'column': c} for c in ('key', 'names', 'comparison')]}
            status, data = client.post('/api/workspace/types', definition)
            self.assertEqual(status, 200, data)
            card = {'id': 'firms', 'title': 'Firms', 'query': {'type': 'firm'}, 'chart': {'kind': 'rows'}}
            filtering = {'field': 'names', 'label': 'Company', 'op': 'name_is'}
            board = self.make(client, spec={'components': [card], 'filters': [filtering]})
            self.assertEqual(board['spec']['filters'], [filtering])
            for term, keys in [('NORA\'S CO-OP', ['a']), ('Noras Co-op', ['a']), ('Ｎｏｒｔｈ  Pier', ['a']),
                               ('East County', ['b']), ('Shared label', ['c', 'd']), ('County', []), ("'", [])]:
                with self.subTest(term=term):
                    response = self.data(client, board['id'], {'names': term})
                    self.assertIsNone(response['bar'][0]['options'])
                    self.assertEqual([row[0] for row in self.card(response, 'firms')['result']['rows']], keys)
                    q = {'type': 'firm', 'filters': [{'field': 'names', 'op': 'name_is', 'value': term}]}
                    self.assertEqual([row[0] for row in self.table(client, q)['rows']], keys)
            self.assertEqual(self.table(client, {'type': 'firm', 'search': 'North Pier'})['total'], 3)
            legacy = self.make(client, 'literal', spec={'components': [card], 'filters': [{'field': 'names'}]})
            self.assertEqual(self.card(self.data(client, legacy['id'], {'names': 'East County'}), 'firms')['result']['total'], 0)
            self.make(client, spec={'components': [card], 'filters': [{**filtering, 'op': 'anything'}]}, expect=400)
