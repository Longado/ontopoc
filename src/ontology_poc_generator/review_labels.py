"""Human reviews as a label store, and three ways of judging compared against them."""
from __future__ import annotations

import json
import re

EXPORT_SCHEMA = 'public_review_export.v1'
LABEL_SCHEMA = 'review_label.v1'
HUMAN_MARKS = {'same': 'yes', 'different': 'no', 'unsure': None}
HUMAN_LABELS = {'same': '同一故障', 'different': '不是', 'unsure': '说不清'}
# The iteration-1 baseline, kept fixed: a fire flag, or a fire word at the start of a word ("misfire" is not one).
RULE_WORDS = re.compile(r'\b(?:fire|smoke|burn|flame|thermal|melt)', re.IGNORECASE)
RULE_VERSION = 'fire_keywords.v1'
_VIN_CHARS = '[A-HJ-NPR-Z0-9]'
_UNCLEAN = (('本机路径', re.compile(r'/Users/|/home/|[A-Za-z]:\\')),
            ('疑似密钥', re.compile(r'\bsk-[A-Za-z0-9_-]{16,}')),
            # an 11-character VIN prefix or a full 17-character VIN: letters and digits mixed, no I/O/Q
            ('疑似车架号', re.compile(rf'\b(?=[A-HJ-NPR-Z0-9]*\d)(?=[A-HJ-NPR-Z0-9]*[A-HJ-NPR-Z]){_VIN_CHARS}{{11}}(?:{_VIN_CHARS}{{6}})?\b')),
            ('邮箱', re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+')),
            ('电话', re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)|\+\d{1,3}[\s-]?\d[\d\s-]{6,}\d|\(\d{3}\)\s?\d{3}-\d{4}|(?<!\d)\d{3}-\d{3}-\d{4}(?!\d)')))


class LabelError(ValueError):
    """The download cannot become labels without misrepresenting what was reviewed."""


def read_json_file(path, *, lines: bool = False):
    """Read a JSON (or JSON-lines) file, turning missing and malformed files into plain messages."""
    try:
        text = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        raise LabelError(f'找不到文件：{path}') from None
    try:
        return [json.loads(line) for line in text.splitlines() if line.strip()] if lines else json.loads(text)
    except ValueError:
        raise LabelError(f'{path} 不是有效的 JSON') from None


def labels_from_export(export: dict, pack: dict, reviewer: str | None, imported_at: str) -> list[dict]:
    if export.get('schema') != EXPORT_SCHEMA:
        raise LabelError(f'不是复核页的下载文件（需要 {EXPORT_SCHEMA}）')
    dataset = pack['dataset']['id']
    if export.get('dataset') != dataset:
        raise LabelError(f'下载文件的数据集是 {export.get("dataset")!r}，不是 {dataset}')
    if export.get('ontology_hash') != pack['ontology']['hash']:
        raise LabelError('下载文件的本体与当前页面数据不一致：复核时看到的范围和现在的不是同一份，请用当前页面重新复核')
    who = (reviewer or export.get('reviewer') or '').strip()
    if not who:
        raise LabelError('缺少复核人：页面"结果"页填写，或导入时加 --reviewer')
    members, candidates = {}, {}
    for recall in pack['recalls']:
        members.setdefault(recall['series'], []).append(recall['id'])
        for c in recall['candidates']:
            candidates.setdefault((recall['series'], c['id']), c)
    rows = []
    for r in export.get('reviews') or []:
        key = (r.get('recall'), r.get('complaint'))
        if key not in candidates:
            raise LabelError(f'投诉 {key[1]} 不是召回 {key[0]} 的候选')
        if r.get('human') not in HUMAN_MARKS:
            raise LabelError(f'投诉 {key[1]} 的人工结论 {r.get("human")!r} 无法识别')
        check = candidates[key].get('text_check') or {}
        signal = pack['signals'][key[1]]
        rows.append({
            'schema': LABEL_SCHEMA, 'dataset': dataset, 'ontology_hash': pack['ontology']['hash'],
            'series': key[0], 'series_recalls': members[key[0]], 'complaint': key[1],
            'bucket': candidates[key]['bucket'], 'human': r['human'], 'note': r.get('note') or '',
            'model_verdict': check.get('verdict'), 'model': check.get('model'), 'prompt_version': check.get('prompt_version'),
            'reviewer': who, 'reviewed_at': r.get('updated_at'), 'imported_at': imported_at,
            'flags': list(signal.get('flags') or []),
            # the complaint text stays in the page data; the public label store keeps only the rule's result
            'rule_verdict': rule_verdict({'flags': signal.get('flags') or [],
                                          'text': '\n'.join(f['value'] for f in signal.get('fields') or [])}),
            'rule_version': RULE_VERSION,
        })
    return rows


def label_key(row: dict) -> tuple:
    return row['reviewer'], row['series'], row['complaint']


def merge_labels(existing: list[dict], new: list[dict]) -> tuple[list[dict], list[dict]]:
    """The latest import wins per reviewer, series and complaint; returns (merged, rows whose verdict or note changed)."""
    incoming = {label_key(r): r for r in new}
    merged = [incoming.get(label_key(r), r) for r in existing]
    overwritten = [r for r in existing if label_key(r) in incoming
                   and (r['human'], r['note']) != (incoming[label_key(r)]['human'], incoming[label_key(r)]['note'])]
    known = {label_key(r) for r in existing}
    return merged + [r for r in new if label_key(r) not in known], overwritten


def check_clean(rows: list[dict]) -> None:
    for row in rows:
        for field, value in row.items():
            for name, pattern in _UNCLEAN:
                if isinstance(value, str) and pattern.search(value):
                    raise LabelError(f'投诉 {row.get("complaint")} 的 {field} 含{name}，样本库是公开的，请在页面上改掉后重新下载')


def rule_verdict(label: dict) -> str:
    return 'yes' if 'fire' in label.get('flags', []) or RULE_WORDS.search(label.get('text') or '') else 'no'


def _model(label: dict) -> str:
    return label.get('model_verdict') if label.get('model_verdict') in ('yes', 'no') else 'unknown'


METHODS = {
    'rule': lambda label: label['rule_verdict'],
    'model': _model,
    'rule_then_model': lambda label: _model(label) if label['rule_verdict'] == 'yes' else 'no',
}


def compare(labels: list[dict]) -> dict:
    """Counts only: agreement with the human, misses, extras and undecided per method. Unsure labels are left out."""
    decided = [l for l in labels if HUMAN_MARKS.get(l['human'])]
    several = len({l['reviewer'] for l in labels}) > 1
    methods = {}
    for name, judge in METHODS.items():
        tally = {'agree': 0, 'missed': [], 'extra': [], 'undecided': []}
        for l in decided:
            verdict, ref = judge(l), f'{l["series"]}/{l["complaint"]}' + (f'（{l["reviewer"]}）' if several else '')
            if verdict == 'unknown':
                tally['undecided'].append(ref)
            elif verdict == HUMAN_MARKS[l['human']]:
                tally['agree'] += 1
            else:
                tally['missed' if verdict == 'no' else 'extra'].append(ref)
        methods[name] = tally
    return {'samples': len(decided), 'unsure': len(labels) - len(decided),
            'reviewers': len({l['reviewer'] for l in labels}), 'methods': methods}
