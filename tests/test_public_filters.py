import copy
import json
from pathlib import Path
import unittest

from ontology_poc_generator.public_ontology import build_graph, verify_proposal

FIXTURES = Path(__file__).resolve().parent / 'fixtures/nhtsa'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def vehicles_only(proposal, where):
    p = copy.deepcopy(proposal)
    vehicle = next(t for t in p['object_types'] if t['key'] == 'vehicle_model_year')
    vehicle['populated_from'][1]['where'] = where
    return p


TIRE = ('vehicle_model_year', (('make', 'MICHELIN'), ('model', 'PILOT'), ('model_year', '9999')))


class PopulationFilterTests(unittest.TestCase):
    def setUp(self):
        self.bundle = copy.deepcopy(load('mini_bundle.json'))
        fire = next(r for r in self.bundle['sources']['complaints']['records'] if r['odiNumber'] == 11600123)
        fire['products'].append({'type': 'Tire', 'productMake': 'MICHELIN', 'productModel': 'PILOT', 'productYear': '9999'})
        self.proposal = load('reference_proposal.json')

    def codes(self, proposal):
        return {e['code'] for e in verify_proposal(proposal, self.bundle)['errors']}

    def test_non_vehicle_products_do_not_become_vehicles(self):
        self.assertIn(TIRE, build_graph(self.proposal, self.bundle)['sources_of'])
        filtered = vehicles_only(self.proposal, {'path': 'products[].type', 'equals': 'Vehicle'})
        self.assertEqual(self.codes(filtered), set())
        graph = build_graph(filtered, self.bundle)
        self.assertNotIn(TIRE, graph['sources_of'])
        self.assertIn(('vehicle_model_year', (('make', 'CHEVROLET'), ('model', 'BOLT EV'), ('model_year', '2023'))),
                      graph['sources_of'])

    def test_filter_must_exist_keep_something_and_stay_in_the_same_list(self):
        for where in ({'path': 'products[].kind', 'equals': 'Vehicle'},
                      {'path': 'products[].type', 'equals': 'Spaceship'},
                      {'path': 'recalls[].type', 'equals': 'Vehicle'},
                      {'path': 'products[].type'}):
            with self.subTest(where=where):
                self.assertIn('where_invalid', self.codes(vehicles_only(self.proposal, where)))


if __name__ == '__main__':
    unittest.main()
