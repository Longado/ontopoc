"""OntoPoc Query (本体查询): SQL you already know, written over the business objects. Text in, the checked query out, and back.

    SELECT c.客户名称, sum(o.金额) AS 合计
    FROM (o:订单)-[:订单属于客户]->(c:客户)
    WHERE o.状态码 <> '已取消'
    GROUP BY c.客户名称
    ORDER BY 合计 DESC
    LIMIT 3

There is no second engine. `compile_query` turns the text into the structured query Q&A already runs (ontology_questions.run_query: start, where, via,
group_by, share, measure, top, order), and workspace_questions.run_text runs it through the same scope as a question: the types, properties and rows this
person may read, the confirmed meanings, views and relations. `to_text` writes a structured query (one the model wrote, one saved with an answer) back as
text, so either form can be read and edited.

What it adds over the JSON is the reading, and the refusals, said in words before anything is counted:
  - a relation is named, never joined by hand; an unknown one is refused with the relations that type has;
  - a node the query does not use is refused rather than dropped: in SQL an inner join to it would quietly leave rows out;
  - a range (>, <, BETWEEN), an OR, a filter on an object that is not the one counted, two numbers at once: each is refused naming what is missing,
    because the checked query cannot say it yet (rather than being read as something it is not);
  - a type or property this person may not see is "not there", in the same words as one that does not exist.

`catalog` is {'types': {key: {'name', 'properties': [column, ...]}}, 'relations': {key: {'name', 'from', 'to'}}}: what this person may see
(workspace_questions.query_catalog). `$name` in a value is a parameter: it is filled from `params` as a value, never as text.
"""
from __future__ import annotations

import re

AGGREGATES = {'count': 'count', 'sum': 'sum', 'avg': 'average', 'average': 'average', 'share': 'share'}
ALIASES = {'count': '数量', 'sum': '合计', 'average': '平均', 'share': '占比'}
BUCKETS = ('month', 'year')   # GROUP BY month(o.下单日期): a date read as its month or its year
COMPARE = {'>': 'more_than', '>=': 'at_least', '<': 'less_than', '<=': 'at_most'}
KEYWORDS = {'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'GROUP', 'BY', 'ORDER', 'ASC', 'DESC', 'LIMIT', 'AS', 'IN', 'NOT', 'BETWEEN', 'LIKE', 'IS', 'NULL', 'JOIN', 'ON', 'HAVING'}
MAX_TEXT = 4000
QUERY_KEYS = ('start', 'where', 'via', 'group_by', 'share', 'measure', 'top', 'order')
_TOKEN = re.compile(r"""
    (?P<space>\s+|--[^\n]*)
  | (?P<string>'(?:[^']|'')*')
  | (?P<quoted>`[^`]+`)
  | (?P<number>-?\d+(?:\.\d+)?(?![\w一-鿿]))
  | (?P<param>\$[A-Za-z_一-鿿][\w一-鿿]*)
  | (?P<op>->|<-|<>|!=|>=|<=|[(),.:\[\]\-=*<>])
  | (?P<word>[A-Za-z_㐀-鿿豈-﫿][\w㐀-鿿豈-﫿]*)
""", re.VERBOSE)


class QueryError(ValueError):
    """The text cannot be read or cannot be run as written: str() says why in Chinese, `at` is where (a character offset) when it is about one place."""

    def __init__(self, message: str, at: int | None = None):
        super().__init__(message)
        self.at = at


# --- reading the text --------------------------------------------------------------------------------------------------------------------------------

def _tokens(text: str) -> list[tuple[str, str, int]]:
    out, i = [], 0
    while i < len(text):
        m = _TOKEN.match(text, i)
        if m is None:
            raise QueryError(f'第 {i + 1} 个字“{text[i]}”读不懂', i)
        kind = m.lastgroup
        if kind != 'space':
            value = m.group()
            if kind == 'string':
                value = value[1:-1].replace("''", "'")
            elif kind == 'quoted':
                kind, value = 'name', value[1:-1]
            elif kind == 'word':
                kind, value = ('kw', value.upper()) if value.upper() in KEYWORDS else ('name', value)
            out.append((kind, value, i))
        i = m.end()
    out.append(('end', '', len(text)))
    return out


class _Reader:
    def __init__(self, text: str, params: dict | None):
        self.text, self.tokens, self.i, self.params = text, _tokens(text), 0, params or {}

    def peek(self, kind=None, value=None, ahead=0) -> bool:
        k, v, _ = self.tokens[min(self.i + ahead, len(self.tokens) - 1)]
        return (kind is None or k == kind) and (value is None or v == value)

    def at(self) -> int:
        return self.tokens[self.i][2]

    def take(self, kind=None, value=None, what=None):
        k, v, at = self.tokens[self.i]
        if (kind and k != kind) or (value and v != value):
            seen = '结尾' if k == 'end' else f'“{v}”'
            raise QueryError(f'第 {at + 1} 个字附近应该是 {what or value or kind}，这里是{seen}', at)
        self.i += 1
        return v

    def name(self, what: str) -> str:
        """A name; a keyword stands for itself where only a name can be (a type keyed `order`)."""
        k, v, at = self.tokens[self.i]
        if k == 'kw':
            self.i += 1
            return self.text[at:at + len(v)]
        return self.take('name', what=what)

    def value(self):
        k, v, at = self.tokens[self.i]
        if k in ('string', 'number'):
            self.i += 1
            if k == 'number' and self.tokens[self.i][0] == 'number' and self.tokens[self.i][1].startswith('-'):   # 2026-01-01 read as 2026, -01, -01
                raise QueryError(f'第 {at + 1} 个字附近：日期要加引号，例如 \'2026-01-01\'', at)
            return v
        if k == 'param':
            self.i += 1
            if v[1:] not in self.params:
                raise QueryError(f'缺少参数 {v}：调用时在 params 里给它一个值，例如 "params": {{"{v[1:]}": "…"}}', at)
            given = self.params[v[1:]]
            if isinstance(given, bool) or not isinstance(given, (str, int, float)):
                raise QueryError(f'参数 {v} 要是一个文字或数字', at)
            return given if isinstance(given, str) else format(given, 'g') if isinstance(given, float) else str(given)
        raise QueryError(f'第 {at + 1} 个字附近应该是一个值（\'文字\'、数字或 $参数）', at)


def _ref(r: _Reader) -> tuple[str, str]:
    var = r.name('对象的简称，例如 o')
    r.take('op', '.', '“.”，写成 简称.属性，例如 o.金额')
    return var, r.name('属性名')


def _group_ref(r: _Reader) -> tuple[str, str, str | None]:
    """o.城市, or month(o.下单日期) / year(o.下单日期): (var, property, 'month' | 'year' | None)."""
    if r.peek('name') and r.peek('op', '(', 1):
        at, fn = r.at(), r.take().lower()
        if fn not in BUCKETS:
            raise QueryError(f'不认识的函数 {fn}：要算的数用 count、sum、avg、share，日期可以按 month 或 year 分组', at)
        r.take('op', '(')
        var, prop = _ref(r)
        r.take('op', ')')
        return var, prop, fn
    return (*_ref(r), None)


def _select_item(r: _Reader) -> dict:
    at = r.at()
    if r.peek('name') and r.tokens[r.i][1].lower() in AGGREGATES and r.peek('op', '(', 1):
        fn = AGGREGATES[r.take().lower()]
        r.take('op', '(')
        if fn == 'count':
            if r.peek('op', '*'):
                r.take()
                item = {'kind': 'agg', 'fn': 'count', 'var': None}
            else:
                item = {'kind': 'agg', 'fn': 'count', 'var': r.name('要数的对象的简称，例如 count(o)')}
                if r.peek('op', '.'):
                    raise QueryError('count 数的是对象：写 count(o) 或 count(*)，不是 count(o.属性)', at)
        elif fn == 'share':
            var, prop = _ref(r)
            r.take('op', '=', '“=”：share(o.属性 = \'值\') 算等于这个值的对象占多少')
            item = {'kind': 'agg', 'fn': 'share', 'var': var, 'prop': prop, 'value': r.value()}
        else:
            var, prop = _ref(r)
            item = {'kind': 'agg', 'fn': fn, 'var': var, 'prop': prop}
        r.take('op', ')')
    else:
        var, prop, by = _group_ref(r)
        item = {'kind': 'field', 'var': var, 'prop': prop, 'by': by}
    if r.peek('kw', 'AS'):
        r.take()
        item['alias'] = r.name('别名')
    item['at'] = at
    return item


def _node(r: _Reader) -> dict:
    at = r.at()
    r.take('op', '(', '“(”：节点写成 (简称:对象类型)，例如 (o:订单)')
    var = r.name('对象的简称')
    kind = None
    if r.peek('op', ':'):
        r.take()
        kind = r.name('对象类型')
    r.take('op', ')')
    return {'var': var, 'type': kind, 'at': at}


def _edge(r: _Reader) -> dict:
    """-[:r]->, <-[:r]- or -[:r]-: (relation name, 'out' | 'in' | 'any')."""
    at = r.at()
    back = r.peek('op', '<-')
    r.take('op', '<-' if back else '-', '关系，写成 -[:关系]-> 或 <-[:关系]-')
    r.take('op', '[')
    r.take('op', ':', '“:”，关系写成 [:关系名]')
    name = r.name('关系名')
    r.take('op', ']')
    if back:
        r.take('op', '-')
        return {'relation': name, 'dir': 'in', 'at': at}
    if r.peek('op', '->'):
        r.take()
        return {'relation': name, 'dir': 'out', 'at': at}
    r.take('op', '-', '“->” 或 “-”')
    return {'relation': name, 'dir': 'any', 'at': at}


def _condition(r: _Reader) -> dict:
    at = r.at()
    var, prop = _ref(r)
    if r.peek('op', '='):
        r.take()
        return {'var': var, 'prop': prop, 'not': False, 'values': [r.value()], 'at': at}
    if r.peek('op', '<>') or r.peek('op', '!='):
        r.take()
        return {'var': var, 'prop': prop, 'not': True, 'values': [r.value()], 'at': at}
    if r.tokens[r.i][1] in COMPARE and r.tokens[r.i][0] == 'op':
        op = r.take()
        return {'var': var, 'prop': prop, 'range': {COMPARE[op]: r.value()}, 'at': at}
    if r.peek('kw', 'BETWEEN'):
        r.take()
        low = r.value()
        r.take('kw', 'AND', 'AND：BETWEEN 下限 AND 上限')
        return {'var': var, 'prop': prop, 'range': {'at_least': low, 'at_most': r.value()}, 'at': at}
    negated = r.peek('kw', 'NOT')
    if negated:
        r.take()
    if r.peek('kw', 'IN'):
        r.take()
        r.take('op', '(')
        values = [r.value()]
        while r.peek('op', ','):
            r.take()
            values.append(r.value())
        r.take('op', ')')
        return {'var': var, 'prop': prop, 'not': negated, 'values': values, 'at': at}
    k, v, here = r.tokens[r.i]
    if v in ('LIKE', 'IS'):
        raise QueryError(f'{var}.{prop} 用了 {v}：{"模糊匹配" if v == "LIKE" else "空值判断"}还不支持；能写 =、<>、IN、NOT IN、>、>=、<、<=、BETWEEN', here)
    raise QueryError(f'第 {here + 1} 个字附近应该是 =、<>、IN、NOT IN、>、>=、<、<= 或 BETWEEN', here)


def parse(text: str, params: dict | None = None) -> dict:
    """The text as its parts (no names are looked up yet): select, chains, where, group, order, limit."""
    if not isinstance(text, str) or not text.strip():
        raise QueryError('请写一条查询，例如 SELECT count(o) FROM (o:订单)')
    if len(text) > MAX_TEXT:
        raise QueryError(f'一条查询最多 {MAX_TEXT} 个字')
    r = _Reader(text, params)
    r.take('kw', 'SELECT', 'SELECT')
    select = [_select_item(r)]
    while r.peek('op', ','):
        r.take()
        select.append(_select_item(r))
    r.take('kw', 'FROM', 'FROM')
    chains = []
    while True:
        chain = [_node(r)]
        while r.peek('op', '-') or r.peek('op', '<-'):
            chain += [_edge(r), _node(r)]
        chains.append(chain)
        if not r.peek('op', ','):
            break
        r.take()
    if r.peek('kw', 'JOIN'):
        raise QueryError('这里不写 JOIN：在 FROM 里沿关系走，例如 FROM (o:订单)-[:订单属于客户]->(c:客户)', r.at())
    where = []
    if r.peek('kw', 'WHERE'):
        r.take()
        where.append(_condition(r))
        while r.peek('kw', 'AND'):
            r.take()
            where.append(_condition(r))
        if r.peek('kw', 'OR'):
            raise QueryError('现在只能用 AND 连起几个条件；OR 还不支持（同一个属性的几个值可以写 IN）', r.at())
    group = []
    if r.peek('kw', 'GROUP'):
        r.take()
        r.take('kw', 'BY', 'BY')
        group.append(dict(zip(('var', 'prop', 'by'), _group_ref(r))))
        while r.peek('op', ','):
            r.take()
            group.append(dict(zip(('var', 'prop', 'by'), _group_ref(r))))
    if r.peek('kw', 'HAVING'):
        raise QueryError('HAVING 还不支持：要“前几名”或“最少的几个”，用 ORDER BY 和 LIMIT', r.at())
    order = None
    if r.peek('kw', 'ORDER'):
        at = r.at()
        r.take()
        r.take('kw', 'BY', 'BY')
        if r.peek('name') and r.peek('op', '(', 1):
            target = _select_item(r)
            target.pop('alias', None)
        elif r.peek('name') and r.peek('op', '.', 1):
            target = {'kind': 'field', **dict(zip(('var', 'prop'), _ref(r)))}
        else:
            target = {'kind': 'alias', 'name': r.name('要排序的数（它的别名或写法）')}
        direction = 'smallest'
        if r.peek('kw', 'DESC') or r.peek('kw', 'ASC'):
            direction = 'largest' if r.take() == 'DESC' else 'smallest'
        order = {'target': target, 'direction': direction, 'at': at}
    limit = None
    if r.peek('kw', 'LIMIT'):
        at = r.at()
        r.take()
        k, v, _ = r.tokens[r.i]
        if k != 'number' or not v.isdigit() or int(v) < 1:
            raise QueryError('LIMIT 后面写一个大于 0 的整数', at)
        r.take()
        limit = {'n': int(v), 'at': at}
    if not r.peek('end'):
        k, v, at = r.tokens[r.i]
        raise QueryError(f'第 {at + 1} 个字附近的“{v}”多出来了，或者这个位置还不支持它', at)
    return {'select': select, 'chains': chains, 'where': where, 'group': group, 'order': order, 'limit': limit}


# --- names, against what this person may see ---------------------------------------------------------------------------------------------------------

def _named(table: dict, written: str) -> str | None:
    """The key whose key or name is `written` (a key first: names may repeat)."""
    if written in table:
        return written
    return next((k for k, v in table.items() if v.get('name') == written), None)


def _type_name(catalog: dict, key: str) -> str:
    return catalog['types'][key].get('name') or key


def _relation_line(catalog: dict, key: str) -> str:
    r = catalog['relations'][key]
    return f'{r.get("name") or key}（{_type_name(catalog, r["from"])}→{_type_name(catalog, r["to"])}）'


def _no_type(catalog: dict, written: str, at) -> QueryError:
    known = '、'.join(_type_name(catalog, k) for k in catalog['types']) or '（还没有）'
    return QueryError(f'没有对象类型「{written}」。你能查的对象类型：{known}', at)


def _no_property(catalog: dict, key: str, prop: str, at) -> QueryError:
    props = catalog['types'][key]['properties']
    return QueryError(f'{_type_name(catalog, key)} 没有属性「{prop}」。它的属性：{"、".join(props) or "（没有）"}', at)


def _bind(catalog: dict, parsed: dict) -> tuple[dict, list[tuple[str, str, str]]]:
    """({var: type key}, [(var, var, relation key)] as walked in either direction): the pattern checked against the catalog."""
    types, edges = {}, []
    for chain in parsed['chains']:
        for node in chain[0::2]:
            if node['type'] is None:
                if node['var'] not in types:
                    raise QueryError(f'({node["var"]}) 前面没有写过它是什么对象：第一次出现时写成 ({node["var"]}:对象类型)', node['at'])
                continue
            key = _named(catalog['types'], node['type'])
            if key is None:
                raise _no_type(catalog, node['type'], node['at'])
            if types.get(node['var'], key) != key:
                raise QueryError(f'简称 {node["var"]} 已经是 {_type_name(catalog, types[node["var"]])}，不能再当 {node["type"]}', node['at'])
            types[node['var']] = key
        for left, edge, right in zip(chain[0::2], chain[1::2], chain[2::2]):
            a, b = types[left['var']], types[right['var']]
            key = _named(catalog['relations'], edge['relation'])
            touching = [k for k, r in catalog['relations'].items() if a in (r['from'], r['to'])]
            if key is None or a not in (catalog['relations'][key]['from'], catalog['relations'][key]['to']):
                said = '没有关系' if key is None else f'关系「{edge["relation"]}」不连着 {_type_name(catalog, a)}：'
                listed = '、'.join(_relation_line(catalog, k) for k in touching) or '（没有）'
                raise QueryError(f'{said}「{edge["relation"]}」。{_type_name(catalog, a)} 能走的关系：{listed}' if key is None
                                 else f'{said}{_type_name(catalog, a)} 能走的关系：{listed}', edge['at'])
            r = catalog['relations'][key]
            ends = {'out': (a, b), 'in': (b, a)}.get(edge['dir'])
            fits = (r['from'], r['to']) == ends if ends else {r['from'], r['to']} == {a, b}
            if not fits:
                raise QueryError(f'关系「{r.get("name") or key}」是从 {_type_name(catalog, r["from"])} 到 {_type_name(catalog, r["to"])}，'
                                 f'这里写的是 {_type_name(catalog, a)} {"→" if edge["dir"] != "in" else "←"} {_type_name(catalog, b)}', edge['at'])
            if left['var'] == right['var']:
                raise QueryError('一条关系的两头要是两个不同的简称', edge['at'])
            edges.append((left['var'], right['var'], key))
    return types, edges


def _paths(start: str, edges: list) -> dict[str, list[str]]:
    """{var: [relation keys from start to it]} over the pattern, which must be a tree (one way from start to each node)."""
    out, todo = {start: []}, [start]
    seen_edges = set()
    while todo:
        here = todo.pop(0)
        for i, (a, b, key) in enumerate(edges):
            if here in (a, b) and i not in seen_edges:
                seen_edges.add(i)
                other = b if here == a else a
                if other in out:
                    raise QueryError(f'从 {start} 到 {other} 有两条路：一个节点只能从一条路走到')
                out[other] = [*out[here], key]
                todo.append(other)
    return out


def compile_query(text: str, catalog: dict, params: dict | None = None) -> dict:
    """The checked query the text says, with every key (see QUERY_KEYS), or QueryError saying what cannot be said and why."""
    parsed = parse(text, params)
    types, edges = _bind(catalog, parsed)

    def prop_of(var, prop, at=None):
        if var not in types:
            raise QueryError(f'简称 {var} 没有在 FROM 里出现', at)
        if prop not in catalog['types'][types[var]]['properties']:
            raise _no_property(catalog, types[var], prop, at)
        return prop

    aggs = [s for s in parsed['select'] if s['kind'] == 'agg']
    fields = [s for s in parsed['select'] if s['kind'] == 'field']
    if len(aggs) != 1:
        raise QueryError('SELECT 里要有且只有一个要算的数：count(o)、sum(o.金额)、avg(o.金额) 或 share(o.状态码 = \'已取消\')。'
                         + ('一次算两个数还不支持，分成两条查询' if aggs else ''), parsed['select'][0]['at'])
    agg = aggs[0]
    first = parsed['chains'][0][0]['var']
    counted = agg['var'] or first
    if counted not in types:
        raise QueryError(f'简称 {counted} 没有在 FROM 里出现', agg['at'])
    group = parsed['group']
    for v in [g['var'] for g in group] + [f['var'] for f in fields]:
        if v not in types:
            raise QueryError(f'简称 {v} 没有在 FROM 里出现')
    grouped = {(g['var'], g['prop'], g.get('by')) for g in group}
    for f in fields:
        if (f['var'], f['prop'], f.get('by')) not in grouped:
            shown = f'{f["by"]}({f["var"]}.{f["prop"]})' if f.get('by') else f'{f["var"]}.{f["prop"]}'
            raise QueryError(f'{shown} 在 SELECT 里，也要写进 GROUP BY（和 SQL 一样，写法也要一样）', f['at'])
    filtered = {c['var'] for c in parsed['where']}
    group = parsed['group']
    if agg['fn'] == 'count' and not group and len(filtered) == 1 and filtered != {counted}:
        start = next(iter(filtered))   # "the customers of the cancelled orders": filter the orders, count the customers they reach
    else:
        start = counted
    for c in parsed['where']:
        if c['var'] not in types:
            raise QueryError(f'简称 {c["var"]} 没有在 FROM 里出现', c['at'])
        if c['var'] != start:
            raise QueryError(f'条件只能写在被数或被算的对象（{start}）上；{c["var"]}.{c["prop"]} 是 {_type_name(catalog, types[c["var"]])} 的属性。'
                             f'跨对象的条件还不支持', c['at'])
    paths = _paths(start, edges)
    unreached = [v for v in types if v not in paths]
    if unreached:
        raise QueryError(f'{"、".join(unreached)} 和 {start} 没有连在一起：FROM 里的节点要沿关系连成一片')
    used = {start, *(g['var'] for g in group), *([counted] if counted != start else [])}
    needed = {v for u in used for v in types if paths[v] == paths[u][:len(paths[v])]}   # every node on the way from start to a used one
    idle = [v for v in types if v not in needed]
    if idle:
        raise QueryError(f'{"、".join(f"({v}:{_type_name(catalog, types[v])})" for v in idle)} 没有用到。'
                         f'SQL 里多连一张表会悄悄去掉连不上的行，这里不会，所以请删掉它，或者按它分组')
    where = []
    for c in parsed['where']:
        prop = prop_of(c['var'], c['prop'], c['at'])
        if 'range' in c:
            where.append({'field': prop, **{k: str(v) for k, v in c['range'].items()}})
            continue
        values = list(dict.fromkeys(str(v) for v in c['values']))
        if not c['not'] and len(values) > 1:
            raise QueryError(f'{c["var"]}.{prop} IN 几个值还不支持（“不在这几个值里”可以写 NOT IN）；分成几条查询，或者确认一个视图', c['at'])
        where.append({'field': prop, 'not_equals': values[0] if len(values) == 1 else values} if c['not'] else {'field': prop, 'equals': values[0]})
    group_by = []
    for g in group:
        if g['var'] not in types:
            raise QueryError(f'简称 {g["var"]} 没有在 FROM 里出现')
        group_by.append({'via': paths[g['var']], 'field': prop_of(g['var'], g['prop']), **({'by': g['by']} if g.get('by') else {})})
    measure = share = None
    if agg['fn'] in ('sum', 'average'):
        measure = {'field': prop_of(agg['var'], agg['prop'], agg['at']), 'op': agg['fn']}
    elif agg['fn'] == 'share':
        share = {'field': prop_of(agg['var'], agg['prop'], agg['at']), 'equals': str(agg['value'])}
    order, top = None, None
    if parsed['order']:
        o = parsed['order']
        t = o['target']
        same = (t['kind'] == 'alias' and t['name'] == agg.get('alias', ALIASES[agg['fn']])) or \
               (t['kind'] == 'agg' and all(t.get(k) == agg.get(k) for k in ('fn', 'var', 'prop', 'value')))
        if not same:
            raise QueryError('ORDER BY 现在只能按算出来的那个数排（写它的别名，或者再写一遍 sum(o.金额) 这样的写法）', o['at'])
        if not group:
            raise QueryError('ORDER BY 要和 GROUP BY 一起用：没有分组，就没有可以排的组', o['at'])
        order = o['direction']
    if parsed['limit']:
        if not group:
            raise QueryError('LIMIT 要和 GROUP BY 一起用：它留下排在前面的几组', parsed['limit']['at'])
        top = parsed['limit']['n']
    via = paths[counted] if counted != start else []
    return {'start': types[start], 'where': where, 'via': via, 'group_by': group_by or None, 'share': share, 'measure': measure, 'top': top, 'order': order}


# --- writing it back -----------------------------------------------------------------------------------------------------------------------------------

def canonical(query: dict) -> dict:
    """A structured query with every key, in the shape compile_query returns (group_by as dimensions, empty parts as None or [])."""
    q = {k: query.get(k) for k in QUERY_KEYS}
    q['where'] = list(q['where'] or [])
    q['via'] = list(q['via'] or [])
    gb = q['group_by']
    if isinstance(gb, str):
        gb = [{'via': q['via'], 'field': gb}]
        q['via'] = []
    q['group_by'] = [{'via': list(d.get('via') or []), 'field': d['field'], **({'by': d['by']} if d.get('by') else {})} for d in gb] if gb else None
    return q


def _ident(name: str) -> str:
    return name if re.fullmatch(r'[A-Za-z_㐀-鿿豈-﫿][\w㐀-鿿豈-﫿]*', name) and name.upper() not in KEYWORDS else f'`{name}`'


def _literal(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _shown_name(table: dict, key: str) -> str:
    """The name to write: the label when no other entry has it, else the key."""
    name = table[key].get('name') or key
    return name if sum(1 for v in table.values() if (v.get('name') or None) == name) == 1 and name not in table else key


def to_text(query: dict, catalog: dict) -> str:
    """The structured query as OntoPoc Query text (compile_query of it gives canonical(query) back). QueryError when it names what the catalog lacks."""
    q = canonical(query)
    if q['start'] not in catalog['types']:
        raise _no_type(catalog, str(q['start']), None)
    used_letters: dict[str, int] = {}

    def letter(key):
        base = key[0].lower() if key[:1].isascii() and key[:1].isalpha() else 't'
        used_letters[base] = used_letters.get(base, 0) + 1
        return base if used_letters[base] == 1 else f'{base}{used_letters[base]}'

    start_var = letter(q['start'])
    node_of = {(): start_var}
    type_of = {(): q['start']}
    chains: list[str] = []

    def walk(via):
        """The variable at the end of `via` from start, adding the steps to the pattern."""
        for i in range(1, len(via) + 1):
            path, key = tuple(via[:i]), via[i - 1]
            if path in node_of:
                continue
            if key not in catalog['relations']:
                raise QueryError(f'没有关系「{key}」')
            r, here = catalog['relations'][key], type_of[path[:-1]]
            if here not in (r['from'], r['to']):
                raise QueryError(f'关系「{key}」不连着 {_type_name(catalog, here)}')
            there = r['to'] if r['from'] == here else r['from']
            var = letter(there)
            node_of[path], type_of[path] = var, there
            arrow = f'-[:{_ident(_shown_name(catalog["relations"], key))}]->' if r['from'] == here else f'<-[:{_ident(_shown_name(catalog["relations"], key))}]-'
            prev = node_of[path[:-1]]
            if chains and chains[-1].endswith(f'({prev})') or (chains and chains[-1].endswith(f':{_ident(_shown_name(catalog["types"], here))})') and chains[-1].rsplit('(', 1)[1].startswith(prev + ':')):
                chains[-1] += f'{arrow}({var}:{_ident(_shown_name(catalog["types"], there))})'
            else:
                chains.append(f'({prev}){arrow}({var}:{_ident(_shown_name(catalog["types"], there))})')
        return node_of[tuple(via)]

    head = f'({start_var}:{_ident(_shown_name(catalog["types"], q["start"]))})'
    chains.append(head)
    dims = [(walk(d['via']), d['field'], d.get('by')) for d in q['group_by'] or []]
    dim_text = lambda v, f, by: f'{by}({v}.{_ident(f)})' if by else f'{v}.{_ident(f)}'
    counted = walk(q['via']) if q['via'] else start_var
    if chains[0] == head and len(chains) > 1 and chains[1].startswith(f'({start_var})'):
        chains[0] = head + chains.pop(1)[len(f'({start_var})'):]
    m, s = q['measure'], q['share']
    if m:
        fn = {'sum': 'sum', 'average': 'avg'}.get(m.get('op'))
        if fn is None:
            raise QueryError(f'不支持的算法 {m.get("op")}')
        field = m.get('field') or m.get('derived')
        if not isinstance(field, str) or not field:
            raise QueryError('求和、求平均没有写字段')
        agg, alias = f'{fn}({start_var}.{_ident(str(field))})', ALIASES[m['op']]
    elif s:
        if not isinstance(s.get('field'), str) or 'equals' not in s:
            raise QueryError('占比要写字段和它等于的值')
        agg, alias = f'share({start_var}.{_ident(str(s["field"]))} = {_literal(s["equals"])})', ALIASES['share']
    else:
        agg, alias = f'count({counted})', ALIASES['count']
    lines = [f'SELECT {", ".join([*(dim_text(*d) for d in dims), f"{agg} AS {alias}"])}', f'FROM {", ".join(chains)}']
    conds = []
    bound = lambda v: str(v) if re.fullmatch(r'-?\d+(\.\d+)?', str(v)) else _literal(v)
    for w in q['where']:
        ranged = [k for k in COMPARE.values() if isinstance(w, dict) and k in w]
        if not isinstance(w, dict) or not isinstance(w.get('field'), str) or not ('equals' in w or 'not_equals' in w or ranged):
            raise QueryError('筛选要写成“某个字段等于（或不等于）某个值”，或一个范围')
        f = f'{start_var}.{_ident(str(w["field"]))}'
        if ranged:
            if set(ranged) == {'at_least', 'at_most'}:
                conds.append(f'{f} BETWEEN {bound(w["at_least"])} AND {bound(w["at_most"])}')
            else:
                conds += [f'{f} {op} {bound(w[k])}' for op, k in COMPARE.items() if k in w]
            continue
        if 'not_equals' in w:
            v = w['not_equals']
            if v in ([], None, ''):
                raise QueryError('“不等于”后面要写一个值，或一个值的列表')
            conds.append(f'{f} NOT IN ({", ".join(map(_literal, v))})' if isinstance(v, list) and len(v) != 1 else f'{f} <> {_literal(v[0] if isinstance(v, list) else v)}')
        else:
            conds.append(f'{f} = {_literal(w.get("equals"))}')
    if conds:
        lines.append('WHERE ' + '\n  AND '.join(conds))
    if dims:
        lines.append('GROUP BY ' + ', '.join(dim_text(*d) for d in dims))
    if q['order']:
        lines.append(f'ORDER BY {alias} {"DESC" if q["order"] == "largest" else "ASC"}')
    if q['top']:
        lines.append(f'LIMIT {q["top"]}')
    return '\n'.join(lines)
