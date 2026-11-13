"""A pipeline: a list of typed steps over the workspace tables, each compiled to one SQL statement.

    {"steps": [{"id": "orders", "type": "input", "dataset": "订单"},      # a stored table; {"type": "input", "view": "有效订单"} reads a view
               {"id": "tickets", "type": "input", "dataset": "售后工单"},
               {"id": "joined", "type": "join", "left": "orders", "right": "tickets", "how": "left",
                "on": [{"left": "订单号", "right": "订单号"}]},
               {"id": "out", "type": "output", "from": "joined", "name": "订单带工单"}]}

A step names the steps it reads by id, always ones written before it, so the list is a tree of steps that cannot loop. Running it
executes the statements in order into temporary tables of a read-only connection and counts the rows of each node. A join
is measured before it runs, from the distinct keys of its two inputs (one GROUP BY each, so the cost follows the inputs and not
the rows the join makes), and refused when it would make more than ROW_CAP rows. After it runs, when it made more rows than
the rows of its left input that took part, the keys that repeat on the right and the numeric columns whose sum would then be
counted more than once are named, with the sums before and after; the same is said the other way round when the left side
repeats a key and a numeric column of the right side would be counted more than once. A column that is a code (confirmed
or not) is not a sum and is left out of both. Keys are compared as the text stored: " 2" and "2", or "1" and "1.0", do not
match, and the report says how many left keys would match if they were trimmed or read as numbers. An empty key matches nothing.
Steps stay plain data and a run changes nothing in the workspace; the engine is SQLite, the statements are generic SQL.
"""
from __future__ import annotations

import copy

NUMERIC = ('integer', 'decimal')
HOWS = ('inner', 'left')
EXAMPLES = 3
STEP_TYPES = ('input', 'join', 'output')
ROW_CAP = 1_000_000   # the most rows one join may make: past it the join is refused, before it runs


def workspace_datasets(conn, dataset_ids: dict[str, int]) -> dict[str, dict]:
    """{name: {'table', 'rows', 'columns': [{'name', 'type'}]}} for the dataset versions given as {name: dataset id}.
    Every stored value is text; the type is what the import read the column as."""
    out = {}
    for name, dataset_id in dataset_ids.items():
        table, rows = conn.execute('SELECT table_name, rows_stored FROM dataset WHERE id = ?', (dataset_id,)).fetchone()
        columns = [{'name': n, 'type': t} for n, t in conn.execute('SELECT name, inferred_type FROM "column" WHERE dataset_id = ? ORDER BY position', (dataset_id,))]
        out[name] = {'table': table, 'rows': rows, 'columns': columns}
    return out


def workspace_views(views: list[dict]) -> dict[str, dict]:
    """{name: {'table', 'rows', 'columns', 'source'}} for the views of a run that can be read, in the shape workspace_datasets
    gives tables. 'table' is the name the view has in the database (named_views.view_names is the one place that maps it);
    _行号 is not among the columns."""
    return {v['name']: {'table': v['sql_name'], 'rows': v['rows'], 'columns': [dict(c) for c in v['columns']], 'source': v['source']}
            for v in views if v['state'] == 'confirmed'}


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _text(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{what}要写成不为空的文字')
    return value


def _input_of(step: dict, sid: str, datasets: dict, views: dict) -> tuple[str, dict]:
    """(what it is called for a person, its dataset or view) for an input step; ValueError when it names neither or both."""
    if 'view' in step and 'dataset' in step:
        raise ValueError(f'步骤 {sid}：输入只能读一张表（dataset）或一个视图（view），不能两个都写')
    kind, pool = ('视图', views) if 'view' in step else ('表', datasets)
    name = step.get('view') if 'view' in step else step.get('dataset')
    if not isinstance(name, str):
        raise ValueError(f'步骤 {sid}：输入的{kind}名要写成文字')
    if name not in pool:
        raise ValueError(f'步骤 {sid}：这次运行里没有这{"个" if kind == "视图" else "张"}{kind} {name}')
    return f'{kind} {name}', pool[name]


def check_pipeline(spec, datasets: dict, views: dict | None = None) -> dict:
    """The pipeline as a copy, or ValueError with the words the person reads: every step has a known type and a new id,
    reads only steps written before it, and names tables, views and columns that exist."""
    views = views or {}
    steps = spec.get('steps') if isinstance(spec, dict) else None
    if not isinstance(steps, list) or not steps:
        raise ValueError('管道要有 steps：一组按顺序写的步骤')
    columns: dict[str, list[str]] = {}
    for position, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise ValueError(f'第 {position} 步要写成 {{"id": …, "type": …}}')
        sid = _text(step.get('id'), f'第 {position} 步的 id')
        if sid in columns:
            raise ValueError(f'步骤编号重复：{sid}')
        kind = step.get('type')
        if kind not in STEP_TYPES:
            raise ValueError(f'步骤 {sid} 是不认识的步骤类型 {kind}，只有 {"、".join(STEP_TYPES)}')
        read = lambda ref, role: columns[ref] if isinstance(ref, str) and ref in columns else _undefined(sid, role, ref)   # a list or an object is not a step id
        if kind == 'input':
            columns[sid] = [c['name'] for c in _input_of(step, sid, datasets, views)[1]['columns']]
        elif kind == 'join':
            left, right = read(step.get('left'), '左'), read(step.get('right'), '右')
            if step.get('how') not in HOWS:
                raise ValueError(f'步骤 {sid}：关联方式只能是 inner 或 left')
            on = step.get('on')
            if not isinstance(on, list) or not on or not all(isinstance(p, dict) for p in on):
                raise ValueError(f'步骤 {sid}：要写关联字段，例如 [{{"left": "订单号", "right": "订单号"}}]')
            for pair in on:
                for side, names, ref in (('left', left, step['left']), ('right', right, step['right'])):
                    if not isinstance(pair.get(side), str) or pair[side] not in names:
                        raise ValueError(f'步骤 {sid}：读的步骤 {ref} 里没有列 {pair.get(side)}')
            columns[sid] = [c['name'] for c in _join_columns(step, [{'name': n, 'type': ''} for n in left], [{'name': n, 'type': ''} for n in right])]
        else:
            read(step.get('from'), '来源')
            _text(step.get('name'), f'步骤 {sid}：输出要写名字，输出的名字')
            columns[sid] = columns[step['from']]
    return copy.deepcopy(spec)


def _undefined(sid: str, role: str, ref):
    raise ValueError(f'步骤 {sid}：{role}边读的步骤 {ref} 还没有定义（只能读写在它前面的步骤）')


def _join_columns(step: dict, left: list[dict], right: list[dict]) -> list[dict]:
    """The columns of a join: the left ones, then the right ones. A name both sides have gets left_ or right_ in front,
    except a join key written the same on both sides, which is kept once (the left one)."""
    same_key = {p['right'] for p in step['on'] if p['left'] == p['right']}
    right = [c for c in right if c['name'] not in same_key]
    clash = {c['name'] for c in left} & {c['name'] for c in right}
    out = [{**c, 'name': f'left_{c["name"]}' if c['name'] in clash else c['name'], 'source': c['name']} for c in left] \
        + [{**c, 'name': f'right_{c["name"]}' if c['name'] in clash else c['name'], 'source': c['name']} for c in right]
    names = [c['name'] for c in out]
    if len(set(names)) < len(names):
        raise ValueError(f'步骤 {step["id"]}：连接后有重名的列：{sorted({n for n in names if names.count(n) > 1})[0]}')
    return out


def _on(step: dict) -> str:
    """The join condition: keys equal as stored, and an empty key never equal to another empty key."""
    return ' AND '.join(f'l.{_q(p["left"])} = r.{_q(p["right"])} AND l.{_q(p["left"])} <> \'\'' for p in step['on'])


def compile_pipeline(spec: dict, datasets: dict, views: dict | None = None) -> list[dict]:
    """One entry per step: {'id', 'type', 'table' (the temporary table the step is run into), 'columns': [{'name', 'type'}],
    'sql'}. An output step is a name for a table already there: its sql is empty. A column carries 'origin', the stored
    table and column it comes from, which is how a code column is recognised after a join."""
    views = views or {}
    steps, kept = [], {}
    for index, step in enumerate(spec['steps']):
        sid, table = step['id'], f'pl_{index}'
        if step['type'] == 'input':
            data = _input_of(step, sid, datasets, views)[1]
            origin = data['source'] if 'view' in step else step['dataset']
            columns = [{**c, 'origin': f'{origin}.{c["name"]}'} for c in data['columns']]
            sql = f'CREATE TEMP TABLE {table} AS SELECT {", ".join(_q(c["name"]) for c in columns)} FROM {_q(data["table"])}'
        elif step['type'] == 'join':
            (left, lcols), (right, rcols) = kept[step['left']], kept[step['right']]
            columns = _join_columns(step, lcols, rcols)
            sources = [f'{"l" if i < len(lcols) else "r"}.{_q(c["source"])} AS {_q(c["name"])}' for i, c in enumerate(columns)]
            sql = f'CREATE TEMP TABLE {table} AS SELECT {", ".join(sources)} FROM {left} AS l {step["how"].upper()} JOIN {right} AS r ON {_on(step)}'
        else:
            table, columns, sql = kept[step['from']][0], kept[step['from']][1], ''
        kept[sid] = (table, columns)
        steps.append({'id': sid, 'type': step['type'], 'table': table, 'columns': columns, 'sql': sql})
    return steps


def _number(value):
    return None if value is None else int(value) if float(value).is_integer() else round(float(value), 2)


def _filled(keys: list[str]) -> str:
    return ' AND '.join(f"{_q(k)} IS NOT NULL AND {_q(k)} <> ''" for k in keys)


def _key_counts(conn, table: str, keys: list[str], name: str) -> None:
    """One row per distinct filled key of this input, with how many rows have it (columns k0, k1…, n), indexed."""
    aliases = ', '.join(f'{_q(k)} AS k{i}' for i, k in enumerate(keys))
    conn.execute(f'CREATE TEMP TABLE {name} AS SELECT {aliases}, COUNT(*) AS n FROM {table} WHERE {_filled(keys)} GROUP BY {", ".join(f"k{i}" for i in range(len(keys)))}')
    conn.execute(f'CREATE INDEX temp.{name}_k ON {name}({", ".join(f"k{i}" for i in range(len(keys)))})')


def _as_number(column: str) -> str:
    """A key read as a number when it looks like one, else trimmed text: "1.0", " 1" and "1" come out the same."""
    t = f'TRIM({column})'
    return (f"CASE WHEN {t} GLOB '*[0-9]*' AND {t} NOT GLOB '*[^0-9.]*' AND {t} NOT GLOB '*.*.*' AND CAST({t} AS REAL) = CAST({t} AS INTEGER) "
            f'THEN CAST(CAST({t} AS INTEGER) AS TEXT) ELSE {t} END')


def _measure_join(conn, index: int, step: dict, ltable: str, rtable: str, row_cap: int) -> dict:
    """What the join will make, from the distinct keys of its inputs alone: rows in, rows that match, rows it will make.
    ValueError, before anything is run, when it would make more than row_cap. Leaves the two key-count tables for the report."""
    lkeys, rkeys = [p['left'] for p in step['on']], [p['right'] for p in step['on']]
    _key_counts(conn, ltable, lkeys, f'jl_{index}')
    _key_counts(conn, rtable, rkeys, f'jr_{index}')
    on = ' AND '.join(f'l.k{i} = r.k{i}' for i in range(len(lkeys)))
    left_rows = conn.execute(f'SELECT COUNT(*) FROM {ltable}').fetchone()[0]
    matched, joined = conn.execute(f'SELECT COALESCE(SUM(l.n), 0), COALESCE(SUM(l.n * r.n), 0) FROM jl_{index} AS l JOIN jr_{index} AS r ON {on}').fetchone()
    expected = joined + (left_rows - matched if step['how'] == 'left' else 0)
    if expected > row_cap:
        raise ValueError(f'步骤 {step["id"]}：这个连接会产生 {expected:,} 行，超过一次最多 {row_cap:,} 行，没有运行。'
                         f'通常是连接的列在两边都有大量重复的值，先换一列或先去重')
    return {'left_rows': left_rows, 'matched_left': matched, 'expected_rows': expected}


def _sum(conn, table: str, column: str, where: str = '') -> float | None:
    return conn.execute(f'SELECT SUM(CAST({_q(column)} AS REAL)) FROM {table}{where}').fetchone()[0]


def _doubled(conn, columns: list[dict], keys: set, skip, table: str, baseline: str, out_table: str, out_names: dict) -> list[dict]:
    """The numeric columns of an input whose sum over the joined rows differs from their sum over the rows of the input that took
    part (`baseline` picks them once each). Keys and codes are not sums, and a column the join dropped is not looked at."""
    found = []
    for c in columns:
        if c['type'] not in NUMERIC or c['name'] in keys or c.get('origin') in skip or c['name'] not in out_names:
            continue
        without, with_ = _sum(conn, table, c['name'], baseline), _sum(conn, out_table, out_names[c['name']])
        if without is not None and with_ is not None and round(without, 6) != round(with_, 6):
            found.append({'column': c['name'], 'without': _number(without), 'with': _number(with_)})
    return found


def _join_report(conn, index: int, step: dict, compiled: dict, left: tuple, right: tuple, rows_out: int, measured: dict, skip) -> dict:
    """What a join did: the rows made beyond its left input and, when there are some, which keys repeat on the right and which
    numeric columns' sums would count rows more than once; the same for the right side's columns when the left repeats a
    key; keys that match only after trimming or reading as numbers; empty keys."""
    (ltable, lcols), (rtable, rcols) = left, right
    left_rows, matched = measured['left_rows'], measured['matched_left']
    extra = rows_out - (left_rows if step['how'] == 'left' else matched)
    lkeys, rkeys = [p['left'] for p in step['on']], [p['right'] for p in step['on']]
    on = ' AND '.join(f'l.k{i} = r.k{i}' for i in range(len(lkeys)))
    sides = ', '.join(f'l.k{i}' for i in range(len(lkeys)))
    report = {'how': step['how'], 'on': step['on'], 'left_rows': left_rows, 'matched_left': matched, 'extra_rows': extra, 'fan_out': None, 'right_fan_out': None,
              'left_blank': left_rows - conn.execute(f'SELECT COALESCE(SUM(n), 0) FROM jl_{index}').fetchone()[0],
              'right_blank': conn.execute(f'SELECT COUNT(*) FROM {rtable}').fetchone()[0] - conn.execute(f'SELECT COALESCE(SUM(n), 0) FROM jr_{index}').fetchone()[0],
              'near_matches': []}
    for i, (a, b) in enumerate(zip(lkeys, rkeys)):
        near = [row[0] for row in conn.execute(
            f'SELECT DISTINCT k{i} FROM jl_{index} WHERE k{i} NOT IN (SELECT k{i} FROM jr_{index}) '
            f'AND {_as_number(f"k{i}")} IN (SELECT {_as_number(f"k{i}")} FROM jr_{index}) ORDER BY k{i}')]
        if near:
            report['near_matches'].append({'left': a, 'right': b, 'count': len(near), 'examples': near[:EXAMPLES]})

    def repeating(side: str) -> tuple[int, list[dict]]:
        """Keys both inputs have that `side` has on more than one row: how many, and the first few with their rows on each side."""
        shown = f'FROM jl_{index} AS l JOIN jr_{index} AS r ON {on} WHERE {side}.n > 1'
        count = conn.execute(f'SELECT COUNT(*) {shown}').fetchone()[0]
        rows = conn.execute(f'SELECT {sides}, r.n, l.n {shown} ORDER BY {side}.n DESC, {sides} LIMIT {EXAMPLES}').fetchall()
        return count, [{'key': {p['left']: value for p, value in zip(step['on'], row[:-2])}, 'right_rows': row[-2], 'left_rows': row[-1]} for row in rows]

    skip_keys = set(lkeys)
    out_left = {c['source']: c['name'] for c in compiled['columns'][:len(lcols)]}
    out_right = {c['source']: c['name'] for c in compiled['columns'][len(lcols):]}
    if extra > 0:
        count, examples = repeating('r')
        baseline = '' if step['how'] == 'left' else f' WHERE ({", ".join(_q(k) for k in lkeys)}) IN (SELECT {", ".join(f"k{i}" for i in range(len(lkeys)))} FROM jr_{index})'
        doubled = _doubled(conn, lcols, skip_keys, skip, ltable, baseline, compiled['table'], out_left)
        report['fan_out'] = {'columns': lkeys, 'repeated_keys': count, 'examples': examples, 'double_counted': doubled}
    count, examples = repeating('l')
    if count:
        baseline = f' WHERE ({", ".join(_q(k) for k in rkeys)}) IN (SELECT {", ".join(f"k{i}" for i in range(len(lkeys)))} FROM jl_{index})'
        doubled = _doubled(conn, rcols, set(rkeys), skip, rtable, baseline, compiled['table'], out_right)
        if doubled:
            report['right_fan_out'] = {'columns': rkeys, 'repeated_keys': count, 'examples': examples, 'double_counted': doubled}
    return report


def run_pipeline(conn, spec: dict, datasets: dict, views: dict | None = None, skip=frozenset(), row_cap: int = ROW_CAP) -> dict:
    """Run a checked pipeline on a connection that may only read its tables: {'nodes': [...], 'row_cap'} in step order. Each node
    has its id, type, rows_in (one count per input), rows_out, columns, sql, and for a join `join` (see _join_report). skip:
    "table.column" names that are codes, which a join does not report as sums. ValueError, before it runs, for a join that
    would make more than row_cap rows. The temporary tables are dropped afterwards."""
    views = views or {}
    steps = compile_pipeline(check_pipeline(spec, datasets, views), datasets, views)
    by_id = {s['id']: s for s in steps}
    nodes, made = [], []
    try:
        for index, (step, compiled) in enumerate(zip(spec['steps'], steps)):
            measured = None
            if step['type'] == 'join':
                left, right = by_id[step['left']], by_id[step['right']]
                made += [f'jl_{index}', f'jr_{index}']
                measured = _measure_join(conn, index, step, left['table'], right['table'], row_cap)
            if compiled['sql']:
                made.append(compiled['table'])
                conn.execute(f'DROP TABLE IF EXISTS temp.{compiled["table"]}')
                conn.execute(compiled['sql'])
            rows_out = conn.execute(f'SELECT COUNT(*) FROM {compiled["table"]}').fetchone()[0]
            inputs = [step[k] for k in ('left', 'right', 'from') if k in step]
            node = {'id': compiled['id'], 'type': compiled['type'],
                    'rows_in': [(views[step['view']] if 'view' in step else datasets[step['dataset']])['rows']] if step['type'] == 'input'
                    else [conn.execute(f'SELECT COUNT(*) FROM {by_id[i]["table"]}').fetchone()[0] for i in inputs],
                    'rows_out': rows_out, 'columns': [c['name'] for c in compiled['columns']], 'sql': compiled['sql']}
            if step['type'] == 'input':
                node['reads'] = _input_of(step, step['id'], datasets, views)[0]
            if measured:
                node['join'] = _join_report(conn, index, step, compiled, (left['table'], left['columns']), (right['table'], right['columns']), rows_out, measured, skip)
            nodes.append(node)
    finally:
        for table in made:
            conn.execute(f'DROP TABLE IF EXISTS temp.{table}')
    return {'nodes': nodes, 'row_cap': row_cap}
