"""Dashboards: a board of metric cards, charts and tables over object types, with one filter bar, published to named people or to everyone who is signed in.

A board holds no numbers. Each component is a query (explorer.normalize_query) and a chart (explorer.normalize_chart) and is worked out each time somebody opens the
board, by the person who opens it: over the types, views and rows *they* may read (explorer reads through can_access, row rules and viewer visibility). Publishing a
board to someone gives them the board, never data their role does not give them; a component whose type they may not see says so instead of a number.

Each component carries its caliber: the confirmed definitions it stands on, generated from them (caliber.py): 剔除 状态码 = 2（已取消），Bob 确认于 订单 v1. When any of
them stops being confirmed the line turns grey with the reason it carries and so does the component. A board is not an element with a confirmation of its own: its
trust is the trust of the definitions it shows.

The one thing a board stores is, for each reader and each component, the last result that was worked out while every definition under it was confirmed (dashboard_last): when
a viewer opens the board after the data under it moved, the type is not theirs to read until somebody confirms it again, and the component says it is waiting for
them and shows that number, labelled with when it was confirmed. It is the number that was shown, never one worked out again from the new data, and only the reader's
own (over the rows their rules let them read). A change to the board's spec drops what it stored.

A card can also be an OntoPoc Query (`text`, chart kind 'query'): a saved query, worked out the same way, by the person who opens the board, through the same engine as a
question (workspace_questions.run_text), with no model. The board's parameters ({name, label, default}) are asked once at the top of the board and passed to every
query card as values for its $names: a value is compared as a value, never read as query text. Each one has a default, so the board always shows a number, and every
$name a card uses must be one of them. Someone who opens the board but did not make it is not told what a query card that they cannot work out reads (a property
kept from them reads like one that does not exist, so the reason would name it): they are told the card is closed to them.

A share link is the board's address in the app. It opens only for someone who is signed in and may see the board: there is no anonymous access.
Visibility: the owner and admins always; `everyone` is every signed-in person; `named` the people listed; `private` (the default, a draft) the owner. After
`expires_at` only the owner and admins can still open it, and it says it expired.
"""
from __future__ import annotations

from ontology_poc_generator.lang import TrMap, tr
from datetime import date, datetime, timezone
import json
import re

from ontology_poc_generator.explorer import _standing, explore_chart, explore_meta, explore_table, normalize_chart, normalize_query
from ontology_poc_generator.object_types import VIEW_PREFIX, TypeRefused, _confirmers, _content, _type_row, element_row, type_id, was_confirmed, waiting_for_viewer
from ontology_poc_generator.object_views import view_id
from ontology_poc_generator.ontopoc_query import QueryError, is_graph, param_names
from ontology_poc_generator.type_access import can_access, hidden_columns

SCHEMA = '''
CREATE TABLE IF NOT EXISTS dashboard (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, owner_id INTEGER NOT NULL, owner TEXT NOT NULL, spec_json TEXT NOT NULL, scope TEXT NOT NULL,
    visible_to_json TEXT NOT NULL, expires_at TEXT, refresh_seconds INTEGER NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dashboard_last (
    dashboard_id INTEGER NOT NULL, component_id TEXT NOT NULL, reader INTEGER NOT NULL, picks TEXT NOT NULL, result_json TEXT NOT NULL, at TEXT NOT NULL,
    PRIMARY KEY (dashboard_id, component_id, reader, picks));
'''
SCOPES = TrMap({'private': ('只有我', 'Only me'), 'named': ('指定的人', 'Named people'), 'everyone': ('所有登录的人', 'Everyone who signs in')})
REFRESH = (0, 60, 300, 900, 3600)   # seconds between two reads of the data; 0 is "only when the page is opened or the person asks"
MAX_COMPONENTS, MAX_BAR, MAX_NAME, MAX_TITLE = 12, 4, 40, 40
MAX_PARAMS, MAX_VALUE, MAX_TEXT = 4, 200, 4000   # parameters on a board, characters in a parameter's value, characters in a query card
PARAM_NAME = re.compile(r'[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]{0,19}')   # as the query reads a $name
def closed_text() -> str:
    return tr('这个组件你现在算不了：它用到的对象类型、属性或关系你看不到，或者现在不在了', 'You cannot compute this component now: you cannot see an object type, property or relation it uses, or it is gone')
def unsettled_text() -> str:
    return tr('这个组件现在算不了：它用到的定义现在不是已确认的状态，要等有权限的人再确认', 'This component cannot be computed now: a definition it uses is not confirmed, and someone with the right must confirm it again')   # a reader is not told which: the reason can name a column kept from them
def bad_value_text() -> str:
    return tr('你填的参数值在这里用不了（例如要数字或日期的地方填了文字），请换一个值，或者清空用默认值', 'The parameter value you entered cannot be used here (for example text where a number or date is needed). Use another value, or clear it to use the default')
ROW_LIMIT = 10   # an instance table on a board shows this many rows
def sign_in_note() -> str:
    return tr('分享链接打开时仍然要先登录，并且要在看板的发布范围里；没有匿名访问。', 'A shared link still needs sign-in, and the person must be within the board\'s audience; there is no anonymous access.')


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


def _reads_nothing(conn, user: dict | None, record: dict) -> bool:
    """A reader (not the owner, not an admin) for whom no component's type opens: the board has nothing to show them, so it is neither listed nor there."""
    if _is_admin(user) or _owns(user, record):
        return False
    for component in record['spec']['components']:
        if 'text' in component:
            if _text_opens(conn, user, component, _defaults(record['spec'])):
                return False
            continue
        try:
            _type_row(conn, component['query']['type'], user)
            return False
        except TypeRefused:
            if waiting_for_viewer(conn, element_row(conn, type_id(component['query']['type'])), user):   # it waits for a second look: theirs to be told so, not closed
                return False
    return True


def _found(conn, user: dict | None, dashboard_id) -> dict:
    row = conn.execute(f'SELECT {COLUMNS} FROM dashboard WHERE id = ?', (dashboard_id,)).fetchone() if isinstance(dashboard_id, int) and not isinstance(dashboard_id, bool) else None
    record = _record(row) if row else None
    if record is None or not _may_open(user, record) or _reads_nothing(conn, user, record):
        if record is not None and _expired(record) and _published_to(user, record):   # only someone it was published to is told that it has ended: to anyone else it is not there
            raise DashboardRefused(tr('这个看板已经过期，不再开放了', 'This board has expired and is no longer open'), 410)
        raise DashboardRefused(tr('没有这个看板', 'There is no such board'), 404)
    return record


def _summary(record: dict, user: dict | None) -> dict:
    return {'id': record['id'], 'name': record['name'], 'owner': record['owner'], 'scope': record['scope'], 'expires_at': record['expires_at'], 'expired': _expired(record),
            'refresh_seconds': record['refresh_seconds'], 'updated_at': record['updated_at'], 'components': len(record['spec']['components']),
            'mine': _owns(user, record), 'may_change': _owns(user, record) or _is_admin(user)}


def list_dashboards(conn, user: dict | None) -> list[dict]:
    ensure_schema(conn)
    records = [_record(r) for r in conn.execute(f'SELECT {COLUMNS} FROM dashboard ORDER BY id DESC')]
    return [_summary(r, user) for r in records if _may_open(user, r) and not _reads_nothing(conn, user, r)]


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
                'owner_id': None, 'sign_in_note': sign_in_note()}
    names = {i: n for i, n in conn.execute('SELECT id, display_name FROM user')}
    return {**record, **_summary(record, user), 'visible_names': [names.get(i, tr('（已删除）', '(deleted)')) for i in record['visible_to']], 'sign_in_note': sign_in_note(), 'owner_id': record['owner_id']}


# --- what a board is made of ---------------------------------------------------------------------------------------------------------------------------

def _clean_name(value, what: str, limit: int) -> str:
    text = value.strip() if isinstance(value, str) else ''
    if not text or len(text) > limit or '\n' in text:
        raise DashboardRefused(tr(f'{what}要写一行字，最多 {limit} 个字符', f'{what} must be one line of at most {limit} characters'))
    return text


def normalize_spec(raw) -> dict:
    """{'components': [{'id', 'title', 'query', 'chart'}], 'filters': [{'field', 'label'}]} from what a page sent. A component's chart kind is one of the explorer's, or
    'rows' for a list of the first rows."""
    if not isinstance(raw, dict) or not isinstance(raw.get('components'), list) or not raw['components']:
        raise DashboardRefused(tr('看板里至少要有一个组件', 'A board needs at least one component'))
    if len(raw['components']) > MAX_COMPONENTS:
        raise DashboardRefused(tr(f'一个看板最多 {MAX_COMPONENTS} 个组件', f'A board can have at most {MAX_COMPONENTS} components'))
    components, seen = [], set()
    for i, c in enumerate(raw['components'], 1):
        if not isinstance(c, dict):
            raise DashboardRefused(tr('组件要写成对象', 'A component must be written as an object'))
        title = _clean_name(c.get('title'), tr(f'第 {i} 个组件的标题', f'The title of component {i}'), MAX_TITLE)
        raw_chart = c.get('chart')
        ident = c.get('id') if isinstance(c.get('id'), str) and re.fullmatch(r'[A-Za-z0-9_-]{1,20}', c['id']) else f'c{i}'
        if ident in seen:
            raise DashboardRefused(tr(f'组件编号“{ident}”重复了', f'The component id "{ident}" is repeated'))
        seen.add(ident)
        if 'text' in c or (isinstance(raw_chart, dict) and raw_chart.get('kind') == 'query'):
            components.append({'id': ident, 'title': title, 'text': _query_text(c, title), 'chart': {'kind': 'query'}})
            continue
        rows = isinstance(raw_chart, dict) and raw_chart.get('kind') == 'rows'
        try:
            query = normalize_query(c.get('query'))
            chart = {'kind': 'rows'} if rows else normalize_chart(raw_chart)
        except TypeRefused as exc:
            raise DashboardRefused(tr(f'“{title}”：{exc}', f'"{title}": {exc}')) from None
        components.append({'id': ident, 'title': title, 'query': query, 'chart': chart})
    bar = raw.get('filters') or []
    if not isinstance(bar, list) or len(bar) > MAX_BAR or not all(isinstance(f, dict) for f in bar):
        raise DashboardRefused(tr(f'筛选条最多 {MAX_BAR} 项', f'The filter bar can have at most {MAX_BAR} items'))
    filters = [{'field': _clean_name(f.get('field'), tr('筛选项的字段', 'The filter field'), 60), 'label': _clean_name(f.get('label') or f.get('field'), tr('筛选项的名字', 'The filter name'), MAX_TITLE)} for f in bar]
    for raw_filter, normalized in zip(bar, filters):
        op = raw_filter.get('op', 'eq')
        if op not in ('eq', 'name_is'):
            raise DashboardRefused(tr('筛选项只支持等于或名称匹配', 'A filter bar supports equality or name matching'))
        if op == 'name_is':
            normalized['op'] = op
    if len({f['field'] for f in filters}) != len(filters):
        raise DashboardRefused(tr('筛选条里一个字段只能出现一次', 'A field can appear only once in the filter bar'))
    params = _params(raw.get('params'))
    declared = {p['name'] for p in params}
    for c in components:
        missing = [n for n in param_names(c['text']) if n not in declared] if 'text' in c else []
        if missing:
            raise DashboardRefused(tr(f'“{c["title"]}”用到了 {tr("、", ", ").join("$" + n for n in missing)}：要在看板的参数里加上它和默认值', f'"{c["title"]}" uses {", ".join("$" + n for n in missing)}: add it with a default value to the board parameters'))
    return {'components': components, 'filters': filters, 'params': params}


def _query_text(c: dict, title: str) -> str:
    """A query card's text, checked for what can be checked without the data: one query of at most MAX_TEXT characters that can be read into words."""
    text = c.get('text')
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise DashboardRefused(tr(f'“{title}”：要写一条本体查询，最多 {MAX_TEXT} 个字符', f'"{title}": write an ontology query of at most {MAX_TEXT} characters'))
    if not isinstance(c.get('chart'), dict) or c['chart'].get('kind') != 'query':
        raise DashboardRefused(tr(f'“{title}”：本体查询组件的种类是 query，它的结果按查询自己的样子显示', f'"{title}": an ontology query component has the kind query, and its result is shown as the query gives it'))
    try:
        param_names(text)
    except QueryError as exc:
        raise DashboardRefused(tr(f'“{title}”：{exc}', f'"{title}": {exc}')) from None
    if is_graph(text):   # a board shows numbers to everyone it is shared with, viewers too; a graph shows objects one by one
        raise DashboardRefused(tr(f'“{title}”：看板组件要算一个数，SELECT GRAPH 画的是一个个对象，请在问答页的“写查询”里看', f'"{title}": a board component computes a number, while SELECT GRAPH draws individual objects; look at it under Write a query on the Ask page'))
    return text


def _params(raw) -> list[dict]:
    """The board's parameters, [{name, label, default}]: at most MAX_PARAMS, each name once, each with a default (the board is worked out with it until a reader
    types another value)."""
    if raw in (None, ''):
        return []
    if not isinstance(raw, list) or not all(isinstance(p, dict) for p in raw):
        raise DashboardRefused(tr('参数要写成 [{"name": 名字, "label": 显示的名字, "default": 默认值}]', 'Parameters must be written as [{"name": name, "label": display name, "default": default value}]'))
    if len(raw) > MAX_PARAMS:
        raise DashboardRefused(tr(f'一个看板最多 {MAX_PARAMS} 个参数', f'A board can have at most {MAX_PARAMS} parameters'))
    out = []
    for p in raw:
        name = p['name'].strip() if isinstance(p.get('name'), str) else ''
        if not PARAM_NAME.fullmatch(name):
            raise DashboardRefused(tr(f'参数名“{name}”要以字母、下划线或汉字开头，只有字母、数字、下划线和汉字，最多 20 个字符，不写 $', f'The parameter name "{name}" must start with a letter, underscore or Chinese character, use only letters, digits, underscores and Chinese characters, be at most 20 characters, and omit the $'))
        if name in {q['name'] for q in out}:
            raise DashboardRefused(tr(f'参数名 ${name} 重复了', f'The parameter name ${name} is repeated'))
        default = p.get('default')
        default = str(default).strip() if isinstance(default, (str, int, float)) and not isinstance(default, bool) else ''
        if not default or len(default) > MAX_VALUE:
            raise DashboardRefused(tr(f'参数 ${name} 要写默认值，最多 {MAX_VALUE} 个字符：看板打开时先用它算', f'The parameter ${name} needs a default of at most {MAX_VALUE} characters: the board is computed with it when opened'))
        label = p['label'] if isinstance(p.get('label'), str) and p['label'].strip() else name
        out.append({'name': name, 'label': _clean_name(label, tr(f'参数 ${name} 的名字', f'The name of parameter ${name}'), MAX_TITLE), 'default': default})
    return out


def _defaults(spec: dict) -> dict:
    return {p['name']: p['default'] for p in spec.get('params', [])}


def _values(spec: dict, given) -> dict:
    """The parameters a board is worked out with: what the reader typed for a parameter the board has, the default for one left empty; other names are ignored."""
    if given in (None, ''):
        given = {}
    if not isinstance(given, dict) or not all(isinstance(k, str) and isinstance(v, (str, int, float)) and not isinstance(v, bool) and len(str(v)) <= MAX_VALUE for k, v in given.items()):
        raise DashboardRefused(tr(f'参数要写成 {{名字: 取值}}，取值是文字或数字，最多 {MAX_VALUE} 个字符', f'Parameters must be written as {{name: value}}, where a value is text or a number of at most {MAX_VALUE} characters'))
    typed = {k: str(v).strip() for k, v in given.items()}
    return {p['name']: typed.get(p['name']) or p['default'] for p in spec.get('params', [])}


def _publish(conn, payload: dict) -> dict:
    scope = payload.get('scope', 'private')
    if not isinstance(scope, str) or scope not in SCOPES:
        raise DashboardRefused(tr(f'发布范围要是 {tr("、", ", ").join(SCOPES)} 之一', f'The audience must be one of: {", ".join(SCOPES)}'))
    visible = payload.get('visible_to') or []
    if scope == 'named':
        active = {i for (i,) in conn.execute('SELECT id FROM user WHERE disabled = 0')}
        if not isinstance(visible, list) or not visible or not all(isinstance(i, int) and not isinstance(i, bool) and i in active for i in visible):
            raise DashboardRefused(tr('指定的人要写成在用账号的编号列表，至少一个', 'Named people must be a list of active account ids, at least one'))
        visible = sorted(set(visible))
    else:
        visible = []
    expires = payload.get('expires_at') or None
    if expires is not None:
        if not isinstance(expires, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', expires):
            raise DashboardRefused(tr('到期日要写成 年-月-日', 'The expiry date must be written as YYYY-MM-DD'))
        try:
            date.fromisoformat(expires)
        except ValueError:
            raise DashboardRefused(tr('到期日不是一个真实的日期', 'The expiry date is not a real date')) from None
        if expires < date.today().isoformat():
            raise DashboardRefused(tr('到期日不能早于今天', 'The expiry date cannot be before today'))
    refresh = payload.get('refresh_seconds', 0)
    if refresh not in REFRESH or isinstance(refresh, bool):
        raise DashboardRefused(tr(f'刷新间隔要是 {tr("、", ", ").join(str(r) for r in REFRESH)} 秒之一（0 是只在打开时读）', f'The refresh interval must be one of {", ".join(str(r) for r in REFRESH)} seconds (0 reads only when opened)'))
    return {'scope': scope, 'visible_to': visible, 'expires_at': expires, 'refresh_seconds': refresh}


def _checked(conn, user: dict | None, payload: dict) -> tuple[str, dict, dict]:
    name = _clean_name(payload.get('name'), tr('看板的名字', 'The board name'), MAX_NAME)
    spec = normalize_spec(payload.get('spec'))
    problem = next((c for c in evaluate(conn, user, spec, {}, _defaults(spec)) if c['status'] != 'ok'), None)   # a component that cannot be worked out is refused here, not found out by the readers
    if problem:
        raise DashboardRefused(tr(f'“{problem["title"]}”：{problem["message"]}', f'"{problem["title"]}": {problem["message"]}'))
    return name, spec, _publish(conn, payload)


def create_dashboard(conn, user: dict | None, payload: dict) -> dict:
    ensure_schema(conn)
    name, spec, published = _checked(conn, user, payload)
    now = _now()
    cursor = conn.execute('INSERT INTO dashboard(name, owner_id, owner, spec_json, scope, visible_to_json, expires_at, refresh_seconds, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)',
                          (name, user['id'] if user else 0, user['display_name'] if user else tr('本机', 'local'), json.dumps(spec, ensure_ascii=False), published['scope'],
                           json.dumps(published['visible_to']), published['expires_at'], published['refresh_seconds'], now, now))
    return dashboard_detail(conn, user, cursor.lastrowid)


def update_dashboard(conn, user: dict | None, payload: dict) -> dict:
    ensure_schema(conn)
    record = _found(conn, user, payload.get('id'))
    if not (_owns(user, record) or _is_admin(user)):
        raise DashboardRefused(tr('只有看板的主人或管理员能改它', 'Only the board owner or an admin can change it'), 403)
    if payload.get('version') != record['version']:
        raise DashboardRefused(tr('这个看板在你打开之后被改过，请刷新后再改', 'This board was changed after you opened it. Refresh and edit again'), 409)
    name, spec, published = _checked(conn, user, payload)
    conn.execute('UPDATE dashboard SET name = ?, spec_json = ?, scope = ?, visible_to_json = ?, expires_at = ?, refresh_seconds = ?, version = version + 1, updated_at = ? WHERE id = ?',
                 (name, json.dumps(spec, ensure_ascii=False), published['scope'], json.dumps(published['visible_to']), published['expires_at'], published['refresh_seconds'], _now(), record['id']))
    conn.execute('DELETE FROM dashboard_last WHERE dashboard_id = ?', (record['id'],))   # what was stored was worked out for the components as they were
    return dashboard_detail(conn, user, record['id'])


def delete_dashboard(conn, user: dict | None, payload: dict) -> dict:
    ensure_schema(conn)
    record = _found(conn, user, payload.get('id'))
    if not (_owns(user, record) or _is_admin(user)):
        raise DashboardRefused(tr('只有看板的主人或管理员能删它', 'Only the board owner or an admin can delete it'), 403)
    conn.execute('DELETE FROM dashboard WHERE id = ?', (record['id'],))
    conn.execute('DELETE FROM dashboard_last WHERE dashboard_id = ?', (record['id'],))
    conn.execute('DELETE FROM checked_number WHERE dashboard_id = ?', (record['id'],))   # what the team checked on it goes with it
    return {'deleted': record['id']}


# --- working a board out -------------------------------------------------------------------------------------------------------------------------------

def _with_bar(conn, user: dict | None, component: dict, filters: list[dict]) -> dict:
    """The component's query with the filter bar's picks added for the fields its type has (a pick for a field it does not have leaves it alone)."""
    query = component['query']
    row = _type_row(conn, query['type'], user)
    own = {p['column'] for p in _content(row)['properties']} - hidden_columns(conn, row['element_id'], user)
    added = [f for f in filters if f['field'] in own]
    return {**query, 'filters': [*query['filters'], *added]}


def _waiting_on(conn, user: dict | None, component: dict) -> list[str] | None:
    """The people who could confirm it again, when what a reader cannot read is a type (or a view of it) that was confirmed and needs another look, and not one that is
    closed to them: [] when nobody could. None when the component is unreadable for another reason."""
    query = component['query']
    rows = [element_row(conn, type_id(query['type']))]
    if query['view']:
        rows.append(element_row(conn, view_id(query['view'])))
    if rows[0] is None or not can_access(conn, rows[0]['element_id'], user):
        return None
    pending = [r for r in rows if r is not None and (r['state'] == 'needs_look' or (r['element_id'].startswith(VIEW_PREFIX) and r['state'] in ('proposed', 'checked')))]   # a view changed since it was confirmed waits too
    if not pending or not all(was_confirmed(conn, r['element_id']) for r in pending):   # one nobody ever confirmed is not waiting for a re-confirmation
        return None
    return list(dict.fromkeys(name for r in pending for name in _confirmers(conn, r, user)[1]))


def _changed_view(conn, component: dict) -> bool:
    """Whether the component's view waits because a person changed it (not because the data moved)."""
    row = element_row(conn, view_id(component['query']['view'])) if component['query']['view'] else None
    return row is not None and row['state'] in ('proposed', 'checked')


def _kept_from(conn, user: dict | None, component: dict) -> set[str]:
    """The columns of the component's type kept from this person (none for a query card: it is told it is closed, not which columns)."""
    if 'text' in component:
        return set()
    return hidden_columns(conn, type_id(str(component['query'].get('type'))), user)


def _failed(conn, user: dict | None, component: dict, exc: Exception) -> dict:
    base = {'id': component['id'], 'title': component['title'], 'chart': component['chart']}
    if _kept_from(conn, user, component):   # the reason may name a column kept from them: say only that they cannot read it
        return {**base, 'chart': {'kind': component['chart'].get('kind')}, 'status': 'unavailable', 'message': tr('这个组件用到了你看不到的属性', 'This component uses a property you cannot see')}   # the kind only: the rest names columns
    waiting = _waiting_on(conn, user, component) if isinstance(exc, TypeRefused) else None
    if waiting is not None:
        who = tr('、', ', ').join(waiting) or tr('有权限确认的人', 'someone who may confirm')
        message = tr(f'定义改了，正在等 {who} 再确认', f'The definition was changed and is waiting for {who} to confirm it again') if _changed_view(conn, component) else tr(f'数据更新了，正在等 {who} 再确认', f'The data was updated and is waiting for {who} to confirm again')
        return {**base, 'status': 'waiting', 'message': message, 'waiting_on': waiting}
    status = getattr(exc, 'status', None)
    message = tr('你现在看不到这个对象类型：它还没有确认，或者没有开放给你', 'You cannot see this object type now: it is not confirmed yet, or it is not open to you') if isinstance(exc, TypeRefused) and status == 404 and str(exc) in ('没有这个对象类型', 'There is no such object type') else str(exc)
    return {**base, 'status': 'unavailable', 'message': message}


def _work_out(conn, user: dict | None, component: dict, filters: list[dict]) -> dict:
    query = _with_bar(conn, user, component, filters)
    if component['chart']['kind'] == 'rows':
        table = explore_table(conn, user, query)
        result = {**table, 'rows': table['rows'][:ROW_LIMIT], 'numbers': table['numbers'][:ROW_LIMIT], 'shown': min(ROW_LIMIT, table['total'])}
    else:
        result = explore_chart(conn, user, query, component['chart'])
    return {'id': component['id'], 'title': component['title'], 'chart': component['chart'], 'status': 'ok', 'result': result}


def _text_opens(conn, user: dict | None, component: dict, values: dict) -> bool:
    """Whether a query card can be read into a query over what this person may see (not yet whether its definitions answer)."""
    from ontology_poc_generator.ontopoc_query import compile_query
    from ontology_poc_generator.workspace_questions import query_catalog, scope
    try:
        compile_query(component['text'], query_catalog(scope(conn, user)), values)
        return True
    except (QueryError, KeyError, TypeError, AttributeError):
        return False


def _work_out_text(conn, user: dict | None, component: dict, values: dict, author: bool, defaults: dict) -> dict:
    """A query card worked out for this person: the answer as a question's (status, answer, text with the values in it, definitions, limited_by_rule) and its standing.
    A refusal says why to the board's author. Anyone else is told only which kind of trouble it is (closed to them, not confirmed now, or a value they typed that
    the card cannot use, when the same card works with the defaults): a reason can name a column or type kept from them."""
    from ontology_poc_generator.workspace_questions import QaRefused, run_text
    base = {'id': component['id'], 'title': component['title'], 'chart': component['chart']}
    try:
        got = run_text(conn, user, component['text'], values)
    except QaRefused as exc:
        if author:
            return {**base, 'status': 'unavailable', 'message': str(exc)}
        return {**base, 'status': 'unavailable', 'message': bad_value_text() if values != defaults and _runs(conn, user, component, defaults) else closed_text()}
    if got['status'] not in ('answered', 'no_data'):
        return {**base, 'status': 'unavailable', 'message': (got.get('reason') or tr('没有算出来', 'It could not be computed')) if author else unsettled_text()}
    result = {k: got[k] for k in ('status', 'answer', 'reason', 'text', 'definitions', 'limited_by_rule', 'types', 'datasets') if k in got}
    return {**base, 'status': 'ok', 'result': {**result, 'standing': _standing(conn, [d['id'] for d in got.get('definitions', [])])}}


def _runs(conn, user: dict | None, component: dict, values: dict) -> bool:
    """Whether a query card is worked out with these values for this person without being refused as written."""
    from ontology_poc_generator.workspace_questions import QaRefused, run_text
    try:
        run_text(conn, user, component['text'], values)
        return True
    except QaRefused:
        return False


def evaluate(conn, user: dict | None, spec: dict, bar: dict, values: dict | None = None, author: bool = True) -> list[dict]:
    """Every component worked out for this person: {'id', 'title', 'chart', 'status': 'ok', 'result'} or {..., 'status': 'unavailable', 'message'}. A component that
    cannot be read by this person (a type they may not see, a view or column that is gone) says why and the others still show. `values` are the parameters the query
    cards are worked out with; `author` is whether this person made the board (or may change it): only they are told what a query card that fails reads."""
    filters = [{'field': f['field'], 'op': f.get('op', 'eq'), 'value': bar[f['field']]}
               for f in spec['filters'] if f['field'] in bar]
    out = []
    for component in spec['components']:
        if 'text' in component:
            out.append(_work_out_text(conn, user, component, values if values is not None else _defaults(spec), author, _defaults(spec)))
            continue
        try:
            out.append(_work_out(conn, user, component, filters))
        except TypeRefused as exc:
            out.append(_failed(conn, user, component, exc))
    return out


def _bar_options(conn, user: dict | None, spec: dict, picked: dict) -> list[dict]:
    """The filter bar as the page draws it: each field with its name, the values to pick from (read from the first component whose type has the field, over the rows
    this person may read) and the pick."""
    out = []
    kept = set().union(set(), *(_kept_from(conn, user, c) for c in spec['components']))
    for f in spec['filters']:
        if f['field'] in kept:   # a filter on a column kept from them is not on their bar
            continue
        options, name = None, f['label']
        for component in (c for c in spec['components'] if 'query' in c):
            try:
                fields = explore_meta(conn, user, component['query']['type'])['fields']
            except TypeRefused:
                continue
            found = next((x for x in fields if x['key'] == f['field'] and not x['derived']), None)
            if found:
                options = None if f.get('op') == 'name_is' else found['options']
                break
        out.append({**f, 'name': name, 'options': options, 'value': picked.get(f['field'], '')})
    return out


def _picked(spec: dict, bar) -> dict:
    """The filter bar's picks from a request: {field: value}, for the fields the board has and only non-empty ones."""
    if bar in (None, ''):
        return {}
    if not isinstance(bar, dict) or not all(isinstance(k, str) and isinstance(v, str) and len(v) <= 200 for k, v in bar.items()):
        raise DashboardRefused(tr('筛选条的取值要写成 {字段: 取值}', 'Filter bar values must be written as {field: value}'))
    fields = {f['field'] for f in spec['filters']}
    return {k: v for k, v in bar.items() if k in fields and v.strip()}


def _headline(components: list[dict]) -> dict:
    """What the top of a board says about its numbers: all of them stand on confirmed definitions only when every component shows a number that does."""
    ok = [c for c in components if c['status'] == 'ok']
    grey = [c['title'] for c in ok if not c['result']['standing']['confirmed']]
    waiting = [c['title'] for c in components if c['status'] == 'waiting']
    unavailable = [c['title'] for c in components if c['status'] == 'unavailable']
    said = [*([tr(f'{len(grey)} 个组件用到了现在不是“已确认”的定义，灰色显示：{tr("、", ", ").join(grey)}', f'{len(grey)} components use definitions that are not confirmed now and are shown grey: {", ".join(grey)}')] if grey else []),
            *([tr(f'{len(waiting)} 个组件在等再确认：{tr("、", ", ").join(waiting)}', f'{len(waiting)} components are waiting to be confirmed again: {", ".join(waiting)}')] if waiting else []),
            *([tr(f'{len(unavailable)} 个组件你现在看不到：{tr("、", ", ").join(unavailable)}', f'You cannot see {len(unavailable)} components now: {", ".join(unavailable)}')] if unavailable else [])]
    return {'components': len(components), 'unavailable': unavailable, 'waiting': waiting, 'grey': grey, 'text': tr('；'.join(said) or '全部按已确认的定义算出', '; '.join(said) or 'All computed from confirmed definitions')}


def _with_last(conn, user: dict | None, board: int, picked: dict, components: list[dict], components_spec: list[dict] = ()) -> list[dict]:
    """Each result that stands on confirmed definitions is kept for this reader as the last confirmed one; a component that waits for a confirmation carries the one that
    was kept, {'result', 'at'}, or none when this reader had not read it while it was confirmed."""
    reader, picks, out = user['id'] if user else 0, json.dumps(picked, sort_keys=True, ensure_ascii=False), []
    for c in components:
        key = (board, c['id'], reader, picks)
        if c['chart'].get('kind') == 'query':   # never "waiting" (a query card says why it is refused): what it kept would not be read back
            out.append(c)
        elif c['status'] == 'ok' and c['result']['standing']['confirmed']:
            conn.execute('INSERT OR REPLACE INTO dashboard_last(dashboard_id, component_id, reader, picks, result_json, at) VALUES (?, ?, ?, ?, ?, ?)',
                         (*key, json.dumps(c['result'], ensure_ascii=False), _now()))
            out.append(c)
        elif c['status'] == 'waiting' and next((x for x in components_spec if x['id'] == c['id']), None) and _kept_from(conn, user, next(x for x in components_spec if x['id'] == c['id'])):
            out.append({**c, 'last': None})   # what was kept was worked out before a column was kept from them
        elif c['status'] == 'waiting':
            kept = conn.execute('SELECT result_json, at FROM dashboard_last WHERE dashboard_id = ? AND component_id = ? AND reader = ? AND picks = ?', key).fetchone()
            out.append({**c, 'last': {'result': json.loads(kept[0]), 'at': kept[1]} if kept else None})
        else:
            out.append(c)
    return out


def _param_options(spec: dict, values: dict) -> list[dict]:
    return [{**p, 'value': values[p['name']]} for p in spec.get('params', [])]


def dashboard_data(conn, user: dict | None, dashboard_id, bar=None, params=None) -> dict:
    """The board worked out for this person with the filter bar's picks and the parameters they typed (the defaults for the rest)."""
    ensure_schema(conn)
    record = _found(conn, user, dashboard_id)
    picked = _picked(record['spec'], bar)
    values = _values(record['spec'], params)
    kept_as = {'bar': picked, 'params': values} if values else picked   # a board with no parameters keeps what it kept before under the same key
    author = _owns(user, record) or _is_admin(user)
    components = _with_last(conn, user, record['id'], kept_as, evaluate(conn, user, record['spec'], picked, values, author), record['spec']['components'])
    from ontology_poc_generator.checked_numbers import on_board
    components, checked = on_board(conn, user, record, components, not picked and values == _defaults(record['spec']))   # the numbers the team checked, worked out again by code
    return {'id': record['id'], 'name': record['name'], 'bar': _bar_options(conn, user, record['spec'], picked), 'params': _param_options(record['spec'], values),
            'components': components, 'headline': {**_headline(components), 'checked': checked},
            'refresh_seconds': record['refresh_seconds'], 'expired': _expired(record), 'read_at': _now(), 'sign_in_note': sign_in_note()}


def preview(conn, user: dict | None, payload: dict) -> dict:
    """A board that is not saved, worked out for its author: what the editor shows beside the form."""
    spec = normalize_spec(payload.get('spec'))
    picked = _picked(spec, payload.get('bar'))
    values = _values(spec, payload.get('params'))
    components = evaluate(conn, user, spec, picked, values)
    return {'bar': _bar_options(conn, user, spec, picked), 'params': _param_options(spec, values), 'components': components, 'headline': _headline(components)}
