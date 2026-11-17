"""Actions: the one way a person changes data in the workspace. Three kinds, on one object type:
- edit (the default): change one or more properties of one object;
- create (R12a): add one object: its key and the properties the action names, every value checked against its property's type; a key that is already there is
  refused, never written over;
- delete (R12a): remove one object, with a reason. The whole row is kept on the request, so an undo puts the same row back. It reads every column of the row, so
  a person kept from one of them is not shown the action.

The definition is an element like the others (objaction:<name>, the name is the id and is fixed): a name, the kind, the type, the properties it writes, up to
MAX_CONDITIONS conditions the object has to meet (edit and delete: =, ≠, >, ≥, <, ≤ on numbers and dates, empty, not empty, one of; all must hold; the old single
`condition` reads as one "="), and optionally the people who may submit it. A person puts it forward (checked), another builder confirms it; it reads its
type and the meanings of the code columns it writes or tests (element_dep), so it goes to needs_look when one of them does. An edit that writes a property a row
rule on its type reads cannot be confirmed (row_rules says why); a create must make a row its submitter may read, a delete removes only one they may read. The
parameters are the written properties (a create's key first); one with confirmed meanings takes one of them (a code and its label), the others a value that
fits the property's type.

Running it makes a record, not a change. A builder submits {action, the object's key, a value for each property, a reason}; the record keeps the values the
object has now (before), the values asked for (after) and the version of the dataset it was read on, and waits in 待确认 for another builder, who approves or
rejects. The submitter can withdraw it; a record nobody decides in EXPIRE_DAYS expires. Records are never deleted: they end approved, rejected, withdrawn or
expired, and one whose data moved ends the way "needs_look" says (a person can reject it or the submitter withdraw it; a new submit starts again).
At approval nothing is written unless the dataset is still at the version the submitter read and the object still holds the before-values: otherwise the record
goes to needs_look ("数据在提交后变了") and the data is untouched. When it holds, the change is written as a new version of the dataset by key (the same update by
key an upload uses), with the action and the record on the version, and what stands on the dataset is rechecked as after an upload.

"Can read it" is checked at submit and at approval: the type is visible to the person and a row rule that names them keeps the object's row; a person who may
not read it is told there is no such object. The log is always on: every submit, approval, rejection, withdrawal, expiry, and every refused or failed attempt
(who, when, why, what was asked) is a line on the action's element, shown on the type's 日志 tab and the action's page.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from ontology_poc_generator.accounts import list_users, two_person
from ontology_poc_generator.object_types import (
    ACTION_PREFIX, MAX_DESCRIPTION, MAX_NAME, TYPE_NAME, TypeRefused, _content, _edit_names, _state_view, _text, _type_row, _visible,
    element_row, enum_id, log_entries, recheck_after_write, type_id, whole_type_row, write_confirmation, write_elements)
from ontology_poc_generator.object_views import meaning_labels
from ontology_poc_generator.row_rules import conflict_with_actions, keeps, restriction
from ontology_poc_generator.type_access import hidden_columns, reads_hidden
from ontology_poc_generator.workspace_store import (
    _DECIMAL, _INTEGER, _canonical, _key_of, apply_upload, current_dataset, dataset_records, infer_type, log_line, now_text, plan_upload)

EXPIRE_DAYS = 14
MAX_PROPERTIES = 5
MAX_CREATE_PROPERTIES = 20   # a create fills in an object: more of its properties than an edit changes at once
MAX_CONDITIONS = 5
MAX_IN = 20
MAX_SUBMITTERS = 20
MAX_REASON = 300
MAX_VALUE = 500   # a text value goes into the dataset, the pending record and the log
KINDS = ('edit', 'create', 'delete')
KIND_WORD = {'edit': '改', 'create': '新建', 'delete': '删除'}
OPS = {'eq': '是', 'ne': '不是', 'gt': '大于', 'ge': '大于等于', 'lt': '小于', 'le': '小于等于', 'empty': '为空', 'not_empty': '不为空', 'in': '是…之一'}
ORDERED = ('gt', 'ge', 'lt', 'le')
NUMBER_TYPES = ('integer', 'decimal')
DATE_TYPES = ('date', 'datetime', 'month')
STATE_WORDS = {'proposed': '还是模型的草稿', 'checked': '还没有另一位确认', 'needs_look': '需要再看', 'rejected': '被退回了'}


def action_id(name: str) -> str:
    return f'{ACTION_PREFIX}{name}'


def kind_of(content: dict) -> str:
    """edit, create or delete: a definition written before R12a is an edit."""
    return content.get('kind') or 'edit'


def conditions_of(content: dict) -> list[dict]:
    """The definition's conditions as [{column, op, value}]: the old single `condition` reads as one "="."""
    if content.get('conditions') is not None:
        return content['conditions']
    old = content.get('condition')
    return [{'column': old['column'], 'op': 'eq', 'value': old['value']}] if old else []


# --- the definition a person writes -------------------------------------------------------------------------------------------------------------------

def check_definition(conn, payload: dict, user: dict | None, name: str | None = None) -> dict:
    """The content of an action as a person wrote it: a name, its kind, a type this person may see, the properties it writes (not the key), its conditions and
    who may submit it. TypeRefused says what is wrong."""
    name = _text(payload.get('name') if name is None else name, '行为的名字', MAX_NAME)
    description = _text(payload.get('description') or '', '说明', MAX_DESCRIPTION, required=False)
    kind = payload.get('kind') or 'edit'
    if kind not in KINDS:
        raise TypeRefused('kind 只能是 edit（改）、create（新建）或 delete（删除）')
    t = _content(whole_type_row(conn, payload.get('type'), user))
    columns = payload.get('properties')
    props = {p['column']: p for p in t['properties']}
    if kind == 'delete':
        if columns not in (None, []):
            raise TypeRefused('删除行为不写要改的属性：删掉的是整个对象')
        columns = []
    else:
        most, least = (MAX_CREATE_PROPERTIES, 0) if kind == 'create' else (MAX_PROPERTIES, 1)
        if (not isinstance(columns, list) or not least <= len(columns) <= most or not all(isinstance(c, str) for c in columns)
                or len(set(columns)) != len(columns)):
            raise TypeRefused(f'要选 {least} 到 {most} 个要{"填" if kind == "create" else "改"}的属性，不重复')
    for column in columns:
        if column not in props:
            raise TypeRefused(f'“{column}”不是“{t["name"]}”的属性')
        if column in t['key']:
            raise TypeRefused(f'“{column}”是主键，行为不能改它：主键决定改的是哪一个对象' if kind == 'edit' else f'“{column}”是主键：新建时总要填，不用另外选')
    for column in [*columns, *(t['key'] if kind == 'create' else [])]:
        if props[column]['enum'] and element_row(conn, enum_id(t['english_name'], column)) is None:
            raise TypeRefused(f'“{column}”是代码列，先给它写含义：行为的参数要从含义里选')
    raw = payload.get('conditions')
    if raw is None and payload.get('condition') is not None:   # the old form: one "property = value"
        old = payload['condition']
        raw = [{'column': old.get('column'), 'op': 'eq', 'value': old.get('value')}] if isinstance(old, dict) else old
    conditions = _check_conditions(conn, t, props, raw)
    if kind == 'create' and conditions:
        raise TypeRefused('新建行为不能设条件：要新建的对象还不存在，没有可以检查的值')
    if kind == 'edit':
        clash = conflict_with_actions(conn, type_id(t['english_name']), columns)
        if clash:
            raise TypeRefused(clash, 409)
    choices = _check_choices(conn, payload.get('choices'), columns, props, user)
    submitters = _check_submitters(conn, payload.get('submitters'))
    return {'name': name, 'description': description, 'kind': kind, 'type': t['english_name'], 'properties': list(columns), 'conditions': conditions,
            **({'choices': choices} if choices else {}), **({'submitters': submitters} if submitters else {})}


def _condition_value(value) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ''


def _check_conditions(conn, t: dict, props: dict, raw) -> list[dict]:
    """[{column, op, value}] checked against the type: an operator it has, a value that fits the property (a code column's from its meanings; a number or a date to
    compare in order), none for empty / not empty, 1 to MAX_IN values for "one of"."""
    if raw in (None, []):
        return []
    if not isinstance(raw, list) or not all(isinstance(c, dict) for c in raw):
        raise TypeRefused('条件要写成 [{column, op, value}] 的列表')
    if len(raw) > MAX_CONDITIONS:
        raise TypeRefused(f'条件最多 {MAX_CONDITIONS} 条')
    out = []
    for c in raw:
        column, op, value = c.get('column'), c.get('op') or 'eq', c.get('value')
        if column not in props:
            raise TypeRefused('条件要选对象的一个属性')
        if op not in OPS:
            raise TypeRefused(f'条件的比较方式只能是：{"、".join(OPS.values())}')
        name, ptype = props[column]['name'], props[column]['type']
        labels = meaning_labels(conn, t['english_name'], column) if props[column]['enum'] else None
        if op in ('empty', 'not_empty'):
            if value not in (None, '', []):
                raise TypeRefused(f'“{name} {OPS[op]}”不写取值')
            out.append({'column': column, 'op': op})
            continue
        if op == 'in':
            values = [_condition_value(v) for v in value] if isinstance(value, list) else []
            if not 1 <= len(values) <= MAX_IN or not all(values) or any(len(v) > 100 or '\n' in v for v in values):
                raise TypeRefused(f'“{name} 是…之一”要列 1 到 {MAX_IN} 个取值，每个 1 到 100 个字')
            bad = [v for v in values if labels is not None and v not in labels]
            if bad:
                raise TypeRefused(f'“{bad[0]}”不是“{name}”已写含义里的取值')
            out.append({'column': column, 'op': op, 'value': list(dict.fromkeys(values))})
            continue
        text = _condition_value(value)
        if not text or len(text) > 100 or '\n' in text:
            raise TypeRefused('条件的取值要写 1 到 100 个字，不能换行')
        if op in ORDERED:
            if labels is not None or ptype not in (*NUMBER_TYPES, *DATE_TYPES):
                raise TypeRefused(f'“{name}”不是数字或日期，不能比大小')
            if ptype in NUMBER_TYPES and infer_type([text]) not in NUMBER_TYPES:
                raise TypeRefused(f'“{name}”要和一个数字比较，“{text}”不是数字')
            if ptype in DATE_TYPES and infer_type([text]) not in DATE_TYPES:
                raise TypeRefused(f'“{name}”要和一个日期比较，“{text}”不是日期')
        elif labels is not None and text not in labels:
            raise TypeRefused(f'“{text}”不是“{name}”已写含义里的取值')
        out.append({'column': column, 'op': op, 'value': text})
    return out


def _check_submitters(conn, raw) -> list[int]:
    """The ids of the people who may submit the action (none: every builder who may see it)."""
    if raw in (None, []):
        return []
    if not isinstance(raw, list) or len(raw) > MAX_SUBMITTERS or not all(isinstance(i, int) and not isinstance(i, bool) for i in raw):
        raise TypeRefused(f'能提交的人要写成账号 id 的列表，最多 {MAX_SUBMITTERS} 个')
    known = {u['id'] for u in list_users(conn)}
    if set(raw) - known:
        raise TypeRefused('能提交的人里有不存在的账号')
    return sorted(set(raw))


def _holds(cond: dict, value, ptype: str) -> bool:
    """Whether one condition holds for this value of the object."""
    empty = value is None or str(value).strip() == ''
    op = cond['op']
    if op == 'empty':
        return empty
    if op == 'not_empty':
        return not empty
    if op == 'ne':
        return empty or _canonical(value) != _canonical(cond['value'])
    if empty:
        return False
    if op == 'eq':
        return _canonical(value) == _canonical(cond['value'])
    if op == 'in':
        return _canonical(value) in {_canonical(v) for v in cond['value']}
    if ptype in NUMBER_TYPES:
        if not all(_INTEGER.fullmatch(str(v).strip()) or _DECIMAL.fullmatch(str(v).strip()) for v in (value, cond['value'])):
            return False   # not a plain number: not more or less than one (1e3, inf and 1_0 are text here, as everywhere a value is matched)
        a, b = float(str(value).strip()), float(str(cond['value']).strip())
    else:
        a, b = str(value).strip(), str(cond['value']).strip()
    return {'gt': a > b, 'ge': a >= b, 'lt': a < b, 'le': a <= b}[op]


def _phrase(conn, english: str, names: dict, cond: dict) -> str:
    """One condition as a person reads it: 状态码 是「生产中」, 金额 大于 3000, 客户编号 是 KH001、KH002 之一."""
    name, op = names[cond['column']], cond['op']
    if op in ('empty', 'not_empty'):
        return f'{name} {OPS[op]}'
    if op == 'in':
        return f'{name} 是 {"、".join(_label(conn, english, cond["column"], v) for v in cond["value"])} 之一'
    if op in ('eq', 'ne'):
        return f'{name} {OPS[op]}「{_label(conn, english, cond["column"], cond["value"])}」'
    return f'{name} {OPS[op]} {cond["value"]}'


def _condition_view(conn, english: str, names: dict, cond: dict) -> dict:
    value = cond.get('value')
    label = ('、'.join(_label(conn, english, cond['column'], v) for v in value) if isinstance(value, list)
             else _label(conn, english, cond['column'], value) if value is not None else '')
    return {**cond, 'name': names[cond['column']], 'label': label}


def _check_choices(conn, choices, columns: list[str], props: dict, user: dict | None) -> dict:
    """{column: {type, column}}: a written property whose new value must be one of a column of a type (another, or its own). A code column picks from its meanings
    already, so it has none."""
    if choices in (None, {}):
        return {}
    if not isinstance(choices, dict) or len(choices) > MAX_PROPERTIES:
        raise TypeRefused('可选值要写成 {属性: {type, column}}')
    out = {}
    for column, source in choices.items():
        if column not in columns:
            raise TypeRefused(f'“{column}”不是这个行为要改的属性')
        if props[column]['enum']:
            raise TypeRefused(f'“{column}”是代码列，参数已经从含义里选')
        if not isinstance(source, dict) or not isinstance(source.get('type'), str) or not isinstance(source.get('column'), str):
            raise TypeRefused(f'“{column}”的可选值要写明从哪个对象类型的哪一列来')
        other = _content(whole_type_row(conn, source['type'], user))
        if source['column'] not in {p['column'] for p in other['properties']}:
            raise TypeRefused(f'“{source["column"]}”不是“{other["name"]}”的属性')
        out[column] = {'type': other['english_name'], 'column': source['column']}
    return out


MAX_OPTIONS = 500


def _allowed_values(conn, source: dict, user: dict | None, everyone: bool = False) -> tuple[list[str], dict | None]:
    """(the distinct values of the source column, its type's content or None when the type is gone): over the rows this person may read, or with `everyone`
    over all of them (what an approval checks against: whether the value exists, not who may see it)."""
    row = element_row(conn, type_id(source['type']))
    if row is None:
        return [], None
    other = _content(row)
    dataset = current_dataset(conn, other['dataset'])
    if dataset is None:
        return [], other
    limit = None if everyone else restriction(conn, row['element_id'], user)
    values: dict = {}
    for r in dataset_records(conn, dataset):
        text = str(r.get(source['column']) or '').strip()
        if text and keeps(r, limit):
            values.setdefault(_canonical(text), text)   # 1 and 1.0 are one value: the first spelling met is offered
    return sorted(values.values()), other


def check_names_free(conn, content: dict) -> None:
    mine = action_id(content['name'])
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objaction:%'"):
        if element_id != mine and element_id.casefold() == mine.casefold():
            raise TypeRefused(f'已经有叫“{element_id[len(ACTION_PREFIX):]}”的行为（名字不分大小写）', 409)


def _reset_reasons(old: dict, new: dict) -> list[str]:
    read = {'kind': kind_of, 'conditions': conditions_of, 'submitters': lambda c: c.get('submitters') or [], 'choices': lambda c: c.get('choices')}
    return [label for key, label in (('kind', '种类'), ('type', '对象类型'), ('properties', '要改的属性'), ('conditions', '条件'), ('choices', '可选值'), ('submitters', '能提交的人'))
            if read.get(key, lambda c: c.get(key))(old) != read.get(key, lambda c: c.get(key))(new)]


def _enum_columns(content: dict, key: list[str] | None = None) -> list[str]:
    """The columns whose meanings the action uses: what it writes (a create's key too) and what its conditions test."""
    return list(dict.fromkeys([*(key or []), *content['properties'], *(c['column'] for c in conditions_of(content))]))


def _reads(conn, content: dict) -> list[str]:
    t = _content(element_row(conn, type_id(content['type'])))
    coded = {p['column'] for p in t['properties'] if p['enum']}
    written_key = t['key'] if kind_of(content) == 'create' else []
    return list(dict.fromkeys([type_id(content['type']), *(enum_id(content['type'], c) for c in _enum_columns(content, written_key) if c in coded),
                               *(type_id(src['type']) for src in (content.get('choices') or {}).values())]))   # the type its choices come from


def waiting_on(conn, content: dict) -> list[dict]:
    """What the action stands on that is not confirmed: its type, and the meanings of the code columns it writes or tests."""
    out = []
    for element_id in _reads(conn, content):
        row = element_row(conn, element_id)
        if row is None or row['state'] != 'confirmed':
            c = _content(row) if row else {}
            out.append({'id': element_id, 'name': c.get('name') or f'{c.get("type", "")}.{c.get("column", "")}', 'state': row['state'] if row else None})
    return out


def describe(conn, content: dict) -> str:
    """The definition as a sentence: 改 订单 的「状态码」；只在 状态码 是「生产中」时可以提交 / 新建 订单，要填「订单号」「金额」 / 删除 订单."""
    t = _content(element_row(conn, type_id(content['type'])))
    names = {p['column']: p['name'] for p in t['properties']}
    text = '、'.join(_phrase(conn, content['type'], names, c) for c in conditions_of(content))
    when = f'；只在 {text}{"" if text.endswith("」") else " "}时可以提交' if text else ''
    picks = ''.join(f'；「{names[c]}」从 {_type_name(conn, s["type"])} 的 {s["column"]} 里选' for c, s in (content.get('choices') or {}).items())
    kind = kind_of(content)
    if kind == 'create':
        head = f'新建 {t["name"]}，要填{"".join(f"「{names[c]}」" for c in [*t["key"], *content["properties"]])}'
    elif kind == 'delete':
        head = f'删除 {t["name"]}'
    else:
        head = f'改 {t["name"]} 的{"、".join(f"「{names[c]}」" for c in content["properties"])}'
    return f'{head}{picks}{when}'


def _type_name(conn, english: str) -> str:
    row = element_row(conn, type_id(english))
    return _content(row)['name'] if row else english


def _label(conn, english: str, column: str, value) -> str:
    """A value as a person reads it: its meaning when the column has one on file, else the value."""
    return meaning_labels(conn, english, column).get(str(value), str(value)) if value is not None else '（空）'


def _anchors(conn, content: dict) -> dict:
    dataset = current_dataset(conn, _content(element_row(conn, type_id(content['type'])))['dataset'])
    return {'dataset': dataset['name'], 'version': dataset['version']} if dataset else {}


def create_action(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    content = check_definition(conn, payload, user)
    if element_row(conn, action_id(content['name'])):
        raise TypeRefused(f'已经有叫“{content["name"]}”的行为', 409)
    check_names_free(conn, content)
    anchors = _anchors(conn, content)
    write_elements(conn, [(action_id(content['name']), 'checked', f'dataset:{anchors.get("dataset")}@v{anchors.get("version")}', who, content, anchors, who)],
                   {action_id(content['name']): _reads(conn, content)})
    return {'id': content['name']}


def update_action(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{id, version, ...}: a change to the type, the properties or the condition puts it forward again (a confirmed one stops being confirmed); the description
    keeps the state."""
    row = _action_row(conn, payload.get('id'), user)
    if payload.get('version') != row['version']:
        raise TypeRefused('这个行为在你打开之后被改了，请刷新后再改', 409)
    old = _content(row)
    content = check_definition(conn, payload, user, old['name'])
    reset = _reset_reasons(old, content)
    if reset or row['state'] in ('proposed', 'rejected'):
        anchors = _anchors(conn, content)
        write_elements(conn, [(row['element_id'], 'checked', f'dataset:{anchors.get("dataset")}@v{anchors.get("version")}', who, content, anchors, who)],
                       {row['element_id']: _reads(conn, content)}, {row['element_id']: row['version']})
    elif old['description'] != content['description']:
        _edit_names(conn, row, content, who)
    return {'id': old['name'], 'state': element_row(conn, row['element_id'])['state'], 'reset': reset}


def confirm_action(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{id, version}: another builder confirms the definition they read. Its type and the meanings it uses must be confirmed, and no row rule on the type may read
    a property it writes."""
    row = _action_row(conn, payload.get('id'), user)
    if payload.get('version') != row['version']:
        raise TypeRefused('确认要带上你看到的那一版；它在你看过之后被改了，请刷新后重新看一遍', 409)
    if row['state'] == 'confirmed':
        raise TypeRefused('已经确认过了', 409)
    if row['state'] == 'rejected':
        raise TypeRefused('已经被退回了：要先按退回的理由改，再重新提出', 409)
    content = _content(row)
    waiting = waiting_on(conn, content)
    if waiting:
        raise TypeRefused(f'行为用到的{"、".join("“" + w["name"] + "”" for w in waiting)}还没有确认，要先确认它们', 409)
    clash = conflict_with_actions(conn, type_id(content['type']), content['properties']) if kind_of(content) == 'edit' else None
    if clash:
        raise TypeRefused(f'不能确认：{clash}', 409)
    anchors = _anchors(conn, content)
    write_confirmation(conn, row['element_id'], content, f'dataset:{anchors.get("dataset")}@v{anchors.get("version")}', who, anchors, {anchors['dataset']: anchors['version']} if anchors else {},
                       row['version'], _reads(conn, content))
    return {'state': 'confirmed'}


# --- what a person reads ------------------------------------------------------------------------------------------------------------------------------

def _action_row(conn, name, user: dict | None) -> dict:
    row = element_row(conn, action_id(str(name)))
    if row is None or not action_visible(conn, row, user):
        raise TypeRefused('没有这个行为', 404)
    return row


def action_visible(conn, row: dict, user: dict | None) -> bool:
    """Actions are for builders (a viewer can run nothing): those who may see the action's type."""
    if user is not None and user['role'] == 'viewer':
        return False
    content = _content(row)
    type_row = element_row(conn, type_id(content['type']))
    sources = [element_row(conn, type_id(s['type'])) for s in (content.get('choices') or {}).values()]   # the types its values are offered from: theirs to see too
    return (type_row is not None and _visible(conn, type_row, user) and not reads_hidden(conn, row['element_id'], user, content)
            and all(s is not None and _visible(conn, s, user) for s in sources))


def action_state(conn, row: dict, user: dict | None) -> dict:
    state = _state_view(conn, row, user)
    waiting = waiting_on(conn, _content(row))
    return {**state, 'can_confirm': state['can_confirm'] and not waiting, 'waiting_on': waiting}


def parameters(conn, content: dict, user: dict | None = None) -> list[dict]:
    """The parameters the action asks for: each written property with its type and, for a code column, the meanings to pick from; for a property with choices, the
    values of the source column over the rows this person may read (at most MAX_OPTIONS). A create asks for the key first ('key': True); a delete asks for none."""
    t = _content(element_row(conn, type_id(content['type'])))
    props = {p['column']: p for p in t['properties']}
    out = []
    key = t['key'] if kind_of(content) == 'create' else []
    for column in [*key, *content['properties']]:
        source = (content.get('choices') or {}).get(column)
        if source:
            values, other = _allowed_values(conn, source, user)
            out.append({'column': column, 'name': props[column]['name'], 'type': props[column]['type'], 'type_name': TYPE_NAME[props[column]['type']], 'key': False,
                        'choices_from': {'type': source['type'], 'type_name': other['name'] if other else source['type'], 'column': source['column']},
                        'options': [{'value': v, 'label': v} for v in values[:MAX_OPTIONS]], 'options_cut': len(values) > MAX_OPTIONS})
            continue
        labels = meaning_labels(conn, content['type'], column) if props[column]['enum'] else None
        out.append({'column': column, 'name': props[column]['name'], 'type': props[column]['type'], 'type_name': TYPE_NAME[props[column]['type']],
                    'key': column in key, 'choices_from': None,
                    'options': None if labels is None else [{'value': v, 'label': labels[v]} for v in sorted(labels, key=lambda v: (not v.lstrip('-').isdigit(), int(v) if v.lstrip('-').isdigit() else 0, v))]})
    return out


def _line(conn, row: dict, user: dict | None) -> dict:
    content = _content(row)
    t = _content(element_row(conn, type_id(content['type'])))
    names = {p['column']: p['name'] for p in t['properties']}
    people = {u['id']: u for u in list_users(conn)}
    return {'id': content['name'], 'name': content['name'], 'description': content['description'], 'kind': kind_of(content), 'type': content['type'], 'type_name': t['name'],
            'properties': content['properties'], 'conditions': [_condition_view(conn, content['type'], names, c) for c in conditions_of(content)],
            'submitters': [{'id': i, 'name': people[i]['display_name'] if i in people else f'#{i}'} for i in content.get('submitters') or []],
            'can_submit': not content.get('submitters') or (user is not None and user['id'] in content['submitters']),
            'says': describe(conn, content), 'parameters': parameters(conn, content, user), **action_state(conn, row, user)}


def list_actions(conn, english_name: str, user: dict | None) -> list[dict]:
    _type_row(conn, english_name, user)
    out = []
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objaction:%' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        if _content(row)['type'] == english_name and action_visible(conn, row, user):
            out.append(_line(conn, row, user))
    return out


def action_form(conn, english_name: str, user: dict | None) -> dict:
    """What the form for a new action offers: the type's properties (not the key) with whether each is a code column, and the code columns' meanings."""
    t = _content(whole_type_row(conn, english_name, user))
    shown = lambda p: {'column': p['column'], 'name': p['name'], 'enum': p['enum'], 'type': p['type'], 'key': p['column'] in t['key'],
                       'labels': sorted(set(meaning_labels(conn, english_name, p['column']).values())) if p['enum'] else None,
                       'values': [{'value': v, 'label': l} for v, l in sorted(meaning_labels(conn, english_name, p['column']).items())] if p['enum'] else None}
    builders = [{'id': u['id'], 'name': u['display_name']} for u in list_users(conn) if u['role'] != 'viewer' and not u['disabled']]
    return {'properties': [shown(p) for p in t['properties'] if p['column'] not in t['key']], 'condition_properties': [shown(p) for p in t['properties']],
            'ops': [{'op': k, 'word': w} for k, w in OPS.items()], 'kinds': [{'kind': k, 'word': w} for k, w in KIND_WORD.items()], 'people': builders}


def action_detail(conn, name: str, user: dict | None) -> dict:
    row = _action_row(conn, name, user)
    expire_old(conn)
    records = [record_view(conn, r, user) for r in _records(conn, 'action_id = ?', (row['element_id'],), limit=50)]
    from ontology_poc_generator.notices import lines, recipients_of
    told = recipients_of(conn, row['element_id'])
    return {**_line(conn, row, user), 'records': [r for r in records if r], 'log': log_entries(conn, [row['element_id']], user),
            'notify': {'recipients': told, 'lines': lines(conn, told, _content(row)['type'])}}


# --- records -------------------------------------------------------------------------------------------------------------------------------------------

def _records(conn, where: str, args: tuple = (), limit: int | None = None) -> list[dict]:
    cursor = conn.execute(f'SELECT * FROM action_record WHERE {where} ORDER BY id DESC' + (f' LIMIT {limit}' if limit else ''), args)
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, r)) for r in cursor]


def _record(conn, record_id, user: dict | None) -> dict:
    found = _records(conn, 'id = ?', (record_id,)) if isinstance(record_id, int) and not isinstance(record_id, bool) else []
    if not found:
        raise TypeRefused('没有这条提交', 404)
    rec = found[0]
    action = element_row(conn, rec['action_id'])
    if action is None or not action_visible(conn, action, user):
        raise TypeRefused('没有这条提交', 404)
    return rec


def _find(conn, type_content: dict, dataset: dict, key: dict) -> dict | None:
    """The row of the dataset with this key (matched in its plain form), or None."""
    wanted = tuple(_canonical(str(key[c])) for c in type_content['key'])
    return next((r for r in dataset_records(conn, dataset) if _key_of(r, type_content['key']) == wanted), None)


def _may_read(conn, type_row: dict, record: dict | None, user: dict | None) -> bool:
    """Whether this person can read the object: they may see its type and, when a row rule limits the type, one that names them keeps its row. `record` None is
    a row that is not there: only someone who is not limited may be told so."""
    limit = restriction(conn, type_row['element_id'], user)
    return _visible(conn, type_row, user) and (limit is None or (record is not None and keeps(record, limit)))


def _object_text(t: dict, key: dict) -> str:
    return f'{t["name"]} {" + ".join(str(key[c]) for c in t["key"])}'


def _names(conn, english: str) -> dict:
    row = element_row(conn, type_id(english))
    return {p['column']: p['name'] for p in _content(row)['properties']} if row else {}


def _pairs(conn, english: str, columns, values: dict) -> str:
    names = _names(conn, english)
    return '，'.join(f'{names.get(c, c)} {_label(conn, english, c, values.get(c))}' for c in columns)


def _change(conn, english: str, columns, before: dict, after: dict) -> str:
    """'状态码 从 生产中 改成 已交付', one clause per property an edit writes."""
    names = _names(conn, english)
    label = lambda c, v: _label(conn, english, c, v)
    return '，'.join(f'{names.get(c, c)} 从 {label(c, before.get(c))} 改成 {label(c, after.get(c))}' for c in columns)


def _op(rec: dict) -> str:
    """What a request does: edit, create or delete (a request made before R12a is an edit; an undo of a create is a delete, of a delete a create)."""
    return rec.get('op') or 'edit'


def _shown_columns(conn, t: dict, user: dict | None, values: dict) -> list[str]:
    """The type's properties (not the key) that are in `values` and this person may read, in the type's order: what a create or a delete is shown with."""
    hidden = hidden_columns(conn, type_id(t['english_name']), user) if user is not None else set()
    return [p['column'] for p in t['properties'] if p['column'] not in t['key'] and p['column'] in values and p['column'] not in hidden]


def _named_columns(content: dict, t: dict, values: dict) -> list[str]:
    """The properties a log line or a notice about this action may name, in the type's order: what the action reads (a delete reads them all), since the log and
    the notices go to everyone who may see the action, and seeing it says nothing about other columns."""
    allowed = None if kind_of(content) == 'delete' else set(content['properties'])
    return [p['column'] for p in t['properties'] if p['column'] not in t['key'] and p['column'] in values and (allowed is None or p['column'] in allowed)]


def _of_type(t: dict, values: dict) -> dict:
    """Only the type's own properties of a stored row: the dataset may hold columns the type does not take up, and a request shows nothing beyond the type."""
    columns = {p['column'] for p in t['properties']}
    return {c: v for c, v in values.items() if c in columns}


def _subject(op: str, current: dict | None, key: dict, before: dict, after: dict) -> dict | None:
    """The row a request is about, for who may read it: the object as it is now; while it is not there, the row a create would add or a delete removed."""
    if current is not None:
        return current
    if op == 'create':
        return {**after, **key}
    if op == 'delete':
        return before or None
    return None


def _texts(conn, op: str, t: dict, user: dict | None, before: dict, after: dict) -> tuple[str, str, str]:
    """(before_text, after_text, change_text) of a request as this person reads it."""
    english = t['english_name']
    if op == 'create':
        shown = _pairs(conn, english, _shown_columns(conn, t, user, after), after)
        return '（还没有）', shown, f'新建：{shown}'
    if op == 'delete':
        shown = _pairs(conn, english, _shown_columns(conn, t, user, before), before)
        return shown, '（删除）', f'删除：{shown}'
    columns = list(after)
    return _pairs(conn, english, columns, before), _pairs(conn, english, columns, after), _change(conn, english, columns, before, after)


def record_view(conn, rec: dict, user: dict | None, light: bool = False) -> dict | None:
    """One record as a page shows it; None when this person may not read the object it is about (a person never reads a row a rule keeps from them). A column
    kept from them is left out of what a create or a delete shows."""
    action = element_row(conn, rec['action_id'])
    type_row = element_row(conn, rec['type_id'])
    if action is None or type_row is None or reads_hidden(conn, rec['action_id'], user, _content(action)):   # an action on a column kept from them: none of its records
        return None
    content, t = _content(action), _content(type_row)
    op = _op(rec)
    dataset = current_dataset(conn, rec['dataset'])
    key, before, after = json.loads(rec['key_json']), json.loads(rec['before_json']), json.loads(rec['after_json'])
    current = _find(conn, t, dataset, key) if dataset else None
    if not _may_read(conn, type_row, _subject(op, current, key, before, after), user):
        return None
    hidden = hidden_columns(conn, type_row['element_id'], user) if user is not None else set()
    before, after = ({c: v for c, v in _of_type(t, d).items() if c not in hidden} for d in (before, after))
    before_text, after_text, change_text = _texts(conn, op, t, user, before, after)
    same_person = user is not None and rec['submitted_by_user_id'] is not None and user['id'] == rec['submitted_by_user_id']
    rule = two_person(conn)
    can_decide = (rec['state'] == 'pending' and user is not None and user['role'] != 'viewer' and not (same_person and rule['active']))
    return {'id': rec['id'], 'action': content['name'], 'kind': op, 'type': t['english_name'], 'type_name': t['name'], 'object': _object_text(t, key), 'key': key,
            'before_text': before_text, 'after_text': after_text, 'change_text': change_text, 'before': before, 'after': after, 'reason': rec['reason'],
            'state': rec['state'], 'submitted_by': rec['submitted_by'], 'submitted_at': rec['submitted_at'], 'decided_by': rec['decided_by'], 'decided_at': rec['decided_at'],
            'note': rec['note'], 'why': rec['why'], 'new_version': rec['new_version'], 'dataset': rec['dataset'], 'dataset_version': rec['dataset_version'],
            'dataset_now': dataset['version'] if dataset else None, 'stale': rec['state'] == 'pending' and (dataset is None or dataset['version'] != rec['dataset_version']),
            'can_decide': can_decide, 'can_withdraw': rec['state'] in ('pending', 'needs_look') and same_person, 'undo_of': rec.get('undo_of'),
            'can_undo': rec['state'] == 'approved' and user is not None and user['role'] != 'viewer' and _undone_by(conn, rec['id']) is None}


def open_records(conn, user: dict | None) -> list[dict]:
    """The records waiting for a person's look (pending, or needs another look) that they may read, newest first."""
    expire_old(conn)
    out = []
    if user is not None and user['role'] == 'viewer':
        return out
    for rec in _records(conn, "state IN ('pending', 'needs_look')"):
        view = record_view(conn, rec, user)
        if view:
            out.append(view)
    return out


def expire_old(conn) -> None:
    """A pending record nobody decided in EXPIRE_DAYS ends as expired (the log says so)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=EXPIRE_DAYS)).isoformat(timespec='seconds')
    for rec in _records(conn, "state = 'pending' AND submitted_at < ?", (cutoff,)):
        conn.execute('BEGIN IMMEDIATE')
        try:
            if conn.execute("UPDATE action_record SET state = 'expired', decided_at = ? WHERE id = ? AND state = 'pending'", (now_text(), rec['id'])).rowcount:
                log_line(conn, 'system', rec['action_id'], 'action_expired', after={'record': rec['id'], 'text': f'#{rec["id"]}（{rec["submitted_by"]} 提交）{EXPIRE_DAYS} 天没人处理，过期了'}, user_id=None)
            conn.execute('COMMIT')
        except BaseException:
            conn.execute('ROLLBACK')
            raise


# --- running an action ---------------------------------------------------------------------------------------------------------------------------------

def _refuse(conn, who: str | None, element_id: str, message: str, attempt: dict, status: int = 409, change: str = 'action_refused', record: int | None = None):
    """Write the refused attempt to the action's log (who, what was asked, why), then raise it."""
    what = {'submit': '提交', 'approve': '批准', 'reject': '驳回', 'undo': '撤销'}[attempt['op']]
    log_line(conn, who or '未署名', element_id, change, after={'record': record, 'text': f'{who or "未署名"} 的{what}被拒：{message}', 'reason': message, 'attempt': attempt})
    raise TypeRefused(message, status)


def _fits(kind: str, wanted: str) -> bool:
    return wanted == 'text' or kind == wanted or (wanted == 'decimal' and kind == 'integer') or (wanted == 'datetime' and kind == 'date')


def _check_values(conn, content: dict, t: dict, params, user: dict | None = None, everyone: bool = True) -> tuple[dict, str | None]:
    """(the values as strings, what is wrong in words or None): a value for every written property and no other, of the property's type, a code column's from its
    meanings."""
    if params is None and not content['properties']:   # a create that asks for the key alone
        params = {}
    if not isinstance(params, dict):
        return {}, '要给出每个属性的新值'
    props = {p['column']: p for p in t['properties']}
    extra = [c for c in params if c not in content['properties']]
    if extra:
        return {}, f'这个行为不改“{"、".join(extra)}”'
    out = {}
    for column in content['properties']:
        value = params.get(column)
        text = str(value).strip() if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ''
        if not text:
            return {}, f'“{props[column]["name"]}”要给一个新值'
        if len(text) > MAX_VALUE or '\n' in text:
            return {}, f'“{props[column]["name"]}”的新值最多 {MAX_VALUE} 个字，不能换行'
        if props[column]['enum']:
            labels = meaning_labels(conn, content['type'], column)
            if text not in labels:
                return {}, f'“{props[column]["name"]}”的值“{text}”不是它的含义里的取值：{"、".join(f"{v}（{l}）" for v, l in sorted(labels.items()))}'
        elif not _fits(infer_type([text]), props[column]['type']):
            return {}, f'“{props[column]["name"]}”的值“{text}”不能当{TYPE_NAME.get(props[column]["type"], props[column]["type"])}用'
        source = (content.get('choices') or {}).get(column)
        if source:
            values, other = _allowed_values(conn, source, user, everyone)
            if _canonical(text) not in {_canonical(v) for v in values}:
                return {}, f'“{props[column]["name"]}”的值“{text}”不在“{other["name"] if other else source["type"]}”的“{source["column"]}”里'
        out[column] = text
    return out, None


def _reason(payload) -> str:
    reason = payload.get('reason')
    return reason.strip() if isinstance(reason, str) else ''


def _insert(conn, rec: dict, who: str | None, user: dict | None, log_after: dict) -> int:
    """A pending request and its log line, as one write."""
    conn.execute('BEGIN IMMEDIATE')
    try:
        if rec.get('undo_of') is not None and _undone_by(conn, rec['undo_of']) is not None:   # again inside the write: two undos sent at once make one request
            raise TypeRefused(f'#{rec["undo_of"]} 已经撤销过，或者有一条撤销在等批准', 409)
        record_id = conn.execute('INSERT INTO action_record(action_id, action_version, type_id, dataset, dataset_version, key_json, before_json, after_json, reason, state, submitted_by,'
                                 " submitted_by_user_id, submitted_at, undo_of, op) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)",
                                 (rec['action_id'], rec['action_version'], rec['type_id'], rec['dataset'], rec['dataset_version'], json.dumps(rec['key'], ensure_ascii=False),
                                  json.dumps(rec['before'], ensure_ascii=False), json.dumps(rec['after'], ensure_ascii=False), rec['reason'], who, user['id'] if user else None,
                                  now_text(), rec.get('undo_of'), rec['op'])).lastrowid
        log_line(conn, who or '未署名', rec['action_id'], 'action_submitted', after={'record': record_id, **log_after})
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return record_id


def submit(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{action, key: {column: value}, params: {column: value}, reason?}: a pending record for another builder to approve. Refused (and logged) when the action is not
    confirmed, the person may not submit it or cannot read the object, a value does not fit, a condition does not hold, nothing would change, a create's key is taken,
    or a delete has no reason."""
    row = _action_row(conn, payload.get('action'), user)
    content, element_id = _content(row), row['element_id']
    kind = kind_of(content)
    attempt = {'op': 'submit', 'key': payload.get('key'), 'params': payload.get('params')}
    refuse = lambda message, status=409: _refuse(conn, who, element_id, message, attempt, status)
    if row['state'] != 'confirmed':
        refuse(f'这个行为{STATE_WORDS.get(row["state"], row["state"])}，要另一位建设者确认之后才能提交')
    type_row = element_row(conn, type_id(content['type']))
    t = _content(type_row)
    if type_row['state'] != 'confirmed':
        refuse(f'“{t["name"]}”现在不是已确认的状态，不能提交')
    submitters = content.get('submitters') or []
    if submitters and (user is None or user['id'] not in submitters):
        people = {u['id']: u['display_name'] for u in list_users(conn)}
        refuse(f'只有{"、".join(people.get(i, f"#{i}") for i in submitters)}可以提交这个行为', 403)
    dataset = current_dataset(conn, t['dataset'])
    if dataset is None:
        refuse(f'数据集“{t["dataset"]}”已经不在了')
    key = payload.get('key')
    if not isinstance(key, dict) or set(key) != set(t['key']) or any(not isinstance(v, (str, int, float)) or isinstance(v, bool) or not str(v).strip() for v in key.values()):
        refuse(f'要用主键“{" + ".join(t["key"])}”指定是哪一个对象', 400)
    reason = _reason(payload)
    if len(reason) > MAX_REASON or '\n' in reason:
        refuse(f'理由最多 {MAX_REASON} 个字，不能换行', 400)
    if kind == 'delete' and not reason:
        refuse('删除要写理由：删掉的对象之后要能说清为什么删', 400)
    props = {p['column']: p for p in t['properties']}
    names = {c: p['name'] for c, p in props.items()}
    found = _find(conn, t, dataset, key)
    english = content['type']
    if kind == 'create':
        if found is not None:
            refuse(f'已经有 {_object_text(t, {c: found[c] for c in t["key"]})}：新建不会改写已有的对象，要改它请用改的行为' if _may_read(conn, type_row, found, user)
                   else '这个主键已经被占用了：新建不会改写已有的对象')
        keyed = {c: str(key[c]).strip() for c in t['key']}
        for c in t['key']:
            if len(keyed[c]) > MAX_VALUE or '\n' in keyed[c] or not _fits(infer_type([keyed[c]]), props[c]['type']):
                refuse(f'主键“{names[c]}”的值“{keyed[c][:40]}”不能当{TYPE_NAME.get(props[c]["type"], props[c]["type"])}用', 400)
            labels = meaning_labels(conn, english, c) if props[c]['enum'] else None
            if labels is not None and keyed[c] not in labels:
                refuse(f'主键“{names[c]}”的值“{keyed[c][:40]}”不是它的含义里的取值：{"、".join(f"{v}（{l}）" for v, l in sorted(labels.items()))}', 400)
        after, wrong = _check_values(conn, content, t, payload.get('params'), user, everyone=False)
        if wrong:
            refuse(wrong, 400)
        limit = restriction(conn, type_row['element_id'], user)
        if limit is not None and not keeps({**after, **keyed}, limit):
            refuse('新对象不在你看得到的范围里：行规则会把它挡在你外面，换成你能看到的值', 409)
        before, shown = {}, _object_text(t, keyed)
        text = f'{who} 提交“{content["name"]}”：新建 {shown}，{_pairs(conn, english, list(after), after)}'
    else:
        if found is None or not _may_read(conn, type_row, found, user):
            refuse('没有这个对象，或者你看不到它', 404)
        keyed = {c: found[c] for c in t['key']}
        shown = _object_text(t, keyed)
        failed = [c for c in conditions_of(content) if not _holds(c, found.get(c['column']), props[c['column']]['type'])]
        if failed:
            c = failed[0]
            refuse(f'条件不满足：{shown} 的“{names[c["column"]]}”现在是“{_label(conn, english, c["column"], found.get(c["column"]))}”，'
                   f'这个行为要 {_phrase(conn, english, names, c)}')
        if kind == 'edit':
            after, wrong = _check_values(conn, content, t, payload.get('params'), user, everyone=False)   # only the values they may read: a refusal tells nothing of the rest
            if wrong:
                refuse(wrong, 400)
            clash = conflict_with_actions(conn, type_row['element_id'], content['properties'])
            if clash:
                refuse(clash)
            before = {c: found.get(c) for c in content['properties']}
            if all(_canonical(before[c]) == _canonical(after[c]) for c in after):
                refuse(f'{shown} 已经是这些值了，没有要改的：{_pairs(conn, english, list(before), before)}')
            text = f'{who} 提交“{content["name"]}”：{shown}，{_pairs(conn, english, list(before), before)} → {_pairs(conn, english, list(after), after)}'
        else:
            if payload.get('params') not in (None, {}):
                refuse('删除行为不带参数：删掉的是整个对象', 400)
            before, after = dict(found), {}   # the whole row, every column: an undo puts this back
            text = f'{who} 提交“{content["name"]}”：删除 {shown}（{_pairs(conn, english, _named_columns(content, t, before), before)}）'
    text += f'（{reason}）' if reason else ''
    record_id = _insert(conn, {'action_id': element_id, 'action_version': row['version'], 'type_id': type_row['element_id'], 'dataset': dataset['name'],
                               'dataset_version': dataset['version'], 'key': keyed, 'before': before, 'after': after, 'reason': reason, 'op': kind}, who, user,
                        {'text': text, 'object': shown, 'before': _of_type(t, before), 'after': _of_type(t, after), 'dataset_version': dataset['version'], 'kind': kind})
    return {'record': record_id, 'state': 'pending'}


def _write_state(conn, rec: dict, state: str, who: str | None, user: dict | None, note: str | None, why: str | None, change: str, text: str, new_version: int | None = None) -> None:
    """The record's new state and its log line, inside the caller's transaction."""
    if conn.execute('UPDATE action_record SET state = ?, decided_by = ?, decided_by_user_id = ?, decided_at = ?, note = ?, why = ?, new_version = ? WHERE id = ? AND state IN (?, ?)',
                    (state, who, user['id'] if user else None, now_text(), note, why, new_version, rec['id'], 'pending', 'needs_look')).rowcount != 1:
        raise TypeRefused('这条提交在你看过之后被处理了，请刷新', 409)
    self_decided = rec['submitted_by_user_id'] is not None and user is not None and rec['submitted_by_user_id'] == user['id']
    log_line(conn, who or '未署名', rec['action_id'], change, after={'record': rec['id'], 'text': text + ('（提交人自己批准，没有第二个人）' if self_decided and state == 'approved' else ''),
                                                                   'submitted_by': rec['submitted_by'], 'decided_by': who, 'why': why, 'version': new_version, 'self_confirmed': self_decided and state == 'approved'})


def _set_state(conn, rec: dict, state: str, who: str | None, user: dict | None, note: str | None, why: str | None, change: str, text: str, new_version: int | None = None) -> None:
    conn.execute('BEGIN IMMEDIATE')
    try:
        _write_state(conn, rec, state, who, user, note, why, change, text, new_version)
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise


def _moved(conn, t: dict, columns, then: dict, now: dict, word: str) -> list[str]:
    """'“金额”提交时是“1200”，现在是“1”', for each column whose value is not what it was."""
    names = _names(conn, t['english_name'])
    return [f'“{names.get(c, c)}”{word}是“{_label(conn, t["english_name"], c, then.get(c))}”，现在是“{_label(conn, t["english_name"], c, now.get(c))}”'
            for c in columns if _canonical(now.get(c)) != _canonical(then.get(c))]


def decide(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{id, decision: 'approve' | 'reject', note?}: another builder (the submitter only when two-person confirmation is off) approves or rejects a pending record.
    Approving writes a new version of the dataset with the action on it, unless the data moved since the submit (an edit: the dataset or the object's values; a create:
    the key was taken; a delete: the object is gone or holds other values): then the record goes to needs_look and nothing is written. Refusals are logged."""
    rec = _record(conn, payload.get('id'), user)
    expire_old(conn)
    rec = _record(conn, payload.get('id'), user)
    decision, note = payload.get('decision'), payload.get('note')
    note = note.strip() if isinstance(note, str) else ''
    if decision not in ('approve', 'reject') or len(note) > MAX_REASON or '\n' in note:
        raise TypeRefused(f'要写 approve 或 reject，说明最多 {MAX_REASON} 个字，不能换行')
    action = element_row(conn, rec['action_id'])
    content = _content(action)
    op = _op(rec)
    attempt = {'op': 'approve' if decision == 'approve' else 'reject', 'record': rec['id']}
    refuse = lambda message, status=409: _refuse(conn, who, rec['action_id'], message, attempt, status, record=rec['id'])
    if rec['state'] != 'pending' and not (rec['state'] == 'needs_look' and decision == 'reject'):
        ended = {'approved': '已批准', 'rejected': '已驳回', 'withdrawn': '已撤回', 'expired': '已过期', 'needs_look': '需要再看（数据变了，只能驳回或撤回，再重新提交）'}[rec['state']]
        raise TypeRefused(f'这条提交已经是“{ended}”，不能再{"批准" if decision == "approve" else "驳回"}', 409)
    if user is not None and user['role'] == 'viewer':
        refuse('查看者不能批准或驳回', 403)
    if two_person(conn)['active'] and user is not None and rec['submitted_by_user_id'] == user['id']:
        refuse('这条是你自己提交的，要另一位建设者来批准或驳回；想收回可以撤回', 403)
    type_row = element_row(conn, rec['type_id'])
    t = _content(type_row)
    dataset = current_dataset(conn, rec['dataset'])
    key = json.loads(rec['key_json'])
    before, after = json.loads(rec['before_json']), json.loads(rec['after_json'])
    found = _find(conn, t, dataset, key) if dataset else None
    if not _may_read(conn, type_row, _subject(op, found, key, before, after), user):
        refuse('没有这个对象，或者你看不到它', 404)
    shown = _object_text(t, key)
    if decision == 'reject':
        _set_state(conn, rec, 'rejected', who, user, note, None, 'action_rejected',
                   f'{who} 驳回了 #{rec["id"]}（{rec["submitted_by"]} 提交）：{shown}' + (f'，{note}' if note else ''))
        return {'state': 'rejected'}
    if action['state'] != 'confirmed':
        refuse(f'这个行为现在{STATE_WORDS.get(action["state"], action["state"])}，不能批准：先让它回到已确认')
    if type_row['state'] != 'confirmed':
        refuse(f'“{t["name"]}”现在不是已确认的状态，不能批准')
    if op == 'edit':
        clash = conflict_with_actions(conn, rec['type_id'], content['properties'])
        if clash:
            refuse(clash)
    if rec['action_version'] != action['version']:   # the definition was changed (and confirmed again) after the submit: what was asked is not what the action now says
        why = '行为定义在提交后变了：现在的定义不是提交时的那一版，没有写入，请按现在的定义重新提交'
        _set_state(conn, rec, 'needs_look', who, user, note, why, 'action_needs_look', f'{who} 要批准 #{rec["id"]}，但{why}')
        return {'state': 'needs_look', 'why': why}
    english = t['english_name']
    moved = []
    if dataset is None:
        moved.append(f'数据集“{rec["dataset"]}”已经不在了')
    elif op == 'edit':
        if dataset['version'] != rec['dataset_version']:
            moved.append(f'{dataset["name"]} 现在是第 {dataset["version"]} 版，提交时读的是第 {rec["dataset_version"]} 版')
        if found is None:
            moved.append(f'{shown} 已经不在数据里了')
        else:
            moved += _moved(conn, t, before, before, found, '提交时')
    elif op == 'create':
        if found is not None:
            moved.append(f'{shown} 提交后已经有了：新建不会改写它')
    elif found is None:
        moved.append(f'{shown} 已经不在数据里了')
    else:
        moved += _moved(conn, t, list(dict.fromkeys([*before, *found])), before, found, '提交时')
    if moved:
        why = '数据在提交后变了：' + '；'.join(moved)
        _set_state(conn, rec, 'needs_look', who, user, note, why, 'action_needs_look', f'{who} 要批准 #{rec["id"]}，但{why}，没有写入')
        return {'state': 'needs_look', 'why': why}
    if op == 'delete':
        written = {}
    elif op == 'create' and rec.get('undo_of') is not None:
        written = after   # an undo of a delete puts back the row that was removed, every column as it was
    else:
        written, wrong = _check_values(conn, content, t, after)
        if wrong:
            why = f'现在写不进去：{wrong}'
            _set_state(conn, rec, 'needs_look', who, user, note, why, 'action_failed', f'{who} 批准 #{rec["id"]} 失败：{why}')
            raise TypeRefused(why, 409)
    if op == 'create':
        row_now = {**written, **key}
        what = f'新建 {shown}，{_pairs(conn, english, _named_columns(content, t, row_now), row_now)}'
    elif op == 'delete':
        row_now = found
        what = f'删除 {shown}（{_pairs(conn, english, _named_columns(content, t, found), found)}）'
    else:
        row_now = {**found, **written}
        what = f'{shown}，{_pairs(conn, english, list(before), before)} → {_pairs(conn, english, list(after), after)}'
    conn.execute('BEGIN IMMEDIATE')   # the new version, the record's approved state and its log line are one write: all of it or none (the caller holds the upload lock)
    try:
        if op == 'delete':
            wanted = tuple(_canonical(str(key[c])) for c in t['key'])
            rest = [r for r in dataset_records(conn, dataset) if _key_of(r, t['key']) != wanted]
            plan = plan_upload(conn, dataset['name'], rest, mode='overwrite')
        else:
            plan = plan_upload(conn, dataset['name'], [{**{c: (found or key)[c] for c in t['key']}, **written}], mode='update_by_key', key_columns=t['key'])
            if op == 'create' and plan['changes'].get('added') != 1:
                raise ValueError(f'{shown} 没有加进去')
        plan['changes'] = {**plan['changes'], 'action': {'id': content['name'], 'record': rec['id'], **({'kind': op} if op != 'edit' else {}), 'submitted_by': rec['submitted_by'], 'approved_by': who}}
        done = apply_upload(conn, plan, who or '未署名', origin=f'action:{content["name"]}')
        if not done['created']:
            raise ValueError('写入没有改变任何数据')
        version = done['dataset']['version']
        _write_state(conn, rec, 'approved', who, user, note, None, 'action_approved',
                     f'{who} 批准了 #{rec["id"]}（{rec["submitted_by"]} 提交）：{what}；{dataset["name"]} 有了第 {version} 版', version)
        from ontology_poc_generator.notices import deliver   # notices reads this module's records
        deliver(conn, action, rec['id'], row_now, f'“{content["name"]}”：{what}（{rec["submitted_by"]} 提交，{who} 批准）', user)
        conn.execute('COMMIT')
    except TypeRefused:   # the record was decided by someone else in between
        conn.execute('ROLLBACK')
        raise
    except ValueError as exc:
        conn.execute('ROLLBACK')
        why = f'写入失败：{exc}'
        _set_state(conn, rec, 'needs_look', who, user, note, why, 'action_failed', f'{who} 批准 #{rec["id"]} 失败：{why}')
        raise TypeRefused(why, 409) from None
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    problem = recheck_after_write(conn, dataset['name'], who or '未署名')   # as after an upload, once the version stands
    return {'state': 'approved', 'version': version, 'dataset': dataset['name'], 'recheck_error': problem}


def _undone_by(conn, record_id: int) -> int | None:
    """The request that undoes this one and is waiting, needs another look, or was approved; None when there is none."""
    found = conn.execute("SELECT id FROM action_record WHERE undo_of = ? AND state IN ('pending', 'needs_look', 'approved') ORDER BY id DESC LIMIT 1", (record_id,)).fetchone()
    return found[0] if found else None


def undo(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{id, reason?}: a new pending request that takes back what an approved request did, for another builder to approve like any other (decide): an edit's values
    written back, a created object deleted, a deleted row put back. Refused when the request is not approved, when an undo of it already waits or was approved, or
    when the object changed since (an edit's or a create's values are no longer what was written; a deleted key is in use again): then a person submits what they
    want from what is there now."""
    rec = _record(conn, payload.get('id'), user)
    attempt = {'op': 'undo', 'record': rec['id']}
    refuse = lambda message, status=409: _refuse(conn, who, rec['action_id'], message, attempt, status, record=rec['id'])
    type_row = element_row(conn, rec['type_id'])
    t = _content(type_row)
    op = _op(rec)
    dataset = current_dataset(conn, rec['dataset'])
    key = json.loads(rec['key_json'])
    was, wrote = json.loads(rec['before_json']), json.loads(rec['after_json'])
    found = _find(conn, t, dataset, key) if dataset else None
    if not _may_read(conn, type_row, _subject(op, found, key, was, wrote), user):   # first: nothing about the request is said to someone who may not read its object
        refuse('没有这个对象，或者你看不到它', 404)
    if rec['state'] != 'approved':
        refuse('只有已批准的提交可以撤销：还在等批准的，提交的人可以撤回，别人可以驳回')
    if _undone_by(conn, rec['id']) is not None:
        refuse(f'#{rec["id"]} 已经撤销过，或者有一条撤销在等批准')
    action = element_row(conn, rec['action_id'])
    content = _content(action)
    if action['state'] != 'confirmed':
        refuse(f'这个行为现在{STATE_WORDS.get(action["state"], action["state"])}，要回到已确认才能提交撤销')
    submitters = content.get('submitters') or []
    if submitters and (user is None or user['id'] not in submitters):   # an undo is a submit like any other
        people = {u['id']: u['display_name'] for u in list_users(conn)}
        refuse(f'只有{"、".join(people.get(i, f"#{i}") for i in submitters)}可以提交这个行为，撤销也一样', 403)
    shown = _object_text(t, key)
    english = t['english_name']
    reason = _reason(payload)
    if len(reason) > MAX_REASON or '\n' in reason:
        refuse(f'理由最多 {MAX_REASON} 个字，不能换行', 400)
    if op == 'delete':
        if dataset is None:
            refuse(f'数据集“{rec["dataset"]}”已经不在了')
        if found is not None:
            refuse(f'{shown} 删除后又有了：不能直接撤销，请按现在的数据另外处理')
        new_op, before, after = 'create', {}, was
        text = f'{who} 提交撤销 #{rec["id"]}（“{content["name"]}”）：把删掉的 {shown} 放回去'
    else:
        if found is None:
            refuse(f'{shown} 已经不在数据里了，没法撤销')
        if op == 'edit' and set(wrote) != set(content['properties']):
            refuse(f'行为的定义变了：#{rec["id"]} 改的是 {"、".join(wrote)}，现在这个行为改的是 {"、".join(content["properties"])}。不能用它撤销，请按现在的值另外提交')
        moved = _moved(conn, t, wrote, wrote, found, '批准时写成')
        if moved:
            refuse(f'{shown} 批准后又改过：{"；".join(moved)}。不能直接撤销，请按现在的值另外提交')
        if op == 'create':
            new_op, before, after = 'delete', dict(found), {}
            text = f'{who} 提交撤销 #{rec["id"]}（“{content["name"]}”）：删掉新建的 {shown}'
        else:
            new_op, before, after = 'edit', {c: found.get(c) for c in wrote}, was
            text = f'{who} 提交撤销 #{rec["id"]}（“{content["name"]}”）：{shown}，{_pairs(conn, english, list(before), before)} → {_pairs(conn, english, list(after), after)}'
    text += f'（{reason}）' if reason else ''
    record_id = _insert(conn, {'action_id': rec['action_id'], 'action_version': action['version'], 'type_id': rec['type_id'], 'dataset': dataset['name'],
                               'dataset_version': dataset['version'], 'key': key, 'before': before, 'after': after, 'reason': reason or f'撤销 #{rec["id"]}',
                               'op': new_op, 'undo_of': rec['id']}, who, user,
                        {'undo_of': rec['id'], 'text': text, 'object': shown, 'before': _of_type(t, before), 'after': _of_type(t, after), 'dataset_version': dataset['version'], 'kind': new_op})
    return {'record': record_id, 'state': 'pending', 'undo_of': rec['id']}


def withdraw(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{id}: the person who submitted a record takes it back (pending or needing another look)."""
    rec = _record(conn, payload.get('id'), user)
    if user is None or rec['submitted_by_user_id'] != user['id']:
        raise TypeRefused('只有提交的人可以撤回', 403)
    if rec['state'] not in ('pending', 'needs_look'):
        raise TypeRefused('这条提交已经处理过了', 409)
    _set_state(conn, rec, 'withdrawn', who, user, None, None, 'action_withdrawn', f'{who} 撤回了 #{rec["id"]}')
    return {'state': 'withdrawn'}



# --- an upload that would write over what an action wrote ------------------------------------------------------------------------------------------------

def overwritten_by_upload(conn, name: str, current: list[dict], incoming: list[dict]) -> list[dict]:
    """The rows an action wrote into this dataset that the version `incoming` would change back or drop: [{'key', 'columns', 'action', 'record', 'approved_by'}].
    A warning for the upload's answer; it does not block. `current` and `incoming` are the rows of the current version and of the one about to be written."""
    done = _records(conn, "state = 'approved' AND dataset = ?", (name,))
    if not done:
        return []
    out, seen = [], set()
    for rec in done:   # newest first: a later action on the same cell is the one to name
        t = _content(element_row(conn, rec['type_id'])) if element_row(conn, rec['type_id']) else None
        if t is None:
            continue
        key = json.loads(rec['key_json'])
        wanted = tuple(_canonical(str(key[c])) for c in t['key'])
        was = next((r for r in current if _key_of(r, t['key']) == wanted), None)
        now = next((r for r in incoming if _key_of(r, t['key']) == wanted), None)
        if was is None:
            continue
        columns = [c for c, v in json.loads(rec['after_json']).items() if (rec['id'], c) not in seen and _canonical(was.get(c)) == _canonical(v)
                   and (now is None or _canonical(now.get(c)) != _canonical(was.get(c)))]
        seen.update((rec['id'], c) for c in columns)
        if columns or (now is None and (rec['id'], '') not in seen):
            seen.add((rec['id'], ''))
            out.append({'key': ' + '.join(str(key[c]) for c in t['key']), 'columns': columns, 'removed': now is None, 'action': _content(element_row(conn, rec['action_id']))['name'],
                        'record': rec['id'], 'approved_by': rec['decided_by']})
    return out
