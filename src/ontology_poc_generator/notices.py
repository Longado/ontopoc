"""Notices: who an action tells when one of its changes is approved, and each person's list of what they were told.

An action names up to five recipients, each one of:
- {'kind': 'people', 'user_ids': [...]}: these people;
- {'kind': 'attr', 'column': <a property of the action's type>, 'user_attr': <a person's attribute>}: the people whose attribute equals that column of the row;
- {'kind': 'via', 'relation': <a relation with the action's type at one end>, 'column': <a property of the other end>, 'user_attr': ...}: the people whose attribute
  equals that column of the object the row points to through the relation.

The list is not part of what is confirmed (it changes who hears, not what is written): a builder who may see the action and every type it names sets it, and the
change goes to the action's log. When a change is approved, each person found is told unless they approved it themselves, are disabled, or may not read the row (the
type, a column the action reads kept from them, a row rule): a notice quotes the row. Nobody is told twice of one change.
"""
from __future__ import annotations

import json

from ontology_poc_generator.accounts import MAX_ATTR_NAME, list_users
from ontology_poc_generator.object_types import TypeRefused, _content, _visible, element_row, type_id, whole_type_row
from ontology_poc_generator.row_rules import keeps, restriction
from ontology_poc_generator.type_access import hidden_columns, reads_hidden
from ontology_poc_generator.workspace_store import _canonical, current_dataset, dataset_records, log_line, now_text

MAX_RECIPIENTS = 5
LISTED = 100


def recipients_of(conn, action_element_id: str) -> list[dict]:
    row = conn.execute('SELECT spec_json FROM action_notify WHERE action_id = ?', (action_element_id,)).fetchone()
    return json.loads(row[0]) if row else []


def _relation(conn, name) -> dict | None:
    row = element_row(conn, f'relation:{name}') if isinstance(name, str) else None
    return _content(row) if row else None


def _other_end(relation: dict, english: str) -> tuple[str, str, str] | None:
    """(this end's column, the other type, the other end's column) when the relation has the action's type at one end and another type at the other."""
    for here, there in (('from', 'to'), ('to', 'from')):
        if relation[here] == english and relation[there] != english:
            return relation[f'{here}_column'], relation[there], relation[f'{there}_column']
    return None


def lines(conn, recipients: list[dict], type_name: str) -> list[str]:
    """Each recipient in words, for the action page and the log."""
    names = {u['id']: u['display_name'] for u in list_users(conn)}
    out = []
    for r in recipients:
        if r['kind'] == 'people':
            out.append('、'.join(names.get(i, f'#{i}') for i in r['user_ids']))
        elif r['kind'] == 'attr':
            out.append(f'{r["column"]} = 自己的{r["user_attr"]} 的人')
        else:
            relation = _relation(conn, r['relation']) or {}
            other = element_row(conn, type_id(relation.get('to') if relation.get('from') == type_name else relation.get('from', '')))
            out.append(f'经关系“{relation.get("name", r["relation"])}”，{_content(other)["name"] if other else "另一端"}的 {r["column"]} = 自己的{r["user_attr"]} 的人')
    return out


def set_notify(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{action, recipients}: replace who the action tells. Returns {'recipients', 'lines'}."""
    from ontology_poc_generator.object_actions import _action_row, action_id   # object_actions tells people through this module
    row = _action_row(conn, payload.get('action'), user)
    content = _content(row)
    t = _content(whole_type_row(conn, content['type'], user))   # a type with a column kept from them: not theirs to name people on
    recipients = payload.get('recipients')
    if not isinstance(recipients, list) or len(recipients) > MAX_RECIPIENTS or not all(isinstance(r, dict) for r in recipients):
        raise TypeRefused(f'通知对象要写成列表，最多 {MAX_RECIPIENTS} 项')
    properties = {p['column'] for p in t['properties']}
    known = {u['id'] for u in list_users(conn) if not u['disabled']}
    clean = []
    for r in recipients:
        kind = r.get('kind')
        attr = r.get('user_attr').strip() if isinstance(r.get('user_attr'), str) else ''
        if kind == 'people':
            ids = r.get('user_ids')
            if not isinstance(ids, list) or not ids or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids) or set(ids) - known:
                raise TypeRefused('点名要选至少一个在用的账号')
            clean.append({'kind': 'people', 'user_ids': sorted(set(ids))})
            continue
        if kind not in ('attr', 'via'):
            raise TypeRefused('通知对象只能是点名的人、按人的属性，或经一个关系按人的属性')
        if not attr or len(attr) > MAX_ATTR_NAME or not attr.isprintable():
            raise TypeRefused(f'人的属性名要写 1 到 {MAX_ATTR_NAME} 个字，不能换行')
        if kind == 'attr':
            if r.get('column') not in properties:
                raise TypeRefused(f'“{r.get("column")}”不是“{t["name"]}”的属性')
            clean.append({'kind': 'attr', 'column': r['column'], 'user_attr': attr})
            continue
        relation = _relation(conn, r.get('relation'))
        if relation and relation['from'] == relation['to']:
            raise TypeRefused(f'关系“{relation["name"]}”两端都是“{t["name"]}”，分不清从哪一端找人，这一版还不能用')
        ends = _other_end(relation, content['type']) if relation else None
        if ends is None:
            raise TypeRefused(f'没有一端是“{t["name"]}”的关系“{r.get("relation")}”', 400)
        other = _content(whole_type_row(conn, ends[1], user))
        if r.get('column') not in {p['column'] for p in other['properties']}:
            raise TypeRefused(f'“{r.get("column")}”不是“{other["name"]}”的属性')
        clean.append({'kind': 'via', 'relation': r['relation'], 'column': r['column'], 'user_attr': attr})
    before = recipients_of(conn, row['element_id'])
    if clean != before:
        conn.execute('BEGIN IMMEDIATE')
        try:
            conn.execute('DELETE FROM action_notify WHERE action_id = ?', (row['element_id'],))
            if clean:
                conn.execute('INSERT INTO action_notify(action_id, spec_json) VALUES (?, ?)', (row['element_id'], json.dumps(clean, ensure_ascii=False)))
            said = lines(conn, clean, content['type'])
            log_line(conn, who or '未署名', row['element_id'], 'notify_changed', before={'lines': lines(conn, before, content['type'])},
                     after={'lines': said, 'summary': '批准后通知：' + ('；'.join(said) or '不通知任何人')})
            conn.execute('COMMIT')
        except BaseException:
            conn.execute('ROLLBACK')
            raise
    return {'recipients': clean, 'lines': lines(conn, clean, content['type'])}


def _matching(people: list[dict], attr: str, value) -> list[dict]:
    wanted = _canonical(value)
    return [p for p in people if wanted not in (None, '') and _canonical((p.get('attrs') or {}).get(attr)) == wanted]


def deliver(conn, action_row: dict, record_id: int, row: dict, text: str, approver: dict | None) -> int:
    """Tell the people the action names that this change (to `row`, as it is after the change) was approved. Runs inside the approval's write. Returns how many."""
    recipients = recipients_of(conn, action_row['element_id'])
    if not recipients:
        return 0
    content = _content(action_row)
    people = [p for p in list_users(conn) if not p['disabled']]
    found: dict[int, dict] = {}
    for r in recipients:
        try:   # a recipient that no longer fits (a relation edited or gone) is skipped: telling people never stops the change itself
            if r['kind'] == 'people':
                found.update({p['id']: p for p in people if p['id'] in r['user_ids']})
            elif r['kind'] == 'attr':   # matched on that column: someone kept from it is not found through it
                found.update({p['id']: p for p in _matching(people, r['user_attr'], row.get(r['column']))
                              if r['column'] not in hidden_columns(conn, type_id(content['type']), p)})
            else:
                relation = _relation(conn, r['relation'])
                ends = _other_end(relation, content['type']) if relation else None
                other = element_row(conn, type_id(ends[1])) if ends else None
                dataset = current_dataset(conn, _content(other)['dataset']) if other else None
                if dataset is None:
                    continue
                link = _canonical(row.get(ends[0]))
                for there in (rec for rec in dataset_records(conn, dataset) if link not in (None, '') and _canonical(rec.get(ends[2])) == link):   # every object it points to
                    for p in _matching(people, r['user_attr'], there.get(r['column'])):
                        limit = restriction(conn, other['element_id'], p)   # found through the other type: only by a row and a column of it they may read
                        if _visible(conn, other, p) and r['column'] not in hidden_columns(conn, other['element_id'], p) and (limit is None or keeps(there, limit)):
                            found[p['id']] = p
        except (KeyError, TypeError, AttributeError):
            continue
    type_row = element_row(conn, type_id(content['type']))
    told = 0
    for person in found.values():
        if approver is not None and person['id'] == approver.get('id'):
            continue
        limit = restriction(conn, type_row['element_id'], person)
        if not _visible(conn, type_row, person) or reads_hidden(conn, action_row['element_id'], person, content) or (limit is not None and not keeps(row, limit)):
            continue
        conn.execute('INSERT INTO notice(user_id, at, action_name, record_id, text) VALUES (?, ?, ?, ?, ?)', (person['id'], now_text(), content['name'], record_id, text))
        told += 1
    return told


def _still_readable(conn, record_id: int | None, user: dict, cache: dict | None = None) -> bool:
    """Whether this person may still read what a notice quotes: the action (its columns not kept from them), its type, and the object's row as it is now (a row rule
    added since keeps it from them: not shown). A notice whose record or action is gone is not shown either."""
    cache = {} if cache is None else cache
    rec = conn.execute('SELECT action_id, type_id, dataset, key_json FROM action_record WHERE id = ?', (record_id,)).fetchone() if record_id is not None else None
    action, type_row = (element_row(conn, rec[0]), element_row(conn, rec[1])) if rec else (None, None)
    if action is None or type_row is None or not _visible(conn, type_row, user) or reads_hidden(conn, rec[0], user, _content(action)):
        return False
    if type_row['element_id'] not in cache:   # once per type in one listing: the limit and the rows it keeps, by key
        limit = restriction(conn, type_row['element_id'], user)
        dataset = current_dataset(conn, rec[2]) if limit is not None else None
        key = _content(type_row)['key']
        kept = {tuple(_canonical(r.get(c)) for c in key) for r in dataset_records(conn, dataset) if keeps(r, limit)} if dataset else set()
        cache[type_row['element_id']] = (limit, key, kept)
    limit, key, kept = cache[type_row['element_id']]
    if limit is None:
        return True
    wanted = json.loads(rec[3])
    return tuple(_canonical(wanted.get(c)) for c in key) in kept


def list_notices(conn, user: dict | None) -> dict:
    """This person's notices, newest first (the last LISTED that they may still read), and how many of those are unread. Each is checked again as it is read:
    access taken away since (the type, a column, a row rule) takes the notice with it."""
    if user is None or user.get('id') is None:
        return {'notices': [], 'unread': 0}
    rows = conn.execute('SELECT id, at, action_name, record_id, text, read_at FROM notice WHERE user_id = ? ORDER BY id DESC LIMIT ?', (user['id'], LISTED)).fetchall()
    cache: dict = {}
    shown = [{'id': i, 'at': at, 'action': a, 'record': r, 'text': t, 'read': read is not None} for i, at, a, r, t, read in rows if _still_readable(conn, r, user, cache)]
    return {'notices': shown, 'unread': sum(1 for n in shown if not n['read'])}


def mark_read(conn, user: dict | None, payload: dict) -> dict:
    """{ids: [...]} or {all: true}: mark this person's notices read (another's are left alone)."""
    if user is None or user.get('id') is None:
        return {'unread': 0}
    if payload.get('all') is True:
        conn.execute('UPDATE notice SET read_at = ? WHERE user_id = ? AND read_at IS NULL', (now_text(), user['id']))
    else:
        ids = payload.get('ids')
        if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids) or len(ids) > LISTED:
            raise TypeRefused(f'要写 ids（最多 {LISTED} 个）或 all: true')
        if ids:
            conn.execute(f'UPDATE notice SET read_at = ? WHERE user_id = ? AND read_at IS NULL AND id IN ({",".join("?" * len(ids))})', (now_text(), user['id'], *ids))
    return list_notices(conn, user)
