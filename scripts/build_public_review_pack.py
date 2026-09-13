"""Publish (or --check) review-page data: one pack per dataset plus the dataset index the page reads."""
import argparse
import json
from pathlib import Path
import sys

from ontology_poc_generator.nhtsa_sources import PublicSourceError, dataset_id, dataset_label, load_source_bundle
from ontology_poc_generator.public_review_pack import PackError, build_review_pack

ROOT = Path(__file__).resolve().parents[1]
INDEX = 'index.json'


def _rel(path: Path) -> str:
    """Repo-relative when inside the repo, so the committed index carries no machine paths."""
    path = path.resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def _abs(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def _build(report: Path, snapshot: Path) -> tuple[dict, str, dict]:
    bundle = load_source_bundle(snapshot)
    pack = build_review_pack(json.loads(report.read_text(encoding='utf-8')), bundle)
    ident = dataset_id(bundle)
    entry = {'id': ident, 'label': dataset_label(bundle), 'pack': f'{ident}.json',
             'recalls': len(pack['recalls']), 'complaints': pack['source']['record_counts'].get('complaints', 0),
             'retrieved': pack['source']['retrieved_from'][:10], 'report': _rel(report), 'snapshot': _rel(snapshot)}
    return pack, json.dumps(pack, ensure_ascii=False, separators=(',', ':')) + '\n', entry


def _read_index(data: Path) -> dict:
    path = data / INDEX
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'schema': 'review_datasets.v1', 'datasets': []}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, help='recorded online run for one dataset')
    parser.add_argument('--snapshot', type=Path, help='the snapshot that run was built from')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'landing-page/public/data')
    parser.add_argument('--check', action='store_true', help='verify every dataset in the index is up to date')
    args = parser.parse_args(argv)
    try:
        if args.check:
            index, stale = _read_index(args.data_dir), []
            for entry in index['datasets']:
                _, text, fresh = _build(_abs(entry['report']), _abs(entry['snapshot']))
                current = (args.data_dir / entry['pack'])
                if fresh != entry or not current.exists() or current.read_text(encoding='utf-8') != text:
                    stale.append(entry['id'])
            if stale or not index['datasets']:
                print(f'stale or missing: {", ".join(stale) or "no datasets"}; rerun with --report and --snapshot', file=sys.stderr)
                return 1
            print(f'{len(index["datasets"])} dataset(s) up to date')
            return 0
        if not args.report or not args.snapshot:
            parser.error('--report and --snapshot are required unless --check')
        pack, text, entry = _build(args.report, args.snapshot)
    except (OSError, ValueError, PackError, PublicSourceError) as exc:
        print(f'cannot build review pack: {exc}', file=sys.stderr)
        return 2
    args.data_dir.mkdir(parents=True, exist_ok=True)
    (args.data_dir / entry['pack']).write_text(text, encoding='utf-8')
    index = _read_index(args.data_dir)
    others = [e for e in index['datasets'] if e['id'] != entry['id']]
    index = {**index, 'datasets': sorted([*others, entry], key=lambda e: e['id'])}
    (args.data_dir / INDEX).write_text(json.dumps(index, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    if entry['report'].startswith('output/'):
        print('warning: the report is under output/ (not committed); copy it to examples/nhtsa/runs/ first', file=sys.stderr)
    print(f'wrote {entry["pack"]}: {len(pack["recalls"])} recalls; index has {len(index["datasets"])} dataset(s)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
