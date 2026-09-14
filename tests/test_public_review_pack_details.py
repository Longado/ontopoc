import json
from pathlib import Path
import unittest

from ontology_poc_generator.public_review_pack import build_review_pack
from tests.test_public_review_pack import load, make_report


class PackDetailsTest(unittest.TestCase):
    def test_the_page_can_say_why_earlier_attempts_were_sent_back(self):
        bundle = load('mini_bundle.json')
        report = make_report(bundle)
        report['ontology']['attempts'] = [
            {'errors': [{'code': 'field_unaccounted', 'message': 'recalls.X: neither used nor listed in ignored_fields'}],
             'model': 'deepseek-flash'},
            {'errors': [], 'model': 'deepseek-flash'}]
        summary = build_review_pack(report, bundle)['ontology']
        self.assertEqual(summary['attempts'], 2)
        self.assertEqual(summary['attempt_errors'], [
            [{'code': 'field_unaccounted', 'message': 'recalls.X: neither used nor listed in ignored_fields'}], []])

    def test_cleaning_done_at_fetch_time_reaches_the_page(self):
        bundle = {**load('mini_bundle.json'), 'cleaning': [{'source': 'complaints', 'rule': 'r', 'removed': 3}]}
        self.assertEqual(build_review_pack(make_report(bundle), bundle)['source']['cleaning'],
                         [{'source': 'complaints', 'rule': 'r', 'removed': 3}])
        plain = load('mini_bundle.json')
        self.assertEqual(build_review_pack(make_report(plain), plain)['source']['cleaning'], [])


if __name__ == '__main__':
    unittest.main()
