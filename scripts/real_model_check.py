"""Real-model check of the team app, for the end of a round.

Starts the real service on a fresh data folder, builds the planted workspace the tests use (types, relations, the 已取消订单数 statistic and the
有效订单 view, each confirmed by a second builder), asks the model a fixed set of questions and compares every answer with the CSV rows themselves.
Then it uploads the 订单 table with every 状态码 shifted by one and checks that the same question is refused.

The question set is written once here and is not tuned on (a set the code is tuned on proves nothing). A miss (refused, or not answered) is
counted, never a wrong number: the run fails only when an answer gives a number the rows do not.

    hk run "OpenRouter" -- sh -c 'PYTHONPATH=src:. .venv/bin/python scripts/real_model_check.py --out /tmp/check'

The model comes from the environment (DEEPSEEK_API_KEY, or OPENROUTER_API_KEY for DeepSeek V4.1 Flash through OpenRouter; see gateway_from_env).
Writes report.json and report.md to --out.
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

PASSWORD = 'correct horse battery'
WAIT_SECONDS = 200   # a real model can take a minute; the tests' client waits 30 s


def judge(case: dict, status: int | None, body: dict | None) -> str:
    """'right', 'wrong', 'missed' or 'error' for one answer. case: {'expect': 'count' | 'sum' | 'groups' | 'refuse', 'truth': ...}."""
    if status != 200 or not isinstance(body, dict) or 'status' not in body:
        return 'error'
    if case['expect'] == 'refuse':
        return 'right' if body['status'] == 'refused' else 'wrong' if body['status'] == 'answered' else 'missed'
    if body['status'] != 'answered':
        return 'missed'
    answer = body.get('answer') or {}
    if case['expect'] == 'count':
        return 'right' if answer.get('total') == case['truth'] and 'measure' not in answer else 'wrong'
    if case['expect'] == 'sum':
        return 'right' if (answer.get('measure') or {}).get('value') == case['truth'] else 'wrong'
    groups = answer.get('groups') or []
    wanted = case['truth']
    return 'right' if len(groups) >= len(wanted) and all(g[0] == name and g[1] == value for g, (name, value) in zip(groups, wanted)) else 'wrong'


def truths() -> dict:
    """What each question's answer is, from the planted CSV rows (the 客户 table after the mended upload)."""
    from tests import test_workspace_store as planted
    from tests.test_object_relations import customers_mended
    orders = planted.planted_bundle()['sources']['订单']['records']
    names = {r['客户编号']: r['客户名称'] for r in csv.DictReader(io.StringIO(base64.b64decode(customers_mended()['content_base64']).decode('utf-8')))}
    total, cancelled = defaultdict(int), defaultdict(int)
    for r in orders:
        total[r['客户编号']] += int(r['金额'])
        cancelled[r['客户编号']] += r['状态码'] == '2'
    by_total = sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))
    lowest = sorted(total.items(), key=lambda kv: (kv[1], kv[0]))
    most_cancelled = sorted(cancelled.items(), key=lambda kv: (-kv[1], kv[0]))
    named = lambda pairs: [[names[k], v] for k, v in pairs]
    return {'cancelled': sum(r['状态码'] == '2' for r in orders), 'not_cancelled_sum': sum(int(r['金额']) for r in orders if r['状态码'] != '2'),
            'top1': named(by_total[:1]), 'top3': named(by_total[:3]), 'bottom1': named(lowest[:1]), 'bottom3': named(lowest[:3]),
            'most_cancelled': named(most_cancelled[:1])}


QUESTIONS = [   # (question, what kind of answer, which truth)
    ('已取消的订单有多少？', 'count', 'cancelled'),
    ('没取消的订单金额合计是多少？', 'sum', 'not_cancelled_sum'),
    ('哪个客户的订单金额合计最高？', 'groups', 'top1'),
    ('订单金额合计最高的三个客户是哪几个？', 'groups', 'top3'),
    ('哪个客户的订单金额合计最低？', 'groups', 'bottom1'),
    ('订单金额最少的是哪个客户？', 'groups', 'bottom1'),
    ('订单金额合计最低的三个客户是哪几个？', 'groups', 'bottom3'),
    ('已取消订单数最多的客户是哪个？', 'groups', 'most_cancelled'),
]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def build_workspace(ann, bob) -> None:
    """The planted workspace, put forward by Ann and confirmed by Bob. 客户 is keyed on 客户编号 (unique after the mended upload), so questions can walk
    订单属于客户; keyed on 客户编号 + 城市 the service refuses that walk and says why."""
    from tests.test_derived_properties import CANCELLED, COMMIT, CUSTOMER, ORDER, PRODUCT, RELATIONS, STOCK, TABLES, TICKET, customers_mended
    from tests.test_object_types import VALID

    def ok(result, what):
        status, body = result
        if status != 200:
            raise RuntimeError(f'{what}: {status} {body}')
        return body

    ok(ann.post('/api/workspace/datasets/upload', {'files': TABLES}), 'upload')
    ok(ann.post('/api/workspace/datasets/upload', {'files': [customers_mended()]}), 'upload 客户')
    customer = {**CUSTOMER, 'key': ['客户编号'], 'properties': [{'column': '客户名称'}, {'column': '城市'}, {'column': '客户等级'}]}
    types = (ORDER, customer, PRODUCT, STOCK, COMMIT, TICKET)
    for t in types:
        ok(ann.post('/api/workspace/types', t), t['english_name'])
    for t in types:
        for column in (('状态码',) if t['english_name'] == 'order' else ()) + (None,):
            shown = ok(bob.get(f'/api/workspace/types/{t["english_name"]}'), 'type')
            shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
            ok(bob.post('/api/workspace/types/confirm', {'id': t['english_name'], 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})}),
               f'confirm {t["english_name"]}')
    names = {t['english_name'] for t in types}
    for r in RELATIONS:
        if r['from'] in names and r['to'] in names:
            ok(ann.post('/api/workspace/relations', r), r['english_name'])
            detail = ok(bob.get(f'/api/workspace/relations/{r["english_name"]}'), 'relation')
            ok(bob.post('/api/workspace/queue/confirm', {'element': f'relation:{r["english_name"]}', 'version': detail['version'], 'seen': detail['check']['signature']}), 'confirm relation')
    ok(ann.post('/api/workspace/types/derived', CANCELLED), 'statistic')
    line = next(d for d in ok(bob.get('/api/workspace/types/customer/derived'), 'derived')['derived'] if d['id'] == CANCELLED['english_name'])
    ok(bob.post('/api/workspace/types/derived/confirm', {'type': 'customer', 'english_name': CANCELLED['english_name'], 'version': line['version'], 'seen': line['seen']}), 'confirm statistic')
    ok(ann.post('/api/workspace/types/views', VALID), 'view')
    view = next(v for v in ok(bob.get('/api/workspace/types/order/views'), 'views')['views'] if v['name'] == VALID['name'])
    ok(bob.post('/api/workspace/types/views/confirm', {'id': VALID['name'], 'version': view['version'], 'seen': view['seen']}), 'confirm view')


def ask(person, question: str) -> tuple[int | None, dict | None, float]:
    started = time.time()
    try:
        status, body = person.post('/api/workspace/ask', {'question': question})
    except (OSError, URLError) as exc:
        return None, {'error': repr(exc)}, round(time.time() - started, 1)
    return status, body, round(time.time() - started, 1)


def summary(body: dict | None) -> dict:
    if not isinstance(body, dict):
        return {}
    answer = body.get('answer') or {}
    return {'status': body.get('status'), 'path': body.get('path'), 'reason': body.get('reason') or body.get('error'),
            'answer': {k: (answer[k][:5] if k == 'groups' else answer[k]) for k in ('total', 'groups', 'measure', 'order', 'tied_beyond_top') if k in answer},
            'definitions': [d.get('name') for d in body.get('definitions') or []]}


def markdown(report: dict) -> str:
    counts = report['counts']
    lines = [f'# Real-model check {report["at"]}', '', f'Model: `{report["model"] or "?"}`. '
             f'Right {counts.get("right", 0)}, wrong {counts.get("wrong", 0)}, missed {counts.get("missed", 0)}, error {counts.get("error", 0)}.', '',
             '| Question | Verdict | Seconds | Got | Truth |', '|---|---|---|---|---|']
    for r in report['results']:
        got = r['got'].get('answer') or r['got'].get('reason') or ''
        lines.append(f'| {r["question"]} | {r["verdict"]} | {r["seconds"]} | {json.dumps(got, ensure_ascii=False)[:120]} | {json.dumps(r["truth"], ensure_ascii=False)[:80]} |')
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--out', required=True, help='folder for the data, the server log and the report (emptied first)')
    parser.add_argument('--repeat', type=int, default=1, help='ask each question this many times')
    args = parser.parse_args(argv)
    from ontology_poc_generator import accounts
    from ontology_poc_generator.ontology_server import gateway_from_env
    from ontology_poc_generator.workspace_store import open_workspace
    from tests import test_access
    from tests.test_access import Client
    from tests.test_object_types import shifted_orders_csv

    gateway = gateway_from_env()
    if gateway is None:
        print('No model key in the environment: run it inside hk run "OpenRouter" (or with DEEPSEEK_API_KEY).', file=sys.stderr)
        return 2
    out = Path(args.out)
    data = out / 'data'
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True)
    conn = open_workspace(data / 'workspace.sqlite')
    for name, display, role in (('root', '管理员', 'admin'), ('ann', 'Ann', 'builder'), ('bob', 'Bob', 'builder')):
        accounts.create_user(conn, name, display, role, PASSWORD, 'host', must_change=False)
    conn.close()

    port = free_port()
    base, origin = f'http://127.0.0.1:{port}', f'http://127.0.0.1:{port + 1}'
    opener = test_access.urlopen
    test_access.urlopen = lambda request, timeout=30: opener(request, timeout=WAIT_SECONDS)

    class Person(Client):
        def call(self, method, path, payload=None, origin_=None, headers=None, **_):
            return super().call(method, path, payload, origin=origin, headers=headers)

    log = open(out / 'server.log', 'w')
    server = subprocess.Popen([sys.executable, '-m', 'ontology_poc_generator.ontology_server', '--port', str(port), '--data-dir', str(data), '--origin', origin],
                              stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy())
    try:
        for _ in range(100):
            try:
                urlopen(base + '/api/auth/me', timeout=1)
                break
            except URLError as exc:
                if getattr(exc, 'code', None):
                    break
                time.sleep(0.1)
        ann, bob = Person(base), Person(base)
        for person, name in ((ann, 'ann'), (bob, 'bob')):
            status, body = person.login(name, PASSWORD)
            if status != 200:
                raise RuntimeError(f'sign-in {name}: {status} {body}')
        build_workspace(ann, bob)
        truth = truths()
        results = []
        for question, expect, key in QUESTIONS:
            for _ in range(args.repeat):
                status, body, seconds = ask(ann, question)
                case = {'expect': expect, 'truth': truth[key]}
                results.append({'question': question, 'verdict': judge(case, status, body), 'seconds': seconds, 'http': status, 'truth': truth[key], 'got': summary(body)})
        status, body = ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})
        if status != 200:
            raise RuntimeError(f'shifted upload: {status} {body}')
        status, body, seconds = ask(ann, QUESTIONS[0][0])
        results.append({'question': f'{QUESTIONS[0][0]}（状态码错位上传之后）', 'verdict': judge({'expect': 'refuse'}, status, body), 'seconds': seconds, 'http': status,
                        'truth': 'refused', 'got': summary(body)})
    finally:
        server.terminate()
        server.wait(timeout=10)
        log.close()
    counts = defaultdict(int)
    for r in results:
        counts[r['verdict']] += 1
    report = {'at': time.strftime('%Y-%m-%d %H:%M'), 'model': gateway.model, 'counts': dict(counts), 'results': results}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    (out / 'report.md').write_text(markdown(report), encoding='utf-8')
    print(markdown(report))
    return 1 if counts.get('wrong') else 0


if __name__ == '__main__':
    sys.exit(main())
