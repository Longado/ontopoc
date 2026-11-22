"""Value rules: what every row of an object type must hold, written on its properties and confirmed with the type (they are part of its content).

A rule is kept in the type's content as a small object with only the fields its kind needs, so each can be written later as a SHACL property shape without
guessing (sh:path is the column; the comparison and the bound map one to one):
    {"column": c, "check": "not_empty"}                               sh:minCount 1, and the value is not blank
    {"column": c, "check": "gt" | "ge" | "lt" | "le", "value": n}     sh:minExclusive | sh:minInclusive | sh:maxExclusive | sh:maxInclusive n
    {"column": c, "check": "between", "low": a, "high": b}            sh:minInclusive a and sh:maxInclusive b (both ends included)
    {"column": c, "check": "in_codes"}                                sh:in the values of the column's confirmed code meanings
    {"column": c, "check": "not_before", "other": d}                  on d, sh:lessThanOrEquals c (d is never after c)
The bounds are JSON numbers. A type with no rules keeps no "rules" key at all, so its content is what it was before rules existed.

What each rule judges (the same for every reader, the type page, the confirm check and the recheck after new data):
- empty: no value, or only blanks (spaces and line breaks of every kind, and zero-width characters: BLANKS). "not empty" is broken by an empty cell; every
  other rule leaves empty cells unjudged.
- number rules (on an integer or decimal property): a filled cell must be a plain number (-12, 3.5; blanks around it are ignored) that meets the comparison;
  anything else filled (abc, 1e3, 12., a full-width digit) breaks the rule. The comparison is exact however many digits the cell has: as floats, except near the
  bound, where the decimal text is compared (a bound has at most 15 significant digits, which a float keeps exactly).
- codes (on a code column): a filled cell must be one of the values the column's meanings give a meaning to, exactly as stored.
- date order (two date or date-and-time properties, or two months): a row with either cell empty is not judged; a filled cell that is not a real date
  (2026-02-30, soon) breaks it; a date alone is the start of its day. The column must not be before the other.

All of a type's rules are counted in one pass over its rows (one SELECT with a sum per rule); the keys of up to 20 rows that break a rule are fetched only
for a rule that some row breaks. Column names come from the type's stored properties and are quoted as names; bounds and codes are bound parameters.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
import re

from ontology_poc_generator.lang import tr

MAX_RULES = 20
EXAMPLES = 20
REASON_EXAMPLES = 5
NUMBER_TYPES = ('integer', 'decimal')
DAY_TYPES = ('date', 'datetime')
BOUNDED = ('gt', 'ge', 'lt', 'le')
CHECKS = ('not_empty', *BOUNDED, 'between', 'in_codes', 'not_before')
_NUMBER_TEXT = re.compile(r'-?[0-9]{1,15}(\.[0-9]{1,15})?', re.ASCII)
DIGITS = 15   # a bound has at most this many significant digits: a float keeps every such decimal exactly as written
# what counts as nothing in a cell: every kind of space and line break, and the zero-width characters (none of them a quote, so they sit in an SQL literal)
BLANKS = ''.join(c for c in map(chr, range(0x3001)) if c.isspace()) + '\u200b\u200c\u200d\u2060\ufeff'
_BLANKS_SQL = "'" + BLANKS + "'"


class RuleRefused(ValueError):
    """A rule a person wrote that cannot stand on this type; the message says why, in the reader's language."""


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _bound(value, column: str):
    """A bound as a JSON number: an int or float (not yes/no, not infinite) or the text of a plain number. RuleRefused otherwise."""
    if isinstance(value, bool) or value is None:
        number = None
    elif isinstance(value, int):
        number = value if abs(value) < 10 ** 15 else None
    elif isinstance(value, float):
        number = value if math.isfinite(value) and abs(value) < 1e15 else None
    elif isinstance(value, str) and _NUMBER_TEXT.fullmatch(value.strip()):
        number = float(value.strip())
    else:
        number = None
    if number is None:
        raise RuleRefused(tr(f'“{column}”的规则要写一个数，例如 0 或 12.5', f'The rule on "{column}" needs a number, for example 0 or 12.5'))
    written = value.strip() if isinstance(value, str) else str(value)
    if len(Decimal(written).normalize().as_tuple().digits) > DIGITS:
        raise RuleRefused(tr(f'“{column}”的规则里的数最多写 {DIGITS} 位有效数字', f'The number in the rule on "{column}" can have at most {DIGITS} significant digits'))
    return int(number) if float(number).is_integer() else float(number)


def read_rules(given, properties: list[dict], has_codes) -> list[dict]:
    """The rules as they are kept, from what a person wrote: [{column, check, ...}], at most MAX_RULES, each on a property of the type and of a kind that
    property can take. `has_codes(column)`: whether the code column has meanings a code rule can stand on. RuleRefused says what does not fit."""
    if not isinstance(given, list) or not all(isinstance(r, dict) for r in given):
        raise RuleRefused(tr('值规则要写成列表：[{column, check, ...}]', 'Value rules must be a list: [{column, check, ...}]'))
    if len(given) > MAX_RULES:
        raise RuleRefused(tr(f'一个对象类型最多 {MAX_RULES} 条值规则', f'An object type can have at most {MAX_RULES} value rules'))
    props = {p['column']: p for p in properties}
    kept = []
    for r in given:
        column, check = r.get('column'), r.get('check')
        if not isinstance(column, str) or column not in props:
            raise RuleRefused(tr(f'值规则写的“{column}”不是这个对象类型的属性', f'The value rule names "{column}", which is not a property of this object type'))
        if check not in CHECKS:
            raise RuleRefused(tr(f'“{column}”的规则种类只能是 {", ".join(CHECKS)}', f'The kind of rule on "{column}" must be one of {", ".join(CHECKS)}'))
        kind = props[column]['type']
        if check in (*BOUNDED, 'between') and kind not in NUMBER_TYPES:
            raise RuleRefused(tr(f'“{column}”不是数字属性，只能写“不能为空”{"或“是写了含义的代码之一”" if props[column]["enum"] else ""}', f'"{column}" is not a number property: it can only be "not empty"{" or one of its codes" if props[column]["enum"] else ""}'))
        rule = {'column': column, 'check': check}
        if check in BOUNDED:
            rule['value'] = _bound(r.get('value'), column)
        elif check == 'between':
            rule['low'], rule['high'] = _bound(r.get('low'), column), _bound(r.get('high'), column)
            if rule['low'] > rule['high']:
                raise RuleRefused(tr(f'“{column}”的范围要从小写到大：{rule["low"]} 比 {rule["high"]} 大', f'The range on "{column}" must go from low to high: {rule["low"]} is more than {rule["high"]}'))
        elif check == 'in_codes':
            if not props[column]['enum']:
                raise RuleRefused(tr(f'“{column}”不是代码列，不能要求它是写了含义的代码之一', f'"{column}" is not a code column, so it cannot be required to be one of its codes'))
            if not has_codes(column):
                raise RuleRefused(tr(f'“{column}”还没有写含义：先写含义，再要求它是写了含义的代码之一', f'"{column}" has no meanings yet: write them first, then require it to be one of its codes'))
        elif check == 'not_before':
            other = r.get('other')
            if not isinstance(other, str) or other not in props or other == column:
                raise RuleRefused(tr(f'“{column}”不能早于的那一列要是这个对象类型的另一个属性', f'The column "{column}" must not be before has to be another property of this object type'))
            kinds = {kind, props[other]['type']}
            if not (kinds <= set(DAY_TYPES) or kinds == {'month'}):
                raise RuleRefused(tr(f'“{column}”和“{other}”要都是日期（或都是月份），才能比先后', f'"{column}" and "{other}" must both be dates (or both months) to be put in order'))
            rule['other'] = other
        if rule in kept:
            raise RuleRefused(tr(f'“{column}”的同一条规则写了两次', f'The same rule on "{column}" is written twice'))
        kept.append(rule)
    return kept


def columns_of(rule: dict) -> set[str]:
    return {rule['column'], *([rule['other']] if 'other' in rule else [])}


# --- what breaks a rule, in SQL ----------------------------------------------------------------------------------------------------------------------

def _trim(v: str) -> str:
    """The cell without the blanks around it. Plain ASCII text (most cells: numbers, dates, codes) has only spaces to trim, which the short form does quickly."""
    return f"(CASE WHEN {v} GLOB '*[^ -~]*' THEN trim({v}, {_BLANKS_SQL}) ELSE trim({v}) END)"


def _empty(s: str) -> str:
    """`s`: the cell with its blanks trimmed (or NULL)."""
    return f"({s} IS NULL OR {s} = '')"


def _number(s: str) -> str:
    """A filled cell that is a plain number: an optional minus, digits, at most one point with digits after it (`s` is trimmed of blanks)."""
    return f"(({s} GLOB '[0-9]*' OR {s} GLOB '-[0-9]*') AND substr({s}, 2) NOT GLOB '*[^0-9.]*' AND {s} NOT GLOB '*.*.*' AND {s} NOT GLOB '*.')"


_DAY = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"


def _day(s: str, kind: str) -> tuple[str, str]:
    """(the cell is a real date, its moment as a julian day) for a date, date-and-time or month cell (`s` is trimmed of blanks)."""
    if kind == 'month':
        first = f"({s} || '-01')"
        return f"({s} GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]' AND substr({s}, 1, 4) <> '0000' AND date({first}) IS {first})", f'julianday({first})'
    shapes = ' OR '.join(f"{s} GLOB '{_DAY}{tail}'" for tail in ('', '[T ][0-9][0-9]:[0-9][0-9]', '[T ][0-9][0-9]:[0-9][0-9]:[0-9][0-9]'))
    # year 0 and hour 24 name no real moment, though SQLite reads them
    return (f"(({shapes}) AND substr({s}, 1, 4) <> '0000' AND (length({s}) = 10 OR substr({s}, 12, 2) <= '23') AND julianday({s}) IS NOT NULL "
            f"AND date(substr({s}, 1, 10)) IS substr({s}, 1, 10))", f'julianday({s})')


_OPS = {'gt': '>', 'ge': '>=', 'lt': '<', 'le': '<='}
EXACT = 'value_rule_order'   # the SQL function that orders a cell's number against a bound exactly, for the few cells a float cannot tell from the bound


_PLAIN = re.compile(r'-?[0-9]+(\.[0-9]+)?', re.ASCII)


def _order(text, bound) -> int | None:
    """-1, 0 or 1 as the cell's plain number is below, at or above the bound; None (never an error) for anything that is not a plain number: NaN, Infinity,
    1e999, hex and the rest that Decimal would read are text here."""
    try:
        if not (isinstance(text, str) and isinstance(bound, str) and _PLAIN.fullmatch(text) and _PLAIN.fullmatch(bound)):
            return None
        a, b = Decimal(text), Decimal(bound)
        return (a > b) - (a < b)
    except Exception:
        return None


def _holds(s: str, op: str, bound) -> tuple[str, list]:
    """(the cell's number meets `op bound`, its parameters): as floats, except within a hair of the bound, where a float may have lost the digits that decide it
    (0.10000000000000000001 against 0.1) and the decimal text is compared exactly."""
    near = abs(float(bound)) * 1e-9 + 1e-200
    return (f'(CASE WHEN abs(CAST({s} AS REAL) - ?) <= ? THEN {EXACT}({s}, ?) {op} 0 ELSE CAST({s} AS REAL) {op} ? END)',
            [float(bound), near, str(bound), float(bound)])


def broken_sql(rule: dict, kinds: dict[str, str], codes: dict[str, list[str]], cell=None) -> tuple[str, list]:
    """(a condition true for a row that breaks the rule, its parameters). `cell(column)`: (the cell trimmed of blanks, the cell as stored) as SQL expressions;
    by default they are worked out from the column itself. What holds is wrapped in COALESCE(..., 0): a test that comes out NULL (a date SQLite cannot read)
    counts as not holding, never as unknown."""
    cell = cell or (lambda column: (_trim(_quote(column)), _quote(column)))
    s, raw = cell(rule['column'])
    check = rule['check']
    if check == 'not_empty':
        return _empty(s), []
    if check in _OPS:
        holds, params = _holds(s, _OPS[check], rule['value'])
        return f"(NOT {_empty(s)} AND NOT COALESCE(CASE WHEN {_number(s)} THEN {holds} ELSE 0 END, 0))", params   # CASE: the comparison only ever sees a plain number
    if check == 'between':
        (low, low_params), (high, high_params) = _holds(s, '>=', rule['low']), _holds(s, '<=', rule['high'])
        return f"(NOT {_empty(s)} AND NOT COALESCE(CASE WHEN {_number(s)} THEN {low} AND {high} ELSE 0 END, 0))", [*low_params, *high_params]
    if check == 'in_codes':
        allowed = list(codes.get(rule['column']) or [])
        return (f"(NOT {_empty(s)} AND {raw} NOT IN ({', '.join('?' * len(allowed))}))" if allowed else f'(NOT {_empty(s)})'), allowed
    o = cell(rule['other'])[0]
    (v_ok, v_day), (o_ok, o_day) = _day(s, kinds[rule['column']]), _day(o, kinds[rule['other']])
    return f'(NOT {_empty(s)} AND NOT {_empty(o)} AND NOT COALESCE({v_ok} AND {o_ok} AND {v_day} >= {o_day}, 0))', []


def run(conn, table: str, rules: list[dict], kinds: dict[str, str], codes: dict[str, list[str]], key: list[str], examples: int = EXAMPLES, only: str | None = None) -> dict:
    """Count, in one pass over the table, the rows that break each rule, and fetch the key of up to `examples` of them per broken rule, in table order.
    `only`: a temporary table of the rowids a reader may see (column r); the rest are not read. {'rows_checked', 'query', 'rules': [{'broken', 'examples'}]}.
    Each column a rule reads is trimmed of blanks once per row, in a subquery SQLite reads row by row (LIMIT -1 OFFSET 0 keeps it from being merged into the
    outer query, which would trim the cell again for every test made on it)."""
    conn.create_function(EXACT, 2, _order, deterministic=True)
    within = f' WHERE rowid IN (SELECT r FROM temp.{_quote(only)})' if only else ''
    used = list(dict.fromkeys(c for rule in rules for c in sorted(columns_of(rule), key=lambda c: c != rule['column'])))
    alias = {c: (f'c{i}', f'v{i}') for i, c in enumerate(used)}
    picked = ['rowid AS r', *(f'{_quote(k)} AS k{j}' for j, k in enumerate(key)), *(f'{_trim(_quote(c))} AS {alias[c][0]}, {_quote(c)} AS {alias[c][1]}' for c in used)]
    rows = f'(SELECT {", ".join(picked)} FROM {_quote(table)}{within} ORDER BY rowid LIMIT -1 OFFSET 0)'
    conditions = [broken_sql(rule, kinds, codes, alias.__getitem__) for rule in rules]
    sums = ', '.join(f'COALESCE(SUM(CASE WHEN {sql} THEN 1 ELSE 0 END), 0)' for sql, _ in conditions)
    query = f'SELECT COUNT(*){", " + sums if sums else ""} FROM {rows}'
    counts = conn.execute(query, [p for _, params in conditions for p in params]).fetchone()
    found = []
    for (sql, params), broken in zip(conditions, counts[1:]):
        keys = [list(k) for k in conn.execute(f'SELECT {", ".join(f"k{j}" for j in range(len(key)))} FROM {rows} WHERE {sql} LIMIT ?', [*params, examples])] if broken and examples else []
        found.append({'broken': broken, 'examples': keys})
    return {'rows_checked': counts[0], 'query': query, 'rules': found}


# --- what a rule says --------------------------------------------------------------------------------------------------------------------------------

def _shown(number) -> str:
    return str(number)


def says(rule: dict, names: dict[str, str] | None = None) -> str:
    """The rule as one sentence, by the properties' names."""
    name = lambda c: (names or {}).get(c, c)
    c, check = name(rule['column']), rule['check']
    if check == 'not_empty':
        return tr(f'“{c}”不能为空', f'"{c}" must not be empty')
    if check == 'gt':
        return tr(f'“{c}”要大于 {_shown(rule["value"])}', f'"{c}" must be greater than {_shown(rule["value"])}')
    if check == 'ge':
        return tr(f'“{c}”要至少是 {_shown(rule["value"])}', f'"{c}" must be at least {_shown(rule["value"])}')
    if check == 'lt':
        return tr(f'“{c}”要小于 {_shown(rule["value"])}', f'"{c}" must be less than {_shown(rule["value"])}')
    if check == 'le':
        return tr(f'“{c}”要最多是 {_shown(rule["value"])}', f'"{c}" must be at most {_shown(rule["value"])}')
    if check == 'between':
        return tr(f'“{c}”要在 {_shown(rule["low"])} 到 {_shown(rule["high"])} 之间（含两端）', f'"{c}" must be between {_shown(rule["low"])} and {_shown(rule["high"])}, both included')
    if check == 'in_codes':
        return tr(f'“{c}”要是写了含义的代码之一', f'"{c}" must be one of the codes that have a meaning')
    return tr(f'“{c}”不能早于“{name(rule["other"])}”', f'"{c}" must not be before "{name(rule["other"])}"')


def note() -> str:
    """How the rules treat what is not a plain value, for the page."""
    return tr('空着的格子只算违反“不能为空”，其他规则不判断它；填了但不是数字的格子违反数字规则；不是真实日期的格子（例如 2026-02-30）违反日期规则；只有日期没有时间的，按当天开始算。'
              '有一条规则不满足，这个对象类型就不能确认；确认之后新数据违反了它，对象类型会退回“需要再看”。',
              'An empty cell breaks only "not empty"; other rules do not judge it. A filled cell that is not a number breaks a number rule, and one that is not a real date '
              '(such as 2026-02-30) breaks a date rule; a date without a time counts as the start of that day. While any rule is broken the object type cannot be confirmed; '
              'once it is confirmed, new data that breaks a rule sends it back for another look.')


def broken_text(rule_says: str, broken: int, rows: int, examples: list[list]) -> str:
    """The problem a broken rule is, for a refusal or the reason a type went back: which rule, how many rows of how many, the first few keys."""
    shown = tr('、', ', ').join(' + '.join(str(v) for v in k) for k in examples[:REASON_EXAMPLES])
    return tr(f'值规则{rule_says}：查了全部 {rows} 行，有 {broken} 行不满足{"，例如 " + shown if shown else ""}',
              f'The value rule {rule_says}: of all {rows} rows checked, {broken} break it{", for example " + shown if shown else ""}')
