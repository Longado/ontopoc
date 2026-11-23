"""The workspace: one SQLite file holding every imported table row, the types read from them, and every check run.

Import never loses a row quietly: rows are stored as real SQL tables (one per dataset version, every value kept as the
text it was read as), the count written is checked against the count received, and rows the file reader dropped
(blank lines, title lines) are counted with their reason, so rows in the file = rows stored + rows dropped. A check records the query it ran
and how many rows it looked at, so a later stage can show the evidence behind a definition.
"""
from __future__ import annotations

from ontology_poc_generator.lang import tr
from contextlib import contextmanager
from datetime import date, datetime, timezone
import hashlib
import json
import os
import re
import sqlite3

from ontology_poc_generator.accounts import SCHEMA as ACCOUNTS_SCHEMA, two_person
from ontology_poc_generator.actor import actor_id_for, current_actor, token_mark
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
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, version INTEGER NOT NULL, origin TEXT, file_sha256 TEXT NOT NULL,
    rows_in INTEGER NOT NULL, rows_stored INTEGER NOT NULL, table_name TEXT NOT NULL, imported_at TEXT NOT NULL,
    dropped_json TEXT, who TEXT, mode TEXT, changes_json TEXT, UNIQUE (name, version));
CREATE TABLE IF NOT EXISTS current_dataset (name TEXT PRIMARY KEY, dataset_id INTEGER NOT NULL REFERENCES dataset(id));
CREATE TABLE IF NOT EXISTS "column" (
    dataset_id INTEGER NOT NULL REFERENCES dataset(id), name TEXT NOT NULL, position INTEGER NOT NULL,
    inferred_type TEXT NOT NULL, distinct_count INTEGER NOT NULL, missing_count INTEGER NOT NULL,
    value_counts_json TEXT, PRIMARY KEY (dataset_id, name));
CREATE TABLE IF NOT EXISTS element_state (
    element_id TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK (state IN ('proposed', 'checked', 'confirmed', 'needs_look', 'rejected')),
    evidence_ref TEXT, confirmed_by TEXT, confirmed_at TEXT, version INTEGER NOT NULL, content_json TEXT, anchors_json TEXT);
CREATE TABLE IF NOT EXISTS element_dep (
    element_id TEXT NOT NULL, depends_on TEXT NOT NULL, PRIMARY KEY (element_id, depends_on));
CREATE TABLE IF NOT EXISTS confirmation (
    id INTEGER PRIMARY KEY AUTOINCREMENT, element_id TEXT NOT NULL, confirmed_by TEXT, confirmed_by_user_id INTEGER, proposed_by TEXT,
    confirmed_at TEXT NOT NULL, content_json TEXT, evidence_ref TEXT, dataset_versions_json TEXT, self_confirmed INTEGER NOT NULL DEFAULT 0, snapshot_json TEXT);
CREATE TABLE IF NOT EXISTS type_access (
    type_id TEXT PRIMARY KEY, user_ids_json TEXT NOT NULL);
-- who an action tells when one of its changes is approved (notices.py), and what each person was told
CREATE TABLE IF NOT EXISTS action_notify (action_id TEXT PRIMARY KEY, spec_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notice (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, at TEXT NOT NULL, action_name TEXT NOT NULL, record_id INTEGER, text TEXT NOT NULL, read_at TEXT);
CREATE INDEX IF NOT EXISTS notice_user ON notice(user_id, id);
-- a property only the people listed (and admins) may see: for anyone else the type is the type without it (type_access.hidden_columns)
CREATE TABLE IF NOT EXISTS column_access (
    type_id TEXT NOT NULL, column_name TEXT NOT NULL, user_ids_json TEXT NOT NULL, PRIMARY KEY (type_id, column_name));
CREATE TABLE IF NOT EXISTS value_privacy (
    type_id TEXT NOT NULL, column_name TEXT NOT NULL, PRIMARY KEY (type_id, column_name));
-- what a pipeline's output column was made from, kept with the dataset it wrote: 'unsent' (made from a column kept from the model), 'ai' (made from a model's answer)
CREATE TABLE IF NOT EXISTS column_mark (
    dataset_id INTEGER NOT NULL REFERENCES dataset(id), column_name TEXT NOT NULL, mark TEXT NOT NULL CHECK (mark IN ('unsent', 'ai')), PRIMARY KEY (dataset_id, column_name, mark));
-- an output column of a pipeline whose figure was worked out over a join that made several rows of one (a sum or a count of a column the join repeated): FAN_NOTE says so
CREATE TABLE IF NOT EXISTS column_fan (
    dataset_id INTEGER NOT NULL REFERENCES dataset(id), column_name TEXT NOT NULL, PRIMARY KEY (dataset_id, column_name));
CREATE TABLE IF NOT EXISTS row_rule (
    id INTEGER PRIMARY KEY AUTOINCREMENT, type_id TEXT NOT NULL, column_name TEXT NOT NULL, value TEXT NOT NULL, user_ids_json TEXT NOT NULL, user_attr TEXT);
CREATE TABLE IF NOT EXISTS action_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT, action_id TEXT NOT NULL, action_version INTEGER NOT NULL, type_id TEXT NOT NULL, dataset TEXT NOT NULL, dataset_version INTEGER NOT NULL,
    key_json TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL, reason TEXT,
    state TEXT NOT NULL CHECK (state IN ('pending', 'approved', 'rejected', 'withdrawn', 'expired', 'needs_look')),
    submitted_by TEXT, submitted_by_user_id INTEGER, submitted_at TEXT NOT NULL, decided_by TEXT, decided_by_user_id INTEGER, decided_at TEXT, note TEXT, why TEXT, new_version INTEGER,
    undo_of INTEGER, op TEXT);   -- op: edit (or NULL, before R12a), create or delete
CREATE TABLE IF NOT EXISTS pipeline_version (
    pipeline_id TEXT NOT NULL, version INTEGER NOT NULL, definition_json TEXT NOT NULL, saved_by TEXT, saved_by_user_id INTEGER, saved_at TEXT NOT NULL,
    PRIMARY KEY (pipeline_id, version));
CREATE TABLE IF NOT EXISTS pipeline_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT, pipeline_id TEXT NOT NULL, definition_version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'cancelled')), who TEXT, who_user_id INTEGER, started_at TEXT NOT NULL, finished_at TEXT,
    duration_ms INTEGER, input_versions_json TEXT, nodes_json TEXT, failures_json TEXT, outputs_json TEXT, error TEXT);
-- the model's part of a pipeline (pipeline_llm): answers kept per node, the answers a person expects for rows, the last count against them
CREATE TABLE IF NOT EXISTS llm_cache (
    pipeline_id TEXT NOT NULL, step_id TEXT NOT NULL, key_hash TEXT NOT NULL, contract TEXT NOT NULL, value_json TEXT NOT NULL, raw_json TEXT, model TEXT, at TEXT NOT NULL,
    PRIMARY KEY (pipeline_id, step_id, key_hash));
CREATE TABLE IF NOT EXISTS llm_label (
    pipeline_id TEXT NOT NULL, step_id TEXT NOT NULL, row_hash TEXT NOT NULL, fields_json TEXT NOT NULL, expected_json TEXT NOT NULL, who TEXT, who_user_id INTEGER, at TEXT NOT NULL,
    PRIMARY KEY (pipeline_id, step_id, row_hash));
CREATE TABLE IF NOT EXISTS llm_review (
    pipeline_id TEXT NOT NULL, step_id TEXT NOT NULL, contract TEXT NOT NULL, total INTEGER NOT NULL, matched INTEGER NOT NULL, min_match INTEGER, who TEXT, who_user_id INTEGER, at TEXT NOT NULL,
    distinct_rows INTEGER, detail_json TEXT,   -- how many different rows the step had to ask about then, and what each labelled row came back as
    PRIMARY KEY (pipeline_id, step_id));
CREATE TABLE IF NOT EXISTS qa_question (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, asked_by TEXT, question TEXT NOT NULL, asked_at TEXT NOT NULL, status TEXT NOT NULL,
    answer_json TEXT NOT NULL, definitions_json TEXT NOT NULL, dataset_versions_json TEXT NOT NULL, types_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assistant_turn (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, mode TEXT NOT NULL, message TEXT NOT NULL, scope_json TEXT NOT NULL, at TEXT NOT NULL,
    card_json TEXT NOT NULL, named_json TEXT NOT NULL, outcome_json TEXT);
CREATE TABLE IF NOT EXISTS check_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT, element_id TEXT NOT NULL, check_type TEXT NOT NULL, query TEXT NOT NULL,
    rows_checked INTEGER, violations INTEGER, samples_json TEXT, dataset_id INTEGER, null_key_rows INTEGER,
    status TEXT NOT NULL CHECK (status IN ('passed', 'failed', 'error', 'skipped')),
    checked_at TEXT NOT NULL DEFAULT '');
-- live sources (workspace_sources): a database connection (the password sealed, see source_vault), the tables read as datasets, and every pull
CREATE TABLE IF NOT EXISTS data_source (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, kind TEXT NOT NULL CHECK (kind IN ('postgresql', 'mysql')),
    host TEXT NOT NULL, port INTEGER NOT NULL, database TEXT NOT NULL, username TEXT NOT NULL, secret TEXT NOT NULL,
    tls TEXT NOT NULL DEFAULT 'required', ca_pem TEXT, status TEXT NOT NULL DEFAULT 'untested' CHECK (status IN ('untested', 'ok', 'failed')), status_at TEXT, status_note TEXT, can_write INTEGER, write_note TEXT,
    created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER NOT NULL REFERENCES data_source(id), table_name TEXT NOT NULL, dataset TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL, key_json TEXT, UNIQUE (source_id, table_name));
-- schedules (workspace_schedules) and the log of what a pull or a scheduled run did
CREATE TABLE IF NOT EXISTS schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, kind TEXT NOT NULL CHECK (kind IN ('source', 'pipeline')), target TEXT NOT NULL, scope_json TEXT,
    cadence TEXT NOT NULL CHECK (cadence IN ('hourly', 'daily', 'weekly', 'upstream')), minute INTEGER, hour INTEGER, weekday INTEGER, tz TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1, last_slot TEXT, upstream_seen_json TEXT, created_by TEXT, created_by_user_id INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS refresh_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, target TEXT NOT NULL, item TEXT NOT NULL DEFAULT '', schedule_id INTEGER,
    reason TEXT NOT NULL CHECK (reason IN ('manual', 'schedule', 'upstream')), who TEXT, status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'skipped')),
    started_at TEXT NOT NULL, finished_at TEXT, rows INTEGER, dataset TEXT, version INTEGER, changed INTEGER, error TEXT, error_public TEXT, detail_json TEXT);
CREATE TABLE IF NOT EXISTS log (
    time TEXT NOT NULL, who TEXT NOT NULL, element_id TEXT, change TEXT NOT NULL, before_json TEXT, after_json TEXT);
-- numbers the team has checked (checked_numbers): a board card or a saved answer, the value the team trusts, what OntoPoc computed then and on what; the latest row of each is the check
CREATE TABLE IF NOT EXISTS checked_number (
    id INTEGER PRIMARY KEY AUTOINCREMENT, dashboard_id INTEGER, component_id TEXT, component_json TEXT, question_id INTEGER,
    trusted REAL NOT NULL, computed REAL NOT NULL, note TEXT NOT NULL, by_user_id INTEGER, by_name TEXT NOT NULL, at TEXT NOT NULL,
    datasets_json TEXT NOT NULL, definitions_json TEXT NOT NULL);
-- questions we need (needed_questions): the team's list of questions, each with what it should give (a number, or that it must be refused), proposed by one person and
-- confirmed by another; every run of the list (who, how many asks, how many model calls) and what each question came back as in it
CREATE TABLE IF NOT EXISTS needed_question (
    id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL, expect_kind TEXT CHECK (expect_kind IN ('number', 'refused')), expect_value REAL, expect_blocker TEXT, expect_version INTEGER NOT NULL DEFAULT 1, note TEXT,
    state TEXT NOT NULL CHECK (state IN ('none', 'proposed', 'confirmed', 'needs_look')), version INTEGER NOT NULL,
    written_by TEXT, written_by_user_id INTEGER, written_at TEXT NOT NULL, confirmed_by TEXT, confirmed_by_user_id INTEGER, confirmed_at TEXT, self_confirmed INTEGER NOT NULL DEFAULT 0,
    basis_json TEXT, look_json TEXT);
CREATE TABLE IF NOT EXISTS needed_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT, by_name TEXT NOT NULL, by_user_id INTEGER, started_at TEXT NOT NULL, finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'done', 'stopped')), repeats INTEGER NOT NULL, planned INTEGER NOT NULL, calls INTEGER NOT NULL DEFAULT 0,
    model TEXT, prompt_version TEXT, note TEXT, owner TEXT);   -- owner: the token of the service running it; a running row no service runs was cut off
CREATE TABLE IF NOT EXISTS needed_result (
    run_id INTEGER NOT NULL, question_id INTEGER NOT NULL, question TEXT NOT NULL, outcome TEXT NOT NULL, result_json TEXT NOT NULL, PRIMARY KEY (run_id, question_id));
'''


class SelfConfirmation(ValueError):
    """A definition cannot be confirmed by the person who proposed it while two-person confirmation is on; the message is shown to the person."""


class StaleElement(ValueError):
    """An element changed after the version the writer read, so their write would have overwritten someone else's."""


class RowCountMismatch(RuntimeError):
    """The rows written are not the rows received; the message names the table and is shown to the person."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


now_text = _now   # for the modules that write log lines of their own


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def open_workspace(path) -> sqlite3.Connection:
    """Open (creating if needed) the workspace file; ':memory:' for a throwaway one. Transactions are explicit."""
    if str(path) != ':memory:' and not os.path.exists(path):
        os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))   # made private from the start, not after a moment at the umask's mode
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.executescript(SCHEMA + ACCOUNTS_SCHEMA)
    if str(path) != ':memory:':
        os.chmod(path, 0o600)   # the file holds password hashes and sessions: this account only
    for table, column in (('dataset', 'dropped_json'), ('dataset', 'who'), ('dataset', 'mode'), ('dataset', 'changes_json'), ('check_result', 'dataset_id'), ('check_result', 'null_key_rows'),
                          ('element_state', 'content_json'), ('element_state', 'anchors_json'), ('element_state', 'proposed_by'), ('element_state', 'reason'),
                          ('dataset', 'who_user_id'), ('element_state', 'confirmed_by_user_id'), ('element_state', 'proposed_by_user_id'), ('log', 'user_id'), ('log', 'via_token'),
                          ('element_state', 'cause'), ('element_state', 'via'), ('confirmation', 'snapshot_json'), ('llm_review', 'distinct_rows'), ('llm_review', 'detail_json'),
                          ('api_token', 'scope'), ('api_token', 'expires_at'), ('action_record', 'undo_of'), ('action_record', 'op'),
                          ('data_source', 'tls'), ('data_source', 'ca_pem'), ('refresh_run', 'error_public'), ('schedule', 'created_by_user_id'), ('user', 'attrs_json'), ('row_rule', 'user_attr'),
                          ('needed_question', 'expect_blocker'), ('needed_run', 'owner'), ('element_state', 'changed_json'), ('needed_question', 'changed_json')):
        if column not in {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}:   # a file made before the column existed
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {"INTEGER" if column in ("dataset_id", "null_key_rows", "distinct_rows", "undo_of") or column.endswith("user_id") else "TEXT"}')
    if 'expect_version' not in {r[1] for r in conn.execute('PRAGMA table_info(needed_question)')}:   # counts each new expectation and each confirmation of one: a result belongs to one
        conn.execute('ALTER TABLE needed_question ADD COLUMN expect_version INTEGER NOT NULL DEFAULT 1')
    _never_reuse_ids(conn)
    _allow_needs_look(conn)
    conn.execute('INSERT OR IGNORE INTO current_dataset SELECT name, id FROM dataset WHERE version = '
                 '(SELECT MAX(version) FROM dataset d WHERE d.name = dataset.name)')
    return conn


def _never_reuse_ids(conn) -> None:
    """A file made before dataset, check_result and user ids were AUTOINCREMENT: rebuild those tables so an id, once used, is never given out again
    (a deleted dataset's id, taken by a later one, would show the old one's checks; a check id is what an evidence reference names; a deleted
    guest's account id, taken by a later account, would find whatever rows still name it). Check results that belong to no dataset any more
    are dropped. The counters start at the highest id still there: an id freed before this cannot be known."""
    def todo_now() -> dict:
        old = {name: conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone()[0] for name in ('dataset', 'check_result', 'user')}
        return {name: sql for name, sql in old.items() if 'AUTOINCREMENT' not in sql}
    if not todo_now():
        return
    with _plain_rename(conn):
        conn.execute('BEGIN IMMEDIATE')
        try:
            todo = todo_now()   # read again under the write lock: another opener may have done it while this one waited
            if todo:
                _rebuild_with_ids_kept(conn, todo)
            conn.execute('COMMIT')
        except BaseException:
            conn.execute('ROLLBACK')
            raise


def _rebuild_with_ids_kept(conn, todo: dict) -> None:
    conn.execute('DELETE FROM check_result WHERE dataset_id IS NOT NULL AND dataset_id NOT IN (SELECT id FROM dataset)')
    for name, sql in todo.items():
        rebuilt = re.sub(r'\bid INTEGER PRIMARY KEY\b', 'id INTEGER PRIMARY KEY AUTOINCREMENT', sql, count=1)
        assert rebuilt != sql, f'{name}: its id column is not the plain INTEGER PRIMARY KEY this migration knows'
        conn.execute(re.sub(r'^CREATE TABLE (IF NOT EXISTS )?"?\w+"?', f'CREATE TABLE {name}_rebuilt', rebuilt, count=1))
        conn.execute(f'INSERT INTO {name}_rebuilt SELECT * FROM {name}')
        conn.execute(f'DROP TABLE {name}')
        conn.execute(f'ALTER TABLE {name}_rebuilt RENAME TO {name}')


@contextmanager
def _plain_rename(conn):
    """While a table is rebuilt (new one made, old one dropped, new one renamed into its place): sqlite's rename only renames. By default it also
    reads every view in the file again and refuses when one of them names a table that is gone (a run's view whose data was deleted), which
    would stop the file from opening at all; nothing refers to the rebuilt table's temporary name, so there is nothing for it to rewrite."""
    conn.execute('PRAGMA legacy_alter_table = ON')
    try:
        yield
    finally:
        conn.execute('PRAGMA legacy_alter_table = OFF')


def _allow_needs_look(conn) -> None:
    """A file made before the state 'needs_look' existed has a CHECK that refuses it: rebuild element_state with the same rows and the wider CHECK."""
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'element_state'").fetchone()[0]
    if 'CHECK' not in sql or 'needs_look' in sql:
        return
    rebuilt = sql.replace("'confirmed', 'rejected'", "'confirmed', 'needs_look', 'rejected'")
    assert rebuilt != sql, 'element_state: its state CHECK is not the one this migration knows'
    columns = ', '.join(r[1] for r in conn.execute('PRAGMA table_info(element_state)'))
    with _plain_rename(conn):
        conn.execute('BEGIN IMMEDIATE')
        try:
            conn.execute(re.sub(r'^CREATE TABLE (IF NOT EXISTS )?"?element_state"?', 'CREATE TABLE element_state_rebuilt', rebuilt, count=1))
            conn.execute(f'INSERT INTO element_state_rebuilt({columns}) SELECT {columns} FROM element_state')
            conn.execute('DROP TABLE element_state')
            conn.execute('ALTER TABLE element_state_rebuilt RENAME TO element_state')
            conn.execute('COMMIT')
        except BaseException:
            conn.execute('ROLLBACK')
            raise


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


_ACTOR = object()


def _log(conn, who: str, element_id: str | None, change: str, before=None, after=None, user_id=_ACTOR) -> None:
    """One line of the log. user_id: the account behind `who`; by default the actor's own when `who` is their name. via_token: the label of the token the request
    that wrote it carried (actor.token_mark), None for a person signed in."""
    conn.execute('INSERT INTO log(time, who, element_id, change, before_json, after_json, user_id, via_token) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                 (_now(), who, element_id, change, None if before is None else json.dumps(before, ensure_ascii=False),
                  None if after is None else json.dumps(after, ensure_ascii=False), actor_id_for(who) if user_id is _ACTOR else user_id, token_mark()))


log_line = _log   # for the modules that also record what was before


def log_write(conn, who: str, element_id: str, change: str, after=None) -> None:
    """The trace of a write that keeps its data in a file of its own (a rule, a form, a card): who did it, under what, when."""
    _log(conn, who, element_id, change, after=after)


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
def element_state_writes(conn, changes: list[tuple], versions: dict[str, int] | None = None):
    """Record what a person decided about definitions, all or none, and hold the transaction open for the caller: the
    rows are written but only kept when the block ends without an error, so whatever else must be saved with them (the
    run file) can fail first and take the rows back. Each change is (element_id, state, evidence_ref, confirmed_by) and
    optionally a fifth, the definition confirmed (a dict kept as JSON: the meanings of a code column), a sixth, what it was
    confirmed on and what has changed since (anchors.stored: kept as JSON beside it) and a seventh, `author`: the person whose own definition
    it is (a view), kept as proposed_by next to confirmed_by; a model suggestion a person accepts has none. While two-person confirmation is
    active a definition is never confirmed by its author; when it is off the log marks a self-confirmation. state is checked when the data it was
    confirmed on no longer looks the same: the definition is kept but is not confirmed until a person looks again. state is
    confirmed, rejected, or proposed (taken back, or a definition put forward for another person to confirm); evidence_ref names what backed it ('check_result:12,check_result:13',
    or 'open_item:<id>'); confirmed_by is the person (None when they did not sign). version counts real
    changes: the same state, person, definition and evidence (compared by what the checks found, not by their ids) leaves the row,
    its time and its version as they were. Evidence from an older run never replaces newer evidence already kept.
    `versions` ({element_id: the version the writer read}): inside the write transaction a row that is no longer at that version raises StaleElement and
    nothing is written, so the last writer does not silently win.
    When the caller already holds a transaction the rows join it: they are kept or taken back with whatever else it wrote.
    Yields each element's row as it stands."""
    outer = conn.in_transaction   # a caller that confirms several things as one (batch_confirm) holds the transaction: the rows are kept or taken back with all of them
    if not outer:
        conn.execute('BEGIN IMMEDIATE')   # the write lock now: a transaction that reads first and writes later is refused at once, not waited for, when another holds it
    try:
        two = two_person(conn)
        back: dict[str, dict] = {}   # what a change put back to the version last confirmed, to be confirmed again as it was once the write is in
        for element_id, state, evidence_ref, confirmed_by, *rest in changes:
            content = json.dumps(rest[0], ensure_ascii=False, sort_keys=True) if rest and rest[0] is not None else None
            anchors = json.dumps(rest[1], ensure_ascii=False, sort_keys=True) if len(rest) > 1 and rest[1] is not None else None
            cursor = conn.execute('SELECT * FROM element_state WHERE element_id = ?', (element_id,))
            found = cursor.fetchone()
            before = dict(zip([c[0] for c in cursor.description], found)) if found else None
            if versions and element_id in versions and (before is None or before['version'] != versions[element_id]):
                raise StaleElement(element_id)
            if before:
                kept, kept_at = _evidence(conn, before['evidence_ref'])
                given, given_at = _evidence(conn, evidence_ref)
                if given_at and kept_at > given_at:
                    evidence_ref, given = before['evidence_ref'], kept   # this run is older than the evidence on file
                if (before['state'], before['confirmed_by'], before['content_json'], before['anchors_json'], kept) == (state, confirmed_by, content, anchors, given):
                    continue
            author = rest[2] if len(rest) > 2 else None
            carried = before is not None and author is None and state in ('confirmed', 'checked')   # a confirmation keeps who proposed what it confirms
            proposed_by = before['proposed_by'] if carried else author
            proposer_id = before['proposed_by_user_id'] if carried else actor_id_for(author)
            actor_id = actor_id_for(confirmed_by)
            confirmer_id = actor_id if actor_id is not None else before['confirmed_by_user_id'] if before and before['confirmed_by'] == confirmed_by else None   # a re-check by someone else leaves whose confirmation it was
            self_confirmed = state == 'confirmed' and proposer_id is not None and proposer_id == actor_id
            if self_confirmed and two['active']:
                raise SelfConfirmation(tr('这一条是你自己提的，要另一位来确认', 'You put this forward yourself, so someone else must confirm it'))
            if state == 'confirmed' and before is not None and tracked(element_id) and not may_confirm(conn, before, actor_id):   # the callers say who and how to get out first (object_types.write_confirmation)
                raise SelfConfirmation(tr('这一条在上次确认之后你改过，要另一位来确认', 'You changed this since it was last confirmed, so someone else must confirm it'))
            record, was = next_record(conn, element_id, before, content, state, actor_id)
            if was is not None:
                back[element_id] = was
            after = {'state': state, 'evidence_ref': evidence_ref, 'confirmed_by': confirmed_by, 'confirmed_at': _now(),
                     'version': before['version'] + 1 if before else 1, 'content_json': content, 'anchors_json': anchors}
            conn.execute('INSERT OR REPLACE INTO element_state(element_id, state, evidence_ref, confirmed_by, confirmed_at, version, content_json, anchors_json,'
                         ' proposed_by, confirmed_by_user_id, proposed_by_user_id, changed_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                         (element_id, *after.values(), proposed_by, confirmer_id, proposer_id, record))
            _log(conn, confirmed_by or tr('未署名', 'unsigned'), element_id, state, before=before and _logged({k: before[k] for k in after}),
                 after={**_logged(after), **({'self_confirmed': True} if self_confirmed else {})}, user_id=confirmer_id)
        for element_id, was in back.items():   # after every change of this write is in: what a definition put back stands on may be among them
            restore_if_back(conn, element_id, was)
        rows = {}
        for element_id, *_ in changes:
            cursor = conn.execute('SELECT * FROM element_state WHERE element_id = ?', (element_id,))
            rows[element_id] = dict(zip([c[0] for c in cursor.description], cursor.fetchone()))
        yield rows
        if not outer:
            conn.execute('COMMIT')
    except BaseException:
        if not outer:
            conn.execute('ROLLBACK')
        raise


# --- who changed a definition since it was last confirmed ---------------------------------------------------------------------------------------------
# One rule for every definition kind of the team workspace that a second person confirms (pipelines keep their own: whoever saved its steps since the last
# confirmation, workspace_pipelines._editors). Each keeps, in element_state.changed_json, the set of accounts that changed what it says since it was last
# confirmed (or since it was put forward): {"by": [account ids], "of": a fingerprint of the content the record describes, "was": the confirmed row an edit sent
# back, while it waits}. Nobody in the set and not its proposer may confirm it while two-person confirmation is active (may_confirm); confirming empties it;
# nothing another person does takes a name out of it. The only ways out: what it says is again exactly what was last confirmed (the set empties and, when
# nothing else sent it back, it is confirmed again as it was: restore_if_back), or a person outside the set confirms.
TRACKED = ('objtype:', 'enum:', 'relation:', 'objview:', 'objaction:', 'derived:')


def tracked(element_id: str) -> bool:
    """Whether this rule covers the element: a definition of the team workspace that a second person confirms. The early screen's relations
    (relation:<run>:<name>) share a prefix with the workspace's (relation:<English name>) and are not covered."""
    if element_id.startswith('relation:'):
        return ':' not in element_id[len('relation:'):]
    return element_id.startswith(TRACKED)
CONTENT_WRITES = ('proposed', 'checked', 'edited')   # the log lines of a write that put a definition's content forward or changed it
SINCE = ('confirmed', 'restored')   # the log lines after which a definition is again what a second person confirmed


def fingerprint(content_json: str | None) -> str | None:
    return hashlib.sha256(content_json.encode()).hexdigest()[:16] if content_json else None


def _kept_record(row: dict) -> dict | None:
    """The record of who changed it, when it describes the content as it stands; None when there is none (a file from before it was kept) or when the content was
    changed without it (older code writing to this file): then it is not trusted."""
    kept = json.loads(row['changed_json']) if row.get('changed_json') else None
    return kept if kept is not None and kept.get('of') == fingerprint(row.get('content_json')) else None


def writers_in_log(conn, element_id: str, changes=CONTENT_WRITES, since=SINCE) -> set[int]:
    """The accounts the log says wrote this element's content since its last confirmation (ever, when it never was)."""
    last = conn.execute(f'SELECT MAX(rowid) FROM log WHERE element_id = ? AND change IN ({",".join("?" * len(since))})', (element_id, *since)).fetchone()[0] or 0
    return {u for (u,) in conn.execute(f'SELECT user_id FROM log WHERE element_id = ? AND rowid > ? AND user_id IS NOT NULL AND change IN ({",".join("?" * len(changes))})',
                                       (element_id, last, *changes))}


def changers(conn, row: dict) -> set[int]:
    """The accounts that changed what this definition says since it was last confirmed (or since it was put forward). Without a record that describes the content
    as it stands, everyone the log names as having written it since, and whoever the record names: when in doubt, more people are kept from confirming, not
    fewer. Empty for what this rule does not cover (a pipeline, the early screen's definitions)."""
    if not tracked(row['element_id']):
        return set()
    kept = _kept_record(row)
    if kept is not None:
        return set(kept.get('by') or [])
    stale = json.loads(row['changed_json']) if row.get('changed_json') else {}
    return set(stale.get('by') or []) | writers_in_log(conn, row['element_id'])


def barred(conn, row: dict) -> set[int]:
    """Who may not confirm it while two-person confirmation is active: everyone who changed it since it was last confirmed, and the one who put it forward."""
    return changers(conn, row) | ({row['proposed_by_user_id']} if row.get('proposed_by_user_id') is not None else set())


def may_confirm(conn, row: dict, person_id: int | None) -> bool:
    """The one test of whether this person may confirm this definition (as far as who they are goes): not while two-person confirmation is active and they are in
    barred(). A person with no account (the built-in local admin of a service without sign-in) is not kept out, as before."""
    return person_id is None or not two_person(conn)['active'] or person_id not in barred(conn, row)


def last_confirmed_content(conn, element_id: str) -> str | None:
    found = conn.execute('SELECT content_json FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 1', (element_id,)).fetchone()
    return found[0] if found else None


_WAS = ('content_json', 'evidence_ref', 'confirmed_by', 'confirmed_at', 'anchors_json', 'proposed_by', 'confirmed_by_user_id', 'proposed_by_user_id')


def next_record(conn, element_id: str, before: dict | None, content: str | None, state: str, actor_id: int | None) -> tuple[str | None, dict | None]:
    """(the record to keep with this write, the confirmed row to put back when the content is again what was last confirmed). A confirmation empties the set; a
    change of the content adds its writer, unless the content is again exactly what was last confirmed, which empties it; a write that changes nothing of the content
    keeps it. An edit that sends a confirmed definition back keeps the confirmed row it replaced ("was") for as long as it waits, so that putting the content back
    confirms it again as it was."""
    if not tracked(element_id):
        return None, None
    if state == 'confirmed':
        return json.dumps({'by': [], 'of': fingerprint(content)}), None
    kept = _kept_record(before) if before else None
    was = (kept or {}).get('was')
    by = changers(conn, before) if before else set()
    if before is None or content != before['content_json']:
        if before is not None and before['state'] == 'confirmed':
            was = {**{k: before[k] for k in _WAS}, 'deps': [d for (d,) in conn.execute('SELECT depends_on FROM element_dep WHERE element_id = ? ORDER BY depends_on', (element_id,))]}
        if content is not None and content == last_confirmed_content(conn, element_id):
            by = set()
        elif actor_id is not None:
            by = by | {actor_id}
    record = {'by': sorted(by), 'of': fingerprint(content), **({'was': was} if was else {})}
    return json.dumps(record, ensure_ascii=False, sort_keys=True), (was if was and content == was['content_json'] and state in ('proposed', 'checked') else None)


def _stands_as_confirmed(conn, element_id: str, was: dict) -> bool:
    """Whether nothing but the edit sent it back: the datasets it was last confirmed on are still at those versions, and everything it read then is confirmed now."""
    found = conn.execute('SELECT dataset_versions_json FROM confirmation WHERE element_id = ? ORDER BY id DESC LIMIT 1', (element_id,)).fetchone()
    for name, version in (json.loads(found[0]) if found and found[0] else {}).items():
        now = current_dataset(conn, name)
        if now is None or now['version'] != version:
            return False
    for dep in was.get('deps') or []:
        if dep.startswith('column:'):
            continue
        if dep.startswith('dataset:'):   # the pipelines that write it
            if conn.execute("SELECT 1 FROM element_dep d LEFT JOIN element_state s ON s.element_id = d.depends_on WHERE d.element_id = ? AND (s.state IS NULL OR s.state != 'confirmed')", (dep,)).fetchone():
                return False
            continue
        held = conn.execute('SELECT state FROM element_state WHERE element_id = ?', (dep,)).fetchone()
        if held is None or held[0] != 'confirmed':
            return False
    return True


def restore_if_back(conn, element_id: str, was: dict) -> bool:
    """Inside the caller's transaction: a definition an edit sent back whose content is again exactly what was last confirmed is confirmed again as it was (the same
    person, time, evidence and anchors; no new confirmation is recorded) when nothing else sent it back (_stands_as_confirmed). The log says it was put back."""
    row = conn.execute('SELECT state, content_json, version FROM element_state WHERE element_id = ?', (element_id,)).fetchone()
    if row is None or row[0] not in ('proposed', 'checked') or row[1] != was['content_json'] or not _stands_as_confirmed(conn, element_id, was):
        return False
    conn.execute("UPDATE element_state SET state = 'confirmed', evidence_ref = ?, confirmed_by = ?, confirmed_at = ?, anchors_json = ?, proposed_by = ?, confirmed_by_user_id = ?, "
                 "proposed_by_user_id = ?, reason = NULL, cause = NULL, via = NULL, changed_json = ? WHERE element_id = ?",
                 (was['evidence_ref'], was['confirmed_by'], was['confirmed_at'], was['anchors_json'], was['proposed_by'], was['confirmed_by_user_id'], was['proposed_by_user_id'],
                  json.dumps({'by': [], 'of': fingerprint(was['content_json'])}), element_id))
    actor = current_actor()
    _log(conn, actor['display_name'] if actor else tr('未署名', 'unsigned'), element_id, 'restored', before={'state': row[0], 'version': row[2]},
         after={'state': 'confirmed', 'confirmed_by': was['confirmed_by'], 'confirmed_at': was['confirmed_at'], 'version': row[2]})
    return True


def drop_was(conn, element_id: str) -> None:
    """Something other than an edit sent it back (a person sent it back): putting its content back no longer confirms it again by itself."""
    conn.execute("UPDATE element_state SET changed_json = json_remove(changed_json, '$.was') WHERE element_id = ? AND changed_json IS NOT NULL", (element_id,))


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


def fan_note() -> str:
    return tr('含重复计算：关联后一行变多行', 'Counts repeated rows: a join turned one row into several')


def fan_marks(conn, dataset_id: int) -> set[str]:
    """The columns of this version of a dataset that a pipeline wrote from a figure a join repeated (FAN_NOTE)."""
    return {c for (c,) in conn.execute('SELECT column_name FROM column_fan WHERE dataset_id = ?', (dataset_id,))}


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
                   rows_in: int | None = None, dropped: dict | None = None, mode: str | None = None, changes: dict | None = None,
                   reuse: bool = True, keeps_current: bool = False) -> dict:
    """Store every record as a row of a new dataset version, or return the version already holding this content (reuse=False always
    stores a new one); either way that version becomes the current one, unless keeps_current: then the name's current version is left
    where it is (a name with none gets this one). The run-based screen imports that way: what it imports is its own run's, and a
    person's choice of current version in the workspace is not its to change. rows_in is the number of data rows in the file and dropped says
    how many of them the reader left out and why ({'blank': 2, 'title': 1}); without them the records are all there was.
    mode ('new', 'update_by_key', 'overwrite') and changes ({'changed', 'added', 'unchanged', ...}) are kept on the version beside who.
    Raises RowCountMismatch, writing nothing, when the rows do not add up or what was stored is not what was received."""
    dropped = {k: n for k, n in (dropped or {}).items() if n}
    expected = len(records)
    rows_in = expected + sum(dropped.values()) if rows_in is None else rows_in
    if rows_in != expected + sum(dropped.values()):
        raise RowCountMismatch(tr(f'{name}：文件里有 {rows_in} 行，读到 {expected} 行、丢掉 {sum(dropped.values())} 行，对不上，已取消导入', f'{name}: the file has {rows_in} rows, {expected} were read and {sum(dropped.values())} dropped, which does not add up, so the import was cancelled'))
    existing = _dataset(conn, 'name = ? AND file_sha256 = ? ORDER BY version DESC LIMIT 1', (name, file_sha256)) if reuse else None
    if existing:
        if not (keeps_current and current_dataset(conn, name)):
            _set_current(conn, who, existing)
        return {**existing, 'reused': True}
    names = _unique_names(records)
    if not names:
        raise ValueError(f'{name}: no columns to store')
    if mode is None and keeps_current and not current_dataset(conn, name):
        mode = 'new'   # the first version of a name, made by the old screen: a new dataset like any other, so it shows in Tasks
    originals = list(dict.fromkeys(k for r in records for k in r))
    outer = conn.in_transaction   # a caller that writes more with the version (an approved action) holds the transaction: it commits or rolls back with them
    if not outer:
        conn.execute('BEGIN IMMEDIATE')   # the write lock now: a transaction that reads first and writes later is refused at once, not waited for, when another holds it
    try:
        version = (conn.execute('SELECT COALESCE(MAX(version), 0) FROM dataset WHERE name = ?', (name,)).fetchone()[0]) + 1
        dataset_id = conn.execute('INSERT INTO dataset(name, version, origin, file_sha256, rows_in, rows_stored, table_name, imported_at, dropped_json, who, mode, changes_json, who_user_id)'
                                  " VALUES (?, ?, ?, ?, ?, 0, '', ?, ?, ?, ?, ?, ?)",
                                  (name, version, origin, file_sha256, rows_in, _now(), json.dumps(dropped) if dropped else None, who, mode,
                                   None if changes is None else json.dumps(changes, ensure_ascii=False), actor_id_for(who))).lastrowid
        table = f'ds_{dataset_id}'
        conn.execute(f'CREATE TABLE {_quote(table)} ({", ".join(_quote(n) + " TEXT" for n in names)})')
        conn.executemany(f'INSERT INTO {_quote(table)} VALUES ({", ".join("?" * len(names))})',
                         ([r.get(n) for n in originals] for r in records))
        rows_stored = conn.execute(f'SELECT COUNT(*) FROM {_quote(table)}').fetchone()[0]
        if rows_stored != expected:
            raise RowCountMismatch(tr(f'{name}：读到 {expected} 行，只存入 {rows_stored} 行，已取消导入', f'{name}: {expected} rows were read but only {rows_stored} stored, so the import was cancelled'))
        conn.execute('UPDATE dataset SET rows_stored = ?, table_name = ? WHERE id = ?', (rows_stored, table, dataset_id))
        for position, column in enumerate(names):
            d = _describe([row[0] for row in conn.execute(f'SELECT {_quote(column)} FROM {_quote(table)}')])
            conn.execute('INSERT INTO "column" VALUES (?, ?, ?, ?, ?, ?, ?)',
                         (dataset_id, column, position, d['inferred_type'], d['distinct_count'], d['missing_count'], d['value_counts_json']))
        if not (keeps_current and conn.execute('SELECT 1 FROM current_dataset WHERE name = ?', (name,)).fetchone()):
            conn.execute('INSERT OR REPLACE INTO current_dataset(name, dataset_id) VALUES (?, ?)', (name, dataset_id))
        _log(conn, who, f'dataset:{name}', f'import v{version}: {rows_in} rows in the file, {rows_stored} stored, {sum(dropped.values())} dropped',
             after={'version': version, 'rows_in': rows_in, 'rows_stored': rows_stored, 'dropped': dropped, 'file_sha256': file_sha256})
        if not outer:
            conn.execute('COMMIT')
    except BaseException:
        if not outer:
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
        negative = text.startswith('-')
        whole, _, fraction = text.lstrip('-').partition('.')   # on the digits as written: a number of any length keeps every digit
        fraction = fraction.rstrip('0')
        if whole == '0' and not fraction:
            return '0'
        return ('-' if negative else '') + whole + ('.' + fraction if fraction else '')
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
        raise ValueError(tr('按主键更新要先选出主键列', 'Updating by key needs the key columns chosen first'))
    here = list(dict.fromkeys(k for r in current for k in r))
    there = list(dict.fromkeys(k for r in incoming for k in r))
    for column in key_columns:
        if column not in there:
            raise ValueError(tr(f'新文件里没有主键列“{column}”，没法按它更新', f'The new file has no key column "{column}", so it cannot update by it'))
        if column not in here:
            raise ValueError(tr(f'现有数据里没有“{column}”这一列，没法按它更新', f'The existing data has no column "{column}", so it cannot update by it'))
    empty = sum(1 for r in incoming if any(r.get(c) in (None, '') for c in key_columns))
    if empty:
        raise ValueError(tr(f'新文件里有 {empty} 行的主键是空的，对不上现有的行，请先补上或删掉这些行', f'{empty} rows in the new file have an empty key and cannot be matched to existing rows. Fill them in or remove them first'))
    seen: dict[tuple, int] = {}
    for r in incoming:
        seen[_key_of(r, key_columns)] = seen.get(_key_of(r, key_columns), 0) + 1
    repeated = [k for k, n in seen.items() if n > 1]
    if repeated:
        raise ValueError(tr(f'新文件里主键“{_shown(repeated[0])}”出现了 {seen[repeated[0]]} 行（共 {len(repeated)} 个主键重复），不知道取哪一行', f'In the new file the key "{_shown(repeated[0])}" appears in {seen[repeated[0]]} rows ({len(repeated)} keys repeat in all), so it is unclear which row to take'))
    where: dict[tuple, list[int]] = {}
    for i, r in enumerate(current):
        where.setdefault(_key_of(r, key_columns), []).append(i)
    clash = [k for k in seen if len(where.get(k, ())) > 1]
    if clash:
        raise ValueError(tr(f'现有数据里主键“{_shown(clash[0])}”有 {len(where[clash[0]])} 行（共 {len(clash)} 个主键），按主键更新会分不清改哪一行', f'In the existing data the key "{_shown(clash[0])}" is in {len(where[clash[0]])} rows ({len(clash)} keys in all), so updating by key could not tell which row to change'))
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
DELETED = 'deleted'   # the log line of a dataset removed with all its versions
NO_CHANGE = 'no change'   # the log line of an upload that changed nothing and wrote no version (its mode is in the line's detail)


def plan_upload(conn, name: str, records: list[dict], *, mode: str | None = None, key_columns: list[str] | None = None,
                rows_in: int | None = None, dropped: dict | None = None) -> dict:
    """What saving this file under `name` would do, decided without writing: the records the new version holds, its mode and the
    counts. No mode means a new dataset: refused when the name is taken, because which one is meant is the person's to say.
    Raises ValueError (plain Chinese) for anything that cannot be done without guessing."""
    current = current_dataset(conn, name)
    if mode not in (None, *UPLOAD_MODES):
        raise ValueError(tr('导入方式只有按主键更新（update_by_key）和覆盖（overwrite）两种', 'The import mode can only be update by key (update_by_key) or overwrite (overwrite)'))
    if mode is None:
        if current:
            raise ValueError(tr(f'已经有叫“{name}”的数据集。要更新它，请指定数据集和方式：按主键更新或覆盖；要新建，请换一个名字', f'There is already a dataset named "{name}". To update it, name the dataset and the mode (update by key or overwrite); to create a new one, pick another name'))
        return {'name': name, 'mode': 'new', 'records': records, 'rows_in': rows_in, 'dropped': dropped, 'unchanged': False,
                'changes': {'changed': 0, 'added': len(records), 'unchanged': 0}}
    if current is None:
        raise ValueError(tr(f'没有叫“{name}”的数据集，不能{"按主键更新" if mode == "update_by_key" else "覆盖"}它', f'There is no dataset named "{name}", so it cannot be {"updated by key" if mode == "update_by_key" else "overwritten"}'))
    if mode == 'overwrite':
        return {'name': name, 'mode': mode, 'records': records, 'rows_in': rows_in, 'dropped': dropped, 'unchanged': False,
                'changes': {'replaced_rows': current['rows_stored']}}
    if not isinstance(key_columns, list) or not key_columns or not all(isinstance(c, str) and c for c in key_columns):
        raise ValueError(tr('主键列要写成列名的列表，例如 ["订单号"]', 'The key columns must be a list of column names, for example ["Order ID"]'))
    if len(set(key_columns)) != len(key_columns):
        raise ValueError(tr(f'主键列里有重复的列：{tr("、", ", ").join(c for c in dict.fromkeys(key_columns) if key_columns.count(c) > 1)}', f'The key columns repeat a column: {", ".join(c for c in dict.fromkeys(key_columns) if key_columns.count(c) > 1)}'))
    merged, counts = merge_by_key(dataset_records(conn, current), records, key_columns)
    file_rows = len(records) + sum((dropped or {}).values())
    return {'name': name, 'mode': mode, 'records': merged, 'rows_in': None, 'dropped': None, 'key_columns': list(key_columns),
            'unchanged': not (counts['changed'] or counts['added']), 'current': current,
            'changes': {**counts, 'file_rows': rows_in if rows_in is not None else file_rows, 'key_columns': list(key_columns)}}


def apply_upload(conn, plan: dict, who: str, origin: str = 'upload') -> dict:
    """Write what plan_upload decided as the next version of the dataset, recording who and the counts with it. An update that
    changes and adds nothing, and an overwrite with what the current version already holds, write nothing: {'created': False} and a
    line in the log. Content an older version holds is written as a new version of its own, and says which it equals
    (changes['same_as']): a person's upload never moves the current version quietly. Otherwise {'created': True, 'dataset': the
    version, 'key_check': ...} where key_check is the key check of an update's key columns on the rows now stored."""
    name, records = plan['name'], plan['records']
    sha = records_sha256(records)
    twin = None if plan['mode'] == 'new' else _dataset(conn, 'name = ? AND file_sha256 = ? ORDER BY version DESC LIMIT 1', (name, sha))
    current = current_dataset(conn, name) if plan['mode'] != 'new' else None
    if plan['unchanged'] or (plan['mode'] == 'overwrite' and twin and twin['id'] == current['id']):
        _log(conn, who, f'dataset:{name}', NO_CHANGE, after={**plan['changes'], 'mode': plan['mode']})   # the only trace of an upload that wrote no version
        return {'created': False, 'dataset': current, 'mode': plan['mode'], 'changes': plan['changes'], 'reused': False}
    changes = {**plan['changes'], **({'same_as': twin['version']} if twin else {})}
    dataset = import_records(conn, name, records, origin, sha, who, plan['rows_in'], plan['dropped'], mode=plan['mode'], changes=changes, reuse=False)
    key_check = check_key(conn, dataset['id'], plan['key_columns']) if plan.get('key_columns') else None
    return {'created': True, 'dataset': dataset, 'mode': plan['mode'], 'changes': changes, 'reused': False, 'key_check': key_check}


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


def check_key(conn, dataset_id: int, columns: list[str], record: bool = True) -> dict:
    """Is this column set unique and filled across every stored row? Records the query, the rows looked at, the extra
    rows beyond the first per key, up to five duplicated keys, and the rows with an empty key column. Either failure fails, and so does a
    version with no rows: a check that looked at nothing has not passed. `record=False`: the same check read only (a page asking whether a type
    can be confirmed now), kept nowhere, with no id."""
    dataset, cols, filled, table = _key_context(conn, dataset_id, columns)
    query = (f'SELECT {cols}, COUNT(*) AS n FROM {table} WHERE {filled} GROUP BY {cols} HAVING COUNT(*) > 1 '
             'ORDER BY n DESC, ' + cols)
    rows_checked = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    null_key_rows = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE NOT ({filled})').fetchone()[0]
    violations = conn.execute(f'SELECT COALESCE(SUM(n - 1), 0) FROM ({query})').fetchone()[0]
    samples = [{'key': dict(zip(columns, row[:-1])), 'count': row[-1]}
               for row in conn.execute(f'{query} LIMIT {SAMPLE_LIMIT}')]
    status = 'failed' if violations or null_key_rows or not rows_checked else 'passed'
    if not record:
        return {'id': None, 'element_id': f'key:{dataset["name"]}({",".join(columns)})', 'check_type': 'key_unique', 'dataset': dataset['name'], 'dataset_id': dataset['id'], 'columns': list(columns),
                'query': query, 'rows_checked': rows_checked, 'violations': violations, 'null_key_rows': null_key_rows, 'samples': samples, 'status': status}
    return _record_check(conn, dataset, columns, 'key_unique', query, rows_checked, violations, null_key_rows, samples, status)


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


def check_bundle(conn, ontology: dict, bundle: dict, origin: str, relations: bool = True, who: str = 'system') -> dict:
    """Import every source table of a bundle, then check each object type's identity columns as a key (or, for a
    reference column, as a list of values). 'tables': one entry per table with the rows in the file, rows stored and
    rows dropped; a table that cannot be stored says why and the others go on. 'keys': one entry per checked
    population; a failed check is reported as failed and nothing is fixed. 'relations': each relation checked against the stored
    tables (relation_checks); `relations=False` leaves them out. `who` signs the dataset versions it writes: the person who started the build."""
    tables, datasets = [], {}
    for name, s in bundle['sources'].items():
        read = s.get('rows_read')
        dropped = s.get('dropped_rows')
        try:
            d = import_records(conn, name, s['records'], origin, records_sha256(s['records']), who, rows_in=read, dropped=dropped, keeps_current=True)
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
