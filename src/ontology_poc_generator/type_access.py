"""Who may see an object type: everyone, or the people named (an allow-list; there are no "not these" rules). Admins see every type. A viewer
sees a type only when it is also confirmed (object_types._visible adds that). The list is not part of what a person confirms: changing it
leaves the state alone and goes to the log as access_changed, with who.

A type nobody may see is nobody's but the admins'; every read path (list, detail, objects, log, relations, the queue, the dataset "used by", the
task list, the question scope) asks can_access / visible_type_ids here, so there is one place that says who sees what.
"""
from __future__ import annotations

import json

from ontology_poc_generator.row_rules import has_rules, rules_of
from ontology_poc_generator.workspace_store import log_line

TYPE_PREFIX = 'objtype:'


class AccessRefused(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def allowed_ids(conn, type_element_id: str) -> list[int] | None:
    """The user ids on the list, or None when the type is visible to everyone."""
    row = conn.execute('SELECT user_ids_json FROM type_access WHERE type_id = ?', (type_element_id,)).fetchone()
    return None if row is None else json.loads(row[0])


def visible_to(conn, type_element_id: str) -> str | list[str]:
    """'everyone', or the names of the people on the list (for a page that says who sees the type)."""
    allowed = allowed_ids(conn, type_element_id)
    return 'everyone' if allowed is None else _names(conn, allowed)


def can_access(conn, type_element_id: str, user: dict | None) -> bool:
    """Whether this person may see the type at all (a viewer's need for it to be confirmed is checked by the caller). The local no-sign-in
    person and admins see everything."""
    if user is None or user['role'] == 'admin':
        return True
    allowed = allowed_ids(conn, type_element_id)
    return allowed is None or user['id'] in allowed


def dataset_hidden(conn, name: str, user: dict | None) -> bool:
    """A dataset that a type this person may not see reads is not theirs to see either: its rows, its download, an upload to it, its removal. Only
    admins, and people allowed to see every type that reads it, get past this; to everyone else it is not found. A type with row rules makes its dataset the
    admins' too: the dataset holds the rows a rule keeps from them."""
    if user is None or user['role'] == 'admin':
        return False
    return any(not can_access(conn, element_id, user) or has_rules(conn, element_id) for (element_id,) in conn.execute(   # a row-ruled type's dataset holds rows they may not see
        "SELECT element_id FROM element_dep WHERE depends_on = ? AND element_id LIKE 'objtype:%'", (f'dataset:{name}',)))


def visible_type_ids(conn, user: dict | None, confirmed_only: bool = False) -> list[str]:
    """The English names of the types this person may see, by name; a viewer's are the confirmed ones, and with confirmed_only so are everyone's
    (the scope of a question: confirmed types the asker may see and nothing else)."""
    out = []
    for element_id, state in conn.execute("SELECT element_id, state FROM element_state WHERE element_id LIKE 'objtype:%' ORDER BY element_id").fetchall():
        viewer = user is not None and user['role'] == 'viewer'
        if (viewer or confirmed_only) and state != 'confirmed':
            continue
        if can_access(conn, element_id, user):
            out.append(element_id[len(TYPE_PREFIX):])
    return out


def _names(conn, ids: list[int]) -> list[str]:
    return [r[0] for r in conn.execute(f'SELECT display_name FROM user WHERE id IN ({",".join("?" * len(ids))}) ORDER BY display_name', ids)] if ids else []


def set_access(conn, english_name: str, visible_to, who: str | None) -> dict:
    """visible_to: 'everyone' or a list of user ids. Returns {'visible_to': 'everyone' | [names]}."""
    element_id = f'{TYPE_PREFIX}{english_name}'
    if conn.execute('SELECT 1 FROM element_state WHERE element_id = ?', (element_id,)).fetchone() is None:
        raise AccessRefused('没有这个对象类型', 404)
    before = allowed_ids(conn, element_id)
    if visible_to == 'everyone':
        ids = None
    elif isinstance(visible_to, list) and all(isinstance(i, int) and not isinstance(i, bool) for i in visible_to):
        ids = sorted(set(visible_to))
        known = {r[0] for r in conn.execute(f'SELECT id FROM user WHERE id IN ({",".join("?" * len(ids))})', ids)} if ids else set()
        if set(ids) - known:
            raise AccessRefused('名单里有不存在的账号')
    else:
        raise AccessRefused('可见范围要写成 everyone，或一份账号编号的名单')
    if ids == before:
        return {'visible_to': 'everyone' if ids is None else _names(conn, ids)}
    conn.execute('BEGIN IMMEDIATE')
    try:
        if ids is None:
            conn.execute('DELETE FROM type_access WHERE type_id = ?', (element_id,))
        else:
            conn.execute('INSERT OR REPLACE INTO type_access(type_id, user_ids_json) VALUES (?, ?)', (element_id, json.dumps(ids)))
        log_line(conn, who or '未署名', element_id, 'access_changed',
                 before={'visible_to': 'everyone' if before is None else _names(conn, before)},
                 after={'visible_to': 'everyone' if ids is None else _names(conn, ids)})
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return {'visible_to': 'everyone' if ids is None else _names(conn, ids)}


def hidden_values(conn, type_element_id: str) -> set[str]:
    """The columns of this type whose values are never sent to the model that reads a question (a builder's switch on the type page). Not part of what a
    person confirms: flipping it leaves the state alone and goes to the log."""
    return {c for (c,) in conn.execute('SELECT column_name FROM value_privacy WHERE type_id = ?', (type_element_id,))}


def set_values_hidden(conn, english_name: str, column: str, hidden: bool, who: str | None) -> dict:
    element_id = f'{TYPE_PREFIX}{english_name}'
    row = conn.execute('SELECT content_json FROM element_state WHERE element_id = ?', (element_id,)).fetchone()
    if row is None:
        raise AccessRefused('没有这个对象类型', 404)
    if column not in {p['column'] for p in json.loads(row[0])['properties']}:
        raise AccessRefused(f'这个对象类型没有属性“{column}”')
    if not isinstance(hidden, bool):
        raise AccessRefused('hide_values 要写成 true 或 false')
    if hidden == (column in hidden_values(conn, element_id)):
        return {'hide_values': hidden}
    conn.execute('BEGIN IMMEDIATE')
    try:
        if hidden:
            conn.execute('INSERT OR IGNORE INTO value_privacy(type_id, column_name) VALUES (?, ?)', (element_id, column))
        else:
            conn.execute('DELETE FROM value_privacy WHERE type_id = ? AND column_name = ?', (element_id, column))
        log_line(conn, who or '未署名', element_id, 'values_privacy_changed', after={'column': column, 'hide_values': hidden})
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return {'hide_values': hidden}


def access_table(conn) -> dict:
    """The admin's page: every type with who sees it, and the people (not disabled) a list can name."""
    people = [{'id': i, 'name': n, 'role': r} for i, n, r in conn.execute(
        'SELECT id, display_name, role FROM user WHERE disabled = 0 ORDER BY role DESC, display_name')]
    types = []
    for element_id, state, content in conn.execute("SELECT element_id, state, content_json FROM element_state WHERE element_id LIKE 'objtype:%' ORDER BY element_id").fetchall():
        allowed = allowed_ids(conn, element_id)
        c = json.loads(content)
        types.append({'id': element_id[len(TYPE_PREFIX):], 'name': c['name'], 'state': state, 'everyone': allowed is None, 'user_ids': allowed or [],
                      'columns': [{'column': p['column'], 'name': p['name']} for p in c['properties']], 'row_rules': rules_of(conn, element_id)})
    return {'people': people, 'types': types}
