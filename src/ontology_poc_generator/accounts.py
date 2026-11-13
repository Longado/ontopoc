"""Accounts of the workspace: people, passwords, sessions, API tokens and three roles (viewer, builder, admin).

Passwords are hashed with scrypt from the standard library. A session is a random token in a cookie; only its SHA-256 is stored, so
the table cannot be replayed and a row can be deleted to sign someone out at once. API tokens (for scripts and the MCP server) work the
same way and never exceed their owner's role. The first admin is made on the host with `python -m ontology_poc_generator.accounts
create-admin`: there is no default account and no setup page on the network.

Everything here takes a workspace connection and returns plain dicts; HTTP lives in auth_http.py.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import json
import math
import re
import secrets
import sqlite3
import sys
import threading
import time
import unicodedata
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROLES = ('viewer', 'builder', 'admin')
RANK = {role: i for i, role in enumerate(ROLES, 1)}
ROLE_LABEL = {'viewer': '查看', 'builder': '建设', 'admin': '管理员'}

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1   # stored with each hash, so raising them later does not lock anyone out
MIN_PASSWORD, MAX_PASSWORD = 12, 1024   # the cap keeps a huge "password" from being used to burn the host's CPU
IDLE, ABSOLUTE = timedelta(hours=8), timedelta(days=14)
TOUCH_EVERY = timedelta(seconds=60)   # last-seen is written at most this often, not on every request
GENERIC = '账号或密码不对'
USERNAME = re.compile(r'[\w.@+-]{1,64}')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('viewer', 'builder', 'admin')), password_hash TEXT, disabled INTEGER NOT NULL DEFAULT 0,
    must_change INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, last_login_at TEXT, provider TEXT NOT NULL DEFAULT 'local');
CREATE TABLE IF NOT EXISTS session (
    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES user(id), created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
    expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS api_token (
    id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES user(id), label TEXT NOT NULL,
    created_at TEXT NOT NULL, last_used_at TEXT, revoked_at TEXT);
'''

_USER_KEYS = ('id', 'username', 'display_name', 'role', 'disabled', 'must_change', 'created_at', 'last_login_at', 'provider')
_USER_COLUMNS = ', '.join(_USER_KEYS)
_JOINED = ', '.join(f'u.{k}' for k in _USER_KEYS)   # for queries that also read session or api_token, which have columns of the same names


class AccountError(ValueError):
    """A refusal in plain Chinese, with the HTTP status it should be sent with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec='seconds')


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# passwords

def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(unicodedata.normalize('NFC', password).encode(), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=256 * n * r * p)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f'scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${_scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P).hex()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = stored.split('$')
        if scheme != 'scrypt':
            return False
        found = _scrypt(password, bytes.fromhex(salt), int(n), int(r), int(p))
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(found, bytes.fromhex(expected))


_dummy_hashes: dict[tuple, str] = {}


def _dummy_hash() -> str:
    """A hash of nothing anyone knows, made with the current cost: checked when the account does not exist, so that a wrong name and a wrong
    password take the same time."""
    key = (SCRYPT_N, SCRYPT_R, SCRYPT_P)
    if key not in _dummy_hashes:
        _dummy_hashes[key] = hash_password(secrets.token_urlsafe(16))
    return _dummy_hashes[key]


def password_problem(password, username: str = '') -> str | None:
    if not isinstance(password, str):
        return '密码要写成文字'
    if len(password) < MIN_PASSWORD:
        return f'密码至少 {MIN_PASSWORD} 个字符'
    if len(password) > MAX_PASSWORD:
        return f'密码最多 {MAX_PASSWORD} 个字符'
    if username and password.strip().lower() == username.strip().lower():
        return '密码不能和账号一样'
    return None


# sign-in limits

class LoginLimiter:
    """Five wrong passwords for one account lock it for a minute, then twice as long each time up to fifteen minutes; one client address may
    get 20 wrong passwords in ten minutes. An unknown account name is counted the same way, so the limit says nothing about which names
    exist. Kept in memory: restarting the service is not something a person at the sign-in page can do."""

    ACCOUNT_FREE, CLIENT_MAX, CLIENT_WINDOW, FORGET = 4, 20, 600, 3600

    def __init__(self, clock=time.monotonic):
        self._clock, self._lock = clock, threading.Lock()
        self._accounts: dict[str, list] = {}   # name -> [failures, locked until, last failure]
        self._clients: dict[str, deque] = {}

    def wait(self, name: str, client: str) -> int:
        """Seconds the person must wait before this attempt may be checked; 0 when it may."""
        now = self._clock()
        with self._lock:
            locked = self._accounts.get(name, [0, 0, 0])[1] - now
            times = self._clients.get(client, deque())
            while times and now - times[0] > self.CLIENT_WINDOW:
                times.popleft()
            over = self.CLIENT_WINDOW - (now - times[0]) if len(times) >= self.CLIENT_MAX else 0
        return max(0, math.ceil(max(locked, over)))

    def fail(self, name: str, client: str) -> None:
        now = self._clock()
        with self._lock:
            if len(self._accounts) > 10_000:   # a flood of made-up names does not grow memory without end
                self._accounts = {k: v for k, v in self._accounts.items() if now - v[2] < self.FORGET}
            record = self._accounts.setdefault(name, [0, 0, now])
            record[0] += 1
            record[2] = now
            if record[0] > self.ACCOUNT_FREE:
                record[1] = now + min(60 * 2 ** (record[0] - self.ACCOUNT_FREE - 1), 900)
            self._clients.setdefault(client, deque()).append(now)
            if len(self._clients) > 10_000:
                self._clients = {k: v for k, v in self._clients.items() if v and now - v[-1] < self.CLIENT_WINDOW}

    def clear(self, name: str) -> None:
        with self._lock:
            self._accounts.pop(name, None)


# users

def _public(row: sqlite3.Row | tuple) -> dict:
    user = dict(zip(_USER_KEYS, row))
    return {**user, 'disabled': bool(user['disabled']), 'must_change': bool(user['must_change'])}


def _log(conn, who: str, element: str, change: str, detail: dict | None = None) -> None:
    conn.execute('INSERT INTO log(time, who, element_id, change, before_json, after_json) VALUES (?, ?, ?, ?, NULL, ?)',
                 (_stamp(_now()), who[:64], element, change, json.dumps(detail, ensure_ascii=False) if detail else None))


def get_user(conn, user_id: int) -> dict | None:
    row = conn.execute(f'SELECT {_USER_COLUMNS} FROM user WHERE id = ?', (user_id,)).fetchone()
    return _public(row) if row else None


def list_users(conn) -> list[dict]:
    return [_public(r) for r in conn.execute(f'SELECT {_USER_COLUMNS} FROM user ORDER BY id')]


def user_count(conn) -> int:
    return conn.execute('SELECT COUNT(*) FROM user').fetchone()[0]


def _active_admins(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM user WHERE role = 'admin' AND disabled = 0").fetchone()[0]


def _name(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountError(f'要写{what}')
    value = value.strip()
    if len(value) > 64 or not value.isprintable():
        raise AccountError(f'{what}最多 64 个字，不能有换行和控制字符')
    return value


def create_user(conn, username, display_name, role, password, by: str, must_change: bool = True, provider: str = 'local') -> dict:
    username = _name(username, '账号')
    if not USERNAME.fullmatch(username):
        raise AccountError('账号只能用字母、数字、汉字和 . _ @ + -')
    display_name = _name(display_name or username, '显示名')
    if role not in ROLES:
        raise AccountError('角色要从 查看、建设、管理员 里选')
    if provider == 'local':
        problem = password_problem(password, username)
        if problem:
            raise AccountError(problem)
    try:
        cursor = conn.execute('INSERT INTO user(username, display_name, role, password_hash, must_change, created_at, provider) VALUES (?, ?, ?, ?, ?, ?, ?)',
                              (username, display_name, role, hash_password(password) if provider == 'local' else None, int(must_change), _stamp(_now()), provider))
    except sqlite3.IntegrityError:
        raise AccountError(f'已经有叫“{username}”的账号', 409) from None
    _log(conn, by, f'user:{cursor.lastrowid}', 'user_created', {'username': username, 'role': role})
    return get_user(conn, cursor.lastrowid)


def authenticate(conn, limiter: LoginLimiter, username, password, client: str) -> dict:
    """The user for a right name and password. A wrong name, a wrong password, a disabled account and an account without a password all
    answer the same words after the same work; too many tries answer how long to wait."""
    name = (username.strip().lower() if isinstance(username, str) else '')[:64]
    if not isinstance(password, str) or len(password) > MAX_PASSWORD:
        raise AccountError(GENERIC, 401)
    seconds = limiter.wait(name, client)
    if seconds:
        raise AccountError(f'试得太多了，请 {seconds} 秒后再试', 429)
    row = conn.execute(f'SELECT {_USER_COLUMNS}, password_hash FROM user WHERE username = ?', (name,)).fetchone()
    stored = row[-1] if row and row[-1] else None
    good = verify_password(password, stored or _dummy_hash())
    if row and good and stored and not row[4]:
        limiter.clear(name)
        _log(conn, row[1], f'user:{row[0]}', 'login')
        conn.execute('UPDATE user SET last_login_at = ? WHERE id = ?', (_stamp(_now()), row[0]))
        return _public(row[:-1])
    limiter.fail(name, client)
    _log(conn, name or '(空)', 'login', 'login_failed', {'client': client[:64]})
    raise AccountError(GENERIC, 401)


def change_password(conn, user: dict, current, new, keep_token: str | None = None) -> None:
    row = conn.execute('SELECT password_hash FROM user WHERE id = ?', (user['id'],)).fetchone()
    if not row or not row[0] or not isinstance(current, str) or not verify_password(current, row[0]):
        raise AccountError('现在的密码不对', 403)
    problem = password_problem(new, user['username'])
    if problem:
        raise AccountError(problem)
    conn.execute('UPDATE user SET password_hash = ?, must_change = 0 WHERE id = ?', (hash_password(new), user['id']))
    end_sessions(conn, user['id'], except_token=keep_token)
    _log(conn, user['username'], f'user:{user["id"]}', 'password_changed')


def _target(conn, user_id) -> dict:
    target = get_user(conn, user_id) if isinstance(user_id, int) and not isinstance(user_id, bool) else None
    if target is None:
        raise AccountError('没有这个账号', 404)
    return target


def set_role(conn, actor: dict, user_id, role) -> dict:
    target = _target(conn, user_id)
    if role not in ROLES:
        raise AccountError('角色要从 查看、建设、管理员 里选')
    if target['id'] == actor['id']:
        raise AccountError('不能改自己的角色，请另一位管理员来改')
    if target['role'] == 'admin' and role != 'admin' and not target['disabled'] and _active_admins(conn) <= 1:
        raise AccountError('至少要留一位启用的管理员')
    conn.execute('UPDATE user SET role = ? WHERE id = ?', (role, target['id']))
    _log(conn, actor['username'], f'user:{target["id"]}', 'role_changed', {'from': target['role'], 'to': role})
    return get_user(conn, target['id'])


def set_display_name(conn, actor: dict, user_id, display_name) -> dict:
    target = _target(conn, user_id)
    conn.execute('UPDATE user SET display_name = ? WHERE id = ?', (_name(display_name, '显示名'), target['id']))
    return get_user(conn, target['id'])


def set_disabled(conn, actor: dict, user_id, disabled) -> dict:
    target = _target(conn, user_id)
    if not isinstance(disabled, bool):
        raise AccountError('要写明停用还是启用（true 或 false）')
    if disabled and target['id'] == actor['id']:
        raise AccountError('不能停用自己')
    if disabled and target['role'] == 'admin' and not target['disabled'] and _active_admins(conn) <= 1:
        raise AccountError('至少要留一位启用的管理员')
    conn.execute('UPDATE user SET disabled = ? WHERE id = ?', (int(disabled), target['id']))
    if disabled:
        end_sessions(conn, target['id'])
        conn.execute('UPDATE api_token SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL', (_stamp(_now()), target['id']))
    _log(conn, actor['username'], f'user:{target["id"]}', 'user_disabled' if disabled else 'user_enabled')
    return get_user(conn, target['id'])


def reset_password(conn, actor_name: str, user_id: int, password, must_change: bool = True) -> dict:
    target = _target(conn, user_id)
    problem = password_problem(password, target['username'])
    if problem:
        raise AccountError(problem)
    conn.execute('UPDATE user SET password_hash = ?, must_change = ? WHERE id = ?', (hash_password(password), int(must_change), user_id))
    end_sessions(conn, user_id)
    _log(conn, actor_name, f'user:{user_id}', 'password_reset')
    return get_user(conn, user_id)


# sessions

def start_session(conn, user_id: int, now: datetime | None = None) -> str:
    now = now or _now()
    conn.execute('DELETE FROM session WHERE expires_at < ?', (_stamp(now),))
    token = secrets.token_urlsafe(32)   # 256 bits; a fresh one at every sign-in
    conn.execute('INSERT INTO session(token_hash, user_id, created_at, last_seen_at, expires_at) VALUES (?, ?, ?, ?, ?)',
                 (_digest(token), user_id, _stamp(now), _stamp(now), _stamp(now + ABSOLUTE)))
    return token


def session_user(conn, token: str | None, now: datetime | None = None) -> dict | None:
    """The user a session token belongs to, if it is still good: not idle for 8 hours, not older than 14 days, user not disabled."""
    if not token:
        return None
    now = now or _now()
    row = conn.execute(f'SELECT s.last_seen_at, s.expires_at, {_JOINED} FROM session s JOIN user u ON u.id = s.user_id WHERE s.token_hash = ?',
                       (_digest(token),)).fetchone()
    if row is None:
        return None
    seen, expires = datetime.fromisoformat(row[0]), datetime.fromisoformat(row[1])
    user = _public(row[2:])
    if user['disabled'] or now >= expires or now - seen >= IDLE:
        conn.execute('DELETE FROM session WHERE token_hash = ?', (_digest(token),))
        return None
    if now - seen >= TOUCH_EVERY:
        conn.execute('UPDATE session SET last_seen_at = ? WHERE token_hash = ?', (_stamp(now), _digest(token)))
    return user


def end_session(conn, token: str | None) -> None:
    if token:
        conn.execute('DELETE FROM session WHERE token_hash = ?', (_digest(token),))


def end_sessions(conn, user_id: int, except_token: str | None = None) -> None:
    conn.execute('DELETE FROM session WHERE user_id = ? AND token_hash != ?', (user_id, _digest(except_token) if except_token else ''))


# API tokens

TOKEN_PREFIX = 'otp_'


def create_token(conn, user: dict, label, now: datetime | None = None) -> tuple[dict, str]:
    """(the token's record, the token itself). The token is shown once; only its hash is kept."""
    label = _name(label, '用途说明')
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    cursor = conn.execute('INSERT INTO api_token(token_hash, user_id, label, created_at) VALUES (?, ?, ?, ?)', (_digest(token), user['id'], label, _stamp(now or _now())))
    _log(conn, user['username'], f'user:{user["id"]}', 'token_created', {'label': label})
    return {'id': cursor.lastrowid, 'label': label}, token


def token_user(conn, token: str | None, now: datetime | None = None) -> dict | None:
    """The owner of an API token, if it is not revoked and the owner is not disabled. The token has the owner's role, whatever it is now."""
    if not token or not token.startswith(TOKEN_PREFIX):
        return None
    now = now or _now()
    row = conn.execute(f'SELECT t.id, t.last_used_at, {_JOINED} FROM api_token t JOIN user u ON u.id = t.user_id '
                       'WHERE t.token_hash = ? AND t.revoked_at IS NULL AND u.disabled = 0', (_digest(token),)).fetchone()
    if row is None:
        return None
    if row[1] is None or now - datetime.fromisoformat(row[1]) >= TOUCH_EVERY:
        conn.execute('UPDATE api_token SET last_used_at = ? WHERE id = ?', (_stamp(now), row[0]))
    return _public(row[2:])


def list_tokens(conn, user_id: int) -> list[dict]:
    return [{'id': i, 'label': label, 'created_at': created, 'last_used_at': used, 'revoked': revoked is not None}
            for i, label, created, used, revoked in conn.execute('SELECT id, label, created_at, last_used_at, revoked_at FROM api_token WHERE user_id = ? ORDER BY id', (user_id,))]


def revoke_token(conn, user: dict, token_id) -> None:
    done = conn.execute('UPDATE api_token SET revoked_at = ? WHERE id = ? AND user_id = ? AND revoked_at IS NULL', (_stamp(_now()), token_id, user['id']))
    if not done.rowcount:
        raise AccountError('没有这个令牌', 404)


# on the host

def _prompt_password(name: str) -> str:
    while True:
        first = getpass.getpass(f'{name} 的密码（至少 {MIN_PASSWORD} 个字符）：')
        problem = password_problem(first, name)
        if problem:
            print(problem, file=sys.stderr)
        elif first == getpass.getpass('再输一次：'):
            return first
        else:
            print('两次不一样', file=sys.stderr)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Accounts of the workspace, managed on the machine that holds its data.')
    parser.add_argument('command', choices=('create-admin', 'reset-password', 'list'))
    parser.add_argument('username', nargs='?', help='the account (asked for when left out)')
    parser.add_argument('--data-dir', type=Path, help='the folder the service keeps its data in (default: the service default)')
    args = parser.parse_args(argv)
    from ontology_poc_generator.ontology_server import ROOT
    from ontology_poc_generator.workspace_store import open_workspace
    conn = open_workspace((args.data_dir or ROOT / 'output/ontology-runs') / 'workspace.sqlite')
    try:
        if args.command == 'list':
            for u in list_users(conn):
                print(f'{u["id"]:>3}  {u["username"]:<20} {u["role"]:<8} {"停用" if u["disabled"] else "启用"}  {u["display_name"]}')
            return 0
        name = args.username or input('账号：').strip()
        if args.command == 'create-admin':
            user = create_user(conn, name, name, 'admin', _prompt_password(name), 'host', must_change=False)
            print(f'已建好管理员“{user["username"]}”。')
        else:
            found = conn.execute('SELECT id FROM user WHERE username = ?', (name,)).fetchone()
            if not found:
                print(f'没有叫“{name}”的账号', file=sys.stderr)
                return 1
            reset_password(conn, 'host', found[0], _prompt_password(name), must_change=False)
            print('密码已重置，这个账号的登录都已退出。')
    except AccountError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
