"""Compare rule, model, and rule-then-model against human labels. Prints counts only, never percentages."""
import argparse
import json
from pathlib import Path
import sys

from ontology_poc_generator.review_labels import compare

NAMES = {'rule': '只用规则', 'model': '只用模型', 'rule_then_model': '先规则再看模型'}


def _table(labels: list[dict]) -> list[str]:
    result = compare(labels)
    lines = [f'样本 {result["samples"]} 条（复核人 {result["reviewers"]} 位；"说不清" {result["unsure"]} 条不计入）',
             '', '| 做法 | 与人一致 | 该判是却判否 | 该判否却判是 | 没有结论 |', '|---|---|---|---|---|']
    for key, name in NAMES.items():
        m = result['methods'][key]
        lines.append(f'| {name} | {m["agree"]} | {len(m["missed"])} | {len(m["extra"])} | {len(m["undecided"])} |')
    for key, name in NAMES.items():
        m = result['methods'][key]
        for field, what in (('missed', '该判是却判否'), ('extra', '该判否却判是')):
            if m[field]:
                lines.append(f'- {name} · {what}：{", ".join(m[field])}')
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', type=Path, required=True, help='examples/labels/<dataset>.jsonl')
    args = parser.parse_args(argv)
    try:
        labels = [json.loads(line) for line in args.labels.read_text(encoding='utf-8').splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        print(f'cannot read labels: {exc}', file=sys.stderr)
        return 2
    out = ['规则是迭代 1 的起火基线：投诉标了起火，或原文有以 fire / smoke / burn / flame / thermal / melt 开头的词；'
           '它只对起火类召回有意义。', '只列条数，不换算比例：一次试用的样本只够看方向。', '', '## 全部', '', *_table(labels)]
    series = sorted({l['series'] for l in labels})
    if len(series) > 1:
        for s in series:
            out += ['', f'## 召回 {s}', '', *_table([l for l in labels if l['series'] == s])]
    print('\n'.join(out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
