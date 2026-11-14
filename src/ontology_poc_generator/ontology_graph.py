"""The ontology drawn: the relation graph (types as nodes, relations as edges) and the lineage graph (dataset -> type -> relation, view, action -> saved answer),
and what the type page says about what uses it. Everything is read from what already exists (element_state, element_dep, the confirmations, the saved answers);
nothing is stored here.

Who sees what is decided by the functions the other pages use: a type is a node only for a person who may see it (object_types._visible), a relation an edge only
when both its types are visible, a view and an action follow their type, a saved answer is its asker's. A person a row rule limits reads counts of their own rows
(visible_rows, check_relation with user), never of the whole data, and the words of a stale cause, which may quote whole-data counts and keys, are not sent to them.

A node that needs another look says why in one of four causes (数据变了, 定义改了, 上一步过时, 更上游过时). The two first are a node's own: the reason the store
wrote when the data or the definition moved. The two last mean its own data and definition are as they were and what it reads is not: the cause then
carries the words of the node at the root of the chain and says how far away it is. The reasons are sentences (object_types._flag, _flag_readers); `_own_cause`
reads them in one place.
"""
from __future__ import annotations

import json

from ontology_poc_generator.object_actions import action_visible
from ontology_poc_generator.object_relations import _relation_visible, cardinality_false, check_relation
from ontology_poc_generator.object_types import (
    ACTION_PREFIX, ENUM_PREFIX, RELATION_PREFIX, TYPE_PREFIX, VIEW_PREFIX, TypeRefused, _content, _label, _state_view, _type_row, _types_read, _visible, element_row, type_id, visible_rows)
from ontology_poc_generator.object_views import view_visible
from ontology_poc_generator.row_rules import restriction
from ontology_poc_generator.type_access import dataset_hidden
from ontology_poc_generator.workspace_questions import _mine, reopen
from ontology_poc_generator.workspace_store import current_dataset

CAUSE_LABEL = {'data': '数据变了', 'definition': '定义改了', 'upstream': '上一步过时', 'far_upstream': '更上游过时'}
ANSWER_NODES = 15   # the latest saved answers of the person, drawn in the lineage
HIDDEN_WORDS = '原因里有全部数据的统计，你受行规则限制，看不到'
CARDINALITY_NAME = {'many_to_one': '多对一', 'one_to_many': '一对多', 'one_to_one': '一对一'}


# --- why something needs another look ------------------------------------------------------------------------------------------------------------

def _own_cause(reason: str | None) -> str:
    """'definition' for a reason that says a definition changed (it ends 要重新确认), 'cascade' for one that only says what it reads needs a look
    (it begins 它用的 and says 需要再看), else 'data': a new version of a dataset moved what a check found."""
    reason = reason or ''
    if reason.endswith('要重新确认'):
        return 'definition'
    if reason.startswith('它用的') and '需要再看' in reason:
        return 'cascade'
    return 'data'


def _chain(conn, element_id: str, path: tuple = ()) -> dict | None:
    """For an element in needs_look: {depth, own, root, text}: `own` the root's cause (data / definition; None when the chain is cut), `root` the element id at its
    end, `text` the root's reason, `depth` the steps from the element to it (0: the element itself)."""
    row = element_row(conn, element_id)
    if row is None or row['state'] != 'needs_look':
        return None
    own = _own_cause(row['reason'])
    if own != 'cascade':
        return {'depth': 0, 'own': own, 'root': element_id, 'text': row['reason']}
    parents = [p for (p,) in conn.execute('SELECT depends_on FROM element_dep WHERE element_id = ?', (element_id,)) if p not in path and p != element_id]
    found = [c for c in (_chain(conn, p, (*path, element_id)) for p in parents) if c]
    if not found:   # what it read has been put right since, and it has not been looked at again
        return {'depth': 1, 'own': None, 'root': element_id, 'text': row['reason']}
    best = min(found, key=lambda c: c['depth'])
    if best['own'] and best['depth'] == 0 and element_id.startswith(TYPE_PREFIX) and best['root'].startswith(f'{ENUM_PREFIX}{element_id[len(TYPE_PREFIX):]}:'):
        return {**best, 'at': element_id}   # the meanings of its own columns are the type's own input: the data or definition moved under it, it is not one step behind a parent
    return {**best, 'depth': best['depth'] + 1, 'at': element_id}


def _cause(conn, chain: dict | None, hide: bool) -> dict | None:
    if chain is None:
        return None
    kind = chain['own'] if chain['depth'] == 0 else 'upstream' if chain['depth'] == 1 else 'far_upstream'
    root_row = element_row(conn, chain['root'])
    root = _label(conn, chain['root']) if root_row and chain.get('at', chain['root']) != chain['root'] else None
    return {'cause': kind, 'label': CAUSE_LABEL[kind], 'root_cause': chain['own'], 'root': root, 'short': None if hide else _short(conn, kind, root_row),
            'text': None if hide else chain['text'], **({'text_hidden': HIDDEN_WORDS} if hide else {})}


def _short(conn, kind: str, root_row: dict | None) -> str | None:
    """What moved, in a few words for the node itself: for a data cause on a set of meanings, '订单 第 2 版 状态码 取值变了'."""
    if kind != 'data' or root_row is None or not root_row['element_id'].startswith(ENUM_PREFIX):
        return None
    content = _content(root_row)
    dataset = current_dataset(conn, content['dataset'])
    return f'{content["dataset"]} 第 {dataset["version"]} 版 {content["column"]} 取值变了' if dataset else None


def _limited(conn, row: dict | None, user: dict | None) -> bool:
    """Whether a row rule limits this person on any type the element is about. Unlike object_types.limited_on this holds for actions too: an action's own definition
    quotes no counts, but the cause on it is the words of the element at the root of the chain, which do."""
    return row is not None and any(restriction(conn, t, user) is not None for t in _types_read(row))


def stale_cause(conn, row: dict, user: dict | None) -> dict | None:
    """The cause of an element that needs another look, or None when it does not. The words are held back when the person is limited on this element or on the one
    at the root of the chain, whose reason they are."""
    chain = _chain(conn, row['element_id'])
    return _cause(conn, chain, _limited(conn, row, user) or (chain is not None and _limited(conn, element_row(conn, chain['root']), user)))


# --- the pieces both graphs draw -----------------------------------------------------------------------------------------------------------------

def _small(conn, row: dict, user: dict | None) -> dict:
    """A view or an action as a line under its type: id, name, state."""
    content = _content(row)
    return {'id': row['element_id'], 'key': content['name'], 'name': content['name'], 'state': row['state'], 'stale': stale_cause(conn, row, user)}


def _mine_answers(conn, user: dict | None) -> list[tuple[int, str, str, list[str]]]:
    """The person's own saved answers, newest first: (id, question, when, the element ids of the types it read)."""
    where, args = _mine(user)
    return [(i, q, at, [type_id(t['id']) for t in json.loads(types)]) for i, q, at, types in conn.execute(
        f'SELECT id, question, asked_at, types_json FROM qa_question WHERE {where} ORDER BY id DESC', args)]


def _by_type(conn, user: dict | None) -> dict[str, dict]:
    """For each type element id: the views, actions and relations this person may see that are about it."""
    out: dict[str, dict] = {}
    for prefix, kind, can_see in ((VIEW_PREFIX, 'views', view_visible), (ACTION_PREFIX, 'actions', action_visible), (RELATION_PREFIX, 'relations', _relation_visible)):
        for (element_id,) in conn.execute('SELECT element_id FROM element_state WHERE element_id LIKE ? ORDER BY element_id', (f'{prefix}%',)).fetchall():
            row = element_row(conn, element_id)
            if not can_see(conn, row, user):
                continue
            content = _content(row)
            for t in ([type_id(content['from']), type_id(content['to'])] if kind == 'relations' else [type_id(content['type'])]):
                out.setdefault(t, {'views': [], 'actions': [], 'relations': []})[kind].append(row)
    return out


def _type_nodes(conn, user: dict | None) -> list[dict]:
    """Every type this person may see, as a node: what the drawer shows."""
    by_type = _by_type(conn, user)
    answers = _mine_answers(conn, user)
    nodes = []
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objtype:%' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        if not _visible(conn, row, user):
            continue
        content = _content(row)
        dataset = current_dataset(conn, content['dataset'])
        state = _state_view(conn, row, user)
        limited = restriction(conn, element_id, user) is not None
        near = by_type.get(element_id, {'views': [], 'actions': [], 'relations': []})
        nodes.append({
            'id': element_id, 'kind': 'type', 'key': content['english_name'], 'name': content['name'], 'description': content['description'], 'state': row['state'],
            'model_draft': state['model_draft'], 'objects': visible_rows(conn, row, dataset, user) if dataset else None, 'rows_limited': limited,
            'dataset': {'name': content['dataset'], 'version': dataset['version'] if dataset else None},
            'key_columns': content['key'], 'properties': [{'name': p['name'], 'column': p['column'], 'type': p['type'], 'key': p['column'] in content['key']} for p in content['properties']],
            'confirmed_by': state['confirmed_by'], 'confirmed_at': state['confirmed_at'], 'confirmed_on': state['confirmed_on'], 'proposed_by': state['proposed_by'],
            'stale': stale_cause(conn, row, user),
            'views': [_small(conn, r, user) for r in near['views']], 'actions': [_small(conn, r, user) for r in near['actions']],
            'relations': [{'id': r['element_id'], 'key': _content(r)['english_name'], 'name': _content(r)['name']} for r in near['relations']],
            'answers': sum(1 for _, _, _, types in answers if element_id in types)})
    return nodes


def _verdict_words(result: dict) -> str | None:
    """Why the declared cardinality is false on today's data, with the counts and no key values."""
    n, f, one, many = result['numbers'], result['fanout'], result['one'], result['many']
    words = []
    if n['extra_rows']:
        words.append(f'{one["dataset"]} 里“{one["column"]}”有 {f["keys"]} 个值重复，连上它们的 {f["source_rows"]} 行会多出 {f["extra_rows"]} 行')
    if n['many_repeats']:
        words.append(f'一对一不成立：{many["dataset"]} 里“{many["column"]}”有 {n["many_repeats"]} 个值出现了不止一次')
    return '；'.join(words) or None


def _edge(conn, row: dict, user: dict | None) -> dict:
    content = _content(row)
    result = check_relation(conn, content, record=False, user=user)
    ends = {e: element_row(conn, type_id(content[e])) for e in ('from', 'to')}
    limited = any(restriction(conn, r['element_id'], user) is not None for r in ends.values())
    one_end = {'many_to_one': 'to', 'one_to_many': 'from'}.get(content['cardinality'])
    edge = {'id': row['element_id'], 'kind': 'relation', 'key': content['english_name'], 'name': content['name'], 'from': type_id(content['from']), 'to': type_id(content['to']),
            'from_name': _content(ends['from'])['name'], 'to_name': _content(ends['to'])['name'], 'from_column': content['from_column'], 'to_column': content['to_column'],
            'cardinality': content['cardinality'], 'cardinality_label': CARDINALITY_NAME[content['cardinality']], 'arrow_to': type_id(content[one_end]) if one_end else None,
            'state': row['state'], 'stale': stale_cause(conn, row, user), 'rows_limited': limited, 'problems': result['problems']}
    if result['problems']:
        return {**edge, 'connected': None, 'of': None, 'unmatched': None, 'cardinality_ok': None, 'cardinality_text': None}
    n = result['numbers']
    false = cardinality_false(result)
    return {**edge, 'connected': n['matched'], 'of': n['rows'], 'unmatched': n['unmatched'], 'cardinality_ok': not false, 'cardinality_text': _verdict_words(result) if false else None}


# --- the relation graph --------------------------------------------------------------------------------------------------------------------------

def relation_graph(conn, user: dict | None) -> dict:
    """{nodes: the types this person may see, edges: the relations between them (a relation whose type they may not see is not there)}. An edge says how many
    rows of the many side find the one side ('连上 N / M 行'), and whether the declared cardinality holds on the data now."""
    nodes = _type_nodes(conn, user)
    shown = {n['id'] for n in nodes}
    edges = []
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'relation:%' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        if _relation_visible(conn, row, user) and {type_id(_content(row)[e]) for e in ('from', 'to')} <= shown:
            edges.append(_edge(conn, row, user))
    return {'nodes': nodes, 'edges': edges, 'rows_limited': any(n['rows_limited'] for n in nodes)}


# --- the lineage graph ---------------------------------------------------------------------------------------------------------------------------

def _dataset_node(conn, name: str, readers: list[dict], user: dict | None) -> dict:
    dataset = current_dataset(conn, name)
    return {'id': f'dataset:{name}', 'kind': 'dataset', 'key': name, 'name': name, 'state': None, 'version': dataset['version'], 'uploaded_at': dataset['imported_at'], 'who': dataset['who'],
            'used_for': [r['name'] for r in readers], 'link': not dataset_hidden(conn, name, user), 'stale': None}


def _answer_node(conn, user: dict | None, answer_id: int, question: str, asked_at: str) -> tuple[dict, list[str]] | None:
    """A saved answer as a node, with the ids of what it read (types, relations, views). None when this person may no longer read it."""
    now = reopen(conn, user, answer_id)
    if 'withheld' in now:
        return None
    named = [d['id'] for d in now.get('definitions', [])] + [type_id(t['id']) for t in now.get('types', [])]
    stale, changed = now.get('stale', []), now.get('changed', [])
    cause, state = None, 'confirmed'
    if changed or stale:
        state = 'needs_look'
        moved = [c for c in (element_row(conn, c['id']) for c in changed) if c]
        chain = min((c for c in (_chain(conn, r['element_id']) for r in moved) if c), key=lambda c: c['depth'], default=None)
        hide = any(_limited(conn, element_row(conn, e), user) for e in named)   # the answer read these: a limit on any of them is a limit on the words
        if chain:
            cause = _cause(conn, {**chain, 'depth': chain['depth'] + 1}, hide)
        elif changed:
            cause = {'cause': 'definition', 'label': CAUSE_LABEL['definition'], 'root_cause': 'definition', 'root': None, 'text': f'它用的{"、".join(c["name"] for c in changed)}后来改过'}
        else:
            cause = {'cause': 'data', 'label': CAUSE_LABEL['data'], 'root_cause': 'data', 'root': None,
                     'text': '；'.join(f'它读的“{s["dataset"]}”是第 {s["read"]} 版，现在是第 {s["now"]} 版' if s['now'] else f'它读的“{s["dataset"]}”已经不在了' for s in stale)}
    return {'id': f'answer:{answer_id}', 'kind': 'answer', 'key': answer_id, 'name': question, 'state': state, 'asked_at': asked_at, 'stale': cause}, list(dict.fromkeys(named))


def lineage_graph(conn, user: dict | None) -> dict:
    """Datasets -> object types -> relations, views and actions -> the person's saved answers, from element_dep and the answers' own record. A dataset is drawn
    when a type this person may see reads it (a builder also sees one nothing reads); a hidden type is not there at all."""
    types = _type_nodes(conn, user)
    nodes: list[dict] = list(types)
    for t in types:
        for kind in ('view', 'action'):
            nodes += [{**v, 'kind': kind, 'type': t['key'], 'type_name': t['name']} for v in t[f'{kind}s']]
    shown = {n['id'] for n in types}
    relations = [e for e in relation_graph(conn, user)['edges'] if {e['from'], e['to']} <= shown]
    nodes += relations
    by_dataset: dict[str, list[dict]] = {}
    for t in types:
        by_dataset.setdefault(t['dataset']['name'], []).append(t)
    for (name,) in conn.execute('SELECT name FROM current_dataset ORDER BY name').fetchall():
        readers = by_dataset.get(name, [])
        if readers or (user is None or user['role'] != 'viewer') and not dataset_hidden(conn, name, user):
            nodes.append(_dataset_node(conn, name, readers, user))
    ids = {n['id'] for n in nodes}
    edges = [{'from': t, 'to': r['id']} for r in relations for t in (r['from'], r['to'])]
    for n in nodes:   # what each element reads that is drawn: the datasets under a type, the type under a view or action
        if n['kind'] in ('type', 'view', 'action'):
            for (parent,) in conn.execute('SELECT depends_on FROM element_dep WHERE element_id = ?', (n['id'],)).fetchall():
                if parent in ids and (n['kind'] == 'type') == parent.startswith('dataset:'):
                    edges.append({'from': parent, 'to': n['id']})
    drawn = 0
    for answer_id, question, asked_at, _types in _mine_answers(conn, user):
        made = _answer_node(conn, user, answer_id, question, asked_at) if drawn < ANSWER_NODES else None
        reads = [r for r in made[1] if r in ids] if made else []
        if reads:
            drawn += 1
            nodes.append(made[0])
            edges += [{'from': r, 'to': made[0]['id']} for r in reads]
    return {'nodes': nodes, 'edges': list({(e['from'], e['to']): e for e in edges}.values()), 'rows_limited': any(n['rows_limited'] for n in types)}


# --- the type page: what uses it, and the data it stands on ---------------------------------------------------------------------------------------

def type_uses(conn, english_name: str, user: dict | None) -> dict:
    """{data: the dataset, its version and when it was uploaded, used_by: [{kind, label, count, items}]} for the type page. Kinds with nothing are left out."""
    row = _type_row(conn, english_name, user)
    content = _content(row)
    dataset = current_dataset(conn, content['dataset'])
    element_id = row['element_id']
    near = _by_type(conn, user).get(element_id, {'views': [], 'actions': [], 'relations': []})
    answers = [{'id': i, 'name': q} for i, q, _at, types in _mine_answers(conn, user) if element_id in types]
    kinds = [('views', '视图', [{'id': _content(r)['name'], 'name': _content(r)['name'], 'state': r['state']} for r in near['views']]),
             ('actions', '行为', [{'id': _content(r)['name'], 'name': _content(r)['name'], 'state': r['state']} for r in near['actions']]),
             ('relations', '关系', [{'id': _content(r)['english_name'], 'name': _content(r)['name'], 'state': r['state']} for r in near['relations']]),
             ('answers', '你存下的回答', answers)]
    return {'data': {'dataset': content['dataset'], 'version': dataset['version'] if dataset else None, 'uploaded_at': dataset['imported_at'] if dataset else None,
                     'who': dataset['who'] if dataset else None, 'link': dataset is not None and not dataset_hidden(conn, content['dataset'], user)},
            'used_by': [{'kind': k, 'label': label, 'count': len(items), 'items': items} for k, label, items in kinds if items]}
