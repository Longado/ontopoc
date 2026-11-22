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
SAY = None   # the host sets this to lang.tr so a message comes in the asker's language; this file imports nothing from ontopoc, and on its own says the Chinese


def tr(zh, en):
    return SAY(zh, en) if SAY else zh


ALIASES = {'count': '数量', 'sum': '合计', 'average': '平均', 'share': '占比'}
ALIASES_EN = {'count': 'count', 'sum': 'total', 'average': 'average', 'share': 'share'}   # the name a number gets when the query does not give one, for an English asker


def _alias(fn):
    return tr(ALIASES[fn], ALIASES_EN[fn])
BUCKETS = ('month', 'year')   # GROUP BY month(o.下单日期): a date read as its month or its year
COMPARE = {'>': 'more_than', '>=': 'at_least', '<': 'less_than', '<=': 'at_most'}
KEYWORDS = {'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'GROUP', 'BY', 'ORDER', 'ASC', 'DESC', 'LIMIT', 'AS', 'IN', 'NOT', 'BETWEEN', 'LIKE', 'IS', 'NULL', 'JOIN', 'ON', 'HAVING'}
MAX_TEXT = 4000
MAX_GRAPH = 100   # start objects a SELECT GRAPH may draw: a picture of more is not read, it is counted
MAX_LIST = 50   # objects one page of a SELECT LIST shows at most: LIMIT n sets a smaller page, a larger one is refused
TODAY = 'today'   # a range bound that is the date of the day the query runs (with `rows`): the host puts the date in and says which one it used
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
            raise QueryError(tr(f'第 {i + 1} 个字“{text[i]}”读不懂', f'Cannot read character {i + 1}, "{text[i]}"'), i)
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
            seen = tr('结尾', 'the end') if k == 'end' else tr(f'“{v}”', f'"{v}"')
            raise QueryError(tr(f'第 {at + 1} 个字附近应该是 {what or value or kind}，这里是{seen}', f'Expected {what or value or kind} near character {at + 1}, found {seen}'), at)
        self.i += 1
        return v

    def name(self, what: str) -> str:
        """A name; a keyword stands for itself where only a name can be (a type keyed `order`)."""
        k, v, at = self.tokens[self.i]
        if k == 'kw':
            self.i += 1
            return self.text[at:at + len(v)]
        return self.take('name', what=what)

    def value(self, today: bool = False):
        """A value: 'text', a number or a $parameter; with `today`, also the word today (a range bound)."""
        k, v, at = self.tokens[self.i]
        if today and k == 'name' and v.lower() == TODAY:
            self.i += 1
            return TODAY
        if k in ('string', 'number'):
            self.i += 1
            if k == 'number' and self.tokens[self.i][0] == 'number' and self.tokens[self.i][1].startswith('-'):   # 2026-01-01 read as 2026, -01, -01
                raise QueryError(tr(f'第 {at + 1} 个字附近：日期要加引号，例如 \'2026-01-01\'', f"Near character {at + 1}: a date needs quotes, for example '2026-01-01'"), at)
            return v
        if k == 'param':
            self.i += 1
            if v[1:] not in self.params:
                raise QueryError(tr(f'缺少参数 {v}：调用时在 params 里给它一个值，例如 "params": {{"{v[1:]}": "…"}}', f'Missing parameter {v}: give it a value in params, for example "params": {{"{v[1:]}": "..."}}'), at)
            given = self.params[v[1:]]
            if isinstance(given, bool) or not isinstance(given, (str, int, float)):
                raise QueryError(tr(f'参数 {v} 要是一个文字或数字', f'Parameter {v} must be text or a number'), at)
            return given if isinstance(given, str) else format(given, 'g') if isinstance(given, float) else str(given)
        raise QueryError(tr(f'第 {at + 1} 个字附近应该是一个值（\'文字\'、数字或 $参数）', f"Expected a value near character {at + 1} ('text', a number or a $parameter)"), at)


def _ref(r: _Reader) -> tuple[str, str]:
    var = r.name(tr('对象的简称，例如 o', 'a short name for the object, for example o'))
    r.take('op', '.', tr('“.”，写成 简称.属性，例如 o.金额', '".", written short name.property, for example o.amount'))
    return var, r.name(tr('属性名', 'a property name'))


def _group_ref(r: _Reader) -> tuple[str, str, str | None]:
    """o.城市, or month(o.下单日期) / year(o.下单日期): (var, property, 'month' | 'year' | None)."""
    if r.peek('name') and r.peek('op', '(', 1):
        at, fn = r.at(), r.take().lower()
        if fn not in BUCKETS:
            raise QueryError(tr(f'不认识的函数 {fn}：要算的数用 count、sum、avg、share，日期可以按 month 或 year 分组', f'Unknown function {fn}: use count, sum, avg or share to calculate, and group dates by month or year'), at)
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
                item = {'kind': 'agg', 'fn': 'count', 'var': r.name(tr('要数的对象的简称，例如 count(o)', 'the short name of the object to count, for example count(o)'))}
                if r.peek('op', '.'):
                    raise QueryError(tr('count 数的是对象：写 count(o) 或 count(*)，不是 count(o.属性)', 'count counts objects: write count(o) or count(*), not count(o.property)'), at)
        elif fn == 'share':
            var, prop = _ref(r)
            r.take('op', '=', tr('“=”：share(o.属性 = \'值\') 算等于这个值的对象占多少', "\"=\": share(o.property = 'value') gives the share of objects equal to that value"))
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
        item['alias'] = r.name(tr('别名', 'an alias'))
    item['at'] = at
    return item


def _node(r: _Reader) -> dict:
    at = r.at()
    r.take('op', '(', tr('“(”：节点写成 (简称:对象类型)，例如 (o:订单)', '"(": write a node as (short name:object type), for example (o:orders)'))
    var = r.name(tr('对象的简称', 'a short name for the object'))
    kind = None
    if r.peek('op', ':'):
        r.take()
        kind = r.name(tr('对象类型', 'an object type'))
    r.take('op', ')')
    return {'var': var, 'type': kind, 'at': at}


def _edge(r: _Reader) -> dict:
    """-[:r]->, <-[:r]- or -[:r]-: (relation name, 'out' | 'in' | 'any')."""
    at = r.at()
    back = r.peek('op', '<-')
    r.take('op', '<-' if back else '-', tr('关系，写成 -[:关系]-> 或 <-[:关系]-', 'a relation, written -[:relation]-> or <-[:relation]-'))
    r.take('op', '[')
    r.take('op', ':', tr('“:”，关系写成 [:关系名]', '":", a relation is written [:relation name]'))
    name = r.name(tr('关系名', 'a relation name'))
    r.take('op', ']')
    if back:
        r.take('op', '-')
        return {'relation': name, 'dir': 'in', 'at': at}
    if r.peek('op', '->'):
        r.take()
        return {'relation': name, 'dir': 'out', 'at': at}
    r.take('op', '-', tr('“->” 或 “-”', '"->" or "-"'))
    return {'relation': name, 'dir': 'any', 'at': at}


def _condition(r: _Reader, today: bool = False) -> dict:
    """One condition; `today`: a range bound may be the word today."""
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
        return {'var': var, 'prop': prop, 'range': {COMPARE[op]: r.value(today)}, 'at': at}
    if r.peek('kw', 'BETWEEN'):
        r.take()
        low = r.value(today)
        r.take('kw', 'AND', tr('AND：BETWEEN 下限 AND 上限', 'AND: BETWEEN lower AND upper'))
        return {'var': var, 'prop': prop, 'range': {'at_least': low, 'at_most': r.value(today)}, 'at': at}
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
        raise QueryError(tr(f'{var}.{prop} 用了 {v}：{"模糊匹配" if v == "LIKE" else "空值判断"}还不支持；能写 =、<>、IN、NOT IN、>、>=、<、<=、BETWEEN', f'{var}.{prop} uses {v}: {"fuzzy matching" if v == "LIKE" else "null checks"} are not supported yet. You can write =, <>, IN, NOT IN, >, >=, <, <=, BETWEEN'), here)
    raise QueryError(tr(f'第 {here + 1} 个字附近应该是 =、<>、IN、NOT IN、>、>=、<、<= 或 BETWEEN', f'Expected =, <>, IN, NOT IN, >, >=, <, <= or BETWEEN near character {here + 1}'), here)


def param_names(text: str) -> list[str]:
    """The $names a query uses, each once, in order of first use; none inside a quoted value or a comment. QueryError when the text cannot be read at all."""
    return list(dict.fromkeys(v[1:] for k, v, _ in _tokens(text) if k == 'param'))


def _rows_head(r: _Reader) -> dict | None:
    """SELECT LIST o, SELECT LIST o.p, o.q or SELECT ONE o: {'kind': 'list' | 'one', 'var', 'props': [(var, prop, at)], 'at'}; None when the text says neither."""
    if not (r.peek('name') and r.tokens[r.i][1].upper() in ('LIST', 'ONE') and (r.peek('name', ahead=1) or r.peek('kw', ahead=1)) and not r.peek('kw', 'FROM', 1)):
        return None
    at, kind = r.at(), r.take().lower()
    kind = 'list' if kind == 'list' else 'one'
    if kind == 'one' or not r.peek('op', '.', 1):
        var = r.name(tr('对象的简称，例如 SELECT LIST o', 'the short name of the objects, for example SELECT LIST o'))
        if r.peek('op', '.'):
            raise QueryError(tr('SELECT ONE 后面只写对象的简称，例如 SELECT ONE o：它给出这个对象全部能看的属性', 'Write only the short name after SELECT ONE, for example SELECT ONE o: it gives every property of the object you may see'), r.at())
        if r.peek('op', ','):
            raise QueryError(tr('只写 SELECT LIST o 就给主键和前 8 个属性；要指定属性，写 SELECT LIST o.属性, o.属性', 'SELECT LIST o alone gives the key and the first 8 properties; to name properties, write SELECT LIST o.property, o.property'), r.at())
        return {'kind': kind, 'var': var, 'props': [], 'at': at}
    props = []
    while True:
        here = r.at()
        var, prop = _ref(r)
        props.append((var, prop, here))
        if not r.peek('op', ','):
            break
        r.take()
    return {'kind': kind, 'var': props[0][0], 'props': props, 'at': at}


def parse(text: str, params: dict | None = None, rows: bool = False) -> dict:
    """The text as its parts (no names are looked up yet): select, chains, where, group, order, limit. `rows`: SELECT LIST, SELECT ONE and the range bound
    today are read too (without it they are read as before: not at all)."""
    if not isinstance(text, str) or not text.strip():
        raise QueryError(tr('请写一条查询，例如 SELECT count(o) FROM (o:订单)', 'Write a query, for example SELECT count(o) FROM (o:orders)'))
    if len(text) > MAX_TEXT:
        raise QueryError(tr(f'一条查询最多 {MAX_TEXT} 个字', f'A query can be at most {MAX_TEXT} characters'))
    r = _Reader(text, params)
    r.take('kw', 'SELECT', 'SELECT')
    listing = _rows_head(r) if rows else None
    if listing:
        return _parse_rows(r, listing)
    graph = r.peek('name') and r.tokens[r.i][1].upper() == 'GRAPH' and (r.peek('kw', 'FROM', 1) or r.peek('op', ',', 1))
    if graph:   # SELECT GRAPH: the objects and how they are related, not a number
        r.take()
        if r.peek('op', ','):
            raise QueryError(tr('SELECT GRAPH 后面直接写 FROM：一条查询要么画图，要么算一个数', 'Write FROM right after SELECT GRAPH: a query either draws a graph or calculates one number'), r.at())
        select = []
    else:
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
        raise QueryError(tr('这里不写 JOIN：在 FROM 里沿关系走，例如 FROM (o:订单)-[:订单属于客户]->(c:客户)', 'Do not write JOIN: follow relations in FROM, for example FROM (o:orders)-[:order_customer]->(c:customers)'), r.at())
    where = []
    if r.peek('kw', 'WHERE'):
        r.take()
        where.append(_condition(r, rows))
        while r.peek('kw', 'AND'):
            r.take()
            where.append(_condition(r, rows))
        if r.peek('kw', 'OR'):
            raise QueryError(tr('现在只能用 AND 连起几个条件；OR 还不支持（同一个属性的几个值可以写 IN）', 'Conditions can only be joined with AND; OR is not supported yet (several values of one property can be written with IN)'), r.at())
    group = []
    if graph and (r.peek('kw', 'GROUP') or r.peek('kw', 'ORDER')):
        word = 'GROUP BY' if r.peek('kw', 'GROUP') else 'ORDER BY'
        raise QueryError(tr(f'SELECT GRAPH 不写 {word}：它画出对象和它们之间的关系；要少画一些，用 LIMIT n 只留前 n 个起点对象', f'SELECT GRAPH does not take {word}: it draws objects and the relations between them. To draw fewer, use LIMIT n to keep only the first n start objects'), r.at())
    if r.peek('kw', 'GROUP'):
        r.take()
        r.take('kw', 'BY', 'BY')
        group.append(dict(zip(('var', 'prop', 'by'), _group_ref(r))))
        while r.peek('op', ','):
            r.take()
            group.append(dict(zip(('var', 'prop', 'by'), _group_ref(r))))
    if r.peek('kw', 'HAVING'):
        raise QueryError(tr('HAVING 还不支持：要“前几名”或“最少的几个”，用 ORDER BY 和 LIMIT', 'HAVING is not supported yet: for the top few or the fewest, use ORDER BY and LIMIT'), r.at())
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
            target = {'kind': 'alias', 'name': r.name(tr('要排序的数（它的别名或写法）', 'the number to sort by (its alias or how it is written)'))}
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
            raise QueryError(tr('LIMIT 后面写一个大于 0 的整数', 'Write a whole number greater than 0 after LIMIT'), at)
        r.take()
        limit = {'n': int(v), 'at': at}
        if graph and limit['n'] > MAX_GRAPH:
            raise QueryError(tr(f'SELECT GRAPH 最多画 {MAX_GRAPH} 个起点对象；要看总数，用 count()', f'SELECT GRAPH draws at most {MAX_GRAPH} start objects; for a total, use count()'), at)
    if not r.peek('end'):
        k, v, at = r.tokens[r.i]
        raise QueryError(tr(f'第 {at + 1} 个字附近的“{v}”多出来了，或者这个位置还不支持它', f'"{v}" near character {at + 1} is extra, or is not supported in this position'), at)
    return {'select': select, 'chains': chains, 'where': where, 'group': group, 'order': order, 'limit': limit, 'graph': bool(graph)}


def _parse_rows(r: _Reader, listing: dict) -> dict:
    """The rest of a SELECT LIST or SELECT ONE: FROM one node (no relation), WHERE conditions joined by AND (a range bound may be today), and for a list LIMIT n
    (the page size, at most MAX_LIST)."""
    word = 'SELECT LIST' if listing['kind'] == 'list' else 'SELECT ONE'
    r.take('kw', 'FROM', 'FROM')
    node = _node(r)
    if r.peek('op', '-') or r.peek('op', '<-') or r.peek('op', ','):
        raise QueryError(tr(f'{word} 列出的是一个对象类型自己的对象：FROM 里只写一个节点，例如 FROM (o:订单)，不沿关系走', f'{word} lists the objects of one object type: write one node in FROM, for example FROM (o:orders), and follow no relation'), r.at())
    if r.peek('kw', 'JOIN'):
        raise QueryError(tr('这里不写 JOIN：在 FROM 里沿关系走，例如 FROM (o:订单)-[:订单属于客户]->(c:客户)', 'Do not write JOIN: follow relations in FROM, for example FROM (o:orders)-[:order_customer]->(c:customers)'), r.at())
    where = []
    if r.peek('kw', 'WHERE'):
        r.take()
        where.append(_condition(r, today=True))
        while r.peek('kw', 'AND'):
            r.take()
            where.append(_condition(r, today=True))
        if r.peek('kw', 'OR'):
            raise QueryError(tr('现在只能用 AND 连起几个条件；OR 还不支持（同一个属性的几个值可以写 IN）', 'Conditions can only be joined with AND; OR is not supported yet (several values of one property can be written with IN)'), r.at())
    for word_kw in ('GROUP', 'ORDER', 'HAVING'):
        if r.peek('kw', word_kw):
            raise QueryError(tr(f'{word} 不分组、不排序：对象按主键排好，一页最多 {MAX_LIST} 个；要算数用 count()、sum()', f'{word} does not group or sort: the objects come in the order of their key, at most {MAX_LIST} a page; to calculate, use count() or sum()'), r.at())
    limit = None
    if r.peek('kw', 'LIMIT'):
        at = r.at()
        r.take()
        k, v, _ = r.tokens[r.i]
        if k != 'number' or not v.isdigit() or int(v) < 1:
            raise QueryError(tr('LIMIT 后面写一个大于 0 的整数', 'Write a whole number greater than 0 after LIMIT'), at)
        if listing['kind'] == 'one':
            raise QueryError(tr('SELECT ONE 只给一个对象，不写 LIMIT', 'SELECT ONE gives one object: do not write LIMIT'), at)
        if int(v) > MAX_LIST:
            raise QueryError(tr(f'一页最多列 {MAX_LIST} 个对象，LIMIT 写 1 到 {MAX_LIST}；后面的对象翻页看（page 2、3…），总数在 total 里', f'A page lists at most {MAX_LIST} objects: write LIMIT 1 to {MAX_LIST}. See the rest on the next pages (page 2, 3, ...); the total is in total'), at)
        r.take()
        limit = {'n': int(v), 'at': at}
    if not r.peek('end'):
        k, v, at = r.tokens[r.i]
        raise QueryError(tr(f'第 {at + 1} 个字附近的“{v}”多出来了，或者这个位置还不支持它', f'"{v}" near character {at + 1} is extra, or is not supported in this position'), at)
    return {'select': [], 'chains': [[node]], 'where': where, 'group': [], 'order': None, 'limit': limit, 'graph': False, 'rows': listing}


def is_graph(text) -> bool:
    """Does the text ask for a graph (SELECT GRAPH …)? False for anything that cannot be read."""
    try:
        tokens = _tokens(text) if isinstance(text, str) else []
    except QueryError:
        return False
    return len(tokens) > 2 and tokens[0][:2] == ('kw', 'SELECT') and tokens[1][0] == 'name' and tokens[1][1].upper() == 'GRAPH' and tokens[2][:2] in (('kw', 'FROM'), ('op', ','))


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
    return tr(f'{r.get("name") or key}（{_type_name(catalog, r["from"])}→{_type_name(catalog, r["to"])}）', f'{r.get("name") or key} ({_type_name(catalog, r["from"])}→{_type_name(catalog, r["to"])})')


def _no_type(catalog: dict, written: str, at) -> QueryError:
    known = tr('、', ', ').join(_type_name(catalog, k) for k in catalog['types']) or tr('（还没有）', '(none yet)')
    return QueryError(tr(f'没有对象类型「{written}」。你能查的对象类型：{known}', f'There is no object type "{written}". Object types you can query: {known}'), at)


def _no_property(catalog: dict, key: str, prop: str, at) -> QueryError:
    props = catalog['types'][key]['properties']
    return QueryError(tr(f'{_type_name(catalog, key)} 没有属性「{prop}」。它的属性：{"、".join(props) or "（没有）"}', f'{_type_name(catalog, key)} has no property "{prop}". Its properties: {", ".join(props) or "(none)"}'), at)


def _bind(catalog: dict, parsed: dict) -> tuple[dict, list[tuple[str, str, str]]]:
    """({var: type key}, [(var, var, relation key)] as walked in either direction): the pattern checked against the catalog."""
    types, edges = {}, []
    for chain in parsed['chains']:
        for node in chain[0::2]:
            if node['type'] is None:
                if node['var'] not in types:
                    raise QueryError(tr(f'({node["var"]}) 前面没有写过它是什么对象：第一次出现时写成 ({node["var"]}:对象类型)', f'({node["var"]}) has not been given an object type yet: the first time it appears, write ({node["var"]}:object type)'), node['at'])
                continue
            key = _named(catalog['types'], node['type'])
            if key is None:
                raise _no_type(catalog, node['type'], node['at'])
            if types.get(node['var'], key) != key:
                raise QueryError(tr(f'简称 {node["var"]} 已经是 {_type_name(catalog, types[node["var"]])}，不能再当 {node["type"]}', f'The short name {node["var"]} is already {_type_name(catalog, types[node["var"]])} and cannot also be {node["type"]}'), node['at'])
            types[node['var']] = key
        for left, edge, right in zip(chain[0::2], chain[1::2], chain[2::2]):
            a, b = types[left['var']], types[right['var']]
            key = _named(catalog['relations'], edge['relation'])
            touching = [k for k, r in catalog['relations'].items() if a in (r['from'], r['to'])]
            if key is None or a not in (catalog['relations'][key]['from'], catalog['relations'][key]['to']):
                said = tr('没有关系', 'There is no relation') if key is None else tr(f'关系「{edge["relation"]}」不连着 {_type_name(catalog, a)}：', f'The relation "{edge["relation"]}" does not connect to {_type_name(catalog, a)}. ')
                listed = tr('、', ', ').join(_relation_line(catalog, k) for k in touching) or tr('（没有）', '(none)')
                raise QueryError(tr(f'{said}「{edge["relation"]}」。{_type_name(catalog, a)} 能走的关系：{listed}', f'{said} "{edge["relation"]}". Relations {_type_name(catalog, a)} can follow: {listed}') if key is None
                                 else tr(f'{said}{_type_name(catalog, a)} 能走的关系：{listed}', f'{said}Relations {_type_name(catalog, a)} can follow: {listed}'), edge['at'])
            r = catalog['relations'][key]
            ends = {'out': (a, b), 'in': (b, a)}.get(edge['dir'])
            fits = (r['from'], r['to']) == ends if ends else {r['from'], r['to']} == {a, b}
            if not fits:
                raise QueryError(tr(f'关系「{r.get("name") or key}」是从 {_type_name(catalog, r["from"])} 到 {_type_name(catalog, r["to"])}，'
                                    f'这里写的是 {_type_name(catalog, a)} {"→" if edge["dir"] != "in" else "←"} {_type_name(catalog, b)}',
                                    f'The relation "{r.get("name") or key}" goes from {_type_name(catalog, r["from"])} to {_type_name(catalog, r["to"])}, '
                                    f'but the query has {_type_name(catalog, a)} {"→" if edge["dir"] != "in" else "←"} {_type_name(catalog, b)}'), edge['at'])
            if left['var'] == right['var']:
                raise QueryError(tr('一条关系的两头要是两个不同的简称', 'The two ends of a relation must have different short names'), edge['at'])
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
                    raise QueryError(tr(f'从 {start} 到 {other} 有两条路：一个节点只能从一条路走到', f'There are two paths from {start} to {other}: a node can only be reached by one path'))
                out[other] = [*out[here], key]
                todo.append(other)
    return out


def compile_query(text: str, catalog: dict, params: dict | None = None, rows: bool = False) -> dict:
    """The checked query the text says, with every key (see QUERY_KEYS), or QueryError saying what cannot be said and why. `rows`: SELECT LIST and SELECT ONE
    are read too, and give the same keys plus 'list' ({'properties', 'limit'?}) or 'lookup' ({key column: value}); a range bound may be today."""
    parsed = parse(text, params, rows)
    types, edges = _bind(catalog, parsed)

    def prop_of(var, prop, at=None):
        if var not in types:
            raise QueryError(tr(f'简称 {var} 没有在 FROM 里出现', f'The short name {var} does not appear in FROM'), at)
        if prop not in catalog['types'][types[var]]['properties']:
            raise _no_property(catalog, types[var], prop, at)
        return prop

    if parsed.get('rows'):
        return _compile_rows(parsed, types, prop_of)
    if parsed['graph']:
        return _compile_graph(catalog, parsed, types, edges, prop_of)

    aggs = [s for s in parsed['select'] if s['kind'] == 'agg']
    fields = [s for s in parsed['select'] if s['kind'] == 'field']
    if len(aggs) != 1:
        raise QueryError(tr('SELECT 里要有且只有一个要算的数：count(o)、sum(o.金额)、avg(o.金额) 或 share(o.状态码 = \'已取消\')。', "SELECT needs exactly one number to calculate: count(o), sum(o.amount), avg(o.amount) or share(o.status = 'cancelled'). ")
                         + (tr('一次算两个数还不支持，分成两条查询', 'Calculating two numbers at once is not supported yet: split it into two queries') if aggs else ''), parsed['select'][0]['at'])
    agg = aggs[0]
    first = parsed['chains'][0][0]['var']
    counted = agg['var'] or first
    if counted not in types:
        raise QueryError(tr(f'简称 {counted} 没有在 FROM 里出现', f'The short name {counted} does not appear in FROM'), agg['at'])
    group = parsed['group']
    for v in [g['var'] for g in group] + [f['var'] for f in fields]:
        if v not in types:
            raise QueryError(tr(f'简称 {v} 没有在 FROM 里出现', f'The short name {v} does not appear in FROM'))
    grouped = {(g['var'], g['prop'], g.get('by')) for g in group}
    for f in fields:
        if (f['var'], f['prop'], f.get('by')) not in grouped:
            shown = f'{f["by"]}({f["var"]}.{f["prop"]})' if f.get('by') else f'{f["var"]}.{f["prop"]}'
            raise QueryError(tr(f'{shown} 在 SELECT 里，也要写进 GROUP BY（和 SQL 一样，写法也要一样）', f'{shown} is in SELECT, so it must also be in GROUP BY (as in SQL, written the same way)'), f['at'])
    filtered = {c['var'] for c in parsed['where']}
    group = parsed['group']
    if agg['fn'] == 'count' and not group and len(filtered) == 1 and filtered != {counted}:
        start = next(iter(filtered))   # "the customers of the cancelled orders": filter the orders, count the customers they reach
    else:
        start = counted
    for c in parsed['where']:
        if c['var'] not in types:
            raise QueryError(tr(f'简称 {c["var"]} 没有在 FROM 里出现', f'The short name {c["var"]} does not appear in FROM'), c['at'])
        if c['var'] != start:
            raise QueryError(tr(f'条件只能写在被数或被算的对象（{start}）上；{c["var"]}.{c["prop"]} 是 {_type_name(catalog, types[c["var"]])} 的属性。'
                                f'跨对象的条件还不支持',
                                f'Conditions can only be on the object being counted or calculated ({start}); {c["var"]}.{c["prop"]} is a property of {_type_name(catalog, types[c["var"]])}. '
                                f'Conditions across objects are not supported yet'), c['at'])
    paths = _paths(start, edges)
    unreached = [v for v in types if v not in paths]
    if unreached:
        raise QueryError(tr(f'{"、".join(unreached)} 和 {start} 没有连在一起：FROM 里的节点要沿关系连成一片', f'{", ".join(unreached)} is not connected to {start}: the nodes in FROM must be linked by relations'))
    used = {start, *(g['var'] for g in group), *([counted] if counted != start else [])}
    needed = {v for u in used for v in types if paths[v] == paths[u][:len(paths[v])]}   # every node on the way from start to a used one
    idle = [v for v in types if v not in needed]
    if idle:
        raise QueryError(tr(f'{"、".join(f"({v}:{_type_name(catalog, types[v])})" for v in idle)} 没有用到。'
                            f'SQL 里多连一张表会悄悄去掉连不上的行，这里不会，所以请删掉它，或者按它分组',
                            f'{", ".join(f"({v}:{_type_name(catalog, types[v])})" for v in idle)} is not used. '
                            f'In SQL, joining an extra table quietly drops the rows that do not match; this does not, so remove it or group by it'))
    where = _where(parsed, prop_of)
    group_by = []
    for g in group:
        if g['var'] not in types:
            raise QueryError(tr(f'简称 {g["var"]} 没有在 FROM 里出现', f'The short name {g["var"]} does not appear in FROM'))
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
        same = (t['kind'] == 'alias' and t['name'] in ({agg['alias']} if agg.get('alias') else {ALIASES[agg['fn']], ALIASES_EN[agg['fn']]})) or \
               (t['kind'] == 'agg' and all(t.get(k) == agg.get(k) for k in ('fn', 'var', 'prop', 'value')))
        if not same:
            raise QueryError(tr('ORDER BY 现在只能按算出来的那个数排（写它的别名，或者再写一遍 sum(o.金额) 这样的写法）', 'ORDER BY can only sort by the calculated number (write its alias, or write it again, such as sum(o.amount))'), o['at'])
        if not group:
            raise QueryError(tr('ORDER BY 要和 GROUP BY 一起用：没有分组，就没有可以排的组', 'ORDER BY goes with GROUP BY: with no groups there is nothing to sort'), o['at'])
        order = o['direction']
    if parsed['limit']:
        if not group:
            raise QueryError(tr('LIMIT 要和 GROUP BY 一起用：它留下排在前面的几组', 'LIMIT goes with GROUP BY: it keeps the first few groups'), parsed['limit']['at'])
        top = parsed['limit']['n']
    via = paths[counted] if counted != start else []
    return {'start': types[start], 'where': where, 'via': via, 'group_by': group_by or None, 'share': share, 'measure': measure, 'top': top, 'order': order}


# --- writing it back -----------------------------------------------------------------------------------------------------------------------------------

def _where(parsed: dict, prop_of) -> list[dict]:
    where = []
    for c in parsed['where']:
        prop = prop_of(c['var'], c['prop'], c['at'])
        if 'range' in c:
            where.append({'field': prop, **{k: str(v) for k, v in c['range'].items()}})
            continue
        values = list(dict.fromkeys(str(v) for v in c['values']))
        if not c['not'] and len(values) > 1:
            raise QueryError(tr(f'{c["var"]}.{prop} IN 几个值还不支持（“不在这几个值里”可以写 NOT IN）；分成几条查询，或者确认一个视图', f'{c["var"]}.{prop} IN several values is not supported here ("not one of these values" can be written NOT IN). Split it into several queries, or confirm a view'), c['at'])
        where.append({'field': prop, 'not_equals': values[0] if len(values) == 1 else values} if c['not'] else {'field': prop, 'equals': values[0]})
    return where


def _compile_graph(catalog: dict, parsed: dict, types: dict, edges: list, prop_of) -> dict:
    """SELECT GRAPH: the first node is the start; WHERE is on it; every other node is drawn, reached from the start by its path. `graph` is those paths
    (relation keys from the start), `top` the start objects drawn at most."""
    start = parsed['chains'][0][0]['var']
    for c in parsed['where']:
        if c['var'] not in types:
            raise QueryError(tr(f'简称 {c["var"]} 没有在 FROM 里出现', f'The short name {c["var"]} does not appear in FROM'), c['at'])
        if c['var'] != start:
            raise QueryError(tr(f'条件只能写在起点对象（{start}，FROM 里的第一个）上；{c["var"]}.{c["prop"]} 是 {_type_name(catalog, types[c["var"]])} 的属性。'
                                f'跨对象的条件还不支持',
                                f'Conditions can only be on the start object ({start}, the first in FROM); {c["var"]}.{c["prop"]} is a property of {_type_name(catalog, types[c["var"]])}. '
                                f'Conditions across objects are not supported yet'), c['at'])
    paths = _paths(start, edges)
    unreached = [v for v in types if v not in paths]
    if unreached:
        raise QueryError(tr(f'{"、".join(unreached)} 和 {start} 没有连在一起：FROM 里的节点要沿关系连成一片', f'{", ".join(unreached)} is not connected to {start}: the nodes in FROM must be linked by relations'))
    drawn = list(dict.fromkeys(tuple(paths[v]) for v in types if v != start))
    return {'start': types[start], 'where': _where(parsed, prop_of), 'via': [], 'group_by': None, 'share': None, 'measure': None,
            'top': parsed['limit']['n'] if parsed['limit'] else None, 'order': None, 'graph': [list(p) for p in drawn]}


def _compile_rows(parsed: dict, types: dict, prop_of) -> dict:
    """SELECT LIST: the objects of the one node that meet the conditions, with the properties named (none: the key and the first ones). SELECT ONE: the object
    whose key the conditions give, every one an equals (which columns are the key is checked where the type is known)."""
    listing = parsed['rows']
    node = parsed['chains'][0][0]
    var = node['var']
    if listing['var'] != var:
        raise QueryError(tr(f'简称 {listing["var"]} 没有在 FROM 里出现', f'The short name {listing["var"]} does not appear in FROM'), listing['at'])
    for c in parsed['where']:
        if c['var'] != var:
            raise QueryError(tr(f'简称 {c["var"]} 没有在 FROM 里出现', f'The short name {c["var"]} does not appear in FROM'), c['at'])
    base = {'start': types[var], 'via': [], 'group_by': None, 'share': None, 'measure': None, 'top': None, 'order': None}
    if listing['kind'] == 'one':
        lookup = {}
        for c in parsed['where']:
            if 'range' in c or c['not'] or len(c['values']) != 1:
                raise QueryError(tr('SELECT ONE 按主键找一个对象：WHERE 里每个条件都写成 o.主键列 = \'值\'，用 AND 连起来；要按条件列出对象，用 SELECT LIST', "SELECT ONE finds one object by its key: write each condition as o.key_column = 'value', joined by AND; to list objects that meet conditions, use SELECT LIST"), c['at'])
            prop = prop_of(var, c['prop'], c['at'])
            if prop in lookup:
                raise QueryError(tr(f'{var}.{prop} 写了两次', f'{var}.{prop} is written twice'), c['at'])
            lookup[prop] = str(c['values'][0])
        if not lookup:
            raise QueryError(tr('SELECT ONE 要写 WHERE o.主键列 = \'值\'：它按主键找一个对象', "SELECT ONE needs WHERE o.key_column = 'value': it finds one object by its key"), listing['at'])
        return {**base, 'where': [], 'lookup': lookup}
    for v, _, at in listing['props']:
        if v != var:
            raise QueryError(tr(f'简称 {v} 没有在 FROM 里出现', f'The short name {v} does not appear in FROM'), at)
    named = [prop_of(var, p, at) for _, p, at in listing['props']]
    return {**base, 'where': _where(parsed, prop_of), 'list': {'properties': list(dict.fromkeys(named)), **({'limit': parsed['limit']['n']} if parsed['limit'] else {})}}


def canonical(query: dict, rows: bool = False) -> dict:
    """A structured query with every key, in the shape compile_query returns (group_by as dimensions, empty parts as None or []). `rows`: a list or a lookup
    keeps its part ('list', 'lookup')."""
    q = {k: query.get(k) for k in QUERY_KEYS}
    q['where'] = list(q['where'] or [])
    q['via'] = list(q['via'] or [])
    gb = q['group_by']
    if isinstance(gb, str):
        gb = [{'via': q['via'], 'field': gb}]
        q['via'] = []
    q['group_by'] = [{'via': list(d.get('via') or []), 'field': d['field'], **({'by': d['by']} if d.get('by') else {})} for d in gb] if gb else None
    if query.get('graph') is not None:   # SELECT GRAPH: the paths it draws
        q['graph'] = [list(p) for p in query['graph']]
    if rows and isinstance(query.get('list'), dict):   # SELECT LIST: the properties named, and the page size when one is given
        props = query['list'].get('properties') or []
        q['list'] = {'properties': list(dict.fromkeys(props)) if isinstance(props, list) else props, **({'limit': query['list']['limit']} if query['list'].get('limit') is not None else {})}
    elif rows and isinstance(query.get('lookup'), dict):   # SELECT ONE: the key it looks up
        q['lookup'] = {str(k): str(v) for k, v in query['lookup'].items()}
    return q


def _ident(name: str) -> str:
    return name if re.fullmatch(r'[A-Za-z_㐀-鿿豈-﫿][\w㐀-鿿豈-﫿]*', name) and name.upper() not in KEYWORDS else f'`{name}`'


def _literal(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _shown_name(table: dict, key: str) -> str:
    """The name to write: the label when no other entry has it, else the key."""
    name = table[key].get('name') or key
    return name if sum(1 for v in table.values() if (v.get('name') or None) == name) == 1 and name not in table else key


def to_text(query: dict, catalog: dict, rows: bool = False) -> str:
    """The structured query as OntoPoc Query text (compile_query of it gives canonical(query) back). QueryError when it names what the catalog lacks. `rows`: a
    list is written SELECT LIST, a lookup SELECT ONE, and the range bound today as the word today."""
    q = canonical(query, rows)
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
                raise QueryError(tr(f'没有关系「{key}」', f'There is no relation "{key}"'))
            r, here = catalog['relations'][key], type_of[path[:-1]]
            if here not in (r['from'], r['to']):
                raise QueryError(tr(f'关系「{key}」不连着 {_type_name(catalog, here)}', f'The relation "{key}" does not connect to {_type_name(catalog, here)}'))
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
    graph = q.get('graph')
    for path in graph or []:
        walk(path)
    dims = [(walk(d['via']), d['field'], d.get('by')) for d in q['group_by'] or []]
    dim_text = lambda v, f, by: f'{by}({v}.{_ident(f)})' if by else f'{v}.{_ident(f)}'
    counted = walk(q['via']) if q['via'] else start_var
    if chains[0] == head and len(chains) > 1 and chains[1].startswith(f'({start_var})'):
        chains[0] = head + chains.pop(1)[len(f'({start_var})'):]
    m, s = q['measure'], q['share']
    listed, lookup = q.get('list'), q.get('lookup')
    if listed is not None or lookup is not None:
        agg = alias = None
    elif graph is not None:
        agg = alias = None
    elif m:
        fn = {'sum': 'sum', 'average': 'avg'}.get(m.get('op'))
        if fn is None:
            raise QueryError(tr(f'不支持的算法 {m.get("op")}', f'Unsupported calculation {m.get("op")}'))
        field = m.get('field') or m.get('derived')
        if not isinstance(field, str) or not field:
            raise QueryError(tr('求和、求平均没有写字段', 'A sum or average needs a field'))
        agg, alias = f'{fn}({start_var}.{_ident(str(field))})', _alias(m['op'])
    elif s:
        if not isinstance(s.get('field'), str) or 'equals' not in s:
            raise QueryError(tr('占比要写字段和它等于的值', 'A share needs a field and the value it equals'))
        agg, alias = f'share({start_var}.{_ident(str(s["field"]))} = {_literal(s["equals"])})', _alias('share')
    else:
        agg, alias = f'count({counted})', _alias('count')
    if lookup is not None:
        head_line = f'SELECT ONE {start_var}'
    elif listed is not None:
        props = listed.get('properties') or []
        head_line = f'SELECT LIST {", ".join(f"{start_var}.{_ident(str(p))}" for p in props)}' if props else f'SELECT LIST {start_var}'
    else:
        head_line = 'SELECT GRAPH' if graph is not None else f'SELECT {", ".join([*(dim_text(*d) for d in dims), f"{agg} AS {alias}"])}'
    lines = [head_line, f'FROM {", ".join(chains)}']
    conds = [f'{start_var}.{_ident(str(k))} = {_literal(v)}' for k, v in (lookup or {}).items()]
    bound = lambda v: TODAY if rows and str(v).lower() == TODAY else str(v) if re.fullmatch(r'-?\d+(\.\d+)?', str(v)) else _literal(v)
    for w in q['where']:
        ranged = [k for k in COMPARE.values() if isinstance(w, dict) and k in w]
        if not isinstance(w, dict) or not isinstance(w.get('field'), str) or not ('equals' in w or 'not_equals' in w or ranged):
            raise QueryError(tr('筛选要写成“某个字段等于（或不等于）某个值”，或一个范围', 'A filter must be "a field equals (or does not equal) a value", or a range'))
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
                raise QueryError(tr('“不等于”后面要写一个值，或一个值的列表', 'After "does not equal", write a value or a list of values'))
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
    if listed is not None and listed.get('limit') is not None:
        lines.append(f'LIMIT {listed["limit"]}')
    return '\n'.join(lines)
