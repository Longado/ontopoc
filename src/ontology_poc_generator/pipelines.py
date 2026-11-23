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
that come along); transform (the operators of pipeline_ops, each reporting the rows it affected); union (the rows of several steps one after another, columns
matched by name: a column whose type differs between them, a missing column unless "missing": "empty", or a code column whose confirmed meanings are not the same on
every side is refused; the rows found in more than one input are counted, as is every row a missing column was left empty on); split (each row to the first branch
whose condition holds, the rest to a "rest" branch when there is one; a branch has its own id that later steps read, and the run counts per branch the rows, the rows
whose condition was empty and the rows that met it but went to an earlier branch, and the rows that went to no branch); output (the columns it keeps, a key built
from columns, duplicate and empty keys counted). A join is measured before it runs, from the distinct keys of its two inputs (one GROUP BY each, so the cost follows the
inputs and not the rows the join makes), and refused when it would make more than ROW_CAP rows. After it runs, when it made more rows than the rows of its left
input that took part, the keys that repeat on the right and the numeric columns whose sum would then be counted more than once are named, with the sums before
and after; the same is said the other way round when the left side repeats a key and a numeric column of the right side would be counted more than once. An
inner or left join also carries two hidden columns that identify the row each value came from, so that a later group statistic can say, group by group, what
it counted twice. A column that is a code (confirmed or not) is not a sum and is left out of both. Keys are compared as the text stored: " 2" and "2", or "1" and
"1.0", do not match, and the report says how many left keys would match if they were trimmed or read as numbers.
Steps stay plain data and a run changes nothing in the workspace; the engine is SQLite, the statements are generic SQL.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import re
import sqlite3
import time

from ontology_poc_generator.pipeline_funcs import register
from ontology_poc_generator.pipeline_llm import check_llm_step, llm_sql
from ontology_poc_generator.pipeline_ops import MAX_OPERATORS, OpError, UPSTREAM, _double_counted, _where, carry, compile_op, new_context, visible
from ontology_poc_generator.lang import tr
from ontology_poc_generator.pipeline_expr import WordMap

NUMERIC = ('integer', 'decimal')
HOWS = ('inner', 'left', 'anti', 'semi')
NULL_KEYS = ('no_match', 'equal')
EXAMPLES = 3
STEP_TYPES = ('input', 'join', 'transform', 'llm', 'union', 'split', 'output')
MAX_UNION, MAX_BRANCHES = 10, 10   # inputs of one union, branches of one split
MISSING = ('error', 'empty')
TYPE_WORD = WordMap({'integer': ('整数', 'whole number'), 'decimal': ('小数', 'decimal'), 'text': ('文本', 'text'), 'date': ('日期', 'date'), 'month': ('月份', 'month'), 'datetime': ('日期时间', 'date and time'), 'boolean': ('是否', 'yes/no')})
BRANCH = '__branch'   # the column of a split's own table that says which branch a row went to (-1: none)
ROW_CAP = 1_000_000   # the most rows one join may make: past it the join is refused, before it runs
MAX_STEPS = 60
KEY_EXAMPLES = 20
PREVIEW_SECONDS, RUN_SECONDS = 5, 20   # the longest one call may compute: trying a pipeline, and running it
OUTPUT_CAP = 200_000   # the most rows all the outputs of one run may hold together
_ENGINE_LIMIT = re.compile(r'interrupted|too large|too many|too complex|too deep')


class PipelineRunError(ValueError):
    """A run that stopped for a reason a person asked for (a conversion set to stop on failure), or that was too much for the engine."""


class Lease:
    """The time the engine has left in a `deadline` block. Time spent waiting for the model is not the engine's: the step that waited gives it back (`extend`)."""

    def __init__(self, seconds: float):
        self.end = time.monotonic() + seconds

    def extend(self, seconds: float) -> None:
        self.end += seconds


@contextmanager
def deadline(engine, seconds: float, advice: str | None = None):
    """Whatever the engine computes inside this block is stopped after `seconds` (SQLite's progress handler; it stops SQL, not a Python function in the middle of a
    value). The stop, and a statement SQLite itself refuses as too big, come out as a PipelineRunError in words a person reads, with `advice` for what to do about it.
    Yields the Lease."""
    advice = advice or tr('数据多的时候，先在前面加过滤，或把步骤拆开分别试', 'When there is a lot of data, add a filter earlier on, or split the steps and try them one by one')
    lease = Lease(seconds)
    engine.set_progress_handler(lambda: 1 if time.monotonic() > lease.end else 0, 1000)
    try:
        yield lease
    except sqlite3.OperationalError as exc:
        if not _ENGINE_LIMIT.search(str(exc)):
            raise
        if 'interrupted' in str(exc):
            raise PipelineRunError(tr(f'算了超过 {seconds:g} 秒，已经停下。{advice}', f'Ran for more than {seconds:g} seconds and stopped. {advice}')) from None
        raise PipelineRunError(tr(f'数据库算不了这一步：{exc}。表达式、条件或步骤太大，请拆小', f'The database could not work out this step: {exc}. The expression, condition or step is too big; split it up')) from None
    finally:
        engine.set_progress_handler(None, 0)


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
        raise ValueError(tr(f'{what}要写成不为空的文字', f'{what} must be non-empty text'))
    return value


def dataset_key(step: dict) -> str:
    """What an input step's dataset is called in the `datasets` given to a run: its name, or name@vN when a version is pinned."""
    return step['dataset'] if step.get('version') is None else f'{step["dataset"]}@v{step["version"]}'


def _input_of(step: dict, sid: str, datasets: dict, views: dict) -> tuple[str, dict]:
    """(what it is called for a person, its dataset or view) for an input step; ValueError when it names neither or both."""
    if 'view' in step and 'dataset' in step:
        raise ValueError(tr(f'步骤 {sid}：输入只能读一张表（dataset）或一个视图（view），不能两个都写', f'Step {sid}: an input can read one dataset or one view, not both'))
    kind, pool = (tr('视图', 'view'), views) if 'view' in step else (tr('表', 'table'), datasets)
    name = step.get('view') if 'view' in step else step.get('dataset')
    if not isinstance(name, str):
        raise ValueError(tr(f'步骤 {sid}：输入的{kind}名要写成文字', f'Step {sid}: the {kind} name of an input must be text'))
    if 'version' in step and ('view' in step or not isinstance(step['version'], int) or isinstance(step['version'], bool) or step['version'] < 1):
        raise ValueError(tr(f'步骤 {sid}：版本（version）只用在表上，写成大于 0 的整数', f'Step {sid}: version only applies to a dataset; write a whole number greater than 0'))
    key = name if 'view' in step else dataset_key(step)
    if key not in pool:
        raise ValueError(tr(f'步骤 {sid}：这次运行里没有这{"个" if "view" in step else "张"}{kind} {key}', f'Step {sid}: this run has no {kind} {key}'))
    return f'{kind} {name}' + (tr(f' 第 {step["version"]} 版', f' version {step["version"]}') if step.get('version') is not None else ''), pool[key]


def _input_columns(step: dict, sid: str, datasets: dict, views: dict, ctx: dict) -> list[dict]:
    """The columns an input reads, each with where it comes from; one a builder switched off for the model (`ctx['unsent']`: "dataset.column"), or that a pipeline wrote
    from such a column or from a model's answer (`ctx['ai']`), is marked, and the mark travels with it."""
    data = _input_of(step, sid, datasets, views)[1]
    origin = data['source'] if 'view' in step else step['dataset']
    return [{**c, 'origin': f'{origin}.{c["name"]}', **{mark: True for mark in ('unsent', 'ai') if f'{origin}.{c["name"]}' in ctx.get(mark, ())},
             **({'fan_agg': [UPSTREAM]} if f'{origin}.{c["name"]}' in ctx.get('fan', ()) else {})} for c in data['columns']]


def _split_read(sid: str, ref: str):
    raise ValueError(tr(f'步骤 {sid}：{ref} 是拆分，要读它的某一个分支（写分支的名字），不能读整个拆分', f'Step {sid}: {ref} is a split, so read one of its branches (give the branch name), not the whole split'))


def _undefined(sid: str, role: str, ref):
    raise ValueError(tr(f'步骤 {sid}：{role}边读的步骤 {ref} 还没有定义（只能读写在它前面的步骤）', f'Step {sid}: the {role} input {ref} is not defined yet (a step can only read steps written before it)'))


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
        raise ValueError(tr(f'步骤 {step["id"]}：连接后有重名的列：{sorted({n for n in names if names.count(n) > 1})[0]}', f'Step {step["id"]}: columns have the same name after the join: {sorted({n for n in names if names.count(n) > 1})[0]}'))
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
        raise ValueError(tr(f'步骤 {sid}：operators 要写成操作的列表，最多 {MAX_OPERATORS} 个', f'Step {sid}: operators must be a list of operators, at most {MAX_OPERATORS}'))
    columns = [{k: v for k, v in c.items() if k != 'badge'} for c in columns]
    stages = []
    for j, op in enumerate(operators):
        label = tr(f'步骤 {sid} 的第 {j + 1} 个操作', f'operator {j + 1} of step {sid}')
        stage = compile_op(op, src, columns, ctx, tr(f'{label}（{op.get("op") if isinstance(op, dict) else op}）', f'{label} ({op.get("op") if isinstance(op, dict) else op})'))
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
        raise ValueError(tr(f'步骤 {sid}：要留的列（columns）要写成不重复的列名列表', f'Step {sid}: the columns to keep (columns) must be a list of distinct column names'))
    for n in chosen or []:
        if n not in shown:
            raise ValueError(tr(f'步骤 {sid}：读的步骤里没有列 {n}', f'Step {sid}: the step it reads has no column {n}'))
    names = list(shown) if chosen is None else list(chosen)
    key, build, key_names = step.get('key'), None, None
    if key is not None:
        cols = key.get('columns') if isinstance(key, dict) else None
        if not isinstance(cols, list) or not cols or len(set(map(str, cols))) != len(cols) or any(not isinstance(c, str) or c not in shown for c in cols):
            raise ValueError(tr(f'步骤 {sid}：主键（key）要写成 {{"columns": […], "separator": "|", "as": 新列名}}，列要在读的步骤里', f'Step {sid}: the key must be written as {{"columns": [...], "separator": "|", "as": new column name}}, and the columns must be in the step it reads'))
        separator = key.get('separator', '|')
        if not isinstance(separator, str) or len(separator) > 10:
            raise ValueError(tr(f'步骤 {sid}：主键的分隔符最多 10 个字', f'Step {sid}: the key separator can be at most 10 characters'))
        if len(cols) == 1 and not key.get('as'):
            key_names = list(cols)
            names += [c for c in cols if c not in names]
        else:
            built = key.get('as') or tr('键', 'key')
            if not isinstance(built, str) or built in names or built.startswith('__') or built in shown and built not in cols:
                raise ValueError(tr(f'步骤 {sid}：主键的新列名「{built}」不能和别的列重名', f'Step {sid}: the new key column name "{built}" cannot be the same as another column'))
            parts = [f'pl_text({_q(c)})' for c in cols]
            build = (built, f'({f" || ? || ".join(parts)})' if len(parts) > 1 else parts[0], [separator] * (len(parts) - 1))
            key_names = [built]
    out = [{k: v for k, v in shown[n].items() if k in ('name', 'type', 'origin', 'ai', 'unsent', 'fan_agg')} for n in names] + ([{'name': build[0], 'type': 'text', **carry(*(shown[c] for c in cols))}] if build else [])
    return {'columns': out, 'key': key_names, 'dropped': [n for n in shown if n not in names], 'build': build}


def _union_columns(step: dict, sid: str, sources: list[tuple[str, list[dict]]], ctx: dict) -> list[dict]:
    """The columns of a union: every column a person sees in any input, in the order they first appear, each with the marks of all the columns it stacks. The hidden
    columns of a join (the source rows) do not go through: rows of different inputs have no common source row. ValueError for a column of two types, a column one
    input lacks (unless missing is "empty"), and a code column whose confirmed meanings are not the same in every input."""
    names = list(dict.fromkeys(c['name'] for _, cols in sources for c in visible(cols)))
    by_input = [(ref, {c['name']: c for c in visible(cols)}) for ref, cols in sources]
    out = []
    for n in names:
        have = [(ref, cols[n]) for ref, cols in by_input if n in cols]
        types = list(dict.fromkeys(c['type'] for _, c in have))
        if len(types) > 1:
            where = '，'.join(tr(f'在 {ref} 里是{TYPE_WORD.get(c["type"], c["type"])}', f'in {ref} it is {TYPE_WORD.get(c["type"], c["type"])}') for ref, c in have)
            raise ValueError(tr(f'步骤 {sid}：列「{n}」{where}：先用“字段转换”把它们变成同一种类型再合并', f'Step {sid}: column "{n}" {where}. Use "Convert type" to make them the same type before combining'))
        lacking = [ref for ref, cols in by_input if n not in cols]
        if lacking and step.get('missing', 'error') != 'empty':
            raise ValueError(tr(f'步骤 {sid}：{"、".join(lacking)} 没有列「{n}」。要让缺的列留空，把 missing 设成 empty（留空的行会数出来）；或者先把列名改成一样的', f'Step {sid}: {", ".join(lacking)} has no column "{n}". To leave the missing columns empty, set missing to empty (the rows left empty are counted); or rename the columns to match first'))
        origins = list(dict.fromkeys(c.get('origin') for _, c in have))
        if len(origins) > 1 and any(o in ctx.get('codes', ()) for o in origins):
            meanings = [ctx.get('meanings', {}).get(o) for o in origins]
            if not all(meanings) or any(m != meanings[0] for m in meanings):
                raise ValueError(tr(f'步骤 {sid}：列「{n}」是代码列，来自 {"、".join(str(o) for o in origins)}，它们确认过的代码含义不一样（或有一边没有确认）：'
                                 '合并后同一个代码会是两个意思。先用“打标签”把代码换成含义，再合并', f'Step {sid}: column "{n}" is a code column from {", ".join(str(o) for o in origins)}, and their confirmed code meanings differ (or one side is not confirmed): '
                                 'after combining, the same code would mean two things. Use "Add labels" to replace the codes with meanings first, then combine'))
            ctx.setdefault('used', set()).update(origins)   # the union stands on every side's meanings: one of them changing sends it back for a look
        first = have[0][1]
        out.append({'name': n, 'type': types[0], **({'origin': first['origin']} if first.get('origin') else {}), **carry(*(c for _, c in have))})   # a computed column has no origin
    added = step.get('source_column')
    if added is not None:
        if not isinstance(added, str) or not added.strip() or len(added) > 60 or added in names or added.startswith('__'):
            raise ValueError(tr(f'步骤 {sid}：标出来源的新列（source_column）要写一个和别的列都不重名的列名', f'Step {sid}: the new column that marks the source (source_column) needs a name that no other column has'))
        out.append({'name': added, 'type': 'text'})
    return out


def _union_sql(step: dict, table: str, sources: list[tuple[str, str, list[dict]]], columns: list[dict]) -> tuple[str, list]:
    """CREATE TEMP TABLE … AS one SELECT per input joined by UNION ALL; a column an input lacks is NULL there, and the source column holds the input's step id."""
    added = step.get('source_column')
    selects, params = [], []
    for ref, table_of, cols in sources:
        have = {c['name'] for c in visible(cols)}
        parts = [(_q(c['name']) if c['name'] in have else 'NULL') + f' AS {_q(c["name"])}' for c in columns if c['name'] != added]
        if added:
            parts.append(f'? AS {_q(added)}')
            params.append(ref)
        selects.append(f'SELECT {", ".join(parts)} FROM {table_of}')
    return f'CREATE TEMP TABLE {table} AS ' + ' UNION ALL '.join(selects), params


def _branches(step: dict, sid: str, columns: list[dict], ctx: dict, taken) -> list[dict]:
    """A split's branches as [{'id', 'rest', 'cond', 'params'}], checked: at least one branch with a condition, every id new, at most one rest branch and it is the last."""
    branches = step.get('branches')
    if not isinstance(branches, list) or not branches or len(branches) > MAX_BRANCHES or not all(isinstance(b, dict) for b in branches):
        raise ValueError(tr(f'步骤 {sid}：拆分要写分支（branches），每个分支 {{"id": 名字, "where": 条件}}，最后可以有一个 {{"id": 名字, "rest": true}} 接住其余的行，最多 {MAX_BRANCHES} 个', f'Step {sid}: a split needs branches, each {{"id": name, "where": condition}}, and optionally a last {{"id": name, "rest": true}} to catch the other rows, at most {MAX_BRANCHES}'))
    out, seen = [], set()
    for i, b in enumerate(branches):
        bid = _text(b.get('id'), tr(f'步骤 {sid} 的第 {i + 1} 个分支的名字（id）', f'the name (id) of branch {i + 1} of step {sid}'))
        if bid in taken or bid in seen or bid == sid:
            raise ValueError(tr(f'步骤 {sid}：分支名「{bid}」和别的步骤或分支重复了', f'Step {sid}: the branch name "{bid}" is the same as another step or branch'))
        seen.add(bid)
        if b.get('rest'):
            if i != len(branches) - 1:
                raise ValueError(tr(f'步骤 {sid}：“其余”分支（rest）要放在最后，接住前面的分支都没接的行', f'Step {sid}: the "rest" branch must come last and catch the rows no earlier branch took'))
            out.append({'id': bid, 'rest': True, 'cond': None, 'params': []})
            continue
        if b.get('where') is None:
            raise ValueError(tr(f'步骤 {sid}：分支「{bid}」要写条件（where），或者写成 "rest": true 接住其余的行', f'Step {sid}: branch "{bid}" needs a condition (where), or "rest": true to catch the other rows'))
        try:
            cond, params = _where(b['where'], columns, ctx, tr(f'步骤 {sid} 的分支「{bid}」', f'branch "{bid}" of step {sid}'))
        except OpError as exc:
            raise ValueError(str(exc)) from None
        out.append({'id': bid, 'rest': False, 'cond': cond, 'params': params})
    if not any(not b['rest'] for b in out):
        raise ValueError(tr(f'步骤 {sid}：拆分至少要有一个带条件的分支', f'Step {sid}: a split needs at least one branch with a condition'))
    return out


def check_pipeline(spec, datasets: dict, views: dict | None = None, ctx: dict | None = None) -> dict:
    """The pipeline as a copy, or ValueError with the words the person reads: every step has a known type and a new id, reads only steps written before it, and
    names tables, views and columns that exist; every operator of a transform is checked against the columns it reads, and an output's columns and key too."""
    views, ctx = views or {}, ctx or new_context()
    steps = spec.get('steps') if isinstance(spec, dict) else None
    if not isinstance(steps, list) or not steps:
        raise ValueError(tr('管道要有 steps：一组按顺序写的步骤', 'A pipeline needs steps: a list of steps written in order'))
    if len(steps) > MAX_STEPS:
        raise ValueError(tr(f'一条管道最多 {MAX_STEPS} 个步骤', f'A pipeline can have at most {MAX_STEPS} steps'))
    columns: dict[str, list[dict]] = {}
    outputs: set[str] = set()
    splits: set[str] = set()   # a split is read through its branches, not by its own id
    for position, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(tr(f'第 {position + 1} 步要写成 {{"id": …, "type": …}}', f'Step {position + 1} must be written as {{"id": ..., "type": ...}}'))
        sid = _text(step.get('id'), tr(f'第 {position + 1} 步的 id', f'the id of step {position + 1}'))
        if sid in columns:
            raise ValueError(tr(f'步骤编号重复：{sid}', f'Step id repeated: {sid}'))
        kind = step.get('type')
        if kind not in STEP_TYPES:
            raise ValueError(tr(f'步骤 {sid} 是不认识的步骤类型 {kind}，只有 {"、".join(STEP_TYPES)}', f'Step {sid} has an unknown step type {kind}. The types are {", ".join(STEP_TYPES)}'))
        read = lambda ref, role: _split_read(sid, ref) if isinstance(ref, str) and ref in splits else columns[ref] if isinstance(ref, str) and ref in columns else _undefined(sid, role, ref)   # a list or an object is not a step id
        if kind == 'input':
            columns[sid] = _input_columns(step, sid, datasets, views, ctx)
        elif kind == 'join':
            left, right = read(step.get('left'), tr('左', 'left')), read(step.get('right'), tr('右', 'right'))
            if step.get('how') not in HOWS:
                raise ValueError(tr(f'步骤 {sid}：关联方式只能是 inner 或 left（保留左边的行），或 anti（左边没有对上的行）、semi（左边有对上的行）', f'Step {sid}: the join type must be inner or left (keep the left rows), or anti (left rows with no match) or semi (left rows with a match)'))
            if step.get('null_keys') not in (None, *NULL_KEYS):
                raise ValueError(tr(f'步骤 {sid}：空值的处理（null_keys）只能是 no_match（空值不匹配，默认）或 equal（空值相等）', f'Step {sid}: null_keys must be no_match (empty values do not match, the default) or equal (empty values are equal)'))
            on = step.get('on')
            if not isinstance(on, list) or not on or not all(isinstance(p, dict) for p in on):
                raise ValueError(tr(f'步骤 {sid}：要写关联字段，例如 [{{"left": "订单号", "right": "订单号"}}]', f'Step {sid}: write the join fields, for example [{{"left": "order_id", "right": "order_id"}}]'))
            for pair in on:
                for side, cols, ref in (('left', left, step['left']), ('right', right, step['right'])):
                    if pair.get(side) in (None, ''):
                        raise ValueError(tr(f'步骤 {sid}：关联的列没选齐', f'Step {sid}: the join columns are not all chosen'))
                    if not isinstance(pair.get(side), str) or pair[side] not in {c['name'] for c in visible(cols)}:
                        raise ValueError(tr(f'步骤 {sid}：读的步骤 {ref} 里没有列 {pair.get(side)}', f'Step {sid}: the step {ref} it reads has no column {pair.get(side)}'))
            chosen = step.get('right_columns')
            if chosen is not None:
                if not isinstance(chosen, list) or any(not isinstance(c, str) or c not in {x['name'] for x in visible(right)} for c in chosen):
                    raise ValueError(tr(f'步骤 {sid}：要带过来的右边的列（right_columns）要写成右边读的步骤里有的列名列表', f'Step {sid}: the right-hand columns to bring over (right_columns) must be a list of column names the right-hand step has'))
            columns[sid] = _join_columns(step, left, right)
        elif kind == 'transform':
            source = read(step.get('from'), tr('来源', 'source'))
            try:
                columns[sid] = _transform(step, sid, 'x', source, ctx, position)[1]
            except OpError as exc:
                raise ValueError(str(exc)) from None
        elif kind == 'llm':
            columns[sid] = check_llm_step(step, sid, read(step.get('from'), tr('来源', 'source')))
        elif kind == 'union':
            refs = step.get('inputs')
            if not isinstance(refs, list) or len(refs) < 2 or len(refs) > MAX_UNION or not all(isinstance(r, str) for r in refs) or len(set(refs)) != len(refs):
                raise ValueError(tr(f'步骤 {sid}：合并要写至少两个不同的来源步骤（inputs），最多 {MAX_UNION} 个', f'Step {sid}: a union needs at least two different source steps (inputs), at most {MAX_UNION}'))
            if step.get('missing', 'error') not in MISSING:
                raise ValueError(tr(f'步骤 {sid}：缺列的处理（missing）只能是 error（有输入缺列就不合并，默认）或 empty（缺的列留空，并数出留空的行）', f'Step {sid}: missing must be error (do not combine if an input lacks a column, the default) or empty (leave the missing columns empty and count those rows)'))
            columns[sid] = _union_columns(step, sid, [(r, read(r, tr('来源', 'source'))) for r in refs], ctx)
        elif kind == 'split':
            source = read(step.get('from'), tr('来源', 'source'))
            for b in _branches(step, sid, source, ctx, columns):
                columns[b['id']] = [{k: v for k, v in c.items() if k != 'badge'} for c in source]
            columns[sid] = source
            splits.add(sid)
        else:
            source = read(step.get('from'), tr('来源', 'source'))
            name = _text(step.get('name'), tr(f'步骤 {sid}：输出要写名字，输出的名字', f'Step {sid}: an output needs a name, the name of the output'))
            if len(name) > 100:
                raise ValueError(tr(f'步骤 {sid}：输出的名字最多 100 个字', f'Step {sid}: an output name can be at most 100 characters'))
            if name in outputs:
                raise ValueError(tr(f'步骤 {sid}：已经有一个输出叫「{name}」，两个输出不能写到同一个数据集', f'Step {sid}: there is already an output called "{name}", and two outputs cannot write to the same dataset'))
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
        stages, output, params, llm, split = [], None, [], None, None
        if step['type'] == 'input':
            data = _input_of(step, sid, datasets, views)[1]
            columns = _input_columns(step, sid, datasets, views, ctx)
            sql = f'CREATE TEMP TABLE {table} AS SELECT {", ".join(_q(c["name"]) for c in columns)} FROM {_q(data["table"])}'
        elif step['type'] == 'join':
            (left, lcols), (right, rcols) = kept[step['left']], kept[step['right']]
            columns = _join_columns(step, lcols, rcols)
            sql = _join_sql(step, table, left, right, columns)
        elif step['type'] == 'transform':
            src, columns = kept[step['from']]
            table, columns, stages = _transform(step, sid, src, columns, ctx, index)
            sql = ''
        elif step['type'] == 'union':
            sources = [(r, *kept[r]) for r in step['inputs']]
            columns = _union_columns(step, sid, [(r, cols) for r, _, cols in sources], ctx)
            sql, params = _union_sql(step, table, sources, columns)
        elif step['type'] == 'split':
            src, columns = kept[step['from']]
            columns = [{k: v for k, v in c.items() if k != 'badge'} for c in columns]
            made = _branches(step, sid, columns, ctx, {})
            ruled = [b for b in made if not b['rest']]
            case = ' '.join(f'WHEN ({b["cond"]}) THEN {i}' for i, b in enumerate(ruled))
            params = [p for b in ruled for p in b['params']]
            names = ', '.join(_q(c['name']) for c in columns)
            taken = {c['name'] for c in columns}
            marker = next(m for m in (BRANCH, *(f'{BRANCH}_{k}' for k in range(1, len(taken) + 2))) if m not in taken)   # never one of the source's own columns
            sql = f'CREATE TEMP TABLE {table} AS SELECT {names}, CASE {case} ELSE -1 END AS {_q(marker)} FROM {src}'
            split = []
            for i, b in enumerate(made):
                btable = f'{table}_b{i}'
                split.append({**b, 'index': -1 if b['rest'] else i, 'table': btable, 'marker': marker,
                              'sql': f'CREATE TEMP TABLE {btable} AS SELECT {names} FROM {table} WHERE {_q(marker)} = {-1 if b["rest"] else i}'})
                kept[b['id']] = (btable, columns)
        elif step['type'] == 'llm':
            src, source_columns = kept[step['from']]
            columns = check_llm_step(step, sid, source_columns)
            llm = {'answers': f'{table}_ans', 'source': src, 'source_columns': source_columns}
            sql = llm_sql(table, src, source_columns, columns[len(source_columns):], llm['answers'])
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
        steps.append({'id': sid, 'type': step['type'], 'table': table, 'columns': columns, 'sql': sql, 'params': params, 'stages': stages, 'output': output, 'llm': llm,
                      'split': split})
    return steps


def step_inputs(step: dict) -> list[str]:
    """The ids a step reads: a join's two sides, the one step a transform, LLM, split or output reads, a union's inputs (a branch id stands for its split)."""
    refs = [step[k] for k in ('left', 'right', 'from') if isinstance(step.get(k), str)]
    return refs + [r for r in step.get('inputs') or [] if isinstance(r, str)] if isinstance(step.get('inputs'), list) else refs


def needed_steps(spec: dict, targets) -> set[str]:
    """The ids of the steps the targets read, directly or not, and the targets themselves: what has to run for them."""
    by_id = {s['id']: s for s in spec['steps'] if isinstance(s, dict) and isinstance(s.get('id'), str)}
    owner = {b['id']: s['id'] for s in by_id.values() if s.get('type') == 'split' and isinstance(s.get('branches'), list)
             for b in s['branches'] if isinstance(b, dict) and isinstance(b.get('id'), str)}   # a branch is made by its split
    found, todo = set(), list(targets)
    while todo:
        ref = todo.pop()
        sid = owner.get(ref, ref)
        if sid in found or sid not in by_id:   # a step that reads one that is not there is for the check to refuse
            continue
        found.add(sid)
        todo += step_inputs(by_id[sid])
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


def _index_right(conn, index: int, step: dict, rtable: str) -> None:
    """The right side's join keys, indexed, for the joins SQLite would otherwise run as every left row against every right row: an anti or semi join (a lookup in a
    subquery) and a join where empty keys are equal (the COALESCE hides the column from an automatic index). The index goes away with the table."""
    equal = step.get('null_keys') == 'equal'
    if equal or step['how'] in ('anti', 'semi'):
        keys = ', '.join(f"COALESCE({_q(p['right'])}, '')" if equal else _q(p['right']) for p in step['on'])
        conn.execute(f'DROP INDEX IF EXISTS temp.ix_{index}')
        conn.execute(f'CREATE INDEX temp.ix_{index} ON {rtable}({keys})')


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
        raise ValueError(tr(f'步骤 {step["id"]}：这个连接会产生 {expected:,} 行，超过一次最多 {row_cap:,} 行，没有运行。'
                         f'通常是连接的列在两边都有大量重复的值，先换一列或先去重', f'Step {step["id"]}: this join would produce {expected:,} rows, more than the {row_cap:,} allowed at once, so it did not run. '
                         f'Usually the join columns have many repeated values on both sides: use another column or remove duplicates first'))
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


def _repeated(conn, source: dict, output: dict, skip) -> list[str]:
    """The number columns an output keeps as a join repeated them: their sum over the output's rows differs from the sum that counts each source row once (the
    hidden columns of the join name it, `fan`). A figure a later aggregation worked out is not one of them (fan_agg says that); a code column is not a sum."""
    by_name = {c['name']: c for c in source['columns'] if not c.get('hidden')}
    there = {c['name'] for c in source['columns'] if c.get('hidden')}
    found = []
    for c in output['columns']:
        s = by_name.get(c['name'])
        if s is None or not s.get('fan') or not set(s['fan']) <= there or s['type'] not in NUMERIC or s.get('origin') in skip:
            continue
        if _double_counted(conn, source['table'], [], {'fn': 'sum', 'col': s, 'name': c['name']}):
            found.append(c['name'])
    return found


def _union_report(conn, step: dict, sources: list[tuple[str, str, list[dict]]], columns: list[dict]) -> dict:
    """What a union did beyond stacking: {'filled_empty': {column: rows left empty because their input had no such column}, 'same_rows': {'count': distinct rows found
    in more than one input, 'examples': the first EXAMPLES as {column: value}}}. Rows found twice are counted twice by a later sum: the run says so instead."""
    names = [c['name'] for c in columns if c['name'] != step.get('source_column')]
    filled = {}
    for ref, table, cols in sources:
        have = {c['name'] for c in visible(cols)}
        rows = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        for n in names:
            if n not in have:
                filled[n] = filled.get(n, 0) + rows
    shared = ', '.join(_q(n) for n in names)
    distinct = [f'SELECT DISTINCT {", ".join((_q(n) if n in {c["name"] for c in visible(cols)} else "NULL") + " AS " + _q(n) for n in names)} FROM {table}' for _, table, cols in sources]
    repeated = f'SELECT {shared} FROM ({" UNION ALL ".join(distinct)}) GROUP BY {shared} HAVING COUNT(*) > 1'
    count = conn.execute(f'SELECT COUNT(*) FROM ({repeated})').fetchone()[0]
    examples = [dict(zip(names, r)) for r in conn.execute(f'{repeated} LIMIT {EXAMPLES}')] if count else []
    return {'filled_empty': filled, 'same_rows': {'count': count, 'examples': examples}}


def _split_report(conn, table: str, branches: list[dict]) -> dict:
    """Each branch's rows; for a branch with a condition, the rows whose condition was empty (not "false": a field was empty) and the rows that met it but had gone to an
    earlier branch; and the rows that went to no branch (when there is no rest branch, they leave the pipeline here)."""
    out = []
    for b in branches:
        rows = conn.execute(f'SELECT COUNT(*) FROM {b["table"]}').fetchone()[0]
        entry = {'id': b['id'], 'rest': b['rest'], 'rows': rows}
        if not b['rest']:
            marker = _q(b['marker'])
            empty, also = conn.execute(f'SELECT COALESCE(SUM(({b["cond"]}) IS NULL), 0), COALESCE(SUM(({b["cond"]}) AND {marker} >= 0 AND {marker} < {b["index"]}), 0) FROM {table}',
                                       b['params'] + b['params']).fetchone()
            entry.update({'empty_condition': empty, 'also_matched': also})
        out.append(entry)
    rest = any(b['rest'] for b in branches)
    unassigned = 0 if rest else conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {_q(branches[0]["marker"])} = -1').fetchone()[0]
    return {'branches': out, 'unassigned': unassigned}


def _failures(operators: list[dict]) -> dict:
    """What a node lost or could not do, by kind, nonzero only: values that did not convert, expressions with no result, codes with no label, rows a condition
    dropped because a field was empty."""
    out = {}
    for op in operators:
        for key, name in FAILURE_KEYS:
            if op.get(key):
                out[name] = out.get(name, 0) + op[key]
    return out


def prepare_llm(conn, ctx: dict, step: dict, compiled: dict) -> dict:
    """The answers of an LLM step as a table beside its rows (the model's part of a run is `ctx['llm']`, an LlmRun); its report. A run with nothing to do it is refused."""
    if ctx.get('llm') is None:
        raise ValueError(tr(f'步骤 {step["id"]}：这里不能调用模型，管道里的 AI 步骤只在管道页面里运行', f'Step {step["id"]}: the model cannot be called here; AI steps in a pipeline only run on the pipeline page'))
    return ctx['llm'].prepare(conn, step, compiled['llm']['source'], compiled['llm']['source_columns'], compiled['llm']['answers'])


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
    by_id.update({b['id']: {'table': b['table'], 'columns': s['columns']} for s in steps if s['split'] for b in s['split']})   # a branch is read as a table of its own
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
            if step['type'] == 'join':
                _index_right(conn, index, step, by_id[step['right']]['table'])
            report = None
            if compiled['llm']:
                made.append(compiled['llm']['answers'])
                report = prepare_llm(conn, ctx, step, compiled)
            if compiled['sql']:
                made.append(compiled['table'])
                conn.execute(f'DROP TABLE IF EXISTS temp.{compiled["table"]}')
                conn.execute(compiled['sql'], compiled['params'])
            for b in compiled['split'] or []:
                made.append(b['table'])
                conn.execute(f'DROP TABLE IF EXISTS temp.{b["table"]}')
                conn.execute(b['sql'])
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
            inputs = step_inputs(step)
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
            if report is not None:
                node['llm'] = report
                node['failures'] = report['failures']
            if step['type'] == 'output':
                node['output'] = _output_report(conn, compiled['table'], compiled['output'])
                repeated = _repeated(conn, by_id[step['from']], compiled['output'], skip)
                if repeated:   # said only when there is one: an output without stays as it was
                    node['output']['repeated'] = repeated
            if step['type'] == 'union':
                node['union'] = _union_report(conn, step, [(r, by_id[r]['table'], by_id[r]['columns']) for r in step['inputs']], compiled['columns'])
            if compiled['split']:
                node['split'] = _split_report(conn, compiled['table'], compiled['split'])
            nodes.append(node)
            if after:
                after(conn, node, compiled)
    finally:
        for table in made:
            conn.execute(f'DROP TABLE IF EXISTS temp.{table}')
    return {'nodes': nodes, 'row_cap': row_cap}
