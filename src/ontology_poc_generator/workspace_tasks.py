"""The workspace's task list: what the service has been asked to do, newest first. A task is a modelling job the service
recorded (jobs/<id>.json) or an upload of a dataset (a version made through the workspace API, or an update that matched every
row and wrote none). Nothing here starts or changes a task.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from ontology_poc_generator.workspace_store import NO_CHANGE

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
        except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError):
            unreadable += 1
    return tasks, unreadable


def upload_tasks(conn) -> list[dict]:
    """The versions made through the workspace API, and the updates that changed nothing."""
    tasks = []
    for name, version, who, mode, at, rows, changes in conn.execute(
            'SELECT name, version, who, mode, imported_at, rows_stored, changes_json FROM dataset WHERE mode IS NOT NULL'):
        tasks.append({'kind': 'upload', 'id': f'{name}@{version}', 'title': name, 'state': 'done', 'at': at, 'who': who, 'mode': mode,
                      'version': version, 'rows': rows, 'changes': json.loads(changes) if changes else {}, 'created_version': True})
    for name, who, at, after in conn.execute('SELECT element_id, who, time, after_json FROM log WHERE change = ?', (NO_CHANGE,)):
        tasks.append({'kind': 'upload', 'id': f'{name}@{at}', 'title': name.removeprefix('dataset:'), 'state': 'done', 'at': at, 'who': who,
                      'mode': 'update_by_key', 'version': None, 'rows': None, 'changes': json.loads(after), 'created_version': False})
    return tasks


def list_tasks(conn, jobs_dir: Path, running: set[str]) -> tuple[list[dict], int]:
    """(jobs and uploads together, newest first, at most LIMIT; the number of job files that could not be read)."""
    jobs, unreadable = job_tasks(jobs_dir, running)
    return sorted(jobs + upload_tasks(conn), key=lambda t: t['at'], reverse=True)[:LIMIT], unreadable
