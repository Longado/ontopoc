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
  exclude    a named view a person made that leaves the meaning out is read in its place; else the query language, which
             can only say "a field equals a value", cannot say it, and the answer is refused naming what could not be applied
  omitted    a confirmed label the model did not list, that the question says verbatim (three characters or more, or with its
             column named) or that the query filters by: refused, saying the model did not say how it was used
  unknown    an id the model wrote that is in no catalog entry (a synonym such as 取消), whatever direction it gave: refused, saying the name did not match,
             and the omissions it causes are not reported on top
  waiting    a meaning whose confirmation broke when the data changed (anchors.py) and waits for a second look: counts as nothing
             confirmed, and a question that says its label (or a model that lists it) is refused saying so, never answered under the
             old label
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
from ontology_poc_generator.named_views import query_tables, query_types
from ontology_poc_generator.ontology_questions import _fields, _resolve_field, _shape_limit, _types, clean_used
from ontology_poc_generator.public_ontology import normalize_proposal, normalize_value
from ontology_poc_generator.repeated_keys import rule_key
from ontology_poc_generator.workspace_store import describes_rows

EXCLUDING = '这个问法要把它排除，查询只能写“某个字段等于某个值”，做不到排除'
UNSAID, UNSAID_HOW = 'unsaid', '出题员没有说明它是怎么用的'
UNBACKED, UNBACKED_HOW = '没法核对', '只是提到却没有用到它，没法核对'


def _verbatim(question: str, term: str, column: str | None = None) -> bool:
    """Does the question say the label itself? A label of one or two characters (1 = 是) is in every other sentence, so it counts
    only with its column named; one made of letters and digits must stand apart from them."""
    if column is not None and len(term) < 3 and column not in question:
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


def definition_catalog(meanings: dict | None, views: list[dict]) -> list[dict]:
    """What the model is told a person has confirmed: each code meaning (its label) and each view they named, with what it is."""
    out = [{'id': meaning_id(field, label), 'name': label, 'kind': 'meaning', 'means': f'{field} 里 {"、".join(sorted(c for c, said in m["labels"].items() if said == label))} = {label}'}
           for field, m in sorted((meanings or {}).items()) for label in sorted({x for x in m['labels'].values() if x})]
    return out + [{'id': v['name'], 'name': v['name'], 'kind': 'view', 'means': v['from']} for v in views if v['definition'] is not None]


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
    """(the "table.path" it reads, the value it is compared with, 'filter' | 'share' | 'group') for every filter, share and
    dimension of the query, each field read as the object type it belongs to reads it: a field is not another table's column
    of the same name."""
    start = types.get(query.get('start'))
    group_by = query.get('group_by')
    dims = [group_by] if isinstance(group_by, (str, dict)) else group_by if isinstance(group_by, list) else []
    share = query.get('share') if isinstance(query.get('share'), dict) else {}
    resolve = lambda t, name: _resolve_field(t, name) if t else None
    out = [(resolve(start, w.get('field')), w.get('equals'), 'filter') for w in query.get('where') or [] if isinstance(w, dict)]
    if share:
        out.append((resolve(start, share.get('field')), share.get('equals'), 'share'))
    for d in dims:
        if isinstance(d, str):
            out.append((resolve(start, d), None, 'group'))
        elif isinstance(d, dict):
            out.append((resolve(_reached(types, relations, query.get('start'), d.get('via') or []), d.get('field')), None, 'group'))
    return out


def _use(uses: list, field: str, labels: dict[str, str], label: str) -> str | None:
    """How the query reads this meaning of this column: "filter" or "share" when one names it or one of its codes, "group" when
    the column is a dimension (which shows every meaning of it), else None."""
    wanted = {label, *(code for code, said in labels.items() if said == label)}
    found = None
    for resolved, equals, kind in uses:
        if resolved != field:
            continue
        if kind == 'group':
            found = found or 'group'
        elif str(equals) in wanted:
            return kind
    return found


def _says(direction: str, definition: str, how: str) -> dict:
    return {'definition': definition, 'direction': direction, 'how': how}


def definition_check(question: str, query: dict, ontology: dict, views: list[dict], meanings: dict | None, used: list | None,
                     told: list | None = None, waiting: dict | None = None) -> dict:
    """{'unmet': [{'definition', 'kind', 'why'}], 'apply': [views to choose rows by], 'understood': [{'definition', 'direction',
    'how'}]}: the model's `definitions_used` (see the top of the file) checked against `query`; `understood` is how the model's
    word was carried out (or that it said nothing), said beside every answer, a refusal too, so that a wrong direction can be
    seen. A meaning counts for a column of an object the query reads (a product is also populated from the orders table, but its
    status is not the orders' status); one the model says it excludes and the query never reads is refused, not dropped. `told`
    is the ids the model was given when it wrote the question (None: all of them): one it was not given, such as a meaning
    confirmed after the question was written, is not held against it for being left out. An item stored before ids existed
    names a meaning by its label alone; that reads as every meaning with that label. `waiting` is {field: {'labels': {code: label},
    'changes': [what changed]}} for the meanings that wait for a second look."""
    if _shape_limit(query):   # a query the language cannot read is said so by the query itself, not refused for a definition
        return {'unmet': [], 'apply': [], 'understood': []}
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
    unmet, apply, understood, omitted = [], [], [], []
    known = {v['name'] for v in views if v['definition'] is not None}
    for field, held in sorted((waiting or {}).items()):
        for label in sorted({x for x in held['labels'].values() if x}):
            ident = meaning_id(field, label)
            known.add(ident)
            direction = declared.get(ident) or (declared.get(label) if label in bare else None)
            if direction or _verbatim(question, label, field.partition('.')[2]):
                codes = '、'.join(sorted(c for c, said in held['labels'].items() if said == label))
                unmet.append({'definition': label, 'kind': 'meaning', 'why': f'{field} 里 {codes} = {label} 这个定义在等你再看一眼（{"；".join(held["changes"][:2])}），不按它回答'})
                understood.append(_says(direction or UNSAID, label, '定义在等再看一眼'))
    offered = lambda *names: told is None or any(n in told for n in names)
    for v in views:
        if v['definition'] is None:   # a table's own views (labels, current) are not something a question names
            continue
        direction = declared.get(v['name'])
        if direction == 'exclude':
            unmet.append({'definition': v['name'], 'kind': 'view', 'why': EXCLUDING})
            understood.append(_says(direction, v['name'], '查询做不到排除'))
        elif direction is None:
            if offered(v['name']) and _verbatim(question, v['name']):
                omitted.append(({'definition': v['name'], 'kind': 'view', 'why': '问题里说了它，但出题员没有说明它是怎么用的，这条查询也没有读它'}, _says(UNSAID, v['name'], UNSAID_HOW)))
        elif direction == 'mention':
            if v['source'] in tables:
                understood.append(_says(direction, v['name'], '只是提到，没有读它'))
            else:
                unmet.append({'definition': v['name'], 'kind': 'view', 'why': f'出题员说问题只是提到它，但这条查询没有读它的表「{v["source"]}」，{UNBACKED}'})
                understood.append(_says(direction, v['name'], UNBACKED_HOW))
        elif v['state'] != 'confirmed':
            unmet.append({'definition': v['name'], 'kind': 'view', 'why': f'这个视图现在用不了：{v["why"]}'})
            understood.append(_says(direction, v['name'], '视图现在用不了'))
        elif v['source'] not in tables:
            unmet.append({'definition': v['name'], 'kind': 'view', 'why': f'它是「{v["source"]}」表上的定义，这条查询没有读这张表'})
            understood.append(_says(direction, v['name'], '查询没有读它的表'))
        else:
            apply.append(v)
            understood.append(_says(direction, v['name'], f'读视图 {v["name"]}'))
    addressed = set()   # labels of meanings the model said something about, in whichever column
    for field, meaning in sorted((meanings or {}).items()):
        for label in sorted({x for x in meaning['labels'].values() if x}):
            known.update((meaning_id(field, label), *([label] if label in bare else [])))
            if declared.get(meaning_id(field, label)) or (label in bare and declared.get(label)):
                addressed.add(label)
    for field, meaning in sorted((meanings or {}).items()):
        column = field.partition('.')[2]
        for label in sorted({x for x in meaning['labels'].values() if x}):
            codes = '、'.join(sorted(c for c, said in meaning['labels'].items() if said == label))
            ident = meaning_id(field, label)
            direction = declared.get(ident) or (declared.get(label) if label in bare else None)
            what = f'{field} 里 {codes} = {label}'
            if field not in read_fields:
                if direction == 'mention':
                    unmet.append({'definition': label, 'kind': 'meaning', 'why': f'{what}：出题员说问题只是提到它，但这条查询没有读「{field.partition(".")[0]}」表里的对象，{UNBACKED}'})
                    understood.append(_says(direction, label, UNBACKED_HOW))
                if direction == 'exclude':
                    unmet.append({'definition': label, 'kind': 'meaning', 'why': f'{what}：这个问法要把它排除，但这条查询没有读「{field.partition(".")[0]}」表里的对象，排除没有地方可做'})
                    understood.append(_says(direction, label, '查询没有读它所在的列'))
                continue
            use = _use(uses, field, meaning['labels'], label)
            applied = use in ('filter', 'share')
            if direction == 'exclude':
                other = _excluding_view(views, field, label)
                if other is not None and not applied and other['source'] in tables:
                    apply.append(other)   # the view a person made leaves it out: read that (a dimension on the column is fine)
                    understood.append(_says(direction, label, f'读视图 {other["name"]}'))
                else:
                    hint = f'（你定义过的视图「{other["name"]}」就是把它排除后的行，可以直接问它）' if other else ''
                    unmet.append({'definition': label, 'kind': 'meaning', 'why': f'{what}：{EXCLUDING}{hint}'})
                    understood.append(_says(direction, label, '查询做不到排除'))
            elif direction == 'include':
                if use is None:
                    unmet.append({'definition': label, 'kind': 'meaning', 'why': f'{what} 是确认过的含义，但这条查询没有按它筛选'})
                understood.append(_says(direction, label, f'{column} = {codes}' if applied else f'按 {column} 分组' if use else '查询没有按它筛选'))
            elif direction == 'mention':
                if use == 'filter':
                    unmet.append({'definition': label, 'kind': 'meaning', 'why': f'{what}：出题员说问题只是提到它，这条查询却按它筛选了行，方向没法核对'})
                elif use is None:
                    unmet.append({'definition': label, 'kind': 'meaning', 'why': f'{what}：出题员说问题只是提到它，但这条查询既没有算它的占比，也没有按「{column}」分组，{UNBACKED}'})
                understood.append(_says(direction, label, f'算它的占比（{column} = {codes}）' if use == 'share' else f'按 {column} 分组' if use == 'group' else f'{column} = {codes}' if use else UNBACKED_HOW))
            elif not offered(ident, label):
                continue
            elif use == 'filter' or use == 'share':
                omitted.append(({'definition': label, 'kind': 'meaning', 'why': f'{what} 是确认过的含义，这条查询按它筛选了，但出题员没有说明问题是要包含还是排除它，方向没法核对'}, _says(UNSAID, label, f'{column} = {codes}，但出题员没说方向')))
            elif label not in addressed and _verbatim(question, label, column):
                omitted.append(({'definition': label, 'kind': 'meaning', 'why': f'{what} 是确认过的含义，问题里说了它，但出题员没有说明它是怎么用的，这条查询也没有按它筛选'}, _says(UNSAID, label, UNSAID_HOW)))
    unknown = [(name, d) for name, d in sorted(declared.items()) if name not in known and not (told is not None and name in told)]
    for name, d in unknown if known else []:   # with nothing confirmed the model was told no names: a name it writes is nothing to check
        unmet.append({'definition': name, 'kind': 'unknown', 'why': f'模型写的定义名对不上：「{name}」不是你确认过的定义，也不是视图名，没法核对它是怎么用的'})
        understood.append(_says(d, name, '定义名对不上'))
    if not (unknown and known):   # a name that did not match is why the model seems to have said nothing: that is what is reported
        unmet += [u for u, _ in omitted]
        understood += [w for _, w in omitted]
    return {'unmet': unmet, 'apply': list(({v['name']: v for v in apply}).values()), 'understood': list({(u['definition'], u['how']): u for u in understood}.values())}


def refusal(unmet: list[dict]) -> dict:
    """The answer that says which definitions the question named and the query did not apply."""
    said = '；'.join(f'问题里提到「{u["definition"]}」，{u["why"]}' for u in unmet)
    return {'status': 'definition_unmet', 'reason': f'没有按你确认过的定义回答：{said}。没有给出数字', 'unmet': unmet}


def filter_conditions(ontology: dict, query: dict, meanings: dict | None) -> dict[str, list[tuple[str, set]]]:
    """{table: [(column, the values the filter accepts)]} for the query's filters: a meaning stands for all its codes."""
    types = _types(normalize_proposal(ontology))
    start = types.get(query.get('start'))
    out: dict[str, list[tuple[str, set]]] = {}
    for w in (query.get('where') or []) if start else []:
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
            found.append(f'「{t["dataset"]}」没能存进工作区：{t.get("error")}')
    for k in checks.get('keys', []):
        table = k['dataset']
        if table not in conditions or k['check_type'] != 'key_unique' or k['status'] != 'failed' or table not in records:
            continue
        undecided = rule_key(k['object_type'], table) not in (repeat_rules or {})
        where = f'「{table}」表按 {"、".join(k["key_columns"])} 识别'
        keys = [_key_of(r, k['key_columns']) for r in records[table]]
        counted = Counter(keys)
        shared = could_match(table, [r for r, key in zip(records[table], keys) if all(key) and counted[key] > 1]) if k['violations'] and undecided else []
        empty = could_match(table, [r for r, key in zip(records[table], keys) if not all(key)]) if k['null_key_rows'] else []
        if shared:
            found.append(f'{where}，有 {k["violations"]} 行是重复编号，还没有定怎么算，其中 {len(shared)} 行符合这次的筛选条件，同一编号的几行被当成同一个对象')
        if empty:
            found.append(f'{where}，有 {len(empty)} 行的编号是空的且符合这次的筛选条件，这些行不属于任何对象')
    return found


def with_upstream(answer: dict, problems: list[str]) -> dict:
    """"No data" is not said of a table that was damaged upstream: the answer says what was wrong with it."""
    if answer.get('status') != 'no_data' or not problems:
        return answer
    return {**answer, 'status': 'rows_lost', 'upstream': problems,
            'reason': f'没有找到满足筛选条件的行，但读的表在上游就有问题，不能当成“数据里真的没有”：{"；".join(problems)}'}


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
