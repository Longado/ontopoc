"""Demo mode: a public demo site where a visitor clicks "Try the demo" and gets a guest account that can only read.

Guests are viewers with provider 'demo' and no password. They are limited per address (GUEST_PER_ADDRESS an hour) and in total (ONTOPOC_DEMO_MAX_GUESTS
live ones), and cleanup() removes the ones older than a day with everything keyed by them. `python -m ontology_poc_generator.demo seed --data-dir DIR`
builds the ready workspace the guests look at (no model key needed).
"""
from __future__ import annotations

import argparse
import base64
import http.cookiejar
import json
import os
import secrets
import shutil
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError

from ontology_poc_generator import accounts
from ontology_poc_generator.accounts import AccountError, transaction
from ontology_poc_generator.lang import tr

PROVIDER = 'demo'
GUEST_PER_ADDRESS = 5   # new guests one address may make in an hour
GUEST_AGE = timedelta(hours=24)
CLEANUP_EVERY = 3600   # seconds
MARKER = '.ontopoc-demo'
def sample_dir() -> Path:
    """docs/pilot/sample: beside the source in a checkout, or under the working folder in an installed copy (the image has it at /app/docs/pilot)."""
    for root in (Path(__file__).resolve().parents[2], Path.cwd()):
        if (root / 'docs' / 'pilot' / 'sample' / 'orders.csv').is_file():
            return root / 'docs' / 'pilot' / 'sample'
    raise SystemExit('docs/pilot/sample was not found: run the seed from the repository folder')

SCHEMA = 'CREATE TABLE IF NOT EXISTS demo_guest (user_id INTEGER PRIMARY KEY, client TEXT NOT NULL, at REAL NOT NULL)'


def max_guests() -> int:
    try:
        return int(os.environ.get('ONTOPOC_DEMO_MAX_GUESTS', '300'))
    except ValueError:
        return 300


def not_in_demo() -> str:
    return tr('演示里不能做这个', 'Not in the demo')


def is_guest(user: dict | None) -> bool:
    return bool(user) and user.get('provider') == PROVIDER


def create_guest(conn, client: str, now: float | None = None) -> dict:
    """A new read-only guest for this address, or AccountError 429 when the address or the whole demo has had enough."""
    now = time.time() if now is None else now
    conn.execute(SCHEMA)
    client = client[:64]
    with transaction(conn):
        recent = conn.execute('SELECT COUNT(*) FROM demo_guest WHERE client = ? AND at > ?', (client, now - 3600)).fetchone()[0]
        if recent >= GUEST_PER_ADDRESS:
            raise AccountError(tr(f'这个地址一小时内最多能开 {GUEST_PER_ADDRESS} 个访客账号，请稍后再试', f'This address can open at most {GUEST_PER_ADDRESS} guest accounts an hour. Try again later'), 429)
        live = conn.execute('SELECT COUNT(*) FROM user WHERE provider = ?', (PROVIDER,)).fetchone()[0]
        if live >= max_guests():
            raise AccountError(tr('演示现在人太多了，请稍后再来', 'The demo is full right now. Come back a little later'), 429)
        user = None
        for _ in range(20):
            digits = f'{secrets.randbelow(10000):04d}'
            try:
                user = accounts.create_user(conn, f'guest-{secrets.token_hex(4)}', tr(f'访客 {digits}', f'Guest {digits}'), 'viewer', None, 'demo',
                                            must_change=False, provider=PROVIDER)
                break
            except AccountError as exc:
                if exc.status != 409:
                    raise
        if user is None:
            raise AccountError(tr('演示现在人太多了，请稍后再来', 'The demo is full right now. Come back a little later'), 429)
        conn.execute('INSERT INTO demo_guest(user_id, client, at) VALUES (?, ?, ?)', (user['id'], client, now))
    return user


def cleanup(conn, now: datetime | float | None = None) -> int:
    """Delete guests older than GUEST_AGE and everything keyed by them; returns how many guests went."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif not isinstance(now, datetime):
        now = datetime.fromtimestamp(now, timezone.utc)
    cutoff = (now - GUEST_AGE).isoformat(timespec='seconds')
    conn.execute(SCHEMA)
    with transaction(conn):
        ids = [r[0] for r in conn.execute('SELECT id FROM user WHERE provider = ? AND created_at < ?', (PROVIDER, cutoff))]
        for uid in ids:
            tokens = [r[0] for r in conn.execute('SELECT id FROM api_token WHERE user_id = ?', (uid,))]
            for (table,) in (('session',), ('api_token',)):
                conn.execute(f'DELETE FROM {table} WHERE user_id = ?', (uid,))
            for table in ('notice', 'qa_question', 'assistant_turn'):
                conn.execute(f'DELETE FROM {table} WHERE user_id = ?', (uid,))
            keys = [f'user:{uid}'] + [f'token:{t}' for t in tokens]
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ask_budget'").fetchone():
                conn.executemany('DELETE FROM ask_budget WHERE who = ?', [(k,) for k in keys])
            conn.execute('DELETE FROM log WHERE user_id = ? OR element_id = ?', (uid, f'user:{uid}'))
            conn.execute('DELETE FROM demo_guest WHERE user_id = ?', (uid,))
            conn.execute('DELETE FROM user WHERE id = ?', (uid,))
        conn.execute('DELETE FROM demo_guest WHERE user_id NOT IN (SELECT id FROM user)')
    return len(ids)


def cleanup_loop(open_conn, stop: threading.Event, every: float = CLEANUP_EVERY) -> None:
    """Run cleanup now and then every hour until stop is set."""
    while not stop.is_set():
        try:
            conn = open_conn()
            try:
                cleanup(conn)
            finally:
                conn.close()
        except Exception as exc:   # the demo keeps serving; the next round tries again
            print(f'demo cleanup failed: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
        stop.wait(every)


# seed

class _Client:
    def __init__(self, base: str, username: str, password: str):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        status, body = self.req('POST', '/api/auth/login', {'username': username, 'password': password})
        if status != 200:
            raise RuntimeError(f'sign-in of {username} failed: {body}')

    def req(self, method: str, path: str, body=None):
        request = urllib.request.Request(self.base + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json', 'Origin': self.base, 'Accept-Language': 'en'})
        try:
            with self.opener.open(request) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def must(self, method: str, path: str, body=None) -> dict:
        status, payload = self.req(method, path, body)
        if status != 200:
            raise RuntimeError(f'{method} {path} -> {status}: {json.dumps(payload, ensure_ascii=False)[:300]}')
        return payload


def _password() -> str:
    return secrets.token_urlsafe(18)


def _confirm(builder: _Client, type_id: str, column: str | None = None) -> None:
    t = builder.must('GET', f'/api/workspace/types/{type_id}')
    node = next(p for p in t['properties'] if p['column'] == column)['meanings'] if column else t
    body = {'id': type_id, 'version': node['version'], 'seen': node['seen']}
    builder.must('POST', '/api/workspace/types/confirm', {**body, 'column': column} if column else body)


def seed(data_dir: Path, admin_name: str = 'demo-admin', force_fresh: bool = False) -> dict:
    """Builds the demo workspace in data_dir and returns {'admin': name, 'password': password, 'data_dir': path}."""
    from ontology_poc_generator.ontology_server import make_server
    from ontology_poc_generator.workspace_store import open_workspace
    data_dir = Path(data_dir)
    if force_fresh and data_dir.exists() and any(data_dir.iterdir()):
        if not (data_dir / MARKER).is_file():
            raise SystemExit(f'{data_dir} was not made by this seed (no {MARKER} file in it), so --force-fresh will not wipe it')
        for child in data_dir.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    data_dir.mkdir(parents=True, exist_ok=True)
    db = data_dir / 'workspace.sqlite'
    conn = open_workspace(db)
    try:
        if accounts.user_count(conn):
            raise SystemExit(f'{data_dir} already has accounts; seed only builds a fresh demo (use --force-fresh to start over in a demo folder)')
        admin_pw, builder_pw = _password(), _password()
        accounts.create_user(conn, admin_name, admin_name, 'admin', admin_pw, 'demo-seed', must_change=False)
        accounts.create_user(conn, 'demo-builder', 'Demo builder', 'builder', builder_pw, 'demo-seed', must_change=False)
    finally:
        conn.close()
    (data_dir / MARKER).write_text('made by ontopoc.demo seed\n')
    server = make_server(port=0, gateway=None, output_dir=data_dir)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    try:
        base = f'http://127.0.0.1:{server.server_port}'
        admin, builder = _Client(base, admin_name, admin_pw), _Client(base, 'demo-builder', builder_pw)
        sample = sample_dir()
        files = [{'filename': n, 'content_base64': base64.b64encode((sample / n).read_bytes()).decode()} for n in ('orders.csv', 'customers.csv')]
        admin.must('POST', '/api/workspace/datasets/upload', {'files': files})
        meanings = [{'value': v, 'label': l} for v, l in (('0', 'New'), ('1', 'Paid'), ('2', 'Shipped'), ('3', 'Delivered'), ('4', 'Cancelled'), ('5', 'Refunded'))]
        admin.must('POST', '/api/workspace/types', {'english_name': 'order', 'name': 'Order', 'dataset': 'orders', 'key': ['order_id'],
                   'properties': [{'column': c} for c in ('order_id', 'customer_id', 'order_date', 'amount')] + [{'column': 'status_code', 'enum': True}],
                   'enums': {'status_code': meanings}})
        _confirm(builder, 'order', 'status_code')
        _confirm(builder, 'order')
        admin.must('POST', '/api/workspace/types/views', {'name': 'Valid orders', 'type': 'order',
                   'filters': [{'column': 'status_code', 'op': 'is_not', 'label': l} for l in ('New', 'Cancelled', 'Refunded')]})
        view = next(v for v in builder.must('GET', '/api/workspace/types/order/views')['views'] if v['name'] == 'Valid orders')
        builder.must('POST', '/api/workspace/types/views/confirm', {'id': 'Valid orders', 'version': view['version'], 'seen': view['seen']})
        admin.must('POST', '/api/workspace/types', {'english_name': 'customer', 'name': 'Customer', 'dataset': 'customers', 'key': ['customer_id'],
                   'properties': [{'column': c} for c in ('customer_id', 'name', 'city', 'tier')]})
        # Customer stays unconfirmed on purpose: a question about customers is refused with the reason, which is what the demo shows
        types = [t['id'] for t in admin.must('GET', '/api/workspace/types')['types']]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    conn = open_workspace(db)
    try:   # the builder only confirmed: nobody signs in as them afterwards
        accounts.set_disabled(conn, accounts.get_user(conn, 1), 2, True)
    finally:
        conn.close()
    return {'admin': admin_name, 'password': admin_pw, 'data_dir': str(data_dir), 'types': types}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Demo workspace tools.')
    sub = parser.add_subparsers(dest='command', required=True)
    s = sub.add_parser('seed', help='build a ready demo workspace from docs/pilot/sample (no model key needed)')
    s.add_argument('--data-dir', type=Path, required=True)
    s.add_argument('--admin-name', default='demo-admin')
    s.add_argument('--force-fresh', action='store_true', help='wipe the folder first, only when an earlier seed made it')
    args = parser.parse_args(argv)
    result = seed(args.data_dir, args.admin_name, args.force_fresh)
    print(f'Demo workspace built in {result["data_dir"]} (datasets orders, customers; types {", ".join(result["types"])}).')
    print(f'Admin account: {result["admin"]}')
    print(f'Admin password (shown once, store it now): {result["password"]}')
    print(f'Serve it:  ONTOPOC_DEMO=1 python -m ontology_poc_generator.ontology_server --demo --data-dir {result["data_dir"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
