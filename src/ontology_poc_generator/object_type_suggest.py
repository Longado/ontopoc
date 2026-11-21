"""The model suggests object types from some datasets, as a task. One call, which sees each dataset's name, row count and each column's name, type, number
of distinct values and empty cells (no row, no value); everything it hands back is checked by the same code a person's definition goes through
(object_types.check_definition: the key must be unique and filled on the full data), and what passes is kept as a proposed element with no proposer: a model draft,
never confirmed. The task leaves one line in the log (what was asked, what was proposed, what was dropped and why) which the task list reads."""
from __future__ import annotations

import json
from contextlib import nullcontext

from ontology_poc_generator.assistant_checks import type_assumptions, type_self_check
from ontology_poc_generator.draft_receipts import issue, type_fingerprint
from ontology_poc_generator.lang import english, tr
from ontology_poc_generator.agent_harness import ask_model
from ontology_poc_generator.object_types import (
    CODE_TYPES, TypeRefused, _readable_dataset, dataset_columns, check_definition, element_row, check_names_free, write_elements, type_id)
from ontology_poc_generator.recognition import model_failure_text
from ontology_poc_generator.workspace_store import current_dataset, log_line

SUGGEST_PROMPT_VERSION = 'object_types.v1'
MODEL_NAME = '模型建议'   # who the log names for what the model wrote
MAX_PURPOSE = 400
MODEL_SECONDS = 120   # how long the model may take for one suggestion; the page says "usually 15–40 seconds" and waits for it
TASK_ELEMENT = 'task:suggest'
ENGLISH_NOTE = '\n\nThe person asking works in English: write the basis and needed_for texts in English.'   # appended only for an English asker; the Chinese prompt is unchanged

SYSTEM_PROMPT = """你在帮顾问从数据集里建议对象类型。一个对象类型是一类业务对象（订单、客户、产品），一行数据是它的一个对象。你会收到建模目的，以及每个数据集的名称、行数，和每一列的名称、类型、不同取值数、空值数、是不是整列都不重复。没有给你任何一行数据。

只输出 JSON：
{"object_types": [{"name": "中文名", "english_name": "字母开头，只用字母数字下划线", "dataset": "数据集名，原样照抄", "key": ["主键列，原样照抄"], "basis": "为什么这是一类对象、为什么选这个主键", "properties": [{"column": "列名，原样照抄", "needed_for": "目的里的哪件事要用这一列"}]}]}

规则：
- 只放目的真要用到的属性，不要给每一列都建属性。每个属性写 needed_for；写不出它为目的做什么，就不要放。
- 主键要整列都不重复、没有空值；不能是小数列或是/否列；一列不够就写几列（复合主键）。
- 一个数据集最多建议一个对象类型。按月份、版本一行一条的表记录的是“观察”，不是产品或订单本身：主键要带上月份或版本那一列。
- 数据集名、列名只能用给你的，原样照抄；没有把握的对象类型不要写。
"""


def _described(conn, names: list[str], user: dict | None) -> list[dict]:
    out = []
    for name in names:
        dataset = _readable_dataset(conn, name, user)
        if dataset is None:
            raise TypeRefused(tr(f'没有叫“{name}”的数据集', f'No dataset named “{name}”'), 404)
        out.append({'name': name, 'rows': dataset['rows_stored'], 'columns': [
            {'name': column, 'type': c['type'], 'distinct': c['distinct'], 'empty': c['missing'], 'all_different': c['missing'] == 0 and c['distinct'] == dataset['rows_stored']}
            for column, c in dataset_columns(conn, dataset['id']).items()]})
    return out


def _task_line(conn, who: str | None, after: dict) -> None:
    log_line(conn, who or '未署名', f'{TASK_ELEMENT}:{after["at"]}', 'suggest', after=after)


def suggest_types(conn, gateway, names, purpose, who: str | None, now: str, user: dict | None = None, lock=None) -> dict:
    """{'proposed': [{'id', 'name'}], 'rejected': [{'name', 'reason'}], 'model'}. TypeRefused (400 for the request, 502 for the model) with a task line in the
    log either way. The model is asked without `lock` (it takes up to MODEL_SECONDS); what it handed back is checked and written under it, so an upload
    does not land between the check and the write."""
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        raise TypeRefused(tr('要选至少一个数据集', 'Select at least one dataset'))
    if not isinstance(purpose, str) or len(purpose.strip()) > MAX_PURPOSE:
        raise TypeRefused(tr(f'建模目的最多 {MAX_PURPOSE} 个字', f'The modelling purpose is at most {MAX_PURPOSE} characters'))
    purpose = purpose.strip()
    datasets = _described(conn, list(dict.fromkeys(names)), user)
    judgement = ask_model(gateway, 'type_suggester', SUGGEST_PROMPT_VERSION, suggest_prompt(), {'purpose': purpose, 'datasets': datasets}, MODEL_SECONDS)
    task = {'at': now, 'datasets': [d['name'] for d in datasets], 'purpose': purpose, 'model': judgement.model, 'proposed': [], 'rejected': [], 'error': None}
    reply = judgement.reply
    if judgement.failure == 'request':
        task['error'] = model_failure_text(judgement.message)
    elif judgement.failure == 'not_json' or not isinstance(reply, dict) or not isinstance(reply.get('object_types'), list):
        task['error'] = tr('模型返回的不是约定的 JSON', 'The model did not return the agreed JSON')
    if task['error']:
        _task_line(conn, who, task)
        raise TypeRefused(task['error'], 502)
    asked = {d['name'] for d in datasets}
    with lock or nullcontext():
        for suggested in reply['object_types']:
            label = suggested.get('name') if isinstance(suggested, dict) else None
            try:
                made = _keep(conn, suggested, asked, user)
                task['proposed'].append(made)
            except TypeRefused as exc:
                task['rejected'].append({'name': str(label), 'reason': str(exc)})
        _task_line(conn, who, task)
    return {**{k: task[k] for k in ('proposed', 'rejected', 'model')}, 'self_check': type_self_check(len(task['proposed']), len(task['rejected']))}


def _keep(conn, suggested, asked: set[str], user: dict | None) -> dict:
    """One suggestion through the checks a person's definition goes through, then kept as a proposed element: no proposer by name (a model draft), the task's
    model as the writer, and the account of the person who asked as proposed_by_user_id, which the two-person rule reads."""
    if not isinstance(suggested, dict):
        raise TypeRefused(tr('不是一个对象类型的写法', 'This is not a valid object type'))
    if suggested.get('dataset') not in asked:
        raise TypeRefused(tr(f'数据集“{suggested.get("dataset")}”不在这次选的数据集里', f'Dataset “{suggested.get("dataset")}” is not among the datasets selected this time'))
    wanted = suggested.get('properties') if isinstance(suggested.get('properties'), list) else []
    why = {p.get('column'): p.get('needed_for') for p in wanted if isinstance(p, dict) and isinstance(p.get('needed_for'), str) and p['needed_for'].strip()}
    content, _, _, key_check = check_definition(conn, {'name': suggested.get('name'), 'english_name': suggested.get('english_name'), 'dataset': suggested.get('dataset'),
                                                 'key': suggested.get('key'), 'properties': [{'column': c} for c in why]}, user=user)
    check_names_free(conn, content)
    if element_row(conn, type_id(content['english_name'])):
        raise TypeRefused(tr(f'已经有英文名“{content["english_name"]}”的对象类型', f'An object type with the English name “{content["english_name"]}” already exists'))
    basis = suggested.get('basis') if isinstance(suggested.get('basis'), str) else ''
    content = {**content, 'basis': basis.strip()[:200], 'properties': [{**p, 'needed_for': why[p['column']].strip()[:100]} if p['column'] in why else p for p in content['properties']]}
    dataset = current_dataset(conn, content['dataset'])
    anchors = {'dataset': dataset['name'], 'version': dataset['version'], 'key_rows': key_check['rows_checked']}
    asker = user.get('id') if user else None   # the person who asked counts as its proposer for the two-person rule: they do not confirm the model's draft alone
    write_elements(conn, [(type_id(content['english_name']), 'proposed', f'check_result:{key_check["id"]},dataset:{dataset["name"]}@v{dataset["version"]}', MODEL_NAME,
                   content, anchors, None)], {type_id(content['english_name']): [f'dataset:{dataset["name"]}']},
                   after=(lambda c: c.execute('UPDATE element_state SET proposed_by_user_id = ? WHERE element_id = ?', (asker, type_id(content['english_name'])))) if asker is not None else None)
    used = {p['column'] for p in content['properties']}
    columns = dataset_columns(conn, dataset['id'])
    left_out = [c for c in columns if c not in used]   # the columns of the dataset this type does not use
    codes = [p['column'] for p in content['properties'] if p['column'] in columns and bool(columns[p['column']]['counts']) and columns[p['column']]['type'] in CODE_TYPES]   # code columns: their meanings are for a person to confirm
    receipt = issue(conn, user, 'type', content['english_name'], type_fingerprint(content))   # the server's record that this person was given this draft (draft_receipts)
    return {'draft_receipt': receipt, 'id': content['english_name'], 'name': content['name'], 'basis': content['basis'], 'dataset': dataset['name'], 'key': content['key'], 'left_out': left_out,
            'assumptions': type_assumptions(content['english_name'], content['key'], key_check['rows_checked'], codes)}


def suggest_prompt() -> str:
    return SYSTEM_PROMPT + ENGLISH_NOTE if english() else SYSTEM_PROMPT
