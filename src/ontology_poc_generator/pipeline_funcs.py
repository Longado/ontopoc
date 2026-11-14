"""The small functions a pipeline's SQL calls, registered on the SQLite connection that runs it: type conversion (字段转换), text clean-up (文本清理) and the exact
percentile. They are fixed code written here; nothing a person types is ever run. A conversion that cannot read a value returns null, and the operator that
asked for it counts those rows and lists them (a null here is never the end of the story: see pipeline_ops.cast)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import math
import re

_DECIMAL = re.compile(r'[+-]?(\d+(\.\d*)?|\.\d+)')
_INTEGER = re.compile(r'[+-]?\d+')
_ISO_DATE = re.compile(r'(\d{4})-(\d{2})-(\d{2})')
_ISO_DATETIME = re.compile(r'(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?')
MAX_DIGITS = 40   # a longer number is read as text, not converted (Python refuses to turn a very long digit string into an int)
TRUE_WORDS ={'true', 'y', 'yes', '是', 't', '1'}
FALSE_WORDS = {'false', 'n', 'no', '否', 'f', '0'}
DATE_FORMAT_TOKENS = (('YYYY', r'(?P<Y>\d{4})'), ('YY', r'(?P<y>\d{2})'), ('MM', r'(?P<m>\d{2})'), ('DD', r'(?P<d>\d{2})'), ('HH', r'(?P<H>\d{2})'),
                      ('mm', r'(?P<M>\d{2})'), ('ss', r'(?P<S>\d{2})'), ('M', r'(?P<m>\d{1,2})'), ('D', r'(?P<d>\d{1,2})'), ('H', r'(?P<H>\d{1,2})'))
GUESS_FORMATS = ('YYYY-MM-DD', 'YYYY/MM/DD', 'YYYY/M/D', 'YYYY.MM.DD', 'YYYYMMDD', 'MM/DD/YYYY', 'M/D/YYYY', 'DD/MM/YYYY', 'D/M/YYYY', 'YYYY年M月D日',
                 'YYYY-MM-DD HH:mm:ss', 'YYYY-MM-DD HH:mm', 'YYYY/MM/DD HH:mm:ss')


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def number_text(value) -> str | None:
    """A number as the text a dataset keeps it as: 12.0 is 12, 0.1 + 0.2 is 0.3, no exponent."""
    if value is None:
        return None
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return format(Decimal(repr(round(value, 10))), 'f')
    return str(value)


def to_bool(value) -> int | None:
    text = _text(value)
    if text is None:
        return None
    return 1 if text.lower() in TRUE_WORDS else 0 if text.lower() in FALSE_WORDS else None


def to_decimal(value, thousands=0) -> float | None:
    text = _text(value)
    if not text:
        return None
    if thousands:
        text = text.replace(',', '')
    return float(text) if len(text) <= MAX_DIGITS and _DECIMAL.fullmatch(text) else None


def to_integer(value, thousands=0) -> int | None:
    text = _text(value)
    if not text:
        return None
    if thousands:
        text = text.replace(',', '')
    return int(text) if len(text) <= MAX_DIGITS and _INTEGER.fullmatch(text) else None


def format_regex(fmt: str) -> re.Pattern:
    """A date format written as YYYY-MM-DD, M/D/YYYY, YYYY年M月D日, YYYY-MM-DD HH:mm:ss, as a pattern with the parts named. ValueError when it has no year,
    month and day, or repeats a part."""
    pattern, i, seen = '', 0, []
    while i < len(fmt):
        for token, regex in DATE_FORMAT_TOKENS:
            if fmt.startswith(token, i):
                seen.append(regex[regex.index('<') + 1])
                pattern += regex
                i += len(token)
                break
        else:
            pattern += re.escape(fmt[i])
            i += 1
    if len(set(seen)) != len(seen):
        raise ValueError('格式里同一个部分写了两次')
    if not ({'Y', 'm', 'd'} <= set(seen) or {'y', 'm', 'd'} <= set(seen)):
        raise ValueError('格式里要有年、月、日：YYYY（或 YY）、MM（或 M）、DD（或 D）')
    return re.compile(pattern)


def _parse_with(text: str, pattern: re.Pattern) -> datetime | None:
    m = pattern.fullmatch(text)
    if not m:
        return None
    g = m.groupdict()
    year = int(g['Y']) if g.get('Y') else 2000 + int(g['y'])
    try:
        return datetime(year, int(g['m']), int(g['d']), int(g.get('H') or 0), int(g.get('M') or 0), int(g.get('S') or 0))
    except ValueError:
        return None


def _iso(text: str) -> datetime | None:
    for pattern in (_ISO_DATETIME, _ISO_DATE):
        m = pattern.fullmatch(text)
        if m:
            parts = [int(p) for p in m.groups() if p is not None]
            try:
                return datetime(*parts)
            except ValueError:
                return None
    return None


_PATTERNS: dict[str, re.Pattern] = {}


def _read_date(value, fmt) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    if fmt is None:
        return _iso(text)
    if fmt not in _PATTERNS:
        _PATTERNS[fmt] = format_regex(fmt)
    return _parse_with(text, _PATTERNS[fmt])


def to_date(value, fmt=None) -> str | None:
    moment = _read_date(value, fmt)
    return None if moment is None else moment.date().isoformat()


def to_datetime(value, fmt=None) -> str | None:
    moment = _read_date(value, fmt)
    return None if moment is None else moment.strftime('%Y-%m-%d %H:%M:%S')


def guess_formats(examples: list[str]) -> list[dict]:
    """For each known date format, how many of the examples it reads: [{'format', 'parsed', 'of', 'failed': [the first few it could not read]}], best first."""
    examples = [e for e in examples if isinstance(e, str) and e.strip()]
    out = []
    for fmt in GUESS_FORMATS:
        pattern = format_regex(fmt)
        failed = [e for e in examples if _parse_with(e.strip(), pattern) is None]
        out.append({'format': fmt, 'parsed': len(examples) - len(failed), 'of': len(examples), 'failed': failed[:5]})
    return sorted(out, key=lambda r: (-r['parsed'], GUESS_FORMATS.index(r['format'])))


class Percentile:
    """The exact percentile of the numbers in a group, by linear interpolation between the two nearest ranks (the median of 1, 2, 3, 4 is 2.5). Nulls are
    skipped by SQL before they get here; a group of only nulls has no value."""

    def __init__(self):
        self.values: list[float] = []
        self.p = None

    def step(self, value, p):
        if value is not None:
            self.values.append(float(value))
        self.p = p

    def finalize(self):
        if not self.values:
            return None
        ordered = sorted(self.values)
        at = (len(ordered) - 1) * self.p
        low, high = math.floor(at), math.ceil(at)
        return ordered[low] + (ordered[high] - ordered[low]) * (at - low)


def _clean_whitespace(value):
    return None if value is None else re.sub(r'\s+', ' ', str(value)).strip()


def _replace(value, find, with_):
    return None if value is None else str(value).replace(find, with_)


def _regex(value, pattern, with_):
    return None if value is None else re.sub(pattern, lambda m: with_, str(value))


def register(conn) -> None:
    """Make the functions known to this connection (a read-only one included: they change nothing)."""
    for name, args, fn in (('pl_bool', 1, to_bool), ('pl_text', 1, number_text), ('pl_to_decimal', 2, to_decimal), ('pl_to_integer', 2, to_integer),
                           ('pl_to_boolean', 1, to_bool), ('pl_to_date', 2, to_date), ('pl_to_datetime', 2, to_datetime),
                           ('pl_trim', 1, lambda v: None if v is None else str(v).strip()), ('pl_ws', 1, _clean_whitespace),
                           ('pl_upper', 1, lambda v: None if v is None else str(v).upper()), ('pl_lower', 1, lambda v: None if v is None else str(v).lower()),
                           ('pl_replace', 3, _replace), ('pl_regex', 3, _regex)):
        conn.create_function(name, args, fn, deterministic=True)
    conn.create_aggregate('pl_pct', 2, Percentile)
