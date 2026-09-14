import contextlib
import io
import unittest
from unittest.mock import patch

from ontology_poc_generator.review_labels import (
    HUMAN_LABELS, RULE_VERSION, LabelError, check_clean, compare, labels_from_export,
)
from tests.test_review_labels import PACK, export, review


class LabelStoreKeepsNoComplaintTextTest(unittest.TestCase):
    def test_rows_carry_the_rule_result_instead_of_the_complaint_text(self):
        rows = labels_from_export(export(review('c1', 'same'), review('c2', 'different'), review('c3', 'unsure')),
                                  PACK, 'qe-01', 'now')
        for row in rows:
            self.assertNotIn('text', row)
            self.assertEqual(row['rule_version'], RULE_VERSION)
        self.assertEqual([r['rule_verdict'] for r in rows], ['yes', 'yes', 'no'])

    def test_compare_reads_the_stored_rule_result(self):
        labels = [{'series': 'S', 'complaint': 'x', 'human': 'same', 'model_verdict': 'no', 'rule_verdict': 'yes',
                   'flags': [], 'reviewer': 'qe-01'}]
        self.assertEqual(compare(labels)['methods']['rule']['agree'], 1)


class CleanCheckTest(unittest.TestCase):
    def row(self, note):
        return {**labels_from_export(export(review('c1', 'same')), PACK, 'qe-01', 'now')[0], 'note': note}

    def test_rejects_vins_emails_and_phone_numbers(self):
        for note in ('VIN 1G1FZ6S01K4', 'full vin 1G1FZ6S09P4123456', 'mail qe@example.com', '手机 13812345678',
                     'call (312) 555-0199', 'call 312-555-0199', 'tel +86 10 12345678'):
            with self.subTest(note=note), self.assertRaises(LabelError):
                check_clean([self.row(note)])

    def test_accepts_ordinary_notes(self):
        for note in ('2020-10-13 召回后 2021 款仍起火', '座椅下冒烟，经销商换了电池包', 'recall 20V701000 then 21V560000',
                     'SERVICE BRAKES', '11483089 与 11486128 同一车主?'):
            with self.subTest(note=note):
                check_clean([self.row(note)])


class WordingTest(unittest.TestCase):
    def test_the_verdict_names_a_failure_not_a_defect(self):
        self.assertEqual(HUMAN_LABELS['same'], '同一故障')


class OnlineRunArgumentsTest(unittest.TestCase):
    def test_snapshot_is_required(self):
        from scripts.run_public_ontology import main
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit_:
            main(['--campaign', '21V650000', '--output', 'unused.json'])
        self.assertEqual(exit_.exception.code, 2)

    def test_without_campaigns_it_lists_them_and_calls_no_model(self):
        from scripts.run_public_ontology import main
        from tests.test_run_public_ontology import MINI
        out = io.StringIO()
        with patch('scripts.run_public_ontology.OpenAICompatibleGateway') as gateway, contextlib.redirect_stdout(out):
            self.assertEqual(main(['--snapshot', MINI]), 0)
        gateway.assert_not_called()
        self.assertIn('21V650000', out.getvalue())
        self.assertIn('--campaign', out.getvalue())


if __name__ == '__main__':
    unittest.main()
