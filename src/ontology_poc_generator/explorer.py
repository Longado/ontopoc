"""The object explorer: for one object type, its instances with filters, a chart (group × measure × aggregation × chart type), one object on a page with the
objects related to it, and "转到关联的 X" (the linked set of another type).

Nothing here computes a statistic of its own. Aggregations are the pipelines' (pipeline_ops.AGGREGATIONS and _aggregate_sql, run on the rows in a throwaway
in-memory table), derived properties are the stage-4 ones (derived_properties.confirmed_columns), views are object_views, relations are object_relations. What this
module adds is the selection (which rows), and the standing of a result:

  - Only confirmed things draw in colour. A result says which definitions it stands on (caliber.lines_of); when any of them is not confirmed it carries
    `confirmed: False` and the reasons, and the page draws it grey with them. That covers the type, a view, a derived property used as a group, measure or filter,
    the meanings of a code column shown by label, and a relation a pivot goes through.
  - Visibility is the rest of the app's: a type this person may not see is not there (404), a viewer reads confirmed things only, and every table, view and pivot reads
    the rows a row rule lets this person read. A person a row rule limits gets counts of their rows and never a count of the whole data.
  - Nothing is dropped quietly: empty values form a group of their own (空), values a measure cannot read are counted, groups past the cap are counted.
"""
from __future__ import annotations

import math
import sqlite3

from ontology_poc_generator.caliber import grey_reasons, lines_of, root_reason
from ontology_poc_generator.derived_properties import confirmed_columns
from ontology_poc_generator.named_views import ORDERED_TEXT
from ontology_poc_generator.object_relations import _relation_visible, relation_id
from ontology_poc_generator.object_types import OBJECT_PAGE, RELATION_PREFIX, TypeRefused, _content, _state_view, _type_row, dataset_columns, element_row, enum_id, type_id
from ontology_poc_generator.object_views import list_views, meaning_labels, view_id, view_summary, view_visible
from ontology_poc_generator.pipeline_expr import NUMBER_TYPES
from ontology_poc_generator.pipeline_funcs import register
from ontology_poc_generator.pipeline_ops import AGGREGATIONS, _aggregate_sql, aggregation_options
from ontology_poc_generator.row_rules import keeps, restriction
from ontology_poc_generator.workspace_store import _canonical, current_dataset, dataset_records

FILTER_OPS = {'eq': '等于', 'ne': '不等于', 'contains': '包含', 'gt': '大于', 'ge': '不小于', 'lt': '小于', 'le': '不大于', 'empty': '为空', 'filled': '有值'}
NO_VALUE = ('empty', 'filled')
ORDER_OPS = ('gt', 'ge', 'lt', 'le')
CHARTS = {'number': '单个数字', 'bar': '柱状图', 'pie': '饼图', 'histogram': '直方图', 'table': '统计表'}
STAT_COLUMNS = (('count', '有值'), ('sum', '求和'), ('avg', '平均'), ('min', '最小'), ('p25', 'P25'), ('median', '中位数'), ('p75', 'P75'), ('max', '最大'))
ADDITIVE = ('count', 'sum')   # what a pie may show: shares of a whole
MAX_FILTERS, MAX_GROUPS, MAX_BINS, OPTION_LIMIT, RELATED_SHOWN = 8, 30, 50, 20, 5
NAMED_LEFT_OUT = 10   # the groups a chart did not draw that a result names (their number is always given)
ORDERS = {'desc': '从大到小', 'asc': '从小到大'}
VIA = 'via:'   # a group key "via:<relation>:<column>": a property of the type on the one end of a many-to-one relation, reached through it
EMPTY_GROUP = '（空）'


# --- the rows of a type as this person may read them ---------------------------------------------------------------------------------------------------

def _row_text(value) -> str | None:
    text = None if value is None else str(value).strip()
    return text or None


def _load(conn, user: dict | None, english: str) -> dict:
    """The type as a table: {'row', 'content', 'dataset', 'limit', 'fields', 'by_key', 'rows': [{'n' (the row's number among the rows this person may read, from 1: a
    limited person is not told where their rows lie in the whole data), 'pos' (its place in the dataset), 'rec' (the stored row), 'derived' ({field key: value})}]} over
    the rows this person may read, and the fields in the order a page lists them: derived properties first, then the type's own."""
    row = _type_row(conn, english, user)
    content = _content(row)
    dataset = current_dataset(conn, content['dataset'])
    if dataset is None:
        raise TypeRefused(f'数据集“{content["dataset"]}”已经不在了', 409)
    cols = dataset_columns(conn, dataset['id'])
    gone = [p['column'] for p in content['properties'] if p['column'] not in cols]
    if gone:
        raise TypeRefused(f'{dataset["name"]} 第 {dataset["version"]} 版里没有这些列了：{"、".join(gone)}', 409)
    limit = restriction(conn, row['element_id'], user)
    kept = [(i, r) for i, r in enumerate(dataset_records(conn, dataset), 1) if keeps(r, limit)]
    derived = confirmed_columns(conn, english, user)
    rows = [{'n': n, 'pos': pos, 'rec': rec, 'derived': {f'derived:{d["english_name"]}': d['values'].get(pos) for d in derived},
             'outside': {f'derived:{d["english_name"]}' for d in derived if pos in d['outside']}} for n, (pos, rec) in enumerate(kept, 1)]
    fields = [{'key': f'derived:{d["english_name"]}', 'column': None, 'name': d['name'], 'type': d['output_type'], 'code': False, 'derived': True, 'is_key': False,
               'confirmed': d['confirmed'], 'says': d['says'], 'element': d['id'], 'labels': {}, 'meaning': None} for d in derived]
    for p in content['properties']:
        held = element_row(conn, enum_id(english, p['column'])) if p['enum'] else None
        fields.append({'key': p['column'], 'column': p['column'], 'name': p['name'], 'type': p['type'], 'code': p['enum'], 'derived': False, 'is_key': p['column'] in content['key'],
                       'confirmed': True, 'says': None, 'element': None, 'labels': meaning_labels(conn, english, p['column']) if p['enum'] else {},
                       'meaning': {'state': held['state'] if held else None, 'element': held['element_id']} if p['enum'] else None})
    return {'row': row, 'content': content, 'dataset': dataset, 'limit': limit, 'fields': fields, 'by_key': {f['key']: f for f in fields}, 'rows': rows}


def _value(row: dict, field: dict):
    if field.get('via'):
        return row['via'].get(field['key'])
    return row['derived'].get(field['key']) if field['derived'] else row['rec'].get(field['column'])


def _by_size(text: str) -> tuple:
    """Numbers in numeric order before the rest, which go in alphabetical order."""
    number = _number(text)
    return (number is None, number if number is not None else 0, text)


def _options(table: dict, field: dict) -> list[dict] | None:
    """The values a filter on this field can be picked from, read from the rows this person may read (so a limited person is not told what the whole data holds):
    None when there are more than OPTION_LIMIT of them."""
    seen: dict[str, None] = {}
    for r in table['rows']:
        v = _row_text(_value(r, field))
        if v is not None:
            seen.setdefault(v)
            if len(seen) > OPTION_LIMIT:
                return None
    return [{'value': v, 'label': field['labels'].get(v)} for v in sorted(seen, key=_by_size)]


def _field_view(table: dict, f: dict, with_options: bool = True) -> dict:
    out = {k: f[k] for k in ('key', 'name', 'type', 'code', 'derived', 'is_key', 'confirmed', 'says')}
    out['numeric'] = f['type'] in NUMBER_TYPES and not f['code']
    out['ordered'] = f['type'] in NUMBER_TYPES or f['type'] in ORDERED_TEXT
    out['meaning_state'] = f['meaning']['state'] if f['meaning'] else None
    out['labels'] = f['labels']
    if with_options:
        out['options'] = _options(table, f)
    return out


# --- what to select ----------------------------------------------------------------------------------------------------------------------------------------

def _text_of(value, what: str, limit: int = 200) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise TypeRefused(f'{what}要写成文字，最多 {limit} 个字符')
    return value


def whole_page(value) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeRefused('page 要是一个整数')
    return value


def normalize_query(raw, depth: int = 0) -> dict:
    """{'type', 'view', 'filters': [{'field', 'op', 'value'}], 'rows': [numbers] | None, 'pivot': {'relation', 'side', 'source': query} | None} from what a page sent."""
    if not isinstance(raw, dict) or not isinstance(raw.get('type'), str) or not raw['type']:
        raise TypeRefused('要写明看哪个对象类型（type）')
    view = raw.get('view')
    if view not in (None, '') and not isinstance(view, str):
        raise TypeRefused('视图要写它的名字')
    filters = raw.get('filters') or []
    if not isinstance(filters, list) or len(filters) > MAX_FILTERS or not all(isinstance(f, dict) for f in filters):
        raise TypeRefused(f'条件最多 {MAX_FILTERS} 个')
    clean = []
    for f in filters:
        op = f.get('op')
        if not isinstance(op, str) or op not in FILTER_OPS:
            raise TypeRefused(f'条件的比较方式要是 {"、".join(FILTER_OPS)} 之一')
        clean.append({'field': _text_of(f.get('field'), '条件的字段'), 'op': op, 'value': '' if op in NO_VALUE else _text_of(f.get('value', ''), '条件的取值')})
    rows = raw.get('rows')
    if rows is not None and (not isinstance(rows, list) or len(rows) > 100 or not all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in rows)):
        raise TypeRefused('rows 要写成行号列表（最多 100 个）')
    pivot = raw.get('pivot')
    if pivot is not None:
        if depth or not isinstance(pivot, dict) or pivot.get('side') not in ('from', 'to') or not isinstance(pivot.get('relation'), str):
            raise TypeRefused('转到关联对象要写明哪个关系（relation）、起点在关系的哪一端（side）和起点的选法（source）；只能转一次')
        pivot = {'relation': pivot['relation'], 'side': pivot['side'], 'source': normalize_query(pivot.get('source'), depth + 1)}
    return {'type': raw['type'], 'view': view or None, 'filters': clean, 'rows': rows, 'pivot': pivot}


def _number(text):
    try:
        return float(str(text).strip())
    except ValueError:
        return None


def _matches(row: dict, field: dict, flt: dict) -> bool:
    v, op = _row_text(_value(row, field)), flt['op']
    if op == 'empty':
        return v is None
    if op == 'filled':
        return v is not None
    wanted = flt['value'].strip()
    if op == 'eq':
        return v is not None and _canonical(v) == _canonical(wanted)
    if op == 'ne':
        return v is None or _canonical(v) != _canonical(wanted)
    if op == 'contains':
        return v is not None and (wanted.casefold() in v.casefold() or wanted.casefold() in (field['labels'].get(v) or '').casefold())
    if v is None:
        return False
    if field['type'] in NUMBER_TYPES:
        a, b = _number(v), _number(wanted)
        if a is None or b is None:
            return False
        return {'gt': a > b, 'ge': a >= b, 'lt': a < b, 'le': a <= b}[op]
    return {'gt': v > wanted, 'ge': v >= wanted, 'lt': v < wanted, 'le': v <= wanted}[op]


def _check_filters(table: dict, filters: list[dict]) -> list[dict]:
    fields = []
    for flt in filters:
        field = table['by_key'].get(flt['field'])
        if field is None:
            raise TypeRefused(f'这个对象类型里没有“{flt["field"]}”这个字段')
        if flt['op'] in ORDER_OPS and not (field['type'] in NUMBER_TYPES or field['type'] in ORDERED_TEXT):
            raise TypeRefused(f'“{field["name"]}”是{field["type"]}，不能比大小；数字、年月、日期才可以')
        if flt['op'] not in NO_VALUE and not flt['value'].strip():
            raise TypeRefused(f'“{field["name"]}”的条件要写取值')
        if flt['op'] in ORDER_OPS and field['type'] in NUMBER_TYPES and _number(flt['value']) is None:
            raise TypeRefused(f'“{field["name"]}”是数字，条件的取值要写成数字')
        fields.append(field)
    return fields


def select(conn, user: dict | None, query: dict) -> dict:
    """The rows a normalised query picks, over what this person may read: {'table', 'rows', 'used' (the definitions it stands on: element ids), 'fields' (the fields its
    filters read)}. A view keeps its rows, a pivot takes the rows of the other type that the source rows link to, a filter keeps what it says, rows names row numbers."""
    table = _load(conn, user, query['type'])
    rows, used = table['rows'], [table['row']['element_id']]
    if query['view']:
        vrow = element_row(conn, view_id(query['view']))
        if vrow is None or not view_visible(conn, vrow, user) or _content(vrow)['type'] != query['type']:
            raise TypeRefused(f'这个对象类型没有叫“{query["view"]}”的视图', 404)
        summary = view_summary(conn, _content(vrow))
        if summary['problems']:
            raise TypeRefused(f'视图“{query["view"]}”现在读不了：{summary["problems"][0]}', 409)
        keep = set(summary['positions'])
        rows = [r for r in rows if r['pos'] in keep]
        used.append(vrow['element_id'])
    if query['pivot']:
        rows, more = _pivot(conn, user, query, table, rows)
        used += more
    if query['rows'] is not None:
        wanted = set(query['rows'])
        rows = [r for r in rows if r['n'] in wanted]
    fields = _check_filters(table, query['filters'])
    for flt, field in zip(query['filters'], fields):
        rows = [r for r in rows if _matches(r, field, flt)]
    used += [f['element'] for f in fields if f['derived']]
    return {'table': table, 'rows': rows, 'used': used, 'fields': fields}


def _pivot(conn, user: dict | None, query: dict, table: dict, rows: list[dict]) -> tuple[list[dict], list[str]]:
    p = query['pivot']
    relation = element_row(conn, relation_id(p['relation']))
    if relation is None or not _relation_visible(conn, relation, user):
        raise TypeRefused('没有这个关系', 404)
    rc = _content(relation)
    other = 'to' if p['side'] == 'from' else 'from'
    if rc[p['side']] != p['source']['type'] or rc[other] != query['type']:
        raise TypeRefused(f'关系“{rc["name"]}”不是从“{p["source"]["type"]}”连到“{query["type"]}”的')
    source = select(conn, user, p['source'])
    src_col, dst_col = rc[f'{p["side"]}_column'], rc[f'{other}_column']
    linked = {_canonical(r['rec'].get(src_col)) for r in source['rows'] if _row_text(r['rec'].get(src_col)) is not None}
    return [r for r in rows if _row_text(r['rec'].get(dst_col)) is not None and _canonical(r['rec'].get(dst_col)) in linked], [relation['element_id'], *source['used']]


# --- standing ------------------------------------------------------------------------------------------------------------------------------------------------

def _standing(conn, used: list[str]) -> dict:
    """{'confirmed', 'reasons', 'lines'}: the caliber of what was selected. The type itself is a line only when it is not confirmed (a confirmed type is no
    definition worth reciting on every card)."""
    lines = lines_of(conn, used)
    shown = [l for l in lines if l['kind'] != 'type' or not l['confirmed']]
    return {'confirmed': all(l['confirmed'] for l in lines), 'reasons': grey_reasons(lines), 'why': root_reason(conn, lines), 'lines': shown}


def _type_line(conn, user: dict | None, row: dict) -> dict:
    content = _content(row)
    return {'id': content['english_name'], 'name': content['name'], **{k: v for k, v in _state_view(conn, row, user).items() if k in ('state', 'proposed_by', 'reason', 'confirmed_by', 'confirmed_on')}}


# --- the page of a type ------------------------------------------------------------------------------------------------------------------------------------

def _relations_of(conn, user: dict | None, english: str) -> list[dict]:
    """The relations of a type this person may see, each way: a pivot goes from the type to the one on the other end."""
    relations = []
    for (element_id,) in conn.execute('SELECT element_id FROM element_state WHERE element_id LIKE ? ORDER BY element_id', (f'{RELATION_PREFIX}%',)).fetchall():
        rel = element_row(conn, element_id)
        rc = _content(rel)
        if english not in (rc['from'], rc['to']) or not _relation_visible(conn, rel, user):
            continue
        for side in ('from', 'to'):
            if rc[side] == english:   # a relation of a type to itself is two ways: as the one it starts from, and as the one it ends at
                other = rc['to' if side == 'from' else 'from']
                relations.append({'id': rc['english_name'], 'name': rc['name'], 'side': side, 'other': other, 'other_name': _content(element_row(conn, type_id(other)))['name'],
                                  'state': rel['state'], 'confirmed': rel['state'] == 'confirmed', 'cardinality': rc['cardinality']})
    return relations


def explore_meta(conn, user: dict | None, english: str) -> dict:
    """What the explorer offers on a type: its fields (with the values a filter can be picked from), the views, and the relations a pivot can go through."""
    table = _load(conn, user, english)
    row = table['row']
    return {'type': _type_line(conn, user, row), 'dataset': table['dataset']['name'], 'dataset_version': table['dataset']['version'], 'rows': len(table['rows']),
            'rows_limited': table['limit'] is not None, 'fields': [_field_view(table, f) for f in table['fields']],
            'views': [{k: v[k] for k in ('id', 'name', 'says', 'state', 'reason', 'confirmed_by', 'confirmed_on')} for v in list_views(conn, english, user) if not v['problems']],
            'relations': _relations_of(conn, user, english), 'reach': reach_options(conn, user, english), 'charts': CHARTS, 'aggregations': AGGREGATIONS, 'filter_ops': FILTER_OPS}


def _object_key(table: dict, row: dict) -> tuple[dict, str]:
    key = {c: row['rec'].get(c) for c in table['content']['key']}
    return key, ' + '.join('' if v is None else str(v) for v in key.values())


def _display(table: dict, row: dict) -> list:
    return [_value(row, f) for f in table['fields']]


def _outside(table: dict, row: dict) -> list[int]:
    """The columns (by their place in the row) whose value is empty because everything it is worked out from lies outside the rows this person may read."""
    return [i for i, f in enumerate(table['fields']) if f['key'] in row['outside']]


def _columns(table: dict) -> list[dict]:
    return [{'column': f['key'], 'name': f['name'], 'type': f['type'], 'key': f['is_key'], 'derived': f['derived'], 'confirmed': f['confirmed'], 'says': f['says']} for f in table['fields']]


def _enums(table: dict) -> dict:
    return {f['key']: {'state': f['meaning']['state'], 'labels': f['labels']} for f in table['fields'] if f['code']}


def explore_table(conn, user: dict | None, raw_query, page=1) -> dict:
    """One page of the instances a query selects, in the shape the objects tab reads (columns, rows, enums), with the row number of each (for its own page) and the standing."""
    query = normalize_query(raw_query)
    got = select(conn, user, query)
    table, rows = got['table'], got['rows']
    pages = max(1, -(-len(rows) // OBJECT_PAGE))
    page = min(max(whole_page(page), 1), pages)
    shown = rows[(page - 1) * OBJECT_PAGE:page * OBJECT_PAGE]
    return {'query': query, 'columns': _columns(table), 'rows': [_display(table, r) for r in shown], 'numbers': [r['n'] for r in shown], 'outside': [_outside(table, r) for r in shown], 'total': len(rows), 'page': page, 'pages': pages,
            'limit': OBJECT_PAGE, 'dataset': table['dataset']['name'], 'dataset_version': table['dataset']['version'], 'rows_limited': table['limit'] is not None,
            'enums': _enums(table), 'standing': _standing(conn, got['used'])}


# --- charts --------------------------------------------------------------------------------------------------------------------------------------------------

def normalize_chart(raw) -> dict:
    """{'kind', 'group', 'measure', 'fn', 'bins', 'top', 'order'} from what a page sent; what is missing for the kind is said in words. `top` keeps the N biggest
    groups of a bar, a pie or a statistics table (by value; a statistics table by rows), `order` puts the groups from the biggest or the smallest."""
    if not isinstance(raw, dict) or not isinstance(raw.get('kind'), str) or raw['kind'] not in CHARTS:
        raise TypeRefused(f'图要写明种类（kind）：{"、".join(CHARTS)}')
    out = {'kind': raw['kind'], 'group': raw.get('group') or None, 'measure': raw.get('measure') or None, 'fn': raw.get('fn') or 'count', 'bins': raw.get('bins', 10), 'top': raw.get('top') or None,
           'order': raw.get('order') or None}
    for name in ('group', 'measure'):
        if out[name] is not None and not isinstance(out[name], str):
            raise TypeRefused(f'{name} 要写字段的名字')
    if not isinstance(out['fn'], str) or out['fn'] not in AGGREGATIONS:
        raise TypeRefused(f'统计方式要是 {"、".join(AGGREGATIONS)} 之一')
    if not isinstance(out['bins'], int) or isinstance(out['bins'], bool) or not 2 <= out['bins'] <= MAX_BINS:
        raise TypeRefused(f'直方图的分段数要在 2 到 {MAX_BINS} 之间')
    if out['top'] is not None and (not isinstance(out['top'], int) or isinstance(out['top'], bool) or not 1 <= out['top'] <= MAX_GROUPS):
        raise TypeRefused(f'只看前几组最少 1、最多 {MAX_GROUPS}')
    if out['order'] is not None and out['order'] not in ORDERS:
        raise TypeRefused(f'排序要写 {"、".join(f"{k}（{v}）" for k, v in ORDERS.items())}')
    return out


def _chart_fields(table: dict, chart: dict) -> tuple[dict | None, dict | None]:
    group = measure = None
    if chart['group'] is not None:
        group = table['by_key'].get(chart['group'])
        if group is None:
            raise TypeRefused(f'这个对象类型里没有“{chart["group"]}”这个字段')
    if chart['measure'] is not None:
        measure = table['by_key'].get(chart['measure'])
        if measure is None:
            raise TypeRefused(f'这个对象类型里没有“{chart["measure"]}”这个字段')
    kind = chart['kind']
    if kind in ('bar', 'pie') and group is None:
        raise TypeRefused(f'{CHARTS[kind]}要选按哪一列分组')
    if kind in ('histogram', 'table') and (measure is None or measure['type'] not in NUMBER_TYPES or measure['code']):
        raise TypeRefused(f'{CHARTS[kind]}要选一个数字列来量（代码列不算：代码的大小没有意义）')
    if kind == 'histogram' and group is not None:
        raise TypeRefused('直方图不分组')
    if kind != 'table' and measure is not None:
        columns = [{'name': measure['key'], 'type': measure['type'], 'origin': f'code:{measure["key"]}' if measure['code'] else measure['key']}]
        options = aggregation_options(columns, frozenset({f'code:{measure["key"]}'} if measure['code'] else ()))
        if kind != 'histogram' and chart['fn'] not in options[measure['key']]:
            raise TypeRefused(f'“{measure["name"]}”不能{AGGREGATIONS[chart["fn"]]}；可以用：{"、".join(AGGREGATIONS[f] for f in options[measure["key"]])}')
    if kind != 'table' and kind != 'histogram' and measure is None and chart['fn'] != 'count':
        raise TypeRefused(f'{AGGREGATIONS[chart["fn"]]}要指定哪一列')
    if kind == 'pie' and chart['fn'] not in ADDITIVE:
        raise TypeRefused('饼图是份额，只能用计数或求和')
    return group, measure


def _memory(rows: list[dict], group: dict | None, measure: dict | None) -> sqlite3.Connection:
    """The rows as a throwaway table g, m, so the pipelines' aggregation SQL can run on them."""
    mem = sqlite3.connect(':memory:')
    register(mem)
    mem.execute('CREATE TABLE t (g, m)')
    mem.executemany('INSERT INTO t VALUES (?, ?)', [(_row_text(_value(r, group)) if group else None, _row_text(_value(r, measure)) if measure else None) for r in rows])
    return mem


def _group_label(group: dict, value, confirmed_meaning: bool) -> str:
    if value is None:
        return EMPTY_GROUP
    label = group['labels'].get(value) if group['code'] and confirmed_meaning else None
    return f'{value} {label}' if label else str(value)


def _group_order(group: dict, items: list[dict]) -> list[dict]:
    """Numbers, dates and codes in their own order; the rest by size, the biggest first."""
    if group['type'] in NUMBER_TYPES:
        return sorted(items, key=lambda i: (i['key'] is None, _number(i['key']) if _number(i['key']) is not None else 0, str(i['key'])))
    if group['type'] in ORDERED_TEXT or group['code']:
        return sorted(items, key=lambda i: (i['key'] is None, str(i['key'])))
    return sorted(items, key=lambda i: (-(i['value'] if isinstance(i['value'], (int, float)) else 0), i['key'] is None, str(i['key'])))


def _grouped(mem, group, measure, fn: str, confirmed_meaning: bool) -> list[dict]:
    """Every group with its aggregation and rows, labelled, in no particular order."""
    col = {'name': 'm', 'type': measure['type']} if measure else None
    sql, params, _ = _aggregate_sql(fn, col)
    found = [{'key': k, 'value': v, 'rows': n} for k, v, n in mem.execute(f'SELECT g, {sql}, COUNT(*) FROM t GROUP BY g', params)]
    for item in found:
        item['label'] = _group_label(group, item['key'], confirmed_meaning)
    return found


def _size(item: dict) -> float:
    return float(item['value']) if isinstance(item['value'], (int, float)) else float('-inf')


def _arranged(group: dict, items: list[dict], chart: dict) -> tuple[list[dict], list[dict]]:
    """(the groups to draw, the groups left out). Past the cap or the top N the biggest groups are the ones kept; what is drawn then goes in the order asked for, or in
    the group's own order (numbers, dates and codes in sequence, the rest biggest first)."""
    limit = chart['top'] or MAX_GROUPS
    if len(items) > limit:
        ranked = sorted(items, key=lambda i: (-_size(i), str(i['label'])))
        kept, left = ranked[:limit], ranked[limit:]
    else:
        kept, left = items, []
    if chart['order'] in ORDERS:
        kept = sorted(kept, key=lambda i: (i['value'] is None, -_size(i) if chart['order'] == 'desc' else _size(i), str(i['label'])))
    elif chart['top']:
        kept = sorted(kept, key=lambda i: (-_size(i), str(i['label'])))
    else:
        kept = _group_order(group, kept)
    return kept, sorted(left, key=lambda i: (-_size(i), str(i['label'])))


def _named(items: list[dict], with_value: bool) -> list[dict]:
    """The groups a chart did not draw as a reader is told of them: the label, the rows and, when the chart measures something, its value (the first few)."""
    return [{'label': i['label'], 'rows': i['rows'], 'value': i['value'] if with_value else None} for i in items[:NAMED_LEFT_OUT]]


def _histogram(rows: list[dict], measure: dict, bins: int) -> dict:
    numbers, missing = [], 0
    for r in rows:
        v = _number(_row_text(_value(r, measure)) or '')
        if v is None or math.isnan(v) or math.isinf(v):
            missing += 1
        else:
            numbers.append(v)
    if not numbers:
        return {'bins': [], 'missing': missing, 'values': 0}
    low, high = min(numbers), max(numbers)
    if low == high:
        return {'bins': [{'from': low, 'to': high, 'count': len(numbers)}], 'missing': missing, 'values': len(numbers)}
    width = (high - low) / bins
    counts = [0] * bins
    for v in numbers:
        counts[min(int((v - low) / width), bins - 1)] += 1
    return {'bins': [{'from': round(low + i * width, 6), 'to': round(low + (i + 1) * width, 6), 'count': c} for i, c in enumerate(counts)], 'missing': missing, 'values': len(numbers)}


def explore_chart(conn, user: dict | None, raw_query, raw_chart) -> dict:
    """A chart of what a query selects. kind: number (one value: the aggregation of the measure over the rows), bar and pie (the aggregation of the measure for each
    group), histogram (a number column in equal-width bins), table (the statistics of a number column, for each group or for all). The result carries what it was
    worked out on (rows), the standing (grey and why) and, for a group, what it counted but did not draw: the groups past the cap or the top N, named with their rows
    and value, and the rows a group through a relation could not place (their key has no match on the other end), named the same way."""
    query, chart = normalize_query(raw_query), normalize_chart(raw_chart)
    got = select(conn, user, query)
    table, rows = got['table'], got['rows']
    used = list(got['used'])
    reached = None
    if chart['group'] is not None and chart['group'].startswith(VIA):
        reached = _reach(conn, user, table, query, chart['group'], rows)
        table, rows = {**table, 'by_key': {**table['by_key'], chart['group']: reached['field']}}, reached['placed']
        used += reached['used']
    group, measure = _chart_fields(table, chart)
    meaning = True
    for f in (group, measure):
        if f is not None and f['derived']:
            used.append(f['element'])
    if group is not None and group['code'] and group['meaning'] and group['meaning']['element']:
        used.append(group['meaning']['element'])
        meaning = group['meaning']['state'] == 'confirmed'
    out = {'query': query, 'chart': chart, 'rows': len(got['rows']), 'standing': _standing(conn, used), 'group': group and group['name'], 'measure': measure and measure['name'],
           'fn': chart['fn'], 'rows_limited': table['limit'] is not None}
    kind = chart['kind']
    if kind == 'histogram':
        return {**out, **_histogram(rows, measure, chart['bins'])}
    if reached is not None:
        out = {**out, **_unplaced(reached, measure, chart)}
    mem = _memory(rows, group, measure)
    try:
        if kind == 'number':
            sql, params, _ = _aggregate_sql(chart['fn'], {'name': 'm', 'type': measure['type']} if measure else None)
            value = mem.execute(f'SELECT {sql} FROM t', params).fetchone()[0]
            return {**out, 'value': value}
        if kind == 'table':
            col = {'name': 'm', 'type': measure['type']}
            aggs = [_aggregate_sql(fn, col) for fn, _ in STAT_COLUMNS]
            parts = ', '.join(a[0] for a in aggs)
            params = [p for a in aggs for p in a[1]]
            found = [{'key': r[0], 'rows': r[1], 'values': list(r[2:]), 'value': r[1]} for r in mem.execute(f'SELECT g, COUNT(*), {parts} FROM t GROUP BY g', params)]
            for item in found:
                item['label'] = _group_label(group, item['key'], meaning) if group else '全部'
            shown, left = _arranged(group, found, chart) if group else (found, [])
            for item in shown:
                item.pop('value', None)
            return {**out, 'columns': [{'fn': fn, 'name': name} for fn, name in STAT_COLUMNS], 'table': shown, 'groups_hidden': len(left), 'rows_hidden': sum(i['rows'] for i in left),
                    'hidden_groups': _named(left, False)}
        items, left = _arranged(group, _grouped(mem, group, measure, chart['fn'], meaning), chart)
        if kind == 'pie' and any(isinstance(i['value'], (int, float)) and i['value'] < 0 for i in items):
            raise TypeRefused('这一列有负数，不能画成饼图（份额不能是负的）')
        return {**out, 'groups': items, 'groups_hidden': len(left), 'rows_hidden': sum(i['rows'] for i in left), 'hidden_groups': _named(left, measure is not None)}
    finally:
        mem.close()


# --- a group reached through a relation --------------------------------------------------------------------------------------------------------------------

def _many_end(rel: dict) -> bool:
    """Whether the type this relation is seen from is on its many end, so each of its rows reaches at most one row on the other."""
    return rel['cardinality'] == 'one_to_one' or (rel['cardinality'] == 'many_to_one') == (rel['side'] == 'from')


def reach_options(conn, user: dict | None, english: str) -> list[dict]:
    """The properties a group can be taken from through a confirmed relation whose one end is the other type: [{'key': 'via:<relation>:<column>', 'name': '客户的客户名称',
    'relation', 'relation_name', 'other', 'column'}]."""
    out = []
    for rel in _relations_of(conn, user, english):
        if not (rel['confirmed'] and _many_end(rel)):
            continue
        other = _content(element_row(conn, type_id(rel['other'])))
        link = _content(element_row(conn, relation_id(rel['id'])))[f'{"to" if rel["side"] == "from" else "from"}_column']
        out += [{'key': f'{VIA}{rel["id"]}:{p["column"]}', 'name': f'{rel["other_name"]}的{p["name"]}', 'relation': rel['id'], 'relation_name': rel['name'], 'other': rel['other'], 'column': p['column']}
                for p in other['properties'] if p['column'] != link]
    return out


def _reach(conn, user: dict | None, table: dict, query: dict, key: str, rows: list[dict]) -> dict:
    """The rows given a group through a relation: {'field', 'placed' (the rows whose key finds a row on the other end, each with its value), 'unplaced' (the rows
    whose key finds none), 'link' (a field that reads the key), 'used'}."""
    _, relation, column = key.split(':', 2) if key.count(':') >= 2 else (None, None, None)
    rel = next((r for r in _relations_of(conn, user, query['type']) if r['id'] == relation and _many_end(r)), None)
    if rel is None:
        raise TypeRefused(f'这个关系不是从“{table["content"]["name"]}”连到一个对象的（多对一）：{relation}')
    rc = _content(element_row(conn, relation_id(relation)))
    other_side = 'to' if rel['side'] == 'from' else 'from'
    other = _load(conn, user, rel['other'])
    base = other['by_key'].get(column)
    if base is None or base['derived']:
        raise TypeRefused(f'“{rel["other_name"]}”里没有“{column}”这个字段')
    here, there = rc[f'{rel["side"]}_column'], rc[f'{other_side}_column']
    found: dict = {}
    for r in other['rows']:
        link = _row_text(r['rec'].get(there))
        if link is not None:
            found.setdefault(_canonical(link), _value(r, base))   # a key that repeats on the one end keeps its first row: a confirmed relation has none
    field = {**base, 'key': key, 'name': f'{rel["other_name"]}的{base["name"]}', 'via': True, 'is_key': False}
    placed, unplaced = [], []
    for r in rows:
        link = _row_text(r['rec'].get(here))
        if link is not None and _canonical(link) in found:
            placed.append({**r, 'via': {key: found[_canonical(link)]}})
        else:
            unplaced.append(r)
    return {'field': field, 'placed': placed, 'unplaced': unplaced, 'link': {'key': here, 'column': here, 'derived': False, 'via': False}, 'other_name': rel['other_name'],
            'used': [relation_id(relation), other['row']['element_id']]}


def _unplaced(reached: dict, measure: dict | None, chart: dict) -> dict:
    """The rows a group through a relation could not place, by the key they carry: {'unplaced': [{'label', 'rows', 'value'}], 'unplaced_groups', 'unplaced_rows'}."""
    rows = reached['unplaced']
    if not rows:
        return {'unplaced': [], 'unplaced_groups': 0, 'unplaced_rows': 0}
    mem = _memory(rows, reached['link'], measure)
    try:
        items = sorted(_grouped(mem, {'labels': {}, 'code': False}, measure, chart['fn'] if chart['kind'] in ('bar', 'pie') else 'count', True), key=lambda i: (-i['rows'], str(i['label'])))
    finally:
        mem.close()
    with_value = measure is not None and chart['kind'] in ('bar', 'pie')
    return {'unplaced': _named(items, with_value), 'unplaced_groups': len(items), 'unplaced_rows': len(rows), 'unplaced_through': reached['other_name']}


# --- one object ------------------------------------------------------------------------------------------------------------------------------------------

def explore_object(conn, user: dict | None, english: str, n) -> dict:
    """One object: its fields (as the objects tab shows a row), and for each relation of its type the objects related to it (how many, the first few) with the query
    that opens the whole set in the explorer. A type or a relation this person may not see is not listed; the counts are of the rows they may read."""
    table = _load(conn, user, english)
    found = next((r for r in table['rows'] if r['n'] == n), None)
    if found is None:
        raise TypeRefused('没有这个对象', 404)
    key, text = _object_key(table, found)
    related = []
    for rel in _relations_of(conn, user, english):
        try:
            query = {'type': rel['other'], 'view': None, 'filters': [], 'rows': None,
                     'pivot': {'relation': rel['id'], 'side': rel['side'], 'source': {'type': english, 'view': None, 'filters': [], 'rows': [n], 'pivot': None}}}
            got = select(conn, user, query)
        except TypeRefused:   # the other type's data is gone or unreadable now: the page does not list a count it cannot stand behind
            continue
        other = got['table']
        related.append({**rel, 'count': len(got['rows']), 'objects': [{'n': r['n'], 'text': _object_key(other, r)[1]} for r in got['rows'][:RELATED_SHOWN]], 'query': query,
                        'rows_limited': other['limit'] is not None})
    return {'type': _type_line(conn, user, table['row']), 'n': n, 'key': key, 'text': text, 'columns': _columns(table), 'row': _display(table, found), 'outside': _outside(table, found), 'enums': _enums(table),
            'dataset': table['dataset']['name'], 'dataset_version': table['dataset']['version'], 'related': related, 'standing': _standing(conn, [table['row']['element_id']])}
