"""The rows behind one object: what a platform's object page lists as its instances.

The objects are the ones the ontology check already found (build_graph), so the count here is the count everywhere
else. Each row takes, from every record that names the object, the fields the ontology reads from that table; when two
tables disagree the first filled value is shown — telling them apart is the data check's job, not this list's.
"""
from __future__ import annotations

from ontology_poc_generator.public_ontology import build_graph, normalize_proposal, resolve

PAGE_SIZE = 20


def object_rows(ontology: dict, bundle: dict, type_key: str, page: int = 1, size: int = PAGE_SIZE) -> dict:
    p = normalize_proposal(ontology)
    t = next((t for t in p['object_types'] if t['key'] == type_key), None)
    if t is None:
        raise KeyError(type_key)
    if page < 1 or size < 1:
        raise ValueError('page and size start at 1')
    read = {}   # source -> the fields this object takes from it, identity first
    for pop in t['populated_from']:
        read.setdefault(pop['source'], []).extend(pop['identity'].values())
    for a in t['attributes']:
        read.setdefault(a.get('source'), []).append(a.get('path'))
    columns = list(dict.fromkeys(path for paths in read.values() for path in paths))
    records_of = build_graph(ontology, bundle)['records_of']
    found = [inst for inst in records_of if inst[0] == type_key]   # in the order the data first names them
    rows = []
    for inst in found[(page - 1) * size: page * size]:
        row = {}
        for source, index in records_of[inst]:
            record = bundle['sources'][source]['records'][index]
            for path in read.get(source, []):
                if row.get(path) is None:
                    value = next((v for v in resolve(record, path) if v not in (None, '')), None)
                    if value is not None:
                        row[path] = str(value)
        rows.append({c: row[c] for c in columns if c in row})
    return {'type': type_key, 'label': t.get('label') or type_key, 'total': len(found), 'page': page, 'size': size,
            'columns': columns, 'rows': rows}
