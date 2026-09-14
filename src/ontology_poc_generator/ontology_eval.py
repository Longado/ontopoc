"""Automatic evaluation of an ontology against the data it was built from. Code only: every number has a source row."""
from __future__ import annotations

from ontology_poc_generator.public_ontology import build_graph, field_paths, normalize_proposal, normalize_value, resolve

EXAMPLES = 5  # identities listed per finding; the counts are always complete


def _label(inst: tuple) -> str:
    return '|'.join(str(v) for _, v in inst[1])


def _fields(p: dict, bundle: dict) -> dict:
    used = {(pop['source'], path) for t in p['object_types'] for pop in t['populated_from'] for path in pop['identity'].values()}
    used |= {(a.get('source'), a.get('path')) for t in p['object_types'] for a in t['attributes']}
    used |= {(t['time_field'].get('source'), t['time_field'].get('path')) for t in p['object_types'] if t.get('time_field')}
    ignored = {(f.get('source'), f.get('path')) for f in p['ignored_fields']}
    out = {}
    for name, source in bundle['sources'].items():
        paths = field_paths(source['records'])
        n_used = sum((name, path) in used for path in paths)
        n_ignored = sum((name, path) in ignored and (name, path) not in used for path in paths)
        out[name] = {'total': len(paths), 'used': n_used, 'ignored': n_ignored, 'unaccounted': len(paths) - n_used - n_ignored}
    return out


def _identity_conflicts(p: dict, bundle: dict, graph: dict) -> list[dict]:
    """The same object read from several rows of one table with different attribute values."""
    out = []
    for t in p['object_types']:
        for inst, refs in graph['records_of'].items():
            if inst[0] != t['key']:
                continue
            for src in dict.fromkeys(s for s, _ in refs):
                rows = [bundle['sources'][s]['records'][i] for s, i in refs if s == src]
                for a in (a for a in t['attributes'] if a.get('source') == src):
                    values = {str(v) for r in rows for v in resolve(r, a['path']) if v not in (None, '')}
                    if len({normalize_value(v) for v in values}) > 1:
                        out.append({'type': t['key'], 'source': src, 'identity': _label(inst), 'field': a['path'],
                                    'values': sorted(values)})
    return out


def _identity_spellings(p: dict, bundle: dict) -> list[dict]:
    """One object written several ways (case, spaces): the graph merges them, the data owner should still hear about it."""
    out = []
    for t in p['object_types']:
        seen: dict[str, set] = {}
        for pop in t['populated_from']:
            if pop['transform'] != 'none' or any('[].' in path for path in pop['identity'].values()):
                continue
            keys = sorted(pop['identity'])
            for record in bundle['sources'][pop['source']]['records']:
                raw = [record.get(pop['identity'][k]) for k in keys]
                if any(v in (None, '') for v in raw):
                    continue
                seen.setdefault('|'.join(normalize_value(v) for v in raw), set()).add('|'.join(str(v) for v in raw))
        out += [{'type': t['key'], 'identity': key, 'variants': sorted(v)} for key, v in seen.items() if len(v) > 1]
    return out


def _suspected_duplicates(p: dict, graph: dict) -> list[dict]:
    """Numeric identities that only differ by leading zeros (00106 / 106): flagged for a person to confirm, not merged."""
    out = []
    for t in p['object_types']:
        groups: dict[int, list[str]] = {}
        for inst in graph['sources_of']:
            label = _label(inst)
            if inst[0] == t['key'] and label.isdigit():
                groups.setdefault(int(label), []).append(label)
        out += [{'type': t['key'], 'rule': 'leading_zeros', 'identities': sorted(g)} for g in groups.values() if len(g) > 1]
    return out


def _missing_across_sources(p: dict, graph: dict) -> list[dict]:
    """Objects referenced in one table but absent from the table that describes them (the one giving attributes)."""
    out = []
    for t in p['object_types']:
        defining = {a.get('source') for a in t['attributes']} & {pop['source'] for pop in t['populated_from']}
        if not defining or len({pop['source'] for pop in t['populated_from']}) < 2:
            continue
        for src in sorted(defining):
            missing = sorted(_label(i) for i, srcs in graph['sources_of'].items() if i[0] == t['key'] and src not in srcs)
            if missing:
                out.append({'type': t['key'], 'source': src, 'count': len(missing), 'examples': missing[:EXAMPLES]})
    return out


def _relations(p: dict, bundle: dict, graph: dict) -> list[dict]:
    return [{'key': r['key'], 'source': r['source'], 'rows': len(bundle['sources'][r['source']]['records']),
             'linked_rows': len({ref for _, _, ref in graph['edges'][r['key']]})} for r in p['relations']]


def _orphans(p: dict, graph: dict) -> list[dict]:
    in_relations = {r[end] for r in p['relations'] for end in ('from', 'to')}
    out = []
    for t in p['object_types']:
        if t['key'] not in in_relations:
            continue
        alone = sorted(_label(i) for i in graph['sources_of'] if i[0] == t['key'] and not graph['adjacent'].get(i))
        out.append({'type': t['key'], 'count': len(alone), 'examples': alone[:EXAMPLES]})
    return out


def _source_groups(bundle: dict, graph: dict) -> list[list[str]]:
    """Tables joined by objects they share; one group means every table connects to the rest."""
    names = list(bundle['sources'])
    parent = {n: n for n in names}

    def root(n):
        while parent[n] != n:
            n = parent[n]
        return n
    for srcs in graph['sources_of'].values():
        first, *rest = sorted(srcs, key=names.index)
        for other in rest:
            a, b = root(first), root(other)
            if a != b:
                parent[max(a, b, key=names.index)] = min(a, b, key=names.index)
    groups: dict[str, list[str]] = {}
    for n in names:
        groups.setdefault(root(n), []).append(n)
    return list(groups.values())


def data_fit(ontology: dict, bundle: dict) -> dict:
    p = normalize_proposal(ontology)
    graph = build_graph(ontology, bundle)
    fit = {
        'fields': _fields(p, bundle),
        'identity_conflicts': _identity_conflicts(p, bundle, graph),
        'identity_spellings': _identity_spellings(p, bundle),
        'suspected_duplicates': _suspected_duplicates(p, graph),
        'missing_across_sources': _missing_across_sources(p, graph),
        'relations': _relations(p, bundle, graph),
        'orphans': _orphans(p, graph),
        'source_groups': _source_groups(bundle, graph),
    }
    fit['checks'] = [
        {'key': 'fields_accounted', 'passed': all(f['unaccounted'] == 0 for f in fit['fields'].values())},
        {'key': 'identity_consistent', 'passed': not fit['identity_conflicts']},
        {'key': 'identity_spelling', 'passed': not fit['identity_spellings']},
        {'key': 'relations_link', 'passed': all(r['linked_rows'] > 0 for r in fit['relations'])},
        {'key': 'references_resolve', 'passed': not fit['missing_across_sources']},
        {'key': 'sources_connected', 'passed': len(fit['source_groups']) == 1},
    ]
    return fit
