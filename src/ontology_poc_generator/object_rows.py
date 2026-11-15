"""The rows behind one object: what a platform's object page lists as its instances.

The objects are the ones the ontology check already found (build_graph), so the count here is the count everywhere
else. Each row takes, from every record that names the object, the fields the ontology reads from that table; when two
tables disagree the first filled value is shown — telling them apart is the data check's job, not this list's.
"""
from __future__ import annotations

from ontology_poc_generator.code_meanings import shown
from ontology_poc_generator.ontology_eval import NAME_LIKE
from ontology_poc_generator.public_ontology import build_graph, normalize_proposal, resolve
from ontology_poc_generator.repeated_keys import applicable, latest_row, repeated_keys, tie_or_blank
from ontology_poc_generator.workspace_store import describes_rows

PAGE_SIZE = 20
REPEAT_EXAMPLES = 3


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
    return _row_from(bundle, records_of[inst], read)


def _row_from(bundle: dict, pairs: list, read: dict) -> dict:
    """One row from these (source, record index) pairs, the first pair filling a field first."""
    row = {}
    for source, index in pairs:
        record = bundle['sources'][source]['records'][index]
        for path in read.get(source, []):
            if row.get(path) is None:
                value = next((v for v in resolve(record, path) if v not in (None, '')), None)
                if value is not None:
                    row[path] = shown(bundle.get('meanings'), f'{source}.{path}', str(value))   # a code reads as its confirmed meaning
    return row


def node_id(inst: tuple) -> str:
    return f"{inst[0]}:{'|'.join(str(v) for _, v in inst[1])}"


def _display(t: dict) -> str | None:
    """The name-like attribute an object is shown by, when it has one."""
    return next((a.get('path') for a in t['attributes'] if any(w in str(a.get('path', '')).lower() for w in NAME_LIKE)), None)


def _labeller(t: dict, bundle: dict, records_of: dict):
    """An object's number as it is written, and a name-like field when it has one as a second line. The number leads:
    on Northwind an order's name-like field is its ship name, and an order labelled by it read like a customer."""
    read = _read(t)
    identity = list(dict.fromkeys(p for pop in t['populated_from'] for p in pop['identity'].values()))
    display = _display(t)

    def label(inst):
        row = _row(bundle, records_of, read, inst)
        return '|'.join(row.get(p, '') for p in identity).strip('|') or node_id(inst).split(':', 1)[1], row.get(display), row
    return label


def _identity_repeats(records_of: dict, found: list, own, rules: dict, groups: dict) -> list[dict]:
    """Per source table that describes this object (not a table that only mentions it, where repeats are normal): how
    many of its rows name an object, how many different identities they carry, how many rows carry an identity an earlier
    row of the same table already had, up to three of those identities, and the rule a person chose for them (None until
    one is; "latest by a column" says how many keys were decided by a tie or by a blank in the column). `records_of` is
    every row, also the ones a choice left out of the graph. The graph counts one object per identity; the list below
    shows its rows by that rule."""
    rows, objects, examples = {}, {}, {}
    for inst in found:
        counts = {}
        for source, _ in records_of[inst]:
            if not own(inst[0], source):
                continue
            rows[source] = rows.get(source, 0) + 1
            counts[source] = counts.get(source, 0) + 1
        for source, n in counts.items():
            objects[source] = objects.get(source, 0) + 1
            if n > 1 and len(examples.setdefault(source, [])) < REPEAT_EXAMPLES:
                examples[source].append('|'.join(str(v) for _, v in inst[1]))
    return [{'source': s, 'rows': rows[s], 'identities': objects[s], 'repeated': rows[s] - objects[s], 'examples': examples.get(s, []),
             'rule': _with_unsaid(rules.get(s), groups.get(s))} for s in rows]


def _with_unsaid(rule: dict | None, group: tuple | None) -> dict | None:
    """A "latest by a column" rule with how many keys the column could not settle: `ties` (the later row of the file was
    taken) and `blank` (a row has no value in the column, which counts as the oldest)."""
    if not rule or rule['rule'] != 'keep_latest' or group is None:
        return rule
    records, objects = group
    said = [tie_or_blank(records, o['rows'], rule['column']) for o in objects]
    return {**rule, 'ties': sum('tie' in x for x in said), 'blank': sum('blank' in x for x in said)}


def _entries(found: list, records_of: dict, bundle: dict, repeats: dict, rules: dict) -> list[tuple]:
    """What the list shows, as (instance, (source, record) pairs the row is read from, mark). An object whose key repeats
    in the table describing it has a row for each of those rows (marked, with the rule chosen so far) until a person says
    "keep the latest": then one row, the latest by the column they named (the one the graph already keeps; the mark says
    when a tie or a blank in the column left the choice to file order). The other tables' records fill what the row lacks."""
    out = []
    for inst in found:
        repeated = repeats.get('|'.join(str(v) for _, v in inst[1]))
        if repeated is None:
            out.append((inst, records_of[inst], None))
            continue
        source, rows = repeated
        rule = rules.get(source)
        rest = [p for p in records_of[inst] if p[0] != source]
        if rule and rule['rule'] == 'keep_latest':
            keep = latest_row(bundle['sources'][source]['records'], rows, rule['column'])
            out.append((inst, [(source, keep), *rest], {'repeat': 'keep_latest', 'rows': len(rows), 'column': rule['column'],
                                                       **tie_or_blank(bundle['sources'][source]['records'], rows, rule['column'])}))
        else:
            out += [(inst, [(source, i), *rest], {'repeat': rule['rule'] if rule else 'pending', 'rows': len(rows)}) for i in rows]
    return out


def object_rows(ontology: dict, bundle: dict, type_key: str, page: int = 1, size: int | None = PAGE_SIZE, graph: dict | None = None) -> dict:
    """size=None hands over every row at once, for a download. `objects` is how many objects the graph has, `total` how
    many rows the list shows (more while some key repeats and no rule is chosen); `mentioned_only` are the objects no table
    describes, which other tables name (an order's customer that has no customer row); row_marks says, for each row of
    the page, whether it is one of several rows of a repeated key (and what was decided about them)."""
    t = _type(ontology, type_key)
    if page < 1 or (size is not None and size < 1):
        raise ValueError('page and size start at 1')
    read = _read(t)
    columns = list(dict.fromkeys(path for paths in read.values() for path in paths))
    graph = graph or build_graph(ontology, bundle)
    records_of = graph['records_of']
    found = [inst for inst in records_of if inst[0] == type_key]   # in the order the data first names them
    own = describes_rows(ontology)
    mine = [g for g in repeated_keys(ontology, bundle, graph) if g['type'] == type_key]
    chosen = bundle.get('repeat_rules') or {}
    rules = {g['source']: r for g in mine if (r := applicable(g, chosen.get(g['rule_key'])))}   # by source table; one that cannot be carried out is not a choice
    repeats = {o['identity']: (g['source'], o['rows']) for g in mine for o in g['objects']}
    entries = _entries(found, records_of, bundle, repeats, rules)
    size = size or max(1, len(entries))
    shown = entries[(page - 1) * size: page * size]
    rows = [_row_from(bundle, pairs, read) for _, pairs, _ in shown]
    mentioned = [inst for inst in found if not any(own(type_key, s) for s, _ in records_of[inst])]
    return {'type': type_key, 'label': t.get('label') or type_key, 'objects': len(found), 'total': len(entries), 'page': page, 'size': size,
            'mentioned_only': {'count': len(mentioned), 'examples': ['|'.join(str(v) for _, v in i[1]) for i in mentioned[:REPEAT_EXAMPLES]]},
            'identity_repeats': _identity_repeats(graph.get('records_all', records_of), found, own, rules,
                                                  {g['source']: (bundle['sources'][g['source']]['records'], g['objects']) for g in mine}),
            'columns': columns, 'rows': [{c: r[c] for c in columns if c in r} for r in rows], 'row_marks': [mark for _, _, mark in shown]}


def find_instances(ontology: dict, bundle: dict, type_key: str, query: str = '', size: int = PAGE_SIZE, graph: dict | None = None) -> dict:
    """Objects of one type whose name or number contains the query: where an instance graph starts."""
    t = _type(ontology, type_key)
    records_of = (graph or build_graph(ontology, bundle))['records_of']
    label = _labeller(t, bundle, records_of)
    q = query.strip().upper()
    found = []
    for inst in (i for i in records_of if i[0] == type_key):
        number, name, _ = label(inst)
        if not q or q in number.upper() or q in (name or '').upper():
            found.append({'id': node_id(inst), 'label': number, 'name': name})
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
    number, name, fields = labels[inst[0]](inst)
    nodes = {node: {'id': node, 'type': inst[0], 'label': number, 'name': name}}
    edges, more = [], []
    for r in p['relations']:
        if inst[0] not in (r['from'], r['to']):
            continue
        pairs = [(a, b) for a, b, _ in graph['edges'][r['key']] if inst in (a, b)]
        others = sorted({b if a == inst else a for a, b in pairs}, key=lambda i: order.get(i, 0))
        for other in others[:size]:
            if node_id(other) not in nodes:
                number, name, _ = labels[other[0]](other)
                nodes[node_id(other)] = {'id': node_id(other), 'type': other[0], 'label': number, 'name': name}
        shown = {node_id(o) for o in others[:size]}
        edges += [{'from': node_id(a), 'to': node_id(b), 'relation': r['key'], 'label': r.get('label')}
                  for a, b in dict.fromkeys(pairs) if {node_id(a), node_id(b)} - {node} <= shown]
        if len(others) > size:
            more.append({'relation': r['key'], 'type': r['to'] if r['from'] == inst[0] else r['from'], 'hidden': len(others) - size})
    return {'center': {**nodes[node], 'fields': fields}, 'nodes': list(nodes.values()), 'edges': edges, 'more': more}
