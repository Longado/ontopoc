"""Q&A on the workspace: a question is answered only from what people confirmed, and says exactly why when it cannot.

The engine is the one the per-run questions use (ontology_questions: the model writes a structured query from a catalog, code runs it on the rows;
answer_checks: the model says how each confirmed definition is used and code checks that against the query). What changes here is where it reads from:
the scope is the confirmed object types this person may see (type_access.visible_type_ids), the code meanings and relations confirmed on them, read at the
current version of each dataset. The model gets the catalog (names, typed properties, meaning labels, relation keys, category values) and never a row;
a column a builder marked "don't send values" goes without its values and meanings.

A question that names a definition which is not confirmed (proposed, checked, needs another look, sent back) is refused before the model is asked, naming it,
why, and who could confirm it; there is no answer from the old definition. Every answer is stored with the definitions it used (their version and who confirmed
them) and the dataset versions it read; reopened later it says whether a dataset has a newer version and whether the asker may still see every type it used.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re

from ontology_poc_generator.answer_checks import _uses, choose_rows, definition_catalog, definition_check, refusal
from ontology_poc_generator.named_views import name_views
from ontology_poc_generator.object_relations import _relation_visible, check_relation
from ontology_poc_generator.object_types import ENUM_PREFIX, RELATION_PREFIX, TYPE_PREFIX, VIEW_PREFIX, _confirmers, _content, _visible, dataset_columns, element_row, enum_id, type_id
from ontology_poc_generator.object_views import describe, kept_positions, view_visible
from ontology_poc_generator.ontology_questions import _catalog, answer_query, ask_questions
from ontology_poc_generator.public_ontology import build_graph, normalize_proposal
from ontology_poc_generator.relation_checks import unmatched_answer, with_relation_gaps
from ontology_poc_generator.type_access import hidden_values, visible_type_ids
from ontology_poc_generator.workspace_store import current_dataset, dataset_records

MAX_QUESTION = 300
HISTORY_LIMIT = 100
ROW_KEYS = {'examples', 'without_value_examples', 'keys', 'samples'}   # the objects behind a count: a viewer reads the counts and not these
STATE_WORDS = {'proposed': '模型提出了，还没有人确认', 'checked': '已经提出，还没有另一位确认', 'needs_look': '需要再看', 'rejected': '被退回了'}


class QaRefused(ValueError):
    """The request cannot be served: str() says why in Chinese, `status` is the HTTP status."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _confirmation(conn, element_id: str) -> tuple:
    row = conn.execute('SELECT confirmed_by, confirmed_at FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 1', (element_id,)).fetchone()
    return row or (None, None)


# --- the scope ------------------------------------------------------------------------------------------------------------------------------------

def scope(conn, user: dict | None) -> dict:
    """{'types': {english name: {'row', 'content', 'dataset'}}, 'meanings': {english name: {column: {'row', 'labels'}}}, 'relations': {english name: {'row', 'content'}},
    'views': {name: {'row', 'content'}}}: the confirmed types this person may see (and whose dataset is still there), the confirmed meanings of their code columns,
    the confirmed relations whose two ends are among them, and the confirmed views of those types whose conditions stand on confirmed meanings (a view on a column
    marked "don't send values" is left out: what it says would tell the model the meanings)."""
    types, meanings, relations, views = {}, {}, {}, {}
    for name in visible_type_ids(conn, user, confirmed_only=True):
        row = element_row(conn, type_id(name))
        content = _content(row)
        dataset = current_dataset(conn, content['dataset'])
        if dataset is None:
            continue
        types[name] = {'row': row, 'content': content, 'dataset': dataset}
        for p in content['properties']:
            held = element_row(conn, enum_id(name, p['column'])) if p['enum'] else None
            if held and held['state'] == 'confirmed':
                meanings.setdefault(name, {})[p['column']] = {'row': held, 'labels': {e['value']: e['label'] for e in _content(held)['values'] if e['label']}}
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'relation:%' AND state = 'confirmed' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        content = _content(row)
        if content['from'] in types and content['to'] in types:
            relations[content['english_name']] = {'row': row, 'content': content}
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objview:%' AND state = 'confirmed' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        content = _content(row)
        columns = {f['column'] for f in content['filters']}
        if content['type'] in types and view_visible(conn, row, user) and columns <= set(meanings.get(content['type'], {})) \
                and not columns & hidden_values(conn, type_id(content['type'])):
            views[content['name']] = {'row': row, 'content': content}
    return {'types': types, 'meanings': meanings, 'relations': relations, 'views': views}


def _unsettled(conn, user: dict | None) -> list[dict]:
    """The types and relations this person may see that are not confirmed, with the state, the reason and who could confirm: what is outside the scope
    for a reason a builder can do something about. A viewer sees none (they see only confirmed ones)."""
    out = []
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objtype:%' OR element_id LIKE 'relation:%' OR element_id LIKE 'objview:%' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        if row['state'] == 'confirmed':
            continue
        visible = (_visible(conn, row, user) if element_id.startswith(TYPE_PREFIX) else view_visible(conn, row, user) if element_id.startswith(VIEW_PREFIX)
                   else _relation_visible(conn, row, user))
        if visible:
            out.append(_definition_line(conn, row, user))
    return out


def scope_line(conn, user: dict | None) -> dict:
    """What the Q&A page says about what may be asked: the confirmed types in scope, the relations, and (for builders) what is left out and why."""
    sc = scope(conn, user)
    return {'types': [{'id': k, 'name': v['content']['name']} for k, v in sc['types'].items()],
            'relations': [{'id': k, 'name': v['content']['name']} for k, v in sc['relations'].items()],
            'views': [{'id': k, 'name': k, 'type': v['content']['type']} for k, v in sc['views'].items()],
            'left_out': _unsettled(conn, user)}


# --- definitions that are not settled -----------------------------------------------------------------------------------------------------------------

def _kind_and_name(conn, row: dict) -> tuple[str, str]:
    content = _content(row)
    element_id = row['element_id']
    if element_id.startswith(ENUM_PREFIX):
        return 'meaning', f'{_content(element_row(conn, type_id(content["type"])))["name"]}.{content["column"]}'
    return ('type' if element_id.startswith(TYPE_PREFIX) else 'view' if element_id.startswith(VIEW_PREFIX) else 'relation'), content['name']


def _definition_line(conn, row: dict, user: dict | None) -> dict:
    """One definition as a refusal names it: what it is, its state, the reason it needs a look, and the builders who could confirm it."""
    kind, name = _kind_and_name(conn, row)
    _, confirmers = _confirmers(conn, row, user)
    return {'id': row['element_id'], 'kind': kind, 'name': name, 'state': row['state'], 'reason': row['reason'] if row['state'] in ('needs_look', 'rejected') else None,
            'proposed_by': row['proposed_by'], 'who_can_confirm': confirmers, **({'type': _content(row)['type']} if kind == 'view' else {})}


def _causes(conn, row: dict, user: dict | None) -> list[dict]:
    """The definitions behind an unsettled one: for a type, its meanings that are not confirmed; for a relation, its end types that are not; for a view, its type
    and the meanings its conditions use."""
    if row['element_id'].startswith(VIEW_PREFIX):
        content = _content(row)
        found = [r['element_id'] for r in (element_row(conn, e) for e in (type_id(content['type']), *(enum_id(content['type'], c) for c in dict.fromkeys(f['column'] for f in content['filters']))))
                 if r and r['state'] != 'confirmed']
    elif row['element_id'].startswith(TYPE_PREFIX):
        found = [r['element_id'] for r in (element_row(conn, e) for (e,) in conn.execute("SELECT depends_on FROM element_dep WHERE element_id = ? AND depends_on LIKE 'enum:%'", (row['element_id'],)))
                 if r and r['state'] != 'confirmed']
    elif row['element_id'].startswith(RELATION_PREFIX):
        content = _content(row)
        found = [r['element_id'] for r in (element_row(conn, type_id(content[e])) for e in ('from', 'to')) if r and r['state'] != 'confirmed']
    else:
        found = []
    return [_definition_line(conn, element_row(conn, e), user) for e in found]


def _named(question: str, text: str) -> bool:
    """Does the question say this name? Letters and digits must stand apart from other letters and digits; a name in words is a substring."""
    if text.isascii():
        return re.search(rf'(?<![A-Za-z0-9]){re.escape(text)}(?![A-Za-z0-9])', question, re.I) is not None
    return text in question


def _blockers(conn, user: dict | None, question: str) -> list[dict]:
    """The unsettled definitions this person may see that the question names: a type by its name, a relation when both its types are named. A relation
    or type nobody may see is not looked for, so nothing is said about it."""
    out = []
    for line in _unsettled(conn, user):
        row = element_row(conn, line['id'])
        content = _content(row)
        if line['kind'] == 'type':
            hit = _named(question, content['name']) or _named(question, content['english_name'])
        elif line['kind'] == 'view':
            hit = _named(question, content['name'])
        else:
            ends = [element_row(conn, type_id(content[e])) for e in ('from', 'to')]
            hit = all(r and (_named(question, _content(r)['name']) or _named(question, _content(r)['english_name'])) for r in ends)
        if hit:
            out.append({**line, 'because': _causes(conn, row, user)})
    return out


def _refused_unsettled(blockers: list[dict]) -> dict:
    """The refusal that names the definition at the bottom of the chain (订单.状态码) first, then what stands on it (订单)."""
    lines, names = [], []
    for b in blockers:
        for d in [*b['because'], b]:
            if d['id'] in names:
                continue
            names.append(d['id'])
            why = d['reason'] or STATE_WORDS[d['state']]
            who = f'；可以确认的人：{"、".join(d["who_can_confirm"])}' if d['who_can_confirm'] else ''
            lines.append({**d, 'text': f'{_kind_word(d["kind"])}「{d["name"]}」：{why}{who}'})
    return {'status': 'refused', 'reason': '没有回答：问题用到的定义不是已确认的状态。' + '；'.join(l['text'] for l in lines),
            'refusal': {'kind': 'unsettled', 'definitions': lines}}


def _kind_word(kind: str) -> str:
    return {'type': '对象类型', 'relation': '关系', 'meaning': '含义', 'view': '视图'}[kind]


# --- what the engine reads ----------------------------------------------------------------------------------------------------------------------------

def _inputs(conn, sc: dict) -> dict:
    """The ontology, the rows and the meanings in the shape the engine reads: a dataset is a source (its name without dots, which the engine reads as the end of
    a table name), a type is read from its dataset by its key, a property is an attribute, a confirmed relation binds its one side by the key and the many
    side's column. A relation the engine cannot bind (a one side that is not keyed on the joined column, or a relation between one type) stays out of the
    ontology and is listed in `unusable`."""
    alias = {}
    for t in sc['types'].values():
        name = t['dataset']['name']
        alias.setdefault(name, name.replace('.', '_') if name.replace('.', '_') not in alias.values() else f'{name.replace(".", "_")}_{len(alias)}')
    object_types = [{'key': k, 'label': t['content']['name'], 'populated_from': [{'source': alias[t['dataset']['name']], 'identity': {c: c for c in t['content']['key']}}],
                     'attributes': [{'source': alias[t['dataset']['name']], 'path': p['column']} for p in t['content']['properties']]} for k, t in sc['types'].items()]
    relations, unusable = [], []
    for k, r in sc['relations'].items():
        c = r['content']
        many, one = ('from', 'to') if c['cardinality'] in ('many_to_one', 'one_to_one') else ('to', 'from')
        one_key = sc['types'][c[one]]['content']['key']
        if c['from'] == c['to'] or one_key != [c[f'{one}_column']]:
            unusable.append(k)
            continue
        relations.append({'key': k, 'from': c['from'], 'to': c['to'], 'label': c['name'], 'meaning': c.get('description') or '',
                          'source': alias[sc['types'][c[many]]['dataset']['name']], f'{one}_identity': {one_key[0]: c[f'{many}_column']}})
    sources = {alias[name]: {'records': dataset_records(conn, d), 'requests': []}
               for name, d in {t['dataset']['name']: t['dataset'] for t in sc['types'].values()}.items()}
    meanings = {f'{alias[sc["types"][k]["dataset"]["name"]]}.{column}': {'labels': m['labels']} for k, cols in sc['meanings'].items() for column, m in cols.items()}
    return {'ontology': {'object_types': object_types, 'relations': relations, 'ignored_fields': [], 'open_questions': []}, 'alias': alias, 'unusable': unusable,
            'bundle': {'decision': '', 'sources': sources, 'meanings': meanings}, 'views': _engine_views(conn, sc, alias, sources)}


def _engine_views(conn, sc: dict, alias: dict, sources: dict) -> list[dict]:
    """The confirmed views in the shape answer_checks reads (see named_views.compile_views): `source` is the dataset's alias, `definition` says a single
    condition in the words the check looks for ("a view that leaves a meaning out"), anything else is 'combined' and is only ever read by name; `positions` are
    the rows (from 1) it keeps of the dataset as read now."""
    out = []
    for name, v in sc['views'].items():
        content, t = v['content'], sc['types'][v['content']['type']]
        source = alias[t['dataset']['name']]
        kinds = {n: c['type'] for n, c in dataset_columns(conn, t['dataset']['id']).items()}
        labels = {f['column']: sc['meanings'][content['type']][f['column']]['labels'] for f in content['filters']}
        positions = kept_positions(sources[source]['records'], kinds, labels, content)
        single = len(content['filters']) == 1 and not content['latest']
        who, at = _confirmation(conn, v['row']['element_id'])
        out.append({'name': name, 'sql_name': None, 'kind': 'filter' if not content['latest'] else 'latest' if not content['filters'] else 'combined', 'source': source, 'state': 'confirmed',
                    'why': None, 'from': describe(content, t['content']['name']), 'confirmed_by': who, 'confirmed_at': at,
                    'definition': {'kind': 'filter', **content['filters'][0]} if single else {'kind': 'combined'}, 'rows': len(positions), 'positions': positions,
                    'element': v['row']['element_id']})
    return out


def _catalog_for_model(conn, sc: dict, parts: dict) -> tuple[dict, list[dict]]:
    """(the catalog the model reads, the definitions it is told). Names, typed properties, meaning labels, relation keys and the values of columns with few
    values; the key columns' values (they identify objects) and every value and meaning of a column marked "don't send values" are left out."""
    ontology, bundle, alias = parts['ontology'], parts['bundle'], parts['alias']
    hidden = {f'{alias[t["dataset"]["name"]]}.{c}' for k, t in sc['types'].items() for c in hidden_values(conn, type_id(k))}
    sent = {f: m for f, m in bundle['meanings'].items() if f not in hidden}
    catalog = _catalog(ontology, {**bundle, 'meanings': sent})
    for entry in catalog['object_types']:
        t = sc['types'][entry['key']]
        kinds = {p['column']: p['type'] for p in t['content']['properties']}
        entry['description'] = t['content'].get('description') or ''
        for a in entry['attributes']:
            if a['path'] in kinds:
                a['type'] = kinds[a['path']]
            if f'{alias[t["dataset"]["name"]]}.{a["path"]}' in hidden or a['path'] in t['content']['key']:
                a.pop('values', None)
                a.pop('meanings', None)
    return catalog, definition_catalog(sent, parts['views'])


def _checked_relations(conn, sc: dict, parts: dict) -> list[dict]:
    """The relation checks (connected rows, the keys that miss) in the shape relation_checks reads, for every confirmed relation in scope: the engine's
    "which orders name a customer the table lacks" is answered from these."""
    out = []
    for k, r in sc['relations'].items():
        c = r['content']
        result = check_relation(conn, c, record=False)
        if result['problems']:
            continue
        many, one = result['many'], result['one']
        out.append({'key': k, 'from': c['from'], 'to': c['to'], 'source': parts['alias'][many['dataset']],
                    'sides': [{'object': one['type'], 'other': many['type'], 'columns': [many['column']], 'lookup': parts['alias'][one['dataset']],
                               'unmatched': result['numbers']['unmatched'], 'unmatched_keys': result['unmatched_keys'], 'samples': result['samples']}]})
    return out


# --- asking -----------------------------------------------------------------------------------------------------------------------------------------------

def _reads(sc: dict, parts: dict, query, used: list, spec) -> tuple[list[str], list[str], set]:
    """(the types the answer read, the relations it walked, the "dataset.column" fields it filtered, shared or grouped by, or the model said it used). From the
    query; for an answer the relation check gave (no query), from the relation the model named."""
    if not query:
        key = spec.get('relation') if isinstance(spec, dict) else None
        return ([sc['relations'][key]['content']['from'], sc['relations'][key]['content']['to']], [key], set()) if key in sc['relations'] else ([], [], set())
    ontology = normalize_proposal(parts['ontology'])
    types = {t['key']: t for t in ontology['object_types']}
    relations = {r['key']: r for r in ontology['relations']}
    dims = query.get('group_by') if isinstance(query.get('group_by'), list) else []
    walked = sorted({k for k in [*(query.get('via') or []), *(k for d in dims if isinstance(d, dict) for k in d.get('via') or [])] if k in relations})
    read = list(dict.fromkeys([query['start'], *[end for k in walked for end in (relations[k]['from'], relations[k]['to'])]]))
    fields = {f for f, _, _ in _uses(query, types, relations) if f} | {u['id'].rpartition('=')[0] for u in used if isinstance(u.get('id'), str)}
    return read, walked, fields


def _used_definitions(conn, sc: dict, parts: dict, read: list[str], walked: list[str], fields: set, views: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """(the definitions the answer stood on with their version and who confirmed them, the types it read, {dataset: version} it read): the types, the
    relations, the views whose rows it read, and the meanings of the code columns the answer used."""
    elements = [type_id(k) for k in read] + [f'{RELATION_PREFIX}{k}' for k in walked]
    elements += [v['element'] for v in views]
    for k in read:
        for column, m in sc['meanings'].get(k, {}).items():
            if f'{parts["alias"][sc["types"][k]["dataset"]["name"]]}.{column}' in fields:
                elements.append(m['row']['element_id'])
    lines = []
    for element_id in dict.fromkeys(elements):
        row = element_row(conn, element_id)
        who, at = _confirmation(conn, element_id)
        kind, name = _kind_and_name(conn, row)
        lines.append({'id': element_id, 'kind': kind, 'name': name, 'state': row['state'], 'version': row['version'], 'confirmed_by': who, 'confirmed_at': at,
                      **({'type': _content(row)['type']} if kind == 'view' else {})})   # a view's page is on its type
    return lines, [{'id': k, 'name': sc['types'][k]['content']['name']} for k in read], {sc['types'][k]['dataset']['name']: sc['types'][k]['dataset']['version'] for k in read}


def _steps(item: dict, types: list[dict], relations: list[str]) -> list[dict]:
    """The steps a person can open: what was understood, which types and relations were found, the query and what came of it, with the check of the definitions.
    A step that failed is shown as failed."""
    failed = item['status'] not in ('answered', 'no_data')
    steps = [{'name': '理解问题', 'text': item.get('reasoning') or '模型没有写理解'}]
    if item.get('query') is not None:
        steps += [{'name': '找对象类型', 'text': '、'.join(t['name'] for t in types) or '没有找到'},
                  {'name': '找关系', 'text': '、'.join(relations) or '这道题用不到关系'},
                  {'name': '改写成查询', 'text': item.get('path') or '', 'query': item['query']}]
    checks = item.get('understood') or []
    if checks:
        steps.append({'name': '核对定义', 'text': '；'.join(f'{c["definition"]}：{c["how"]}' for c in checks)})
    steps.append({'name': '结果', 'text': item.get('reason') or ('没有满足条件的数据' if item['status'] == 'no_data' else '算出了结果'), 'failed': failed})
    return steps


def _strip_rows(value):
    """A viewer's answer without the objects behind its counts."""
    if isinstance(value, dict):
        return {k: _strip_rows(v) for k, v in value.items() if k not in ROW_KEYS}
    return [_strip_rows(v) for v in value] if isinstance(value, list) else value


def _clean_question(question) -> str:
    if not isinstance(question, str) or not question.strip():
        raise QaRefused('请写下要问的问题')
    if len(question.strip()) > MAX_QUESTION:
        raise QaRefused(f'问题最多 {MAX_QUESTION} 个字')
    return question.strip()


def _answered(conn, gateway, user: dict | None, question: str, sc: dict) -> dict:
    parts = _inputs(conn, sc)
    ontology, bundle = parts['ontology'], parts['bundle']
    catalog, definitions = _catalog_for_model(conn, sc, parts)
    relations = _checked_relations(conn, sc, parts)
    graph = build_graph(ontology, bundle)

    applied = []   # the views the last answer was worked out from, kept for the definitions it stood on

    def answer(query, asked, used=None, check=True, told=None):
        checked = definition_check(asked, query, ontology, parts['views'], bundle['meanings'], used, told)
        if checked['unmet']:
            return {**refusal(checked['unmet']), 'understood': checked['understood']}
        reading, reading_graph = bundle, graph
        if checked['apply']:   # the rows the views keep, in every table they are about (a row all of them keep)
            kept = {}
            for v in checked['apply']:
                kept[v['source']] = set(v['positions']) if v['source'] not in kept else kept[v['source']] & set(v['positions'])
            chosen = choose_rows(ontology, bundle, kept)
            reading = {**bundle, 'sources': {**bundle['sources'], **{t: {**bundle['sources'][t], 'records': r} for t, r in chosen.items()}}}
            reading_graph = build_graph(ontology, reading)
        applied[:] = checked['apply']
        now = name_views(with_relation_gaps(answer_query(ontology, reading, query, asked, reading_graph), query, ontology, relations), query, ontology, checked['apply'], None)
        by = {v['name']: v['confirmed_by'] for v in checked['apply']}
        if (now.get('evidence') or {}).get('views'):   # the answer says who stands behind each view it read
            now = {**now, 'evidence': {**now['evidence'], 'views': [{**v, 'confirmed_by': by[v['name']]} for v in now['evidence']['views']]}}
        return {**now, 'understood': checked['understood']} if checked['understood'] else now
    spoken = {}   # what the model said the question asks of a relation, kept for the definitions an answer from the relation check stands on

    def unmatched(spec):
        spoken['spec'] = spec
        return unmatched_answer({**ontology, 'relations': [{'key': k, 'from': r['content']['from'], 'to': r['content']['to']} for k, r in sc['relations'].items()]}, relations, spec)   # also a relation a query cannot walk (its one side is keyed on more than the joined column): the relation check counts it all the same
    answer.unmatched = unmatched
    asked = ask_questions(ontology, bundle, gateway, question, answerer=answer, definitions=definitions, catalog=catalog)
    if asked['error'] or not asked['items']:
        raise QaRefused(asked['error'] or '模型没有给出回答', 502)
    item = asked['items'][0]
    query = item.get('query') if isinstance(item.get('query'), dict) and item['query'].get('start') in sc['types'] else None
    read, walked, fields = _reads(sc, parts, query, item.get('definitions_used') or [], spoken.get('spec')) if item['status'] in ('answered', 'no_data') else ([], [], set())
    lines, types, datasets = _used_definitions(conn, sc, parts, read, walked, fields, applied if item['status'] in ('answered', 'no_data') else [])
    result = {key: item[key] for key in ('status', 'answer', 'path', 'reason', 'reasoning', 'query', 'evidence', 'understood', 'unmet', 'definitions_used') if key in item}
    if item['status'] in ('ontology_gap', 'query_limit') and not item.get('from_relation_check'):
        result['refusal'] = {'kind': 'not_in_scope', 'in_scope': [t['content']['name'] for t in sc['types'].values()], 'left_out': _unsettled(conn, user)}
    elif item['status'] == 'definition_unmet':
        result['refusal'] = {'kind': 'definition_unmet', 'definitions': item.get('unmet') or []}
    return {**result, 'model': asked['model'], 'steps': _steps({**item, **result}, types, [d['name'] for d in lines if d['kind'] == 'relation']), 'definitions': lines, 'types': types, 'datasets': datasets}


def ask(conn, gateway, user: dict | None, question) -> dict:
    """Answer one question from what this person may see and what is confirmed, keep it with the definitions and dataset versions it used, and return it.
    QaRefused (503 without a model, 502 when it failed) when no answer could be worked out at all; a refusal to answer is an answer, saved like the rest."""
    question = _clean_question(question)
    sc = scope(conn, user)
    blockers = _blockers(conn, user, question)
    if blockers:
        result = {**_refused_unsettled(blockers), 'definitions': [], 'types': [], 'datasets': {}, 'steps': [{'name': '核对定义', 'text': '问题里提到的定义还没有确认，没有去问模型', 'failed': True}]}
    elif not sc['types']:
        result = {'status': 'refused', 'reason': '范围里还没有已确认的对象类型，没有东西可以回答。', 'refusal': {'kind': 'not_in_scope', 'in_scope': [], 'left_out': _unsettled(conn, user)},
                  'definitions': [], 'types': [], 'datasets': {}, 'steps': []}
    else:
        if gateway is None:
            raise QaRefused('本机服务没有模型凭据：设置 DEEPSEEK_API_KEY 后重启 ontology_server。', 503)
        result = _answered(conn, gateway, user, question, sc)
    if user is not None and user['role'] == 'viewer':
        result = _strip_rows(result)
    now = _now()
    cursor = conn.execute('INSERT INTO qa_question(user_id, asked_by, question, asked_at, status, answer_json, definitions_json, dataset_versions_json, types_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                          (user['id'] if user else None, user['display_name'] if user else None, question, now, result['status'], json.dumps(result, ensure_ascii=False),
                           json.dumps(result['definitions'], ensure_ascii=False), json.dumps(result['datasets'], ensure_ascii=False), json.dumps(result['types'], ensure_ascii=False)))
    return {'id': cursor.lastrowid, 'question': question, 'asked_at': now, **result}


# --- history ---------------------------------------------------------------------------------------------------------------------------------------------

def _mine(user: dict | None) -> tuple[str, tuple]:
    return ('user_id = ?', (user['id'],)) if user else ('user_id IS NULL', ())


def history(conn, user: dict | None) -> list[dict]:
    """The person's own questions, newest first: nobody's but theirs, whatever the role."""
    where, args = _mine(user)
    return [{'id': i, 'question': q, 'asked_at': at, 'status': s} for i, q, at, s in conn.execute(
        f'SELECT id, question, asked_at, status FROM qa_question WHERE {where} ORDER BY id DESC LIMIT {HISTORY_LIMIT}', args)]


def reopen(conn, user: dict | None, question_id: int) -> dict:
    """A saved answer as it stands now: `stale` lists the datasets it read that have another current version, `changed` the definitions it used that are not as
    they were (not confirmed, or confirmed again since), and when the asker may no longer see a type it used the answer is withheld and says which."""
    where, args = _mine(user)
    found = conn.execute(f'SELECT id, question, asked_at, answer_json FROM qa_question WHERE id = ? AND {where}', (question_id, *args)).fetchone()
    if found is None:
        raise QaRefused('没有这条问题', 404)
    i, question, at, stored = found
    record = json.loads(stored)
    seeing = set(visible_type_ids(conn, user))
    lost = [t['name'] for t in record['types'] if t['id'] not in seeing]
    if lost:
        return {'id': i, 'question': question, 'asked_at': at, 'status': record['status'], 'withheld': {'types': lost},
                'reason': f'这条回答用到的对象类型你现在看不到了：{"、".join(lost)}，所以不再显示它。'}
    stale = []
    for name, read in record['datasets'].items():
        now = current_dataset(conn, name)
        if now is None or now['version'] != read:
            stale.append({'dataset': name, 'read': read, 'now': now['version'] if now else None})
    changed = []
    for d in record['definitions']:
        row = element_row(conn, d['id'])
        if row is None or row['state'] != 'confirmed' or row['version'] != d['version']:
            changed.append({'id': d['id'], 'name': d['name'], 'state': row['state'] if row else None})
    return {'id': i, 'question': question, 'asked_at': at, **record, 'stale': stale, 'changed': changed}
