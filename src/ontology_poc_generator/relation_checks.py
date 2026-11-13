"""Does each relation of the ontology connect the rows it says it connects? Checked on the stored tables, in SQL.

A relation is read from one table (its source): each row of it names an object at each end by binding columns (订单.订单号 and
订单.客户编号). The rows of that table are the many side; an end whose object another table describes (客户) is the one side, and
a row finds its match when that table has a row with the same key. For each such end:

  matched / unmatched   rows of the source whose key is filled, found / not found in the describing table (compared as written;
                        the ones that would match after trimming and ignoring case are counted apart), with the keys that miss
                        and how many rows each one stands for
  fan-out               keys that repeat in the describing table: a join from the source would make a row for each of them, so
                        the source rows naming such a key and the rows a join would add are counted (as the table is stored: a repeat
                        rule a person chose later is not applied here)
  cardinality           how many objects one object of each end is joined to in the source rows, said as one of the four
                        (one_to_one, one_to_many, many_to_one, many_to_many, read from -> to); when the relation declares one,
                        whether the rows keep to it

Every number is stored as check_result rows (relation_match, relation_fanout, relation_cardinality) tied to the dataset version
they looked at, with the query that was run. An end no other table describes (the engineer on a ticket) has nothing to match
against and is not reported; a relation whose columns are not in the stored tables is left out, as for key checks."""
from __future__ import annotations

from ontology_poc_generator.pipelines import _as_number
from ontology_poc_generator.public_ontology import normalize_proposal
from ontology_poc_generator.workspace_store import SAMPLE_LIMIT, _quote, describes_rows, record_result

CARDINALITIES = ('one_to_one', 'one_to_many', 'many_to_one', 'many_to_many')


def _cat(alias: str, columns: list[str]) -> str:
    return ' || char(31) || '.join(f'{alias}.{_quote(c)}' for c in columns)


def _filled(alias: str, columns: list[str]) -> str:
    return ' AND '.join(f"({alias}.{_quote(c)} IS NOT NULL AND {alias}.{_quote(c)} <> '')" for c in columns)


def _key_text(columns: list[str], row: tuple) -> str:
    return ' + '.join(str(v) for v in row[:len(columns)])


def _describing(p: dict, own, type_key: str, logical: set) -> dict | None:
    """The population that tells the objects of a type apart by exactly these logical keys, read from a table whose rows
    describe them (not from a table that only names them)."""
    t = next((t for t in p['object_types'] if t['key'] == type_key), None)
    return next((pop for pop in (t['populated_from'] if t else []) if set(pop['identity']) == logical and pop['transform'] == 'none'
                 and not pop.get('where') and not any('[].' in path for path in pop['identity'].values()) and own(type_key, pop['source'])), None)


def _observed(most_from: int, most_to: int) -> str:
    return 'one_to_one' if most_from <= 1 and most_to <= 1 else 'many_to_one' if most_from <= 1 else 'one_to_many' if most_to <= 1 else 'many_to_many'


def _holds(declared: str, most_from: int, most_to: int) -> bool:
    return {'one_to_one': most_from <= 1 and most_to <= 1, 'many_to_one': most_from <= 1, 'one_to_many': most_to <= 1, 'many_to_many': True}[declared]


def _side_numbers(conn, s_table: str, d_table: str, mine: list[str], d_cols: list[str], rows: int) -> dict:
    """The numbers of one end, worked out from the distinct keys of both tables (one GROUP BY each, an index on the described side's),
    so the cost follows the rows and not rows times rows. Keys that miss are also looked for in the way pipelines read keys that
    only differ in spaces, case or number form ("1", "1.0", "001"), on the missing keys alone."""
    ks = [f'k{i}' for i in range(len(mine))]
    kl = ', '.join(ks)
    keyed = lambda table, columns: (f'CREATE TEMP TABLE {{name}} AS SELECT {", ".join(f"{_quote(c)} AS k{i}" for i, c in enumerate(columns))}, COUNT(*) AS n '
                                    f'FROM {table} t WHERE {_filled("t", columns)} GROUP BY {kl}')
    on = ' AND '.join(f'rc_d.{k} = rc_s.{k}' for k in ks)
    norm = lambda alias: ' || char(31) || '.join(f'UPPER({_as_number(f"{alias}.{k}")})' for k in ks)
    setup = [keyed(s_table, mine).format(name='rc_s'), keyed(d_table, d_cols).format(name='rc_d'), f'CREATE INDEX temp.rc_d_k ON rc_d({kl})']
    missing = f'SELECT {kl}, n FROM rc_s WHERE NOT EXISTS (SELECT 1 FROM rc_d WHERE {on}) ORDER BY n DESC, {kl}'
    repeated = f'SELECT {kl}, n FROM rc_d WHERE n > 1 ORDER BY n DESC, {kl}'
    for sql in setup:
        conn.execute(sql)
    try:
        unmatched, distinct = conn.execute(f'SELECT COALESCE(SUM(n), 0), COUNT(*) FROM ({missing})').fetchone()
        near = 0
        if unmatched:
            conn.execute(f'CREATE TEMP TABLE rc_dn AS SELECT DISTINCT {norm("rc_d")} AS nk FROM rc_d')
            conn.execute('CREATE INDEX temp.rc_dn_k ON rc_dn(nk)')
            near = conn.execute(f'SELECT COALESCE(SUM(n), 0) FROM ({missing}) m WHERE EXISTS (SELECT 1 FROM rc_dn WHERE rc_dn.nk = {norm("m")})').fetchone()[0]
        hit_rows, extra = conn.execute(f'SELECT COALESCE(SUM(rc_s.n), 0), COALESCE(SUM(rc_s.n * (rc_d.n - 1)), 0) FROM rc_s JOIN rc_d ON {on} WHERE rc_d.n > 1').fetchone()
        return {'missing_sql': ';\n'.join([*setup, missing]), 'repeated_sql': ';\n'.join([setup[1], repeated]), 'unmatched': unmatched, 'unmatched_keys': distinct,
                'empty': rows - conn.execute('SELECT COALESCE(SUM(n), 0) FROM rc_s').fetchone()[0], 'near': near,
                'samples': [{'key': _key_text(mine, row), 'rows': row[-1]} for row in conn.execute(f'{missing} LIMIT {SAMPLE_LIMIT}')],
                'fan_keys': conn.execute('SELECT COUNT(*) FROM rc_d WHERE n > 1').fetchone()[0], 'source_rows': hit_rows, 'extra_rows': extra,
                'fan_samples': [{'key': _key_text(d_cols, row), 'rows': row[-1]} for row in conn.execute(f'{repeated} LIMIT {SAMPLE_LIMIT}')]}
    finally:
        for name in ('rc_s', 'rc_d', 'rc_dn'):
            conn.execute(f'DROP TABLE IF EXISTS temp.{name}')


def check_relations(conn, ontology: dict, datasets: dict[str, dict]) -> list[dict]:
    """One entry per relation that can be checked: {'key', 'from', 'to', 'source', 'dataset_id', 'version', 'sides': [one per end
    with a describing table], 'own_ends': the ends whose describing table is the relation's own table read by its own key (nothing
    to look up), 'cardinality'}. See the top of the file for what each holds."""
    p = normalize_proposal(ontology)
    own = describes_rows(ontology)
    columns = lambda d: {r[0] for r in conn.execute('SELECT name FROM "column" WHERE dataset_id = ?', (d['id'],))}
    out = []
    for r in p.get('relations') or []:
        source = datasets.get(r.get('source'))
        binds = {end: r.get(f'{end}_identity') for end in ('from', 'to')}
        if source is None or not all(isinstance(b, dict) and b for b in binds.values()):
            continue
        known = columns(source)
        logical = {end: sorted(b) for end, b in binds.items()}
        cols = {end: [binds[end][k] for k in logical[end]] for end in binds}
        if not all(set(c) <= known for c in cols.values()):
            continue
        s_table = _quote(source['table_name'])
        sides, own_ends = [], []
        for end, other in (('to', 'from'), ('from', 'to')):
            pop = _describing(p, own, r[end], set(binds[end]))
            d = datasets.get(pop['source']) if pop else None
            if d is None:
                continue
            d_cols = [pop['identity'][k] for k in logical[end]]
            if d['id'] == source['id'] and d_cols == cols[end]:   # a table's own key matches itself: nothing to check, and nothing missing
                own_ends.append(end)
                continue
            if not set(d_cols) <= columns(d):
                continue
            mine = cols[end]
            rows = conn.execute(f'SELECT COUNT(*) FROM {s_table}').fetchone()[0]
            found = _side_numbers(conn, s_table, _quote(d['table_name']), mine, d_cols, rows)
            missing, repeated = found['missing_sql'], found['repeated_sql']
            unmatched, distinct, empty, near = found['unmatched'], found['unmatched_keys'], found['empty'], found['near']
            samples, fan_keys, hit_rows, extra, fan_samples = found['samples'], found['fan_keys'], found['source_rows'], found['extra_rows'], found['fan_samples']
            element = f'relation:{r["key"]}:{end}'
            ids = {
                'match': record_result(conn, element, source['id'], 'relation_match', missing, rows, unmatched, empty,
                                       {'distinct_keys': distinct, 'keys': samples, 'if_trimmed': near}, 'failed' if unmatched else 'passed'),
                'fanout': record_result(conn, element, d['id'], 'relation_fanout', repeated, d['rows_stored'], fan_keys, 0,
                                        {'source_rows': hit_rows, 'extra_rows': extra, 'keys': fan_samples}, 'failed' if fan_keys else 'passed')}
            sides.append({'end': end, 'object': r[end], 'other': r[other], 'columns': mine, 'lookup': pop['source'], 'lookup_columns': d_cols,
                          'lookup_dataset_id': d['id'], 'rows': rows, 'empty': empty, 'matched': rows - empty - unmatched, 'unmatched': unmatched,
                          'unmatched_keys': distinct, 'samples': samples, 'if_trimmed': near,
                          'fanout': {'keys': fan_keys, 'source_rows': hit_rows, 'extra_rows': extra, 'samples': fan_samples}, 'check_ids': ids})
        if not sides:
            continue
        both = f'{_filled("s", cols["from"])} AND {_filled("s", cols["to"])}'
        most = lambda a, b: conn.execute(f'SELECT COALESCE(MAX(c), 0) FROM (SELECT COUNT(DISTINCT {_cat("s", cols[b])}) AS c FROM {s_table} s WHERE {both} GROUP BY {_cat("s", cols[a])})').fetchone()[0]
        most_from, most_to = most('from', 'to'), most('to', 'from')   # objects one `from` is joined to, and one `to` is joined to
        declared = r.get('cardinality') if r.get('cardinality') in CARDINALITIES else None
        holds = None if declared is None else _holds(declared, most_from, most_to)
        cardinality = {'declared': declared, 'observed': _observed(most_from, most_to), 'most_from': most_from, 'most_to': most_to, 'holds': holds}
        cardinality['check_id'] = record_result(conn, f'relation:{r["key"]}', source['id'], 'relation_cardinality',
                                                f'COUNT(DISTINCT to key) per from key, and COUNT(DISTINCT from key) per to key, over the rows of {r["source"]} with both keys filled',
                                                source['rows_stored'], 0 if holds in (None, True) else 1, 0, cardinality,
                                                'skipped' if declared is None else 'passed' if holds else 'failed')
        out.append({'key': r['key'], 'from': r['from'], 'to': r['to'], 'source': r['source'], 'dataset_id': source['id'], 'version': source['version'],
                    'sides': sides, 'own_ends': own_ends, 'cardinality': cardinality})
    return out


def _gap(ontology: dict, relation: dict, side: dict, effect: str) -> dict:
    label = {t['key']: t.get('label') or t['key'] for t in ontology['object_types']}
    return {'relation': relation['key'], 'many': label.get(side['other'], side['other']), 'one': label.get(side['object'], side['object']),
            'table': side['lookup'], 'rows': side['unmatched'], 'keys': [s['key'] for s in side['samples']], 'distinct': side['unmatched_keys'], 'effect': effect}


def with_relation_gaps(answer: dict, query, ontology: dict, relations: list[dict] | None) -> dict:
    """The answer with, in its evidence, every relation its query walks whose source rows name an object that the table
    describing it does not have: 'dropped' when the relation is walked to group by the other object's attribute (those rows
    land in no group), 'counted' when it only joins (the object is still counted, by its key alone)."""
    if not isinstance(query, dict) or not relations:
        return answer
    group_by = query.get('group_by')
    dims = [group_by] if isinstance(group_by, dict) else group_by if isinstance(group_by, list) else []
    walked = lambda via: {k for k in via if isinstance(k, str)} if isinstance(via, list) else set()
    grouped = set().union(*(walked(d.get('via')) for d in dims if isinstance(d, dict)))
    gaps = [_gap(ontology, r, side, 'dropped' if r['key'] in grouped else 'counted') for r in relations
            if r['key'] in grouped | walked(query.get('via')) for side in r['sides'] if side['unmatched']]
    return {**answer, 'evidence': {**(answer.get('evidence') or {}), 'relation_gaps': gaps}} if gaps else answer


def unmatched_answer(ontology: dict, relations: list[dict] | None, spec) -> dict | None:
    """The answer to "how many of these name an object the other table does not have?", read from the relation check (the query
    language cannot say "no related object"). `spec` is what the model said about the question: {'relation': key, 'direction':
    'many_without_one' (rows of the relation's source whose key the other table lacks) or 'one_without_many', 'other_conditions':
    whether the question also filters}. Only the first, with no other condition, is what the check counts; the other asks are
    refused here, saying so. None when the model named no relation that is in the ontology and was checked, or the relation has two
    describing tables (which of them the question means is then not known)."""
    key = spec.get('relation') if isinstance(spec, dict) else None
    found = next((r for r in relations or [] if r['key'] == key and key in {x['key'] for x in ontology['relations']}), None)
    if found is None or len(found['sides']) != 1:
        return None
    side = found['sides'][0]
    if spec.get('direction') != 'many_without_one' or spec.get('other_conditions') is not False:
        return {'status': 'query_limit', 'reason': f'关系检查只能数「{found["source"]} 表里的{"、".join(side["columns"])}在 {side["lookup"]} 表里找不到」的行；'
                                                   '这个问法反过来问，或带了别的条件，现在算不出来', 'from_relation_check': True}
    return {'status': 'answered', 'answer': {'total': side['unmatched'], 'relation_gap': _gap(ontology, found, side, 'asked')},
            'path': f'关系检查：{found["source"]} 表里的{"、".join(side["columns"])}，在 {side["lookup"]} 表里找不到的行', 'from_relation_check': True}
