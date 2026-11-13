"""What reads a dataset: the runs that stored it as one of their tables, the relations of those runs that start from it, and the confirmed
definitions (views, code meanings, repeat rules) that are about it. Deleting a dataset is refused while any of these exists.
"""
from __future__ import annotations

import json
from pathlib import Path


def _run_readers(run_paths: list[Path], name: str) -> list[dict]:
    readers = []
    for path in run_paths:
        try:
            run = json.loads(path.read_text(encoding='utf-8'))
            tables = (run.get('data_checks') or {}).get('tables') or []
            if not any(t.get('dataset') == name for t in tables):
                continue
            label = f'{(run.get("file") or {}).get("name") or path.name} {str(run.get("started_at") or "")[:16]}'.strip()
            readers.append({'kind': '运行', 'name': label})
            for r in (run.get('ontology') or {}).get('relations') or []:
                if r.get('source') == name:
                    readers.append({'kind': '关系', 'name': f'{r.get("label") or r.get("key")}（运行 {label}）'})
        except (OSError, ValueError, AttributeError, TypeError, RecursionError):
            continue   # a run file that cannot be read cannot be said to read anything
    return readers


def _definition_readers(conn, name: str) -> list[dict]:
    readers = []
    for element_id, content, state in conn.execute(
            "SELECT element_id, content_json, state FROM element_state WHERE state IN ('confirmed', 'checked') "
            "AND (element_id LIKE 'view:%' OR element_id LIKE 'property:%' OR element_id LIKE 'repeat_rule:%')"):
        kind, _, rest = element_id.partition(':')
        _, _, label = rest.partition(':')   # the file's key comes first; it holds no colon
        if kind == 'view':
            if json.loads(content or '{}').get('base') == name:
                readers.append({'kind': '视图', 'name': label})
        elif kind == 'property':
            if label.startswith(f'{name}.'):
                readers.append({'kind': '口径', 'name': label})
        elif label.endswith(f'.{name}'):
            readers.append({'kind': '重复键规则', 'name': label})
    return readers


def dataset_readers(conn, run_paths: list[Path], name: str) -> list[dict]:
    """[{'kind', 'name'}] of everything that reads the dataset called `name`; empty when nothing does."""
    return _run_readers(run_paths, name) + _definition_readers(conn, name)
