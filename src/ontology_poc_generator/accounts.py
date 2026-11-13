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
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROLES = ('viewer', 'builder', 'admin')
RANK = {role: i for i, role in enumerate(ROLES, 1)}
ROLE_LABEL = {'viewer': '查看', 'builder': '建设', 'admin': '管理员'}

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 3   # stored with each hash (OWASP's minimum for scrypt); a hash made with lower ones is made again at the next sign-in
HASHING_AT_ONCE, HASHING_WAIT = 3, 3.0   # one hash takes 32 MiB, so only this many run together; another waits this many seconds, then is told the service is busy
MIN_PASSWORD, MAX_PASSWORD = 12, 1024   # the cap keeps a huge "password" from being used to burn the host's CPU
IDLE, ABSOLUTE = timedelta(hours=8), timedelta(days=14)
MAX_SESSIONS = 10   # signed in at once per person
TOUCH_EVERY = timedelta(seconds=60)   # last-seen is written at most this often, not on every request
GENERIC = '账号或密码不对'
USERNAME = re.compile(r'[\w.@+-]{1,64}')


def fold(name: str) -> str:
    """An account name as it is stored and looked up: compatibility forms and case folded the same way everywhere (the Kelvin sign is a k)."""
    return unicodedata.normalize('NFKC', name).strip().casefold()

SCHEMA = '''
CREATE TABLE IF NOT EXISTS sign_in_limit (key TEXT PRIMARY KEY, failures INTEGER NOT NULL, since REAL NOT NULL, locked_until REAL NOT NULL, last REAL NOT NULL);
CREATE INDEX IF NOT EXISTS sign_in_limit_last ON sign_in_limit(last);
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('viewer', 'builder', 'admin')), password_hash TEXT, disabled INTEGER NOT NULL DEFAULT 0,
    must_change INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, last_login_at TEXT, provider TEXT NOT NULL DEFAULT 'local');
CREATE TABLE IF NOT EXISTS session (
    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES user(id), created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
    expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS setting (key TEXT PRIMARY KEY, value TEXT NOT NULL);
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


@contextmanager
def transaction(conn):
    conn.execute('BEGIN IMMEDIATE')
    try:
        yield
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec='seconds')


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# passwords

class Busy(AccountError):
    """Too many passwords are being hashed at once to take another now."""


_hashing = threading.BoundedSemaphore(HASHING_AT_ONCE)


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    if not _hashing.acquire(timeout=HASHING_WAIT):   # scrypt lets go of the GIL: unlimited parallel hashes would use all the memory before anyone is signed in
        raise Busy('服务现在很忙，请稍后再试', 503)
    try:
        return hashlib.scrypt(unicodedata.normalize('NFC', password).encode(), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=256 * n * r * p)
    finally:
        _hashing.release()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f'scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${_scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P).hex()}'


def _parts(stored: str) -> tuple[bytes, int, int, int, bytes] | None:
    try:
        scheme, n, r, p, salt, expected = stored.split('$')
        return (bytes.fromhex(salt), int(n), int(r), int(p), bytes.fromhex(expected)) if scheme == 'scrypt' else None
    except ValueError:
        return None


def verify_password(password: str, stored: str) -> bool:
    parts = _parts(stored)
    if parts is None:
        return False
    salt, n, r, p, expected = parts
    try:
        found = _scrypt(password, salt, n, r, p)
    except Busy:
        raise
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(found, expected)


def needs_rehash(stored: str) -> bool:
    """Whether a stored hash was made with less cost than the current one."""
    parts = _parts(stored)
    return parts is not None and parts[1:4] != (SCRYPT_N, SCRYPT_R, SCRYPT_P)


_dummy_hashes: dict[tuple, str] = {}


def dummy_hash() -> str:
    """A hash of nothing anyone knows, made with the current cost: checked when the account does not exist, so that a wrong name and a wrong
    password take the same time. Made once per cost; Gate makes it at start so the first stranger does not pay for it."""
    key = (SCRYPT_N, SCRYPT_R, SCRYPT_P)
    if key not in _dummy_hashes:
        _dummy_hashes[key] = hash_password(secrets.token_urlsafe(16))
    return _dummy_hashes[key]


COMMON_PASSWORDS = frozenset(('password1234', 'password12345', 'password123456', 'qwertyuiop12', 'qwertyuiop123', 'iloveyou1234', 'welcome12345',
                              'administrator', '123456789012', '1234567890123', '0123456789ab', 'letmein12345'))


def password_problem(password, username: str = '') -> str | None:
    if not isinstance(password, str):
        return '密码要写成文字'
    if len(password) < MIN_PASSWORD or len(password.strip()) < MIN_PASSWORD:
        return f'密码至少 {MIN_PASSWORD} 个字符，不算头尾的空格'
    if len(password) > MAX_PASSWORD:
        return f'密码最多 {MAX_PASSWORD} 个字符'
    if username and password.strip().lower() == username.strip().lower():
        return '密码不能和账号一样'
    if password.strip().lower() in COMMON_PASSWORDS or len(set(password)) == 1:
        return '这个密码太常见了，换一个'
    return None


# sign-in limits

class LoginLimiter:
    """Wrong passwords are counted three ways, in the workspace file: by account and address together (five tries, then a wait that doubles
    from a minute to fifteen), by account alone (a high ceiling, so guessing spread over many addresses still stops) and by address alone
    (20 in ten minutes). A try is counted when it starts and given back if the password turns out right, so a burst of parallel tries cannot
    all pass a check made before any of them was counted. In the file so that the host's reset-password can clear a lock. An unknown account
    name is counted the same way, so the limit says nothing about which names exist."""

    PAIR_FREE, ACCOUNT_CEILING, ACCOUNT_LOCK = 4, 50, 900
    CLIENT_MAX, CLIENT_WINDOW, FORGET = 20, 600, 3600

    def __init__(self, clock=time.time):
        self._clock = clock

    @staticmethod
    def _keys(name: str, client: str) -> tuple[str, str, str]:
        return f'pair:{name}|{client}', f'account:{name}', f'client:{client}'

    def _rows(self, conn, name: str, client: str, now: float) -> list[list]:
        """[failures, window start, locked until] of the pair, the account and the address; a row whose window is over counts as empty."""
        out = []
        for key, window in zip(self._keys(name, client), (self.FORGET, self.FORGET, self.CLIENT_WINDOW)):
            row = conn.execute('SELECT failures, since, locked_until FROM sign_in_limit WHERE key = ?', (key,)).fetchone()
            out.append([0, now, 0.0] if row is None or now - row[1] >= window else list(row))
        return out

    def _wait(self, rows: list[list], now: float) -> int:
        pair, account, client = rows
        over = client[1] + self.CLIENT_WINDOW - now if client[0] >= self.CLIENT_MAX else 0
        return max(0, math.ceil(max(pair[2] - now, account[2] - now, over)))

    def wait(self, conn, name: str, client: str) -> int:
        """Seconds the person must wait before a try may be checked; 0 when it may. Counts nothing."""
        now = self._clock()
        return self._wait(self._rows(conn, name, client, now), now)

    def begin(self, conn, name: str, client: str) -> int:
        """Seconds to wait (the try is refused and not counted), or 0: the try is allowed and counted as a failure until refund() says it was not."""
        now = self._clock()
        conn.execute('BEGIN IMMEDIATE')   # the check and the count are one step: nothing else counts between them
        try:
            conn.execute('DELETE FROM sign_in_limit WHERE last < ?', (now - self.FORGET,))
            rows = self._rows(conn, name, client, now)
            seconds = self._wait(rows, now)
            if not seconds:
                pair, account, client_row = rows
                pair[0] += 1
                if pair[0] > self.PAIR_FREE:
                    pair[2] = now + min(60 * 2 ** (pair[0] - self.PAIR_FREE - 1), 900)
                account[0] += 1
                if account[0] >= self.ACCOUNT_CEILING:
                    account[2] = now + self.ACCOUNT_LOCK
                client_row[0] += 1
                for key, row in zip(self._keys(name, client), rows):
                    conn.execute('INSERT OR REPLACE INTO sign_in_limit(key, failures, since, locked_until, last) VALUES (?, ?, ?, ?, ?)', (key, *row, now))
            conn.execute('COMMIT')
        except BaseException:
            conn.execute('ROLLBACK')
            raise
        return seconds

    def refund(self, conn, name: str, client: str) -> None:
        """The try that begin() counted was not a failure (the password was right, or it could not be checked). The pair starts clean; the account
        and the address each get that one try back and keep the failures of others."""
        pair, account, address = self._keys(name, client)
        conn.execute('BEGIN IMMEDIATE')
        try:
            conn.execute('DELETE FROM sign_in_limit WHERE key = ?', (pair,))
            conn.execute('UPDATE sign_in_limit SET failures = MAX(failures - 1, 0) WHERE key IN (?, ?)', (account, address))
            conn.execute('COMMIT')
        except BaseException:
            conn.execute('ROLLBACK')
            raise

    @staticmethod
    def forget(conn, name: str) -> None:
        """Clear every lock on an account (a new password was set for it)."""
        prefix = f'pair:{name}|'
        conn.execute('DELETE FROM sign_in_limit WHERE key = ? OR substr(key, 1, ?) = ?', (f'account:{name}', len(prefix), prefix))


# users

def _public(row: sqlite3.Row | tuple) -> dict:
    user = dict(zip(_USER_KEYS, row))
    return {**user, 'disabled': bool(user['disabled']), 'must_change': bool(user['must_change'])}


def _printable(text: str) -> str:
    return ''.join(c for c in text if c.isprintable())


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


MAX_DISPLAY = 40   # what a signature may be anywhere a name is kept (a client's answer, a confirmer)
RESERVED_NAMES = ('system', '本机', '未署名', 'host')   # signatures the service writes itself


def _name(value, what: str, limit: int = 64) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountError(f'要写{what}')
    value = value.strip()
    if len(value) > limit or not value.isprintable():
        raise AccountError(f'{what}最多 {limit} 个字，不能有换行和控制字符')
    return value


def _display_name(conn, value, owner: int | None) -> str:
    """A display name is what every signature shows, so it must name one person: not another's (case aside) and not one the service signs with."""
    name = _name(value, '显示名', MAX_DISPLAY)
    taken = [fold(r[0]) for r in conn.execute('SELECT display_name FROM user WHERE id IS NOT ?', (owner,))] + [fold(n) for n in RESERVED_NAMES]
    if fold(name) in taken:
        raise AccountError(f'“{name}”已经是别人的显示名，或是服务自己用的名字，换一个', 409)
    return name


def create_user(conn, username, display_name, role, password, by: str, must_change: bool = True, provider: str = 'local') -> dict:
    username = fold(_name(username, '账号'))
    if not USERNAME.fullmatch(username):
        raise AccountError('账号只能用字母、数字、汉字和 . _ @ + -')
    display_name = _display_name(conn, display_name or username, None)
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
    answer the same words after the same work; too many tries answer how long to wait. The try is counted before the password is checked."""
    name = fold(username)[:64] if isinstance(username, str) else ''
    client = client[:64]
    if not isinstance(password, str) or len(password) > MAX_PASSWORD:
        raise AccountError(GENERIC, 401)
    seconds = limiter.begin(conn, name, client)
    if seconds:
        raise AccountError(f'试得太多了，请 {seconds} 秒后再试', 429)
    try:
        row = conn.execute(f'SELECT {_USER_COLUMNS}, password_hash FROM user WHERE username = ?', (name,)).fetchone()
        stored = row[-1] if row and row[-1] else None
        good = verify_password(password, stored or dummy_hash())
    except Busy:
        limiter.refund(conn, name, client)   # nothing was checked, so nothing failed
        raise
    if row and good and stored and not row[4]:
        limiter.refund(conn, name, client)
        _log(conn, row[1], f'user:{row[0]}', 'login')
        conn.execute('UPDATE user SET last_login_at = ? WHERE id = ?', (_stamp(_now()), row[0]))
        if needs_rehash(stored):
            conn.execute('UPDATE user SET password_hash = ? WHERE id = ?', (hash_password(password), row[0]))
        return _public(row[:-1])
    _log(conn, '(sign-in)', 'login', 'login_failed', {'name': _printable(name), 'client': _printable(client)})   # what a stranger typed is data, not a signature
    raise AccountError(GENERIC, 401)


def change_password(conn, user: dict, current, new, keep_token: str | None = None, limiter: LoginLimiter | None = None, client: str = '') -> None:
    """The current password is always asked for, and wrong guesses are limited like sign-in. Other sessions end and every API token is revoked."""
    key = f'pw:{user["id"]}'   # a colon cannot be in an account name, so this never meets one
    if limiter:
        seconds = limiter.begin(conn, key, client[:64])
        if seconds:
            raise AccountError(f'试得太多了，请 {seconds} 秒后再试', 429)
    row = conn.execute('SELECT password_hash FROM user WHERE id = ?', (user['id'],)).fetchone()
    try:
        right = bool(row and row[0] and isinstance(current, str) and len(current) <= MAX_PASSWORD and verify_password(current, row[0]))
    except Busy:
        if limiter:
            limiter.refund(conn, key, client[:64])
        raise
    if not right:
        raise AccountError('现在的密码不对', 403)
    if limiter:
        limiter.refund(conn, key, client[:64])
    problem = password_problem(new, user['username'])
    if problem:
        raise AccountError(problem)
    hashed = hash_password(new)
    with transaction(conn):   # not the caller's: the count the limiter kept above must stay when this is refused
        conn.execute('UPDATE user SET password_hash = ?, must_change = 0 WHERE id = ?', (hashed, user['id']))
        end_sessions(conn, user['id'], except_token=keep_token)
        revoke_tokens(conn, user['id'])
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
    end_sessions(conn, target['id'])   # the person signs in again, and tokens are made again: nothing issued under the old role survives
    revoke_tokens(conn, target['id'])
    _log(conn, actor['username'], f'user:{target["id"]}', 'role_changed', {'from': target['role'], 'to': role})
    return get_user(conn, target['id'])


def set_display_name(conn, actor: dict, user_id, display_name) -> dict:
    target = _target(conn, user_id)
    name = _display_name(conn, display_name, target['id'])
    conn.execute('UPDATE user SET display_name = ? WHERE id = ?', (name, target['id']))
    _log(conn, actor['username'], f'user:{target["id"]}', 'display_name_changed', {'from': target['display_name'], 'to': name})   # past signatures keep the old name
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
        revoke_tokens(conn, target['id'])
    _log(conn, actor['username'], f'user:{target["id"]}', 'user_disabled' if disabled else 'user_enabled')
    return get_user(conn, target['id'])


def reset_password(conn, actor_name: str, user_id: int, password, must_change: bool = True) -> dict:
    target = _target(conn, user_id)
    problem = password_problem(password, target['username'])
    if problem:
        raise AccountError(problem)
    conn.execute('UPDATE user SET password_hash = ?, must_change = ? WHERE id = ?', (hash_password(password), int(must_change), user_id))
    end_sessions(conn, user_id)
    revoke_tokens(conn, user_id)
    LoginLimiter.forget(conn, fold(target['username']))   # a locked-out person who was given a new password is let in
    _log(conn, actor_name, f'user:{user_id}', 'password_reset')
    return get_user(conn, user_id)


# sessions

def start_session(conn, user_id: int, now: datetime | None = None) -> str:
    now = now or _now()
    conn.execute('DELETE FROM session WHERE expires_at < ?', (_stamp(now),))
    token = secrets.token_urlsafe(32)   # 256 bits; a fresh one at every sign-in
    conn.execute('INSERT INTO session(token_hash, user_id, created_at, last_seen_at, expires_at) VALUES (?, ?, ?, ?, ?)',
                 (_digest(token), user_id, _stamp(now), _stamp(now), _stamp(now + ABSOLUTE)))
    conn.execute('DELETE FROM session WHERE user_id = ? AND rowid NOT IN (SELECT rowid FROM session WHERE user_id = ? ORDER BY rowid DESC LIMIT ?)',
                 (user_id, user_id, MAX_SESSIONS))   # the newest few stay
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


# settings

def two_person(conn) -> dict:
    """{'enabled': the switch, 'builders': people who can confirm, 'active': whether a confirmer must differ from the proposer now}. The rule
    switches itself off while the workspace has one person who can confirm: two people cannot check each other when there is one."""
    row = conn.execute("SELECT value FROM setting WHERE key = 'two_person'").fetchone()
    enabled = row is None or row[0] != 'off'   # on unless someone turned it off
    builders = conn.execute("SELECT COUNT(*) FROM user WHERE disabled = 0 AND role IN ('builder', 'admin')").fetchone()[0]
    return {'enabled': enabled, 'builders': builders, 'active': enabled and builders >= 2}


def set_two_person(conn, enabled, by: str) -> dict:
    if not isinstance(enabled, bool):
        raise AccountError('two_person 要写 true 或 false')
    conn.execute("INSERT OR REPLACE INTO setting(key, value) VALUES ('two_person', ?)", ('on' if enabled else 'off',))
    _log(conn, by, 'setting:two_person', 'setting_changed', {'two_person': enabled})
    return two_person(conn)


# API tokens

TOKEN_PREFIX = 'otp_'


def revoke_tokens(conn, user_id: int) -> None:
    conn.execute('UPDATE api_token SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL', (_stamp(_now()), user_id))


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
            found = conn.execute('SELECT id FROM user WHERE username = ?', (fold(name),)).fetchone()
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
