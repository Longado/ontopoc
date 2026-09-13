import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from ontology_poc_generator.nhtsa_sources import (
    PublicSourceError, dataset_id, dataset_label, fetch_nhtsa_bundle, validate_bundle,
)
from ontology_poc_generator.public_review_pack import build_review_pack
from tests.test_public_review_pack import make_report

FIXTURES = Path(__file__).resolve().parent / 'fixtures/nhtsa'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def scoped(bundle, make='chevrolet', models=('bolt ev', 'bolt euv'), years=(2017, 2023)):
    return {**bundle, 'scope': {'make': make, 'models': list(models), 'years': list(years)}}


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class DatasetScopeTests(unittest.TestCase):
    def test_fetch_records_what_was_asked_for(self):
        def opener(request, timeout):
            return Reply(json.dumps({'results': []}).encode())
        b = fetch_nhtsa_bundle('hyundai', ['kona electric'], [2019, 2020, 2021], decision='d', opener=opener,
                               clock=lambda: '2026-09-13T00:00:00+00:00')
        self.assertEqual(b['scope'], {'make': 'hyundai', 'models': ['kona electric'], 'years': [2019, 2021]})

    def test_id_and_label_come_from_the_scope(self):
        b = scoped(load('mini_bundle.json'))
        self.assertEqual(dataset_id(b), 'nhtsa-chevrolet-bolt-ev-bolt-euv-2017-2023')
        self.assertEqual(dataset_label(b), 'CHEVROLET BOLT EV / BOLT EUV · 2017–2023')

    def test_malformed_scope_is_rejected(self):
        for bad in ({'make': '', 'models': ['x'], 'years': [2019, 2020]},
                    {'make': 'ford', 'models': [], 'years': [2019, 2020]},
                    {'make': 'ford', 'models': ['x'], 'years': [2021, 2019]}):
            with self.subTest(bad=bad), self.assertRaises(PublicSourceError):
                validate_bundle({**load('mini_bundle.json'), 'scope': bad})
        with self.assertRaises(PublicSourceError):
            dataset_id(load('mini_bundle.json'))

    def test_pack_names_its_dataset(self):
        b = scoped(load('mini_bundle.json'))
        pack = build_review_pack(make_report(b), b)
        self.assertEqual(pack['dataset'], {'id': 'nhtsa-chevrolet-bolt-ev-bolt-euv-2017-2023',
                                           'label': 'CHEVROLET BOLT EV / BOLT EUV · 2017–2023'})


class DatasetIndexScriptTests(unittest.TestCase):
    def run_script(self, args):
        from scripts.build_public_review_pack import main
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(args)

    def write(self, d, name, obj):
        path = Path(d) / name
        path.write_text(json.dumps(obj), encoding='utf-8')
        return path

    def test_two_datasets_share_one_index_and_check_covers_both(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d) / 'data'
            bolt = scoped(load('mini_bundle.json'))
            kona = scoped(copy.deepcopy(load('mini_bundle.json')), make='hyundai', models=['kona electric'], years=[2019, 2021])
            for name, bundle in (('bolt', bolt), ('kona', kona)):
                snap = self.write(d, f'{name}-snapshot.json', bundle)
                report = self.write(d, f'{name}-report.json', make_report(bundle))
                self.assertEqual(self.run_script(['--report', str(report), '--snapshot', str(snap), '--data-dir', str(data)]), 0)
            index = json.loads((data / 'index.json').read_text(encoding='utf-8'))
            self.assertEqual([e['id'] for e in index['datasets']],
                             ['nhtsa-chevrolet-bolt-ev-bolt-euv-2017-2023', 'nhtsa-hyundai-kona-electric-2019-2021'])
            kona_entry = index['datasets'][1]
            self.assertEqual(kona_entry['pack'], 'nhtsa-hyundai-kona-electric-2019-2021.json')
            self.assertEqual((kona_entry['recalls'], kona_entry['complaints']), (3, 5))
            self.assertTrue((data / kona_entry['pack']).exists())
            self.assertEqual(self.run_script(['--check', '--data-dir', str(data)]), 0)
            (data / kona_entry['pack']).write_text('{}', encoding='utf-8')
            self.assertEqual(self.run_script(['--check', '--data-dir', str(data)]), 1)

    def test_snapshot_without_scope_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as d:
            bundle = load('mini_bundle.json')
            snap = self.write(d, 's.json', bundle)
            report = self.write(d, 'r.json', make_report(bundle))
            self.assertEqual(self.run_script(['--report', str(report), '--snapshot', str(snap), '--data-dir', str(Path(d) / 'data')]), 2)


if __name__ == '__main__':
    unittest.main()
