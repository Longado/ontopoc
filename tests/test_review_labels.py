import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from ontology_poc_generator.review_labels import (
    LabelError, check_clean, compare, labels_from_export, merge_labels, rule_verdict,
)

HASH = 'a' * 64


def candidate(cid, bucket, verdict):
    check = None if verdict is None else {
        'verdict': verdict, 'evidence': '', 'reasoning': 'r', 'model': 'deepseek-flash',
        'prompt_version': 'public_defect_match.v3'}
    return {'id': cid, 'bucket': bucket, 'text_check': check}


def summary(text, *flags):
    return {'flags': list(flags), 'fields': [{'path': 'summary', 'value': text}, {'path': 'fire', 'value': str(bool(flags))}]}


PACK = {
    'dataset': {'id': 'nhtsa-demo-car-2020-2021', 'label': 'DEMO CAR · 2020–2021'},
    'ontology': {'hash': HASH},
    'run': {'model': 'deepseek-flash', 'matcher_prompt_version': 'public_defect_match.v3'},
    'recalls': [
        {'id': '20V001000', 'series': '20V001000', 'candidates': [
            candidate('c1', 'outside_all', 'yes'), candidate('c2', 'outside_all', 'no'),
            candidate('c3', 'inside_scope', 'no'), candidate('c4', 'outside_all', 'unknown')]},
        {'id': '21V002000', 'series': '20V001000', 'candidates': [candidate('c1', 'outside_all', 'yes')]},
        {'id': '22V003000', 'series': '22V003000', 'candidates': [candidate('c5', 'outside_all', None)]},
    ],
    'signals': {
        'c1': summary('The pack caught fire in the garage', 'fire'),
        'c2': summary('Smoke from under the seat'),
        'c3': summary('Misfire at idle, check engine light'),
        'c4': summary('Battery would not charge'),
        'c5': summary('Brake pedal went soft'),
    },
}


def review(complaint, human, recall='20V001000', note='', at='2026-10-01T02:00:00Z'):
    return {'recall': recall, 'complaint': complaint, 'human': human, 'note': note, 'updated_at': at}


def export(*reviews, **extra):
    return {'schema': 'public_review_export.v1', 'dataset': PACK['dataset']['id'], 'ontology_hash': HASH,
            'reviewer': 'qe-01', 'reviews': list(reviews), **extra}


class LabelsFromExportTest(unittest.TestCase):
    def test_rows_carry_the_human_mark_and_the_recorded_model_verdict(self):
        rows = labels_from_export(export(review('c1', 'same', note='seen it'), review('c5', 'different', recall='22V003000')),
                                  PACK, None, '2026-10-02T00:00:00Z')
        first, second = rows
        self.assertEqual(first['dataset'], 'nhtsa-demo-car-2020-2021')
        self.assertEqual(first['series'], '20V001000')
        self.assertEqual(first['series_recalls'], ['20V001000', '21V002000'])
        self.assertEqual((first['complaint'], first['human'], first['note']), ('c1', 'same', 'seen it'))
        self.assertEqual((first['model_verdict'], first['model'], first['prompt_version']),
                         ('yes', 'deepseek-flash', 'public_defect_match.v3'))
        self.assertEqual((first['reviewer'], first['reviewed_at'], first['imported_at']),
                         ('qe-01', '2026-10-01T02:00:00Z', '2026-10-02T00:00:00Z'))
        self.assertEqual(first['ontology_hash'], HASH)
        self.assertEqual(first['flags'], ['fire'])
        self.assertEqual(first['rule_verdict'], 'yes')
        self.assertIsNone(second['model_verdict'])
        self.assertIsNone(second['prompt_version'])

    def test_command_line_reviewer_wins_over_the_file(self):
        rows = labels_from_export(export(review('c1', 'same')), PACK, 'qe-07', 'now')
        self.assertEqual(rows[0]['reviewer'], 'qe-07')

    def test_a_reviewer_is_required(self):
        for missing in (None, '', '  '):
            with self.subTest(missing=missing), self.assertRaisesRegex(LabelError, '复核人'):
                labels_from_export(export(review('c1', 'same'), reviewer=missing), PACK, None, 'now')

    def test_rejects_a_different_ontology(self):
        with self.assertRaisesRegex(LabelError, '本体'):
            labels_from_export(export(review('c1', 'same'), ontology_hash='b' * 64), PACK, 'qe-01', 'now')

    def test_rejects_another_dataset(self):
        with self.assertRaisesRegex(LabelError, '数据集'):
            labels_from_export(export(review('c1', 'same'), dataset='nhtsa-other'), PACK, 'qe-01', 'now')

    def test_rejects_rows_the_pack_does_not_have(self):
        for bad in (review('c9', 'same'), review('c5', 'same'), review('c1', 'maybe'), review('c1', 'same', recall='99V000000')):
            with self.subTest(bad=bad), self.assertRaises(LabelError):
                labels_from_export(export(bad), PACK, 'qe-01', 'now')

    def test_rejects_an_unknown_file(self):
        with self.assertRaisesRegex(LabelError, 'public_review_export.v1'):
            labels_from_export({**export(), 'schema': 'something_else'}, PACK, 'qe-01', 'now')


class MergeTest(unittest.TestCase):
    def rows(self, *reviews, reviewer='qe-01'):
        return labels_from_export(export(*reviews), PACK, reviewer, 'now')

    def test_latest_import_wins_per_reviewer_series_and_complaint(self):
        old = self.rows(review('c1', 'same'), review('c2', 'same'))
        other = self.rows(review('c1', 'different'), reviewer='qe-02')
        new = self.rows(review('c2', 'different', note='changed my mind'), review('c3', 'unsure'))
        merged, overwritten = merge_labels(old + other, new)
        self.assertEqual([(r['reviewer'], r['complaint'], r['human']) for r in merged],
                         [('qe-01', 'c1', 'same'), ('qe-01', 'c2', 'different'), ('qe-02', 'c1', 'different'),
                          ('qe-01', 'c3', 'unsure')])
        self.assertEqual([(r['complaint'], r['human']) for r in overwritten], [('c2', 'same')])

    def test_merge_does_not_change_its_inputs(self):
        old = self.rows(review('c1', 'same'))
        before = copy.deepcopy(old)
        merge_labels(old, self.rows(review('c1', 'different')))
        self.assertEqual(old, before)


class CleanTest(unittest.TestCase):
    def test_rejects_local_paths_and_keys(self):
        row = labels_from_export(export(review('c1', 'same')), PACK, 'qe-01', 'now')[0]
        for note in ('see /Users/someone/Desktop/x.png', 'see /home/me/x', r'C:\Users\me\x', 'key sk-abcdefghijklmnopqrstuv'):
            with self.subTest(note=note), self.assertRaises(LabelError):
                check_clean([{**row, 'note': note}])
        check_clean([row])


def label(complaint, human, model, *, text='Battery would not charge', flags=(), series='20V001000', rule='no'):
    return {'series': series, 'complaint': complaint, 'human': human, 'model_verdict': model,
            'text': text, 'flags': list(flags), 'reviewer': 'qe-01', 'rule_verdict': rule}


class RuleTest(unittest.TestCase):
    def test_fire_flag_or_a_fire_word_at_the_start_of_a_word(self):
        self.assertEqual(rule_verdict(label('x', 'same', None, flags=['fire'])), 'yes')
        for text in ('SMOKE from the seat', 'it was burning', 'the wires melted', 'flames', 'thermal event', 'Fire!'):
            with self.subTest(text=text):
                self.assertEqual(rule_verdict(label('x', 'same', None, text=text)), 'yes')
        for text in ('misfire at idle', 'crash', 'VIN 1G1BURN0000'):
            with self.subTest(text=text):
                self.assertEqual(rule_verdict(label('x', 'same', None, text=text)), 'no')


class CompareTest(unittest.TestCase):
    LABELS = [
        label('a', 'same', 'yes', rule='yes'),
        label('b', 'same', 'no', rule='yes'),
        label('c', 'same', 'yes', rule='no'),
        label('d', 'different', 'no', rule='yes'),
        label('e', 'different', 'no', rule='no'),
        label('f', 'different', 'unknown', rule='yes'),  # model undecided
        label('g', 'different', None, rule='no'),        # never checked by the model
        label('h', 'unsure', 'yes', rule='yes'),         # not counted
    ]

    def test_counts_for_each_way_of_judging(self):
        result = compare(self.LABELS)
        self.assertEqual((result['samples'], result['unsure'], result['reviewers']), (7, 1, 1))
        rule, model, both = (result['methods'][m] for m in ('rule', 'model', 'rule_then_model'))
        self.assertEqual(rule['agree'], 4)
        self.assertEqual(rule['missed'], ['20V001000/c'])
        self.assertEqual(rule['extra'], ['20V001000/d', '20V001000/f'])
        self.assertEqual(rule['undecided'], [])
        self.assertEqual(model['agree'], 4)
        self.assertEqual(model['missed'], ['20V001000/b'])
        self.assertEqual(model['extra'], [])
        self.assertEqual(model['undecided'], ['20V001000/f', '20V001000/g'])
        self.assertEqual(both['agree'], 4)
        self.assertEqual(both['missed'], ['20V001000/b', '20V001000/c'])
        self.assertEqual(both['extra'], [])
        self.assertEqual(both['undecided'], ['20V001000/f'])

    def test_empty_labels(self):
        result = compare([])
        self.assertEqual((result['samples'], result['unsure'], result['reviewers']), (0, 0, 0))
        self.assertEqual(result['methods']['rule']['agree'], 0)


class ScriptsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data, self.labels = root / 'data', root / 'labels'
        self.data.mkdir()
        (self.data / 'index.json').write_text(json.dumps({'schema': 'review_datasets.v1', 'datasets': [
            {'id': PACK['dataset']['id'], 'pack': f'{PACK["dataset"]["id"]}.json'}]}), encoding='utf-8')
        (self.data / f'{PACK["dataset"]["id"]}.json').write_text(json.dumps(PACK), encoding='utf-8')
        self.download = root / 'download.json'

    def tearDown(self):
        self.tmp.cleanup()

    def run_import(self, data, *extra):
        from scripts.import_reviews import main
        self.download.write_text(json.dumps(data), encoding='utf-8')
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(['--input', str(self.download), '--data-dir', str(self.data),
                         '--labels-dir', str(self.labels), *extra])
        return code, out.getvalue(), err.getvalue()

    def stored(self):
        path = self.labels / f'{PACK["dataset"]["id"]}.jsonl'
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]

    def test_import_then_reimport_lists_what_was_overwritten(self):
        code, out, _ = self.run_import(export(review('c1', 'same'), review('c2', 'different')), '--reviewer', 'qe-01')
        self.assertEqual(code, 0, out)
        self.assertEqual([r['human'] for r in self.stored()], ['same', 'different'])
        code, out, _ = self.run_import(export(review('c2', 'same', at='2026-10-03T00:00:00Z')), '--reviewer', 'qe-01')
        self.assertEqual(code, 0)
        self.assertEqual([r['human'] for r in self.stored()], ['same', 'same'])
        self.assertIn('20V001000/c2', out)

    def test_import_refuses_and_writes_nothing(self):
        for data, extra, message in (
                (export(review('c1', 'same'), ontology_hash='b' * 64), (), '本体'),
                (export(review('c1', 'same'), reviewer=None), (), '复核人'),
                (export(review('c1', 'same'), dataset='../../escape'), (), '数据集'),
                (export(review('c1', 'same', note='/Users/someone/a.png')), (), '本机路径')):
            with self.subTest(message=message):
                code, _, err = self.run_import(data, *extra)
                self.assertEqual(code, 2)
                self.assertIn(message, err)
                self.assertFalse(self.labels.exists())

    def test_import_needs_the_reviewer_code_on_the_command_line(self):
        code, _, err = self.run_import(export(review('c1', 'same'), reviewer='张伟'))
        self.assertEqual(code, 2)
        self.assertIn('--reviewer', err)
        self.assertIn('张伟', err)
        self.assertFalse(self.labels.exists())

    def test_compare_prints_counts_not_percentages(self):
        from scripts.compare_judgments import main
        path = Path(self.tmp.name) / 'labels.jsonl'
        path.write_text(''.join(json.dumps(r) + '\n' for r in CompareTest.LABELS), encoding='utf-8')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['--labels', str(path)]), 0)
        text = out.getvalue()
        self.assertIn('样本 7 条', text)
        self.assertIn('| 只用规则 | 4 | 1 | 2 | 0 |', text)
        self.assertIn('| 只用模型 | 4 | 1 | 0 | 2 |', text)
        self.assertIn('| 先规则再看模型 | 4 | 2 | 0 | 1 |', text)
        self.assertNotIn('%', text)


if __name__ == '__main__':
    unittest.main()
