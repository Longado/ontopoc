"""待确认: one queue over the workspace of everything a person has to judge: every object type, set of code meanings and relation that is proposed, checked
or needs another look, with the evidence behind it and the reason it came back. Each item can be confirmed (the same confirmation as on its own page:
another builder, the version the person saw) or sent back with a reason (it becomes "rejected", the reason beside it, until its proposer saves it again).
What a person sees is only what they may see (type_access); the count on the navigation item is the number of items this person may confirm now.

The per-run review stack's typed replies (不对 / 不适用 / 已知例外 with an anchor) belong to the questions of one run and are not used here: a definition on the
workspace is either confirmed or sent back with words.
"""
from __future__ import annotations

import json

from ontology_poc_generator.object_relations import (
    _relation_visible, check_relation, confirm_relation, evidence_lines, relation_view)
from ontology_poc_generator.object_types import (
    ENUM_PREFIX, RELATION_PREFIX, STALE, TYPE_PREFIX, VIEW_PREFIX, TypeRefused, _confirmers, _content, _state_view, _visible, confirm_element, dataset_columns, element_row, seen_of_meaning, seen_of_type)
from ontology_poc_generator.object_views import confirm_view, describe, seen_of_view, view_state, view_summary, view_visible
from ontology_poc_generator.workspace_store import current_dataset, log_line

IN_QUEUE = ('proposed', 'checked', 'needs_look')
ORDER = {'needs_look': 0, 'checked': 1, 'proposed': 2}
MAX_REASON = 300


def _type_lines(conn, row: dict, content: dict) -> list[dict]:
    anchors = json.loads(row['anchors_json']) if row['anchors_json'] else {}
    lines = []
    if anchors.get('key_rows') is not None:
        lines.append({'ok': True, 'text': f'主键“{" + ".join(content["key"])}”在 {anchors["dataset"]} 第 {anchors["version"]} 版的全部 {anchors["key_rows"]} 行上唯一，没有空值'})
    lines.append({'ok': True, 'text': f'{len(content["properties"])} 个属性，来自 {content["dataset"]}'})
    for column, state in conn.execute("SELECT substr(d.depends_on, ?), s.state FROM element_dep d JOIN element_state s ON s.element_id = d.depends_on "
                                      "WHERE d.element_id = ? AND d.depends_on LIKE 'enum:%'", (len(f'{ENUM_PREFIX}{content["english_name"]}:') + 1, row['element_id'])):
        lines.append({'ok': state == 'confirmed', 'text': f'“{column}”的含义{"已确认" if state == "confirmed" else "还没有确认"}'})
    return lines


def _meaning_lines(content: dict, row: dict) -> list[dict]:
    counts = (json.loads(row['anchors_json']) if row['anchors_json'] else {}).get('counts') or {}
    return [{'ok': True, 'text': f'{e["value"]} = {e["label"]}（提出时 {counts.get(e["value"], 0)} 行）'} for e in content['values']]


def _item(conn, row: dict, user: dict | None, light: bool = False) -> dict | None:
    """One element as the queue shows it, or None when this person may not see it. The titles are the name only: the page puts the kind (对象类型, 取值含义,
    关系) in front. `light`: states only, no evidence and no check run (what the count on the navigation item needs)."""
    element_id, content = row['element_id'], _content(row)
    if element_id.startswith(RELATION_PREFIX):
        if not _relation_visible(conn, row, user):
            return None
        view = relation_view(conn, row, user)
        names = {e: _content(r)['name'] for e in ('from', 'to') if (r := element_row(conn, f'{TYPE_PREFIX}{content[e]}'))}
        base = {'kind': 'relation', 'title': f'{names.get("from", content["from"])} → {names.get("to", content["to"])}（{content["name"]}）', 'id': content['english_name'], 'lines': []}
        if not light:
            result = check_relation(conn, content, record=False)
            base['lines'] = evidence_lines(result)
            view['seen'] = result.get('signature')   # what the person reads, which confirming has to quote
    elif element_id.startswith(VIEW_PREFIX):
        if not view_visible(conn, row, user):
            return None
        view = view_state(conn, row, user)
        type_name = _content(element_row(conn, f'{TYPE_PREFIX}{content["type"]}'))['name']
        base = {'kind': 'view', 'title': f'{content["name"]}（{type_name}的视图）', 'id': content['type'], 'view': content['name'], 'lines': []}
        if not light:
            summary = view_summary(conn, content)
            base['lines'] = [{'ok': True, 'text': describe(content, type_name)},
                             *([{'ok': False, 'text': p} for p in summary['problems']] if summary['problems']
                               else [{'ok': True, 'text': f'{summary["dataset"]} 第 {summary["version"]} 版的 {summary["of"]} 行里，视图留下 {summary["rows"]} 行'}]),
                             *[{'ok': w['state'] == 'confirmed', 'text': f'“{w["name"]}”{"已确认" if w["state"] == "confirmed" else "还没有确认"}'} for w in view['waiting_on']]]
            view['seen'] = seen_of_view(summary)
    elif element_id.startswith(ENUM_PREFIX):
        type_row = element_row(conn, f'{TYPE_PREFIX}{content["type"]}')
        if type_row is None or not _visible(conn, type_row, user):
            return None
        view = _state_view(conn, row, user)
        view['can_confirm'] = view['can_confirm'] and row['state'] != 'needs_look'   # meanings that need another look are put forward again, not confirmed as they were
        base = {'kind': 'meaning', 'title': f'{_content(type_row)["name"]}.{content["column"]}', 'id': content['type'], 'column': content['column'], 'lines': []}
        if not light:
            dataset = current_dataset(conn, content['dataset'])
            base['lines'] = _meaning_lines(content, row)
            view['seen'] = seen_of_meaning(dataset, (dataset_columns(conn, dataset['id']) if dataset else {}).get(content['column']))
    else:
        if not _visible(conn, row, user):
            return None
        view = _state_view(conn, row, user)
        base = {'kind': 'type', 'title': content['name'], 'id': content['english_name'], 'lines': []}
        if not light:
            base['lines'] = _type_lines(conn, row, content)
            view['seen'] = seen_of_type(current_dataset(conn, content['dataset']))
    if light:
        return {'element': element_id, **base, **view}
    if row['state'] == 'needs_look' and row['reason']:
        base['lines'] = [{'ok': False, 'text': row['reason']}, *base['lines']]
    if view.get('model_draft'):
        base['lines'].append({'ok': False, 'text': '模型写的草稿，还没有人看过'})
    return {'element': element_id, **base, **view}


def queue(conn, user: dict | None, light: bool = False) -> dict:
    """{'items': what this person may see, those they can confirm first, then needs-another-look, checked, proposed; 'count': how many of them they can confirm now}.
    `light`: the count only, from the states (no relation check runs); items carry no evidence."""
    items = []
    for element_id, in conn.execute("SELECT element_id FROM element_state WHERE state IN ('proposed', 'checked', 'needs_look') AND "
                                    "(element_id LIKE 'objtype:%' OR element_id LIKE 'enum:%' OR element_id LIKE 'relation:%' OR element_id LIKE 'objview:%') ORDER BY element_id").fetchall():
        item = _item(conn, element_row(conn, element_id), user, light)
        if item:
            items.append(item)
    items.sort(key=lambda i: (not i['can_confirm'], ORDER[i['state']], i['element']))
    return {'items': [] if light else items, 'count': sum(1 for i in items if i['can_confirm'])}


def _parse(element: str) -> tuple[str, dict]:
    if element.startswith(RELATION_PREFIX):
        return 'relation', {'id': element[len(RELATION_PREFIX):]}
    if element.startswith(VIEW_PREFIX):
        return 'view', {'id': element[len(VIEW_PREFIX):]}
    if element.startswith(ENUM_PREFIX):
        type_name, _, column = element[len(ENUM_PREFIX):].partition(':')
        return 'meaning', {'id': type_name, 'column': column}
    if element.startswith(TYPE_PREFIX):
        return 'type', {'id': element[len(TYPE_PREFIX):]}
    raise TypeRefused('这不是一个可以确认的定义')


def _row_for(conn, element: str, user: dict | None) -> dict:
    row = element_row(conn, element) if isinstance(element, str) else None
    item = _item(conn, row, user, light=True) if row and row['state'] in (*IN_QUEUE, 'confirmed', 'rejected') else None
    if row is None or item is None:
        raise TypeRefused('队列里没有这一项', 404)
    return row


def confirm_item(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{element, version, seen?}: the confirmation of one item, the same as on its own page."""
    element = payload.get('element')
    _row_for(conn, element, user)
    kind, ref = _parse(element)
    if kind == 'relation':
        return confirm_relation(conn, {**ref, 'version': payload.get('version'), 'seen': payload.get('seen')}, who, user)
    if kind == 'view':
        return confirm_view(conn, {**ref, 'version': payload.get('version'), 'seen': payload.get('seen')}, who, user)
    return confirm_element(conn, {**ref, 'version': payload.get('version'), 'seen': payload.get('seen')}, who, user)


def send_back(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{element, version, reason}: the item is rejected with the reason beside it. Whoever may confirm it may send it back (not its proposer, not a viewer);
    the version is the one they saw. Its proposer saves it again (changed or not) to put it forward anew."""
    element, reason = payload.get('element'), payload.get('reason')
    row = _row_for(conn, element, user)
    reason = reason.strip() if isinstance(reason, str) else ''
    if not reason or len(reason) > MAX_REASON or '\n' in reason:
        raise TypeRefused(f'退回要写理由，1 到 {MAX_REASON} 个字，不能换行')
    if payload.get('version') != row['version']:
        raise TypeRefused('它在你看过之后被改了，请刷新后重新看一遍', 409)
    if row['state'] not in IN_QUEUE:
        raise TypeRefused('这一项不在待确认里了', 409)
    if row['state'] == 'needs_look' and not element.startswith((TYPE_PREFIX, RELATION_PREFIX, VIEW_PREFIX)):
        raise TypeRefused('这组含义需要再看：请按现在的数据重新提出含义，不用退回', 409)
    if not _confirmers(conn, row, user)[0]:   # who may judge it, whether or not it can be confirmed yet
        raise TypeRefused('你现在不能处理这一项：它要另一位构建者来看', 403)
    conn.execute('BEGIN IMMEDIATE')
    try:
        if conn.execute("UPDATE element_state SET state = 'rejected', reason = ?, version = version + 1 WHERE element_id = ? AND version = ?",
                        (reason, element, row['version'])).rowcount != 1:   # someone wrote it between the read and here
            raise TypeRefused(STALE, 409)
        log_line(conn, who or '未署名', element, 'sent_back', before={'state': row['state']}, after={'state': 'rejected', 'reason': reason})
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return {'state': 'rejected'}
