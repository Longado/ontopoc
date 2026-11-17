"""The operators of a transform step. An operator is plain data ({"op": "filter", "where": {...}}); compile_op checks it against the columns it reads
(OpError, in plain Chinese, names the operator and the column that is wrong) and returns what the engine runs: the columns it leaves, one SELECT over the
table before it with its bound parameters, and `measure`, which after the run says what the operator did to the rows (rows affected, rows dropped and why,
values that could not be converted). Nothing is silently lost: a row dropped because a condition was empty is counted apart from one dropped because it
was false, a value that cannot be converted is counted and listed, a code that no label was written for is counted.

A column is {'name', 'type'} with, where it has them, 'origin' ("dataset.column", which is how a code column is recognised after a join), 'badge' ('new' or
'replaced' in the transform that made it), 'hidden' (the row-identity columns a join adds so that a later sum can say what it counted twice; no person writes them
and no output carries them) and 'fan' (the hidden columns that identify the source row of this column's value).
"""
from __future__ import annotations

import difflib
import re

from ontology_poc_generator.pipeline_expr import COLUMN_TYPE, EXPR_TYPE, NUMBER_TYPES, TYPE_WORD, WordMap, compile_expression, error_condition
from ontology_poc_generator.pipeline_funcs import format_regex
from ontology_poc_generator.lang import tr

MAX_OPERATORS = 30
MAX_GROUP_DEPTH, MAX_CONDITIONS, MAX_LIST = 5, 50, 500
EXAMPLES = 20
NAME_LIMIT = 60
CMPS = {'eq': '=', 'ne': '<>', 'gt': '>', 'lt': '<', 'ge': '>=', 'le': '<='}
AGGREGATIONS = WordMap({'sum': ('求和', 'Sum'), 'count': ('计数', 'Count'), 'count_distinct': ('去重计数', 'Count distinct'), 'avg': ('平均', 'Average'), 'min': ('最小', 'Min'), 'max': ('最大', 'Max'), 'median': ('中位数', 'Median'),
                        'p25': ('P25', 'P25'), 'p75': ('P75', 'P75')})
NUMERIC_ONLY = ('sum', 'avg', 'median', 'p25', 'p75')
PERCENTILE = {'median': 0.5, 'p25': 0.25, 'p75': 0.75}
CAST_TYPES = WordMap({'date': ('日期', 'Date'), 'datetime': ('日期时间', 'Date and time'), 'decimal': ('小数', 'Decimal'), 'integer': ('整数', 'Whole number'), 'boolean': ('是否', 'Yes/no')})
_CATALOG = [   # what the operator picker lists: id, name, category, what it does (each as (中文, English))
    ('filter', ('数据过滤', 'Filter'), ('常用', 'Common'), ('按条件留下行；条件为假和条件为空删掉的行分开数', 'Keep the rows that meet a condition; rows dropped because the condition was false and because it was empty are counted apart')),
    ('fill_null', ('空值替换', 'Fill empty values'), ('清洗', 'Clean'), ('把空值换成常量、另一列或表达式算出的值', 'Replace empty values with a constant, another column or the result of an expression')),
    ('text_clean', ('文本清理', 'Clean text'), ('文本', 'Text'), ('去空格、合并空白、替换文字、统一大小写', 'Trim spaces, merge whitespace, replace text, unify case')),
    ('cast', ('字段转换', 'Convert type'), ('类型', 'Type'), ('转成日期、时间、小数、整数、是否；转不了的行数和清单都给出', 'Convert to date, date and time, decimal, whole number or yes/no; the count and list of rows that cannot be converted are given')),
    ('calc', ('计算列', 'Calculated column'), ('数值', 'Numbers'), ('用表达式加一列，或替换一列；可以先试算', 'Add a column with an expression, or replace one; you can try it first')),
    ('aggregate', ('分组统计', 'Group and calculate'), ('汇总', 'Summarize'), ('按几列分组，求和、计数、平均、中位数等，空值不计入', 'Group by some columns and take sums, counts, averages, medians and so on; empty values are not counted')),
    ('dedupe', ('排重', 'Remove duplicates'), ('清洗', 'Clean'), ('按主键去重，保留第一条或最后一条（要指定排序的列）', 'Remove duplicates by key, keeping the first or last row (name the column to order by)')),
    ('label', ('打标签', 'Add labels'), ('常用', 'Common'), ('把代码换成含义（读已确认的含义，或自己写对照表）', 'Replace codes with meanings (read the confirmed meanings, or write your own mapping)'))]


class _Catalog:
    """CATALOG iterates as (id, name, category, what it does) in the language of the request."""
    def __iter__(self):
        for key, name, category, what in _CATALOG:
            yield key, tr(*name), tr(*category), tr(*what)


CATALOG = _Catalog()


class OpError(ValueError):
    """An operator that cannot be run, in the words the person reads."""


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def new_context(meanings: dict | None = None, codes=frozenset(), unsent=frozenset(), ai=frozenset(), fan=frozenset()) -> dict:
    """What the operators may ask the workspace: meanings {"dataset.column": {label: [codes]}} (confirmed ones only), codes {"dataset.column"} (columns that are
    code lists, confirmed or not), unsent {"dataset.column"} (columns whose values a builder keeps from the model, or that a pipeline wrote from such columns), ai
    {"dataset.column"} (columns a pipeline wrote from what a model answered), fan {"dataset.column"} (columns a pipeline wrote from a figure a join repeated), and `used`, which the operators fill with the meanings they read."""
    return {'meanings': meanings or {}, 'codes': set(codes), 'unsent': set(unsent), 'ai': set(ai), 'fan': set(fan), 'used': set()}


FLAGS = ('unsent', 'ai')   # what a column made from other columns inherits: not to be sent to the model, written by the model


UPSTREAM = '__upstream'   # in `fan_agg`: the column was already worked out over a repeated join in the pipeline that wrote its dataset


def carry(*sources: dict) -> dict:
    """The marks a column made from these columns inherits: the flags of FLAGS, and `fan_agg`, the names of the aggregations (over a column a join repeated) it comes from;
    which of them really counted a row twice is known only once the run has measured it."""
    aggs = sorted({n for c in sources for n in c.get('fan_agg', ())})
    return {**{k: True for k in FLAGS if any(c.get(k) for c in sources)}, **({'fan_agg': aggs} if aggs else {})}


def visible(columns: list[dict]) -> list[dict]:
    return [c for c in columns if not c.get('hidden')]


def _by_name(columns: list[dict]) -> dict[str, dict]:
    return {c['name']: c for c in visible(columns)}


def _col(columns: list[dict], name, label: str, what: str = tr('列', 'column')) -> dict:
    found = _by_name(columns).get(name) if isinstance(name, str) else None
    if found is None:
        if name in (None, ''):
            raise OpError(tr(f'{label}：没选{what}', f'{label}: {what} not chosen'))
        near = difflib.get_close_matches(str(name), list(_by_name(columns)), n=3, cutoff=0.5)
        raise OpError(tr(f'{label}：没有{what}「{name}」', f'{label}: no {what} "{name}"') + (tr(f'，是不是{"、".join(f"「{n}」" for n in near)}？', f'. Did you mean {", ".join(f"\"{n}\"" for n in near)}?') if near else ''))
    return found


def _cols(columns: list[dict], names, label: str) -> list[dict]:
    if not isinstance(names, list) or not names or len(set(map(str, names))) != len(names):
        raise OpError(tr(f'{label}：要选一列或几列，不能重复', f'{label}: choose one or more columns, without repeating any'))
    return [_col(columns, n, label) for n in names]


def _new_name(columns: list[dict], name, label: str, replacing: str | None = None) -> str:
    if not isinstance(name, str) or not name.strip() or len(name) > NAME_LIMIT or '\n' in name or name.startswith('__'):
        raise OpError(tr(f'{label}：新列的名字要写 1 到 {NAME_LIMIT} 个字，不能换行，不能用 __ 开头', f'{label}: a new column name must be 1 to {NAME_LIMIT} characters, with no line break and not starting with __'))
    if name in _by_name(columns) and name != replacing:
        raise OpError(tr(f'{label}：已经有叫「{name}」的列', f'{label}: a column called "{name}" already exists'))
    return name


def _ref(col: dict) -> str:
    """A column as SQL reads it: a number as a number (the table keeps text), a yes/no as 1 or 0."""
    if col['type'] in NUMBER_TYPES:
        return f'CAST({_q(col["name"])} AS REAL)'
    return f'pl_bool({_q(col["name"])})' if col['type'] == 'boolean' else _q(col['name'])


def _blank(name: str, empty: bool = True) -> str:
    column = _q(name)
    return f"({column} IS NULL OR TRIM(CAST({column} AS TEXT)) = '')" if empty else f'({column} IS NULL)'


def _count(conn, table: str) -> int:
    return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


def _value(col: dict, raw, label: str, whole: bool = False):
    """A value written in a condition or a replacement, in the type of the column it meets. `whole`: an integer column takes only a whole number."""
    kind = col['type']
    if isinstance(raw, (dict, list)) or raw is None:
        raise OpError(tr(f'{label}：「{col["name"]}」要比较的值没有写', f'{label}: the value to compare "{col["name"]}" with is missing'))
    if kind in NUMBER_TYPES:
        try:
            number = float(str(raw).strip().replace(',', ''))
        except ValueError:
            raise OpError(tr(f'{label}：「{col["name"]}」是数字列，「{raw}」不是数字', f'{label}: "{col["name"]}" is a number column and "{raw}" is not a number')) from None
        if number != number or number in (float('inf'), float('-inf')):
            raise OpError(tr(f'{label}：「{raw}」不是一个数', f'{label}: "{raw}" is not a number'))
        if kind == 'integer' and whole and not number.is_integer():
            raise OpError(tr(f'{label}：「{col["name"]}」是整数列，不能填小数 {raw}', f'{label}: "{col["name"]}" is a whole-number column, so it cannot take the decimal {raw}'))
        return number
    if kind in ('date', 'datetime'):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}' + ('' if kind == 'date' else r'( \d{2}:\d{2}(:\d{2})?)?'), str(raw)):
            raise OpError(tr(f'{label}：「{col["name"]}」是{TYPE_WORD[EXPR_TYPE[kind]]}列，「{raw}」要写成 {"2026-05-03" if kind == "date" else "2026-05-03 或 2026-05-03 14:30:00"} 这样', f'{label}: "{col["name"]}" is a {TYPE_WORD[EXPR_TYPE[kind]]} column, so "{raw}" must be written like {"2026-05-03" if kind == "date" else "2026-05-03 or 2026-05-03 14:30:00"}'))
        return str(raw)
    if kind == 'boolean':
        text = str(raw).strip().lower()
        if text in ('true', '是', 'yes', 'y', '1'):
            return 1
        if text in ('false', '否', 'no', 'n', '0'):
            return 0
        raise OpError(tr(f'{label}：「{col["name"]}」是是否列，值要写 是 或 否', f'{label}: "{col["name"]}" is a yes/no column, so the value must be yes or no'))
    return str(raw)


# --- filter -------------------------------------------------------------------------------------------------------------------------------------------

def _meaning_codes(col: dict, wanted, ctx: dict, label: str) -> list[str]:
    known = ctx['meanings'].get(col.get('origin'))
    if not known:
        raise OpError(tr(f'{label}：「{col["name"]}」还没有已确认的含义，不能按含义选；先给这一列写含义并确认，或直接写代码值', f'{label}: "{col["name"]}" has no confirmed meanings, so you cannot choose by meaning. Write and confirm meanings for this column first, or write the code values directly'))
    codes = []
    for name in ([wanted] if isinstance(wanted, str) else wanted if isinstance(wanted, list) else []):
        if not isinstance(name, str) or name not in known:
            raise OpError(tr(f'{label}：「{col["name"]}」已确认的含义里没有「{name}」，有：{"、".join(known)}', f'{label}: "{col["name"]}" has no confirmed meaning "{name}". It has: {", ".join(known)}'))
        codes += known[name]
    if not codes:
        raise OpError(tr(f'{label}：要写含义的名字', f'{label}: write the name of the meaning'))
    ctx['used'].add(col['origin'])
    return codes


def _condition(node, columns, ctx, label) -> tuple[str, list]:
    col = _col(columns, node.get('column'), label)
    cmp = node.get('cmp')
    if not isinstance(cmp, str):
        raise OpError(tr(f'{label}：条件里的比较方式（cmp）要写成文字', f'{label}: the comparison in a condition (cmp) must be written as text'))
    ref = _ref(col)
    if cmp in ('is_null', 'not_null'):
        sql = _blank(col['name'])
        return (sql if cmp == 'is_null' else f'(NOT {sql})'), []
    if 'meaning' in node or 'meanings' in node:
        if cmp not in ('eq', 'ne', 'in'):
            raise OpError(tr(f'{label}：按含义选只能用 等于、不等于、属于', f'{label}: choosing by meaning only works with equals, does not equal and is one of'))
        codes = [_value(col, c, label) for c in _meaning_codes(col, node.get('meaning', node.get('meanings')), ctx, label)]
        marks = ', '.join('?' * len(codes))
        return (f'({ref} NOT IN ({marks}))' if cmp == 'ne' else f'({ref} IN ({marks}))'), codes
    if cmp in CMPS:
        return f'({ref} {CMPS[cmp]} ?)', [_value(col, node.get('value'), label)]
    if cmp == 'in':
        values = node.get('values')
        if not isinstance(values, list) or not values or len(values) > MAX_LIST:
            raise OpError(tr(f'{label}：属于要写一组值（最多 {MAX_LIST} 个）', f'{label}: "is one of" needs a list of values (at most {MAX_LIST})'))
        return f'({ref} IN ({", ".join("?" * len(values))}))', [_value(col, v, label) for v in values]
    if cmp == 'between':
        low, high = _value(col, node.get('low'), label), _value(col, node.get('high'), label)
        return f'({ref} BETWEEN ? AND ?)', [low, high]
    raise OpError(tr(f'{label}：条件「{cmp}」不认识，可用：{"、".join([*CMPS, "in", "between", "is_null", "not_null"])}', f'{label}: the condition "{cmp}" is not recognised. You can use: {", ".join([*CMPS, "in", "between", "is_null", "not_null"])}'))


def _where(node, columns, ctx, label, depth=0, counter=None) -> tuple[str, list]:
    counter = counter if counter is not None else [0]
    if not isinstance(node, dict):
        raise OpError(tr(f'{label}：条件要写成 {{"column": …, "cmp": …, "value": …}} 或 {{"all": […]}} / {{"any": […]}}', f'{label}: write the condition as {{"column": ..., "cmp": ..., "value": ...}} or {{"all": [...]}} / {{"any": [...]}}'))
    if 'all' in node or 'any' in node:
        mode = 'all' if 'all' in node else 'any'
        items = node[mode]
        if depth >= MAX_GROUP_DEPTH or not isinstance(items, list) or not items:
            raise OpError(tr(f'{label}：条件组里要有条件，最多套 {MAX_GROUP_DEPTH} 层', f'{label}: a condition group needs conditions and can nest at most {MAX_GROUP_DEPTH} levels'))
        parts = [_where(item, columns, ctx, label, depth + 1, counter) for item in items]
        return '(' + (' AND ' if mode == 'all' else ' OR ').join(s for s, _ in parts) + ')', [x for _, p in parts for x in p]
    counter[0] += 1
    if counter[0] > MAX_CONDITIONS:
        raise OpError(tr(f'{label}：一个过滤最多 {MAX_CONDITIONS} 个条件', f'{label}: a filter can have at most {MAX_CONDITIONS} conditions'))
    return _condition(node, columns, ctx, label)


def _filter(op, src, columns, ctx, label):
    cond, params = _where(op.get('where'), columns, ctx, label)
    select = f'SELECT {", ".join(_q(c["name"]) for c in columns)} FROM {src} WHERE {cond}'

    def measure(conn, src, out):
        nulls, false = conn.execute(f'SELECT COALESCE(SUM(({cond}) IS NULL), 0), COALESCE(SUM(({cond}) = 0), 0) FROM {src}', params + params).fetchone()
        return {'dropped_false': false, 'dropped_null': nulls, 'affected': false + nulls,
                'text': tr(f'条件为假删掉 {false} 行；条件为空删掉 {nulls} 行', f'{false} rows dropped because the condition was false; {nulls} rows dropped because it was empty') + (tr('（这些行的条件字段是空的，不是不满足）', ' (the condition column is empty in these rows, which is not the same as not meeting it)') if nulls else '')}
    return {'columns': columns, 'select': select, 'params': params, 'measure': measure}


# --- fill_null, text_clean ----------------------------------------------------------------------------------------------------------------------------

def _fill_null(op, src, columns, ctx, label):
    chosen = _cols(columns, op.get('columns'), label)
    how = op.get('with')
    if not isinstance(how, dict) or sum(k in how for k in ('constant', 'column', 'expression')) != 1:
        raise OpError(tr(f'{label}：要写用什么替换：{{"constant": 值}}、{{"column": 另一列}} 或 {{"expression": 表达式}} 三选一', f'{label}: say what to replace with, choosing one of {{"constant": value}}, {{"column": another column}} or {{"expression": expression}}'))
    empty = bool(op.get('empty_as_null'))
    replaced, read = {}, {}   # what each chosen column is filled with, and the columns that value is read from (its marks go with it)
    for col in chosen:
        if 'constant' in how:
            replaced[col['name']] = ('?', [_value(col, how['constant'], label, whole=True)])
        elif 'column' in how:
            other = _col(columns, how['column'], label)
            if EXPR_TYPE[other['type']] != EXPR_TYPE[col['type']]:
                raise OpError(tr(f'{label}：「{col["name"]}」是{TYPE_WORD[EXPR_TYPE[col["type"]]]}，「{other["name"]}」是{TYPE_WORD[EXPR_TYPE[other["type"]]]}，不能互相替换', f'{label}: "{col["name"]}" is {TYPE_WORD[EXPR_TYPE[col["type"]]]} and "{other["name"]}" is {TYPE_WORD[EXPR_TYPE[other["type"]]]}, so one cannot replace the other'))
            replaced[col['name']] = (_q(other['name']), [])
            read[col['name']] = [other]
        else:
            result = compile_expression(how['expression'], [{'name': c['name'], 'type': c['type']} for c in visible(columns)], EXPR_TYPE[col['type']])
            if not result['ok']:
                raise OpError(tr(f'{label}：表达式不对：{result["errors"][0]["message"]}', f'{label}: the expression is wrong: {result["errors"][0]["message"]}'))
            replaced[col['name']] = (result['sql'], result['params'])
            read[col['name']] = [_by_name(columns)[f] for f in result['fields']]
    selects, params, out_columns = [], [], []
    for c in columns:
        if c['name'] in replaced:
            sql, p = replaced[c['name']]
            selects.append(f'CASE WHEN {_blank(c["name"], empty)} THEN {sql} ELSE {_q(c["name"])} END AS {_q(c["name"])}')
            params += p
            out_columns.append({**c, 'badge': 'replaced', **carry(c, *read.get(c['name'], []))})   # the rows that were empty now hold a value read from those columns
        else:
            selects.append(_q(c['name']))
            out_columns.append(c)

    def measure(conn, src, out):
        sums = ', '.join(f'COALESCE(SUM({_blank(c["name"], empty)}), 0)' for c in chosen)
        row = conn.execute(f'SELECT {sums}, COALESCE(SUM({" OR ".join(_blank(c["name"], empty) for c in chosen)}), 0) FROM {src}').fetchone()
        return {'by_column': {c['name']: n for c, n in zip(chosen, row)}, 'affected': row[-1], 'text': tr(f'{row[-1]} 行里至少有一列被替换', f'{row[-1]} rows had at least one column replaced')}
    return {'columns': out_columns, 'select': f'SELECT {", ".join(selects)} FROM {src}', 'params': params, 'measure': measure}


CLEAN_FUNCTION = {'trim': 'pl_trim', 'whitespace': 'pl_ws', 'upper': 'pl_upper', 'lower': 'pl_lower'}


def _clean_steps(steps, label) -> list[tuple[str, list]]:
    if not isinstance(steps, list) or not steps or len(steps) > 10:
        raise OpError(tr(f'{label}：要写 1 到 10 个清理动作', f'{label}: write 1 to 10 clean-up actions'))
    out = []
    for step in steps:
        what = step.get('do') if isinstance(step, dict) else None
        if not isinstance(what, str):
            raise OpError(tr(f'{label}：清理动作只有 trim、whitespace、replace、upper、lower', f'{label}: the clean-up actions are trim, whitespace, replace, upper and lower'))
        if what in CLEAN_FUNCTION:
            out.append((f'{CLEAN_FUNCTION[what]}(%s)', []))
        elif what == 'replace':
            find, with_ = step.get('find'), step.get('with', '')
            if not isinstance(find, str) or not find or not isinstance(with_, str):
                raise OpError(tr(f'{label}：替换要写要找的文字（find）和换成什么（with，可以是空）', f'{label}: a replace needs the text to find (find) and what to put instead (with, which can be empty)'))
            if step.get('regex'):
                raise OpError(tr(f'{label}：替换只按原样的文字找，不支持正则', f'{label}: replace finds the text exactly as written and does not support regular expressions'))
            out.append(('pl_replace(%s, ?, ?)', [find, with_]))   # the find text is literal: a person's pattern never runs (a backtracking regex cannot be interrupted)
        else:
            raise OpError(tr(f'{label}：清理动作只有 trim、whitespace、replace、upper、lower', f'{label}: the clean-up actions are trim, whitespace, replace, upper and lower'))
    return out


def _text_clean(op, src, columns, ctx, label):
    chosen = _cols(columns, op.get('columns'), label)
    for c in chosen:
        if c['type'] not in ('text', 'month'):
            raise OpError(tr(f'{label}：「{c["name"]}」是{TYPE_WORD[EXPR_TYPE[c["type"]]]}列，文本清理只用在文本列上', f'{label}: "{c["name"]}" is a {TYPE_WORD[EXPR_TYPE[c["type"]]]} column, and text clean-up only works on text columns'))
    steps = _clean_steps(op.get('steps'), label)
    rewritten = {}
    for c in chosen:
        sql, params = _q(c['name']), []
        for template, p in steps:
            sql, params = template % sql, params + p   # the inner expression's parameters come first: they stand first in the text
        rewritten[c['name']] = (sql, params)
    selects, params, out_columns = [], [], []
    for c in columns:
        if c['name'] in rewritten:
            selects.append(f'{rewritten[c["name"]][0]} AS {_q(c["name"])}')
            params += rewritten[c['name']][1]
            out_columns.append({**c, 'badge': 'replaced'})
        else:
            selects.append(_q(c['name']))
            out_columns.append(c)

    def measure(conn, src, out):
        changed = [f'({sql}) IS NOT {_q(name)}' for name, (sql, _) in rewritten.items()]
        every = [x for _, p in rewritten.values() for x in p]
        row = conn.execute(f'SELECT {", ".join(f"COALESCE(SUM({c}), 0)" for c in changed)}, COALESCE(SUM({" OR ".join(changed)}), 0) FROM {src}', every * 2).fetchone()
        return {'by_column': dict(zip(rewritten, row)), 'affected': row[-1], 'text': tr(f'{row[-1]} 行有文字被改', f'{row[-1]} rows had text changed')}
    return {'columns': out_columns, 'select': f'SELECT {", ".join(selects)} FROM {src}', 'params': params, 'measure': measure}


# --- cast ---------------------------------------------------------------------------------------------------------------------------------------------

def _cast(op, src, columns, ctx, label):
    col = _col(columns, op.get('column'), label)
    to = op.get('to')
    if not isinstance(to, str) or to not in CAST_TYPES:
        raise OpError(tr(f'{label}：转成什么类型要写 {"、".join(CAST_TYPES)} 之一', f'{label}: say which type to convert to, one of {", ".join(CAST_TYPES)}'))
    fmt, thousands = op.get('format'), bool(op.get('thousands'))
    if fmt is not None:
        if to not in ('date', 'datetime') or not isinstance(fmt, str):
            raise OpError(tr(f'{label}：格式只用在转日期和日期时间上，写成 YYYY-MM-DD 这样', f'{label}: a format only applies when converting to date or date and time, written like YYYY-MM-DD'))
        try:
            format_regex(fmt)
        except ValueError as exc:
            raise OpError(tr(f'{label}：日期格式「{fmt}」不对：{exc}', f'{label}: the date format "{fmt}" is wrong: {exc}')) from None
    if thousands and to not in ('decimal', 'integer'):
        raise OpError(tr(f'{label}：千分位只用在转小数和整数上', f'{label}: a thousands separator only applies when converting to decimal or whole number'))
    target = _new_name(columns, op.get('as', col['name']), label, replacing=col['name'])
    ref = _q(col['name'])
    sql, params = {'decimal': ('pl_to_decimal(%s, ?)', [int(thousands)]), 'integer': ('pl_to_integer(%s, ?)', [int(thousands)]), 'boolean': ('pl_to_boolean(%s)', []),
                   'date': ('pl_to_date(%s, ?)', [fmt]), 'datetime': ('pl_to_datetime(%s, ?)', [fmt])}[to]
    convert = sql % ref
    new = {'name': target, 'type': to, 'badge': 'replaced' if target == col['name'] else 'new', **carry(col)}
    out_columns = [new if c['name'] == col['name'] and target == col['name'] else c for c in columns] + ([] if target == col['name'] else [new])
    selects, select_params = [], []
    for c in out_columns:
        if c is new:
            selects.append(f'{convert} AS {_q(target)}')
            select_params += params
        else:
            selects.append(_q(c['name']))
    stop = op.get('on_failure') == 'stop'
    bad = f"{ref} IS NOT NULL AND TRIM(CAST({ref} AS TEXT)) <> '' AND ({convert}) IS NULL"

    def measure(conn, src, out):
        failures = conn.execute(f'SELECT COUNT(*) FROM {src} WHERE {bad}', params).fetchone()[0]
        failed = [{'row': r, 'value': v} for r, v in conn.execute(f'SELECT rowid, {ref} FROM {src} WHERE {bad} ORDER BY rowid LIMIT {EXAMPLES}', params)]
        filled = conn.execute(f"SELECT COUNT(*) FROM {src} WHERE {ref} IS NOT NULL AND TRIM(CAST({ref} AS TEXT)) <> ''").fetchone()[0]
        text = tr(f'{failures} 行无法转成{CAST_TYPES[to]}，这些行的「{target}」是空的', f'{failures} rows could not be converted to {CAST_TYPES[to]}, and "{target}" is empty in those rows') if failures else tr(f'{filled} 行都转成了{CAST_TYPES[to]}', f'{filled} rows were all converted to {CAST_TYPES[to]}')
        return {'failures': failures, 'failed': failed, 'affected': filled - failures, 'text': text,
                **({'halt': tr(f'{label}：{failures} 行无法转成{CAST_TYPES[to]}，按要求停下来了', f'{label}: {failures} rows could not be converted to {CAST_TYPES[to]}, so it stopped as asked')} if stop and failures else {})}
    return {'columns': out_columns, 'select': f'SELECT {", ".join(selects)} FROM {src}', 'params': select_params, 'measure': measure}


# --- calc ---------------------------------------------------------------------------------------------------------------------------------------------

def shift_notices(conn, src: str, result_sql: str, params: list, fields: list[dict], truncates: bool) -> list[dict]:
    """A date made from another date, set against its source: every row early or late by the same days, or (for a week or month start) later than the source."""
    notices = []
    for f in fields[:3]:
        source = _q(f['name'])
        diff = (f"(CAST(strftime('%s', {result_sql}) AS INTEGER) - CAST(strftime('%s', {source}) AS INTEGER)) / 86400.0")
        n, low, high, later = conn.execute(f'SELECT COUNT(*), MIN(d), MAX(d), COALESCE(SUM(d > 0), 0) FROM (SELECT {diff} AS d FROM {src} '
                                           f'WHERE ({result_sql}) IS NOT NULL AND {source} IS NOT NULL)', params + params).fetchone()
        if n and low == high and round(low, 4) != 0:
            days = int(round(abs(low)))
            notices.append({'kind': 'date_shift', 'field': f['name'], 'days': round(low), 'rows': n,
                            'text': tr(f'每行都比来源「{f["name"]}」{"晚" if low > 0 else "早"} {days} 天（共 {n} 行）：如果不是有意移的，检查表达式', f'Every row is {days} days {"later" if low > 0 else "earlier"} than the source "{f["name"]}" ({n} rows in all): if that is not intended, check the expression')})
        elif truncates and later:
            notices.append({'kind': 'later_than_source', 'field': f['name'], 'rows': later,
                            'text': tr(f'{later} 行取出来的周（月）起始日比来源「{f["name"]}」还晚：起始日不可能晚于原日期，表达式可能移错了', f'For {later} rows the start of the week (month) it gives is later than the source "{f["name"]}": a start date cannot be later than the original date, so the expression may be shifted wrongly')})
    return notices


def _calc(op, src, columns, ctx, label):
    name = op.get('name')
    existing = _by_name(columns).get(name) if isinstance(name, str) else None
    replacing = bool(op.get('replace'))
    if existing is not None and not replacing:
        raise OpError(tr(f'{label}：已经有叫「{name}」的列；要替换它，写 "replace": true', f'{label}: a column called "{name}" already exists. To replace it, write "replace": true'))
    _new_name(columns, name, label, replacing=name if replacing else None)
    declared = op.get('type')
    if declared is not None and declared not in ('decimal', 'text', 'date', 'datetime', 'boolean'):
        raise OpError(tr(f'{label}：列的类型只能是 decimal、text、date、datetime、boolean（要整数，在表达式里用 round(x, 0)）', f'{label}: the column type can only be decimal, text, date, datetime or boolean (for a whole number, use round(x, 0) in the expression)'))
    if op.get('english_name') is not None and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}', str(op['english_name'])):
        raise OpError(tr(f'{label}：英文名只能用字母、数字和下划线，字母开头', f'{label}: an English name can only use letters, digits and underscores, and must start with a letter'))
    inputs = [{'name': c['name'], 'type': c['type']} for c in visible(columns)]
    result = compile_expression(op.get('expression'), inputs, EXPR_TYPE[declared] if declared else None)
    if not result['ok']:
        raise OpError(tr(f'{label}：表达式不对：{result["errors"][0]["message"]}', f'{label}: the expression is wrong: {result["errors"][0]["message"]}') + (tr(f'（第 {result["errors"][0]["pos"] + 1} 个字符）', f' (character {result["errors"][0]["pos"] + 1})') if result['errors'][0]['pos'] else ''))
    by_name = {c['name']: c for c in inputs}
    sources = [by_name[f] for f in result['fields'] if by_name[f]['type'] in ('date', 'datetime')]
    new = {'name': name, 'type': COLUMN_TYPE[result['type']], 'badge': 'replaced' if existing else 'new', **carry(*(_by_name(columns)[f] for f in result['fields'])),
           **({'english_name': op['english_name']} if op.get('english_name') else {})}
    selects, params, out_columns = [], [], []
    for c in columns:
        if existing is not None and c['name'] == name:
            selects.append(f'{result["sql"]} AS {_q(name)}')
            params += result['params']
            out_columns.append(new)
        else:
            selects.append(_q(c['name']))
            out_columns.append(c)
    if existing is None:
        selects.append(f'{result["sql"]} AS {_q(name)}')
        params += result['params']
        out_columns.append(new)
    failing, failing_params = error_condition(result['sql'], result['params'], result['fields'])

    def measure(conn, src, out):
        errors = conn.execute(f'SELECT COUNT(*) FROM {src} WHERE {failing}', failing_params).fetchone()[0]
        rows = [r[0] for r in conn.execute(f'SELECT rowid FROM {src} WHERE {failing} ORDER BY rowid LIMIT 5', failing_params)]
        notices = shift_notices(conn, src, result['sql'], result['params'], sources, result['truncates']) if new['type'] in ('date', 'datetime') else []
        total = _count(conn, src)
        return {'errors': errors, 'error_rows': rows, 'notices': notices, 'affected': total - errors,
                'text': tr(f'{errors} 行算不出结果（字段都有值，结果却是空：除以 0、日期不对）', f'{errors} rows have no result (every input has a value but the result is empty: division by 0, an invalid date)') if errors else tr(f'{total} 行都算出了结果', f'{total} rows all got a result')}
    return {'columns': out_columns, 'select': f'SELECT {", ".join(selects)} FROM {src}', 'params': params, 'measure': measure}


# --- aggregate ----------------------------------------------------------------------------------------------------------------------------------------

def aggregation_options(columns: list[dict], codes=frozenset()) -> dict[str, list[str]]:
    """{column: the aggregations it may have}: every column may be counted, counted distinct, and have its min and max; a number is also summed, averaged and
    given a median and quartiles, unless it is a code column, whose values mean something other than an amount."""
    out = {}
    for c in visible(columns):
        numeric = c['type'] in NUMBER_TYPES and c.get('origin') not in codes
        out[c['name']] = [f for f in AGGREGATIONS if numeric or f not in NUMERIC_ONLY]
    return out


def _aggregate_sql(fn: str, col: dict | None) -> tuple[str, list, str]:
    """(SQL, parameters, the type of the result) of one aggregation: nulls are ignored by all of them, a group with only nulls has an empty result except for counts."""
    if col is None:
        return 'COUNT(*)', [], 'integer'
    q = _q(col['name'])
    if fn == 'count':
        return f'COUNT({q})', [], 'integer'
    if fn == 'count_distinct':
        return f'COUNT(DISTINCT {q})', [], 'integer'
    if fn in ('min', 'max'):
        return f'{fn.upper()}({_ref(col)})', [], col['type']
    if fn == 'sum':
        return (f'SUM(CAST({q} AS INTEGER))', [], 'integer') if col['type'] == 'integer' else (f'ROUND(SUM(CAST({q} AS REAL)), 6)', [], 'decimal')
    if fn == 'avg':
        return f'AVG(CAST({q} AS REAL))', [], 'decimal'
    return f'pl_pct(CAST({q} AS REAL), ?)', [PERCENTILE[fn]], 'decimal'


def _aggregate(op, src, columns, ctx, label):
    groups = op.get('group_by') or []
    group_cols = _cols(columns, groups, label) if groups else []
    wanted = op.get('aggregations')
    if not isinstance(wanted, list) or not wanted or len(wanted) > 30:
        raise OpError(tr(f'{label}：要写至少一个统计：{{"fn": "sum", "column": …, "as": …}}', f'{label}: write at least one calculation: {{"fn": "sum", "column": ..., "as": ...}}'))
    options = aggregation_options(columns, ctx['codes'])
    used, aggs = {c['name'] for c in group_cols}, []
    for item in wanted:
        fn = item.get('fn') if isinstance(item, dict) else None
        if not isinstance(fn, str) or fn not in AGGREGATIONS:
            raise OpError(tr(f'{label}：统计方式要是 {"、".join(AGGREGATIONS)} 之一', f'{label}: the calculation must be one of {", ".join(AGGREGATIONS)}'))
        col = _col(columns, item.get('column'), label) if item.get('column') is not None else None
        if col is None and fn != 'count':
            raise OpError(tr(f'{label}：{AGGREGATIONS[fn]}要指定哪一列', f'{label}: {AGGREGATIONS[fn]} needs a column'))
        if col is not None and fn not in options[col['name']]:
            if col.get('origin') in ctx['codes'] and col['type'] in NUMBER_TYPES:
                raise OpError(tr(f'{label}：「{col["name"]}」是代码列，把代码{AGGREGATIONS[fn]}没有意义；可以用计数或去重计数', f'{label}: "{col["name"]}" is a code column, so applying {AGGREGATIONS[fn]} to codes means nothing. Use Count or Count distinct'))
            raise OpError(tr(f'{label}：「{col["name"]}」是{TYPE_WORD[EXPR_TYPE[col["type"]]]}列，不能{AGGREGATIONS[fn]}；可以用：{"、".join(AGGREGATIONS[f] for f in options[col["name"]])}', f'{label}: "{col["name"]}" is a {TYPE_WORD[EXPR_TYPE[col["type"]]]} column and cannot be used with {AGGREGATIONS[fn]}. You can use: {", ".join(AGGREGATIONS[f] for f in options[col["name"]])}'))
        sql, params, kind = _aggregate_sql(fn, col)
        name = _agg_name(item, fn, col, used, label)
        used.add(name)
        aggs.append({'fn': fn, 'col': col, 'name': name, 'sql': sql, 'params': params, 'type': kind})
    selects = [_q(c['name']) for c in group_cols] + [f'{a["sql"]} AS {_q(a["name"])}' for a in aggs]
    params = [p for a in aggs for p in a['params']]
    group_by = f' GROUP BY {", ".join(_q(c["name"]) for c in group_cols)}' if group_cols else ''
    out_columns = [{'name': c['name'], 'type': c['type'], **({'origin': c['origin']} if c.get('origin') else {}), **carry(c)} for c in group_cols] + \
                  [{'name': a['name'], 'type': a['type'], 'badge': 'new', **_fanned(a), 'aggregation': {'fn': a['fn'], 'column': a['col']['name'] if a['col'] else None, 'exact': a['fn'] in PERCENTILE}} for a in aggs]

    def measure(conn, src, out):
        doubled = [d for a in aggs for d in _double_counted(conn, src, group_cols, a)]
        return {'groups': _count(conn, out), 'double_counted': doubled, 'affected': _count(conn, src),
                'text': tr('空值不计入；一组里全是空值的，结果为空（计数除外）', 'Empty values are not counted; a group with only empty values has an empty result (except Count)') + (tr(f'。有 {len(doubled)} 项统计把同一行算了不止一次', f'. {len(doubled)} calculations count the same row more than once') if doubled else '')}
    return {'columns': out_columns, 'select': f'SELECT {", ".join(selects)} FROM {src}{group_by}', 'params': params, 'measure': measure}


def _fanned(agg: dict) -> dict:
    """The marks an aggregated column starts with: those of the column it reads, and its own name in `fan_agg` when it adds, averages or counts a column a join repeated."""
    col = agg['col']
    if col is None:
        return {}
    marks = carry(col)
    if agg['fn'] in ('sum', 'avg', 'count') and col.get('fan'):
        marks = {**marks, 'fan_agg': sorted({*marks.get('fan_agg', []), agg['name']})}
    return marks


def _agg_name(item: dict, fn: str, col: dict | None, used: set, label: str) -> str:
    name = item.get('as') or (f'{AGGREGATIONS[fn]}_{col["name"]}' if col else tr('行数', 'row_count'))
    if not isinstance(name, str) or not name.strip() or len(name) > NAME_LIMIT or name.startswith('__') or name in used:
        raise OpError(tr(f'{label}：统计结果的名字「{name}」不能为空、不能重复、不能用 __ 开头', f'{label}: the name "{name}" of a result cannot be empty, repeated or start with __'))
    return name


def _double_counted(conn, src: str, group_cols: list[dict], agg: dict) -> list[dict]:
    """For a sum, average or count of a column that a join repeated (its rows were multiplied by matches on the other side): the groups where the figure
    differs from the one counting each source row once, with both. `fan` on the column names the hidden columns that identify its source rows."""
    col = agg['col']
    if agg['fn'] not in ('sum', 'avg', 'count') or col is None or not col.get('fan'):
        return []
    keys = [_q(c['name']) for c in group_cols]
    tags = [_q(t) for t in col['fan']]
    value = _q(col['name'])
    expr = {'sum': 'ROUND(SUM(CAST(v AS REAL)), 6)', 'avg': 'AVG(CAST(v AS REAL))', 'count': 'COUNT(v)'}[agg['fn']]
    groups = ', '.join(f'{k} AS g{i}' for i, k in enumerate(keys))
    once = f'SELECT {groups + ", " if groups else ""}{", ".join(tags)}, MIN({value}) AS v FROM {src} GROUP BY {", ".join(keys + tags)}'
    every = f'SELECT {groups + ", " if groups else ""}{value} AS v FROM {src}'
    by = ', '.join(f'g{i}' for i in range(len(keys)))
    pick = (by + ', ') if by else ''
    group_by = f' GROUP BY {by}' if by else ''
    joined = ' AND '.join(f'w.g{i} IS t.g{i}' for i in range(len(keys))) or '1 = 1'
    sql = (f'SELECT {", ".join(f"w.g{i}" for i in range(len(keys)))}{", " if keys else ""}w.x, t.x FROM '
           f'(SELECT {pick}{expr} AS x FROM ({every}){group_by}) AS w JOIN '
           f'(SELECT {pick}{expr} AS x FROM ({once}){group_by}) AS t ON {joined} WHERE w.x IS NOT t.x ORDER BY ABS(w.x - t.x) DESC')
    rows = conn.execute(sql).fetchall()
    if not rows:
        return []
    names = [c['name'] for c in group_cols]
    return [{'column': col['name'], 'as': agg['name'], 'fn': agg['fn'], 'groups': len(rows),
             'examples': [{'group': dict(zip(names, r[:len(names)])), 'with': _round(r[-2]), 'true': _round(r[-1])} for r in rows[:EXAMPLES]]}]


def _round(value):
    return None if value is None else int(value) if float(value).is_integer() else round(float(value), 4)


# --- dedupe, label ------------------------------------------------------------------------------------------------------------------------------------

def _dedupe(op, src, columns, ctx, label):
    keys = _cols(columns, op.get('keys'), label) if op.get('keys') else []
    keep = op.get('keep', 'first')
    if keep not in ('first', 'last'):
        raise OpError(tr(f'{label}：保留 first（第一条）还是 last（最后一条）', f'{label}: say whether to keep first or last'))
    names = ', '.join(_q(c['name']) for c in columns)
    if not keys:   # the whole row (the columns a person sees): identical rows are the same row, whichever is kept
        select = f'SELECT {names} FROM {src} WHERE rowid IN (SELECT MIN(rowid) FROM {src} GROUP BY {", ".join(_q(c["name"]) for c in visible(columns))})'
        measure = lambda conn, src, out: {'dropped': _count(conn, src) - _count(conn, out), 'affected': _count(conn, src) - _count(conn, out), 'text': tr('整行完全一样的只留一行', 'Only one of each fully identical row is kept')}
        return {'columns': columns, 'select': select, 'params': [], 'measure': measure}
    order = _col(columns, op.get('order_by'), label, tr('排序的列', 'order-by column')) if op.get('order_by') else None
    if order is None:
        raise OpError(tr(f'{label}：按主键排重要指定按哪一列排先后（order_by），否则留哪一条是不确定的', f'{label}: removing duplicates by key needs the column to order by (order_by), otherwise which row is kept is not defined'))
    part = ', '.join(_q(c['name']) for c in keys)
    ref = _ref(order)
    direction = '' if keep == 'first' else ' DESC'
    blank = ' OR '.join(_blank(c['name']) for c in keys)
    select = (f'SELECT {names} FROM (SELECT {names}, ROW_NUMBER() OVER (PARTITION BY {part} ORDER BY ({ref} IS NULL), {ref}{direction}, rowid{direction}) AS __rn, '
              f'({blank}) AS __blank FROM {src}) WHERE __rn = 1 OR __blank')
    filled = ' AND '.join(f'NOT {_blank(c["name"])}' for c in keys)

    def measure(conn, src, out):
        total, kept = _count(conn, src), _count(conn, out)
        repeated = conn.execute(f'SELECT {part}, COUNT(*) AS n FROM {src} WHERE {filled} GROUP BY {part} HAVING n > 1 ORDER BY n DESC, {part} LIMIT 3').fetchall()
        blank_rows = conn.execute(f'SELECT COUNT(*) FROM {src} WHERE {blank}').fetchone()[0]
        return {'dropped': total - kept, 'affected': total - kept, 'blank_key_rows_kept': blank_rows,
                'examples': [{'key': dict(zip([c["name"] for c in keys], r[:-1])), 'rows': r[-1]} for r in repeated],
                'text': tr(f'去掉 {total - kept} 行，每个主键留{"最早" if keep == "first" else "最晚"}的一行（按「{order["name"]}」）', f'Removed {total - kept} rows, keeping the {"earliest" if keep == "first" else "latest"} row of each key (by "{order["name"]}")') + (tr(f'；{blank_rows} 行主键是空的，没有去重', f'; {blank_rows} rows have an empty key and were not deduplicated') if blank_rows else '')}
    return {'columns': columns, 'select': select, 'params': [], 'measure': measure}


def _label(op, src, columns, ctx, label):
    col = _col(columns, op.get('column'), label)
    mapping = {}
    table = op.get('mapping') or []
    if not isinstance(table, list):
        raise OpError(tr(f'{label}：对照表（mapping）要写成一组 {{"value": 代码, "label": 含义}}', f'{label}: the mapping must be a list of {{"value": code, "label": meaning}}'))
    for item in table:
        if not isinstance(item, dict) or not isinstance(item.get('label'), str) or not item['label'].strip() or item.get('value') is None:
            raise OpError(tr(f'{label}：对照表每一行要写 {{"value": 代码, "label": 含义}}', f'{label}: each row of the mapping must be {{"value": code, "label": meaning}}'))
        value = str(item['value'])
        if value in mapping:
            raise OpError(tr(f'{label}：代码 {value} 写了两个含义', f'{label}: the code {value} has two meanings'))
        mapping[value] = item['label']
    if op.get('from_meaning'):
        known = ctx['meanings'].get(col.get('origin'))
        if not known:
            raise OpError(tr(f'{label}：「{col["name"]}」还没有已确认的含义，不能直接读；先给这一列写含义并确认，或自己写对照表', f'{label}: "{col["name"]}" has no confirmed meanings, so they cannot be read directly. Write and confirm meanings for this column first, or write your own mapping'))
        ctx['used'].add(col['origin'])
        for name, codes in known.items():
            for code in codes:
                mapping.setdefault(code, name)
    if not mapping or len(mapping) > MAX_LIST:
        raise OpError(tr(f'{label}：要有对照（mapping）或读已确认的含义（from_meaning），最多 {MAX_LIST} 条', f'{label}: give a mapping or read the confirmed meanings (from_meaning), at most {MAX_LIST} entries'))
    target = _new_name(columns, op.get('as', col['name']), label, replacing=col['name'])
    unmapped = op.get('unmapped', 'null')
    if unmapped not in ('null', 'keep', 'other') or (unmapped == 'other' and not isinstance(op.get('other'), str)):
        raise OpError(tr(f'{label}：对不上的代码怎么办：null（留空）、keep（留原值）或 other（写成 other 指定的文字）', f'{label}: say what to do with codes that match nothing: null (leave empty), keep (keep the original) or other (write the text given in other)'))
    text = f'pl_text({_q(col["name"])})'
    whens = ' '.join('WHEN ? THEN ?' for _ in mapping)
    params = [x for pair in mapping.items() for x in pair]
    otherwise = {'null': ('', []), 'keep': (f' ELSE {text}', []), 'other': (' ELSE ?', [op.get('other')])}[unmapped]
    new = {'name': target, 'type': 'text', 'badge': 'replaced' if target == col['name'] else 'new', **carry(col)}
    selects, select_params, out_columns = [], [], []
    for c in columns:
        if c['name'] == target:
            selects.append(f'CASE {text} {whens}{otherwise[0]} END AS {_q(target)}')
            select_params += params + otherwise[1]
            out_columns.append(new)
        else:
            selects.append(_q(c['name']))
            out_columns.append(c)
    if target != col['name']:
        selects.append(f'CASE {text} {whens}{otherwise[0]} END AS {_q(target)}')
        select_params += params + otherwise[1]
        out_columns.append(new)
    mapped = list(mapping)

    def measure(conn, src, out):
        where = f'{_q(col["name"])} IS NOT NULL AND {text} NOT IN ({", ".join("?" * len(mapped))})'
        rows = conn.execute(f'SELECT {text}, COUNT(*) FROM {src} WHERE {where} GROUP BY {text} ORDER BY 2 DESC, 1 LIMIT {EXAMPLES}', mapped).fetchall()
        count = conn.execute(f'SELECT COUNT(*) FROM {src} WHERE {where}', mapped).fetchone()[0]
        return {'unmapped_rows': count, 'unmapped_values': [{'value': v, 'rows': n} for v, n in rows], 'affected': _count(conn, src) - count,
                'text': tr(f'{count} 行的值没有对应的含义', f'{count} rows have a value with no matching meaning') + ('，' + {'null': tr('这些行的新列是空的', 'the new column is empty in these rows'), 'keep': tr('保留了原值', 'the original value was kept'), 'other': tr(f'写成了「{op.get("other")}」', f'written as "{op.get("other")}"')}[unmapped] if count else '')}
    return {'columns': out_columns, 'select': f'SELECT {", ".join(selects)} FROM {src}', 'params': select_params, 'measure': measure}


OPERATORS = {'filter': _filter, 'fill_null': _fill_null, 'text_clean': _text_clean, 'cast': _cast, 'calc': _calc, 'aggregate': _aggregate, 'dedupe': _dedupe, 'label': _label}


def compile_op(op, src: str, columns: list[dict], ctx: dict, label: str) -> dict:
    """{'columns', 'select', 'params', 'measure'} for one operator reading the table `src` of `columns`; OpError says what is wrong."""
    if not isinstance(op, dict) or not isinstance(op.get('op'), str) or op['op'] not in OPERATORS:
        raise OpError(tr(f'{label}：操作类型要是 {"、".join(OPERATORS)} 之一', f'{label}: the operator must be one of {", ".join(OPERATORS)}'))
    return OPERATORS[op['op']](op, src, columns, ctx, label)
