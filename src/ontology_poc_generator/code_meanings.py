"""What the codes in a table mean. A column such as 订单.状态码 holding 0, 1 and 2 says nothing by itself, and the data
cannot say it either: code can count each value and set it against the table's other columns (rows under this value
all lack 交付天数), and a model may guess a meaning from that, but only a person who knows the business can confirm one.

This module finds the code columns, writes the facts a person decides from, validates the model's guesses and a person's
answer, and turns the confirmed meanings into the text shown everywhere a code appears ("2 = 已取消"). A code nobody
confirmed is shown as unconfirmed. Where meanings are stored (element_state) and how they are asked (an open item) is
not decided here."""
from __future__ import annotations

import re

from ontology_poc_generator.agent_harness import ask_model
from ontology_poc_generator.recognition import model_failure_text

DESCRIBE_CODES_PROMPT_VERSION = 'company_code_meanings.v1'
MAX_VALUES = 12        # a column with more values than this is a category, not a code list
PATTERN_ROWS = 20      # "another column tells this value's rows from the rest" needs this many rows on both sides: by simulation
                       # (3 values, half of every other column blank at random) it fired by chance in 8-35% of runs at 10 rows
                       # a value with 5-30 other columns, 3-8% at 15, and at most 1% at 20
MAX_LABEL, MAX_DESCRIPTION, MAX_BASIS = 40, 200, 200
SHORT_CODE = re.compile(r'[0-9A-Za-z_\-]{1,4}', re.ASCII)   # a value written in words says what it means: it is not a code
YEAR = re.compile(r'(19|20)[0-9]{2}', re.ASCII)
FLAG_PAIRS = ({'y', 'n'}, {'yes', 'no'}, {'t', 'f'}, {'true', 'false'}, {'0', '1'})   # 是/否 are not ASCII: SHORT_CODE already drops them
UNCONFIRMED = '（含义未确认）'

DESCRIBE_CODES_SYSTEM_PROMPT = """你在帮顾问弄清数据表里的代码列是什么意思。每一列是几个短代码（如 0、1、2），你会收到：建模目的，每一列的表名、列名、总行数，每个取值的行数，以及代码从数据里算出来的、这个取值和表里其他列的关系（例如“这 16 行的「交付天数」全是空的”）。没有给你任何一行原始数据。

只输出 JSON：
{"columns": [{"id": "列的 id，原样照抄", "values": [{"value": "取值，原样照抄", "basis": "先写你的依据：看的是哪条事实，没有事实就直说没有", "label": "这个代码的中文含义，一般 2 到 6 个字", "description": "一句话说明；没有就写空字符串"}]}]}

规则：
- id 和 value 只能用给你的，原样照抄。
- 只有事实能支持、或这类代码在业务里公认的含义，才写 label。没有把握的取值直接不写，不要凑；只凭几个取值的个数猜含义是最常见的错。
- basis 要老实：事实没有支持这个含义时写“数据里没看出规律”，由人来决定。
"""


def _blank(value) -> bool:
    return value is None or value == ''


def _pct(share: float) -> str:
    return f'{share * 100:.0f}%' if share * 100 >= 1 or share == 0 else '不到 1%'


def _relation_facts(n: int, m: int, blank_mine: int, blank_rest: int, other: str) -> tuple[list[str], str | None]:
    """How one value's n rows differ from the m rows of the other values in whether another column is left empty. The
    column lines the value up (a pattern, 'held') only when the share left empty differs by more than half between the
    two groups and both groups have PATTERN_ROWS rows or more; a difference in fewer rows is reported as 'thin', a
    coincidence until more rows say otherwise."""
    mine, rest = blank_mine / n, blank_rest / m if m else 0
    if abs(mine - rest) <= 0.5:
        return ([f'其中「{other}」为空 {blank_mine} 行'] if blank_mine else []), None
    if mine == 1 and rest == 0:
        said = f'这 {n} 行的「{other}」全是空的，其他取值的 {m} 行都有值'
    elif mine == 0 and rest == 1:
        said = f'只有这个取值的行填了「{other}」，其他取值的 {m} 行全是空的'
    else:
        said = f'这 {n} 行里「{other}」为空的占 {_pct(mine)}，其他取值的 {m} 行里占 {_pct(rest)}'
    if min(n, m) >= PATTERN_ROWS:
        return [said], 'held'
    return [f'{said}；但比较的两组里有一组只有 {min(n, m)} 行，可能是巧合'], 'thin'


def _flag_or_year(values: set[str]) -> bool:
    """Years (2020, 2021) and yes/no pairs are values a person reads as they are, not codes to look up (what DBAutoDoc's
    EnumCandidateGate and ydata-profiling's categorical test also leave out)."""
    return all(YEAR.fullmatch(v) for v in values) or {v.lower() for v in values} in FLAG_PAIRS


def code_columns(bundle: dict, skip: frozenset = frozenset()) -> list[dict]:
    """The columns that look like code lists, from the data alone: 2 to MAX_VALUES values, each a short code, each value
    on two rows or more on average, and not a year or a yes/no pair. skip: (table, column) pairs that identify objects, which are keys, not codes. A
    candidate may still not be a code (a version number): a person says so ("不是代码") and it is not offered again.
    Each value comes with its rows, its share, and the facts that set it against the table's other columns."""
    out = []
    for source, s in bundle['sources'].items():
        records = s['records']
        names = list(dict.fromkeys(k for r in records for k in r))
        blank = {n: [_blank(r.get(n)) for r in records] for n in names}
        for column in names:
            if (source, column) in skip:
                continue
            rows_of: dict[str, list[int]] = {}
            for i, r in enumerate(records):
                if not blank[column][i]:
                    rows_of.setdefault(str(r[column]), []).append(i)
            filled = sum(len(v) for v in rows_of.values())
            if not 2 <= len(rows_of) <= MAX_VALUES or filled < 2 * len(rows_of) or not all(SHORT_CODE.fullmatch(v) for v in rows_of) or _flag_or_year(set(rows_of)):
                continue
            others = [n for n in names if n != column]
            total_blank = {n: sum(blank[n][i] for v in rows_of.values() for i in v) for n in others}
            values = []
            for value in sorted(rows_of):
                idx, facts, kinds = rows_of[value], [], set()
                for other in others:
                    blank_mine = sum(blank[other][i] for i in idx)
                    said, kind = _relation_facts(len(idx), filled - len(idx), blank_mine, total_blank[other] - blank_mine, other)
                    facts += said
                    kinds.add(kind)
                pattern = 'held' in kinds
                if not kinds & {'held', 'thin'}:
                    rest = filled - len(idx)
                    facts.append(f'只有 {len(idx)} 行，太少，看不出规律' if len(idx) < PATTERN_ROWS
                                 else f'其余取值只有 {rest} 行，太少，没法拿来比，看不出规律' if rest < PATTERN_ROWS
                                 else '和这张表里别的列没看出规律：没有哪一列能把它和其他取值分开')
                share = len(idx) / len(records)
                values.append({'value': value, 'rows': len(idx), 'share': share, 'pattern': pattern,
                               'facts': [f'{len(idx)} 行，占 {_pct(share)}', *facts]})
            out.append({'id': f'code_meaning:{source}.{column}', 'field': f'{source}.{column}', 'source': source, 'column': column,
                        'rows': len(records), 'blank': len(records) - filled, 'values': values})
    return out


def _text(value, limit: int) -> str | None:
    return value.strip() if isinstance(value, str) and len(value.strip()) <= limit else None


def clean_draft(profiles: list[dict], reply) -> dict:
    """The model's guesses that name a real column and a real value of it, with short text; the rest dropped with the reason."""
    known = {p['id']: {v['value'] for v in p['values']} for p in profiles}
    out = {'columns': {}, 'rejected': []}
    for column in reply.get('columns') if isinstance(reply, dict) and isinstance(reply.get('columns'), list) else []:
        cid = column.get('id') if isinstance(column, dict) else None
        if cid not in known:
            out['rejected'].append({'item': str(cid), 'reason': f'没有这一列：{cid}'})
            continue
        for v in column.get('values') if isinstance(column.get('values'), list) else []:
            value = v.get('value') if isinstance(v, dict) else None
            if value not in known[cid]:
                out['rejected'].append({'item': f'{cid}={value}', 'reason': f'这一列里没有取值 {value}'})
                continue
            label, description, basis = _text(v.get('label'), MAX_LABEL), _text(v.get('description') or '', MAX_DESCRIPTION), _text(v.get('basis') or '', MAX_BASIS)
            if not label or description is None or basis is None:
                out['rejected'].append({'item': f'{cid}={value}', 'reason': '含义、描述或依据不是一段短文字'})
                continue
            out['columns'].setdefault(cid, {})[value] = {'label': label, 'description': description, 'basis': basis}
    return out


def draft_meanings(profiles: list[dict], gateway, purpose: str) -> dict:
    """One call for all the columns. The model sees counts and facts, never a row."""
    request = {'purpose': purpose, 'columns': [
        {'id': p['id'], 'table': p['source'], 'column': p['column'], 'rows': p['rows'],
         'values': [{'value': v['value'], 'facts': v['facts']} for v in p['values']]} for p in profiles]}
    out = {'prompt_version': DESCRIBE_CODES_PROMPT_VERSION, 'model': None, 'columns': {}, 'rejected': [], 'error': None}
    judgement = ask_model(gateway, 'field_describer', DESCRIBE_CODES_PROMPT_VERSION, DESCRIBE_CODES_SYSTEM_PROMPT, request)
    out['model'] = judgement.model
    if judgement.failure == 'request':
        return {**out, 'error': model_failure_text(judgement.message)}
    if judgement.failure == 'not_json' or not isinstance(judgement.reply, dict) or not isinstance(judgement.reply.get('columns'), list):
        return {**out, 'error': '模型返回的不是约定的 JSON'}
    return {**out, **clean_draft(profiles, judgement.reply)}


def check_enum(profile: dict, posted) -> list[dict]:
    """A person's answer for some values of one column as {value, label, description} entries. A blank label takes that
    value's meaning back. Raises ValueError, with the text the person reads, when it cannot be kept."""
    if not isinstance(posted, list) or not posted:
        raise ValueError('values 要写成列表，至少一项')
    known = {v['value'] for v in profile['values']}
    kept = []
    for entry in posted:
        if not isinstance(entry, dict) or entry.get('value') not in known:
            raise ValueError(f'这一列里没有取值 {entry.get("value") if isinstance(entry, dict) else entry}')
        label, description = entry.get('label') or '', entry.get('description') or ''
        if not isinstance(label, str) or len(label.strip()) > MAX_LABEL:
            raise ValueError(f'取值 {entry["value"]} 的含义要写 1–{MAX_LABEL} 个字')
        if not isinstance(description, str) or len(description.strip()) > MAX_DESCRIPTION:
            raise ValueError(f'取值 {entry["value"]} 的说明最多 {MAX_DESCRIPTION} 个字')
        kept.append({'value': entry['value'], 'label': label.strip(), 'description': description.strip()})
    return kept


def merge_enum(kept: list[dict], posted: list[dict]) -> list[dict]:
    """The meanings on file with a person's answer put over them: what was not mentioned stays, a blank label removes."""
    merged = {e['value']: e for e in kept}
    for e in posted:
        if e['label']:
            merged[e['value']] = e
        else:
            merged.pop(e['value'], None)
    return [merged[v] for v in sorted(merged)]


def meanings_of(profiles: list[dict], enums: dict) -> dict:
    """{field: {'labels': {value: label}}} for every code column, confirmed or not: what shown() reads."""
    return {p['field']: {'labels': {e['value']: e['label'] for e in (enums.get(p['field']) or {}).get('values', [])}} for p in profiles}


def shown(meanings: dict | None, field: str, value) -> str:
    """A code as people read it: "2 = 已取消" once confirmed, "2（含义未确认）" until then, anything else as written."""
    code = (meanings or {}).get(field)
    if code is None:
        return value
    label = code['labels'].get(str(value))
    return f'{value} = {label}' if label else f'{value}{UNCONFIRMED}'


def codes_for_label(meanings: dict | None, field: str, value) -> list:
    """The codes a question's value stands for: itself when it is a code, else every code confirmed to mean it ("已交付"
    may be 0 and 1 both); the value as given when nothing matches."""
    code = (meanings or {}).get(field)
    if code is None or value in code['labels']:
        return [value]
    return [c for c, label in code['labels'].items() if label == value] or [value]


def shown_codes(meanings: dict | None, field: str, codes: list) -> str:
    """One code as shown(); several that were confirmed to mean the same as "0, 1 = 已交付"."""
    code = (meanings or {}).get(field)
    if len(codes) > 1 and code is not None and len({code['labels'].get(c) for c in codes}) == 1 and code['labels'].get(codes[0]):
        return f'{", ".join(codes)} = {code["labels"][codes[0]]}'
    return shown(meanings, field, codes[0])
