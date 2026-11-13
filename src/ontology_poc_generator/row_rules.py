"""Row rules: which rows of an object type a person sees. A rule is "these named people see the rows where <property> = <value>" (an allow-list, one property,
one value; there are no "not these" rules and no combinations). A type with no rules shows everyone every row. A type with rules shows a person only the rows
that match one of the rules that name them, and nothing when none does; admins, and the local no-sign-in person, see every row.

The rules are the admin's, on the 权限 page, kept apart from what a person confirms (changing them goes to the log as row_rules_changed, with who). The rows
are limited where they are read: the objects tab, the counts and rows a relation shows, Q&A (the rows are limited before anything is counted, and the answer
says so), the views' counts, an action's submit and approval. A dataset a row-ruled type reads is the admins' only (type_access.dataset_hidden), so the
dataset pages, a download or an upload cannot be a way round.

An action may not write a property a row rule on its type reads: the one action could move a row into or out of someone's view. Setting such a rule is refused
naming the action; confirming such an action is refused (object_actions).
"""
from __future__ import annotations

import json

from ontology_poc_generator.workspace_store import _canonical, log_line

MAX_RULES = 30
MAX_VALUE = 100


class RuleRefused(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def rules_of(conn, type_element_id: str) -> list[dict]:
    return [{'id': i, 'column': c, 'value': v, 'user_ids': json.loads(u)} for i, c, v, u in conn.execute(
        'SELECT id, column_name, value, user_ids_json FROM row_rule WHERE type_id = ? ORDER BY id', (type_element_id,))]


def has_rules(conn, type_element_id: str) -> bool:
    return conn.execute('SELECT 1 FROM row_rule WHERE type_id = ? LIMIT 1', (type_element_id,)).fetchone() is not None


def columns_ruled(conn, type_element_id: str) -> set[str]:
    return {c for (c,) in conn.execute('SELECT column_name FROM row_rule WHERE type_id = ?', (type_element_id,))}


def restriction(conn, type_element_id: str, user: dict | None) -> list[tuple[str, str]] | None:
    """None when this person sees every row of the type; else the (column, value) pairs a row must match one of (an empty list: no row)."""
    if user is None or user['role'] == 'admin':
        return None
    rules = rules_of(conn, type_element_id)
    if not rules:
        return None
    return [(r['column'], r['value']) for r in rules if user['id'] in r['user_ids']]


def keeps(record: dict, limit: list[tuple[str, str]] | None) -> bool:
    return limit is None or any(_canonical(record.get(c)) == _canonical(v) for c, v in limit)


def positions(records: list[dict], limit: list[tuple[str, str]] | None) -> set[int]:
    """The positions (from 1) of the rows this limit lets through."""
    return {i for i, r in enumerate(records, 1) if keeps(r, limit)}


def describe(limit: list[tuple[str, str]]) -> str:
    return '、'.join(f'{c} = {v}' for c, v in limit) if limit else '没有一条规则让你看到行'


def _actions_writing(conn, type_element_id: str) -> dict[str, list[str]]:
    """{column: [action names]} of the definitions on this type (any state but sent back) that write it."""
    english = type_element_id.partition(':')[2]
    out: dict[str, list[str]] = {}
    for content, in conn.execute("SELECT content_json FROM element_state WHERE element_id LIKE 'objaction:%' AND state != 'rejected'"):
        c = json.loads(content)
        if c['type'] == english:
            for column in c['properties']:
                out.setdefault(column, []).append(c['name'])
    return out


def conflict_with_actions(conn, type_element_id: str, written: list[str]) -> str | None:
    """Why an action that writes these columns cannot stand on this type, or None: a row rule reads one of them."""
    ruled = columns_ruled(conn, type_element_id) & set(written)
    if not ruled:
        return None
    return f'这个类型的行规则用到“{"、".join(sorted(ruled))}”，行为不能改写它：一次改写就能把一行移进或移出某个人看得到的范围'


def set_rules(conn, english_name: str, rules, who: str | None) -> dict:
    """Replace the rules of one type with `rules`: [{column, value, user_ids}]. Returns {'rules': [...]}."""
    element_id = f'objtype:{english_name}'
    found = conn.execute('SELECT content_json FROM element_state WHERE element_id = ?', (element_id,)).fetchone()
    if found is None:
        raise RuleRefused('没有这个对象类型', 404)
    columns = {p['column'] for p in json.loads(found[0])['properties']}
    if not isinstance(rules, list) or len(rules) > MAX_RULES or not all(isinstance(r, dict) for r in rules):
        raise RuleRefused(f'规则要写成列表，最多 {MAX_RULES} 条')
    clean = []
    for r in rules:
        column, value, ids = r.get('column'), r.get('value'), r.get('user_ids')
        if column not in columns:
            raise RuleRefused(f'“{column}”不是这个对象类型的属性')
        value = value.strip() if isinstance(value, str) else ''
        if not value or len(value) > MAX_VALUE or '\n' in value:
            raise RuleRefused(f'取值要写 1 到 {MAX_VALUE} 个字，不能换行')
        if not isinstance(ids, list) or not ids or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
            raise RuleRefused('每条规则要点名至少一个人')
        ids = sorted(set(ids))
        known = {x for (x,) in conn.execute(f'SELECT id FROM user WHERE id IN ({",".join("?" * len(ids))})', ids)}
        if set(ids) - known:
            raise RuleRefused('名单里有不存在的账号')
        clean.append({'column': column, 'value': value, 'user_ids': ids})
    used = _actions_writing(conn, element_id)
    clash = sorted({r['column'] for r in clean} & set(used))
    if clash:
        raise RuleRefused(f'“{"、".join(clash)}”被行为“{"、".join(sorted({n for c in clash for n in used[c]}))}”改写：规则读的属性不能同时被行为改写，一次改写就能把一行移进或移出某个人看得到的范围', 409)
    before = rules_of(conn, element_id)
    if [{k: r[k] for k in ('column', 'value', 'user_ids')} for r in before] == clean:
        return {'rules': before}
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('DELETE FROM row_rule WHERE type_id = ?', (element_id,))
        conn.executemany('INSERT INTO row_rule(type_id, column_name, value, user_ids_json) VALUES (?, ?, ?, ?)',
                         [(element_id, r['column'], r['value'], json.dumps(r['user_ids'])) for r in clean])
        names = lambda ids: [n for (n,) in conn.execute(f'SELECT display_name FROM user WHERE id IN ({",".join("?" * len(ids))}) ORDER BY display_name', ids)]
        say = lambda rs: [{'column': r['column'], 'value': r['value'], 'users': names(r['user_ids'])} for r in rs]
        summary = '；'.join(f'{"、".join(r["users"])} 看 {r["column"]} = {r["value"]} 的行' for r in say(clean)) or '行规则全部去掉了'
        log_line(conn, who or '未署名', element_id, 'row_rules_changed', before={'rules': say(before)}, after={'rules': say(clean), 'summary': f'行规则：{summary}'})
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return {'rules': rules_of(conn, element_id)}
