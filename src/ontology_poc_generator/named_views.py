"""Confirmed definitions as named SQL views in the workspace file. A code meaning a person confirmed, a rule they chose for
a repeated key, and a row filter or "latest per key" they defined by name are each compiled to a view over the stored
tables of one run, so a reader of rows (a pipeline, a question) reads the definition from one place and not from a text
that it may or may not follow.

Four kinds, all computed here from what element_state holds and nothing else:
  labels   订单                a confirmed code meaning adds a column: 状态码_含义 beside 状态码
  current  库存快照_当前        a repeated-key rule "keep the latest by X" gives one row per key
  filter   有效订单            a named row filter: 状态码_含义 is not 已取消
  latest   最新快照            a named "latest row per key" for a versioned or snapshot table

A view whose definition no longer holds (a meaning taken back, a column that has gone) is listed as unavailable with the
reason and does not exist in the file. Every view carries the row's place in its stored table as _行号: it breaks ties the
way a later row of the file wins, as the rule for repeated keys does.

Views belong to one run: their names in the file end in __<8 characters of the run's id>, and they read the tables that run
stored, so opening an older run of the same file never changes what a newer one reads. The definitions themselves are the
file's (kept under its key, shared by every run on the same version line). The file's views are written when a definition
changes (sync_views); what the page and the readers of rows read each time is the same SQL as temporary views on their own
connection (read_views), so listing views never needs the write lock."""
from __future__ import annotations

import json
import sqlite3

from ontology_poc_generator.anchors import stored, view_anchor
from ontology_poc_generator.code_meanings import UNCONFIRMED
from ontology_poc_generator.public_ontology import normalize_proposal
from ontology_poc_generator.repeated_keys import rule_key
from ontology_poc_generator.workspace_store import element_contents, element_rows, set_element_states

ROW = '_行号'
RANK = '_排名'
NUMERIC = ('integer', 'decimal')
ORDERED_TEXT = ('month', 'date', 'datetime')   # written year first, so text order is time order
KINDS = ('filter', 'latest')
OPS = {'is': '=', 'is_not': 'IS NOT'}
MAX_NAME = 30
SUFFIX_LENGTH = 8


class StaleProposal(ValueError):
    """A confirmation names a version of the proposal that is no longer the one on file; the message is shown to the person (HTTP 409)."""


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _lit(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def sql_name(scope: str, name: str) -> str:
    return f'{name}__{scope[:SUFFIX_LENGTH]}'


def _filled(*columns: str) -> str:
    return ' AND '.join(f"({_q(c)} IS NOT NULL AND {_q(c)} <> '')" for c in columns)


def _labels(enums: dict, source: str, column: str) -> dict[str, str]:
    """{code: label} a person confirmed for this column; empty when none."""
    entry = enums.get(f'{source}.{column}') or {}
    return {e['value']: e['label'] for e in entry.get('values', []) if e.get('label')}


def _people(entries: list[dict]) -> tuple[str | None, str | None]:
    names = list(dict.fromkeys(e['confirmed_by'] for e in entries if e.get('confirmed_by')))
    return ('、'.join(names) or None), max((e['confirmed_at'] for e in entries), default=None)


def _view(scope, name, kind, source, select, entries, why=None, from_text='', definition=None, base=None) -> dict:
    by, at = _people(entries)
    columns = [] if why or base is None else [{'name': n, 'type': base['types'][n]} for n in base['names']]   # what a reader sees: _行号 is not one of them
    return {'name': name, 'sql_name': sql_name(scope, name), 'kind': kind, 'source': source, 'sql': select, 'state': 'unavailable' if why else 'confirmed',
            'why': why, 'from': from_text, 'confirmed_by': by, 'confirmed_at': at, 'definition': definition, 'columns': columns,
            'row_alias': None if why or base is None else base['row']}


def _order_expression(column: str, types: dict) -> str | None:
    if types.get(column) in NUMERIC:
        return f'CAST(t.{_q(column)} AS REAL)'
    return f't.{_q(column)}' if types.get(column) in ORDERED_TEXT else None


def orderable(column_type: str) -> bool:
    return column_type in NUMERIC or column_type in ORDERED_TEXT


def _cannot_order(column: str, types: dict) -> str:
    return f'「{column}」是{types.get(column, "不存在的")}类型的列，SQL 里排不出先后（数字、年月、日期才可以）'


def _free(alias: str, taken: set) -> str:
    while alias in taken:
        alias += '_'
    return alias


def _list(items: list[str]) -> str:
    return ',\n  '.join(items)


def _latest_select(base: dict, keys: list[str], order: str) -> str:
    row = f't.{_q(base["row"])}' if base['has_row'] else 't.rowid'
    blank = f"(t.{_q(order)} IS NOT NULL AND t.{_q(order)} <> '')"
    inner = (f'SELECT {_list(["t." + _q(n) for n in base["names"]] + [f"{row} AS {_q(base['row'])}"])},\n'
             f'  ROW_NUMBER() OVER (PARTITION BY {", ".join("t." + _q(k) for k in keys)}\n'
             f'    ORDER BY {blank} DESC, {_order_expression(order, base["types"])} DESC, {row} DESC) AS {_q(base["rank"])}\n'
             f'FROM {base["ref"]} AS t')
    return (f'SELECT {_list([_q(n) for n in [*base["names"], base["row"]]])}\nFROM (\n{inner})\n'
            f'WHERE {_q(base["rank"])} = 1 OR NOT ({_filled(*keys)})')   # a row with no key names no object: all are kept


def _bases(scope: str, tables: dict, enums: dict) -> tuple[dict, list[dict]]:
    """What later views read for each table: the table with its meaning columns when it has confirmed codes, else the table
    itself; and the labels views."""
    bases, views = {}, []
    for source, data in tables.items():
        names = [c['name'] for c in data['columns']]
        types = {c['name']: c['type'] for c in data['columns']}
        coded = [c for c in names if _labels(enums, source, c)]
        taken = {*names, *(f'{n}_含义' for n in names)}   # a column of the table may already be called _行号: the aliases must not collide with any name a view has
        row, rank = _free(ROW, taken), _free(RANK, taken)
        bases[source] = {'ref': _q(data['table']), 'names': names, 'types': types, 'has_row': False, 'row': row, 'rank': rank}
        if not coded:
            continue
        added, why = [], None
        for column in coded:
            label_column = f'{column}_含义'
            if label_column in names:
                why = f'表里已经有一列叫「{label_column}」'
            whens = ''.join(f'\n    WHEN t.{_q(column)} = {_lit(v)} THEN {_lit(label)}' for v, label in sorted(_labels(enums, source, column).items()))
            added.append((label_column, f'CASE\n    WHEN t.{_q(column)} IS NULL THEN NULL{whens}\n    ELSE {_lit(UNCONFIRMED)} END'))
        columns = ['t.' + _q(n) for n in names] + [f'{expression} AS {_q(label)}' for label, expression in added] + [f't.rowid AS {_q(row)}']
        select = f'SELECT {_list(columns)}\nFROM {_q(data["table"])} AS t'
        labelled = {'ref': '', 'names': names + [label for label, _ in added], 'types': {**types, **{label: 'text' for label, _ in added}}, 'has_row': True, 'row': row, 'rank': rank}
        view = _view(scope, source, 'labels', source, select, [enums[f'{source}.{c}'] for c in coded], why,
                     '、'.join(f'{source}.{c} 的已确认含义' for c in coded), base=labelled)
        views.append(view)
        if not why:
            bases[source] = {**labelled, 'ref': _q(view['sql_name'])}
    return bases, views


def _named_view(scope: str, name: str, definition: dict, bases: dict, enums: dict, duplicate: bool, waiting: dict | None = None) -> dict:
    source, why, select = definition['base'], None, None
    base = bases.get(source)
    if duplicate:
        why = f'名字「{name}」和别的视图或表重了（不分大小写）'
    elif base is None:
        why = f'「{source}」这次没有存进工作区'
    elif definition['kind'] == 'latest':
        missing = [c for c in [*definition['key'], definition['order']] if c not in base['names']]
        if missing:
            why = f'表里已经没有列 {"、".join(missing)}'
        elif _order_expression(definition['order'], base['types']) is None:
            why = _cannot_order(definition['order'], base['types'])
        else:
            select = _latest_select(base, definition['key'], definition['order'])
    else:
        column, label = definition['column'], definition['label']
        if label in _labels(waiting or {}, source, column).values():
            why = f'「{label}」是「{source}.{column}」的含义，它要你再看一眼才能用（数据变了，见“需要再看一眼”）'
        elif label not in _labels(enums, source, column).values():
            why = f'「{label}」现在不是「{source}.{column}」已确认的含义'
        else:
            select = (f'SELECT {_list([_q(n) for n in [*base["names"], base["row"]]])}\nFROM {base["ref"]}\n'
                      f'WHERE {_q(column + "_含义")} {OPS[definition["op"]]} {_lit(label)}')
    said = (f'你定义的：{source}里每个「{"」「".join(definition["key"])}」只留「{definition["order"]}」最新的一行' if definition['kind'] == 'latest'
            else f'你定义的：{source}.{definition["column"]} {"是" if definition["op"] == "is" else "不是"}「{definition["label"]}」的行')
    return _view(scope, name, definition['kind'], source, select, [definition], why, said, definition, base)


def compile_views(scope: str, ontology: dict, tables: dict, enums: dict, rules: dict, named: dict, waiting: dict | None = None) -> list[dict]:
    """Every definition a person confirmed for one run as a view, in the order they can be created: tables is
    {source: {'table', 'columns': [{'name', 'type'}]}} (see pipelines.workspace_datasets), enums the confirmed meanings by
    "table.column", rules the repeated-key rules by "type.table", named the views a person defined, by name, waiting the
    meanings that wait for a second look (same shape as enums: a view that needs one says so)."""
    bases, views = _bases(scope, tables, enums)
    taken = {n.lower() for n in [*(v['name'] for v in views), *tables]}   # SQLite does not tell view names apart by case
    for t in normalize_proposal(ontology)['object_types']:
        for pop in t['populated_from']:
            rule = rules.get(rule_key(t['key'], pop['source']))
            if not rule or rule['rule'] != 'keep_latest' or f'{pop["source"]}_当前'.lower() in taken:   # one view per table, even when two types are read from it
                continue
            source, name, keys, order = pop['source'], f'{pop["source"]}_当前', list(pop['identity'].values()), rule['column']
            base = bases.get(source)
            why = None if base else f'「{source}」这次没有存进工作区'
            if base and not set(keys) <= set(base['names']):
                why = f'编号列 {"、".join(keys)} 不是「{source}」里的列'
            elif base and _order_expression(order, base['types']) is None:
                why = _cannot_order(order, base['types'])
            views.append(_view(scope, name, 'current', source, None if why else _latest_select(base, keys, order), [rule], why,
                               f'{t.get("label") or t["key"]}（{source}表）重复编号的处理办法：只留「{order}」最新的一行', base=base))
            taken.add(name.lower())
    for name, definition in sorted(named.items()):
        try:
            views.append(_named_view(scope, name, definition, bases, enums, name.lower() in taken, waiting))
        except (KeyError, TypeError) as exc:   # a definition kept in a shape this code does not read: one row saying so, with the way to take it back
            views.append(_view(scope, name, str(definition.get('kind')) if isinstance(definition, dict) else 'unknown', None, None, [], f'定义读不出来：{type(exc).__name__} {exc}', '', definition))
        taken.add(name.lower())
    return views


def _existing(conn, run_id: str) -> dict[str, str]:
    tail = f'__{run_id[:SUFFIX_LENGTH]}'
    return {n: s for n, s in conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'view'") if n.endswith(tail)}


def sync_views(conn, run_id: str, views: list[dict]) -> dict[str, str]:
    """Make the file hold exactly this run's available views, each as it is compiled now: a view that changed is created again,
    one that no longer holds is dropped. Takes the write lock only when something has to change. A view the database
    refuses is left out and named, with the database's words, in what is returned: one bad view does not stop the others."""
    wanted = {v['sql_name']: f'CREATE VIEW {_q(v["sql_name"])} AS {v["sql"]}' for v in views if v['state'] == 'confirmed'}
    if _existing(conn, run_id) == wanted:
        return {}
    refused = {}
    conn.execute('BEGIN IMMEDIATE')
    try:
        have = _existing(conn, run_id)
        for name in have:
            if wanted.get(name) != have[name]:
                conn.execute(f'DROP VIEW {_q(name)}')
        for name, create in wanted.items():
            if have.get(name) != create:
                try:
                    conn.execute(create)
                except sqlite3.Error as exc:
                    refused[name] = f'{type(exc).__name__}: {exc}'[:200]
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return refused


def drop_views_except(conn, keep_run_ids: set[str]) -> int:
    """Drop the views of every run not in keep_run_ids: a run whose file is gone no longer has views. Returns how many."""
    keep = {f'__{r[:SUFFIX_LENGTH]}' for r in keep_run_ids}
    gone = [n for (n,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'") if '__' in n and n[n.rindex('__'):] not in keep]
    if gone:
        conn.execute('BEGIN IMMEDIATE')
        try:
            for name in gone:
                conn.execute(f'DROP VIEW {_q(name)}')
            conn.execute('COMMIT')
        except BaseException:
            conn.execute('ROLLBACK')
            raise
    return len(gone)


def read_views(conn, run_id: str, views: list[dict]) -> None:
    """Make this run's available views, and only those, readable on this connection as temporary views: the same SQL the
    file's views hold, always as compiled now, and no write to the file (so a read-only connection can do it)."""
    tail = f'__{run_id[:SUFFIX_LENGTH]}'
    for (name,) in conn.execute("SELECT name FROM sqlite_temp_master WHERE type = 'view'").fetchall():
        if name.endswith(tail):
            conn.execute(f'DROP VIEW temp.{_q(name)}')
    for v in views:
        if v['state'] == 'confirmed':
            conn.execute(f'CREATE TEMP VIEW {_q(v["sql_name"])} AS {v["sql"]}')


def view_names(views: list[dict]) -> dict[str, str]:
    """The one place a person's name for a view becomes the name it has in the database: {name: stored name}, available views only."""
    return {v['name']: v['sql_name'] for v in views if v['state'] == 'confirmed'}


def compiled_views(conn, key: str, run_id: str, ontology: dict, tables: dict) -> list[dict]:
    """Every definition on file under this key as a view over this run's tables (see compile_views); reads only."""
    return compile_views(run_id, ontology, tables, element_contents(conn, f'property:{key}:'),
                         element_contents(conn, f'repeat_rule:{key}:'), element_contents(conn, f'view:{key}:'),
                         {k: r['content'] for k, r in element_rows(conn, f'property:{key}:', 'checked').items() if r['content']})


def table_columns(tables: dict) -> list[dict]:
    """What a form for defining a view offers: each table's columns and whether SQL can put its values in order."""
    return [{'name': name, 'columns': [{'name': c['name'], 'orderable': orderable(c['type'])} for c in data['columns']]} for name, data in tables.items()]


def views_of_run(conn, key: str, run_id: str, ontology: dict, tables: dict) -> list[dict]:
    """The views of one run, each with its row count, read on this connection without writing to the file. A view that
    cannot be read is unavailable, with the database's own words."""
    views = compiled_views(conn, key, run_id, ontology, tables)
    read_views(conn, run_id, views)
    out = []
    for v in views:
        count = None
        if v['state'] == 'confirmed':
            try:
                count = conn.execute(f'SELECT COUNT(*) FROM {_q(v["sql_name"])}').fetchone()[0]
            except sqlite3.Error as exc:
                v = {**v, 'state': 'unavailable', 'why': f'{type(exc).__name__}: {exc}'[:200], 'columns': []}
        out.append({**v, 'rows': count})
    return out


def view_rowids(conn, view: dict) -> list[int]:
    """The positions (in the table as stored, from 1) of the rows a view keeps, in file order. A view only chooses rows: the
    values an answer reads are the stored table's own."""
    return [r[0] for r in conn.execute(f'SELECT {_q(view["row_alias"])} FROM {_q(view["sql_name"])} ORDER BY 1')]


def query_types(ontology: dict, query: dict) -> set[str]:
    """The object types a query reads: its start, and every one it walks to."""
    relations = {r['key']: r for r in normalize_proposal(ontology)['relations']}
    group_by = query.get('group_by')
    dims = [group_by] if isinstance(group_by, dict) else group_by if isinstance(group_by, list) else []
    paths = [query.get('via') or [], *[d.get('via') or [] for d in dims if isinstance(d, dict)]]
    return {query.get('start')} | {end for path in paths if isinstance(path, list) for r in path if r in relations for end in (relations[r]['from'], relations[r]['to'])}


def query_tables(ontology: dict, query: dict) -> set[str]:
    """The tables a query reads rows of: the ones the object types it reads are populated from."""
    types = {t['key']: t for t in normalize_proposal(ontology)['object_types']}
    return {pop['source'] for k in query_types(ontology, query) if k in types for pop in types[k]['populated_from']}


def name_views(answer: dict, query, ontology: dict, applied: list[dict], unread: str | None) -> dict:
    """The answer with the views its rows were chosen by named in its evidence ({'views': [{'name', 'kind', 'source', 'rows',
    'from'}]}), or, when a view could not be used and the table's rows were read instead, that said in `views_unread`."""
    tables = query_tables(ontology, query) if isinstance(query, dict) else set()
    used = [{'name': v['name'], 'kind': v['kind'], 'source': v['source'], 'rows': v['rows'], 'from': v['from']} for v in applied if v['source'] in tables]
    if not used and not unread:
        return answer
    return {**answer, 'evidence': {**(answer.get('evidence') or {}), **({'views': used} if used else {}), **({'views_unread': unread} if unread else {})}}


def definitions_signature(conn, key: str) -> tuple:
    """What every view of a file is compiled from: its definitions with their versions. Two reads that see the same
    signature (and the same tables) see the same views, so what was worked out from them can be kept."""
    return tuple(sorted(row for prefix in ('property', 'repeat_rule', 'view') for row in conn.execute(
        'SELECT element_id, version FROM element_state WHERE substr(element_id, 1, ?) = ? AND state = ?', (len(f'{prefix}:{key}:'), f'{prefix}:{key}:', 'confirmed'))))


def check_definition(posted, tables: dict, enums: dict, reserved: set) -> tuple[str, dict]:
    """A person's definition of a view as (name, content to keep). Raises ValueError, with the text the person reads, when
    it cannot be kept."""
    if not isinstance(posted, dict):
        raise ValueError('视图要写成 {"name": …, "kind": …}')
    name = posted.get('name')
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > MAX_NAME or '"' in name:
        raise ValueError(f'视图的名字要写 1–{MAX_NAME} 个字，不含引号')
    name = name.strip()
    if name.lower() in {r.lower() for r in reserved}:   # SQLite does not tell view names apart by case
        raise ValueError(f'「{name}」已经是一张表或一个视图的名字（不分大小写）')
    kind, source = posted.get('kind'), posted.get('base')
    if kind not in KINDS:
        raise ValueError('视图的种类只有：按含义筛行（filter）、每个编号只留最新一行（latest）')
    if source not in tables:
        raise ValueError(f'这次运行里没有这张表：{source}')
    types = {c['name']: c['type'] for c in tables[source]['columns']}
    if kind == 'filter':
        column, op, label = posted.get('column'), posted.get('op'), posted.get('label')
        if op not in OPS:
            raise ValueError('条件只能是“是”或“不是”（is、is_not）')
        if column not in types or not _labels(enums, source, column):
            raise ValueError(f'「{source}.{column}」还没有已确认的含义，先确认它的含义')
        if label not in _labels(enums, source, column).values():
            raise ValueError(f'「{label}」不是「{source}.{column}」已确认的含义：{"、".join(sorted(set(_labels(enums, source, column).values())))}')
        return name, {'kind': kind, 'base': source, 'column': column, 'op': op, 'label': label}
    keys, order = posted.get('key'), posted.get('order')
    if not isinstance(keys, list) or not keys or not all(k in types for k in keys) or len(set(keys)) != len(keys):
        raise ValueError(f'编号列要写成「{source}」里的几列，不重复')
    if order not in types or order in keys:
        raise ValueError(f'要选「{source}」里的一列来比先后，不能是编号列')
    if _order_expression(order, types) is None:
        raise ValueError(_cannot_order(order, types))
    return name, {'kind': kind, 'base': source, 'key': keys, 'order': order}


def definition_change(key: str, name: str, content: dict | None, signer: str | None, anchors: dict | None = None, state: str = 'confirmed',
                      author: str | None = None) -> tuple:
    """The element_state change for one view: confirmed with who defined it and what it was defined on, or taken back (content None), or put
    forward for another person to confirm (state 'proposed'). `author` is whose own definition it is; a confirmation of a proposal leaves it
    out and the proposer on file stays."""
    element = f'view:{key}:{name}'
    if content is None:
        return (element, 'proposed', None, signer)
    evidence = f'element:property:{key}:{content["base"]}.{content["column"]}' if content['kind'] == 'filter' else None
    return (element, state, evidence, signer, content, stored(anchors), author)


def proposed_views(conn, key: str) -> list[dict]:
    """The views put forward and waiting for another person: [{'name', 'definition', 'proposed_by', 'proposed_at', 'version'}]. `version` is what
    a confirmation must carry back: it moves whenever the definition on file changes."""
    prefix = f'view:{key}:'
    return [{'name': element_id[len(prefix):], 'definition': json.loads(content), 'proposed_by': by, 'proposed_at': at, 'version': version}
            for element_id, content, by, at, version in conn.execute(
                "SELECT element_id, content_json, proposed_by, confirmed_at, version FROM element_state WHERE substr(element_id, 1, ?) = ? "
                "AND state = 'proposed' AND content_json IS NOT NULL ORDER BY element_id", (len(prefix), prefix))]


def view_anchor_now(conn, key: str, run_id: str, ontology: dict, tables: dict, name: str, content: dict, versions: dict) -> dict:
    """The anchor of a view as it would be once defined: the rows it keeps of its table now. Reads the file's definitions with this
    one added, on temporary views of this connection."""
    named = {**element_contents(conn, f'view:{key}:'), name: {**content, 'confirmed_by': None, 'confirmed_at': None}}
    views = compile_views(run_id, ontology, tables, element_contents(conn, f'property:{key}:'), element_contents(conn, f'repeat_rule:{key}:'), named)
    read_views(conn, run_id, views)
    view = next(v for v in views if v['name'] == name)
    if view['state'] != 'confirmed':
        raise ValueError(view['why'])
    rows = conn.execute(f'SELECT COUNT(*) FROM {_q(view["sql_name"])}').fetchone()[0]
    return view_anchor(rows, tables[content['base']]['rows'], content['base'], versions.get(content['base']))


def save_definition(conn, key: str, posted, tables: dict, ontology: dict, signer: str | None, run_id: str = 'anchored', versions: dict | None = None,
                    propose: bool = False) -> str:
    """Keep or take back a person's named view; returns the sentence saying what happened. ValueError says why not. `versions`:
    {table: the dataset version it is stored as}, kept in the view's anchor. `propose`: put it forward for another person instead of confirming
    it ({"confirm": name, "version": N} in `posted` is that other person confirming the version of the proposal they looked at: StaleProposal when
    it has changed since, so a confirmation never lands on a definition nobody reviewed; checked against the data as it is now)."""
    enums = element_contents(conn, f'property:{key}:')
    confirming = isinstance(posted, dict) and isinstance(posted.get('confirm'), str)
    if confirming:
        waiting = {v['name']: v for v in proposed_views(conn, key)}.get(posted['confirm'])
        if waiting is None:
            raise ValueError(f'没有等着确认的视图「{posted["confirm"]}」')
        seen = posted.get('version')
        if not isinstance(seen, int) or isinstance(seen, bool):
            raise ValueError('确认要带上你看到的那一版（version，在待确认的列表里）')
        if seen != waiting['version']:
            raise StaleProposal(f'视图「{posted["confirm"]}」在你看过之后被改了（你看的是第 {seen} 版，现在是第 {waiting["version"]} 版），请重新看一遍再确认')
        posted = {**waiting['definition'], 'name': posted['confirm']}
    if isinstance(posted, dict) and posted.get('remove') is True:
        name = posted.get('name')
        if name not in element_contents(conn, f'view:{key}:'):
            raise ValueError(f'没有叫「{name}」的视图可以删')
        set_element_states(conn, [definition_change(key, name, None, signer)])
        return f'视图「{name}」已收回'
    others = lambda name: {n for n in element_contents(conn, f'view:{key}:') if n != name}   # a name already defined is redefined, not refused; one that differs only in case is refused
    reserved = set(tables) | {f'{s}_当前' for s in tables}
    name = posted.get('name').strip() if isinstance(posted, dict) and isinstance(posted.get('name'), str) else ''
    name, content = check_definition(posted, tables, enums, reserved | others(name))
    anchor = view_anchor_now(conn, key, run_id, ontology, tables, name, content, versions or {})   # a view that cannot be read on the data as it is now is refused either way
    if propose and not confirming:
        set_element_states(conn, [definition_change(key, name, content, signer, state='proposed', author=signer)])
        return f'视图「{name}」已提交，等另一位确认'
    set_element_states(conn, [definition_change(key, name, content, signer, anchor, author=None if confirming else signer)])
    return f'视图「{name}」已确认'
