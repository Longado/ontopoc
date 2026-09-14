"""Add a review-page download to the label store: examples/labels/<dataset>.jsonl (latest import wins)."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from ontology_poc_generator.review_labels import (
    HUMAN_LABELS, LabelError, check_clean, label_key, labels_from_export, merge_labels, read_json_file,
)

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='the file downloaded from the review page')
    parser.add_argument('--reviewer', help='required: the reviewer\'s code name (the label store is public; the name typed in the page is not used)')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'landing-page/public/data')
    parser.add_argument('--labels-dir', type=Path, default=ROOT / 'examples/labels',
                        help='label store; the default is committed to the public repo')
    args = parser.parse_args(argv)
    try:
        export = read_json_file(args.input)
        index = read_json_file(args.data_dir / 'index.json')
        entry = next((e for e in index['datasets'] if e['id'] == export.get('dataset')), None)
        if entry is None:
            raise LabelError(f'页面数据里没有数据集 {export.get("dataset")!r}，请确认下载文件来自当前页面')
        pack = read_json_file(args.data_dir / entry['pack'])
        rows = labels_from_export(export, pack, args.reviewer, datetime.now(timezone.utc).isoformat(timespec='seconds'))
        check_clean(rows)
        if not args.reviewer:
            typed = export.get('reviewer') or ''
            raise LabelError('导入时要用 --reviewer 写明复核人代号；样本库是公开的，不直接用页面里填的名字'
                             + (f'（文件里是"{typed}"）' if typed else ''))
        path = args.labels_dir / f'{entry["id"]}.jsonl'
        existing = read_json_file(path, lines=True) if path.exists() else []
    except (OSError, ValueError, KeyError, AttributeError, TypeError) as exc:
        print(f'无法导入：{exc}', file=sys.stderr)
        return 2
    merged, overwritten = merge_labels(existing, rows)
    known, fresh = {label_key(r) for r in existing}, {label_key(r): r for r in rows}
    added = sum(k not in known for k in fresh)
    args.labels_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in merged), encoding='utf-8')
    print(f'导入 {len(rows)} 条到 {path.name}：新增 {added} 条，改动 {len(overwritten)} 条，'
          f'未变 {len(rows) - added - len(overwritten)} 条；样本库现有 {len(merged)} 条')
    for old in overwritten:
        new = fresh[label_key(old)]
        change = (f'{HUMAN_LABELS[old["human"]]} → {HUMAN_LABELS[new["human"]]}' if old['human'] != new['human']
                  else f'{HUMAN_LABELS[new["human"]]}（备注有改动）')
        print(f'  改动 {old["reviewer"]} {old["series"]}/{old["complaint"]}：{change}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
