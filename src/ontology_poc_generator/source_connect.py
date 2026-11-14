"""The outbound side of a data source: which addresses may be dialled, the PostgreSQL and MySQL connections (read-only sessions, TLS by default), the table list,
the privilege check and one table's rows as text. Nothing here knows about datasets or the workspace file.

The drivers (pg8000 for PostgreSQL, PyMySQL for MySQL) are pure Python and optional: `pip install "ontopoc[sources]"`. They are imported when a connection is
opened, so a service without them runs and the source page says which package is missing.

Passwords: every message that leaves this module (and so reaches a page, a refresh log or a log line) has the password taken out of it first (scrub); the
connection arguments are never put in a message or kept in an exception.

Two sentences per failure: `str(error)` is for an admin (it may say what the driver said, scrubbed), `error.public` is for everyone else and carries nothing of the
database's address, account or server text.
"""
from __future__ import annotations

import importlib
import ipaddress
import json
import re
import socket
import ssl
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

KINDS = {'postgresql': 'PostgreSQL', 'mysql': 'MySQL'}
DEFAULT_PORTS = {'postgresql': 5432, 'mysql': 3306}
TLS_MODES = ('required', 'none')
CONNECT_SECONDS = 10
LIST_SECONDS = 10   # the whole table list: the database stops it after this
STATEMENT_SECONDS = 60
MAX_TABLES = 500
MAX_PULL_ROWS = 500_000   # rows one pull reads into memory; more is refused, with the count, rather than cut
MAX_PULL_BYTES = 200 * 1024 * 1024   # the payload one pull reads (the text and bytes of the cells, counted as they arrive); more is refused
FETCH_ROWS = 2000
GENERIC = '连不上这个数据源，或读取时出了错。请让管理员看详情'

# Addresses a data source may never point at: a cloud's metadata service hands out the machine's credentials to whoever asks. localhost is allowed (this is a
# local tool and a database on the same machine is the common case), but the page says so.
_BLOCKED_NETWORKS = tuple(ipaddress.ip_network(n) for n in ('169.254.0.0/16', 'fe80::/10'))
_BLOCKED_ADDRESSES = frozenset(ipaddress.ip_address(a) for a in ('fd00:ec2::254', '100.100.100.200', '168.63.129.16', '192.0.0.192'))
_BLOCKED_NAMES = frozenset({'metadata', 'metadata.google.internal', 'metadata.goog', 'instance-data', 'instance-data.ec2.internal'})
_NAT64 = ipaddress.ip_network('64:ff9b::/96')
_COMPATIBLE = ipaddress.ip_network('::/96')


class SourceError(ValueError):
    """A source problem. str() is a sentence safe to show an admin and to log (no password, no connection string); `public` is the one for everyone else, which
    by default is the same sentence: raise with a `public` of your own when the sentence carries the driver's or the network's own words."""

    def __init__(self, message: str, public: str | None = None):
        super().__init__(message)
        self.public = message if public is None else public


def _embedded(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> list:
    """The address itself and any IPv4 address it carries: mapped (::ffff:a.b.c.d), compatible (::a.b.c.d), NAT64 (64:ff9b::a.b.c.d) and 6to4 (2002:aabb:ccdd::)."""
    if isinstance(address, ipaddress.IPv4Address):
        return [address]
    out = [address]
    if address.ipv4_mapped:
        out.append(address.ipv4_mapped)
    elif address in _NAT64 or (address in _COMPATIBLE and int(address) > 1):
        out.append(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF))
    elif address.sixtofour:
        out.append(address.sixtofour)
    return out


def _check_address(address) -> None:
    for each in _embedded(address):
        if each in _BLOCKED_ADDRESSES or any(each in net for net in _BLOCKED_NETWORKS):
            raise SourceError('这个地址是云服务商的内部地址（元数据服务，169.254 开头一类），机器用它领取自己的凭据，不能当数据源。换成数据库自己的地址')


def check_host(host: str) -> None:
    """The early check, with no lookup: an address written out, or a metadata name. connect() checks again on what the name resolves to."""
    name = host.strip().lower().rstrip('.')
    if name in _BLOCKED_NAMES or name.endswith('.metadata.google.internal'):
        raise SourceError('这个主机名是云服务商的内部服务（元数据服务），机器用它领取自己的凭据，不能当数据源。换成数据库自己的地址')
    try:
        literal = ipaddress.ip_address(name.strip('[]'))
    except ValueError:
        return
    _check_address(literal)


def _checked_addresses(host: str, port: int) -> list:
    """Every address the host looks up to, each checked (socket.gaierror when it looks up to nothing). A number such as 2852039166 or 0xa9fea9fe and a name such as
    169.254.169.254.nip.io only show what they are here."""
    found = socket.getaddrinfo(host.strip('[]'), port, type=socket.SOCK_STREAM)
    addresses = [ipaddress.ip_address(info[4][0].split('%')[0]) for info in found]
    for address in addresses:
        _check_address(address)
    return addresses


def screen_host(host: str, port: int) -> None:
    """The check when a source is saved: the written-out address and the metadata names (check_host), then what the host looks up to. A name that looks up to nothing is
    let through: it may not be in DNS yet, and the connection test says so when it is tried."""
    check_host(host)
    try:
        _checked_addresses(host, port)
    except socket.gaierror:
        return


def resolve(host: str, port: int) -> str:
    """The address to dial: the host looked up once and every answer checked, and that address (not the name) is what is connected to, so a name that answers
    differently the second time cannot move the connection onto a blocked address."""
    try:
        check_host(host)
        try:
            addresses = _checked_addresses(host, port)
        except socket.gaierror:
            raise SourceError('找不到这个主机名：名字解析不出地址') from None
    except SourceError as exc:
        raise SourceError(str(exc), GENERIC) from None
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
        raise SourceError(f"这台服务器还连不了 {KINDS[kind]}：少了连接它用的程序包 {package}。请运维人员在服务器上执行 pip install 'ontopoc[sources]'（或单独 pip install {package}），装好后重启服务") from None


def describe(exc: BaseException, password: str) -> str:
    """One sentence for a driver or network failure, for an admin. Where the driver gives a code that says what happened the sentence is ours; otherwise the
    driver's text, scrubbed."""
    if isinstance(exc, SourceError):
        return str(exc)
    cause = exc
    while cause.__cause__ is not None:   # pg8000 wraps the socket error in its own InterfaceError
        cause = cause.__cause__
    if isinstance(cause, ssl.SSLCertVerificationError):
        return f'TLS 证书验证没通过，连接已拒绝：{scrub(cause.verify_message or cause, password)}。用公认机构签的证书，或在服务所在的机器上把签发机构加进信任（SSL_CERT_FILE）'
    if isinstance(cause, ssl.SSLError):
        return f'TLS 握手失败：{scrub(cause, password)}'
    arg = exc.args[0] if exc.args else None
    if isinstance(arg, str) and 'refuses SSL' in arg:
        return '数据库不支持 TLS：让 DBA 开启它，或把这个数据源的加密改成“不用”（密码和数据会明文过网络）'
    if isinstance(arg, dict):   # pg8000: the server's error fields, C is the SQLSTATE and M the message
        code, message = str(arg.get('C', '')), str(arg.get('M', ''))
        if code in ('28P01', '28000'):
            return '用户名或密码不对，或这个账号不让从这台机器登录'
        if code == '3D000':
            return '没有这个数据库'
        if code == '57014':
            return f'查询超过时限，已被数据库停掉'
        return f'数据库说：{scrub(message, password)}'
    if isinstance(arg, int) and len(exc.args) > 1:   # PyMySQL: (error number, message)
        if arg == 1045:
            return '用户名或密码不对，或这个账号不让从这台机器登录'
        if arg == 1049:
            return '没有这个数据库'
        if arg in (2003, 2002, 2013):
            return '连不上：对方没有应答，或连接中途断了'
        if arg in (3024, 1317, 1969):
            return '查询超过时限，已被数据库停掉'
        return f'数据库说：{scrub(exc.args[1], password)}'
    if isinstance(cause, (TimeoutError, socket.timeout)):
        return f'连接超时或读取超时（连接 {CONNECT_SECONDS} 秒、读取 {STATEMENT_SECONDS} 秒没有应答）'
    if isinstance(cause, ConnectionRefusedError):
        return '连接被对方拒绝：地址或端口不对，或数据库没有在听'
    text = scrub(cause, password)
    if 'cryptography' in text:
        return '这个账号用 caching_sha2_password 认证，PyMySQL 在不加密的连接上需要 cryptography 包才能登录：把加密设成“必须”，或 pip install cryptography，或让 DBA 给这个账号改用 mysql_native_password'
    return f'{type(cause).__name__}：{text}'


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


def _weigh(row) -> int:
    """About how many bytes of payload a row carries: the text and bytes of its cells, a fixed few for the rest."""
    return 8 * len(row) + sum(len(v) if isinstance(v, (str, bytes, bytearray, memoryview)) else 16 for v in row)


class Connection:
    """What the rest of the service uses of a database: tables(), writes(), read(), close(). The two classes below are the real ones; a test brings its own."""

    def tables(self) -> list[dict]:
        """[{name, kind ('表' or '视图'), rows (the database's own estimate, None when it has none), approx (True), supported, note}], at most MAX_TABLES. A table whose
        schema or name has a dot or a quote in it is listed with supported False and cannot be read: its name cannot be told apart from another table's."""
        raise NotImplementedError

    def writes(self) -> tuple[bool, str]:
        """(whether this account can change data or structure, in words)."""
        raise NotImplementedError

    def read(self, table: str, limit: int) -> tuple[list[str], list[tuple]]:
        """(the column names, up to `limit` rows) of a table named in tables(); SourceError past MAX_PULL_BYTES."""
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class _Sql(Connection):
    """Shared by the two drivers: the cursor work. A subclass says how to list, estimate, quote, stream and check privileges."""

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

    def _listed(self) -> list[dict]:
        """[{'name': what the page shows, 'parts': what is quoted, 'kind': 'TABLE' | 'VIEW', 'rows': estimate or None}]"""
        raise NotImplementedError

    def _quoted(self, parts: tuple) -> str:
        raise NotImplementedError

    def _batches(self, sql: str):
        """(column names, an iterator of lists of rows): the rows as they come, never the whole result at once. Closing the iterator ends the statement."""
        raise NotImplementedError

    def _within(self, seconds: int) -> None:
        """The database's own time limit for the statements that follow."""
        raise NotImplementedError

    def tables(self) -> list[dict]:
        self._within(LIST_SECONDS)
        try:
            found = self._listed()[:MAX_TABLES]
        finally:
            self._within(STATEMENT_SECONDS)
        return [{'name': t['name'], 'kind': '视图' if t['kind'] == 'VIEW' else '表', 'rows': t['rows'], 'approx': True, 'supported': self._supported(t['parts']),
                 'note': None if self._supported(t['parts']) else '模式名或表名里有点或引号，分不清是哪张表，不支持读取'} for t in found]

    def _supported(self, parts: tuple) -> bool:
        return not any('.' in p or '"' in p or '`' in p for p in parts)

    def read(self, table: str, limit: int) -> tuple[list[str], list[tuple]]:
        found = next((t for t in self._listed() if t['name'] == table), None)   # only a name the database itself listed is ever put into SQL
        if found is None or not self._supported(found['parts']):
            raise SourceError(f'数据源里没有“{table}”这张表，或这个账号读不了它，或它的名字里有点或引号，不支持读取')
        columns, batches = self._batches(f'SELECT * FROM {self._quoted(found["parts"])} LIMIT {int(limit)}')
        rows, weight = [], 0
        try:
            for batch in batches:
                weight += sum(_weigh(r) for r in batch)
                if weight > MAX_PULL_BYTES:
                    raise SourceError(f'“{table}”超过约 {MAX_PULL_BYTES // 1024 // 1024} MB，一次读不完。在数据库里建一个只含需要的行和列的视图，再读那个视图')
                rows.extend(batch)
        finally:
            batches.close()
        return columns, rows

    def close(self) -> None:
        self.raw.close()


def _dial(address: str, port: int) -> socket.socket:
    """A connected socket to the address that was checked, with the read time limit as a last stop behind the database's own."""
    sock = socket.create_connection((address, port), CONNECT_SECONDS)
    sock.settimeout(STATEMENT_SECONDS + 5)
    return sock


def _tls_context() -> ssl.SSLContext:
    return ssl.create_default_context()   # certificate and host name are checked


class Postgres(_Sql):
    _SYSTEM = "('pg_catalog', 'information_schema')"

    @classmethod
    def open(cls, host: str, address: str, port: int, database: str, user: str, password: str, tls: str) -> 'Postgres':
        driver = _driver('pg8000.dbapi', 'pg8000', 'postgresql')
        sock = _dial(address, port)   # the checked address is dialled; the name is only what the certificate is checked against
        try:
            raw = driver.connect(host=host, port=port, database=database, user=user, password=password, sock=sock,
                                                                        ssl_context=_tls_context() if tls == 'required' else False, application_name='ontopoc')
        except BaseException:
            sock.close()
            raise
        raw.autocommit = True
        conn = cls(raw, password)
        conn._query('SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY')   # a write is refused by the server, whatever the account may do
        conn._within(STATEMENT_SECONDS)
        return conn

    def _within(self, seconds: int) -> None:
        self._query(f'SET statement_timeout = {seconds * 1000}')

    def _listed(self) -> list[dict]:
        rows = self._query(
            "SELECT t.table_schema, t.table_name, t.table_type, c.reltuples::bigint FROM information_schema.tables t "
            "LEFT JOIN pg_namespace n ON n.nspname = t.table_schema LEFT JOIN pg_class c ON c.relnamespace = n.oid AND c.relname = t.table_name "
            f"WHERE t.table_type IN ('BASE TABLE', 'VIEW') AND t.table_schema NOT IN {self._SYSTEM} AND t.table_schema NOT LIKE 'pg\\_%' ORDER BY 1, 2")[1]
        return [{'name': f'{schema}.{name}', 'parts': (schema, name), 'kind': 'VIEW' if kind == 'VIEW' else 'TABLE',
                 'rows': None if kind == 'VIEW' or estimate is None or estimate < 0 else int(estimate)} for schema, name, kind, estimate in rows]   # -1: never analysed

    def _quoted(self, parts: tuple) -> str:
        return '.'.join('"' + p.replace('"', '""') + '"' for p in parts)

    def _batches(self, sql: str):
        cursor = self.raw.cursor()
        cursor.execute('BEGIN READ ONLY')
        cursor.execute(f'DECLARE ontopoc_pull NO SCROLL CURSOR FOR {sql}')   # the server hands over rows a batch at a time: a wide table is stopped by the byte cap, not by memory
        cursor.execute(f'FETCH {FETCH_ROWS} FROM ontopoc_pull')
        columns = [d[0] for d in cursor.description]
        first = list(cursor.fetchall())

        def batches():
            try:
                batch = first
                while batch:
                    yield batch
                    cursor.execute(f'FETCH {FETCH_ROWS} FROM ontopoc_pull')
                    batch = list(cursor.fetchall())
            finally:
                cursor.execute('ROLLBACK')
                cursor.close()
        return columns, batches()

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
    def open(cls, host: str, address: str, port: int, database: str, user: str, password: str, tls: str) -> 'MySql':
        driver = _driver('pymysql', 'PyMySQL', 'mysql')
        sock = _dial(address, port)
        try:
            raw = driver.connect(host=host, port=port, database=database, user=user, password=password, charset='utf8mb4', connect_timeout=CONNECT_SECONDS,
                                 read_timeout=STATEMENT_SECONDS + 5, write_timeout=STATEMENT_SECONDS + 5, autocommit=True, defer_connect=True,
                                 **({'ssl': _tls_context()} if tls == 'required' else {'ssl_disabled': True}))
            raw.connect(sock)
        except BaseException:
            sock.close()
            raise
        conn = cls(raw, password)
        conn._cursors = importlib.import_module('pymysql.cursors')
        conn._query('SET SESSION TRANSACTION READ ONLY')
        conn._within(STATEMENT_SECONDS)
        return conn

    def _within(self, seconds: int) -> None:
        try:
            self._query(f'SET SESSION max_execution_time = {seconds * 1000}')   # MySQL 5.7.8 and later: the server stops a SELECT that runs longer
        except Exception:
            self._query(f'SET SESSION max_statement_time = {seconds}')   # MariaDB, in seconds; when neither exists the socket read time limit is what stops it

    def _listed(self) -> list[dict]:
        rows = self._query("SELECT table_name, table_type, table_rows FROM information_schema.tables WHERE table_schema = DATABASE() "
                           "AND table_type IN ('BASE TABLE', 'VIEW') ORDER BY 1")[1]
        return [{'name': str(name), 'parts': (str(name),), 'kind': 'VIEW' if kind == 'VIEW' else 'TABLE', 'rows': None if kind == 'VIEW' or estimate is None else int(estimate)}
                for name, kind, estimate in rows]

    def _quoted(self, parts: tuple) -> str:
        return '`' + parts[0].replace('`', '``') + '`'

    def _batches(self, sql: str):
        cursor = self.raw.cursor(self._cursors.SSCursor)   # streams: rows are read off the wire as they are asked for
        cursor.execute(sql)
        columns = [d[0] for d in cursor.description]

        def batches():
            try:
                while True:
                    batch = list(cursor.fetchmany(FETCH_ROWS))
                    if not batch:
                        return
                    yield batch
            finally:
                self.raw.close()   # an unfinished streamed result would be read to its end before the cursor closes: closing the connection is what stops it
        return columns, batches()

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


def connect(kind: str, host: str, port: int, database: str, user: str, password: str, tls: str = 'required') -> Connection:
    """An open, read-only connection; SourceError (a safe sentence, and a public one) for anything that stops it."""
    if kind not in OPENERS:
        raise SourceError(f'不认识的数据库类型“{kind}”，只有 PostgreSQL 和 MySQL')
    if tls not in TLS_MODES:
        raise SourceError('加密只能选“必须”或“不用”')
    address = resolve(host, port)
    try:
        return OPENERS[kind](host, address, port, database, user, password, tls)
    except SourceError:
        raise
    except Exception as exc:   # nothing of the driver's own exception travels on: its arguments can carry the password
        raise SourceError(describe(exc, password), GENERIC) from None
