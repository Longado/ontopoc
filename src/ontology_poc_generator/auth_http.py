"""The sign-in gate in front of every route, and the routes for accounts (/api/auth/*, /api/users*).

A request is admitted when its Host and (for a POST) its Origin are ones this service was configured for, and the role of the person
behind its session cookie or API token is enough for the route (access.py). With no_auth the service keeps its old local-only behaviour
and every request is the built-in local admin: for trials and tests on one's own machine, never for a shared one.
"""
from __future__ import annotations

import os
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlsplit

from ontology_poc_generator import accounts
from ontology_poc_generator.accounts import transaction
from ontology_poc_generator.actor import set_actor
from ontology_poc_generator.access import PUBLIC, allows, required_role
from ontology_poc_generator.workspace_store import open_workspace

COOKIE = 'ontopoc_session'
LOCAL_USER = {'id': None, 'username': '本机', 'display_name': '本机', 'role': 'admin', 'disabled': False, 'must_change': False,
              'created_at': None, 'last_login_at': None, 'provider': 'local'}
LOOPBACK = ('127.0.0.1', 'localhost')
LOOPBACK_ADDRESSES = ('127.0.0.1', '::1')   # the peer a proxy on this machine connects from
PROXY_HEADERS = ('X-Forwarded-For', 'X-Forwarded-Host', 'X-Forwarded-Proto', 'Forwarded', 'X-Real-IP', 'Via')   # a client that reaches the service itself sends none of these
AUTH_BODY = 4096   # the biggest body any /api/auth/* or /api/users* request needs, read before anyone is signed in
STILL_NEEDED = ('/api/auth/me', '/api/auth/logout', '/api/auth/password')   # what a person who must change their password may still do
NOT_HERE = '这个服务没有开登录（--no-auth），没有账号可管理'
NO_TOKEN = '这个操作要用登录后的页面做，不能用令牌'


class Gate:
    def __init__(self, db_path, port: int, origins=(), no_auth: bool = False, trusted_proxies=None):
        """origins: the extra addresses people reach the service at, e.g. https://ontopoc.example.com (the proxy that terminates TLS) or a
        dev server; the service's own http://127.0.0.1:<port> and http://localhost:<port> are always allowed. trusted_proxies: the peer
        addresses whose X-Forwarded-For is believed (by default this machine, once an https origin is configured: the proxy in front).
        no_auth is refused unless ONTOPOC_DEV=1 and when any origin is configured: a service with a proxy in front is a shared one."""
        if no_auth and os.environ.get('ONTOPOC_DEV') != '1':
            raise ValueError('--no-auth 只用于开发：先设置环境变量 ONTOPOC_DEV=1，再用它。有人要登录的服务不能关登录')
        if no_auth and origins:
            raise ValueError('--no-auth 不能和 --origin 一起用：前面有代理的服务是给别人用的，不能关登录')
        self.db_path, self.no_auth, self.limiter = db_path, no_auth, accounts.LoginLimiter()
        extra = [o.rstrip('/') for o in origins]
        for origin in extra:
            parts = urlsplit(origin)
            if parts.scheme not in ('http', 'https') or not parts.hostname or parts.path or parts.query:
                raise ValueError(f'地址“{origin}”要写成 https://主机名 的样子')
            if parts.scheme == 'http' and parts.hostname not in LOOPBACK:
                raise ValueError(f'地址“{origin}”不是本机，必须用 https（密码和登录信息不能走明文）')
        self.origins = {f'http://{h}:{port}' for h in LOOPBACK} | set(extra)
        self.hosts = set(LOOPBACK) | {urlsplit(o).hostname for o in extra}
        # a cookie is Secure as soon as the service is reached over https; the proxy in front is then the one we trust to say who is calling
        self.secure = any(o.startswith('https://') for o in extra)
        self.proxies = set(trusted_proxies) if trusted_proxies is not None else set(LOOPBACK_ADDRESSES) if self.secure else set()
        self.cookie = ('__Host-' if self.secure else '') + COOKIE   # the prefix makes a browser refuse a cookie that is not Secure, for this exact host, at /
        if not no_auth:
            accounts.dummy_hash()   # made now, not by the first stranger who tries an unknown name

    def connect(self):
        return open_workspace(self.db_path)

    def needs_first_admin(self) -> bool:
        conn = self.connect()
        try:
            return accounts.user_count(conn) == 0
        finally:
            conn.close()

    # who is calling

    def client(self, h) -> str:
        """The caller's address: the peer, or, when the peer is a proxy we trust, the last address in the forwarded header. The proxy appends the
        address it saw (as a new header line or onto the last one); what came before is the caller's own claim."""
        peer = h.client_address[0]
        if peer in self.proxies:
            forwarded = [a.strip() for a in ','.join(h.headers.get_all('X-Forwarded-For') or []).split(',') if a.strip()]
            return forwarded[-1] if forwarded else peer
        return peer

    def _credentials(self, h) -> tuple[str | None, str | None]:
        """(bearer token, session cookie token)."""
        header = h.headers.get('Authorization', '')
        bearer = (header[7:].strip() if header[:7].lower() == 'bearer ' else '') or None   # an empty value is no credential: the cookie then needs the Origin check
        try:
            cookie = SimpleCookie(h.headers.get('Cookie', '')).get(self.cookie)
        except CookieError:
            cookie = None
        return bearer, cookie.value if cookie else None

    def admit(self, h, method: str) -> bool:
        """Sets h.user (None for a stranger on a public route) and h.session_token; replies and returns False when the request is refused."""
        h.user, h.session_token = None, None
        set_actor(None)   # this thread served another request before: nothing of that one stays
        if self.no_auth:
            if any(h.headers.get(name) is not None for name in PROXY_HEADERS):   # a request that came through a proxy is not from this machine, whatever its Host says
                h.reply(403, {'error': '没开登录的服务不接受经过代理的请求。'})
                return False
            h.user = LOCAL_USER
            return h.local_request()
        path = urlsplit(h.path).path
        host = urlsplit('http://' + h.headers.get('Host', '')).hostname
        if host not in self.hosts:
            h.reply(403, {'error': '这个地址不对，请用部署时给的地址访问。'})
            return False
        bearer, cookie = self._credentials(h)
        if method == 'POST' and bearer is None and h.headers.get('Origin') not in self.origins:   # a cookie rides along with any page the browser has open
            h.reply(403, {'error': '请求不是从本站页面发出的。'})
            return False
        conn = self.connect()
        try:
            user = accounts.token_user(conn, bearer) if bearer else accounts.session_user(conn, cookie)
            empty = accounts.user_count(conn) == 0
        finally:
            conn.close()
        h.user, h.session_token = user, None if bearer else cookie
        set_actor(user)
        if empty and path != '/api/ontology/health':   # nothing to sign in to: the only way forward is on the machine
            h.reply(503, {'error': '还没有账号。请在服务所在的机器上运行：python -m ontology_poc_generator.accounts create-admin', 'setup': True})
            return False
        needed = required_role(method, path)
        if needed == PUBLIC:
            return True
        if user is None:
            h.reply(401, {'error': '请先登录', 'login': True})
            return False
        if user['must_change'] and path not in STILL_NEEDED:
            h.reply(403, {'error': '请先把初始密码改掉', 'must_change': True})
            return False
        if not allows(user['role'], needed):
            h.reply(403, {'error': '你的角色不能做这个'})
            return False
        return True

    # accounts

    def handle(self, h, method: str) -> bool:
        """The account routes; True when the request was one of them (and has been answered)."""
        path = urlsplit(h.path).path
        if not (path.startswith('/api/auth/') or path == '/api/users' or path.startswith('/api/users/') or path == '/api/settings'):
            return False
        if self.no_auth:
            if path == '/api/auth/me':
                h.reply(200, {'user': LOCAL_USER, 'auth': False})
            else:
                h.reply(400, {'error': NOT_HERE})
            return True
        try:
            payload = h.read_json(AUTH_BODY) if method == 'POST' else {}
            if payload is None:
                return True
            if path not in ('/api/auth/login', '/api/auth/me') and h.session_token is None:
                raise accounts.AccountError(NO_TOKEN, 403)
            conn = self.connect()
            try:
                self._route(h, conn, method, path, payload)
            finally:
                conn.close()
        except accounts.AccountError as exc:
            h.reply(exc.status, {'error': str(exc)}, {'Retry-After': '60'} if exc.status == 429 else None)
        except (ValueError, UnicodeError) as exc:
            h.reply(400, {'error': str(exc)})
        return True

    def _cookie(self, token: str, max_age: int) -> dict:
        return {'Set-Cookie': f'{self.cookie}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}' + ('; Secure' if self.secure else '')}

    def _route(self, h, conn, method: str, path: str, payload: dict) -> None:
        user, me = h.user, {'auth': True}   # me: what every account answer carries, so a page can tell the service has sign-in
        if path == '/api/auth/login':
            found = accounts.authenticate(conn, self.limiter, payload.get('username'), payload.get('password'), self.client(h))   # not in a transaction: a failure's log line must stay
            accounts.end_session(conn, h.session_token)   # signing in again ends the session this browser already had
            token = accounts.start_session(conn, found['id'])
            h.reply(200, {'user': found, **me}, self._cookie(token, int(accounts.ABSOLUTE.total_seconds())))
        elif path == '/api/auth/me':
            h.reply(200, {'user': user, **me})
        elif path == '/api/auth/logout':
            accounts.end_session(conn, h.session_token)
            h.reply(200, {'ok': True}, self._cookie('', 0))
        elif path == '/api/auth/password':
            accounts.change_password(conn, user, payload.get('current'), payload.get('new'), keep_token=h.session_token,
                                     limiter=self.limiter, client=self.client(h))
            h.reply(200, {'user': accounts.get_user(conn, user['id']), **me})
        elif path == '/api/auth/tokens' and method == 'GET':
            h.reply(200, {'tokens': accounts.list_tokens(conn, user['id'])})
        elif path == '/api/auth/tokens':
            with transaction(conn):
                record, token = accounts.create_token(conn, user, payload.get('label'))
            h.reply(200, {**record, 'token': token})   # the only time the token itself is shown
        elif path == '/api/auth/tokens/revoke':
            accounts.revoke_token(conn, user, payload.get('id'))
            h.reply(200, {'ok': True})
        elif path == '/api/users' and method == 'GET':
            h.reply(200, {'users': accounts.list_users(conn)})
        elif path == '/api/users':
            with transaction(conn):
                made = accounts.create_user(conn, payload.get('username'), payload.get('display_name'), payload.get('role'), payload.get('password'), user['username'])
            h.reply(200, {'user': made})
        elif path == '/api/settings' and method == 'GET':
            h.reply(200, {'two_person': accounts.two_person(conn)})
        elif path == '/api/settings':
            if 'two_person' not in payload:
                raise accounts.AccountError('要写明改什么（two_person）')
            with transaction(conn):
                h.reply(200, {'two_person': accounts.set_two_person(conn, payload['two_person'], user['username'])})
        elif path in ('/api/users/update', '/api/users/disable', '/api/users/reset-password'):
            with transaction(conn):
                h.reply(200, {'user': self._change(conn, user, path, payload)})
        else:
            h.reply(404, {'error': '没有这个接口'})

    @staticmethod
    def _change(conn, actor: dict, path: str, payload: dict) -> dict:
        target = payload.get('id')
        if path == '/api/users/disable':
            return accounts.set_disabled(conn, actor, target, payload.get('disabled'))
        if path == '/api/users/reset-password':
            if target == actor['id']:
                raise accounts.AccountError('自己的密码要在“我的账号”里改，那里要输入现在的密码', 403)
            return accounts.reset_password(conn, actor['username'], target, payload.get('password'))
        if 'role' not in payload and 'display_name' not in payload:
            raise accounts.AccountError('要写明改什么（role 或 display_name）')
        if 'display_name' in payload:
            accounts.set_display_name(conn, actor, target, payload['display_name'])
        return accounts.set_role(conn, actor, target, payload['role']) if 'role' in payload else accounts.get_user(conn, target)
