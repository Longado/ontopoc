"""The routes of the use layer, as plain functions of (connection, person, path, payload): the explorer, dashboards and what an outside agent reads. The service's
handler opens the connection, takes the write lock for the ones that write, and turns the refusals into answers. Who may call what is access.py's table."""
from __future__ import annotations

from ontology_poc_generator.lang import tr, unknown_endpoint
import re
from urllib.parse import unquote

from ontology_poc_generator import agent_access, dashboards, explorer
from ontology_poc_generator.object_types import TypeRefused

PREFIXES = ('/api/workspace/explore', '/api/workspace/dashboards', '/api/workspace/agent')
WRITES = ('/api/workspace/dashboards', '/api/workspace/dashboards/update', '/api/workspace/dashboards/delete')   # the POSTs that change what is stored
SKILL_FILE = ('application/zip', 'ontopoc-definitions.zip')


def owns(path: str) -> bool:
    route = path.split('?')[0]
    return any(route == p or route.startswith(p + '/') for p in PREFIXES)


def writes(path: str) -> bool:
    return path.split('?')[0] in WRITES


def _whole(text: str, what: str) -> int:
    if not re.fullmatch(r'[0-9]{1,9}', text):
        raise TypeRefused(tr(f'{what}要写成数字', f'{what} must be a number'), 404)
    return int(text)


def get(conn, user: dict | None, path: str, query: dict[str, list[str]]):
    """The answer of a GET: a dict, or (content type, file name, bytes) for a download."""
    parts = [unquote(p) for p in path.split('?')[0].split('/') if p][2:]   # after /api/workspace
    first = lambda name: (query.get(name) or [None])[0]
    if parts[0] == 'explore':
        if len(parts) == 2:
            return explorer.explore_meta(conn, user, parts[1])
        if len(parts) == 4 and parts[2] == 'object':
            return explorer.explore_object(conn, user, parts[1], _whole(parts[3], tr('对象的行号', 'The object row number')))
    elif parts[0] == 'dashboards':
        if len(parts) == 1:
            return {'dashboards': dashboards.list_dashboards(conn, user), 'people': dashboards.people(conn, user), 'sign_in_note': dashboards.sign_in_note()}
        if len(parts) == 2:
            return dashboards.dashboard_detail(conn, user, _whole(parts[1], tr('看板的编号', 'The board id')))
    elif parts[0] == 'agent':
        if len(parts) == 1:
            return agent_access.agent_info(conn, user)
        if parts[1] == 'definitions':
            return agent_access.definitions(conn, user)
        if parts[1] == 'unconfirmed':
            return agent_access.unconfirmed(conn, user)
        if parts[1] == 'standing' and len(parts) == 2:
            return agent_access.standing_sheet(conn, user) if first('format') == 'csv' else agent_access.standing(conn, user, first('id'))
        if parts[1] == 'derived':
            raise TypeRefused(tr('读派生属性要用 POST /api/workspace/agent/derived，type、name、key 写在请求体里', 'Read a derived property with POST /api/workspace/agent/derived, with type, name and key in the request body'), 405)
        if parts[1] == 'skill':
            return (*SKILL_FILE, agent_access.skill_zip(conn, user))
    raise TypeRefused(unknown_endpoint(), 404)


def post(conn, user: dict | None, path: str, payload: dict):
    route = path.split('?')[0]
    if route == '/api/workspace/explore/table':
        return explorer.explore_table(conn, user, payload.get('query'), payload.get('page') or 1)
    if route == '/api/workspace/explore/chart':
        return explorer.explore_chart(conn, user, payload.get('query'), payload.get('chart'))
    if route == '/api/workspace/dashboards':
        return dashboards.create_dashboard(conn, user, payload)
    if route == '/api/workspace/dashboards/update':
        return dashboards.update_dashboard(conn, user, payload)
    if route == '/api/workspace/dashboards/delete':
        return dashboards.delete_dashboard(conn, user, payload)
    if route == '/api/workspace/dashboards/data':
        return dashboards.dashboard_data(conn, user, payload.get('id'), payload.get('bar'), payload.get('params'))
    if route == '/api/workspace/dashboards/preview':
        return dashboards.preview(conn, user, payload)
    if route == '/api/workspace/agent/derived':
        return agent_access.read_derived(conn, user, payload.get('type'), payload.get('name'), payload.get('key'), payload.get('page') or 1)
    raise TypeRefused(unknown_endpoint(), 404)
