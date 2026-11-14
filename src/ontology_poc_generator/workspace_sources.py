"""Live data sources: a PostgreSQL or MySQL connection an admin sets up, the tables a builder reads from it as datasets, and the log of every pull.

A pulled table goes through the same door as an uploaded file (plan_upload, apply_upload, recheck_after_write in workspace_store and object_types): the rows
become a new dataset version, typed from their text, and whatever was confirmed on the version before is checked against it, so a pull that moves the data
sends the confirmed definitions that read it to needs_look with the cause 数据变了. The version says where it came from: origin `source:<name>/<table>` and the
time it was pulled.

Who sees what. The password is sealed (source_vault) and appears nowhere else. The connection details (host, port, database, account, what the driver said when it
failed) are an admin's. Everything a person reads of a pull, a table or a schedule is filtered by what they may see of the dataset or pipeline it concerns
(dataset_hidden, pipeline_visible): what is kept from them is not named, not counted, and its keys and changes are not quoted.
"""
from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path

from ontology_poc_generator.object_actions import overwritten_by_upload
from ontology_poc_generator.object_types import recheck_after_write
from ontology_poc_generator.source_connect import (
    DEFAULT_PORTS, GENERIC, KINDS, MAX_PULL_ROWS, TLS_MODES, SourceError, check_host, connect, describe, records_of)
from ontology_poc_generator.source_vault import seal, unseal
from ontology_poc_generator.type_access import dataset_hidden
from ontology_poc_generator.workspace_store import (
    UPLOAD_MODES, apply_upload, current_dataset, dataset_records, log_write, now_text, plan_upload)

NAME_LIMIT = 60
TEXT_LIMIT = 253
LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1', '[::1]'}
STATUS_WORDS = {'untested': '未测试', 'ok': '正常', 'failed': '失败'}
ORIGIN_PREFIX = 'source:'
RUN_LIST_LIMIT = 50
TABLE_CACHE_SECONDS = 600   # a builder's look at the table list is the database's answer of up to ten minutes ago; an admin's test is always fresh
HIDDEN_ERROR = '这个数据集你看不到，细节只给能看它的人'
INTERNAL_ERROR = '读取时出了内部错误，详情见服务日志'

_active: set[tuple] = set()   # what is being pulled or run right now, by (kind, target, item): a second one for the same thing does not start
_active_lock = threading.Lock()
_table_cache: dict[str, tuple[float, list]] = {}   # source name -> (when, the database's table list)


@contextlib.contextmanager
def claimed(key: tuple):
    """Yields whether this caller got the key; the key is free again when the block ends."""
    with _active_lock:
        got = key not in _active
        if got:
            _active.add(key)
    try:
        yield got
    finally:
        if got:
            with _active_lock:
                _active.discard(key)


class NotFound(ValueError):
    """Nothing of that name for this person: the same words whether it does not exist or is kept from them, so asking is no way to find out which."""


def is_admin(user: dict | None) -> bool:
    return user is None or user['role'] == 'admin'


def origin_of(source: str, table: str) -> str:
    return f'{ORIGIN_PREFIX}{source}/{table}'


def _directory(conn) -> Path | None:
    """Where the workspace file lives (the key of the sealed passwords is beside it); None for a workspace in memory."""
    path = conn.execute('PRAGMA database_list').fetchone()[2]
    return Path(path).parent if path else None


def _row(conn, name) -> dict:
    cursor = conn.execute('SELECT * FROM data_source WHERE name = ?', (str(name or ''),))
    found = cursor.fetchone()
    if found is None:
        raise KeyError(name)
    return dict(zip([c[0] for c in cursor.description], found))


def _bound(conn, source_id: int) -> list[dict]:
    cursor = conn.execute('SELECT table_name, dataset, mode, key_json FROM source_table WHERE source_id = ? ORDER BY table_name', (source_id,))
    return [{'table': t, 'dataset': d, 'mode': m, 'key_columns': json.loads(k) if k else None} for t, d, m, k in cursor]


def bound_for(conn, source_id: int, user: dict | None) -> list[dict]:
    """The tables of a source read as datasets, leaving out the ones whose dataset is kept from this person."""
    return [b for b in _bound(conn, source_id) if not dataset_hidden(conn, b['dataset'], user)]


def _binding(conn, source_id: int, table: str) -> dict | None:
    found = conn.execute('SELECT dataset, mode, key_json FROM source_table WHERE source_id = ? AND table_name = ?', (source_id, table)).fetchone()
    return None if found is None else {'dataset': found[0], 'mode': found[1], 'key_columns': json.loads(found[2]) if found[2] else None}


def _bound_elsewhere(conn, source_id: int, table: str, dataset: str) -> bool:
    """Whether this dataset is already the reading of another table (or another source): two sources cannot feed one dataset, their versions would mix."""
    return conn.execute('SELECT 1 FROM source_table WHERE dataset = ? AND NOT (source_id = ? AND table_name = ?)', (dataset, source_id, table)).fetchone() is not None


def public_source(conn, row: dict, user: dict | None) -> dict:
    """A source as a page reads it. Whoever may use it sees its name, kind, whether it works (a status word and, when it failed, a general reason), whether the
    connection is encrypted and the tables they may see read as datasets. The connection details, what the driver said and which privileges the account has are an
    admin's. Never the password, not even sealed: `has_password` says one is kept."""
    admin = is_admin(user)
    failed = row['status'] == 'failed'
    out = {'name': row['name'], 'kind': row['kind'], 'kind_label': KINDS[row['kind']], 'status': row['status'], 'status_label': STATUS_WORDS[row['status']],
           'status_at': row['status_at'], 'status_note': row['status_note'] if admin else (GENERIC if failed else None),
           'can_write': None if row['can_write'] is None else bool(row['can_write']), 'tls': row['tls'] or 'required', 'tables': bound_for(conn, row['id'], user)}
    if admin:
        out |= {'write_note': row['write_note'], 'host': row['host'], 'port': row['port'], 'database': row['database'], 'username': row['username'], 'has_password': True,
                'local': row['host'].strip('[]').lower() in LOCAL_HOSTS, 'created_by': row['created_by'], 'created_at': row['created_at']}
    return out


def list_sources(conn, user: dict | None) -> list[dict]:
    cursor = conn.execute('SELECT * FROM data_source ORDER BY name')
    columns = [c[0] for c in cursor.description]
    return [public_source(conn, dict(zip(columns, r)), user) for r in cursor.fetchall()]


def source_detail(conn, name: str, user: dict | None) -> dict | None:
    try:
        row = _row(conn, name)
    except KeyError:
        return None
    return {**public_source(conn, row, user), 'runs': refresh_runs(conn, 'source', row['name'], user=user), 'schedules': _schedules_of(conn, row['name'], user)}


def _schedules_of(conn, name: str, user: dict | None) -> list[dict]:
    from ontology_poc_generator.workspace_schedules import list_schedules   # workspace_schedules reads this module
    return [s for s in list_schedules(conn, user) if s['kind'] == 'source' and s['target'] == name]


# --- setting a source up ---------------------------------------------------------------------------------------------------------------------------

def _text(payload: dict, field: str, label: str, limit: int = TEXT_LIMIT, required: bool = True) -> str | None:
    value = payload.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f'要填{label}')
        return None
    if not isinstance(value, str):
        raise ValueError(f'{label}要写成文字')
    if len(value.strip()) > limit:
        raise ValueError(f'{label}不能超过 {limit} 个字符')
    return value.strip()


def _connection_fields(payload: dict, kind: str) -> dict:
    host = _text(payload, 'host', '主机')
    if re.search(r'[\s/@?#]', host) or '://' in host:
        raise ValueError('主机只写地址，例如 db.example.com 或 10.0.0.5，不要带协议、路径或账号')
    try:
        check_host(host)
    except SourceError as exc:
        raise ValueError(str(exc)) from None
    port = payload.get('port', DEFAULT_PORTS[kind])
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError('端口要写成 1 到 65535 的整数')
    return {'host': host, 'port': port, 'database': _text(payload, 'database', '数据库名'), 'username': _text(payload, 'username', '账号')}


def _tls(payload: dict, host: str, current: str | None = None) -> str:
    """The encryption setting: what the request says, else what the source had, else "required" unless the database is on this machine."""
    tls = payload.get('tls', current if current is not None else ('none' if host.strip('[]').lower() in LOCAL_HOSTS else 'required'))
    if tls not in TLS_MODES:
        raise ValueError('加密只能选“必须”（核对证书，默认）或“不用”（密码和数据会明文过网络）')
    return tls


def _name_taken(conn, name: str) -> bool:
    return conn.execute('SELECT 1 FROM data_source WHERE name = ?', (name,)).fetchone() is not None


def create_source(conn, payload: dict, who: str | None) -> dict:
    """{name, kind, host, port?, database, username, password, tls?}: save a source, status 未测试. The password is sealed on the way in."""
    name = _text(payload, 'name', '数据源的名字', NAME_LIMIT)
    if re.search(r'[/@\\]', name):
        raise ValueError('数据源的名字里不能有 / @ \\（它会写进数据集的来源里）')
    kind = payload.get('kind')
    if kind not in KINDS:
        raise ValueError('数据库类型只能选 PostgreSQL 或 MySQL')
    fields = _connection_fields(payload, kind)
    tls = _tls(payload, fields['host'])
    password = payload.get('password')
    if not isinstance(password, str) or not password:
        raise ValueError('要填密码')
    if _name_taken(conn, name):
        raise ValueError(f'已经有叫“{name}”的数据源')
    stamp, signer = now_text(), str(who or '').strip() or '未署名'
    try:
        conn.execute('INSERT INTO data_source(name, kind, host, port, database, username, secret, tls, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                     (name, kind, fields['host'], fields['port'], fields['database'], fields['username'], seal(_directory(conn), password), tls, signer, stamp, stamp))
    except sqlite3.IntegrityError:   # another request made the same name between the check and the write
        raise ValueError(f'已经有叫“{name}”的数据源') from None
    log_write(conn, signer, f'source:{name}', 'created', {'kind': kind, 'host': fields['host'], 'port': fields['port'], 'database': fields['database'], 'tls': tls})
    return public_source(conn, _row(conn, name), None)


def update_source(conn, payload: dict, who: str | None) -> dict:
    """{name, host, port, database, username, password?, tls?}: change the connection. The name stays (datasets say where they came from by it). A blank password
    keeps the one saved, but only while the host, port, database and account are what they were: the saved password is not sent to a new place without its owner
    typing it again. The status goes back to 未测试."""
    try:
        row = _row(conn, payload.get('name'))
    except KeyError:
        raise ValueError('没有这个数据源') from None
    fields = _connection_fields({**{k: row[k] for k in ('host', 'port', 'database', 'username')}, **{k: v for k, v in payload.items() if k in ('host', 'port', 'database', 'username')}}, row['kind'])
    password = payload.get('password')
    if password is not None and not isinstance(password, str):
        raise ValueError('密码要写成文字')
    moved = [label for key, label in (('host', '主机'), ('port', '端口'), ('database', '数据库名'), ('username', '账号')) if fields[key] != row[key]]
    if moved and not password:
        raise ValueError(f'改了{"、".join(moved)}，要重新填密码：保存的密码不会自己送到新的地方去')
    tls = _tls(payload, fields['host'], row['tls'] or 'required')
    secret = seal(_directory(conn), password) if password else row['secret']
    signer = str(who or '').strip() or '未署名'
    conn.execute("UPDATE data_source SET host = ?, port = ?, database = ?, username = ?, secret = ?, tls = ?, status = 'untested', status_at = NULL, status_note = NULL, can_write = NULL, "
                 'write_note = NULL, updated_at = ? WHERE id = ?', (fields['host'], fields['port'], fields['database'], fields['username'], secret, tls, now_text(), row['id']))
    _table_cache.pop(row['name'], None)
    log_write(conn, signer, f'source:{row["name"]}', 'updated', {'host': fields['host'], 'port': fields['port'], 'database': fields['database'], 'tls': tls, 'password_changed': bool(password)})
    return public_source(conn, _row(conn, row['name']), None)


def delete_source(conn, name: str, who: str | None) -> dict:
    """Refused (ValueError naming the datasets) while any dataset comes from it; its schedules go with it. The check and the delete are one transaction: a pull that
    finishes in between cannot leave a dataset pointing at a source that is gone. Returns {'name', 'schedules'}."""
    row = _row(conn, name)   # KeyError: no such source
    signer = str(who or '').strip() or '未署名'
    conn.execute('BEGIN IMMEDIATE')
    try:
        bound = [d for (d,) in conn.execute('SELECT dataset FROM source_table WHERE source_id = ? ORDER BY dataset', (row['id'],))]
        if bound:
            raise ValueError(f'有 {len(bound)} 个数据集来自“{row["name"]}”：' + '、'.join(f'「{d}」' for d in bound) + '。先删掉它们，再删数据源')
        gone = conn.execute("DELETE FROM schedule WHERE kind = 'source' AND target = ?", (row['name'],)).rowcount
        conn.execute('DELETE FROM data_source WHERE id = ?', (row['id'],))
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    _table_cache.pop(row['name'], None)
    log_write(conn, signer, f'source:{row["name"]}', 'deleted', {'schedules': gone})
    return {'name': row['name'], 'schedules': gone}


# --- talking to the database -----------------------------------------------------------------------------------------------------------------------

@contextlib.contextmanager
def _open(conn, row: dict):
    """An open connection to the source, with every failure turned into a SourceError whose text holds no password (and whose `public` text holds nothing of the database)."""
    password = unseal(_directory(conn), row['secret'])
    live = connect(row['kind'], row['host'], row['port'], row['database'], row['username'], password, row['tls'] or 'required')
    try:
        yield live
    except SourceError:
        raise
    except Exception as exc:
        raise SourceError(describe(exc, password), GENERIC) from None
    finally:
        with contextlib.suppress(Exception):   # a close that fails has nothing to say the person needs
            live.close()


def _annotated(conn, row: dict, tables: list[dict], user: dict | None) -> list[dict]:
    """The table list with the dataset each is already read as; a table read as a dataset this person may not see says only that (hidden)."""
    bound = {b['table']: b['dataset'] for b in _bound(conn, row['id'])}
    out = []
    for t in tables:
        dataset = bound.get(t['name'])
        hidden = dataset is not None and dataset_hidden(conn, dataset, user)
        out.append({**t, 'dataset': None if hidden else dataset, 'hidden': hidden})
    return out


def test_source(conn, name: str, who: str | None) -> dict:
    """Connect, list the tables (the database's own row estimates) and check whether the account can write. The result is kept on the source (正常 or 失败 and when).
    Returns {status, status_label, note, tables, can_write, write_note}; a failure comes back as status 失败 with its reason, not as an error. An admin's call."""
    row = _row(conn, name)
    result = {'status': 'failed', 'tables': [], 'can_write': None, 'write_note': None}
    try:
        with _open(conn, row) as live:
            tables = live.tables()
            writes, why = live.writes()
        _table_cache[row['name']] = (time.monotonic(), tables)
        result = {'status': 'ok', 'tables': tables, 'can_write': writes, 'write_note': why or None}
        note = None if not writes else f'这个账号不是只读的：{why}。建议换一个只有 SELECT 权限的账号'
    except (SourceError, ValueError) as exc:
        note = str(exc)
        _table_cache.pop(row['name'], None)   # what a failed look found is that the last list can no longer be trusted
    conn.execute('UPDATE data_source SET status = ?, status_at = ?, status_note = ?, can_write = ?, write_note = ? WHERE id = ?',
                 (result['status'], now_text(), note, None if result['can_write'] is None else int(result['can_write']), result['write_note'], row['id']))
    log_write(conn, str(who or '').strip() or '未署名', f'source:{row["name"]}', 'tested', {'status': result['status']})
    return {**result, 'status_label': STATUS_WORDS[result['status']], 'note': note, 'tables': _annotated(conn, row, result['tables'], None)}


def source_tables(conn, name: str, user: dict | None) -> list[dict]:
    """The tables a builder can pick from a source: the database's own row estimates, as they were up to TABLE_CACHE_SECONDS ago (one look at the database serves every
    click), each with the dataset it is already read as. While one look is under way another asks to wait, or gets the last answer. SourceError otherwise."""
    row = _row(conn, name)
    cached = _table_cache.get(row['name'])
    if cached is None or time.monotonic() - cached[0] >= TABLE_CACHE_SECONDS:
        with claimed(('source', row['name'], '')) as got:
            if got:
                with _open(conn, row) as live:
                    cached = (time.monotonic(), live.tables())
                _table_cache[row['name']] = cached
            elif cached is None:
                raise SourceError('另一个请求正在读这个数据源的表列表，稍等几秒再试')
    return _annotated(conn, row, cached[1], user)


# --- pulling ---------------------------------------------------------------------------------------------------------------------------------------

def _run_view(row: dict) -> dict:
    """A run as the log holds it: every field, the error for an admin and the one for everyone else, the changes, the definitions it sent back."""
    detail = json.loads(row['detail_json']) if row['detail_json'] else None
    return {'id': row['id'], 'kind': row['kind'], 'target': row['target'], 'item': row['item'], 'schedule_id': row['schedule_id'], 'reason': row['reason'], 'who': row['who'],
            'status': row['status'], 'started_at': row['started_at'], 'finished_at': row['finished_at'], 'rows': row['rows'], 'dataset': row['dataset'], 'version': row['version'],
            'changed': None if row['changed'] is None else bool(row['changed']), 'error': row['error'], 'error_public': row['error_public'] or row['error'], 'detail': detail}


def visible_run(conn, run: dict, user: dict | None) -> dict | None:
    """What this person may read of a run. Everything for an admin. For anyone else: nothing at all of a pipeline's run when the pipeline is kept from them; of a run
    that wrote a dataset kept from them only that it happened (no dataset, rows, version, changes, keys, error); of the rest the changes with their keys, the number of
    definitions it sent back (not which) and the general reason it failed, not the database's words."""
    if is_admin(user):
        return {k: v for k, v in run.items() if k != 'error_public'}
    if run['kind'] == 'pipeline':
        from ontology_poc_generator.object_types import element_row
        from ontology_poc_generator.workspace_pipelines import pipeline_visible
        pipeline = element_row(conn, f'pipeline:{run["target"]}')
        if pipeline is None or not pipeline_visible(conn, pipeline, user):
            return None
    detail = run['detail'] or {}
    names = [w['dataset'] for w in detail.get('outputs') or []] or [n for n in (run['dataset'] or '').split('、') if n]
    out = {k: v for k, v in run.items() if k != 'error_public'}
    if any(dataset_hidden(conn, n, user) for n in names):
        return {**out, 'dataset': None, 'rows': None, 'version': None, 'changed': None, 'detail': None, 'hidden': True, 'error': HIDDEN_ERROR if run['error'] else None}
    shown = {k: v for k, v in detail.items() if k not in ('flagged', 'recheck_error')}
    if detail.get('recheck_error'):
        shown['recheck_error'] = '有一步检查出了错，请让管理员看详情'
    return {**out, 'error': run['error_public'], 'detail': shown or None, 'hidden': False}


def refresh_runs(conn, kind: str | None = None, target: str | None = None, schedule_id: int | None = None, limit: int = RUN_LIST_LIMIT, user: dict | None = None) -> list[dict]:
    """The log, newest first, as this person may read it (visible_run); `user` None is the local admin."""
    where = [c for c, v in (('kind = ?', kind), ('target = ?', target), ('schedule_id = ?', schedule_id)) if v is not None]
    args = [v for v in (kind, target, schedule_id) if v is not None]
    cursor = conn.execute(f'SELECT * FROM refresh_run {"WHERE " + " AND ".join(where) if where else ""} ORDER BY id DESC LIMIT ?', (*args, limit))
    columns = [c[0] for c in cursor.description]
    shown = (visible_run(conn, _run_view(dict(zip(columns, r))), user) for r in cursor.fetchall())
    return [r for r in shown if r is not None]


def start_run(conn, kind: str, target: str, item: str, reason: str, who: str, schedule_id: int | None = None) -> int:
    return conn.execute('INSERT INTO refresh_run(kind, target, item, schedule_id, reason, who, status, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (kind, target, item, schedule_id, reason, who, 'running', now_text())).lastrowid


def finish_run(conn, run_id: int, status: str, *, rows=None, dataset=None, version=None, changed=None, error=None, error_public=None, detail=None) -> dict:
    """Close a run in the log and return it as the log holds it (the raw view: filter it with visible_run before a person reads it)."""
    conn.execute('UPDATE refresh_run SET status = ?, finished_at = ?, rows = ?, dataset = ?, version = ?, changed = ?, error = ?, error_public = ?, detail_json = ? WHERE id = ?',
                 (status, now_text(), rows, dataset, version, None if changed is None else int(changed), error, error_public if error_public is not None else error,
                  None if detail is None else json.dumps(detail, ensure_ascii=False), run_id))
    cursor = conn.execute('SELECT * FROM refresh_run WHERE id = ?', (run_id,))
    return _run_view(dict(zip([c[0] for c in cursor.description], cursor.fetchone())))


def interrupted_runs(conn) -> int:
    """Called when the service starts: a run still marked running belongs to a process that is gone."""
    return conn.execute("UPDATE refresh_run SET status = 'failed', finished_at = ?, error = '服务重启，这次没有跑完', error_public = '服务重启，这次没有跑完' WHERE status = 'running'", (now_text(),)).rowcount


def _confirmed(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT element_id FROM element_state WHERE state = 'confirmed'")}


def _plan_for(conn, dataset: str, mode: str, key_columns, records: list[dict]) -> dict:
    """What writing these rows under this name does: a new dataset when the name is free, else the mode the table was set up with."""
    existing = current_dataset(conn, dataset)
    return plan_upload(conn, dataset, records, mode=mode if existing else None, key_columns=key_columns if existing and mode == 'update_by_key' else None, rows_in=len(records))


def _taken_text(dataset: str) -> str:
    return f'数据集“{dataset}”已经从另一张表读来，不能再写进去；换一个名字'


def refresh_table(conn, source: dict, table: str, dataset: str, mode: str, key_columns: list[str] | None, who: str, reason: str, lock, *,
                  schedule_id: int | None = None, user: dict | None = None) -> dict:
    """Pull one table into a dataset: read the rows (no lock held while the database answers), then write them as the next version, and the binding of the table to the
    dataset with it, in one transaction under `lock`. The run is logged either way: start, end, rows, version, error. A pull that moves what confirmed definitions read
    sends them to needs_look (cause 数据变了); `detail` counts them. Returns the run as the log holds it (raw: visible_run before a person reads it). A second pull of the
    same table while one runs is not started: refused (manual) or logged as skipped (scheduled). Nothing raises but a manual refusal; an error nobody expected is a
    failed run that says so and is printed to the service's log."""
    key = ('source', source['name'], table)
    with claimed(key) as got:
        if not got:
            if reason == 'manual':
                raise ValueError(f'“{table}”正在拉取，等这一次结束再试')
            return finish_run(conn, start_run(conn, 'source', source['name'], table, reason, who, schedule_id), 'skipped', dataset=dataset, error='上一次拉取还没结束，这次跳过')
        run_id = start_run(conn, 'source', source['name'], table, reason, who, schedule_id)
        try:
            with _open(conn, source) as live:
                columns, rows = live.read(table, MAX_PULL_ROWS + 1)
            if len(rows) > MAX_PULL_ROWS:
                raise SourceError(f'“{table}”超过 {MAX_PULL_ROWS:,} 行，一次读不完。在数据库里建一个只含需要的行和列的视图，再读那个视图')
            records, left_out = records_of(columns, rows)
            if not records or not records[0]:
                raise SourceError(f'“{table}”里没有数据行或没有能读成文字的列' + (f'（二进制列没读：{"、".join(left_out)}）' if left_out else ''))
            with lock:   # the lock an upload takes: the check of what reads the dataset and the write it stands on are not split by other new data
                if dataset_hidden(conn, dataset, user):
                    raise ValueError(f'没有叫“{dataset}”的数据集可以写入，也不能用这个名字新建')
                if _bound_elsewhere(conn, source['id'], table, dataset):
                    raise ValueError(_taken_text(dataset))
                plan = _plan_for(conn, dataset, mode, key_columns, records)
                plan['changes'] = {**plan['changes'], 'source': {'name': source['name'], 'table': table, 'left_out': left_out}}
                current = current_dataset(conn, dataset)
                overwrites = overwritten_by_upload(conn, dataset, dataset_records(conn, current), plan['records']) if current and not plan['unchanged'] else []
                before = _confirmed(conn)
                conn.execute('BEGIN IMMEDIATE')   # apply_upload joins a transaction its caller holds: the version and the binding stand or fall together
                try:
                    done = apply_upload(conn, plan, who, origin=origin_of(source['name'], table))
                    if not _binding(conn, source['id'], table):
                        conn.execute('INSERT INTO source_table(source_id, table_name, dataset, mode, key_json) VALUES (?, ?, ?, ?, ?)',
                                     (source['id'], table, dataset, mode, json.dumps(key_columns, ensure_ascii=False) if key_columns else None))
                    log_write(conn, who, f'source:{source["name"]}', 'pulled', {'table': table, 'dataset': dataset, 'version': done['dataset']['version'], 'created_version': done['created']})
                    conn.execute('COMMIT')
                except sqlite3.IntegrityError:   # another pull bound this dataset between the check and the write: the version is taken back with the binding
                    conn.execute('ROLLBACK')
                    raise ValueError(_taken_text(dataset)) from None
                except BaseException:
                    conn.execute('ROLLBACK')
                    raise
                problem = recheck_after_write(conn, dataset, who) if done['created'] else None
                flagged = sorted(before - _confirmed(conn))
            detail = {'changes': {k: v for k, v in done['changes'].items() if k not in ('source', 'pipeline')}, 'left_out': left_out, 'flagged': flagged, 'flagged_count': len(flagged),
                      'recheck_error': problem, 'overwritten_action_rows': len(overwrites) if done['created'] else 0}
            return finish_run(conn, run_id, 'success', rows=len(records), dataset=dataset, version=done['dataset']['version'], changed=done['created'], detail=detail)
        except (SourceError, ValueError) as exc:
            return finish_run(conn, run_id, 'failed', dataset=dataset, error=str(exc), error_public=getattr(exc, 'public', str(exc)))
        except Exception as exc:   # not ours: the run is not left "running", the person is told something went wrong, and what it was is in the service's log
            print(f'pull of “{table}” from “{source["name"]}” stopped with {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
            return finish_run(conn, run_id, 'failed', dataset=dataset, error=INTERNAL_ERROR)


def pull_table(conn, payload: dict, who: str | None, user: dict | None, lock) -> dict:
    """{source, table, name?, mode?, key_columns?}: read a table of a source as a dataset (named like the table unless `name` says), the first time or again. The
    refresh mode (overwrite, or update_by_key with its key columns) is kept with the table and used by every later refresh. A name that is already a dataset needs
    its mode said, like an upload: what to do with a dataset that exists is never guessed. Refused in words, before anything is read or written, when the dataset is kept
    from this person or already comes from another table. Returns the run, raw (visible_run before a person reads it)."""
    try:
        source = _row(conn, payload.get('source'))
    except KeyError:
        raise ValueError('没有这个数据源') from None
    table = payload.get('table')
    if not isinstance(table, str) or not table:
        raise ValueError('要写明读哪张表（table）')
    signer = str(who or '').strip() or '未署名'
    bound = _binding(conn, source['id'], table)
    if bound and dataset_hidden(conn, bound['dataset'], user):
        raise ValueError('这张表现在不能由你读成数据集')
    mode = payload.get('mode') or (bound['mode'] if bound else 'overwrite')
    keys = payload.get('key_columns') if payload.get('key_columns') is not None else (bound['key_columns'] if bound else None)
    if bound and payload.get('name') not in (None, '', bound['dataset']):
        raise ValueError(f'“{table}”已经读成数据集“{bound["dataset"]}”了；要更新它请用刷新')
    if mode not in UPLOAD_MODES:
        raise ValueError('刷新方式只有按主键更新（update_by_key）和覆盖（overwrite）两种')
    if mode == 'update_by_key' and not (isinstance(keys, list) and keys and all(isinstance(c, str) and c for c in keys)):
        raise ValueError('按主键更新要先选出主键列（key_columns），例如 ["订单号"]')
    name = bound['dataset'] if bound else str(payload.get('name') or table.rsplit('.', 1)[-1]).strip()
    if not name or len(name) > 100:
        raise ValueError('数据集名字要写 1 到 100 个字')
    if dataset_hidden(conn, name, user):
        raise ValueError(f'没有叫“{name}”的数据集可以写入，也不能用这个名字新建')
    if _bound_elsewhere(conn, source['id'], table, name):
        raise ValueError(_taken_text(name))
    if not bound and current_dataset(conn, name) and not payload.get('mode'):
        raise ValueError(f'已经有叫“{name}”的数据集。要把这张表写进去，请指定方式：按主键更新或覆盖；要新建，请换一个名字')
    return refresh_table(conn, source, table, name, mode, keys, signer, 'manual', lock, user=user)


def refresh_dataset(conn, payload: dict, who: str | None, user: dict | None, lock) -> dict:
    """{dataset}: pull again the table this dataset was read from, the way it was set up. The same words for a dataset that does not come from a source and one kept from the asker."""
    name = payload.get('dataset')
    found = conn.execute('SELECT s.table_name, d.name FROM source_table s JOIN data_source d ON d.id = s.source_id WHERE s.dataset = ?', (str(name or ''),)).fetchone()
    if found is None or dataset_hidden(conn, name, user):
        raise ValueError('这不是从数据源读来的数据集，或者你看不到它')
    return pull_table(conn, {'source': found[1], 'table': found[0]}, who, user, lock)
