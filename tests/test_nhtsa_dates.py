import copy
import json
from pathlib import Path
import tempfile
import unittest

from ontology_poc_generator.nhtsa_sources import PublicSourceError, build_nhtsa_bundle, load_source_bundle

ROOT = Path(__file__).resolve().parents[1]


def bundle_with(recall_date, complaint_filed, incident=None):
    return build_nhtsa_bundle([
        {'kind': 'recalls', 'url': 'https://r', 'retrieved_at': 't', 'payload': {'results': [
            {'NHTSACampaignNumber': 'A', 'Model': 'M', 'ModelYear': '2020', 'ReportReceivedDate': recall_date}]}},
        {'kind': 'complaints', 'url': 'https://c', 'retrieved_at': 't', 'payload': {'results': [
            {'odiNumber': 1, 'dateComplaintFiled': complaint_filed, 'dateOfIncident': incident}]}},
    ], decision='d')


class NhtsaDateTests(unittest.TestCase):
    def test_each_source_keeps_its_own_day_month_order(self):
        b = bundle_with('30/08/2018', '11/14/2018', '11/07/2018')
        self.assertEqual(b['sources']['recalls']['records'][0]['ReportReceivedDate'], '2018-08-30')
        self.assertEqual(b['sources']['complaints']['records'][0]['dateComplaintFiled'], '2018-11-14')
        self.assertEqual(b['date_fields']['recalls'], {'ReportReceivedDate': '%d/%m/%Y'})

    def test_ambiguous_dates_follow_the_declared_source_format(self):
        b = bundle_with('04/05/2020', '04/05/2020')
        self.assertEqual(b['sources']['recalls']['records'][0]['ReportReceivedDate'], '2020-05-04')
        self.assertEqual(b['sources']['complaints']['records'][0]['dateComplaintFiled'], '2020-04-05')

    def test_missing_date_stays_missing_and_bad_date_is_rejected(self):
        self.assertIsNone(bundle_with('30/08/2018', '11/14/2018')['sources']['complaints']['records'][0]['dateOfIncident'])
        with self.assertRaisesRegex(PublicSourceError, 'ReportReceivedDate'):
            bundle_with('11/14/2018', '11/14/2018')

    def test_loaded_bundle_must_really_hold_iso_dates(self):
        b = bundle_with('30/08/2018', '11/14/2018')
        broken = copy.deepcopy(b)
        broken['sources']['complaints']['records'][0]['dateComplaintFiled'] = '11/14/2018'
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'b.json'
            path.write_text(json.dumps(broken), encoding='utf-8')
            with self.assertRaisesRegex(PublicSourceError, 'dateComplaintFiled'):
                load_source_bundle(path)

    def test_committed_snapshot_uses_iso_dates(self):
        b = load_source_bundle(ROOT / 'examples/nhtsa/chevrolet_bolt_2017_2023.json')
        recall = next(r for r in b['sources']['recalls']['records'] if r['NHTSACampaignNumber'] == '21V650000')
        self.assertEqual(recall['ReportReceivedDate'], '2021-08-20')
        complaint = next(r for r in b['sources']['complaints']['records'] if r['odiNumber'] == 11600123)
        self.assertEqual(complaint['dateComplaintFiled'], '2024-07-08')


if __name__ == '__main__':
    unittest.main()
