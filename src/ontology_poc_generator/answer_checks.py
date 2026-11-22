"""An answer checks its own definitions before it is given.

A definition a person confirmed (a code's meaning, a view they named) only counts if the query that computed the answer
used it. Whether a question includes a definition or leaves it out ("已取消的", "不算已取消", "未取消") is a judgement of
meaning, so the model that writes the query says it: `definitions_used`, each with a direction. A definition is named by its id
from the catalog it was given (订单.状态码=已取消, or a view's name), never by its label: the same label in two columns is two
definitions, and a filter on 售后工单.状态码 is not a use of 订单's 已取消. Code never reads the question for negation words;
it checks the executed query against what the model said:

  include    the query filters the meaning's column by one of its codes, or the named view is read (its rows are chosen)
  mention    the question names it without selecting rows by it, but the query must show it: its column is a share (a rate of it)
             or a dimension, or, for a view, the view's table is read. A mention the query does not use is refused ("只是提到却没有用到
             它，没法核对"), since nothing says what the word was for; a filter on its column that picks rows is a use, refused too
  exclude    the query leaves the meaning's codes out ("not_equals": the column is not one of them, code leaves those rows out); else a
             named view a person made that leaves the meaning out is read in its place; else the answer is refused naming what could not be applied
  (include by leaving the rest out) the query language has no "is one of", so 已取消和已退款 is written as "the column is none of the other
             codes". That includes 已取消 and 已退款 only when everything the filter lets through, read per object from the column's values, is a
             code of a meaning the model said the question includes: a code with no meaning, a blank (an object with no value there), or a meaning
             it did not name would be counted too, and is refused as before (so is a check that is not given the values). Only when each object
             holds one value in the column: the query leaves out an object any of whose values is left out, so an object with a kept code and a
             left-out one (two rows of one key, a column of another table's rows) would be dropped, and such a column is not given. Only when
             leaving codes out is all the query does to the column: another filter on it (an equals, a range), a share of it or a view read that
             filters it could drop a kept meaning's rows. Only where it is given the values: the team app, where each type is built from one
             dataset keyed on a unique, filled key and no view's choice reaches past it. A single upload is not given them, and there such a
             question is refused as before: one object can be filled from several tables (an order also from its tickets), and views choose rows
             after the check, so an order a view drops can live on through a ticket with no code and "not 2" would count it
  omitted    a confirmed label the model did not list, that the question says verbatim (three characters or more, or with its
             column named) or that the query filters by: refused, saying the model did not say how it was used
  unknown    an id the model wrote that is in no catalog entry (a synonym such as 取消), whatever direction it gave: refused, saying the name did not match,
             and the omissions it causes are not reported on top
  waiting    a meaning whose confirmation broke when the data changed (anchors.py) and waits for a second look: counts as nothing
             confirmed, and a question that says its label (or a model that lists it) is refused saying so, never answered under the
             old label
  derived    a query that reads a confirmed derived property instead of the rows (每个客户的有效订单金额) uses a view the model says the question includes
             (never one it gave no direction for, or only mentions) whose conditions are exactly the property's on the table it counts, or the meanings it leaves out when they are exactly the ones the model says the question leaves out (or the one
             it keeps). Every derived property the query reads on that table must match: one that counts more rows is refused like a query that reads them.
             It must also reach every row of that table exactly once along its path (by the relations' checks: no key that names nothing, none that repeats),
             or its sum is not the rows' total; and no view confirmed with its conditions may be waiting to be confirmed again (it is being redefined)
             Its own calculation and the query's measure must add up to the rows: a per-object sum or count, read only as the measure with op sum
  understood how the model's word was carried out ("读视图 有效订单", "状态码 = 2"), returned for the page to say beside the answer

  upstream_problems  a filter found nothing, but the table it filtered was damaged before the question was asked and the damaged
                     rows (a repeated key nobody chose a reading for, rows with an empty key) could be the ones it asks for, or the
                     table could not be stored at all: the answer says so instead of "no data" (gap 9 of the rebuild map:
                     downstream could not tell lost rows from missing data). A damaged row that cannot match the filter is not
                     reported: a filter on 火星 is not about the repeated customer who lives in 合肥 and 苏州.

Where the rows come from and where the answer is kept is not decided here."""
from __future__ import annotations

import re
from collections import Counter

from ontology_poc_generator.code_meanings import codes_for_label
from ontology_poc_generator.derived_measures import to_number
from ontology_poc_generator.lang import tr
from ontology_poc_generator.named_views import query_tables, query_types
from ontology_poc_generator.ontology_questions import RANGES, _conditions, _fields, _matcher, _resolve_field, _shape_limit, _types, clean_used
from ontology_poc_generator.public_ontology import build_graph, normalize_proposal, normalize_value
from ontology_poc_generator.repeated_keys import rule_key
from ontology_poc_generator.workspace_store import describes_rows

UNSAID = 'unsaid'


# of a view: a named view is not a column the query can leave a value out of
def _excluding(): return tr('这个问法要把它排除，查询只能写“某个字段等于某个值”，做不到排除', 'The question leaves it out, but a query can only say "a field equals a value", so it cannot leave it out')
def _not_left_out(): return tr('这个问法要把它排除，但这条查询没有把它排除掉（没有写“不等于”）', 'The question leaves it out, but the query does not (it has no "not equal")')
def _unsaid_how(): return tr('模型没有说明它是怎么用的', 'The model did not say how it is used')
def _unbacked(): return tr('没法核对', 'it cannot be checked')
def _unbacked_how(): return tr('只是提到却没有用到它，没法核对', 'Only mentioned, not used, so it cannot be checked')


def _verbatim(question: str, term: str, column: str | None = None, columns: tuple | list = ()) -> bool:
    """Does the question say the label itself? A label of one or two characters (1 = 是) is in every other sentence, so it counts
    only with its column named (by the column, or by one of `columns`: the other names of its property); one made of letters and digits must stand apart from them."""
    if column is not None and len(term) < 3 and not any(c in question for c in (column, *columns)):
        return False
    pattern = rf'(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])' if term.isascii() else re.escape(term)
    return re.search(pattern, question, re.I) is not None


def _excluding_view(views: list[dict], field: str, label: str) -> dict | None:
    """The confirmed view a person made that leaves this meaning of this column out ("有效订单": 状态码 is not 已取消)."""
    table, _, column = field.partition('.')
    return next((v for v in views if v['state'] == 'confirmed' and (v['definition'] or {}).get('kind') == 'filter'
                 and v['definition'].get('op') == 'is_not' and v['definition'].get('label') == label
                 and v['definition'].get('column') == column and v['source'] == table), None)


def meaning_id(field: str, label: str) -> str:
    return f'{field}={label}'


def definition_catalog(meanings: dict | None, views: list[dict], also: dict | None = None) -> list[dict]:
    """What the model is told a person has confirmed: each code meaning (its label) and each view they named, with what it is. `also`: the other names heard
    ({'meanings': {id: names}, 'views': {name: names}}), told as `also_called`."""
    called = lambda kind, key: {'also_called': (also or {}).get(kind, {})[key]} if (also or {}).get(kind, {}).get(key) else {}
    out = [{'id': meaning_id(field, label), 'name': label, 'kind': 'meaning', 'means': tr(f'{field} 里 {"、".join(sorted(c for c, said in m["labels"].items() if said == label))} = {label}', f'In {field}, {", ".join(sorted(c for c, said in m["labels"].items() if said == label))} = {label}'),
            **called('meanings', meaning_id(field, label))}
           for field, m in sorted((meanings or {}).items()) for label in sorted({x for x in m['labels'].values() if x})]
    return out + [{'id': v['name'], 'name': v['name'], 'kind': 'view', 'means': v['from'], **called('views', v['name'])} for v in views if v['definition'] is not None]


def _reached(types: dict, relations: dict, start: str, via: list) -> dict | None:
    """The object type a dimension reads from, after walking `via` from `start` (relations in either direction)."""
    here = start
    for key in via if isinstance(via, list) else []:
        r = relations.get(key)
        if r is None or here not in (r['from'], r['to']):
            return None
        here = r['to'] if here == r['from'] else r['from']
    return types.get(here)


def _uses(query: dict, types: dict, relations: dict) -> list[tuple[str | None, object, str]]:
    """(the "table.path" it reads, the value it is compared with (a list for 'exclude'), 'filter' | 'exclude' | 'share' | 'group') for
    every filter, share and dimension of the query, each field read as the object type it belongs to reads it: a field is not
    another table's column of the same name."""
    start = types.get(query.get('start'))
    group_by = query.get('group_by')
    dims = [group_by] if isinstance(group_by, (str, dict)) else group_by if isinstance(group_by, list) else []
    share = query.get('share') if isinstance(query.get('share'), dict) else {}
    resolve = lambda t, name: _resolve_field(t, name) if t else None
    out = [(resolve(start, w.get('field')), w['not_equals'], 'exclude') if 'not_equals' in w else (resolve(start, w.get('field')), w.get('equals'), 'filter')
           for w in query.get('where') or [] if isinstance(w, dict)]
    if share:
        out.append((resolve(start, share.get('field')), share.get('equals'), 'share'))
    for d in dims:
        if isinstance(d, str):
            out.append((resolve(start, d), None, 'group'))
        elif isinstance(d, dict):
            out.append((resolve(_reached(types, relations, query.get('start'), d.get('via') or []), d.get('field')), None, 'group'))
    return out


def _use(uses: list, field: str, labels: dict[str, str], label: str) -> str | None:
    """How the query reads this meaning of this column: "filter", "exclude" or "share" when one names it or one of its codes, "group" when
    the column is a dimension (which shows every meaning of it), else None."""
    wanted = {label, *(code for code, said in labels.items() if said == label)}
    found = None
    for resolved, equals, kind in uses:
        if resolved != field:
            continue
        if kind == 'group':
            found = found or 'group'
        elif any(str(v) in wanted for v in (equals if isinstance(equals, list) else [equals])):
            return kind
    return found


def column_values(bundle: dict, meanings: dict | None, ontology: dict, graph: dict | None = None) -> dict[str, set[str]]:
    """{field: the values its column holds, as normalize_value reads them, '' for an object with none} for each column with meanings, read per object as
    the query reads it: what a filter that leaves codes out lets through. The query leaves out an object when any of its values is left out, so a column
    in which some object holds more than one value (two rows of one key, a column of rows of another table) is not given: an object that holds a kept
    code and a left-out one would be dropped though its meaning is kept."""
    types = _types(normalize_proposal(ontology))
    graph = graph or build_graph(ontology, bundle)
    values, _, _ = _matcher(types, bundle, graph)
    out, mixed = {}, set()
    for key, t in types.items():
        for field in set(_fields(t)) & set(meanings or {}):
            for inst in (i for i in graph['sources_of'] if i[0] == key):
                got = {normalize_value(v) or '' for v in values(inst, field)} or {''}
                if len(got) > 1:
                    mixed.add(field)
                out.setdefault(field, set()).update(got)
    return {field: held for field, held in out.items() if field not in mixed}


def _left_in(uses: list, field: str, labels: dict[str, str], held: set[str] | None) -> set[str] | None:
    """The meanings a filter that leaves codes out of this column keeps, when every value it lets through (of `held`, the column's values) is a code with
    a meaning: "not 0, 1, 2, 3" on a column holding 0 to 5 keeps 4's and 5's. None when there is no such filter, the values are not known, or it lets a
    blank or a code with no meaning through."""
    given = [v for resolved, equals, kind in uses if resolved == field and kind == 'exclude' for v in (equals if isinstance(equals, list) else [equals])]
    if not given or held is None:
        return None
    left_out = {normalize_value(c) for v in given for c in codes_for_label({field: {'labels': labels}}, field, str(v))}
    said = {normalize_value(c): label for c, label in labels.items() if label}
    through = held - left_out
    return {said[v] for v in through} if through and through <= set(said) else None


def _read_derived(query: dict, types: dict, uses: list, derived: dict | None) -> dict:
    """{field: the confirmed derived property, with `summed`: the query reads it only as its measure, added up} for each one the query reads: in a filter, a
    share, a dimension or its measure."""
    if not derived:
        return {}
    start = types.get(query.get('start'))
    measure = query.get('measure') if isinstance(query.get('measure'), dict) else {}
    named = measure.get('field') if isinstance(measure.get('field'), str) else measure.get('derived') if isinstance(measure.get('derived'), str) else None
    measured = _resolve_field(start, named) if start and named else None
    elsewhere = {f for f, _, _ in uses if f}
    return {f: {**d, 'summed': f == measured and f not in elsewhere and measure.get('op') == 'sum'} for f, d in derived.items() if f in elsewhere or f == measured}   # summed: read only as the measure, added up


def _same_rows(read: dict, source: str, conditions: set, per_object: bool = False) -> dict | None:
    """The derived property through which the query reads `source` (a table) by exactly these conditions ({(column, op, label)}): every derived property it reads
    that counts rows of that table has them, no more and no fewer, so no row the conditions leave out is in its values. None when it reads none, or one that
    differs (it would bring rows in that the conditions keep out, or leave out rows they keep). `per_object`: the query keeps to particular objects (picks_objects),
    so it reads those objects' own rows: every row of the table need not reach an object, but none may be counted for more than one."""
    about = [d for d in read.values() if d['source'] == source]
    if about and all({(c['column'], c['op'], c['label']) for c in d['conditions']} == conditions and _adds_up(d) and d.get('exact' if not per_object else 'once') and not d.get('waiting') for d in about):
        return about[0]
    return None


def _picks_objects(query: dict) -> bool:
    """The query keeps to particular objects of its start type (an equals in its filter, no hop to another type): a per-object count then reads those objects' own
    rows (客户 KH026 的已取消订单数), whether or not every row of the table reaches exactly one object. A total over every object does not."""
    return not query.get('via') and any(isinstance(w, dict) and w.get('equals') not in (None, '', []) for w in query.get('where') or [])


def picks_objects(query: dict, ontology: dict, bundle: dict, graph: dict) -> bool:
    """_picks_objects, and what its filter leaves out changes the number: the measured property's values of the objects it leaves out (as run_query reads the
    filter over these rows) do not add up to 0. A filter that leaves out nothing counted, every customer's 国家 = CN, only customers with no orders, or customers
    whose amounts cancel out, is a total over all of them, and the rows that reach no object would be left out without a word. A query the language cannot read is not one (_shape_limit says so)."""
    if not _picks_objects(query) or _shape_limit(query) or not isinstance(query.get('where'), list) or not all(isinstance(w, dict) for w in query['where']):
        return False
    types = _types(normalize_proposal(ontology))
    start, measure = query.get('start'), query.get('measure')
    if not isinstance(start, str) or start not in types or not isinstance(measure, dict):
        return False
    named = measure.get('field') if isinstance(measure.get('field'), str) else measure.get('derived') if isinstance(measure.get('derived'), str) else None
    measured = _resolve_field(types[start], named) if named else None
    where, why = _conditions(types, start, query['where'], bundle.get('meanings'), lambda k: k)
    if measured is None or why:
        return False
    values, has, _ = _matcher(types, bundle, graph)
    left_out = [i for i in graph['sources_of'] if i[0] == start and not all(has(i, w) != w.get('not', False) for w in where)]
    read = [to_number(v) for i in left_out for v in values(i, measured) if str(v).strip()]
    return any(x is None for x in read) or abs(sum(read)) > 1e-9   # what it leaves out changes the number: their values do not add up to 0


def _adds_up(d: dict) -> bool:
    """Whether the property's values, as the query uses them, add up to its rows: a per-object sum or count, added up by the query's measure. An average, an
    extreme, a distinct count, a formula, or a measure that averages them, is not the rows' total."""
    return d.get('fn') in ('sum', 'count') and bool(d.get('summed'))


def _not_through(read: dict, source: str, conditions: set) -> str:
    """Why a derived property the query reads, with exactly these conditions on `source`, still does not stand for those rows ("" when none has them): a view
    confirmed with its conditions is being redefined, or not every row reaches exactly one object along its path (a key that names nothing, or repeats)."""
    for d in read.values():
        if d['source'] != source or {(c['column'], c['op'], c['label']) for c in d['conditions']} != conditions:
            continue
        if not _adds_up(d):
            return tr(f'（派生属性 {d["name"]} 每个对象的值是按「{d.get("fn") or "算式"}」算的，这条查询{"把它加起来" if d.get("summed") else "不是只把它加起来"}，得到的不是这些行的合计）',
                      f' (the derived property {d["name"]} is worked out per object by "{d.get("fn") or "a formula"}", and the query {"adds it up" if d.get("summed") else "does not just add it up"}, which is not the total of the rows)')
        if d.get('waiting'):
            names = tr('、', ', ').join(d['waiting'])
            return tr(f'（派生属性 {d["name"]} 的条件和视图「{names}」确认时一样，但这个视图改了，还在等确认，现在不能拿派生属性代替它）',
                      f' (the derived property {d["name"]} has the conditions view "{names}" was confirmed with, but that view has been changed and waits for confirming, so the property cannot stand for it now)')
        if not d.get('exact'):
            return tr(f'（派生属性 {d["name"]} 把行算到各个对象上，但「{source}」里不是每一行都正好连上一个对象：有连不上的或重复连上的，加起来和这些行本身的合计不一样）',
                      f' (the derived property {d["name"]} adds rows up per object, but not every row of "{source}" reaches exactly one object: some reach none or more than one, so its sum is not the total of the rows)')
    return ''


def _says(direction: str, definition: str, how: str) -> dict:
    return {'definition': definition, 'direction': direction, 'how': how}


def definition_check(question: str, query: dict, ontology: dict, views: list[dict], meanings: dict | None, used: list | None,
                     told: list | None = None, waiting: dict | None = None, values: dict | None = None, derived: dict | None = None,
                     picks: bool = False, also: dict | None = None) -> dict:
    """{'unmet': [{'definition', 'kind', 'why'}], 'apply': [views to choose rows by], 'understood': [{'definition', 'direction',
    'how'}]}: the model's `definitions_used` (see the top of the file) checked against `query`; `understood` is how the model's
    word was carried out (or that it said nothing), said beside every answer, a refusal too, so that a wrong direction can be
    seen. A meaning counts for a column of an object the query reads (a product is also populated from the orders table, but its
    status is not the orders' status); one the model says it excludes and the query never reads is refused, not dropped (and so is one it includes when the query
    counts that table's rows through a derived property that does not keep exactly it). `told`
    is the ids the model was given when it wrote the question (None: all of them): one it was not given, such as a meaning
    confirmed after the question was written, is not held against it for being left out. An item stored before ids existed
    names a meaning by its label alone; that reads as every meaning with that label. `waiting` is {field: {'labels': {code: label},
    'changes': [what changed]}} for the meanings that wait for a second look. `values` is column_values() of the rows the query reads (the team app only): without
    it a filter that leaves codes out is never read as including the codes it keeps. `derived` is {"table.path" of the property: {'name', 'source' (the table its rows
    are counted from), 'conditions': [{column, op, label}], 'exact': every row of that table reaches exactly one object along its path, 'once': none reaches more than one, 'waiting': views confirmed
    with its conditions that are being redefined}} for the confirmed derived properties: a query that reads one whose conditions are exactly a view's
    (or exactly the meanings the model says the question leaves out) on that table uses that definition through it, though it does not read the table itself. A meaning the question says that the model
    did not list is refused when the query reads such a property, as for a view, even when it is said only inside the property's name: no list of words can tell
    "已取消订单金额" from "减去已取消订单金额", so the model has to say the meaning is included. `picks` is picks_objects(): the query keeps
    to particular objects, so such a property need not have every row reach an object, only none reach more than one. `also` is {'views': {name: other names},
    'meanings': {id: other names}, 'columns': {field: the other names of its property}}: a question that says an other name says the name."""
    if _shape_limit(query):   # a query the language cannot read is said so by the query itself, not refused for a definition
        return {'unmet': [], 'apply': [], 'understood': []}
    also = also or {}
    in_question = lambda term, names=(), column=None, field=None: any(_verbatim(question, t, column, also.get('columns', {}).get(field, ())) for t in (term, *names))   # the term or one of its other names
    rank = {'mention': 0, 'include': 1, 'exclude': 2}
    declared, bare = {}, set()
    for u in clean_used(used):
        if rank[u['direction']] >= rank.get(declared.get(u['id']), -1):
            declared[u['id']] = u['direction']
        if u.get('legacy'):
            bare.add(u['id'])
    normalized = normalize_proposal(ontology)
    tables = query_tables(ontology, query)
    types = _types(normalized)
    uses = _uses(query, types, {r['key']: r for r in normalized['relations']})
    read_fields = {f for k in query_types(ontology, query) if k in types for f in _fields(types[k])}
    read_derived = _read_derived(query, types, uses, derived)
    through = lambda v: _same_rows(read_derived, v['source'], {(f['column'], f['op'], f['label']) for f in v['filters']}) if v.get('filters') and not v.get('latest') and v['source'] not in tables else None
    by_derived = lambda d, v: tr(f'读派生属性 {d["name"]}（它的条件和视图 {v["name"]} 一样）', f'Reads the derived property {d["name"]} (its conditions are those of the view {v["name"]})')
    unmet, apply, understood, omitted = [], [], [], []
    known = {v['name'] for v in views if v['definition'] is not None}
    for field, held in sorted((waiting or {}).items()):
        for label in sorted({x for x in held['labels'].values() if x}):
            ident = meaning_id(field, label)
            known.add(ident)
            direction = declared.get(ident) or (declared.get(label) if label in bare else None)
            if direction or in_question(label, also.get('meanings', {}).get(ident, ()), field.partition('.')[2], field):
                codes = tr('、', ', ').join(sorted(c for c, said in held['labels'].items() if said == label))
                unmet.append({'definition': label, 'kind': 'meaning', 'why': tr(f'{field} 里 {codes} = {label} 这个定义在等你再看一眼（{"；".join(held["changes"][:2])}），不按它回答',
                                                                              f'The definition {field}: {codes} = {label} is waiting for another look ({"; ".join(held["changes"][:2])}), so the answer does not use it')})
                understood.append(_says(direction or UNSAID, label, tr('定义在等再看一眼', 'Definition waiting for another look')))
    offered = lambda *names: told is None or any(n in told for n in names)
    for v in views:
        if v['definition'] is None:   # a table's own views (labels, current) are not something a question names
            continue
        direction = declared.get(v['name'])
        if direction == 'exclude':
            unmet.append({'definition': v['name'], 'kind': 'view', 'why': _excluding()})
            understood.append(_says(direction, v['name'], tr('查询做不到排除', 'A query cannot leave it out')))
        elif direction is None:
            if offered(v['name']) and in_question(v['name'], also.get('views', {}).get(v['name'], ())):
                omitted.append(({'definition': v['name'], 'kind': 'view', 'why': tr('问题里说了它，但模型没有说明它是怎么用的，这条查询也没有读它', 'The question names it, but the model did not say how it is used, and the query does not read it')}, _says(UNSAID, v['name'], _unsaid_how())))
        elif direction == 'mention':
            if v['source'] in tables:
                understood.append(_says(direction, v['name'], tr('只是提到，没有读它', 'Only mentioned, not read')))
            else:
                unmet.append({'definition': v['name'], 'kind': 'view', 'why': tr(f'模型说问题只是提到它，但这条查询没有读它的表「{v["source"]}」，{_unbacked()}', f'The model said it is only mentioned, but the query does not read its table "{v["source"]}", so {_unbacked()}')})
                understood.append(_says(direction, v['name'], _unbacked_how()))
        elif v['state'] != 'confirmed':
            unmet.append({'definition': v['name'], 'kind': 'view', 'why': tr(f'这个视图现在用不了：{v["why"]}', f'This view cannot be used right now: {v["why"]}')})
            understood.append(_says(direction, v['name'], tr('视图现在用不了', 'The view cannot be used right now')))
        elif v['source'] not in tables and (d := through(v)):   # the model says the question includes it, and the rows it keeps are what a derived property the query reads counts (only then: no direction or a mention is refused above)
            understood.append(_says(direction, v['name'], by_derived(d, v)))
        elif v['source'] not in tables:
            unmet.append({'definition': v['name'], 'kind': 'view', 'why': tr(f'它是「{v["source"]}」表上的定义，这条查询没有读这张表', f'It is defined on the table "{v["source"]}", which the query does not read')
                          + (_not_through(read_derived, v['source'], {(f['column'], f['op'], f['label']) for f in v['filters']}) if v.get('filters') else '')})
            understood.append(_says(direction, v['name'], tr('查询没有读它的表', 'The query does not read its table')))
        else:
            apply.append(v)
            understood.append(_says(direction, v['name'], tr(f'读视图 {v["name"]}', f'Reads view {v["name"]}')))
    addressed = set()   # labels of meanings the model said something about, in whichever column
    for field, meaning in sorted((meanings or {}).items()):
        for label in sorted({x for x in meaning['labels'].values() if x}):
            known.update((meaning_id(field, label), *([label] if label in bare else [])))
            if declared.get(meaning_id(field, label)) or (label in bare and declared.get(label)):
                addressed.add(label)
    for field, meaning in sorted((meanings or {}).items()):
        column = field.partition('.')[2]
        kept = _left_in(uses, field, meaning['labels'], (values or {}).get(field)) if field in read_fields else None
        included = {label for label in meaning['labels'].values() if label and (declared.get(meaning_id(field, label)) or (declared.get(label) if label in bare else None)) == 'include'}
        narrowed = any(resolved == field and kind in ('filter', 'share') for resolved, _, kind in uses) or any(   # an equals, a range or a share on the column,
            v['definition'].get('kind') == 'filter' and f'{v["source"]}.{v["definition"].get("column")}' == field for v in apply)   # or a view read that filters it
        rest = kept if kept and kept <= included and not narrowed else None   # the filter leaves the other codes out to keep just the meanings the question includes
        for label in sorted({x for x in meaning['labels'].values() if x}):
            codes = tr('、', ', ').join(sorted(c for c, said in meaning['labels'].items() if said == label))
            ident = meaning_id(field, label)
            direction = declared.get(ident) or (declared.get(label) if label in bare else None)
            what = tr(f'{field} 里 {codes} = {label}', f'{field}: {codes} = {label}')
            colon = tr('：', ': ')
            if field not in read_fields:
                if direction == 'mention':
                    unmet.append({'definition': label, 'kind': 'meaning', 'why': tr(f'{what}：模型说问题只是提到它，但这条查询没有读「{field.partition(".")[0]}」表里的对象，{_unbacked()}',
                                                                                   f'{what}: the model said it is only mentioned, but the query does not read objects from the table "{field.partition(".")[0]}", so {_unbacked()}')})
                    understood.append(_says(direction, label, _unbacked_how()))
                left_out = {(column, 'is_not', x) for x in meaning['labels'].values() if x and (declared.get(meaning_id(field, x)) or (declared.get(x) if x in bare else None)) == 'exclude'}
                asked_in = {x for x in meaning['labels'].values() if x and (declared.get(meaning_id(field, x)) or (declared.get(x) if x in bare else None)) == 'include'}   # (its own count: the filter-includes code above is not read here)
                if direction == 'include' and any(d['source'] == field.partition('.')[0] for d in read_derived.values()):   # the question wants only these rows, and the query counts rows of their table through a derived property: one that keeps exactly this meaning
                    d = _same_rows(read_derived, field.partition('.')[0], {(column, 'is', label)}, picks) if len(asked_in) == 1 else None
                    if d:
                        understood.append(_says(direction, label, tr(f'派生属性 {d["name"]} 只算 {column} = {codes}', f'The derived property {d["name"]} counts only {column} = {codes}')))
                    elif len(asked_in) == 1 and (still := _not_through(read_derived, field.partition('.')[0], {(column, 'is', label)})):   # it reads one that counts only them, which cannot stand for them here
                        unmet.append({'definition': label, 'kind': 'meaning', 'why': tr(f'{what}：问题只要这些行，这条查询没有读「{field.partition(".")[0]}」表里的对象，读的派生属性只算它们，但这里不能代替这些行',
                                                                                       f'{what}: the question wants only these rows; the query reads no objects from the table "{field.partition(".")[0]}", and the derived property it reads counts only them but cannot stand for them here') + still})
                        understood.append(_says(direction, label, tr('查询没有读它所在的列', 'The query does not read its column')))
                    else:
                        unmet.append({'definition': label, 'kind': 'meaning', 'why': tr(f'{what}：问题只要这些行，但这条查询没有读「{field.partition(".")[0]}」表里的对象，也没有读只算它的派生属性，没法只算它们',
                                                                                       f'{what}: the question wants only these rows, but the query reads no objects from the table "{field.partition(".")[0]}" and no derived property that counts only them, so it cannot keep to them')})
                        understood.append(_says(direction, label, tr('查询没有读它所在的列', 'The query does not read its column')))
                if direction == 'exclude' and (d := _same_rows(read_derived, field.partition('.')[0], left_out, picks)):   # a derived property the query reads leaves out exactly these
                    understood.append(_says(direction, label, tr(f'派生属性 {d["name"]} 不算 {column} = {codes}', f'The derived property {d["name"]} leaves out {column} = {codes}')))
                elif direction == 'exclude':
                    unmet.append({'definition': label, 'kind': 'meaning', 'why': tr(f'{what}：这个问法要把它排除，但这条查询没有读「{field.partition(".")[0]}」表里的对象，排除没有地方可做',
                                                                                   f'{what}: the question leaves it out, but the query does not read objects from the table "{field.partition(".")[0]}", so there is nowhere to leave it out')
                                  + _not_through(read_derived, field.partition('.')[0], left_out)})
                    understood.append(_says(direction, label, tr('查询没有读它所在的列', 'The query does not read its column')))
                elif direction is None and offered(ident, label) and label not in addressed and in_question(label, also.get('meanings', {}).get(ident, ()), column, field) \
                        and (counting := [d['name'] for d in read_derived.values() if d['source'] == field.partition('.')[0]]):   # as for a view: the property picks these rows by its own conditions, and the model said nothing of how the question uses the meaning
                    omitted.append(({'definition': label, 'kind': 'meaning', 'why': tr(f'{what} 是确认过的含义，问题里说了它，但模型没有说明它是怎么用的；这条查询读的派生属性{"、".join(counting)}按自己的条件挑「{field.partition(".")[0]}」的行，没法核对。'
                                                                                  f'请换个问法再问：写明是只算「{label}」还是不算它，或者直接点名派生属性「{"」「".join(counting)}」',
                                                                                  f'{what} is a confirmed meaning and the question names it, but the model did not say how it is used; the derived property {", ".join(counting)} the query reads picks the rows of "{field.partition(".")[0]}" by its own conditions, so it cannot be checked. '
                                                                                  f'Ask again in other words: say whether only "{label}" counts or it is left out, or name the derived property "{", ".join(counting)}" outright')},
                                    _says(UNSAID, label, _unsaid_how())))
                continue
            use = _use(uses, field, meaning['labels'], label)
            applied = use in ('filter', 'share')
            if direction == 'exclude':
                other = _excluding_view(views, field, label)
                if use == 'exclude':   # the query itself leaves the meaning's codes out
                    understood.append(_says(direction, label, tr(f'{column} 不是 {codes}（{label}）', f'{column} is not {codes} ({label})')))
                elif other is not None and not applied and other['source'] in tables:
                    apply.append(other)   # the view a person made leaves it out: read that (a dimension on the column is fine)
                    understood.append(_says(direction, label, tr(f'读视图 {other["name"]}', f'Reads view {other["name"]}')))
                else:
                    hint = tr(f'（你定义过的视图「{other["name"]}」就是把它排除后的行，可以直接问它）', f' (your view "{other["name"]}" is these rows with it left out; you can ask it directly)') if other else ''
                    unmet.append({'definition': label, 'kind': 'meaning', 'why': f'{what}{colon}{_not_left_out()}{hint}'})
                    understood.append(_says(direction, label, tr('查询没有把它排除', 'The query does not leave it out')))
            elif direction == 'include' and use is None and rest and label in rest:   # one of the meanings kept by leaving every other code out
                shown = tr('、', ', ').join(sorted(rest))
                understood.append(_says(direction, label, tr(f'{column} 去掉其他取值后只剩 {shown}', f'{column} with the other values left out: only {shown} remain')))
            elif direction == 'include':
                if use is None:
                    unmet.append({'definition': label, 'kind': 'meaning', 'why': tr(f'{what} 是确认过的含义，但这条查询没有按它筛选', f'{what} is a confirmed meaning, but the query does not filter by it')})
                elif use == 'exclude':
                    unmet.append({'definition': label, 'kind': 'meaning', 'why': tr(f'{what}：问题要把它算进来，这条查询却把它排除了', f'{what}: the question includes it, but the query leaves it out')})
                understood.append(_says(direction, label, f'{column} = {codes}' if applied else tr(f'{column} 不是 {codes}，和问题相反', f'{column} is not {codes}, the opposite of the question') if use == 'exclude'
                                 else tr(f'按 {column} 分组', f'Grouped by {column}') if use else tr('查询没有按它筛选', 'The query does not filter by it')))
            elif direction == 'mention':
                if use in ('filter', 'exclude'):
                    unmet.append({'definition': label, 'kind': 'meaning', 'why': tr(f'{what}：模型说问题只是提到它，这条查询却按它筛选了行，方向没法核对', f'{what}: the model said it is only mentioned, but the query filters rows by it, so the direction cannot be checked')})
                elif use is None:
                    unmet.append({'definition': label, 'kind': 'meaning', 'why': tr(f'{what}：模型说问题只是提到它，但这条查询既没有算它的占比，也没有按「{column}」分组，{_unbacked()}',
                                                                               f'{what}: the model said it is only mentioned, but the query neither takes its share nor groups by "{column}", so {_unbacked()}')})
                understood.append(_says(direction, label, tr(f'算它的占比（{column} = {codes}）', f'Takes its share ({column} = {codes})') if use == 'share' else tr(f'按 {column} 分组', f'Grouped by {column}') if use == 'group'
                                 else tr(f'{column} 不是 {codes}', f'{column} is not {codes}') if use == 'exclude' else f'{column} = {codes}' if use else _unbacked_how()))
            elif not offered(ident, label):
                continue
            elif use == 'exclude' and rest:   # left out so that only the meanings the question includes remain: said by those
                continue
            elif use in ('filter', 'share', 'exclude'):
                omitted.append(({'definition': label, 'kind': 'meaning', **({} if in_question(label, also.get('meanings', {}).get(ident, ()), column, field) else {'unasked': True}), 'why': tr(f'{what} 是确认过的含义，这条查询按它筛选了，但模型没有说明问题是要包含还是排除它，方向没法核对',
                                                                                  f'{what} is a confirmed meaning and the query filters by it, but the model did not say whether the question includes or leaves it out, so the direction cannot be checked')},
                                _says(UNSAID, label, tr(f'{column} {"不是" if use == "exclude" else "="} {codes}，但模型没说方向', f'{column} {"is not" if use == "exclude" else "="} {codes}, but the model did not say the direction'))))
            elif label not in addressed and in_question(label, also.get('meanings', {}).get(ident, ()), column, field):
                omitted.append(({'definition': label, 'kind': 'meaning', 'why': tr(f'{what} 是确认过的含义，问题里说了它，但模型没有说明它是怎么用的，这条查询也没有按它筛选',
                                                                              f'{what} is a confirmed meaning and the question names it, but the model did not say how it is used, and the query does not filter by it')}, _says(UNSAID, label, _unsaid_how())))
    unknown = [(name, d) for name, d in sorted(declared.items()) if name not in known and not (told is not None and name in told)]
    for name, d in unknown if known else []:   # with nothing confirmed the model was told no names: a name it writes is nothing to check
        unmet.append({'definition': name, 'kind': 'unknown', 'why': tr(f'模型写的定义名对不上：「{name}」不是你确认过的定义，也不是视图名，没法核对它是怎么用的',
                                                                f'The definition name the model wrote does not match: "{name}" is not a definition you confirmed or a view name, so how it is used cannot be checked')})
        understood.append(_says(d, name, tr('定义名对不上', 'The definition name does not match')))
    if not (unknown and known):   # a name that did not match is why the model seems to have said nothing: that is what is reported
        unmet += [u for u, _ in omitted]
        understood += [w for _, w in omitted]
    return {'unmet': unmet, 'apply': list(({v['name']: v for v in apply}).values()), 'understood': list({(u['definition'], u['how']): u for u in understood}.values())}


def refusal(unmet: list[dict]) -> dict:
    """The answer that says which definitions the question named and the query did not apply."""
    said = tr('；', '; ').join(tr(f'「{u["definition"]}」：{u["why"]}', f'"{u["definition"]}": {u["why"]}') if u.get('unasked')   # only the query used it
                               else tr(f'问题里提到「{u["definition"]}」，{u["why"]}', f'The question mentions "{u["definition"]}": {u["why"]}') for u in unmet)
    return {'status': 'definition_unmet', 'reason': tr(f'没有按你确认过的定义回答：{said}。没有给出数字', f'Not answered under your confirmed definitions. {said}. No number is given.'), 'unmet': unmet}


def filter_conditions(ontology: dict, query: dict, meanings: dict | None) -> dict[str, list[tuple[str, set]]]:
    """{table: [(column, the values the filter accepts)]} for the query's filters: a meaning stands for all its codes."""
    types = _types(normalize_proposal(ontology))
    start = types.get(query.get('start'))
    out: dict[str, list[tuple[str, set]]] = {}
    for w in (query.get('where') or []) if start else []:
        if isinstance(w, dict) and any(k in w for k in RANGES):   # a range names no value to look rows up by
            continue
        field = _resolve_field(start, w.get('field')) if isinstance(w, dict) else None
        if field:
            table, _, column = field.partition('.')
            out.setdefault(table, []).append((column, {normalize_value(c) for c in codes_for_label(meanings, field, w.get('equals'))}))
    return out


def _key_of(record: dict, columns: list[str]) -> tuple:
    return tuple(normalize_value(record.get(c)) for c in columns)


def upstream_problems(data_checks: dict | None, conditions: dict[str, list[tuple[str, set]]], repeat_rules: dict | None,
                      records: dict[str, list[dict]]) -> list[str]:
    """What was already wrong with the tables a filter reads, in the words an answer says, for the damaged rows the filter could
    be asking for: rows with an empty key (no object can have them) and rows whose key is shared by several and nobody has chosen
    how to read (a person's choice is theirs and is not reported). A table that could not be stored is reported whatever the
    filter says. Rows the reader dropped are blank or title rows and cannot match a filter, so they are not reported here."""
    found, checks = [], data_checks or {}
    could_match = lambda table, rows: [r for r in rows if all(normalize_value(r.get(c)) in values for c, values in conditions[table])]
    for t in checks.get('tables', []):
        if t['dataset'] in conditions and t.get('status') == 'error':
            found.append(tr(f'「{t["dataset"]}」没能存进工作区：{t.get("error")}', f'"{t["dataset"]}" could not be saved to the workspace: {t.get("error")}'))
    for k in checks.get('keys', []):
        table = k['dataset']
        if table not in conditions or k['check_type'] != 'key_unique' or k['status'] != 'failed' or table not in records:
            continue
        undecided = rule_key(k['object_type'], table) not in (repeat_rules or {})
        where = tr(f'「{table}」表按 {"、".join(k["key_columns"])} 识别', f'"{table}" identifies rows by {", ".join(k["key_columns"])}')
        keys = [_key_of(r, k['key_columns']) for r in records[table]]
        counted = Counter(keys)
        shared = could_match(table, [r for r, key in zip(records[table], keys) if all(key) and counted[key] > 1]) if k['violations'] and undecided else []
        empty = could_match(table, [r for r, key in zip(records[table], keys) if not all(key)]) if k['null_key_rows'] else []
        if shared:
            found.append(tr(f'{where}，有 {k["violations"]} 行是重复编号，还没有定怎么算，其中 {len(shared)} 行符合这次的筛选条件，同一编号的几行被当成同一个对象',
                            f'{where}; {k["violations"]} rows have a repeated key and nobody has chosen how to read them, {len(shared)} of them match this filter, and rows with the same key are treated as one object'))
        if empty:
            found.append(tr(f'{where}，有 {len(empty)} 行的编号是空的且符合这次的筛选条件，这些行不属于任何对象',
                            f'{where}; {len(empty)} rows have an empty key and match this filter, so they belong to no object'))
    return found


def with_upstream(answer: dict, problems: list[str]) -> dict:
    """"No data" is not said of a table that was damaged upstream: the answer says what was wrong with it."""
    if answer.get('status') != 'no_data' or not problems:
        return answer
    return {**answer, 'status': 'rows_lost', 'upstream': problems,
            'reason': tr(f'没有找到满足筛选条件的行，但读的表在上游就有问题，不能当成“数据里真的没有”：{"；".join(problems)}',
                         f'No rows match the filter, but a table it reads already had problems upstream, so this is not "there is really no data": {"; ".join(problems)}')}


def choose_rows(ontology: dict, bundle: dict, kept: dict[str, set[int]]) -> dict:
    """{table: its records} after the views have chosen: for each table in `kept` ({table: positions of the rows its views keep,
    from 1}) only those rows. An object a view leaves out of its table is also left out of the other tables that populate the same
    kind of object: 有效订单 drops the 16 cancelled orders from 订单, and the commitment and ticket rows that name them
    would otherwise bring 4 of them back as orders only mentioned elsewhere. (Only for populations read straight from a
    column; the other tables keep every row of their own otherwise.)"""
    sources = {table: [r for i, r in enumerate(bundle['sources'][table]['records'], 1) if i in rows] for table, rows in kept.items()}
    plain = lambda pop: pop['transform'] == 'none' and not pop.get('where') and not any('[].' in path for path in pop['identity'].values())
    own = describes_rows(ontology)
    identity = lambda record, pop: tuple(normalize_value(record.get(pop['identity'][k])) for k in sorted(pop['identity']))
    for t in normalize_proposal(ontology)['object_types']:
        pops = [pop for pop in t['populated_from'] if plain(pop)]
        for chosen in (pop for pop in pops if pop['source'] in kept and own(t['key'], pop['source'])):   # rows that describe the object, not rows that only name it (orders name customers)
            records = bundle['sources'][chosen['source']]['records']
            stayed = {identity(r, chosen) for r in sources[chosen['source']]}
            left_out = {identity(r, chosen) for r in records} - stayed
            for other in (pop for pop in pops if pop['source'] != chosen['source'] and set(pop['identity']) == set(chosen['identity'])):
                rows = sources.get(other['source'], bundle['sources'][other['source']]['records'])
                sources[other['source']] = [r for r in rows if identity(r, other) not in left_out]
    return sources
