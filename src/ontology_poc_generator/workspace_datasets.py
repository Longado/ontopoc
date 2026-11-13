"""The workspace's datasets as pages read them: a list, one dataset with its columns, key checks, versions and a preview, and
the upload of table files that either makes a new dataset or updates an existing one on the person's explicit say.

Nothing here knows about runs: a dataset is a name with versions in the workspace file.
"""
from __future__ import annotations

import base64
import binascii
import json
from pathlib import PurePath

from ontology_poc_generator.company_sources import TABLE_SUFFIXES, SourceFileError, load_table_file
from ontology_poc_generator.workspace_store import NO_CHANGE, UPLOAD_MODES, apply_upload, current_dataset, plan_upload

PREVIEW_ROWS = 50
MAX_NAME = 100


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _rows(conn, sql: str, args: tuple = ()) -> list[dict]:
    cursor = conn.execute(sql, args)
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, row)) for row in cursor]


def _updated_at(conn, name: str, fallback: str) -> str:
    """When the dataset last changed: the latest thing written about it (an import, or an older version made current again)."""
    row = conn.execute('SELECT MAX(time) FROM log WHERE element_id = ? AND change <> ?', (f'dataset:{name}', NO_CHANGE)).fetchone()
    return max(row[0] or '', fallback)


def list_datasets(conn) -> list[dict]:
    """Every dataset with its current version: name, origin, rows, column count, version, updated time, who, and how many things use it."""
    rows = _rows(conn, 'SELECT d.*, (SELECT COUNT(*) FROM "column" c WHERE c.dataset_id = d.id) AS column_count, '
                       '(SELECT COUNT(*) FROM dataset v WHERE v.name = d.name) AS version_count '
                       'FROM dataset d JOIN current_dataset c ON c.dataset_id = d.id ORDER BY d.name')
    return [{'name': r['name'], 'origin': r['origin'], 'rows': r['rows_stored'], 'columns': r['column_count'], 'version': r['version'],
             'versions': r['version_count'], 'updated_at': _updated_at(conn, r['name'], r['imported_at']), 'who': r['who'],
             'used_by': 0} for r in rows]   # used_by: nothing reads a dataset yet; object types and pipelines will


def _version_row(row: dict, current_id: int) -> dict:
    changes = json.loads(row['changes_json']) if row['changes_json'] else {}
    return {'version': row['version'], 'who': row['who'], 'at': row['imported_at'], 'mode': row['mode'] or 'upload', 'rows': row['rows_stored'],
            'changed': changes.get('changed'), 'added': changes.get('added'), 'unchanged': changes.get('unchanged'),
            'blank_kept': changes.get('blank_kept'), 'replaced_rows': changes.get('replaced_rows'), 'file_rows': changes.get('file_rows'), 'key_columns': changes.get('key_columns'),
            'current': row['id'] == current_id}


def _key_columns(element_id: str, name: str, known: set[str]) -> list[str]:
    """The columns a key check names, read out of its element id (key:<dataset>(<column>,<column>)) by the dataset's own name and
    columns, so a name or a column with a bracket or a comma in it still comes out whole."""
    parts = element_id[len(f'key:{name}('):-1].split(',')
    out, i = [], 0
    while i < len(parts):
        j = next((j for j in range(len(parts), i, -1) if ','.join(parts[i:j]) in known), i + 1)
        out.append(','.join(parts[i:j]))
        i = j
    return out


def _key_checks(conn, dataset_id: int, name: str) -> list[dict]:
    """The latest recorded key check of each column set on this version."""
    known = {r[0] for r in conn.execute('SELECT name FROM "column" WHERE dataset_id = ?', (dataset_id,))}
    rows = _rows(conn, 'SELECT * FROM check_result WHERE dataset_id = ? AND check_type IN (\'key_unique\', \'key_distinct\') '
                       'AND id IN (SELECT MAX(id) FROM check_result WHERE dataset_id = ? GROUP BY element_id) ORDER BY id', (dataset_id, dataset_id))
    return [{'id': r['id'], 'columns': _key_columns(r['element_id'], name, known), 'type': r['check_type'], 'status': r['status'],
             'rows_checked': r['rows_checked'], 'violations': r['violations'], 'null_key_rows': r['null_key_rows'],
             'samples': json.loads(r['samples_json'] or '[]'), 'at': r['checked_at']} for r in rows]


def dataset_detail(conn, name: str, version: int | None = None) -> dict | None:
    """One dataset as its page shows it, for the current version or the one asked for; None when there is no such dataset or version.
    columns: name, inferred type, fill rate, and whether the stored counts show it unique and filled on every row (a possible key);
    key_checks: the checks recorded on this version; versions: every version with who, when, mode and the counts."""
    current = current_dataset(conn, name)
    if current is None:
        return None
    shown = current if version is None else (_rows(conn, 'SELECT * FROM dataset WHERE name = ? AND version = ?', (name, version)) or [None])[0]
    if shown is None:
        return None
    total = shown['rows_stored']
    checks = _key_checks(conn, shown['id'], name)
    single = {c['columns'][0]: c for c in checks if len(c['columns']) == 1}
    columns = [{'name': c['name'], 'type': c['inferred_type'], 'distinct': c['distinct_count'], 'missing': c['missing_count'],
                'fill_rate': (total - c['missing_count']) / total if total else None,
                'possible_key': bool(total) and c['missing_count'] == 0 and c['distinct_count'] == total,
                'key_check': single.get(c['name'])}
               for c in _rows(conn, 'SELECT * FROM "column" WHERE dataset_id = ? ORDER BY position', (shown['id'],))]
    cols = ', '.join(_quote(c['name']) for c in columns)
    cursor = conn.execute(f'SELECT {cols} FROM {_quote(shown["table_name"])} ORDER BY rowid LIMIT {PREVIEW_ROWS}')
    versions = _rows(conn, 'SELECT * FROM dataset WHERE name = ? ORDER BY version DESC', (name,))
    skipped = _rows(conn, 'SELECT time, who, after_json FROM log WHERE element_id = ? AND change = ? ORDER BY time DESC', (f'dataset:{name}', NO_CHANGE))
    return {'name': name, 'origin': shown['origin'], 'version': shown['version'], 'current_version': current['version'],
            'rows': total, 'updated_at': _updated_at(conn, name, current['imported_at']), 'who': shown['who'], 'used_by': 0,
            'dropped': json.loads(shown['dropped_json'] or '{}'), 'columns': columns, 'key_checks': checks,
            'versions': [_version_row(v, current['id']) for v in versions],
            'no_change_updates': [{'at': r['time'], 'who': r['who'], **json.loads(r['after_json'])} for r in skipped],
            'preview': {'columns': [c['name'] for c in columns], 'rows': [list(r) for r in cursor], 'limit': PREVIEW_ROWS, 'total': total}}


def _decode(part: dict) -> tuple[str, bytes]:
    filename = str(part.get('filename') or '')
    if not isinstance(part.get('content_base64'), str):
        raise SourceFileError(f'{PurePath(filename).name or "文件"}：请求缺少 content_base64（文件内容）')
    try:
        data = base64.b64decode(part['content_base64'], validate=True)
    except (binascii.Error, ValueError):
        raise SourceFileError(f'{PurePath(filename).name}：文件内容不是有效的 base64') from None
    if PurePath(filename).suffix.lower() not in TABLE_SUFFIXES:
        raise SourceFileError(f'{PurePath(filename).name or "文件"}：数据集只支持 {" / ".join(TABLE_SUFFIXES)} 文件')
    return filename, data


def _name(value) -> str:
    text = str(value or '').strip()
    if not text or len(text) > MAX_NAME:
        raise ValueError(f'数据集名字要写 1 到 {MAX_NAME} 个字')
    return text


def _jobs(conn, parts: list) -> list[dict]:
    """Each uploaded file as the writes it asks for, checked as a whole before anything is written: [{'file', 'plan'}].
    A part is {'filename', 'content_base64'} and, to update a dataset that exists, 'target' (its name), 'mode' and for update_by_key
    'key_columns'; 'name' picks the name of a new dataset (the file's name otherwise). A name that is taken is never decided by
    guessing: without a target and a mode the request is refused, naming the dataset."""
    jobs, taken = [], {}
    for part in parts:
        if not isinstance(part, dict):
            raise ValueError('每个文件要写成 {"filename": …, "content_base64": …}')
        filename, data = _decode(part)
        label = PurePath(filename).name
        mode, target = part.get('mode') or None, part.get('target') or None
        if mode and mode not in UPLOAD_MODES:
            raise ValueError(f'{label}：导入方式只有按主键更新（update_by_key）和覆盖（overwrite）两种')
        for field in ('target', 'name', 'mode'):
            if part.get(field) is not None and not isinstance(part[field], str):
                raise ValueError(f'{label}：{field} 要写成文字')
        keys = part.get('key_columns')
        if keys is not None and not (isinstance(keys, list) and keys and all(isinstance(c, str) and c for c in keys)):
            raise ValueError(f'{label}：主键列（key_columns）要写成列名的列表，例如 ["订单号"]')
        if bool(mode) != bool(target):
            raise ValueError(f'{label}：要更新已有的数据集，数据集（target）和方式（mode）要一起写；不要靠文件名猜')
        if mode == 'update_by_key' and not part.get('key_columns'):
            raise ValueError(f'{label}：按主键更新要先选出主键列（key_columns）')
        try:
            sources = load_table_file(filename, data)['sources']
        except SourceFileError as exc:
            raise ValueError(f'{label}：{exc}') from None
        if not sources:
            raise ValueError(f'{label}：文件里没有数据行：第一行应是表头，下面是数据')
        if len(sources) > 1 and (target or part.get('name')):
            raise ValueError(f'{label}：文件里有 {len(sources)} 个工作表（{"、".join(sources)}），更新或改名只能用于只有一个工作表的文件')
        for sheet, source in sources.items():
            name = _name(target or (part.get('name') if len(sources) == 1 and part.get('name') else None)
                         or (PurePath(filename).stem if len(sources) == 1 else sheet))
            if name in taken:
                raise ValueError(f'{label}：和“{taken[name]}”都要写入数据集“{name}”，一次上传里一个数据集只能写一次')
            taken[name] = label
            try:
                plan = plan_upload(conn, name, source['records'], mode=mode, key_columns=part.get('key_columns'),
                                   rows_in=source.get('rows_read'), dropped=source.get('dropped_rows'))
            except ValueError as exc:
                raise ValueError(f'{label}：{exc}') from None
            jobs.append({'file': label, 'plan': plan})
    return jobs


def _outcome(job: dict, done: dict) -> dict:
    dataset = done['dataset']
    return {'file': job['file'], 'name': job['plan']['name'], 'mode': done['mode'], 'version': dataset['version'], 'rows': dataset['rows_stored'],
            'created_version': done['created'], 'reused': done['reused'], 'changes': done['changes'],
            'key_check': done.get('key_check') and {k: done['key_check'][k] for k in ('status', 'columns', 'rows_checked', 'violations', 'null_key_rows', 'samples')}}


def upload(conn, parts: list, who: str | None) -> list[dict]:
    """Save the uploaded table files: a new dataset for each name not taken, a new version for each explicit update. Everything is
    checked first (ValueError in plain Chinese, nothing written); then each is written as one version."""
    if not parts:
        raise ValueError('没有选择文件')
    jobs = _jobs(conn, parts)
    signer = str(who or '').strip() or '未署名'
    return [_outcome(job, apply_upload(conn, job['plan'], signer)) for job in jobs]
