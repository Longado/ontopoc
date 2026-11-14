"""Dashboards: a board of metric cards, charts and tables over object types, with one filter bar, published to named people or to everyone who is signed in.

A board holds no numbers. Each component is a query (explorer.normalize_query) and a chart (explorer.normalize_chart) and is worked out each time somebody opens the
board, by the person who opens it: over the types, views and rows *they* may read (explorer reads through can_access, row rules and viewer visibility). Publishing a
board to someone gives them the board, never data their role does not give them; a component whose type they may not see says so instead of a number.

Each component carries its caliber: the confirmed definitions it stands on, generated from them (caliber.py): 剔除 状态码 = 2（已取消），Bob 确认于 订单 v1. When any of
them stops being confirmed the line turns grey with the reason it carries and so does the component. A board is not an element with a confirmation of its own: its
trust is the trust of the definitions it shows.

A share link is the board's address in the app. It opens only for someone who is signed in and may see the board: there is no anonymous access.
Visibility: the owner and admins always; `everyone` is every signed-in person; `named` the people listed; `private` (the default, a draft) the owner. After
`expires_at` only the owner and admins can still open it, and it says it expired.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import re

from ontology_poc_generator.explorer import explore_chart, explore_meta, explore_table, normalize_chart, normalize_query
from ontology_poc_generator.object_types import TypeRefused, _content, _type_row

SCHEMA = '''
CREATE TABLE IF NOT EXISTS dashboard (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, owner_id INTEGER NOT NULL, owner TEXT NOT NULL, spec_json TEXT NOT NULL, scope TEXT NOT NULL,
    visible_to_json TEXT NOT NULL, expires_at TEXT, refresh_seconds INTEGER NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
'''
SCOPES = {'private': '只有我', 'named': '指定的人', 'everyone': '所有登录的人'}
REFRESH = (0, 60, 300, 900, 3600)   # seconds between two reads of the data; 0 is "only when the page is opened or the person asks"
MAX_COMPONENTS, MAX_BAR, MAX_NAME, MAX_TITLE = 12, 4, 40, 40
ROW_LIMIT = 10   # an instance table on a board shows this many rows
SIGN_IN_NOTE = '分享链接打开时仍然要先登录，并且要在看板的发布范围里；没有匿名访问。'


class DashboardRefused(ValueError):
    """A refusal in plain Chinese; status is the HTTP status."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure_schema(conn) -> None:
    conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _is_admin(user: dict | None) -> bool:
    return user is None or user['role'] == 'admin'   # no sign-in (a local service) acts as the admin


def _owns(user: dict | None, record: dict) -> bool:
    return user is None or user['id'] == record['owner_id']


def _record(row) -> dict:
    i, name, owner_id, owner, spec, scope, visible, expires, refresh, version, created, updated = row
    return {'id': i, 'name': name, 'owner_id': owner_id, 'owner': owner, 'spec': json.loads(spec), 'scope': scope, 'visible_to': json.loads(visible), 'expires_at': expires,
            'refresh_seconds': refresh, 'version': version, 'created_at': created, 'updated_at': updated}


COLUMNS = 'id, name, owner_id, owner, spec_json, scope, visible_to_json, expires_at, refresh_seconds, version, created_at, updated_at'


def _expired(record: dict) -> bool:
    return bool(record['expires_at']) and record['expires_at'] < date.today().isoformat()


def _published_to(user: dict | None, record: dict) -> bool:
    return record['scope'] == 'everyone' or (record['scope'] == 'named' and user['id'] in record['visible_to'])


def _may_open(user: dict | None, record: dict) -> bool:
    if _is_admin(user) or _owns(user, record):
        return True
    return not _expired(record) and _published_to(user, record)


def _found(conn, user: dict | None, dashboard_id) -> dict:
    row = conn.execute(f'SELECT {COLUMNS} FROM dashboard WHERE id = ?', (dashboard_id,)).fetchone() if isinstance(dashboard_id, int) and not isinstance(dashboard_id, bool) else None
    record = _record(row) if row else None
    if record is None or not _may_open(user, record):
        if record is not None and _expired(record) and _published_to(user, record):   # only someone it was published to is told that it has ended: to anyone else it is not there
            raise DashboardRefused('这个看板已经过期，不再开放了', 410)
        raise DashboardRefused('没有这个看板', 404)
    return record


def _summary(record: dict, user: dict | None) -> dict:
    return {'id': record['id'], 'name': record['name'], 'owner': record['owner'], 'scope': record['scope'], 'expires_at': record['expires_at'], 'expired': _expired(record),
            'refresh_seconds': record['refresh_seconds'], 'updated_at': record['updated_at'], 'components': len(record['spec']['components']),
            'mine': _owns(user, record), 'may_change': _owns(user, record) or _is_admin(user)}


def list_dashboards(conn, user: dict | None) -> list[dict]:
    ensure_schema(conn)
    records = [_record(r) for r in conn.execute(f'SELECT {COLUMNS} FROM dashboard ORDER BY id DESC')]
    return [_summary(r, user) for r in records if _may_open(user, r)]


def people(conn, user: dict | None) -> list[dict]:
    """The accounts a board can be published to by name: for those who may publish (builders and admins), not for a viewer."""
    if user is not None and user['role'] == 'viewer':
        return []
    return [{'id': i, 'name': name} for i, name in conn.execute('SELECT id, display_name FROM user WHERE disabled = 0 ORDER BY display_name')]


def dashboard_detail(conn, user: dict | None, dashboard_id: int) -> dict:
    ensure_schema(conn)
    record = _found(conn, user, dashboard_id)
    if not (_owns(user, record) or _is_admin(user)):   # a reader gets the board worked out (dashboard_data), not what it is made of or who else it went to
        return {**{k: record[k] for k in ('id', 'name', 'owner', 'scope', 'expires_at', 'refresh_seconds', 'version', 'updated_at')}, **_summary(record, user),
                'owner_id': None, 'sign_in_note': SIGN_IN_NOTE}
    names = {i: n for i, n in conn.execute('SELECT id, display_name FROM user')}
    return {**record, **_summary(record, user), 'visible_names': [names.get(i, '（已删除）') for i in record['visible_to']], 'sign_in_note': SIGN_IN_NOTE, 'owner_id': record['owner_id']}


# --- what a board is made of ---------------------------------------------------------------------------------------------------------------------------

def _clean_name(value, what: str, limit: int) -> str:
    text = value.strip() if isinstance(value, str) else ''
    if not text or len(text) > limit or '\n' in text:
        raise DashboardRefused(f'{what}要写一行字，最多 {limit} 个字符')
    return text


def normalize_spec(raw) -> dict:
    """{'components': [{'id', 'title', 'query', 'chart'}], 'filters': [{'field', 'label'}]} from what a page sent. A component's chart kind is one of the explorer's, or
    'rows' for a list of the first rows."""
    if not isinstance(raw, dict) or not isinstance(raw.get('components'), list) or not raw['components']:
        raise DashboardRefused('看板里至少要有一个组件')
    if len(raw['components']) > MAX_COMPONENTS:
        raise DashboardRefused(f'一个看板最多 {MAX_COMPONENTS} 个组件')
    components, seen = [], set()
    for i, c in enumerate(raw['components'], 1):
        if not isinstance(c, dict):
            raise DashboardRefused('组件要写成对象')
        title = _clean_name(c.get('title'), f'第 {i} 个组件的标题', MAX_TITLE)
        raw_chart = c.get('chart')
        rows = isinstance(raw_chart, dict) and raw_chart.get('kind') == 'rows'
        try:
            query = normalize_query(c.get('query'))
            chart = {'kind': 'rows'} if rows else normalize_chart(raw_chart)
        except TypeRefused as exc:
            raise DashboardRefused(f'“{title}”：{exc}') from None
        ident = c.get('id') if isinstance(c.get('id'), str) and re.fullmatch(r'[A-Za-z0-9_-]{1,20}', c['id']) else f'c{i}'
        if ident in seen:
            raise DashboardRefused(f'组件编号“{ident}”重复了')
        seen.add(ident)
        components.append({'id': ident, 'title': title, 'query': query, 'chart': chart})
    bar = raw.get('filters') or []
    if not isinstance(bar, list) or len(bar) > MAX_BAR or not all(isinstance(f, dict) for f in bar):
        raise DashboardRefused(f'筛选条最多 {MAX_BAR} 项')
    filters = [{'field': _clean_name(f.get('field'), '筛选项的字段', 60), 'label': _clean_name(f.get('label') or f.get('field'), '筛选项的名字', MAX_TITLE)} for f in bar]
    if len({f['field'] for f in filters}) != len(filters):
        raise DashboardRefused('筛选条里一个字段只能出现一次')
    return {'components': components, 'filters': filters}


def _publish(conn, payload: dict) -> dict:
    scope = payload.get('scope', 'private')
    if scope not in SCOPES:
        raise DashboardRefused(f'发布范围要是 {"、".join(SCOPES)} 之一')
    visible = payload.get('visible_to') or []
    if scope == 'named':
        active = {i for (i,) in conn.execute('SELECT id FROM user WHERE disabled = 0')}
        if not isinstance(visible, list) or not visible or not all(isinstance(i, int) and not isinstance(i, bool) and i in active for i in visible):
            raise DashboardRefused('指定的人要写成在用账号的编号列表，至少一个')
        visible = sorted(set(visible))
    else:
        visible = []
    expires = payload.get('expires_at') or None
    if expires is not None:
        if not isinstance(expires, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', expires):
            raise DashboardRefused('到期日要写成 年-月-日')
        try:
            date.fromisoformat(expires)
        except ValueError:
            raise DashboardRefused('到期日不是一个真实的日期') from None
        if expires < date.today().isoformat():
            raise DashboardRefused('到期日不能早于今天')
    refresh = payload.get('refresh_seconds', 0)
    if refresh not in REFRESH or isinstance(refresh, bool):
        raise DashboardRefused(f'刷新间隔要是 {"、".join(str(r) for r in REFRESH)} 秒之一（0 是只在打开时读）')
    return {'scope': scope, 'visible_to': visible, 'expires_at': expires, 'refresh_seconds': refresh}


def _checked(conn, user: dict | None, payload: dict) -> tuple[str, dict, dict]:
    name = _clean_name(payload.get('name'), '看板的名字', MAX_NAME)
    spec = normalize_spec(payload.get('spec'))
    problem = next((c for c in evaluate(conn, user, spec, {}) if c['status'] != 'ok'), None)   # a component that cannot be worked out is refused here, not found out by the readers
    if problem:
        raise DashboardRefused(f'“{problem["title"]}”：{problem["message"]}')
    return name, spec, _publish(conn, payload)


def create_dashboard(conn, user: dict | None, payload: dict) -> dict:
    ensure_schema(conn)
    name, spec, published = _checked(conn, user, payload)
    now = _now()
    cursor = conn.execute('INSERT INTO dashboard(name, owner_id, owner, spec_json, scope, visible_to_json, expires_at, refresh_seconds, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)',
                          (name, user['id'] if user else 0, user['display_name'] if user else '本机', json.dumps(spec, ensure_ascii=False), published['scope'],
                           json.dumps(published['visible_to']), published['expires_at'], published['refresh_seconds'], now, now))
    return dashboard_detail(conn, user, cursor.lastrowid)


def update_dashboard(conn, user: dict | None, payload: dict) -> dict:
    ensure_schema(conn)
    record = _found(conn, user, payload.get('id'))
    if not (_owns(user, record) or _is_admin(user)):
        raise DashboardRefused('只有看板的主人或管理员能改它', 403)
    if payload.get('version') != record['version']:
        raise DashboardRefused('这个看板在你打开之后被改过，请刷新后再改', 409)
    name, spec, published = _checked(conn, user, payload)
    conn.execute('UPDATE dashboard SET name = ?, spec_json = ?, scope = ?, visible_to_json = ?, expires_at = ?, refresh_seconds = ?, version = version + 1, updated_at = ? WHERE id = ?',
                 (name, json.dumps(spec, ensure_ascii=False), published['scope'], json.dumps(published['visible_to']), published['expires_at'], published['refresh_seconds'], _now(), record['id']))
    return dashboard_detail(conn, user, record['id'])


def delete_dashboard(conn, user: dict | None, payload: dict) -> dict:
    ensure_schema(conn)
    record = _found(conn, user, payload.get('id'))
    if not (_owns(user, record) or _is_admin(user)):
        raise DashboardRefused('只有看板的主人或管理员能删它', 403)
    conn.execute('DELETE FROM dashboard WHERE id = ?', (record['id'],))
    return {'deleted': record['id']}


# --- working a board out -------------------------------------------------------------------------------------------------------------------------------

def _with_bar(conn, user: dict | None, component: dict, bar: dict) -> dict:
    """The component's query with the filter bar's picks added for the fields its type has (a pick for a field it does not have leaves it alone)."""
    query = component['query']
    own = {p['column'] for p in _content(_type_row(conn, query['type'], user))['properties']}
    added = [{'field': f, 'op': 'eq', 'value': v} for f, v in bar.items() if f in own]
    return {**query, 'filters': [*query['filters'], *added]}


def _failed(component: dict, exc: Exception) -> dict:
    status = getattr(exc, 'status', None)
    message = '你现在看不到这个对象类型：它还没有确认，或者没有开放给你' if isinstance(exc, TypeRefused) and status == 404 and str(exc) == '没有这个对象类型' else str(exc)
    return {'id': component['id'], 'title': component['title'], 'chart': component['chart'], 'status': 'unavailable', 'message': message}


def _work_out(conn, user: dict | None, component: dict, bar: dict) -> dict:
    query = _with_bar(conn, user, component, bar)
    if component['chart']['kind'] == 'rows':
        table = explore_table(conn, user, query)
        result = {**table, 'rows': table['rows'][:ROW_LIMIT], 'numbers': table['numbers'][:ROW_LIMIT], 'shown': min(ROW_LIMIT, table['total'])}
    else:
        result = explore_chart(conn, user, query, component['chart'])
    return {'id': component['id'], 'title': component['title'], 'chart': component['chart'], 'status': 'ok', 'result': result}


def evaluate(conn, user: dict | None, spec: dict, bar: dict) -> list[dict]:
    """Every component worked out for this person: {'id', 'title', 'chart', 'status': 'ok', 'result'} or {..., 'status': 'unavailable', 'message'}. A component that
    cannot be read by this person (a type they may not see, a view or column that is gone) says why and the others still show."""
    out = []
    for component in spec['components']:
        try:
            out.append(_work_out(conn, user, component, bar))
        except TypeRefused as exc:
            out.append(_failed(component, exc))
    return out


def _bar_options(conn, user: dict | None, spec: dict, picked: dict) -> list[dict]:
    """The filter bar as the page draws it: each field with its name, the values to pick from (read from the first component whose type has the field, over the rows
    this person may read) and the pick."""
    out = []
    for f in spec['filters']:
        options, name = None, f['label']
        for component in spec['components']:
            try:
                fields = explore_meta(conn, user, component['query']['type'])['fields']
            except TypeRefused:
                continue
            found = next((x for x in fields if x['key'] == f['field'] and not x['derived']), None)
            if found:
                options = found['options']
                break
        out.append({**f, 'name': name, 'options': options, 'value': picked.get(f['field'], '')})
    return out


def _picked(spec: dict, bar) -> dict:
    """The filter bar's picks from a request: {field: value}, for the fields the board has and only non-empty ones."""
    if bar in (None, ''):
        return {}
    if not isinstance(bar, dict) or not all(isinstance(k, str) and isinstance(v, str) and len(v) <= 200 for k, v in bar.items()):
        raise DashboardRefused('筛选条的取值要写成 {字段: 取值}')
    fields = {f['field'] for f in spec['filters']}
    return {k: v for k, v in bar.items() if k in fields and v.strip()}


def _headline(components: list[dict]) -> dict:
    ok = [c for c in components if c['status'] == 'ok']
    grey = [c['title'] for c in ok if not c['result']['standing']['confirmed']]
    return {'components': len(components), 'unavailable': [c['title'] for c in components if c['status'] != 'ok'], 'grey': grey,
            'text': ('全部按已确认的定义算出' if not grey else f'{len(grey)} 个组件用到了现在不是“已确认”的定义，灰色显示：{"、".join(grey)}')}


def dashboard_data(conn, user: dict | None, dashboard_id, bar=None) -> dict:
    """The board worked out for this person with the filter bar's picks."""
    ensure_schema(conn)
    record = _found(conn, user, dashboard_id)
    picked = _picked(record['spec'], bar)
    components = evaluate(conn, user, record['spec'], picked)
    return {'id': record['id'], 'name': record['name'], 'bar': _bar_options(conn, user, record['spec'], picked), 'components': components, 'headline': _headline(components),
            'refresh_seconds': record['refresh_seconds'], 'expired': _expired(record), 'read_at': _now(), 'sign_in_note': SIGN_IN_NOTE}


def preview(conn, user: dict | None, payload: dict) -> dict:
    """A board that is not saved, worked out for its author: what the editor shows beside the form."""
    spec = normalize_spec(payload.get('spec'))
    picked = _picked(spec, payload.get('bar'))
    components = evaluate(conn, user, spec, picked)
    return {'bar': _bar_options(conn, user, spec, picked), 'components': components, 'headline': _headline(components)}
