"""NHTSA matches complaint model names loosely: asking for "kona electric" also returns gasoline "KONA" complaints."""
import io
import json
from pathlib import Path
import unittest

from ontology_poc_generator.nhtsa_sources import fetch_nhtsa_bundle, load_source_bundle

ROOT = Path(__file__).resolve().parents[1]


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def product(model, year='2020', make='HYUNDAI', kind='Vehicle'):
    return {'type': kind, 'productYear': year, 'productMake': make, 'productModel': model, 'manufacturer': 'Hyundai'}


class RequestedModelTests(unittest.TestCase):
    def fetch(self, complaints):
        def opener(request, timeout):
            results = complaints if 'complaints' in request.full_url else []
            return Reply(json.dumps({'results': results}).encode())
        return fetch_nhtsa_bundle('hyundai', ['kona electric'], [2020], decision='d', opener=opener,
                                  clock=lambda: '2026-09-13T00:00:00+00:00')

    def test_complaints_about_other_models_are_dropped_and_counted(self):
        b = self.fetch([
            {'odiNumber': 1, 'products': [product('KONA ELECTRIC')]},
            {'odiNumber': 2, 'products': [product('KONA')]},
            {'odiNumber': 3, 'products': [product('KONA'), product('Kona Electric')]},
            {'odiNumber': 4, 'products': [product('ENERGY SAVER', make='MICHELIN', kind='Tire')]},
        ])
        self.assertEqual([c['odiNumber'] for c in b['sources']['complaints']['records']], [1, 3])
        note = next(n for n in b['cleaning'] if 'requested models' in n['rule'])
        self.assertEqual(note['removed'], 2)

    def test_committed_snapshots_hold_only_requested_models_or_vin_rescued_ones(self):
        for name in ('chevrolet_bolt_2017_2023.json', 'hyundai_kona_electric_kona_ev_2019_2021.json',
                     'hyundai_kona_electric_kona_ev_2019_2021_2026-09-14.json'):
            b = load_source_bundle(ROOT / 'examples/nhtsa' / name)
            wanted = {m.upper() for m in b['scope']['models']}
            rescued = {i for n in b.get('cleaning', []) if 'VIN prefix' in n['rule'] for i in n['records']}
            for c in b['sources']['complaints']['records']:
                with self.subTest(snapshot=name, complaint=c['odiNumber']):
                    named = {p.get('productModel', '').upper() for p in c['products']} & wanted
                    self.assertTrue(named or c['odiNumber'] in rescued)


if __name__ == '__main__':
    unittest.main()
