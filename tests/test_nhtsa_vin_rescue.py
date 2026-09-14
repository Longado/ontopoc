"""A complaint that names only "KONA" can still be an electric Kona: its VIN prefix says so."""
import json
import unittest

from ontology_poc_generator.nhtsa_sources import fetch_nhtsa_bundle
from tests.test_nhtsa_scope_filter import Reply, product


def complaint(odi, model, vin):
    return {'odiNumber': odi, 'vin': vin, 'products': [product(model)]}


class VinRescueTests(unittest.TestCase):
    def fetch(self, complaints):
        def opener(request, timeout):
            results = complaints if 'complaints' in request.full_url else []
            return Reply(json.dumps({'results': results}).encode())
        return fetch_nhtsa_bundle('hyundai', ['kona electric', 'kona ev'], [2020], decision='d', opener=opener,
                                  clock=lambda: '2026-09-14T00:00:00+00:00')

    def test_other_model_names_are_kept_when_the_vin_prefix_matches_a_requested_model(self):
        b = self.fetch([
            complaint(1, 'KONA ELECTRIC', 'KM8K33AG0LU'),
            complaint(2, 'KONA', 'KM8K33AG5LU'),
            complaint(3, 'KONA', 'KM8K12AA5LU'),
            complaint(4, 'KONA', ''),
            complaint(5, 'KONA EV', 'KM8K53AG1MU'),
        ])
        self.assertEqual([c['odiNumber'] for c in b['sources']['complaints']['records']], [1, 2, 5])
        dropped = next(n for n in b['cleaning'] if 'requested models' in n['rule'])
        self.assertEqual((dropped['removed'], dropped['records']), (2, [3, 4]))
        rescued = next(n for n in b['cleaning'] if 'VIN prefix' in n['rule'])
        self.assertEqual((rescued['kept'], rescued['records']), (1, [2]))

    def test_nothing_to_rescue_is_still_recorded(self):
        b = self.fetch([complaint(1, 'KONA ELECTRIC', 'KM8K33AG0LU')])
        dropped = next(n for n in b['cleaning'] if 'requested models' in n['rule'])
        rescued = next(n for n in b['cleaning'] if 'VIN prefix' in n['rule'])
        self.assertEqual((dropped['removed'], dropped['records'], rescued['kept'], rescued['records']), (0, [], 0, []))


if __name__ == '__main__':
    unittest.main()
