import copy
import importlib
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'examples/nhtsa/chevrolet_bolt_2017_2023.json'


def recall(campaign, model, year):
    return {'NHTSACampaignNumber': campaign, 'Model': model, 'ModelYear': year,
            'Make': 'CHEVROLET', 'Component': 'SEAT BELTS'}


def complaint(odi, year):
    return {'odiNumber': odi, 'components': 'STEERING', 'summary': 'text',
            'products': [{'productYear': year, 'productMake': 'CHEVROLET', 'productModel': 'BOLT EV'}]}


def response(kind, url, results, at='2026-09-13T03:29:39+00:00'):
    return {'kind': kind, 'url': url, 'retrieved_at': at, 'payload': {'results': results}}


class NhtsaSourceTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('ontology_poc_generator.nhtsa_sources'),
                             'NHTSA public source adapter is not implemented')
        return importlib.import_module('ontology_poc_generator.nhtsa_sources')

    def bundle(self):
        return self.api().build_nhtsa_bundle([
            response('recalls', 'https://api.nhtsa.gov/recalls/recallsByVehicle?a=2', [
                recall('21V650000', 'BOLT EV', '2021'), recall('20V701000', 'BOLT EV', '2019')]),
            response('recalls', 'https://api.nhtsa.gov/recalls/recallsByVehicle?a=1', [
                recall('20V701000', 'BOLT EV', '2019')]),
            response('complaints', 'https://api.nhtsa.gov/complaints/complaintsByVehicle?a=1', [
                complaint(11600123, '2023'), complaint(11429913, '2019')]),
            response('complaints', 'https://api.nhtsa.gov/complaints/complaintsByVehicle?a=2', [
                complaint(11429913, '2019')]),
        ], decision='decide scope')

    def test_duplicates_removed_and_order_stable(self):
        b = self.bundle()
        self.assertEqual(b['schema'], 'public_source_bundle.v1')
        self.assertEqual(b['evidence_scope'], 'public_data')
        recalls = b['sources']['recalls']['records']
        self.assertEqual([(r['NHTSACampaignNumber'], r['ModelYear']) for r in recalls],
                         [('20V701000', '2019'), ('21V650000', '2021')])
        self.assertEqual([r['odiNumber'] for r in b['sources']['complaints']['records']], [11429913, 11600123])
        self.assertEqual(len(b['sources']['recalls']['requests']), 2)

    def test_input_order_does_not_change_bundle_or_hash(self):
        api = self.api()
        responses = [
            response('recalls', 'https://api.nhtsa.gov/r?1', [recall('A', 'M', '2020')]),
            response('recalls', 'https://api.nhtsa.gov/r?2', [recall('B', 'M', '2021')]),
            response('complaints', 'https://api.nhtsa.gov/c?1', [complaint(2, '2020'), complaint(1, '2021')]),
        ]
        a = api.build_nhtsa_bundle(responses, decision='d')
        b = api.build_nhtsa_bundle(list(reversed(responses)), decision='d')
        self.assertEqual(a, b)
        self.assertEqual(api.bundle_content_hash(a), api.bundle_content_hash(b))
        self.assertRegex(api.bundle_content_hash(a), r'^[0-9a-f]{64}$')

    def test_load_rejects_missing_provenance_and_wrong_scope(self):
        api = self.api()
        good = self.bundle()
        bad_cases = []
        no_requests = copy.deepcopy(good)
        no_requests['sources']['recalls']['requests'] = []
        bad_cases.append(no_requests)
        no_time = copy.deepcopy(good)
        no_time['sources']['complaints']['requests'][0]['retrieved_at'] = ''
        bad_cases.append(no_time)
        plain_http = copy.deepcopy(good)
        plain_http['sources']['recalls']['requests'][0]['url'] = 'http://api.nhtsa.gov/x'
        bad_cases.append(plain_http)
        synthetic = copy.deepcopy(good)
        synthetic['evidence_scope'] = 'synthetic_demo'
        bad_cases.append(synthetic)
        no_decision = copy.deepcopy(good)
        no_decision['decision'] = ' '
        bad_cases.append(no_decision)
        with tempfile.TemporaryDirectory() as d:
            for i, case in enumerate(bad_cases):
                path = Path(d) / f'{i}.json'
                path.write_text(json.dumps(case), encoding='utf-8')
                with self.subTest(case=i), self.assertRaises(api.PublicSourceError):
                    api.load_source_bundle(path)
            path = Path(d) / 'good.json'
            path.write_text(json.dumps(good), encoding='utf-8')
            self.assertEqual(api.load_source_bundle(path), good)

    def test_fetch_uses_https_urls_and_records_time(self):
        api = self.api()
        seen = []

        class Reply(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def opener(request, timeout):
            seen.append(request.full_url)
            results = [recall('X', 'BOLT EV', '2020')] if 'recalls' in request.full_url else [complaint(5, '2020')]
            return Reply(json.dumps({'results': results}).encode())

        b = api.fetch_nhtsa_bundle('chevrolet', ['bolt ev'], [2020], decision='d', opener=opener,
                                   clock=lambda: '2026-09-13T00:00:00+00:00')
        self.assertEqual(seen, [
            'https://api.nhtsa.gov/recalls/recallsByVehicle?make=chevrolet&model=bolt+ev&modelYear=2020',
            'https://api.nhtsa.gov/complaints/complaintsByVehicle?make=chevrolet&model=bolt+ev&modelYear=2020'])
        self.assertEqual(b['sources']['recalls']['requests'][0]['retrieved_at'], '2026-09-13T00:00:00+00:00')

    def test_fetch_failure_is_reported_not_swallowed(self):
        api = self.api()

        def opener(request, timeout):
            raise OSError('network down')

        with self.assertRaises(api.PublicSourceError):
            api.fetch_nhtsa_bundle('chevrolet', ['bolt ev'], [2020], decision='d', opener=opener)

    def test_committed_snapshot_matches_spike_counts(self):
        b = self.api().load_source_bundle(SNAPSHOT)
        recalls = b['sources']['recalls']['records']
        self.assertEqual(len({r['NHTSACampaignNumber'] for r in recalls}), 13)
        self.assertEqual(len(b['sources']['complaints']['records']), 679)
        self.assertEqual(len(b['sources']['recalls']['requests']), 14)


if __name__ == '__main__':
    unittest.main()
