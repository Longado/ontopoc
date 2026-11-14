"""The workspace's task list: what the service has been asked to do, newest first. A task is a modelling job the service
recorded (jobs/<id>.json) or an upload of a dataset (a version made through the workspace API, or an update that matched every
row and wrote none). Nothing here starts or changes a task.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from ontology_poc_generator.type_access import dataset_hidden, visible_type_ids
from ontology_poc_generator.workspace_store import DELETED, NO_CHANGE

LIMIT = 200


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec='seconds')


def job_tasks(jobs_dir: Path, running: set[str]) -> tuple[list[dict], int]:
    """(the modelling jobs on disk, how many files could not be read). A job the file says is running but this process is not running was cut
    off by a restart: 'interrupted'. A file cut short by a crash, or of another shape than the service writes, is counted, not shown."""
    tasks, unreadable = [], 0
    for path in jobs_dir.glob('*.json') if jobs_dir.is_dir() else []:
        try:
            job = json.loads(path.read_text(encoding='utf-8'))
            events = job.get('events') or []
            state = 'interrupted' if job['state'] == 'running' and path.stem not in running else job['state']
            read = next((e['detail'] for e in events if e['stage'] == 'read'), {})
            tasks.append({'kind': 'draft', 'id': path.stem, 'title': read.get('file') or path.stem, 'state': str(state),
                          'at': events[0]['at'] if events else _iso(path.stat().st_mtime),
                          'ended_at': events[-1]['at'] if events and state != 'running' else None,
                          'error': job.get('error') if state == 'failed' else None})
        except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, RecursionError):   # RecursionError: a file nested too deeply to parse
            unreadable += 1
    return tasks, unreadable


def upload_tasks(conn, user: dict | None = None) -> list[dict]:
    """The versions made through the workspace API, the uploads that changed nothing, and the datasets removed."""
    tasks = []
    for name, version, who, mode, at, rows, changes in conn.execute(
            'SELECT name, version, who, mode, imported_at, rows_stored, changes_json FROM dataset WHERE mode IS NOT NULL'):
        tasks.append({'kind': 'upload', 'id': f'{name}@{version}', 'title': name, 'state': 'done', 'at': at, 'who': who, 'mode': mode,
                      'version': version, 'rows': rows, 'changes': json.loads(changes) if changes else {}, 'created_version': True})
    for name, who, at, after in conn.execute('SELECT element_id, who, time, after_json FROM log WHERE change = ? AND element_id LIKE ?', (NO_CHANGE, 'dataset:%')):
        changes = json.loads(after)
        tasks.append({'kind': 'upload', 'id': f'{name}@{at}', 'title': name.removeprefix('dataset:'), 'state': 'done', 'at': at, 'who': who,
                      'mode': changes.get('mode', 'update_by_key'), 'version': None, 'rows': None, 'changes': changes, 'created_version': False})
    for name, who, at, before in conn.execute('SELECT element_id, who, time, before_json FROM log WHERE change = ?', (DELETED,)):
        tasks.append({'kind': 'upload', 'id': name, 'title': name.removeprefix('deleted:').rpartition('@')[0], 'state': 'done', 'at': at, 'who': who,
                      'mode': 'deleted', 'version': None, 'rows': None, 'changes': json.loads(before), 'created_version': False})
    tasks = [t for t in tasks if not dataset_hidden(conn, t['title'], user)]   # a dataset this person may not see is not in their task list either
    if user is not None and user['role'] == 'viewer':   # the keys of the rows an upload changed are rows
        for t in tasks:
            t['changes'] = {k: v for k, v in t['changes'].items() if k not in ('changed_keys', 'added_keys')}
    return tasks


def suggest_tasks(conn, user: dict | None = None) -> list[dict]:
    """The model's suggestions of object types: what was asked, the types it proposed, those the checks dropped and why (object_type_suggest).
    The types a person may not see (type_access) are not listed for them, nor is a task about a dataset they may not see. A viewer gets none: what the
    checks dropped says why, with the repeated values of the data in it."""
    if user is not None and user['role'] == 'viewer':
        return []
    seen = set(visible_type_ids(conn, user)) if user is not None and user['role'] != 'admin' else None
    tasks = []
    for element_id, who, at, after in conn.execute('SELECT element_id, who, time, after_json FROM log WHERE change = ?', ('suggest',)):
        task = json.loads(after)
        if any(dataset_hidden(conn, name, user) for name in task['datasets']):
            continue
        if seen is not None:
            task = {**task, 'proposed': [p for p in task['proposed'] if p['id'] in seen]}
        tasks.append({'kind': 'suggest', 'id': element_id, 'title': '、'.join(task['datasets']), 'state': 'failed' if task['error'] else 'done', 'at': at, 'who': who,
                      'error': task['error'], 'proposed': task['proposed'], 'rejected': task['rejected'], 'model': task['model']})
    return tasks


def list_tasks(conn, jobs_dir: Path, running: set[str], user: dict | None = None) -> tuple[list[dict], int]:
    """(jobs, uploads and suggestions together, newest first, at most LIMIT; the number of job files that could not be read)."""
    jobs, unreadable = job_tasks(jobs_dir, running)
    return sorted(jobs + upload_tasks(conn, user) + suggest_tasks(conn, user), key=lambda t: t['at'], reverse=True)[:LIMIT], unreadable
