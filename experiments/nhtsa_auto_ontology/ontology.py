# Superseded by src/ontology_poc_generator/public_ontology.py and public_scope.py; kept as the 2026-09-13 spike record.
"""Deterministic half of the spike: sources, spec validation, graph build, scope query."""
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

RAW = Path(__file__).parent / 'raw'
ROLES = ('event', 'affected_object', 'mechanism', 'signal')
TRANSFORMS = {'none', 'split_comma', 'colon_hierarchy'}
KEY = re.compile(r'^[a-z][a-z0-9_]{0,40}$')


def load_sources():
    recalls, complaints = {}, {}
    for f in sorted(glob.glob(str(RAW / 'rcl_*.json'))):
        for r in json.loads(Path(f).read_text())['results']:
            recalls[(r['NHTSACampaignNumber'], r['Model'], r['ModelYear'])] = r
    for f in sorted(glob.glob(str(RAW / 'cmp_*.json'))):
        for r in json.loads(Path(f).read_text())['results']:
            complaints[r['odiNumber']] = r
    return {'recalls': list(recalls.values()), 'complaints': list(complaints.values())}


def resolve(record, path):
    """'a' -> [value]; 'list[].b' -> [value per element]. Missing -> []."""
    if '[].' in path:
        head, tail = path.split('[].', 1)
        return [e.get(tail) for e in record.get(head) or [] if isinstance(e, dict)]
    return [record.get(path)] if path in record else []


def field_catalog(sources, examples=3, width=140):
    out = {}
    for name, records in sources.items():
        paths = {}
        for r in records:
            for k, v in r.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    for e in v:
                        for kk in e:
                            paths.setdefault(f'{k}[].{kk}', [])
                else:
                    paths.setdefault(k, [])
        for p in paths:
            seen = []
            for r in records:
                for v in resolve(r, p):
                    s = str(v)[:width]
                    if v not in (None, '') and s not in seen:
                        seen.append(s)
                if len(seen) >= examples:
                    break
            paths[p] = seen
        out[name] = {'record_count': len(records), 'fields': paths}
    return out


def _norm(v):
    return re.sub(r'\s+', ' ', str(v)).strip().upper() if v not in (None, '') else None


def _instances(record, pop):
    ident = pop['identity']
    keys = sorted(ident)
    lists = {p.split('[].')[0] for p in ident.values() if '[].' in p}
    if lists:
        (head,) = lists
        rows = [{k: e.get(ident[k].split('[].', 1)[1]) if '[].' in ident[k] else record.get(ident[k])
                 for k in keys} for e in record.get(head) or []]
    else:
        rows = [{k: record.get(ident[k]) for k in keys}]
    out = []
    for row in rows:
        vals = {k: _norm(v) for k, v in row.items()}
        if any(v is None for v in vals.values()):
            continue
        if pop['transform'] == 'split_comma':
            (k,) = keys
            out += [((k, part.strip()),) for part in vals[k].split(',') if part.strip()]
        else:
            out.append(tuple((k, vals[k]) for k in keys))
    return out


def validate_spec(spec, sources):
    errors = []
    if not isinstance(spec, dict) or not {'object_types', 'relations'} <= set(spec):
        return ['spec must contain object_types and relations']
    types = {}
    for t in spec['object_types']:
        k = t.get('key')
        if not isinstance(k, str) or not KEY.match(k) or k in types:
            errors.append(f'bad or duplicate object type key: {k!r}')
            continue
        types[k] = t
        if t.get('role') not in ROLES + ('context',):
            errors.append(f'{k}: unknown role {t.get("role")!r}')
        logical = None
        for pop in t.get('populated_from') or []:
            src, ident = pop.get('source'), pop.get('identity')
            if src not in sources:
                errors.append(f'{k}: unknown source {src!r}')
                continue
            if not isinstance(ident, dict) or not ident:
                errors.append(f'{k}/{src}: identity must be a non-empty object')
                continue
            if pop.get('transform', 'none') not in TRANSFORMS:
                errors.append(f'{k}/{src}: unknown transform {pop.get("transform")!r}')
            pop.setdefault('transform', 'none')
            if pop['transform'] != 'none' and len(ident) != 1:
                errors.append(f'{k}/{src}: transform needs exactly one identity field')
            if len({p.split('[].')[0] for p in ident.values() if '[].' in p}) > 1:
                errors.append(f'{k}/{src}: identity mixes fields from different lists')
            for lk, path in ident.items():
                if not any(v not in (None, '') for r in sources[src] for v in resolve(r, path)):
                    errors.append(f'{k}/{src}: field {path!r} has no values in the data')
            if logical is None:
                logical = set(ident)
            elif set(ident) != logical:
                errors.append(f'{k}: logical keys differ across sources ({sorted(logical)} vs {sorted(ident)})')
        if not t.get('populated_from'):
            errors.append(f'{k}: populated_from is empty')
    used = {(pop.get('source'), path) for t in types.values() for pop in t.get('populated_from') or []
            if isinstance(pop.get('identity'), dict) for path in pop['identity'].values()}
    used |= {(a.get('source'), a.get('path')) for t in types.values() for a in t.get('attributes') or []}
    used |= {(f.get('source'), f.get('path')) for f in spec.get('ignored_fields') or [] if isinstance(f, dict)}
    for src, records in sources.items():
        for path in field_catalog({src: records}, examples=0)[src]['fields']:
            if (src, path) not in used:
                errors.append(f'{src}.{path}: field is neither used nor listed in ignored_fields')
    for role in ROLES:
        n = sum(t.get('role') == role for t in types.values())
        if n != 1:
            errors.append(f'role {role}: need exactly one object type, got {n}')
    rels = {}
    for r in spec['relations']:
        k = r.get('key')
        if not isinstance(k, str) or not KEY.match(k) or k in rels:
            errors.append(f'bad or duplicate relation key: {k!r}')
            continue
        rels[k] = r
        for end in ('from', 'to'):
            t = types.get(r.get(end))
            if t is None:
                errors.append(f'relation {k}: unknown {end} type {r.get(end)!r}')
            elif r.get('source') not in {p.get('source') for p in t.get('populated_from') or []}:
                errors.append(f'relation {k}: {r.get(end)} is not populated from source {r.get("source")!r}')
    return errors


def build_graph(spec, sources):
    """Instances keyed (type, identity); edges carry the source record that shows them together."""
    inst_sources = defaultdict(set)   # instance -> sources seen in
    part_of = set()                   # (child, parent) from colon_hierarchy
    per_record = defaultdict(dict)    # (source, idx) -> type -> [most specific instances]
    for t in spec['object_types']:
        for pop in t['populated_from']:
            src = pop['source']
            for i, rec in enumerate(sources[src]):
                found = []
                for ident in _instances(rec, pop):
                    if pop['transform'] == 'colon_hierarchy':
                        (k, v), = ident
                        parts = [p.strip() for p in v.split(':')]
                        chain = [(t['key'], ((k, ':'.join(parts[:n])),)) for n in range(1, len(parts) + 1)]
                        for inst in chain:
                            inst_sources[inst].add(src)
                        part_of.update(zip(chain[1:], chain[:-1]))
                        found.append(chain[-1])
                    else:
                        inst = (t['key'], ident)
                        inst_sources[inst].add(src)
                        found.append(inst)
                per_record[(src, i)].setdefault(t['key'], []).extend(found)
    edges = defaultdict(set)          # relation key -> {(a, b, record)}
    for r in spec['relations']:
        for (src, i), by_type in per_record.items():
            if src != r['source']:
                continue
            for a in by_type.get(r['from'], []):
                for b in by_type.get(r['to'], []):
                    edges[r['key']].add((a, b, (src, i)))
    return {'inst_sources': inst_sources, 'part_of': part_of, 'edges': edges, 'per_record': per_record}


def graph_checks(spec, sources, g):
    """Data-grounded checks; returns (metrics, errors)."""
    role = {t['role']: t['key'] for t in spec['object_types']}
    rel_between = lambda x, y: [r for r in spec['relations'] if {r['from'], r['to']} == {x, y}]
    errors, metrics = [], {'instances': {}, 'shared_across_sources': {}, 'links': {}}
    for t in spec['object_types']:
        insts = [i for i in g['inst_sources'] if i[0] == t['key']]
        metrics['instances'][t['key']] = len(insts)
        metrics['shared_across_sources'][t['key']] = sum(len(g['inst_sources'][i]) > 1 for i in insts)
    for r in spec['relations']:
        metrics['links'][r['key']] = len(g['edges'].get(r['key'], ()))
        if not metrics['links'][r['key']]:
            errors.append(f'relation {r["key"]}: zero links in the data')
    for a, b in (('event', 'affected_object'), ('event', 'mechanism'),
                 ('signal', 'affected_object'), ('signal', 'mechanism')):
        if a in role and b in role and not rel_between(role[a], role[b]):
            errors.append(f'no relation between {a} ({role[a]}) and {b} ({role[b]}); scope question unanswerable')
    for r in ('affected_object', 'mechanism'):
        if r in role and not metrics['shared_across_sources'][role[r]] and \
                not any(p[1] in g['inst_sources'] and len(g['inst_sources'][p[1]]) > 1
                        for p in g['part_of'] if p[0][0] == role[r]):
            errors.append(f'{r} ({role[r]}): no object is shared between sources, sources do not connect')
    return metrics, errors


def _linked(spec, g, inst, other_type):
    out = set()
    for r in spec['relations']:
        for a, b, _ in g['edges'].get(r['key'], ()):
            if a == inst and b[0] == other_type:
                out.add(b)
            elif b == inst and a[0] == other_type:
                out.add(a)
    return out


def ancestors(g, inst):
    parents = {c: p for c, p in g['part_of']}
    out = []
    while inst in parents:
        inst = parents[inst]
        out.append(inst)
    return out


def scope(spec, g, event_inst):
    role = {t['role']: t['key'] for t in spec['object_types']}
    covered = _linked(spec, g, event_inst, role['affected_object'])
    mech = _linked(spec, g, event_inst, role['mechanism'])
    mech_anc = {a for m in mech for a in ancestors(g, m)}
    events = [i for i in g['inst_sources'] if i[0] == role['event']]
    rows = []
    for s in (i for i in g['inst_sources'] if i[0] == role['signal']):
        objs = _linked(spec, g, s, role['affected_object'])
        smech = _linked(spec, g, s, role['mechanism'])
        smech_all = smech | {a for m in smech for a in ancestors(g, m)}
        if smech & mech or smech_all & mech:
            match = 'same_part'
        elif smech & mech_anc:
            match = 'same_category'
        else:
            continue
        inside = bool(objs & covered)
        other = sorted(e[1][0][1] for e in events if e != event_inst
                       and _linked(spec, g, e, role['mechanism']) == mech
                       and objs & _linked(spec, g, e, role['affected_object']))
        rows.append({'signal': s, 'objects': sorted(objs), 'part_match': match,
                     'inside_scope': inside, 'covered_by_other_events_same_part': other})
    return {'event': event_inst, 'covered': sorted(covered), 'mechanism': sorted(mech), 'candidates': rows}
