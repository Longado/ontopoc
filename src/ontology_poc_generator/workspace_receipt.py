"""Receipts: what a confirmation changed, and what the workspace stands on, both read from the records that are already kept. Nothing new is stored.

The receipt of a change (POST /api/workspace/receipt {elements}, several for one upload's group; a POST, so that a read-only token, which may make any GET, never
makes the copy of the workspace it needs) is made from the confirmation records: the latest confirmation of each
element (who put it forward, who confirmed it, on which dataset versions, its evidence) beside the one before it (what it said then). The board numbers it moved are
worked out again the way the preview worked them out (change_preview): the cards as they are now, beside the cards on the definitions as they were confirmed before,
both on the data as it is now. When a dataset had a new version between the two confirmations, the item says so (data_moved), and whether this confirmation
accepted it: when the data had sent the item back, confirming it is what lets the new data's numbers count.
So the receipt read right after confirming says what the preview said; read later, it is worked out on the data of that later moment, and says when.

The workspace summary (GET /api/workspace/receipt) counts what this person may see: the definitions by kind and state, the checks behind the confirmed ones (their
evidence's check results), how many rows the confirmed types read of all the rows there are, and who confirmed what on which version.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json

from ontology_poc_generator.caliber import _text as caliber_text
from ontology_poc_generator.change_preview import answers, as_last_confirmed, cards, compare, sent_back, waited_on_data, work_out, workspace_copy
from ontology_poc_generator.lang import tr
from ontology_poc_generator.object_views import describe as describe_view
from ontology_poc_generator.object_types import (
    ACTION_PREFIX, DERIVED_PREFIX, ENUM_PREFIX, PIPELINE_PREFIX, RELATION_PREFIX, TYPE_PREFIX, VIEW_PREFIX, TypeRefused, _content, element_row, stale_word)
from ontology_poc_generator.type_access import hidden_columns, reads_hidden
from ontology_poc_generator.workspace_store import current_dataset

KINDS = ((TYPE_PREFIX, 'type'), (ENUM_PREFIX, 'meaning'), (RELATION_PREFIX, 'relation'), (VIEW_PREFIX, 'view'), (DERIVED_PREFIX, 'derived'), (ACTION_PREFIX, 'action'),
         (PIPELINE_PREFIX, 'pipeline'))
MAX_ELEMENTS = 100
MAX_CONFIRMATIONS = 200


def _kind(element_id: str) -> str | None:
    return next((kind for prefix, kind in KINDS if element_id.startswith(prefix)), None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def kept_text() -> str:
    return tr('这一版用到了你看不到的列，内容不显示', 'This version uses a column kept from you, so what it said is not shown')


def _said(conn, element_id: str, content: dict, user: dict | None) -> str:
    """A definition in one line, as this person may read it: a view as the queue describes it; the caliber's line for a meaning, a relation or a derived property; a
    type's name, key and properties without those kept from them (type_access: for them the type has no such property). A version that read a column kept from them
    (an earlier one may have, when the one confirmed now does not) is said to be there, not what it said."""
    if element_id.startswith(TYPE_PREFIX):
        hidden = hidden_columns(conn, element_id, user)
        props = tr('、', ', ').join(p.get('name') or p['column'] for p in content.get('properties', []) if p['column'] not in hidden)
        return tr(f'{content["name"]}：主键 {" + ".join(content["key"])}；属性 {props}；来自 {content["dataset"]}', f'{content["name"]}: key {" + ".join(content["key"])}; properties {props}; from {content["dataset"]}')
    if reads_hidden(conn, element_id, user, content):
        return kept_text()
    if element_id.startswith((ACTION_PREFIX, PIPELINE_PREFIX)):
        return content.get('name') or element_id
    if element_id.startswith(VIEW_PREFIX):   # as the queue words it: the conditions one after another, so two versions read side by side
        type_row = element_row(conn, f'{TYPE_PREFIX}{content["type"]}')
        return describe_view(content, _content(type_row)['name'] if type_row else None)
    return caliber_text(conn, element_id, content)


def _seen(conn, row: dict, user: dict | None):
    from ontology_poc_generator.review_queue import _item, seen_by
    return _item(conn, row, user, light=True) if seen_by(conn, row, user) else None


def change_receipt(conn, user: dict | None, elements: list[str]) -> dict:
    """{'items': [{element, kind, title, before, after, proposed_by, confirmed_by, confirmed_at, on, on_before, evidence}], 'cards', 'answers', 'checked', 'at'}
    for confirmed elements this person may see (404 for any other)."""
    if not elements or len(elements) > MAX_ELEMENTS or len(set(elements)) != len(elements):
        raise TypeRefused(tr(f'要写明是哪些定义（element，1 到 {MAX_ELEMENTS} 个，不重复）', f'Say which definitions (element, 1 to {MAX_ELEMENTS}, each once)'))
    items = []
    for element_id in elements:
        row = element_row(conn, element_id)
        shown = _seen(conn, row, user) if row is not None else None
        last = conn.execute('SELECT content_json, dataset_versions_json, proposed_by, confirmed_by, confirmed_at, evidence_ref FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 2',
                            (element_id,)).fetchall()
        if shown is None or row['state'] != 'confirmed' or not last:
            raise TypeRefused(tr('没有这个已确认的定义', 'There is no such confirmed definition'), 404)
        before = last[1] if len(last) > 1 else None
        on, on_before = json.loads(last[0][1] or '{}'), json.loads(before[1] or '{}') if before else {}
        items.append({'element': element_id, 'kind': _kind(element_id), 'title': shown['title'],
                      'before': _said(conn, element_id, json.loads(before[0]), user) if before else None, 'after': _said(conn, element_id, json.loads(last[0][0]), user),
                      'proposed_by': last[0][2], 'confirmed_by': last[0][3], 'confirmed_at': last[0][4], 'on': json.loads(last[0][1] or '{}'),
                      'on_before': on_before if before else None, 'evidence': last[0][5],
                      'data_moved': [{'name': n, 'from': on_before[n], 'to': v, 'accepted': sent} for n, v in sorted(on.items()) if n in on_before and on_before[n] != v
                                     for sent in [waited_on_data(conn, element_id) is not None]]})   # accepted: the data sent it back and this confirmation lets the new data's numbers count
    with workspace_copy(conn) as copy:
        picked, checked = cards(copy, user)
        after = work_out(copy, user, picked)
        touched = {*elements, *sent_back(copy, elements)}
        as_last_confirmed(copy, elements, confirmed_now=True)   # on the data as it is now: a move of the data is each item's data_moved, not a number of this change
        now = work_out(copy, user, picked)
    return {'items': items, 'cards': compare(picked, now, after, touched), 'answers': answers(conn, user, touched), 'checked': checked, 'at': _now()}


def summary(conn, user: dict | None) -> dict:
    """What the workspace stands on, over what this person may see: {'definitions': {kind: {state: n}}, 'needs_look': {word: n}, 'checks': {status: n}, 'rows':
    {covered, total, uncovered, datasets, datasets_covered} (None for a person a type list, row rule or column limit keeps from some data), 'confirmations':
    [{element, kind, title, by, at, on}] newest first, 'at'}."""
    from ontology_poc_generator.auth_http import limited_anywhere
    definitions: dict[str, dict[str, int]] = {}
    needs_look: dict[str, int] = {}
    checks = {'passed': 0, 'failed': 0, 'error': 0, 'skipped': 0}
    confirmed: list[tuple[dict, dict]] = []
    for (element_id,) in conn.execute('SELECT element_id FROM element_state ORDER BY element_id').fetchall():
        kind = _kind(element_id)
        row = element_row(conn, element_id) if kind else None
        shown = _seen(conn, row, user) if row is not None and row['content_json'] else None
        if shown is None:
            continue
        definitions.setdefault(kind, {})
        definitions[kind][row['state']] = definitions[kind].get(row['state'], 0) + 1
        if row['state'] == 'needs_look':
            word = stale_word(row['cause'], row['via']) or tr('需要再看', 'Needs another look')
            needs_look[word] = needs_look.get(word, 0) + 1
        if row['state'] == 'confirmed':
            confirmed.append((row, shown))
            for part in (row['evidence_ref'] or '').split(','):
                if part.startswith('check_result:') and part[len('check_result:'):].isdigit():
                    found = conn.execute('SELECT status FROM check_result WHERE id = ?', (int(part[len('check_result:'):]),)).fetchone()
                    if found:
                        checks[found[0]] = checks.get(found[0], 0) + 1
    rows = None
    if not limited_anywhere(conn, user):
        read = {_content(r)['dataset'] for r, _ in confirmed if r['element_id'].startswith(TYPE_PREFIX)}
        current = [current_dataset(conn, name) for (name,) in conn.execute('SELECT name FROM current_dataset ORDER BY name')]
        current = [d for d in current if d]
        total = sum(d['rows_stored'] for d in current)
        covered = sum(d['rows_stored'] for d in current if d['name'] in read)
        rows = {'covered': covered, 'total': total, 'uncovered': total - covered, 'datasets': len(current), 'datasets_covered': sum(1 for d in current if d['name'] in read)}
    out = []
    for row, shown in confirmed:
        last = conn.execute('SELECT confirmed_by, confirmed_at, dataset_versions_json FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 1', (row['element_id'],)).fetchone()
        if last:
            out.append({'element': row['element_id'], 'kind': _kind(row['element_id']), 'title': shown['title'], 'by': last[0], 'at': last[1], 'on': json.loads(last[2] or '{}')})
    out.sort(key=lambda c: c['at'] or '', reverse=True)
    return {'definitions': definitions, 'needs_look': needs_look, 'checks': checks, 'rows': rows, 'confirmations': out[:MAX_CONFIRMATIONS], 'at': _now()}
