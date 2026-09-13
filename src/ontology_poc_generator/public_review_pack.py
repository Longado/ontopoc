"""Static data for the review page: every recall's deterministic scope plus the recorded model text checks."""
from __future__ import annotations

from collections import Counter

from ontology_poc_generator.nhtsa_sources import referenced_campaigns
from ontology_poc_generator.public_ontology import build_graph, linked, ontology_content_hash, resolve
from ontology_poc_generator.public_scope import BOUNDARY, ScopeError, instance_date, require_matching_bundle, scope


class PackError(ValueError):
    """The run report cannot be turned into review data without misrepresenting it."""


def _label(identity: dict) -> str:
    return ' '.join(str(v) for v in identity.values())


def _fields(ontology: dict, bundle: dict, type_key: str, refs) -> list[dict]:
    t = next(t for t in ontology['object_types'] if t['key'] == type_key)
    out, seen = [], set()
    for source, index in refs:
        record = bundle['sources'][source]['records'][index]
        for a in t.get('attributes') or []:
            if a.get('source') != source:
                continue
            for value in resolve(record, a['path']):
                if value in (None, '') or (a['path'], str(value)) in seen:
                    continue
                seen.add((a['path'], str(value)))
                out.append({'path': a['path'], 'value': str(value)})
    return out


def _flags(ontology: dict, bundle: dict, type_key: str, refs) -> list[str]:
    """Declared yes/no attributes that are true, e.g. fire or crash."""
    t = next(t for t in ontology['object_types'] if t['key'] == type_key)
    return sorted({a['path'] for s, i in refs for a in t.get('attributes') or [] if a.get('source') == s
                   and any(v is True for v in resolve(bundle['sources'][s]['records'][i], a['path']))})


def _ontology_summary(ontology: dict) -> dict:
    return {
        'status': ontology['status'],
        'human_review': ontology['human_review'],
        'hash': ontology_content_hash(ontology),
        'attempts': len(ontology.get('attempts') or []),
        'object_types': [{
            'key': t['key'], 'label': t.get('label'), 'role': t['role'], 'rationale': t.get('rationale'),
            'time_field': t.get('time_field'),
            'sources': [{'source': p['source'], 'fields': list(p['identity'].values()),
                         'transform': p.get('transform') or 'none', 'where': p.get('where')} for p in t['populated_from']],
            'attributes': [f'{a["source"]}.{a["path"]}' for a in t.get('attributes') or []],
        } for t in ontology['object_types']],
        'relations': [{k: r.get(k) for k in ('key', 'from', 'to', 'source', 'meaning')} for r in ontology['relations']],
        'ignored_fields': ontology.get('ignored_fields') or [],
        'data_gaps': ontology.get('data_gaps') or [],
        'value_aliases': ontology.get('value_aliases') or [],
        'rejected_aliases': [a for a in ontology.get('alias_proposals') or [] if a.get('verdict') == 'rejected'],
        'metrics': ontology['verification']['metrics'],
    }


def _series(ids: list[str], references: dict) -> dict:
    """Recalls connected by explicit references form one series; its id is the earliest member (ids are date-ordered)."""
    parent = {i: i for i in ids}

    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for i in ids:
        for j in references[i]:
            a, b = root(i), root(j)
            if a != b:
                first, second = sorted((a, b), key=ids.index)
                parent[second] = first
    return {i: root(i) for i in ids}


def build_review_pack(report: dict, bundle: dict) -> dict:
    ontology = report.get('ontology') or {}
    try:
        require_matching_bundle(ontology, bundle)
    except ScopeError as exc:
        raise PackError(str(exc)) from exc
    role = {t['role']: t['key'] for t in ontology['object_types']}
    graph = build_graph(ontology, bundle)
    events = sorted((i for i in graph['sources_of'] if i[0] == role['event']),
                    key=lambda e: (instance_date(ontology, bundle, graph, e) or '', _label(dict(e[1]))))
    ids = [_label(dict(e[1])) for e in events]
    texts = {i: ' '.join(f['value'] for f in _fields(ontology, bundle, role['event'], graph['records_of'][e]))
             for i, e in zip(ids, events)}
    references = {i: [r for r in referenced_campaigns(texts[i], ids) if r != i] for i in ids}
    series = _series(ids, references)
    recorded = report.get('scopes') or {}
    results = {}
    for event, event_id in zip(events, ids):
        try:
            results[event_id] = scope(ontology, bundle, dict(event[1]), graph)
        except ScopeError as exc:
            raise PackError(str(exc)) from exc
        if event_id in recorded:
            got = [(_label(c['signal']), c['bucket']) for c in recorded[event_id]['candidates']]
            if got != [(_label(c['signal']), c['bucket']) for c in results[event_id]['candidates']]:
                raise PackError(f'{event_id}: recorded scope differs from recomputation')
    checks = {}  # series id -> complaint id -> text check (earliest checked member of the series wins)
    for event_id in ids:
        if event_id in recorded:
            per = checks.setdefault(series[event_id], {})
            for c in recorded[event_id]['candidates']:
                per.setdefault(_label(c['signal']), c['text_check'])
    recalls, signals, considered = [], {}, set()
    for event, event_id in zip(events, ids):
        result, series_checks = results[event_id], checks.get(series[event_id], {})
        candidates = []
        for c in result['candidates']:
            cid = _label(c['signal'])
            considered.add(cid)
            if cid not in signals:
                signal = (role['signal'], tuple(sorted(c['signal'].items())))
                refs = [(r['source'], r['index']) for r in c['source_refs']]
                signals[cid] = {
                    'objects': [_label(o) for o in c['objects']],
                    'parts': sorted(_label(dict(p[1])) for p in linked(graph, signal, role['mechanism'])),
                    'date': instance_date(ontology, bundle, graph, signal),
                    'flags': _flags(ontology, bundle, role['signal'], refs),
                    'fields': _fields(ontology, bundle, role['signal'], refs),
                }
            candidates.append({'id': cid, 'bucket': c['bucket'], 'part_match': c['part_match'],
                               'via_alias': c['via_alias'], 'timing': c['timing'],
                               'other_events': [_label(e) for e in c['other_events']],
                               'text_check': series_checks.get(cid)})
        mechanism = [_label(m) for m in result['mechanism']]
        recalls.append({
            'id': event_id,
            'date': instance_date(ontology, bundle, graph, event),
            'group': ' / '.join(mechanism),
            'series': series[event_id],
            'references': references[event_id],
            'mechanism': mechanism,
            'covered': [_label(o) for o in result['covered']],
            'fields': _fields(ontology, bundle, role['event'], graph['records_of'][event]),
            'text_checked': bool(series_checks),
            'counts': {b: sum(c['bucket'] == b for c in candidates)
                       for b in ('inside_scope', 'covered_by_other_event', 'outside_all')},
            'candidates': candidates,
        })
    groups = {}
    for r in recalls:
        groups.setdefault(r['group'], []).append(r['id'])
    unconsidered = [i for i in graph['sources_of'] if i[0] == role['signal'] and _label(dict(i[1])) not in considered]
    parts = Counter(_label(dict(p[1])) for i in unconsidered for p in linked(graph, i, role['mechanism']))
    requests = [r for s in bundle['sources'].values() for r in s['requests']]
    return {
        'schema': 'public_review_pack.v1',
        'boundary': BOUNDARY,
        'source': {
            'decision': bundle['decision'],
            'events': len(events),
            'record_counts': {name: len(s['records']) for name, s in bundle['sources'].items()},
            'retrieved_from': min(r['retrieved_at'] for r in requests),
            'retrieved_to': max(r['retrieved_at'] for r in requests),
        },
        'run': {'model': ontology.get('model'), 'modeler_prompt_version': ontology.get('prompt_version'),
                'alias_prompt_version': ontology.get('alias_prompt_version'),
                'matcher_prompt_version': next((c['text_check']['prompt_version'] for s in recorded.values()
                                                for c in s['candidates'] if c.get('text_check')), None),
                'started_at': report.get('started_at')},
        'ontology': _ontology_summary(ontology),
        'groups': [{'id': g, 'recalls': members} for g, members in groups.items()],
        'recalls': sorted(recalls, key=lambda r: (r['group'], r['date'] or '', r['id'])),
        'signals': signals,
        'unconsidered': {'count': len(unconsidered), 'top_parts': parts.most_common(5)},
    }
