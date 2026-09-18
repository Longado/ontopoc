"""The form a person has to fill in downstream, filled in as far as the data allows.

A platform that receives an ontology asks, per attribute: is it the key, what type is it, how long. None of that is a
judgement — every value is in the file we just read — so code reads it and the person is left with the columns only a
person can write (the business name, the description, which field to display). Nothing here guesses from a field's
name: a column called 金额 full of words is text, and a column of ids with a leading zero is text too, because turning
03795904 into a number makes it a different id.
"""
from __future__ import annotations

import re

from ontology_poc_generator.public_ontology import build_graph, field_paths, normalize_proposal, resolve

_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_DATETIME = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?')


_PADDED = re.compile(r'^[+-]?0\d')   # 03795904: the zero belongs to the id, and any number type would drop it


def _is_int(v: str) -> bool:
    body = v[1:] if v[:1] in '+-' else v
    return body.isdigit()


def _is_decimal(v: str) -> bool:
    try:
        float(v)
    except ValueError:
        return False
    return True


def _type_of(values: list[str]) -> str | None:
    """The one type every value fits. Nothing to read means nothing to say."""
    if not values:
        return None
    if any(_PADDED.match(v) for v in values):
        return 'VARCHAR'
    for name, fits in (('INTEGER', _is_int), ('DATE', _DATE.match), ('DATETIME', _DATETIME.match), ('DECIMAL', _is_decimal)):
        if all(fits(v) for v in values):
            return name
    return 'VARCHAR'


def _field_shape(path: str, reads: list[tuple[str, list[dict]]], identity: bool) -> dict:
    """One row of the form for one field, however many tables it was read from: the type every value fits, the longest
    value, and how many rows had nothing in it."""
    seen, empty, rows = [], 0, 0
    for _, records in reads:
        for r in records:
            got = [str(v) for v in resolve(r, path) if v not in (None, '')]
            seen += got
            empty += not got
        rows += len(records)
    return {'path': path, 'identity': identity, 'sources': sorted(source for source, _ in reads), 'type': _type_of(seen),
            'length': max((len(v) for v in seen), default=0), 'empty': empty, 'rows': rows}


def _cardinality(most_from: int, most_to: int) -> str:
    if most_from > 1 and most_to > 1:
        return 'many_to_many'
    if most_from > 1 or most_to > 1:
        return 'one_to_many'
    return 'one_to_one'


def handover_form(ontology: dict, bundle: dict, graph: dict | None = None) -> dict:
    """Per object: the fields with their type and length. Per relation: how many hang off each end."""
    p = normalize_proposal(ontology)
    graph = graph or build_graph(ontology, bundle)
    types = []
    for t in p['object_types']:
        identity_fields = sorted({path for pop in t['populated_from'] for path in pop['identity'].values()})
        reads: dict[str, list[str]] = {}   # field -> the tables it is read from, in the order first met
        for pop in t['populated_from']:
            for path in sorted(pop['identity'].values()):
                reads.setdefault(path, []).append(pop['source'])
        for a in t['attributes']:
            source, path = a.get('source'), a.get('path')
            if source in bundle['sources'] and path in field_paths(bundle['sources'][source]['records']):
                reads.setdefault(path, []).append(source)
        fields = [_field_shape(path, [(src, bundle['sources'][src]['records']) for src in dict.fromkeys(sources)], path in identity_fields)
                  for path, sources in reads.items()]
        types.append({'type': t['key'], 'label': t.get('label') or t['key'], 'identity_fields': identity_fields,
                      # a platform that takes one primary key per table cannot hold an object identified by two columns
                      'needs_single_key': len(identity_fields) > 1, 'fields': fields})
    relations = []
    for r in p['relations']:
        per_from: dict = {}
        per_to: dict = {}
        for a, b, _ in graph['edges'][r['key']]:
            left, right = (a, b) if a[0] == r['from'] else (b, a)
            per_from.setdefault(left, set()).add(right)
            per_to.setdefault(right, set()).add(left)
        most_from = max((len(v) for v in per_from.values()), default=0)
        most_to = max((len(v) for v in per_to.values()), default=0)
        relations.append({'key': r['key'], 'from': r['from'], 'to': r['to'],
                          'cardinality': _cardinality(most_from, most_to), 'most_from': most_from, 'most_to': most_to})
    return {'types': types, 'relations': relations}
