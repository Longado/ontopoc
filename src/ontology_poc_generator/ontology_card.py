"""The data-meaning card (口径卡): one card per uploaded table. What code can read off the rows is filled in (how many
rows, which columns identify an object and whether they do it uniquely, the first and last date in a date column);
what only a person can say is left empty for the consultant to fill with the client's answer: is a column a figure
that can be added up, which time a date column is, what one row is, whether an object is all in the data.

Every cell has a stable id built from the table and the column (never a count or a name the model chose), so an answer
stays with the cell across runs of the same file. The questions follow the card: a running total is not added up, a
period-to-date amount is added up on one period only, and an object that is only partly in the data says so beside
the answer. No model is called here.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import itertools
import re

from ontology_poc_generator.derived_measures import to_number
from ontology_poc_generator.handover_form import _PADDED, source_profile
from ontology_poc_generator.ontology_confirm import without_wrong
from ontology_poc_generator.public_ontology import _conditions, build_graph, normalize_proposal, normalize_value, resolve

MAX_NOTE, MAX_BASIS, MAX_BY = 300, 200, 40
HISTORY = 200      # changes kept in the file, the oldest dropped first
EXAMPLES = 3       # duplicate keys named on a card
DATES, AMOUNTS = ('DATE', 'DATETIME'), ('INTEGER', 'DECIMAL')
PLACEHOLDERS = ('-', '--', '—', '/', 'n/a', 'na', 'null', 'none', 'nan')   # what a figure column holds where there is no figure, compared lower-cased
NOT_BUSINESS_TIME = ('fetched', 'system')   # a date column answered like this says when the row was taken or entered: it cannot fix a period

# the words a person reads for each value of each kind of cell: the page, the minutes and the MCP tools all use these
SAYS = {
    'grain': {'one_object': '一行就是一个对象', 'event': '一行是一次事件或一次修改（同一个东西有多行）',
              'period': '一行是一段时期的汇总', 'unsure': '说不清'},
    'date': {'business': '业务发生的日期', 'system': '系统录入或修改的时间', 'fetched': '取数的时间', 'unsure': '说不清'},
    'amount': {'flow': '每行是这一笔自己的数，可以跨行相加', 'running': '每次事件后的累计值', 'latest': '截至最近一次的值',
               'period_to_date': '期初到期末的累计值', 'not_amount': '不是数量（编号或代码）', 'unsure': '说不清'},
    'complete': {'full': '数据里是全的', 'partial': '数据里只有一部分', 'unsure': '说不清'},
}

NO_CARD = {'tables': [], 'objects': [], 'cells': 0, 'blank': 0}   # a document, or an ontology that did not pass verification: nothing to ask


class CardError(ValueError):
    """What was posted cannot be kept; the message is shown to the user."""


def says(cell_id: str, value) -> str:
    kind = cell_id.partition(':')[0]
    if kind == 'range':
        start, end = value.get('from'), value.get('to')
        return f'声明覆盖 {start} 至 {end}' if start and end else f'声明覆盖到 {end}' if end else f'声明从 {start} 起'
    return SAYS[kind].get(value, str(value))


def complete_id(t: dict) -> str:
    """Whether an object is all in the data is asked by the table and the key it is read with, not by the type's key,
    so an answer survives the model renaming the object. Two types can be read from one table by the same key and told
    apart only by the conditions they keep rows with: those follow the key, so each type has its own cell."""
    pop = t['populated_from'][0]
    where = ';'.join(sorted(f"{c['path']}={c['equals']}" for c in _conditions(pop)))
    return f"complete:{pop['source']}|{','.join(sorted(pop['identity'].values()))}" + (f'|{where}' if where else '')


def _view(cell_id: str, answer: dict | None) -> dict | None:
    return {**answer, 'says': says(cell_id, answer['value'])} if answer else None


def _blank(answer) -> bool:
    return not answer or answer.get('value') == 'unsure'


def _span(records: list, path: str) -> tuple:
    days = [str(v)[:10] for r in records for v in resolve(r, path) if v not in (None, '')]
    return (min(days), max(days)) if days else (None, None)


def is_padded_number(text: str) -> bool:
    """03795904: it reads as a number, but the zero belongs to the id and any number type would drop it."""
    return bool(_PADDED.match(text)) and to_number(text) is not None


def _noise(records: list, path: str) -> dict | None:
    """What a text column of figures carries besides the figures: values with a thousands comma and the placeholders
    written where there is no figure. None when the column is not that: a word that is no placeholder, an id with a
    leading zero, no figure at all, or nothing but clean figures (those are typed as numbers already)."""
    thousands, held, figures = 0, Counter(), 0
    for r in records:
        for v in resolve(r, path):
            text = '' if v is None else str(v).strip()
            if not text:
                continue
            if to_number(text) is not None:   # the same reading the questions use
                if is_padded_number(text):
                    return None
                figures += 1
                thousands += ',' in text
            elif text.lower() in PLACEHOLDERS:
                held[text.lower()] += 1
            else:
                return None
    return {'thousands': thousands, 'placeholders': dict(held)} if figures and (thousands or held) else None


def _unique(records: list, fields: list) -> dict | None:
    """How many different keys the identity columns of the table give, and which keys more than one row carries. Keys
    are folded the way the graph folds them, so two spellings of one number count as the same object. A row with a
    blank identity column keeps the blank in its key as an empty string, so no row drops out; `blank` counts those rows."""
    if not fields:
        return None
    seen, shown, blank = Counter(), {}, 0
    for r in records:
        parts = [[v for v in resolve(r, f) if normalize_value(v)] for f in fields]
        blank += not all(parts)
        for combo in itertools.product(*(part or [''] for part in parts)):   # a column inside a list gives one key per element, a flat column one per row
            key = tuple(map(normalize_value, combo))
            seen[key] += 1
            shown.setdefault(key, ' · '.join(map(str, combo)))
    repeated = [key for key, n in seen.items() if n > 1]
    return {'fields': fields, 'distinct': len(seen), 'duplicates': len(repeated), 'blank': blank, 'examples': [shown[k] for k in repeated[:EXAMPLES]]}


def build_card(ontology: dict, bundle: dict, cells: dict | None = None, graph: dict | None = None, decisions: dict | None = None) -> dict:
    """The card of a run: the code facts of every table, with the stored answers (`cells`) beside them. An object a
    person judged wrong (`decisions`, as open items read them) has no cell asking whether it is all in the data; its
    table keeps its own cells, since the table is still there."""
    cells = cells or {}
    p = normalize_proposal(ontology)
    kept = {t['key'] for t in without_wrong(p, decisions)['object_types']}
    graph = graph or build_graph(ontology, bundle)
    identity = {}   # table -> object key -> the columns that identify it there
    for t in p['object_types']:
        for pop in t['populated_from']:
            identity.setdefault(pop['source'], {}).setdefault(t['key'], set()).update(pop['identity'].values())
    label = {t['key']: t.get('label') or t['key'] for t in p['object_types']}
    tables = []
    for profile in source_profile(bundle):
        name, records = profile['name'], bundle['sources'][profile['name']]['records']
        keys = identity.get(name, {})
        key_columns = sorted(set().union(*keys.values()))
        dates, amounts = [], []
        for f in profile['fields']:
            cell = f'{name}.{f["path"]}'
            if f['type'] in DATES:
                low, high = _span(records, f['path'])
                dates.append({'id': f'date:{cell}', 'range_id': f'range:{cell}', 'field': f['path'], 'type': f['type'], 'min': low, 'max': high,
                              'empty': f['empty'], 'answer': _view(f'date:{cell}', cells.get(f'date:{cell}')),
                              'declared': _view(f'range:{cell}', cells.get(f'range:{cell}'))})
            elif f['path'] not in key_columns:
                noise = _noise(records, f['path']) if f['type'] == 'VARCHAR' else None
                if f['type'] in AMOUNTS or noise:
                    amounts.append({'id': f'amount:{cell}', 'field': f['path'], 'type': f['type'], 'empty': f['empty'],
                                    'answer': _view(f'amount:{cell}', cells.get(f'amount:{cell}')), **({'noise': noise} if noise else {})})
        tables.append({'source': name, 'rows': len(records),
                       'objects': [{'type': k, 'label': label[k], 'identity': sorted(paths)} for k, paths in keys.items()],
                       'grain': {'id': f'grain:{name}', 'unique': _unique(records, key_columns), 'answer': _view(f'grain:{name}', cells.get(f'grain:{name}'))},
                       'dates': dates, 'amounts': amounts})
    counts = Counter(inst[0] for inst in graph['sources_of'])
    objects = [{'id': complete_id(t), 'type': t['key'], 'label': label[t['key']], 'count': counts[t['key']],
                'answer': _view(complete_id(t), cells.get(complete_id(t)))} for t in p['object_types'] if t['key'] in kept]
    counted = list(dict.fromkeys([*(t['grain']['id'] for t in tables), *(d['id'] for t in tables for d in t['dates']),
                                  *(a['id'] for t in tables for a in t['amounts']), *(o['id'] for o in objects)]))
    return {'tables': tables, 'objects': objects, 'cells': len(counted), 'blank': sum(_blank(cells.get(i)) for i in counted)}


def blank_by_table(card: dict) -> list[tuple]:
    """Per table that still has cells nobody answered, in the card's order: (table, how many, the date and amount
    columns among them). An object's cell is counted under the first table that object is read from."""
    objects = {o['id']: o for o in card['objects']}.values()
    out = []
    for t in card['tables']:
        columns = [c['field'] for c in (*t['dates'], *t['amounts']) if _blank(c['answer'])]
        own = sum(_blank(o['answer']) and o['id'].partition(':')[2].partition('|')[0] == t['source'] for o in objects)
        n = len(columns) + _blank(t['grain']['answer']) + own
        if n:
            out.append((t['source'], n, columns))
    return out


def card_ids(card: dict) -> set:
    """Every cell the card has as it is laid out now, the optional range cells included."""
    return {*(t['grain']['id'] for t in card['tables']), *(d[k] for t in card['tables'] for d in t['dates'] for k in ('id', 'range_id')),
            *(a['id'] for t in card['tables'] for a in t['amounts']), *(o['id'] for o in card['objects'])}


def live_cells(stored: dict, ontology: dict, bundle: dict, decisions: dict | None = None, graph: dict | None = None) -> dict:
    """The stored answers (`stored`: {cell id: answer}) that sit on the card as it is laid out now, which is what the
    questions are given. A column that went away, or an object judged wrong, leaves cells in the file that the card has
    no place for: they say nothing about the data any more. The file keeps them, so an answer comes back with its column."""
    on_card = card_ids(build_card(ontology, bundle, None, graph, decisions))
    return {i: a for i, a in stored.items() if i in on_card}


def check_by(by) -> str:
    if not isinstance(by, str) or not 0 < len(by.strip()) <= MAX_BY:
        raise CardError(f'答复人要写 1–{MAX_BY} 个字')
    return by.strip()


def clean_text(value, limit: int, what: str) -> str:
    """An optional short text, stripped; '' when it was not given."""
    if value is None:
        return ''
    if not isinstance(value, str):
        raise CardError(f'{what}要写成文字')
    if len(value.strip()) > limit:
        raise CardError(f'{what}最多 {limit} 个字')
    return value.strip()


def _day(value) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _range(cell_id: str, value) -> dict | None:
    """The covered period a person declared: either end may be left open, both left open says nothing."""
    bad = CardError(f'「{cell_id}」的时段要写成 {{"from": 日期, "to": 日期}}，日期写 YYYY-MM-DD，可以只写一头')
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {'from', 'to'}:
        raise bad
    start, end = value.get('from'), value.get('to')
    if any(d is not None and not _day(d) for d in (start, end)):
        raise bad
    if start is None and end is None:
        return None
    if start and end and start > end:
        raise CardError(f'「{cell_id}」的起始日期晚于结束日期')
    return {'from': start, 'to': end}


def check_cells(card: dict, raw, by, at: str) -> dict:
    """The answers posted for cells, ready to keep: {cell id: answer, or None to clear it}. Anything wrong raises
    CardError and nothing is returned, so a request is kept whole or not at all."""
    by = check_by(by)
    if not isinstance(raw, list):
        raise CardError('cells 要写成列表')
    on_card = card_ids(card)
    out = {}
    for entry in raw:
        if not isinstance(entry, dict):
            raise CardError('每一格的写法不对，要写成 {"id": …, "value": …}')
        cell_id = entry.get('id')
        if not isinstance(cell_id, str) or cell_id not in on_card:
            raise CardError(f'口径卡上没有这一格：{cell_id}')
        if 'value' not in entry:
            raise CardError('每一格都要写 value（清空就写 null）')
        value = entry['value']
        kind = cell_id.partition(':')[0]
        if kind == 'range':
            value = _range(cell_id, value)
        elif value is not None and not (isinstance(value, str) and value in SAYS[kind]):
            raise CardError(f'「{cell_id}」的答复只能是：{"、".join(SAYS[kind])}')
        note, basis = clean_text(entry.get('note'), MAX_NOTE, f'「{cell_id}」的备注'), clean_text(entry.get('basis'), MAX_BASIS, f'「{cell_id}」的出处')
        out[cell_id] = None if value is None else {'value': value, 'note': note, 'by': by, 'basis': basis, 'at': at}
    return out


def with_changes(stored: dict, cells: dict, items: dict, at: str) -> dict:
    """The card file after these answers (None clears one). Every change goes into the history; the same words said
    again are not a change, so the first answer keeps its date."""
    history = list(stored.get('history') or [])
    bare = lambda a: a and {k: v for k, v in a.items() if k != 'at'}
    kept = {}
    for part, changes in (('cells', cells), ('items', items)):
        now = dict(stored.get(part) or {})
        for key, new in changes.items():
            old = now.get(key)
            if bare(new) == bare(old):
                continue
            history.append({'id': key, 'old': old, 'new': new, 'at': at})
            if new is None:
                now.pop(key)
            else:
                now[key] = new
        kept[part] = now
    return {**kept, 'history': history[-HISTORY:]}


def measure_fields(measure: dict) -> list:
    """The columns a measure adds up as "table.column": its field, or every factor of a derived formula."""
    if measure.get('derived'):
        return list(dict.fromkeys(f['field'] for term in measure['derived']['terms'] for f in term['factors']))
    return [measure['field']]


def is_period_to_date(cells: dict | None, measure: dict | None) -> bool:
    """Whether the measure reads a column the card says is a period-to-date amount (any factor of a derived one). Each
    period's figure already holds the ones before it, so a number that adds periods together means nothing: a total over
    all the groups of an answer split by period, or the rows a filter removed."""
    return bool(cells and measure) and any((cells.get(f'amount:{f}') or {}).get('value') == 'period_to_date' for f in measure_fields(measure))


def _period_columns(cells: dict, bundle: dict, source: str) -> set:
    """The columns of a table that can fix a period: those with a date cell (every value in them is a DATE or DATETIME,
    as the card reads them), except one the card says is the time of fetching or entering. A date nobody has answered
    yet still counts."""
    if source not in bundle['sources']:
        return set()
    [profile] = source_profile({'sources': {source: bundle['sources'][source]}})
    return {f['path'] for f in profile['fields'] if f['type'] in DATES
            and (cells.get(f'date:{source}.{f["path"]}') or {}).get('value') not in NOT_BUSINESS_TIME}


def _on_one_period(cells: dict, bundle: dict, field: str, where: list, dims: list) -> bool:
    """A date of the amount's own table is fixed by a filter, or the answer is split by that date directly."""
    source = field.partition('.')[0]
    dates = _period_columns(cells, bundle, source)
    dated = lambda f: f.partition('.')[0] == source and f.partition('.')[2] in dates
    return any(dated(w['field']) for w in where) or any(not d['via'] and dated(d['field']) for d in dims)


def refusal(cells: dict, bundle: dict, measure: dict, where: list, dims: list) -> dict | None:
    """The answer a question gets instead of a number when the card says the column cannot be added up that way, or
    None. `where` and `dims` are the query's filters and groupings with their fields resolved to "table.column". An
    average is never stopped."""
    if measure['op'] != 'sum':
        return None
    for field in measure_fields(measure):
        cell_id, column = f'amount:{field}', field.partition('.')[2]
        meaning = (cells.get(cell_id) or {}).get('value')
        if meaning == 'running':
            reason = f'「{column}」在口径卡里是“{SAYS["amount"]["running"]}”：一行已经包含之前的数，跨行相加会重复。可以改问某一次（某个对象、某一天）的值。'
        elif meaning == 'period_to_date' and not _on_one_period(cells, bundle, field, where, dims):
            reason = (f'「{column}」在口径卡里是“{SAYS["amount"]["period_to_date"]}”：要先固定在一期上'
                      '（按同一张表里一个不是取数或录入时间的日期列，筛一个日期或按它分组），才能相加。')
        else:
            continue
        return {'status': 'query_limit', 'reason': reason, 'refused_by_card': cell_id}
    return None


def _through(answered: dict, bundle: dict, source: str) -> str | None:
    """How far the table's data goes: the declared end of each column answered as the business date, else the latest
    date in it; the latest of those."""
    records, ends = bundle['sources'][source]['records'], []
    for cell_id, answer in answered.items():
        if cell_id.startswith(f'date:{source}.') and answer['value'] == 'business':
            path = cell_id[len(f'date:{source}.'):]
            end = (answered.get(f'range:{source}.{path}') or {'value': {}})['value'].get('to') or _span(records, path)[1]
            if end:
                ends.append(end)
    return max(ends, default=None)


def evidence(cells: dict | None, bundle: dict, start: dict, measure: dict | None, where: list) -> dict | None:
    """What an answer used from the card: the tables the start object is read from with how far their data goes, the
    cells answered that the question depends on, and the objects said to be only partly in the data. None while no
    cell of the card has been answered. `start` is the start object's type, `where` the resolved filters."""
    answered = {i: a for i, a in (cells or {}).items() if not _blank(a)}
    if not answered:
        return None
    tables = []
    for source in dict.fromkeys(pop['source'] for pop in start['populated_from']):
        through = _through(answered, bundle, source)
        tables.append({'source': source, 'rows': len(bundle['sources'][source]['records']), **({'through': through} if through else {})})
    wanted = [*(f'amount:{f}' for f in (measure_fields(measure) if measure else [])),
              *(f'{kind}:{w["field"]}' for w in where for kind in ('date', 'range')), complete_id(start)]
    name = start.get('label') or start['key']
    lines = [{'id': i, 'field': name if i.startswith('complete:') else i.partition(':')[2].partition('.')[2], 'says': says(i, answered[i]['value']),
              'by': answered[i].get('by'), 'basis': answered[i].get('basis'), 'at': answered[i].get('at')}
             for i in dict.fromkeys(wanted) if i in answered]
    partly = answered.get(complete_id(start))
    incomplete = [{'type': start['key'], 'label': name, 'note': partly.get('note', ''), 'by': partly.get('by')}] if partly and partly['value'] == 'partial' else []
    return {'tables': tables, 'lines': lines, 'incomplete': incomplete}
