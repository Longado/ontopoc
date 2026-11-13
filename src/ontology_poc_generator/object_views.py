"""Views on the workspace: a named choice of the rows of one object type, kept like the type itself. A view is one element (objview:<name>) with a person's
definition, a state, a confirmation snapshot and what it reads (element_dep: the type, its dataset, and the meanings its conditions use).

A view is an object type plus conditions and/or "latest per key":
  conditions   a code column "is" or "is not" one of its meanings (订单.状态码 不是 已取消); all of them must hold
  latest       one row per key, the one with the greatest value of an ordering column (库存快照: per 产品编号 the greatest 快照月份); a row with no key stays.
               It is taken first and the conditions are applied to what it leaves, so a later version that is cancelled drops the object, an earlier one does not
               come back. Ties go to the row that comes later in the file.
Only the choice of rows is the view's: the values an answer reads are the type's own. Saving shows how many rows it keeps of how many (the evidence a
person reads); confirming is another builder, the version and the counts they saw (409 when either moved), the type and the meanings it names confirmed.
A view goes to needs_look when the type or a meaning under it does (object_types._flag follows element_dep) and when a new upload changes how many rows it
keeps or the rows there are (recheck_dependents calls view_problems). Saving with another type, conditions or latest rule puts it forward again; the
description is an edit only. The name is the id, so it is fixed from creation. Who sees a view follows its type (a viewer: confirmed ones only).

Question answering reads confirmed views through workspace_questions: named_views' per-run views are SQL over a run's stored tables and stay as they are; this
is the same idea over the workspace's elements, picked by rows in code (answer_checks.definition_check and choose_rows are the engine's, shared).
"""
from __future__ import annotations

import hashlib
import json

from ontology_poc_generator.named_views import NUMERIC, orderable
from ontology_poc_generator.object_types import (
    MAX_DESCRIPTION, MAX_NAME, TYPE_PREFIX, VIEW_PREFIX, TypeRefused, _content, _edit_names, _state_view, _text, _type_row, _visible,
    dataset_columns, element_row, enum_id, log_entries, type_id, write_confirmation, write_elements)
from ontology_poc_generator.public_ontology import normalize_value
from ontology_poc_generator.row_rules import positions as row_positions, restriction
from ontology_poc_generator.workspace_store import current_dataset, dataset_records

OPS = {'is': '是', 'is_not': '不是'}
MAX_FILTERS = 5


def view_id(name: str) -> str:
    return f'{VIEW_PREFIX}{name}'


def meaning_labels(conn, english_name: str, column: str) -> dict[str, str]:
    """{code: label} of the meanings on file for this column, in whatever state; empty when none."""
    row = element_row(conn, enum_id(english_name, column))
    return {e['value']: e['label'] for e in _content(row)['values'] if e['label']} if row and row['content_json'] else {}


# --- which rows a definition keeps ---------------------------------------------------------------------------------------------------------------------

def _rank(value, numeric: bool) -> tuple:
    """A value of the ordering column as something that can be compared: blank or unreadable ranks below every value."""
    text = '' if value is None else str(value).strip()
    if numeric:
        try:
            return (1, float(text)) if text else (0, 0.0)
        except ValueError:
            return (0, 0.0)
    return (1, text) if text else (0, '')


def kept_positions(records: list[dict], kinds: dict[str, str], labels: dict[str, dict[str, str]], content: dict) -> list[int]:
    """The positions (from 1) of the rows of `records` this definition keeps. kinds: {column: inferred type}, labels: {column: {code: label}} of the columns
    the conditions name."""
    positions = list(range(1, len(records) + 1))
    latest = content.get('latest')
    if latest:
        numeric = kinds[latest['order']] in NUMERIC
        best: dict[tuple, tuple] = {}
        loose = []
        for i, record in enumerate(records, 1):
            key = tuple(normalize_value(record.get(c)) for c in latest['key'])
            if not all(key):   # a row with no key names no object: it stays
                loose.append(i)
                continue
            rank = (_rank(record.get(latest['order']), numeric), i)   # the later row wins a tie
            if key not in best or rank > best[key][0]:
                best[key] = (rank, i)
        positions = sorted([p for _, p in best.values()] + loose)
    for f in content['filters']:
        wanted = {normalize_value(code) for code, label in labels[f['column']].items() if label == f['label']}
        positions = [p for p in positions if (normalize_value(records[p - 1].get(f['column'])) in wanted) == (f['op'] == 'is')]
    return positions


def _read_problems(conn, content: dict) -> tuple[list[str], dict | None, dict]:
    """(what stops the definition being read now, in words; the current dataset; its columns)."""
    type_row = element_row(conn, type_id(content['type']))
    if type_row is None:
        return [f'对象类型“{content["type"]}”已经不在了'], None, {}
    dataset = current_dataset(conn, _content(type_row)['dataset'])
    if dataset is None:
        return [f'数据集“{_content(type_row)["dataset"]}”已经不在了'], None, {}
    cols = dataset_columns(conn, dataset['id'])
    problems = []
    latest = content.get('latest')
    named = [*(f['column'] for f in content['filters']), *((latest['key'] + [latest['order']]) if latest else [])]
    gone = [c for c in dict.fromkeys(named) if c not in cols]
    if gone:
        return [f'{dataset["name"]} 第 {dataset["version"]} 版里没有这些列了：{"、".join(gone)}'], dataset, cols
    for f in content['filters']:
        if f['label'] not in meaning_labels(conn, content['type'], f['column']).values():
            problems.append(f'“{f["label"]}”现在不是“{f["column"]}”已写的含义')
    if latest and not orderable(cols[latest['order']]['type']):
        problems.append(f'“{latest["order"]}”现在的内容排不出先后（数字、年月、日期才可以）')
    return problems, dataset, cols


def view_summary(conn, content: dict) -> dict:
    """The definition on the current data: {'problems': [...]} when it cannot be read, else {'problems': [], 'rows': kept, 'of': all, 'dataset', 'version',
    'positions'}."""
    problems, dataset, cols = _read_problems(conn, content)
    if problems:
        return {'problems': problems}
    records = dataset_records(conn, dataset)
    labels = {f['column']: meaning_labels(conn, content['type'], f['column']) for f in content['filters']}
    positions = kept_positions(records, {n: c['type'] for n, c in cols.items()}, labels, content)
    return {'problems': [], 'rows': len(positions), 'of': len(records), 'dataset': dataset['name'], 'version': dataset['version'], 'positions': positions,
            'signature': _signature(records, positions, content, _content(element_row(conn, type_id(content['type'])))['key'])}


def _signature(records: list[dict], positions: list[int], content: dict, type_key: list[str]) -> str:
    """A hash of which rows the view keeps, by the type's key (and for a latest rule, the key and the ordering value it picked on): the same count of other rows
    gives another hash."""
    latest = content.get('latest')
    columns = list(dict.fromkeys([*type_key, *((latest['key'] + [latest['order']]) if latest else [])]))
    kept = sorted(['' if records[p - 1].get(c) is None else str(records[p - 1].get(c)) for c in columns] for p in positions)
    return hashlib.sha256(json.dumps(kept, ensure_ascii=False).encode('utf-8')).hexdigest()


def _public(summary: dict) -> dict:
    return {k: v for k, v in summary.items() if k not in ('positions', 'signature')}


def seen_of_view(summary: dict) -> dict | None:
    """What a person reads of a view, which confirming has to quote: the dataset version and how many rows it keeps of how many."""
    return None if summary['problems'] else {'dataset_version': summary['version'], 'rows': summary['rows'], 'of': summary['of']}


def describe(content: dict, type_name: str | None = None) -> str:
    """The definition as a sentence: 订单里 状态码 不是 已取消 的行（先取每个 产品编号 里 快照月份 最新的一行）."""
    latest = content.get('latest')
    parts = [f'{f["column"]} {OPS[f["op"]]}「{f["label"]}」' for f in content['filters']]
    first = f'每个「{"」「".join(latest["key"])}」只留「{latest["order"]}」最新的一行' if latest else ''
    return f'{type_name or content["type"]}里' + (f'{first}' if first else '') + (f'{"，再" if first else ""}只留 {"，且 ".join(parts)} 的行' if parts else '')


def view_problems(conn, row: dict) -> list[str]:
    """For a confirmed view, after a dataset moved: what is different now, in words (empty when it keeps the same rows of the same count as when it was confirmed)."""
    content = _content(row)
    summary = view_summary(conn, content)
    if summary['problems']:
        return summary['problems']
    was = json.loads(row['anchors_json'])
    if (summary['rows'], summary['of']) == (was['rows'], was['of']):
        if summary['signature'] == was.get('signature', summary['signature']):
            return []
        return [f'{summary["dataset"]} 第 {summary["version"]} 版之后，视图留下的还是 {summary["rows"]} / {summary["of"]} 行，但已经不是确认时的那些行']
    return [f'{summary["dataset"]} 第 {summary["version"]} 版之后，视图留下的行变了：确认时 {was["rows"]} / {was["of"]} 行，现在 {summary["rows"]} / {summary["of"]} 行']


# --- the definition a person writes -------------------------------------------------------------------------------------------------------------------

def check_definition(conn, payload: dict, user: dict | None, name: str | None = None) -> dict:
    """The content of a view as a person wrote it: a name, the type (which this person may see), conditions on its code columns using meanings that are
    written, and/or a latest rule on columns of its dataset that can be put in order. TypeRefused says what is wrong."""
    name = _text(payload.get('name') if name is None else name, '视图的名字', MAX_NAME)
    description = _text(payload.get('description') or '', '说明', MAX_DESCRIPTION, required=False)
    type_row = _type_row(conn, payload.get('type'), user)
    type_content = _content(type_row)
    dataset = current_dataset(conn, type_content['dataset'])
    if dataset is None:
        raise TypeRefused(f'数据集“{type_content["dataset"]}”已经不在了', 409)
    cols = dataset_columns(conn, dataset['id'])
    posted = payload.get('filters') or []
    if not isinstance(posted, list) or len(posted) > MAX_FILTERS or not all(isinstance(f, dict) for f in posted):
        raise TypeRefused(f'条件要写成列表，最多 {MAX_FILTERS} 个')
    codes = {p['column'] for p in type_content['properties'] if p['enum']}
    filters = []
    for f in posted:
        column, op, label = f.get('column'), f.get('op'), f.get('label')
        if column not in codes:
            raise TypeRefused(f'“{column}”不是“{type_content["name"]}”的代码列，没有含义可以拿来筛')
        if op not in OPS:
            raise TypeRefused('条件只能是“是”或“不是”')
        known = sorted(set(meaning_labels(conn, type_content['english_name'], column).values()))
        if label not in known:
            raise TypeRefused(f'“{label}”不是“{column}”已写的含义' + (f'：{"、".join(known)}' if known else '，先给这一列写含义'))
        filters.append({'column': column, 'op': op, 'label': label})
    latest = payload.get('latest')
    if latest is not None:
        keys, order = latest.get('key') if isinstance(latest, dict) else None, latest.get('order') if isinstance(latest, dict) else None
        if not isinstance(keys, list) or not keys or len(set(map(str, keys))) != len(keys) or not all(isinstance(k, str) and k in cols for k in keys):
            raise TypeRefused(f'“每个…只留最新”的编号要选“{type_content["dataset"]}”里的一列或几列，不重复')
        if order not in cols or order in keys:
            raise TypeRefused('比先后的列要选数据集里的一列，不能是编号列')
        if not orderable(cols[order]['type']):
            raise TypeRefused(f'“{order}”里的内容排不出先后（数字、年月、日期才可以）')
        latest = {'key': list(keys), 'order': order}
    if not filters and latest is None:
        raise TypeRefused('视图要写至少一个条件，或者“每个编号只留最新的一行”')
    return {'name': name, 'description': description, 'type': type_content['english_name'], 'filters': filters, 'latest': latest}


def check_names_free(conn, content: dict) -> None:
    """The name is the id, so it is unique case-insensitively among views, and it is not the name of an object type (a question names one or the other)."""
    mine = view_id(content['name'])
    for element_id, in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objview:%'"):
        if element_id != mine and element_id.casefold() == mine.casefold():
            raise TypeRefused(f'已经有叫“{element_id[len(VIEW_PREFIX):]}”的视图（名字不分大小写）', 409)
    for element_id, other in conn.execute("SELECT element_id, content_json FROM element_state WHERE element_id LIKE 'objtype:%'"):
        names = {json.loads(other)['name'].casefold(), element_id[len(TYPE_PREFIX):].casefold()}
        if content['name'].casefold() in names:
            raise TypeRefused(f'已经有叫“{content["name"]}”的对象类型，视图换一个名字', 409)


def reset_reasons(old: dict, new: dict) -> list[str]:
    """What changed that a confirmation was about: the type, the conditions, the latest rule. The description is not on the list."""
    return [label for key, label in (('type', '对象类型'), ('filters', '条件'), ('latest', '“只留最新”的规则')) if old[key] != new[key]]


def _evidence(summary: dict) -> str:
    return f'dataset:{summary["dataset"]}@v{summary["version"]}'


def _reads(content: dict, summary: dict) -> list[str]:
    return [type_id(content['type']), f'dataset:{summary["dataset"]}', *(enum_id(content['type'], c) for c in dict.fromkeys(f['column'] for f in content['filters']))]


def _anchors(summary: dict) -> dict:
    return {'dataset': summary['dataset'], 'version': summary['version'], 'rows': summary['rows'], 'of': summary['of'], 'signature': summary['signature']}


def _change(content: dict, summary: dict, who: str | None) -> tuple:
    return (view_id(content['name']), 'checked', _evidence(summary), who, content, _anchors(summary), who)


def create_view(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """Put a view forward (state checked, the person its proposer): how many rows it keeps is counted on the full current data. Returns {'id', 'rows', 'of'}."""
    content = check_definition(conn, payload, user)
    if element_row(conn, view_id(content['name'])):
        raise TypeRefused(f'已经有叫“{content["name"]}”的视图', 409)
    check_names_free(conn, content)
    summary = view_summary(conn, content)
    if summary['problems']:
        raise TypeRefused('；'.join(summary['problems']), 409)
    write_elements(conn, [_change(content, summary, who)], {view_id(content['name']): _reads(content, summary)})
    return {'id': content['name'], 'rows': summary['rows'], 'of': summary['of']}


def update_view(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{id, version, ...the fields of create}: a change to the type, conditions or latest rule puts it forward again as this person's (a confirmed one that
    changes stops being confirmed); so does saving one that was sent back; the description keeps the state. 409 when the version has moved."""
    row = _view_row(conn, payload.get('id'), user)
    if payload.get('version') != row['version']:
        raise TypeRefused('这个视图在你打开之后被改了，请刷新后再改', 409)
    old = _content(row)
    content = check_definition(conn, payload, user, old['name'])
    reset = reset_reasons(old, content)
    if reset or row['state'] in ('proposed', 'rejected'):
        summary = view_summary(conn, content)
        if summary['problems']:
            raise TypeRefused('；'.join(summary['problems']), 409)
        write_elements(conn, [_change(content, summary, who)], {row['element_id']: _reads(content, summary)}, {row['element_id']: row['version']})
    elif old['description'] != content['description']:
        _edit_names(conn, row, content, who)
    return {'id': old['name'], 'state': element_row(conn, row['element_id'])['state'], 'reset': reset}


def confirm_view(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{id, version, seen}: confirm what the person looked at. `seen` is {dataset_version, rows, of} of the detail they read; the count is made again on the
    data as it is and the confirmation is refused (409) when it is not that. The type and the meanings the conditions use must be confirmed. Another
    builder (SelfConfirmation otherwise)."""
    row = _view_row(conn, payload.get('id'), user)
    if payload.get('version') != row['version']:
        raise TypeRefused('确认要带上你看到的那一版；它在你看过之后被改了，请刷新后重新看一遍', 409)
    if row['state'] == 'confirmed':
        raise TypeRefused('已经确认过了', 409)
    if row['state'] == 'rejected':
        raise TypeRefused('已经被退回了：要先按退回的理由改，再重新提出', 409)
    if not isinstance(payload.get('seen'), dict):
        raise TypeRefused('确认要带上你看到的数据版本和行数（seen）')
    content = _content(row)
    waiting = waiting_on(conn, content)
    if waiting:
        raise TypeRefused(f'视图用到的{"、".join(f"“{w["name"]}”" for w in waiting)}还没有确认，要先确认它们', 409)
    summary = view_summary(conn, content)
    if summary['problems']:
        raise TypeRefused(f'按现在的数据过不了检查，不能确认：{"；".join(summary["problems"])}', 409)
    if payload['seen'] != seen_of_view(summary):
        raise TypeRefused(f'数据在你看过之后变了：{summary["dataset"]} 现在是第 {summary["version"]} 版，视图留下 {summary["rows"]} / {summary["of"]} 行，和你看到的不一样，请刷新后重新看一遍', 409)
    write_confirmation(conn, row['element_id'], content, _evidence(summary), who, _anchors(summary), {summary['dataset']: summary['version']}, row['version'], _reads(content, summary))
    return {'state': 'confirmed'}


# --- what the pages read ------------------------------------------------------------------------------------------------------------------------------

def _view_row(conn, name, user: dict | None) -> dict:
    row = element_row(conn, view_id(str(name)))
    if row is None or not view_visible(conn, row, user):
        raise TypeRefused('没有这个视图', 404)
    return row


def view_visible(conn, row: dict, user: dict | None) -> bool:
    """A view is seen by those who may see its type; a viewer also needs it confirmed (and so the type)."""
    if user is not None and user['role'] == 'viewer' and row['state'] != 'confirmed':
        return False
    type_row = element_row(conn, type_id(_content(row)['type']))
    return type_row is not None and _visible(conn, type_row, user)


def waiting_on(conn, content: dict) -> list[dict]:
    """What a view stands on that is not confirmed: its type, and the meanings its conditions use, as [{'id', 'name', 'state'}]."""
    out = []
    type_row = element_row(conn, type_id(content['type']))
    if type_row and type_row['state'] != 'confirmed':
        out.append({'id': content['type'], 'name': _content(type_row)['name'], 'state': type_row['state']})
    for column in dict.fromkeys(f['column'] for f in content['filters']):
        meaning = element_row(conn, enum_id(content['type'], column))
        if meaning is None or meaning['state'] != 'confirmed':
            out.append({'id': f'{content["type"]}:{column}', 'name': f'{_content(type_row)["name"] if type_row else content["type"]}.{column}', 'state': meaning['state'] if meaning else None})
    return out


def view_state(conn, row: dict, user: dict | None) -> dict:
    """_state_view, and that a view whose type or meanings are not confirmed cannot be confirmed yet."""
    state = _state_view(conn, row, user)
    waiting = waiting_on(conn, _content(row))
    return {**state, 'can_confirm': state['can_confirm'] and not waiting, 'waiting_on': waiting}


def _line(conn, row: dict, user: dict | None, summary: dict, type_name: str) -> dict:
    content = _content(row)
    anchors = json.loads(row['anchors_json']) if row['anchors_json'] else None
    return {'id': content['name'], 'name': content['name'], 'description': content['description'], 'type': content['type'], 'type_name': type_name,
            'filters': content['filters'], 'latest': content['latest'], 'says': describe(content, type_name), 'problems': summary['problems'],
            'rows': summary.get('rows'), 'of': summary.get('of'), 'dataset': summary.get('dataset'), 'dataset_version': summary.get('version'),
            'seen': seen_of_view(summary), 'anchored': anchors, **view_state(conn, row, user)}


def list_views(conn, english_name: str, user: dict | None) -> list[dict]:
    """The views of one type this person may see, with how many rows each keeps on the data as it is now."""
    type_row = _type_row(conn, english_name, user)
    type_name = _content(type_row)['name']
    out = []
    for element_id, in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objview:%' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        if _content(row)['type'] == english_name and view_visible(conn, row, user):
            summary = view_summary(conn, _content(row))
            line = _line(conn, row, user, _public(summary), type_name)
            limit = restriction(conn, type_row['element_id'], user)
            if limit is not None and not summary['problems']:   # a row rule limits the type: the counts are of the rows this person may read
                readable = row_positions(dataset_records(conn, current_dataset(conn, summary['dataset'])), limit)
                line['rows'], line['of'] = len(readable & set(summary['positions'])), len(readable)
            out.append(line)
    return out


def view_form(conn, english_name: str, user: dict | None) -> dict:
    """What the form for a new view offers on this type: the code columns with the meanings written for them, and the columns of its dataset with whether
    they can be put in order."""
    type_row = _type_row(conn, english_name, user)
    content = _content(type_row)
    dataset = current_dataset(conn, content['dataset'])
    cols = dataset_columns(conn, dataset['id']) if dataset else {}
    return {'codes': [{'column': p['column'], 'name': p['name'], 'labels': sorted(set(meaning_labels(conn, english_name, p['column']).values()))} for p in content['properties'] if p['enum']],
            'columns': [{'name': n, 'orderable': orderable(c['type'])} for n, c in cols.items()]}


def view_log(conn, name: str, user: dict | None) -> list[dict]:
    return log_entries(conn, [_view_row(conn, name, user)['element_id']])
