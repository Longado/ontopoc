"""Derived measures: an amount no column holds, written as a formula over one object's own fields — unit price ×
quantity × (1 − discount), or price − cost. The question writer proposes the formula; code refuses anything but sums of
products of the object's fields (a field, or 1 − field), computes it on every object and counts the ones it could
not; a person confirms it and it stays with the file, like rules and forms.

The form is deliberately small: no constants, no division, no functions. A formula that needs more is a question the
query cannot answer yet, and says so.
"""
from __future__ import annotations

import re

from ontology_poc_generator.public_ontology import build_graph, normalize_proposal

MAX_LABEL, MAX_TERMS, MAX_FACTORS = 20, 4, 4   # what a person reads as one formula on one line
EXAMPLES = 3


def parse_derived(ontology: dict, raw) -> tuple[dict | None, str | None]:
    """The formula in the one shape code will compute, or the reason it is refused."""
    from ontology_poc_generator import ontology_questions as questions   # questions imports this module: resolve at call time
    types = {t['key']: t for t in normalize_proposal(ontology)['object_types']}
    if not isinstance(raw, dict):
        return None, '指标要写成 {type, label, terms}'
    t = types.get(raw.get('type'))
    if t is None:
        return None, f"本体里没有对象 {raw.get('type')}"
    label = raw.get('label')
    if not isinstance(label, str) or not label.strip() or len(label.strip()) > MAX_LABEL:
        return None, f'指标名要写 1–{MAX_LABEL} 个字'
    terms = raw.get('terms')
    if not isinstance(terms, list) or not 0 < len(terms) <= MAX_TERMS:
        return None, f'公式要有 1–{MAX_TERMS} 项'
    out = []
    for term in terms:
        factors = term.get('factors') if isinstance(term, dict) else None
        if factors is None or term.get('sign', 1) not in (1, -1) or not isinstance(factors, list) or not 0 < len(factors) <= MAX_FACTORS:
            return None, f'公式每一项要写 sign（1 或 −1）和 1–{MAX_FACTORS} 个因子'
        read = []
        for f in factors:
            if not isinstance(f, dict) or set(f) - {'field', 'complement'}:
                return None, '因子只能是一个字段，或"1 − 字段"'
            field = questions._resolve_field(t, f.get('field'))
            if field is None:
                return None, f"{t.get('label') or t['key']} 没有字段 {f.get('field')}"
            read.append({'field': field, 'complement': bool(f.get('complement'))})
        out.append({'sign': term.get('sign', 1), 'factors': read})
    return {'type': t['key'], 'label': label.strip(), 'terms': out}, None


def formula_text(derived: dict) -> str:
    """The formula as a person writes it: 单价 × 数量 ×（1 − 折扣）."""
    def factor(f):
        name = f['field'].partition('.')[2]
        return f'（1 − {name}）' if f['complement'] else name
    text = ''
    for i, term in enumerate(derived['terms']):
        product = ' × '.join(factor(f) for f in term['factors']).replace(' × （', ' ×（')
        if i == 0:
            text = product if term['sign'] == 1 else f'−{product}'
        else:
            text += (' − ' if term['sign'] == -1 else ' + ') + product
    return text


def compute(ontology: dict, bundle: dict, derived: dict, graph: dict | None = None) -> dict:
    """The formula on every object of its type. An object is left out, and counted, when a field has no value, more
    than one value, or a value that is not a number: never read as zero."""
    from ontology_poc_generator import ontology_questions as questions
    p = normalize_proposal(ontology)
    types = {t['key']: t for t in p['object_types']}
    graph = graph or build_graph(ontology, bundle)
    identity = {(k, f): logical for k, t in types.items() for f, logical in questions._identity_fields(t).items()}

    def values(inst, field):
        logical = identity.get((inst[0], field))
        return {str(v) for k, v in inst[1] if k == logical and v not in (None, '')} if logical else questions._values(bundle, graph, inst, field)

    out, skipped, why, examples = {}, 0, [], []
    for inst in graph['sources_of']:
        if inst[0] != derived['type']:
            continue
        name = ' · '.join(str(v) for _, v in inst[1])
        total, problem = 0.0, None
        for term in derived['terms']:
            product = 1.0
            for f in term['factors']:
                found = values(inst, f['field'])
                field = f['field'].partition('.')[2]
                if len(found) != 1:
                    problem = f'{name}：{field} {"没有值" if not found else f"有 {len(found)} 个不同的值"}'
                    break
                raw = next(iter(found))
                try:
                    number = float(raw.replace(',', ''))
                except ValueError:
                    problem = f'{name}：{field} = {raw} 不是数字'
                    break
                product *= (1 - number) if f['complement'] else number
            if problem:
                break
            total += term['sign'] * product
        if problem:
            skipped += 1
            if len(why) < EXAMPLES:
                why.append(problem)
            continue
        value = round(total, 10)
        out[inst] = int(value) if float(value).is_integer() else value
        if len(examples) < EXAMPLES:
            examples.append({'name': name, 'value': out[inst]})
    return {'values': out, 'counted': len(out), 'skipped': skipped, 'skipped_examples': why, 'examples': examples}


def preview(ontology: dict, bundle: dict, derived: dict, graph: dict | None = None) -> dict:
    """What the page shows before a person confirms: how many objects it computes on, which it cannot, a few values."""
    got = compute(ontology, bundle, derived, graph)
    return {k: got[k] for k in ('counted', 'skipped', 'skipped_examples', 'examples')}


def plain_reason(ontology: dict, text: str) -> str:
    """A reason written by the model, with the ontology's keys (customer_places_order) turned into the names a person
    reads. Longest keys first, and only whole keys, so order is not rewritten inside order_line."""
    p = normalize_proposal(ontology)
    types = {t['key']: t.get('label') or t['key'] for t in p['object_types']}
    names = dict(types)
    for r in p['relations']:
        names[r['key']] = r.get('label') or f"{types.get(r['from'], r['from'])}→{types.get(r['to'], r['to'])}"
    for key in sorted(names, key=len, reverse=True):
        text = re.sub(rf'(?<![A-Za-z0-9_]){re.escape(key)}(?![A-Za-z0-9_])', names[key], str(text))
    return text
