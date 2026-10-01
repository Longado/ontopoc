"""Run-to-run stability: the same file is modelled several times, and each object and relation of the run shown is
labelled by how many runs contain it. Runs are aligned with the same rule as evaluation 3 (same table and identity
fields, else same label); nothing is merged, only counted."""
from __future__ import annotations

from ontology_poc_generator.ontology_compare import match_types, relation_matches

STABILITY_RUNS = 3   # product choice: three runs tell "every time" from "most times" from "once"


def _label(t: dict) -> str:
    return t.get('label') or t['key']


def _relation_matches(r: dict, others: list, mapping: dict) -> bool:
    return any(relation_matches(r, o, mapping) for o in others)


def stability_of(shown: dict, others: list[dict]) -> dict:
    verified = [o for o in others if o.get('status') == 'auto_built_verified']
    types = {t['key']: 1 for t in shown['object_types']}
    relations = {r['key']: 1 for r in shown['relations']}
    elsewhere_types: list[dict] = []   # clusters of types missing from the shown run: {'type', 'count'}
    elsewhere_relations: dict[frozenset, dict] = {}
    for run in verified:
        mapping = match_types(shown['object_types'], run['object_types'])
        for key in mapping:
            types[key] += 1
        for r in shown['relations']:
            relations[r['key']] += _relation_matches(r, run['relations'], mapping)
        matched = set(mapping.values())
        rest = [t for t in run['object_types'] if t['key'] not in matched]
        known = match_types([c['type'] for c in elsewhere_types], rest)
        for c in elsewhere_types:
            c['count'] += c['type']['key'] in known
        seen = set(known.values())
        elsewhere_types += [{'type': t, 'count': 1} for t in rest if t['key'] not in seen]
        back = {v: k for k, v in mapping.items()}
        shown_label = {t['key']: _label(t) for t in shown['object_types']}
        name = {t['key']: shown_label[back[t['key']]] if t['key'] in back else _label(t) for t in run['object_types']}
        for r in run['relations']:
            if any(relation_matches(r, shown_relation, back) for shown_relation in shown['relations']):
                continue   # one of the shown run's relations, already counted above
            ends = frozenset((name[r['from']], name[r['to']]))
            if any(f'{end}_identity' in r for end in ('from', 'to')):
                ends = (name[r['from']], name[r['to']], r['source'],
                        tuple(sorted((r.get('from_identity') or {}).items())), tuple(sorted((r.get('to_identity') or {}).items())))
            entry = elsewhere_relations.setdefault(ends, {'label': f'{name[r["from"]]} — {name[r["to"]]}', 'count': 0})
            entry['count'] += 1
    return {
        'runs': 1 + len(verified), 'failed': len(others) - len(verified),
        'failures': [{'error': o['error']} if o.get('error') else {'codes': sorted({e['code'] for e in (o.get('attempts') or [{}])[-1].get('errors', [])})}
                     for o in others if o.get('status') != 'auto_built_verified'],
        'types': types, 'relations': relations,
        'elsewhere': {'types': [{'label': _label(c['type']), 'count': c['count']} for c in elsewhere_types],
                      'relations': list(elsewhere_relations.values())},
    }
