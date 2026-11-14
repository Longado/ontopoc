"""Actions: the one way a person changes data in the workspace. v1 has one kind, an edit: on one object type, change one or more properties of one object.

The definition is an element like the others (objaction:<name>, the name is the id and is fixed): a name, the type, the properties it writes, and one optional
condition "property = value" the object has to meet for the action to be allowed. A person puts it forward (checked), another builder confirms it; it reads its
type and the meanings of the code columns it writes or tests (element_dep), so it goes to needs_look when one of them does. An action that writes a property a row
rule on its type reads cannot be confirmed (row_rules says why). The parameters are the written properties; one with confirmed meanings takes one of them (a
code and its label), the others a value that fits the property's type.

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

from ontology_poc_generator.accounts import two_person
from ontology_poc_generator.object_types import (
    ACTION_PREFIX, MAX_DESCRIPTION, MAX_NAME, TYPE_NAME, TypeRefused, _content, _edit_names, _state_view, _text, _type_row, _visible,
    element_row, enum_id, log_entries, recheck_after_write, type_id, write_confirmation, write_elements)
from ontology_poc_generator.object_views import meaning_labels
from ontology_poc_generator.row_rules import conflict_with_actions, keeps, restriction
from ontology_poc_generator.workspace_store import (
    _canonical, _key_of, apply_upload, current_dataset, dataset_records, infer_type, log_line, now_text, plan_upload)

EXPIRE_DAYS = 14
MAX_PROPERTIES = 5
MAX_REASON = 300
MAX_VALUE = 500   # a text value goes into the dataset, the pending record and the log
STATE_WORDS = {'proposed': '还是模型的草稿', 'checked': '还没有另一位确认', 'needs_look': '需要再看', 'rejected': '被退回了'}


def action_id(name: str) -> str:
    return f'{ACTION_PREFIX}{name}'


# --- the definition a person writes -------------------------------------------------------------------------------------------------------------------

def check_definition(conn, payload: dict, user: dict | None, name: str | None = None) -> dict:
    """The content of an action as a person wrote it: a name, a type this person may see, the properties it writes (not the key), and an optional condition on one
    property of the object. TypeRefused says what is wrong."""
    name = _text(payload.get('name') if name is None else name, '行为的名字', MAX_NAME)
    description = _text(payload.get('description') or '', '说明', MAX_DESCRIPTION, required=False)
    t = _content(_type_row(conn, payload.get('type'), user))
    columns = payload.get('properties')
    if not isinstance(columns, list) or not columns or len(columns) > MAX_PROPERTIES or not all(isinstance(c, str) for c in columns) or len(set(columns)) != len(columns):
        raise TypeRefused(f'要选 1 到 {MAX_PROPERTIES} 个要改的属性，不重复')
    props = {p['column']: p for p in t['properties']}
    for column in columns:
        if column not in props:
            raise TypeRefused(f'“{column}”不是“{t["name"]}”的属性')
        if column in t['key']:
            raise TypeRefused(f'“{column}”是主键，行为不能改它：主键决定改的是哪一个对象')
        if props[column]['enum'] and element_row(conn, enum_id(t['english_name'], column)) is None:
            raise TypeRefused(f'“{column}”是代码列，先给它写含义：行为的参数要从含义里选')
    condition = payload.get('condition')
    if condition is not None:
        column, value = (condition.get('column'), condition.get('value')) if isinstance(condition, dict) else (None, None)
        if column not in props:
            raise TypeRefused('条件要选对象的一个属性')
        value = str(value).strip() if isinstance(value, (str, int)) and not isinstance(value, bool) else ''
        if not value or len(value) > 100 or '\n' in value:
            raise TypeRefused('条件的取值要写 1 到 100 个字，不能换行')
        if props[column]['enum'] and value not in meaning_labels(conn, t['english_name'], column):
            raise TypeRefused(f'“{value}”不是“{column}”已写含义里的取值')
        condition = {'column': column, 'value': value}
    clash = conflict_with_actions(conn, type_id(t['english_name']), columns)
    if clash:
        raise TypeRefused(clash, 409)
    return {'name': name, 'description': description, 'type': t['english_name'], 'properties': list(columns), 'condition': condition}


def check_names_free(conn, content: dict) -> None:
    mine = action_id(content['name'])
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objaction:%'"):
        if element_id != mine and element_id.casefold() == mine.casefold():
            raise TypeRefused(f'已经有叫“{element_id[len(ACTION_PREFIX):]}”的行为（名字不分大小写）', 409)


def _reset_reasons(old: dict, new: dict) -> list[str]:
    return [label for key, label in (('type', '对象类型'), ('properties', '要改的属性'), ('condition', '条件')) if old[key] != new[key]]


def _enum_columns(content: dict) -> list[str]:
    return list(dict.fromkeys([*content['properties'], *([content['condition']['column']] if content['condition'] else [])]))


def _reads(conn, content: dict) -> list[str]:
    t = _content(element_row(conn, type_id(content['type'])))
    coded = {p['column'] for p in t['properties'] if p['enum']}
    return [type_id(content['type']), *(enum_id(content['type'], c) for c in _enum_columns(content) if c in coded)]


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
    """The definition as a sentence: 改 订单 的「状态码」；只在 状态码 是「生产中」时可以提交."""
    t = _content(element_row(conn, type_id(content['type'])))
    names = {p['column']: p['name'] for p in t['properties']}
    cond = content['condition']
    when = ''
    if cond:
        when = f'；只在 {names[cond["column"]]} 是「{_label(conn, content["type"], cond["column"], cond["value"])}」时可以提交'
    return f'改 {t["name"]} 的{"、".join(f"「{names[c]}」" for c in content["properties"])}{when}'


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
        raise TypeRefused(f'行为用到的{"、".join(f"“{w["name"]}”" for w in waiting)}还没有确认，要先确认它们', 409)
    clash = conflict_with_actions(conn, type_id(content['type']), content['properties'])
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
    type_row = element_row(conn, type_id(_content(row)['type']))
    return type_row is not None and _visible(conn, type_row, user)


def action_state(conn, row: dict, user: dict | None) -> dict:
    state = _state_view(conn, row, user)
    waiting = waiting_on(conn, _content(row))
    return {**state, 'can_confirm': state['can_confirm'] and not waiting, 'waiting_on': waiting}


def parameters(conn, content: dict) -> list[dict]:
    """The parameters the action asks for: each written property with its type and, for a code column, the meanings to pick from."""
    t = _content(element_row(conn, type_id(content['type'])))
    props = {p['column']: p for p in t['properties']}
    out = []
    for column in content['properties']:
        labels = meaning_labels(conn, content['type'], column) if props[column]['enum'] else None
        out.append({'column': column, 'name': props[column]['name'], 'type': props[column]['type'], 'type_name': TYPE_NAME[props[column]['type']],
                    'options': None if labels is None else [{'value': v, 'label': labels[v]} for v in sorted(labels, key=lambda v: (not v.lstrip('-').isdigit(), int(v) if v.lstrip('-').isdigit() else 0, v))]})
    return out


def _line(conn, row: dict, user: dict | None) -> dict:
    content = _content(row)
    t = _content(element_row(conn, type_id(content['type'])))
    cond = content['condition']
    return {'id': content['name'], 'name': content['name'], 'description': content['description'], 'type': content['type'], 'type_name': t['name'], 'properties': content['properties'],
            'condition': cond and {**cond, 'label': _label(conn, content['type'], cond['column'], cond['value']), 'name': next(p['name'] for p in t['properties'] if p['column'] == cond['column'])},
            'says': describe(conn, content), 'parameters': parameters(conn, content), **action_state(conn, row, user)}


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
    t = _content(_type_row(conn, english_name, user))
    return {'properties': [{'column': p['column'], 'name': p['name'], 'enum': p['enum'], 'labels': sorted(set(meaning_labels(conn, english_name, p['column']).values())) if p['enum'] else None,
                            'values': [{'value': v, 'label': l} for v, l in sorted(meaning_labels(conn, english_name, p['column']).items())] if p['enum'] else None}
                           for p in t['properties'] if p['column'] not in t['key']]}


def action_detail(conn, name: str, user: dict | None) -> dict:
    row = _action_row(conn, name, user)
    expire_old(conn)
    records = [record_view(conn, r, user) for r in _records(conn, 'action_id = ?', (row['element_id'],), limit=50)]
    return {**_line(conn, row, user), 'records': [r for r in records if r], 'log': log_entries(conn, [row['element_id']], user)}


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


def _pairs(conn, content: dict, values: dict) -> str:
    t = _content(element_row(conn, type_id(content['type'])))
    names = {p['column']: p['name'] for p in t['properties']}
    return '，'.join(f'{names[c]} {_label(conn, content["type"], c, values.get(c))}' for c in content['properties'])


def _change(conn, content: dict, before: dict, after: dict) -> str:
    """'状态码 从 生产中 改成 已交付', one clause per property the action writes."""
    t = _content(element_row(conn, type_id(content['type'])))
    names = {p['column']: p['name'] for p in t['properties']}
    label = lambda c, v: _label(conn, content['type'], c, v)
    return '，'.join(f'{names[c]} 从 {label(c, before.get(c))} 改成 {label(c, after.get(c))}' for c in content['properties'])


def record_view(conn, rec: dict, user: dict | None, light: bool = False) -> dict | None:
    """One record as a page shows it; None when this person may not read the object it is about (a person never reads a row a rule keeps from them)."""
    action = element_row(conn, rec['action_id'])
    type_row = element_row(conn, rec['type_id'])
    if action is None or type_row is None:
        return None
    content, t = _content(action), _content(type_row)
    dataset = current_dataset(conn, rec['dataset'])
    current = _find(conn, t, dataset, json.loads(rec['key_json'])) if dataset else None
    if not _may_read(conn, type_row, current, user):
        return None
    key, before, after = json.loads(rec['key_json']), json.loads(rec['before_json']), json.loads(rec['after_json'])
    same_person = user is not None and rec['submitted_by_user_id'] is not None and user['id'] == rec['submitted_by_user_id']
    rule = two_person(conn)
    can_decide = (rec['state'] == 'pending' and user is not None and user['role'] != 'viewer' and not (same_person and rule['active']))
    return {'id': rec['id'], 'action': content['name'], 'type': t['english_name'], 'type_name': t['name'], 'object': _object_text(t, key), 'key': key,
            'before_text': _pairs(conn, content, before), 'after_text': _pairs(conn, content, after), 'change_text': _change(conn, content, before, after), 'before': before, 'after': after, 'reason': rec['reason'],
            'state': rec['state'], 'submitted_by': rec['submitted_by'], 'submitted_at': rec['submitted_at'], 'decided_by': rec['decided_by'], 'decided_at': rec['decided_at'],
            'note': rec['note'], 'why': rec['why'], 'new_version': rec['new_version'], 'dataset': rec['dataset'], 'dataset_version': rec['dataset_version'],
            'dataset_now': dataset['version'] if dataset else None, 'stale': rec['state'] == 'pending' and (dataset is None or dataset['version'] != rec['dataset_version']),
            'can_decide': can_decide, 'can_withdraw': rec['state'] in ('pending', 'needs_look') and same_person}


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
    what = {'submit': '提交', 'approve': '批准', 'reject': '驳回'}[attempt['op']]
    log_line(conn, who or '未署名', element_id, change, after={'record': record, 'text': f'{who or "未署名"} 的{what}被拒：{message}', 'reason': message, 'attempt': attempt})
    raise TypeRefused(message, status)


def _fits(kind: str, wanted: str) -> bool:
    return wanted == 'text' or kind == wanted or (wanted == 'decimal' and kind == 'integer') or (wanted == 'datetime' and kind == 'date')


def _check_values(conn, content: dict, t: dict, params) -> tuple[dict, str | None]:
    """(the values as strings, what is wrong in words or None): a value for every written property and no other, of the property's type, a code column's from its
    meanings."""
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
        out[column] = text
    return out, None


def submit(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{action, key: {column: value}, params: {column: value}, reason?}: a pending record for another builder to approve. Refused (and logged) when the action is not
    confirmed, the person cannot read the object, a value does not fit, the condition does not hold or nothing would change."""
    row = _action_row(conn, payload.get('action'), user)
    content, element_id = _content(row), row['element_id']
    attempt = {'op': 'submit', 'key': payload.get('key'), 'params': payload.get('params')}
    refuse = lambda message, status=409: _refuse(conn, who, element_id, message, attempt, status)
    if row['state'] != 'confirmed':
        refuse(f'这个行为{STATE_WORDS.get(row["state"], row["state"])}，要另一位构建者确认之后才能提交')
    type_row = element_row(conn, type_id(content['type']))
    t = _content(type_row)
    if type_row['state'] != 'confirmed':
        refuse(f'“{t["name"]}”现在不是已确认的状态，不能提交')
    dataset = current_dataset(conn, t['dataset'])
    if dataset is None:
        refuse(f'数据集“{t["dataset"]}”已经不在了')
    key = payload.get('key')
    if not isinstance(key, dict) or set(key) != set(t['key']) or any(not isinstance(v, (str, int, float)) or isinstance(v, bool) or not str(v).strip() for v in key.values()):
        refuse(f'要用主键“{" + ".join(t["key"])}”指定是哪一个对象', 400)
    found = _find(conn, t, dataset, key)
    if found is None or not _may_read(conn, type_row, found, user):
        refuse('没有这个对象，或者你看不到它', 404)
    reason = payload.get('reason')
    reason = reason.strip() if isinstance(reason, str) else ''
    if len(reason) > MAX_REASON or '\n' in reason:
        refuse(f'理由最多 {MAX_REASON} 个字，不能换行', 400)
    after, wrong = _check_values(conn, content, t, payload.get('params'))
    if wrong:
        refuse(wrong, 400)
    clash = conflict_with_actions(conn, type_row['element_id'], content['properties'])
    if clash:
        refuse(clash)
    cond = content['condition']
    shown = _object_text(t, {c: found[c] for c in t['key']})
    if cond and _canonical(found.get(cond['column'])) != _canonical(cond['value']):
        names = {p['column']: p['name'] for p in t['properties']}
        refuse(f'条件不满足：{shown} 的“{names[cond["column"]]}”现在是“{_label(conn, content["type"], cond["column"], found.get(cond["column"]))}”，'
               f'这个行为要它是“{_label(conn, content["type"], cond["column"], cond["value"])}”')
    before = {c: found.get(c) for c in content['properties']}
    if all(_canonical(before[c]) == _canonical(after[c]) for c in after):
        refuse(f'{shown} 已经是这些值了，没有要改的：{_pairs(conn, content, before)}')
    keyed = {c: found[c] for c in t['key']}
    text = f'{who} 提交“{content["name"]}”：{shown}，{_pairs(conn, content, before)} → {_pairs(conn, content, after)}' + (f'（{reason}）' if reason else '')
    conn.execute('BEGIN IMMEDIATE')
    try:
        record_id = conn.execute('INSERT INTO action_record(action_id, action_version, type_id, dataset, dataset_version, key_json, before_json, after_json, reason, state, submitted_by,'
                                 " submitted_by_user_id, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
                                 (element_id, row['version'], type_row['element_id'], dataset['name'], dataset['version'], json.dumps(keyed, ensure_ascii=False),
                                  json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), reason, who, user['id'] if user else None, now_text())).lastrowid
        log_line(conn, who or '未署名', element_id, 'action_submitted', after={'record': record_id, 'text': text, 'object': shown, 'before': before, 'after': after, 'dataset_version': dataset['version']})
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
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


def decide(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{id, decision: 'approve' | 'reject', note?}: another builder (the submitter only when two-person confirmation is off) approves or rejects a pending record.
    Approving writes a new version of the dataset by key with the action on it, unless the data moved since the submit: then the record goes to needs_look and nothing
    is written. Refusals are logged on the action."""
    rec = _record(conn, payload.get('id'), user)
    expire_old(conn)
    rec = _record(conn, payload.get('id'), user)
    decision, note = payload.get('decision'), payload.get('note')
    note = note.strip() if isinstance(note, str) else ''
    if decision not in ('approve', 'reject') or len(note) > MAX_REASON or '\n' in note:
        raise TypeRefused(f'要写 approve 或 reject，说明最多 {MAX_REASON} 个字，不能换行')
    action = element_row(conn, rec['action_id'])
    content = _content(action)
    attempt = {'op': 'approve' if decision == 'approve' else 'reject', 'record': rec['id']}
    refuse = lambda message, status=409: _refuse(conn, who, rec['action_id'], message, attempt, status, record=rec['id'])
    if rec['state'] != 'pending' and not (rec['state'] == 'needs_look' and decision == 'reject'):
        ended = {'approved': '已批准', 'rejected': '已驳回', 'withdrawn': '已撤回', 'expired': '已过期', 'needs_look': '需要再看（数据变了，只能驳回或撤回，再重新提交）'}[rec['state']]
        raise TypeRefused(f'这条提交已经是“{ended}”，不能再{"批准" if decision == "approve" else "驳回"}', 409)
    if user is not None and user['role'] == 'viewer':
        refuse('查看者不能批准或驳回', 403)
    if two_person(conn)['active'] and user is not None and rec['submitted_by_user_id'] == user['id']:
        refuse('这条是你自己提交的，要另一位构建者来批准或驳回；想收回可以撤回', 403)
    type_row = element_row(conn, rec['type_id'])
    t = _content(type_row)
    dataset = current_dataset(conn, rec['dataset'])
    key = json.loads(rec['key_json'])
    found = _find(conn, t, dataset, key) if dataset else None
    if not _may_read(conn, type_row, found, user):
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
    clash = conflict_with_actions(conn, rec['type_id'], content['properties'])
    if clash:
        refuse(clash)
    if rec['action_version'] != action['version']:   # the definition was changed (and confirmed again) after the submit: what was asked is not what the action now says
        why = '行为定义在提交后变了：现在的定义不是提交时的那一版，没有写入，请按现在的定义重新提交'
        _set_state(conn, rec, 'needs_look', who, user, note, why, 'action_needs_look', f'{who} 要批准 #{rec["id"]}，但{why}')
        return {'state': 'needs_look', 'why': why}
    before, after = json.loads(rec['before_json']), json.loads(rec['after_json'])
    moved = []
    if dataset is None:
        moved.append(f'数据集“{rec["dataset"]}”已经不在了')
    else:
        if dataset['version'] != rec['dataset_version']:
            moved.append(f'{dataset["name"]} 现在是第 {dataset["version"]} 版，提交时读的是第 {rec["dataset_version"]} 版')
        if found is None:
            moved.append(f'{shown} 已经不在数据里了')
        else:
            moved += [f'“{c}”提交时是“{_label(conn, t["english_name"], c, before[c])}”，现在是“{_label(conn, t["english_name"], c, found.get(c))}”'
                      for c in before if _canonical(found.get(c)) != _canonical(before[c])]
    if moved:
        why = '数据在提交后变了：' + '；'.join(moved)
        _set_state(conn, rec, 'needs_look', who, user, note, why, 'action_needs_look', f'{who} 要批准 #{rec["id"]}，但{why}，没有写入')
        return {'state': 'needs_look', 'why': why}
    written, wrong = _check_values(conn, content, t, after)
    if wrong:
        why = f'现在写不进去：{wrong}'
        _set_state(conn, rec, 'needs_look', who, user, note, why, 'action_failed', f'{who} 批准 #{rec["id"]} 失败：{why}')
        raise TypeRefused(why, 409)
    conn.execute('BEGIN IMMEDIATE')   # the new version, the record's approved state and its log line are one write: all of it or none (the caller holds the upload lock)
    try:
        plan = plan_upload(conn, dataset['name'], [{**{c: found[c] for c in t['key']}, **written}], mode='update_by_key', key_columns=t['key'])
        plan['changes'] = {**plan['changes'], 'action': {'id': content['name'], 'record': rec['id'], 'submitted_by': rec['submitted_by'], 'approved_by': who}}
        done = apply_upload(conn, plan, who or '未署名', origin=f'action:{content["name"]}')
        if not done['created']:
            raise ValueError('写入没有改变任何数据')
        version = done['dataset']['version']
        _write_state(conn, rec, 'approved', who, user, note, None, 'action_approved',
                     f'{who} 批准了 #{rec["id"]}（{rec["submitted_by"]} 提交）：{shown}，{_pairs(conn, content, before)} → {_pairs(conn, content, after)}；{dataset["name"]} 有了第 {version} 版', version)
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
