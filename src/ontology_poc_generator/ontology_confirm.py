"""A person's item-by-item judgement of a built ontology, turned into a reference ontology for that file.
Kept objects carry the tables and identity fields they were built from, so later runs are matched by what they read,
not by what they are called; renamed objects keep that match. The reference is what evaluation 3 compares against."""
from __future__ import annotations

from ontology_poc_generator.ontology_compare import match_types

VERDICTS = ('ok', 'wrong')
MAX_LABEL = 40
MAX_ADDED = 30
MAX_VARIANT_GROUPS = 50


def without_wrong(ontology: dict, decisions: dict | None) -> dict:
    """The ontology every consumer uses once a person has judged it: objects and relations judged wrong are out, and so
    is a relation with a wrong object at either end. Not judged yet is kept. A copy; the stored draft is not changed."""
    types = (decisions or {}).get('types') or {}
    relations = (decisions or {}).get('relations') or {}
    kept = [t for t in ontology['object_types'] if types.get(t['key'], {}).get('verdict') != 'wrong']
    keys = {t['key'] for t in kept}
    return {**ontology, 'object_types': kept, 'relations': [r for r in ontology['relations'] if r['from'] in keys and r['to'] in keys
                                                             and relations.get(r['key'], {}).get('verdict') != 'wrong']}


class ConfirmError(ValueError):
    """The decisions do not fit the ontology; the message is shown to the user."""


def _label(value, what: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > MAX_LABEL:
        raise ConfirmError(f'{what}的名字要写 1–{MAX_LABEL} 个字')
    return value.strip()


def _verdicts(given, known: dict, what: str) -> dict:
    if not isinstance(given, dict):
        raise ConfirmError(f'{what}的判断格式不对')
    out = {}
    for key, d in given.items():
        if key not in known:
            raise ConfirmError(f'本体里没有这个{what}：{key}')
        if not isinstance(d, dict) or d.get('verdict') not in VERDICTS:
            raise ConfirmError(f'{what} {key} 的 verdict 只能是 ok 或 wrong')
        out[key] = d
    return out


def _variants(given, types: dict, kept_keys: set) -> list:
    """Groups of spellings a person accepted as one and the same thing. The candidates were already checked against the
    data before they were shown (`name_variants.variant_candidates`); here only the person's own judgement is checked."""
    if given is None:
        return []
    if not isinstance(given, list) or len(given) > MAX_VARIANT_GROUPS:
        raise ConfirmError(f'写法对应的格式不对：最多 {MAX_VARIANT_GROUPS} 组')
    out = []
    for i, g in enumerate(given):
        if not isinstance(g, dict) or not isinstance(g.get('type'), str):
            raise ConfirmError(f'第 {i + 1} 组写法没有写清是哪个对象的')
        key = g['type']
        if key not in types:
            raise ConfirmError(f'本体里没有这个对象：{key}')
        if key not in kept_keys:
            raise ConfirmError(f'第 {i + 1} 组写法属于{types[key].get("label") or key}，但这个对象没有判“对”')
        values = g.get('values')
        if not isinstance(values, list) or len({v for v in values if isinstance(v, str) and v.strip()}) < 2:
            raise ConfirmError(f'第 {i + 1} 组写法要给同一个对象的两个或更多写法')
        out.append({'type': key, 'values': sorted({v.strip() for v in values})})
    return out


def confirmed_reference(ontology: dict, decisions: dict) -> dict:
    types = {t['key']: t for t in ontology['object_types']}
    relations = {r['key']: r for r in ontology['relations']}
    if not isinstance(decisions, dict):
        raise ConfirmError('判断格式不对')
    type_d = _verdicts(decisions.get('types') or {}, types, '对象')
    rel_d = _verdicts(decisions.get('relations') or {}, relations, '关系')
    added = decisions.get('added') or []
    if not isinstance(added, list) or len(added) > MAX_ADDED:
        raise ConfirmError(f'补充的对象最多 {MAX_ADDED} 个')
    kept = []
    for key, d in type_d.items():
        if d['verdict'] == 'ok':
            t = types[key]
            kept.append({'key': key, 'label': _label(d.get('label'), '对象') or t.get('label') or key,
                         'populated_from': [{'source': p.get('source'), 'identity': p.get('identity') or {}} for p in t.get('populated_from') or []]})
    kept_keys = {t['key'] for t in kept}
    links = []
    for key, d in rel_d.items():
        if d['verdict'] != 'ok':
            continue
        r = relations[key]
        dropped = [types[end].get('label') or end for end in (r['from'], r['to']) if end not in kept_keys]
        if dropped:
            raise ConfirmError(f'关系 {key} 判了"对"，但它连着的{"、".join(dropped)}没有判"对"')
        links.append({'key': key, 'from': r['from'], 'to': r['to']})
    names = {t['label'] for t in kept}
    for i, name in enumerate(added):
        name = _label(name, f'补充的第 {i + 1} 个对象')
        if name in names:
            raise ConfirmError(f'补充的对象“{name}”和已有的对象重名')
        names.add(name)
        kept.append({'key': f'added_{i + 1}', 'label': name, 'populated_from': []})
    if not kept:
        raise ConfirmError('至少要判一个对象"对"，或补充一个对象')
    variants = _variants(decisions.get('variants'), types, kept_keys)
    # what a person threw out is a correction too: kept so the next run of this file starts with it thrown out again
    rejected = [{'key': key, 'label': types[key].get('label') or key,
                 'populated_from': [{'source': p.get('source'), 'identity': p.get('identity') or {}} for p in types[key].get('populated_from') or []]}
                for key, d in type_d.items() if d['verdict'] == 'wrong']
    rejected_links = [{'key': key, 'from': relations[key]['from'], 'to': relations[key]['to']}
                      for key, d in rel_d.items() if d['verdict'] == 'wrong']
    return {'object_types': kept, 'relations': links, 'rejected_types': rejected, 'rejected_relations': rejected_links,
            **({'name_variants': variants} if variants else {})}


def prefill_from_reference(ontology: dict, reference: dict) -> dict:
    """Decisions for a new run of a confirmed file: what matches the confirmation starts as right (with its confirmed
    name); an object the person added that this run now has starts as right too; only the differences are left."""
    ours = {t['key']: t for t in ontology['object_types']}
    ref_types = reference['object_types']
    mapping = match_types(ref_types, ontology['object_types'])   # same table and identity fields, else same name
    thrown = match_types(reference.get('rejected_types') or [], [t for t in ontology['object_types'] if t['key'] not in mapping.values()])
    types = {our_key: {'verdict': 'wrong'} for our_key in thrown.values()}
    for ref_key, our_key in mapping.items():
        label = next(t['label'] for t in ref_types if t['key'] == ref_key)
        types[our_key] = {'verdict': 'ok', **({'label': label} if label != (ours[our_key].get('label') or our_key) else {})}
    # the same two objects the other way round is another relation (a customer's orders is not an order's customer)
    confirmed_ends = {(mapping.get(r['from']), mapping.get(r['to'])) for r in reference['relations']}
    relations = {r['key']: {'verdict': 'ok'} for r in ontology['relations'] if (r['from'], r['to']) in confirmed_ends}
    thrown_ends = {(thrown.get(r['from'], mapping.get(r['from'])), thrown.get(r['to'], mapping.get(r['to'])))
                   for r in reference.get('rejected_relations') or []}
    relations.update({r['key']: {'verdict': 'wrong'} for r in ontology['relations'] if (r['from'], r['to']) in thrown_ends})
    returned = [t['label'] for t in (reference.get('rejected_types') or []) if t['key'] in thrown]
    added = [t['label'] for t in ref_types if t['key'].startswith('added_') and t['key'] not in mapping]
    groups = reference.get('name_variants')   # the stored file can have been hand-edited: anything unreadable is left out
    variants = [{'type': mapping[g['type']], 'values': g['values']} for g in (groups if isinstance(groups, list) else [])
                if isinstance(g, dict) and mapping.get(g.get('type')) and isinstance(g.get('values'), list)]
    return {'types': types, 'relations': relations, 'added': added, 'variants': variants, 'returned': returned}
