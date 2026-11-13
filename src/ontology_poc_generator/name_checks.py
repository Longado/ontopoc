"""Does a column do what its name says? A column named 交付天数P50 claims to be the median of 交付天数; where the rows it was
worked out from are in another table, code works the statistic out again and compares, row by row.

  claim    the statistic the name says: P50 / 中位数 / median, P90 (any P and a number), 平均 / 均值 / avg / mean, 合计 / 总计 / sum / total,
           最大 / max, 最小 / min, in Chinese or in English words (days_avg, total_amount too). A name that says more than one, or
           none, claims nothing, and its values are not even read.
  source   the rows to work it out from: the column named like the claimed column without the statistic (交付天数) in another table,
           whose rows name the same objects by the same identity (the object 产品 is told apart by 产品编号 in both tables, as the
           draft's populations say). A table that has no such column is not guessed at; when two tables have it, the finding says
           which two (`candidates`) and the open item asks which one.
  compare  per row of the claiming table: the value written, the value worked out from the rows that name it, and whether the
           written value is the worked out one rounded to the precision it is written in (11.5 written as 12 agrees, as 11 does
           not; a whole number in a column that has decimals elsewhere is read at that column's precision). The median is the
           standard one, whether the name says 中位数, median or P50: the middle value, or the mean of the two middle ones, and
           nothing else. Any other percentile (P90) may be written by interpolation or by nearest rank; the finding says which.
           The other
           statistics are worked out too, so the finding can say which one the column really is. Source values that are not
           numbers (12天, N/A, nan) are counted and shown, not left out unseen; the same for non-numbers written in the claiming
           column itself. A statistic that does not agree over the whole
           table but does over a confirmed view of it (有效订单 keeps the orders that were not cancelled) is told as that
           (`view`), not as a mismatch.

The model is not asked: the name says the claim and the draft says the link between the tables. Every number comes from the rows."""
from __future__ import annotations

import math
import re
import statistics
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Context, Decimal

from ontology_poc_generator.public_ontology import normalize_proposal, normalize_value

STAT_WORDS = {'median': '中位数', 'mean': '平均数', 'sum': '合计', 'max': '最大值', 'min': '最小值'}
METHOD_WORDS = {'interpolation': '插值', 'nearest_rank': '最近秩'}
_PERCENT = re.compile(r'(?<![A-Za-z])P(\d{1,2})(?!\d)', re.I)
_word = lambda w: rf'(?<![A-Za-z]){w}(?![A-Za-z])'   # \b does not stop at "_": days_avg, total_amount
_WORDS = {'median': re.compile(rf'中位数|中位|{_word("median")}', re.I),
          'mean': re.compile(rf'平均数|平均值|平均|均值|{_word("avg")}|{_word("average")}|{_word("mean")}', re.I),
          'sum': re.compile(rf'合计|总计|总和|{_word("sum")}|{_word("total")}', re.I),
          'max': re.compile(rf'最大值|最大|最高值|最高|{_word("max")}|{_word("maximum")}', re.I),
          'min': re.compile(rf'最小值|最小|最低值|最低|{_word("min")}|{_word("minimum")}', re.I)}
_EDGES = ' _-—:：()（）的'
UNREADABLE_SHOWN = 3
WIDE = Context(prec=800)   # a float is at most 309 digits before the point; the default 28 cannot round 1e30 to a unit


def _percentile(values: list[float], q: float) -> float:
    """Linear interpolation between the closest ranks (the median of an even count is the mean of the two in the middle)."""
    ordered = sorted(values)
    at = (len(ordered) - 1) * q / 100
    low = int(at)
    return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (at - low)


def _nearest_rank(values: list[float], q: float) -> float:
    return sorted(values)[max(math.ceil(q / 100 * len(values)), 1) - 1]


def _stat(kind: str, values: list[float]) -> float:
    if kind.startswith('p'):
        return _percentile(values, int(kind[1:]))
    try:
        return {'median': statistics.median, 'mean': statistics.fmean, 'sum': sum, 'max': max, 'min': min}[kind](values)
    except OverflowError:   # fmean of values near the largest float
        return math.inf


def claim_of(column: str) -> tuple[str, str, str] | None:
    """(statistic, how the name says it, the name without it) for a column name that claims one statistic, else None.
    The statistic is 'p<N>' for a percentile, with P50 the median."""
    found = [(m.group(0), 'median' if m.group(1) == '50' else f'p{int(m.group(1))}') for m in _PERCENT.finditer(column) if 0 < int(m.group(1)) < 100]
    found += [(m.group(0), kind) for kind, pattern in _WORDS.items() for m in pattern.finditer(column)]
    kinds = {kind for _, kind in found}
    if len(kinds) != 1:
        return None
    said, kind = found[0]
    base = column.replace(said, '', 1).strip(_EDGES)
    return (kind, said, base) if len(base) >= 2 else None


def _read(value) -> tuple[float | None, bool]:
    """(the number, False); (None, False) for a blank; (None, True) for text that is not a finite number (12天, N/A, nan)."""
    if normalize_value(value) is None:
        return None, False
    try:
        number = float(str(value).replace(',', ''))
    except ValueError:
        return None, True
    return (number, False) if math.isfinite(number) else (None, True)


def _decimals(texts: list[str]) -> int:
    return max((len(t.partition('.')[2]) for t in texts if '.' in t), default=0)


def _written_as(text, computed: float, floor: int) -> bool:
    """Is `text` the worked out value rounded to the precision `text` is written in: its own decimals, or `floor` (the most any
    value of the column has) for a whole number? A half-way value may have been rounded up or to even."""
    text = str(text).replace(',', '').strip()
    places = len(text.partition('.')[2]) if '.' in text else floor
    try:   # a value too large or too long to round (1e30 at 800 digits of room, inf) is not one that agrees
        written, exact, unit = Decimal(text), Decimal(repr(round(computed, 9))), Decimal(1).scaleb(-places, WIDE)
        return written in (exact.quantize(unit, ROUND_HALF_UP, WIDE), exact.quantize(unit, ROUND_HALF_EVEN, WIDE))
    except ArithmeticError:
        return False


def _homes(t: dict, table: str, logical: list, base: str, sources: dict) -> list[tuple]:
    """(table, its identity columns) for each other table that names the same objects by the same identity and has a column
    called what the claimed column measures."""
    homes = [(pop['source'], tuple(pop['identity'][k] for k in logical)) for pop in t['populated_from']
             if pop['source'] != table and pop['source'] in sources and pop['transform'] == 'none' and set(pop['identity']) == set(logical)
             and base in {k for r in sources[pop['source']]['records'] for k in r}]
    return list(dict.fromkeys(homes))


def _groups(records: list[dict], source_by, base: str, only=None) -> tuple[dict, int, list]:
    """{key: the numbers of the rows that name it}, how many values are not numbers and the first few of them. `only`: the
    positions (from 1) of the rows to read, for a view."""
    groups: dict[tuple, list[float]] = {}
    unreadable, shown = 0, []
    for i, r in enumerate(records, 1):
        if only is not None and i not in only:
            continue
        v, bad = _read(r.get(base))
        if bad:
            unreadable += 1
            if len(shown) < UNREADABLE_SHOWN and str(r.get(base)) not in shown:
                shown.append(str(r.get(base)))
        key = tuple(normalize_value(r.get(c)) for c in source_by)
        if v is not None and all(key):
            groups.setdefault(key, []).append(v)
    return groups, unreadable, shown


def _compare(records, column, by, groups, kind, percent, floor) -> tuple[list, int, int]:
    """One entry per row of the claiming table with a value and a key; how many such rows no source row names; and how many have
    source rows whose statistic is too large to be a number (a sum of 1e308 and 1e308), which cannot be compared."""
    rows, no_source, too_large = [], 0, 0
    for r in records:
        written, _ = _read(r.get(column))
        key = tuple(normalize_value(r.get(c)) for c in by)
        if written is None or not all(key):
            continue
        found = groups.get(key)
        if not found:
            no_source += 1
            continue
        text = r.get(column)
        computed = {k: _stat(k, found) for k in (kind, *[x for x in STAT_WORDS if x != kind])}
        if not all(math.isfinite(v) for v in computed.values()):
            too_large += 1
            continue
        ranked = _nearest_rank(found, percent) if percent else None
        methods = [m for m, v in (('interpolation', computed[kind]), ('nearest_rank', ranked)) if v is not None and _written_as(text, v, floor)]
        rows.append({'key': ' + '.join(str(k) for k in key), 'written': written, 'rows': len(found),
                     'computed': {k: round(v, 4) for k, v in computed.items()}, **({'ranked': round(ranked, 4)} if percent else {}),
                     'agrees': bool(methods) if percent else _written_as(text, computed[kind], floor), 'methods': methods,
                     'agrees_with': [k for k, v in computed.items() if _written_as(text, v, floor)]})
    return rows, no_source, too_large


def _one_method(rows: list[dict]) -> str | None:
    """The way a percentile was written when every row agrees with it: interpolation first, else nearest rank."""
    return next((m for m in METHOD_WORDS if rows and all(m in x['methods'] for x in rows)), None)


def _by_view(records, column, by, source_records, source, source_by, base, kind, percent, floor, subsets, whole) -> str | None:
    """The name of the one confirmed view of the source table over which the claimed statistic holds: every row compared over the
    whole table (`whole`) either agrees over the view or has no rows in it and is written as 0 (a total of nothing; a blank or a
    non-number is not compared anywhere), and at least one agrees. A view that keeps the rows of one product out of three says
    nothing about the other two."""
    for name, kept in sorted((subsets(source) or {}).items()):
        groups, _, _ = _groups(source_records, source_by, base, only=kept)
        rows, _, _ = _compare(records, column, by, groups, kind, percent, floor)
        agreeing = {x['key'] for x in rows if x['agrees']}
        outside = [x for x in whole if x['key'] not in {r['key'] for r in rows}]
        if agreeing and len(agreeing) == len(rows) and all(x['written'] == 0 for x in outside):
            return name
    return None


def name_vs_calculation(ontology: dict, bundle: dict) -> list[dict]:
    """One finding per column whose name claims a statistic of rows found in another table:
    {'table', 'column', 'says': the claimed statistic, 'said': the words in the name, 'source', 'source_column', 'by': [the
    claiming table's key columns], 'rows': [{'key', 'written', 'computed': {statistic: value}, 'rows': how many source rows, 'agrees'}],
    'mismatched', 'compared', 'no_source' (rows no source row names), 'too_large' (rows whose worked out statistic is too large to be a
    number), 'actual': the one statistic every compared row agrees with, or
    None, 'method' (a percentile other than the median: how it was written, when every row agrees), 'unreadable' and 'unreadable_shown' (source
    values that are not numbers), 'written_unreadable' and 'written_unreadable_shown' (the same in the claiming column), 'view' (the confirmed view over which the claim holds, when it does not over the table)}.
    A finding with 'candidates' (the tables it could be worked out from) has no rows: it could not choose. A column that agrees
    on every compared row is a finding too (a person may want to see that it was checked); callers that ask what to settle
    keep those with mismatched > 0 and no view.
    The claim is read from the name before any value is: a table with no claiming column costs nothing. Worked out once per
    bundle: when it holds a 'calc_memo' dict the result is kept in it, for as long as 'views_signature()' (what the confirmed views
    and the stored tables are at) stays the same; when it holds 'subsets' (source -> {view name: positions of the rows the view
    keeps}) a mismatch is looked for in the confirmed views."""
    memo = bundle.get('calc_memo')
    signature = bundle['views_signature']() if memo is not None and bundle.get('views_signature') else None
    if memo is not None and 'findings' in memo and memo.get('signature') == signature:
        return memo['findings']
    p = normalize_proposal(ontology)
    sources = bundle['sources']
    out = []
    for t in p['object_types']:
        for here in (pop for pop in t['populated_from'] if pop['transform'] == 'none' and pop['source'] in sources):
            table, records = here['source'], sources[here['source']]['records']
            logical = sorted(here['identity'])
            by = [here['identity'][k] for k in logical]
            for column in dict.fromkeys(k for r in records for k in r):
                claim = claim_of(column)
                if claim is None or column in by:
                    continue
                values = [_read(r.get(column)) for r in records]
                if not any(v is not None for v, _ in values):
                    continue
                kind, said, base = claim
                percent = int(kind[1:]) if kind.startswith('p') else None   # the median is not read by percentile: no nearest rank
                homes = _homes(t, table, logical, base, sources)
                head = {'table': table, 'column': column, 'says': kind, 'said': said, 'source_column': base, 'by': by}
                if len(homes) > 1:
                    out.append({**head, 'candidates': [s for s, _ in homes], 'rows': [], 'compared': 0, 'mismatched': 0, 'no_source': 0, 'too_large': 0, 'actual': None,
                                'method': None, 'unreadable': 0, 'unreadable_shown': [], 'view': None, 'written_unreadable': 0, 'written_unreadable_shown': []})
                    continue
                if not homes:
                    continue
                source, source_by = homes[0]
                groups, unreadable, shown = _groups(sources[source]['records'], source_by, base)
                floor = _decimals([str(r.get(column)) for r, (v, _) in zip(records, values) if v is not None])
                rows, no_source, too_large = _compare(records, column, by, groups, kind, percent, floor)
                if not rows:
                    continue
                every = set.intersection(*(set(x['agrees_with']) for x in rows))
                mismatched = sum(not x['agrees'] for x in rows)
                subsets = bundle.get('subsets')
                view = _by_view(records, column, by, sources[source]['records'], source, source_by, base, kind, percent, floor, subsets, rows) if mismatched and subsets else None
                said_bad = list(dict.fromkeys(str(r.get(column)) for r, (_, bad) in zip(records, values) if bad))
                out.append({**head, 'source': source, 'rows': rows, 'compared': len(rows), 'mismatched': mismatched, 'no_source': no_source, 'too_large': too_large,
                            'written_unreadable': sum(bad for _, bad in values), 'written_unreadable_shown': said_bad[:UNREADABLE_SHOWN],
                            'actual': next((k for k in STAT_WORDS if k in every and k != kind), None),
                            'method': _one_method(rows) if percent else None, 'unreadable': unreadable, 'unreadable_shown': shown, 'view': view})
    if memo is not None:
        memo['findings'], memo['signature'] = out, signature
    return out
