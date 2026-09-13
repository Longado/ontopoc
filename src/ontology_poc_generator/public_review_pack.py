"""Static data for the review page: every recall's deterministic scope plus the recorded model text checks."""
from __future__ import annotations

from ontology_poc_generator.public_ontology import build_graph, linked, ontology_content_hash, resolve
from ontology_poc_generator.public_scope import BOUNDARY, ScopeError, scope


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


def _ontology_summary(ontology: dict) -> dict:
    return {
        'status': ontology['status'],
        'human_review': ontology['human_review'],
        'hash': ontology_content_hash(ontology),
        'attempts': len(ontology.get('attempts') or []),
        'object_types': [{
            'key': t['key'], 'label': t.get('label'), 'role': t['role'], 'rationale': t.get('rationale'),
            'sources': [{'source': p['source'], 'fields': list(p['identity'].values()), 'transform': p['transform']}
                        for p in t['populated_from']],
            'attributes': [f'{a["source"]}.{a["path"]}' for a in t.get('attributes') or []],
        } for t in ontology['object_types']],
        'relations': [{k: r.get(k) for k in ('key', 'from', 'to', 'source', 'meaning')} for r in ontology['relations']],
        'ignored_fields': ontology.get('ignored_fields') or [],
        'data_gaps': ontology.get('data_gaps') or [],
        'metrics': ontology['verification']['metrics'],
    }


def build_review_pack(report: dict, bundle: dict) -> dict:
    ontology = report.get('ontology') or {}
    if ontology.get('status') != 'auto_built_verified':
        raise PackError('ontology in the report is not verified')
    role = {t['role']: t['key'] for t in ontology['object_types']}
    graph = build_graph(ontology, bundle)
    events = sorted(i for i in graph['sources_of'] if i[0] == role['event'])
    recorded = report.get('scopes') or {}
    recalls, signals = [], {}
    for event in events:
        identity = dict(event[1])
        event_id = _label(identity)
        try:
            result = scope(ontology, bundle, identity)
        except ScopeError as exc:
            raise PackError(str(exc)) from exc
        checks = {}
        if event_id in recorded:
            got = [(_label(c['signal']), c['bucket']) for c in recorded[event_id]['candidates']]
            if got != [(_label(c['signal']), c['bucket']) for c in result['candidates']]:
                raise PackError(f'{event_id}: recorded scope differs from recomputation')
            checks = {_label(c['signal']): c['text_check'] for c in recorded[event_id]['candidates']}
        candidates = []
        for c in result['candidates']:
            cid = _label(c['signal'])
            if cid not in signals:
                signal = (role['signal'], tuple(sorted(c['signal'].items())))
                signals[cid] = {
                    'objects': [_label(o) for o in c['objects']],
                    'parts': sorted(_label(dict(p[1])) for p in linked(graph, signal, role['mechanism'])),
                    'fields': _fields(ontology, bundle, role['signal'],
                                      [(r['source'], r['index']) for r in c['source_refs']]),
                }
            candidates.append({'id': cid, 'bucket': c['bucket'], 'part_match': c['part_match'],
                               'other_events': [_label(e) for e in c['other_events']],
                               'text_check': checks.get(cid)})
        counts = {b: sum(c['bucket'] == b for c in candidates)
                  for b in ('inside_scope', 'covered_by_other_event', 'outside_all')}
        recalls.append({
            'id': event_id,
            'mechanism': [_label(m) for m in result['mechanism']],
            'covered': [_label(o) for o in result['covered']],
            'fields': _fields(ontology, bundle, role['event'], graph['records_of'][event]),
            'text_checked': event_id in recorded,
            'counts': counts,
            'candidates': candidates,
        })
    requests = [r for s in bundle['sources'].values() for r in s['requests']]
    return {
        'schema': 'public_review_pack.v1',
        'boundary': BOUNDARY,
        'source': {
            'decision': bundle['decision'],
            'record_counts': {name: len(s['records']) for name, s in bundle['sources'].items()},
            'retrieved_from': min(r['retrieved_at'] for r in requests),
            'retrieved_to': max(r['retrieved_at'] for r in requests),
        },
        'run': {'model': ontology.get('model'), 'modeler_prompt_version': ontology.get('prompt_version'),
                'matcher_prompt_version': next((c['text_check']['prompt_version'] for s in recorded.values()
                                                for c in s['candidates'] if c.get('text_check')), None),
                'started_at': report.get('started_at')},
        'ontology': _ontology_summary(ontology),
        'recalls': recalls,
        'signals': signals,
    }
