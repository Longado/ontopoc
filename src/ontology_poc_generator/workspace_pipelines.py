"""Pipelines on the workspace: a pipeline is one element (pipeline:<name>) with a person's definition (the steps of pipelines.py), a state, a confirmation snapshot
and what it reads (element_dep). It reads datasets (and the views and meanings its steps use), and the datasets it writes read it: element_dep has
input dataset <- pipeline <- output dataset <- the types built on it, which is the chain a stale flag follows.

States are the workspace's: checked (a person saved it and the definition checks ran), confirmed (another builder looked, and did not edit it), needs_look (it was
confirmed and its data moved). Saving a changed definition puts it forward again and sends everything that reads it (the output's types, their views and saved
answers) to needs_look with the cause 定义改了; a new version of an input dataset sends it to needs_look with the cause 数据变了 (pipeline_problems, called by
recheck_dependents). A type built on a pipeline's output cannot be confirmed before the pipeline is (object_types.unconfirmed_producers). The output dataset is not
an element: `outputs` of a pipeline's detail says whether the data in it is stale against the pipeline's definition and its inputs, and why.

A run (run_now) writes the outputs as new datasets or new versions, each recording the run and the input versions it came from, after checking every output
(columns, key unique and not empty); it changes nothing when an output is refused. Preview and the dry run of a confirmation run on a connection that may only read.
Pipelines are a builder's: a viewer sees none. A pipeline may not read a dataset a row rule holds back (it would carry the held-back rows to a dataset anyone may
see), nor one this person may not see; a pipeline that reads one is not shown to them.
"""
from __future__ import annotations

import copy
import json
import time

from ontology_poc_generator.accounts import two_person
from ontology_poc_generator.actor import actor_id_for
from ontology_poc_generator.object_types import (
    MAX_DESCRIPTION, MAX_NAME, PIPELINE_PREFIX, STALE, TYPE_PREFIX, VIEW_PREFIX, TypeRefused, _content, _edit_names, _flag_readers, _state_view, _text, dataset_columns,
    element_row, log_entries, recheck_after_write, unconfirmed_producers, write_confirmation)
from ontology_poc_generator.pipeline_expr import COLUMN_TYPE, FUNCTION_DOCS, compile_expression, error_condition
from ontology_poc_generator.pipeline_funcs import guess_formats, number_text, register
from ontology_poc_generator.pipeline_ops import AGGREGATIONS, CAST_TYPES, CATALOG, aggregation_options, new_context, shift_notices, visible
from ontology_poc_generator.pipelines import (
    HOWS, ROW_CAP, PipelineRunError, check_pipeline, compile_pipeline, dataset_key, needed_steps, run_pipeline, workspace_datasets)
from ontology_poc_generator.row_rules import has_rules
from ontology_poc_generator.type_access import dataset_hidden
from ontology_poc_generator.workspace_store import (
    SelfConfirmation, StaleElement, apply_upload, current_dataset, element_state_writes, log_line, now_text, plan_upload)
from ontology_poc_generator.object_views import view_summary, view_visible

PREVIEW_ROWS = 100
TRIAL_ROWS = 100
TRIAL_SHOWN = 5
TOP_VALUES = 5
MAX_BODY_SPEC = 200_000   # the characters of a definition's JSON


def pipeline_id(name: str) -> str:
    return f'{PIPELINE_PREFIX}{name}'


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _canonical(spec) -> str:
    return json.dumps(spec, ensure_ascii=False, sort_keys=True)


# --- what a pipeline reads ----------------------------------------------------------------------------------------------------------------------------

def _row_ruled(conn, dataset_name: str) -> bool:
    return any(has_rules(conn, element_id) for (element_id,) in conn.execute(
        "SELECT element_id FROM element_dep WHERE depends_on = ? AND element_id LIKE 'objtype:%'", (f'dataset:{dataset_name}',)))


def resolve_inputs(conn, engine, spec, user: dict | None) -> dict:
    """What the inputs of a definition are now: {'datasets' (the engine's: name or name@vN -> table, rows, columns), 'views' (a confirmed view as a temporary table of
    the rows it keeps, on the connection the engine runs on), 'versions' ({name or name@vN or view:<name>: the dataset version read}), 'reads' (what the pipeline
    depends on), 'cleanup' (the temporary tables to drop)}. TypeRefused for an input this person may not use: a dataset they cannot see, one a row rule holds back, a view
    that is not confirmed."""
    steps = spec.get('steps') if isinstance(spec, dict) else None
    ids, views, versions, reads, cleanup = {}, {}, {}, [], []
    for step in steps if isinstance(steps, list) else []:
        if not isinstance(step, dict) or step.get('type') != 'input':
            continue
        if isinstance(step.get('dataset'), str):
            name = step['dataset']
            if dataset_hidden(conn, name, user):
                raise TypeRefused(f'没有叫“{name}”的数据集', 404)
            if _row_ruled(conn, name):
                raise TypeRefused(f'“{name}”的行受行规则限制，不能做管道的输入：管道会把没权限看的行带到别的数据集里', 409)
            pinned = step.get('version')
            found = conn.execute('SELECT id, version FROM dataset WHERE name = ? AND version = ?', (name, pinned)).fetchone() if isinstance(pinned, int) and not isinstance(pinned, bool) \
                else (lambda d: (d['id'], d['version']) if d else None)(current_dataset(conn, name))
            if found is None:
                raise TypeRefused(f'没有叫“{name}”的数据集' + (f'的第 {pinned} 版' if pinned is not None else ''), 404)
            ids[dataset_key(step)] = found[0]
            versions[dataset_key(step)] = found[1]
            reads.append(f'dataset:{name}')
        elif isinstance(step.get('view'), str):
            view = element_row(conn, f'{VIEW_PREFIX}{step["view"]}')
            if view is None or not view_visible(conn, view, user):
                raise TypeRefused(f'没有叫“{step["view"]}”的视图', 404)
            if view['state'] != 'confirmed':
                raise TypeRefused(f'视图“{step["view"]}”还没有确认（{view["state"]}），不能做管道的输入', 409)
            content = _content(view)
            summary = view_summary(conn, content)
            if summary['problems']:
                raise TypeRefused(f'视图“{step["view"]}”现在读不了：{"；".join(summary["problems"])}', 409)
            if _row_ruled(conn, summary['dataset']):
                raise TypeRefused(f'视图“{step["view"]}”的数据集受行规则限制，不能做管道的输入', 409)
            dataset = current_dataset(conn, summary['dataset'])
            table = f'pv_{len(cleanup)}'
            engine.execute(f'DROP TABLE IF EXISTS temp.{table}')
            engine.execute(f'CREATE TEMP TABLE {table} AS SELECT * FROM {_q(dataset["table_name"])} WHERE rowid IN (SELECT value FROM json_each(?))', (json.dumps(summary['positions']),))
            cleanup.append(table)
            cols = dataset_columns(conn, dataset['id'])
            views[step['view']] = {'table': table, 'rows': len(summary['positions']), 'columns': [{'name': n, 'type': c['type']} for n, c in cols.items()], 'source': dataset['name']}
            versions[f'view:{step["view"]}'] = dataset['version']
            reads.append(view['element_id'])
    return {'datasets': workspace_datasets(conn, ids), 'views': views, 'versions': versions, 'reads': reads, 'cleanup': cleanup}


def drop_temporary(engine, resolved: dict) -> None:
    for table in resolved['cleanup']:
        engine.execute(f'DROP TABLE IF EXISTS temp.{table}')


def build_context(conn) -> tuple[dict, dict]:
    """(the context the operators read, {"dataset.column": the id of the element holding its meanings}): meanings that are confirmed, and the columns that are code
    lists in any state (a type says so, or someone wrote meanings for them), which a sum or average refuses."""
    meanings, ids, codes = {}, {}, set()
    for element_id, content, state in conn.execute("SELECT element_id, content_json, state FROM element_state WHERE element_id LIKE 'enum:%' AND content_json IS NOT NULL"):
        c = json.loads(content)
        origin = f'{c["dataset"]}.{c["column"]}'
        codes.add(origin)
        ids[origin] = element_id
        if state == 'confirmed':
            by_label: dict[str, list[str]] = {}
            for e in c['values']:
                if e['label']:
                    by_label.setdefault(e['label'], []).append(e['value'])
            meanings[origin] = by_label
    for content, in conn.execute("SELECT content_json FROM element_state WHERE element_id LIKE 'objtype:%' AND content_json IS NOT NULL"):
        c = json.loads(content)
        codes |= {f'{c["dataset"]}.{p["column"]}' for p in c['properties'] if p['enum']}
    return new_context(meanings, codes), ids


# --- who may see and what is allowed ------------------------------------------------------------------------------------------------------------------

def _datasets_of(spec) -> list[str]:
    return [s['dataset'] for s in (spec.get('steps') or []) if isinstance(s, dict) and s.get('type') == 'input' and isinstance(s.get('dataset'), str)]


def pipeline_visible(conn, row: dict, user: dict | None) -> bool:
    """A pipeline is a builder's, and not shown to a person who may not see a dataset it reads."""
    if user is not None and user['role'] == 'viewer':
        return False
    return not any(dataset_hidden(conn, name, user) for name in _datasets_of(_content(row)['spec']))


def _pipeline_row(conn, name, user: dict | None) -> dict:
    row = element_row(conn, pipeline_id(str(name)))
    if row is None or not pipeline_visible(conn, row, user):
        raise TypeRefused('没有这条管道', 404)
    return row


def producer_of(conn, dataset_name: str) -> str | None:
    """The id of the pipeline that writes this dataset, if one does."""
    found = conn.execute("SELECT depends_on FROM element_dep WHERE element_id = ? AND depends_on LIKE 'pipeline:%'", (f'dataset:{dataset_name}',)).fetchone()
    return found[0] if found else None


def _upstream(conn, dataset_name: str, seen: set[str]) -> set[str]:
    """Every dataset this one is made from, through the pipelines that write it."""
    producer = producer_of(conn, dataset_name)
    if producer is None:
        return seen
    for (depends_on,) in conn.execute("SELECT depends_on FROM element_dep WHERE element_id = ? AND depends_on LIKE 'dataset:%'", (producer,)).fetchall():
        name = depends_on[len('dataset:'):]
        if name not in seen:
            seen.add(name)
            _upstream(conn, name, seen)
    return seen


def _check_outputs(conn, spec: dict, own: str, user: dict | None) -> None:
    """Each output is a dataset that is new, or that this pipeline already writes, or that a person says (mode "new_version") it is to take over; never one another
    pipeline writes, one a person may not see, or one this pipeline reads (a loop)."""
    reads = set(_datasets_of(spec))
    for step in spec['steps']:
        if step['type'] != 'output':
            continue
        name, mode = step['name'], step.get('mode')
        if mode not in (None, 'new', 'new_version'):
            raise TypeRefused(f'输出“{name}”的 mode 只能是 new（新数据集）或 new_version（接管已有的数据集写新版本）')
        if dataset_hidden(conn, name, user):
            raise TypeRefused(f'没有叫“{name}”的数据集可以写入，也不能用这个名字新建', 409)
        producer = producer_of(conn, name)
        if producer not in (None, own):
            raise TypeRefused(f'数据集“{name}”已经是管道“{_content(element_row(conn, producer))["name"]}”的输出，一个数据集只能有一条管道写', 409)
        if current_dataset(conn, name) is not None and producer is None and mode != 'new_version':
            raise TypeRefused(f'已经有叫“{name}”的数据集，不是管道写的。要让这条管道接管它、以后写它的新版本，输出里写 "mode": "new_version"；要新建，请换一个名字', 409)
        upstream = reads | {n for r in reads for n in _upstream(conn, r, set())}
        if name in upstream:
            raise TypeRefused(f'输出“{name}”也是这条管道（或它上游的管道）要读的数据，会绕成一圈', 409)


# --- the definition a person writes -------------------------------------------------------------------------------------------------------------------

def check_definition(conn, engine, payload: dict, user: dict | None, name: str | None = None, own: str | None = None, outputs_free: bool = True) -> dict:
    """{'content' (name, description, spec), 'reads', 'outputs', 'versions', 'ctx', 'resolved'} for a pipeline as a person wrote it: its inputs may be used, every step
    and operator checks against the columns it reads (names and types), the outputs are free to write (unless `outputs_free` is off: a preview of a draft does not write).
    TypeRefused says what is wrong. The caller drops the temporary tables (drop_temporary) when done."""
    name = _text(payload.get('name') if name is None else name, '管道的名字', MAX_NAME)
    if ':' in name or '/' in name or '?' in name or '#' in name or name == 'options':
        raise TypeRefused('管道的名字不能有冒号、斜杠、问号、井号，也不能叫 options')
    description = _text(payload.get('description') or '', '说明', MAX_DESCRIPTION, required=False)
    spec = payload.get('spec')
    if not isinstance(spec, dict) or len(_canonical(spec)) > MAX_BODY_SPEC:
        raise TypeRefused('管道要写成 {"steps": […]}，不能太大')
    resolved = resolve_inputs(conn, engine, spec, user)
    try:
        ctx, meaning_ids = build_context(conn)
        checked = check_pipeline(spec, resolved['datasets'], resolved['views'], ctx)
        if outputs_free:
            _check_outputs(conn, checked, own or pipeline_id(name), user)
    except (ValueError, TypeRefused) as exc:
        drop_temporary(engine, resolved)
        if isinstance(exc, TypeRefused):
            raise
        raise TypeRefused(str(exc)) from None
    reads = [*dict.fromkeys(resolved['reads']), *(meaning_ids[o] for o in sorted(ctx['used']) if o in meaning_ids)]
    outputs = [s['name'] for s in checked['steps'] if s['type'] == 'output']
    return {'content': {'name': name, 'description': description, 'spec': checked}, 'reads': reads, 'outputs': outputs, 'versions': resolved['versions'], 'ctx': ctx, 'resolved': resolved}


def _write(conn, change: tuple, reads: list[str], outputs: list[str], version_row: tuple | None, versions: dict | None = None, after=None) -> None:
    """The element, what it reads, the datasets it writes and the definition version, all or nothing (and `after(conn)` in the same transaction)."""
    element_id = change[0]
    try:
        with element_state_writes(conn, [change], versions):
            conn.execute('DELETE FROM element_dep WHERE element_id = ?', (element_id,))
            conn.executemany('INSERT OR IGNORE INTO element_dep(element_id, depends_on) VALUES (?, ?)', [(element_id, r) for r in reads])
            conn.execute("DELETE FROM element_dep WHERE depends_on = ? AND element_id LIKE 'dataset:%'", (element_id,))
            conn.executemany('INSERT OR IGNORE INTO element_dep(element_id, depends_on) VALUES (?, ?)', [(f'dataset:{o}', element_id) for o in outputs])
            if version_row:
                conn.execute('INSERT INTO pipeline_version(pipeline_id, version, definition_json, saved_by, saved_by_user_id, saved_at) VALUES (?, ?, ?, ?, ?, ?)', version_row)
            if after:
                after(conn)
    except StaleElement:
        raise TypeRefused(STALE, 409) from None


def _version_row(element_id: str, version: int, content: dict, who: str | None) -> tuple:
    return (element_id, version, json.dumps({'spec': content['spec'], 'description': content['description']}, ensure_ascii=False, sort_keys=True), who, actor_id_for(who), now_text())


def _change(content: dict, version: int, versions: dict, who: str | None) -> tuple:
    anchors = {'definition_version': version, 'inputs': versions}
    return (pipeline_id(content['name']), 'checked', f'pipeline:{content["name"]}@d{version}', who, {**content, 'definition_version': version}, anchors, who)


def create_pipeline(conn, payload: dict, who: str | None, user: dict | None, engine=None) -> dict:
    """Put a pipeline forward (state checked, the person who wrote it its proposer): {'id', 'definition_version'}."""
    engine = engine or conn
    found = check_definition(conn, engine, payload, user)
    try:
        element_id = pipeline_id(found['content']['name'])
        if element_row(conn, element_id):
            raise TypeRefused(f'已经有叫“{found["content"]["name"]}”的管道', 409)
        for (other,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'pipeline:%'"):
            if other.casefold() == element_id.casefold():
                raise TypeRefused(f'已经有叫“{other[len(PIPELINE_PREFIX):]}”的管道（名字不分大小写）', 409)
        _write(conn, _change(found['content'], 1, found['versions'], who), found['reads'], found['outputs'], _version_row(element_id, 1, found['content'], who))
    finally:
        drop_temporary(engine, found['resolved'])
    return {'id': found['content']['name'], 'definition_version': 1}


def update_pipeline(conn, payload: dict, who: str | None, user: dict | None, engine=None) -> dict:
    """{id, version, description?, spec?}: save a changed definition. A changed spec is a new definition version: the pipeline is put forward again as this person's,
    and what read it (the datasets it writes, the types on them, their views, saved answers) goes to needs_look, cause 定义改了. A pipeline that was sent back, or a
    model's draft, is put forward again by saving it. A change of the description alone keeps the state. 409 when the version has moved. The name is the id."""
    engine = engine or conn
    row = _pipeline_row(conn, payload.get('id'), user)
    if payload.get('version') != row['version']:
        raise TypeRefused('这条管道在你打开之后被改了，请刷新后再改', 409)
    old = _content(row)
    found = check_definition(conn, engine, {**payload, 'spec': payload.get('spec', old['spec'])}, user, old['name'], row['element_id'])
    try:
        new, element_id = found['content'], row['element_id']
        changed = _canonical(new['spec']) != _canonical(old['spec'])
        if changed or row['state'] in ('proposed', 'rejected'):
            version = old['definition_version'] + (1 if changed else 0)
            after = (lambda c: _flag_readers(c, element_id, f'管道“{old["name"]}”的定义改了（第 {version} 版）', [], 'definition')) if changed else None
            _write(conn, _change(new, version, found['versions'], who), found['reads'], found['outputs'], _version_row(element_id, version, new, who) if changed else None,
                   {element_id: row['version']}, after)
            return {'id': old['name'], 'state': 'checked', 'definition_version': version, 'changed': changed}
        if new['description'] != old['description']:
            _edit_names(conn, row, {'name': old['name'], 'description': new['description']}, who)
        return {'id': old['name'], 'state': row['state'], 'definition_version': old['definition_version'], 'changed': False}
    finally:
        drop_temporary(engine, found['resolved'])


# --- running: preview, review, run -------------------------------------------------------------------------------------------------------------------

def _execute(engine, spec: dict, resolved: dict, ctx: dict, upto=None, after=None) -> dict:
    return run_pipeline(engine, spec, resolved['datasets'], resolved['views'], ctx['codes'], ROW_CAP, ctx, upto, after)


def node_stats(conn, table: str, columns: list[dict]) -> list[dict]:
    """Per column of a table: how many are empty, how many distinct values, the smallest and the largest and (for numbers) the mean; for text the length range and
    the commonest values. Over every row (basis full), not a sample."""
    out = []
    for c in visible(columns):
        q = _q(c['name'])
        nulls = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {q} IS NULL OR TRIM(CAST({q} AS TEXT)) = ''").fetchone()[0]
        stat = {'name': c['name'], 'type': c['type'], 'nulls': nulls, 'distinct': conn.execute(f'SELECT COUNT(DISTINCT {q}) FROM {table}').fetchone()[0]}
        if c['type'] in ('integer', 'decimal'):
            low, high, mean = conn.execute(f'SELECT MIN(CAST({q} AS REAL)), MAX(CAST({q} AS REAL)), AVG(CAST({q} AS REAL)) FROM {table}').fetchone()
            stat |= {'min': _plain(low), 'max': _plain(high), 'mean': None if mean is None else round(mean, 4)}
        else:
            low, high = conn.execute(f'SELECT MIN({q}), MAX({q}) FROM {table}').fetchone()
            stat |= {'min': low, 'max': high}
            if c['type'] in ('text', 'month'):
                stat['length'] = list(conn.execute(f'SELECT MIN(LENGTH({q})), MAX(LENGTH({q})) FROM {table}').fetchone())
            stat['top'] = [{'value': v, 'rows': n} for v, n in conn.execute(f'SELECT {q}, COUNT(*) FROM {table} WHERE {q} IS NOT NULL GROUP BY {q} ORDER BY 2 DESC, 1 LIMIT {TOP_VALUES}')]
        out.append(stat)
    return out


def _plain(value):
    return None if value is None else int(value) if float(value).is_integer() else round(float(value), 4)


def _column_info(columns: list[dict], ctx: dict) -> list[dict]:
    """The columns a person sees with their types, the badge (new or replaced) a step gave them, and what each may be used for: its confirmed meanings, the
    aggregations it may have."""
    options = aggregation_options(columns, ctx['codes'])
    return [{**{k: c[k] for k in ('name', 'type', 'badge', 'aggregation', 'origin', 'english_name') if k in c},
             'code': c.get('origin') in ctx['codes'], 'meanings': ctx['meanings'].get(c.get('origin')), 'aggregations': options[c['name']]} for c in visible(columns)]


def preview(conn, engine, payload: dict, user: dict | None) -> dict:
    """{id | spec, node, operator?, rows?}: the first rows of one node, computed from the inputs up to it (with `operator`, only the first operators of a transform node
    up to that one), with the node's report (rows in and out, what each operator affected, the join's fan-out, the output's key), its columns and their statistics over
    all rows (basis full)."""
    engine = engine or conn
    spec, name = _spec_of(conn, payload, user)
    node = payload.get('node')
    if not isinstance(node, str) or node not in {s['id'] for s in spec.get('steps', []) if isinstance(s, dict)}:
        raise TypeRefused('要写预览哪一个步骤（node）')
    spec = {**copy.deepcopy(spec), 'steps': [s for s in copy.deepcopy(spec['steps']) if s.get('id') in needed_steps(spec, [node])]}   # what the node reads and nothing after it: a step further down that is wrong does not stop this one
    if payload.get('operator') is not None:
        step = next(s for s in spec['steps'] if s['id'] == node)
        if step.get('type') != 'transform' or not isinstance(payload['operator'], int) or not 0 <= payload['operator'] < len(step['operators']):
            raise TypeRefused('预览到第几个操作（operator）要写成这个转换步骤里的序号，从 0 数起')
        step['operators'] = step['operators'][:payload['operator'] + 1]
    found = check_definition(conn, engine, {'name': name or 'preview', 'spec': spec}, user, outputs_free=False)
    captured = {}

    def take(c, report, compiled):
        if report['id'] == node:
            limit = min(max(int(payload.get('rows') or PREVIEW_ROWS), 1), PREVIEW_ROWS)
            cols = [c2['name'] for c2 in visible(compiled['columns'])]
            captured['rows'] = [list(r) for r in c.execute(f'SELECT {", ".join(_q(n) for n in cols)} FROM {compiled["table"]} ORDER BY rowid LIMIT {limit}')]
            captured['stats'] = node_stats(c, compiled['table'], compiled['columns'])
            captured['columns'] = _column_info(compiled['columns'], found['ctx'])
    try:
        register(engine)
        result = _execute(engine, found['content']['spec'], found['resolved'], found['ctx'], needed_steps(found['content']['spec'], [node]), take)
    except (ValueError, PipelineRunError) as exc:
        raise TypeRefused(str(exc), 409) from None
    finally:
        drop_temporary(engine, found['resolved'])
    report = next(n for n in result['nodes'] if n['id'] == node)
    if report['type'] == 'output':
        report['output']['status'] = output_status(conn, report['output'], _output_step(found['content']['spec'], node))
    return {'node': {k: v for k, v in report.items() if k not in ('sql', 'column_types')}, 'columns': captured['columns'], 'rows': captured['rows'], 'stats': captured['stats'],
            'basis': 'full', 'inputs': found['versions'], 'limit': PREVIEW_ROWS}


def summary(conn, engine, payload: dict, user: dict | None) -> dict:
    """{id | spec}: every node's report (rows in and out, what each operator did, the join's fan-out, an output's key and status line, its columns with types) from a run
    on the current data with nothing written and no rows returned: what the graph shows on each card. A draft that does not check is refused with the reason (409 or 400)."""
    engine = engine or conn
    spec, name = _spec_of(conn, payload, user)
    found = check_definition(conn, engine, {'name': name or 'preview', 'spec': spec}, user, outputs_free=False)
    try:
        register(engine)
        result = _execute(engine, found['content']['spec'], found['resolved'], found['ctx'])
    except (ValueError, PipelineRunError) as exc:
        raise TypeRefused(str(exc), 409) from None
    finally:
        drop_temporary(engine, found['resolved'])
    nodes = [{k: v for k, v in n.items() if k != 'sql'} for n in result['nodes']]
    for n in nodes:
        if n['type'] == 'output':
            n['output']['status'] = output_status(conn, n['output'], _output_step(found['content']['spec'], n['id']))
    return {'nodes': nodes, 'inputs': found['versions']}


def columns_at(conn, engine, payload: dict, user: dict | None) -> dict:
    """{id | spec, step, operator?}: the columns a transform's operator reads (what the operators before it left), with types, meanings and the aggregations each may have:
    what the operator forms offer to pick from."""
    engine = engine or conn
    found, compiled, _ = _columns_before(conn, engine, payload, user)
    try:
        return {'columns': _column_info(compiled['columns'], found['ctx'])}
    finally:
        drop_temporary(engine, found['resolved'])


def _output_step(spec: dict, node: str) -> dict:
    return next(s for s in spec['steps'] if s['id'] == node)


def _spec_of(conn, payload: dict, user: dict | None) -> tuple[dict, str | None]:
    """(the definition a request is about, the name of the pipeline it belongs to or None): a draft sent as `spec` (an editor's unsaved changes, which may belong to the
    saved pipeline `id`), else the saved pipeline `id`."""
    saved = _pipeline_row(conn, payload['id'], user) if payload.get('id') is not None else None
    if isinstance(payload.get('spec'), dict):
        return payload['spec'], _content(saved)['name'] if saved else None
    if saved is None:
        raise TypeRefused('要写是哪条管道（id），或者一份还没保存的定义（spec）')
    return _content(saved)['spec'], _content(saved)['name']


def output_status(conn, report: dict, step: dict) -> dict:
    """The status line of an output: 匹配 (the columns it must have are all there), 丢列 (and some columns of the step it reads are left out), 错误 (a column the dataset
    it writes to already has is missing, so writing would break what reads it). The columns required are those of the dataset's current version when it exists, else the
    columns chosen. A column is matched by its name."""
    shown = [c['name'] for c in report['columns']]
    existing = current_dataset(conn, step['name'])
    required = [r[0] for r in conn.execute('SELECT name FROM "column" WHERE dataset_id = ? ORDER BY position', (existing['id'],))] if existing else shown
    matched = sum(1 for r in required if r in shown)
    dropped = len(report['dropped'])
    if matched < len(required):
        missing = [r for r in required if r not in shown]
        return {'state': 'error', 'matched': matched, 'required': len(required), 'dropped': dropped, 'missing': missing, 'text': f'错误 ({matched}/{len(required)})：缺 {"、".join(missing)}'}
    if dropped:
        return {'state': 'dropped', 'matched': matched, 'required': len(required), 'dropped': dropped, 'missing': [], 'text': f'丢列 ({matched}/{len(required)}, {dropped} 列丢弃)'}
    return {'state': 'match', 'matched': matched, 'required': len(required), 'dropped': 0, 'missing': [], 'text': f'匹配 ({matched}/{len(required)} 必需列)'}


def _compact(nodes: list[dict]) -> list[dict]:
    """What a run record keeps of each node: the counts, what each operator did, the join's report and the output's key report, not the SQL."""
    return [{k: v for k, v in n.items() if k not in ('sql', 'column_types')} for n in nodes]


def _inputs_now(conn, content: dict) -> dict:
    """The dataset versions the definition would read now: the version a step pins, else the current one."""
    out = {}
    for step in content['spec']['steps']:
        if step['type'] == 'input' and 'dataset' in step:
            current = current_dataset(conn, step['dataset'])
            out[dataset_key(step)] = step['version'] if step.get('version') is not None else current['version'] if current else None
        elif step['type'] == 'input':
            view = element_row(conn, f'{VIEW_PREFIX}{step["view"]}')
            type_row = element_row(conn, f'{TYPE_PREFIX}{_content(view)["type"]}') if view else None
            current = current_dataset(conn, _content(type_row)['dataset']) if type_row else None
            out[f'view:{step["view"]}'] = current['version'] if current else None
    return out


def review(conn, engine, payload: dict, user: dict | None) -> dict:
    """{id}: what a second person reads before confirming: the steps that changed since the last confirmation (ADD / MOD / DEL, with before and after), and the
    statistics of every node's output then (kept with that confirmation) and now (a run on the current data, nothing written)."""
    engine = engine or conn
    row = _pipeline_row(conn, payload.get('id'), user)
    content = _content(row)
    last = _last_confirmation(conn, row['element_id'])
    before_spec = last['content']['spec'] if last else None
    stats_now = _dry_run(conn, engine, row, user)
    return {'id': content['name'], 'definition_version': content['definition_version'], 'compared_with': last['content']['definition_version'] if last else None,
            'changes': diff_specs(before_spec, content['spec']), 'stats_before': last['anchors']['stats'] if last and last['anchors'] else None, 'rows_before': last['anchors'].get('rows') if last and last['anchors'] else None,
            'stats_now': stats_now['stats'],
            'rows_now': stats_now['rows'], 'inputs_now': stats_now['inputs'], 'failures': stats_now['failures']}


def _last_confirmation(conn, element_id: str) -> dict | None:
    """The latest confirmation snapshot: {'content' (the definition confirmed), 'versions' (the dataset versions it was confirmed on), 'anchors' (what was kept with it:
    the statistics of each node's output then)}."""
    found = conn.execute('SELECT content_json, dataset_versions_json, snapshot_json FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 1', (element_id,)).fetchone()
    return None if not found else {'content': json.loads(found[0]), 'versions': json.loads(found[1]), 'anchors': json.loads(found[2]) if found[2] else None}


def diff_specs(old: dict | None, new: dict) -> list[dict]:
    """Per step: ADD, MOD or DEL with the step as it was and as it is."""
    before = {s['id']: s for s in (old or {}).get('steps', [])}
    after = {s['id']: s for s in new['steps']}
    out = [{'id': i, 'change': 'ADD', 'before': None, 'after': s} for i, s in after.items() if i not in before]
    out += [{'id': i, 'change': 'MOD', 'before': before[i], 'after': s} for i, s in after.items() if i in before and _canonical(before[i]) != _canonical(s)]
    out += [{'id': i, 'change': 'DEL', 'before': s, 'after': None} for i, s in before.items() if i not in after]
    return out


def _dry_run(conn, engine, row: dict, user: dict | None) -> dict:
    """The pipeline run on the current data with nothing written: the statistics of each node, rows per node, failures per node and the inputs read. TypeRefused (409) when
    it cannot be run."""
    engine = engine or conn
    content = _content(row)
    resolved = resolve_inputs(conn, engine, content['spec'], user)
    ctx, _ = build_context(conn)
    stats = {}
    try:
        register(engine)
        result = _execute(engine, content['spec'], resolved, ctx, None, lambda c, report, compiled: stats.__setitem__(report['id'], node_stats(c, compiled['table'], compiled['columns'])))
        problems = _output_problems(conn, result['nodes'], content['spec'])
        if problems:
            raise TypeRefused('；'.join(problems), 409)
    except TypeRefused:
        raise
    except (ValueError, PipelineRunError) as exc:
        raise TypeRefused(f'按现在的数据运行不了：{exc}', 409) from None
    finally:
        drop_temporary(engine, resolved)
    return {'stats': stats, 'rows': {n['id']: n.get('rows_out') for n in result['nodes']}, 'inputs': resolved['versions'],
            'failures': {n['id']: n['failures'] for n in result['nodes'] if n.get('failures')}}


def _output_problems(conn, nodes: list[dict], spec: dict) -> list[str]:
    """What stops each output being written: a column the dataset already has is missing, a key that repeats (the keys listed) or is empty, no rows."""
    problems = []
    for n in nodes:
        if n['type'] != 'output' or n.get('skipped'):
            continue
        out, name = n['output'], _output_step(spec, n['id'])['name']
        status = output_status(conn, out, _output_step(spec, n['id']))
        if status['state'] == 'error':
            problems.append(f'输出“{name}”{status["text"]}')
        if out['duplicate_keys']:
            shown = '、'.join(f'{" + ".join(map(str, e["key"]))}（{e["rows"]} 行）' for e in out['duplicate_keys']['examples'][:10])
            problems.append(f'输出“{name}”的主键有 {out["duplicate_keys"]["count"]} 个重复：{shown}' + ('等' if out['duplicate_keys']['count'] > 10 else ''))
        if out['empty_keys']:
            problems.append(f'输出“{name}”有 {out["empty_keys"]} 行的主键是空的')
        if not n['rows_out']:
            problems.append(f'输出“{name}”没有一行，没有写数据集')
    return problems


def _as_text(value, kind: str) -> str | None:
    if value is None:
        return None
    if kind == 'boolean':
        return 'true' if str(value).lower() in ('1', 'true') else 'false'
    return number_text(value) if isinstance(value, (int, float)) else str(value)


def _record(conn, run_id: int, **fields) -> None:
    sets = ', '.join(f'{k} = ?' for k in fields)
    conn.execute(f'UPDATE pipeline_run SET {sets} WHERE id = ?', (*(json.dumps(v, ensure_ascii=False) if k.endswith('_json') else v for k, v in fields.items()), run_id))


def run_now(conn, engine, payload: dict, who: str | None, user: dict | None) -> dict:
    """{id}: run the pipeline now on the current data of its inputs. Every output is checked first (its columns against the dataset it writes to, its key unique and not
    empty, at least a row); if any is refused nothing is written and the run is failed with the reasons. Otherwise each output is a new dataset or a new version, recording the
    run and the input versions, and what reads it is checked again (recheck_after_write). The run is kept either way: status, who, when, how long, rows and failures per
    node, the versions read, what was written. Returns the run (see run_detail)."""
    engine = engine or conn
    row = _pipeline_row(conn, payload.get('id'), user)
    content, element_id = _content(row), row['element_id']
    started = time.monotonic()
    run_id = conn.execute('INSERT INTO pipeline_run(pipeline_id, definition_version, status, who, who_user_id, started_at) VALUES (?, ?, ?, ?, ?, ?)',
                          (element_id, content['definition_version'], 'running', who, actor_id_for(who), now_text())).lastrowid
    resolved = None
    try:
        resolved = resolve_inputs(conn, engine, content['spec'], user)
        ctx, _ = build_context(conn)
        _record(conn, run_id, input_versions_json=resolved['versions'])
        _check_outputs(conn, content['spec'], element_id, user)
        outputs = {}
        feeds = needed_steps(content['spec'], [s['id'] for s in content['spec']['steps'] if s['type'] == 'output'])

        def take(c, report, compiled):
            if report['type'] == 'output':
                cols = compiled['output']['columns']
                outputs[report['id']] = [[_as_text(v, col['type']) for v, col in zip(r, cols)]
                                         for r in c.execute(f'SELECT {", ".join(_q(col["name"]) for col in cols)} FROM {compiled["table"]} ORDER BY rowid')]
        register(engine)
        result = _execute(engine, content['spec'], resolved, ctx, feeds, take)
        problems = _output_problems(conn, result['nodes'], content['spec'])
        if problems:
            raise PipelineRunError('；'.join(problems))
        written = _write_outputs(conn, content, row, run_id, resolved['versions'], result['nodes'], outputs, who)
    except (TypeRefused, ValueError) as exc:   # PipelineRunError is a ValueError
        _record(conn, run_id, status='failed', error=str(exc), finished_at=now_text(), duration_ms=round((time.monotonic() - started) * 1000))
        log_line(conn, who or '未署名', element_id, 'run_failed', after={'run': run_id, 'error': str(exc)})
        return run_detail(conn, content['name'], run_id, user)
    except BaseException as exc:   # something not ours (the database): the run is not left "running"
        _record(conn, run_id, status='failed', error=f'运行出错：{exc}', finished_at=now_text(), duration_ms=round((time.monotonic() - started) * 1000))
        raise
    finally:
        if resolved:
            drop_temporary(engine, resolved)
    failures = {n['id']: n['failures'] for n in result['nodes'] if n.get('failures')}
    _record(conn, run_id, status='success', finished_at=now_text(), duration_ms=round((time.monotonic() - started) * 1000), nodes_json=_compact(result['nodes']),
            failures_json=failures, outputs_json=written)
    log_line(conn, who or '未署名', element_id, 'run', after={'run': run_id, 'outputs': [w['dataset'] for w in written]})
    return run_detail(conn, content['name'], run_id, user)


def _write_outputs(conn, content: dict, row: dict, run_id: int, versions: dict, nodes: list[dict], outputs: dict, who: str | None) -> list[dict]:
    """Each output as a new dataset or a new version, carrying the run, the definition version and the input versions; what reads each is checked again."""
    signer = who or '未署名'
    written = []
    for step in content['spec']['steps']:
        if step['type'] != 'output' or step['id'] not in outputs:
            continue
        columns = next(n for n in nodes if n['id'] == step['id'])['output']['columns']
        records = [dict(zip([c['name'] for c in columns], r)) for r in outputs[step['id']]]
        existing = current_dataset(conn, step['name'])
        plan = plan_upload(conn, step['name'], records, mode='overwrite' if existing else None, rows_in=len(records))
        plan['changes'] = {**plan['changes'], 'pipeline': {'id': content['name'], 'run': run_id, 'definition_version': content['definition_version'], 'inputs': versions}}
        done = apply_upload(conn, plan, signer, origin=f'pipeline:{content["name"]}@run{run_id}')
        error = recheck_after_write(conn, step['name'], signer) if done['created'] else None
        written.append({'dataset': step['name'], 'version': done['dataset']['version'], 'rows': len(records), 'created_version': done['created'], 'mode': plan['mode'],
                        'recheck_error': error})
    return written


# --- confirming ---------------------------------------------------------------------------------------------------------------------------------------

def _editors(conn, element_id: str) -> set[int]:
    """The accounts that saved a definition version since the last confirmation (all of them when it was never confirmed): the one who confirms must not be among them."""
    last = _last_confirmation(conn, element_id)
    since = last['content']['definition_version'] if last else 0
    return {u for (u,) in conn.execute('SELECT saved_by_user_id FROM pipeline_version WHERE pipeline_id = ? AND version > ? AND saved_by_user_id IS NOT NULL', (element_id, since))}


def waiting_on(conn, content: dict) -> list[dict]:
    """What a pipeline stands on that is not confirmed: the views and meanings it reads, and the pipelines whose output it reads."""
    out = []
    for (depends_on,) in conn.execute('SELECT depends_on FROM element_dep WHERE element_id = ? ORDER BY depends_on', (pipeline_id(content['name']),)).fetchall():
        if depends_on.startswith(('objview:', 'enum:')):
            dep = element_row(conn, depends_on)
            if dep is None or dep['state'] != 'confirmed':
                out.append({'id': depends_on, 'name': _content(dep)['name'] if dep and depends_on.startswith('objview:') else depends_on, 'state': dep['state'] if dep else None})
        elif depends_on.startswith('dataset:'):
            out += [{'id': pipeline_id(n), 'name': n, 'state': 'unconfirmed'} for n in unconfirmed_producers(conn, depends_on[len('dataset:'):])]
    return out


def pipeline_state(conn, row: dict, user: dict | None) -> dict:
    """_state_view, and that whoever edited the definition since it was last confirmed cannot confirm it, nor one whose inputs are not confirmed."""
    state = _state_view(conn, row, user)
    editors = _editors(conn, row['element_id']) if two_person(conn)['active'] else set()
    waiting = waiting_on(conn, _content(row))
    names = {i: n for i, n in conn.execute('SELECT id, display_name FROM user')} if editors else {}
    editor_names = {names.get(e, str(e)) for e in editors}
    mine = user is not None and user.get('id') in editors
    return {**state, 'can_confirm': state['can_confirm'] and not mine and not waiting, 'waiting_on': waiting, 'editors': sorted(editor_names),
            'confirmers': [n for n in state['confirmers'] if n not in editor_names] if not waiting else []}


def confirm_pipeline(conn, payload: dict, who: str | None, user: dict | None, engine=None) -> dict:
    """{id, version, seen: {inputs: {dataset: version}}}: confirm what the person looked at. Another builder who did not edit the definition since it was last confirmed
    (SelfConfirmation otherwise while two-person confirmation is active); the version they saw and the input versions they saw (409 when either moved); what the pipeline
    stands on confirmed. The pipeline is run on the current data with nothing written, refused if it cannot be, and the statistics of every node are kept with the
    confirmation: they are what the next person's review is compared with."""
    engine = engine or conn
    row = _pipeline_row(conn, payload.get('id'), user)
    if payload.get('version') != row['version']:
        raise TypeRefused('确认要带上你看到的那一版；它在你看过之后被改了，请刷新后重新看一遍', 409)
    if row['state'] == 'confirmed':
        raise TypeRefused('已经确认过了', 409)
    if row['state'] == 'rejected':
        raise TypeRefused('已经被退回了：要先按退回的理由改，再重新提出', 409)
    content, element_id = _content(row), row['element_id']
    if two_person(conn)['active'] and user is not None and user.get('id') in _editors(conn, element_id):
        raise SelfConfirmation('这条管道的定义你改过，要另一位来确认')
    waiting = waiting_on(conn, content)
    if waiting:
        names = '、'.join(f'“{w["name"]}”' for w in waiting)
        raise TypeRefused(f'管道用到的{names}还没有确认，要先确认它们', 409)
    if not isinstance(payload.get('seen'), dict):
        raise TypeRefused('确认要带上你看到的输入数据版本（seen）')
    now = _inputs_now(conn, content)
    if payload['seen'].get('inputs') != now:
        read = '、'.join(f'{k} 第 {v} 版' for k, v in now.items())
        raise TypeRefused(f'数据在你看过之后变了：现在读的是 {read}，和你看到的不一样，请刷新后重新看一遍', 409)
    dry = _dry_run(conn, engine, row, user)
    anchors = {'definition_version': content['definition_version'], 'inputs': dry['inputs']}
    write_confirmation(conn, element_id, content, f'pipeline:{content["name"]}@d{content["definition_version"]}', who, anchors, dry['inputs'], row['version'],
                       snapshot={'stats': dry['stats'], 'rows': dry['rows'], 'inputs': dry['inputs']})
    return {'state': 'confirmed'}


def pipeline_problems(conn, row: dict) -> list[str]:
    """For a confirmed pipeline, after a dataset moved: what is different now, in words (empty when every input it reads is the version it was confirmed on and the
    definition still checks)."""
    was = (json.loads(row['anchors_json']) if row['anchors_json'] else {}).get('inputs', {})
    problems = []
    for key, version in was.items():
        if key.startswith('view:') or '@v' in key:   # a view moves with its own state; a pinned version does not move
            continue
        now = current_dataset(conn, key)
        if now is None:
            problems.append(f'数据集“{key}”已经不在了')
        elif now['version'] != version:
            problems.append(f'数据变了：{key} 第 {version} 版 → 第 {now["version"]} 版（{now["who"] or "未署名"}上传），管道读的是它')
    if not problems:
        resolved = None
        try:
            resolved = resolve_inputs(conn, conn, _content(row)['spec'], None)
            ctx, _ = build_context(conn)
            check_pipeline(_content(row)['spec'], resolved['datasets'], resolved['views'], ctx)
        except (ValueError, TypeRefused) as exc:
            problems.append(f'按现在的数据，管道过不了检查：{exc}')
        finally:
            if resolved:
                drop_temporary(conn, resolved)
    return problems


# --- what the pages read ------------------------------------------------------------------------------------------------------------------------------

def _run_line(r: tuple) -> dict:
    return {'id': r[0], 'status': r[1], 'who': r[2], 'started_at': r[3], 'finished_at': r[4], 'duration_ms': r[5], 'definition_version': r[6]}


RUN_COLUMNS = 'id, status, who, started_at, finished_at, duration_ms, definition_version'


def output_states(conn, row: dict) -> list[dict]:
    """The datasets the pipeline writes and whether what is in them is stale against it: written by a run of an older definition (定义改了), or from older input
    versions (数据变了), or not written yet. `confirmed` says whether the pipeline that wrote them is."""
    content = _content(row)
    last = conn.execute(f"SELECT id, definition_version, input_versions_json, outputs_json FROM pipeline_run WHERE pipeline_id = ? AND status = 'success' ORDER BY id DESC LIMIT 1",
                        (row['element_id'],)).fetchone()
    now = _inputs_now(conn, content)
    out = []
    for step in content['spec']['steps']:
        if step['type'] != 'output':
            continue
        current = current_dataset(conn, step['name'])
        state = {'dataset': step['name'], 'version': current['version'] if current else None, 'confirmed': row['state'] == 'confirmed', 'built': last is not None and current is not None,
                 'run': last[0] if last else None, 'stale': False, 'cause': None, 'word': None, 'reason': None}
        if last and current:
            was = json.loads(last[2] or '{}')
            if last[1] != content['definition_version']:
                state |= {'stale': True, 'cause': 'definition', 'word': '定义改了', 'reason': f'管道的定义从第 {last[1]} 版改成了第 {content["definition_version"]} 版，这份数据还是旧定义算的'}
            elif any(now.get(k) != v for k, v in was.items() if '@v' not in k):
                moved = next(k for k, v in was.items() if '@v' not in k and now.get(k) != v)
                state |= {'stale': True, 'cause': 'data', 'word': '数据变了', 'reason': f'{moved} 从第 {was[moved]} 版变成了第 {now.get(moved)} 版，这份数据还是旧数据算的'}
        out.append(state)
    return out


def list_pipelines(conn, user: dict | None) -> list[dict]:
    out = []
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'pipeline:%' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        if not pipeline_visible(conn, row, user):
            continue
        content = _content(row)
        last = conn.execute(f'SELECT {RUN_COLUMNS} FROM pipeline_run WHERE pipeline_id = ? ORDER BY id DESC LIMIT 1', (element_id,)).fetchone()
        first = conn.execute('SELECT saved_by FROM pipeline_version WHERE pipeline_id = ? ORDER BY version LIMIT 1', (element_id,)).fetchone()
        out.append({'id': content['name'], 'name': content['name'], 'description': content['description'], 'definition_version': content['definition_version'],
                    'outputs': output_states(conn, row), 'last_run': _run_line(last) if last else None, 'created_by': first[0] if first else None, **pipeline_state(conn, row, user)})
    return out


def pipeline_detail(conn, name: str, user: dict | None) -> dict:
    row = _pipeline_row(conn, name, user)
    content = _content(row)
    ctx, _ = build_context(conn)
    versions = [{'version': v, 'saved_by': by, 'saved_at': at} for v, by, at in conn.execute(
        'SELECT version, saved_by, saved_at FROM pipeline_version WHERE pipeline_id = ? ORDER BY version DESC', (row['element_id'],))]
    last = _last_confirmation(conn, row['element_id'])
    return {'id': content['name'], 'name': content['name'], 'description': content['description'], 'spec': content['spec'], 'definition_version': content['definition_version'],
            'versions': versions, 'outputs': output_states(conn, row), 'inputs_now': _inputs_now(conn, content), 'changes_since_confirmed': diff_specs(last['content']['spec'] if last else None, content['spec']),
            'confirmed_definition_version': last['content']['definition_version'] if last else None, **pipeline_state(conn, row, user)}


def pipeline_versions(conn, name: str, user: dict | None, frm=None, to=None) -> dict:
    """The definition versions kept (who saved each, when), and with `frm` and `to` the ADD / MOD / DEL of the steps between two of them."""
    row = _pipeline_row(conn, name, user)
    kept = {v: (json.loads(d), by, at) for v, d, by, at in conn.execute('SELECT version, definition_json, saved_by, saved_at FROM pipeline_version WHERE pipeline_id = ?', (row['element_id'],))}
    out = {'versions': [{'version': v, 'saved_by': kept[v][1], 'saved_at': kept[v][2], 'steps': len(kept[v][0]['spec']['steps'])} for v in sorted(kept, reverse=True)]}
    if frm is not None and to is not None:
        if frm not in kept or to not in kept:
            raise TypeRefused('没有这个定义版本', 404)
        out['changes'] = diff_specs(kept[frm][0]['spec'], kept[to][0]['spec'])
        out['spec'] = kept[to][0]['spec']
    return out


def run_list(conn, name: str, user: dict | None) -> list[dict]:
    row = _pipeline_row(conn, name, user)
    return [_run_line(r) for r in conn.execute(f'SELECT {RUN_COLUMNS} FROM pipeline_run WHERE pipeline_id = ? ORDER BY id DESC', (row['element_id'],))]


def run_detail(conn, name: str, run_id: int, user: dict | None) -> dict:
    """One run: status, who, when, duration, the versions it read, rows and what each operator did per node, failures per node, what it wrote (the new versions) and, for
    a failed one, why."""
    row = _pipeline_row(conn, name, user)
    found = conn.execute(f'SELECT {RUN_COLUMNS}, input_versions_json, nodes_json, failures_json, outputs_json, error FROM pipeline_run WHERE id = ? AND pipeline_id = ?',
                         (run_id, row['element_id'])).fetchone()
    if found is None:
        raise TypeRefused('没有这次运行', 404)
    loads = lambda text: json.loads(text) if text else None
    return {**_run_line(found), 'input_versions': loads(found[7]), 'nodes': loads(found[8]) or [], 'failures': loads(found[9]) or {}, 'outputs': loads(found[10]) or [], 'error': found[11]}


def pipeline_log(conn, name: str, user: dict | None) -> list[dict]:
    return log_entries(conn, [_pipeline_row(conn, name, user)['element_id']], user)


# --- the expression editor, the operator picker ---------------------------------------------------------------------------------------------------------

def options() -> dict:
    """What the editors list: the operators by category, the functions by group (a click inserts the template), the aggregations, the join kinds, the types a column can be converted to."""
    groups: dict[str, list] = {}
    for group, name, template, what in FUNCTION_DOCS:
        groups.setdefault(group, []).append({'name': name, 'template': template, 'text': what})
    return {'operators': [{'op': o, 'name': n, 'category': c, 'text': t} for o, n, c, t in CATALOG], 'functions': [{'group': g, 'functions': f} for g, f in groups.items()],
            'aggregations': [{'fn': k, 'name': v} for k, v in AGGREGATIONS.items()], 'joins': list(HOWS), 'cast_types': [{'to': k, 'name': v} for k, v in CAST_TYPES.items()]}


def _columns_before(conn, engine, payload: dict, user: dict | None):
    """(spec up to the operator, the columns the expression reads, the step id): the columns a transform's operator sees, i.e. after the operators before it. `step` is the
    transform and `operator` its place (default: after all of them); a draft in `spec` or a saved pipeline in `id`."""
    spec, name = _spec_of(conn, payload, user)
    step_id = payload.get('step')
    steps = spec.get('steps') if isinstance(spec.get('steps'), list) else []
    step = next((s for s in steps if isinstance(s, dict) and s.get('id') == step_id and s.get('type') == 'transform'), None)
    if step is None:
        raise TypeRefused('要写表达式在哪个转换步骤里（step）')
    spec = {**copy.deepcopy(spec), 'steps': [s for s in copy.deepcopy(steps) if s.get('id') in needed_steps(spec, [step_id])]}
    at = payload.get('operator')
    next(s for s in spec['steps'] if s['id'] == step_id)['operators'] = step['operators'][:at] if isinstance(at, int) and not isinstance(at, bool) and at >= 0 else step['operators']
    found = check_definition(conn, engine, {'name': name or 'preview', 'spec': spec}, user, outputs_free=False)
    compiled = {s['id']: s for s in compile_pipeline(found['content']['spec'], found['resolved']['datasets'], found['resolved']['views'], found['ctx'])}
    return found, compiled[step_id], step_id


def check_expression(conn, engine, payload: dict, user: dict | None) -> dict:
    """{id | spec, step, operator?, expression, type?}: 校验 an expression against the columns its operator reads, without running anything: {'ok', 'errors', 'type',
    'fields'}. A field that does not exist or a type that does not fit is named."""
    engine = engine or conn
    found, compiled, _ = _columns_before(conn, engine, payload, user)
    try:
        columns = [{'name': c['name'], 'type': c['type']} for c in visible(compiled['columns'])]
        wanted = payload.get('type')
        result = compile_expression(payload.get('expression'), columns, None if wanted is None else {'decimal': 'number'}.get(wanted, wanted))
        return {'ok': result['ok'], 'errors': result['errors'], 'type': result['type'], 'column_type': COLUMN_TYPE.get(result['type']), 'fields': result['fields'],
                'columns': [{'name': c['name'], 'type': c['type']} for c in columns]}
    finally:
        drop_temporary(engine, found['resolved'])


def trial_expression(conn, engine, payload: dict, user: dict | None) -> dict:
    """{id | spec, step, operator?, expression, rows?}: 试算 on the first rows (default 100) of what the operator reads: the values for the first 5 with the fields they came
    from, and how many of the rows gave no result although their fields had values. Labelled 样本: it is the first rows, not the whole table. A date made from a date is set against it
    (the notices of pipeline_ops.calc)."""
    engine = engine or conn
    found, compiled, step_id = _columns_before(conn, engine, payload, user)
    try:
        columns = [{'name': c['name'], 'type': c['type']} for c in visible(compiled['columns'])]
        result = compile_expression(payload.get('expression'), columns)
        if not result['ok']:
            return {'ok': False, 'errors': result['errors'], 'basis': '样本'}
        sample = min(max(int(payload.get('rows') or TRIAL_ROWS), 1), 1000)
        out = {}

        def take(c, report, comp):
            if report['id'] != step_id:
                return
            table = comp['table']
            fields = result['fields']
            shown = f'SELECT {"".join(_q(f) + ", " for f in fields)}{result["sql"]} FROM (SELECT * FROM {table} ORDER BY rowid LIMIT {TRIAL_SHOWN})'
            out['rows'] = [{'fields': dict(zip(fields, r[:-1])), 'value': r[-1]} for r in c.execute(shown, result['params'])]
            failing, params = error_condition(result['sql'], result['params'], fields)
            counted = c.execute(f'SELECT COUNT(*), COALESCE(SUM({failing}), 0) FROM (SELECT * FROM {table} ORDER BY rowid LIMIT {sample})', params).fetchone()
            out['rows_tried'], out['errors'] = counted
            if result['type'] in ('date', 'datetime'):
                by_name = {col['name']: col for col in columns}
                out['notices'] = shift_notices(c, f'(SELECT * FROM {table} ORDER BY rowid LIMIT {sample})', result['sql'], result['params'],
                                                [by_name[f] for f in fields if by_name[f]['type'] in ('date', 'datetime')], result['truncates'])
        register(engine)
        _execute(engine, found['content']['spec'], found['resolved'], found['ctx'], needed_steps(found['content']['spec'], [step_id]), take)
        return {'ok': True, 'type': result['type'], 'errors': out['errors'], 'rows': out['rows'], 'rows_tried': out['rows_tried'], 'notices': out.get('notices', []), 'basis': '样本'}
    except (ValueError, PipelineRunError) as exc:
        raise TypeRefused(str(exc), 409) from None
    finally:
        drop_temporary(engine, found['resolved'])


def format_guess(payload: dict) -> dict:
    """{examples: [text]}: how many of the examples each known date format reads, best first."""
    examples = payload.get('examples')
    if not isinstance(examples, list) or not examples or len(examples) > 200 or not all(isinstance(e, str) for e in examples):
        raise TypeRefused('要贴几个日期的样例（examples），最多 200 个')
    return {'formats': guess_formats(examples)[:6]}
