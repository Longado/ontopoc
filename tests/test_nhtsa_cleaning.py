from pathlib import Path
import unittest

from ontology_poc_generator.nhtsa_sources import build_nhtsa_bundle, load_source_bundle

ROOT = Path(__file__).resolve().parents[1]
DEMO = {'type': 'Vehicle', 'productYear': '9999', 'productMake': 'TBD', 'productModel': 'TBD', 'manufacturer': 'ODI Demo Co'}
BOLT = {'type': 'Vehicle', 'productYear': '2023', 'productMake': 'CHEVROLET', 'productModel': 'BOLT EV',
        'manufacturer': 'General Motors, LLC'}
TIRE = {'type': 'Tire', 'productYear': '9999', 'productMake': 'MICHELIN', 'productModel': 'ENERGY SAVER',
        'manufacturer': 'Michelin North America, Inc.'}


def bundle(products):
    return build_nhtsa_bundle([
        {'kind': 'recalls', 'url': 'https://r', 'retrieved_at': 't', 'payload': {'results': []}},
        {'kind': 'complaints', 'url': 'https://c', 'retrieved_at': 't',
         'payload': {'results': [{'odiNumber': 1, 'products': products}]}},
    ], decision='d')


class PlaceholderProductTests(unittest.TestCase):
    def test_nhtsa_demo_placeholders_are_removed_and_counted(self):
        b = bundle([BOLT, DEMO])
        self.assertEqual(b['sources']['complaints']['records'][0]['products'], [BOLT])
        (note,) = b['cleaning']
        self.assertEqual((note['source'], note['removed']), ('complaints', 1))
        self.assertIn('ODI Demo Co', note['rule'])

    def test_real_non_vehicle_products_are_kept_for_the_ontology_to_filter(self):
        b = bundle([BOLT, TIRE])
        self.assertEqual(b['sources']['complaints']['records'][0]['products'], [BOLT, TIRE])
        self.assertEqual(b['cleaning'][0]['removed'], 0)

    def test_committed_snapshot_has_no_demo_placeholders(self):
        b = load_source_bundle(ROOT / 'examples/nhtsa/chevrolet_bolt_2017_2023.json')
        makers = {p.get('manufacturer') for c in b['sources']['complaints']['records'] for p in c['products']}
        self.assertNotIn('ODI Demo Co', makers)
        self.assertEqual(b['cleaning'][0]['removed'], 3)
        self.assertEqual(len(b['sources']['complaints']['records']), 679)


if __name__ == '__main__':
    unittest.main()
