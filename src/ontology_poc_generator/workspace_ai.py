"""What the editor asks of the assistant (pipeline_assist): 用一句话描述 a filter or a calculated column, an AI 编排 draft of steps over selected nodes, and 解释 of selected steps.
Each is a draft: nothing is saved, nothing is added to the pipeline; the person applies it. Every answer says what the model was shown, and is checked by our code before it is
shown (columns, operators and functions exist, a dry run on the current data gives its row counts). The same access rules as a preview apply: someone kept from an input gets nothing.
"""
from __future__ import annotations

import copy

from ontology_poc_generator.assistant_checks import plan_assumptions, plan_self_check
from ontology_poc_generator.lang import tr
from ontology_poc_generator.object_types import TypeRefused, element_row
from ontology_poc_generator.pipeline_assist import (
    MAX_DRAFT_STEPS, ask_plan, column_facts, disclosure, explain, parse_condition, parse_expression, settle_plan, values_seen)
from ontology_poc_generator.pipeline_expr import FUNCTION_DOCS, compile_expression
from ontology_poc_generator.pipeline_funcs import register
from ontology_poc_generator.pipeline_llm import LlmService
from ontology_poc_generator.pipeline_ops import OpError, compile_op, visible
from ontology_poc_generator.pipelines import PREVIEW_SECONDS, PipelineRunError, compile_pipeline, deadline, needed_steps
from ontology_poc_generator.workspace_pipelines import (
    _columns_before, _execute, _spec_of, build_context, check_definition, drop_temporary, llm_run)

FUNCTIONS = [name for _, name, _, _ in FUNCTION_DOCS]


def _gateway(llm: LlmService | None):
    if llm is None or llm.gateway is None:
        raise TypeRefused(tr('本机服务没有模型凭据，AI 助手用不了', 'This server has no model credentials, so the AI assistant is not available'), 409)
    return llm.gateway


def _confirmed_by(conn, ctx: dict, meaning_ids: dict, columns: list[dict]) -> dict:
    """{column name: who confirmed its meanings} for the columns whose meanings are confirmed."""
    out = {}
    for c in visible(columns):
        element = meaning_ids.get(c.get('origin')) if c.get('origin') in ctx['meanings'] else None
        row = element_row(conn, element) if element else None
        if row and row.get('confirmed_by'):
            out[c['name']] = row['confirmed_by']
    return out


def _run_to(engine, found: dict, targets, take, llm_part=None):
    """Runs what `targets` read on the current data with nothing written, calling `take(conn, report, compiled)` for each step; TypeRefused (409) when it cannot be run."""
    try:
        register(engine)
        with deadline(engine, PREVIEW_SECONDS):
            return _execute(engine, found['content']['spec'], found['resolved'], found['ctx'], needed_steps(found['content']['spec'], targets), take, llm_part)
    except (ValueError, PipelineRunError) as exc:
        raise TypeRefused(str(exc), 409) from None


def _answers(payload: dict) -> dict:
    raw = payload.get('answers') or {}
    if not isinstance(raw, dict) or not all(isinstance(k, str) and isinstance(v, list) and all(isinstance(x, (str, int, float)) for x in v) for k, v in raw.items()):
        raise TypeRefused(tr('答案要写成 {问题编号: [值…]}', 'Answers must be written as {question id: [values…]}'))
    return raw


def _sentence(payload: dict) -> str:
    text = payload.get('text')
    if not isinstance(text, str) or not text.strip() or len(text) > 500:
        raise TypeRefused(tr('要用一句话说清楚，最多 500 个字（text）', 'Say it in one sentence, at most 500 characters (text)'))
    return text.strip()


def _settled(settle, raw):
    """`settle()`; a `raw` the client sent back that is not the shape the model's answer had (the code reads it as that) is refused in words, not left to fail."""
    try:
        return settle()
    except (TypeError, AttributeError, KeyError) as exc:
        if raw is None:
            raise   # the model's own answer was checked as it came; a failure here is ours
        raise TypeRefused(tr('raw 要写成上一次返回的 raw，原样带回来；这一份读不了，请重新问一次', 'raw must be the raw from the last reply, sent back unchanged. This one cannot be read, so ask again')) from exc


def _raw(payload: dict):
    raw = payload.get('raw')
    if raw is not None and not isinstance(raw, dict):
        raise TypeRefused(tr('raw 要写成上一次返回的 raw', 'raw must be the raw from the last reply'))
    return raw


def parse(conn, engine, payload: dict, user: dict | None, llm: LlmService | None = None) -> dict:
    """{id | spec, step, operator?, kind: filter | calc, text, raw?, answers?}: a sentence written as the conditions of a filter, or as the name and expression of a calculated column, for
    the columns the operator reads. With `raw` and `answers` (a person answered a question) the model is not asked again. The result is a draft: {'where' | 'name', 'expression', 'questions',
    'cites', 'check': {'ok', 'error'}, 'raw', 'sees', 'basis'}."""
    sentence, kind = _sentence(payload), payload.get('kind')
    if kind not in ('filter', 'calc'):
        raise TypeRefused(tr('kind 要写 filter 或 calc', 'kind must be filter or calc'))
    raw, answers = _raw(payload), _answers(payload)
    gateway = None if raw is not None else _gateway(llm)
    found, compiled, step_id = _columns_before(conn, engine, payload, user)
    try:
        seen = {}
        _, meaning_ids = build_context(conn)
        _run_to(engine, found, [step_id], lambda c, report, comp: seen.update(values_seen(c, comp['table'], comp['columns'], found['ctx'])) if report['id'] == step_id else None)
        columns = [{**c} for c in visible(compiled['columns'])]
        facts = column_facts(columns, found['ctx'], seen)
        out = {'kind': kind, 'sees': disclosure(facts), 'label': tr('AI 写的草稿，用不用由你定', 'Drafted by AI. You decide whether to use it')}
        if kind == 'filter':
            drafted = _settled(lambda: parse_condition(gateway, sentence, facts, seen, answers, _confirmed_by(conn, found['ctx'], meaning_ids, columns), raw), raw)
            if 'error' in drafted:
                raise TypeRefused(drafted['error'], 409)
            check = {'ok': False, 'error': tr('没有一个条件能先写下来：先回答下面的问题', 'No condition could be drafted yet. Answer the questions below first')} if drafted['where'] is None else _checked_filter(drafted['where'], compiled['columns'], found['ctx'])
            return {**out, **drafted, 'check': check}
        drafted = parse_expression(gateway, sentence, facts, FUNCTIONS)
        if 'error' in drafted:
            raise TypeRefused(drafted['error'], 409)
        result = compile_expression(drafted['expression'], [{'name': c['name'], 'type': c['type']} for c in columns])
        check = {'ok': True, 'type': result['type']} if result['ok'] else {'ok': False, 'error': result['errors'][0]['message']}
        return {**out, **drafted, 'questions': [], 'cites': [], 'check': check}
    finally:
        drop_temporary(engine, found['resolved'])


def _checked_filter(where: dict, columns: list[dict], ctx: dict) -> dict:
    try:
        compile_op({'op': 'filter', 'where': where}, 'x', columns, ctx, tr('这个条件', 'this condition'))
        return {'ok': True}
    except OpError as exc:
        return {'ok': False, 'error': str(exc)}


def _selected(spec: dict, payload: dict) -> list[str]:
    ids = payload.get('selected')
    by_id = {s['id']: s for s in spec.get('steps', []) if isinstance(s, dict) and isinstance(s.get('id'), str)}
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i in by_id for i in ids):
        raise TypeRefused(tr('先选中要用的节点（selected）：AI 只能读选中的节点', 'Select the nodes to use first (selected). The AI reads only the selected nodes'))
    if any(by_id[i].get('type') == 'output' for i in ids):
        raise TypeRefused(tr('输出节点不能选：它没有可读的列', 'An output node cannot be selected: it has no columns to read'))
    return list(dict.fromkeys(ids))


def draft(conn, engine, payload: dict, user: dict | None, llm: LlmService | None = None) -> dict:
    """The draft, with its key assumptions and self-check worked out by code from what it contains (assistant_checks): no further model call."""
    out = _draft(conn, engine, payload, user, llm)
    return {**out, 'assumptions': plan_assumptions(out, _answers(payload)), 'self_check': plan_self_check(out)}


def _draft(conn, engine, payload: dict, user: dict | None, llm: LlmService | None = None) -> dict:
    """{id | spec, selected: [step ids], text, raw?, answers?}: one draft of steps over the selected nodes: each step with a sentence of what it does, the questions that must be asked
    (each with the values seen and no recommended answer when a code is not confirmed; a confirmed meaning is cited instead), and the result of our check (columns, operators and
    functions exist) and of a dry run on the current data (rows in and out per step). Nothing is added to the pipeline: 应用 is the person's, on the page."""
    sentence = _sentence(payload)
    spec, name = _spec_of(conn, payload, user)
    selected, raw, answers = _selected(spec, payload), _raw(payload), _answers(payload)
    gateway = None if raw is not None else _gateway(llm)
    cut = {**copy.deepcopy(spec), 'steps': [s for s in copy.deepcopy(spec['steps']) if s.get('id') in needed_steps(spec, selected)]}
    found = check_definition(conn, engine, {'name': name or 'preview', 'spec': cut}, user, outputs_free=False)
    try:
        compiled = {s['id']: s for s in compile_pipeline(found['content']['spec'], found['resolved']['datasets'], found['resolved']['views'], found['ctx'])}
        seen = {i: {} for i in selected}
        _run_to(engine, found, selected, lambda c, report, comp: seen[report['id']].update(values_seen(c, comp['table'], comp['columns'], found['ctx'])) if report['id'] in seen else None)
        facts = {i: column_facts(compiled[i]['columns'], found['ctx'], seen[i]) for i in selected}
        _, meaning_ids = build_context(conn)
        by = {}
        for i in selected:
            by[i] = _confirmed_by(conn, found['ctx'], meaning_ids, compiled[i]['columns'])
        asked = ask_plan(gateway, sentence, facts) if raw is None else raw
        if 'error' in asked:
            raise TypeRefused(asked['error'], 409)
        merged_by = {c: w for i in selected for c, w in by[i].items()}
        elements = {c['name']: meaning_ids[c['origin']] for i in selected for c in visible(compiled[i]['columns']) if c.get('origin') in found['ctx']['meanings'] and c.get('origin') in meaning_ids}
    finally:
        drop_temporary(engine, found['resolved'])
    settled = _settled(lambda: settle_plan(asked, facts, seen, {s['id'] for s in spec['steps']}, llm.model if llm else None, sentence, answers, merged_by), raw)
    settled['cites'] = [{**c, 'definition': elements.get(c['column'])} for c in settled['cites']]   # where the meaning cited is defined: the card links to it
    out = {'raw': asked, 'basis': str(asked.get('basis') or ''), 'selected': selected, 'questions': settled['questions'], 'cites': settled['cites'], 'problems': settled['problems'],
           'sees': disclosure([f for i in selected for f in facts[i]]), 'label': tr('AI 写的草稿，用不用由你定', 'Drafted by AI. You decide whether to use it'), 'steps': [], 'max_steps': MAX_DRAFT_STEPS}
    if not settled['steps']:
        return {**out, 'check': {'ok': False, 'error': tr('；', '; ').join(settled['problems']) or tr('模型没有写出可用的步骤', 'The model did not write any usable step')}}
    new = [s['step'] for s in settled['steps']]
    whole = {**copy.deepcopy(spec), 'steps': [*copy.deepcopy(spec['steps']), *new]}
    trimmed = {**whole, 'steps': [s for s in whole['steps'] if s['id'] in needed_steps(whole, [s['id'] for s in new])]}
    try:
        again = check_definition(conn, engine, {'name': name or 'preview', 'spec': trimmed}, user, outputs_free=False)
    except TypeRefused as exc:
        return {**out, 'steps': [{**s, 'rows_in': None, 'rows_out': None} for s in settled['steps']], 'check': {'ok': False, 'error': str(exc)}}
    try:
        nodes = {n['id']: n for n in _run_to(engine, again, [s['id'] for s in new], None, llm_run(conn, llm, name, 'cache'))['nodes']}
    except TypeRefused as exc:
        return {**out, 'steps': [{**s, 'rows_in': None, 'rows_out': None} for s in settled['steps']], 'check': {'ok': False, 'error': str(exc)}}
    finally:
        drop_temporary(engine, again['resolved'])
    steps = [{**s, 'rows_in': nodes[s['id']]['rows_in'], 'rows_out': nodes[s['id']]['rows_out'], 'failures': nodes[s['id']].get('failures') or {},
              'to_call': (nodes[s['id']].get('llm') or {}).get('to_call'), 'operators': [{'op': o['op'], 'text': o.get('text'), 'rows_in': o['rows_in'], 'rows_out': o['rows_out']} for o in nodes[s['id']].get('operators', [])]}
             for s in settled['steps']]
    return {**out, 'steps': steps, 'check': {'ok': True, 'dry_run': tr('按现在的数据试算，没有写任何东西', 'Tried on the current data. Nothing was written')}}


def explain_steps(conn, engine, payload: dict, user: dict | None, llm: LlmService | None = None) -> dict:
    """{id | spec, selected: [step ids]}: a plain description of the selected steps, written by the model from their settings (not from rows). It is labelled AI-written: the settings are still
    what the person who confirms reads."""
    spec, name = _spec_of(conn, payload, user)
    selected = _selected(spec, payload)
    gateway = _gateway(llm)
    cut = {**copy.deepcopy(spec), 'steps': [s for s in copy.deepcopy(spec['steps']) if s.get('id') in needed_steps(spec, selected)]}
    found = check_definition(conn, engine, {'name': name or 'preview', 'spec': cut}, user, outputs_free=False)   # who may not see an input gets nothing
    drop_temporary(engine, found['resolved'])
    steps = [s for s in found['content']['spec']['steps'] if s['id'] in selected]
    said = explain(gateway, steps)
    if 'error' in said:
        raise TypeRefused(said['error'], 409)
    return {**said, 'selected': selected, 'label': tr('AI 写的说明，供读的人参考；以步骤的设置为准', 'Explained by AI, for reading only. The step settings are what counts'),
            'sees': {'text': tr('会把选中步骤的设置发给模型，设置里写的具体取值（比如过滤条件里的客户名、编号）也在内；不发数据行，也不发取值统计。', 'The settings of the selected steps are sent to the model, including the values written in them (for example a customer name or id in a filter). No data rows and no value counts are sent.')}}
