"""Add a review-page download to the label store: examples/labels/<dataset>.jsonl (latest import wins)."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from ontology_poc_generator.review_labels import LabelError, check_clean, labels_from_export, merge_labels

ROOT = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='the file downloaded from the review page')
    parser.add_argument('--reviewer', help='who reviewed; overrides the name in the file (use a code name, the repo is public)')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'landing-page/public/data')
    parser.add_argument('--labels-dir', type=Path, default=ROOT / 'examples/labels')
    args = parser.parse_args(argv)
    try:
        export = json.loads(args.input.read_text(encoding='utf-8'))
        index = json.loads((args.data_dir / 'index.json').read_text(encoding='utf-8'))
        entry = next((e for e in index['datasets'] if e['id'] == export.get('dataset')), None)
        if entry is None:
            raise LabelError(f'页面数据里没有数据集 {export.get("dataset")!r}，请确认下载文件来自当前页面')
        pack = json.loads((args.data_dir / entry['pack']).read_text(encoding='utf-8'))
        rows = labels_from_export(export, pack, args.reviewer, datetime.now(timezone.utc).isoformat(timespec='seconds'))
        check_clean(rows)
    except (OSError, ValueError, KeyError, AttributeError) as exc:
        print(f'cannot import reviews: {exc}', file=sys.stderr)
        return 2
    path = args.labels_dir / f'{entry["id"]}.jsonl'
    merged, overwritten = merge_labels(_read_jsonl(path), rows)
    args.labels_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in merged), encoding='utf-8')
    print(f'imported {len(rows)} review(s) into {path.name}; it now holds {len(merged)}')
    for r in overwritten:
        print(f'  overwritten: {r["reviewer"]} {r["series"]}/{r["complaint"]} (was {r["human"]}, reviewed {r["reviewed_at"]})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
