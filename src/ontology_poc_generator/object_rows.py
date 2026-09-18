"""The rows behind one object: what a platform's object page lists as its instances.

The objects are the ones the ontology check already found (build_graph), so the count here is the count everywhere
else. Each row takes, from every record that names the object, the fields the ontology reads from that table; when two
tables disagree the first filled value is shown — telling them apart is the data check's job, not this list's.
"""
from __future__ import annotations

from ontology_poc_generator.ontology_eval import NAME_LIKE
from ontology_poc_generator.public_ontology import build_graph, normalize_proposal, resolve

PAGE_SIZE = 20


def _type(ontology: dict, type_key: str) -> dict:
    t = next((t for t in normalize_proposal(ontology)['object_types'] if t['key'] == type_key), None)
    if t is None:
        raise KeyError(type_key)
    return t


def _read(t: dict) -> dict:
    """source -> the fields this object takes from it, identity first"""
    read = {}
    for pop in t['populated_from']:
        read.setdefault(pop['source'], []).extend(pop['identity'].values())
    for a in t['attributes']:
        read.setdefault(a.get('source'), []).append(a.get('path'))
    return read


def _row(bundle: dict, records_of: dict, read: dict, inst: tuple) -> dict:
    row = {}
    for source, index in records_of[inst]:
        record = bundle['sources'][source]['records'][index]
        for path in read.get(source, []):
            if row.get(path) is None:
                value = next((v for v in resolve(record, path) if v not in (None, '')), None)
                if value is not None:
                    row[path] = str(value)
    return row


def node_id(inst: tuple) -> str:
    return f"{inst[0]}:{'|'.join(str(v) for _, v in inst[1])}"


def _labeller(t: dict, bundle: dict, records_of: dict):
    """An object's name on the graph: a name-like field when it has one (a platform's display field), else its number."""
    read = _read(t)
    identity = list(dict.fromkeys(p for pop in t['populated_from'] for p in pop['identity'].values()))
    display = next((a.get('path') for a in t['attributes'] if any(w in str(a.get('path', '')).lower() for w in NAME_LIKE)), None)

    def label(inst):
        row = _row(bundle, records_of, read, inst)
        return row.get(display) or '|'.join(row.get(p, '') for p in identity) or node_id(inst).split(':', 1)[1], row
    return label


def object_rows(ontology: dict, bundle: dict, type_key: str, page: int = 1, size: int | None = PAGE_SIZE, graph: dict | None = None) -> dict:
    """size=None hands over every row at once, for a download."""
    t = _type(ontology, type_key)
    if page < 1 or (size is not None and size < 1):
        raise ValueError('page and size start at 1')
    read = _read(t)
    columns = list(dict.fromkeys(path for paths in read.values() for path in paths))
    records_of = (graph or build_graph(ontology, bundle))['records_of']
    found = [inst for inst in records_of if inst[0] == type_key]   # in the order the data first names them
    size = size or max(1, len(found))
    rows = [_row(bundle, records_of, read, inst) for inst in found[(page - 1) * size: page * size]]
    return {'type': type_key, 'label': t.get('label') or type_key, 'total': len(found), 'page': page, 'size': size,
            'columns': columns, 'rows': [{c: r[c] for c in columns if c in r} for r in rows]}


def find_instances(ontology: dict, bundle: dict, type_key: str, query: str = '', size: int = PAGE_SIZE, graph: dict | None = None) -> dict:
    """Objects of one type whose name or number contains the query: where an instance graph starts."""
    t = _type(ontology, type_key)
    records_of = (graph or build_graph(ontology, bundle))['records_of']
    label = _labeller(t, bundle, records_of)
    q = query.strip().upper()
    found = []
    for inst in (i for i in records_of if i[0] == type_key):
        name, _ = label(inst)
        if not q or q in name.upper() or q in node_id(inst).split(':', 1)[1].upper():
            found.append({'id': node_id(inst), 'label': name})
    return {'type': type_key, 'total': len(found), 'items': found[:size]}


def neighbourhood(ontology: dict, bundle: dict, node: str, size: int = PAGE_SIZE, graph: dict | None = None) -> dict:
    """One object, its fields as written, and the objects the data connects it to: a page per relation, the rest counted."""
    graph = graph or build_graph(ontology, bundle)
    records_of = graph['records_of']
    inst = next((i for i in records_of if node_id(i) == node), None)
    if inst is None:
        raise KeyError(node)
    p = normalize_proposal(ontology)
    types = {t['key']: t for t in p['object_types']}
    labels = {k: _labeller(t, bundle, records_of) for k, t in types.items()}
    order = {i: n for n, i in enumerate(records_of)}   # neighbours in the order the data first names them
    name, fields = labels[inst[0]](inst)
    nodes = {node: {'id': node, 'type': inst[0], 'label': name}}
    edges, more = [], []
    for r in p['relations']:
        if inst[0] not in (r['from'], r['to']):
            continue
        pairs = [(a, b) for a, b, _ in graph['edges'][r['key']] if inst in (a, b)]
        others = sorted({b if a == inst else a for a, b in pairs}, key=lambda i: order.get(i, 0))
        for other in others[:size]:
            nodes.setdefault(node_id(other), {'id': node_id(other), 'type': other[0], 'label': labels[other[0]](other)[0]})
        shown = {node_id(o) for o in others[:size]}
        edges += [{'from': node_id(a), 'to': node_id(b), 'relation': r['key'], 'label': r.get('label')}
                  for a, b in dict.fromkeys(pairs) if {node_id(a), node_id(b)} - {node} <= shown]
        if len(others) > size:
            more.append({'relation': r['key'], 'type': r['to'] if r['from'] == inst[0] else r['from'], 'hidden': len(others) - size})
    return {'center': {**nodes[node], 'fields': fields}, 'nodes': list(nodes.values()), 'edges': edges, 'more': more}
