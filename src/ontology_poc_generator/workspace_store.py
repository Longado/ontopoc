"""The workspace: one SQLite file holding every imported table row, the types read from them, and every check run.

Import never loses a row quietly: rows are stored as real SQL tables (one per dataset version, every value kept as the
text it was read as), the count written is checked against the count received, and rows the file reader dropped
(blank lines, title lines) are counted with their reason, so rows in the file = rows stored + rows dropped. A check records the query it ran
and how many rows it looked at, so a later stage can show the evidence behind a definition.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
import sqlite3

from ontology_poc_generator.public_ontology import normalize_proposal

VALUE_COUNT_LIMIT = 20   # a column with more distinct values than this keeps no value counts
SAMPLE_LIMIT = 5
_BOOLEAN_PAIRS = ({'true', 'false'}, {'是', '否'}, {'y', 'n'}, {'yes', 'no'})
_INTEGER = re.compile(r'-?\d+', re.ASCII)   # ASCII only: fullwidth and Arabic-Indic digits are text, a later cast would fail
_DECIMAL = re.compile(r'-?\d+\.\d+', re.ASCII)
_LEADING_ZERO = re.compile(r'-?0\d', re.ASCII)   # 007 is a code, not a number
_MONTH = re.compile(r'\d{4}-(0[1-9]|1[0-2])', re.ASCII)
_ISO_DATE = re.compile(r'\d{4}-\d{2}-\d{2}', re.ASCII)
_ISO_DATETIME = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?', re.ASCII)

SCHEMA = '''
CREATE TABLE IF NOT EXISTS dataset (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL, origin TEXT, file_sha256 TEXT NOT NULL,
    rows_in INTEGER NOT NULL, rows_stored INTEGER NOT NULL, table_name TEXT NOT NULL, imported_at TEXT NOT NULL,
    dropped_json TEXT, who TEXT, mode TEXT, changes_json TEXT, UNIQUE (name, version));
CREATE TABLE IF NOT EXISTS current_dataset (name TEXT PRIMARY KEY, dataset_id INTEGER NOT NULL REFERENCES dataset(id));
CREATE TABLE IF NOT EXISTS "column" (
    dataset_id INTEGER NOT NULL REFERENCES dataset(id), name TEXT NOT NULL, position INTEGER NOT NULL,
    inferred_type TEXT NOT NULL, distinct_count INTEGER NOT NULL, missing_count INTEGER NOT NULL,
    value_counts_json TEXT, PRIMARY KEY (dataset_id, name));
CREATE TABLE IF NOT EXISTS element_state (
    element_id TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK (state IN ('proposed', 'checked', 'confirmed', 'rejected')),
    evidence_ref TEXT, confirmed_by TEXT, confirmed_at TEXT, version INTEGER NOT NULL, content_json TEXT, anchors_json TEXT);
CREATE TABLE IF NOT EXISTS check_result (
    id INTEGER PRIMARY KEY, element_id TEXT NOT NULL, check_type TEXT NOT NULL, query TEXT NOT NULL,
    rows_checked INTEGER, violations INTEGER, samples_json TEXT, dataset_id INTEGER, null_key_rows INTEGER,
    status TEXT NOT NULL CHECK (status IN ('passed', 'failed', 'error', 'skipped')),
    checked_at TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS log (
    time TEXT NOT NULL, who TEXT NOT NULL, element_id TEXT, change TEXT NOT NULL, before_json TEXT, after_json TEXT);
'''


class RowCountMismatch(RuntimeError):
    """The rows written are not the rows received; the message names the table and is shown to the person."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def open_workspace(path) -> sqlite3.Connection:
    """Open (creating if needed) the workspace file; ':memory:' for a throwaway one. Transactions are explicit."""
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.executescript(SCHEMA)
    for table, column in (('dataset', 'dropped_json'), ('dataset', 'who'), ('dataset', 'mode'), ('dataset', 'changes_json'), ('check_result', 'dataset_id'), ('check_result', 'null_key_rows'),
                          ('element_state', 'content_json'), ('element_state', 'anchors_json')):
        if column not in {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}:   # a file made before the column existed
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {"INTEGER" if column in ("dataset_id", "null_key_rows") else "TEXT"}')
    conn.execute('INSERT OR IGNORE INTO current_dataset SELECT name, id FROM dataset WHERE version = '
                 '(SELECT MAX(version) FROM dataset d WHERE d.name = dataset.name)')
    return conn


def records_sha256(records: list[dict]) -> str:
    """Fingerprint of a table's content, so the same rows imported twice are recognised as the same version."""
    return hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def infer_type(values: list[str | None]) -> str:
    """One column's type from all of its values. A number is never read as boolean: 0/1/2 stay integers."""
    present = [v for v in values if v is not None]
    if not present:
        return 'text'
    distinct = set(present)
    lowered = {v.lower() for v in distinct}
    if lowered in _BOOLEAN_PAIRS:   # both values of a pair: a column holding only "Y" says nothing about N
        return 'boolean'
    if all(_INTEGER.fullmatch(v) and not _LEADING_ZERO.match(v) for v in distinct):
        return 'integer'
    if all((_INTEGER.fullmatch(v) or _DECIMAL.fullmatch(v)) and not _LEADING_ZERO.match(v) for v in distinct):
        return 'decimal'
    if all(_MONTH.fullmatch(v) for v in distinct):
        return 'month'
    # a datetime column has midnight values read back as bare dates, so one with both is still a datetime
    if all(_ISO_DATE.fullmatch(v) and _parses(date.fromisoformat, v) for v in distinct):
        return 'date'
    if all(_ISO_DATETIME.fullmatch(v) and _parses(datetime.fromisoformat, v) or
           _ISO_DATE.fullmatch(v) and _parses(date.fromisoformat, v) for v in distinct):
        return 'datetime'
    return 'text'


def _parses(parse, value: str) -> bool:
    try:
        parse(value)
    except ValueError:
        return False
    return True


def _describe(values: list[str | None]) -> dict:
    counts: dict[str, int] = {}
    for v in values:
        if v is not None:
            counts[v] = counts.get(v, 0) + 1
    return {'inferred_type': infer_type(values), 'distinct_count': len(counts), 'missing_count': values.count(None),
            'value_counts_json': json.dumps(dict(sorted(counts.items(), key=lambda kv: -kv[1])), ensure_ascii=False)
            if len(counts) <= VALUE_COUNT_LIMIT else None}


def _log(conn, who: str, element_id: str | None, change: str, before=None, after=None) -> None:
    conn.execute('INSERT INTO log(time, who, element_id, change, before_json, after_json) VALUES (?, ?, ?, ?, ?, ?)',
                 (_now(), who, element_id, change, None if before is None else json.dumps(before, ensure_ascii=False),
                  None if after is None else json.dumps(after, ensure_ascii=False)))


def _logged(row: dict) -> dict:
    """A row of element_state as the log keeps it: the anchors (megabytes of row hashes for a big table) as their size and a short
    fingerprint, not copied."""
    anchors = row.get('anchors_json')
    return {**row, 'anchors_json': None if anchors is None else f'{len(anchors)} bytes, sha256 {hashlib.sha256(anchors.encode()).hexdigest()[:12]}'}


def _evidence(conn, ref: str | None) -> tuple[frozenset, str]:
    """What a saved evidence reference says, by content: for each check it names, the table and key columns checked
    (inside the element id), the kind of check and what it found; and the latest time any of them ran. Each upload runs
    its checks again under new ids, so two references are the same evidence when their findings are the same."""
    ids = [int(r.split(':')[1]) for r in (ref or '').split(',') if r.startswith('check_result:')]
    rows = [conn.execute('SELECT element_id, check_type, status, violations, null_key_rows, checked_at FROM check_result WHERE id = ?', (i,)).fetchone()
            for i in ids]
    rows = [r for r in rows if r]
    return frozenset(r[:5] for r in rows), max((r[5] for r in rows), default='')


@contextmanager
def element_state_writes(conn, changes: list[tuple]):
    """Record what a person decided about definitions, all or none, and hold the transaction open for the caller: the
    rows are written but only kept when the block ends without an error, so whatever else must be saved with them (the
    run file) can fail first and take the rows back. Each change is (element_id, state, evidence_ref, confirmed_by) and
    optionally a fifth, the definition confirmed (a dict kept as JSON: the meanings of a code column) and a sixth, what it was
    confirmed on and what has changed since (anchors.stored: kept as JSON beside it). state is checked when the data it was
    confirmed on no longer looks the same: the definition is kept but is not confirmed until a person looks again. state is
    confirmed, rejected, or proposed (taken back); evidence_ref names what backed it ('check_result:12,check_result:13',
    or 'open_item:<id>'); confirmed_by is the person (None when they did not sign). version counts real
    changes: the same state, person, definition and evidence (compared by what the checks found, not by their ids) leaves the row,
    its time and its version as they were. Evidence from an older run never replaces newer evidence already kept.
    Yields each element's row as it stands."""
    conn.execute('BEGIN IMMEDIATE')   # the write lock now: a transaction that reads first and writes later is refused at once, not waited for, when another holds it
    try:
        for element_id, state, evidence_ref, confirmed_by, *rest in changes:
            content = json.dumps(rest[0], ensure_ascii=False, sort_keys=True) if rest and rest[0] is not None else None
            anchors = json.dumps(rest[1], ensure_ascii=False, sort_keys=True) if len(rest) > 1 and rest[1] is not None else None
            cursor = conn.execute('SELECT * FROM element_state WHERE element_id = ?', (element_id,))
            found = cursor.fetchone()
            before = dict(zip([c[0] for c in cursor.description], found)) if found else None
            if before:
                kept, kept_at = _evidence(conn, before['evidence_ref'])
                given, given_at = _evidence(conn, evidence_ref)
                if given_at and kept_at > given_at:
                    evidence_ref, given = before['evidence_ref'], kept   # this run is older than the evidence on file
                if (before['state'], before['confirmed_by'], before['content_json'], before['anchors_json'], kept) == (state, confirmed_by, content, anchors, given):
                    continue
            after = {'state': state, 'evidence_ref': evidence_ref, 'confirmed_by': confirmed_by, 'confirmed_at': _now(),
                     'version': before['version'] + 1 if before else 1, 'content_json': content, 'anchors_json': anchors}
            conn.execute('INSERT OR REPLACE INTO element_state(element_id, state, evidence_ref, confirmed_by, confirmed_at, version, content_json, anchors_json)'
                         ' VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (element_id, *after.values()))
            _log(conn, confirmed_by or '未署名', element_id, state, before=before and _logged({k: before[k] for k in after}), after=_logged(after))
        rows = {}
        for element_id, *_ in changes:
            cursor = conn.execute('SELECT * FROM element_state WHERE element_id = ?', (element_id,))
            rows[element_id] = dict(zip([c[0] for c in cursor.description], cursor.fetchone()))
        yield rows
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise


def set_element_states(conn, changes: list[tuple]) -> dict[str, dict]:
    """element_state_writes with nothing else to save: the rows are kept straight away."""
    with element_state_writes(conn, changes) as rows:
        return rows


def element_contents(conn, prefix: str) -> dict[str, dict]:
    """The confirmed definitions on file under this prefix, keyed by what follows it: the content with who confirmed it,
    when, and which version."""
    return {element_id[len(prefix):]: {**json.loads(content), 'confirmed_by': by, 'confirmed_at': at, 'version': version}
            for element_id, content, by, at, version in conn.execute(
                "SELECT element_id, content_json, confirmed_by, confirmed_at, version FROM element_state "
                "WHERE substr(element_id, 1, ?) = ? AND state = 'confirmed' AND content_json IS NOT NULL", (len(prefix), prefix))}


def store_anchors(conn, element_id: str, anchors: dict) -> None:
    """Attach anchors (anchors.stored) to an element that has none, as they were worked out from the rows an earlier run kept. Nothing
    else about the element changes: not its state, its person, its time or its version."""
    conn.execute('UPDATE element_state SET anchors_json = ? WHERE element_id = ? AND anchors_json IS NULL',
                 (json.dumps(anchors, ensure_ascii=False, sort_keys=True), element_id))


def element_rows(conn, prefix: str, state: str) -> dict[str, dict]:
    """The elements under this prefix in this state, keyed by what follows it: {'element_id', 'content' (the definition, or None),
    'anchors' (what it was confirmed on), 'review' (what changed, for a checked one), 'confirmed_by', 'confirmed_at', 'version',
    'evidence_ref'}."""
    out = {}
    for element_id, content, anchored, by, at, version, evidence in conn.execute(
            'SELECT element_id, content_json, anchors_json, confirmed_by, confirmed_at, version, evidence_ref FROM element_state '
            'WHERE substr(element_id, 1, ?) = ? AND state = ?', (len(prefix), prefix, state)):
        stored = json.loads(anchored) if anchored else {}
        out[element_id[len(prefix):]] = {'element_id': element_id, 'content': json.loads(content) if content else None, 'anchors': stored.get('anchors'),
                                         'review': stored.get('review'), 'confirmed_by': by, 'confirmed_at': at, 'version': version, 'evidence_ref': evidence}
    return out


def element_rejected(conn, prefix: str) -> set[str]:
    """What follows the prefix, for every element under it that a person rejected."""
    return {element_id[len(prefix):] for (element_id,) in conn.execute(
        "SELECT element_id FROM element_state WHERE substr(element_id, 1, ?) = ? AND state = 'rejected'", (len(prefix), prefix))}


def element_ids(conn, prefix: str) -> list[str]:
    """Every element id on file that starts with this prefix."""
    return [r[0] for r in conn.execute("SELECT element_id FROM element_state WHERE substr(element_id, 1, ?) = ?", (len(prefix), prefix))]


def _dataset(conn, where: str, args: tuple) -> dict | None:
    cursor = conn.execute(f'SELECT * FROM dataset WHERE {where}', args)
    row = cursor.fetchone()
    return dict(zip([c[0] for c in cursor.description], row)) if row else None


def current_dataset(conn, name: str) -> dict | None:
    """The version the person last uploaded under this name: not necessarily the highest number, because uploading
    older content again makes that older version current."""
    return _dataset(conn, 'id = (SELECT dataset_id FROM current_dataset WHERE name = ?)', (name,))


def _unique_names(records) -> list[str]:
    """Column names in first-seen order; a name equal to an earlier one apart from case gets _2, _3 (SQLite names are
    case-insensitive)."""
    stored: list[str] = []
    for key in dict.fromkeys(k for r in records for k in r):
        name, n = key, 1
        while name.lower() in {x.lower() for x in stored}:
            n += 1
            name = f'{key}_{n}'
        stored.append(name)
    return stored


def import_records(conn, name: str, records, origin: str, file_sha256: str, who: str = 'system',
                   rows_in: int | None = None, dropped: dict | None = None, mode: str | None = None, changes: dict | None = None) -> dict:
    """Store every record as a row of a new dataset version, or return the version already holding this content;
    either way that version becomes the current one. rows_in is the number of data rows in the file and dropped says
    how many of them the reader left out and why ({'blank': 2, 'title': 1}); without them the records are all there was.
    mode ('new', 'update_by_key', 'overwrite') and changes ({'changed', 'added', 'unchanged', ...}) are kept on the version beside who.
    Raises RowCountMismatch, writing nothing, when the rows do not add up or what was stored is not what was received."""
    dropped = {k: n for k, n in (dropped or {}).items() if n}
    expected = len(records)
    rows_in = expected + sum(dropped.values()) if rows_in is None else rows_in
    if rows_in != expected + sum(dropped.values()):
        raise RowCountMismatch(f'{name}：文件里有 {rows_in} 行，读到 {expected} 行、丢掉 {sum(dropped.values())} 行，对不上，已取消导入')
    existing = _dataset(conn, 'name = ? AND file_sha256 = ? ORDER BY version DESC LIMIT 1', (name, file_sha256))
    if existing:
        _set_current(conn, who, existing)
        return {**existing, 'reused': True}
    names = _unique_names(records)
    if not names:
        raise ValueError(f'{name}: no columns to store')
    originals = list(dict.fromkeys(k for r in records for k in r))
    conn.execute('BEGIN IMMEDIATE')   # the write lock now: a transaction that reads first and writes later is refused at once, not waited for, when another holds it
    try:
        version = (conn.execute('SELECT COALESCE(MAX(version), 0) FROM dataset WHERE name = ?', (name,)).fetchone()[0]) + 1
        dataset_id = conn.execute('INSERT INTO dataset(name, version, origin, file_sha256, rows_in, rows_stored, table_name, imported_at, dropped_json, who, mode, changes_json)'
                                  " VALUES (?, ?, ?, ?, ?, 0, '', ?, ?, ?, ?, ?)",
                                  (name, version, origin, file_sha256, rows_in, _now(), json.dumps(dropped) if dropped else None, who, mode,
                                   None if changes is None else json.dumps(changes, ensure_ascii=False))).lastrowid
        table = f'ds_{dataset_id}'
        conn.execute(f'CREATE TABLE {_quote(table)} ({", ".join(_quote(n) + " TEXT" for n in names)})')
        conn.executemany(f'INSERT INTO {_quote(table)} VALUES ({", ".join("?" * len(names))})',
                         ([r.get(n) for n in originals] for r in records))
        rows_stored = conn.execute(f'SELECT COUNT(*) FROM {_quote(table)}').fetchone()[0]
        if rows_stored != expected:
            raise RowCountMismatch(f'{name}：读到 {expected} 行，只存入 {rows_stored} 行，已取消导入')
        conn.execute('UPDATE dataset SET rows_stored = ?, table_name = ? WHERE id = ?', (rows_stored, table, dataset_id))
        for position, column in enumerate(names):
            d = _describe([row[0] for row in conn.execute(f'SELECT {_quote(column)} FROM {_quote(table)}')])
            conn.execute('INSERT INTO "column" VALUES (?, ?, ?, ?, ?, ?, ?)',
                         (dataset_id, column, position, d['inferred_type'], d['distinct_count'], d['missing_count'], d['value_counts_json']))
        conn.execute('INSERT OR REPLACE INTO current_dataset(name, dataset_id) VALUES (?, ?)', (name, dataset_id))
        _log(conn, who, f'dataset:{name}', f'import v{version}: {rows_in} rows in the file, {rows_stored} stored, {sum(dropped.values())} dropped',
             after={'version': version, 'rows_in': rows_in, 'rows_stored': rows_stored, 'dropped': dropped, 'file_sha256': file_sha256})
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return {**_dataset(conn, 'id = ?', (dataset_id,)), 'reused': False}


def _set_current(conn, who: str, dataset: dict) -> None:
    """Uploading content an earlier version already holds makes that version current again."""
    before = conn.execute('SELECT dataset_id FROM current_dataset WHERE name = ?', (dataset['name'],)).fetchone()
    if before is None or before[0] != dataset['id']:
        conn.execute('INSERT OR REPLACE INTO current_dataset(name, dataset_id) VALUES (?, ?)', (dataset['name'], dataset['id']))
        _log(conn, who, f'dataset:{dataset["name"]}', f'v{dataset["version"]} is current again',
             before={'dataset_id': before[0] if before else None}, after={'dataset_id': dataset['id']})


def dataset_records(conn, dataset: dict) -> list[dict]:
    """Every row of one stored dataset version, in the order it was stored, as {column: text or None}."""
    cursor = conn.execute(f'SELECT * FROM {_quote(dataset["table_name"])} ORDER BY rowid')
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, row)) for row in cursor]


def _canonical(value):
    """A key value as it is matched: a number in its plain form (1.0, 1.00 and 1 are one key, as an Excel file and a CSV
    file write the same number differently), anything else as the trimmed text. A code with a leading zero (007) is text, not 7."""
    if value is None:
        return None
    text = str(value).strip()
    if (_INTEGER.fullmatch(text) or _DECIMAL.fullmatch(text)) and not _LEADING_ZERO.match(text):
        number = Decimal(text)
        return '0' if number == 0 else format(number.normalize(), 'f')
    return text


def _key_of(row: dict, columns: list[str]) -> tuple:
    return tuple(_canonical(row.get(c)) for c in columns)


def _shown(key: tuple) -> str:
    return ' + '.join(str(v) for v in key)


def merge_by_key(current: list[dict], incoming: list[dict], key_columns: list[str]) -> tuple[list[dict], dict]:
    """The rows of a dataset after an update by key, and what the update did: {'changed', 'added', 'unchanged'}.
    A row of the new file whose key is already there replaces the values it carries; a key that is not there is appended after
    the existing rows; a row of the current data that the file does not mention stays, because an update never deletes. Keys are
    matched in their plain form (1.0 is 1). A blank cell in the file leaves the stored value as it is and is not a change
    ('blank_kept' counts the cells that kept a value; 'changed_keys' and 'added_keys' name the first KEY_LIST_LIMIT rows of each); columns the file does not carry keep their values; columns only the file
    carries are added (empty for rows it does not touch).
    Raises ValueError, with the reason in plain Chinese, when a key cannot be matched without guessing."""
    if not key_columns:
        raise ValueError('按主键更新要先选出主键列')
    here = list(dict.fromkeys(k for r in current for k in r))
    there = list(dict.fromkeys(k for r in incoming for k in r))
    for column in key_columns:
        if column not in there:
            raise ValueError(f'新文件里没有主键列“{column}”，没法按它更新')
        if column not in here:
            raise ValueError(f'现有数据里没有“{column}”这一列，没法按它更新')
    empty = sum(1 for r in incoming if any(r.get(c) in (None, '') for c in key_columns))
    if empty:
        raise ValueError(f'新文件里有 {empty} 行的主键是空的，对不上现有的行，请先补上或删掉这些行')
    seen: dict[tuple, int] = {}
    for r in incoming:
        seen[_key_of(r, key_columns)] = seen.get(_key_of(r, key_columns), 0) + 1
    repeated = [k for k, n in seen.items() if n > 1]
    if repeated:
        raise ValueError(f'新文件里主键“{_shown(repeated[0])}”出现了 {seen[repeated[0]]} 行（共 {len(repeated)} 个主键重复），不知道取哪一行')
    where: dict[tuple, list[int]] = {}
    for i, r in enumerate(current):
        where.setdefault(_key_of(r, key_columns), []).append(i)
    clash = [k for k in seen if len(where.get(k, ())) > 1]
    if clash:
        raise ValueError(f'现有数据里主键“{_shown(clash[0])}”有 {len(where[clash[0]])} 行（共 {len(clash)} 个主键），按主键更新会分不清改哪一行')
    columns = here + [c for c in there if c not in here]
    rows = [{c: r.get(c) for c in columns} for r in current]
    changed = added = blank_kept = 0
    changed_keys, added_keys = [], []
    for r in incoming:
        found = where.get(_key_of(r, key_columns))
        merged = {c: r.get(c) for c in columns}
        if found is None:
            rows.append(merged)
            added += 1
            added_keys.append(_shown(tuple(r.get(c) for c in key_columns)))
            continue
        stored = rows[found[0]]
        given = {c: r[c] for c in there if c not in key_columns and r.get(c) not in (None, '')}   # a key is what matched: its stored spelling stays
        blank_kept += sum(1 for c in there if c not in key_columns and r.get(c) in (None, '') and stored.get(c) is not None)
        taken = {**stored, **given}
        if taken != stored:
            rows[found[0]] = taken
            changed += 1
            changed_keys.append(_shown(tuple(stored.get(c) for c in key_columns)))
    return rows, {'changed': changed, 'added': added, 'unchanged': len(seen) - changed - added, 'blank_kept': blank_kept,
                  'changed_keys': changed_keys[:KEY_LIST_LIMIT], 'added_keys': added_keys[:KEY_LIST_LIMIT]}


UPLOAD_MODES = ('update_by_key', 'overwrite')
KEY_LIST_LIMIT = 50   # keys of changed and added rows kept with a version, so its page can say which rows
NO_CHANGE = 'update_by_key: no change'   # the log line of an update that matched every row and changed none


def plan_upload(conn, name: str, records: list[dict], *, mode: str | None = None, key_columns: list[str] | None = None,
                rows_in: int | None = None, dropped: dict | None = None) -> dict:
    """What saving this file under `name` would do, decided without writing: the records the new version holds, its mode and the
    counts. No mode means a new dataset: refused when the name is taken, because which one is meant is the person's to say.
    Raises ValueError (plain Chinese) for anything that cannot be done without guessing."""
    current = current_dataset(conn, name)
    if mode not in (None, *UPLOAD_MODES):
        raise ValueError('导入方式只有按主键更新（update_by_key）和覆盖（overwrite）两种')
    if mode is None:
        if current:
            raise ValueError(f'已经有叫“{name}”的数据集。要更新它，请指定数据集和方式：按主键更新或覆盖；要新建，请换一个名字')
        return {'name': name, 'mode': 'new', 'records': records, 'rows_in': rows_in, 'dropped': dropped, 'unchanged': False,
                'changes': {'changed': 0, 'added': len(records), 'unchanged': 0}}
    if current is None:
        raise ValueError(f'没有叫“{name}”的数据集，不能{"按主键更新" if mode == "update_by_key" else "覆盖"}它')
    if mode == 'overwrite':
        return {'name': name, 'mode': mode, 'records': records, 'rows_in': rows_in, 'dropped': dropped, 'unchanged': False,
                'changes': {'replaced_rows': current['rows_stored']}}
    if not isinstance(key_columns, list) or not key_columns or not all(isinstance(c, str) and c for c in key_columns):
        raise ValueError('主键列要写成列名的列表，例如 ["订单号"]')
    merged, counts = merge_by_key(dataset_records(conn, current), records, key_columns)
    file_rows = len(records) + sum((dropped or {}).values())
    return {'name': name, 'mode': mode, 'records': merged, 'rows_in': None, 'dropped': None, 'key_columns': list(key_columns),
            'unchanged': not (counts['changed'] or counts['added']), 'current': current,
            'changes': {**counts, 'file_rows': rows_in if rows_in is not None else file_rows, 'key_columns': list(key_columns)}}


def apply_upload(conn, plan: dict, who: str, origin: str = 'upload') -> dict:
    """Write what plan_upload decided as the next version of the dataset, recording who and the counts with it. An update that
    changes and adds nothing writes nothing: {'created': False}. Otherwise {'created': True, 'dataset': the version, 'key_check': ...}
    where key_check is the key check of an update's key columns on the rows now stored."""
    if plan['unchanged']:
        _log(conn, who, f'dataset:{plan["name"]}', NO_CHANGE, after=plan['changes'])   # the only trace of an upload that wrote no version
        return {'created': False, 'dataset': plan['current'], 'mode': plan['mode'], 'changes': plan['changes'], 'reused': False}
    records = plan['records']
    dataset = import_records(conn, plan['name'], records, origin, records_sha256(records), who, plan['rows_in'], plan['dropped'],
                             mode=plan['mode'], changes=plan['changes'])
    key_check = check_key(conn, dataset['id'], plan['key_columns']) if plan.get('key_columns') else None
    return {'created': not dataset['reused'], 'dataset': dataset, 'mode': plan['mode'], 'changes': plan['changes'],
            'reused': dataset['reused'], 'key_check': key_check}


def _key_context(conn, dataset_id: int, columns: list[str]):
    dataset = _dataset(conn, 'id = ?', (dataset_id,))
    if dataset is None:
        raise ValueError(f'no dataset {dataset_id}')
    known = {r[0] for r in conn.execute('SELECT name FROM "column" WHERE dataset_id = ?', (dataset_id,))}
    if not columns or not set(columns) <= known:
        raise ValueError(f'{dataset["name"]}: unknown key columns {sorted(set(columns) - known) or columns}')
    cols = ', '.join(_quote(c) for c in columns)
    filled = ' AND '.join(f"({_quote(c)} IS NOT NULL AND {_quote(c)} <> '')" for c in columns)
    return dataset, cols, filled, _quote(dataset['table_name'])


def record_result(conn, element_id, dataset_id, check_type, query, rows_checked, violations, null_key_rows, samples, status) -> int:
    """One row of check_result, tied to the dataset version it looked at: what was run, over how many rows, what it found."""
    return conn.execute('INSERT INTO check_result(element_id, check_type, query, rows_checked, violations, samples_json, status, checked_at, dataset_id, null_key_rows)'
                        ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        (element_id, check_type, query, rows_checked, violations, json.dumps(samples, ensure_ascii=False), status, _now(),
                         dataset_id, null_key_rows)).lastrowid


def _record_check(conn, dataset, columns, check_type, query, rows_checked, violations, null_key_rows, samples, status) -> dict:
    element_id = f'key:{dataset["name"]}({",".join(columns)})'
    check_id = record_result(conn, element_id, dataset['id'], check_type, query, rows_checked, violations, null_key_rows, samples, status)
    return {'id': check_id, 'element_id': element_id, 'check_type': check_type, 'dataset': dataset['name'],
            'dataset_id': dataset['id'], 'columns': list(columns), 'query': query, 'rows_checked': rows_checked,
            'violations': violations, 'null_key_rows': null_key_rows, 'samples': samples, 'status': status}


def check_key(conn, dataset_id: int, columns: list[str]) -> dict:
    """Is this column set unique and filled across every stored row? Records the query, the rows looked at, the extra
    rows beyond the first per key, up to five duplicated keys, and the rows with an empty key column. Either failure fails."""
    dataset, cols, filled, table = _key_context(conn, dataset_id, columns)
    query = (f'SELECT {cols}, COUNT(*) AS n FROM {table} WHERE {filled} GROUP BY {cols} HAVING COUNT(*) > 1 '
             'ORDER BY n DESC, ' + cols)
    rows_checked = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    null_key_rows = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE NOT ({filled})').fetchone()[0]
    violations = conn.execute(f'SELECT COALESCE(SUM(n - 1), 0) FROM ({query})').fetchone()[0]
    samples = [{'key': dict(zip(columns, row[:-1])), 'count': row[-1]}
               for row in conn.execute(f'{query} LIMIT {SAMPLE_LIMIT}')]
    return _record_check(conn, dataset, columns, 'key_unique', query, rows_checked, violations, null_key_rows, samples,
                         'failed' if violations or null_key_rows else 'passed')


def check_distinct(conn, dataset_id: int, columns: list[str]) -> dict:
    """For a column that names objects another table describes (the engineer on a ticket): repeats are expected, so
    count the distinct filled values instead. Empty cells are counted, not failed: a ticket may have no engineer yet."""
    dataset, cols, filled, table = _key_context(conn, dataset_id, columns)
    query = f'SELECT COUNT(*) FROM (SELECT DISTINCT {cols} FROM {table} WHERE {filled})'
    rows_checked = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    null_key_rows = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE NOT ({filled})').fetchone()[0]
    distinct = conn.execute(query).fetchone()[0]
    return {**_record_check(conn, dataset, columns, 'key_distinct', query, rows_checked, 0, null_key_rows, [],
                            'passed' if distinct else 'failed'), 'distinct': distinct}


def describes_rows(ontology: dict):
    """(object type, source) -> does each row of that table describe an object of that type? Read from the draft's
    structure, not from names: a population is a reference (a column naming objects the table does not describe, like
    the engineer on a ticket) when the type takes no attributes from that table while another type does."""
    described = {(t['key'], a.get('source')) for t in normalize_proposal(ontology)['object_types'] for a in t['attributes']}
    tables_described = {source for _, source in described}
    return lambda type_key, source: (type_key, source) in described or source not in tables_described


def _key_populations(ontology: dict) -> list[tuple[str, str, tuple[str, ...], bool]]:
    """(object type, source, identity columns, describes_rows) for each population whose identity is one plain column
    set per row; populations that split a list, build a hierarchy, filter rows or read list elements are not row keys."""
    own = describes_rows(ontology)
    found = []
    for t in normalize_proposal(ontology)['object_types']:
        for pop in t['populated_from']:
            paths = tuple(pop['identity'][k] for k in sorted(pop['identity']))
            if pop['transform'] == 'none' and not pop.get('where') and not any('[].' in path for path in paths):
                found.append((t['key'], pop['source'], paths, own(t['key'], pop['source'])))
    return found


def check_bundle(conn, ontology: dict, bundle: dict, origin: str, relations: bool = True) -> dict:
    """Import every source table of a bundle, then check each object type's identity columns as a key (or, for a
    reference column, as a list of values). 'tables': one entry per table with the rows in the file, rows stored and
    rows dropped; a table that cannot be stored says why and the others go on. 'keys': one entry per checked
    population; a failed check is reported as failed and nothing is fixed. 'relations': each relation checked against the stored
    tables (relation_checks); `relations=False` leaves them out."""
    tables, datasets = [], {}
    for name, s in bundle['sources'].items():
        read = s.get('rows_read')
        dropped = s.get('dropped_rows')
        try:
            d = import_records(conn, name, s['records'], origin, records_sha256(s['records']), rows_in=read, dropped=dropped)
        except RowCountMismatch as exc:
            tables.append({'dataset': name, 'status': 'error', 'error': str(exc), 'rows_in': read if read is not None else len(s['records']),
                           'rows_stored': None, 'dropped': dropped or {}})
            continue
        datasets[name] = d
        tables.append({'dataset': name, 'dataset_id': d['id'], 'version': d['version'], 'status': 'ok', 'rows_in': d['rows_in'],
                       'rows_stored': d['rows_stored'], 'dropped': json.loads(d['dropped_json'] or '{}')})
    runs, keys = {}, []
    for type_key, source, columns, describes_rows in _key_populations(ontology):
        d = datasets.get(source)
        known = {r[0] for r in conn.execute('SELECT name FROM "column" WHERE dataset_id = ?', (d['id'],))} if d else set()
        if d is None or not set(columns) <= known:
            continue   # a table that was not stored or a column the draft invented: the model checks name that
        check = check_key if describes_rows else check_distinct
        if (source, columns, check) not in runs:
            runs[(source, columns, check)] = check(conn, d['id'], list(columns))
        r = runs[(source, columns, check)]
        keys.append({'object_type': type_key, 'dataset': source, 'dataset_id': d['id'], 'version': d['version'],
                     'key_columns': list(columns), 'check_type': r['check_type'], 'status': r['status'],
                     'violations': r['violations'], 'null_key_rows': r['null_key_rows'], 'rows_checked': r['rows_checked'],
                     'samples': r['samples'], 'check_id': r['id'], **({'distinct': r['distinct']} if 'distinct' in r else {})})
    if not relations:
        return {'tables': tables, 'keys': keys}
    from ontology_poc_generator.relation_checks import check_relations   # it reads the helpers of this module
    return {'tables': tables, 'keys': keys, 'relations': check_relations(conn, ontology, datasets)}


def key_errors(proposal: dict, bundle: dict) -> list[dict]:
    """The failed key checks of a draft as errors the modeller can be sent back with, so it can pick a better key.
    Run on a throwaway in-memory workspace: nothing is saved."""
    conn = open_workspace(':memory:')
    try:
        keys = check_bundle(conn, proposal, bundle, 'draft', relations=False)['keys']
    except (sqlite3.Error, ValueError):   # the same checks run again with the saved run, which shows the failure to the person
        return []
    finally:
        conn.close()
    errors = []
    for k in (k for k in keys if k['check_type'] == 'key_unique' and k['status'] == 'failed'):
        where = f'{k["dataset"]} ({", ".join(k["key_columns"])})'
        if k['violations']:
            sample = k['samples'][0]
            errors.append({'code': 'key_not_unique', 'message': f'key not unique in {where}: {k["violations"]} repeated, e.g. '
                           f'{" + ".join(sample["key"].values())} ({sample["count"]} rows). If one row per {k["object_type"]} is expected '
                           '(master data), a repeat is a data problem: keep this key, the repeat is reported to the client. Change the key '
                           'only if the table legitimately holds several rows per object (versions, snapshots, months), and then use a time or version column'})
        if k['null_key_rows']:
            errors.append({'code': 'key_empty', 'message': f'key empty in {where}: {k["null_key_rows"]} rows have no value'})
    return errors
