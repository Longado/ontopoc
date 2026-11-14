"""A pipeline: a list of typed steps over the workspace tables, each compiled to SQL.

    {"steps": [{"id": "orders", "type": "input", "dataset": "订单"},      # a stored table (add "version": 2 to pin one); {"type": "input", "view": "有效订单"} reads a view
               {"id": "tickets", "type": "input", "dataset": "售后工单"},
               {"id": "joined", "type": "join", "left": "orders", "right": "tickets", "how": "left",
                "on": [{"left": "订单号", "right": "订单号"}]},
               {"id": "clean", "type": "transform", "from": "joined", "operators": [{"op": "filter", "where": {...}}, {"op": "calc", ...}]},
               {"id": "out", "type": "output", "from": "clean", "name": "订单带工单"}]}

A step names the steps it reads by id, always ones written before it, so the list is a tree of steps that cannot loop. Running it executes the statements
in order into temporary tables of a connection and counts the rows of each node. The step types: input; join (inner, left, anti: the left rows with no match,
semi: the left rows with a match; empty keys match nothing, or match each other with "null_keys": "equal"; "right_columns" picks the right-hand columns
that come along); transform (the operators of pipeline_ops, each reporting the rows it affected); output (the columns it keeps, a key built from columns,
duplicate and empty keys counted). A join is measured before it runs, from the distinct keys of its two inputs (one GROUP BY each, so the cost follows the
inputs and not the rows the join makes), and refused when it would make more than ROW_CAP rows. After it runs, when it made more rows than the rows of its left
input that took part, the keys that repeat on the right and the numeric columns whose sum would then be counted more than once are named, with the sums before
and after; the same is said the other way round when the left side repeats a key and a numeric column of the right side would be counted more than once. An
inner or left join also carries two hidden columns that identify the row each value came from, so that a later group statistic can say, group by group, what
it counted twice. A column that is a code (confirmed or not) is not a sum and is left out of both. Keys are compared as the text stored: " 2" and "2", or "1" and
"1.0", do not match, and the report says how many left keys would match if they were trimmed or read as numbers.
Steps stay plain data and a run changes nothing in the workspace; the engine is SQLite, the statements are generic SQL.
"""
from __future__ import annotations

import copy

from ontology_poc_generator.pipeline_funcs import register
from ontology_poc_generator.pipeline_ops import MAX_OPERATORS, OpError, compile_op, new_context, visible

NUMERIC = ('integer', 'decimal')
HOWS = ('inner', 'left', 'anti', 'semi')
NULL_KEYS = ('no_match', 'equal')
EXAMPLES = 3
STEP_TYPES = ('input', 'join', 'transform', 'output')
ROW_CAP = 1_000_000   # the most rows one join may make: past it the join is refused, before it runs
MAX_STEPS = 60
KEY_EXAMPLES = 20


class PipelineRunError(ValueError):
    """A run that stopped for a reason a person asked for (a conversion set to stop on failure)."""


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


def dataset_key(step: dict) -> str:
    """What an input step's dataset is called in the `datasets` given to a run: its name, or name@vN when a version is pinned."""
    return step['dataset'] if step.get('version') is None else f'{step["dataset"]}@v{step["version"]}'


def _input_of(step: dict, sid: str, datasets: dict, views: dict) -> tuple[str, dict]:
    """(what it is called for a person, its dataset or view) for an input step; ValueError when it names neither or both."""
    if 'view' in step and 'dataset' in step:
        raise ValueError(f'步骤 {sid}：输入只能读一张表（dataset）或一个视图（view），不能两个都写')
    kind, pool = ('视图', views) if 'view' in step else ('表', datasets)
    name = step.get('view') if 'view' in step else step.get('dataset')
    if not isinstance(name, str):
        raise ValueError(f'步骤 {sid}：输入的{kind}名要写成文字')
    if 'version' in step and (kind == '视图' or not isinstance(step['version'], int) or isinstance(step['version'], bool) or step['version'] < 1):
        raise ValueError(f'步骤 {sid}：版本（version）只用在表上，写成大于 0 的整数')
    key = name if 'view' in step else dataset_key(step)
    if key not in pool:
        raise ValueError(f'步骤 {sid}：这次运行里没有这{"个" if kind == "视图" else "张"}{kind} {key}')
    return f'{kind} {name}' + (f' 第 {step["version"]} 版' if step.get('version') is not None else ''), pool[key]


def _input_columns(step: dict, sid: str, datasets: dict, views: dict) -> list[dict]:
    data = _input_of(step, sid, datasets, views)[1]
    origin = data['source'] if 'view' in step else step['dataset']
    return [{**c, 'origin': f'{origin}.{c["name"]}'} for c in data['columns']]


def _undefined(sid: str, role: str, ref):
    raise ValueError(f'步骤 {sid}：{role}边读的步骤 {ref} 还没有定义（只能读写在它前面的步骤）')


def _lineage(sid: str, side: str) -> str:
    return f'__{side}_{sid}'


def _join_columns(step: dict, left: list[dict], right: list[dict]) -> list[dict]:
    """The columns of a join: the left ones, then the right ones the person chose (all by default). A name both sides have gets left_ or right_ in front,
    except a join key written the same on both sides, which is kept once (the left one). An anti or semi join keeps the left columns only. An inner or left
    join adds two hidden columns, the row of each side a joined row came from, and marks every column with the hidden columns that identify its source row
    ('fan'), which is how a later sum can say what it counted twice. Each column says which side it came from ('side') and its name there ('source')."""
    if step['how'] in ('anti', 'semi'):
        return [{**c, 'source': c['name'], 'side': 'l'} for c in left]
    same_key = {p['right'] for p in step['on'] if p['left'] == p['right']}
    chosen = step.get('right_columns')
    right_shown = [c for c in visible(right) if c['name'] not in same_key and (chosen is None or c['name'] in chosen)]
    clash = {c['name'] for c in visible(left)} & {c['name'] for c in right_shown}
    lname, rname = _lineage(step['id'], 'l'), _lineage(step['id'], 'r')
    prefixed = lambda c, side, tag: {**c, 'name': f'{side}_{c["name"]}' if c['name'] in clash else c['name'], 'source': c['name'], 'side': side[0], 'fan': [*c.get('fan', []), tag]}
    carried = lambda c, side: {**{k: v for k, v in c.items() if k != 'rowid_of'}, 'source': c['name'], 'side': side}   # a hidden column of an earlier join is passed along as it is
    out = [prefixed(c, 'left', lname) if not c.get('hidden') else carried(c, 'l') for c in left] \
        + [prefixed(c, 'right', rname) for c in right_shown] \
        + [carried(c, 'r') for c in right if c.get('hidden')] \
        + [{'name': lname, 'type': 'integer', 'hidden': True, 'rowid_of': 'l'}, {'name': rname, 'type': 'integer', 'hidden': True, 'rowid_of': 'r'}]
    names = [c['name'] for c in out]
    if len(set(names)) < len(names):
        raise ValueError(f'步骤 {step["id"]}：连接后有重名的列：{sorted({n for n in names if names.count(n) > 1})[0]}')
    return out


def _on(step: dict) -> str:
    """The join condition: keys equal as stored, and an empty key never equal to another empty key (or, with null_keys "equal", empty keys equal each other)."""
    if step.get('null_keys') == 'equal':
        return ' AND '.join(f"COALESCE(l.{_q(p['left'])}, '') = COALESCE(r.{_q(p['right'])}, '')" for p in step['on'])
    return ' AND '.join(f'l.{_q(p["left"])} = r.{_q(p["right"])} AND l.{_q(p["left"])} <> \'\'' for p in step['on'])


def _join_sql(step: dict, table: str, left: str, right: str, columns: list[dict]) -> str:
    if step['how'] in ('anti', 'semi'):
        select = ', '.join(f'l.{_q(c["name"])}' for c in columns)
        return (f'CREATE TEMP TABLE {table} AS SELECT {select} FROM {left} AS l WHERE {"NOT " if step["how"] == "anti" else ""}'
                f'EXISTS (SELECT 1 FROM {right} AS r WHERE {_on(step)})')
    sources = [f'l.rowid AS {_q(c["name"])}' if c.get('rowid_of') == 'l' else f'r.rowid AS {_q(c["name"])}' if c.get('rowid_of') == 'r'
               else f'{c["side"]}.{_q(c["source"])} AS {_q(c["name"])}' for c in columns]
    return f'CREATE TEMP TABLE {table} AS SELECT {", ".join(sources)} FROM {left} AS l {step["how"].upper()} JOIN {right} AS r ON {_on(step)}'


def _transform(step: dict, sid: str, src: str, columns: list[dict], ctx: dict, index: int) -> tuple[str, list[dict], list[dict]]:
    """(the table the step ends in, its columns, one stage per operator: {'op', 'table', 'sql', 'params', 'measure'}). The badges of the columns the step
    was given are dropped: New and Replace say what this step did."""
    operators = step.get('operators')
    if not isinstance(operators, list) or len(operators) > MAX_OPERATORS:
        raise ValueError(f'步骤 {sid}：operators 要写成操作的列表，最多 {MAX_OPERATORS} 个')
    columns = [{k: v for k, v in c.items() if k != 'badge'} for c in columns]
    stages = []
    for j, op in enumerate(operators):
        label = f'步骤 {sid} 的第 {j + 1} 个操作'
        stage = compile_op(op, src, columns, ctx, f'{label}（{op.get("op") if isinstance(op, dict) else op}）')
        table = f'pl_{index}_{j}'
        stages.append({'op': op['op'], 'table': table, 'sql': f'CREATE TEMP TABLE {table} AS {stage["select"]}', 'params': stage['params'], 'measure': stage['measure']})
        src, columns = table, stage['columns']
    return src, columns, stages


def _output(step: dict, sid: str, columns: list[dict]) -> dict:
    """What an output keeps: {'columns' (the ones chosen, or all a person sees, and a built key), 'key' (the column names that identify a row, or None), 'dropped'
    (the columns left out), 'build' (the key made from several columns: (name, SQL, parameters) or None)}. ValueError for a column or key that is not there."""
    shown = {c['name']: c for c in visible(columns)}
    chosen = step.get('columns')
    if chosen is not None and (not isinstance(chosen, list) or not chosen or len(set(map(str, chosen))) != len(chosen) or any(not isinstance(n, str) for n in chosen)):
        raise ValueError(f'步骤 {sid}：要留的列（columns）要写成不重复的列名列表')
    for n in chosen or []:
        if n not in shown:
            raise ValueError(f'步骤 {sid}：读的步骤里没有列 {n}')
    names = list(shown) if chosen is None else list(chosen)
    key, build, key_names = step.get('key'), None, None
    if key is not None:
        cols = key.get('columns') if isinstance(key, dict) else None
        if not isinstance(cols, list) or not cols or len(set(map(str, cols))) != len(cols) or any(not isinstance(c, str) or c not in shown for c in cols):
            raise ValueError(f'步骤 {sid}：主键（key）要写成 {{"columns": […], "separator": "|", "as": 新列名}}，列要在读的步骤里')
        separator = key.get('separator', '|')
        if not isinstance(separator, str) or len(separator) > 10:
            raise ValueError(f'步骤 {sid}：主键的分隔符最多 10 个字')
        if len(cols) == 1 and not key.get('as'):
            key_names = list(cols)
            names += [c for c in cols if c not in names]
        else:
            built = key.get('as') or '键'
            if not isinstance(built, str) or built in names or built.startswith('__') or built in shown and built not in cols:
                raise ValueError(f'步骤 {sid}：主键的新列名「{built}」不能和别的列重名')
            parts = [f'pl_text({_q(c)})' for c in cols]
            build = (built, f'({f" || ? || ".join(parts)})' if len(parts) > 1 else parts[0], [separator] * (len(parts) - 1))
            key_names = [built]
    out = [{k: v for k, v in shown[n].items() if k in ('name', 'type', 'origin')} for n in names] + ([{'name': build[0], 'type': 'text'}] if build else [])
    return {'columns': out, 'key': key_names, 'dropped': [n for n in shown if n not in names], 'build': build}


def check_pipeline(spec, datasets: dict, views: dict | None = None, ctx: dict | None = None) -> dict:
    """The pipeline as a copy, or ValueError with the words the person reads: every step has a known type and a new id, reads only steps written before it, and
    names tables, views and columns that exist; every operator of a transform is checked against the columns it reads, and an output's columns and key too."""
    views, ctx = views or {}, ctx or new_context()
    steps = spec.get('steps') if isinstance(spec, dict) else None
    if not isinstance(steps, list) or not steps:
        raise ValueError('管道要有 steps：一组按顺序写的步骤')
    if len(steps) > MAX_STEPS:
        raise ValueError(f'一条管道最多 {MAX_STEPS} 个步骤')
    columns: dict[str, list[dict]] = {}
    outputs: set[str] = set()
    for position, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f'第 {position + 1} 步要写成 {{"id": …, "type": …}}')
        sid = _text(step.get('id'), f'第 {position + 1} 步的 id')
        if sid in columns:
            raise ValueError(f'步骤编号重复：{sid}')
        kind = step.get('type')
        if kind not in STEP_TYPES:
            raise ValueError(f'步骤 {sid} 是不认识的步骤类型 {kind}，只有 {"、".join(STEP_TYPES)}')
        read = lambda ref, role: columns[ref] if isinstance(ref, str) and ref in columns else _undefined(sid, role, ref)   # a list or an object is not a step id
        if kind == 'input':
            columns[sid] = _input_columns(step, sid, datasets, views)
        elif kind == 'join':
            left, right = read(step.get('left'), '左'), read(step.get('right'), '右')
            if step.get('how') not in HOWS:
                raise ValueError(f'步骤 {sid}：关联方式只能是 inner 或 left（保留左边的行），或 anti（左边没有对上的行）、semi（左边有对上的行）')
            if step.get('null_keys') not in (None, *NULL_KEYS):
                raise ValueError(f'步骤 {sid}：空值的处理（null_keys）只能是 no_match（空值不匹配，默认）或 equal（空值相等）')
            on = step.get('on')
            if not isinstance(on, list) or not on or not all(isinstance(p, dict) for p in on):
                raise ValueError(f'步骤 {sid}：要写关联字段，例如 [{{"left": "订单号", "right": "订单号"}}]')
            for pair in on:
                for side, cols, ref in (('left', left, step['left']), ('right', right, step['right'])):
                    if not isinstance(pair.get(side), str) or pair[side] not in {c['name'] for c in visible(cols)}:
                        raise ValueError(f'步骤 {sid}：读的步骤 {ref} 里没有列 {pair.get(side)}')
            chosen = step.get('right_columns')
            if chosen is not None:
                if not isinstance(chosen, list) or any(not isinstance(c, str) or c not in {x['name'] for x in visible(right)} for c in chosen):
                    raise ValueError(f'步骤 {sid}：要带过来的右边的列（right_columns）要写成右边读的步骤里有的列名列表')
            columns[sid] = _join_columns(step, left, right)
        elif kind == 'transform':
            source = read(step.get('from'), '来源')
            try:
                columns[sid] = _transform(step, sid, 'x', source, ctx, position)[1]
            except OpError as exc:
                raise ValueError(str(exc)) from None
        else:
            source = read(step.get('from'), '来源')
            name = _text(step.get('name'), f'步骤 {sid}：输出要写名字，输出的名字')
            if len(name) > 100:
                raise ValueError(f'步骤 {sid}：输出的名字最多 100 个字')
            if name in outputs:
                raise ValueError(f'步骤 {sid}：已经有一个输出叫「{name}」，两个输出不能写到同一个数据集')
            outputs.add(name)
            columns[sid] = _output(step, sid, source)['columns']
    return copy.deepcopy(spec)


def compile_pipeline(spec: dict, datasets: dict, views: dict | None = None, ctx: dict | None = None) -> list[dict]:
    """One entry per step: {'id', 'type', 'table' (the temporary table the step ends in), 'columns': [{'name', 'type'}], 'sql' (the statement of a step that is
    one), 'stages' (a transform's operators, one statement each), 'output' (an output's keep and key)}. An output step that keeps every column is a name for a
    table already there: its sql is empty. A column carries 'origin', the stored table and column it comes from, which is how a code column is recognised after a
    join. The spec has been through check_pipeline."""
    views, ctx = views or {}, ctx or new_context()
    steps, kept = [], {}
    for index, step in enumerate(spec['steps']):
        sid, table = step['id'], f'pl_{index}'
        stages, output, params = [], None, []
        if step['type'] == 'input':
            data = _input_of(step, sid, datasets, views)[1]
            columns = _input_columns(step, sid, datasets, views)
            sql = f'CREATE TEMP TABLE {table} AS SELECT {", ".join(_q(c["name"]) for c in columns)} FROM {_q(data["table"])}'
        elif step['type'] == 'join':
            (left, lcols), (right, rcols) = kept[step['left']], kept[step['right']]
            columns = _join_columns(step, lcols, rcols)
            sql = _join_sql(step, table, left, right, columns)
        elif step['type'] == 'transform':
            src, columns = kept[step['from']]
            table, columns, stages = _transform(step, sid, src, columns, ctx, index)
            sql = ''
        else:
            src, source_columns = kept[step['from']]
            output = _output(step, sid, source_columns)
            columns = output['columns']
            if output['build'] or [c['name'] for c in columns] != [c['name'] for c in source_columns]:   # a column to drop or leave out (a hidden one), another order, or a key to make
                selects = [_q(c['name']) for c in columns if not (output['build'] and c['name'] == output['build'][0])] + ([f'{output["build"][1]} AS {_q(output["build"][0])}'] if output['build'] else [])
                params = output['build'][2] if output['build'] else []
                sql = f'CREATE TEMP TABLE {table} AS SELECT {", ".join(selects)} FROM {src}'
            else:
                table, sql = src, ''
        kept[sid] = (table, columns)
        steps.append({'id': sid, 'type': step['type'], 'table': table, 'columns': columns, 'sql': sql, 'params': params, 'stages': stages, 'output': output})
    return steps


def needed_steps(spec: dict, targets) -> set[str]:
    """The ids of the steps the targets read, directly or not, and the targets themselves: what has to run for them."""
    by_id = {s['id']: s for s in spec['steps'] if isinstance(s, dict) and isinstance(s.get('id'), str)}
    found, todo = set(), list(targets)
    while todo:
        sid = todo.pop()
        if sid in found or sid not in by_id:   # a step that reads one that is not there is for the check to refuse
            continue
        found.add(sid)
        todo += [by_id[sid][k] for k in ('left', 'right', 'from') if isinstance(by_id[sid].get(k), str)]
    return found


def _number(value):
    return None if value is None else int(value) if float(value).is_integer() else round(float(value), 2)


def _filled(keys: list[str]) -> str:
    return ' AND '.join(f"{_q(k)} IS NOT NULL AND {_q(k)} <> ''" for k in keys)


def _key_counts(conn, table: str, keys: list[str], name: str, equal: bool = False) -> None:
    """One row per distinct filled key of this input, with how many rows have it (columns k0, k1…, n), indexed. With `equal`, empty keys are keys too (an empty
    one is the same as a missing one)."""
    aliases = ', '.join((f"COALESCE({_q(k)}, '')" if equal else _q(k)) + f' AS k{i}' for i, k in enumerate(keys))
    where = '' if equal else f' WHERE {_filled(keys)}'
    conn.execute(f'CREATE TEMP TABLE {name} AS SELECT {aliases}, COUNT(*) AS n FROM {table}{where} GROUP BY {", ".join(f"k{i}" for i in range(len(keys)))}')
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
    equal = step.get('null_keys') == 'equal'
    _key_counts(conn, ltable, lkeys, f'jl_{index}', equal)
    _key_counts(conn, rtable, rkeys, f'jr_{index}', equal)
    on = ' AND '.join(f'l.k{i} = r.k{i}' for i in range(len(lkeys)))
    left_rows = conn.execute(f'SELECT COUNT(*) FROM {ltable}').fetchone()[0]
    matched, joined = conn.execute(f'SELECT COALESCE(SUM(l.n), 0), COALESCE(SUM(l.n * r.n), 0) FROM jl_{index} AS l JOIN jr_{index} AS r ON {on}').fetchone()
    expected = {'inner': joined, 'left': joined + left_rows - matched, 'anti': left_rows - matched, 'semi': matched}[step['how']]
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
        if c.get('hidden') or c['type'] not in NUMERIC or c['name'] in keys or c.get('origin') in skip or c['name'] not in out_names:
            continue
        without, with_ = _sum(conn, table, c['name'], baseline), _sum(conn, out_table, out_names[c['name']])
        if without is not None and with_ is not None and round(without, 6) != round(with_, 6):
            found.append({'column': c['name'], 'without': _number(without), 'with': _number(with_)})
    return found


def _join_report(conn, index: int, step: dict, compiled: dict, left: tuple, right: tuple, rows_out: int, measured: dict, skip) -> dict:
    """What a join did: the left rows with no match, the rows made beyond its left input and, when there are some, which keys repeat on the right and which
    numeric columns' sums would count rows more than once; the same for the right side's columns when the left side repeats a
    key; keys that match only after trimming or reading as numbers; empty keys."""
    (ltable, lcols), (rtable, rcols) = left, right
    left_rows, matched = measured['left_rows'], measured['matched_left']
    how = step['how']
    extra = rows_out - (left_rows if how == 'left' else matched) if how in ('inner', 'left') else 0
    lkeys, rkeys = [p['left'] for p in step['on']], [p['right'] for p in step['on']]
    on = ' AND '.join(f'l.k{i} = r.k{i}' for i in range(len(lkeys)))
    sides = ', '.join(f'l.k{i}' for i in range(len(lkeys)))
    report = {'how': how, 'on': step['on'], 'null_keys': step.get('null_keys') or 'no_match', 'left_rows': left_rows, 'matched_left': matched, 'left_unmatched': left_rows - matched,
              'extra_rows': extra, 'fan_out': None, 'right_fan_out': None,
              'left_blank': left_rows - conn.execute(f'SELECT COALESCE(SUM(n), 0) FROM jl_{index}').fetchone()[0],
              'right_blank': conn.execute(f'SELECT COUNT(*) FROM {rtable}').fetchone()[0] - conn.execute(f'SELECT COALESCE(SUM(n), 0) FROM jr_{index}').fetchone()[0],
              'near_matches': []}
    for i, (a, b) in enumerate(zip(lkeys, rkeys)):
        near = [row[0] for row in conn.execute(
            f'SELECT DISTINCT k{i} FROM jl_{index} WHERE k{i} NOT IN (SELECT k{i} FROM jr_{index}) '
            f'AND {_as_number(f"k{i}")} IN (SELECT {_as_number(f"k{i}")} FROM jr_{index}) ORDER BY k{i}')]
        if near:
            report['near_matches'].append({'left': a, 'right': b, 'count': len(near), 'examples': near[:EXAMPLES]})
    if how in ('anti', 'semi'):
        return report

    def repeating(side: str) -> tuple[int, list[dict]]:
        """Keys both inputs have that `side` has on more than one row: how many, and the first few with their rows on each side."""
        shown = f'FROM jl_{index} AS l JOIN jr_{index} AS r ON {on} WHERE {side}.n > 1'
        count = conn.execute(f'SELECT COUNT(*) {shown}').fetchone()[0]
        rows = conn.execute(f'SELECT {sides}, r.n, l.n {shown} ORDER BY {side}.n DESC, {sides} LIMIT {EXAMPLES}').fetchall()
        return count, [{'key': {p['left']: value for p, value in zip(step['on'], row[:-2])}, 'right_rows': row[-2], 'left_rows': row[-1]} for row in rows]

    skip_keys = set(lkeys)
    out_left = {c['source']: c['name'] for c in compiled['columns'] if c.get('side') == 'l' and not c.get('hidden')}
    out_right = {c['source']: c['name'] for c in compiled['columns'] if c.get('side') == 'r' and not c.get('hidden')}
    if extra > 0:
        count, examples = repeating('r')
        baseline = '' if how == 'left' else f' WHERE ({", ".join(_q(k) for k in lkeys)}) IN (SELECT {", ".join(f"k{i}" for i in range(len(lkeys)))} FROM jr_{index})'
        doubled = _doubled(conn, lcols, skip_keys, skip, ltable, baseline, compiled['table'], out_left)
        report['fan_out'] = {'columns': lkeys, 'repeated_keys': count, 'examples': examples, 'double_counted': doubled}
    count, examples = repeating('l')
    if count:
        baseline = f' WHERE ({", ".join(_q(k) for k in rkeys)}) IN (SELECT {", ".join(f"k{i}" for i in range(len(lkeys)))} FROM jl_{index})'
        doubled = _doubled(conn, rcols, set(rkeys), skip, rtable, baseline, compiled['table'], out_right)
        if doubled:
            report['right_fan_out'] = {'columns': rkeys, 'repeated_keys': count, 'examples': examples, 'double_counted': doubled}
    return report


def _output_report(conn, table: str, output: dict) -> dict:
    """The output as it will be written: its columns, its key and, when it has one, the keys that repeat (the first KEY_EXAMPLES, with how many rows) and the
    rows whose key is empty."""
    report = {'columns': output['columns'], 'dropped': output['dropped'], 'key': output['key'], 'duplicate_keys': None, 'empty_keys': 0}
    if output['key']:
        keys = ', '.join(_q(k) for k in output['key'])
        blank = ' OR '.join(f"({_q(k)} IS NULL OR TRIM(CAST({_q(k)} AS TEXT)) = '')" for k in output['key'])
        report['empty_keys'] = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {blank}').fetchone()[0]
        repeated = f'SELECT {keys}, COUNT(*) AS n FROM {table} WHERE NOT ({blank}) GROUP BY {keys} HAVING n > 1'
        count, extra = conn.execute(f'SELECT COUNT(*), COALESCE(SUM(n - 1), 0) FROM ({repeated})').fetchone()
        if count:
            report['duplicate_keys'] = {'count': count, 'extra_rows': extra, 'examples': [{'key': list(r[:-1]), 'rows': r[-1]} for r in
                                                                                         conn.execute(f'{repeated} ORDER BY n DESC, {keys} LIMIT {KEY_EXAMPLES}')]}
    return report


FAILURE_KEYS = (('failures', 'cast_failures'), ('errors', 'calc_errors'), ('unmapped_rows', 'unmapped_rows'), ('dropped_null', 'dropped_by_empty_condition'))


def _failures(operators: list[dict]) -> dict:
    """What a node lost or could not do, by kind, nonzero only: values that did not convert, expressions with no result, codes with no label, rows a condition
    dropped because a field was empty."""
    out = {}
    for op in operators:
        for key, name in FAILURE_KEYS:
            if op.get(key):
                out[name] = out.get(name, 0) + op[key]
    return out


def run_pipeline(conn, spec: dict, datasets: dict, views: dict | None = None, skip=frozenset(), row_cap: int = ROW_CAP, ctx: dict | None = None,
                 upto=None, after=None) -> dict:
    """Run a checked pipeline on a connection that may only read its tables: {'nodes': [...], 'row_cap'} in step order. Each node has its id, type, rows_in
    (one count per input), rows_out, columns (names a person sees), column_types, sql, and for a join `join` (see _join_report), for a transform `operators`
    (each with its rows in and out, how many it affected and what it could not do) and `failures`, for an output `output` (see _output_report). skip: "table.column"
    names that are codes, which a join does not report as sums. upto: the ids of the steps to run (a step not in it is reported with skipped true, and with
    orphan true when no output reads it); None runs all. after(conn, node, compiled): called as each step has run, while its table is still there. ValueError,
    before it runs, for a join that would make more than row_cap rows. The temporary tables are dropped afterwards."""
    views, ctx = views or {}, ctx or new_context()
    steps = compile_pipeline(check_pipeline(spec, datasets, views, ctx), datasets, views, ctx)
    by_id = {s['id']: s for s in steps}
    feeds = needed_steps(spec, [s['id'] for s in spec['steps'] if s['type'] == 'output'])
    register(conn)
    nodes, made = [], []
    try:
        for index, (step, compiled) in enumerate(zip(spec['steps'], steps)):
            if upto is not None and step['id'] not in upto:
                nodes.append({'id': step['id'], 'type': step['type'], 'skipped': True, 'orphan': step['id'] not in feeds})
                continue
            measured = None
            if step['type'] == 'join':
                left, right = by_id[step['left']], by_id[step['right']]
                made += [f'jl_{index}', f'jr_{index}']
                measured = _measure_join(conn, index, step, left['table'], right['table'], row_cap)
            if compiled['sql']:
                made.append(compiled['table'])
                conn.execute(f'DROP TABLE IF EXISTS temp.{compiled["table"]}')
                conn.execute(compiled['sql'], compiled['params'])
            operators = []
            if compiled['stages']:
                previous = by_id[step['from']]['table']
                for stage in compiled['stages']:
                    made.append(stage['table'])
                    conn.execute(f'DROP TABLE IF EXISTS temp.{stage["table"]}')
                    conn.execute(stage['sql'], stage['params'])
                    extra = stage['measure'](conn, previous, stage['table'])
                    operators.append({'op': stage['op'], 'rows_in': conn.execute(f'SELECT COUNT(*) FROM {previous}').fetchone()[0],
                                      'rows_out': conn.execute(f'SELECT COUNT(*) FROM {stage["table"]}').fetchone()[0], **{k: v for k, v in extra.items() if k != 'halt'}})
                    if extra.get('halt'):
                        raise PipelineRunError(extra['halt'])
                    previous = stage['table']
            rows_out = conn.execute(f'SELECT COUNT(*) FROM {compiled["table"]}').fetchone()[0]
            inputs = [step[k] for k in ('left', 'right', 'from') if k in step]
            shown = visible(compiled['columns'])
            node = {'id': compiled['id'], 'type': compiled['type'],
                    'rows_in': [(views[step['view']] if 'view' in step else datasets[dataset_key(step)])['rows']] if step['type'] == 'input'
                    else [conn.execute(f'SELECT COUNT(*) FROM {by_id[i]["table"]}').fetchone()[0] for i in inputs],
                    'rows_out': rows_out, 'columns': [c['name'] for c in shown], 'sql': compiled['sql'],
                    'column_types': [{k: c[k] for k in ('name', 'type', 'badge', 'aggregation', 'origin') if k in c} for c in shown]}
            if step['type'] == 'input':
                node['reads'] = _input_of(step, step['id'], datasets, views)[0]
            if measured:
                node['join'] = _join_report(conn, index, step, compiled, (left['table'], left['columns']), (right['table'], right['columns']), rows_out, measured, skip)
            if step['type'] == 'transform':
                node['operators'] = operators
                node['failures'] = _failures(operators)
            if step['type'] == 'output':
                node['output'] = _output_report(conn, compiled['table'], compiled['output'])
            nodes.append(node)
            if after:
                after(conn, node, compiled)
    finally:
        for table in made:
            conn.execute(f'DROP TABLE IF EXISTS temp.{table}')
    return {'nodes': nodes, 'row_cap': row_cap}
