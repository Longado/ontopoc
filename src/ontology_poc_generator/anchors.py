"""A confirmation remembers what it was confirmed on, so the next upload can tell whether it still holds.

A person who confirmed "2 = 已取消" looked at one table: three codes, 16 rows under 2. Next month's file may have the codes
shifted (1 becomes 2, 2 becomes 3). The confirmation then carries over under a new line of versions and the old label sits on
other rows. Each kind of confirmation therefore keeps anchors from the data it was confirmed on:

  code meaning   the values of the column with a count each; when the table has a key, a short hash of the key of every row under
                 each value (so the same rows can be found again whatever else changed), else a few rows per value
  repeat rule    the ids that repeated (the rule's `covers`, kept by repeated_keys.check_rule)
  named view     the rows it keeps, the rows of its table, and the dataset version of the table
  relation       per side, the rows, and how many found their object and how many did not

On a new upload each anchor is looked at again. One that still holds changes nothing. One that is broken moves the
confirmation to "checked" (element_state): the definition is kept, with a sentence on what changed ("上次 2 有 16 行，现在 2 有
48 行"), and nothing reads it as confirmed until a person looks again and confirms it as it is, or edits it.

A count is judged by its share of the table, not its size: a month with more rows is not a change. The two numbers below are
choices, not measurements: a share that grows to more than twice, or falls below half, and by at least five rows."""
from __future__ import annotations

from collections import Counter
import hashlib
from datetime import datetime, timezone

SHARE_FACTOR = 2
MIN_ROWS = 5
SAMPLES = 3        # rows kept per code value
EXAMPLES = 3
HASH_CHARS = 16     # 64 bits of a row key's hash: at 100,000 rows a 32-bit one lost about two of them to a clash
ID_LIMIT = 100_000   # a table with more rows keeps no row ids (they would weigh megabytes) and falls back on the sample rows
SWAP_SHARE_PERCENT = 30   # a code is read as swapped when at least this share of its rows still there now carry one other code


def moved(was_k: int, was_n: int, now_k: int, now_n: int) -> bool:
    """Did k of n rows become a different share of the table: more than SHARE_FACTOR times, or less than 1/SHARE_FACTOR, and by
    at least MIN_ROWS rows against what the old share would give at the new size."""
    if not was_n or not now_n:
        return False
    expected = was_k / was_n * now_n
    return abs(now_k - expected) >= MIN_ROWS and (now_k > SHARE_FACTOR * expected or now_k * SHARE_FACTOR < expected)


def _pct(k: int, n: int) -> str:
    return f'{k / n * 100:.0f}%' if n else '0%'


def _text(value) -> str:
    return '' if value is None else str(value)


def stored(anchors: dict | None, review: dict | None = None) -> dict:
    """What element_state keeps beside a definition: its anchors and, once it is waiting for a second look, what changed."""
    return {'anchors': anchors, **({'review': review} if review else {})}


def waiting(row: dict, changes: list[str], against: str) -> tuple:
    """The element_state change that takes a confirmed element to checked: the same definition and anchors, and what changed.
    `row` is workspace_store.element_rows' entry."""
    review = {'changes': changes, 'against': against, 'was_confirmed_by': row['confirmed_by'], 'was_confirmed_at': row['confirmed_at'],
              'found_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    return (row['element_id'], 'checked', row['evidence_ref'], row['confirmed_by'], row['content'], stored(row['anchors'], review))


# code meanings

def _row_id(record: dict, key: list[str]) -> str | None:
    parts = [_text(record.get(c)) for c in key]
    return '\x1f'.join(parts) if all(parts) else None


def _hash(text: str) -> str:
    return hashlib.blake2b(text.encode(), digest_size=8).hexdigest()


def _ids_by_code(records: list[dict], column: str, key: list[str]) -> dict[str, set[str]]:
    """{code: the hashes of the keys of its rows}; a key that is empty or sits on more than one row names no row and is left out."""
    seen: Counter = Counter()
    pairs = []
    for r in records:
        found = _row_id(r, key)
        if found is not None and r.get(column) not in (None, ''):
            h = _hash(found)
            seen[h] += 1
            pairs.append((str(r[column]), h))
    out: dict[str, set[str]] = {}
    for code, h in pairs:
        if seen[h] == 1:
            out.setdefault(code, set()).add(h)
    return out


def code_anchor(profile: dict, records: list[dict], key: list[str] | None = None) -> dict:
    """The column as it is now: its values with their rows; when `key` (the table's identity columns) is given and the table is not
    huge, the hash of each row's key under its value, so that a later upload can find the same rows and see what code they carry;
    and for each value the first SAMPLES rows (all other columns) for a table with no key."""
    column = profile['column']
    columns = [c for c in dict.fromkeys(k for r in records for k in r) if c != column]
    samples: dict[str, list] = {}
    for r in records:
        value = r.get(column)
        if value in (None, ''):
            continue
        got = samples.setdefault(str(value), [])
        if len(got) < SAMPLES:
            got.append({c: _text(r.get(c)) for c in columns})
    ids = _ids_by_code(records, column, key) if key and len(records) <= ID_LIMIT and all(any(c in r for r in records) for c in key) else None
    return {'kind': 'code', 'source': profile['source'], 'column': column, 'rows': profile['rows'], 'columns': columns,
            'values': {v['value']: v['rows'] for v in profile['values']}, 'samples': {} if ids else samples,
            **({'key': key, 'ids': {c: ''.join(sorted(h)) for c, h in ids.items()}} if ids else {})}


def _example(sample: dict, columns: list[str]) -> str:
    """The first filled column of a sample row, in the table's column order (the stored sample's own keys are sorted)."""
    column, value = next(((c, sample[c]) for c in columns if sample.get(c)), ('', ''))
    return f'{column} {value}' if column else '一行'


def check_code(anchor: dict, labels: dict[str, str], profile: dict | None, records: list[dict]) -> list[str]:
    """What is no longer as it was when these meanings were confirmed (empty: it holds). `labels` is {code: meaning} of the
    confirmed values, `profile` the column as code_meanings.code_columns finds it now (None when it is no longer a code column)."""
    column = anchor['column']
    if profile is None:
        if not any(column in r for r in records):
            return [f'表里现在没有「{column}」这一列']
        return [f'「{column}」现在不再像一列代码：有 {len({str(r[column]) for r in records if r.get(column) not in (None, "")})} 个不同的取值']
    now = {v['value']: v['rows'] for v in profile['values']}
    changes = []
    for value in sorted(v for v in labels if v in anchor['values']):
        if moved(anchor['values'][value], anchor['rows'], now.get(value, 0), profile['rows']):
            changes.append(f'上次 {value} 有 {anchor["values"][value]} 行（占 {_pct(anchor["values"][value], anchor["rows"])}），'
                           f'现在 {value} 有 {now.get(value, 0)} 行（占 {_pct(now.get(value, 0), profile["rows"])}）')
    new = [v for v in sorted(now) if v not in anchor['values']]
    if new:
        changes.append('多了取值 ' + '、'.join(f'{v}（{now[v]} 行）' for v in new))
    changes += _swapped(anchor, labels, records) if anchor.get('ids') else []
    index: dict[tuple, set] = {}
    for r in records:
        if r.get(column) not in (None, ''):
            index.setdefault(tuple(_text(r.get(c)) for c in anchor['columns']), set()).add(str(r[column]))
    different: Counter = Counter()
    example: dict = {}
    for value in sorted(labels):
        for sample in anchor['samples'].get(value, []):
            found = index.get(tuple(sample[c] for c in anchor['columns']))
            if found is not None and value not in found:
                pair = (value, '、'.join(sorted(found)))
                different[pair] += 1
                example.setdefault(pair, sample)
    for (value, now_codes), n in sorted(different.items()):
        changes.append(f'抽查的同一批行里，{n} 行上次是 {value}，现在是 {now_codes}（如{_example(example[(value, now_codes)], anchor['columns'])}）')
    gone = [v for v in sorted(labels) if v in anchor['values'] and v not in now]
    if changes and gone:
        changes.append('已有含义的取值现在一行都没有：' + '、'.join(gone))
    return changes


def _swapped(anchor: dict, labels: dict[str, str], records: list[dict]) -> list[str]:
    """Rows found again by their key (every row, not a sample): of the rows that carried a code that has a meaning, how many now carry
    one other code. At least MIN_ROWS of them, and at least SWAP_SHARE_PERCENT of the rows still there: a status that moves on for a few
    rows (an order delivered) is not a different meaning, a code that now sits on the rows another code sat on is."""
    column, key = anchor['column'], anchor['key']
    now = _ids_by_code(records, column, key)
    where = {h: code for code, hashes in now.items() for h in hashes}
    out = []
    for code in sorted(c for c in labels if c in anchor['ids']):
        was = [anchor['ids'][code][i:i + HASH_CHARS] for i in range(0, len(anchor['ids'][code]), HASH_CHARS)]
        here = [h for h in was if h in where]
        goes = Counter(where[h] for h in here if where[h] != code)
        for other, k in sorted(goes.items()):
            if k >= MIN_ROWS and k * 100 >= SWAP_SHARE_PERCENT * len(here):
                moved_rows = {h for h in here if where[h] == other}
                example = next((found for r in records if (found := _row_id(r, key)) is not None and _hash(found) in moved_rows), '')   # the first in the file
                out.append(f'按「{"、".join(key)}」对，上次是 {code} 的 {len(here)} 行里有 {k} 行现在是 {other}（如{"、".join(key)} {example.replace(chr(31), " ")}）')
    return out


# named views

def view_anchor(rows: int, source_rows: int, table: str, version: int | None) -> dict:
    return {'kind': 'view', 'rows': rows, 'source_rows': source_rows, 'table': table, 'version': version}


def check_view(anchor: dict, rows: int, source_rows: int, version: int | None) -> list[str]:
    if not moved(anchor['rows'], anchor['source_rows'], rows, source_rows):
        return []
    table = anchor['table']
    swapped = f'；「{table}」表从第 {anchor["version"]} 版换成了第 {version} 版' if anchor.get('version') and version and anchor['version'] != version else ''
    return [f'上次视图留下 {anchor["rows"]} 行（「{table}」共 {anchor["source_rows"]} 行里的 {_pct(anchor["rows"], anchor["source_rows"])}），'
            f'现在留下 {rows} 行（共 {source_rows} 行里的 {_pct(rows, source_rows)}）{swapped}']


# relations

def relation_anchor(check: dict) -> dict:
    """check: one entry of check_relations."""
    return {'kind': 'relation', 'sides': [{'end': s['end'], 'object': s['object'], 'rows': s['rows'], 'matched': s['matched'], 'unmatched': s['unmatched']} for s in check['sides']]}


def check_relation(anchor: dict, check: dict, label) -> list[str]:
    now = {s['end']: s for s in check['sides']}
    changes = []
    for was in anchor['sides']:
        side = now.get(was['end'])
        if side and moved(was['unmatched'], was['rows'], side['unmatched'], side['rows']):
            changes.append(f'{label(was["object"])}那一头：上次 {was["rows"]} 行里 {was["unmatched"]} 行找不到对应，现在 {side["rows"]} 行里 {side["unmatched"]} 行找不到')
    return changes


# the list a person reads

RULE_SAYS = {'keep_both': '每一行都留', 'data_error': '当作数据错误'}


def review_items(rows: dict[str, dict], named_views: dict, relations: dict[str, str], newer: str | None = None) -> list[dict]:
    """The elements waiting for a second look, as the page lists them. rows: {storage prefix: element_rows(..., 'checked')}
    for property, repeat_rule, view and relation; named_views the confirmed views by name (what reads a meaning); relations
    the readable name of each relation by key; newer the run of the line that is more recent than the one the page shows (it is
    looked at there, not here)."""
    out = []
    for field, row in sorted(rows['property'].items()):
        table, _, column = field.partition('.')
        meant = [f'{e["value"]} = {e["label"]}' for e in (row['content'] or {}).get('values', []) if e.get('label')]
        reading = [n for n, d in sorted(named_views.items()) if isinstance(d, dict) and d.get('kind') == 'filter' and d.get('base') == table and d.get('column') == column]
        out.append(_entry('property', 'code_meaning', field, f'「{table}」的「{column}」的含义：{"、".join(meant)}', row,
                          {'tab': 'data', 'table': table}, [f'视图「{n}」读它，现在读不了' for n in reading], newer))
    for name, row in sorted(rows['repeat_rule'].items()):
        source = name.partition('.')[2]
        rule = row['content'] or {}
        said = RULE_SAYS.get(rule.get('rule'), f'只留「{rule.get("column")}」最新的一行')
        out.append(_entry('repeat_rule', 'repeat_rule', name, f'「{source}」表重复编号的处理办法：{said}', row, {'tab': 'data', 'table': source}, [], newer))
    for name, row in sorted(rows['view'].items()):
        out.append(_entry('view', 'view', name, f'视图「{name}」', row, {'tab': 'data', 'table': (row['content'] or {}).get('base')}, [], newer))
    for name, row in sorted(rows['relation'].items()):
        out.append(_entry('relation', 'relation', name, f'关系「{relations.get(name, name)}」判过“对”', row, {'tab': 'objects', 'place': 'confirm'}, [], newer))
    return out


def _entry(prefix: str, kind: str, name: str, title: str, row: dict, target: dict, depends: list[str], newer: str | None) -> dict:
    review = row['review'] or {}
    return {'id': f'review:{prefix}:{name}', 'kind': kind, 'name': name, 'title': title, 'changes': review.get('changes', []),
            'confirmed_by': review.get('was_confirmed_by'), 'confirmed_at': review.get('was_confirmed_at'), 'found_at': review.get('found_at'),
            'against': review.get('against'), 'depends': depends, 'target': target, 'newer': newer}
