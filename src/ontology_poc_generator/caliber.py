"""The 口径 of a number: the confirmed definitions it stands on, each as one line a reader can check, generated from the definitions themselves.

    剔除 状态码 = 2（已取消），Bob 确认于 订单 v1

A line is coloured only while its definition is confirmed. Once it is not (a new upload moved the data under it, or somebody changed it) the line says so, with the
reason the definition carries, and everything drawn from it goes grey (explorer, dashboards). Nothing here decides who may see a definition: the callers pass only
elements their person may read.
"""
from __future__ import annotations

import json

from ontology_poc_generator.derived_properties import describe as describe_derived
from ontology_poc_generator.object_types import DERIVED_PREFIX, ENUM_PREFIX, RELATION_PREFIX, TYPE_PREFIX, VIEW_PREFIX, _content, _settled_since, element_row, presented_row, stale_word
from ontology_poc_generator.lang import tr
from ontology_poc_generator.object_views import in_out_text

def _state_word(state):
    words = {'proposed': tr('模型提出了，还没有人确认', 'Proposed by the model, not confirmed yet'), 'checked': tr('已经提出，还没有另一位确认', 'Proposed, waiting for a second person to confirm'),
             'needs_look': tr('需要再看', 'Needs another look'), 'rejected': tr('被退回了', 'Sent back')}
    return words.get(state, state)


def _kind_word(kind):
    return {'type': tr('对象类型', 'Object type'), 'meaning': tr('含义', 'Meaning'), 'relation': tr('关系', 'Relation'), 'view': tr('视图', 'View'), 'derived': tr('派生属性', 'Derived property')}[kind]


def _type_name(conn, english: str) -> str:
    row = element_row(conn, f'{TYPE_PREFIX}{english}')
    return _content(row)['name'] if row else english


def _view_text(conn, content: dict) -> str:
    parts = [in_out_text(conn, content)] if content['filters'] else []
    latest = content.get('latest')
    if latest:
        parts.insert(0, tr(f'每个 {"、".join(latest["key"])} 只留 {latest["order"]} 最新的一行', f'Keep only the latest row by {latest["order"]} for each {", ".join(latest["key"])}'))
    return tr('；', '; ').join(parts)


def _meaning_text(content: dict) -> str:
    codes = tr('、', ', ').join(f'{e["value"]} {e["label"]}' for e in content['values'] if e['label'])
    return f'{content["column"]}{tr("：", ": ")}{codes}'


def _text(conn, element_id: str, content: dict) -> str:
    if element_id.startswith(VIEW_PREFIX):
        return _view_text(conn, content)
    if element_id.startswith(ENUM_PREFIX):
        return _meaning_text(content)
    if element_id.startswith(DERIVED_PREFIX):
        return describe_derived(conn, content)
    if element_id.startswith(RELATION_PREFIX):
        return f'{content["name"]}{tr("：", ": ")}{_type_name(conn, content["from"])} → {_type_name(conn, content["to"])}{tr("（", " (")}{content["from_column"]} = {content["to_column"]}{tr("）", ")")}'
    return content['name']


def _name(conn, element_id: str, content: dict) -> str:
    if element_id.startswith(ENUM_PREFIX):
        return f'{_type_name(conn, content["type"])}.{content["column"]}'
    if element_id.startswith(DERIVED_PREFIX):
        return f'{_type_name(conn, content["type"])}.{content["name"]}'
    return content['name']


def _kind(element_id: str) -> str:
    return ('view' if element_id.startswith(VIEW_PREFIX) else 'meaning' if element_id.startswith(ENUM_PREFIX) else 'derived' if element_id.startswith(DERIVED_PREFIX)
            else 'relation' if element_id.startswith(RELATION_PREFIX) else 'type')


def line_of(conn, element_id: str) -> dict:
    """One definition as a line: {'id', 'kind', 'name', 'state', 'confirmed', 'text' (the definition), 'by' and 'on' (who confirmed it, on which dataset versions), 'line'
    (the sentence a reader sees), 'reason' (why it needs a look, or what state it is in)}. A definition that is gone says so and is not confirmed."""
    row = presented_row(conn, element_row(conn, element_id))   # a type whose value rules are not known to hold is not confirmed to a reader
    if row is None or not row['content_json']:
        return {'id': element_id, 'kind': _kind(element_id), 'name': element_id.split(':', 1)[1], 'state': None, 'confirmed': False, 'text': '', 'by': None, 'on': None,
                'line': tr('这条定义已经不在了', 'This definition no longer exists'), 'reason': tr('这条定义已经不在了', 'This definition no longer exists'), 'stale_word': None}
    content = _content(row)
    last = conn.execute('SELECT confirmed_by, dataset_versions_json FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 1', (element_id,)).fetchone()
    by, on = (last[0], ' '.join(f'{n} v{v}' for n, v in json.loads(last[1]).items())) if last else (None, None)
    text = _text(conn, element_id, content)
    confirmed = row['state'] == 'confirmed'
    stored = _settled_since(conn, row) if row['state'] == 'needs_look' and row['reason'] and not row.get('untrusted') else row['reason']   # as the pages read it: a parent confirmed again says so
    reason = None if confirmed else (stored if row['state'] in ('needs_look', 'rejected') and stored else _state_word(row['state']))
    sentence = (tr(f'{text}，{by} 确认于 {on}', f'{text}, confirmed by {by} on {on}') if confirmed and by and on else text if confirmed
                else tr(f'{text}（{reason}）', f'{text} ({reason})'))
    return {'id': element_id, 'kind': _kind(element_id), 'name': _name(conn, element_id, content), 'state': row['state'], 'confirmed': confirmed, 'text': text,
            'by': by, 'on': on, 'line': sentence, 'reason': reason, 'stale_word': stale_word(row['cause'], row['via']) if row['state'] == 'needs_look' else None}


def lines_of(conn, element_ids: list[str]) -> list[dict]:
    """The lines of these definitions, each once, in the order given."""
    return [line_of(conn, e) for e in dict.fromkeys(element_ids)]


def grey_reasons(lines: list[dict]) -> list[str]:
    """Why what stands on these definitions is not in colour, one sentence for each that is not confirmed; empty when all are."""
    return [tr(f'{_kind_word(l["kind"])}「{l["name"]}」：{l["reason"]}', f'{_kind_word(l["kind"])} "{l["name"]}": {l["reason"]}') for l in lines if not l['confirmed']]


def _roots(conn, element_id: str, seen: frozenset = frozenset()) -> list[str]:
    """The definitions at the bottom of the chain behind one that is not confirmed: what it reads that is not confirmed either, down to the ones that read nothing
    unconfirmed (the code meaning whose values moved, the type whose data changed). The definition itself when nothing under it is the cause."""
    under = [d for (d,) in conn.execute("SELECT d.depends_on FROM element_dep d JOIN element_state s ON s.element_id = d.depends_on WHERE d.element_id = ? AND s.state != 'confirmed' ORDER BY d.depends_on",
                                       (element_id,)) if d not in seen]
    return [r for d in under for r in _roots(conn, d, seen | {element_id})] or [element_id]


def root_reason(conn, lines: list[dict]) -> str | None:
    """The reason at the bottom of the chain, as one sentence: a definition that is not confirmed because of what is under it says "原因见……", and what a reader needs is
    the reason of the definition under it that is not confirmed for a reason of its own. None when everything is confirmed."""
    grey = next((l for l in lines if not l['confirmed']), None)
    if grey is None:
        return None
    root = line_of(conn, _roots(conn, grey['id'])[0])
    return tr(f'{_kind_word(root["kind"])}「{root["name"]}」：{root["reason"]}', f'{_kind_word(root["kind"])} "{root["name"]}": {root["reason"]}')
