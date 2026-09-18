"""Rules found in the data, offered for a person to adopt (the idea of ontexus's Logic layer, and the "checked" rung of
the 极客夜话 principle that a rule is described, checked or enforced; we stop at checked, since we never write data).

Two kinds, neither with a cut-off: a field every object has a value for, and two date fields that are in the same
order on every object that has both. A rule holds on every object or it is not offered. Adopted rules are checked
again on every later run of the file and name the objects that break them.
"""
from __future__ import annotations

from ontology_poc_generator.handover_form import _type_of
from ontology_poc_generator.object_rows import _read, _row
from ontology_poc_generator.public_ontology import build_graph, normalize_proposal

EXAMPLES = 5


def _objects(ontology: dict, bundle: dict, graph: dict | None) -> dict:
    """type -> [(number as written, fields as written)] for every object the ontology finds."""
    p = normalize_proposal(ontology)
    records_of = (graph or build_graph(ontology, bundle))['records_of']
    out = {}
    for t in p['object_types']:
        read = _read(t)
        identity = list(dict.fromkeys(f for pop in t['populated_from'] for f in pop['identity'].values()))
        rows = [_row(bundle, records_of, read, inst) for inst in records_of if inst[0] == t['key']]
        out[t['key']] = (t, [('|'.join(r.get(f, '') for f in identity), r) for r in rows])
    return out


def discover_rules(ontology: dict, bundle: dict, graph: dict | None = None) -> list[dict]:
    rules = []
    for key, (t, objects) in _objects(ontology, bundle, graph).items():
        if not objects:
            continue
        fields = list(dict.fromkeys(a.get('path') for a in t['attributes']))
        for field in fields:
            if all(row.get(field) not in (None, '') for _, row in objects):
                rules.append({'id': f'required:{key}:{field}', 'kind': 'required', 'type': key, 'field': field, 'holds': len(objects)})
        dates = [f for f in fields if _type_of([row[f] for _, row in objects if row.get(f)]) in ('DATE', 'DATETIME')]
        for a in dates:
            for b in dates:
                if a == b:
                    continue
                both = [(row[a], row[b]) for _, row in objects if row.get(a) and row.get(b)]
                # written as YYYY-MM-DD[ hh:mm], so comparing the text is comparing the dates; equal on every row is no order
                if both and all(x <= y for x, y in both) and any(x < y for x, y in both):
                    rules.append({'id': f'order:{key}:{a}:{b}', 'kind': 'order', 'type': key, 'before': a, 'after': b, 'holds': len(both)})
    return rules


def check_rules(ontology: dict, bundle: dict, rules: list[dict], graph: dict | None = None) -> list[dict]:
    """Each rule with the objects in this data that break it."""
    objects = _objects(ontology, bundle, graph)
    out = []
    for rule in rules:
        _, rows = objects.get(rule['type'], (None, []))
        if rule['kind'] == 'required':
            broken = [n for n, row in rows if row.get(rule['field']) in (None, '')]
        else:
            broken = [n for n, row in rows if row.get(rule['before']) and row.get(rule['after']) and row[rule['before']] > row[rule['after']]]
        out.append({**rule, 'violations': {'count': len(broken), 'examples': broken[:EXAMPLES]}})
    return out
