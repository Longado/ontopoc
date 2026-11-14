"""Derived properties on the workspace: a value no column holds, worked out for each object of a type and kept like the type itself. A derived property is one
element (derived:<type>:<English name>) with a person's definition, a state, a confirmation snapshot and what it reads (element_dep: every type on its path,
the relations it walks, their datasets and the meanings its conditions use).

Two kinds:
  函数   a formula over this type's own columns, written in the pipelines' expression language (pipeline_expr): 金额 * 数量 / 100. Nothing is stored; it is
         computed on the rows as they are.
  统计   a value for each object worked out from other objects, reached through confirmed relations, up to three hops: for each 客户 the number of their
         订单 whose 状态码 means 已取消. The path, the measured column, the aggregation (the pipelines' list, and 取最新), conditions that name confirmed meanings.
         A path that only goes to the "one" side of each relation gives one value per object and takes no aggregation; one that crosses a "many" side must say how
         the many rows are made into one.

What is refused when it is written (a definition error, so the message says what to do instead):
  - a name that claims a statistic the aggregation is not (交付天数P50 over a mean; name_checks.claim_of reads the name);
  - a measure on a snapshot or a version table (库存快照: one row per product per month; 订单承诺: one row per order version) added up, averaged or counted:
    only 取最新 (按月份 / 按版本), the extremes and a distinct count are true there; the message offers 按[月份]取最新;
  - a value of a "one" side read through a "many" side (an order's product reached from a customer): each product is repeated once per order, so a sum or
    average of it counts one product several times; only a distinct count, the extremes and 取最新 are true.

What is counted and shown, never dropped quietly: the objects with no value (no related rows, nothing the aggregation can read, an expression that is empty
although its inputs are not, a lookup that finds two different values), the rows a statistic used, and the objects that share the join key of another object.
A number worked out on the sample of an input is labelled 样本.

Rows: every type on the path is read through the rows this person may see (row_rules.restriction), the owner type and each type the path crosses, so a row-limited
person gets the statistic over their rows only. Nothing here quotes a whole-data count to them, and they confirm nothing (object_types.refuse_if_limited).

An edit makes a new version: a change to what the property computes (anything but its display name and description) puts it forward again as this person's, and
the confirmations it had stay as history. When a new upload comes, a confirmed property is moved to needs_look only when it can no longer be computed, or when
the objects it cannot compute a value for are not as many as when it was confirmed; its values follow the data, and an answer says which dataset versions it read.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import re

from ontology_poc_generator.name_checks import STAT_WORDS, claim_of
from ontology_poc_generator.named_views import ORDERED_TEXT, orderable
from ontology_poc_generator.object_relations import _relation_visible, relation_id
from ontology_poc_generator.object_types import (
    DERIVED_PREFIX, ENGLISH_NAME, LIMITED_NOTE, MAX_DESCRIPTION, MAX_NAME, TypeRefused, _content, _edit_names, _state_view, _text, _type_row, _visible,
    dataset_columns, element_row, enum_id, log_entries, refuse_if_limited, type_id, write_confirmation, write_elements)
from ontology_poc_generator.object_views import meaning_labels
from ontology_poc_generator.pipeline_expr import COLUMN_TYPE, FUNCTION_DOCS, MAX_LENGTH, compile_expression, error_condition
from ontology_poc_generator.pipeline_funcs import register
from ontology_poc_generator.pipeline_ops import AGGREGATIONS, NUMBER_TYPES, _aggregate_sql, _q, aggregation_options
from ontology_poc_generator.row_rules import positions, restriction, types_on_dataset_of
from ontology_poc_generator.workspace_store import current_dataset, dataset_records

KINDS = {'function': '函数', 'statistic': '统计'}
MAX_HOPS = 3
MAX_CONDITIONS = 5
OPS = {'is': '是', 'is_not': '不是'}
STAT_FNS = {**AGGREGATIONS, 'latest': '取最新'}
TRUE_ON_REPEATS = ('count_distinct', 'min', 'max', 'latest')   # what a snapshot, a version table or a repeated one-side leaves true
FN_FOR_CLAIM = {'sum': 'sum', 'mean': 'avg', 'median': 'median', 'p25': 'p25', 'p75': 'p75', 'min': 'min', 'max': 'max'}   # the statistic a name says -> the aggregation that is it
CLAIM_OF_FN = {v: k for k, v in FN_FOR_CLAIM.items()}
VERSION_WORD = re.compile(r'版本|version', re.I)
EXAMPLES = 5
ROUTING_HINT = '只用这个对象自己的列算出来的值，建议在管道里做（计算列）：算一次，跟着数据集走。这里的派生属性适合要在问答里按定义引用、或者要随着确认状态管起来的值。'
RESET_LABELS = (('type', '所属类型'), ('kind', '种类'), ('expression', '算式'), ('inputs', '输入的列'), ('output_type', '输出类型'), ('path', '路径'), ('measure', '要统计的列'),
                ('fn', '统计方式'), ('latest', '“取最新”的规则'), ('conditions', '条件'))


def derived_id(type_english: str, english_name: str) -> str:
    return f'{DERIVED_PREFIX}{type_english}:{english_name}'


def _derived_row(conn, type_english, english_name, user: dict | None) -> dict:
    row = element_row(conn, derived_id(str(type_english), str(english_name)))
    if row is None or not derived_visible(conn, row, user):
        raise TypeRefused('没有这个派生属性', 404)
    return row


def derived_visible(conn, row: dict, user: dict | None) -> bool:
    """Seen by those who may see every type on its path (what it says and the values it gives are those types' rows); a viewer also needs it confirmed."""
    if user is not None and user['role'] == 'viewer' and row['state'] != 'confirmed':
        return False
    return all((r := element_row(conn, type_id(t))) is not None and _visible(conn, r, user) for t in _content(row)['types'])


# --- walking the path ---------------------------------------------------------------------------------------------------------------------------------

def _walk(conn, owner: str, path: list, user: dict | None, confirmed_only: bool) -> tuple[list[dict], list[str]]:
    """(the hops of a path of relation names from `owner`, the problems). A hop says which way it goes: toward 'one' (each object has one on the other side: a lookup)
    or toward 'many' (it has several). A relation that joins a type to itself is not walked: it cannot say which role it means."""
    here, hops, problems = owner, [], []
    for key in path:
        row = element_row(conn, relation_id(str(key)))
        if row is None or (user is not None and not _relation_visible(conn, row, user)):
            problems.append(f'没有关系“{key}”')
            break
        c = _content(row)
        if c['from'] == c['to']:
            problems.append(f'关系“{c["name"]}”连着同一个类型，派生属性不走它：看不出是哪个角色')
            break
        if here not in (c['from'], c['to']):
            problems.append(f'关系“{c["name"]}”连的是“{c["from"]}”和“{c["to"]}”，从“{here}”走不了')
            break
        if confirmed_only and row['state'] != 'confirmed':
            problems.append(f'关系“{c["name"]}”还没有确认：派生属性只走已确认的关系')
            break
        near, far = ('from', 'to') if here == c['from'] else ('to', 'from')
        many_side = {'many_to_one': 'from', 'one_to_many': 'to'}.get(c['cardinality'])
        hops.append({'relation': c['english_name'], 'name': c['name'], 'from_type': here, 'to_type': c[far], 'from_column': c[f'{near}_column'], 'to_column': c[f'{far}_column'],
                     'toward': 'many' if many_side == far else 'one'})
        here = c[far]
    return hops, problems


def _chain(conn, content: dict, user: dict | None) -> dict:
    """What the definition reads now: {'problems': [...]} when it cannot be read (a type, dataset, relation or column is gone, an input changed type, a meaning
    is no longer written), else {'problems': [], 'types': {English name: {'name', 'content', 'dataset', 'cols'}}, 'hops': [...], 'owner', 'measured', 'output_type'}."""
    problems: list[str] = []
    owner = content['type']
    hops, walk_problems = _walk(conn, owner, content.get('path') or [], user, confirmed_only=False)
    problems += walk_problems
    types: dict[str, dict] = {}
    for english in dict.fromkeys([owner, *(h['to_type'] for h in hops)]):
        row = element_row(conn, type_id(english))
        if row is None:
            problems.append(f'对象类型“{english}”已经不在了')
            continue
        c = _content(row)
        dataset = current_dataset(conn, c['dataset'])
        if dataset is None:
            problems.append(f'数据集“{c["dataset"]}”已经不在了')
            continue
        types[english] = {'name': c['name'], 'content': c, 'dataset': dataset, 'cols': dataset_columns(conn, dataset['id'])}
    if problems:
        return {'problems': problems}

    def need(english: str, columns) -> None:
        gone = [c for c in dict.fromkeys(columns) if c not in types[english]['cols']]
        if gone:
            problems.append(f'{types[english]["dataset"]["name"]} 第 {types[english]["dataset"]["version"]} 版里没有这些列了：{"、".join(gone)}')
    if content['kind'] == 'function':
        need(owner, (i['column'] for i in content['inputs']))
        result = _compile(content['expression'], types[owner]['cols'], content['inputs'])
        if not result['ok']:
            problems.append(f'算式现在读不了：{result["errors"][0]["message"]}')
        output = COLUMN_TYPE.get(result['type']) if result['ok'] else None
        compiled = result
    else:
        for h in hops:
            need(h['from_type'], [h['from_column']])
            need(h['to_type'], [h['to_column']])
        measured = hops[-1]['to_type']
        need(measured, [c for c in (content['measure']['column'], *(f['column'] for f in content['conditions']), *((content['latest']['order'], content['latest'].get('tie')) if content['latest'] else ())) if c])
        output, compiled = None, None
        if not problems:
            output = _output_type(content['fn'], types[measured]['cols'][content['measure']['column']]['type'] if content['measure']['column'] else None)
            for f in content['conditions']:
                if f['label'] not in meaning_labels(conn, measured, f['column']).values():
                    problems.append(f'“{f["label"]}”现在不是“{f["column"]}”已写的含义')
            if content['latest'] and not orderable(types[measured]['cols'][content['latest']['order']]['type']):
                problems.append(f'“{content["latest"]["order"]}”现在的内容排不出先后（数字、年月、日期才可以）')
    if not problems and output != content['output_type']:
        problems.append(f'输出类型变了：定义时是{TYPE_WORD.get(content["output_type"], content["output_type"])}，现在是{TYPE_WORD.get(output, output)}')
    if problems:
        return {'problems': problems}
    return {'problems': [], 'types': types, 'hops': hops, 'owner': owner, 'measured': hops[-1]['to_type'] if hops else owner, 'output_type': output, 'compiled': compiled}


TYPE_WORD = {'integer': '整数', 'decimal': '小数', 'text': '文本', 'date': '日期', 'month': '月份', 'datetime': '日期时间', 'boolean': '是否'}


def _compile(expression: str, cols: dict, inputs: list[dict]) -> dict:
    """The expression compiled over the columns of the type's dataset as they are now. `inputs`: the columns it was written over (the key and the properties)."""
    return compile_expression(expression, [{'name': i['column'], 'type': cols[i['column']]['type']} for i in inputs if i['column'] in cols])


def _output_type(fn: str, column_type: str | None) -> str:
    if fn in ('count', 'count_distinct'):
        return 'integer'
    if fn == 'sum':
        return 'integer' if column_type == 'integer' else 'decimal'
    if fn in ('avg', 'median', 'p25', 'p75'):
        return 'decimal'
    return column_type or 'text'   # min, max, latest, and a lookup: the column's own type


# --- reading rows through the rows a person may see -----------------------------------------------------------------------------------------------------

@contextmanager
def _tables(conn, chain: dict, user: dict | None):
    """{English name: (quoted table, the column that names a row)} for every type of the chain: the dataset's own table, or for a type a row rule limits this person on a
    temporary copy of the rows they may read that keeps each row's number in the original table (_src). The copies are dropped when the block ends."""
    made, tables = [], {}
    try:
        for english, t in chain['types'].items():
            limit = restriction(conn, type_id(english), user)
            if limit is None:
                tables[english] = (_q(t['dataset']['table_name']), 'rowid')
                continue
            name = f'dp_{len(made)}'
            keep = sorted(positions(dataset_records(conn, t['dataset']), limit))
            conn.execute(f'DROP TABLE IF EXISTS temp.{name}')
            conn.execute(f'CREATE TEMP TABLE {name} AS SELECT rowid AS _src, * FROM {_q(t["dataset"]["table_name"])} WHERE rowid IN ({",".join(map(str, keep)) or "NULL"}) ORDER BY rowid')
            made.append(name)
            tables[english] = (name, '_src')
        yield tables
    finally:
        for name in made:
            conn.execute(f'DROP TABLE IF EXISTS temp.{name}')


def _plain(value, output: str):
    """A value out of SQLite as the property's output type says (a number rounded, a text as it is), or None when it cannot be read as that."""
    if value is None:
        return None
    try:
        if output == 'integer':
            return int(value) if float(value).is_integer() else None
        if output == 'decimal':
            number = round(float(value), 6)   # 24000 * 1.13 is 27120.000000000004 in floating point
            return int(number) if number.is_integer() else number
    except (TypeError, ValueError, OverflowError):
        return None
    return str(value)


def text_of(value, output: str) -> str | None:
    """A value as the text a dataset keeps it as (what the objects page shows and the question engine reads)."""
    if value is None:
        return None
    if output == 'boolean':
        return '是' if value in (1, '1', True, 'true') else '否'
    return str(value)


def _conditions_sql(conn, content: dict, measured: str, alias: str) -> tuple[str, list]:
    parts, params = [], []
    for f in content['conditions']:
        codes = sorted({str(code).strip() for code, label in meaning_labels(conn, measured, f['column']).items() if label == f['label']})
        marks = ','.join('?' * len(codes)) or 'NULL'
        parts.append(f"TRIM(COALESCE(CAST({alias}.{_q(f['column'])} AS TEXT), '')) {'IN' if f['op'] == 'is' else 'NOT IN'} ({marks})")
        params += codes
    return (' AND '.join(parts) or '1 = 1'), params


def evaluate(conn, content: dict, user: dict | None = None) -> dict:
    """The property computed on every object of its type, over the rows `user` may read (everything for None): {'problems': [...]} when it cannot be computed, else
    {'values': {row number in the type's table: value}, 'objects', 'with_value', 'failed', 'rows_used', 'datasets', ...}. `failed` counts the objects whose value could
    not be worked out although there was something to work it out from; the others without a value are counted by reason, never read as zero."""
    chain = _chain(conn, content, user)
    if chain['problems']:
        return {'problems': chain['problems']}
    register(conn)
    with _tables(conn, chain, user) as tables:
        body = _evaluate_function(conn, content, chain, tables) if content['kind'] == 'function' else _evaluate_statistic(conn, content, chain, tables)
    owner = chain['types'][chain['owner']]
    values = body.pop('values')
    return {'problems': [], 'values': values, 'objects': body.pop('objects'), 'with_value': sum(v is not None for v in values.values()), 'output_type': chain['output_type'],
            'datasets': {t['dataset']['name']: t['dataset']['version'] for t in chain['types'].values()}, 'owner_dataset': owner['dataset']['name'], **body}


def _evaluate_function(conn, content: dict, chain: dict, tables: dict) -> dict:
    owner = chain['owner']
    table, ident = tables[owner]
    result = chain['compiled']
    failing, failing_params = error_condition(result['sql'], result['params'], result['fields'])
    rows = conn.execute(f'SELECT {ident}, ({result["sql"]}), ({failing}) FROM {table} ORDER BY {ident}', [*result['params'], *failing_params]).fetchall()
    values = {i: _plain(v, chain['output_type']) if not bad else None for i, v, bad in rows}
    failed = sum(1 for _, _, bad in rows if bad)
    return {'values': values, 'objects': len(rows), 'failed': failed, 'no_value': {'empty_input': sum(1 for i, v, bad in rows if v is None and not bad)}, 'rows_used': None}


def _joins(chain: dict, tables: dict) -> str:
    parts = [f'{tables[chain["owner"]][0]} t0']
    for i, h in enumerate(chain['hops'], 1):
        parts.append(f"JOIN {tables[h['to_type']][0]} t{i} ON t{i}.{_q(h['to_column'])} = t{i - 1}.{_q(h['from_column'])} AND t{i - 1}.{_q(h['from_column'])} <> ''")
    return ' '.join(parts)


def _sort_key(column: str, kind: str, alias: str) -> str:
    return f'CAST({alias}.{_q(column)} AS REAL)' if kind in NUMBER_TYPES else f'{alias}.{_q(column)}'


def _evaluate_statistic(conn, content: dict, chain: dict, tables: dict) -> dict:
    owner, hops, k = chain['owner'], chain['hops'], len(chain['hops'])
    last = f't{k}'
    m = chain['types'][chain['measured']]
    owner_table, owner_id = tables[owner]
    last_id = tables[chain['measured']][1]
    column, fn = content['measure']['column'], content['fn']
    kind = m['cols'][column]['type'] if column else None
    where, params = _conditions_sql(conn, content, chain['measured'], last)
    joined = f'{_joins(chain, tables)} WHERE {where}'
    objects = conn.execute(f'SELECT COUNT(*) FROM {owner_table}').fetchone()[0]
    rows_used = conn.execute(f'SELECT COUNT(*) FROM {joined}', params).fetchone()[0]
    extra = ''
    if fn == 'latest':
        order, tie = content['latest']['order'], content['latest'].get('tie')
        ranked = (f"ROW_NUMBER() OVER (PARTITION BY t0.{owner_id} ORDER BY ({last}.{_q(order)} IS NOT NULL AND {last}.{_q(order)} <> '') DESC, "
                  f"{_sort_key(order, m['cols'][order]['type'], last)} DESC, {(_sort_key(tie, m['cols'][tie]['type'], last) + ' DESC, ') if tie else ''}{last}.{last_id} DESC)")
        sql = (f'SELECT owner, v FROM (SELECT t0.{owner_id} AS owner, {last}.{_q(column)} AS v, {ranked} AS rn FROM {joined}) WHERE rn = 1')
        found = {o: (v, 1) for o, v in conn.execute(sql, params)}
    else:
        inner = f'SELECT t0.{owner_id} AS owner{f", {last}.{_q(column)} AS __v" if column else ""} FROM {joined}'
        if fn == 'value':   # a lookup: the one value on the other side; two different values there are an ambiguity, counted
            sql = f'SELECT owner, MIN(__v), COUNT(DISTINCT __v) FROM ({inner}) GROUP BY owner'
            found = {o: (v, n) for o, v, n in conn.execute(sql, params)}
        else:
            agg, agg_params, _ = _aggregate_sql(fn, {'name': '__v', 'type': kind} if column else None)
            found = {o: (v, 1) for o, v in conn.execute(f'SELECT owner, {agg} FROM ({inner}) GROUP BY owner', [*agg_params, *params])}
    ids = [r[0] for r in conn.execute(f'SELECT {owner_id} FROM {owner_table} ORDER BY {owner_id}')]
    values, no_rows, unreadable, ambiguous = {}, 0, 0, 0
    for i in ids:
        if i not in found:
            values[i] = 0 if fn in ('count', 'count_distinct') else None
            no_rows += fn not in ('count', 'count_distinct')
            continue
        raw, distinct = found[i]
        if distinct > 1:
            values[i] = None
            ambiguous += 1
            continue
        values[i] = _plain(raw, chain['output_type'])
        unreadable += raw is not None and values[i] is None or (raw is None and fn not in ('count', 'count_distinct'))
    shared = 0
    if hops and hops[0]['toward'] == 'many':   # objects that name the same thing by the same join key each count the same rows
        c = _q(hops[0]['from_column'])
        shared = conn.execute(f"SELECT COUNT(*) FROM {owner_table} WHERE {c} <> '' AND {c} IN (SELECT {c} FROM {owner_table} WHERE {c} <> '' GROUP BY {c} HAVING COUNT(*) > 1)").fetchone()[0]
    return {'values': values, 'objects': objects, 'failed': unreadable + ambiguous, 'rows_used': rows_used, 'shared_keys': shared,
            'no_value': {'no_rows': no_rows, 'unreadable': unreadable, 'ambiguous': ambiguous}}


# --- what a person reads ------------------------------------------------------------------------------------------------------------------------------

def _owner_key_text(conn, chain: dict, tables: dict, ids: list[int]) -> dict[int, str]:
    owner = chain['owner']
    table, ident = tables[owner]
    key = chain['types'][owner]['content']['key']
    marks = ','.join('?' * len(ids)) or 'NULL'
    return {i: ' · '.join('' if v is None else str(v) for v in row) for i, *row in conn.execute(f'SELECT {ident}, {", ".join(_q(c) for c in key)} FROM {table} WHERE {ident} IN ({marks})', ids)}


def seen_of(result: dict) -> dict | None:
    """What a person reads of the result, which confirming has to quote: the dataset versions, the objects, how many have a value and how many could not be worked out."""
    if result['problems']:
        return None
    return {'datasets': result['datasets'], 'objects': result['objects'], 'with_value': result['with_value'], 'failed': result['failed']}


def trial(conn, content: dict, user: dict | None = None) -> dict:
    """试算: the property on the real rows (the rows `user` may read), as sentences a person reads before confirming, with a few values and, for a formula, the
    sample (labelled 样本) it is tried on. {'problems', 'lines', 'examples', 'sample', 'numbers'}."""
    result = evaluate(conn, content, user)
    if result['problems']:
        return {'problems': result['problems'], 'lines': [{'ok': False, 'text': p} for p in result['problems']], 'examples': [], 'sample': None, 'numbers': None}
    chain = _chain(conn, content, user)
    limited = any(restriction(conn, type_id(e), user) is not None for e in chain['types'])
    owner_name = chain['types'][chain['owner']]['name']
    n, with_value, empty = result['objects'], result['with_value'], result['objects'] - result['with_value']
    lines = [{'ok': result['failed'] == 0, 'text': f'{"你能看到的" if limited else ""}{n} 个{owner_name}里，{with_value} 个算出了值，{empty} 个没有值'}]
    if limited:
        lines.append({'ok': True, 'text': LIMITED_NOTE})
    lines += _failure_lines(content, result, owner_name)
    if result['rows_used'] is not None:
        lines.append({'ok': True, 'text': f'一共用了 {result["rows_used"]} 行{chain["types"][chain["measured"]]["name"]}的数据'})
    with _tables(conn, chain, user) as tables:
        shown = [i for i, v in result['values'].items() if v is not None][:EXAMPLES]
        labels = _owner_key_text(conn, chain, tables, shown)
        sample = _sample(conn, content, chain, tables) if content['kind'] == 'function' else None
    examples = [{'object': labels[i], 'value': text_of(result['values'][i], result['output_type'])} for i in shown]
    numbers = {k: result.get(k) for k in ('objects', 'with_value', 'failed', 'rows_used', 'shared_keys', 'no_value')}
    return {'problems': [], 'lines': lines, 'examples': examples, 'sample': sample, 'numbers': None if limited else numbers, 'datasets': result['datasets'], 'output_type': result['output_type'],
            'seen': None if limited else seen_of(result), 'limited_note': LIMITED_NOTE if limited else None}


def _failure_lines(content: dict, result: dict, owner_name: str) -> list[dict]:
    no = result['no_value']
    out = []
    if no.get('empty_input'):
        out.append({'ok': False, 'text': f'{no["empty_input"]} 个{owner_name}的输入里有空的，算式没有算它们（空值不当成 0）'})
    if result['failed'] and content['kind'] == 'function':
        out.append({'ok': False, 'text': f'{result["failed"]} 个{owner_name}输入都有值，算式却算不出结果（除以 0、日期不对）'})
    if no.get('no_rows'):
        out.append({'ok': False, 'text': f'{no["no_rows"]} 个{owner_name}没有可以统计的相关数据（没有相关的行，或条件筛完一行不剩），没有值，不是 0'})
    if no.get('unreadable'):
        out.append({'ok': False, 'text': f'{no["unreadable"]} 个{owner_name}有相关的行，但统计的列读不出值'})
    if no.get('ambiguous'):
        out.append({'ok': False, 'text': f'{no["ambiguous"]} 个{owner_name}在另一边找到了不止一个不同的值，没有取其中一个'})
    if result.get('shared_keys'):
        out.append({'ok': False, 'text': f'{result["shared_keys"]} 个{owner_name}和别的{owner_name}用同一个连接键，它们各自数到了同一批行'})
    return out


def _sample(conn, content: dict, chain: dict, tables: dict) -> dict | None:
    """The formula tried on one row whose inputs all have a value: the values it read and what it gave. 样本: one row, not the data."""
    owner = chain['owner']
    table, ident = tables[owner]
    result = chain['compiled']
    filled = ' AND '.join(f"{_q(i['column'])} IS NOT NULL AND {_q(i['column'])} <> ''" for i in content['inputs']) or '1 = 1'
    row = conn.execute(f'SELECT {ident}, ({result["sql"]}), {", ".join(_q(i["column"]) for i in content["inputs"])} FROM {table} WHERE {filled} ORDER BY {ident} LIMIT 1', result['params']).fetchone() \
        if content['inputs'] else None
    if row is None:
        return None
    return {'label': '样本', 'inputs': [{'column': i['column'], 'value': v} for i, v in zip(content['inputs'], row[2:])], 'result': text_of(_plain(row[1], chain['output_type']), chain['output_type'])}


def describe(conn, content: dict) -> str:
    """The definition as a sentence: 客户的已取消订单数：每个客户，数订单里 状态码 是「已取消」的行."""
    owner = element_row(conn, type_id(content['type']))
    owner_name = _content(owner)['name'] if owner else content['type']
    if content['kind'] == 'function':
        return f'{owner_name}的{content["name"]} = {content["expression"]}'
    names = []
    for h in content['path']:
        row = element_row(conn, relation_id(h))
        names.append(_content(row)['name'] if row else h)
    measured = element_row(conn, type_id(content['types'][-1]))
    measured_name = _content(measured)['name'] if measured else content['types'][-1]
    where = '，且'.join(f'「{f["column"]}」{OPS[f["op"]]}「{f["label"]}」' for f in content['conditions'])
    column, fn = content['measure']['column'], content['fn']
    if fn in ('latest', 'value'):
        what = f'取「{column}」' + (f'（按「{content["latest"]["order"]}」最新的一行）' if fn == 'latest' else '')
    elif fn == 'count' and not column:
        what = '数行数'
    else:
        what = f'{STAT_FNS[fn]}「{column}」'
    return f'{owner_name}的{content["name"]}：每个{owner_name}，经过 {" → ".join(names)}，{measured_name}里' + (f'{where}的行，' if where else '的行，') + what


# --- the definition a person writes -------------------------------------------------------------------------------------------------------------------

def _own_columns(owner: dict) -> list[str]:
    return list(dict.fromkeys([*owner['key'], *(p['column'] for p in owner['properties'])]))


def _stat_word(kind: str) -> str:
    return STAT_WORDS.get(kind) or f'第 {kind[1:]} 百分位'


def _name_claim(name: str, fn: str) -> None:
    """A name that says a statistic is that statistic: 交付天数P50 is the median, 平均 is the mean, 合计 the sum. Refused when the aggregation is another."""
    claim = claim_of(name)
    if claim is None or CLAIM_OF_FN.get(fn) == claim[0]:
        return
    offer = FN_FOR_CLAIM.get(claim[0])
    how = f'选“{STAT_FNS[offer]}”' if offer else f'这里没有这种算法（只有{"、".join(STAT_FNS[f] for f in FN_FOR_CLAIM.values())}）'
    said = f'“{claim[1]}”，也就是{_stat_word(claim[0])}'
    raise TypeRefused(f'名字“{name}”说的是{said}，统计方式选的却是“{STAT_FNS[fn]}”：名字和算法对不上，别人会照名字读它。要{_stat_word(claim[0])}就{how}，要{STAT_FNS[fn]}就改名字',
                      detail={'offer': [{'fn': offer}] if offer else [], 'claim': claim[0]})


def _layers(owner_hop: dict, m_content: dict, cols: dict) -> list[dict]:
    """The columns of the many side's key that make it one row per (the thing it is about) per (time or version): a snapshot (a month, a date) or a version. The
    join column must be part of the key and something else in the key must be a period or called a version; an order's lines (订单号 + 行号) are not layers."""
    if owner_hop['to_column'] not in m_content['key']:
        return []
    out = []
    for k in m_content['key']:
        if k == owner_hop['to_column'] or k not in cols:
            continue
        kind = 'snapshot' if cols[k]['type'] in ORDERED_TEXT else 'version' if VERSION_WORD.search(k) else None
        if kind:
            out.append({'column': k, 'kind': kind})
    return out


def _refusals(conn, content: dict, chain: dict) -> None:
    """The checks that make a definition refused, on the chain it reads: a snapshot or version table added up, a repeated one side added up, a name that claims
    another statistic. TypeRefused says what to do instead; `detail.offer` lists the aggregation to switch to."""
    if content['kind'] != 'statistic':
        return
    hops, fn = chain['hops'], content['fn']
    if fn != 'value':   # a lookup says no statistic
        _name_claim(content['name'], fn)
    many_at = [i for i, h in enumerate(hops) if h['toward'] == 'many']
    for i in many_at:
        t = chain['types'][hops[i]['to_type']]
        layers = _layers(hops[i], t['content'], t['cols'])
        if not layers:
            continue
        layer = layers[0]
        word = '快照' if layer['kind'] == 'snapshot' else '版本'
        if i != len(hops) - 1:
            raise TypeRefused(f'“{t["name"]}”每个{chain["types"][hops[i]["from_type"]]["name"]}有多个{layer["column"]}的记录（{word}），它要放在路径的最后一步：路径还往它后面走，同一件事会被每个{word}算一遍')
        if fn not in TRUE_ON_REPEATS:
            what = '数它的行' if fn == 'count' else f'把它的“{content["measure"]["column"]}”{STAT_FNS[fn]}'
            why = '一个存量（库存）每个月存一次，把各月加在一起不是库存' if layer['kind'] == 'snapshot' else '同一件事的几个版本会被当成几件事'
            raise TypeRefused(f'“{t["name"]}”每个{chain["types"][hops[i]["from_type"]]["name"]}有多个{layer["column"]}的记录（{layer["column"]}是它主键的一部分，是{word}），{what}：{why}。'
                              f'可以选“取最新”，按“{layer["column"]}”取每个{chain["types"][hops[i]["from_type"]]["name"]}最新的一条；要数个数就数去重的“{hops[i]["to_column"]}”',
                              detail={'offer': [{'fn': 'latest', 'order': layer['column']}, {'fn': 'count_distinct', 'column': hops[i]['to_column']}], 'layer': layer})
        if fn == 'latest' and content['latest']['order'] != layer['column']:
            raise TypeRefused(f'“{t["name"]}”是按“{layer["column"]}”存的{word}，“取最新”要按“{layer["column"]}”比先后，不能按“{content["latest"]["order"]}”', detail={'offer': [{'fn': 'latest', 'order': layer['column']}]})
    first_many = next(iter(many_at), None)
    if first_many is not None and any(h['toward'] == 'one' for h in hops[first_many + 1:]) and fn not in TRUE_ON_REPEATS:
        crossed = '、'.join(chain['types'][h['to_type']]['name'] for h in hops[first_many + 1:] if h['toward'] == 'one')
        raise TypeRefused(f'路径先走到“多”的一边，再回到“一”的一边（{crossed}）：一边的每个对象会被它每一行重复算一遍，“{STAT_FNS[fn]}”会把同一个对象算好几次。'
                          f'可以选“去重计数”、“最小”、“最大”或“取最新”，或者把要统计的列换成多的一边的列', detail={'offer': [{'fn': f} for f in TRUE_ON_REPEATS]})


def check_definition(conn, payload: dict, user: dict | None, english_name: str | None = None) -> dict:
    """The content of a derived property as a person wrote it. TypeRefused says what is wrong (and for a refused aggregation what to choose instead)."""
    english = payload.get('english_name') if english_name is None else english_name
    if not isinstance(english, str) or not ENGLISH_NAME.fullmatch(english):
        raise TypeRefused('英文名只能用字母、数字和下划线，字母开头，最多 40 个字符')
    name = _text(payload.get('name'), '名称', MAX_NAME)
    description = _text(payload.get('description') or '', '说明', MAX_DESCRIPTION, required=False)
    owner_row = _type_row(conn, payload.get('type'), user)
    owner = _content(owner_row)
    dataset = current_dataset(conn, owner['dataset'])
    if dataset is None:
        raise TypeRefused(f'数据集“{owner["dataset"]}”已经不在了', 409)
    cols = dataset_columns(conn, dataset['id'])
    kind = payload.get('kind')
    if kind not in KINDS:
        raise TypeRefused('种类要选函数或统计')
    base = {'english_name': english, 'name': name, 'description': description, 'type': owner['english_name'], 'kind': kind}
    if kind == 'function':
        body = _function_body(payload, owner, cols)
        content = {**base, **body, 'types': [owner['english_name']], 'path': [], 'measure': None, 'fn': None, 'latest': None, 'conditions': []}
    else:
        body = _statistic_body(conn, payload, owner, name, user)
        content = {**base, **body, 'expression': None, 'inputs': []}
    chain = _chain(conn, content, user)
    if chain['problems']:
        raise TypeRefused('；'.join(chain['problems']), 409)
    _refusals(conn, content, chain)
    return content


def _function_body(payload: dict, owner: dict, cols: dict) -> dict:
    expression = payload.get('expression')
    if not isinstance(expression, str) or not expression.strip():
        raise TypeRefused('要写算式')
    if len(expression) > MAX_LENGTH:
        raise TypeRefused(f'算式最长 {MAX_LENGTH} 个字')
    available = [{'column': c, 'type': cols[c]['type']} for c in _own_columns(owner) if c in cols]
    result = compile_expression(expression, [{'name': a['column'], 'type': a['type']} for a in available])
    if not result['ok']:
        first = result['errors'][0]
        raise TypeRefused(f'算式不对：{first["message"]}' + (f'（第 {first["pos"] + 1} 个字符）' if first['pos'] else ''))
    by_name = {a['column']: a for a in available}
    return {'expression': expression.strip(), 'inputs': [by_name[f] for f in sorted(result['fields'])], 'output_type': COLUMN_TYPE[result['type']]}


def _statistic_body(conn, payload: dict, owner: dict, name: str, user: dict | None) -> dict:
    path = payload.get('path')
    if not isinstance(path, list) or not path or len(path) > MAX_HOPS or not all(isinstance(p, str) for p in path):
        raise TypeRefused(f'路径要选 1 到 {MAX_HOPS} 个关系，一个接着一个')
    hops, problems = _walk(conn, owner['english_name'], path, user, confirmed_only=True)
    if problems:
        raise TypeRefused('；'.join(problems), 409)
    measured = hops[-1]['to_type']
    m_row = _type_row(conn, measured, user)
    m = _content(m_row)
    m_dataset = current_dataset(conn, m['dataset'])
    if m_dataset is None:
        raise TypeRefused(f'数据集“{m["dataset"]}”已经不在了', 409)
    cols = dataset_columns(conn, m_dataset['id'])
    for h in hops:   # each type on the path must be readable by this person
        _type_row(conn, h['to_type'], user)
    many = any(h['toward'] == 'many' for h in hops)
    posted = payload.get('measure') if isinstance(payload.get('measure'), dict) else {}
    column, fn = posted.get('column') or None, payload.get('fn') or None
    available = list(dict.fromkeys([*m['key'], *(p['column'] for p in m['properties'])]))
    if column is not None and (column not in available or column not in cols):
        raise TypeRefused(f'“{m["name"]}”没有属性“{column}”')
    if many:
        if fn not in STAT_FNS:
            raise TypeRefused(f'路径经过“多”的一边（{"、".join(h["name"] for h in hops if h["toward"] == "many")}），每个对象有好几行，要选统计方式：{"、".join(STAT_FNS.values())}')
        if column is None and fn != 'count':
            raise TypeRefused(f'“{STAT_FNS[fn]}”要指定统计哪一列；只有“计数”可以不选列（数行数）')
        if column is not None and fn in AGGREGATIONS:
            codes = frozenset(f'{m["dataset"]}.{p["column"]}' for p in m['properties'] if p['enum'])
            options = aggregation_options([{'name': column, 'type': cols[column]['type'], 'origin': f'{m["dataset"]}.{column}'}], codes)[column]
            if fn not in options:
                is_code = f'{m["dataset"]}.{column}' in codes and cols[column]['type'] in NUMBER_TYPES
                raise TypeRefused(f'“{column}”是代码列，把代码{STAT_FNS[fn]}没有意义；可以用计数或去重计数' if is_code
                                  else f'“{column}”是{TYPE_WORD[cols[column]["type"]]}列，不能{STAT_FNS[fn]}；可以用：{"、".join(STAT_FNS[f] for f in options)}')
    else:
        if fn not in (None, 'value'):
            raise TypeRefused('这条路径只走到“一”的那一边，每个对象在那边只有一个值，不用选统计方式')
        if column is None:
            raise TypeRefused('要选取哪一列的值')
        fn = 'value'
    latest = None
    if fn == 'latest':
        raw = payload.get('latest') if isinstance(payload.get('latest'), dict) else {}
        order, tie = raw.get('order'), raw.get('tie') or None
        if column is None or order not in cols or not orderable(cols[order]['type']):
            raise TypeRefused('“取最新”要选一个排得出先后的列（数字、年月、日期）来比先后')
        if tie is not None and (tie not in cols or tie == order or not orderable(cols[tie]['type'])):
            raise TypeRefused('比先后相同时用的列，要是另一个排得出先后的列')
        latest = {'order': order, 'tie': tie}
    conditions = _conditions(conn, payload.get('conditions'), m, cols)
    return {'path': [h['relation'] for h in hops], 'types': [owner['english_name'], *(h['to_type'] for h in hops)], 'measure': {'column': column}, 'fn': fn, 'latest': latest,
            'conditions': conditions, 'output_type': _output_type(fn, cols[column]['type'] if column else None), 'expression': None, 'inputs': []}


def _conditions(conn, posted, m: dict, cols: dict) -> list[dict]:
    posted = posted or []
    if not isinstance(posted, list) or len(posted) > MAX_CONDITIONS or not all(isinstance(f, dict) for f in posted):
        raise TypeRefused(f'条件要写成列表，最多 {MAX_CONDITIONS} 个')
    codes = {p['column'] for p in m['properties'] if p['enum']}
    out = []
    for f in posted:
        column, op, label = f.get('column'), f.get('op'), f.get('label')
        if column not in codes:
            raise TypeRefused(f'“{column}”不是“{m["name"]}”的代码列，没有含义可以拿来筛')
        if op not in OPS:
            raise TypeRefused('条件只能是“是”或“不是”')
        known = sorted(set(meaning_labels(conn, m['english_name'], column).values()))
        if label not in known:
            raise TypeRefused(f'“{label}”不是“{column}”已写的含义' + (f'：{"、".join(known)}' if known else '，先给这一列写含义'))
        out.append({'column': column, 'op': op, 'label': label})
    return out


def check_names_free(conn, content: dict) -> None:
    """The English name is unique within its type, ignoring case; the name is not the name of a column or property of any type reading the same dataset, nor of
    another derived property of them (a question names one thing)."""
    mine = derived_id(content['type'], content['english_name'])
    owner = _content(element_row(conn, type_id(content['type'])))
    siblings = [e.partition(':')[2] for e in types_on_dataset_of(conn, type_id(content['type']))]
    taken = set(owner['key'])
    for sibling in siblings:
        row = element_row(conn, type_id(sibling))
        if row is not None:
            taken |= {p['column'] for p in _content(row)['properties']} | {p['name'] for p in _content(row)['properties']}
    dataset = current_dataset(conn, owner['dataset'])
    if dataset is not None:
        taken |= set(dataset_columns(conn, dataset['id']))
    for element_id, other in conn.execute("SELECT element_id, content_json FROM element_state WHERE element_id LIKE 'derived:%'"):
        if element_id == mine:
            continue
        o = json.loads(other)
        if element_id.casefold() == mine.casefold():
            raise TypeRefused(f'英文名“{content["english_name"]}”和已有的“{o["english_name"]}”只差大小写', 409)
        if o['type'] in siblings:
            taken.add(o['name'])
    if content['name'] in taken:
        raise TypeRefused(f'“{content["name"]}”已经是这个数据集的一列、一个属性，或另一个派生属性的名字', 409)


def reset_reasons(old: dict, new: dict) -> list[str]:
    """What changed that a confirmation was about: everything the property computes. The display name and the description are not on the list."""
    return [label for key, label in RESET_LABELS if old.get(key) != new.get(key)]


def _reads(content: dict, chain: dict) -> list[str]:
    measured = content['types'][-1]
    return [*(type_id(t) for t in content['types']), *(relation_id(r) for r in content['path']), *(f'dataset:{t["dataset"]["name"]}' for t in chain['types'].values()),
            *(enum_id(measured, c) for c in dict.fromkeys(f['column'] for f in content['conditions']))]


def _anchors(result: dict) -> dict:
    return {'datasets': result['datasets'], 'failed': result['failed'], 'objects': result['objects']}


def _evidence(result: dict) -> str:
    return ','.join(f'dataset:{n}@v{v}' for n, v in result['datasets'].items())


def _change(content: dict, result: dict, who: str | None) -> tuple:
    return (derived_id(content['type'], content['english_name']), 'checked', _evidence(result), who, content, _anchors(result), who)


def create_derived(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """Put a derived property forward (state checked, the person its proposer): it is tried on the real data first. Returns {'id', 'type', 'trial'}."""
    content = check_definition(conn, payload, user)
    if element_row(conn, derived_id(content['type'], content['english_name'])):
        raise TypeRefused(f'这个类型已经有英文名“{content["english_name"]}”的派生属性', 409)
    check_names_free(conn, content)
    chain, result = _chain(conn, content, None), evaluate(conn, content, None)
    write_elements(conn, [_change(content, result, who)], {derived_id(content['type'], content['english_name']): _reads(content, chain)})
    return {'id': content['english_name'], 'type': content['type'], 'trial': trial(conn, content, user)}


def update_derived(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{type, english_name, version, ...the fields of create}: a change to what it computes puts it forward again as this person's, and a confirmed one stops being
    confirmed (what it had been confirmed on stays in the history); so does saving one that was sent back. The display name and the description keep the state."""
    row = _derived_row(conn, payload.get('type'), payload.get('english_name'), user)
    if payload.get('version') != row['version']:
        raise TypeRefused('这个派生属性在你打开之后被改了，请刷新后再改', 409)
    old = _content(row)
    content = check_definition(conn, {**payload, 'type': old['type']}, user, old['english_name'])
    check_names_free(conn, content)
    reset = reset_reasons(old, content)
    if reset or row['state'] in ('proposed', 'rejected'):
        chain, result = _chain(conn, content, None), evaluate(conn, content, None)
        write_elements(conn, [_change(content, result, who)], {row['element_id']: _reads(content, chain)}, {row['element_id']: row['version']})
    elif (old['name'], old['description']) != (content['name'], content['description']):
        _edit_names(conn, row, content, who)
    return {'id': old['english_name'], 'type': old['type'], 'state': element_row(conn, row['element_id'])['state'], 'reset': reset}


def waiting_on(conn, content: dict) -> list[dict]:
    """What a property stands on that is not confirmed: the types and relations on its path, and the meanings its conditions use, as [{'id', 'name', 'state'}]."""
    out = []
    for t in content['types']:
        row = element_row(conn, type_id(t))
        if row is None or row['state'] != 'confirmed':
            out.append({'id': t, 'name': _content(row)['name'] if row else t, 'state': row['state'] if row else None})
    for r in content['path']:
        row = element_row(conn, relation_id(r))
        if row is None or row['state'] != 'confirmed':
            out.append({'id': r, 'name': _content(row)['name'] if row else r, 'state': row['state'] if row else None})
    for column in dict.fromkeys(f['column'] for f in content['conditions']):
        row = element_row(conn, enum_id(content['types'][-1], column))
        if row is None or row['state'] != 'confirmed':
            out.append({'id': f'{content["types"][-1]}:{column}', 'name': f'{content["types"][-1]}.{column}', 'state': row['state'] if row else None})
    return out


def confirm_derived(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{type, english_name, version, seen}: confirm what the person looked at. `seen` is {datasets, objects, with_value, failed} of the trial they read; the trial is
    run again on the data as it is and the confirmation is refused (409) when it is not that. What it stands on must be confirmed, the checks that refuse a
    definition are run again, and the trial (rows used, the objects without a value, a few values) is kept with the confirmation as its evidence. Another builder
    (SelfConfirmation otherwise); a person a row rule limits confirms nothing, since the numbers they read are of some of the rows."""
    row = _derived_row(conn, payload.get('type'), payload.get('english_name'), user)
    refuse_if_limited(conn, row, user)
    if payload.get('version') != row['version']:
        raise TypeRefused('确认要带上你看到的那一版；它在你看过之后被改了，请刷新后重新看一遍', 409)
    if row['state'] == 'confirmed':
        raise TypeRefused('已经确认过了', 409)
    if row['state'] == 'rejected':
        raise TypeRefused('已经被退回了：要先按退回的理由改，再重新提出', 409)
    if not isinstance(payload.get('seen'), dict):
        raise TypeRefused('确认要带上你看到的数据版本和对象数（seen）')
    content = _content(row)
    waiting = waiting_on(conn, content)
    if waiting:
        raise TypeRefused(f'它用到的{"、".join(f"“{w["name"]}”" for w in waiting)}还没有确认，要先确认它们', 409)
    chain = _chain(conn, content, user)
    if chain['problems']:
        raise TypeRefused(f'按现在的数据算不出来，不能确认：{"；".join(chain["problems"])}', 409)
    if chain['types'] and [chain['owner'], *(h['to_type'] for h in chain['hops'])] != content['types']:
        raise TypeRefused('它走的关系连的类型变了，请重新保存一次再确认', 409)
    _refusals(conn, content, chain)
    result = evaluate(conn, content, user)
    if payload['seen'] != seen_of(result):
        raise TypeRefused(f'数据在你看过之后变了：{result["owner_dataset"]} 等数据集的版本或这个属性的值不是你看到的那样了，请刷新后重新看一遍', 409)
    shown = trial(conn, content, user)
    write_confirmation(conn, row['element_id'], content, _evidence(result), who, _anchors(result), result['datasets'], row['version'], _reads(content, chain),
                       snapshot={'trial': {'numbers': shown['numbers'], 'examples': shown['examples'], 'sample': shown['sample'], 'lines': shown['lines']}})
    return {'state': 'confirmed'}


def derived_problems(conn, row: dict) -> list[str]:
    """For a confirmed property, after a dataset moved: what is different now, in words (empty when it can still be computed and the objects it cannot compute a value
    for are as many as when it was confirmed)."""
    content = _content(row)
    result = evaluate(conn, content, None)
    if result['problems']:
        return result['problems']
    was = json.loads(row['anchors_json'])
    if result['failed'] == was['failed']:
        return []
    moved = '、'.join(f'{n} 第 {v} 版' for n, v in result['datasets'].items() if was['datasets'].get(n) != v)
    return [f'{moved}之后，算不出值的对象变了：确认时 {was["failed"]} 个，现在 {result["failed"]} 个']


# --- what the pages read ------------------------------------------------------------------------------------------------------------------------------

def derived_state(conn, row: dict, user: dict | None) -> dict:
    """_state_view, and that a property whose types, relations or meanings are not confirmed cannot be confirmed yet."""
    state = _state_view(conn, row, user)
    waiting = waiting_on(conn, _content(row))
    return {**state, 'can_confirm': state['can_confirm'] and not waiting, 'waiting_on': waiting}


def _used_by(conn, element_id: str, user: dict | None) -> dict:
    """How many of the person's own saved answers stood on this property. Views and actions cannot use one yet."""
    where, args = ('user_id = ?', (user['id'],)) if user else ('user_id IS NULL', ())
    answers = sum(1 for (defs,) in conn.execute(f'SELECT definitions_json FROM qa_question WHERE {where}', args) if any(d['id'] == element_id for d in json.loads(defs)))
    return {'answers': answers, 'views': 0, 'actions': 0}


def _line(conn, row: dict, user: dict | None) -> dict:
    content = _content(row)
    anchors = json.loads(row['anchors_json']) if row['anchors_json'] else None
    shown = trial(conn, content, user)
    return {'id': content['english_name'], 'type': content['type'], 'name': content['name'], 'description': content['description'], 'kind': content['kind'], 'kind_name': KINDS[content['kind']],
            'says': describe(conn, content), 'output_type': content['output_type'], 'definition': content, 'problems': shown['problems'],
            'trial': shown, 'anchored': None if shown.get('limited_note') else anchors, 'used_by': _used_by(conn, row['element_id'], user), **derived_state(conn, row, user),
            'seen': shown.get('seen')}


def list_derived(conn, english_type: str, user: dict | None) -> list[dict]:
    """The derived properties of one type this person may see, with the trial on the data as it is now (the rows this person may read)."""
    _type_row(conn, english_type, user)
    out = []
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'derived:%' AND json_extract(content_json, '$.type') = ? ORDER BY element_id", (english_type,)).fetchall():
        row = element_row(conn, element_id)
        if derived_visible(conn, row, user):
            out.append(_line(conn, row, user))
    return out


def derived_log(conn, english_type: str, english_name: str, user: dict | None) -> dict:
    """What happened to one property, newest first, and the confirmations it has had (the history an edit leaves): who, when, what they confirmed and the trial they read."""
    row = _derived_row(conn, english_type, english_name, user)
    limited = any(restriction(conn, t, user) is not None for t in (type_id(x) for x in _content(row)['types']))
    history = [{'confirmed_by': by, 'confirmed_at': at, 'says': describe(conn, json.loads(content)), 'datasets': json.loads(versions), 'trial': None if limited or not snap else json.loads(snap).get('trial')}
               for by, at, content, versions, snap in conn.execute('SELECT confirmed_by, confirmed_at, content_json, dataset_versions_json, snapshot_json FROM confirmation WHERE element_id = ? ORDER BY id DESC',
                                                                    (row['element_id'],))]
    return {'log': log_entries(conn, [row['element_id']], user), 'confirmations': history}


def derived_shape(conn, payload: dict, user: dict | None) -> dict:
    """What a form needs to offer after the person chose a path: the hops with the way each goes, whether an aggregation is required, the measured type's columns with the
    aggregations each may have, and the layers (snapshot or version) of a many side."""
    owner = _content(_type_row(conn, payload.get('type'), user))
    path = payload.get('path') if isinstance(payload.get('path'), list) else []
    hops, problems = _walk(conn, owner['english_name'], [p for p in path if isinstance(p, str)][:MAX_HOPS], user, confirmed_only=True)
    out = {'hops': [{k: h[k] for k in ('relation', 'name', 'from_type', 'to_type', 'toward')} for h in hops], 'problems': problems, 'many': any(h['toward'] == 'many' for h in hops),
           'measured': None}
    if not hops or problems:
        return out
    m_row = _type_row(conn, hops[-1]['to_type'], user)
    m = _content(m_row)
    dataset = current_dataset(conn, m['dataset'])
    cols = dataset_columns(conn, dataset['id']) if dataset else {}
    codes = frozenset(f'{m["dataset"]}.{p["column"]}' for p in m['properties'] if p['enum'])
    available = [c for c in dict.fromkeys([*m['key'], *(p['column'] for p in m['properties'])]) if c in cols]
    options = aggregation_options([{'name': c, 'type': cols[c]['type'], 'origin': f'{m["dataset"]}.{c}'} for c in available], codes)
    layers = _layers(hops[-1], m, cols) if hops[-1]['toward'] == 'many' else []   # (a layer in the middle of a path is refused when it is saved)
    out['measured'] = {'type': m['english_name'], 'name': m['name'], 'layers': layers,
                       'columns': [{'name': c, 'type': cols[c]['type'], 'code': f'{m["dataset"]}.{c}' in codes, 'orderable': orderable(cols[c]['type']),
                                    'fns': [*options[c], 'latest']} for c in available],
                       'codes': [{'column': p['column'], 'name': p['name'], 'labels': sorted(set(meaning_labels(conn, m['english_name'], p['column']).values()))} for p in m['properties'] if p['enum']]}
    return out


def derived_form(conn, english_type: str, user: dict | None) -> dict:
    """What the form for a new derived property offers on this type: its columns (with a sample value, 样本) for a formula, the functions the editor lists, the
    confirmed relations a path is made of, and the hint that a formula over the type's own columns is better made in a pipeline."""
    owner = _content(_type_row(conn, english_type, user))
    dataset = current_dataset(conn, owner['dataset'])
    cols = dataset_columns(conn, dataset['id']) if dataset else {}
    limit = restriction(conn, type_id(english_type), user)
    sample = {}
    if dataset is not None:
        for record in dataset_records(conn, dataset):
            if limit is not None and not positions([record], limit):
                continue
            for c in cols:
                if c not in sample and record.get(c) not in (None, ''):
                    sample[c] = record[c]
    relations = []   # every confirmed relation this person may see (a path continues from the type it reached), the ones that join a type to itself left out
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'relation:%' AND state = 'confirmed' ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        c = _content(row)
        if _relation_visible(conn, row, user) and c['from'] != c['to']:
            names = {e: _content(element_row(conn, type_id(c[e])))['name'] for e in ('from', 'to')}
            relations.append({'key': c['english_name'], 'name': c['name'], 'from': c['from'], 'to': c['to'], 'from_name': names['from'], 'to_name': names['to'], 'cardinality': c['cardinality']})
    return {'columns': [{'name': c, 'type': cols[c]['type'], 'sample': sample.get(c)} for c in _own_columns(owner) if c in cols], 'sample_label': '样本',
            'functions': [{'group': g, 'name': n, 'template': t, 'does': d} for g, n, t, d in FUNCTION_DOCS], 'relations': relations, 'kinds': KINDS,
            'aggregations': STAT_FNS, 'hint': ROUTING_HINT}


def check_expression(conn, payload: dict, user: dict | None) -> dict:
    """校验 of an expression written for a formula, without trying it on rows: {'ok', 'errors': [{message, pos}], 'column_type'} over the columns of the type's dataset."""
    owner = _content(_type_row(conn, payload.get('type'), user))
    dataset = current_dataset(conn, owner['dataset'])
    if dataset is None:
        raise TypeRefused(f'数据集“{owner["dataset"]}”已经不在了', 409)
    cols = dataset_columns(conn, dataset['id'])
    expression = payload.get('expression')
    result = compile_expression(expression if isinstance(expression, str) else '', [{'name': c, 'type': cols[c]['type']} for c in _own_columns(owner) if c in cols])
    return {'ok': result['ok'], 'errors': result['errors'], 'column_type': COLUMN_TYPE.get(result['type']) if result['ok'] else None}


def trial_payload(conn, payload: dict, user: dict | None) -> dict:
    """试算 of a definition that is not saved: the same checks that refuse it, then the trial."""
    content = check_definition(conn, payload, user)
    return trial(conn, content, user)


# --- what other pages read ---------------------------------------------------------------------------------------------------------------------------

def confirmed_columns(conn, english_type: str, user: dict | None) -> list[dict]:
    """The confirmed derived properties of a type this person may see, each with its values by row number in the type's table over the rows they may read:
    [{'id', 'name', 'output_type', 'says', 'values': {row number: text}}]. One that cannot be computed now is left out."""
    out = []
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'derived:%' AND state = 'confirmed' AND json_extract(content_json, '$.type') = ? ORDER BY element_id",
                                      (english_type,)).fetchall():
        row = element_row(conn, element_id)
        if not derived_visible(conn, row, user):
            continue
        content = _content(row)
        result = evaluate(conn, content, user)
        if result['problems']:
            continue
        out.append({'id': element_id, 'english_name': content['english_name'], 'name': content['name'], 'output_type': result['output_type'], 'says': describe(conn, content),
                    'values': {i: text_of(v, result['output_type']) for i, v in result['values'].items()}})
    return out
