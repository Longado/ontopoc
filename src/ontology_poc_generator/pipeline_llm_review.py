"""Trying an LLM step and checking its quality: 试跑 on typed values, chosen rows or a random sample, and 样本审核, where a person writes the answer they expect for
some rows and the step is held against them (exact match after trimming; no model judges another). The labels belong to the node and stay when the prompt changes;
the count is worked out again, on the labels, by a rerun the person asks for. Everything here that calls the model says so; nothing runs by itself.
"""
from __future__ import annotations

import json
import math
import random

from ontology_poc_generator import pipeline_llm
from ontology_poc_generator.pipeline_funcs import number_text
from ontology_poc_generator.pipeline_llm import (
    LlmError, LlmService, MAX_FIELD_CHARS, _blank, cache_get, cache_put, call_many, compile_prompt, contract_of, effective, prompt_sent, refuse_over, request_of, row_hash)
from ontology_poc_generator.workspace_store import now_text
from ontology_poc_generator.lang import tr

SAMPLE_ROWS = 20   # the sample a person is shown to label when they do not say how many
MIN_LABELLED = 20   # the rows that have to be labelled for a review to pass (every different row the step reads, when there are fewer)
PASS_SHARE = 0.8    # and the share of the labelled rows the step has to get right, whatever pass mark it names itself


def _same_number(a, b) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return False


def _expected_text(value) -> str | None:
    return None if value is None else number_text(value) if isinstance(value, (int, float)) else str(value).strip()


def matches(eff: dict, expected, values) -> bool:
    """Whether what the step wrote for a row is what the person expected: exact after trimming; numbers by value; several labels as a set; an extraction field by field."""
    if values is None:
        return False
    kind = eff['kind']
    if kind == 'extract':
        return isinstance(expected, dict) and all(_expected_text(expected.get(f['name'])) == _expected_text(v) or _same_number(expected.get(f['name']), v)
                                                  for f, v in zip(eff['fields'], values))
    got = values[0]
    if kind == 'number':
        return _same_number(expected, got)
    if kind == 'choices':
        return set(filter(None, (p.strip() for p in str(expected).replace('；', ';').split(';')))) == set(filter(None, (p.strip() for p in str(got).split('；'))))
    return str(expected).strip() == str(got).strip()


def check_expected(eff: dict, expected):
    """The expected answer a person wrote, in the form the step's answers have (LlmError when it cannot be one of them)."""
    kind = eff['kind']
    if kind == 'extract':
        if not isinstance(expected, dict):
            raise LlmError(tr('抽取的标注要写成 {字段名: 值}', 'The label for an extraction must be {field name: value}'))
        return {f['name']: expected.get(f['name']) for f in eff['fields']}
    if kind == 'number':
        if isinstance(expected, bool) or not _is_number(expected):
            raise LlmError(tr(f'标注要写一个数，写的是「{expected}」', f'The label must be a number, and it says "{expected}"'))
        return expected
    if not isinstance(expected, str) or not expected.strip():
        raise LlmError(tr('标注要写期望的答案', 'The label must give the expected answer'))
    expected = expected.strip()
    if kind == 'choice' and expected not in eff['choices']:
        raise LlmError(tr(f'标注「{expected}」不在可选的答案里：{"、".join(eff["choices"])}', f'The label "{expected}" is not among the possible answers: {", ".join(eff["choices"])}'))
    if kind == 'choices':
        picked = [p.strip() for p in expected.replace('；', ';').split(';') if p.strip()]
        if not picked or any(p not in eff['choices'] for p in picked):
            raise LlmError(tr(f'标注要从可选的答案里选，几个用“；”隔开：{"、".join(eff["choices"])}', f'The label must be chosen from the possible answers, separated by "; " when there are several: {", ".join(eff["choices"])}'))
    return expected


def _is_number(value) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def draw(rows: list[tuple[int, dict]], fields: list[str], n: int, seed, skip: set[str]) -> list[tuple[int, dict]]:
    """n rows with different content at random from the rows that have something to ask and are not in `skip` (row hashes); the same seed draws the same rows."""
    pool = {}
    for i, (_, v) in enumerate(rows):
        key = row_hash(v, fields)
        if not all(_blank(v[f]) for f in fields) and key not in skip:
            pool.setdefault(key, (i, v))   # the same content is one row to label: its answer is the same
    return random.Random(seed).sample(list(pool.values()), min(n, len(pool)))


def run_rows(conn, service: LlmService, pipeline_id: str, step: dict, names: list[str], rows: list[tuple[int, dict]], what: str = tr('这次试跑', 'this trial run')) -> list[dict]:
    """The step applied to these (row number, values) rows; `names` are the columns the step reads. For each {'row', 'fields', 'status', 'values', 'message', 'raw', 'cached', 'prompt'}. A row with
    nothing in its prompt fields is skipped without a call. Answers that are answers are kept for later runs, each batch as it comes back. This calls the model, for at most
    MAX_TRIAL_CALLS rows (refused before the first call, in words that start with `what`)."""
    eff = effective(step)
    parts, fields = compile_prompt(eff['prompt'], names)
    model = service.model or step.get('model')
    contract = contract_of(eff, model)
    asked = {}
    for _, values in rows:
        if not all(_blank(values.get(f)) for f in fields):
            asked.setdefault(row_hash(values, fields), values)
    kept = cache_get(conn, pipeline_id, step['id'], contract, list(asked))
    todo = {k: request_of(eff, parts, v) for k, v in asked.items() if k not in kept and all(len(x or '') <= MAX_FIELD_CHARS for x in v.values())}
    refuse_over(len(todo), pipeline_llm.MAX_TRIAL_CALLS, what)
    if todo and service.gateway is None:
        raise LlmError(tr('本机服务没有模型凭据，不能调用模型', 'This server has no model credentials, so the model cannot be called'))
    got = call_many(service.gateway, eff, todo, lambda batch: cache_put(conn, pipeline_id, step['id'], contract, model, {k: g for k, g in batch.items() if g['status'] == 'ok'})) if todo else {}
    out = []
    for position, values in rows:
        shown = {f: values.get(f) for f in fields}
        request = request_of(eff, parts, values)
        if all(_blank(values.get(f)) for f in fields):
            out.append({'row': position, 'fields': shown, 'status': 'skipped', 'values': None, 'message': tr('跳过：提示用到的列都是空的', 'Skipped: every column the prompt uses is empty'), 'raw': None, 'cached': False, 'prompt': None})
            continue
        key = row_hash(values, fields)
        if key in kept:
            out.append({'row': position, 'fields': shown, 'status': 'ok', 'values': kept[key]['values'], 'message': None, 'raw': kept[key]['raw'], 'cached': True, 'prompt': prompt_sent(request)})
        elif key in got:
            g = got[key]
            out.append({'row': position, 'fields': shown, 'status': g['status'], 'values': g['values'], 'message': g['message'], 'raw': g['raw'], 'cached': False, 'prompt': prompt_sent(request)})
        else:
            out.append({'row': position, 'fields': shown, 'status': 'failed', 'values': None, 'message': tr(f'内容超过 {MAX_FIELD_CHARS} 字，没有发送', f'The content is over {MAX_FIELD_CHARS} characters and was not sent'), 'raw': None, 'cached': False, 'prompt': None})
    return out


# --- labels and the count ------------------------------------------------------------------------------------------------------------------------------

def labels_of(conn, pipeline_id: str, step_id: str) -> list[dict]:
    return [{'row_hash': h, 'fields': json.loads(f), 'expected': json.loads(e), 'who': w, 'at': a} for h, f, e, w, a in conn.execute(
        'SELECT row_hash, fields_json, expected_json, who, at FROM llm_label WHERE pipeline_id = ? AND step_id = ? ORDER BY at, row_hash', (pipeline_id, step_id))]


def save_labels(conn, pipeline_id: str, step: dict, names: list[str], labels, who: str | None, who_user_id: int | None) -> int:
    """Keeps the expected answers a person wrote for rows (each {fields, expected}); the fields name the row, so the same row labelled again is replaced. How many."""
    eff = effective(step)
    _, fields = compile_prompt(eff['prompt'], names)
    if not isinstance(labels, list) or not labels:
        raise LlmError(tr('要写至少一行的标注（labels）', 'Write labels for at least one row (labels)'))
    rows = []
    for item in labels:
        values = item.get('fields') if isinstance(item, dict) else None
        if not isinstance(values, dict) or set(values) != set(fields):
            raise LlmError(tr(f'每条标注要带上这一行提示里用到的列：{"、".join(fields)}', f'Each label must include the columns the prompt uses for that row: {", ".join(fields)}'))
        rows.append((row_hash(values, fields), json.dumps(values, ensure_ascii=False), json.dumps(check_expected(eff, item.get('expected')), ensure_ascii=False)))
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.executemany('INSERT OR REPLACE INTO llm_label(pipeline_id, step_id, row_hash, fields_json, expected_json, who, who_user_id, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                         [(pipeline_id, step['id'], h, f, e, who, who_user_id, now_text()) for h, f, e in rows])
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return len(rows)


def remove_label(conn, pipeline_id: str, step_id: str, row_hash_value: str) -> None:
    conn.execute('DELETE FROM llm_label WHERE pipeline_id = ? AND step_id = ? AND row_hash = ?', (pipeline_id, step_id, row_hash_value))


def run_review(conn, service: LlmService, pipeline_id: str, step: dict, names: list[str], who: str | None, who_user_id: int | None, present: set[str], distinct_rows: int) -> dict:
    """The labelled rows run through the step as it is now (this calls the model for those it has no answer for), compared with what the person expected; the count is
    kept with the step's contract, with how many different rows the step has to ask about (`distinct_rows`) and what each labelled row came back as. A label for a row that is
    not among `present` (the row hashes of the data the step reads) is a miss, and is not sent to the model. {'total', 'matched', 'min_match', 'passed',
    'rows': [{fields, expected, values, matched, status, message}]}."""
    eff = effective(step)
    labels = labels_of(conn, pipeline_id, step['id'])
    if not labels:
        raise LlmError(tr('还没有标注：先抽一批行，写下你期望的答案', 'No labels yet: pull a batch of rows and write the answers you expect'))
    real = [l for l in labels if l['row_hash'] in present]
    done = dict(zip((l['row_hash'] for l in real), run_rows(conn, service, pipeline_id, step, names, [(i, l['fields']) for i, l in enumerate(real)], tr('这次样本审核', 'this sample review'))))
    absent = {'values': None, 'status': 'absent', 'message': tr('这一行不在这一步读到的数据里，算没对上', 'This row is not in the data this step read, so it counts as a mismatch')}
    detail = [{'fields': l['fields'], 'expected': l['expected'], 'values': (r := done.get(l['row_hash'], absent))['values'], 'matched': matches(eff, l['expected'], r['values']),
               'status': r['status'], 'message': r['message'], 'row_hash': l['row_hash']} for l in labels]
    matched = sum(d['matched'] for d in detail)
    contract = contract_of(eff, service.model or step.get('model'))
    conn.execute('INSERT OR REPLACE INTO llm_review(pipeline_id, step_id, contract, total, matched, min_match, who, who_user_id, at, distinct_rows, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                 (pipeline_id, step['id'], contract, len(detail), matched, step.get('min_match'), who, who_user_id, now_text(), distinct_rows,
                  json.dumps([{k: d[k] for k in ('row_hash', 'values', 'matched', 'status', 'message')} for d in detail], ensure_ascii=False)))
    return {'total': len(detail), 'matched': matched, 'min_match': step.get('min_match'), 'rows': detail,
            'passed': passes(step.get('min_match'), len(detail), matched, len(detail), distinct_rows)}


def passes(min_match: int | None, labelled: int, matched: int, total: int, distinct_rows: int | None) -> bool:
    """Whether a count passes: the step names a pass mark, enough rows are labelled (MIN_LABELLED, or every different row when the step has fewer), and the rows it got right are
    at least the mark and at least PASS_SHARE of the rows labelled."""
    return min_match is not None and labelled == total and labelled >= min(MIN_LABELLED, distinct_rows or MIN_LABELLED) and matched >= max(min_match, math.ceil(PASS_SHARE * labelled))


def review_state(conn, pipeline_id: str, step: dict, model: str | None = None) -> dict:
    """Where the sample review of this step stands: how many rows are labelled, the last count (and whether it was made with the prompt, model and output the step has now:
    `current`), whether it passed against the line the step names (min_match; none named: it cannot pass), who made it and when."""
    eff = effective(step)
    contract = contract_of(eff, model or step.get('model'))
    labelled = conn.execute('SELECT COUNT(*) FROM llm_label WHERE pipeline_id = ? AND step_id = ?', (pipeline_id, step['id'])).fetchone()[0]
    last = conn.execute('SELECT contract, total, matched, who, at, distinct_rows FROM llm_review WHERE pipeline_id = ? AND step_id = ?', (pipeline_id, step['id'])).fetchone()
    current = last is not None and last[0] == contract and last[1] == labelled
    line = step.get('min_match')
    distinct = last[5] if last else None
    return {'labelled': labelled, 'min_match': line, 'matched': last[2] if last else None, 'total': last[1] if last else None, 'current': current, 'who': last[3] if last else None,
            'at': last[4] if last else None, 'passed': bool(current and passes(line, labelled, last[2], last[1], distinct)),
            'needs_rerun': last is not None and not current,   # a prompt, model or output change, or other labels, since the count was made: it passes nothing until it is run again
            'need_labelled': min(MIN_LABELLED, distinct or MIN_LABELLED), 'need_match': None if line is None else max(line, math.ceil(PASS_SHARE * labelled)),
            'reviewable': eff['template'] != 'summary'}


def review_rows(conn, pipeline_id: str, step: dict) -> list[dict]:
    """What the person who confirms reads: each labelled row, who labelled it, what was expected, what the step answered at the last count, and whether they match."""
    last = conn.execute('SELECT detail_json FROM llm_review WHERE pipeline_id = ? AND step_id = ?', (pipeline_id, step['id'])).fetchone()
    detail = {d['row_hash']: d for d in json.loads(last[0])} if last and last[0] else {}
    who = dict(conn.execute('SELECT row_hash, who FROM llm_label WHERE pipeline_id = ? AND step_id = ?', (pipeline_id, step['id'])).fetchall())
    return [{'fields': l['fields'], 'expected': l['expected'], 'ai': (detail.get(l['row_hash']) or {}).get('values'), 'matched': (detail.get(l['row_hash']) or {}).get('matched'),
             'status': (detail.get(l['row_hash']) or {}).get('status'), 'who': who.get(l['row_hash'])} for l in labels_of(conn, pipeline_id, step['id'])]
