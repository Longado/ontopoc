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

from ontology_poc_generator import other_names
from ontology_poc_generator.name_checks import STAT_WORDS, claim_of
from ontology_poc_generator.named_views import ORDERED_TEXT, orderable
from ontology_poc_generator.object_relations import _relation_visible, relation_id
from ontology_poc_generator.object_types import (
    edit_sends_back,
    keep_unsaid,
    DERIVED_PREFIX, ENGLISH_NAME, limited_note, MAX_DESCRIPTION, MAX_NAME, TypeRefused, _content, _edit_names, _state_view, _text, _type_row, _visible,
    dataset_columns, element_row, enum_id, log_entries, refuse_if_limited, type_id, whole_type_row, write_confirmation, write_elements)
from ontology_poc_generator.object_views import _by_code, _choices, meaning_labels, new_value_words
from ontology_poc_generator.pipeline_expr import COLUMN_TYPE, FUNCTION_DOCS, MAX_LENGTH, WordMap, compile_expression, error_condition
from ontology_poc_generator.pipeline_funcs import register
from ontology_poc_generator.pipelines import PipelineRunError, deadline
from ontology_poc_generator.pipeline_ops import AGGREGATIONS, NUMBER_TYPES, _aggregate_sql, _q, aggregation_options
from ontology_poc_generator.row_rules import positions, restriction, types_on_dataset_of
from ontology_poc_generator.type_access import reads_hidden
from ontology_poc_generator.workspace_store import REPEAT_SAFE, current_dataset, dataset_records, fan_pipelines, fan_refusal, not_measured, not_measured_refusal, shown_pipeline
from ontology_poc_generator.lang import tr

KINDS = WordMap({'function': ('函数', 'Function'), 'statistic': ('统计', 'Statistic')})
MAX_HOPS = 3
DERIVED_SECONDS = 5   # the longest one request may spend working out derived properties


@contextmanager
def time_limit(conn):
    """The derived properties a request works out (on every row, each time a page or a list is read) are stopped after DERIVED_SECONDS; TypeRefused (409) says so."""
    try:
        with deadline(conn, DERIVED_SECONDS, tr('数据多的时候，给类型加行规则缩小范围，或把派生属性拆简单一些', 'When there is a lot of data, add a row rule to the type to narrow it down, or split the derived property into simpler ones')):
            yield
    except PipelineRunError as exc:
        raise TypeRefused(tr(f'派生属性{exc}', f'Derived property: {exc}'), 409) from None
MAX_CONDITIONS = 5
OPS = WordMap({'is': ('是', 'is'), 'is_not': ('不是', 'is not')})
STAT_FNS = WordMap({**{k: dict.__getitem__(AGGREGATIONS, k) for k in AGGREGATIONS}, 'latest': ('取最新', 'Latest')})
TRUE_ON_REPEATS = ('count_distinct', 'min', 'max', 'latest')   # what a snapshot, a version table or a repeated one-side leaves true
FN_FOR_CLAIM = {'sum': 'sum', 'mean': 'avg', 'median': 'median', 'p25': 'p25', 'p75': 'p75', 'min': 'min', 'max': 'max'}   # the statistic a name says -> the aggregation that is it
CLAIM_OF_FN = {v: k for k, v in FN_FOR_CLAIM.items()}
VERSION_WORD = re.compile(r'版本|version', re.I)
EXAMPLES = 5
def _routing_hint():
    return tr('只用这个对象自己的列算出来的值，建议在管道里做（计算列）：算一次，跟着数据集走。这里的派生属性适合要在问答里按定义引用、或者要随着确认状态管起来的值。',
              'For a value worked out only from the object\'s own columns, a pipeline (a calculated column) is the better place: it is worked out once and travels with the dataset. '
              'Derived properties are for values you want questions to use by definition, or to manage through confirmation.')


def _reset_labels():
    return (('type', tr('所属类型', 'Object type')), ('kind', tr('种类', 'Kind')), ('expression', tr('算式', 'Formula')), ('inputs', tr('输入的列', 'Input columns')), ('output_type', tr('输出类型', 'Output type')),
            ('path', tr('路径', 'Path')), ('measure', tr('要统计的列', 'Column to calculate')), ('fn', tr('统计方式', 'Calculation')), ('latest', tr('“取最新”的规则', 'The "latest" rule')), ('conditions', tr('条件', 'Conditions')))


def derived_id(type_english: str, english_name: str) -> str:
    return f'{DERIVED_PREFIX}{type_english}:{english_name}'


def _derived_row(conn, type_english, english_name, user: dict | None) -> dict:
    row = element_row(conn, derived_id(str(type_english), str(english_name)))
    if row is None or not derived_visible(conn, row, user):
        raise TypeRefused(tr('没有这个派生属性', 'No such derived property'), 404)
    return row


def derived_visible(conn, row: dict, user: dict | None) -> bool:
    """Seen by those who may see every type on its path (what it says and the values it gives are those types' rows); a viewer also needs it confirmed."""
    if user is not None and user['role'] == 'viewer' and row['state'] != 'confirmed':
        return False
    return all((r := element_row(conn, type_id(t))) is not None and _visible(conn, r, user) for t in _content(row)['types']) \
        and not reads_hidden(conn, row['element_id'], user, _content(row))   # a column kept from them: inputs, what it counts, conditions, or a join on its path


# --- walking the path ---------------------------------------------------------------------------------------------------------------------------------

def _walk(conn, owner: str, path: list, user: dict | None, confirmed_only: bool) -> tuple[list[dict], list[str]]:
    """(the hops of a path of relation names from `owner`, the problems). A hop says which way it goes: toward 'one' (each object has one on the other side: a lookup)
    or toward 'many' (it has several). A relation that joins a type to itself is not walked: it cannot say which role it means."""
    here, hops, problems = owner, [], []
    for key in path:
        row = element_row(conn, relation_id(str(key)))
        if row is None or (user is not None and not _relation_visible(conn, row, user)):
            problems.append(tr(f'没有关系“{key}”', f'There is no relation "{key}"'))
            break
        c = _content(row)
        if c['from'] == c['to']:
            problems.append(tr(f'关系“{c["name"]}”连着同一个类型，派生属性不走它：看不出是哪个角色', f'The relation "{c["name"]}" joins a type to itself, so a derived property does not follow it: it cannot tell which role is meant'))
            break
        if here not in (c['from'], c['to']):
            problems.append(tr(f'关系“{c["name"]}”连的是“{c["from"]}”和“{c["to"]}”，从“{here}”走不了', f'The relation "{c["name"]}" joins "{c["from"]}" and "{c["to"]}", so it cannot be followed from "{here}"'))
            break
        if confirmed_only and row['state'] != 'confirmed':
            problems.append(tr(f'关系“{c["name"]}”还没有确认：派生属性只走已确认的关系', f'The relation "{c["name"]}" is not confirmed yet: a derived property only follows confirmed relations'))
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
            problems.append(tr(f'对象类型“{english}”已经不在了', f'The object type "{english}" no longer exists'))
            continue
        c = _content(row)
        dataset = current_dataset(conn, c['dataset'])
        if dataset is None:
            problems.append(tr(f'数据集“{c["dataset"]}”已经不在了', f'The dataset "{c["dataset"]}" no longer exists'))
            continue
        types[english] = {'name': c['name'], 'content': c, 'dataset': dataset, 'cols': dataset_columns(conn, dataset['id'])}
    if problems:
        return {'problems': problems}

    def need(english: str, columns) -> None:
        gone = [c for c in dict.fromkeys(columns) if c not in types[english]['cols']]
        if gone:
            problems.append(tr(f'{types[english]["dataset"]["name"]} 第 {types[english]["dataset"]["version"]} 版里没有这些列了：{"、".join(gone)}', f'{types[english]["dataset"]["name"]} version {types[english]["dataset"]["version"]} no longer has these columns: {", ".join(gone)}'))
    if content['kind'] == 'function':
        need(owner, (i['column'] for i in content['inputs']))
        result = _compile(content['expression'], types[owner]['cols'], content['inputs'])
        if not result['ok']:
            problems.append(tr(f'算式现在读不了：{result["errors"][0]["message"]}', f'The formula cannot be read now: {result["errors"][0]["message"]}'))
        output = COLUMN_TYPE.get(result['type']) if result['ok'] else None
        compiled = result
    else:
        for h in hops:
            need(h['from_type'], [h['from_column']])
            need(h['to_type'], [h['to_column']])
        measured = hops[-1]['to_type']
        need(measured, [c for c in (content['measure']['column'], *(f['column'] for f in content['conditions']), *((content['latest']['order'], content['latest'].get('tie')) if content['latest'] else ())) if c])
        output, compiled = None, None
        distorted = not problems and content['fn'] not in (*REPEAT_SAFE, 'latest', 'value')
        marked = fan_pipelines(conn, types[measured]['dataset']['id'], user) if distorted else {}
        unmeasured = not_measured(conn, types[measured]['dataset']['id']) if distorted else None
        if unmeasured:   # a version whose copies were never measured: nothing but a count, a distinct count, a min or a max of it
            problems.append(not_measured_refusal(types[measured]['dataset']['name'], shown_pipeline(conn, unmeasured, user)))
        elif content['measure']['column'] in marked:   # a figure a join copied, worked out per object by what copies change: refused, the same as a question would be
            problems.append(fan_refusal(content['measure']['column'], marked[content['measure']['column']], content['fn']))
        if not problems:
            output = _output_type(content['fn'], types[measured]['cols'][content['measure']['column']]['type'] if content['measure']['column'] else None)
            for f in content['conditions']:
                if f['label'] not in meaning_labels(conn, measured, f['column']).values():
                    problems.append(tr(f'“{f["label"]}”现在不是“{f["column"]}”已写的含义', f'"{f["label"]}" is no longer a meaning written for "{f["column"]}"'))
            if content['latest'] and not orderable(types[measured]['cols'][content['latest']['order']]['type']):
                problems.append(tr(f'“{content["latest"]["order"]}”现在的内容排不出先后（数字、年月、日期才可以）', f'"{content["latest"]["order"]}" can no longer be put in order (only numbers, months and dates can)'))
    if not problems and output != content['output_type']:
        problems.append(tr(f'输出类型变了：定义时是{TYPE_WORD.get(content["output_type"], content["output_type"])}，现在是{TYPE_WORD.get(output, output)}', f'The output type changed: it was {TYPE_WORD.get(content["output_type"], content["output_type"])} when defined and is {TYPE_WORD.get(output, output)} now'))
    if problems:
        return {'problems': problems}
    return {'problems': [], 'types': types, 'hops': hops, 'owner': owner, 'measured': hops[-1]['to_type'] if hops else owner, 'output_type': output, 'compiled': compiled}


TYPE_WORD = WordMap({'integer': ('整数', 'whole number'), 'decimal': ('小数', 'decimal'), 'text': ('文本', 'text'), 'date': ('日期', 'date'), 'month': ('月份', 'month'), 'datetime': ('日期时间', 'date and time'), 'boolean': ('是否', 'yes/no')})


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
        if content['kind'] != 'function' and any(restriction(conn, type_id(e), user) is not None for e in chain['types']):
            with _tables(conn, chain, None) as everything:   # the same joins over all the rows: an object whose related rows are all outside this person's rows has no value for them
                body = _outside_the_rows(content, chain, body, _outside(conn, chain, tables, everything))
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


def row_values(conn, content: dict, rows: list[int]) -> dict[int, str | None]:
    """A per-row formula (kind function) worked out on these rows of its type's table only, {row number: the value as text}; {} for a statistic or one that cannot
    be read now. For a lookup by key: the rows were found by the key and checked against the reader's row rule before this is asked."""
    if content['kind'] != 'function' or not rows:
        return {}
    chain = _chain(conn, content, None)
    if chain['problems']:
        return {}
    register(conn)
    result = chain['compiled']
    failing, failing_params = error_condition(result['sql'], result['params'], result['fields'])
    table = _q(chain['types'][chain['owner']]['dataset']['table_name'])
    found = conn.execute(f'SELECT rowid, ({result["sql"]}), ({failing}) FROM {table} WHERE rowid IN ({",".join("?" * len(rows))}) ORDER BY rowid',
                         [*result['params'], *failing_params, *rows]).fetchall()
    return {i: text_of(_plain(v, chain['output_type']) if not bad else None, chain['output_type']) for i, v, bad in found}


def _outside(conn, chain: dict, tables: dict, everything: dict) -> set[int]:
    """The objects of the owner type that have related rows, none of which this person may read."""
    owner = chain['owner']
    count = lambda t: dict(conn.execute(f'SELECT t0.{t[owner][1]}, COUNT(*) FROM {_joins(chain, t)} GROUP BY 1').fetchall())
    seen, total = count(tables), count(everything)
    return {i for i, n in total.items() if n and not seen.get(i)}


def _outside_the_rows(content: dict, chain: dict, body: dict, outside: set[int]) -> dict:
    """The evaluation with those objects' values taken back: a count of 0 there would say there is nothing, when what there is lies outside the rows they may read."""
    here = {i for i in body['values'] if i in outside}
    counted = content['fn'] in ('count', 'count_distinct')
    no_value = {**body['no_value'], 'no_rows': body['no_value']['no_rows'] - (0 if counted else len(here)), 'outside': len(here)}
    return {**body, 'values': {i: None if i in here else v for i, v in body['values'].items()}, 'no_value': no_value, 'outside': here}


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
    return {'values': values, 'objects': objects, 'failed': unreadable + ambiguous, 'rows_used': rows_used, 'shared_keys': shared, 'orphans': _orphans(conn, chain, tables),
            'no_value': {'no_rows': no_rows, 'unreadable': unreadable, 'ambiguous': ambiguous}}


def _orphans(conn, chain: dict, tables: dict) -> list[dict]:
    """For each hop, the rows on the many end whose key is filled and finds no row on the one end: {'many', 'one' (type names), 'rows', 'keys' (the first few)}. A statistic
    that goes through the relation leaves those rows out (toward the many end they are in no owner's count, toward the one end the owner has nothing to look up)."""
    out = []
    for h in chain['hops']:
        many_end, one_end = ((h['to_type'], h['to_column']), (h['from_type'], h['from_column'])) if h['toward'] == 'many' else ((h['from_type'], h['from_column']), (h['to_type'], h['to_column']))
        (m_type, m_col), (o_type, o_col) = many_end, one_end
        m_table, o_table = tables[m_type][0], tables[o_type][0]
        lost = conn.execute(f"SELECT {_q(m_col)}, COUNT(*) FROM {m_table} WHERE {_q(m_col)} <> '' AND {_q(m_col)} NOT IN (SELECT {_q(o_col)} FROM {o_table} WHERE {_q(o_col)} <> '') "
                            f'GROUP BY {_q(m_col)} ORDER BY 2 DESC, 1 LIMIT {EXAMPLES}').fetchall()
        rows = conn.execute(f"SELECT COUNT(*) FROM {m_table} WHERE {_q(m_col)} <> '' AND {_q(m_col)} NOT IN (SELECT {_q(o_col)} FROM {o_table} WHERE {_q(o_col)} <> '')").fetchone()[0]
        if rows:
            out.append({'many': chain['types'][m_type]['name'], 'one': chain['types'][o_type]['name'], 'rows': rows, 'keys': [k for k, _ in lost]})
    return out


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
    lines = [{'ok': result['failed'] == 0, 'text': tr(f'{"你能看到的" if limited else ""}{n} 个{owner_name}里，{with_value} 个算出了值，{empty} 个没有值', f'Of {"the " if limited else ""}{n} {owner_name} objects{" you can see" if limited else ""}, {with_value} got a value and {empty} have none')}]
    if limited:
        lines.append({'ok': True, 'text': limited_note()})
    lines += _failure_lines(content, result, owner_name)
    if result['rows_used'] is not None:
        lines.append({'ok': True, 'text': tr(f'一共用了 {result["rows_used"]} 行{chain["types"][chain["measured"]]["name"]}的数据', f'{result["rows_used"]} {chain["types"][chain["measured"]]["name"]} rows were used in total')})
    with _tables(conn, chain, user) as tables:
        shown = [i for i, v in result['values'].items() if v is not None][:EXAMPLES]
        labels = _owner_key_text(conn, chain, tables, shown)
        sample = _sample(conn, content, chain, tables) if content['kind'] == 'function' else None
    examples = [{'object': labels[i], 'value': text_of(result['values'][i], result['output_type'])} for i in shown]
    numbers = {k: result.get(k) for k in ('objects', 'with_value', 'failed', 'rows_used', 'shared_keys', 'no_value')}
    return {'problems': [], 'lines': lines, 'examples': examples, 'sample': sample, 'numbers': None if limited else numbers, 'datasets': result['datasets'], 'output_type': result['output_type'],
            'seen': None if limited else seen_of(result), 'limited_note': limited_note() if limited else None}


def _failure_lines(content: dict, result: dict, owner_name: str) -> list[dict]:
    no = result['no_value']
    out = []
    if no.get('empty_input'):
        out.append({'ok': False, 'text': tr(f'{no["empty_input"]} 个{owner_name}的输入里有空的，算式没有算它们（空值不当成 0）', f'{no["empty_input"]} {owner_name} objects have an empty input, so the formula skipped them (an empty value is not treated as 0)')})
    if result['failed'] and content['kind'] == 'function':
        out.append({'ok': False, 'text': tr(f'{result["failed"]} 个{owner_name}输入都有值，算式却算不出结果（除以 0、日期不对）', f'{result["failed"]} {owner_name} objects have every input but the formula gives no result (division by 0, an invalid date)')})
    if no.get('outside'):
        out.append({'ok': True, 'text': tr(f'{no["outside"]} 个{owner_name}的相关行都不在你能看的行里，显示为 —，不是 0', f'{no["outside"]} {owner_name} objects have no related row among the rows you can see, shown as —, not 0')})
    if no.get('no_rows'):
        out.append({'ok': False, 'text': tr(f'{no["no_rows"]} 个{owner_name}没有可以统计的相关数据（没有相关的行，或条件筛完一行不剩），没有值，不是 0', f'{no["no_rows"]} {owner_name} objects have no related data to calculate (no related rows, or the conditions leave none), so they have no value, not 0')})
    if no.get('unreadable'):
        out.append({'ok': False, 'text': tr(f'{no["unreadable"]} 个{owner_name}有相关的行，但统计的列读不出值', f'{no["unreadable"]} {owner_name} objects have related rows, but the column to calculate has no readable value')})
    if no.get('ambiguous'):
        out.append({'ok': False, 'text': tr(f'{no["ambiguous"]} 个{owner_name}在另一边找到了不止一个不同的值，没有取其中一个', f'{no["ambiguous"]} {owner_name} objects found more than one different value on the other side, and none was picked')})
    if result.get('shared_keys'):
        out.append({'ok': False, 'text': tr(f'{result["shared_keys"]} 个{owner_name}和别的{owner_name}用同一个连接键，它们各自数到了同一批行', f'{result["shared_keys"]} {owner_name} objects share a join key with other {owner_name} objects, so each counted the same rows')})
    for o in result.get('orphans') or []:
        out.append({'ok': False, 'text': tr(f'有 {o["rows"]} 行{o["many"]}因为找不到{o["one"]}没算进来（{"、".join(o["keys"])}）', f'{o["rows"]} {o["many"]} rows were left out because no {o["one"]} was found ({", ".join(o["keys"])})')})
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
    return {'label': tr('样本', 'Sample'), 'inputs': [{'column': i['column'], 'value': v} for i, v in zip(content['inputs'], row[2:])], 'result': text_of(_plain(row[1], chain['output_type']), chain['output_type'])}


def describe(conn, content: dict) -> str:
    """The definition as a sentence: 客户的已取消订单数：每个客户，数订单里 状态码 是「已取消」的行."""
    owner = element_row(conn, type_id(content['type']))
    owner_name = _content(owner)['name'] if owner else content['type']
    if content['kind'] == 'function':
        return tr(f'{owner_name}的{content["name"]} = {content["expression"]}', f'{content["name"]} of {owner_name} = {content["expression"]}')
    names = []
    for h in content['path']:
        row = element_row(conn, relation_id(h))
        names.append(_content(row)['name'] if row else h)
    measured = element_row(conn, type_id(content['types'][-1]))
    measured_name = _content(measured)['name'] if measured else content['types'][-1]
    where = tr('，且', ', and ').join(tr(f'「{f["column"]}」{OPS[f["op"]]}「{f["label"]}」', f'"{f["column"]}" {OPS[f["op"]]} "{f["label"]}"') for f in content['conditions'])
    column, fn = content['measure']['column'], content['fn']
    if fn in ('latest', 'value'):
        what = tr(f'取「{column}」', f'take "{column}"') + ((tr(f'（按「{content["latest"]["order"]}」最新的一行）', f' (from the latest row by "{content["latest"]["order"]}")')) if fn == 'latest' else '')
    elif fn == 'count' and not column:
        what = tr('数行数', 'count the rows')
    else:
        what = tr(f'{STAT_FNS[fn]}「{column}」', f'{STAT_FNS[fn]} "{column}"')
    return tr(f'{owner_name}的{content["name"]}：每个{owner_name}，经过 {" → ".join(names)}，{measured_name}里' + (f'{where}的行，' if where else '的行，') + what,
              f'{content["name"]} of {owner_name}: for each {owner_name}, through {" → ".join(names)}, in {measured_name} ' + (f'on the rows where {where}, ' if where else 'rows, ') + what)


# --- the definition a person writes -------------------------------------------------------------------------------------------------------------------

def _own_columns(owner: dict) -> list[str]:
    return list(dict.fromkeys([*owner['key'], *(p['column'] for p in owner['properties'])]))


def _stat_word(kind: str) -> str:
    return STAT_WORDS.get(kind) or tr(f'第 {kind[1:]} 百分位', f'percentile {kind[1:]}')


def _name_claim(name: str, fn: str) -> None:
    """A name that says a statistic is that statistic: 交付天数P50 is the median, 平均 is the mean, 合计 the sum. Refused when the aggregation is another."""
    claim = claim_of(name)
    if claim is None or CLAIM_OF_FN.get(fn) == claim[0]:
        return
    offer = FN_FOR_CLAIM.get(claim[0])
    how = tr(f'选“{STAT_FNS[offer]}”', f'choose "{STAT_FNS[offer]}"') if offer else tr(f'这里没有这种算法（只有{"、".join(STAT_FNS[f] for f in FN_FOR_CLAIM.values())}）', f'there is no such calculation here (only {", ".join(STAT_FNS[f] for f in FN_FOR_CLAIM.values())})')
    said = tr(f'“{claim[1]}”，也就是{_stat_word(claim[0])}', f'"{claim[1]}", which means {_stat_word(claim[0])}')
    raise TypeRefused(tr(f'名字“{name}”说的是{said}，统计方式选的却是“{STAT_FNS[fn]}”：名字和算法对不上，别人会照名字读它。要{_stat_word(claim[0])}就{how}，要{STAT_FNS[fn]}就改名字',
                         f'The name "{name}" says {said}, but the calculation chosen is "{STAT_FNS[fn]}": the name and the calculation do not match, and others will read it by its name. For {_stat_word(claim[0])}, {how}; for {STAT_FNS[fn]}, change the name'),
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
        word = tr('快照', 'snapshot') if layer['kind'] == 'snapshot' else tr('版本', 'version')
        if i != len(hops) - 1:
            raise TypeRefused(tr(f'“{t["name"]}”每个{chain["types"][hops[i]["from_type"]]["name"]}有多个{layer["column"]}的记录（{word}），它要放在路径的最后一步：路径还往它后面走，同一件事会被每个{word}算一遍',
                                 f'Each {chain["types"][hops[i]["from_type"]]["name"]} has several {layer["column"]} records ({word}) in "{t["name"]}", so it must be the last step of the path: the path goes on past it, and the same thing would be counted once for each {word}'))
        if fn not in TRUE_ON_REPEATS:
            what = tr('数它的行', 'count its rows') if fn == 'count' else tr(f'把它的“{content["measure"]["column"]}”{STAT_FNS[fn]}', f'{STAT_FNS[fn]} its "{content["measure"]["column"]}"')
            why = tr('一个存量（库存）每个月存一次，把各月加在一起不是库存', 'A stock (inventory) is stored once a month, and adding the months together is not the stock') if layer['kind'] == 'snapshot' else tr('同一件事的几个版本会被当成几件事', 'Several versions of the same thing would be counted as several things')
            raise TypeRefused(tr(f'“{t["name"]}”每个{chain["types"][hops[i]["from_type"]]["name"]}有多个{layer["column"]}的记录（{layer["column"]}是它主键的一部分，是{word}），{what}：{why}。'
                                 f'可以选“取最新”，按“{layer["column"]}”取每个{chain["types"][hops[i]["from_type"]]["name"]}最新的一条；要数个数就数去重的“{hops[i]["to_column"]}”',
                                 f'Each {chain["types"][hops[i]["from_type"]]["name"]} has several {layer["column"]} records in "{t["name"]}" ({layer["column"]} is part of its key and is the {word}), and you chose to {what}: {why}. '
                                 f'Choose "Latest" to take the latest row of each {chain["types"][hops[i]["from_type"]]["name"]} by "{layer["column"]}", or to count, count distinct "{hops[i]["to_column"]}"'),
                              detail={'offer': [{'fn': 'latest', 'order': layer['column']}, {'fn': 'count_distinct', 'column': hops[i]['to_column']}], 'layer': layer})
        if fn == 'latest' and content['latest']['order'] != layer['column']:
            raise TypeRefused(tr(f'“{t["name"]}”是按“{layer["column"]}”存的{word}，“取最新”要按“{layer["column"]}”比先后，不能按“{content["latest"]["order"]}”', f'"{t["name"]}" stores the {word} by "{layer["column"]}", so "Latest" must compare by "{layer["column"]}", not by "{content["latest"]["order"]}"'), detail={'offer': [{'fn': 'latest', 'order': layer['column']}]})
    first_many = next(iter(many_at), None)
    if first_many is not None and any(h['toward'] == 'one' for h in hops[first_many + 1:]) and fn not in TRUE_ON_REPEATS:
        crossed = tr('、', ', ').join(chain['types'][h['to_type']]['name'] for h in hops[first_many + 1:] if h['toward'] == 'one')
        raise TypeRefused(tr(f'路径先走到“多”的一边，再回到“一”的一边（{crossed}）：一边的每个对象会被它每一行重复算一遍，“{STAT_FNS[fn]}”会把同一个对象算好几次。'
                             f'可以选“去重计数”、“最小”、“最大”或“取最新”，或者把要统计的列换成多的一边的列',
                             f'The path goes to the "many" side and then back to the "one" side ({crossed}): each object on the one side is repeated for each of its rows, so "{STAT_FNS[fn]}" would count the same object several times. '
                             f'Choose "Count distinct", "Min", "Max" or "Latest", or switch the column to calculate to one on the many side'), detail={'offer': [{'fn': f} for f in TRUE_ON_REPEATS]})


def check_definition(conn, payload: dict, user: dict | None, english_name: str | None = None) -> dict:
    """The content of a derived property as a person wrote it. TypeRefused says what is wrong (and for a refused aggregation what to choose instead)."""
    english = payload.get('english_name') if english_name is None else english_name
    if not isinstance(english, str) or not ENGLISH_NAME.fullmatch(english):
        raise TypeRefused(tr('英文名只能用字母、数字和下划线，字母开头，最多 40 个字符', 'An English name can only use letters, digits and underscores, start with a letter, and be at most 40 characters'))
    name = _text(payload.get('name'), tr('名称', 'Name'), MAX_NAME)
    description = _text(payload.get('description') or '', tr('说明', 'Description'), MAX_DESCRIPTION, required=False)
    owner_row = whole_type_row(conn, payload.get('type'), user)
    owner = _content(owner_row)
    dataset = current_dataset(conn, owner['dataset'])
    if dataset is None:
        raise TypeRefused(tr(f'数据集“{owner["dataset"]}”已经不在了', f'The dataset "{owner["dataset"]}" no longer exists'), 409)
    cols = dataset_columns(conn, dataset['id'])
    kind = payload.get('kind')
    if kind not in KINDS:
        raise TypeRefused(tr('种类要选函数或统计', 'Choose function or statistic as the kind'))
    base = other_names.put({'english_name': english, 'name': name, 'description': description, 'type': owner['english_name'], 'kind': kind},
                           other_names.clean(payload.get('other_names'), tr(f'派生属性“{name}”', f'the derived property "{name}"')))
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
        raise TypeRefused(tr('要写算式', 'Write a formula'))
    if len(expression) > MAX_LENGTH:
        raise TypeRefused(tr(f'算式最长 {MAX_LENGTH} 个字', f'A formula can be at most {MAX_LENGTH} characters'))
    available = [{'column': c, 'type': cols[c]['type']} for c in _own_columns(owner) if c in cols]
    result = compile_expression(expression, [{'name': a['column'], 'type': a['type']} for a in available])
    if not result['ok']:
        first = result['errors'][0]
        raise TypeRefused(tr(f'算式不对：{first["message"]}' + (f'（第 {first["pos"] + 1} 个字符）' if first['pos'] else ''), f'The formula is wrong: {first["message"]}' + (f' (character {first["pos"] + 1})' if first['pos'] else '')))
    by_name = {a['column']: a for a in available}
    return {'expression': expression.strip(), 'inputs': [by_name[f] for f in sorted(result['fields'])], 'output_type': COLUMN_TYPE[result['type']]}


def _statistic_body(conn, payload: dict, owner: dict, name: str, user: dict | None) -> dict:
    path = payload.get('path')
    if not isinstance(path, list) or not path or len(path) > MAX_HOPS or not all(isinstance(p, str) for p in path):
        raise TypeRefused(tr(f'路径要选 1 到 {MAX_HOPS} 个关系，一个接着一个', f'Choose 1 to {MAX_HOPS} relations for the path, one after another'))
    hops, problems = _walk(conn, owner['english_name'], path, user, confirmed_only=True)
    if problems:
        raise TypeRefused('；'.join(problems), 409)
    measured = hops[-1]['to_type']
    m_row = whole_type_row(conn, measured, user)
    m = _content(m_row)
    m_dataset = current_dataset(conn, m['dataset'])
    if m_dataset is None:
        raise TypeRefused(tr(f'数据集“{m["dataset"]}”已经不在了', f'The dataset "{m["dataset"]}" no longer exists'), 409)
    cols = dataset_columns(conn, m_dataset['id'])
    for h in hops:   # each type on the path must be readable by this person
        whole_type_row(conn, h['to_type'], user)
    many = any(h['toward'] == 'many' for h in hops)
    posted = payload.get('measure') if isinstance(payload.get('measure'), dict) else {}
    column, fn = posted.get('column') or None, payload.get('fn') or None
    available = list(dict.fromkeys([*m['key'], *(p['column'] for p in m['properties'])]))
    if column is not None and (column not in available or column not in cols):
        raise TypeRefused(tr(f'“{m["name"]}”没有属性“{column}”', f'"{m["name"]}" has no property "{column}"'))
    if many:
        if fn not in STAT_FNS:
            raise TypeRefused(tr(f'路径经过“多”的一边（{"、".join(h["name"] for h in hops if h["toward"] == "many")}），每个对象有好几行，要选统计方式：{"、".join(STAT_FNS.values())}', f'The path goes through the "many" side ({", ".join(h["name"] for h in hops if h["toward"] == "many")}), so each object has several rows. Choose a calculation: {", ".join(STAT_FNS.values())}'))
        if column is None and fn != 'count':
            raise TypeRefused(tr(f'“{STAT_FNS[fn]}”要指定统计哪一列；只有“计数”可以不选列（数行数）', f'"{STAT_FNS[fn]}" needs a column to calculate; only "Count" can go without one (it counts rows)'))
        if column is not None and fn in AGGREGATIONS:
            codes = frozenset(f'{m["dataset"]}.{p["column"]}' for p in m['properties'] if p['enum'])
            options = aggregation_options([{'name': column, 'type': cols[column]['type'], 'origin': f'{m["dataset"]}.{column}'}], codes)[column]
            if fn not in options:
                is_code = f'{m["dataset"]}.{column}' in codes and cols[column]['type'] in NUMBER_TYPES
                raise TypeRefused(tr(f'“{column}”是代码列，把代码{STAT_FNS[fn]}没有意义；可以用计数或去重计数', f'"{column}" is a code column, so applying {STAT_FNS[fn]} to codes means nothing; use Count or Count distinct') if is_code
                                  else tr(f'“{column}”是{TYPE_WORD[cols[column]["type"]]}列，不能{STAT_FNS[fn]}；可以用：{"、".join(STAT_FNS[f] for f in options)}', f'"{column}" is a {TYPE_WORD[cols[column]["type"]]} column and cannot be used with {STAT_FNS[fn]}; you can use: {", ".join(STAT_FNS[f] for f in options)}'))
    else:
        if fn not in (None, 'value'):
            raise TypeRefused(tr('这条路径只走到“一”的那一边，每个对象在那边只有一个值，不用选统计方式', 'This path only goes to the "one" side, where each object has a single value, so no calculation is needed'))
        if column is None:
            raise TypeRefused(tr('要选取哪一列的值', 'Choose which column to take the value from'))
        fn = 'value'
    latest = None
    if fn == 'latest':
        raw = payload.get('latest') if isinstance(payload.get('latest'), dict) else {}
        order, tie = raw.get('order'), raw.get('tie') or None
        if column is None or order not in cols or not orderable(cols[order]['type']):
            raise TypeRefused(tr('“取最新”要选一个排得出先后的列（数字、年月、日期）来比先后', '"Latest" needs a column that can be put in order (a number, month or date) to compare by'))
        if tie is not None and (tie not in cols or tie == order or not orderable(cols[tie]['type'])):
            raise TypeRefused(tr('比先后相同时用的列，要是另一个排得出先后的列', 'The column used to break a tie must be another column that can be put in order'))
        latest = {'order': order, 'tie': tie}
    conditions = _conditions(conn, payload.get('conditions'), m, cols)
    return {'path': [h['relation'] for h in hops], 'types': [owner['english_name'], *(h['to_type'] for h in hops)], 'measure': {'column': column}, 'fn': fn, 'latest': latest,
            'conditions': conditions, 'output_type': _output_type(fn, cols[column]['type'] if column else None), 'expression': None, 'inputs': []}


def _conditions(conn, posted, m: dict, cols: dict) -> list[dict]:
    posted = posted or []
    if not isinstance(posted, list) or len(posted) > MAX_CONDITIONS or not all(isinstance(f, dict) for f in posted):
        raise TypeRefused(tr(f'条件要写成列表，最多 {MAX_CONDITIONS} 个', f'Conditions must be a list of at most {MAX_CONDITIONS}'))
    codes = {p['column'] for p in m['properties'] if p['enum']}
    out = []
    for f in posted:
        column, op, label = f.get('column'), f.get('op'), f.get('label')
        if column not in codes:
            raise TypeRefused(tr(f'“{column}”不是“{m["name"]}”的代码列，没有含义可以拿来筛', f'"{column}" is not a code column of "{m["name"]}", so there is no meaning to filter by'))
        if op not in OPS:
            raise TypeRefused(tr('条件只能是“是”或“不是”', 'A condition can only be "is" or "is not"'))
        known = sorted(set(meaning_labels(conn, m['english_name'], column).values()))
        if label not in known:
            raise TypeRefused(tr(f'“{label}”不是“{column}”已写的含义' + (f'：{"、".join(known)}' if known else '，先给这一列写含义'), f'"{label}" is not a meaning written for "{column}"' + (f': {", ".join(known)}' if known else '. Write meanings for this column first')))
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
            raise TypeRefused(tr(f'英文名“{content["english_name"]}”和已有的“{o["english_name"]}”只差大小写', f'The English name "{content["english_name"]}" differs from the existing "{o["english_name"]}" only in case'), 409)
        if o['type'] in siblings:
            taken.add(o['name'])
    if content['name'] in taken:
        raise TypeRefused(tr(f'“{content["name"]}”已经是这个数据集的一列、一个属性，或另一个派生属性的名字', f'"{content["name"]}" is already the name of a column or property of this dataset, or of another derived property'), 409)
    clash = next((n for n in other_names.of(content) if n in taken), None)   # an other name is a name: not a column or property of this dataset either
    if clash:
        raise TypeRefused(tr(f'“{clash}”已经是这个数据集的一列、一个属性，或另一个派生属性的名字', f'"{clash}" is already the name of a column or property of this dataset, or of another derived property'), 409)
    other_names.check_view(conn, content, mine, 'derived')


def reset_reasons(old: dict, new: dict) -> list[str]:
    """What changed that a confirmation was about: everything the property computes. The display name and the description are not on the list."""
    return [label for key, label in _reset_labels() if old.get(key) != new.get(key)]


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
        raise TypeRefused(tr(f'这个类型已经有英文名“{content["english_name"]}”的派生属性', f'This object type already has a derived property with the English name "{content["english_name"]}"'), 409)
    check_names_free(conn, content)
    chain, result = _chain(conn, content, None), evaluate(conn, content, None)
    write_elements(conn, [_change(content, result, who)], {derived_id(content['type'], content['english_name']): _reads(content, chain)})
    return {'id': content['english_name'], 'type': content['type'], 'trial': trial(conn, content, user)}


def update_derived(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """{type, english_name, version, ...the fields of create}: a change to what it computes puts it forward again as this person's, and a confirmed one stops being
    confirmed (what it had been confirmed on stays in the history); so does saving one that was sent back. The display name and the description keep the state (on one that waits; a confirmed one is put forward again by any change of what it says, whoever makes it: object_types.edit_sends_back)."""
    row = _derived_row(conn, payload.get('type'), payload.get('english_name'), user)
    if payload.get('version') != row['version']:
        raise TypeRefused(tr('这个派生属性在你打开之后被改了，请刷新后再改', 'This derived property was changed after you opened it. Refresh and edit again'), 409)
    old = _content(row)
    content = check_definition(conn, {**keep_unsaid(payload, old), 'type': old['type'], 'other_names': payload['other_names'] if 'other_names' in payload else other_names.of(old)}, user, old['english_name'])
    check_names_free(conn, content)
    others = other_names.of(old) != other_names.of(content)
    reset = reset_reasons(old, content) or edit_sends_back(row, user, (old['name'], old['description']) != (content['name'], content['description']), others)
    if reset or row['state'] in ('proposed', 'rejected'):
        chain, result = _chain(conn, content, None), evaluate(conn, content, None)
        from ontology_poc_generator.object_types import _flag_readers   # a view that uses it as a condition stops being confirmed with it
        said = tr(f'它用的派生属性“{old["name"]}”改了，要重新确认', f'The derived property "{old["name"]}" it uses changed and needs confirming again')
        write_elements(conn, [_change(content, result, who)], {row['element_id']: _reads(content, chain)}, {row['element_id']: row['version']},
                       after=(lambda c: _flag_readers(c, row['element_id'], said, [])) if row['state'] == 'confirmed' else None)
    elif (old['name'], old['description']) != (content['name'], content['description']) or others:
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
    (SelfConfirmation otherwise); a person a row rule limits confirms nothing, since the numbers they read are of some of the rows. `new_values`: as for a view, a
    value a condition column has now that it did not have when the property was confirmed is answered "in" or "out" first (409 naming it otherwise); "out" adds a
    condition and makes the changed property this person's proposal."""
    row = _derived_row(conn, payload.get('type'), payload.get('english_name'), user)
    refuse_if_limited(conn, row, user)
    if payload.get('version') != row['version']:
        raise TypeRefused(tr('确认要带上你看到的那一版；它在你看过之后被改了，请刷新后重新看一遍', 'Confirming needs the version you saw, and it was changed after you looked. Refresh and look again'), 409)
    if row['state'] == 'confirmed':
        raise TypeRefused(tr('已经确认过了', 'Already confirmed'), 409)
    if row['state'] == 'rejected':
        raise TypeRefused(tr('已经被退回了：要先按退回的理由改，再重新提出', 'It was sent back: change it as the reason says, then propose it again'), 409)
    if not isinstance(payload.get('seen'), dict):
        raise TypeRefused(tr('确认要带上你看到的数据版本和对象数（seen）', 'Confirming needs the dataset versions and object counts you saw (seen)'))
    content = _content(row)
    waiting = waiting_on(conn, content)
    if waiting:
        raise TypeRefused(tr(f'它用到的{"、".join("“" + w["name"] + "”" for w in waiting)}还没有确认，要先确认它们', f'It uses {", ".join(chr(34) + w["name"] + chr(34) for w in waiting)}, which {"is" if len(waiting) == 1 else "are"} not confirmed yet. Confirm {"it" if len(waiting) == 1 else "them"} first'), 409)
    chain = _chain(conn, content, user)
    if chain['problems']:
        raise TypeRefused(tr(f'按现在的数据算不出来，不能确认：{"；".join(chain["problems"])}', f'It cannot be worked out from the data as it is now, so it cannot be confirmed: {"; ".join(chain["problems"])}'), 409)
    if chain['types'] and [chain['owner'], *(h['to_type'] for h in chain['hops'])] != content['types']:
        raise TypeRefused(tr('它走的关系连的类型变了，请重新保存一次再确认', 'The types the relations connect have changed. Save it again, then confirm'), 409)
    _refusals(conn, content, chain)
    result = evaluate(conn, content, user)
    if payload['seen'] != seen_of(result):
        raise TypeRefused(tr(f'数据在你看过之后变了：{result["owner_dataset"]} 等数据集的版本或这个属性的值不是你看到的那样了，请刷新后重新看一遍', f'The data changed after you looked: the version of {result["owner_dataset"]} and other datasets, or the values of this property, are no longer what you saw. Refresh and look again'), 409)
    open_ = open_new_values(conn, row)
    choices = _choices(payload.get('new_values'), open_) if open_ else {}
    out = [o for o in open_ if choices[(o['column'], o['value'])] == 'out']
    if out:   # the definition changes, so it is not what the other builder looked at either: it goes to them
        return _keep_out(conn, row, content, out, who)
    shown = trial(conn, content, user)
    write_confirmation(conn, row['element_id'], content, _evidence(result), who, _anchors(result), result['datasets'], row['version'], _reads(content, chain),
                       snapshot={'trial': {'numbers': shown['numbers'], 'examples': shown['examples'], 'sample': shown['sample'], 'lines': shown['lines']},
                                 **({'new_values': [{**o, 'choice': 'in'} for o in open_]} if open_ else {})})
    return {'state': 'confirmed'}


def _condition_codes(conn, row: dict) -> tuple[dict, dict] | None:
    """({column: the values it had when the property was last confirmed}, {column: {value: rows} now}) for the code columns its conditions read, on the type it
    measures: then is the dataset version its confirmation was made on. None when it has no conditions, the data has not moved since, or that version is gone."""
    content = _content(row)
    if content['kind'] != 'statistic' or not content['conditions'] or not row['anchors_json']:
        return None
    t = element_row(conn, type_id(content['types'][-1]))
    dataset = current_dataset(conn, _content(t)['dataset']) if t else None
    version = (json.loads(row['anchors_json']).get('datasets') or {}).get(dataset['name']) if dataset else None
    if version is None or version == dataset['version']:
        return None
    then = conn.execute('SELECT id FROM dataset WHERE name = ? AND version = ?', (dataset['name'], version)).fetchone()
    if then is None:
        return None
    then_cols, now_cols = dataset_columns(conn, then[0]), dataset_columns(conn, dataset['id'])
    columns = dict.fromkeys(f['column'] for f in content['conditions'])
    return ({c: sorted((then_cols.get(c) or {}).get('counts') or {}) for c in columns}, {c: dict((now_cols.get(c) or {}).get('counts') or {}) for c in columns})


def _as_view(content: dict) -> dict:
    """The conditions in the shape object_views words them: a view of the type the property measures."""
    return {'type': content['types'][-1], 'filters': content['conditions'], 'latest': None}


def open_new_values(conn, row: dict) -> list[dict]:
    """object_views.open_new_values for a derived property: the values a code column of an "is not" condition has now that it did not have when the property was
    confirmed, and that its conditions do not already leave out (by the meaning written for them): [{'column', 'value', 'label', 'rows'}]. The property counts each
    of them in unless someone says otherwise, so confirming asks. Only a property that needs another look asks."""
    found = _condition_codes(conn, row) if row['state'] == 'needs_look' else None
    if found is None:
        return []
    was, now = found
    content = _content(row)
    out = []
    for column in dict.fromkeys(f['column'] for f in content['conditions'] if f['op'] == 'is_not'):
        labels = meaning_labels(conn, content['types'][-1], column)
        kept_out = {f['label'] for f in content['conditions'] if f['column'] == column and f['op'] == 'is_not'}
        for value in sorted(set(now[column]) - set(was[column]), key=lambda v: _by_code((v,))):
            if labels.get(value) not in kept_out:
                out.append({'column': column, 'value': value, 'label': labels.get(value, ''), 'rows': now[column][value]})
    return out


def new_value_reason(conn, row: dict) -> str | None:
    """Why the property waits on values its condition columns have now that they did not have when it was confirmed: the same words a view gets
    (object_views.new_value_words). None when there is no such value."""
    found = _condition_codes(conn, row)
    return new_value_words(conn, _as_view(_content(row)), *found) if found else None


def refresh_new_value_reasons(conn, english_name: str, column: str) -> None:
    """object_views.refresh_new_value_reasons for the derived properties that measure this type and read this column: their reason is written again from the meanings
    as they are now."""
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'derived:%' AND state = 'needs_look'").fetchall():
        row = element_row(conn, element_id)
        content = _content(row)
        if content['kind'] != 'statistic' or content['types'][-1] != english_name or column not in {f['column'] for f in content['conditions']} \
                or not any(mark in (row['reason'] or '') for mark in ('出现了新值', ' has new values ')):
            continue
        reason = new_value_reason(conn, row)
        if reason and reason != row['reason']:
            conn.execute("UPDATE element_state SET reason = ? WHERE element_id = ? AND version = ? AND state = 'needs_look'", (reason, element_id, row['version']))


def _keep_out(conn, row: dict, content: dict, out: list[dict], who: str | None) -> dict:
    """"不算进来": a condition for each of these values (by its meaning) is added, and the changed property is this person's proposal for another builder to confirm."""
    unnamed = [o['value'] for o in out if not o['label']]
    if unnamed:
        raise TypeRefused(tr(f'新值 {"、".join(unnamed)} 还没有写含义，没法写成条件：先给它写含义，再选“不算进来”', f'The new values {", ".join(unnamed)} have no meaning yet, so they cannot become a condition. Write their meanings first, then choose "leave it out"'), 409)
    added = list({(o['column'], o['label']): {'column': o['column'], 'op': 'is_not', 'label': o['label']} for o in out}.values())
    changed = {**content, 'conditions': [*content['conditions'], *added]}
    if len(changed['conditions']) > MAX_CONDITIONS:
        raise TypeRefused(tr(f'条件最多 {MAX_CONDITIONS} 个，加上新值的就超了', f'At most {MAX_CONDITIONS} conditions, and adding the new values would go over'), 409)
    chain = _chain(conn, changed, None)
    if chain['problems']:
        raise TypeRefused('；'.join(chain['problems']), 409)
    result = evaluate(conn, changed, None)
    write_elements(conn, [_change(changed, result, who)], {row['element_id']: _reads(changed, chain)}, {row['element_id']: row['version']})
    return {'state': 'checked', 'added': [{'column': a['column'], 'label': a['label']} for a in added]}


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
    moved = tr('、', ', ').join(tr(f'{n} 第 {v} 版', f'{n} version {v}') for n, v in result['datasets'].items() if was['datasets'].get(n) != v)
    return [tr(f'{moved}之后，算不出值的对象变了：确认时 {was["failed"]} 个，现在 {result["failed"]} 个', f'After {moved}, the number of objects with no value changed: {was["failed"]} when confirmed, {result["failed"]} now')]


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
    return {'id': content['english_name'], 'type': content['type'], 'name': content['name'], **({'other_names': other_names.of(content)} if other_names.of(content) else {}), 'description': content['description'], 'kind': content['kind'], 'kind_name': KINDS[content['kind']],
            'says': describe(conn, content), 'output_type': content['output_type'], 'definition': content, 'problems': shown['problems'],
            'trial': shown, 'anchored': None if shown.get('limited_note') else anchors, 'used_by': _used_by(conn, row['element_id'], user), **derived_state(conn, row, user),
            'seen': shown.get('seen'), 'new_values': [] if shown.get('limited_note') else open_new_values(conn, row)}   # a person a row rule limits cannot confirm, and the counts are of the whole data


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
    owner = _content(whole_type_row(conn, payload.get('type'), user))
    path = payload.get('path') if isinstance(payload.get('path'), list) else []
    hops, problems = _walk(conn, owner['english_name'], [p for p in path if isinstance(p, str)][:MAX_HOPS], user, confirmed_only=True)
    out = {'hops': [{k: h[k] for k in ('relation', 'name', 'from_type', 'to_type', 'toward')} for h in hops], 'problems': problems, 'many': any(h['toward'] == 'many' for h in hops),
           'measured': None}
    if not hops or problems:
        return out
    m_row = whole_type_row(conn, hops[-1]['to_type'], user)
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
    owner = _content(whole_type_row(conn, english_type, user))
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
    return {'columns': [{'name': c, 'type': cols[c]['type'], 'sample': sample.get(c)} for c in _own_columns(owner) if c in cols], 'sample_label': tr('样本', 'Sample'),
            'functions': [{'group': g, 'name': n, 'template': t, 'does': d} for g, n, t, d in FUNCTION_DOCS], 'relations': relations, 'kinds': dict(KINDS.items()),
            'aggregations': dict(STAT_FNS.items()), 'hint': _routing_hint()}


def check_expression(conn, payload: dict, user: dict | None) -> dict:
    """校验 of an expression written for a formula, without trying it on rows: {'ok', 'errors': [{message, pos}], 'column_type'} over the columns of the type's dataset."""
    owner = _content(whole_type_row(conn, payload.get('type'), user))
    dataset = current_dataset(conn, owner['dataset'])
    if dataset is None:
        raise TypeRefused(tr(f'数据集“{owner["dataset"]}”已经不在了', f'The dataset "{owner["dataset"]}" no longer exists'), 409)
    cols = dataset_columns(conn, dataset['id'])
    expression = payload.get('expression')
    result = compile_expression(expression if isinstance(expression, str) else '', [{'name': c, 'type': cols[c]['type']} for c in _own_columns(owner) if c in cols])
    return {'ok': result['ok'], 'errors': result['errors'], 'column_type': COLUMN_TYPE.get(result['type']) if result['ok'] else None}


def trial_payload(conn, payload: dict, user: dict | None) -> dict:
    """试算 of a definition that is not saved: the same checks that refuse it, then the trial."""
    content = check_definition(conn, payload, user)
    return trial(conn, content, user)


# --- what other pages read ---------------------------------------------------------------------------------------------------------------------------

def limited_reads(conn, english_type: str, user: dict | None) -> list[dict]:
    """The derived properties of this type that this person may see and that are worked out over rows a row rule limits them to, on a type other than this one (this
    one's own limit is the type's): [{'name', 'types': [{'name', 'rows'}]}], rows being how many rows of that type they may read."""
    from ontology_poc_generator.object_types import visible_rows   # the page of a type reads this; imported where it is used
    out = []
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'derived:%' AND state != 'rejected' AND json_extract(content_json, '$.type') = ? ORDER BY element_id", (english_type,)).fetchall():
        row = element_row(conn, element_id)
        if not derived_visible(conn, row, user):
            continue
        content = _content(row)
        chain = _chain(conn, content, user)
        if chain['problems']:
            continue
        held = [{'name': t['name'], 'rows': visible_rows(conn, element_row(conn, type_id(e)), t['dataset'], user)} for e, t in chain['types'].items()
                if e != english_type and restriction(conn, type_id(e), user) is not None]
        if held:
            out.append({'name': content['name'], 'types': held})
    return out


def confirmed_columns(conn, english_type: str, user: dict | None) -> list[dict]:
    """The derived properties of a type this person may see, each with its values by row number in the type's table over the rows they may read:
    [{'id', 'name', 'output_type', 'says', 'confirmed', 'values': {row number: text}}]. The confirmed ones come first; a viewer sees only those, while a builder also
    gets the ones still waiting (confirmed False), so a value nobody has confirmed never looks like one somebody has. One that cannot be computed now is left out."""
    out = []
    for (element_id, state) in conn.execute("SELECT element_id, state FROM element_state WHERE element_id LIKE 'derived:%' AND state != 'rejected' AND json_extract(content_json, '$.type') = ? "
                                            "ORDER BY state != 'confirmed', element_id", (english_type,)).fetchall():
        row = element_row(conn, element_id)
        if not derived_visible(conn, row, user):
            continue
        content = _content(row)
        result = evaluate(conn, content, user)
        if result['problems']:
            continue
        out.append({'id': element_id, 'english_name': content['english_name'], 'name': content['name'], 'output_type': result['output_type'], 'says': describe(conn, content),
                    'confirmed': state == 'confirmed', 'values': {i: text_of(v, result['output_type']) for i, v in result['values'].items()}, 'outside': result.get('outside', set())})
    return out
