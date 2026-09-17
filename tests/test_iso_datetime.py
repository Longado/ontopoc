import unittest

from ontology_poc_generator.public_ontology import verify_proposal
from tests.test_company_ontology import BUNDLE, PROPOSAL
from ontology_poc_generator.company_ontology import COMPANY_PROFILE


def with_dates(value):
    """The same bundle, but the order date is written the way a real export writes it."""
    records = [{**r, '下单日期': value} for r in BUNDLE['sources']['订单']['records']]
    return {**BUNDLE, 'sources': {**BUNDLE['sources'], '订单': {'records': records, 'requests': []}}}


class IsoDateTimeTests(unittest.TestCase):
    def test_a_timestamp_with_a_time_part_is_still_a_date(self):
        for value in ('2026-08-01T00:00:00.000', '2026-08-01T09:30:00', '2026-08-01 09:30:00', '2026-08-01'):
            with self.subTest(value=value):
                errors = verify_proposal(PROPOSAL, with_dates(value), COMPANY_PROFILE)['errors']
                self.assertEqual([e for e in errors if e['code'] == 'time_field_invalid'], [])

    def test_something_that_is_not_a_date_is_still_refused(self):
        for value in ('第一季度', '2026/08/01', ''):
            with self.subTest(value=value):
                errors = verify_proposal(PROPOSAL, with_dates(value), COMPANY_PROFILE)['errors']
                self.assertTrue([e for e in errors if e['code'] == 'time_field_invalid'], f'{value} should be refused')


if __name__ == '__main__':
    unittest.main()
