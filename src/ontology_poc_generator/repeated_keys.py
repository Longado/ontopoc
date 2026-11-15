"""A key that repeats in the table describing an object (客户 KH012 on two rows). The data cannot say which row is right,
and the object graph counts one object either way, so nothing is merged away until a person says how the rows are to be
read: keep both, keep the latest by a column they name, or call it a data error for the client to fix. Until then the
object list shows every row. Failing the load, or keeping the first or last row by a default, would each make that choice
for the person; here the build collapses nothing until the choice is made.

This module finds the repeats, checks a choice, picks the row "latest" means and says which rows a choice leaves out
(build_graph applies that before any row is read). Where the choice is stored (element_state) and how it is asked (an
open item) is not decided here."""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

from ontology_poc_generator.public_ontology import normalize_proposal
from ontology_poc_generator.workspace_store import describes_rows

RULES = ('keep_both', 'keep_latest', 'data_error')
EXAMPLES = 3
DIFFERING_COLUMNS = 5


def rule_key(type_key: str, source: str) -> str:
    return f'{type_key}.{source}'


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


# 2026-01-05, 2026/1/5, 2026.1.5, 2026年1月5日, each optionally followed by a time and a zone (Z or +08:00)
_DATE = re.compile(r'(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?(?:[T ]+(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})?)?', re.ASCII)
_MONTH = re.compile(r'(\d{4})[-/年](\d{1,2})月?', re.ASCII)   # 2026-01: the first of the month (no dot: 2026.1 is a number)


def _when(value):
    """A date or date-time as a naive UTC datetime, so that any two can be compared (a zone-less value is taken as it is);
    None when it is not one."""
    text = str(value).strip()
    if month_only := _MONTH.fullmatch(text):
        text = f'{month_only[1]}-{month_only[2]}-1'
    m = _DATE.fullmatch(text)
    if not m:
        return None
    year, month, day, hour, minute, second, zone = m.groups()
    try:
        moment = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0))
    except ValueError:
        return None
    if zone and zone != 'Z':
        sign = 1 if zone[0] == '+' else -1
        digits = zone[1:].replace(':', '')
        moment -= sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
    return moment


def _kind(filled: list) -> str | None:
    """How these filled values are ordered: as numbers, as dates, or not at all (None). Text has no order a person meant."""
    if all(_number(v) is not None for v in filled):
        return 'number'
    return 'date' if all(_when(v) is not None for v in filled) else None


def _order_key(kind: str, value):
    return _number(value) if kind == 'number' else _when(value)


def column_order(records: list[dict], rows: list[list[int]], column: str) -> str:
    """What a column says about which of the rows of one key is latest, over the repeated rows only (`rows`: the row
    numbers of each key): 'number' or 'date' when every filled value reads as one and some key's rows differ in it; 'same'
    when no key's rows differ; 'empty' when none is filled; 'text' otherwise (a city or a name has no order)."""
    filled = [v for group in rows for v in (records[i].get(column) for i in group) if v not in (None, '')]
    if not filled:
        return 'empty'
    kind = _kind(filled)
    if kind is None:
        return 'text'
    differs = any(len({_order_key(kind, v) for v in (records[i].get(column) for i in group) if v not in (None, '')}) > 1 for group in rows)
    return kind if differs else 'same'


def latest_row(records: list[dict], rows: list[int], column: str) -> int:
    """Of these rows of one table, the one with the largest value in the column, by value for numbers and dates (else
    by the text as written). A blank is the oldest, and a tie goes to the row later in the file."""
    values = {i: records[i].get(column) for i in rows}
    kind = _kind([v for v in values.values() if v not in (None, '')])
    key = lambda i: ((0, 0) if values[i] in (None, '') else (1, _order_key(kind, values[i]) if kind else str(values[i])), i)
    return max(rows, key=key)


def tie_or_blank(records: list[dict], rows: list[int], column: str) -> dict:
    """What "latest by this column" leaves unsaid for one key: {'tie': True} when the row taken shares its value with
    another row (the later row of the file won), {'blank': True} when some row has no value in the column (a blank counts
    as the oldest). A key whose rows are all blank is both."""
    values = [records[i].get(column) for i in rows]
    filled = [v for v in values if v not in (None, '')]
    kind = _kind(filled)
    ordered = [_order_key(kind, v) if kind else str(v) for v in filled]
    tied = not filled or ordered.count(max(ordered)) > 1
    return {**({'tie': True} if tied else {}), **({'blank': True} if len(filled) < len(values) else {})}


def _differences(records: list[dict], rows: list[int], skip: set) -> list[tuple[str, list[str]]]:
    """The columns (other than the key) on which these rows disagree, with each row's value."""
    out = []
    for column in dict.fromkeys(k for i in rows for k in records[i]):
        if column in skip:
            continue
        values = [str(records[i].get(column) if records[i].get(column) is not None else '') for i in rows]
        if len(set(values)) > 1:
            out.append((column, values))
    return out[:DIFFERING_COLUMNS]


def repeated_keys(ontology: dict, bundle: dict, graph: dict) -> list[dict]:
    """One entry per (object type, table that describes it) where some identities sit on more than one row of the table.
    A table that only mentions the object (orders naming customers) repeats by nature and is not listed. Each object:
    its identity as written, the table's row numbers (0-based, in the order of the file) and where the rows differ."""
    own = describes_rows(ontology)
    populations = {(t['key'], pop['source']): set(pop['identity'].values()) for t in normalize_proposal(ontology)['object_types'] for pop in t['populated_from']}
    groups: dict[tuple, list] = {}
    for inst, pairs in graph.get('records_all', graph['records_of']).items():   # every row, whatever a choice has left out of the graph
        by_source: dict[str, set] = {}
        for source, index in pairs:
            if own(inst[0], source):
                by_source.setdefault(source, set()).add(index)
        for source, rows in by_source.items():
            if len(rows) > 1:
                records = bundle['sources'][source]['records']
                ordered = sorted(rows)
                groups.setdefault((inst[0], source), []).append(
                    {'identity': '|'.join(str(v) for _, v in inst[1]), 'rows': ordered,
                     'differs': _differences(records, ordered, populations.get((inst[0], source), set()))})
    out = []
    for (t, s), objects in groups.items():
        records = bundle['sources'][s]['records']
        columns = list(dict.fromkeys(k for r in records for k in r))
        order = {c: column_order(records, [o['rows'] for o in objects], c) for c in columns}
        out.append({'id': f'repeated_key:{rule_key(t, s)}', 'rule_key': rule_key(t, s), 'type': t, 'source': s, 'objects': objects,
                    'rows': sum(len(o['rows']) for o in objects), 'columns': columns, 'order': order,
                    'latest_columns': [c for c in columns if order[c] in ('number', 'date')]})
    return out


def unmet(group: dict, rule: dict | None) -> str | None:
    """Why a rule a person chose no longer holds for this group, in the words the open item starts with; None when it
    holds. "Latest by a column" needs that column to be in the table and to order the repeated rows (a later upload may
    have dropped it, or filled it with text). A choice was made for the keys that repeated then (`covers`): a key that
    repeats now and was not among them has not been decided about."""
    if not rule:
        return None
    if rule['rule'] == 'keep_latest' and rule.get('column') not in group['latest_columns']:
        return f'上次选的是按「{rule.get("column")}」只留最新的，但这一列现在不在表里或分不出先后。'
    new = [o['identity'] for o in group['objects'] if rule.get('covers') is not None and o['identity'] not in set(rule['covers'])]
    if new:
        return f'上次的选择只管到当时重复的编号，现在又有新的重复编号：{"、".join(new[:EXAMPLES])}{"等" if len(new) > EXAMPLES else ""}。'
    return None


def applicable(group: dict, rule: dict | None) -> dict | None:
    """The rule a person chose for this group as long as it still holds (see unmet)."""
    return None if unmet(group, rule) else rule


def rows_left_out(ontology: dict, bundle: dict, graph: dict) -> dict:
    """(object type, table, row number) -> the row kept instead, for every row a "keep the latest" choice leaves out."""
    chosen = bundle.get('repeat_rules') or {}
    out = {}
    for g in repeated_keys(ontology, bundle, graph):
        rule = applicable(g, chosen.get(g['rule_key']))
        if rule and rule['rule'] == 'keep_latest':
            records = bundle['sources'][g['source']]['records']
            for o in g['objects']:
                keep = latest_row(records, o['rows'], rule['column'])
                out.update({(g['type'], g['source'], i): keep for i in o['rows'] if i != keep})
    return out


def settled_by_latest(ontology: dict, bundle: dict, graph: dict) -> set:
    """(object type, table, identity) of the keys whose rows a person's "keep the latest" choice has settled: the object
    now has one row, so the check's finding that its rows disagree no longer describes what is read."""
    chosen = bundle.get('repeat_rules') or {}
    return {(g['type'], g['source'], o['identity']) for g in repeated_keys(ontology, bundle, graph)
            if (applicable(g, chosen.get(g['rule_key'])) or {}).get('rule') == 'keep_latest' for o in g['objects']}


def data_error_uses(ontology: dict, bundle: dict, graph: dict, used, label) -> list[dict]:
    """The repeated keys a person called a data error, for the objects `used` (instances of an answer): per type and table
    how many of them are such keys and the first few. An answer that read these rows rests on data the client is to fix."""
    chosen = bundle.get('repeat_rules') or {}
    if not any(r['rule'] == 'data_error' for r in chosen.values()):
        return []
    name = lambda inst: '|'.join(str(v) for _, v in inst[1])
    out = []
    for g in repeated_keys(ontology, bundle, graph):
        if (chosen.get(g['rule_key']) or {}).get('rule') != 'data_error':
            continue
        bad = {o['identity'] for o in g['objects']}
        hit = [name(i) for i in used if i[0] == g['type'] and name(i) in bad]
        if hit:
            out.append({'type': label(g['type']), 'source': g['source'], 'objects': len(hit), 'examples': hit[:EXAMPLES]})
    return out


def check_rule(group: dict, posted) -> dict:
    """A person's choice for one repeated-key group, as {'rule'} or {'rule': 'keep_latest', 'column'}. Raises ValueError
    with the text the person reads when it cannot be kept."""
    if not isinstance(posted, dict) or posted.get('rule') not in RULES:
        raise ValueError('要选一种处理办法：每一行都留、只留最新的，或当作数据错误')
    covers = sorted(o['identity'] for o in group['objects'])   # the keys this choice is made for: one that repeats later is asked about again
    if posted['rule'] != 'keep_latest':
        if posted.get('column') is not None:
            raise ValueError('只有“只留最新的”才要选列')
        return {'rule': posted['rule'], 'covers': covers}
    column = posted.get('column')
    if column not in group['columns']:
        raise ValueError(f'要选「{group["source"]}」表里的一列，按它的大小定哪一行最新')
    said = {'text': '不是数字或日期，没法按它定哪一行最新', 'same': '在这些重复的行里取值都一样，分不出哪一行最新',
            'empty': '在这些重复的行里都是空的，分不出哪一行最新'}.get(group['order'][column])
    if said:
        usable = [c for c in group['columns'] if group['order'][c] in ('number', 'date')]
        raise ValueError(f'「{column}」{said}' + (f'。可以用的有：{"、".join(usable)}' if usable else '。这张表里没有一列能分出先后，只能每一行都留，或当作数据错误'))
    return {'rule': 'keep_latest', 'column': column, 'covers': covers}
