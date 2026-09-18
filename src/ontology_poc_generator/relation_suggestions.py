"""Relations the data shows and the ontology does not have, found by code and offered, never added.

Two kinds. The common one follows how these ontologies are built: an object is read from every table that names it,
and a relation is two objects named on the same row. So two objects read from one table with nothing joining them
there is a relation left out; each such group is offered a link to the object that table's rows are about. Taking any
one relation out of the saved real runs, this is what finds it again.

The second is a column naming another object by its name (see _alternate_keys).

The rare one is a pointer:
a suggestion needs what a foreign key is: a column whose every filled value is the number of an object of another
type, that type being identified by that one column and no number repeating. Numbers may differ in case and in the
separators people put in them (SUP-001 is SUP001); leading zeros still count, because 007 and 7 can be two things.
Values alone are not enough: small numbers land inside any list of ids numbered from 1 (Northwind's shipVia 1-3 in
productID, BART's wheelchair_accessible 0-2 in route_id), so the column's name has to say so too — the same name as the
number it points at, or the name of the object it points at. Name-only rules were tried before on Northwind and BART
and each made a dozen relations that were not there; this asks for both.
"""
from __future__ import annotations

import re

from ontology_poc_generator.ontology_eval import _row_owners
from ontology_poc_generator.public_ontology import build_graph, field_paths, normalize_proposal, resolve

_SEPARATORS = re.compile(r'[\s\-_]')
_LIST = re.compile(r'[,，、;；|]')   # several names in one cell


def _number(v: str) -> bool:
    try:
        float(v.replace(',', ''))
    except ValueError:
        return False
    return True


def _loose(v: str) -> str:
    return _SEPARATORS.sub('', v).upper()


def _filled(records: list[dict], path: str) -> list[str]:
    return [str(v).strip() for r in records for v in resolve(r, path)[:1] if v not in (None, '') and str(v).strip()]


def _named_for(field: str, key_field: str, t: dict) -> bool:
    name = _loose(field)
    return name == _loose(key_field) or any(w and _loose(w) in name for w in (t['key'], t.get('label')))


def _same_row(p: dict, bundle: dict, related: set, graph: dict) -> list[dict]:
    owners = _row_owners(p, graph)
    order = [t['key'] for t in p['object_types']]
    out = []
    for source in bundle['sources']:
        here = [t for t in order if any(pop['source'] == source for pop in next(x for x in p['object_types'] if x['key'] == t)['populated_from'])]
        owner = next((t for t in here if t in owners.get(source, ())), None)
        if owner is None or len(here) < 2:
            continue
        group = {t: t for t in here}   # joined through relations read from this table

        def root(t):
            while group[t] != t:
                t = group[t]
            return t
        for r in p['relations']:
            if r.get('source') == source and r['from'] in group and r['to'] in group:
                group[root(r['from'])] = root(r['to'])
        rows = [by_type for (src, _), by_type in graph['per_record'].items() if src == source]
        for rep in dict.fromkeys(root(t) for t in here):
            if rep == root(owner):
                continue
            first = next(t for t in here if root(t) == rep)
            if frozenset((owner, first)) in related:
                continue
            linked = sum(1 for by_type in rows if by_type.get(owner) and by_type.get(first))
            if linked:
                field = next(iter(next(pop for pop in next(x for x in p['object_types'] if x['key'] == first)['populated_from'] if pop['source'] == source)['identity'].values()))
                out.append({'kind': 'same_row', 'from': owner, 'to': first, 'via': {'source': source, 'field': field},
                            'rows': len(bundle['sources'][source]['records']), 'linked': linked})
    return out


def _alternate_keys(p: dict, bundle: dict, graph: dict) -> list[dict]:
    """A column naming another object by its name, not its number (the alternate-key idea in ontexus's mapping
    service). The name column has to tell its objects apart — no name repeats, no lists — and be names, not numbers,
    which match each other by chance. Two things it must not pass off as a new relation: one matching name (a
    restaurant called what a district is called), which shows no pattern; and names that on every row lead to the very
    object the row already names (Northwind's shipName is the order's own customer on all 796 rows), which is the
    relation said twice. On the Taiwan registry the opposite held: all 455 named corporations were other companies."""
    sources, owners, per_record = bundle['sources'], _row_owners(p, graph), graph['per_record']
    names = []   # (type, source, field, loose name -> object)
    for t in p['object_types']:
        for a in t['attributes']:
            source, path = a.get('source'), a.get('path')
            if source not in sources:
                continue
            values = _filled(sources[source]['records'], path)
            loose = {_loose(v) for v in values}
            if len(loose) > 1 and len(loose) == len(values) and not any(_number(v) or _LIST.search(v) for v in values):
                objects = {}
                for index, record in enumerate(sources[source]['records']):
                    found = per_record.get((source, index), {}).get(t['key'])
                    value = next((str(v).strip() for v in resolve(record, path)[:1] if v not in (None, '')), '')
                    if found and value:
                        objects[_loose(value)] = found[0]
                names.append((t['key'], source, path, objects))
    order = [t['key'] for t in p['object_types']]
    out = []
    for source, table in sources.items():
        owner = next((t for t in order if t in owners.get(source, ())), None)
        if owner is None:
            continue
        identity_here = {f for u in p['object_types'] for pop in u['populated_from'] if pop['source'] == source for f in pop['identity'].values()}
        for field in field_paths(table['records']):
            if field in identity_here:
                continue
            cells = [(index, [part for part in (x.strip() for x in _LIST.split(str(v))) if part])
                     for index, record in enumerate(table['records']) for v in resolve(record, field)[:1] if v not in (None, '') and str(v).strip()]
            for key_type, key_source, key_field, objects in names:
                if key_source == source or key_type == owner:
                    continue
                linked, named, elsewhere = 0, set(), False
                for index, parts in cells:
                    hits = [objects[_loose(x)] for x in parts if _loose(x) in objects]
                    if not hits:
                        continue
                    linked += 1
                    named.update(hits)
                    elsewhere |= any(h not in per_record.get((source, index), {}).get(key_type, ()) for h in hits)
                if len(named) > 1 and elsewhere:
                    out.append({'kind': 'alternate_key', 'from': owner, 'to': key_type, 'via': {'source': source, 'field': field},
                                'key': {'source': key_source, 'field': key_field}, 'rows': len(table['records']), 'filled': len(cells), 'linked': linked})
    best = {}   # the same two columns found both ways keep the way more rows bear out
    for x in sorted(out, key=lambda x: -x['linked']):
        best.setdefault(frozenset(((x['via']['source'], x['via']['field']), (x['key']['source'], x['key']['field']))), x)
    return list(best.values())


def suggest_relations(ontology: dict, bundle: dict, graph: dict | None = None) -> list[dict]:
    p = normalize_proposal(ontology)
    sources = bundle['sources']
    related = {frozenset((r['from'], r['to'])) for r in p['relations']}
    types = {t['key']: t for t in p['object_types']}
    keys = []   # (type, source, field, exact values, loose values): a type told apart by one column of one table
    for t in p['object_types']:
        for pop in t['populated_from']:
            fields = list(pop['identity'].values())
            if len(fields) != 1 or pop['source'] not in sources:
                continue
            values = _filled(sources[pop['source']]['records'], fields[0])
            loose = {_loose(v) for v in values}
            if values and len(loose) == len(values):   # no number repeats, even read loosely
                keys.append((t['key'], pop['source'], fields[0], set(values), loose))
    if graph is None:   # read only the tables at hand
        present = {**ontology, 'object_types': [{**t, 'populated_from': [pop for pop in t['populated_from'] if pop['source'] in sources]} for t in p['object_types']],
                   'relations': [r for r in p['relations'] if r.get('source') in sources]}
        graph = build_graph(present, bundle)
    out = _same_row(p, bundle, related, graph) + _alternate_keys(p, bundle, graph)
    for t in p['object_types']:
        for source in dict.fromkeys(pop['source'] for pop in t['populated_from']):
            if source not in sources:
                continue
            identity_here = {f for u in p['object_types'] for pop in u['populated_from'] if pop['source'] == source for f in pop['identity'].values()}
            records = sources[source]['records']
            for field in field_paths(records):
                values = _filled(records, field)
                if not values or field in identity_here:   # a number the table already names an object by is that object, not a pointer
                    continue
                for key_type, key_source, key_field, exact, loose in keys:
                    if key_type == t['key'] or key_source == source or frozenset((t['key'], key_type)) in related \
                            or not _named_for(field, key_field, types[key_type]):
                        continue
                    if all(v in exact for v in values):
                        is_loose = False
                    elif all(_loose(v) in loose for v in values):
                        is_loose = True
                    else:
                        continue
                    out.append({'kind': 'pointer', 'from': t['key'], 'to': key_type, 'via': {'source': source, 'field': field},
                                'key': {'source': key_source, 'field': key_field}, 'rows': len(records), 'linked': len(values), 'loose': is_loose})
    return out
