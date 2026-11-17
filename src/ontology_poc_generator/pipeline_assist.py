"""The assistant in the pipeline editor: a sentence into a filter or an expression (条件解析员), a sentence over selected nodes into a draft of steps (管道编排员), and a plain
description of selected steps (管道说明员). The model drafts; code decides what stands.

What the model is shown: the names and types of the columns of the selected nodes; for a code column whose meanings a person has confirmed, those meanings; for a column that has
at most FEW_VALUES different values of at most LONGEST_VALUE characters, each value and its rows (a code column nobody has confirmed gets none: the model would guess from them); a
column a builder keeps from the model, or with a longer value, or with more values, gets name and type only. This is more than names and types, and the screen says so.

What stands: a condition on a code column is written by meaning, from the confirmed meanings, and the code checks the meaning is one of them; a code value the model wrote
stands only when a confirmed meaning gives it, when the person answered the question, or when the sentence states it next to the column's name (状态码≠2, 状态码 是 2);
digits that merely occur in the sentence are not the person writing the code. A meaning nobody confirmed, or a value that stands on none of these, becomes a question with
the values seen and their rows, and a recommended answer only when a confirmed meaning looks like what was asked for. A step that refers to a node that was not selected, or to a column, operator or function that does not exist, does not stand. Nothing is written by the
assistant: 应用 is the person's.
"""
from __future__ import annotations

import copy
import re

from ontology_poc_generator.agent_harness import ask_model
from ontology_poc_generator.pipeline_ops import AGGREGATIONS, CAST_TYPES, visible
from ontology_poc_generator.recognition import model_failure_text
from ontology_poc_generator.lang import english, tr

PARSE_VERSION, PLAN_VERSION, EXPLAIN_VERSION = 'pipeline_condition_parser.v1', 'pipeline_planner.v1', 'pipeline_explainer.v1'
FEW_VALUES = 12   # a column with at most this many different values is shown to the model with each value and its rows
LONGEST_VALUE = 40   # ... and only when none of those values is longer than this many characters: a column with a longer one goes by name and type only
MAX_DRAFT_STEPS = 6
ALLOWED_STEPS = ('transform', 'join', 'llm')
REFS = ('from', 'left', 'right')

COLUMNS_NOTE = """columns 里每一列有 name、type；code=true 的是代码列：有 meanings（{含义: [代码]}）的，条件用 meaning 写含义，只能从 meanings 里选；没有 meanings 的，用 concept
写你想表达的含义（例如“已取消”），不要写代码值，不要猜代码是什么意思。values_seen 是这一列见过的取值和行数，只用来对上句子里说的值。values_withheld=true 的列看不到取值。"""

CONDITION_FORMAT = """条件写成 {"all": [条件…]} 或 {"any": [条件…]}，条件是：
{"column": 列名, "cmp": "eq|ne|gt|lt|ge|le", "value": 值} 或 {"column": 列名, "cmp": "in", "values": [值…]} 或 {"column": 列名, "cmp": "between", "low": 值, "high": 值}
或 {"column": 列名, "cmp": "is_null|not_null"}；代码列写 {"column": 列名, "cmp": "eq|ne|in", "meaning": 含义} 或 {"column": 列名, "cmp": "eq|ne", "concept": 含义}。"""

PARSE_SYSTEM_PROMPT = f"""你在帮人把一句话写成数据管道里的一个过滤条件，或一个计算列的表达式。你会收到 task（filter 或 calc）、sentence（这个人的话）和 columns。

{COLUMNS_NOTE}

task 是 filter 时，只输出 JSON：{{"basis": "一句话说你怎么理解的", "where": 条件}}
{CONDITION_FORMAT}
task 是 calc 时，只输出 JSON：{{"basis": "一句话说你怎么理解的", "name": "新列的名字", "expression": "表达式"}}；表达式里的列写成 [列名]，只能用 functions 里列出的函数。

只用 columns 里有的列，不要编新的列。句子里说不清的地方，不要猜。"""

PLAN_SYSTEM_PROMPT = f"""你在帮人把一句话写成数据管道里的几个步骤。你会收到 sentence（这个人的话）、selected（他选中的节点，你的步骤只能读这些节点，或读你自己前面写的步骤）和每个节点的 columns。

{COLUMNS_NOTE}

只输出 JSON：{{"basis": "一句话说你怎么理解的", "steps": [{{"summary": "这一步做什么，一句话", "step": 步骤}}]}}，最多 {MAX_DRAFT_STEPS} 步。步骤只有三种：
- 转换：{{"type": "transform", "from": 来源, "operators": [操作…]}}；操作有 filter（{{"op": "filter", "where": 条件}}）、calc（{{"op": "calc", "name": 新列名, "expression": 表达式}}）、aggregate（{{"op": "aggregate", "group_by": [列…], "aggregations": [{{"fn": "{'|'.join(AGGREGATIONS)}", "column": 列, "as": 名字}}]}}）、cast（{{"op": "cast", "column": 列, "to": "{'|'.join(CAST_TYPES)}"}}）、dedupe、fill_null、text_clean。
- 关联：{{"type": "join", "left": 来源, "right": 来源, "how": "inner|left|anti|semi", "on": [{{"left": 列, "right": 列}}]}}。
- AI 判断：{{"type": "llm", "from": 来源, "name": 新列名, "template": "classify", "column": 要分类的列, "categories": [类别…，最后一个是 其他]}}。
来源写选中节点的 id，或写 "$1"、"$2" 指你自己写的第 1、2 步。{CONDITION_FORMAT}
只用 columns 里有的列。句子里说不清的地方，不要猜；不要写输出步骤。"""

EXPLAIN_SYSTEM_PROMPT = """你在帮另一个人看懂一段数据管道。你会收到 steps：选中的步骤和它们的设置。只输出 JSON：{"basis": "你依据哪几步", "text": "用平常话说这几步做了什么，按先后顺序，3 到 8 句，别用英文字段名"}。
只说设置里有的，不要加设置里没有的做法，不要评价好坏。"""


# --- what the model is shown ---------------------------------------------------------------------------------------------------------------------------

class Seen(list):
    """The values of one column with their rows; `complete` is false when the column has more different values than these (a code column's first FEW_VALUES, which a person is
    shown to choose from but which are not sent as the column's values)."""
    complete = True


def values_seen(conn, table: str, columns: list[dict], ctx: dict) -> dict:
    """{column: [{'value', 'rows'}]} for the columns of the table that have few different values (a code column whatever its count), every row counted; a column switched off for
    the model, one the model wrote and a number are left out."""
    seen = {}
    q = lambda name: '"' + name.replace('"', '""') + '"'
    for c in visible(columns):
        if c.get('unsent') or c.get('ai') or c['type'] not in ('text', 'integer', 'month'):
            continue
        column = q(c['name'])
        rows = conn.execute(f"SELECT {column}, COUNT(*) FROM {table} WHERE {column} IS NOT NULL AND TRIM(CAST({column} AS TEXT)) <> '' GROUP BY {column} ORDER BY 2 DESC, 1 LIMIT {FEW_VALUES + 1}").fetchall()
        if rows and (len(rows) <= FEW_VALUES or c.get('origin') in ctx['codes']):
            seen[c['name']] = Seen({'value': str(v), 'rows': n} for v, n in rows[:FEW_VALUES])
            seen[c['name']].complete = len(rows) <= FEW_VALUES
    return seen


def column_facts(columns: list[dict], ctx: dict, seen: dict) -> list[dict]:
    """What the model is shown of each column (see the module's words)."""
    out = []
    for c in visible(columns):
        fact = {'name': c['name'], 'type': c['type']}
        if c.get('unsent'):
            out.append({**fact, 'values_withheld': True})
            continue
        origin = c.get('origin')
        if origin in ctx['codes']:
            fact['code'] = True
            if ctx['meanings'].get(origin):
                fact['meanings'] = ctx['meanings'][origin]
        values = seen.get(c['name'])
        if values and values.complete and all(len(v['value']) <= LONGEST_VALUE for v in values) and (not fact.get('code') or 'meanings' in fact):
            fact['values_seen'] = values
        out.append(fact)
    return out


ENGLISH_NOTE = '\n\nThe person asking works in English: write every "basis", "summary" and "text" in English.'   # appended only for an English asker; the Chinese prompts are unchanged


def _in_language(prompt: str) -> str:
    return prompt + ENGLISH_NOTE if english() else prompt


def disclosure(facts: list[dict]) -> dict:
    """What the person is told is sent besides names and types."""
    return {'values_sent': [f['name'] for f in facts if 'values_seen' in f or 'meanings' in f], 'withheld': [f['name'] for f in facts if f.get('values_withheld')],
            'text': tr(f'除了列名和类型，还会把取值不多的列（最多 {FEW_VALUES} 个不同的取值，每个取值不超过 {LONGEST_VALUE} 个字）的每个取值和行数、已确认的代码含义发给模型；'
                    '取值更多、有更长的取值、或标了不发送的列只发名字和类型；整行数据不发。', f'Besides column names and types, every value and its row count, and the confirmed code meanings, are sent to the model for columns with few values (at most {FEW_VALUES} distinct values, each at most {LONGEST_VALUE} characters); '
                    'columns with more values, longer values, or marked not to be sent only have their name and type sent; whole rows are never sent.')}


# --- conditions: what stands -----------------------------------------------------------------------------------------------------------------------------

def _recommend(concept: str | None, meanings: dict, column: str, by: str | None) -> dict | None:
    """The confirmed meaning whose name contains what was asked for (or is contained in it), as the answer to suggest; None when no confirmed meaning looks like it."""
    if not concept or len(concept) < 2:
        return None
    label = next((l for l in meanings if concept in l or l in concept), None)
    if label is None:
        return None
    codes = meanings[label]
    return {'meaning': label, 'value': codes, 'text': tr(f'“{label}”：代码 {"、".join(codes)}（已确认{f"，{by}" if by else ""}）', f'"{label}": codes {", ".join(codes)} (confirmed{f" by {by}" if by else ""})')}


def _question(column: str, concept: str | None, fact: dict, values: list[dict], by: str | None = None) -> dict:
    """A code the draft cannot decide: which value means the concept, with the values seen and their rows (and the confirmed meanings, when there are some), and as the
    recommended answer the confirmed meaning that looks like what was asked for, if there is one."""
    meanings = fact.get('meanings')
    if meanings:
        evidence = tr(f'已确认的含义有：{"；".join(label + "（" + "、".join(codes) + "）" for label, codes in meanings.items())}，没有“{concept}”', f'The confirmed meanings are: {"; ".join(label + " (" + ", ".join(codes) + ")" for label, codes in meanings.items())}, and none is "{concept}"')
    elif values:
        evidence = tr(f'未确认：见过 {"、".join(v["value"] for v in values)}（{"、".join(str(v["rows"]) + " 行" for v in values)}）', f'Not confirmed: seen {", ".join(v["value"] for v in values)} ({", ".join(str(v["rows"]) + " rows" for v in values)})')
    else:
        evidence = tr('未确认：这一列的含义还没有人确认', 'Not confirmed: nobody has confirmed the meanings of this column yet')
    return {'id': f'{column}|{concept or ""}', 'column': column, 'concept': concept, 'recommended': _recommend(concept, meanings or {}, column, by), 'evidence': evidence,
            'ask': tr(f'「{column}」里哪个代码表示“{concept}”？', f'Which code in "{column}" means "{concept}"?') if concept else tr(f'「{column}」的哪个值？', f'Which value of "{column}"?'),
            'options': [{'value': v['value'], 'text': tr(f'{v["value"]}（{v["rows"]} 行）', f'{v["value"]} ({v["rows"]} rows)')} for v in values]}


def _cite(column: str, label: str, codes: list, by: str | None) -> dict:
    return {'column': column, 'meaning': label, 'codes': codes, 'text': tr(f'「{column}」的含义“{label}”是代码 {"、".join(codes)}（已确认{f"，{by}" if by else ""}）', f'The meaning "{label}" of "{column}" is codes {", ".join(codes)} (confirmed{f" by {by}" if by else ""})')}


STATES = ('≠', '!=', '<>', '==', '=', '不等于', '不是', '等于', '是', '为', ':', '：')   # what may stand between a column's name and the value the person gives it


def _stated(sentence: str, column: str, value: str) -> bool:
    """Whether the sentence gives the column this value as a whole: the column's name, then 是 / 为 / ≠ …, then the value (not the start of a longer number)."""
    gap = r'[\s「」"\'“”]*'
    return re.search(re.escape(column) + gap + '(?:' + '|'.join(map(re.escape, STATES)) + ')' + gap + re.escape(value) + r'(?![0-9A-Za-z])', sentence) is not None


def settle(node, facts: dict, seen: dict, sentence: str, answers: dict, questions: dict, cites: list, by: dict):
    """The condition with every part of it that stands, or None when nothing does: a code column by confirmed meaning; a code value only when a confirmed meaning gives it, the
    person answered for it, or the sentence states it next to the column's name. What cannot stand is added to `questions` ({id: question}), what stands by a meaning to `cites`."""
    if not isinstance(node, dict):
        return None
    if 'all' in node or 'any' in node:
        mode = 'all' if 'all' in node else 'any'
        kept = [x for x in (settle(i, facts, seen, sentence, answers, questions, cites, by) for i in (node[mode] if isinstance(node[mode], list) else [])) if x]
        return {mode: kept} if kept else None
    fact = facts.get(node.get('column'))
    if fact is None or not fact.get('code'):
        return node
    column, labels, cmp = node['column'], fact.get('meanings') or {}, node.get('cmp')
    base = {k: v for k, v in node.items() if k not in ('meaning', 'meanings', 'concept', 'value', 'values')}
    wanted = node.get('meaning', node.get('meanings'))
    concept = node.get('concept')
    if wanted is not None:
        names = [wanted] if isinstance(wanted, str) else [w for w in wanted if isinstance(w, str)] if isinstance(wanted, list) else []
        if names and all(n in labels for n in names):
            cites.extend(_cite(column, n, labels[n], by.get(column)) for n in names)
            return node
        concept = names[0] if names else None   # a meaning nobody confirmed is a concept still to be settled
    key = f'{column}|{concept or ""}'
    if answers.get(key):
        chosen = [str(v) for v in answers[key]]
        return {**base, 'cmp': 'in' if len(chosen) > 1 else (cmp if cmp in ('eq', 'ne') else 'eq'), **({'values': chosen} if len(chosen) > 1 else {'value': chosen[0]})}
    if concept is not None and concept in labels:   # a confirmed meaning of exactly that name
        cites.append(_cite(column, concept, labels[concept], by.get(column)))
        return {**base, 'meaning': concept}
    if concept is None:
        given = [str(node['value'])] if 'value' in node else [str(v) for v in node.get('values') or []]
        back = [label for g in given for label, codes in labels.items() if g in codes]
        if given and len(back) == len(given):   # codes a confirmed meaning stands behind: written by the meaning
            cites.extend(_cite(column, n, labels[n], by.get(column)) for n in dict.fromkeys(back))
            return {**base, 'meaning': back[0] if len(set(back)) == 1 else list(dict.fromkeys(back))}
        if given and all(_stated(sentence, column, g) for g in given):
            return node   # the person wrote the code themselves, next to the column's name
    questions[key] = _question(column, concept, fact, seen.get(column) or [], by.get(column))
    return None


def parse_condition(gateway, sentence: str, facts: list[dict], seen: dict, answers: dict, by: dict, raw: dict | None = None) -> dict:
    """{'raw' (what the model said), 'where' (what stands, or None), 'questions', 'cites', 'basis'} or {'error'}; with `raw` the model is not asked again (a person answered a question)."""
    if raw is None:
        got = ask_model(gateway, 'condition_parser', PARSE_VERSION, _in_language(PARSE_SYSTEM_PROMPT), {'task': 'filter', 'sentence': sentence, 'columns': facts})
        if got.failure == 'request':
            return {'error': model_failure_text(got.message)}
        if got.failure == 'not_json' or not isinstance(got.reply, dict) or not isinstance(got.reply.get('where'), dict):
            return {'error': tr('模型返回的不是约定的 JSON：要有 where', 'The model did not return the agreed JSON: it needs where')}
        raw = got.reply
    questions, cites = {}, []
    where = settle(raw.get('where'), {f['name']: f for f in facts}, seen, sentence, answers, questions, cites, by)
    return {'raw': raw, 'where': where, 'questions': list(questions.values()), 'cites': cites, 'basis': str(raw.get('basis') or '')}


def parse_expression(gateway, sentence: str, facts: list[dict], functions: list[str]) -> dict:
    """{'name', 'expression', 'basis'} the model wrote for a calculated column, or {'error'}; the expression is for the caller to check against the columns."""
    got = ask_model(gateway, 'condition_parser', PARSE_VERSION, _in_language(PARSE_SYSTEM_PROMPT), {'task': 'calc', 'sentence': sentence, 'columns': facts, 'functions': functions})
    if got.failure == 'request':
        return {'error': model_failure_text(got.message)}
    reply = got.reply
    if got.failure == 'not_json' or not isinstance(reply, dict) or not isinstance(reply.get('expression'), str) or not isinstance(reply.get('name'), str):
        return {'error': tr('模型返回的不是约定的 JSON：要有 name 和 expression', 'The model did not return the agreed JSON: it needs name and expression')}
    return {'name': reply['name'].strip(), 'expression': reply['expression'].strip(), 'basis': str(reply.get('basis') or '')}


# --- a draft of steps ------------------------------------------------------------------------------------------------------------------------------------

def ask_plan(gateway, sentence: str, selected: dict) -> dict:
    """The model's draft as it said it ({'basis', 'steps'}), or {'error'}. `selected` is {node id: its column facts}."""
    got = ask_model(gateway, 'pipeline_planner', PLAN_VERSION, _in_language(PLAN_SYSTEM_PROMPT), {'sentence': sentence, 'selected': [{'id': i, 'columns': f} for i, f in selected.items()]})
    if got.failure == 'request':
        return {'error': model_failure_text(got.message)}
    if got.failure == 'not_json' or not isinstance(got.reply, dict) or not isinstance(got.reply.get('steps'), list):
        return {'error': tr('模型返回的不是约定的 JSON：要有 steps', 'The model did not return the agreed JSON: it needs steps')}
    return got.reply


def settle_plan(raw: dict, selected: dict, seen: dict, taken: set[str], model: str | None, sentence: str, answers: dict, by: dict) -> dict:
    """{'steps': [{'id', 'summary', 'step'}], 'questions', 'cites', 'problems'}: the model's steps as ordinary steps with ids of their own, reading only selected nodes or earlier steps of
    the draft, a condition on a code column settled as `settle` says. A draft the code cannot accept as steps says why in `problems` and has none."""
    items = raw.get('steps') if isinstance(raw.get('steps'), list) else []
    problems, steps, questions, cites, root = [], [], {}, [], {}
    if not items or len(items) > MAX_DRAFT_STEPS:
        return {'steps': [], 'questions': [], 'cites': [], 'problems': [tr(f'模型要写 1 到 {MAX_DRAFT_STEPS} 步，它写了 {len(items)} 步', f'The model must write 1 to {MAX_DRAFT_STEPS} steps, and it wrote {len(items)}')]}
    ids, n = [], 0
    for _ in items:
        n += 1
        while f'ai{n}' in taken:
            n += 1
        ids.append(f'ai{n}')
    for position, item in enumerate(items):
        step = copy.deepcopy(item.get('step') if isinstance(item, dict) else None)
        label = tr(f'第 {position + 1} 步', f'step {position + 1}')
        if not isinstance(step, dict) or step.get('type') not in ALLOWED_STEPS:
            problems.append(tr(f'{label}：步骤只能是 {"、".join(ALLOWED_STEPS)}', f'{label}: a step can only be {", ".join(ALLOWED_STEPS)}'))
            continue
        step['id'] = ids[position]
        for key in REFS:
            if key not in step:
                continue
            ref = step[key]
            if isinstance(ref, str) and ref.startswith('$') and ref[1:].isdigit() and 1 <= int(ref[1:]) <= position:
                step[key] = ids[int(ref[1:]) - 1]
            elif ref not in selected:
                problems.append(tr(f'{label}：读了没有选中的节点「{ref}」', f'{label}: it read the node "{ref}", which was not selected'))
        origin = next((root.get(step[k], step[k]) for k in REFS if k in step and (step[k] in selected or step[k] in root)), None)
        root[step['id']] = origin
        if step['type'] == 'llm':
            step.update({'model': model or '', 'template': step.get('template', 'classify')})
        facts = {f['name']: f for f in selected.get(origin, [])}
        for op in step.get('operators') or []:
            if isinstance(op, dict) and op.get('op') == 'filter':
                op['where'] = settle(op.get('where'), facts, seen.get(origin, {}), sentence, answers, questions, cites, by)
        if step['type'] == 'transform':
            step['operators'] = [op for op in step.get('operators') or [] if not (isinstance(op, dict) and op.get('op') == 'filter' and op.get('where') is None)]
        steps.append({'id': step['id'], 'summary': str(item.get('summary') or ''), 'step': step})
    return {'steps': [] if problems else steps, 'questions': list(questions.values()), 'cites': cites, 'problems': problems}


def explain(gateway, steps: list[dict]) -> dict:
    """{'text', 'basis'} in plain words for the selected steps, or {'error'}."""
    got = ask_model(gateway, 'pipeline_explainer', EXPLAIN_VERSION, _in_language(EXPLAIN_SYSTEM_PROMPT), {'steps': steps})
    if got.failure == 'request':
        return {'error': model_failure_text(got.message)}
    if got.failure == 'not_json' or not isinstance(got.reply, dict) or not isinstance(got.reply.get('text'), str) or not got.reply['text'].strip():
        return {'error': tr('模型返回的不是约定的 JSON：要有 text', 'The model did not return the agreed JSON: it needs text')}
    return {'text': got.reply['text'].strip(), 'basis': str(got.reply.get('basis') or '')}
