"""The outbound side of a data source: which addresses may be dialled, the PostgreSQL and MySQL connections (read-only sessions), the table list, the
privilege check and one table's rows as text. Nothing here knows about datasets or the workspace file.

The drivers (pg8000 for PostgreSQL, PyMySQL for MySQL) are pure Python and optional: `pip install "ontopoc[sources]"`. They are imported when a connection is
opened, so a service without them runs and the source page says which package is missing.

Passwords: every message that leaves this module (and so reaches a page, a refresh log or a log line) has the password taken out of it first (scrub); the
connection arguments are never put in a message or kept in an exception. A driver error is reduced to a sentence of ours where the driver's code says what
went wrong, and scrubbed where it does not.
"""
from __future__ import annotations

import importlib
import ipaddress
import json
import re
import socket
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

KINDS = {'postgresql': 'PostgreSQL', 'mysql': 'MySQL'}
DEFAULT_PORTS = {'postgresql': 5432, 'mysql': 3306}
CONNECT_SECONDS = 10
STATEMENT_SECONDS = 60
MAX_TABLES = 500   # tables listed with a row count each (a count is one query per table)
MAX_PULL_ROWS = 500_000   # rows one pull reads into memory; more is refused, with the count, rather than cut

# Addresses a data source may never point at: a cloud's metadata service hands out the machine's credentials to whoever asks. localhost is allowed (this is a
# local tool and a database on the same machine is the common case), but the page says so.
_BLOCKED_NETWORKS = tuple(ipaddress.ip_network(n) for n in ('169.254.0.0/16', 'fe80::/10'))
_BLOCKED_ADDRESSES = frozenset(ipaddress.ip_address(a) for a in ('fd00:ec2::254', '100.100.100.200'))
_BLOCKED_NAMES = frozenset({'metadata', 'metadata.google.internal', 'metadata.goog', 'instance-data', 'instance-data.ec2.internal'})


class SourceError(ValueError):
    """A source problem, in a sentence that is safe to show and to log: it holds no password and no connection string."""


def _check_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address in _BLOCKED_ADDRESSES or any(address in net for net in _BLOCKED_NETWORKS):
        raise SourceError('这个地址是链路本地或云厂商的元数据地址，不能当数据源：它会交出这台机器自己的凭据')


def check_host(host: str) -> None:
    """The early check, with no lookup: an address written out, or a metadata name. connect() checks again on what the name resolves to."""
    name = host.strip().lower().rstrip('.')
    if name in _BLOCKED_NAMES or name.endswith('.metadata.google.internal'):
        raise SourceError('这个主机名是云厂商的元数据服务，不能当数据源：它会交出这台机器自己的凭据')
    try:
        literal = ipaddress.ip_address(name.strip('[]'))
    except ValueError:
        return
    _check_address(literal)


def resolve(host: str, port: int) -> str:
    """The address to dial: the host looked up once and every answer checked, and that address (not the name) is what is connected to, so a name that answers
    differently the second time cannot move the connection onto a blocked address."""
    check_host(host)
    try:
        found = socket.getaddrinfo(host.strip('[]'), port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise SourceError(f'找不到主机“{host}”：名字解析不出地址') from None
    addresses = [ipaddress.ip_address(info[4][0].split('%')[0]) for info in found]
    for address in addresses:
        _check_address(address)
    return str(min(addresses, key=lambda a: a.version))   # IPv4 first: a database published on 127.0.0.1 is not always on ::1


def scrub(text: object, *secrets: str) -> str:
    """The text with each secret taken out. A secret of three characters or more is replaced wherever it occurs; a shorter one only where it stands alone, so a
    one-letter password does not turn the whole message into stars."""
    out = str(text)
    for secret in secrets:
        if not secret:
            continue
        out = out.replace(secret, '***') if len(secret) >= 3 else re.sub(rf'(?<!\w){re.escape(secret)}(?!\w)', '***', out)
    return out


def _driver(module: str, package: str, kind: str):
    try:
        return importlib.import_module(module)
    except ImportError:
        raise SourceError(f'连 {KINDS[kind]} 要先装 {package}：pip install "ontopoc[sources]"（或 pip install {package}），装好后重启服务') from None


def describe(exc: BaseException, password: str) -> str:
    """One sentence for a driver or network failure. Where the driver gives a code that says what happened the sentence is ours; otherwise the driver's text, scrubbed."""
    if isinstance(exc, SourceError):
        return str(exc)
    arg = exc.args[0] if exc.args else None
    if isinstance(arg, dict):   # pg8000: the server's error fields, C is the SQLSTATE and M the message
        code, message = str(arg.get('C', '')), str(arg.get('M', ''))
        if code in ('28P01', '28000'):
            return '用户名或密码不对，或这个账号不让从这台机器登录'
        if code == '3D000':
            return '没有这个数据库'
        if code == '57014':
            return f'查询超过 {STATEMENT_SECONDS} 秒，已被数据库停掉'
        return f'数据库说：{scrub(message, password)}'
    if isinstance(arg, int) and len(exc.args) > 1:   # PyMySQL: (error number, message)
        if arg == 1045:
            return '用户名或密码不对，或这个账号不让从这台机器登录'
        if arg == 1049:
            return '没有这个数据库'
        if arg in (2003, 2002, 2013):
            return '连不上：对方没有应答，或连接中途断了'
        if arg == 3024 or arg == 1317:
            return f'查询超过 {STATEMENT_SECONDS} 秒，已被数据库停掉'
        return f'数据库说：{scrub(exc.args[1], password)}'
    cause = exc
    while cause.__cause__ is not None:   # pg8000 wraps the socket error in its own InterfaceError
        cause = cause.__cause__
    exc = cause if isinstance(cause, OSError) else exc
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return f'连接超时（{CONNECT_SECONDS} 秒没有应答）'
    if isinstance(exc, ConnectionRefusedError):
        return '连接被对方拒绝：地址或端口不对，或数据库没有在听'
    text = scrub(exc, password)
    if 'cryptography' in text:
        return '这个账号用 caching_sha2_password 认证，PyMySQL 需要 cryptography 包才能登录：pip install cryptography，或让 DBA 给这个账号改用 mysql_native_password'
    return f'{type(exc).__name__}：{text}'


def text_of(value) -> str | None:
    """One cell as the text the workspace stores. Dates and times as ISO text, decimals written out in full (never 1E+2), a timestamp with a zone as UTC, a
    boolean as true / false, JSON as JSON; the workspace infers each column's type from this text."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, float):
        return format(Decimal(repr(value)), 'f') if repr(value) not in ('nan', 'inf', '-inf') else repr(value)
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(sep=' ')
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def records_of(columns: list[str], rows: list[tuple]) -> tuple[list[dict], list[str]]:
    """(the rows as {column: text or None}, the columns left out). A column that holds bytes is left out whole and named: raw bytes have no text form that is
    not a guess, and a column dropped in silence is the failure this product refuses."""
    binary = {i for i in range(len(columns)) if any(isinstance(r[i], (bytes, bytearray, memoryview)) for r in rows)}
    keep = [(i, c) for i, c in enumerate(columns) if i not in binary]
    return [{c: text_of(r[i]) for i, c in keep} for r in rows], [columns[i] for i in sorted(binary)]


class Connection:
    """What the rest of the service uses of a database: tables(), writes(), read(), close(). The two classes below are the real ones; a test brings its own."""

    def tables(self) -> list[dict]:
        """[{name, kind ('表' or '视图'), rows (an exact count, None when it could not be counted), note}], at most MAX_TABLES."""
        raise NotImplementedError

    def writes(self) -> tuple[bool, str]:
        """(whether this account can change data or structure, in words)."""
        raise NotImplementedError

    def read(self, table: str, limit: int) -> tuple[list[str], list[tuple]]:
        """(the column names, up to `limit` rows) of a table named in tables()."""
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class _Sql(Connection):
    """Shared by the two drivers: the cursor work. A subclass says how to list, count, quote and check privileges."""

    def __init__(self, raw, password: str):
        self.raw, self.password = raw, password

    def _query(self, sql: str) -> tuple[list[str], list[tuple]]:
        cursor = self.raw.cursor()
        try:
            cursor.execute(sql)
            if not cursor.description:   # a statement with no result (SET): nothing to fetch, and pg8000 refuses to try
                return [], []
            return [d[0] for d in cursor.description], list(cursor.fetchall())
        finally:
            cursor.close()

    def _listed(self) -> list[tuple[str, str]]:
        raise NotImplementedError

    def _quoted(self, name: str) -> str:
        raise NotImplementedError

    def tables(self) -> list[dict]:
        out = []
        for name, kind in self._listed()[:MAX_TABLES]:
            try:
                rows, note = int(self._query(f'SELECT COUNT(*) FROM {self._quoted(name)}')[1][0][0]), None
            except Exception as exc:   # one table that cannot be counted (no right, too slow) is named, not a failure of the list
                rows, note = None, describe(exc, self.password)
            out.append({'name': name, 'kind': '视图' if kind == 'VIEW' else '表', 'rows': rows, 'note': note})
        return out

    def read(self, table: str, limit: int) -> tuple[list[str], list[tuple]]:
        if table not in {name for name, _ in self._listed()}:   # only a name the database itself listed is ever put into SQL
            raise SourceError(f'数据源里没有“{table}”这张表，或这个账号读不了它')
        return self._query(f'SELECT * FROM {self._quoted(table)} LIMIT {int(limit)}')

    def close(self) -> None:
        self.raw.close()


class Postgres(_Sql):
    _SYSTEM = "('pg_catalog', 'information_schema')"

    @classmethod
    def open(cls, address: str, port: int, database: str, user: str, password: str) -> 'Postgres':
        raw = _driver('pg8000.dbapi', 'pg8000', 'postgresql').connect(host=address, port=port, database=database, user=user, password=password,
                                                                    timeout=CONNECT_SECONDS, application_name='ontopoc')
        raw.autocommit = True
        conn = cls(raw, password)
        conn._query('SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY')   # a write is refused by the server, whatever the account may do
        conn._query(f'SET statement_timeout = {STATEMENT_SECONDS * 1000}')
        return conn

    def _listed(self) -> list[tuple[str, str]]:
        rows = self._query(f"SELECT table_schema, table_name, table_type FROM information_schema.tables WHERE table_type IN ('BASE TABLE', 'VIEW') "
                           f"AND table_schema NOT IN {self._SYSTEM} AND table_schema NOT LIKE 'pg\\_%' ORDER BY 1, 2")[1]
        return [(f'{schema}.{name}', kind) for schema, name, kind in rows]

    def _quoted(self, name: str) -> str:
        return '.'.join('"' + part.replace('"', '""') + '"' for part in name.split('.', 1))

    def writes(self) -> tuple[bool, str]:
        found = self._query(
            "SELECT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS super, "
            "EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind IN ('r', 'p') "
            f"AND n.nspname NOT IN {self._SYSTEM} AND n.nspname NOT LIKE 'pg\\_%' AND (has_table_privilege(c.oid, 'INSERT') OR has_table_privilege(c.oid, 'UPDATE') "
            "OR has_table_privilege(c.oid, 'DELETE') OR has_table_privilege(c.oid, 'TRUNCATE'))) AS tables, "
            f"EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspname NOT IN {self._SYSTEM} AND n.nspname NOT LIKE 'pg\\_%' AND has_schema_privilege(n.oid, 'CREATE')) AS schemas")[1][0]
        super_user, on_tables, on_schemas = (bool(v) for v in found)
        reasons = [r for r, on in (('是超级用户', super_user), ('能改某些表的数据', on_tables), ('能在某个模式里建表', on_schemas)) if on]
        return bool(reasons), '、'.join(reasons)


class MySql(_Sql):
    _WRITE = {'ALL PRIVILEGES', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'TRUNCATE', 'FILE', 'SUPER', 'GRANT OPTION'}

    @classmethod
    def open(cls, address: str, port: int, database: str, user: str, password: str) -> 'MySql':
        raw = _driver('pymysql', 'PyMySQL', 'mysql').connect(host=address, port=port, database=database, user=user, password=password, charset='utf8mb4',
                                                           connect_timeout=CONNECT_SECONDS, read_timeout=STATEMENT_SECONDS, write_timeout=STATEMENT_SECONDS, autocommit=True)
        conn = cls(raw, password)
        conn._query('SET SESSION TRANSACTION READ ONLY')
        return conn

    def _listed(self) -> list[tuple[str, str]]:
        rows = self._query("SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = DATABASE() "
                           "AND table_type IN ('BASE TABLE', 'VIEW') ORDER BY 1")[1]
        return [(str(name), kind) for name, kind in rows]

    def _quoted(self, name: str) -> str:
        return '`' + name.replace('`', '``') + '`'

    def writes(self) -> tuple[bool, str]:
        granted = set()
        for (line,) in self._query('SHOW GRANTS FOR CURRENT_USER()')[1]:
            found = re.match(r'GRANT (.+?) ON ', str(line))
            if found:
                granted |= {p.strip().upper() for p in found.group(1).split(',')}
            if 'WITH GRANT OPTION' in str(line):
                granted.add('GRANT OPTION')
        write = sorted(granted & self._WRITE)
        return bool(write), '、'.join(write)


OPENERS = {'postgresql': Postgres.open, 'mysql': MySql.open}   # a test replaces an entry with a function that returns its own Connection


def connect(kind: str, host: str, port: int, database: str, user: str, password: str) -> Connection:
    """An open, read-only connection; SourceError (a safe sentence) for anything that stops it."""
    if kind not in OPENERS:
        raise SourceError(f'不认识的数据库类型“{kind}”，只有 PostgreSQL 和 MySQL')
    address = resolve(host, port)
    try:
        return OPENERS[kind](address, port, database, user, password)
    except SourceError:
        raise
    except Exception as exc:   # nothing of the driver's own exception travels on: its arguments can carry the password
        raise SourceError(describe(exc, password)) from None
