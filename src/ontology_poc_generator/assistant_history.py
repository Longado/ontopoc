"""The assistant's builder-mode turns (query, model, pipeline, and whatever mode comes next), kept per person beside the saved Ask questions.

A turn is the mode, the message, the scope the person had, when, a compact copy of the result card (the draft or suggestion as returned, its assumptions and
self-check; never the model's raw text and never a row), and what happened next if it is known (applied, saved as <name>, not applied). Like an Ask question
it is the person's own: nobody else reads it, whatever the role. The newest HISTORY_LIMIT turns of a person are kept, the older ones dropped.

A card is not a snapshot to show for ever. Opened later, it is shown only if this person still sees everything it names (a type, a view, a dataset, a pipeline,
a column of a type); otherwise the card is withheld and says how many things are hidden, never which. The scope is redacted entry by entry. The checks are the
ones the rest of the workspace uses (workspace_questions._may_see, type_access, workspace_pipelines.pipeline_visible)."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re

from ontology_poc_generator.lang import tr
from ontology_poc_generator.object_types import TYPE_PREFIX, VIEW_PREFIX, element_row, type_id
from ontology_poc_generator.type_access import dataset_hidden, hidden_columns
from ontology_poc_generator.workspace_pipelines import pipeline_id, pipeline_visible
from ontology_poc_generator.workspace_questions import HISTORY_LIMIT, QaRefused, _may_see, _mine
from ontology_poc_generator.workspace_store import current_dataset

MAX_MESSAGE = 4000
MAX_CARD = 80000        # characters of the compact card; a bigger one is kept as a stub that says so
MODE = re.compile(r'[a-z][a-z_]{0,23}')
OUTCOMES = ('applied', 'saved', 'not_applied')
DROPPED = {'raw', 'rows', 'records', 'samples', 'examples', 'without_value_examples', 'unreadable_examples', 'keys'}   # what the model said word for word, and the objects behind a count


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _compact(value):
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items() if k not in DROPPED}
    if isinstance(value, list):
        return [_compact(v) for v in value]
    return value


def _scope(scope) -> dict:
    """The scope as it is kept: only what a scope can name (datasets, types, a pipeline or dataset target); anything else is not kept."""
    scope = scope if isinstance(scope, dict) else {}
    out = {}
    if isinstance(scope.get('datasets'), list):
        out['datasets'] = [str(x)[:200] for x in scope['datasets'] if isinstance(x, str)][:50]
    if isinstance(scope.get('types'), list):
        out['types'] = [str(x)[:200] for x in scope['types'] if isinstance(x, str)][:50]
    target = scope.get('target')
    if isinstance(target, dict) and target.get('kind') in ('pipeline', 'dataset') and isinstance(target.get('name'), str):
        out['target'] = {'kind': target['kind'], 'name': target['name'][:200], 'label': str(target.get('label') or '')[:200]}
    return out


def _named(scope: dict, card: dict) -> dict:
    """What the turn names, for the visibility check on opening: {types, views, datasets, pipelines, columns: {type id: [column]}}."""
    named = {'types': list(scope.get('types', [])), 'views': [], 'datasets': list(scope.get('datasets', [])), 'pipelines': [], 'columns': {}}
    target = scope.get('target')
    if target:
        named['pipelines' if target['kind'] == 'pipeline' else 'datasets'].append(target['name'])
    for p in card.get('proposed') or []:
        if isinstance(p, dict) and isinstance(p.get('id'), str):
            named['types'].append(p['id'])
            if isinstance(p.get('dataset'), str):
                named['datasets'].append(p['dataset'])
            props = [q.get('column') for q in (p.get('properties') or []) if isinstance(q, dict)]
            cols = [c for c in [*(p.get('key') or []), *(p.get('left_out') or []), *props] if isinstance(c, str)]
            if cols:
                named['columns'][p['id']] = sorted(set(cols))
    for s in card.get('steps') or []:
        step = s.get('step') if isinstance(s, dict) else None
        if isinstance(step, dict) and step.get('type') == 'input':
            if isinstance(step.get('dataset'), str):
                named['datasets'].append(step['dataset'])
            if isinstance(step.get('view'), str):
                named['views'].append(step['view'])
    return {k: (sorted(set(v)) if isinstance(v, list) else v) for k, v in named.items()}


def _clean_outcome(outcome) -> dict:
    if not isinstance(outcome, dict) or outcome.get('state') not in OUTCOMES:
        raise QaRefused(tr('结果只能是 applied、saved 或 not_applied', 'The outcome must be applied, saved or not_applied'))
    name = outcome.get('name')
    return {'state': outcome['state'], **({'name': name.strip()[:200]} if isinstance(name, str) and name.strip() else {}), 'at': _now()}


def record(conn, user: dict | None, mode, message, scope, card, outcome=None) -> dict:
    """Keeps one turn for this person and returns {id}. `mode` is any word but "ask" (Ask answers are kept by workspace_questions.ask)."""
    if not isinstance(mode, str) or not MODE.fullmatch(mode) or mode == 'ask':
        raise QaRefused(tr('模式不对：只记录 ask 以外的助手模式', 'Not a mode to keep: only the assistant modes other than ask are kept here'))
    if not isinstance(message, str) or not message.strip():
        raise QaRefused(tr('请带上这一轮的消息', 'A turn needs its message'))
    if not isinstance(card, dict):
        raise QaRefused(tr('请带上结果卡', 'A turn needs its result card'))
    scope = _scope(scope)
    kept = _compact(card)
    if len(json.dumps(kept, ensure_ascii=False)) > MAX_CARD:
        kept = {'truncated': True}
    named = _named(scope, kept)
    cursor = conn.execute('INSERT INTO assistant_turn(user_id, mode, message, scope_json, at, card_json, named_json, outcome_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                          (user['id'] if user else None, mode, message.strip()[:MAX_MESSAGE], json.dumps(scope, ensure_ascii=False), _now(), json.dumps(kept, ensure_ascii=False),
                           json.dumps(named, ensure_ascii=False), json.dumps(_clean_outcome(outcome), ensure_ascii=False) if outcome else None))
    where, args = _mine(user)
    conn.execute(f'DELETE FROM assistant_turn WHERE {where} AND id NOT IN (SELECT id FROM assistant_turn WHERE {where} ORDER BY id DESC LIMIT {HISTORY_LIMIT})', (*args, *args))
    return {'id': cursor.lastrowid}


def _own(conn, user, turn_id) -> tuple:
    where, args = _mine(user)
    found = conn.execute(f'SELECT id, mode, message, scope_json, at, card_json, named_json, outcome_json FROM assistant_turn WHERE id = ? AND {where}', (turn_id, *args)).fetchone()
    if found is None:
        raise QaRefused(tr('没有这一轮', 'No such turn'), 404)
    return found


def mark(conn, user: dict | None, turn_id: int, outcome) -> dict:
    """What happened to the card next: applied, saved as <name>, or not applied. Only the person's own turn; the last word stays."""
    _own(conn, user, turn_id)
    where, args = _mine(user)
    conn.execute(f'UPDATE assistant_turn SET outcome_json = ? WHERE id = ? AND {where}', (json.dumps(_clean_outcome(outcome), ensure_ascii=False), turn_id, *args))
    return {'id': turn_id}


def delete(conn, user: dict | None, turn_id: int) -> dict:
    _own(conn, user, turn_id)
    where, args = _mine(user)
    conn.execute(f'DELETE FROM assistant_turn WHERE id = ? AND {where}', (turn_id, *args))
    return {'deleted': turn_id}


def listing(conn, user: dict | None) -> list[dict]:
    """The person's own turns, newest first, as the rail needs them: no card and no scope (those are read when a turn is opened, and checked then)."""
    where, args = _mine(user)
    return [{'id': i, 'mode': mode, 'message': message, 'asked_at': at, 'outcome': json.loads(outcome) if outcome else None}
            for i, mode, message, at, outcome in conn.execute(f'SELECT id, mode, message, at, outcome_json FROM assistant_turn WHERE {where} ORDER BY id DESC LIMIT {HISTORY_LIMIT}', args)]


def _hidden(conn, user: dict | None, named: dict) -> dict[str, list[str]]:
    """What the turn names that this person cannot see now, by kind (a thing that is gone counts as hidden)."""
    gone = {'types': [], 'views': [], 'datasets': [], 'pipelines': [], 'columns': []}
    for t in named.get('types', []):
        if not _may_see(conn, user, type_id(t)):
            gone['types'].append(t)
    for v in named.get('views', []):
        if not _may_see(conn, user, f"{VIEW_PREFIX}{v}"):
            gone['views'].append(v)
    for d in named.get('datasets', []):
        if current_dataset(conn, d) is None or dataset_hidden(conn, d, user):
            gone['datasets'].append(d)
    for p in named.get('pipelines', []):
        row = element_row(conn, pipeline_id(p))
        if row is None or not pipeline_visible(conn, row, user):
            gone['pipelines'].append(p)
    for t, cols in named.get('columns', {}).items():
        if any(c in hidden_columns(conn, type_id(t), user) for c in cols):
            gone['columns'].append(t)
    return {k: v for k, v in gone.items() if v}


def fetch(conn, user: dict | None, turn_id: int) -> dict:
    """One turn as it reads now. When the person can no longer see something it names, the card is withheld (`withheld` counts what is hidden by kind and names none of it)
    and each scope entry they cannot see is {hidden: true}; the message is their own words and stays."""
    i, mode, message, scope_json, at, card_json, named_json, outcome_json = _own(conn, user, turn_id)
    scope, named, outcome = json.loads(scope_json), json.loads(named_json), json.loads(outcome_json) if outcome_json else None
    gone = _hidden(conn, user, named)
    seen = {k: set(v) for k, v in gone.items()}

    def shown(kind, name):
        return {'kind': kind, 'hidden': True} if name in seen.get(kind, ()) else {'kind': kind, 'name': name}
    out_scope = {}
    if 'datasets' in scope:
        out_scope['datasets'] = [shown('datasets', d) for d in scope['datasets']]
    if 'types' in scope:
        out_scope['types'] = [shown('types', x) for x in scope['types']]
    if 'target' in scope:
        target = scope['target']
        kind = 'pipelines' if target['kind'] == 'pipeline' else 'datasets'
        out_scope['target'] = {'kind': target['kind'], 'hidden': True} if target['name'] in seen.get(kind, ()) else target
    if outcome and outcome.get('name') and mode in ('pipeline', 'model'):   # what was saved is a pipeline's or a type's name: the same rule
        row = element_row(conn, pipeline_id(outcome['name']) if mode == 'pipeline' else f'{TYPE_PREFIX}{outcome["name"]}')
        if row is None or (mode == 'pipeline' and not pipeline_visible(conn, row, user)) or (mode == 'model' and not _may_see(conn, user, type_id(outcome['name']))):
            outcome = {**{k: v for k, v in outcome.items() if k != 'name'}, 'hidden': True}
    body = {'id': i, 'mode': mode, 'message': message, 'asked_at': at, 'scope': out_scope, 'outcome': outcome}
    if gone:
        count = sum(len(v) for v in gone.values())
        return {**body, 'withheld': {k: len(v) for k, v in gone.items()},
                'reason': tr(f'这一轮的结果卡里有 {count} 处你现在看不到的内容（已隐藏），所以不再显示它。可以用“再起草一次”重新来。',
                             f'The card of this turn names {count} thing(s) you can no longer see (hidden), so it is no longer shown. Use "Draft again" to start over.')}
    return {**body, 'card': json.loads(card_json)}
