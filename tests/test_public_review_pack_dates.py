import unittest

from ontology_poc_generator.public_review_pack import build_review_pack
from tests.test_public_review_pack import load, make_report


class PackDateFieldsTest(unittest.TestCase):
    def test_the_page_knows_which_fields_are_dates(self):
        bundle = load('mini_bundle.json')
        source = build_review_pack(make_report(bundle), bundle)['source']
        self.assertEqual(source['date_fields'], {'recalls': ['ReportReceivedDate'],
                                                 'complaints': ['dateComplaintFiled', 'dateOfIncident']})


if __name__ == '__main__':
    unittest.main()
