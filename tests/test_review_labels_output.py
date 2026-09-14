import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from ontology_poc_generator.review_labels import compare, labels_from_export, merge_labels
from tests.test_review_labels import PACK, CompareTest, export, label, review


class ReimportTest(unittest.TestCase):
    def test_unchanged_rows_are_not_reported_as_overwritten(self):
        old = labels_from_export(export(review('c1', 'same'), review('c2', 'different', note='n')), PACK, 'qe-01', 'then')
        new = labels_from_export(export(review('c1', 'same', at='2026-10-05T00:00:00Z'), review('c2', 'different', note='n2')),
                                 PACK, 'qe-01', 'now')
        merged, overwritten = merge_labels(old, new)
        self.assertEqual([r['complaint'] for r in overwritten], ['c2'])
        self.assertEqual([r['imported_at'] for r in merged], ['now', 'now'])


class TwoReviewersTest(unittest.TestCase):
    def test_misjudged_rows_name_the_reviewer_when_there_are_several(self):
        labels = [label('b', 'same', 'no'), {**label('b', 'same', 'no'), 'reviewer': 'qe-02'}]
        result = compare(labels)
        self.assertEqual(result['methods']['model']['missed'], ['20V001000/b（qe-01）', '20V001000/b（qe-02）'])

    def test_one_reviewer_keeps_plain_references(self):
        self.assertEqual(compare(CompareTest.LABELS)['methods']['model']['missed'], ['20V001000/b'])


class ScriptMessagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / 'data'
        self.data.mkdir()
        (self.data / 'index.json').write_text(json.dumps({'schema': 'review_datasets.v1', 'datasets': [
            {'id': PACK['dataset']['id'], 'pack': 'p.json'}]}), encoding='utf-8')
        (self.data / 'p.json').write_text(json.dumps(PACK), encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, module, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = module.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_missing_or_broken_files_are_explained(self):
        from scripts import compare_judgments, import_reviews
        broken = self.root / 'broken.json'
        broken.write_text('{not json', encoding='utf-8')
        base = ['--data-dir', str(self.data), '--labels-dir', str(self.root / 'labels')]
        for module, argv, message in (
                (import_reviews, ['--input', str(self.root / 'nope.json'), *base], '找不到文件'),
                (import_reviews, ['--input', str(broken), *base], '不是有效的 JSON'),
                (compare_judgments, ['--labels', str(self.root / 'nope.jsonl')], '找不到文件'),
                (compare_judgments, ['--labels', str(broken)], '不是有效的 JSON')):
            with self.subTest(module=module.__name__, message=message):
                code, _, err = self.run_main(module, argv)
                self.assertEqual(code, 2)
                self.assertIn(message, err)
                self.assertNotIn('Errno', err)

    def test_import_speaks_chinese_and_lists_only_real_changes(self):
        from scripts import import_reviews
        download = self.root / 'dl.json'
        argv = ['--input', str(download), '--data-dir', str(self.data), '--labels-dir', str(self.root / 'labels'), '--reviewer', 'qe-01']
        download.write_text(json.dumps(export(review('c1', 'same'), review('c2', 'different'))), encoding='utf-8')
        code, out, _ = self.run_main(import_reviews, argv)
        self.assertEqual(code, 0)
        self.assertIn('新增 2 条', out)
        download.write_text(json.dumps(export(review('c1', 'same'), review('c2', 'unsure'))), encoding='utf-8')
        code, out, _ = self.run_main(import_reviews, argv)
        self.assertIn('未变 1 条', out)
        self.assertIn('20V001000/c2：不是 → 说不清', out)
        self.assertNotIn('20V001000/c1', out)
        self.assertNotIn('different', out)


if __name__ == '__main__':
    unittest.main()
