"""Evaluation 3 and run-to-run stability: compare two ontologies by what they are built from, not by what they are called.
Types match when they read the same table by the same identity fields (or, failing that, carry the same label);
relations match when both ends match, in either direction."""
from __future__ import annotations


class ReferenceFileError(ValueError):
    """The reference ontology file is not in a shape that can be compared; the message is shown to the user."""


def _signature(t: dict) -> set:
    return {(p.get('source'), frozenset((p.get('identity') or {}).values())) for p in t.get('populated_from') or []}


def match_types(reference: list, ours: list) -> dict:
    mapping, taken = {}, set()
    for rule in (lambda r, o: _signature(r) & _signature(o), lambda r, o: (r.get('label') or r['key']) == (o.get('label') or o['key'])):
        for r in reference:
            if r['key'] in mapping:
                continue
            o = next((o for o in ours if o['key'] not in taken and rule(r, o)), None)
            if o is not None:
                mapping[r['key']] = o['key']
                taken.add(o['key'])
    return mapping


def compare_ontologies(reference: dict, ours: dict) -> dict:
    ref_types, our_types = reference['object_types'], ours['object_types']
    name = {('ref', t['key']): t.get('label') or t['key'] for t in ref_types} | {('our', t['key']): t.get('label') or t['key'] for t in our_types}
    mapping = match_types(ref_types, our_types)
    rel_text = lambda side, r: f'{name[(side, r["from"])]} — {name[(side, r["to"])]}'
    matched_rel, used = [], set()
    for r in reference['relations']:
        ends = {mapping.get(r['from']), mapping.get(r['to'])}
        o = next((o for o in ours['relations'] if o['key'] not in used and None not in ends and {o['from'], o['to']} == ends), None)
        if o is not None:
            used.add(o['key'])
            matched_rel.append((r, o))
    matched_ref = {id(r) for r, _ in matched_rel}
    return {
        'types': {'matched': [[name[('ref', r)], name[('our', o)]] for r, o in mapping.items()],
                  'only_reference': [name[('ref', t['key'])] for t in ref_types if t['key'] not in mapping],
                  'only_ours': [name[('our', t['key'])] for t in our_types if t['key'] not in mapping.values()]},
        'relations': {'matched': [[rel_text('ref', r), rel_text('our', o)] for r, o in matched_rel],
                      'only_reference': [rel_text('ref', r) for r in reference['relations'] if id(r) not in matched_ref],
                      'only_ours': [rel_text('our', o) for o in ours['relations'] if o['key'] not in used]},
        'counts': {'types': {'reference': len(ref_types), 'ours': len(our_types), 'matched': len(mapping)},
                   'relations': {'reference': len(reference['relations']), 'ours': len(ours['relations']), 'matched': len(matched_rel)}},
    }


def parse_reference(data) -> dict:
    """A hand-written reference: object types with a label (key and populated_from optional), relations naming types."""
    if not isinstance(data, dict) or not isinstance(data.get('object_types'), list) or not data['object_types']:
        raise ReferenceFileError('参考本体的 JSON 里要有 object_types（对象列表），格式可以照示例参考本体写')
    types = []
    for i, t in enumerate(data['object_types']):
        if not isinstance(t, dict) or not isinstance(t.get('label'), str) or not t['label'].strip():
            raise ReferenceFileError(f'参考本体第 {i + 1} 个对象缺少 label')
        pops = [p for p in t.get('populated_from') or [] if isinstance(p, dict) and isinstance(p.get('identity'), dict)]
        types.append({'key': str(t.get('key') or t['label']), 'label': t['label'], 'populated_from': pops})
    known = {t['key']: t['key'] for t in types} | {t['label']: t['key'] for t in types}
    relations = []
    for i, r in enumerate(data.get('relations') or []):
        if not isinstance(r, dict):
            raise ReferenceFileError(f'参考本体第 {i + 1} 条关系格式不对')
        for end in ('from', 'to'):
            if r.get(end) not in known:
                raise ReferenceFileError(f'参考本体第 {i + 1} 条关系的 {end} 指向不存在的对象：{r.get(end)}')
        relations.append({'key': str(r.get('key') or f'r{i + 1}'), 'from': known[r['from']], 'to': known[r['to']]})
    return {'object_types': types, 'relations': relations}
