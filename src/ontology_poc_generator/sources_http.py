"""The requests of the sources and schedules pages, as (status, body) for the service to send. Who may make each request is in access.py (the route table);
the connection details leave only to an admin (workspace_sources.public_source) and no request ever returns a password."""
from __future__ import annotations

import re

from ontology_poc_generator.source_connect import SourceError
from ontology_poc_generator.workspace_schedules import (
    create_schedule, delete_schedule, list_schedules, schedule_runs, update_schedule)
from ontology_poc_generator.workspace_sources import (
    create_source, delete_source, list_sources, pull_table, refresh_dataset, refresh_runs, source_detail, source_tables, test_source, update_source)

Reply = tuple[int, dict]
NOT_FOUND = (404, {'error': 'Unknown workspace endpoint'})


def sources_get(conn, parts: list[str], user: dict | None) -> Reply:
    """/api/workspace/sources (the list), /sources/<name> (one, with its pulls and schedules), /sources/<name>/tables (the tables in the database now, over a live connection)."""
    if not parts:
        return 200, {'sources': list_sources(conn, user)}
    detail = source_detail(conn, parts[0], user)
    if detail is None:
        return 404, {'error': '没有这个数据源'}
    if len(parts) == 1:
        return 200, detail
    if parts[1:] == ['tables']:
        try:
            return 200, {'tables': source_tables(conn, parts[0])}
        except SourceError as exc:
            return 502, {'error': str(exc)}
    if parts[1:] == ['runs']:
        return 200, {'runs': refresh_runs(conn, 'source', parts[0])}
    return NOT_FOUND


def sources_post(conn, route: str, payload: dict, who: str | None, user: dict | None, lock) -> Reply:
    """POST /api/workspace/sources (create), /update, /delete, /test, /pull (read a table as a dataset), /refresh (read a dataset's table again)."""
    try:
        if route == '':
            return 200, create_source(conn, payload, who)
        if route == '/update':
            return 200, update_source(conn, payload, who)
        if route == '/delete':
            return 200, delete_source(conn, payload.get('name'), who)
        if route == '/test':
            return 200, test_source(conn, payload.get('name'), who)
        if route == '/pull':
            return 200, {'run': pull_table(conn, payload, who, user, lock)}
        if route == '/refresh':
            return 200, {'run': refresh_dataset(conn, payload, who, user, lock)}
    except KeyError:
        return 404, {'error': '没有这个数据源'}
    except ValueError as exc:   # SourceError is one: its text holds no password
        return (409 if route == '/delete' else 400), {'error': str(exc)}
    return NOT_FOUND


def schedules_get(conn, parts: list[str]) -> Reply:
    """/api/workspace/schedules (the list), /schedules/<id>/runs (the runs one logged)."""
    if not parts:
        return 200, {'schedules': list_schedules(conn)}
    if len(parts) == 2 and parts[1] == 'runs' and re.fullmatch(r'[0-9]+', parts[0]):
        return 200, {'runs': schedule_runs(conn, int(parts[0]))}
    return NOT_FOUND


def schedules_post(conn, route: str, payload: dict, who: str | None) -> Reply:
    """POST /api/workspace/schedules (create), /update (change it, or switch it on or off), /delete."""
    try:
        if route == '':
            return 200, create_schedule(conn, payload, who)
        if route == '/update':
            return 200, update_schedule(conn, payload, who)
        if route == '/delete':
            return 200, delete_schedule(conn, payload, who)
    except KeyError:
        return 404, {'error': '没有这个调度'}
    except ValueError as exc:
        return 400, {'error': str(exc)}
    return NOT_FOUND
