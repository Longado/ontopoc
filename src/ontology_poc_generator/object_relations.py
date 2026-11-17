"""Relations between object types, kept on the workspace like the types themselves: a relation is one element (relation:<English name>) with a person's
definition, a state, a confirmation snapshot and what it reads (element_dep: both endpoint types and both datasets).

A relation is A -> B with a cardinality and one key pair: a column of A's dataset and a column of B's dataset that hold the same value. Saving it
runs the check on the full current data of both datasets: how many rows of the many side find the one side (157 of 160), the keys that miss with
samples, and the fan-out (a key that repeats on the one side, so a join makes several rows of one: KH012 twice). Saving is allowed whatever they show: they
are the evidence a person comes to read. Confirming is not: it stops when either endpoint type is not confirmed, the person is the proposer (two-person
confirmation), the version is not the one they saw, the numbers are not the ones they saw (the data moved after they looked), a column is gone, or the
declared cardinality is false on today's data (rows a join would multiply; for one-to-one a repeat on the many side). A one-side column that is not the
type's key is a warning only. A viewer reads the counts of a check and none of the rows or keys behind them.

A relation goes to needs_look when either endpoint does (object_types._flag follows element_dep) and when a new upload changes the connected rows
(recheck_dependents calls relation_problems). Saving a relation with a different key, endpoint or cardinality puts it forward again; names and the
description are edits only. Many-to-many is not offered: it needs a table that joins the two, which a key pair cannot say.
"""
from __future__ import annotations

from ontology_poc_generator.lang import TrMap, tr
import json
import re

from ontology_poc_generator.object_types import (
    RELATION_PREFIX, TYPE_PREFIX, TypeRefused, _content, _edit_names, _flag_readers, _state_view, _text, _visible, dataset_columns, element_row, log_entries, refuse_if_limited, type_id,
    write_confirmation, write_elements, MAX_DESCRIPTION, MAX_NAME, ENGLISH_NAME, kept_columns)
from ontology_poc_generator.relation_checks import _side_numbers
from ontology_poc_generator.row_rules import positions, restriction
from ontology_poc_generator.type_access import hidden_columns, reads_hidden
from ontology_poc_generator.workspace_store import SAMPLE_LIMIT, _quote, current_dataset, dataset_records, record_result

CARDINALITY = TrMap({'many_to_one': ('多对一', 'many to one'), 'one_to_many': ('一对多', 'one to many'), 'one_to_one': ('一对一', 'one to one')})
ROW_SAMPLE = 10   # rows shown for the keys that miss and for the keys that repeat
SHOWN_COLUMNS = 6


def relation_id(english_name: str) -> str:
    return f'{RELATION_PREFIX}{english_name}'


def _filled(alias: str, column: str) -> str:
    return f"({alias}.{_quote(column)} IS NOT NULL AND {alias}.{_quote(column)} <> '')"


def _rows(conn, sql: str) -> list[list]:
    return [list(r) for r in conn.execute(sql)]


def check_relation(conn, content: dict, record: bool = True, user: dict | None = None, examples: bool = True) -> dict:
    """The check of a definition on the current data: {'problems': [...]} when it cannot be run (a type, dataset or column is gone), else the numbers
    (see the top of the file) and `signature`, the six counts a person confirms against. With record the two checks are kept as check_result rows. With `user`
    (and no record), an end that a row rule limits for them is read through a temporary copy of the rows they may see, so the counts and rows are theirs. With
    examples=False the rows that miss and the rows that repeat are not fetched (the graphs draw counts only)."""
    if user is None or record:
        return _check_relation(conn, content, record, {}, examples)
    copies, made = {}, []
    try:
        for end in ('from', 'to'):
            type_row = element_row(conn, type_id(content[end]))
            limit = restriction(conn, type_row['element_id'], user) if type_row else None
            dataset = current_dataset(conn, _content(type_row)['dataset']) if limit is not None else None
            if dataset is not None:
                keep = sorted(positions(dataset_records(conn, dataset), limit))
                name = f'rr_{end}'
                conn.execute(f'DROP TABLE IF EXISTS temp.{name}')
                conn.execute(f'CREATE TEMP TABLE {name} AS SELECT * FROM {_quote(dataset["table_name"])} WHERE rowid IN ({",".join(map(str, keep)) or "NULL"}) ORDER BY rowid')
                made.append(name)
                copies[end] = {**dataset, 'table_name': name, 'rows_stored': len(keep)}
        hide = {end: hidden_columns(conn, type_id(content[end]), user) for end in ('from', 'to')}   # the rows that repeat show no column kept from them
        return _check_relation(conn, content, record, copies, examples, hide)
    finally:
        for name in made:
            conn.execute(f'DROP TABLE IF EXISTS temp.{name}')


def _check_relation(conn, content: dict, record: bool, copies: dict, examples: bool = True, hide: dict | None = None) -> dict:
    ends = {end: element_row(conn, type_id(content[end])) for end in ('from', 'to')}
    problems = [tr(f'对象类型“{content[end]}”已经不在了', f'The object type "{content[end]}" is gone') for end, row in ends.items() if row is None]
    if problems:
        return {'problems': problems}
    types = {end: _content(row) for end, row in ends.items()}
    datasets = {end: current_dataset(conn, types[end]['dataset']) for end in ends}
    problems = [tr(f'数据集“{types[end]["dataset"]}”已经不在了', f'The dataset "{types[end]["dataset"]}" is gone') for end, d in datasets.items() if d is None]
    columns = {end: dataset_columns(conn, datasets[end]['id']) for end in ends if datasets[end]}
    problems += [tr(f'{datasets[end]["name"]} 第 {datasets[end]["version"]} 版里没有“{content[f"{end}_column"]}”这一列', f'{datasets[end]["name"]} version {datasets[end]["version"]} has no column "{content[f"{end}_column"]}"') for end in columns if content[f'{end}_column'] not in columns[end]]
    if problems:
        return {'problems': problems}
    datasets = {end: copies.get(end, d) for end, d in datasets.items()}   # the rows a row rule leaves this person, when it limits an end
    many_end, one_end = ('from', 'to') if content['cardinality'] in ('many_to_one', 'one_to_one') else ('to', 'from')
    m, o = types[many_end], types[one_end]
    m_ds, o_ds = datasets[many_end], datasets[one_end]
    m_col, o_col = content[f'{many_end}_column'], content[f'{one_end}_column']
    shown = list(dict.fromkeys([*m['key'], m_col]))
    repeated_shown = list(dict.fromkeys([o_col, *[p['column'] for p in o['properties'] if p['column'] not in (hide or {}).get(one_end, set())]]))[:SHOWN_COLUMNS]
    gone = [tr(f'{ds["name"]} 第 {ds["version"]} 版里没有“{c}”这一列', f'{ds["name"]} version {ds["version"]} has no column "{c}"') for ds, wanted, end in ((m_ds, shown, many_end), (o_ds, repeated_shown, one_end))
            for c in wanted if c not in columns[end]]   # a column in double quotes that is not there would be read by SQLite as its own name, as a value
    if gone:
        return {'problems': gone}
    m_table, o_table = _quote(m_ds['table_name']), _quote(o_ds['table_name'])
    found = _side_numbers(conn, m_table, o_table, [m_col], [o_col], m_ds['rows_stored'])
    unmatched_rows = _rows(conn, f'SELECT {", ".join(f"t.{_quote(c)}" for c in shown)} FROM {m_table} t WHERE {_filled("t", m_col)} AND NOT EXISTS '
                                 f'(SELECT 1 FROM {o_table} o WHERE o.{_quote(o_col)} = t.{_quote(m_col)}) ORDER BY t.rowid LIMIT {ROW_SAMPLE}') if examples else []
    repeated_rows = _rows(conn, f'SELECT {", ".join(_quote(c) for c in repeated_shown)} FROM {o_table} WHERE {_quote(o_col)} IN '
                                f'(SELECT {_quote(o_col)} FROM {o_table} WHERE {_filled(o_table, o_col)} GROUP BY {_quote(o_col)} HAVING COUNT(*) > 1) '
                                f'ORDER BY {_quote(o_col)}, rowid LIMIT {ROW_SAMPLE}') if examples else []
    many_repeats = conn.execute(f'SELECT COUNT(*) FROM (SELECT 1 FROM {m_table} t WHERE {_filled("t", m_col)} GROUP BY t.{_quote(m_col)} HAVING COUNT(*) > 1)').fetchone()[0] \
        if content['cardinality'] == 'one_to_one' else 0   # one to one: the many side may not repeat a key either
    rows, empty, unmatched = m_ds['rows_stored'], found['empty'], found['unmatched']
    numbers = {'rows': rows, 'matched': rows - empty - unmatched, 'unmatched': unmatched, 'fan_keys': found['fan_keys'], 'extra_rows': found['extra_rows'], 'many_repeats': many_repeats}
    warnings = [] if {o_col} == set(o['key']) else [   # unique today is not unique for good unless the column is what the one side is keyed on
        tr(f'“{o["name"]}”的主键是{" + ".join(f"“{k}”" for k in o["key"])}，这里连的是“{o_col}”：它现在{"有重复" if found["fan_keys"] else "没有重复"}，但没有什么保证它以后一直不重复', f'The key of "{o["name"]}" is {" + ".join(o["key"])}, but this connects on "{o_col}": it has {"repeats" if found["fan_keys"] else "no repeats"} now, but nothing guarantees it stays free of repeats')]
    ids = []
    if record:
        element = relation_id(content['english_name'])
        ids = [record_result(conn, element, m_ds['id'], 'relation_match', found['missing_sql'], rows, unmatched, empty,
                             {'distinct_keys': found['unmatched_keys'], 'keys': found['samples'], 'if_trimmed': found['near']}, 'failed' if unmatched else 'passed'),
               record_result(conn, element, o_ds['id'], 'relation_fanout', found['repeated_sql'], o_ds['rows_stored'], found['fan_keys'], 0,
                             {'source_rows': found['source_rows'], 'extra_rows': found['extra_rows'], 'keys': found['fan_samples']}, 'failed' if found['fan_keys'] else 'passed')]
    return {'problems': [], 'numbers': numbers, 'signature': list(numbers.values()), 'warnings': warnings, 'check_ids': ids, 'cardinality': content['cardinality'],
            'many': {'type': m['english_name'], 'name': m['name'], 'dataset': m_ds['name'], 'version': m_ds['version'], 'column': m_col},
            'one': {'type': o['english_name'], 'name': o['name'], 'dataset': o_ds['name'], 'version': o_ds['version'], 'column': o_col},
            'empty': empty, 'samples': found['samples'], 'unmatched_keys': found['unmatched_keys'], 'if_trimmed': found['near'],
            'unmatched_rows': {'columns': shown, 'rows': unmatched_rows},
            'fanout': {'keys': found['fan_keys'], 'source_rows': found['source_rows'], 'extra_rows': found['extra_rows'], 'samples': found['fan_samples'],
                       'rows': {'columns': repeated_shown, 'rows': repeated_rows}},
            'datasets': {m_ds['name']: m_ds['version'], o_ds['name']: o_ds['version']}}


def evidence_lines(result: dict) -> list[dict]:
    """What a person reads before confirming, as sentences: [{'ok', 'text'}]."""
    if result['problems']:
        return [{'ok': False, 'text': p} for p in result['problems']]
    n, many, one = result['numbers'], result['many'], result['one']
    lines = [{'ok': n['unmatched'] == 0 and n['matched'] == n['rows'], 'text': tr(f'{many["dataset"]} 第 {many["version"]} 版的 {n["rows"]} 行里，{n["matched"]} 行用“{many["column"]}”连上了 {one["dataset"]} 的“{one["column"]}”', f'Of the {n["rows"]} rows in {many["dataset"]} version {many["version"]}, {n["matched"]} connected through "{many["column"]}" to "{one["column"]}" in {one["dataset"]}')}]
    if n['unmatched']:
        keys = tr('、', ', ').join(s['key'] for s in result['samples'])
        etc = tr(f' 等 {result["unmatched_keys"]} 个编号', f' and {result["unmatched_keys"] - len(result["samples"])} more keys') if result['unmatched_keys'] > len(result['samples']) else ''
        lines.append({'ok': False, 'strong': True,   # the rows that belong to nobody are what a person confirming this has to see first: they are in no statistic through the relation
                      'text': tr(f'{n["unmatched"]} 行{many["name"]}找不到{one["name"]}', f'{n["unmatched"]} {many["name"]} rows have no {one["name"]}') + (tr(f'：{keys}{etc}', f': {keys}{etc}') if keys else '')
                              + (tr(f'；其中 {result["if_trimmed"]} 行去掉空格、忽略大小写后能对上', f'; {result["if_trimmed"]} of them would match once spaces and letter case are ignored') if result['if_trimmed'] else '')})
    if result['empty']:
        lines.append({'ok': False, 'text': tr(f'{result["empty"]} 行的“{many["column"]}”是空的，没有连任何{one["name"]}', f'{result["empty"]} rows have an empty "{many["column"]}" and connect to no {one["name"]}')})
    f = result['fanout']
    lines += [{'ok': False, 'text': text} for text in (_fanout_line(result), _repeat_line(result)) if text]
    if not f['keys'] and not n['many_repeats']:
        lines.append({'ok': True, 'text': tr(f'{one["dataset"]} 里“{one["column"]}”没有重复，一个{many["name"]}只会连上一个{one["name"]}', f'"{one["column"]}" in {one["dataset"]} has no repeats, so one {many["name"]} connects to only one {one["name"]}')})
    lines += [{'ok': False, 'text': tr(f'提醒：{w}', f'Note: {w}')} for w in result.get('warnings', [])]
    return lines


def _fanout_line(result: dict) -> str | None:
    """The keys that repeat on the one side, in words; None when none does."""
    f, one = result['fanout'], result['one']
    if not f['keys']:
        return None
    keys = tr('、', ', ').join(tr(f'{s["key"]}（{s["rows"]} 次）', f'{s["key"]} ({s["rows"]} times)') for s in f['samples'])
    head = tr(f'{one["dataset"]} 里“{one["column"]}”有 {f["keys"]} 个值重复{f"：{keys}" if keys else ""}', f'"{one["column"]}" in {one["dataset"]} has {f["keys"]} repeated value{"" if f["keys"] == 1 else "s"}{f": {keys}" if keys else ""}')
    if not f['extra_rows']:
        return tr(f'{head}；现在没有行连上它们，但以后连上就会多出行，按{one["name"]}汇总会重复算', f'{head}; no rows connect to them now, but any that do later will add rows, and totals by {one["name"]} will count twice')
    return tr(f'{head}；连上它们的 {f["source_rows"]} 行会多出 {f["extra_rows"]} 行，按{one["name"]}汇总会重复算', f'{head}; the {f["source_rows"]} rows that connect to them gain {f["extra_rows"]} extra rows, and totals by {one["name"]} will count twice')


def _repeat_line(result: dict) -> str | None:
    """For one-to-one: the values of the many side that appear more than once; None when none does."""
    n, many = result['numbers'], result['many']
    return tr(f'一对一不成立：{many["dataset"]} 里“{many["column"]}”有 {n["many_repeats"]} 个值出现了不止一次', f'One to one does not hold: "{many["column"]}" in {many["dataset"]} has {n["many_repeats"]} values that appear more than once') if n['many_repeats'] else None


def cardinality_false(result: dict) -> list[str]:
    """What makes the declared cardinality untrue on today's data, in words: rows that a join would multiply (extra_rows on the one side), or for one-to-one a
    value that repeats on the many side. Keys that repeat with no row connected to them are a warning in the lines, not this."""
    return [text for text in (_fanout_line(result) if result['numbers']['extra_rows'] else None, _repeat_line(result)) if text]


def counts_only(result: dict) -> dict:
    """The check as a viewer reads it: the counts, and none of the rows or keys behind them (no unmatched rows, fan-out rows or samples)."""
    if result['problems']:
        return result
    nothing = {'columns': [], 'rows': []}
    return {**result, 'samples': [], 'unmatched_rows': nothing, 'fanout': {**result['fanout'], 'samples': [], 'rows': nothing}, 'counts_only': True}


def _describe(numbers: dict, many: str, one: str) -> str:
    return tr(f'{numbers["matched"]} / {numbers["rows"]} 行连上{one}，{numbers["fan_keys"]} 个重复的{one}键', f'{numbers["matched"]} / {numbers["rows"]} rows connect to {one}, {numbers["fan_keys"]} repeated {one} keys')


def relation_problems(conn, row: dict) -> list[str]:
    """For a confirmed relation, after a dataset moved: what is different now, in words (empty when the connected rows are the same as when it was confirmed)."""
    content = _content(row)
    result = check_relation(conn, content)
    if result['problems']:
        return result['problems']
    was = json.loads(row['anchors_json'])
    if result['numbers'] == was['numbers']:   # by name: the anchors are stored with their keys sorted, the signature is in the order the page reads it
        return []
    many, one = result['many'], result['one']
    moved = tr('、', ', ').join(tr(f'{name} 第 {v} 版', f'{name} version {v}') for name, v in result['datasets'].items() if was['datasets'].get(name) != v)
    return [tr(f'{moved}之后，连接的行变了：确认时 {_describe(was["numbers"], many["name"], one["name"])}，现在 {_describe(result["numbers"], many["name"], one["name"])}', f'After {moved}, the connected rows changed: when confirmed, {_describe(was["numbers"], many["name"], one["name"])}; now, {_describe(result["numbers"], many["name"], one["name"])}')]


# --- the definition a person writes -------------------------------------------------------------------------------------------------------------

def check_definition(conn, payload: dict, user: dict | None, english_name: str | None = None) -> dict:
    """The content of a relation as a person wrote it: names, the two types (which this person may see), a cardinality that is offered, and a column of
    each type's dataset. TypeRefused says what is wrong."""
    english = payload.get('english_name') if english_name is None else english_name
    if not isinstance(english, str) or not ENGLISH_NAME.fullmatch(english):
        raise TypeRefused(tr('英文名只能用字母、数字和下划线，字母开头，最多 40 个字符', 'The English name may use only letters, digits and underscores, must start with a letter, and is at most 40 characters'))
    if english.casefold() == 'new':
        raise TypeRefused(tr('英文名不能叫 new：页面的“新建”用了这个地址', 'The English name cannot be "new": the New page uses that address'))
    name = _text(payload.get('name'), tr('名称', 'The name'), MAX_NAME)
    description = _text(payload.get('description') or '', tr('说明', 'The description'), MAX_DESCRIPTION, required=False)
    for end in ('from', 'to'):
        row = element_row(conn, type_id(str(payload.get(end))))
        if row is None or not _visible(conn, row, user):
            raise TypeRefused(tr(f'没有“{payload.get(end)}”这个对象类型', f'There is no object type "{payload.get(end)}"'), 404)
        if hidden_columns(conn, row['element_id'], user):
            raise TypeRefused(kept_columns(), 403)
    if payload.get('cardinality') == 'many_to_many':
        raise TypeRefused(tr('多对多要靠一张把两边连起来的表，一对列写不出来，这一版还不能建', 'Many to many needs a table that joins the two sides, which a pair of columns cannot express, so it cannot be created yet'))
    if payload.get('cardinality') not in CARDINALITY:
        raise TypeRefused(tr('基数要选多对一、一对多或一对一', 'Pick many to one, one to many or one to one for the cardinality'))
    for end in ('from', 'to'):
        if not isinstance(payload.get(f'{end}_column'), str) or not payload[f'{end}_column']:
            raise TypeRefused(tr('两边各要选一列', 'Pick one column on each side'))
    content = {'name': name, 'english_name': english, 'description': description, 'from': payload['from'], 'to': payload['to'], 'cardinality': payload['cardinality'],
               'from_column': payload['from_column'], 'to_column': payload['to_column']}
    problems = check_relation(conn, content, record=False)['problems']
    if problems:
        raise TypeRefused(tr('；', '; ').join(problems), 409)
    return content


def preview_relation(conn, payload: dict, user: dict | None) -> dict:
    """How many rows would connect for a relation not yet saved: the same check a save runs, on the rows this person may read, kept nowhere. Names are not needed.
    TypeRefused says what is wrong (a type that is not theirs, a column that is not there)."""
    content = check_definition(conn, {**payload, 'english_name': 'preview', 'name': tr('预览', 'Preview')}, user)
    result = check_relation(conn, content, record=False, user=user)
    n = result['numbers']
    return {'rows': n['rows'], 'matched': n['matched'], 'unmatched': n['unmatched'], 'empty': result['empty'], 'samples': result['samples'],
            'many_name': result['many']['name'], 'one_name': result['one']['name'], 'fan_keys': result['fanout']['keys'], 'cardinality_holds': not cardinality_false(result)}


def check_names_free(conn, content: dict) -> None:
    mine = relation_id(content['english_name'])
    for element_id, other in conn.execute("SELECT element_id, content_json FROM element_state WHERE element_id LIKE 'relation:%'"):
        if element_id == mine:
            continue
        if element_id.casefold() == mine.casefold():
            raise TypeRefused(tr(f'英文名“{content["english_name"]}”和已有的“{element_id[len(RELATION_PREFIX):]}”只差大小写', f'The English name "{content["english_name"]}" differs from the existing "{element_id[len(RELATION_PREFIX):]}" only in case'), 409)
        if json.loads(other)['name'].casefold() == content['name'].casefold():
            raise TypeRefused(tr(f'已经有叫“{content["name"]}”的关系', f'There is already a relation named "{content["name"]}"'), 409)


def reset_reasons(old: dict, new: dict) -> list[str]:
    """What changed that a confirmation was about: the two types, the cardinality, the key columns. Names and the description are not on the list."""
    names = {'from': tr('起点类型', 'the start type'), 'to': tr('终点类型', 'the end type'), 'cardinality': tr('基数', 'the cardinality'), 'from_column': tr('起点的列', 'the start column'), 'to_column': tr('终点的列', 'the end column')}
    return [label for key, label in names.items() if old[key] != new[key]]


def _evidence(result: dict) -> str:
    return ','.join([*(f'check_result:{i}' for i in result['check_ids']), *(f'dataset:{n}@v{v}' for n, v in result['datasets'].items())])


def _reads(content: dict, result: dict) -> list[str]:
    return [type_id(content['from']), type_id(content['to']), *(f'dataset:{n}' for n in result['datasets'])]


def _change(content: dict, result: dict, who: str | None) -> tuple:
    anchors = {'numbers': result['numbers'], 'datasets': result['datasets']}
    return (relation_id(content['english_name']), 'checked', _evidence(result), who, content, anchors, who)


def create_relation(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """Put a relation forward (state checked, the person its proposer): the check runs on the full data now. Returns {'id', 'numbers'}."""
    content = check_definition(conn, payload, user)
    if element_row(conn, relation_id(content['english_name'])):
        raise TypeRefused(tr(f'已经有英文名“{content["english_name"]}”的关系', f'There is already a relation with the English name "{content["english_name"]}"'), 409)
    check_names_free(conn, content)
    result = check_relation(conn, content)
    write_elements(conn, [_change(content, result, who)], {relation_id(content['english_name']): _reads(content, result)})
    return {'id': content['english_name'], 'numbers': result['numbers'], 'warnings': result['warnings']}


def update_relation(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{id, version, ...the fields of create}: a change to the endpoints, cardinality or columns puts it forward again as this person's (and what reads it
    moves to needs_look); so does saving a draft that was sent back; names and the description keep the state. 409 when the version has moved."""
    row = element_row(conn, relation_id(str(payload.get('id'))))
    if row is None or not _relation_visible(conn, row, user):
        raise TypeRefused(tr('没有这个关系', 'There is no such relation'), 404)
    if payload.get('version') != row['version']:
        raise TypeRefused(tr('这个关系在你打开之后被改了，请刷新后再改', 'This relation was changed after you opened it. Refresh and edit again'), 409)
    old = _content(row)
    content = check_definition(conn, payload, user, old['english_name'])
    check_names_free(conn, content)
    reset = reset_reasons(old, content)
    if reset or row['state'] in ('proposed', 'rejected'):
        result = check_relation(conn, content)
        after = (lambda c: _flag_readers(c, row['element_id'], tr(f'它用的“{old["name"]}”关系改了{tr("、", ", ").join(reset)}，要重新确认', f'The relation "{old["name"]}" it uses changed ({", ".join(reset)}) and needs confirming again'), [])) if reset and row['state'] == 'confirmed' else None
        write_elements(conn, [_change(content, result, who)], {row['element_id']: _reads(content, result)}, {row['element_id']: row['version']}, after)
        warnings = result['warnings']
    else:
        warnings = []
        if (old['name'], old['description']) != (content['name'], content['description']):
            _edit_names(conn, row, content, who)
    return {'id': old['english_name'], 'state': element_row(conn, row['element_id'])['state'], 'reset': reset, 'warnings': warnings}


def confirm_relation(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{id, version, seen}: confirm what the person looked at. `seen` is the `signature` of the detail they read (the six counts); the check runs again on the
    data as it is and the confirmation is refused (409) when the counts are not those: the data moved after they looked. Both endpoint types must be confirmed."""
    row = element_row(conn, relation_id(str(payload.get('id'))))
    if row is None or not _relation_visible(conn, row, user):
        raise TypeRefused(tr('没有这个关系', 'There is no such relation'), 404)
    refuse_if_limited(conn, row, user)
    if payload.get('version') != row['version']:
        raise TypeRefused(tr('确认要带上你看到的那一版；它在你看过之后被改了，请刷新后重新看一遍', 'Confirming needs the version you saw; it was changed after you looked, so refresh and look again'), 409)
    if row['state'] == 'confirmed':
        raise TypeRefused(tr('已经确认过了', 'Already confirmed'), 409)
    if row['state'] == 'rejected':
        raise TypeRefused(tr('已经被退回了：要先按退回的理由改，再重新提出', 'It was sent back: change it as the reason says, then put it forward again'), 409)
    if not isinstance(payload.get('seen'), list):
        raise TypeRefused(tr('确认要带上你看到的连接行数（seen）', 'Confirming needs the connected row counts you saw (seen)'))
    content = _content(row)
    unconfirmed = [_content(r)['name'] for r in (element_row(conn, type_id(content[e])) for e in ('from', 'to')) if r['state'] != 'confirmed']
    if unconfirmed:
        raise TypeRefused(tr(f'关系要连接的对象类型都确认之后才能确认：“{"”、“".join(unconfirmed)}”还没有确认', f'A relation can be confirmed only after the object types it connects are confirmed: {", ".join(unconfirmed)} not confirmed yet'), 409)
    result = check_relation(conn, content)
    if result['problems']:
        raise TypeRefused(tr(f'按现在的数据过不了检查，不能确认：{tr("；", "; ").join(result["problems"])}', f'It fails the checks on the current data and cannot be confirmed: {"; ".join(result["problems"])}'), 409)
    if payload['seen'] != result['signature']:
        raise TypeRefused(tr('数据在你看过之后变了，连接的行数和你看到的不一样，请刷新后重新看一遍', 'The data changed after you looked, and the connected row counts are not what you saw. Refresh and look again'), 409)
    false = cardinality_false(result)
    if false:   # saving such a relation is allowed (the evidence is what a person comes to read); standing behind it is not
        raise TypeRefused(tr(f'按现在的数据，{CARDINALITY[content["cardinality"]]}不成立，不能确认：{tr("；", "; ").join(false)}', f'On the current data, {CARDINALITY[content["cardinality"]]} does not hold, so it cannot be confirmed: {"; ".join(false)}'), 409)
    write_confirmation(conn, row['element_id'], content, _evidence(result), who, {'numbers': result['numbers'], 'datasets': result['datasets']}, result['datasets'],
                       row['version'], _reads(content, result))   # what it reads is taken from its two types as they are now
    return {'state': 'confirmed'}


# --- what the pages read ------------------------------------------------------------------------------------------------------------------------

def _relation_visible(conn, row: dict, user: dict | None) -> bool:
    """A relation is seen by those who may see both of its types (a viewer also needs it, and so them, to be confirmed)."""
    content = _content(row)
    if user is not None and user['role'] == 'viewer' and row['state'] != 'confirmed':
        return False
    return all((r := element_row(conn, type_id(content[e]))) is not None and _visible(conn, r, user) for e in ('from', 'to')) \
        and not reads_hidden(conn, row['element_id'], user, content)   # a join column kept from them


def relation_view(conn, row: dict, user: dict | None) -> dict:
    """The state of a relation for a page: _state_view, and that a relation whose endpoint types are not confirmed cannot be confirmed yet."""
    content = _content(row)
    state = _state_view(conn, row, user)
    waiting_on = [{'id': content[e], 'name': _content(r)['name'], 'state': r['state']} for e in ('from', 'to') if (r := element_row(conn, type_id(content[e]))) and r['state'] != 'confirmed']
    return {**state, 'can_confirm': state['can_confirm'] and not waiting_on, 'waiting_on': waiting_on}


def _type_names(conn, content: dict) -> dict:
    return {e: _content(element_row(conn, type_id(content[e])))['name'] for e in ('from', 'to') if element_row(conn, type_id(content[e]))}


def list_relations(conn, user: dict | None) -> list[dict]:
    """Every relation this person may see, by English name, with the connected rows as they are now."""
    out = []
    for element_id, in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'relation:%' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        if not _relation_visible(conn, row, user):
            continue
        content = _content(row)
        result = check_relation(conn, content, record=False, user=user)
        names = _type_names(conn, content)
        out.append({'id': content['english_name'], 'name': content['name'], 'from': content['from'], 'to': content['to'], 'from_name': names.get('from'), 'to_name': names.get('to'),
                    'cardinality': content['cardinality'], 'numbers': result.get('numbers'), 'problems': result['problems'], **relation_view(conn, row, user)})
    return out


def relation_detail(conn, english_name: str, user: dict | None) -> dict:
    row = element_row(conn, relation_id(english_name))
    if row is None or not _relation_visible(conn, row, user):
        raise TypeRefused(tr('没有这个关系', 'There is no such relation'), 404)
    content = _content(row)
    result = check_relation(conn, content, record=False, user=user)
    if user is not None and user['role'] == 'viewer':   # a viewer reads the counts; the rows and keys behind them are data
        result = counts_only(result)
    names = _type_names(conn, content)
    anchors = json.loads(row['anchors_json']) if row['anchors_json'] else None
    return {'id': content['english_name'], 'name': content['name'], 'description': content['description'], 'from': content['from'], 'to': content['to'],
            'from_name': names.get('from'), 'to_name': names.get('to'), 'cardinality': content['cardinality'], 'from_column': content['from_column'], 'to_column': content['to_column'],
            'check': result, 'lines': evidence_lines(result), 'anchored': anchors, **relation_view(conn, row, user)}


def relation_columns(conn, user: dict | None) -> list[dict]:
    """For the form: each type this person may see with the columns of its dataset (and its key), so the key pair can be picked."""
    out = []
    for element_id, in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objtype:%' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        if not _visible(conn, row, user) or hidden_columns(conn, element_id, user):   # a type with a column kept from them: no relation of theirs to define on it
            continue
        content = _content(row)
        dataset = current_dataset(conn, content['dataset'])
        if dataset:
            out.append({'id': content['english_name'], 'name': content['name'], 'dataset': content['dataset'], 'key': content['key'], 'state': row['state'],
                        'columns': [{'name': n, 'type': c['type']} for n, c in dataset_columns(conn, dataset['id']).items()]})
    return out


def relation_log(conn, english_name: str, user: dict | None) -> list[dict]:
    relation_detail_row = element_row(conn, relation_id(english_name))
    if relation_detail_row is None or not _relation_visible(conn, relation_detail_row, user):
        raise TypeRefused(tr('没有这个关系', 'There is no such relation'), 404)
    return log_entries(conn, [relation_id(english_name)])
