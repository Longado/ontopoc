"""The expression language of a computed column and a calculator: a small fixed grammar that is parsed here and compiled to SQL for SQLite. No part of an
expression is ever run as code: it becomes a syntax tree, the tree is checked against the columns of the step it is written on (an unknown field and a
type that does not fit are named before anything runs), and only then is SQL made from it, with every literal as a bound parameter and every field quoted.

    订单号, [金额 含税], 金额 * 数量 / 100, round(金额 / 数量, 2), if(状态码 = 2, '取消', '正常'), date_trunc('week', 下单日期),
    date_diff('day', 下单日期, 交付日期), date_add(下单日期, 7, 'day'), year(下单日期), concat(客户编号, '-', 产品编号)

Types are number, text, date, datetime and boolean (a month column such as 2026-01 is text). A field comes in as the type its column was read as; "+ - * /"
are for numbers only (dates are moved with date_add and measured with date_diff), a comparison needs two of one type, and a null literal fits anywhere.
A result that is null although no field it read was null (a division by zero, a date that is not one) is an error: trial_expression counts them.

Functions (FUNCTIONS says what each takes): round, abs, if, case, coalesce, concat, substring, date_trunc (week or month, a week starts on Monday),
date_diff (day, week, month or year, b minus a; month and year count calendar months and years, not whole spans), date_add (day, week, month, year),
year, month. concat gives null when any part is null; coalesce is the way to give a null a value. An if with a null condition takes the else branch.
"""
from __future__ import annotations

import difflib
import re

from ontology_poc_generator.lang import tr

MAX_LENGTH = 1000
MAX_DEPTH = 40
NUMBER_TYPES = ('integer', 'decimal')


class WordMap(dict):
    """A table of words written as {key: (中文, English)}: lookups answer in the language of the request; keys and iteration order are plain."""
    def __getitem__(self, key):
        return tr(*dict.__getitem__(self, key))

    def get(self, key, default=None):
        return self[key] if key in self else default

    def values(self):
        return [self[k] for k in self]

    def items(self):
        return [(k, self[k]) for k in self]


EXPR_TYPE = {'integer': 'number', 'decimal': 'number', 'text': 'text', 'month': 'text', 'date': 'date', 'datetime': 'datetime', 'boolean': 'boolean'}
TYPE_WORD = WordMap({'number': ('数字', 'number'), 'text': ('文本', 'text'), 'date': ('日期', 'date'), 'datetime': ('日期时间', 'date and time'), 'boolean': ('真假', 'true/false'), 'null': ('空', 'empty')})
COLUMN_TYPE = {'number': 'decimal', 'text': 'text', 'date': 'date', 'datetime': 'datetime', 'boolean': 'boolean'}   # what a column made from an expression is declared as
_FULL_WIDTH = {'，': ',', '（': '(', '）': ')', '＋': '+', '－': '-', '＊': '*', '／': '/', '＝': '=', '＜': '<', '＞': '>', '‘': "'", '’': "'", '“': '"', '”': '"'}
_TOKEN = re.compile(r"""\s*(?:(?P<num>\d+(?:\.\d+)?)|(?P<str>'(?:[^']|'')*'|"(?:[^"]|"")*")|(?P<field>\[[^\]]+\]|`[^`]+`)"""
                    r"""|(?P<op><=|>=|<>|!=|==|[-+*/=<>(),])|(?P<word>[^\W\d]\w*))""", re.UNICODE)
KEYWORDS = {'and', 'or', 'not', 'true', 'false', 'null'}
UNITS = {'date_trunc': ('week', 'month'), 'date_diff': ('day', 'week', 'month', 'year'), 'date_add': ('day', 'week', 'month', 'year')}

# group, name, template, what it does: what the editor lists, so a click inserts the template
_FUNCTION_DOCS = [
    (('数学', 'Math'), 'round', ('round(数值, 2)', 'round(number, 2)'), ('四舍五入到几位小数', 'Round to a number of decimal places')),
    (('数学', 'Math'), 'abs', ('abs(数值)', 'abs(number)'), ('绝对值', 'Absolute value')),
    (('判断', 'Logic'), 'if', ('if(条件, 值1, 值2)', 'if(condition, value1, value2)'), ('条件成立取值1，否则取值2（条件为空按否）', 'Value1 if the condition holds, otherwise value2 (an empty condition counts as false)')),
    (('判断', 'Logic'), 'case', ('case(条件1, 值1, 条件2, 值2, 其余的值)', 'case(condition1, value1, condition2, value2, else_value)'), ('按顺序找第一个成立的条件', 'The value of the first condition that holds, in order')),
    (('判断', 'Logic'), 'coalesce', ('coalesce(字段, 默认值)', 'coalesce(column, default)'), ('第一个不为空的值', 'The first value that is not empty')),
    (('文本', 'Text'), 'concat', ("concat(字段1, '-', 字段2)", "concat(column1, '-', column2)"), ('拼接文本；有一段为空，结果就为空', 'Join text; if any part is empty, the result is empty')),
    (('文本', 'Text'), 'substring', ('substring(文本, 开始位置, 长度)', 'substring(text, start, length)'), ('取一段文字，位置从 1 数起', 'Take part of a text; positions count from 1')),
    (('日期', 'Date'), 'date_trunc', ("date_trunc('week', 日期)", "date_trunc('week', date)"), ('取所在周（周一）或所在月的第一天', 'The first day of the week (Monday) or month')),
    (('日期', 'Date'), 'date_diff', ("date_diff('day', 日期A, 日期B)", "date_diff('day', dateA, dateB)"), ('日期B 减 日期A：day、week、month、year', 'dateB minus dateA: day, week, month, year')),
    (('日期', 'Date'), 'date_add', ("date_add(日期, 7, 'day')", "date_add(date, 7, 'day')"), ('加上几天、几周、几月、几年', 'Add days, weeks, months or years')),
    (('日期', 'Date'), 'year', ('year(日期)', 'year(date)'), ('年份', 'The year')),
    (('日期', 'Date'), 'month', ('month(日期)', 'month(date)'), ('月份', 'The month'))]


class _FunctionDocs:
    """FUNCTION_DOCS iterates as (group, name, template, what it does) in the language of the request."""
    def __iter__(self):
        for group, name, template, what in _FUNCTION_DOCS:
            yield tr(*group), name, tr(*template), tr(*what)


FUNCTION_DOCS = _FunctionDocs()

COMPARE = {'=': '=', '==': '=', '<>': '<>', '!=': '<>', '<': '<', '>': '>', '<=': '<=', '>=': '>='}


class ExprError(ValueError):
    """A parse error: `pos` is the character it was found at."""

    def __init__(self, message: str, pos: int):
        super().__init__(message)
        self.pos = pos


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def tokens(text: str) -> list[tuple]:
    """[(kind, value, position)] with kind num, str, field, op or word; ExprError for a character that is none of them."""
    out, i = [], 0
    while i < len(text):
        if text[i:].strip() == '':
            break
        m = _TOKEN.match(text, i)
        if not m or m.end() == i:
            bad = text[i:].lstrip()[:1]
            at = len(text) - len(text[i:].lstrip())
            if bad in _FULL_WIDTH:
                raise ExprError(tr(f'第 {at + 1} 个字符「{bad}」是全角符号，请换成半角「{_FULL_WIDTH[bad]}」', f'Character {at + 1} "{bad}" is a full-width symbol; use the half-width "{_FULL_WIDTH[bad]}" instead'), at)
            raise ExprError(tr(f'第 {at + 1} 个字符「{bad}」不认识', f'Character {at + 1} "{bad}" is not recognized'), at)
        kind = m.lastgroup
        value = m.group(kind)
        out.append((kind, value, m.start(kind)))
        i = m.end()
    return out


class _Parser:
    def __init__(self, text: str):
        self.tokens, self.i, self.depth = tokens(text), 0, 0
        self.end = len(text)

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None, self.end)

    def take(self):
        token = self.peek()
        self.i += 1
        return token

    def is_op(self, *ops) -> bool:
        kind, value, _ = self.peek()
        return kind == 'op' and value in ops

    def is_word(self, word) -> bool:
        kind, value, _ = self.peek()
        return kind == 'word' and value.lower() == word

    def expect_op(self, op: str, what: str):
        if not self.is_op(op):
            raise ExprError(tr(f'这里要有「{op}」（{what}）', f'Expected "{op}" here ({what})'), self.peek()[2])
        self.take()

    def parse(self):
        if not self.tokens:
            raise ExprError(tr('表达式是空的', 'The expression is empty'), 0)
        node = self.or_()
        if self.i < len(self.tokens):
            kind, value, pos = self.peek()
            raise ExprError(tr(f'「{value}」放在这里不对：前面的部分已经是一个完整的表达式，中间少了运算符或逗号？', f'"{value}" does not belong here: what comes before is already a complete expression. Is an operator or comma missing?'), pos)
        return node

    def nested(self, parse):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise ExprError(tr(f'括号和函数嵌套太深（最多 {MAX_DEPTH} 层）', f'Parentheses and functions are nested too deeply (at most {MAX_DEPTH} levels)'), self.peek()[2])
        try:
            return parse()
        finally:
            self.depth -= 1

    def or_(self):
        node = self.and_()
        while self.is_word('or'):
            pos = self.take()[2]
            node = ('bin', 'or', node, self.and_(), pos)
        return node

    def and_(self):
        node = self.not_()
        while self.is_word('and'):
            pos = self.take()[2]
            node = ('bin', 'and', node, self.not_(), pos)
        return node

    def not_(self):
        if self.is_word('not'):
            pos = self.take()[2]
            return ('not', self.nested(self.not_), pos)
        return self.compare()

    def compare(self):
        node = self.add()
        if self.is_op(*COMPARE):
            kind, op, pos = self.take()
            return ('cmp', COMPARE[op], node, self.add(), pos)
        return node

    def add(self):
        node = self.mul()
        while self.is_op('+', '-'):
            kind, op, pos = self.take()
            node = ('bin', op, node, self.mul(), pos)
        return node

    def mul(self):
        node = self.unary()
        while self.is_op('*', '/'):
            kind, op, pos = self.take()
            node = ('bin', op, node, self.unary(), pos)
        return node

    def unary(self):
        if self.is_op('-', '+'):
            kind, op, pos = self.take()
            return ('neg', self.nested(self.unary), pos) if op == '-' else self.nested(self.unary)
        return self.primary()

    def primary(self):
        kind, value, pos = self.take()
        if kind == 'num':
            return ('num', float(value), pos)
        if kind == 'str':
            return ('str', value[1:-1].replace(value[0] * 2, value[0]), pos)
        if kind == 'field':
            return ('field', value[1:-1], pos)
        if kind == 'op' and value == '(':
            node = self.nested(self.or_)
            self.expect_op(')', tr('括号没有闭合', 'a parenthesis is not closed'))
            return node
        if kind == 'word':
            low = value.lower()
            if low in ('true', 'false'):
                return ('bool', low == 'true', pos)
            if low == 'null':
                return ('null', None, pos)
            if low in KEYWORDS:
                raise ExprError(tr(f'「{value}」是运算符，放在这里不对', f'"{value}" is an operator and does not belong here'), pos)
            if self.is_op('('):
                self.take()
                args = []
                if not self.is_op(')'):
                    args.append(self.nested(self.or_))
                    while self.is_op(','):
                        self.take()
                        args.append(self.nested(self.or_))
                self.expect_op(')', tr(f'函数 {value} 的括号没有闭合', f'the parenthesis of function {value} is not closed'))
                return ('call', low, args, pos)
            return ('field', value, pos)
        if kind is None:
            raise ExprError(tr('表达式没写完', 'The expression is unfinished'), self.end)
        raise ExprError(tr(f'「{value}」放在这里不对，这里应该是一个值、字段或函数', f'"{value}" does not belong here; expected a value, a property or a function'), pos)


def parse(text: str):
    """The syntax tree of an expression; ExprError for a text that is not one."""
    if not isinstance(text, str) or not text.strip():
        raise ExprError(tr('表达式是空的', 'The expression is empty'), 0)
    if len(text) > MAX_LENGTH:
        raise ExprError(tr(f'表达式最长 {MAX_LENGTH} 个字符', f'An expression can be at most {MAX_LENGTH} characters long'), MAX_LENGTH)
    return _Parser(text).parse()


# --- checking and SQL ---------------------------------------------------------------------------------------------------------------------------------

class _Compiler:
    """Walks a tree and returns (type, sql, params) for each node; the errors found are collected, not raised, so a person is told about all of them. A node
    that is wrong has the type 'error', which fits everywhere and says nothing more."""

    def __init__(self, columns: list[dict]):
        self.columns = {c['name']: c['type'] for c in columns}
        self.errors: list[dict] = []
        self.fields: list[str] = []

    def error(self, message: str, pos: int):
        self.errors.append({'message': message, 'pos': pos})
        return 'error', 'NULL', []

    def field_sql(self, name: str, kind: str) -> str:
        column = _q(name)
        if kind in NUMBER_TYPES:
            return f'CAST({column} AS REAL)'
        return f'pl_bool({column})' if kind == 'boolean' else column

    def visit(self, node):
        return getattr(self, f'v_{node[0]}')(node)

    def v_num(self, node):
        return 'number', '?', [node[1]]

    def v_str(self, node):
        return 'text', '?', [node[1]]

    def v_bool(self, node):
        return 'boolean', '1' if node[1] else '0', []

    def v_null(self, node):
        return 'null', 'NULL', []

    def v_field(self, node):
        name, pos = node[1], node[2]
        if name not in self.columns:
            near = difflib.get_close_matches(name, list(self.columns), n=3, cutoff=0.5)
            known = tr('、', ', ').join(tr(f'「{c}」', f'"{c}"') for c in list(self.columns)[:12])
            return self.error(tr(f'没有字段「{name}」', f'No column "{name}"') + (tr(f'，是不是{"、".join(f"「{n}」" for n in near)}？', f'. Did you mean {", ".join(chr(34) + n + chr(34) for n in near)}?') if near else tr(f'。可用的字段：{known}', f'. Available columns: {known}')), pos)
        if name not in self.fields:
            self.fields.append(name)
        kind = self.columns[name]
        return EXPR_TYPE[kind], self.field_sql(name, kind), []

    def v_neg(self, node):
        kind, sql, params = self.visit(node[1])
        if kind not in ('number', 'error', 'null'):
            return self.error(tr(f'负号只能用在数字上，这里是{TYPE_WORD[kind]}', f'A minus sign only works on numbers; this is {TYPE_WORD[kind]}'), node[2])
        return 'number' if kind != 'error' else kind, f'(-{sql})', params

    def v_not(self, node):
        kind, sql, params = self.visit(node[1])
        if kind not in ('boolean', 'error', 'null'):
            return self.error(tr(f'not 后面要是真假的条件，这里是{TYPE_WORD[kind]}', f'not needs a true/false condition; this is {TYPE_WORD[kind]}'), node[2])
        return 'boolean', f'(NOT {sql})', params

    def v_bin(self, node):
        op, pos = node[1], node[4]
        (lk, ls, lp), (rk, rs, rp) = self.visit(node[2]), self.visit(node[3])
        if op in ('and', 'or'):
            for kind in (lk, rk):
                if kind not in ('boolean', 'error', 'null'):
                    return self.error(tr(f'{op} 两边要是真假的条件，这里有一边是{TYPE_WORD[kind]}', f'{op} needs true/false conditions on both sides; one side is {TYPE_WORD[kind]}'), pos)
            return 'boolean', f'({ls} {op.upper()} {rs})', lp + rp
        for kind in (lk, rk):
            if kind not in ('number', 'error', 'null'):
                hint = tr('；日期用 date_add 加减、date_diff 相减', '; for dates use date_add to add and date_diff to subtract') if kind in ('date', 'datetime') else tr('；拼接文本用 concat', '; to join text use concat') if kind == 'text' else ''
                return self.error(tr(f'「{op}」只能算数字，这里有一边是{TYPE_WORD[kind]}{hint}', f'"{op}" only works on numbers; one side is {TYPE_WORD[kind]}{hint}'), pos)
        return ('error' if 'error' in (lk, rk) else 'number'), f'({ls} {op} {rs})', lp + rp

    def v_cmp(self, node):
        op, pos = node[1], node[4]
        (lk, ls, lp), (rk, rs, rp) = self.visit(node[2]), self.visit(node[3])
        if 'error' in (lk, rk):
            return 'error', 'NULL', []
        for side, other in ((node[2], rk), (node[3], lk)):   # a date written as text, compared with a date column, is read as that date
            if side[0] == 'str' and other in ('date', 'datetime'):
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?', side[1]):
                    return self.error(tr(f'「{side[1]}」要写成 2026-05-03 这样的日期才能和日期比较', f'"{side[1]}" must be written as a date like 2026-05-03 to compare with a date'), pos)
                lk, rk = (other, other)
        if 'null' not in (lk, rk) and lk != rk:
            return self.error(tr(f'「{op}」两边类型不同：{TYPE_WORD[lk]}和{TYPE_WORD[rk]}不能比较；类型要先转成一样的（字段转换）', f'The two sides of "{op}" have different types: {TYPE_WORD[lk]} and {TYPE_WORD[rk]} cannot be compared; convert them to the same type first (cast step)'), pos)
        return 'boolean', f'({ls} {COMPARE[op]} {rs})', lp + rp

    # functions ---------------------------------------------------------------------------------------------------------------------------------------

    def v_call(self, node):
        name, args, pos = node[1], node[2], node[3]
        handler = getattr(self, f'f_{name}', None)
        if handler is None:
            near = difflib.get_close_matches(name, [d[1] for d in FUNCTION_DOCS], n=1, cutoff=0.6)
            return self.error(tr(f'没有函数 {name}', f'No function {name}') + (tr(f'，是不是 {near[0]}？', f'. Did you mean {near[0]}?') if near else tr('；可用的函数见函数列表', '; see the function list')), pos)
        return handler(args, pos)

    def arity(self, name: str, args: list, low: int, high: int | None, pos: int) -> bool:
        if len(args) < low or (high is not None and len(args) > high):
            want = f'{low}' if high == low else tr(f'{low} 到 {high}', f'{low} to {high}') if high else tr(f'至少 {low}', f'at least {low}')
            self.error(tr(f'{name} 要 {want} 个参数，这里写了 {len(args)} 个', f'{name} takes {want} arguments; {len(args)} given'), pos)
            return False
        return True

    def typed(self, name: str, arg, wanted: tuple, which: int):
        """(type, sql, params) of an argument that must be one of `wanted` types; an error says which parameter of which function."""
        kind, sql, params = self.visit(arg)
        if kind in ('error',) or kind in wanted or kind == 'null':
            return kind, sql, params
        return self.error(tr(f'{name} 的第 {which} 个参数要是{"或".join(TYPE_WORD[w] for w in wanted)}，这里是{TYPE_WORD[kind]}', f'Argument {which} of {name} must be {" or ".join(TYPE_WORD[w] for w in wanted)}; this is {TYPE_WORD[kind]}'), arg[-1] if isinstance(arg[-1], int) else 0)

    def unit(self, name: str, arg, which: int) -> str | None:
        if arg[0] != 'str' or arg[1] not in UNITS[name]:
            self.error(tr(f'{name} 的第 {which} 个参数要写成 {" 或 ".join(f"{chr(39)}{u}{chr(39)}" for u in UNITS[name])}', f'Argument {which} of {name} must be one of {" or ".join(f"{chr(39)}{u}{chr(39)}" for u in UNITS[name])}'), arg[-1])
            return None
        return arg[1]

    def f_round(self, args, pos):
        if not self.arity('round', args, 1, 2, pos):
            return 'error', 'NULL', []
        (_, s, p) = self.typed('round', args[0], ('number',), 1)
        if len(args) == 2:
            (_, ds, dp) = self.typed('round', args[1], ('number',), 2)
            return 'number', f'ROUND({s}, {ds})', p + dp
        return 'number', f'ROUND({s})', p

    def f_abs(self, args, pos):
        if not self.arity('abs', args, 1, 1, pos):
            return 'error', 'NULL', []
        (_, s, p) = self.typed('abs', args[0], ('number',), 1)
        return 'number', f'ABS({s})', p

    def unify(self, kinds: list[str], pos: int, what: str) -> str:
        real = {k for k in kinds if k not in ('null', 'error')}
        if 'error' in kinds:
            return 'error'
        if len(real) > 1:
            self.error(tr(f'{what}的几个值类型不一样：{"、".join(TYPE_WORD[k] for k in sorted(real))}', f'The values of {what} have different types: {", ".join(TYPE_WORD[k] for k in sorted(real))}'), pos)
            return 'error'
        return real.pop() if real else 'null'

    def condition(self, name: str, arg, which: int):
        return self.typed(name, arg, ('boolean',), which)

    def f_if(self, args, pos):
        if not self.arity('if', args, 3, 3, pos):
            return 'error', 'NULL', []
        (_, cs, cp), (ak, a_s, ap), (bk, bs, bp) = self.condition('if', args[0], 1), self.visit(args[1]), self.visit(args[2])
        return self.unify([ak, bk], pos, 'if'), f'(CASE WHEN {cs} THEN {a_s} ELSE {bs} END)', cp + ap + bp

    def f_case(self, args, pos):
        if len(args) < 3 or len(args) % 2 == 0:
            self.error(tr('case 的参数是：条件1, 值1, 条件2, 值2, …, 其余的值（条件和值成对，最后一个是其余情况的值）', 'case takes: condition1, value1, condition2, value2, ..., else value (conditions and values come in pairs; the last one is the value for all other cases)'), pos)
            return 'error', 'NULL', []
        whens, params, kinds = [], [], []
        for i in range(0, len(args) - 1, 2):
            (_, cs, cp) = self.condition('case', args[i], i + 1)
            vk, vs, vp = self.visit(args[i + 1])
            kinds.append(vk)
            whens.append(f'WHEN {cs} THEN {vs}')
            params += cp + vp
        ek, es, ep = self.visit(args[-1])
        return self.unify([*kinds, ek], pos, 'case'), f'(CASE {" ".join(whens)} ELSE {es} END)', params + ep

    def f_coalesce(self, args, pos):
        if not self.arity('coalesce', args, 2, None, pos):
            return 'error', 'NULL', []
        parts = [self.visit(a) for a in args]
        return self.unify([k for k, _, _ in parts], pos, 'coalesce'), f'COALESCE({", ".join(s for _, s, _ in parts)})', [x for _, _, p in parts for x in p]

    def f_concat(self, args, pos):
        if not self.arity('concat', args, 2, None, pos):
            return 'error', 'NULL', []
        sqls, params = [], []
        for i, arg in enumerate(args, 1):
            kind, sql, p = self.typed('concat', arg, ('text', 'number', 'date', 'datetime'), i)
            sqls.append(f'pl_text({sql})' if kind == 'number' else sql)
            params += p
        return 'text', f'({" || ".join(sqls)})', params

    def f_substring(self, args, pos):
        if not self.arity('substring', args, 2, 3, pos):
            return 'error', 'NULL', []
        parts = [self.typed('substring', args[0], ('text', 'date', 'datetime'), 1), *(self.typed('substring', a, ('number',), i) for i, a in enumerate(args[1:], 2))]
        return 'text', f'SUBSTR({", ".join(s for _, s, _ in parts)})', [x for _, _, p in parts for x in p]

    def f_date_trunc(self, args, pos):
        if not self.arity('date_trunc', args, 2, 2, pos):
            return 'error', 'NULL', []
        unit = self.unit('date_trunc', args[0], 1)
        _, s, p = self.typed('date_trunc', args[1], ('date', 'datetime'), 2)
        if unit is None:
            return 'error', 'NULL', []
        if unit == 'month':
            return 'date', f"date({s}, 'start of month')", p
        return 'date', f"date({s}, '-' || ((CAST(strftime('%w', {s}) AS INTEGER) + 6) % 7) || ' days')", p + p

    def f_date_diff(self, args, pos):
        if not self.arity('date_diff', args, 3, 3, pos):
            return 'error', 'NULL', []
        unit = self.unit('date_diff', args[0], 1)
        (ak, a_s, ap), (bk, bs, bp) = self.typed('date_diff', args[1], ('date', 'datetime'), 2), self.typed('date_diff', args[2], ('date', 'datetime'), 3)
        if unit is None:
            return 'error', 'NULL', []
        if unit in ('day', 'week'):
            return 'number', f"CAST((CAST(strftime('%s', {bs}) AS INTEGER) - CAST(strftime('%s', {a_s}) AS INTEGER)) / {86400 if unit == 'day' else 604800} AS INTEGER)", bp + ap
        if unit == 'month':
            return 'number', (f"((CAST(strftime('%Y', {bs}) AS INTEGER) * 12 + CAST(strftime('%m', {bs}) AS INTEGER)) - "
                              f"(CAST(strftime('%Y', {a_s}) AS INTEGER) * 12 + CAST(strftime('%m', {a_s}) AS INTEGER)))"), bp + bp + ap + ap
        return 'number', f"(CAST(strftime('%Y', {bs}) AS INTEGER) - CAST(strftime('%Y', {a_s}) AS INTEGER))", bp + ap

    def f_date_add(self, args, pos):
        if not self.arity('date_add', args, 3, 3, pos):
            return 'error', 'NULL', []
        (dk, ds, dp), (_, ns, np) = self.typed('date_add', args[0], ('date', 'datetime'), 1), self.typed('date_add', args[1], ('number',), 2)
        unit = self.unit('date_add', args[2], 3)
        if unit is None:
            return 'error', 'NULL', []
        count = f'CAST({ns} AS INTEGER) * 7' if unit == 'week' else f'CAST({ns} AS INTEGER)'
        word = {'day': 'days', 'week': 'days', 'month': 'months', 'year': 'years'}[unit]
        kind = dk if dk in ('date', 'datetime') else 'date'
        return kind, f"{'datetime' if kind == 'datetime' else 'date'}({ds}, printf('%+d {word}', {count}))", dp + np

    def _part(self, name: str, fmt: str, args, pos):
        if not self.arity(name, args, 1, 1, pos):
            return 'error', 'NULL', []
        _, s, p = self.typed(name, args[0], ('date', 'datetime'), 1)
        return 'number', f"CAST(strftime('{fmt}', {s}) AS INTEGER)", p

    def f_year(self, args, pos):
        return self._part('year', '%Y', args, pos)

    def f_month(self, args, pos):
        return self._part('month', '%m', args, pos)


def compile_expression(text: str, columns: list[dict], expect: str | None = None) -> dict:
    """{'ok', 'errors': [{message, pos}], 'type' (number / text / date / datetime / boolean), 'sql', 'params', 'fields': [the fields it reads]} for an expression
    written over `columns` ([{name, type}] with the types a dataset column is read as). Never raises for what a person wrote: a parse error is one entry of
    `errors`, a type error each of its own. `expect`: the type the column it makes is to have; another type is an error."""
    try:
        tree = parse(text)
    except ExprError as exc:
        return {'ok': False, 'errors': [{'message': str(exc), 'pos': exc.pos}], 'type': None, 'sql': None, 'params': [], 'fields': []}
    compiler = _Compiler(columns)
    try:
        kind, sql, params = compiler.visit(tree)
        truncates = _truncates(tree)
    except RecursionError:
        return {'ok': False, 'errors': [{'message': tr('表达式太长太深，拆成几步来算', 'The expression is too long or too deep; split it into several steps'), 'pos': 0}], 'type': None, 'sql': None, 'params': [], 'fields': [], 'truncates': False}
    if kind == 'null' and not compiler.errors:
        compiler.error(tr('这个表达式只有空值，没有算出什么', 'This expression only produces empty values, so nothing is computed'), 0)
    if expect and kind not in (expect, 'error', 'null') and not compiler.errors:
        compiler.error(tr(f'表达式算出来是{TYPE_WORD[kind]}，列要的是{TYPE_WORD.get(expect, expect)}', f'The expression produces {TYPE_WORD[kind]}, but the column needs {TYPE_WORD.get(expect, expect)}'), 0)
    ok = not compiler.errors
    return {'ok': ok, 'errors': compiler.errors, 'type': kind if ok else None, 'sql': sql if ok else None, 'params': params if ok else [],
            'fields': compiler.fields, 'truncates': ok and truncates}


def _truncates(tree) -> bool:
    """Whether the expression takes the start of a week or a month somewhere: a result of that can never be later than the date it came from."""
    if tree[0] == 'call' and tree[1] == 'date_trunc':
        return True
    children = [c for part in tree[1:] for c in (part if isinstance(part, list) else [part]) if isinstance(c, tuple)]
    return any(_truncates(c) for c in children)


def error_condition(sql: str, params: list, fields: list[str]) -> tuple[str, list]:
    """SQL that is true for a row whose result is null although every field the expression read has a value: a division by zero, a date that is not one.
    A row with an empty field is expected to give an empty result and is not an error."""
    filled = ''.join(f' AND {_q(f)} IS NOT NULL' for f in fields)
    return f'(({sql}) IS NULL{filled})', list(params)
