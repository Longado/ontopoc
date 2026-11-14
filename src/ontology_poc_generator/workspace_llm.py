"""What the pipeline pages ask of an LLM step: where it stands (the answers kept, what a run would call, the sample review), 试跑 on typed values, chosen rows or a random
sample, the labels of the sample review and the count against them, and clearing the kept answers. Reading the state never calls the model; 试跑 and the review rerun do.
Every request goes through the same checks as a preview: a person kept from an input of the pipeline gets no answer here either.
"""
from __future__ import annotations

import copy

from ontology_poc_generator.object_types import TypeRefused
from ontology_poc_generator.pipeline_funcs import register
from ontology_poc_generator.pipeline_llm import (
    LlmError, LlmService, cache_clear, cache_counts, compile_prompt, contract_of, effective, read_rows, row_hash)
from ontology_poc_generator.pipeline_llm_review import SAMPLE_ROWS, draw, labels_of, remove_label, review_state, run_review, run_rows, save_labels
from ontology_poc_generator.pipeline_ops import visible
from ontology_poc_generator.pipelines import PREVIEW_SECONDS, PipelineRunError, compile_pipeline, deadline, needed_steps
from ontology_poc_generator.workspace_pipelines import _execute, _pipeline_row, _spec_of, check_definition, drop_temporary, llm_run, pipeline_id
from ontology_poc_generator.workspace_store import log_line

MAX_TRIAL_ROWS = 100
EXPECTED_TOKENS_OUT = 80   # what an answer is reckoned to cost to write, for the estimate: a basis and a short sentence


def _step(spec: dict, step_id) -> dict:
    found = next((s for s in spec.get('steps', []) if isinstance(s, dict) and s.get('id') == step_id and s.get('type') == 'llm'), None)
    if found is None:
        raise TypeRefused('要写是哪个 AI 步骤（step）')
    return found


def _checked(conn, engine, payload: dict, user: dict | None):
    """(the definition as checked up to the step, the step, what it asks, the names it may insert, the pipeline's name or None): the definition is cut down to the step and what it
    reads, so a later step that is wrong does not stop this one."""
    spec, name = _spec_of(conn, payload, user)
    step = _step(spec, payload.get('step'))
    cut = {**copy.deepcopy(spec), 'steps': [s for s in copy.deepcopy(spec['steps']) if s.get('id') in needed_steps(spec, [step['id']])]}
    found = check_definition(conn, engine, {'name': name or 'preview', 'spec': cut}, user, outputs_free=False)
    try:
        compiled = {s['id']: s for s in compile_pipeline(found['content']['spec'], found['resolved']['datasets'], found['resolved']['views'], found['ctx'])}
        step = _step(found['content']['spec'], step['id'])
        names = [c['name'] for c in visible(compiled[step['from']]['columns'])]
        return found, step, effective(step), names, name
    except BaseException:
        drop_temporary(engine, found['resolved'])
        raise


def _rows(engine, found: dict, step: dict, names: list[str]) -> tuple[list[str], list[tuple[int, dict]]]:
    """(the columns the prompt uses, the rows of what the step reads in order): computed on the current data, nothing written."""
    _, fields = compile_prompt(effective(step)['prompt'], names)
    taken = {}

    def take(c, report, compiled):
        if report['id'] == step['from']:
            taken['rows'] = read_rows(c, compiled['table'], fields)
    try:
        register(engine)
        with deadline(engine, PREVIEW_SECONDS):
            _execute(engine, found['content']['spec'], found['resolved'], found['ctx'], needed_steps(found['content']['spec'], [step['from']]), take)
    except (ValueError, PipelineRunError) as exc:
        raise TypeRefused(str(exc), 409) from None
    return fields, taken['rows']


def _estimate(report: dict, service: LlmService | None) -> dict:
    """What the calls still to be made would take: how many, about how many characters go in (one token a character, which is on the high side for Chinese), and the
    cost when the service knows its prices; nothing is claimed about money when it does not."""
    calls, chars = report['to_call'], report['chars_in']
    prices = service is not None and service.price_in is not None and service.price_out is not None
    return {'calls': calls, 'chars_in': chars, 'cost': round((chars * service.price_in + calls * EXPECTED_TOKENS_OUT * service.price_out) / 1_000_000, 4) if prices else None}


def state(conn, engine, payload: dict, user: dict | None, llm: LlmService | None = None) -> dict:
    """{id | spec, step}: where the step stands on the current data: the report of a run that only reads what is kept (rows, skipped, answered from the kept answers, still to call,
    the estimate), the kept answers, whether a prompt, model or output change has made them stale, the sample review and its labels."""
    found, step, eff, names, name = _checked(conn, engine, payload, user)
    scope = pipeline_id(name) if name else ''
    try:
        run = llm_run(conn, llm, name, 'cache')
        _, contract, model = run.contract(step)
        try:
            with deadline(engine, PREVIEW_SECONDS):
                register(engine)
                result = _execute(engine, found['content']['spec'], found['resolved'], found['ctx'], needed_steps(found['content']['spec'], [step['id']]), None, run)
        except (ValueError, PipelineRunError) as exc:
            raise TypeRefused(str(exc), 409) from None
    finally:
        drop_temporary(engine, found['resolved'])
    report = next(n for n in result['nodes'] if n['id'] == step['id'])['llm']
    kept = cache_counts(conn, scope, step['id'], contract)
    why = [*([f'记的模型是 {step["model"]}，现在用的是 {model}'] if model != step.get('model') else []),
           *([f'提示、模型或输出改过：以前记下的 {kept["stale"]} 条答案不再用'] if kept['stale'] else [])]
    return {'step': step['id'], 'name': step['name'], 'template': eff['template'], 'kind': eff['kind'], 'choices': eff['choices'], 'fields': eff['fields'], 'prompt': eff['prompt'],
            'columns': [c['name'] for c in eff['columns']], 'model_now': model, 'model_node': step.get('model'), 'contract': contract, 'report': report, 'cache': kept,
            'recompute': {'rows': report['to_call'], 'why': why} if why else None, 'estimate': _estimate(report, llm), 'review': review_state(conn, scope, step, model),
            'labels': labels_of(conn, scope, step['id']) if scope else [], 'basis': '全部行'}


def trial(conn, engine, payload: dict, user: dict | None, llm: LlmService | None = None) -> dict:
    """{id | spec, step, mode: values | rows | sample, values?, rows?, n?, seed?, exclude_labelled?}: the step tried on typed values (the fields of the prompt), on chosen rows of what
    it reads (their numbers, from 0), or on a random sample (n, default 20): for each the prompt sent, the raw answer and the parsed value. This calls the model, and keeps the
    answers that are answers. A sample is labelled 样本; with exclude_labelled it leaves out the rows that already have a label."""
    found, step, eff, names, name = _checked(conn, engine, payload, user)
    scope = pipeline_id(name) if name else ''
    try:
        fields, rows = _rows(engine, found, step, names) if payload.get('mode') != 'values' else (compile_prompt(eff['prompt'], names)[1], [])
    finally:
        drop_temporary(engine, found['resolved'])
    mode = payload.get('mode')
    if mode == 'values':
        values = payload.get('values')
        if not isinstance(values, dict) or set(values) - set(fields) or not all(v is None or isinstance(v, str) for v in values.values()):
            raise TypeRefused(f'要填提示里用到的列的值：{"、".join(fields)}')
        chosen, basis = [(0, {f: values.get(f) for f in fields})], '输入的值'
    elif mode == 'rows':
        wanted = payload.get('rows')
        if not isinstance(wanted, list) or not 1 <= len(wanted) <= MAX_TRIAL_ROWS or not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(rows) for i in wanted):
            raise TypeRefused(f'要选 1 到 {MAX_TRIAL_ROWS} 行，行号从 0 数起，不超过这一步的行数 {len(rows)}')
        chosen, basis = [(i, rows[i][1]) for i in dict.fromkeys(wanted)], '选的行'
    elif mode == 'sample':
        n = payload.get('n', SAMPLE_ROWS)
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= MAX_TRIAL_ROWS:
            raise TypeRefused(f'样本要 1 到 {MAX_TRIAL_ROWS} 行')
        skip = {l['row_hash'] for l in labels_of(conn, scope, step['id'])} if payload.get('exclude_labelled') and scope else set()
        chosen, basis = draw(rows, fields, n, payload.get('seed'), skip), '样本'
    else:
        raise TypeRefused('试跑的方式（mode）只有 values、rows、sample')
    try:
        done = run_rows(conn, llm or LlmService(), scope, step, names, chosen)
    except LlmError as exc:
        raise TypeRefused(str(exc), 409) from None
    return {'trials': [{**d, 'row_hash': row_hash(d['fields'], fields)} for d in done], 'fields': fields, 'columns': [c['name'] for c in eff['columns']], 'basis': basis,
            'rows_in_input': len(rows) if mode != 'values' else None, 'model': (llm.model if llm else None) or step.get('model')}


def _saved(conn, payload: dict, user: dict | None) -> tuple[dict, str]:
    row = _pipeline_row(conn, payload.get('id'), user)
    return row, row['element_id']


def label(conn, engine, payload: dict, who: str | None, user: dict | None) -> dict:
    """{id, step, labels: [{fields, expected}], remove?: [row hash]}: keep the answers a person expects for rows of a saved pipeline's step (the pipeline must be saved: the
    labels belong to the node)."""
    _, scope = _saved(conn, payload, user)
    found, step, eff, names, _ = _checked(conn, engine, payload, user)
    drop_temporary(engine, found['resolved'])
    try:
        for gone in payload.get('remove') or []:
            remove_label(conn, scope, step['id'], gone)
        saved = save_labels(conn, scope, step, names, payload['labels'], who, user['id'] if user else None) if payload.get('labels') else 0
    except LlmError as exc:
        raise TypeRefused(str(exc)) from None
    log_line(conn, who or '未署名', scope, 'llm_labels', after={'step': step['id'], 'saved': saved})
    return {'saved': saved, 'review': review_state(conn, scope, step, None), 'labels': labels_of(conn, scope, step['id'])}


def review_rerun(conn, engine, payload: dict, who: str | None, user: dict | None, llm: LlmService | None = None) -> dict:
    """{id, step}: run the labelled rows through the step as it is now (this calls the model for the rows it has no answer for) and keep the count against what was expected."""
    _, scope = _saved(conn, payload, user)
    found, step, eff, names, _ = _checked(conn, engine, payload, user)
    drop_temporary(engine, found['resolved'])
    if eff['template'] == 'summary':
        raise TypeRefused('概括没有标准答案，不做样本审核')
    try:
        result = run_review(conn, llm or LlmService(), scope, step, names, who, user['id'] if user else None)
    except LlmError as exc:
        raise TypeRefused(str(exc), 409) from None
    log_line(conn, who or '未署名', scope, 'llm_review', after={'step': step['id'], 'matched': result['matched'], 'total': result['total'], 'passed': result['passed']})
    return {**result, 'review': review_state(conn, scope, step, llm.model if llm else None)}


def clear_cache(conn, engine, payload: dict, who: str | None, user: dict | None) -> dict:
    """{id, step}: forget every answer this step has kept; the next run asks the model again for every row."""
    _, scope = _saved(conn, payload, user)
    found, step, _, _, _ = _checked(conn, engine, payload, user)
    drop_temporary(engine, found['resolved'])
    removed = cache_clear(conn, scope, step['id'])
    log_line(conn, who or '未署名', scope, 'llm_cache_cleared', after={'step': step['id'], 'answers': removed})
    return {'cleared': removed}
