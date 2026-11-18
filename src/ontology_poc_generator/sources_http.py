"""The requests of the sources and schedules pages, as (status, body) for the service to send. Who may make each request is in access.py (the route table);
the connection details leave only to an admin (workspace_sources.public_source), what a person reads of the datasets and pipelines kept from them is filtered
(workspace_sources.visible_run, the lists), and no request ever returns a password."""
from __future__ import annotations

from ontology_poc_generator.lang import tr
import re

from ontology_poc_generator.source_connect import SourceError
from ontology_poc_generator.workspace_schedules import (
    Forbidden, create_schedule, delete_schedule, list_schedules, schedule_runs, update_schedule)
from ontology_poc_generator.workspace_sources import (
    NotFound, create_source, delete_source, is_admin, list_sources, pull_table, refresh_dataset, refresh_runs, source_detail, source_tables, test_source,
    update_source, visible_run)

Reply = tuple[int, dict]
NOT_FOUND = (404, {'error': 'Unknown workspace endpoint'})


def sources_get(conn, parts: list[str], user: dict | None) -> Reply:
    """/api/workspace/sources (the list), /sources/<name> (one, with its pulls and schedules), /sources/<name>/tables (the tables in the database now, over a live connection)."""
    if not parts:
        return 200, {'sources': list_sources(conn, user)}
    detail = source_detail(conn, parts[0], user)
    if detail is None:
        return 404, {'error': tr('没有这个数据源', 'There is no such source')}
    if len(parts) == 1:
        return 200, detail
    if parts[1:] == ['tables']:
        try:
            return 200, {'tables': source_tables(conn, parts[0], user)}
        except SourceError as exc:
            return 502, {'error': str(exc) if is_admin(user) else exc.public}
    if parts[1:] == ['runs']:
        return 200, {'runs': refresh_runs(conn, 'source', parts[0], user=user)}
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
            return 200, {'run': visible_run(conn, pull_table(conn, payload, who, user, lock), user)}
        if route == '/refresh':
            return 200, {'run': visible_run(conn, refresh_dataset(conn, payload, who, user, lock), user)}
    except KeyError:
        return 404, {'error': tr('没有这个数据源', 'There is no such source')}
    except SourceError as exc:   # the database's own words (no password in them) are an admin's; everyone else reads the general reason
        return 400, {'error': str(exc) if is_admin(user) else exc.public}
    except ValueError as exc:
        return (409 if route == '/delete' else 400), {'error': str(exc)}
    return NOT_FOUND


def schedules_get(conn, parts: list[str], user: dict | None) -> Reply:
    """/api/workspace/schedules (the list), /schedules/<id>/runs (the runs one logged)."""
    if not parts:
        return 200, {'schedules': list_schedules(conn, user)}
    if len(parts) == 2 and parts[1] == 'runs' and re.fullmatch(r'[0-9]+', parts[0]):
        try:
            return 200, {'runs': schedule_runs(conn, int(parts[0]), user)}
        except KeyError:
            return 404, {'error': tr('没有这个调度', 'There is no such schedule')}
    return NOT_FOUND


def schedules_post(conn, route: str, payload: dict, who: str | None, user: dict | None) -> Reply:
    """POST /api/workspace/schedules (create), /update (change it, or switch it on or off), /delete. Another person's schedule is theirs or an admin's to change (403)."""
    try:
        if route == '':
            return 200, create_schedule(conn, payload, who, user)
        if route == '/update':
            return 200, update_schedule(conn, payload, who, user)
        if route == '/delete':
            return 200, delete_schedule(conn, payload, who, user)
    except KeyError:
        return 404, {'error': tr('没有这个调度', 'There is no such schedule')}
    except Forbidden as exc:
        return 403, {'error': str(exc)}
    except NotFound as exc:   # a pipeline that is not there and one kept from this person read the same
        return 404, {'error': str(exc)}
    except ValueError as exc:
        return 400, {'error': str(exc)}
    return NOT_FOUND
