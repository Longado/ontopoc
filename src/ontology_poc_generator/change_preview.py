"""What confirming a pending change would do to the numbers on the boards, worked out before it is confirmed.

The confirmation is run for real, on a copy of the workspace file that is thrown away (as upload_preview does for an upload): review_queue.confirm_item for one item,
batch_confirm.confirm_group for what one upload moved. Each board card this person may open is then worked out on the copy by the board's own code
(dashboards.evaluate), as this person, and that is "after". "Now" is the same card worked out on the definitions as they were last confirmed: the copy puts back the
content of the latest confirmation of what is being confirmed, and of what went back for another look under it, and the dataset versions it was confirmed on. That is
what the board's readers were shown (a reader is shown the last confirmed number while a definition waits). Nothing of the real workspace is written; there is no
second calculation of a number, and no record is kept: a receipt after confirming works the same comparison out again from the confirmation records
(workspace_receipt).

A card is listed when it reads what is being confirmed (or what waits under it), or when what it shows would change. Only boards this person may open are looked at,
worked out over what they may read; saved answers that used the definitions are counted, and only the person's own are named by their question. The work is capped
(MAX_CARDS cards a preview works out), and the answer says when it stopped.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile

from ontology_poc_generator import dashboards
from ontology_poc_generator.lang import tr
from ontology_poc_generator.object_types import TypeRefused, element_row, type_id
from ontology_poc_generator.object_views import view_id
from ontology_poc_generator.workspace_store import SelfConfirmation, open_workspace

MAX_CARDS = 30        # board cards a preview works out (twice: now and after)
MAX_ANSWERS = 1000    # the newest saved answers looked at
MAX_NAMED = 20        # of the person's own, named by their question
MAX_GROUPS = 6        # groups of a chart quoted in a card's text


@contextmanager
def workspace_copy(conn):
    """A copy of the workspace this connection reads, open, deleted afterwards."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'workspace.sqlite'
        target = sqlite3.connect(str(path))
        try:
            conn.backup(target)
        finally:
            target.close()
        copy = open_workspace(path)
        try:
            yield copy
        finally:
            copy.close()


# --- a card as a figure -----------------------------------------------------------------------------------------------------------------------------------

def _number(value) -> float | int | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _shown(value) -> str:
    if isinstance(value, float):
        return f'{value:,.2f}'.rstrip('0').rstrip('.') if value != int(value) else f'{int(value):,}'
    if isinstance(value, int):
        return f'{value:,}'
    return '—' if value is None else str(value)


def _groups_text(items: list[dict], hidden: int) -> str:
    said = tr('、', ', ').join(f'{i.get("label", i.get("key"))} {_shown(i.get("value"))}' for i in items[:MAX_GROUPS])
    more = len(items) - MAX_GROUPS + hidden
    return said + (tr(f' 等 {len(items) + hidden} 组', f' and more ({len(items) + hidden} groups)') if more > 0 else '')


def _value_of(chart: dict, result: dict) -> tuple[float | int | None, str]:
    """(the number a card shows, or the total of its groups; what it shows in words)."""
    kind = chart.get('kind')
    if kind == 'query':
        answer = result.get('answer') if isinstance(result.get('answer'), dict) else {}
        total = _number(answer.get('total'))
        groups = answer.get('groups') if isinstance(answer.get('groups'), list) else None
        if groups and all(isinstance(g, dict) for g in groups):
            return total, _groups_text([{'label': g.get('label', g.get('key')), 'value': g.get('value', g.get('total'))} for g in groups], 0)
        return total, _shown(total) if total is not None else (result.get('reason') or tr('没有数', 'No number'))
    if kind == 'number':
        return _number(result.get('value')), _shown(result.get('value'))
    if kind in ('bar', 'pie'):
        items = result.get('groups') or []
        values = [_number(i.get('value')) for i in items]
        total = sum(v for v in values if v is not None) if items and all(v is not None for v in values) and not result.get('groups_hidden') else None
        return total, _groups_text(items, result.get('groups_hidden') or 0)
    if kind == 'rows':
        return _number(result.get('total')), tr(f'{_shown(result.get("total"))} 行', f'{_shown(result.get("total"))} rows')
    return _number(result.get('rows')), tr(f'{_shown(result.get("rows"))} 行', f'{_shown(result.get("rows"))} rows')   # a histogram or a table of statistics: the rows it was worked out on


def figure(component: dict) -> dict:
    """What a worked-out board card shows, in the few words a comparison needs: {'status': 'ok' | 'refused', 'value' (a number, or None), 'text', 'grey' (it stands on
    a definition that is not confirmed), 'why' (the reason it is grey)}."""
    if component.get('status') != 'ok':
        return {'status': 'refused', 'value': None, 'text': component.get('message') or '', 'grey': False, 'why': None}
    result = component['result']
    standing = result.get('standing') or {'confirmed': True}
    value, text = _value_of(component['chart'], result)
    grey = not standing.get('confirmed', True)
    return {'status': 'ok', 'value': value, 'text': text, 'grey': grey, 'why': standing.get('why') if grey else None}


def change(now: dict, after: dict) -> dict:
    """How a card moves: a number by how much, a card that starts or stops refusing, a card that turns grey or back, or one whose words change."""
    if now['status'] == 'ok' and after['status'] != 'ok':
        return {'kind': 'refuses', 'why': after['text']}
    if now['status'] != 'ok' and after['status'] == 'ok':
        return {'kind': 'opens'}
    if now['value'] is not None and after['value'] is not None and after['value'] != now['value']:
        delta = after['value'] - now['value']
        return {'kind': 'number', 'delta': round(delta, 6) if isinstance(delta, float) else delta}
    if now['text'] != after['text']:
        return {'kind': 'other'}
    if now['grey'] != after['grey']:
        return {'kind': 'grey' if after['grey'] else 'confirmed'}
    return {'kind': 'same'}


# --- the boards ------------------------------------------------------------------------------------------------------------------------------------------

def _query_reads(query: dict) -> set[str]:
    reads = {type_id(str(query.get('type')))}
    if query.get('view'):
        reads.add(view_id(str(query['view'])))
    pivot = query.get('pivot')
    if isinstance(pivot, dict):
        reads.add(f'relation:{pivot.get("relation")}')
        if isinstance(pivot.get('source'), dict):
            reads |= _query_reads(pivot['source'])
    return reads


def _reads(component: dict, worked: dict) -> set[str]:
    """The definitions a card stands on: what its query names, and what working it out used (the standing's lines, a query card's definitions)."""
    reads = _query_reads(component['query']) if 'query' in component else set()
    result = worked.get('result') or {}
    reads |= {l['id'] for l in (result.get('standing') or {}).get('lines', []) if isinstance(l, dict) and 'id' in l}
    reads |= {d['id'] for d in result.get('definitions') or [] if isinstance(d, dict) and 'id' in d}
    return reads


def cards(conn, user: dict | None) -> tuple[list[dict], dict]:
    """The cards of the boards this person may open, board by board, at most MAX_CARDS: ([{'board', 'component', 'author'}], {'boards', 'cards', 'capped', 'left'})."""
    picked, left, boards = [], 0, 0
    for summary in sorted(dashboards.list_dashboards(conn, user), key=lambda b: b['id']):
        boards += 1
        record = dashboards._found(conn, user, summary['id'])
        for component in record['spec']['components']:
            if len(picked) >= MAX_CARDS:
                left += 1
                continue
            picked.append({'board': record, 'component': component, 'author': summary['may_change']})
    return picked, {'boards': boards, 'cards': len(picked), 'capped': left > 0, 'left': left}


def work_out(conn, user: dict | None, picked: list[dict]) -> dict[tuple, dict]:
    """{(board id, card id): the card worked out for this person}, with the board's default parameters and no filter picked."""
    out: dict[tuple, dict] = {}
    by_board: dict[int, list[dict]] = {}
    for p in picked:
        by_board.setdefault(p['board']['id'], []).append(p)
    for board_id, ps in by_board.items():
        spec = ps[0]['board']['spec']
        worked = dashboards.evaluate(conn, user, {**spec, 'components': [p['component'] for p in ps]}, {}, dashboards._defaults(spec), ps[0]['author'])
        out.update({(board_id, w['id']): w for w in worked})
    return out


def compare(picked: list[dict], now: dict, after: dict, touched: set[str]) -> list[dict]:
    """The cards that read what is touched, or whose figure moves: board, card, now, after, change."""
    rows = []
    for p in picked:
        key = (p['board']['id'], p['component']['id'])
        a, b = figure(now[key]), figure(after[key])
        if a != b or (_reads(p['component'], now[key]) | _reads(p['component'], after[key])) & touched:
            rows.append({'board': {'id': p['board']['id'], 'name': p['board']['name']}, 'card': {'id': p['component']['id'], 'title': p['component']['title']},
                         'now': a, 'after': b, 'change': change(a, b)})
    return rows


# --- the definitions as they were last confirmed ---------------------------------------------------------------------------------------------------------

def under(conn, elements: list[str]) -> set[str]:
    """What reads these elements, all the way down (element_dep; a dataset a pipeline writes passes it on)."""
    found, todo = set(), list(elements)
    while todo:
        for (reader,) in conn.execute('SELECT element_id FROM element_dep WHERE depends_on = ?', (todo.pop(),)).fetchall():
            if reader not in found and reader not in elements:
                found.add(reader)
                todo.append(reader)
                if reader.startswith('pipeline:'):
                    todo += [d for (d,) in conn.execute("SELECT depends_on FROM element_dep WHERE element_id = ? AND depends_on LIKE 'dataset:%'", (reader,)).fetchall()]
    return found


def as_last_confirmed(copy, elements: list[str], confirmed_now: bool) -> None:
    """On a copy only: each element as it was last confirmed before this change (its content and the dataset versions it was confirmed on) and, under it, what went
    back for another look as it was last confirmed. `confirmed_now`: the change is already confirmed on the copy, so "before" is the confirmation before the latest
    one; an element nobody had confirmed before goes back to waiting for its first confirmation."""
    versions: dict[str, int] = {}
    waiting = [e for e in under(copy, elements) if (row := element_row(copy, e)) is not None and row['state'] == 'needs_look']
    for element_id in [*elements, *waiting]:
        mine = element_id in elements
        rows = copy.execute('SELECT content_json, dataset_versions_json FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 2', (element_id,)).fetchall()
        last = (rows[1:] if mine and confirmed_now else rows)[:1]
        if not last:
            if mine and confirmed_now:
                copy.execute("UPDATE element_state SET state = 'checked' WHERE element_id = ?", (element_id,))
            continue
        copy.execute("UPDATE element_state SET content_json = ?, state = 'confirmed' WHERE element_id = ?", (last[0][0], element_id))
        if mine:
            versions.update(json.loads(last[0][1] or '{}'))
    for name, version in versions.items():
        found = copy.execute('SELECT id FROM dataset WHERE name = ? AND version = ?', (name, version)).fetchone()
        if found:
            copy.execute('INSERT OR REPLACE INTO current_dataset(name, dataset_id) VALUES (?, ?)', (name, found[0]))


def answers(conn, user: dict | None, touched: set[str]) -> dict:
    """The saved answers that used any of these definitions: this person's own by their question ({'id', 'question'}), everyone else's as a count."""
    from ontology_poc_generator.workspace_questions import _mine
    where, args = _mine(user)
    mine, others = [], 0
    for i, question, definitions, types, own in conn.execute(f'SELECT id, question, definitions_json, types_json, ({where}) FROM qa_question ORDER BY id DESC LIMIT {MAX_ANSWERS}', args).fetchall():
        try:
            used = {d.get('id') for d in json.loads(definitions or '[]') if isinstance(d, dict)} | {type_id(str(t.get('id'))) for t in json.loads(types or '[]') if isinstance(t, dict)}
        except (ValueError, AttributeError):
            continue
        if used & touched:
            if own:
                mine.append({'id': i, 'question': question})
            else:
                others += 1
    return {'mine': sorted(mine, key=lambda a: a['id'])[:MAX_NAMED], 'others': others}


# --- the preview ---------------------------------------------------------------------------------------------------------------------------------------

def _elements(conn, payload: dict, user: dict | None) -> list[str]:
    """The elements a confirm request names, refused (404) the way the confirmation itself would refuse one this person may not see."""
    from ontology_poc_generator.batch_confirm import _members
    from ontology_poc_generator.review_queue import _row_for
    if 'items' in payload:
        _members(conn, user, payload.get('dataset'), payload.get('version'))
        items = payload.get('items')
        if not isinstance(items, list) or not all(isinstance(i, dict) and isinstance(i.get('element'), str) for i in items):
            raise TypeRefused(tr('要带上这一组里要确认的项目', 'Send the items of this group to confirm'))
        return [i['element'] for i in items]
    _row_for(conn, payload.get('element'), user)
    return [payload['element']]


def impact(conn, user: dict | None, payload: dict) -> dict:
    """{element, version, seen?, new_values?} (what the confirm button sends) or {dataset, version, items} (what confirming one upload's group sends): the board cards
    the confirmation would move, {'refused': why it would be refused, or None; 'cards': [{board, card, now, after, change}]; 'answers': {mine, others}; 'checked':
    {boards, cards, capped, left}}. Nothing is written."""
    from ontology_poc_generator.batch_confirm import confirm_group
    from ontology_poc_generator.review_queue import confirm_item
    if not isinstance(payload, dict):
        raise TypeRefused(tr('请求要是一个对象', 'The request must be an object'))
    elements = _elements(conn, payload, user)
    who = user['display_name'] if user else payload.get('who')
    with workspace_copy(conn) as copy:
        picked, checked = cards(copy, user)
        try:
            (confirm_group if 'items' in payload else confirm_item)(copy, payload, who, user)
        except (TypeRefused, SelfConfirmation) as exc:
            return {'refused': str(exc), 'cards': [], 'answers': {'mine': [], 'others': 0}, 'checked': checked}
        after = work_out(copy, user, picked)
        touched = {*elements, *under(copy, elements)}
        as_last_confirmed(copy, elements, confirmed_now=True)
        now = work_out(copy, user, picked)
    return {'refused': None, 'cards': compare(picked, now, after, touched), 'answers': answers(conn, user, touched), 'checked': checked}


def upload_impact(copy, user: dict | None, upload) -> tuple[object, dict]:
    """On a copy: (what `upload()` returns, the board cards it moves as impact() words them). "Now" is the copy before the upload: nothing waits yet."""
    picked, checked = cards(copy, user)
    now = work_out(copy, user, picked)
    confirmed = {e for (e,) in copy.execute("SELECT element_id FROM element_state WHERE state = 'confirmed'")}
    written = upload()
    after = work_out(copy, user, picked)
    touched = {e for (e,) in copy.execute("SELECT element_id FROM element_state WHERE state != 'confirmed'")} & confirmed
    return written, {'refused': None, 'cards': compare(picked, now, after, touched), 'answers': answers(copy, user, touched), 'checked': checked}
