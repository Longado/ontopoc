"""Confirming together what one upload moved. A new version of a dataset sends the meanings, the type, the views, the relations and the derived properties that
stood on it back for another look; the second builder would otherwise open a confirm screen for each of them. They are grouped here by the dataset version that
moved them ("订单 第 2 版 让这 4 项需要再看"), shown in dependency order with the evidence each has on its own screen, and confirmed in one action.

An item belongs to a group when it was confirmed once, on a version of a dataset that is not the current one now; the group is that dataset's current version
(the latest one when an item stood on two). Pipelines keep their own cards: what a person reads before confirming one is a review of each of its steps.

The confirmation itself is each item's own (review_queue.confirm_item): the same version and `seen` it asks for on its own page, the same two-person rule, the same
row-rule limits. This module only decides the order, who is offered what, and that the lot is one transaction: when any check refuses, nothing is kept and the
refusal names the item. What a person cannot confirm (their own proposal, an item that waits on one of those, one a row rule limits) is listed and left out, not
failed. Each confirmed item also gets a log line saying it was confirmed with the others."""
from __future__ import annotations

from ontology_poc_generator.lang import tr
import json

from ontology_poc_generator.object_types import (
    ACTION_PREFIX, DERIVED_PREFIX, ENUM_PREFIX, RELATION_PREFIX, TYPE_PREFIX, VIEW_PREFIX, TypeRefused,
    _by_value, _citation_problems, _confirmers, _content, held_note, _label, _type_problems, counted_ahead, dataset_columns, element_row, keep_count, limited_on, unconfirmed_producers)
from ontology_poc_generator.review_queue import IN_QUEUE, _item, confirm_item, queue
from ontology_poc_generator.workspace_store import SelfConfirmation, current_dataset, log_line

GROUPED = (ENUM_PREFIX, TYPE_PREFIX, VIEW_PREFIX, RELATION_PREFIX, DERIVED_PREFIX, ACTION_PREFIX)
RANK = {ENUM_PREFIX: 0, TYPE_PREFIX: 1, VIEW_PREFIX: 2, ACTION_PREFIX: 2, RELATION_PREFIX: 3, DERIVED_PREFIX: 3}   # the order when nothing says one comes after another
DEPENDS_ON = (TYPE_PREFIX, ENUM_PREFIX, VIEW_PREFIX, RELATION_PREFIX, DERIVED_PREFIX, ACTION_PREFIX)
MAX_ITEMS = 100


def _moved_by(conn, element_id: str) -> dict | None:
    """The dataset (as it is now) that moved this element since the version it was last confirmed on, the latest one if it read several; None when nothing did, or
    when it was never confirmed (a first proposal is nobody's "moved")."""
    last = conn.execute('SELECT dataset_versions_json FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 1', (element_id,)).fetchone()
    if not last or not last[0]:
        return None
    moved = [now for name, version in json.loads(last[0]).items() if (now := current_dataset(conn, name)) and now['version'] != version]
    return max(moved, key=lambda d: d['id']) if moved else None


def _scan(conn, only: tuple | None = None) -> dict[tuple, dict]:
    """{(dataset name, version): {'dataset': the dataset, 'rows': the elements in the queue it moved}}, for the whole workspace or one (name, version)."""
    found: dict[tuple, dict] = {}
    like = ' OR '.join(f"element_id LIKE '{p}%'" for p in GROUPED)
    for element_id, in conn.execute(f"SELECT element_id FROM element_state WHERE state IN ({','.join('?' * len(IN_QUEUE))}) AND ({like}) ORDER BY element_id", IN_QUEUE).fetchall():
        moved = _moved_by(conn, element_id)
        if moved is None or (only and (moved['name'], moved['version']) != only):
            continue
        found.setdefault((moved['name'], moved['version']), {'dataset': moved, 'rows': []})['rows'].append(element_row(conn, element_id))
    return found


def _in_order(conn, rows: list[dict]) -> list[dict]:
    """Each element after the ones in the group it stands on (a type after its meanings, a view after its type, a relation after its two types); the rank breaks ties."""
    needs = {r['element_id']: {d for (d,) in conn.execute('SELECT depends_on FROM element_dep WHERE element_id = ?', (r['element_id'],))} for r in rows}
    left = sorted(rows, key=lambda r: (RANK[next(p for p in GROUPED if r['element_id'].startswith(p))], r['element_id']))
    out: list[dict] = []
    while left:
        waiting = {r['element_id'] for r in left}
        nxt = next((r for r in left if not needs[r['element_id']] & waiting), left[0])   # a cycle cannot be ordered: the first by rank
        out.append(nxt)
        left.remove(nxt)
    return out


def _why_not_theirs(conn, row: dict, user: dict | None) -> str | None:
    if limited_on(conn, row, user):
        return tr('你受行规则或列的限制，看不到全部数据：要不受限制的建设者来确认', 'A row rule or a column limit keeps you from seeing all the data: a builder without the limit must confirm')
    if user is not None and user['role'] == 'viewer':
        return tr('你是只读成员，不能确认', 'You are a read-only member and cannot confirm')
    can, others = _confirmers(conn, row, user)
    if not can:   # who holds it and the ways out, as the item's own route says it
        return held_note(conn, row, others) or tr('这一项是你提的或你改过的，要另一位建设者确认', 'You put this forward or changed it, so another builder must confirm it')
    return None


def _plan(conn, rows: list[dict], user: dict | None) -> list[dict]:
    """[{'row', 'mine', 'ready', 'why_not'}] in order. `ready`: the person may confirm it and everything it stands on is confirmed or comes earlier in the group and is
    ready. The prediction only drives what the page offers; the confirmations themselves run each item's own checks."""
    will: set[str] = set()
    out = []
    for row in _in_order(conn, rows):
        element_id, content = row['element_id'], _content(row)
        mine_why = _why_not_theirs(conn, row, user)
        why = mine_why
        if why is None and element_id.startswith(ENUM_PREFIX) and row['state'] == 'needs_look':
            why = tr('这组含义要先按现在的数据重新写，由另一位确认', 'These meanings must be rewritten on the current data first, and confirmed by someone else')
        if why is None:
            waiting = [d for (d,) in conn.execute('SELECT depends_on FROM element_dep WHERE element_id = ? ORDER BY depends_on', (element_id,))
                       if d.startswith(DEPENDS_ON) and d not in will and (held := element_row(conn, d)) and held['state'] != 'confirmed']
            if waiting:
                why = tr(f'要先确认{tr("、", ", ").join(_label(conn, d) for d in waiting)}', f'Confirm {", ".join(_label(conn, d) for d in waiting)} first')
            elif element_id.startswith(TYPE_PREFIX) and (producers := unconfirmed_producers(conn, content['dataset'])):
                why = tr(f'要先确认管道{tr("、", ", ").join(f"“{n}”" for n in producers)}', f'Confirm the pipeline {", ".join(producers)} first')
            elif element_id.startswith(TYPE_PREFIX) and (problems := [*_type_problems(conn, content, record=False)[0], *_citation_problems(conn, content)]):   # confirming it would be refused (confirm_element): not planned, and what stands on it waits
                why = tr(f'按现在的数据过不了检查，确认不了：{tr("；", "; ").join(problems)}', f'It fails the checks on the current data and cannot be confirmed: {"; ".join(problems)}')
        if why is None:
            will.add(element_id)
        out.append({'row': row, 'mine': mine_why is None, 'ready': why is None, 'why_not': why})
    return out


def _meaning_values(conn, row: dict, user: dict | None) -> list[dict]:
    """Each value of a set of meanings as it was when it was last confirmed (its meaning and how many rows had it, counted on the dataset version it was confirmed
    on) beside what it says and has now. A person a row rule limits reads no counts of the whole data."""
    content = _content(row)
    limited = limited_on(conn, row, user)
    now_counts = {}
    dataset = current_dataset(conn, content['dataset'])
    if dataset and not limited:
        now_counts = (dataset_columns(conn, dataset['id']).get(content['column']) or {}).get('counts') or {}
    last = conn.execute('SELECT content_json, dataset_versions_json FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 1', (row['element_id'],)).fetchone()
    then_labels, then_counts = {}, {}
    if last:
        then_labels = {e['value']: e['label'] for e in json.loads(last[0])['values']}
        was = conn.execute('SELECT id FROM dataset WHERE name = ? AND version = ?', (content['dataset'], json.loads(last[1]).get(content['dataset']))).fetchone()
        if was and not limited:
            then_counts = (dataset_columns(conn, was[0]).get(content['column']) or {}).get('counts') or {}
    labels = {e['value']: e['label'] for e in content['values']}
    return [{'value': v, 'label_then': then_labels.get(v), 'rows_then': then_counts.get(v), 'label': labels.get(v, ''), 'rows': now_counts.get(v)}
            for v in _by_value({*then_labels, *then_counts, *labels, *now_counts})]


def queue_with_groups(conn, user: dict | None, light: bool = False) -> dict:
    """review_queue.queue, and: `groups` [{key, dataset, version, uploaded_by, items: the elements in order, hidden}] for each dataset version that moved two or more
    items this person may see, and `group` (the key) on each of those items."""
    body = queue(conn, user, light)
    if light:
        return body
    shown = {i['element'] for i in body['items']}
    groups, keys = [], {}
    for (name, version), found in _scan(conn).items():
        mine = [r for r in found['rows'] if r['element_id'] in shown]
        if len(mine) < 2:
            continue
        key = f'{name}@{version}'
        ordered = [r['element_id'] for r in _in_order(conn, mine)]
        groups.append({'key': key, 'dataset': name, 'version': version, 'uploaded_by': found['dataset']['who'], 'uploaded_at': found['dataset']['imported_at'],
                       'items': ordered, 'hidden': len(found['rows']) - len(mine)})
        keys.update({e: key for e in ordered})
    return {**body, 'groups': groups, 'items': [{**i, 'group': keys[i['element']]} if i['element'] in keys else i for i in body['items']]}


def _members(conn, user: dict | None, dataset, version) -> tuple[dict, list[dict], int]:
    """(the dataset, the elements of the group this person may see, how many more they may not); TypeRefused 404 when there is no such group for them."""
    if not isinstance(dataset, str) or not isinstance(version, int) or isinstance(version, bool):
        raise TypeRefused(tr('要写明是哪个数据集的哪一版', 'Say which dataset and which version'))
    found = _scan(conn, (dataset, version)).get((dataset, version))
    seen = [r for r in found['rows'] if _item(conn, r, user, light=True)] if found else []
    if not seen:
        raise TypeRefused(tr('没有这一组：这一版没有让什么东西需要再看，或者已经都处理了', 'There is no such group: this version did not make anything need review, or all of it is handled'), 404)
    return found['dataset'], seen, len(found['rows']) - len(seen)


def group_detail(conn, user: dict | None, dataset, version) -> dict:
    """One group as the screen reads it: each item in order with the evidence of its queue card (and for a set of meanings what each value meant and had when it was
    confirmed beside now), the version and `seen` its confirmation quotes, `mine` (may this person confirm it), `ready` (and does everything it stands on come
    before it) and why not."""
    moved, rows, hidden = _members(conn, user, dataset, version)
    items = []
    with counted_ahead(conn, [r['element_id'] for r in rows if not limited_on(conn, r, user)]) as counts:   # one count of each type's value rules, kept for the reads made on every page
        for element_id, found in counts.items():
            keep_count(conn, element_id, _content(element_row(conn, element_id)), found)
        plan = _plan(conn, rows, user)
    for place in plan:
        row = place['row']
        items.append({**_item(conn, row, user), 'mine': place['mine'], 'ready': place['ready'], 'why_not': place['why_not'],
                      **({'values': _meaning_values(conn, row, user)} if row['element_id'].startswith(ENUM_PREFIX) else {})})
    return {'dataset': moved['name'], 'version': moved['version'], 'uploaded_by': moved['who'], 'uploaded_at': moved['imported_at'], 'hidden': hidden, 'items': items}


def _asked(payload: dict, members: list[dict]) -> dict[str, dict]:
    asked = payload.get('items')
    if not isinstance(asked, list) or not asked or len(asked) > MAX_ITEMS or not all(isinstance(a, dict) and isinstance(a.get('element'), str) for a in asked):
        raise TypeRefused(tr(f'要带上这一组里要确认的项目（最多 {MAX_ITEMS} 个）', f'Send the items of this group to confirm (at most {MAX_ITEMS})'))
    by_element = {a['element']: a for a in asked}
    if len(by_element) != len(asked):
        raise TypeRefused(tr('同一项写了不止一次', 'An item is listed more than once'))
    outside = [e for e in by_element if e not in {r['element_id'] for r in members}]
    if outside:
        raise TypeRefused(tr('这一项不在这一组里', 'This item is not in this group'), 404)
    return by_element


def confirm_group(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{dataset, version, items: [{element, version, seen?, new_values?}]}: confirm what the person looked at, every item through its own confirmation, in
    dependency order, in one transaction. Every item this person may confirm that is ready has to be in the request (the page sends them once all are seen and the
    questions answered). Returns {confirmed, sent_on (a view whose new value does not count: changed, and the other builder's to confirm), left_out: [{element,
    title, why}], hidden}. A refusal of any item (409 when the data or a version moved, 403, 400 for what it asks for) keeps nothing and names the item."""
    moved, members, hidden = _members(conn, user, payload.get('dataset'), payload.get('version'))
    asked = _asked(payload, members)
    with counted_ahead(conn, [r['element_id'] for r in members]):   # the value rules are counted here, before the write lock below; the checks under it use these counts
        return _confirm_planned(conn, payload, who, user, members, asked, hidden)


def _confirm_planned(conn, payload: dict, who: str | None, user: dict | None, members: list[dict], asked: dict, hidden: int) -> dict:
    plan = _plan(conn, members, user)
    ready = [p for p in plan if p['ready']]
    if not ready:
        raise TypeRefused(tr('这一组里没有你现在能确认的：' + tr('；', '; ').join(f'{_label(conn, p["row"]["element_id"])}{p["why_not"]}' for p in plan), 'Nothing in this group is yours to confirm now: ' + '; '.join(f'{_label(conn, p["row"]["element_id"])}: {p["why_not"]}' for p in plan)), 409)
    missing = [p for p in ready if p['row']['element_id'] not in asked]
    if missing:
        raise TypeRefused(tr(f'这一组里你也能确认{tr("、", ", ").join(_label(conn, p["row"]["element_id"]) for p in missing)}，没有带上：一起确认要把它们都带上', f'You can also confirm {", ".join(_label(conn, p["row"]["element_id"]) for p in missing)} in this group, but they were not sent: confirming together needs all of them'), 409)
    confirmed, sent_on = [], []
    conn.execute('BEGIN IMMEDIATE')   # the confirmations below join this transaction (element_state_writes)
    try:
        for place in ready:
            element_id = place['row']['element_id']
            try:
                done = confirm_item(conn, {**asked[element_id], 'element': element_id}, who, user)
            except (TypeRefused, SelfConfirmation) as exc:
                raise TypeRefused(tr(f'{_label(conn, element_id)}：{exc}', f'{_label(conn, element_id)}: {exc}'), exc.status if isinstance(exc, TypeRefused) else 403) from exc
            (confirmed if done['state'] == 'confirmed' else sent_on).append(element_id)
        for element_id in confirmed if len(confirmed) > 1 else []:
            log_line(conn, who or tr('未署名', 'unsigned'), element_id, 'confirmed_together', after={'with': len(confirmed) - 1, 'text': tr(f'和另外 {len(confirmed) - 1} 项一起确认', f'Confirmed together with {len(confirmed) - 1} other items')})
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    title = lambda element_id: _item(conn, element_row(conn, element_id), user, light=True)['title']
    return {'confirmed': [{'element': e, 'title': title(e)} for e in confirmed], 'sent_on': [{'element': e, 'title': title(e)} for e in sent_on],
            'left_out': [{'element': p['row']['element_id'], 'title': title(p['row']['element_id']), 'why': p['why_not']} for p in plan if not p['ready']], 'hidden': hidden}
