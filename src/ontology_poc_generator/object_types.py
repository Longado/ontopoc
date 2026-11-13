"""Object types and the meanings of their codes, kept on the workspace: a type is built from a dataset by name, no run is involved.

Each type is one element (objtype:<English name>) and each enum column of it that someone gave meanings to is another (enum:<English name>:<column>), both
rows of element_state. The states a person sees: proposed (a model wrote it), checked (a person put it forward and the checks ran clean), confirmed (another
person looked at the evidence and said yes), needs_look (it was confirmed, and the data underneath moved). Every confirmation keeps a snapshot of the
definition, its evidence and the dataset versions it was confirmed on (table confirmation). element_dep says what an element reads: a type reads its
dataset and the meanings of its enum columns, a meaning reads its column. When a dataset gets a new current version, recheck_dependents runs the checks behind
each confirmed element that reads it again and moves the ones whose result changed to needs_look, with the reason in words, and so on to what reads them.

Who may confirm: a builder other than the one who put it forward while two-person confirmation is active (accounts.two_person). Everything here raises
TypeRefused with a plain Chinese message and the HTTP status it deserves; SelfConfirmation (from the store) is the one refusal of who.
For a state that is not confirmed, element_state.confirmed_by and confirmed_at mean who wrote it last and when (as everywhere in this file's store); the
person who confirmed, and when, are read from the confirmation snapshots.
"""
from __future__ import annotations

import json
import re

from ontology_poc_generator.accounts import two_person
from ontology_poc_generator.code_meanings import check_enum, merge_enum
from ontology_poc_generator.type_access import can_access
from ontology_poc_generator.workspace_store import check_key, current_dataset, element_state_writes, log_line

TYPE_PREFIX = 'objtype:'
ENUM_PREFIX = 'enum:'
RELATION_PREFIX = 'relation:'
ENGLISH_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,39}')
MAX_NAME, MAX_DESCRIPTION = 40, 200
OBJECT_PAGE = 50
TYPE_NAME = {'integer': '整数', 'decimal': '小数', 'text': '文本', 'date': '日期', 'month': '月份', 'datetime': '日期时间', 'boolean': '是否'}
KEY_REFUSED = ('decimal', 'boolean')   # a real number or a two-valued column is not an identity
KEY_WARNED = ('date', 'datetime', 'month')
FITS = {'integer': ('integer', 'decimal', 'text'), 'decimal': ('decimal', 'text'), 'text': ('text',), 'date': ('date', 'datetime', 'text'),
        'month': ('month', 'text'), 'datetime': ('datetime', 'text'), 'boolean': ('boolean', 'text')}   # what a column of this inferred type may be declared as
CODE_TYPES = ('integer', 'text')   # a code column is one of these, never boolean
WAITING = ('proposed', 'checked')


class TypeRefused(ValueError):
    """A refusal in plain Chinese. status: the HTTP status; detail: what the page needs to show it (the repeated keys)."""

    def __init__(self, message: str, status: int = 400, detail: dict | None = None):
        super().__init__(message)
        self.status, self.detail = status, detail


def type_id(english_name: str) -> str:
    return f'{TYPE_PREFIX}{english_name}'


def enum_id(english_name: str, column: str) -> str:
    return f'{ENUM_PREFIX}{english_name}:{column}'


def element_row(conn, element_id: str) -> dict | None:
    cursor = conn.execute('SELECT * FROM element_state WHERE element_id = ?', (element_id,))
    found = cursor.fetchone()
    return dict(zip([c[0] for c in cursor.description], found)) if found else None


def _content(row: dict) -> dict:
    return json.loads(row['content_json'])


def dataset_columns(conn, dataset_id: int) -> dict[str, dict]:
    return {name: {'type': kind, 'distinct': distinct, 'missing': missing, 'counts': json.loads(counts) if counts else None}
            for name, kind, distinct, missing, counts in conn.execute(
                'SELECT name, inferred_type, distinct_count, missing_count, value_counts_json FROM "column" WHERE dataset_id = ? ORDER BY position', (dataset_id,))}


def _text(value, what: str, limit: int, required: bool = True) -> str:
    text = value.strip() if isinstance(value, str) else ''
    if (required and not text) or len(text) > limit or '\n' in text:
        raise TypeRefused(f'{what}要写 1 到 {limit} 个字，不能换行' if required else f'{what}最多 {limit} 个字，不能换行')
    return text


def _by_value(values) -> list[str]:
    return sorted(values, key=lambda v: (0, int(v), v) if re.fullmatch(r'-?\d{1,18}', v) else (1, 0, v))


def _set_deps(conn, element_id: str, depends_on: list[str]) -> None:
    conn.execute("DELETE FROM element_dep WHERE element_id = ? AND depends_on NOT LIKE 'enum:%'", (element_id,))   # what a type reads of its meanings is added as they are made
    conn.executemany('INSERT OR IGNORE INTO element_dep(element_id, depends_on) VALUES (?, ?)', [(element_id, d) for d in depends_on])


def _add_dep(conn, element_id: str, depends_on: str) -> None:
    conn.execute('INSERT OR IGNORE INTO element_dep(element_id, depends_on) VALUES (?, ?)', (element_id, depends_on))


def write_elements(conn, changes: list[tuple], reads: dict[str, list[str]]) -> None:
    """Keep the changes all together or not at all, with what each one reads."""
    with element_state_writes(conn, changes):
        for element_id, depends_on in reads.items():
            _set_deps(conn, element_id, depends_on)
        for element_id in reads:
            if element_id.startswith(ENUM_PREFIX):
                _add_dep(conn, type_id(element_id[len(ENUM_PREFIX):].partition(':')[0]), element_id)


# --- the definition a person writes -------------------------------------------------------------------------------------------------------------

def _key_failure(conn, result: dict) -> tuple[str, dict]:
    """(what is wrong with this key, in words; the detail a page shows) for a failed key check: the repeated values, up to 20, and how many rows are empty."""
    repeated = [{'key': list(r[:-1]), 'rows': r[-1]} for r in conn.execute(f'{result["query"]} LIMIT 20')]
    count = conn.execute(f'SELECT COUNT(*) FROM ({result["query"]})').fetchone()[0]
    parts = []
    if result['violations']:
        shown = '、'.join(f'{" + ".join(r["key"])}（{r["rows"]} 行）' for r in repeated[:5])
        parts.append(f'{count} 个值重复，多出 {result["violations"]} 行，例如 {shown}')
    if result['null_key_rows']:
        parts.append(f'{result["null_key_rows"]} 行是空的')
    detail = {'key_check': {'status': result['status'], 'rows_checked': result['rows_checked'], 'violations': result['violations'],
                            'null_key_rows': result['null_key_rows'], 'repeated_values': count, 'repeated': repeated}}
    return f'查了全部 {result["rows_checked"]} 行，{"；".join(parts)}', detail


def check_key_choice(conn, dataset: dict, cols: dict, key) -> tuple[dict, list[str]]:
    """(the key check, warnings) for these columns as the key of a type on this dataset version: no decimal or yes/no column, unique and filled on every row
    (the check is recorded: it is the evidence), a date column warns. TypeRefused names the repeated keys when it fails."""
    if not isinstance(key, list) or not key or not all(isinstance(c, str) for c in key) or len(set(key)) != len(key):
        raise TypeRefused('主键要选一列或几列，不能重复')
    if set(key) - set(cols):
        raise TypeRefused(f'数据集里没有这些列：{"、".join(sorted(set(key) - set(cols)))}')
    warnings = []
    for column in key:
        kind = cols[column]['type']
        if kind in KEY_REFUSED:
            raise TypeRefused(f'“{column}”是{TYPE_NAME[kind]}列，不能做主键：{"小数会因为取整或精度对不上" if kind == "decimal" else "只有两个取值，最多对应两个对象"}')
        if kind in KEY_WARNED:
            warnings.append(f'“{column}”是日期，用日期做主键容易重复，也容易被改；确认前请再想一下')
    key_check = check_key(conn, dataset['id'], key)
    if key_check['status'] != 'passed':
        why, detail = _key_failure(conn, key_check)
        raise TypeRefused(f'这个主键不行：{why}。请换一个主键，或先处理数据里的重复', detail=detail)
    return key_check, warnings


def key_preview(conn, dataset_name, key) -> dict:
    """The wizard's check of a chosen key before anything is saved: {'rows_checked', 'warnings'}, or TypeRefused (with the repeated keys in its detail)."""
    dataset = current_dataset(conn, dataset_name) if isinstance(dataset_name, str) else None
    if dataset is None:
        raise TypeRefused(f'没有叫“{dataset_name}”的数据集', 404)
    check, warnings = check_key_choice(conn, dataset, dataset_columns(conn, dataset['id']), key)
    return {'rows_checked': check['rows_checked'], 'warnings': warnings}


def check_definition(conn, payload: dict, english_name: str | None = None) -> tuple[dict, dict, list[str], dict]:
    """(content, posted meanings, warnings, key_check) of a type as a person wrote it, checked against the current version of the dataset: the key is
    unique and filled on every row (the check is recorded: it is the evidence), no real-number or yes/no key, typed properties that fit their columns, code
    columns with few enough values. Raises TypeRefused."""
    english = payload.get('english_name') if english_name is None else english_name
    if not isinstance(english, str) or not ENGLISH_NAME.fullmatch(english):
        raise TypeRefused('英文名只能用字母、数字和下划线，字母开头，最多 40 个字符')
    if english.casefold() == 'new':
        raise TypeRefused('英文名不能叫 new：页面的“新建”用了这个地址')
    name = _text(payload.get('name'), '名称', MAX_NAME)
    description = _text(payload.get('description') or '', '说明', MAX_DESCRIPTION, required=False)
    dataset = current_dataset(conn, payload.get('dataset')) if isinstance(payload.get('dataset'), str) else None
    if dataset is None:
        raise TypeRefused(f'没有叫“{payload.get("dataset")}”的数据集', 404)
    cols = dataset_columns(conn, dataset['id'])
    key = payload.get('key')
    key_check, warnings = check_key_choice(conn, dataset, cols, key)
    wanted = payload.get('properties') or []
    if not isinstance(wanted, list) or not all(isinstance(p, dict) for p in wanted):
        raise TypeRefused('属性要写成列表')
    by_column: dict[str, dict] = {}
    for p in wanted:
        if p.get('column') not in cols:
            raise TypeRefused(f'数据集里没有这一列：{p.get("column")}')
        if p['column'] in by_column:
            raise TypeRefused(f'列“{p["column"]}”写了两次')
        by_column[p['column']] = p
    for column in key:
        by_column.setdefault(column, {'column': column})
    properties, shown_names = [], set()
    for column, p in by_column.items():
        col = cols[column]
        kind = p.get('type') or col['type']
        if kind not in FITS[col['type']]:
            raise TypeRefused(f'“{column}”里是{TYPE_NAME[col["type"]]}，不能当{TYPE_NAME.get(kind, kind)}用')
        enum = p.get('enum') is True
        if enum and (kind not in CODE_TYPES or not col['counts']):
            raise TypeRefused(f'“{column}”不能当代码列：代码列要是整数或文本，而且取值不超过 20 个')
        shown = _text(p.get('name') or column, '属性名称', MAX_NAME)
        if shown.casefold() in shown_names:
            raise TypeRefused(f'属性名称“{shown}”重复了')
        shown_names.add(shown.casefold())
        properties.append({'column': column, 'name': shown, 'type': kind, 'enum': enum})
    content = {'name': name, 'english_name': english, 'description': description, 'dataset': dataset['name'], 'key': list(key), 'properties': properties}
    posted = payload.get('enums') or {}
    if not isinstance(posted, dict):
        raise TypeRefused('含义要写成 {列名: [{value, label}]}')
    for column in posted:
        if not any(p['column'] == column and p['enum'] for p in properties):
            raise TypeRefused(f'“{column}”不是这个类型里的代码列，没法写含义')
    return content, posted, warnings, key_check


def _meanings(kept: list[dict], column: str, col: dict, posted) -> list[dict]:
    """The meanings after a person's entries are put over the ones on file (check_enum, merge_enum): only values the data has or that already have a
    meaning (so a stale one can be taken back); a blank label takes one back."""
    profile = {'values': [{'value': v} for v in {*(col['counts'] or {}), *(e['value'] for e in kept)}]}
    try:
        entries = check_enum(profile, posted)
    except ValueError as exc:
        raise TypeRefused(str(exc)) from None
    return merge_enum(kept, entries)


def _kept_meanings(conn, english_name: str, column: str) -> list[dict]:
    row = element_row(conn, enum_id(english_name, column))
    return _content(row)['values'] if row and row['content_json'] else []


def check_names_free(conn, content: dict) -> None:
    """The English name is the type's id, so it is unique case-insensitively; the display name too."""
    mine = type_id(content['english_name'])
    for element_id, other in conn.execute("SELECT element_id, content_json FROM element_state WHERE element_id LIKE 'objtype:%'"):
        if element_id == mine:
            continue
        if element_id.casefold() == mine.casefold():
            raise TypeRefused(f'英文名“{content["english_name"]}”和已有的“{element_id[len(TYPE_PREFIX):]}”只差大小写', 409)
        if json.loads(other)['name'].casefold() == content['name'].casefold():
            raise TypeRefused(f'已经有叫“{content["name"]}”的对象类型', 409)


def _type_change(content: dict, dataset: dict, key_check: dict, who: str | None) -> tuple:
    anchors = {'dataset': dataset['name'], 'version': dataset['version'], 'key_rows': key_check['rows_checked']}
    return (type_id(content['english_name']), 'checked', f'check_result:{key_check["id"]},dataset:{dataset["name"]}@v{dataset["version"]}', who, content, anchors, who)


def _meaning_change(conn, content: dict, column: str, values: list[dict], dataset: dict, cols: dict, who: str | None) -> tuple | None:
    """The change that puts these meanings (the whole list now) forward, or None when they are what is already on file (saving a confirmed meaning again
    unchanged does not reset it)."""
    row = element_row(conn, enum_id(content['english_name'], column))
    if not values:
        raise TypeRefused(f'“{column}”至少要有一个取值写了含义')
    if row and row['state'] in (*WAITING, 'confirmed') and values == _content(row)['values']:
        return None
    meaning = {'type': content['english_name'], 'column': column, 'dataset': dataset['name'], 'values': values}
    anchors = {'dataset': dataset['name'], 'version': dataset['version'], 'counts': dict(cols[column]['counts'] or {})}
    return (enum_id(content['english_name'], column), 'checked', f'dataset:{dataset["name"]}@v{dataset["version"]}', who, meaning, anchors, who)


def create_type(conn, payload: dict, who: str | None) -> dict:
    """Put a new object type forward (state checked, the person who wrote it its proposer), with the meanings they gave to its code columns, if any.
    Returns {'id', 'warnings'}."""
    content, posted, warnings, key_check = check_definition(conn, payload)
    if element_row(conn, type_id(content['english_name'])):
        raise TypeRefused(f'已经有英文名“{content["english_name"]}”的对象类型', 409)
    check_names_free(conn, content)
    dataset = current_dataset(conn, content['dataset'])
    cols = dataset_columns(conn, dataset['id'])
    changes, reads = [_type_change(content, dataset, key_check, who)], {type_id(content['english_name']): [f'dataset:{dataset["name"]}']}
    for column, entries in posted.items():
        values = _meanings([], column, cols[column], entries)
        if values:
            changes.append(_meaning_change(conn, content, column, values, dataset, cols, who))
            reads[changes[-1][0]] = [f'column:{dataset["name"]}.{column}']
    write_elements(conn, changes, reads)
    return {'id': content['english_name'], 'warnings': warnings}


def reset_reasons(old: dict, new: dict) -> list[str]:
    """What changed that a confirmation was about: the key, the source dataset, a property's type or whether it is a code column. The display names and
    the description are not on the list. (The meanings of a code column are their own element and reset themselves when their values change.)"""
    reasons = []
    if old['key'] != new['key']:
        reasons.append('主键')
    if old['dataset'] != new['dataset']:
        reasons.append('来源数据集')
    kinds = lambda c: {p['column']: (p['type'], p['enum']) for p in c['properties']}
    if kinds(old) != kinds(new):
        reasons.append('属性的类型')
    return reasons


def update_type(conn, payload: dict, who: str | None) -> dict:
    """Save a changed definition ({id, version, ...the fields of create}). `version` is the one the person was looking at: 409 when it has moved. A change
    on the reset list (reset_reasons) makes it checked again with this person as its proposer, and so does saving a model's draft; a change to the names or
    the description keeps its state and only goes to the log. Meanings in the payload are put forward like propose_meanings does. Returns {'id', 'state', 'reset', 'warnings'}."""
    row = element_row(conn, type_id(str(payload.get('id'))))
    if row is None:
        raise TypeRefused('没有这个对象类型', 404)
    if payload.get('version') != row['version']:
        raise TypeRefused('这个对象类型在你打开之后被改了，请刷新后再改', 409)
    old = _content(row)
    content, posted, warnings, key_check = check_definition(conn, {**payload, 'english_name': old['english_name']}, old['english_name'])
    check_names_free(conn, content)
    dataset = current_dataset(conn, content['dataset'])
    cols = dataset_columns(conn, dataset['id'])
    reset = reset_reasons(old, content)
    changes, reads = [], {}
    if reset or row['state'] in ('proposed', 'rejected'):   # a model's draft a person saves becomes theirs, checked, even with nothing changed; so does one that was sent back
        changes.append(_type_change(content, dataset, key_check, who))
        reads[type_id(old['english_name'])] = [f'dataset:{dataset["name"]}']
    for column, entries in posted.items():
        change = _meaning_change(conn, content, column, _meanings(_kept_meanings(conn, old['english_name'], column), column, cols[column], entries), dataset, cols, who)
        if change:
            changes.append(change)
            reads[change[0]] = [f'column:{dataset["name"]}.{column}']
    if changes:
        write_elements(conn, changes, reads)
    if reset and row['state'] == 'confirmed':   # the type is not confirmed any more: what reads it (the relations) cannot stand on it
        flag_readers(conn, row['element_id'], f'它连接的“{old["name"]}”类型改了{"、".join(reset)}，要重新确认')
    if not reset and (old['name'], old['description']) != (content['name'], content['description']):
        _edit_names(conn, row, content, who)
    return {'id': old['english_name'], 'state': element_row(conn, row['element_id'])['state'], 'reset': reset, 'warnings': warnings}


def _edit_names(conn, row: dict, content: dict, who: str | None) -> None:
    """A change to the display name or the description: the state stays, the log says who."""
    old = _content(row)
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('UPDATE element_state SET content_json = ?, version = version + 1 WHERE element_id = ?',
                     (json.dumps({**old, 'name': content['name'], 'description': content['description']}, ensure_ascii=False, sort_keys=True), row['element_id']))
        log_line(conn, who or '未署名', row['element_id'], 'edited', before={'name': old['name'], 'description': old['description']},
                 after={'name': content['name'], 'description': content['description'], 'state': row['state']})
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise


def propose_meanings(conn, payload: dict, who: str | None) -> dict:
    """{id: the type, column, values: [{value, label, description}]}: what some values of one code column mean, put over what is on file (a blank label
    takes a value's meaning back). The meanings become the person's proposal: checked, and another builder confirms them. Returns {'changed': bool}."""
    row = element_row(conn, type_id(str(payload.get('id'))))
    if row is None:
        raise TypeRefused('没有这个对象类型', 404)
    content, column = _content(row), payload.get('column')
    if not any(p['column'] == column and p['enum'] for p in content['properties']):
        raise TypeRefused(f'“{column}”不是这个类型里的代码列')
    dataset = current_dataset(conn, content['dataset'])
    cols = dataset_columns(conn, dataset['id']) if dataset else {}
    if column not in cols:
        raise TypeRefused(f'数据集里已经没有“{column}”这一列', 409)
    values = _meanings(_kept_meanings(conn, content['english_name'], column), column, cols[column], payload.get('values'))
    change = _meaning_change(conn, content, column, values, dataset, cols, who)
    if change is None:
        return {'changed': False}
    write_elements(conn, [change], {change[0]: [f'column:{dataset["name"]}.{column}']})
    return {'changed': True}


# --- checks: now, and again when the data moves ---------------------------------------------------------------------------------------------------

def _type_problems(conn, content: dict) -> tuple[list[str], int | None]:
    """(what is wrong now, the id of the key check that ran) for a type, read from the current version of its dataset."""
    dataset = current_dataset(conn, content['dataset'])
    if dataset is None:
        return [f'数据集“{content["dataset"]}”已经不在了'], None
    cols = dataset_columns(conn, dataset['id'])
    gone = [p['column'] for p in content['properties'] if p['column'] not in cols]
    if gone:
        return [f'{dataset["name"]} 第 {dataset["version"]} 版里没有这些列了：{"、".join(gone)}'], None
    problems = [f'“{p["column"]}”现在的内容是{TYPE_NAME[cols[p["column"]]["type"]]}，装不进{TYPE_NAME[p["type"]]}'
                for p in content['properties'] if p['type'] not in FITS[cols[p['column']]['type']]]
    key_check = check_key(conn, dataset['id'], content['key'])
    if key_check['status'] != 'passed':
        problems.append(f'主键“{" + ".join(content["key"])}”现在不唯一或有空值：{_key_failure(conn, key_check)[0]}')
    return problems, key_check['id']


def _enum_problems(conn, row: dict) -> list[str]:
    """What moved in the values of a code column since its meanings were confirmed: a value the data has now that was not there, or a value with a
    meaning that is not there any more."""
    content, was = _content(row), json.loads(row['anchors_json'])['counts']
    dataset = current_dataset(conn, content['dataset'])
    col = (dataset_columns(conn, dataset['id']) if dataset else {}).get(content['column'])
    if col is None or col['counts'] is None:
        return [f'“{content["column"]}”现在不再是一列只有几个取值的代码列']
    now = col['counts']
    labels = {e['value']: e['label'] for e in content['values']}
    new = [f'{v}（{now[v]} 行，没有含义）' for v in _by_value(set(now) - set(was))]
    gone = [f'{v}（原来是「{labels[v]}」）' for v in _by_value(set(was) - set(now)) if v in labels]
    if not new and not gone:
        return []
    said = [*([f'新出现 {"、".join(new)}'] if new else []), *([f'不再出现 {"、".join(gone)}'] if gone else [])]
    return [f'{dataset["name"]} 第 {dataset["version"]} 版（{dataset["who"] or "未署名"}上传）里，“{content["column"]}”的取值变了：{"；".join(said)}。确认时的取值是 {"、".join(_by_value(was))}']


def _label(conn, element_id: str) -> str:
    content = _content(element_row(conn, element_id))
    return f'“{content["name"]}”类型' if element_id.startswith(TYPE_PREFIX) else f'“{content["name"]}”关系' if element_id.startswith(RELATION_PREFIX) else f'“{content["column"]}”的含义'


def flag_readers(conn, element_id: str, reason: str) -> list[str]:
    """What reads this element and is confirmed goes to needs_look with the reason (and so on to what reads it): used when the element itself stopped being confirmed."""
    moved: list[str] = []
    conn.execute('BEGIN IMMEDIATE')
    try:
        for (reader,) in conn.execute('SELECT element_id FROM element_dep WHERE depends_on = ?', (element_id,)).fetchall():
            _flag(conn, reader, reason, None, moved)
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return moved


def _flag(conn, element_id: str, reason: str, caused_by: str | None, moved: list[str]) -> None:
    """A confirmed element whose check came out different goes to needs_look with the reason; then the same for what reads it, with its own reason."""
    row = element_row(conn, element_id)
    if row is None or row['state'] != 'confirmed':
        return
    conn.execute("UPDATE element_state SET state = 'needs_look', reason = ?, version = version + 1 WHERE element_id = ?", (reason, element_id))
    log_line(conn, 'system', element_id, 'needs_look',
             before={'state': 'confirmed', 'confirmed_by': row['confirmed_by'], 'confirmed_at': row['confirmed_at']},
             after={'state': 'needs_look', 'reason': reason, 'caused_by': caused_by}, user_id=None)
    moved.append(element_id)
    for (reader,) in conn.execute('SELECT element_id FROM element_dep WHERE depends_on = ?', (element_id,)).fetchall():
        _flag(conn, reader, f'它用的{_label(conn, element_id)}需要再看（原因见{"那一组含义" if element_id.startswith(ENUM_PREFIX) else "那个对象类型"}）', caused_by, moved)


def recheck_dependents(conn, dataset_name: str, caused_by: str | None = None) -> list[str]:
    """The dataset has a new current version: run the checks behind every confirmed element that reads it again. One whose result changed is moved to
    needs_look with the reason, together with what reads it. Returns the ids of the elements that moved."""
    column_prefix = f'column:{dataset_name}.'
    readers = [r[0] for r in conn.execute('SELECT DISTINCT element_id FROM element_dep WHERE depends_on = ? OR substr(depends_on, 1, ?) = ?',
                                          (f'dataset:{dataset_name}', len(column_prefix), column_prefix))]
    moved: list[str] = []
    from ontology_poc_generator.object_relations import relation_problems   # object_relations reads this module: imported here, where it is used
    order = lambda e: 0 if e.startswith(ENUM_PREFIX) else 2 if e.startswith(RELATION_PREFIX) else 1   # meanings, then types (which move with their meanings), then relations (which move with their types)
    conn.execute('BEGIN IMMEDIATE')
    try:
        for element_id in sorted(readers, key=order):
            row = element_row(conn, element_id)
            if row is None or row['state'] != 'confirmed':
                continue
            problems = (_enum_problems(conn, row) if element_id.startswith(ENUM_PREFIX) else relation_problems(conn, row) if element_id.startswith(RELATION_PREFIX)
                        else _type_problems(conn, _content(row))[0])
            if problems:
                _flag(conn, element_id, '；'.join(problems), caused_by, moved)
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return moved


def dataset_readers_of(conn, name: str, user: dict | None = None, everyone: bool = True) -> list[dict]:
    """The object types that read this dataset: all of them for the delete guard (everyone), only the ones this person may see for the "used by" shown on a page."""
    return [{'kind': '对象类型', 'name': json.loads(content)['name']} for element_id, content in conn.execute(
        "SELECT s.element_id, s.content_json FROM element_dep d JOIN element_state s ON s.element_id = d.element_id "
        "WHERE d.depends_on = ? AND d.element_id LIKE 'objtype:%' ORDER BY d.element_id", (f'dataset:{name}',))
        if everyone or _visible(conn, element_row(conn, element_id), user)]


# --- confirming ---------------------------------------------------------------------------------------------------------------------------------

def _enum_now_problems(conn, content: dict) -> list[str]:
    dataset = current_dataset(conn, content['dataset'])
    if dataset is None:
        return [f'数据集“{content["dataset"]}”已经不在了']
    col = dataset_columns(conn, dataset['id']).get(content['column'])
    if col is None or col['counts'] is None:
        return [f'“{content["column"]}”现在不再是一列只有几个取值的代码列']
    return [f'含义里的取值 {e["value"]} 现在的数据里没有' for e in content['values'] if e['value'] not in col['counts']]


def confirm_element(conn, payload: dict, who: str | None) -> dict:
    """{id: the type, column?: a code column (confirms its meanings; without it the type itself), version}: confirm what the person has looked at. A builder
    other than the one who put it forward (SelfConfirmation otherwise), and only the version they saw (409 when it has changed). The checks run again on
    the data as it is now and the snapshot of what was confirmed (definition, evidence, dataset versions) is kept. A type that needs another look can be
    confirmed once its meanings are not waiting on one themselves; meanings that need another look are put forward again instead."""
    row = element_row(conn, type_id(str(payload.get('id'))))
    if row is None:
        raise TypeRefused('没有这个对象类型', 404)
    if payload.get('column') is not None:
        row = element_row(conn, enum_id(row['element_id'][len(TYPE_PREFIX):], str(payload.get('column'))))
        if row is None:
            raise TypeRefused('这一列还没有人提出含义', 404)
    if payload.get('version') != row['version']:
        raise TypeRefused('确认要带上你看到的那一版；它在你看过之后被改了，请刷新后重新看一遍', 409)
    element_id, content, is_type = row['element_id'], _content(row), row['element_id'].startswith(TYPE_PREFIX)
    if row['state'] == 'confirmed':
        raise TypeRefused('已经确认过了', 409)
    if row['state'] == 'rejected':
        raise TypeRefused('已经被退回了：要先按退回的理由改，再重新提出', 409)
    if row['state'] == 'needs_look' and not is_type:
        raise TypeRefused('这组含义需要再看：请按现在的数据重新提出含义，由另一位确认', 409)
    dataset = current_dataset(conn, content['dataset'])
    if is_type:
        problems, check_id = _type_problems(conn, content)
        waiting = [r[0] for r in conn.execute("SELECT d.depends_on FROM element_dep d JOIN element_state s ON s.element_id = d.depends_on "
                                              "WHERE d.element_id = ? AND s.state = 'needs_look'", (element_id,))]
        if waiting:
            problems.append(f'它的{_label(conn, waiting[0])}需要先再看一遍')
        anchors = {'dataset': dataset['name'], 'version': dataset['version']} if dataset else None
        evidence = f'check_result:{check_id},dataset:{dataset["name"]}@v{dataset["version"]}' if check_id else row['evidence_ref']
    else:
        problems = _enum_now_problems(conn, content)
        anchors = {'dataset': dataset['name'], 'version': dataset['version'], 'counts': dataset_columns(conn, dataset['id'])[content['column']]['counts']} if not problems else None
        evidence = f'dataset:{dataset["name"]}@v{dataset["version"]}' if dataset else None
    if problems:
        raise TypeRefused(f'按现在的数据过不了检查，不能确认：{"；".join(problems)}', 409)
    write_confirmation(conn, element_id, content, evidence, who, anchors, {dataset['name']: dataset['version']})
    return {'state': 'confirmed'}


def write_confirmation(conn, element_id: str, content: dict, evidence: str | None, who: str | None, anchors: dict | None, dataset_versions: dict) -> None:
    """The element becomes confirmed by this person and the snapshot of what they confirmed (definition, evidence, dataset versions) is kept with it;
    all or nothing. SelfConfirmation when it is their own proposal while two-person confirmation is active."""
    with element_state_writes(conn, [(element_id, 'confirmed', evidence, who, content, anchors, None)]) as rows:
        kept = rows[element_id]
        conn.execute('INSERT INTO confirmation(element_id, confirmed_by, confirmed_by_user_id, proposed_by, confirmed_at, content_json, evidence_ref, dataset_versions_json, self_confirmed)'
                     ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                     (element_id, kept['confirmed_by'], kept['confirmed_by_user_id'], kept['proposed_by'], kept['confirmed_at'], kept['content_json'], kept['evidence_ref'],
                      json.dumps(dataset_versions, ensure_ascii=False),
                      int(kept['confirmed_by_user_id'] is not None and kept['confirmed_by_user_id'] == kept['proposed_by_user_id'])))


# --- what the pages read ------------------------------------------------------------------------------------------------------------------------

def _confirmers(conn, row: dict, user: dict | None) -> tuple[bool, list[str]]:
    """(whether this person may confirm it now, the builders who may). A viewer never; the one who put it forward not while two-person is active."""
    rule = two_person(conn)
    excluded = row['proposed_by_user_id'] if rule['active'] else None
    others = [name for name, in conn.execute(
        "SELECT display_name FROM user WHERE disabled = 0 AND role IN ('builder', 'admin') AND (? IS NULL OR id != ?) ORDER BY display_name", (excluded, excluded))]
    if user is not None and user['role'] == 'viewer':
        return False, others
    return not (excluded is not None and user is not None and user['id'] == excluded), others


def _state_view(conn, row: dict, user: dict | None) -> dict:
    """The state of one element for a page: who put it forward, whether this person may confirm it, who could, the last confirmation, the reason it needs a look."""
    waiting = row['state'] in WAITING or (row['state'] == 'needs_look' and row['element_id'].startswith((TYPE_PREFIX, RELATION_PREFIX)))
    can, others = _confirmers(conn, row, user)
    blocked = row['state'] == 'needs_look' and conn.execute(
        "SELECT 1 FROM element_dep d JOIN element_state s ON s.element_id = d.depends_on WHERE d.element_id = ? AND s.state = 'needs_look'", (row['element_id'],)).fetchone()
    last = conn.execute('SELECT confirmed_by, confirmed_at, dataset_versions_json, evidence_ref FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 1',
                        (row['element_id'],)).fetchone()
    return {'state': row['state'], 'version': row['version'], 'proposed_by': row['proposed_by'], 'reason': row['reason'] if row['state'] in ('needs_look', 'rejected') else None,
            'model_draft': row['state'] == 'proposed' and row['proposed_by'] is None, 'can_confirm': waiting and can and not blocked, 'confirmers': others if waiting and not blocked else [],
            'confirmed_by': last[0] if last else None, 'confirmed_at': last[1] if last else None,
            'confirmed_on': json.loads(last[2]) if last else None, 'evidence': last[3] if last else None, 'written_at': row['confirmed_at']}


def _visible(conn, row: dict, user: dict | None) -> bool:
    """A type nobody confirmed is for builders; a type with a list of people is for them (and admins) only (type_access)."""
    if user is not None and user['role'] == 'viewer' and row['state'] != 'confirmed':
        return False
    return can_access(conn, row['element_id'], user)


def list_types(conn, user: dict | None) -> list[dict]:
    """Every object type as the list shows it, by English name. A viewer sees only the confirmed ones."""
    out = []
    for element_id, in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objtype:%' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        if not _visible(conn, row, user):
            continue
        content = _content(row)
        dataset = current_dataset(conn, content['dataset'])
        waiting = conn.execute("SELECT COUNT(*) FROM element_dep d JOIN element_state s ON s.element_id = d.depends_on WHERE d.element_id = ? AND d.depends_on LIKE 'enum:%' "
                               "AND s.state != 'confirmed'", (element_id,)).fetchone()[0]
        out.append({'id': content['english_name'], 'name': content['name'], 'dataset': content['dataset'], 'dataset_version': dataset['version'] if dataset else None,
                    'rows': dataset['rows_stored'] if dataset else None, 'meanings_waiting': waiting, **_state_view(conn, row, user)})
    return out


def _meaning_view(conn, content: dict, prop: dict, cols: dict, user: dict | None) -> dict:
    """One code column: its values as the data has them now beside the meanings on file and the rows each had when they were confirmed, and the state."""
    row = element_row(conn, enum_id(content['english_name'], prop['column']))
    now = (cols.get(prop['column']) or {}).get('counts') or {}
    labels = {e['value']: e for e in (_content(row)['values'] if row and row['content_json'] else [])}
    was = json.loads(row['anchors_json'])['counts'] if row and row['anchors_json'] else {}
    values = [{'value': v, 'label': labels[v]['label'] if v in labels else '', 'description': labels[v]['description'] if v in labels else '',
               'rows': now.get(v), 'rows_at_confirmation': was.get(v), 'in_data': v in now} for v in _by_value({*now, *labels})]
    return {'column': prop['column'], 'values': values, **(_state_view(conn, row, user) if row else {'state': None, 'can_confirm': False})}


def type_detail(conn, english_name: str, user: dict | None) -> dict:
    row = element_row(conn, type_id(english_name))
    if row is None or not _visible(conn, row, user):
        raise TypeRefused('没有这个对象类型', 404)
    content = _content(row)
    dataset = current_dataset(conn, content['dataset'])
    cols = dataset_columns(conn, dataset['id']) if dataset else {}
    props = [{**p, 'key': p['column'] in content['key'], 'meanings': _meaning_view(conn, content, p, cols, user) if p['enum'] else None} for p in content['properties']]
    return {'id': content['english_name'], 'name': content['name'], 'description': content['description'], 'dataset': content['dataset'],
            'dataset_version': dataset['version'] if dataset else None, 'rows': dataset['rows_stored'] if dataset else None, 'key': content['key'],
            'properties': props, **_state_view(conn, row, user),
            'columns': [{'name': n, 'type': c['type'], 'enum_candidate': bool(c['counts']) and c['type'] in CODE_TYPES} for n, c in cols.items()]}


def type_objects(conn, english_name: str, page: int, user: dict | None) -> dict:
    """The rows of the type's dataset (its current version) as objects: the key and the properties, one page, with how each code column's meanings stand."""
    detail = type_detail(conn, english_name, user)
    dataset = current_dataset(conn, detail['dataset'])
    if dataset is None:
        raise TypeRefused(f'数据集“{detail["dataset"]}”已经不在了', 409)
    total = dataset['rows_stored']
    pages = max(1, -(-total // OBJECT_PAGE))
    page = min(max(page, 1), pages)
    q = lambda name: '"' + name.replace('"', '""') + '"'
    rows = [list(r) for r in conn.execute(f'SELECT {", ".join(q(p["column"]) for p in detail["properties"])} FROM {q(dataset["table_name"])} '
                                          f'ORDER BY rowid LIMIT {OBJECT_PAGE} OFFSET {(page - 1) * OBJECT_PAGE}')]
    enums = {p['column']: {'state': p['meanings']['state'], 'labels': {v['value']: v['label'] for v in p['meanings']['values'] if v['label']}}
             for p in detail['properties'] if p['meanings']}
    return {'columns': [{'column': p['column'], 'name': p['name'], 'type': p['type'], 'key': p['key']} for p in detail['properties']], 'rows': rows, 'total': total,
            'page': page, 'pages': pages, 'limit': OBJECT_PAGE, 'dataset': detail['dataset'], 'dataset_version': dataset['version'], 'enums': enums}


def type_log(conn, english_name: str, user: dict | None) -> list[dict]:
    """What happened to a type, to the meanings of its code columns and to the dataset it reads, newest first: time, who, what, and for a move to
    needs_look the reason and whose upload it was."""
    detail = type_detail(conn, english_name, user)
    return log_entries(conn, [type_id(english_name), *(enum_id(english_name, p['column']) for p in detail['properties'] if p['meanings']), f'dataset:{detail["dataset"]}'])


def log_entries(conn, ids: list[str]) -> list[dict]:
    """The log lines about these elements, newest first (the caller has checked that this person may read them)."""
    out = []
    for at, who, element, change, before, after in conn.execute(
            f'SELECT time, who, element_id, change, before_json, after_json FROM log WHERE element_id IN ({",".join("?" * len(ids))}) ORDER BY time DESC, rowid DESC', ids):
        after = json.loads(after) if after else {}
        kind = 'dataset' if element.startswith('dataset:') else 'meaning' if element.startswith(ENUM_PREFIX) else 'relation' if element.startswith(RELATION_PREFIX) else 'type'
        out.append({'at': at, 'who': who, 'element': kind, 'column': element.split(':', 2)[2] if kind == 'meaning' else None, 'change': change,
                    'from': (json.loads(before) if before else {}).get('state'), 'to': after.get('state'), 'reason': after.get('reason'),
                    'caused_by': after.get('caused_by'), 'self_confirmed': bool(after.get('self_confirmed')),
                    'visible_to': after.get('visible_to') if change == 'access_changed' else None,
                    'text': after.get('name') if change == 'edited' else change if kind == 'dataset' else None})
    return out
