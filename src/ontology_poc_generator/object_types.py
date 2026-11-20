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

from ontology_poc_generator.lang import TrMap, current, speaking, tr
import contextlib
import contextvars
import json
import re
import sys

from ontology_poc_generator.accounts import two_person
from ontology_poc_generator.assistant_checks import drafted_mark
from ontology_poc_generator.draft_receipts import spend as spend_receipt
from ontology_poc_generator.code_meanings import check_enum, merge_enum
from ontology_poc_generator.row_rules import keeps, positions, restriction
from ontology_poc_generator.type_access import can_access, column_allowed, dataset_hidden, hidden_columns, hidden_values, reads_hidden, visible_to
from ontology_poc_generator.workspace_store import fan_note, StaleElement, _canonical, _key_of, check_key, current_dataset, dataset_records, element_state_writes, fan_marks, log_line

TYPE_PREFIX = 'objtype:'
ENUM_PREFIX = 'enum:'
RELATION_PREFIX = 'relation:'
VIEW_PREFIX = 'objview:'
ACTION_PREFIX = 'objaction:'
PIPELINE_PREFIX = 'pipeline:'
DERIVED_PREFIX = 'derived:'
ENGLISH_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,39}')
MAX_NAME, MAX_DESCRIPTION = 40, 200
OBJECT_PAGE = 50
TYPE_NAME = TrMap({'integer': ('整数', 'integer'), 'decimal': ('小数', 'decimal'), 'text': ('文本', 'text'), 'date': ('日期', 'date'), 'month': ('月份', 'month'), 'datetime': ('日期时间', 'date and time'), 'boolean': ('是否', 'yes/no')})
KEY_REFUSED = ('decimal', 'boolean')   # a real number or a two-valued column is not an identity
KEY_WARNED = ('date', 'datetime', 'month')
FITS = {'integer': ('integer', 'decimal', 'text'), 'decimal': ('decimal', 'text'), 'text': ('text',), 'date': ('date', 'datetime', 'text'),
        'month': ('month', 'text'), 'datetime': ('datetime', 'text'), 'boolean': ('boolean', 'text')}   # what a column of this inferred type may be declared as
CODE_TYPES = ('integer', 'text')   # a code column is one of these, never boolean
WAITING = ('proposed', 'checked')
def limited_note() -> str:
    return tr('受行规则限制，看不到全部数据的统计', 'A row rule limits you, so you cannot see statistics over all the data')


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
        raise TypeRefused(tr(f'{what}要写 1 到 {limit} 个字，不能换行', f'{what} must be 1 to {limit} characters, on one line') if required else tr(f'{what}最多 {limit} 个字，不能换行', f'{what} must be at most {limit} characters, on one line'))
    return text


def _by_value(values) -> list[str]:
    return sorted(values, key=lambda v: (0, int(v), v) if re.fullmatch(r'-?\d{1,18}', v) else (1, 0, v))


def _set_deps(conn, element_id: str, depends_on: list[str]) -> None:
    conn.execute("DELETE FROM element_dep WHERE element_id = ? AND depends_on NOT LIKE 'enum:%'", (element_id,))   # what a type reads of its meanings is added as they are made
    conn.executemany('INSERT OR IGNORE INTO element_dep(element_id, depends_on) VALUES (?, ?)', [(element_id, d) for d in depends_on])


def _add_dep(conn, element_id: str, depends_on: str) -> None:
    conn.execute('INSERT OR IGNORE INTO element_dep(element_id, depends_on) VALUES (?, ?)', (element_id, depends_on))


def stale_note() -> str:
    return tr('它在你看过之后被改了，请刷新后重新看一遍', 'It was changed after you looked at it. Refresh and look again')


def write_elements(conn, changes: list[tuple], reads: dict[str, list[str]], versions: dict[str, int] | None = None, after=None) -> None:
    """Keep the changes all together or not at all, with what each one reads. `versions`: the version of each element the writer read; one that has moved
    since is a 409 and nothing is written. `after(conn)` runs in the same transaction once the rows and what they read are written (the elements that
    stopped being confirmed move what reads them to needs_look there, so the two are never seen apart). Who can confirm what moved is told once it is written
    (one_telling)."""
    try:
        with one_telling(conn), element_state_writes(conn, changes, versions):
            for element_id, depends_on in reads.items():
                _set_deps(conn, element_id, depends_on)
            for element_id in reads:
                if element_id.startswith(ENUM_PREFIX):
                    _add_dep(conn, type_id(element_id[len(ENUM_PREFIX):].partition(':')[0]), element_id)
            if after:
                after(conn)
    except StaleElement:
        raise TypeRefused(stale_note(), 409) from None


# --- the definition a person writes -------------------------------------------------------------------------------------------------------------

def _key_failure(conn, result: dict) -> tuple[str, dict]:
    """(what is wrong with this key, in words; the detail a page shows) for a failed key check: the repeated values, up to 20, and how many rows are empty."""
    repeated = [{'key': list(r[:-1]), 'rows': r[-1]} for r in conn.execute(f'{result["query"]} LIMIT 20')]
    count = conn.execute(f'SELECT COUNT(*) FROM ({result["query"]})').fetchone()[0]
    parts = []
    if result['violations']:
        shown = tr('、', ', ').join(tr(f'{" + ".join(r["key"])}（{r["rows"]} 行）', f'{" + ".join(r["key"])} ({r["rows"]} rows)') for r in repeated[:5])
        parts.append(tr(f'{count} 个值重复，多出 {result["violations"]} 行，例如 {shown}', f'{count} values are repeated, {result["violations"]} extra rows, for example {shown}'))
    if result['null_key_rows']:
        parts.append(tr(f'{result["null_key_rows"]} 行是空的', f'{result["null_key_rows"]} rows are empty'))
    detail = {'key_check': {'status': result['status'], 'rows_checked': result['rows_checked'], 'violations': result['violations'],
                            'null_key_rows': result['null_key_rows'], 'repeated_values': count, 'repeated': repeated}}
    return tr(f'查了全部 {result["rows_checked"]} 行，{tr("；", "; ").join(parts)}', f'Checked all {result["rows_checked"]} rows: {"; ".join(parts)}'), detail


def check_key_choice(conn, dataset: dict, cols: dict, key) -> tuple[dict, list[str]]:
    """(the key check, warnings) for these columns as the key of a type on this dataset version: no decimal or yes/no column, unique and filled on every row
    (the check is recorded: it is the evidence), a date column warns. TypeRefused names the repeated keys when it fails."""
    if not isinstance(key, list) or not key or not all(isinstance(c, str) for c in key) or len(set(key)) != len(key):
        raise TypeRefused(tr('主键要选一列或几列，不能重复', 'Pick one or more columns for the key, without repeats'))
    if set(key) - set(cols):
        raise TypeRefused(tr(f'数据集里没有这些列：{tr("、", ", ").join(sorted(set(key) - set(cols)))}', f'The dataset has no such columns: {", ".join(sorted(set(key) - set(cols)))}'))
    refuse_ai_columns(conn, dataset['name'], key, tr('主键', 'a key'))
    warnings = []
    for column in key:
        kind = cols[column]['type']
        if kind in KEY_REFUSED:
            raise TypeRefused(tr(f'“{column}”是{TYPE_NAME[kind]}列，不能做主键：{"小数会因为取整或精度对不上" if kind == "decimal" else "只有两个取值，最多对应两个对象"}', f'"{column}" is a {TYPE_NAME[kind]} column and cannot be a key: {"decimals stop matching once they are rounded" if kind == "decimal" else "it has only two values, so it can name at most two objects"}'))
        if kind in KEY_WARNED:
            warnings.append(tr(f'“{column}”是日期，用日期做主键容易重复，也容易被改；确认前请再想一下', f'"{column}" is a date. A date is easily repeated and easily changed as a key, so think again before you confirm'))
    key_check = check_key(conn, dataset['id'], key)
    if key_check['status'] != 'passed':
        why, detail = _key_failure(conn, key_check)
        raise TypeRefused(tr(f'这个主键不行：{why}。请换一个主键，或先处理数据里的重复', f'This key does not work: {why}. Pick another key, or deal with the repeats in the data first'), detail=detail)
    return key_check, warnings


def _readable_dataset(conn, name, user: dict | None) -> dict | None:
    """The current version of this dataset, or None when there is none or this person may not see it (dataset_hidden: it is not found to them)."""
    return current_dataset(conn, name) if isinstance(name, str) and not dataset_hidden(conn, name, user) else None


def _type_row(conn, english_name, user: dict | None) -> dict:
    """The row of an object type this person may see; a type they may not see is not there for them (404), whatever they try to do to it."""
    row = element_row(conn, type_id(str(english_name)))
    if row is None or not _visible(conn, row, user):
        raise TypeRefused(tr('没有这个对象类型', 'There is no such object type'), 404)
    return row


def kept_columns() -> str:
    return tr('这个对象类型有属性不让你看：它的定义、含义和建在它上面的东西，要由看得到全部属性的人来写', 'This object type has properties you cannot see: its definition, its meanings and what is built on it must be written by someone who can see every property')


def whole_type_row(conn, english_name, user: dict | None) -> dict:
    """_type_row for writing a definition or opening a form on the type: refused (403) to a person kept from any of its columns, who would otherwise name,
    or be shown, a column they may not see."""
    row = _type_row(conn, english_name, user)
    if hidden_columns(conn, row['element_id'], user):
        raise TypeRefused(kept_columns(), 403)
    return row


def refuse_ai_columns(conn, dataset_name: str, columns, what: str) -> None:
    """A column an LLM step wrote cannot be a key or a confirmed code meaning until its sample review has passed and the pipeline is confirmed by a second person."""
    from ontology_poc_generator.workspace_pipelines import ai_uncleared   # the pipelines read types, so the import is made here
    held = {c: why for c, why in ai_uncleared(conn, dataset_name).items() if c in columns}
    if held:
        column, why = next(iter(held.items()))
        raise TypeRefused(tr(f'“{column}”不能当{what}：{why}', f'"{column}" cannot be {what}: {why}'), 409)


def key_preview(conn, dataset_name, key, user: dict | None = None) -> dict:
    """The wizard's check of a chosen key before anything is saved: {'rows_checked', 'warnings'}, or TypeRefused (with the repeated keys in its detail)."""
    dataset = _readable_dataset(conn, dataset_name, user)
    if dataset is None:
        raise TypeRefused(tr(f'没有叫“{dataset_name}”的数据集', f'There is no dataset named "{dataset_name}"'), 404)
    check, warnings = check_key_choice(conn, dataset, dataset_columns(conn, dataset['id']), key)
    return {'rows_checked': check['rows_checked'], 'warnings': warnings}


def check_definition(conn, payload: dict, english_name: str | None = None, user: dict | None = None) -> tuple[dict, dict, list[str], dict]:
    """(content, posted meanings, warnings, key_check) of a type as a person wrote it, checked against the current version of the dataset: the key is
    unique and filled on every row (the check is recorded: it is the evidence), no real-number or yes/no key, typed properties that fit their columns, code
    columns with few enough values. Raises TypeRefused."""
    english = payload.get('english_name') if english_name is None else english_name
    if not isinstance(english, str) or not ENGLISH_NAME.fullmatch(english):
        raise TypeRefused(tr('英文名只能用字母、数字和下划线，字母开头，最多 40 个字符', 'The English name may use only letters, digits and underscores, must start with a letter, and is at most 40 characters'))
    if english.casefold() == 'new':
        raise TypeRefused(tr('英文名不能叫 new：页面的“新建”用了这个地址', 'The English name cannot be "new": the New page uses that address'))
    name = _text(payload.get('name'), tr('名称', 'The name'), MAX_NAME)
    description = _text(payload.get('description') or '', tr('说明', 'The description'), MAX_DESCRIPTION, required=False)
    dataset = _readable_dataset(conn, payload.get('dataset'), user)
    if dataset is None:
        raise TypeRefused(tr(f'没有叫“{payload.get("dataset")}”的数据集', f'There is no dataset named "{payload.get("dataset")}"'), 404)
    cols = dataset_columns(conn, dataset['id'])
    key = payload.get('key')
    kept = {c for (t,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objtype:%' AND json_extract(content_json, '$.dataset') = ?", (dataset['name'],))
            for c in column_allowed(conn, t)} if isinstance(key, list) else set()
    named = {k for k in key if isinstance(k, str)} if isinstance(key, list) else set()
    if kept & named:   # a column kept from some people binds the dataset: it cannot name the objects of another type over it
        raise TypeRefused(tr(f'“{tr("、", ", ").join(sorted(kept & named))}”在这个数据集上只给部分人看，不能当编号；先在“权限”页让所有人看它', f'"{", ".join(sorted(kept & named))}" is shown to only some people on this dataset, so it cannot be a key. Let everyone see it on the Access page first'), 409)
    key_check, warnings = check_key_choice(conn, dataset, cols, key)
    wanted = payload.get('properties') or []
    if not isinstance(wanted, list) or not all(isinstance(p, dict) for p in wanted):
        raise TypeRefused(tr('属性要写成列表', 'Properties must be a list'))
    by_column: dict[str, dict] = {}
    for p in wanted:
        if p.get('column') not in cols:
            raise TypeRefused(tr(f'数据集里没有这一列：{p.get("column")}', f'The dataset has no column "{p.get("column")}"'))
        if p['column'] in by_column:
            raise TypeRefused(tr(f'列“{p["column"]}”写了两次', f'The column "{p["column"]}" is listed twice'))
        by_column[p['column']] = p
    for column in key:
        by_column.setdefault(column, {'column': column})
    properties, shown_names = [], set()
    for column, p in by_column.items():
        col = cols[column]
        kind = p.get('type') or col['type']
        if kind not in FITS[col['type']]:
            raise TypeRefused(tr(f'“{column}”里是{TYPE_NAME[col["type"]]}，不能当{TYPE_NAME.get(kind, kind)}用', f'"{column}" holds {TYPE_NAME[col["type"]]} values and cannot be used as {TYPE_NAME.get(kind, kind)}'))
        enum = p.get('enum') is True
        if enum and (kind not in CODE_TYPES or not col['counts']):
            raise TypeRefused(tr(f'“{column}”不能当代码列：代码列要是整数或文本，而且取值不超过 20 个', f'"{column}" cannot be a code column: a code column must be integer or text, with at most 20 values'))
        shown = _text(p.get('name') or column, tr('属性名称', 'The property name'), MAX_NAME)
        if shown.casefold() in shown_names:
            raise TypeRefused(tr(f'属性名称“{shown}”重复了', f'The property name "{shown}" is repeated'))
        shown_names.add(shown.casefold())
        properties.append({'column': column, 'name': shown, 'type': kind, 'enum': enum})
    content = {'name': name, 'english_name': english, 'description': description, 'dataset': dataset['name'], 'key': list(key), 'properties': properties}
    posted = payload.get('enums') or {}
    if not isinstance(posted, dict):
        raise TypeRefused(tr('含义要写成 {列名: [{value, label}]}', 'Meanings must be written as {column: [{value, label}]}'))
    for column in posted:
        if not any(p['column'] == column and p['enum'] for p in properties):
            raise TypeRefused(tr(f'“{column}”不是这个类型里的代码列，没法写含义', f'"{column}" is not a code column of this type, so it cannot have meanings'))
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
            raise TypeRefused(tr(f'英文名“{content["english_name"]}”和已有的“{element_id[len(TYPE_PREFIX):]}”只差大小写', f'The English name "{content["english_name"]}" differs from the existing "{element_id[len(TYPE_PREFIX):]}" only in case'), 409)
        if json.loads(other)['name'].casefold() == content['name'].casefold():
            raise TypeRefused(tr(f'已经有叫“{content["name"]}”的对象类型', f'There is already an object type named "{content["name"]}"'), 409)


def _type_change(content: dict, dataset: dict, key_check: dict, who: str | None) -> tuple:
    anchors = {'dataset': dataset['name'], 'version': dataset['version'], 'key_rows': key_check['rows_checked']}
    return (type_id(content['english_name']), 'checked', f'check_result:{key_check["id"]},dataset:{dataset["name"]}@v{dataset["version"]}', who, content, anchors, who)


def _meaning_change(conn, content: dict, column: str, values: list[dict], dataset: dict, cols: dict, who: str | None, fresh: bool = False) -> tuple | None:
    """The change that puts these meanings (the whole list now) forward, or None when they are what is already on file (saving a confirmed meaning again
    unchanged does not reset it). `fresh`: what is on file belongs to another dataset and is not compared."""
    row = element_row(conn, enum_id(content['english_name'], column))
    if not values:
        raise TypeRefused(tr(f'“{column}”至少要有一个取值写了含义', f'At least one value of "{column}" needs a meaning'))
    if not fresh and row and row['state'] in (*WAITING, 'confirmed') and values == _content(row)['values']:
        return None
    meaning = {'type': content['english_name'], 'column': column, 'dataset': dataset['name'], 'values': values}
    anchors = {'dataset': dataset['name'], 'version': dataset['version'], 'counts': dict(cols[column]['counts'] or {})}
    return (enum_id(content['english_name'], column), 'checked', f'dataset:{dataset["name"]}@v{dataset["version"]}', who, meaning, anchors, who)


def create_type(conn, payload: dict, who: str | None, user: dict | None = None) -> dict:
    """Put a new object type forward (state checked, the person who wrote it its proposer), with the meanings they gave to its code columns, if any.
    Returns {'id', 'warnings'}."""
    content, posted, warnings, key_check = check_definition(conn, payload, user=user)
    if element_row(conn, type_id(content['english_name'])):
        raise TypeRefused(tr(f'已经有英文名“{content["english_name"]}”的对象类型', f'There is already an object type with the English name "{content["english_name"]}"'), 409)
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
        reasons.append(tr('主键', 'the key'))
    if old['dataset'] != new['dataset']:
        reasons.append(tr('来源数据集', 'the source dataset'))
    kinds = lambda c: {p['column']: (p['type'], p['enum']) for p in c['properties']}
    if kinds(old) != kinds(new):
        reasons.append(tr('属性的类型', 'a property type'))
    return reasons


def _meaning_columns(conn, english_name: str) -> list[str]:
    """The code columns of this type that have a meaning element."""
    prefix = f'{ENUM_PREFIX}{english_name}:'
    return [element_id[len(prefix):] for (element_id,) in conn.execute('SELECT element_id FROM element_state WHERE substr(element_id, 1, ?) = ?', (len(prefix), prefix))]


def _retire_meanings(conn, english_name: str, columns: list[str], who: str | None, why: str) -> None:
    """Take the meanings of these columns away (inside the caller's transaction): they were about a column that is no longer a code column, or about another
    dataset's values. The type's log says so; the confirmation snapshots they leave stay."""
    for column in columns:
        element = enum_id(english_name, column)
        conn.execute('DELETE FROM element_dep WHERE element_id = ? OR depends_on = ?', (element, element))
        conn.execute('DELETE FROM element_state WHERE element_id = ?', (element,))
    if columns:
        log_line(conn, who or tr('未署名', 'unsigned'), type_id(english_name), 'meanings_retired', after={'columns': columns, 'reason': why})


def _confirmed_meaning(conn, english_name: str, column: str) -> bool:
    row = element_row(conn, enum_id(english_name, column))
    return bool(row) and row['state'] == 'confirmed'


def _meaning_reset_flags(conn, columns: list[str], english_name: str) -> None:
    """A confirmed set of meanings was changed (inside the caller's transaction): what reads it, the type and through it the relations, is not confirmed on them any more."""
    moved: list[str] = []
    for column in columns:
        _flag_readers(conn, enum_id(english_name, column), tr(f'“{column}”的含义改了，要重新确认', f'The meanings of "{column}" changed and need confirming again'), moved)


def update_type(conn, payload: dict, who: str | None, user: dict | None = None) -> dict:
    """Save a changed definition ({id, version, ...the fields of create}). `version` is the one the person was looking at: 409 when it has moved. A change
    on the reset list (reset_reasons) makes it checked again with this person as its proposer, and so does saving a model's draft; a change to the names or
    the description keeps its state and only goes to the log. Meanings in the payload are put forward like propose_meanings does; the meanings of a column
    that is no longer a code column, or of a dataset the type no longer reads, are taken away (post them again to keep them). Everything is written in one
    transaction, with what a confirmed element that stopped being confirmed moves. Returns {'id', 'state', 'reset', 'warnings'}."""
    row = whole_type_row(conn, payload.get('id'), user)
    if payload.get('version') != row['version']:
        raise TypeRefused(tr('这个对象类型在你打开之后被改了，请刷新后再改', 'This object type was changed after you opened it. Refresh and edit again'), 409)
    old = _content(row)
    content, posted, warnings, key_check = check_definition(conn, {**payload, 'english_name': old['english_name']}, old['english_name'], user)
    check_names_free(conn, content)
    dataset = current_dataset(conn, content['dataset'])
    cols = dataset_columns(conn, dataset['id'])
    reset = reset_reasons(old, content)
    if mark := drafted_mark(conn, payload, who, user, 'type', content, old.get('drafted'), old['english_name']):   # applied from the assistant's draft: who, when (a later ordinary edit keeps it)
        content = {**content, 'drafted': mark}
    english = old['english_name']
    existing = _meaning_columns(conn, english)
    moved_dataset = old['dataset'] != content['dataset']
    codes_now = {p['column'] for p in content['properties'] if p['enum']}
    retire = [c for c in existing if (moved_dataset or c not in codes_now) and c not in posted]
    changes, reads, was_confirmed = [], {}, []
    if reset or row['state'] in ('proposed', 'rejected'):   # a model's draft a person saves becomes theirs, checked, even with nothing changed; so does one that was sent back
        changes.append(_type_change(content, dataset, key_check, who))
        reads[type_id(english)] = [f'dataset:{dataset["name"]}']
    for column, entries in posted.items():
        fresh = moved_dataset and column in existing
        kept = [] if fresh else _kept_meanings(conn, english, column)
        change = _meaning_change(conn, content, column, _meanings(kept, column, cols[column], entries), dataset, cols, who, fresh)
        if change:
            changes.append(change)
            reads[change[0]] = [f'column:{dataset["name"]}.{column}']
            if _confirmed_meaning(conn, english, column):
                was_confirmed.append(column)
    if not changes:   # (something to retire always comes with a change on the reset list)
        if (old['name'], old['description']) != (content['name'], content['description']):
            _edit_names(conn, row, content, who)
        return {'id': english, 'state': row['state'], 'reset': reset, 'warnings': warnings}

    def after(c):
        if reset and row['state'] == 'confirmed':   # the type is not confirmed any more: what reads it (the relations) cannot stand on it
            _flag_readers(c, row['element_id'], tr(f'它连接的“{old["name"]}”类型改了{tr("、", ", ").join(reset)}，要重新确认', f'The type "{old["name"]}" it connects to changed ({", ".join(reset)}) and needs confirming again'), [])
        _meaning_reset_flags(c, was_confirmed, english)
        _retire_meanings(c, english, retire, who, tr('来源数据集换了' if moved_dataset else '不再是代码列', 'the source dataset changed' if moved_dataset else 'it is no longer a code column'))

    write_elements(conn, changes, reads, {row['element_id']: row['version']}, after)
    spend_receipt(conn, payload, user)
    if not reset and (old['name'], old['description']) != (content['name'], content['description']):
        _edit_names(conn, element_row(conn, row['element_id']), content, who)
    return {'id': english, 'state': element_row(conn, row['element_id'])['state'], 'reset': reset, 'warnings': warnings}


def _edit_names(conn, row: dict, content: dict, who: str | None) -> None:
    """A change to the display name or the description: the state stays, the log says who."""
    old = _content(row)
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('UPDATE element_state SET content_json = ?, version = version + 1 WHERE element_id = ?',
                     (json.dumps({**old, 'name': content['name'], 'description': content['description']}, ensure_ascii=False, sort_keys=True), row['element_id']))
        log_line(conn, who or tr('未署名', 'unsigned'), row['element_id'], 'edited', before={'name': old['name'], 'description': old['description']},
                 after={'name': content['name'], 'description': content['description'], 'state': row['state']})
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise


def propose_meanings(conn, payload: dict, who: str | None, user: dict | None = None) -> dict:
    """{id: the type, column, values: [{value, label, description}]}: what some values of one code column mean, put over what is on file (a blank label
    takes a value's meaning back). The meanings become the person's proposal: checked, and another builder confirms them. Meanings that were confirmed and
    are changed move the type that reads them, and the relations on it, to needs_look (in the same write). Returns {'changed': bool}."""
    row = whole_type_row(conn, payload.get('id'), user)
    content, column = _content(row), payload.get('column')
    if not any(p['column'] == column and p['enum'] for p in content['properties']):
        raise TypeRefused(tr(f'“{column}”不是这个类型里的代码列', f'"{column}" is not a code column of this type'))
    dataset = current_dataset(conn, content['dataset'])
    cols = dataset_columns(conn, dataset['id']) if dataset else {}
    if column not in cols:
        raise TypeRefused(tr(f'数据集里已经没有“{column}”这一列', f'The dataset no longer has the column "{column}"'), 409)
    values = _meanings(_kept_meanings(conn, content['english_name'], column), column, cols[column], payload.get('values'))
    change = _meaning_change(conn, content, column, values, dataset, cols, who)
    if change is None:
        return {'changed': False}
    was = element_row(conn, change[0])
    write_elements(conn, [change], {change[0]: [f'column:{dataset["name"]}.{column}']}, {change[0]: was['version']} if was else None,
                   (lambda c: _meaning_reset_flags(c, [column], content['english_name'])) if was and was['state'] == 'confirmed' else None)
    _refresh_view_reasons(conn, content['english_name'], column)
    return {'changed': True}


def _refresh_view_reasons(conn, english_name: str, column: str) -> None:
    from ontology_poc_generator.object_views import refresh_new_value_reasons   # object_views reads this module
    refresh_new_value_reasons(conn, english_name, column)


# --- checks: now, and again when the data moves ---------------------------------------------------------------------------------------------------

def _type_problems(conn, content: dict) -> tuple[list[str], int | None]:
    """(what is wrong now, the id of the key check that ran) for a type, read from the current version of its dataset."""
    dataset = current_dataset(conn, content['dataset'])
    if dataset is None:
        return [tr(f'数据集“{content["dataset"]}”已经不在了', f'The dataset "{content["dataset"]}" is gone')], None
    cols = dataset_columns(conn, dataset['id'])
    gone = [p['column'] for p in content['properties'] if p['column'] not in cols]
    if gone:
        return [tr(f'{dataset["name"]} 第 {dataset["version"]} 版里没有这些列了：{tr("、", ", ").join(gone)}', f'{dataset["name"]} version {dataset["version"]} no longer has these columns: {", ".join(gone)}')], None
    problems = [tr(f'“{p["column"]}”现在的内容是{TYPE_NAME[cols[p["column"]]["type"]]}，装不进{TYPE_NAME[p["type"]]}', f'"{p["column"]}" now holds {TYPE_NAME[cols[p["column"]]["type"]]} values, which do not fit {TYPE_NAME[p["type"]]}')
                for p in content['properties'] if p['type'] not in FITS[cols[p['column']]['type']]]
    key_check = check_key(conn, dataset['id'], content['key'])
    if key_check['status'] != 'passed':
        problems.append(tr(f'主键“{" + ".join(content["key"])}”现在不唯一或有空值：{_key_failure(conn, key_check)[0]}', f'The key "{" + ".join(content["key"])}" is no longer unique or has empty values: {_key_failure(conn, key_check)[0]}'))
    return problems, key_check['id']


def _new_codes(conn, row: dict) -> dict[str, int]:
    """{value: rows} of the values a code column has now that it did not have when its meanings were confirmed."""
    content, was = _content(row), json.loads(row['anchors_json'])['counts']
    dataset = current_dataset(conn, content['dataset'])
    col = (dataset_columns(conn, dataset['id']) if dataset else {}).get(content['column'])
    now = col['counts'] if col and col['counts'] is not None else {}
    return {v: now[v] for v in _by_value(set(now) - set(was))}


def _new_value_question(conn, view: dict, moved: list[str]) -> str | None:
    """The reason a view needs another look when a code its conditions read has a new value: the question that has to be answered, and what the view does with it now
    (a condition "is not" lets it in, "is" keeps it out). None when no code its conditions name got a new value in this pass."""
    from ontology_poc_generator.object_views import in_out_text   # object_views reads this module
    content = _content(view)
    said = []
    for f in content['filters']:
        meanings = element_row(conn, enum_id(content['type'], f['column']))
        new = _new_codes(conn, meanings) if meanings and meanings['element_id'] in moved and meanings['anchors_json'] else {}
        if new:
            values = tr('、', ', ').join(new)
            default = tr('会算进来' if f['op'] == 'is_not' else '不会算进来', 'they are counted' if f['op'] == 'is_not' else 'they are left out')
            said.append(tr(f'它用的{_label(conn, meanings["element_id"])}需要再看（原因见那一组含义）。“{f["column"]}”出现了新值 {tr("、", ", ").join(f"{v}（{n} 行）" for v, n in new.items())}：新值 {values} 算不算进来？', f'It uses {_label(conn, meanings["element_id"])}, which needs review (see the reason on that set of meanings). "{f["column"]}" has new values {", ".join(f"{v} ({n} rows)" for v, n in new.items())}: should the new values {values} be counted? ') +
                        tr(f'按现在的写法（{in_out_text(conn, content)}），{"它们" if len(new) > 1 else "它"}{default}。请先给新值写含义，再决定', f'As it is written now ({in_out_text(conn, content)}), {default}. Write meanings for the new values first, then decide'))
    return tr('；', '; ').join(said) or None


def _enum_problems(conn, row: dict) -> list[str]:
    """What moved in the values of a code column since its meanings were confirmed: a value the data has now that was not there, or a value with a
    meaning that is not there any more."""
    content, was = _content(row), json.loads(row['anchors_json'])['counts']
    dataset = current_dataset(conn, content['dataset'])
    col = (dataset_columns(conn, dataset['id']) if dataset else {}).get(content['column'])
    if col is None or col['counts'] is None:
        return [tr(f'“{content["column"]}”现在不再是一列只有几个取值的代码列', f'"{content["column"]}" is no longer a code column with only a few values')]
    now = col['counts']
    labels = {e['value']: e['label'] for e in content['values']}
    new = [tr(f'{v}（{now[v]} 行，没有含义）', f'{v} ({now[v]} rows, no meaning)') for v in _by_value(set(now) - set(was))]
    gone = [tr(f'{v}（原来是「{labels[v]}」）', f'{v} (was "{labels[v]}")') for v in _by_value(set(was) - set(now)) if v in labels]
    if not new and not gone:
        return []
    said = [*([tr(f'新出现 {tr("、", ", ").join(new)}', f'new: {", ".join(new)}')] if new else []), *([tr(f'不再出现 {tr("、", ", ").join(gone)}', f'gone: {", ".join(gone)}')] if gone else [])]
    return [tr(f'{dataset["name"]} 第 {dataset["version"]} 版（{dataset["who"] or "未署名"}上传）里，“{content["column"]}”的取值变了：{tr("；", "; ").join(said)}。确认时的取值是 {tr("、", ", ").join(_by_value(was))}', f'In {dataset["name"]} version {dataset["version"]} (uploaded by {dataset["who"] or "unsigned"}) the values of "{content["column"]}" changed: {"; ".join(said)}. The values when it was confirmed: {", ".join(_by_value(was))}')]


def _label(conn, element_id: str) -> str:
    content = _content(element_row(conn, element_id))
    return (tr(f'“{content["name"]}”类型', f'the type "{content["name"]}"') if element_id.startswith(TYPE_PREFIX) else tr(f'“{content["name"]}”关系', f'the relation "{content["name"]}"') if element_id.startswith(RELATION_PREFIX)
            else tr(f'“{content["name"]}”视图', f'the view "{content["name"]}"') if element_id.startswith(VIEW_PREFIX) else tr(f'“{content["name"]}”行为', f'the action "{content["name"]}"') if element_id.startswith(ACTION_PREFIX)
            else tr(f'“{content["name"]}”管道', f'the pipeline "{content["name"]}"') if element_id.startswith(PIPELINE_PREFIX) else tr(f'“{content["name"]}”派生属性', f'the derived property "{content["name"]}"') if element_id.startswith(DERIVED_PREFIX)
            else tr(f'“{content["column"]}”的含义', f'the meanings of "{content["column"]}"'))


CAUSE_WORDS = TrMap({'data': ('数据变了', 'Data changed'), 'definition': ('定义改了', 'Definition changed')})   # why something needs another look: what changed at the root
VIA_WORDS = TrMap({'parent': ('上一步过时', 'Upstream'), 'ancestor': ('更上游过时', 'Far upstream')})   # and how far away that root is: its direct parent, or further up


def stale_word(cause: str | None, via: str | None) -> str | None:
    """The one of the four words a needs-another-look element shows: 数据变了 or 定义改了 when the change is at its own input or logic, 上一步过时 when its direct
    parent is out of date, 更上游过时 when an ancestor is."""
    return VIA_WORDS.get(via) or CAUSE_WORDS.get(cause)


_MOVES = contextvars.ContextVar('ontopoc_moves', default=None)   # what has gone back to needs_look in the operation running now (one_telling)


@contextlib.contextmanager
def one_telling(conn):
    """One operation (an upload of several files, a pull, a scheduled run, a pipeline run, an edit): everything _flag sends back to needs_look inside it is told once,
    when the outermost of these ends and its writes are done, so each person gets one notice for the whole of it. One inside another adds to the outer one."""
    if _MOVES.get() is not None:
        yield
        return
    token = _MOVES.set([])
    try:
        yield
    finally:
        moved = _MOVES.get()
        _MOVES.reset(token)
        tell_safely(conn, moved)


def tell_safely(conn, moved: list[str]) -> None:
    """Tell who can confirm what moved (notices.tell_moved), only what still needs another look now (a write rolled back took its move with it). Telling never
    undoes or stops the move: the notices are written under a savepoint of their own, and when writing them fails they are dropped and the service's log says so."""
    outside = not conn.in_transaction   # after the operation's own writes: the savepoint is the whole transaction
    try:
        wanted = [e for e in dict.fromkeys(moved) if (r := element_row(conn, e)) is not None and r['state'] == 'needs_look']
        if not wanted:
            return
        from ontology_poc_generator.notices import tell_moved   # notices reads this module: imported here, where it is used
        conn.execute('SAVEPOINT tell_moved')
        try:
            tell_moved(conn, wanted)
        except BaseException:
            conn.execute('ROLLBACK TO tell_moved')
            conn.execute('RELEASE tell_moved')
            raise
        conn.execute('RELEASE tell_moved')
    except Exception as exc:
        if outside and conn.in_transaction:   # never leave a transaction of ours open behind the operation
            with contextlib.suppress(Exception):
                conn.execute('ROLLBACK')
        print(f'notices of definitions that went back were not written: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)


def _flag_readers(conn, element_id: str, reason: str, moved: list[str], cause: str = 'definition') -> None:
    """What reads this element and is confirmed goes to needs_look with the reason (and so on to what reads it): used when the element itself stopped being
    confirmed (its definition was edited). Inside the caller's transaction, so it is written together with what stopped the confirmation. The readers' cause is
    the edit (定义改了) and their parent is out of date."""
    for (reader,) in conn.execute('SELECT element_id FROM element_dep WHERE depends_on = ?', (element_id,)).fetchall():
        _flag(conn, reader, reason, None, moved, cause, 'parent')


def _flag(conn, element_id: str, reason: str, caused_by: str | None, moved: list[str], cause: str = 'data', via: str = 'self', top: bool = True) -> None:
    """A confirmed element whose check came out different goes to needs_look with the reason; then the same for what reads it, with its own reason. `cause` is
    what changed at the root (data or definition) and stays the same all the way down; `via` is self for the element whose own input or logic changed, parent
    for what reads it directly, ancestor for the rest. The dataset a pipeline writes is not an element: it passes the flag on to what reads it. Who can confirm
    what moved, and who confirmed it last, are told (tell_safely): inside an operation (one_telling) the move is added to it and told once at its end; outside
    one, a top call tells its own move (`top` is false for the calls this one makes down the line)."""
    row = element_row(conn, element_id)
    if row is None and element_id.startswith('dataset:'):
        for (reader,) in conn.execute('SELECT element_id FROM element_dep WHERE depends_on = ?', (element_id,)).fetchall():
            _flag(conn, reader, reason, caused_by, moved, cause, via, top)
        return
    if row is None or row['state'] != 'confirmed':
        return
    start = len(moved)
    reason = (_new_value_question(conn, row, moved) if element_id.startswith(VIEW_PREFIX) else None) or reason
    conn.execute("UPDATE element_state SET state = 'needs_look', reason = ?, cause = ?, via = ?, version = version + 1 WHERE element_id = ?", (reason, cause, via, element_id))
    log_line(conn, 'system', element_id, 'needs_look',
             before={'state': 'confirmed', 'confirmed_by': row['confirmed_by'], 'confirmed_at': row['confirmed_at']},
             after={'state': 'needs_look', 'reason': reason, 'caused_by': caused_by, 'cause': cause, 'via': via}, user_id=None)
    moved.append(element_id)
    pending = _MOVES.get()
    if pending is not None:
        pending.append(element_id)
    for (reader,) in conn.execute('SELECT element_id FROM element_dep WHERE depends_on = ?', (element_id,)).fetchall():
        _flag(conn, reader, tr(f'它用的{_label(conn, element_id)}需要再看（原因见{"那一组含义" if element_id.startswith(ENUM_PREFIX) else "那条管道" if element_id.startswith(PIPELINE_PREFIX) else "那个对象类型"}）', f'It uses {_label(conn, element_id)}, which needs review (see the reason on {"that set of meanings" if element_id.startswith(ENUM_PREFIX) else "that pipeline" if element_id.startswith(PIPELINE_PREFIX) else "that object type"})'),
              caused_by, moved, cause, 'parent' if via == 'self' else 'ancestor', False)
    if top and pending is None:
        tell_safely(conn, moved[start:])


def _readers_of_dataset(conn, dataset_name: str) -> set[str]:
    """The elements that read this dataset: what says so in element_dep, and the relations whose two types read it now (a type may have been pointed at
    another dataset since the relation was saved, so a relation's own list is not trusted)."""
    column_prefix = f'column:{dataset_name}.'
    readers = {r[0] for r in conn.execute('SELECT DISTINCT element_id FROM element_dep WHERE depends_on = ? OR substr(depends_on, 1, ?) = ?',
                                          (f'dataset:{dataset_name}', len(column_prefix), column_prefix))}
    for element_id, content in conn.execute("SELECT element_id, content_json FROM element_state WHERE element_id LIKE 'relation:%'").fetchall():
        ends = json.loads(content)
        if any((r := element_row(conn, type_id(ends[e]))) and _content(r)['dataset'] == dataset_name for e in ('from', 'to')):
            readers.add(element_id)
    return readers


def flag_dataset_readers(conn, dataset_name: str, reason: str, caused_by: str | None = None) -> list[str]:
    """Every confirmed element that reads this dataset goes to needs_look with the reason: for when the checks could not be run, so nobody can say they still hold."""
    moved: list[str] = []
    conn.execute('BEGIN IMMEDIATE')
    try:
        for element_id in sorted(_readers_of_dataset(conn, dataset_name)):
            _flag(conn, element_id, reason, caused_by, moved, 'data')
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return moved


def recheck_dependents(conn, dataset_name: str, caused_by: str | None = None) -> list[str]:
    """The dataset has a new current version: run the checks behind every confirmed element that reads it again. One whose result changed is moved to
    needs_look with the reason, together with what reads it. Returns the ids of the elements that moved."""
    readers = _readers_of_dataset(conn, dataset_name)
    moved: list[str] = []
    from ontology_poc_generator.object_relations import relation_problems   # object_relations and object_views read this module: imported here, where they are used
    from ontology_poc_generator.derived_properties import derived_problems
    from ontology_poc_generator.object_views import view_problems
    from ontology_poc_generator.workspace_pipelines import pipeline_problems
    order = lambda e: (0 if e.startswith(ENUM_PREFIX) else 2 if e.startswith((RELATION_PREFIX, VIEW_PREFIX, DERIVED_PREFIX)) else 1, e)   # meanings, then types and pipelines (which move with their meanings), then relations, views and derived properties (which move with their types and relations)
    conn.execute('BEGIN IMMEDIATE')
    try:
        for element_id in sorted(readers, key=order):
            row = element_row(conn, element_id)
            if row is None or row['state'] != 'confirmed':
                continue
            problems = (_enum_problems(conn, row) if element_id.startswith(ENUM_PREFIX) else relation_problems(conn, row) if element_id.startswith(RELATION_PREFIX)
                        else view_problems(conn, row) if element_id.startswith(VIEW_PREFIX) else pipeline_problems(conn, row) if element_id.startswith(PIPELINE_PREFIX)
                        else derived_problems(conn, row) if element_id.startswith(DERIVED_PREFIX)
                        else _type_problems(conn, _content(row))[0])
            if problems:
                _flag(conn, element_id, tr('；', '; ').join(problems), caused_by, moved, 'data')
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return moved


def recheck_after_write(conn, name: str, signer: str) -> str | None:
    """What was confirmed on the version before is checked against the new one (an upload, or an approved action). When the check itself fails, nothing can be said
    to still hold: everything confirmed that reads the dataset goes to needs_look saying so, and the error is returned for the answer, so a new version is never
    live with its readers silently left confirmed. Who can confirm what moved is told once, at the end (one_telling)."""
    with one_telling(conn):
        try:
            recheck_dependents(conn, name, signer)
        except Exception as exc:   # whatever went wrong, the readers are flagged and the person is told
            flag_dataset_readers(conn, name, tr(f'“{name}”有了新版本，重新检查出了错（{exc}），没法确认它还成立，请再看一遍', f'"{name}" has a new version and the re-check failed ({exc}), so it cannot be confirmed to still hold. Please look again'), signer)
            return str(exc)
        return None


def dataset_readers_of(conn, name: str, user: dict | None = None, everyone: bool = True) -> list[dict]:
    """The object types and pipelines that read this dataset: all of them for the delete guard (everyone), only the ones this person may see for the "used by"
    shown on a page (the types they may see; the pipelines, unless they are a viewer: a pipeline is a builder's)."""
    readers = [{'kind': '对象类型', 'name': json.loads(content)['name']} for element_id, content in conn.execute(
        "SELECT s.element_id, s.content_json FROM element_dep d JOIN element_state s ON s.element_id = d.element_id "
        "WHERE d.depends_on = ? AND d.element_id LIKE 'objtype:%' ORDER BY d.element_id", (f'dataset:{name}',))
        if everyone or _visible(conn, element_row(conn, element_id), user)]
    if everyone or user is None or user['role'] != 'viewer':
        readers += [{'kind': '管道', 'name': json.loads(content)['name']} for content, in conn.execute(
            "SELECT s.content_json FROM element_dep d JOIN element_state s ON s.element_id = d.element_id "
            "WHERE d.depends_on = ? AND d.element_id LIKE 'pipeline:%' ORDER BY d.element_id", (f'dataset:{name}',))]
    return readers


# --- confirming ---------------------------------------------------------------------------------------------------------------------------------

def _enum_now_problems(conn, content: dict) -> list[str]:
    dataset = current_dataset(conn, content['dataset'])
    if dataset is None:
        return [tr(f'数据集“{content["dataset"]}”已经不在了', f'The dataset "{content["dataset"]}" is gone')]
    col = dataset_columns(conn, dataset['id']).get(content['column'])
    if col is None or col['counts'] is None:
        return [tr(f'“{content["column"]}”现在不再是一列只有几个取值的代码列', f'"{content["column"]}" is no longer a code column with only a few values')]
    return [tr(f'含义里的取值 {e["value"]} 现在的数据里没有', f'The value {e["value"]} in the meanings is not in the data now') for e in content['values'] if e['value'] not in col['counts']]


def seen_of_type(dataset: dict | None) -> dict | None:
    """What a person reads of a type's data on its page, which confirming has to quote: the dataset version and how many objects (rows) it has."""
    return {'dataset_version': dataset['version'], 'rows': dataset['rows_stored']} if dataset else None


def seen_of_meaning(dataset: dict | None, col: dict | None) -> dict | None:
    """What a person reads of a set of meanings: the dataset version and the rows of each value."""
    return {'dataset_version': dataset['version'], 'counts': dict(col['counts'] or {})} if dataset and col else None


def unconfirmed_producers(conn, dataset_name: str) -> list[str]:
    """The names of the pipelines that write this dataset and are not confirmed: a type built on their output cannot be confirmed before they are."""
    return [json.loads(content)['name'] for (content,) in conn.execute(
        "SELECT s.content_json FROM element_dep d JOIN element_state s ON s.element_id = d.depends_on "
        "WHERE d.element_id = ? AND d.depends_on LIKE 'pipeline:%' AND s.state != 'confirmed' ORDER BY d.depends_on", (f'dataset:{dataset_name}',))]


def _unconfirmed_meanings(conn, element_id: str) -> list[str]:
    """The code columns of this type whose meanings are not confirmed (in any state but confirmed)."""
    return [depends_on[len(ENUM_PREFIX):].partition(':')[2] for (depends_on,) in conn.execute(
        "SELECT d.depends_on FROM element_dep d JOIN element_state s ON s.element_id = d.depends_on "
        "WHERE d.element_id = ? AND d.depends_on LIKE 'enum:%' AND s.state != 'confirmed' ORDER BY d.depends_on", (element_id,))]


def confirm_element(conn, payload: dict, who: str | None, user: dict | None = None) -> dict:
    """{id: the type, column?: a code column (confirms its meanings; without it the type itself), version, seen}: confirm what the person has looked at. A
    builder other than the one who put it forward (SelfConfirmation otherwise), and only the version they saw (409 when it has changed). `seen` is what the
    page showed of the data (seen_of_type, seen_of_meaning): when the data moved after they looked, 409. The checks run again on the data as it is now and
    the snapshot of what was confirmed (definition, evidence, dataset versions) is kept. A type is confirmed only once all its meanings are (409 saying
    which); a type that needs another look can be confirmed once they are; meanings that need another look are put forward again instead."""
    row = _type_row(conn, payload.get('id'), user)
    if payload.get('column') is not None:
        row = element_row(conn, enum_id(row['element_id'][len(TYPE_PREFIX):], str(payload.get('column'))))
        if row is None:
            raise TypeRefused(tr('这一列还没有人提出含义', 'Nobody has put forward meanings for this column yet'), 404)
    refuse_if_limited(conn, row, user)
    if payload.get('version') != row['version']:
        raise TypeRefused(tr('确认要带上你看到的那一版；它在你看过之后被改了，请刷新后重新看一遍', 'Confirming needs the version you saw; it was changed after you looked, so refresh and look again'), 409)
    element_id, content, is_type = row['element_id'], _content(row), row['element_id'].startswith(TYPE_PREFIX)
    if row['state'] == 'confirmed':
        raise TypeRefused(tr('已经确认过了', 'Already confirmed'), 409)
    if row['state'] == 'rejected':
        raise TypeRefused(tr('已经被退回了：要先按退回的理由改，再重新提出', 'It was sent back: change it as the reason says, then put it forward again'), 409)
    if row['state'] == 'needs_look' and not is_type:
        raise TypeRefused(tr('这组含义需要再看：请按现在的数据重新提出含义，由另一位确认', 'These meanings need review: put them forward again on the current data, for someone else to confirm'), 409)
    seen = payload.get('seen')
    if not isinstance(seen, dict):
        raise TypeRefused(tr('确认要带上你看到的数据版本和行数（seen）', 'Confirming needs the data version and row count you saw (seen)'))
    dataset = current_dataset(conn, content['dataset'])
    if is_type:
        refuse_ai_columns(conn, content['dataset'], content['key'], tr('主键', 'a key'))
        problems, check_id = _type_problems(conn, content)
        waiting = _unconfirmed_meanings(conn, element_id)
        if waiting:
            raise TypeRefused(tr(f'它的{tr("、", ", ").join(f"“{c}”" for c in waiting)}的含义还没有确认，要先确认含义', f'The meanings of {", ".join(waiting)} are not confirmed yet. Confirm the meanings first'), 409)
        unsettled = unconfirmed_producers(conn, content['dataset'])
        if unsettled:
            raise TypeRefused(tr(f'“{content["dataset"]}”是管道{tr("、", ", ").join(f"“{n}”" for n in unsettled)}写出来的数据，管道还没有确认，要先确认管道', f'"{content["dataset"]}" is data written by the pipeline {", ".join(unsettled)}, which is not confirmed yet. Confirm the pipeline first'), 409)
        anchors = {'dataset': dataset['name'], 'version': dataset['version']} if dataset else None
        evidence = f'check_result:{check_id},dataset:{dataset["name"]}@v{dataset["version"]}' if check_id else row['evidence_ref']
        now = seen_of_type(dataset)
    else:
        refuse_ai_columns(conn, content['dataset'], [content['column']], tr('已确认的代码含义', 'a confirmed code meaning'))
        problems = _enum_now_problems(conn, content)
        col = dataset_columns(conn, dataset['id']).get(content['column']) if dataset else None
        anchors = {'dataset': dataset['name'], 'version': dataset['version'], 'counts': col['counts']} if not problems else None
        evidence = f'dataset:{dataset["name"]}@v{dataset["version"]}' if dataset else None
        now = seen_of_meaning(dataset, col)
    if problems:
        raise TypeRefused(tr(f'按现在的数据过不了检查，不能确认：{tr("；", "; ").join(problems)}', f'It fails the checks on the current data and cannot be confirmed: {"; ".join(problems)}'), 409)
    if seen != now:
        raise TypeRefused(tr(f'数据在你看过之后变了：{dataset["name"]} 现在是第 {dataset["version"]} 版，和你看到的不一样，请刷新后重新看一遍', f'The data changed after you looked: {dataset["name"]} is now version {dataset["version"]}, not what you saw. Refresh and look again'), 409)
    write_confirmation(conn, element_id, content, evidence, who, anchors, {dataset['name']: dataset['version']}, row['version'])
    if not is_type:
        _refresh_view_reasons(conn, element_id[len(ENUM_PREFIX):].partition(':')[0], content['column'])
    return {'state': 'confirmed'}


def write_confirmation(conn, element_id: str, content: dict, evidence: str | None, who: str | None, anchors: dict | None, dataset_versions: dict,
                       version: int | None = None, reads: list[str] | None = None, snapshot: dict | None = None) -> None:
    """The element becomes confirmed by this person and the snapshot of what they confirmed (definition, evidence, dataset versions) is kept with it;
    all or nothing. SelfConfirmation when it is their own proposal while two-person confirmation is active. `version`: the one the person read, 409 when the
    row has moved since; `reads`: what the element reads now, written with it; `snapshot`: more evidence kept with the confirmation (a pipeline's statistics)."""
    try:
        with element_state_writes(conn, [(element_id, 'confirmed', evidence, who, content, anchors, None)], None if version is None else {element_id: version}) as rows:
            kept = rows[element_id]
            conn.execute('INSERT INTO confirmation(element_id, confirmed_by, confirmed_by_user_id, proposed_by, confirmed_at, content_json, evidence_ref, dataset_versions_json, self_confirmed, snapshot_json)'
                         ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                         (element_id, kept['confirmed_by'], kept['confirmed_by_user_id'], kept['proposed_by'], kept['confirmed_at'], kept['content_json'], kept['evidence_ref'],
                          json.dumps(dataset_versions, ensure_ascii=False),
                          int(kept['confirmed_by_user_id'] is not None and kept['confirmed_by_user_id'] == kept['proposed_by_user_id']),
                          None if snapshot is None else json.dumps(snapshot, ensure_ascii=False)))
            if reads is not None:
                _set_deps(conn, element_id, reads)
    except StaleElement:
        raise TypeRefused(stale_note(), 409) from None


# --- what the pages read ------------------------------------------------------------------------------------------------------------------------

def _types_read(row: dict) -> list[str]:
    """The ids of the object types an element is about (a type: itself; a relation: its two ends; a meaning, view or action: its type; a derived property: its
    type and every type its path reaches)."""
    content = _content(row) if row['content_json'] else {}
    if row['element_id'].startswith(DERIVED_PREFIX):
        return [type_id(t) for t in content['types']]
    return ([type_id(content[e]) for e in ('from', 'to')] if row['element_id'].startswith(RELATION_PREFIX) else [type_id(content['type'])] if row['element_id'].startswith((ENUM_PREFIX, VIEW_PREFIX, ACTION_PREFIX))
            else [row['element_id']])


def limited_on(conn, row: dict, person: dict | None) -> bool:
    """Whether a row rule limits this person to some of the rows of what the element is about: they do not see all the data, and what confirming a type, its
    meanings, a view or a relation quotes (counts of the whole data) is not theirs to read. An action's definition quotes no counts."""
    return not row['element_id'].startswith(ACTION_PREFIX) and any(restriction(conn, t, person) is not None or hidden_columns(conn, t, person) for t in _types_read(row))   # a column kept from them: not all the data either


def hidden_reason() -> str:
    return tr('原因里有全部数据的统计，你受行规则限制，看不到', 'The reason has statistics over all the data, which a row rule keeps you from seeing')


def reason_for(conn, row: dict, user: dict | None) -> tuple[str | None, str | None]:
    """(the reason an element needs another look or was sent back, as this person may read it; the words that stand in its place). The reason a changed dataset sends an element
    back for quotes counts of the whole data, which a person a row rule limits does not read: they see the cause word without the numbers."""
    if row['state'] not in ('needs_look', 'rejected'):
        return None, None
    if row['state'] == 'needs_look' and row['reason'] and limited_on(conn, row, user):
        return None, hidden_reason()
    return (_settled_since(conn, row) if row['state'] == 'needs_look' and row['reason'] else row['reason']), None


def _settled_since(conn, row: dict) -> str:
    """The reason as it reads now: each "它用的X需要再看（原因见…）" the store wrote when X went to needs_look says, once X has been confirmed again, who confirmed it
    and that this element still waits for its own confirmation. Only the words read on the pages change; the stored reason, the log and the graph's cause
    (which reads the stored sentence) stay as written."""
    reason = row['reason']
    reader = current()
    for (parent,) in conn.execute('SELECT depends_on FROM element_dep WHERE element_id = ? ORDER BY depends_on', (row['element_id'],)).fetchall():
        if not ((held := element_row(conn, parent)) and held['state'] == 'confirmed'):
            continue
        for written in ('zh', 'en'):   # the reason was stored in the language of whoever wrote it
            with speaking(written):
                said = tr(f'它用的{_label(conn, parent)}需要再看', f'It uses {_label(conn, parent)}, which needs review')
                tail = tr(r'(（原因见[^）]*）)?', r'( \(see the reason on [^)]*\))?')
            if said in reason:
                who = conn.execute('SELECT confirmed_by FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 1', (parent,)).fetchone()
                with speaking(reader):
                    now = tr(f'它用的{_label(conn, parent)}已经由 {who[0] if who and who[0] else "另一位"} 重新确认，这一项还要再确认一次',
                             f'It uses {_label(conn, parent)}, which {who[0] if who and who[0] else "someone else"} has confirmed again; this one still needs its own confirmation')
                reason = re.sub(re.escape(said) + tail, lambda _: now, reason)   # a function: names are text, not a replacement pattern
    return reason


def refuse_if_limited(conn, row: dict, user: dict | None) -> None:
    if limited_on(conn, row, user):
        raise TypeRefused(tr('你受行规则或列的限制，看不到全部数据：确认要对着全部数据看过才行，请让不受限制的建设者来确认', 'A row rule or a column limit keeps you from seeing all the data. Confirming needs a look at all of it, so ask a builder without the limit'), 403)


def confirmer_people(conn, row: dict) -> list[tuple[int, str]]:
    """(id, name) of the builders who may confirm it: not the one who put it forward while two-person is active, and only people who may see what it is about,
    and all of its data."""
    excluded = row['proposed_by_user_id'] if two_person(conn)['active'] else None
    types = _types_read(row)
    return [(person, name) for person, name, role in conn.execute(
        "SELECT id, display_name, role FROM user WHERE disabled = 0 AND role IN ('builder', 'admin') AND (? IS NULL OR id != ?) ORDER BY display_name", (excluded, excluded))
        if all(can_access(conn, t, {'id': person, 'role': role}) for t in types) and not limited_on(conn, row, {'id': person, 'role': role})]


def _confirmers(conn, row: dict, user: dict | None) -> tuple[bool, list[str]]:
    """(whether this person may confirm it now, the builders who may). A viewer never; the one who put it forward not while two-person is active."""
    excluded = row['proposed_by_user_id'] if two_person(conn)['active'] else None
    others = [name for _, name in confirmer_people(conn, row)]
    if user is not None and user['role'] == 'viewer':
        return False, others
    return not (excluded is not None and user is not None and user['id'] == excluded), others


def _state_view(conn, row: dict, user: dict | None) -> dict:
    """The state of one element for a page: who put it forward, whether this person may confirm it, who could, the last confirmation, the reason it needs a look."""
    waiting = row['state'] in WAITING or (row['state'] == 'needs_look' and row['element_id'].startswith((TYPE_PREFIX, RELATION_PREFIX, VIEW_PREFIX, ACTION_PREFIX, PIPELINE_PREFIX, DERIVED_PREFIX)))
    can, others = _confirmers(conn, row, user)
    meanings = _unconfirmed_meanings(conn, row['element_id']) if row['element_id'].startswith(TYPE_PREFIX) and waiting else []   # a type waits for its meanings first
    producers = unconfirmed_producers(conn, _content(row)['dataset']) if row['element_id'].startswith(TYPE_PREFIX) and waiting else []   # and for the pipeline that writes its data
    blocked = meanings or producers or (row['state'] == 'needs_look' and conn.execute(
        "SELECT 1 FROM element_dep d JOIN element_state s ON s.element_id = d.depends_on WHERE d.element_id = ? AND s.state = 'needs_look'", (row['element_id'],)).fetchone())
    last = conn.execute('SELECT confirmed_by, confirmed_at, dataset_versions_json, evidence_ref FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 1',
                        (row['element_id'],)).fetchone()
    limited = limited_on(conn, row, user)
    reason, reason_hidden = reason_for(conn, row, user)
    return {'state': row['state'], 'version': row['version'], 'proposed_by': row['proposed_by'], 'drafted': _content(row).get('drafted'), 'reason': reason, 'reason_hidden': reason_hidden,
            'model_draft': row['state'] == 'proposed' and row['proposed_by'] is None, 'can_confirm': waiting and can and not blocked and not limited, 'limited_by_rule': limited,
            'cause': row['cause'] if row['state'] == 'needs_look' else None, 'via': row['via'] if row['state'] == 'needs_look' else None,
            'stale_word': stale_word(row['cause'], row['via']) if row['state'] == 'needs_look' else None,
            'cause_word': CAUSE_WORDS.get(row['cause']) if row['state'] == 'needs_look' else None, 'pipelines_blocking': producers,
            'confirmers': others if waiting and not blocked else [],
            'meanings_blocking': [c for c in meanings if c not in kept] if meanings and (kept := hidden_columns(conn, row['element_id'], user)) else meanings,   # a column kept from them is not named
            'confirmed_by': last[0] if last else None, 'confirmed_at': last[1] if last else None,
            'confirmed_on': json.loads(last[2]) if last else None, 'evidence': last[3] if last else None, 'written_at': row['confirmed_at']}


def _visible(conn, row: dict, user: dict | None) -> bool:
    """A type nobody confirmed is for builders; a type with a list of people is for them (and admins) only (type_access)."""
    if user is not None and user['role'] == 'viewer' and row['state'] != 'confirmed':
        return False
    return can_access(conn, row['element_id'], user)


def was_confirmed(conn, element_id: str) -> bool:
    return conn.execute('SELECT 1 FROM confirmation WHERE element_id = ?', (element_id,)).fetchone() is not None


def waiting_for_viewer(conn, row: dict | None, user: dict | None) -> bool:
    """A type a viewer is allowed to see that was confirmed once and now needs another look: it is not closed to them, it waits for a confirmer. They are shown
    that it waits and nothing of its definition or data (a type nobody ever confirmed, or one a list of people leaves them out of, is not this)."""
    return (row is not None and user is not None and user['role'] == 'viewer' and row['state'] == 'needs_look' and row['element_id'].startswith(TYPE_PREFIX)
            and can_access(conn, row['element_id'], user) and was_confirmed(conn, row['element_id']))


def waiting_for(conn, row: dict, user: dict | None) -> list[str]:
    """The builders who could confirm it again, by name."""
    return _confirmers(conn, row, user)[1]


def _waiting_line(conn, row: dict, user: dict | None) -> dict:
    """What a viewer is told of a type that waits: its name and who it waits for, no counts, no dataset, no reason (it quotes the data)."""
    content = _content(row)
    return {'id': content['english_name'], 'name': content['name'], 'state': 'needs_look', 'waiting': True, 'waiting_for': waiting_for(conn, row, user)}


def visible_rows(conn, row: dict, dataset: dict, user: dict | None) -> int:
    """How many rows of the type this person sees: all of the dataset's, or the ones a row rule that names them keeps (row_rules)."""
    limit = restriction(conn, row['element_id'], user)
    return dataset['rows_stored'] if limit is None else len(positions(dataset_records(conn, dataset), limit))


def list_types(conn, user: dict | None) -> list[dict]:
    """Every object type as the list shows it, by English name. A viewer sees only the confirmed ones."""
    out = []
    for element_id, in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objtype:%' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        if waiting_for_viewer(conn, row, user):
            out.append({**_waiting_line(conn, row, user), 'dataset': None, 'dataset_version': None, 'rows': None, 'meanings_waiting': 0})
            continue
        if not _visible(conn, row, user):
            continue
        content = _content(row)
        dataset = current_dataset(conn, content['dataset'])
        waiting = conn.execute("SELECT COUNT(*) FROM element_dep d JOIN element_state s ON s.element_id = d.depends_on WHERE d.element_id = ? AND d.depends_on LIKE 'enum:%' "
                               "AND s.state != 'confirmed'", (element_id,)).fetchone()[0]
        out.append({'id': content['english_name'], 'name': content['name'], 'dataset': content['dataset'], 'dataset_version': dataset['version'] if dataset else None,
                    'rows': visible_rows(conn, row, dataset, user) if dataset else None, 'meanings_waiting': waiting, **_state_view(conn, row, user)})
    return out


def hidden_type_count(conn, user: dict | None) -> int:
    """How many types exist that this person cannot open because a list of people leaves them out (a draft a viewer may not see yet is not counted: it is not out yet;
    one that was confirmed and now needs a look is, since it was theirs to see). Only the number: the names are the list's own business."""
    return sum(1 for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objtype:%'").fetchall()
               if not can_access(conn, element_id, user)
               and not (user is not None and user['role'] == 'viewer' and element_row(conn, element_id)['state'] != 'confirmed' and not was_confirmed(conn, element_id)))


def _meaning_view(conn, content: dict, prop: dict, cols: dict, dataset: dict | None, user: dict | None) -> dict:
    """One code column: its values as the data has them now beside the meanings on file and the rows each had when they were confirmed, and the state."""
    row = element_row(conn, enum_id(content['english_name'], prop['column']))
    now = (cols.get(prop['column']) or {}).get('counts') or {}
    labels = {e['value']: e for e in (_content(row)['values'] if row and row['content_json'] else [])}
    was = json.loads(row['anchors_json'])['counts'] if row and row['anchors_json'] else {}
    limited = restriction(conn, type_id(content['english_name']), user) is not None
    if limited:   # no per-value counts and no list of the values the whole data holds: only the meanings on file
        values = [{'value': v, 'label': labels[v]['label'], 'description': labels[v]['description'], 'rows': None, 'rows_at_confirmation': None, 'in_data': True} for v in _by_value(labels)]
    else:
        values = [{'value': v, 'label': labels[v]['label'] if v in labels else '', 'description': labels[v]['description'] if v in labels else '',
                   'rows': now.get(v), 'rows_at_confirmation': was.get(v), 'in_data': v in now} for v in _by_value({*now, *labels})]
    return {'column': prop['column'], 'values': values, 'seen': None if limited else seen_of_meaning(dataset, cols.get(prop['column'])),
            **({'limited_note': limited_note()} if limited else {}), **(_state_view(conn, row, user) if row else {'state': None, 'can_confirm': False})}


def type_page(conn, english_name: str, user: dict | None) -> dict:
    """What the type's page is sent: a viewer's waiting type says so and nothing more; everything else is type_detail. (The objects, log, views and the rest keep
    asking type_detail, which refuses a type a viewer may not read.)"""
    row = element_row(conn, type_id(str(english_name)))
    return _waiting_line(conn, row, user) if waiting_for_viewer(conn, row, user) else type_detail(conn, english_name, user)


def type_detail(conn, english_name: str, user: dict | None) -> dict:
    row = _type_row(conn, english_name, user)
    content = _content(row)
    hidden = hidden_columns(conn, row['element_id'], user)   # kept from this person: for them the type has no such property, and the dataset's list leaves it out
    content = {**content, 'properties': [p for p in content['properties'] if p['column'] not in hidden]}
    dataset = current_dataset(conn, content['dataset'])
    cols = dataset_columns(conn, dataset['id']) if dataset else {}
    unsent = hidden_values(conn, row['element_id'])
    fanned = fan_marks(conn, dataset['id']) if dataset else set()
    props = [{**p, 'key': p['column'] in content['key'], 'hide_values': p['column'] in unsent, 'fan': fan_note() if p['column'] in fanned else None, 'meanings': _meaning_view(conn, content, p, cols, dataset, user) if p['enum'] else None} for p in content['properties']]
    limited = restriction(conn, row['element_id'], user) is not None
    from ontology_poc_generator.derived_properties import limited_reads   # derived_properties reads this module: imported here, where it is used
    return {'id': content['english_name'], 'name': content['name'], 'description': content['description'], 'dataset': content['dataset'], 'limited_reads': limited_reads(conn, english_name, user),
            'dataset_version': dataset['version'] if dataset else None, 'rows': visible_rows(conn, row, dataset, user) if dataset else None, 'rows_limited': limited,
            **({'limited_note': limited_note()} if limited else {}), 'seen': None if limited else seen_of_type(dataset), 'key': content['key'],
            'properties': props, 'visible_to': None if user is not None and user['role'] == 'viewer' else visible_to(conn, row['element_id']), **_state_view(conn, row, user),
            'columns': [{'name': n, 'type': c['type'], 'enum_candidate': bool(c['counts']) and c['type'] in CODE_TYPES} for n, c in cols.items() if n not in hidden],
            'columns_kept': len(hidden)}


def type_objects(conn, english_name: str, page: int, user: dict | None) -> dict:
    """The rows of the type's dataset (its current version) as objects: the key and the properties, one page, with how each code column's meanings stand."""
    detail = type_detail(conn, english_name, user)
    dataset = current_dataset(conn, detail['dataset'])
    if dataset is None:
        raise TypeRefused(tr(f'数据集“{detail["dataset"]}”已经不在了', f'The dataset "{detail["dataset"]}" is gone'), 409)
    present = dataset_columns(conn, dataset['id'])
    gone = [p['column'] for p in detail['properties'] if p['column'] not in present]
    if gone:   # an unknown column in double quotes would be read by SQLite as the text of its name
        raise TypeRefused(tr(f'{dataset["name"]} 第 {dataset["version"]} 版里没有这些列了：{tr("、", ", ").join(gone)}', f'{dataset["name"]} version {dataset["version"]} no longer has these columns: {", ".join(gone)}'), 409)
    limit = restriction(conn, type_id(english_name), user)
    q = lambda name: '"' + name.replace('"', '""') + '"'
    if limit is None:
        total = dataset['rows_stored']
        pages = max(1, -(-total // OBJECT_PAGE))
        page = min(max(page, 1), pages)
        fetched = [list(r) for r in conn.execute(f'SELECT rowid, {", ".join(q(p["column"]) for p in detail["properties"])} FROM {q(dataset["table_name"])} '
                                                 f'ORDER BY rowid LIMIT {OBJECT_PAGE} OFFSET {(page - 1) * OBJECT_PAGE}')]
        numbers, rows = [r[0] for r in fetched], [r[1:] for r in fetched]
    else:   # a row rule names this person (or none does): only the rows it keeps, paged here
        kept = [(i, r) for i, r in enumerate(dataset_records(conn, dataset), 1) if keeps(r, limit)]
        total = len(kept)
        pages = max(1, -(-total // OBJECT_PAGE))
        page = min(max(page, 1), pages)
        shown = kept[(page - 1) * OBJECT_PAGE:page * OBJECT_PAGE]
        numbers, rows = [i for i, _ in shown], [[r.get(p['column']) for p in detail['properties']] for _, r in shown]
    from ontology_poc_generator.derived_properties import confirmed_columns   # derived_properties reads this module: imported here, where it is used
    derived = confirmed_columns(conn, english_name, user)   # their values come first, tagged 派生 (those not yet confirmed last, and only for builders), over the rows this person may read
    rows = [[*(d['values'].get(n) for d in derived), *row] for n, row in zip(numbers, rows)]
    enums = {p['column']: {'state': p['meanings']['state'], 'labels': {v['value']: v['label'] for v in p['meanings']['values'] if v['label']}}
             for p in detail['properties'] if p['meanings']}
    return {'columns': [{'column': f'derived:{d["english_name"]}', 'name': d['name'], 'type': d['output_type'], 'key': False, 'derived': True, 'confirmed': d['confirmed'], 'says': d['says']} for d in derived]
            + [{'column': p['column'], 'name': p['name'], 'type': p['type'], 'key': p['key']} for p in detail['properties']], 'rows': rows, 'total': total,
            'page': page, 'pages': pages, 'limit': OBJECT_PAGE, 'dataset': detail['dataset'], 'dataset_version': dataset['version'], 'enums': enums, 'rows_limited': limit is not None}


def type_log(conn, english_name: str, user: dict | None) -> list[dict]:
    """What happened to a type, to the meanings of its code columns and to the dataset it reads, newest first: time, who, what, and for a move to
    needs_look the reason and whose upload it was."""
    detail = type_detail(conn, english_name, user)
    only_confirmed = " AND state = 'confirmed'" if user is not None and user['role'] == 'viewer' else ''   # a viewer reads nothing of a view nobody confirmed
    views = [e for (e,) in conn.execute(f"SELECT element_id FROM element_state WHERE element_id LIKE 'objview:%' AND json_extract(content_json, '$.type') = ?{only_confirmed}", (english_name,))]
    actions = [] if user is not None and user['role'] == 'viewer' else [e for (e,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objaction:%' AND json_extract(content_json, '$.type') = ?", (english_name,))]
    derived = [e for (e,) in conn.execute(f"SELECT element_id FROM element_state WHERE element_id LIKE 'derived:%' AND json_extract(content_json, '$.type') = ?{only_confirmed}", (english_name,))]
    return log_entries(conn, [type_id(english_name), *(enum_id(english_name, p['column']) for p in detail['properties'] if p['meanings']), *views, *actions, *derived, f'dataset:{detail["dataset"]}'], user)


def _action_line_readable(conn, element: str, after: dict, user: dict | None) -> bool:
    """Whether this person may read a log line of an action: it quotes the object it is about (its key, before and after values, the reason), so a person a row
    rule limits reads it only when the row is one they may read. The row is the record's, or for an attempt with no record the one its key names; a line whose
    row cannot be found is not shown to them."""
    rec = after.get('record')
    if rec is not None:
        found = conn.execute('SELECT type_id, key_json FROM action_record WHERE id = ?', (rec,)).fetchone()
        tid, key = (found[0], json.loads(found[1])) if found else (None, None)
    else:
        action = element_row(conn, element)
        tid, key = (type_id(_content(action)['type']) if action else None), (after.get('attempt') or {}).get('key')
    limit = restriction(conn, tid, user) if tid else None
    if limit is None:
        return True
    t = _content(element_row(conn, tid))
    dataset = current_dataset(conn, t['dataset'])
    if dataset is None or not isinstance(key, dict) or set(key) != set(t['key']) or not all(isinstance(v, (str, int, float)) and not isinstance(v, bool) for v in key.values()):
        return False
    wanted = tuple(_canonical(str(key[c])) for c in t['key'])
    return any(keeps(r, limit) for r in dataset_records(conn, dataset) if _key_of(r, t['key']) == wanted)


def log_entries(conn, ids: list[str], user: dict | None = None) -> list[dict]:
    """The log lines about these elements, newest first (the caller has checked that this person may read them). A line of an action about a row a row rule keeps
    from `user` is left out altogether."""
    out, limited, kept_from, hidden_of = [], {}, {}, {}
    hidden = lambda element: hidden_of.setdefault(element, hidden_columns(conn, element, user))
    for at, who, element, change, before, after in conn.execute(
            f'SELECT time, who, element_id, change, before_json, after_json FROM log WHERE element_id IN ({",".join("?" * len(ids))}) ORDER BY time DESC, rowid DESC', ids):
        after = json.loads(after) if after else {}
        if element not in kept_from:   # a meaning, view, relation, derived property or action that reads a column kept from this person: none of its lines
            kept_from[element] = element.startswith((ENUM_PREFIX, VIEW_PREFIX, RELATION_PREFIX, DERIVED_PREFIX, ACTION_PREFIX)) and reads_hidden(conn, element, user)
        if kept_from[element] or (change in ('values_privacy_changed', 'column_access_changed') and after.get('column') in hidden(element)):
            continue
        if change == 'needs_look' and after.get('reason'):   # a reason that quotes counts of the whole data
            if element not in limited:
                held = element_row(conn, element)
                limited[element] = held is not None and held['content_json'] is not None and limited_on(conn, held, user)
            if limited[element]:
                after = {**after, 'reason': hidden_reason()}
        if change.startswith('action_') and not _action_line_readable(conn, element, after, user):
            continue
        kind = ('dataset' if element.startswith('dataset:') else 'meaning' if element.startswith(ENUM_PREFIX) else 'relation' if element.startswith(RELATION_PREFIX)
                else 'view' if element.startswith(VIEW_PREFIX) else 'derived' if element.startswith(DERIVED_PREFIX) else 'action' if element.startswith(ACTION_PREFIX) else 'pipeline' if element.startswith(PIPELINE_PREFIX) else 'type')
        out.append({'at': at, 'who': who, 'element': kind, 'column': element.split(':', 2)[2] if kind == 'meaning' else None, 'change': change,
                    'record': after.get('record') if change.startswith('action_') else None,
                    'from': (json.loads(before) if before else {}).get('state'), 'to': after.get('state'), 'reason': after.get('reason'),
                    'caused_by': after.get('caused_by'), 'self_confirmed': bool(after.get('self_confirmed')),
                    'visible_to': after.get('visible_to') if change == 'access_changed' else None,
                    'text': after.get('name') if change == 'edited' else change if kind == 'dataset' else tr('、', ', ').join(c for c in after['columns'] if c not in hidden(element)) or tr('你看不到的列', 'columns you cannot see') if change == 'meanings_retired'
                    else after.get('text') if change.startswith('action_') or change == 'confirmed_together' else after.get('summary') if change in ('row_rules_changed', 'notify_changed')
                    else tr(f'{after["column"]}：{"不再" if after["hide_values"] else "重新"}把取值发给模型', f'{after["column"]}: values are {"no longer" if after["hide_values"] else "again"} sent to the model') if change == 'values_privacy_changed'
                    else tr(f'{after["column"]}：{"所有人都能看" if after["visible_to"] == "everyone" else "只给 " + tr("、", ", ").join(after["visible_to"]) + " 看（还有管理员）" if after["visible_to"] else "只有管理员能看"}', f'{after["column"]}: {"everyone can see it" if after["visible_to"] == "everyone" else "only " + ", ".join(after["visible_to"]) + " (and admins) can see it" if after["visible_to"] else "only admins can see it"}') if change == 'column_access_changed'
                    else tr(f'第 {after["run"]} 次运行，写了 {tr("、", ", ").join(after["outputs"]) or "没有数据集"}', f'Run {after["run"]} wrote {", ".join(after["outputs"]) or "no datasets"}') if change == 'run'
                    else tr(f'第 {after["run"]} 次运行失败：{after["error"]}', f'Run {after["run"]} failed: {after["error"]}') if change == 'run_failed' else None})
    return out
