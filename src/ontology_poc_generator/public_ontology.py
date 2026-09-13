"""Ontology proposed from public source fields, checked against the actual records by code."""
from __future__ import annotations

from collections import defaultdict
import copy
import re

ROLES = ('event', 'affected_object', 'mechanism', 'signal')
_ALL_ROLES = ROLES + ('context',)
TRANSFORMS = ('none', 'split_comma', 'colon_hierarchy')
# The scope question walks these four pairs; each needs a direct relation.
# ponytail: direct relations only; follow relation chains if two-hop paths become common.
_ROLE_PAIRS = (('event', 'affected_object'), ('event', 'mechanism'),
               ('signal', 'affected_object'), ('signal', 'mechanism'))
_KEY = re.compile(r'^[a-z][a-z0-9_]{0,40}$')


def _error(code: str, message: str) -> dict:
    return {'code': code, 'message': message}


def resolve(record: dict, path: str) -> list:
    """'a' -> [value]; 'list[].b' -> [value per list element]; missing -> []."""
    if '[].' in path:
        head, tail = path.split('[].', 1)
        items = record.get(head)
        return [e.get(tail) for e in items if isinstance(e, dict)] if isinstance(items, list) else []
    return [record[path]] if path in record else []


def field_paths(records: list[dict]) -> list[str]:
    paths: dict[str, None] = {}
    for record in records:
        for key, value in record.items():
            if isinstance(value, list) and any(isinstance(e, dict) for e in value):
                for element in value:
                    for sub in element if isinstance(element, dict) else ():
                        paths.setdefault(f'{key}[].{sub}')
            else:
                paths.setdefault(key)
    return list(paths)


def field_catalog(bundle: dict, examples: int = 3, width: int = 140) -> dict:
    """What the modeler sees: field names with a few example values, never the full records."""
    catalog = {}
    for name, source in bundle['sources'].items():
        records = source['records']
        fields = {}
        for path in field_paths(records):
            seen: list[str] = []
            for record in records:
                for value in resolve(record, path):
                    text = str(value)[:width]
                    if value not in (None, '') and text not in seen:
                        seen.append(text)
                if len(seen) >= examples:
                    break
            fields[path] = seen[:examples]
        catalog[name] = {'record_count': len(records), 'fields': fields}
    return catalog


def _has_value(records, path):
    return any(v not in (None, '') for r in records for v in resolve(r, path))


def _path_exists(records, path):
    return any(resolve(r, path) for r in records)


def _structure_errors(proposal) -> list[dict]:
    if not isinstance(proposal, dict):
        return [_error('invalid_response', 'proposal must be a JSON object')]
    types, relations = proposal.get('object_types'), proposal.get('relations')
    if not isinstance(types, list) or not isinstance(relations, list):
        return [_error('invalid_response', 'object_types and relations must be arrays')]
    errors = []
    for t in types:
        if not isinstance(t, dict) or not isinstance(t.get('key'), str) or \
                not isinstance(t.get('populated_from'), list) or \
                any(not isinstance(p, dict) or not isinstance(p.get('identity'), dict) or
                    any(not isinstance(v, str) for v in p['identity'].values())
                    for p in t['populated_from']) or \
                any(not isinstance(a, dict) for a in t.get('attributes') or []):
            errors.append(_error('invalid_response', f'malformed object type: {str(t)[:80]}'))
    for r in relations:
        if not isinstance(r, dict) or any(not isinstance(r.get(k), str) for k in ('key', 'from', 'to', 'source')):
            errors.append(_error('invalid_response', f'malformed relation: {str(r)[:80]}'))
    if any(not isinstance(f, dict) for f in proposal.get('ignored_fields') or []):
        errors.append(_error('invalid_response', 'ignored_fields entries must be objects'))
    return errors


def normalize_proposal(proposal: dict) -> dict:
    """Copy with defaults filled in; never mutates the model's response."""
    p = copy.deepcopy(proposal)
    for t in p['object_types']:
        t['populated_from'] = [{**pop, 'transform': pop.get('transform') or 'none'} for pop in t['populated_from']]
        t['attributes'] = list(t.get('attributes') or [])
    p['ignored_fields'] = list(p.get('ignored_fields') or [])
    return p


def validate_proposal(proposal: dict, bundle: dict) -> list[dict]:
    errors = _structure_errors(proposal)
    if errors:
        return errors
    p = normalize_proposal(proposal)
    sources = {name: s['records'] for name, s in bundle['sources'].items()}
    types: dict[str, dict] = {}
    for t in p['object_types']:
        key = t['key']
        if not _KEY.match(key) or key in types:
            errors.append(_error('invalid_response', f'bad or duplicate object type key: {key!r}'))
            continue
        types[key] = t
        if t.get('role') not in _ALL_ROLES:
            errors.append(_error('invalid_response', f'{key}: unknown role {t.get("role")!r}'))
        if not t['populated_from']:
            errors.append(_error('invalid_response', f'{key}: populated_from is empty'))
        logical = None
        for pop in t['populated_from']:
            src, ident = pop.get('source'), pop['identity']
            if src not in sources:
                errors.append(_error('unknown_source', f'{key}: unknown source {src!r}'))
                continue
            if not ident:
                errors.append(_error('invalid_response', f'{key}/{src}: identity is empty'))
                continue
            if pop['transform'] not in TRANSFORMS:
                errors.append(_error('invalid_response', f'{key}/{src}: unknown transform {pop["transform"]!r}'))
            elif pop['transform'] != 'none' and len(ident) != 1:
                errors.append(_error('transform_needs_single_field',
                                     f'{key}/{src}: {pop["transform"]} needs exactly one identity field'))
            if len({path.split('[].')[0] for path in ident.values() if '[].' in path}) > 1:
                errors.append(_error('mixed_list_identity', f'{key}/{src}: identity mixes fields from different lists'))
            for path in ident.values():
                if not _path_exists(sources[src], path):
                    errors.append(_error('unknown_field', f'{key}/{src}: field {path!r} does not exist'))
                elif not _has_value(sources[src], path):
                    errors.append(_error('empty_field', f'{key}/{src}: field {path!r} has no values'))
            if logical is None:
                logical = set(ident)
            elif set(ident) != logical:
                errors.append(_error('identity_keys_mismatch',
                                     f'{key}: logical keys differ across sources ({sorted(logical)} vs {sorted(ident)})'))
        for a in t['attributes']:
            if a.get('source') not in sources or not _path_exists(sources[a['source']], str(a.get('path'))):
                errors.append(_error('unknown_field', f'{key}: attribute {a.get("source")}.{a.get("path")} does not exist'))
    for f in p['ignored_fields']:
        if f.get('source') not in sources or not _path_exists(sources[f['source']], str(f.get('path'))):
            errors.append(_error('unknown_field', f'ignored field {f.get("source")}.{f.get("path")} does not exist'))
    used = {(pop.get('source'), path) for t in types.values() for pop in t['populated_from']
            for path in pop['identity'].values()}
    used |= {(a.get('source'), a.get('path')) for t in types.values() for a in t['attributes']}
    used |= {(f.get('source'), f.get('path')) for f in p['ignored_fields']}
    for src, records in sources.items():
        for path in field_paths(records):
            if (src, path) not in used:
                errors.append(_error('field_unaccounted', f'{src}.{path}: neither used nor listed in ignored_fields'))
    for role in ROLES:
        count = sum(t.get('role') == role for t in types.values())
        if count != 1:
            errors.append(_error('role_count', f'role {role}: needs exactly one object type, got {count}'))
    relation_keys = set()
    for r in p['relations']:
        if not _KEY.match(r['key']) or r['key'] in relation_keys:
            errors.append(_error('invalid_response', f'bad or duplicate relation key: {r["key"]!r}'))
            continue
        relation_keys.add(r['key'])
        for end in ('from', 'to'):
            t = types.get(r[end])
            if t is None:
                errors.append(_error('relation_unknown_type', f'relation {r["key"]}: unknown {end} type {r[end]!r}'))
            elif r['source'] not in {pop.get('source') for pop in t['populated_from']}:
                errors.append(_error('relation_source_mismatch',
                                     f'relation {r["key"]}: {r[end]} is not populated from {r["source"]!r}'))
    return errors


def _norm(value) -> str | None:
    if value in (None, ''):
        return None
    text = re.sub(r'\s+', ' ', str(value)).strip().upper()
    return text or None


def _identities(record: dict, pop: dict) -> list[tuple]:
    ident = pop['identity']
    keys = sorted(ident)
    heads = {path.split('[].')[0] for path in ident.values() if '[].' in path}
    if heads:
        (head,) = heads
        elements = record.get(head) if isinstance(record.get(head), list) else []
        rows = [{k: (e.get(ident[k].split('[].', 1)[1]) if '[].' in ident[k] else record.get(ident[k]))
                 for k in keys} for e in elements if isinstance(e, dict)]
    else:
        rows = [{k: record.get(ident[k]) for k in keys}]
    out = []
    for row in rows:
        values = {k: _norm(v) for k, v in row.items()}
        if any(v is None for v in values.values()):
            continue
        if pop['transform'] == 'split_comma':
            (k,) = keys
            out += [((k, part.strip()),) for part in values[k].split(',') if part.strip()]
        else:
            out.append(tuple((k, values[k]) for k in keys))
    return out


def build_graph(proposal: dict, bundle: dict) -> dict:
    """Instances are (type_key, ((logical_key, value), ...)); edges remember the record that shows them."""
    p = normalize_proposal(proposal)
    sources_of = defaultdict(set)
    records_of = defaultdict(list)
    part_of = set()
    per_record: dict[tuple, dict] = defaultdict(dict)
    for t in p['object_types']:
        for pop in t['populated_from']:
            src = pop['source']
            for index, record in enumerate(bundle['sources'][src]['records']):
                found = []
                for ident in _identities(record, pop):
                    if pop['transform'] == 'colon_hierarchy':
                        ((k, v),) = ident
                        parts = [s.strip() for s in v.split(':') if s.strip()]
                        chain = [(t['key'], ((k, ':'.join(parts[:n])),)) for n in range(1, len(parts) + 1)]
                        for inst in chain:
                            sources_of[inst].add(src)
                        part_of.update(zip(chain[1:], chain[:-1]))
                        found.append(chain[-1])
                    else:
                        inst = (t['key'], ident)
                        sources_of[inst].add(src)
                        found.append(inst)
                for inst in found:
                    records_of[inst].append((src, index))
                per_record[(src, index)].setdefault(t['key'], []).extend(found)
    edges = {r['key']: set() for r in p['relations']}
    adjacent = defaultdict(set)
    for r in p['relations']:
        for (src, index), by_type in per_record.items():
            if src != r['source']:
                continue
            for a in by_type.get(r['from'], []):
                for b in by_type.get(r['to'], []):
                    edges[r['key']].add((a, b, (src, index)))
                    adjacent[a].add(b)
                    adjacent[b].add(a)
    return {'sources_of': dict(sources_of), 'records_of': dict(records_of), 'part_of': part_of,
            'edges': edges, 'adjacent': dict(adjacent), 'per_record': dict(per_record)}


def linked(graph: dict, inst: tuple, other_type: str) -> set:
    return {n for n in graph['adjacent'].get(inst, ()) if n[0] == other_type}


def ancestors(graph: dict, inst: tuple) -> list:
    parents = dict(graph['part_of'])
    out = []
    while inst in parents:
        inst = parents[inst]
        out.append(inst)
    return out


def graph_checks(proposal: dict, graph: dict) -> tuple[dict, list[dict]]:
    """Checks that only the data can answer: links exist, the four role pairs connect, sources share objects."""
    role = {t['role']: t['key'] for t in proposal['object_types'] if t.get('role') in ROLES}
    errors = []
    metrics = {'instances': {}, 'shared_across_sources': {}, 'links': {}}
    for t in proposal['object_types']:
        insts = [i for i in graph['sources_of'] if i[0] == t['key']]
        metrics['instances'][t['key']] = len(insts)
        metrics['shared_across_sources'][t['key']] = sum(len(graph['sources_of'][i]) > 1 for i in insts)
    for r in proposal['relations']:
        metrics['links'][r['key']] = len(graph['edges'][r['key']])
        if not metrics['links'][r['key']]:
            errors.append(_error('relation_zero_links', f'relation {r["key"]}: no record links {r["from"]} and {r["to"]}'))
    for a, b in _ROLE_PAIRS:
        if not any({r['from'], r['to']} == {role[a], role[b]} for r in proposal['relations']):
            errors.append(_error('role_relation_missing',
                                 f'no direct relation between {a} ({role[a]}) and {b} ({role[b]})'))
    for r in ('affected_object', 'mechanism'):
        if not metrics['shared_across_sources'][role[r]]:
            errors.append(_error('sources_not_connected',
                                 f'{r} ({role[r]}): no object appears in more than one source'))
    return metrics, errors


def verify_proposal(proposal: dict, bundle: dict) -> dict:
    errors = validate_proposal(proposal, bundle)
    if errors:
        return {'errors': errors, 'metrics': None}
    metrics, errors = graph_checks(normalize_proposal(proposal), build_graph(proposal, bundle))
    return {'errors': errors, 'metrics': metrics}
