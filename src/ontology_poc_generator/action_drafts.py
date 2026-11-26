"""The assistant drafts an action (OAG, the action part; ops/cards/oag-action-drafts.md). A question that asks for a change ("把订单 DD20260004 标成已交付") is
answered with a draft of a confirmed action: which action, which object (by its whole key), the values and a reason from the question. The person submits it
through the existing route (POST /api/workspace/actions/submit) and another builder approves it, as for any submit. Asking writes nothing: no record, no log
line, no data; a draft is a reply.

- The model is told (as `ontology.actions` in its request, and a short addition after the Q&A prompt) only the confirmed actions the asker may submit
  (submittable): name, kind, type, key, the properties it writes with their confirmed meanings, what a property's values are picked from (by name, never the
  values), the conditions as text. An action that reads a column a builder marked "don't send values" is not told. Never a row value: the object's current
  values are read by code and shown to the person only.
- The model writes {"action": {"name", "key", "values", "reason"}} in place of a query, or {"action": {"name": null, "type"}} when no action can make the change.
  Code checks the draft with object_actions.check_submit, the checks a submit makes, writing nothing; a check that fails is a refusal in the submit's words
  and names the check. A key the asker may not read is answered exactly as a key nobody has (a create on it is drafted as on a free key).
- An action that is not confirmed (or needs another look) is refused naming it and who can confirm it, as an unconfirmed definition is: before the model is asked
  when the question names it, or when the model names it.
- One draft per question; a reply that chains steps is refused.
- DRAFTS switches it off. Off, or for a person with no confirmed action they may submit (every viewer), every prompt, answer, refusal and stored record is what it
  was before drafts (tests/test_action_drafts_main.py). Only the JSON way of asking drafts; a question the model answers as OntoPoc Query text is as it was.
"""
from __future__ import annotations

from ontology_poc_generator.lang import tr
from ontology_poc_generator.object_actions import (
    SubmitRefused, _action_row, _label, _of_type, _phrase, _shown_columns, _texts, _type_name, action_visible, check_submit, conditions_of,
    describe, kind_of, parameters, waiting_on)
from ontology_poc_generator.object_types import TypeRefused, _content, element_row, enum_id, type_id
from ontology_poc_generator.object_views import meaning_labels
from ontology_poc_generator.type_access import hidden_columns, hidden_values

DRAFTS = True   # whether a question may be answered with a draft of an action; off, Q&A is as it was before drafts
MARK = 'action_draft'   # the key that marks an item the answerer worked out as a draft (or its refusal), for workspace_questions._answered
FIELDS = ('name', 'key', 'values', 'reason', 'type')   # what the model's draft may say: anything more is a chain of steps
KEPT_OUT = ('current', 'current_text', 'change_text', 'beside')   # what a kept draft leaves out: the object's values, read again when it is reopened

PROMPT_VERSION = 'workspace_actions.v1'
PROMPT = '''

Changes to the data (added for this workspace):
- `ontology.actions` lists the confirmed actions the asker may submit: name, kind (edit, create, delete), type, key, the properties it writes (a code column
  with `meanings`: write the code) and the conditions the object must meet, as text.
- A question that asks to CHANGE data (mark, set, change, add, create, delete, remove) is not a query. Write
  "query": {"action": {"name": <an action name from ontology.actions>, "key": {<each key property>: "<the value as the question writes it>"},
  "values": {<each property the action writes>: "<the value from the question>"}, "reason": "<why, in the question's words, or "">"}}.
  A delete has no values; a create's key goes in "key".
- When no listed action can make the change: "query": {"action": {"name": null, "type": <the type key it is about, or null>}}. Never pick an action
  that does not fit and never make up a value.
- One action per question, no chain of steps. Code checks it and shows it to the person, who submits it; your reply changes nothing.
'''


def submittable(conn, user: dict | None, sc: dict) -> list[dict]:
    """The confirmed actions this person may submit, on a type in their Q&A scope, ordered by name: their rows. None for a viewer (action_visible)."""
    out = []
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objaction:%' AND state = 'confirmed' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        content = _content(row)
        submitters = content.get('submitters') or []
        if content['type'] in sc['types'] and action_visible(conn, row, user) and (not submitters or (user is not None and user['id'] in submitters)):
            out.append(row)
    return out


def told(conn, user: dict | None, sc: dict) -> list[dict]:
    """The actions as the model is told them: [] when drafts are off or this person may submit none (then nothing about Q&A changes). An action that reads a
    column whose values are kept from the model is left out."""
    if not DRAFTS:
        return []
    out = []
    for row in submittable(conn, user, sc):
        content = _content(row)
        t = sc['types'][content['type']]['content']
        key = list(_content(element_row(conn, type_id(content['type'])))['key'])
        kind = kind_of(content)
        written = [*(key if kind == 'create' else []), *content['properties']]
        if set([*written, *(c['column'] for c in conditions_of(content))]) & hidden_values(conn, type_id(content['type'])):
            continue
        props = {p['column']: p for p in _content(element_row(conn, type_id(content['type'])))['properties']}
        names = {c: p['name'] for c, p in props.items()}
        said = []
        for column in written:
            p = props[column]
            source = (content.get('choices') or {}).get(column)
            said.append({'path': column, 'name': p['name'], 'type': p['type'], **({'key': True} if column in key and kind == 'create' else {}),
                         **({'meanings': meaning_labels(conn, content['type'], column)} if p['enum'] else {}),
                         **({'picked_from': tr(f'{_type_name(conn, source["type"])} 的 {source["column"]}', f'{source["column"]} of {_type_name(conn, source["type"])}')} if source else {})})
        out.append({'name': content['name'], 'kind': kind, 'type': content['type'], 'type_name': t['name'], 'description': content.get('description') or '', 'key': key,
                    'properties': said, 'conditions': tr('、', ', ').join(_phrase(conn, content['type'], names, c) for c in conditions_of(content))})
    return out


def prompt(more: tuple[str, str] | None) -> tuple[str, str]:
    """What the Q&A adds to the prompt, with the addition for drafts after it: (its version, its text)."""
    return (f'{more[0]}+{PROMPT_VERSION}', more[1] + PROMPT) if more else (PROMPT_VERSION, PROMPT)


def answering(conn, user: dict | None, sc: dict, question: str, answer):
    """The engine's answer(query, ...) that reads a query {"action": ...} as a draft (or its refusal), and every other query as the engine does."""
    def drafted(query, asked, used=None, **more):
        if isinstance(query, dict) and 'action' in query:
            return {MARK: True, **draft(conn, user, sc, question, query)}
        return answer(query, asked, used, **more)
    for name in ('applied', 'ran', 'unmatched'):
        if hasattr(answer, name):
            setattr(drafted, name, getattr(answer, name))
    return drafted


def finish(item: dict) -> dict:
    """A drafted item (or its refusal) as Q&A returns and keeps it."""
    keys = ('status', 'reason', 'reasoning', 'query', 'draft', 'refusal', 'steps', 'definitions', 'types', 'datasets', 'data_as_of')
    return {k: item[k] for k in keys if k in item}


def kept(result: dict) -> dict:
    """A draft as it is kept with the question: without the object's current values (reopen reads them again)."""
    return {**result, 'draft': {k: v for k, v in result['draft'].items() if k not in KEPT_OUT}}


def again(conn, user: dict | None, record: dict, question: str) -> dict:
    """A kept draft read again for the person reopening it: the same draft checked now, with the object's values as they are now (or the refusal now)."""
    if not DRAFTS or not isinstance(record.get('query'), dict) or 'action' not in record['query']:
        return record
    from ontology_poc_generator.workspace_questions import scope
    fresh = draft(conn, user, scope(conn, user), question, record['query'])
    return {**{k: v for k, v in record.items() if k not in ('draft', 'refusal')}, **{k: fresh[k] for k in ('status', 'reason', 'draft', 'refusal', 'steps', 'definitions', 'types', 'datasets') if k in fresh},
            'again': True}


def blockers(conn, user: dict | None, question: str) -> list[dict]:
    """The actions this person may see that the question names by name and that are not confirmed, as workspace_questions._blockers gives a definition: with
    what each stands on that is not confirmed (its type, its meanings), bottom first."""
    from ontology_poc_generator.workspace_questions import _named
    out = []
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objaction:%' AND state != 'confirmed' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        if action_visible(conn, row, user) and _named(question, _content(row)['name']):
            out.append(_unsettled_line(conn, row, user))
    return out


def _unsettled_line(conn, row: dict, user: dict | None) -> dict:
    from ontology_poc_generator.workspace_questions import _definition_line
    content = _content(row)
    because = [_definition_line(conn, element_row(conn, w['id']), user) for w in waiting_on(conn, content) if element_row(conn, w['id']) is not None]
    return {**_definition_line(conn, row, user), 'type': content['type'], 'because': because}


# --- a draft ------------------------------------------------------------------------------------------------------------------------------------------------

def _step(name: str, text: str, failed: bool = False) -> dict:
    return {'name': name, 'text': text, **({'failed': True} if failed else {})}


def _refused(reason: str, refusal: dict, steps: list[dict]) -> dict:
    return {'status': 'refused', 'reason': reason, 'refusal': refusal, 'steps': steps, 'definitions': [], 'types': [], 'datasets': {}}


def _code(conn, english: str, column: str, enum: bool, value):
    """A code column's value as its code: a value that is a meaning's label of exactly one code (and is no code itself) is that code; anything else as written."""
    if not enum or not isinstance(value, str):
        return value
    labels = meaning_labels(conn, english, column)
    codes = [c for c, l in labels.items() if l == value.strip()]
    return codes[0] if value.strip() not in labels and len(codes) == 1 else value


def draft(conn, user: dict | None, sc: dict, question: str, query: dict) -> dict:
    """The draft the model's {"action": ...} asks for, checked as a submit would be and writing nothing; or the refusal that says why there is none."""
    asked = query['action']
    understood = _step(tr('理解问题', 'Understand the question'), tr('问题要改数据：起草一个行为，不算数', 'The question asks for a change: draft an action, no number'))
    if not isinstance(asked, dict) or set(asked) - set(FIELDS):
        why = tr('一个问题只起草一个行为，不连着做几步：请一次问一个改动', 'One question drafts one action, not a chain of steps: ask for one change at a time')
        return _refused(tr(f'没有起草：{why}', f'Not drafted: {why}'), {'kind': 'action_check', 'check': 'one_draft', 'said': why}, [understood, _step(tr('结果', 'Result'), why, True)])
    name = asked.get('name')
    if name in (None, ''):
        return _no_action(conn, user, sc, asked.get('type'), understood)
    try:
        row = _action_row(conn, name if isinstance(name, str) else str(name), user)
    except TypeRefused as no:
        return _check_refused(str(no), 'action', name, understood)
    content = _content(row)
    if row['state'] != 'confirmed':
        from ontology_poc_generator.workspace_questions import _refused_unsettled
        result = _refused_unsettled([_unsettled_line(conn, row, user)])
        return {**result, 'steps': [understood, _step(tr('核对行为', 'Check the action'), tr(f'行为「{content["name"]}」还没有确认', f'The action "{content["name"]}" is not confirmed'), True)],
                'definitions': [], 'types': [], 'datasets': {}}
    type_row = element_row(conn, type_id(content['type']))
    t = _content(type_row)
    props = {p['column']: p for p in t['properties']}
    key = asked.get('key')
    if isinstance(key, dict) and kind_of(content) == 'create':
        key = {c: _code(conn, content['type'], c, c in props and props[c]['enum'], v) for c, v in key.items()}
    values = asked.get('values')
    if isinstance(values, dict):
        values = {c: _code(conn, content['type'], c, c in props and props[c]['enum'], v) for c, v in values.items()}
    elif values is None:
        values = {}
    reason = asked.get('reason') if isinstance(asked.get('reason'), str) and asked['reason'].strip() else question   # no reason written: the question is the reason
    reason = ' '.join(reason.split())
    payload = {'action': content['name'], 'key': key, 'params': values, 'reason': reason}
    who = user['display_name'] if user else None
    try:
        planned = check_submit(conn, row, payload, who, user, hidden_as_missing=True)
    except SubmitRefused as no:
        return _check_refused(str(no), no.check, content['name'], understood)
    return _drafted(conn, user, row, planned, understood)


def _check_refused(said: str, check: str, name, understood: dict) -> dict:
    return _refused(tr(f'没有起草：{said}', f'Not drafted: {said}'), {'kind': 'action_check', 'check': check, 'action': name if isinstance(name, str) else None, 'said': said},
                    [understood, _step(tr('核对行为', 'Check the action'), said, True)])


def _drafted(conn, user: dict | None, row: dict, planned: dict, understood: dict) -> dict:
    content, rec, t = _content(row), planned['record'], planned['type']
    kind, english = rec['op'], t['english_name']
    hidden = hidden_columns(conn, type_id(english), user) if user is not None else set()
    before = {c: v for c, v in _of_type(t, rec['before']).items() if c not in hidden}
    after = {c: v for c, v in _of_type(t, rec['after']).items() if c not in hidden}
    before_text, after_text, change_text = _texts(conn, kind, t, user, before, after)
    names = {p['column']: p['name'] for p in t['properties']}
    shown = f'{t["name"]} {" + ".join(str(rec["key"][c]) for c in t["key"])}'
    label = lambda c, v: _label(conn, english, c, v) if v is not None else None
    if kind == 'create':
        current, asked, values = {}, {**rec['key'], **after}, {**rec['key'], **after}
        beside = [{'column': c, 'name': names[c], 'current': None, 'asked': label(c, v)} for c, v in asked.items()]
        said = tr(f'新建 {shown}' + (f'，{after_text}' if after else ''), f'create {shown}' + (f', {after_text}' if after else ''))
    elif kind == 'delete':
        current, asked, values = {c: before[c] for c in [*t['key'], *_shown_columns(conn, t, user, before)] if c in before}, {}, {}
        beside = [{'column': c, 'name': names[c], 'current': label(c, v), 'asked': None} for c, v in current.items()]
        said = tr(f'删除 {shown}', f'delete {shown}')
    else:
        current, asked, values = before, after, dict(after)
        beside = [{'column': c, 'name': names[c], 'current': label(c, before.get(c)), 'asked': label(c, v)} for c, v in after.items()]
        said = tr(f'{shown}，改成 {after_text}', f'{shown}, to {after_text}')
    dataset = planned['dataset']
    line = {'action': {'id': content['name'], 'name': content['name'], 'kind': kind, 'type': english, 'type_name': t['name'], 'says': describe(conn, content),
                       'version': row['version'], 'parameters': parameters(conn, content, user)},
            'object': shown, 'key': rec['key'], 'params': {} if kind == 'delete' else dict(rec['after']), 'values': values, 'reason': rec['reason'],
            'current': current, 'asked': asked, 'current_text': before_text if kind != 'create' else '', 'asked_text': after_text if kind != 'delete' else '', 'change_text': change_text,
            'beside': beside, 'submit': {'action': content['name'], 'key': rec['key'], 'params': {} if kind == 'delete' else dict(rec['after']), 'reason': rec['reason']},
            'dataset': dataset['name'], 'dataset_version': dataset['version']}
    reason = tr(f'草拟了「{content["name"]}」：{said}。还没有提交：核对后由你提交，另一位建设者批准之后才会改数据。',
                f'Drafted "{content["name"]}": {said}. Nothing is submitted yet: check it and submit it; the data changes only after another builder approves it.')
    steps = [understood, _step(tr('核对行为', 'Check the action'), tr(f'「{content["name"]}」已确认，你可以提交；提交前的检查都通过了（没有写入）：{line["action"]["says"]}',
                                                                      f'"{content["name"]}" is confirmed and yours to submit; every check a submit makes passed (nothing written): {line["action"]["says"]}')),
             _step(tr('结果', 'Result'), reason)]
    return {'status': 'draft', 'reason': reason, 'draft': line, 'steps': steps, 'definitions': _definitions(conn, row, t, kind),
            'types': [{'id': english, 'name': t['name']}], 'datasets': {dataset['name']: dataset['version']}}


def _definitions(conn, row: dict, t: dict, kind: str) -> list[dict]:
    """The definitions a draft stands on, as an answer names them: the action, its type, the meanings of the code columns it writes or tests."""
    content = _content(row)
    coded = {p['column'] for p in t['properties'] if p['enum']}
    columns = [*(t['key'] if kind == 'create' else []), *content['properties'], *(c['column'] for c in conditions_of(content))]
    ids = [row['element_id'], type_id(t['english_name']), *dict.fromkeys(enum_id(t['english_name'], c) for c in columns if c in coded)]
    out = []
    for element_id in ids:
        held = element_row(conn, element_id)
        if held is None:
            continue
        c = _content(held)
        kind_name = ('action', c['name']) if element_id.startswith('objaction:') else ('meaning', f'{t["name"]}.{c["column"]}') if element_id.startswith('enum:') else ('type', c['name'])
        out.append({'id': element_id, 'kind': kind_name[0], 'name': kind_name[1], 'state': held['state'], 'version': held['version'], 'confirmed_by': held['confirmed_by'],
                    'confirmed_at': held['confirmed_at'], **({'type': t['english_name']} if kind_name[0] == 'action' else {})})
    return out


def _no_action(conn, user: dict | None, sc: dict, type_key, understood: dict) -> dict:
    """No confirmed action can make the change: the actions this person may submit on that type (all of them, when the type is not one they may ask about)."""
    mine = [_content(r) for r in submittable(conn, user, sc)]
    on = type_key if isinstance(type_key, str) and type_key in sc['types'] else None
    listed = [c for c in mine if on is None or c['type'] == on]
    items = tr('；', '; ').join(tr(f'「{c["name"]}」（{describe(conn, c)}）', f'"{c["name"]}" ({describe(conn, c)})') for c in listed)
    if on is not None:
        type_name = sc['types'][on]['content']['name']
        reason = (tr(f'没有已确认的行为能做这个改动。你在「{type_name}」上能提交的行为：{items}。', f'No confirmed action can make this change. The actions you may submit on "{type_name}": {items}.') if listed
                  else tr(f'没有已确认的行为能做这个改动：「{type_name}」上没有你能提交的行为。', f'No confirmed action can make this change: there is no action you may submit on "{type_name}".'))
    else:
        reason = (tr(f'没有已确认的行为能做这个改动。你能提交的行为：{items}。', f'No confirmed action can make this change. The actions you may submit: {items}.') if listed
                  else tr('没有已确认的行为能做这个改动，你也没有能提交的行为。', 'No confirmed action can make this change, and there is no action you may submit.'))
    return _refused(reason, {'kind': 'no_action', 'type': on, 'actions': [{'name': c['name'], 'type': c['type'], 'says': describe(conn, c)} for c in listed]},
                    [understood, _step(tr('核对行为', 'Check the action'), reason, True)])
