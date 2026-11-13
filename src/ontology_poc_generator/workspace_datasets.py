"""The workspace's datasets as pages read them: a list, one dataset with its columns, key checks, versions and a preview, and
the upload of table files that either makes a new dataset or updates an existing one on the person's explicit say.

Nothing here knows about runs: a dataset is a name with versions in the workspace file.
"""
from __future__ import annotations

import base64
import binascii
import csv
import io
import json
import re
from pathlib import PurePath

from ontology_poc_generator.actor import actor_id_for
from ontology_poc_generator.company_sources import TABLE_SUFFIXES, SourceFileError, load_table_file
from ontology_poc_generator.object_types import dataset_readers_of, recheck_dependents
from ontology_poc_generator.workspace_store import DELETED, NO_CHANGE, UPLOAD_MODES, apply_upload, current_dataset, now_text as _now_text, plan_upload

PREVIEW_ROWS = 50   # rows on one page of the preview
MAX_NAME = 100
NEAR_KEY_SHARE = 0.95   # a text or integer column with this share of its filled cells distinct reads as meant to be a key
NEAR_KEY_TYPES = ('text', 'integer')
_NUMBER = re.compile(r'[+-]?\d+(\.\d+)?', re.ASCII)


def _csv_cell(value):
    """A cell as the CSV file holds it. Excel runs a cell that starts with = + - @ (or a tab or CR) as a formula, and cells come from customers' files, so
    one is written with a ' in front; a plain number such as -5 or +3 is left alone."""
    if value is None:
        return ''
    if isinstance(value, str) and value[:1] in ('=', '+', '-', '@', '\t', '\r') and not _NUMBER.fullmatch(value):
        return "'" + value
    return value


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
             'used_by': len(dataset_readers_of(conn, r['name']))} for r in rows]   # used_by: the object types that read it; pipelines will too


def _version_row(row: dict, current_id: int) -> dict:
    changes = json.loads(row['changes_json']) if row['changes_json'] else {}
    return {'version': row['version'], 'who': row['who'], 'at': row['imported_at'], 'mode': row['mode'] or 'upload', 'origin': row['origin'], 'rows': row['rows_stored'],
            'changed': changes.get('changed'), 'added': changes.get('added'), 'unchanged': changes.get('unchanged'),
            'blank_kept': changes.get('blank_kept'), 'same_as': changes.get('same_as'), 'changed_keys': changes.get('changed_keys') or [], 'added_keys': changes.get('added_keys') or [], 'replaced_rows': changes.get('replaced_rows'), 'file_rows': changes.get('file_rows'), 'key_columns': changes.get('key_columns'),
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


def _near_key(conn, table: str, column: dict, total: int) -> dict | None:
    """For a column that reads as meant to be a key but is not one: the values that repeat (how many, the rows they cover, the worst three)
    and the rows left blank. None for a column that is not key-like, or is one."""
    filled = total - column['missing_count']
    if (column['inferred_type'] not in NEAR_KEY_TYPES or filled < 2 or column['distinct_count'] < NEAR_KEY_SHARE * filled
            or (column['missing_count'] == 0 and column['distinct_count'] == total)):
        return None
    col = _quote(column['name'])
    repeated = conn.execute(f'SELECT {col}, COUNT(*) FROM {table} WHERE {col} IS NOT NULL GROUP BY {col} HAVING COUNT(*) > 1 ORDER BY 2 DESC, 1').fetchall()
    return {'repeated_values': len(repeated), 'repeated_rows': sum(n for _, n in repeated), 'missing': column['missing_count'],
            'samples': [{'value': v, 'rows': n} for v, n in repeated[:3]]}


def dataset_detail(conn, name: str, version: int | None = None, page: int = 1) -> dict | None:
    """One dataset as its page shows it, for the current version or the one asked for; None when there is no such dataset or version.
    columns: name, inferred type, fill rate, whether the stored counts show it unique and filled on every row (a possible key), and for a
    column that is almost one, where it repeats or is blank (near_key); key_checks: the checks recorded on this version; versions: every
    version with who, when, mode and the counts; preview: one page (PREVIEW_ROWS rows) of the rows."""
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
                'key_check': single.get(c['name']), 'near_key': _near_key(conn, _quote(shown['table_name']), c, total),
                'values': json.loads(c['value_counts_json']) if c['value_counts_json'] else None}   # the values and their rows, for a column with few of them
               for c in _rows(conn, 'SELECT * FROM "column" WHERE dataset_id = ? ORDER BY position', (shown['id'],))]
    cols = ', '.join(_quote(c['name']) for c in columns)
    pages = max(1, -(-total // PREVIEW_ROWS))
    page = min(max(page, 1), pages)
    cursor = conn.execute(f'SELECT {cols} FROM {_quote(shown["table_name"])} ORDER BY rowid LIMIT {PREVIEW_ROWS} OFFSET {(page - 1) * PREVIEW_ROWS}')
    versions = _rows(conn, 'SELECT * FROM dataset WHERE name = ? ORDER BY version DESC', (name,))
    skipped = _rows(conn, 'SELECT time, who, after_json FROM log WHERE element_id = ? AND change = ? ORDER BY time DESC', (f'dataset:{name}', NO_CHANGE))
    return {'name': name, 'origin': shown['origin'], 'version': shown['version'], 'version_at': shown['imported_at'], 'current_version': current['version'],
            'rows': total, 'updated_at': _updated_at(conn, name, current['imported_at']), 'who': shown['who'], 'readers': dataset_readers_of(conn, name),
            'dropped': json.loads(shown['dropped_json'] or '{}'), 'columns': columns, 'key_checks': checks,
            'versions': [_version_row(v, current['id']) for v in versions],
            'no_change_updates': [{'at': r['time'], 'who': r['who'], 'mode': 'update_by_key', **json.loads(r['after_json'])} for r in skipped],
            'preview': {'columns': [c['name'] for c in columns], 'rows': [list(r) for r in cursor], 'limit': PREVIEW_ROWS, 'total': total,
                        'page': page, 'pages': pages}}


def dataset_csv(conn, name: str, version: int | None = None) -> tuple[str, bytes] | None:
    """(file name, bytes) of one version as a CSV Excel opens correctly (UTF-8 with a byte-order mark); None when there is no such version."""
    current = current_dataset(conn, name)
    shown = None if current is None else current if version is None else (_rows(conn, 'SELECT * FROM dataset WHERE name = ? AND version = ?', (name, version)) or [None])[0]
    if shown is None:
        return None
    cursor = conn.execute(f'SELECT * FROM {_quote(shown["table_name"])} ORDER BY rowid')
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(_csv_cell(c[0]) for c in cursor.description)
    writer.writerows(map(_csv_cell, row) for row in cursor)
    return f'{name}-第{shown["version"]}版.csv', out.getvalue().encode('utf-8-sig')


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


class UploadRefused(ValueError):
    """An upload nothing of which was written. str() is the whole message; `files` has the problem of each file that has one, by its position
    in the request, without the file's name (the page shows it on that file's row)."""

    def __init__(self, message: str, files: dict[int, str]):
        super().__init__(message)
        self.files = files


def _part_jobs(conn, part, taken: dict) -> list[dict]:
    """One uploaded file as the writes it asks for: [{'file', 'plan'}], one per sheet. A part is {'filename', 'content_base64'} and, to update
    a dataset that exists, 'target' (its name), 'mode' and for update_by_key 'key_columns'; 'name' picks the name of a new dataset (the file's
    name otherwise). A name that is taken is never decided by guessing: without a target and a mode it is refused, naming the dataset.
    Every message starts with the file's name."""
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
    if keys is not None and len(set(keys)) != len(keys):
        raise ValueError(f'{label}：主键列里有重复的列：{"、".join(c for c in dict.fromkeys(keys) if keys.count(c) > 1)}')
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
    jobs = []
    for sheet, source in sources.items():
        name = _name(target or (part.get('name') if len(sources) == 1 and part.get('name') else None)
                     or (PurePath(filename).stem if len(sources) == 1 else sheet))
        if name in taken:
            raise ValueError(f'{label}：和“{taken[name]}”都要写入数据集“{name}”，一次上传里一个数据集只能写一次')
        try:
            plan = plan_upload(conn, name, source['records'], mode=mode, key_columns=part.get('key_columns'),
                               rows_in=source.get('rows_read'), dropped=source.get('dropped_rows'))
        except ValueError as exc:
            raise ValueError(f'{label}：{exc}') from None
        taken[name] = label   # only a write that will happen takes the name
        jobs.append({'file': label, 'plan': plan})
    return jobs


def _jobs(conn, parts: list) -> list[dict]:
    """Every uploaded file as the writes it asks for, all checked before anything is written. UploadRefused names what is wrong with each
    file that has a problem, not only the first."""
    jobs, taken, problems = [], {}, {}
    for i, part in enumerate(parts):
        try:
            jobs += _part_jobs(conn, part, taken)
        except ValueError as exc:
            label = PurePath(str(part.get('filename') or '')).name if isinstance(part, dict) else ''
            problems[i] = str(exc).removeprefix(f'{label}：')
    if problems:
        names = [PurePath(str(p.get('filename') or '')).name if isinstance(p, dict) else '' for p in parts]
        raise UploadRefused('；'.join(f'{names[i]}：{m}' if names[i] else m for i, m in problems.items()), problems)
    return jobs


def _outcome(job: dict, done: dict) -> dict:
    dataset = done['dataset']
    return {'file': job['file'], 'name': job['plan']['name'], 'mode': done['mode'], 'version': dataset['version'], 'rows': dataset['rows_stored'],
            'created_version': done['created'], 'reused': done['reused'], 'same_as': done['changes'].get('same_as'), 'changes': done['changes'],
            'key_check': done.get('key_check') and {k: done['key_check'][k] for k in ('status', 'columns', 'rows_checked', 'violations', 'null_key_rows', 'samples')}}


def upload(conn, parts: list, who: str | None) -> list[dict]:
    """Save the uploaded table files: a new dataset for each name not taken, a new version for each explicit update. Everything is
    checked first (ValueError in plain Chinese, nothing written); then each is written as one version."""
    if not parts:
        raise ValueError('没有选择文件')
    jobs = _jobs(conn, parts)
    signer = str(who or '').strip() or '未署名'
    outcomes = []
    for job in jobs:
        done = apply_upload(conn, job['plan'], signer)
        if done['created']:
            recheck_dependents(conn, job['plan']['name'], signer)   # what was confirmed on the version before is checked against this one
        outcomes.append(_outcome(job, done))
    return outcomes


def delete_dataset(conn, name: str, who: str | None, readers: list[dict]) -> dict:
    """Remove a dataset with all of its versions and their rows. Refused (ValueError naming each reader) while anything reads it: `readers`
    is what dataset_readers found. The log keeps what was removed, under a name of its own, so a dataset made later under the same name
    starts with a clean history; its key checks are deleted, and its id is never given out again. Returns {'name', 'versions', 'rows'}."""
    versions = _rows(conn, 'SELECT * FROM dataset WHERE name = ?', (name,))
    if not versions:
        raise KeyError(name)
    if readers:
        raise ValueError(f'有 {len(readers)} 处在读“{name}”，先处理它们：' + '、'.join(f'{r["kind"]}「{r["name"]}」' for r in readers))
    signer = str(who or '').strip() or '未署名'
    stamp = _now_text()
    conn.execute('BEGIN IMMEDIATE')
    try:
        for v in versions:
            conn.execute(f'DROP TABLE IF EXISTS {_quote(v["table_name"])}')
            conn.execute('DELETE FROM "column" WHERE dataset_id = ?', (v['id'],))
            conn.execute('DELETE FROM dataset WHERE id = ?', (v['id'],))
            conn.execute('DELETE FROM check_result WHERE dataset_id = ?', (v['id'],))   # the key checks recorded on it go with it
        conn.execute('DELETE FROM current_dataset WHERE name = ?', (name,))
        conn.execute('UPDATE log SET element_id = ? WHERE element_id = ?', (f'deleted:{name}@{stamp}', f'dataset:{name}'))
        conn.execute('INSERT INTO log(time, who, element_id, change, before_json, after_json, user_id) VALUES (?, ?, ?, ?, ?, NULL, ?)',
                     (stamp, signer, f'deleted:{name}@{stamp}', DELETED,
                      json.dumps({'versions': len(versions), 'rows': max(v['rows_stored'] for v in versions)}, ensure_ascii=False), actor_id_for(signer)))
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return {'name': name, 'versions': len(versions), 'rows': max(v['rows_stored'] for v in versions)}
