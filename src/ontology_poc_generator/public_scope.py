"""Recall scope over an auto-built public ontology: deterministic buckets, then candidates for review."""
from __future__ import annotations

from ontology_poc_generator.nhtsa_sources import bundle_content_hash
from ontology_poc_generator.public_ontology import (
    ancestors,
    build_graph,
    linked,
    normalize_value,
    ontology_content_hash,
)

BOUNDARY = '候选，待质量工程师复核；不代表缺陷已确认、车辆已召回或已处置。'


class ScopeError(ValueError):
    """The scope question cannot be answered with this ontology and bundle."""


def _identity(inst: tuple) -> dict:
    return dict(inst[1])


def scope(ontology: dict, bundle: dict, event_identity: dict) -> dict:
    if ontology.get('schema') != 'public_ontology.v1' or ontology.get('status') != 'auto_built_verified':
        raise ScopeError('ontology must be a verified public_ontology.v1')
    if ontology.get('source_bundle_hash') != bundle_content_hash(bundle):
        raise ScopeError('ontology was built from a different source bundle')
    role = {t['role']: t['key'] for t in ontology['object_types']}
    graph = build_graph(ontology, bundle)
    event = (role['event'], tuple(sorted((k, normalize_value(v)) for k, v in event_identity.items())))
    if event not in graph['sources_of']:
        raise ScopeError(f'event not found in the bundle: {event_identity}')
    covered = linked(graph, event, role['affected_object'])
    mechanism = linked(graph, event, role['mechanism'])
    mechanism_parents = {a for m in mechanism for a in ancestors(graph, m)}
    siblings = [(e, linked(graph, e, role['affected_object'])) for e in sorted(graph['sources_of'])
                if e[0] == role['event'] and e != event and linked(graph, e, role['mechanism']) == mechanism]
    candidates = []
    for signal in sorted(i for i in graph['sources_of'] if i[0] == role['signal']):
        parts = linked(graph, signal, role['mechanism'])
        parts_with_parents = parts | {a for p in parts for a in ancestors(graph, p)}
        if parts_with_parents & mechanism:
            part_match = 'same_part'
        elif parts & mechanism_parents:
            part_match = 'same_category'
        else:
            continue
        objects = linked(graph, signal, role['affected_object'])
        others = [_identity(e) for e, scope_objects in siblings if objects & scope_objects]
        bucket = 'inside_scope' if objects & covered else ('covered_by_other_event' if others else 'outside_all')
        candidates.append({
            'signal': _identity(signal),
            'objects': [_identity(o) for o in sorted(objects)],
            'part_match': part_match,
            'bucket': bucket,
            'other_events': others,
            'source_refs': [{'source': s, 'index': i} for s, i in graph['records_of'][signal]],
            'text_check': None,
        })
    return {
        'schema': 'public_scope_result.v1',
        'ontology_hash': ontology_content_hash(ontology),
        'event': {'type': role['event'], 'identity': _identity(event)},
        'covered': [_identity(o) for o in sorted(covered)],
        'mechanism': [_identity(m) for m in sorted(mechanism)],
        'candidates': candidates,
        'boundary': BOUNDARY,
    }
