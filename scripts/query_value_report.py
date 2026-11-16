"""What OntoPoc Query does that hand-written SQL does not, measured on the planted workspace. No model is used.

Starts the service on a throwaway folder, builds the planted workspace (as real_model_check does), then for each case runs
  - the SQL a person with database access would write, on the same rows loaded into SQLite, and
  - the OntoPoc Query text, through the service, as a named person,
and writes report.json and report.md to --out:
  1. everyday questions: the two give the same number (the query is not a new way to be wrong);
  2. traps: a row rule, a code that changed meaning, a join that doubles rows, a hidden column. SQL gives a number with no warning;
     the query gives the asker's number and says it was limited, or refuses and says why;
  3. size: the same questions as the JSON the model writes today, as OntoPoc Query, and as SQL (characters).

    PYTHONPATH=src:. .venv/bin/python scripts/query_value_report.py --out /tmp/query-value
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import csv
import io
import json
import sqlite3
import tempfile
import threading
from pathlib import Path


def rows_of(upload: dict) -> list[dict]:
    return list(csv.DictReader(io.StringIO(base64.b64decode(upload['content_base64']).decode('utf-8'))))


def sql_db(tables: dict[str, list[dict]]) -> sqlite3.Connection:
    db = sqlite3.connect(':memory:')
    for name, rows in tables.items():
        cols = list(rows[0])
        db.execute(f'CREATE TABLE {name} ({", ".join(cols)})')
        db.executemany(f'INSERT INTO {name} VALUES ({", ".join("?" * len(cols))})', [[r[c] for c in cols] for r in rows])
    return db


@contextlib.contextmanager
def service():
    from ontology_poc_generator import accounts, ontology_server
    from ontology_poc_generator.workspace_store import open_workspace
    from tests.test_access import GOOD
    with tempfile.TemporaryDirectory() as out:
        server = ontology_server.make_server(port=0, gateway=None, output_dir=Path(out))
        conn = open_workspace(Path(out) / 'workspace.sqlite')
        accounts.create_user(conn, 'root', '管理员', 'admin', GOOD, 'host', must_change=False)
        conn.close()
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}'
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


def people(base: str, *names, roles=None) -> dict:
    from tests.test_access import GOOD, Client
    admin = Client(base)
    admin.login('root')
    out = {'admin': admin}
    for name in names:
        admin.post('/api/users', {'username': name, 'display_name': name.title(), 'role': (roles or {}).get(name, 'builder'), 'password': 'first password 1'})
        person = Client(base)
        person.login(name, 'first password 1')
        person.post('/api/auth/password', {'current': 'first password 1', 'new': GOOD})
        out[name] = person
    return out


def ok(result, what: str) -> dict:
    """A setup step that must work: a refused one would make the comparison say something it did not test."""
    status, body = result
    if status != 200:
        raise RuntimeError(f'{what}: {status} {body}')
    return body


def said(body: dict) -> str:
    """One line for what the query gave back."""
    if 'error' in body:
        return f'拒绝（400）：{body["error"]}'
    if body.get('status') != 'answered':
        return f'拒绝：{body.get("reason")}'
    a = body['answer']
    number = a['measure']['value'] if 'measure' in a else a.get('groups', [])[:3] if a.get('groups') else a.get('total')
    limited = '；' + '、'.join(f'按行规则只读了你的行（{l["rule"]}）' for l in body['limited_by_rule']) if body.get('limited_by_rule') else ''
    return f'{json.dumps(number, ensure_ascii=False)}{limited}'


EVERYDAY = [   # (question, SQL, OntoPoc Query, how to read the answer)
    ('已取消的订单有多少？', "SELECT count(*) FROM 订单 WHERE 状态码 = '2'",
     "SELECT count(o) FROM (o:订单) WHERE o.状态码 = '已取消'", 'total'),
    ('没取消的订单金额合计？', "SELECT sum(金额) FROM 订单 WHERE 状态码 <> '2'",
     "SELECT sum(o.金额) FROM (o:订单) WHERE o.状态码 <> '已取消'", 'measure'),
    ('订单金额合计最高的三个客户？',
     'SELECT c.客户名称, sum(o.金额) AS 合计 FROM 订单 o JOIN 客户 c ON o.客户编号 = c.客户编号 GROUP BY c.客户名称 ORDER BY 合计 DESC LIMIT 3',
     'SELECT c.客户名称, sum(o.金额) AS 合计 FROM (o:订单)-[:订单属于客户]->(c:客户) GROUP BY c.客户名称 ORDER BY 合计 DESC LIMIT 3', 'groups'),
    ('每个客户等级各有多少订单？',
     'SELECT c.客户等级, count(*) AS 数量 FROM 订单 o JOIN 客户 c ON o.客户编号 = c.客户编号 GROUP BY c.客户等级 ORDER BY 数量 DESC',
     'SELECT c.客户等级, count(o) AS 数量 FROM (o:订单)-[:订单属于客户]->(c:客户) GROUP BY c.客户等级 ORDER BY 数量 DESC', 'groups'),
    ('售后工单按产品品类分，各有多少？',
     'SELECT p.品类, count(*) AS 数量 FROM 售后工单 t JOIN 订单 o ON t.订单号 = o.订单号 JOIN 产品 p ON o.产品编号 = p.产品编号 GROUP BY p.品类 ORDER BY 数量 DESC',
     'SELECT p.品类, count(t) AS 数量 FROM (t:售后工单)-[:工单属于订单]->(o:订单)-[:订单买的产品]->(p:产品) GROUP BY p.品类 ORDER BY 数量 DESC', 'groups'),
]


def answer_value(body: dict, kind: str):
    a = body.get('answer') or {}
    if kind == 'total':
        return a.get('total')
    if kind == 'measure':
        return (a.get('measure') or {}).get('value')
    return [[g[0], g[1]] for g in a.get('groups') or []]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    from scripts.real_model_check import build_workspace
    from tests import test_workspace_store as planted
    from tests.test_derived_properties import CUSTOMER, ORDER, RELATIONS, TABLES
    from tests.test_object_relations import customers_mended
    from tests.test_object_types import shifted_orders_csv

    sources = planted.planted_bundle()['sources']
    tables = {name: sources[name]['records'] for name in ('订单', '客户', '产品', '售后工单')}
    mended = {**tables, '客户': rows_of(customers_mended())}
    report = {'everyday': [], 'traps': [], 'size': []}

    def query(client, text, **params):
        return client.post('/api/workspace/query', {'text': text, **({'params': params} if params else {})})[1]

    with service() as base:
        team = people(base, 'ann', 'bob', 'vera', 'carl', roles={'vera': 'viewer'})
        build_workspace(team['ann'], team['bob'])
        admin, ann = team['admin'], team['ann']
        db = sql_db(mended)
        for question, sql, text, kind in EVERYDAY:
            got = query(ann, text)
            rows = db.execute(sql).fetchall()
            want = rows[0][0] if kind in ('total', 'measure') else [[r[0], r[1]] for r in rows]
            mine = answer_value(got, kind)
            report['everyday'].append({'question': question, 'sql': sql, 'query': text, 'sql_gives': want, 'query_gives': mine,
                                       'same': mine == want, 'stood_on': [d['name'] for d in got.get('definitions') or []]})


        text = 'SELECT count(o) FROM (o:订单) WHERE o.金额 > 20000'
        report['traps'].append({'case': '文字列当数字比：数据集的列存成文字（DIP 除主键外都是 text）', 'question': '金额超过 20000 的订单有多少？',
                                'sql': 'SELECT count(*) FROM 订单 WHERE 金额 > 20000', 'sql_gives': db.execute('SELECT count(*) FROM 订单 WHERE 金额 > 20000').fetchone()[0],
                                'query': text, 'query_gives': said(query(ann, text)),
                                'truth': f'{sum(int(r["金额"]) > 20000 for r in tables["订单"])} 张（SQL 写成 CAST(金额 AS INTEGER) > 20000 也能得到；不写就是每一行都“大于”）'})

        ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
        ok(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH001', 'user_ids': [ids['vera']]}]}), 'row rule')
        report['traps'].append({'case': '行规则：Vera 只能看客户 KH001 的订单', 'question': '一共有多少订单？',
                                'sql': 'SELECT count(*) FROM 订单', 'sql_gives': db.execute('SELECT count(*) FROM 订单').fetchone()[0],
                                'query': 'SELECT count(o) FROM (o:订单)', 'query_gives': said(query(team['vera'], 'SELECT count(o) FROM (o:订单)')),
                                'truth': f'Vera 能看的订单有 {sum(1 for r in tables["订单"] if r["客户编号"] == "KH001")} 张'})

        ok(admin.post('/api/workspace/column-access', {'type': 'order', 'column': '金额', 'visible_to': [ids['ann']]}), 'column access')
        report['traps'].append({'case': '隐藏的列：订单.金额 只给 Ann 看，Carl 来问', 'question': '订单金额合计？',
                                'sql': 'SELECT sum(金额) FROM 订单', 'sql_gives': db.execute('SELECT sum(金额) FROM 订单').fetchone()[0],
                                'query': 'SELECT sum(o.金额) FROM (o:订单)', 'query_gives': said(query(team['carl'], 'SELECT sum(o.金额) FROM (o:订单)')),
                                'truth': 'Carl 不该读到金额；对他来说这个属性不存在，和写错一个属性名的回答一样'})

        text = "SELECT count(o) FROM (o:订单) WHERE o.状态码 = '已取消'"
        before = query(admin, text)
        ok(admin.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]}), 'upload the shifted orders')
        shifted = sql_db({'订单': rows_of(shifted_orders_csv())})
        report['traps'].append({'case': '代码换了含义（管理员来问，行规则不限他）：新上传的订单表里 状态码 整体加了 1（2 现在是“生产中”）', 'question': '已取消的订单有多少？',
                                'sql': "SELECT count(*) FROM 订单 WHERE 状态码 = '2'", 'sql_gives': shifted.execute("SELECT count(*) FROM 订单 WHERE 状态码 = '2'").fetchone()[0],
                                'query': text, 'query_gives': said(query(admin, text)),
                                'truth': f'上传前查询答 {answer_value(before, "total")} 张；上传后“已取消”是代码 3，SQL 的 2 数的是生产中的订单'})

    with service() as base:   # 客户 as uploaded, KH012 twice
        team = people(base, 'ann', 'bob')
        ann, bob = team['ann'], team['bob']
        ann.post('/api/workspace/datasets/upload', {'files': TABLES})
        for t in (ORDER, CUSTOMER):
            ann.post('/api/workspace/types', t)
            for column in (('状态码',) if t is ORDER else ()) + (None,):
                shown = bob.get(f'/api/workspace/types/{t["english_name"]}')[1]
                shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
                bob.post('/api/workspace/types/confirm', {'id': t['english_name'], 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})
        ann.post('/api/workspace/relations', RELATIONS[0])
        detail = bob.get('/api/workspace/relations/order_customer')[1]
        confirm = bob.post('/api/workspace/queue/confirm', {'element': 'relation:order_customer', 'version': detail['version'], 'seen': detail['check']['signature']})[1]
        text = 'SELECT c.客户等级, sum(o.金额) AS 合计 FROM (o:订单)-[:订单属于客户]->(c:客户) GROUP BY c.客户等级'
        sql = 'SELECT sum(o.金额) FROM 订单 o JOIN 客户 c ON o.客户编号 = c.客户编号'
        truth = sum(int(r['金额']) for r in tables['订单'])
        report['traps'].append({'case': '会把行算两遍的连接：客户表里 KH012 出现了两次（两个城市）', 'question': '按客户等级的订单金额合计（全部加起来应等于订单总额）',
                                'sql': sql, 'sql_gives': sql_db(tables).execute(sql).fetchone()[0],
                                'query': text, 'query_gives': f'{said(query(ann, text))}（确认这条关系时：{confirm.get("error")}）',
                                'truth': f'订单总额 {truth}'})

    from ontology_poc_generator.ontopoc_query import to_text
    from scripts.real_model_check import QUESTIONS   # noqa: F401  (the question set the model is checked on)
    catalog = {'types': {'order': {'name': '订单', 'properties': ['订单号', '客户编号', '金额', '状态码']}, 'customer': {'name': '客户', 'properties': ['客户编号', '客户名称']}},
               'relations': {'order_customer': {'name': '订单属于客户', 'from': 'order', 'to': 'customer'}}}
    by_customer = [{'via': ['order_customer'], 'field': '客户名称'}]
    sized = [   # the real-model check's questions, in the JSON the model writes for them today
        ('已取消的订单有多少？', {'start': 'order', 'where': [{'field': '状态码', 'equals': '2'}], 'via': [], 'group_by': None, 'share': None, 'measure': None, 'top': None, 'order': None},
         "SELECT count(*) FROM 订单 WHERE 状态码 = '2'"),
        ('没取消的订单金额合计是多少？', {'start': 'order', 'where': [{'field': '状态码', 'not_equals': '2'}], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': '金额', 'op': 'sum'}, 'top': None, 'order': None},
         "SELECT sum(金额) FROM 订单 WHERE 状态码 <> '2'"),
        ('订单金额合计最高的三个客户是哪几个？', {'start': 'order', 'where': [], 'via': [], 'group_by': by_customer, 'share': None, 'measure': {'field': '金额', 'op': 'sum'}, 'top': 3, 'order': 'largest'},
         'SELECT c.客户名称, sum(o.金额) AS 合计 FROM 订单 o JOIN 客户 c ON o.客户编号 = c.客户编号 GROUP BY c.客户名称 ORDER BY 合计 DESC LIMIT 3'),
        ('订单金额合计最低的三个客户是哪几个？', {'start': 'order', 'where': [], 'via': [], 'group_by': by_customer, 'share': None, 'measure': {'field': '金额', 'op': 'sum'}, 'top': 3, 'order': 'smallest'},
         'SELECT c.客户名称, sum(o.金额) AS 合计 FROM 订单 o JOIN 客户 c ON o.客户编号 = c.客户编号 GROUP BY c.客户名称 ORDER BY 合计 ASC LIMIT 3'),
        ('已取消订单数最多的客户是哪个？', {'start': 'order', 'where': [{'field': '状态码', 'equals': '2'}], 'via': [], 'group_by': by_customer, 'share': None, 'measure': None, 'top': 1, 'order': 'largest'},
         "SELECT c.客户名称, count(*) AS 数量 FROM 订单 o JOIN 客户 c ON o.客户编号 = c.客户编号 WHERE o.状态码 = '2' GROUP BY c.客户名称 ORDER BY 数量 DESC LIMIT 1"),
    ]
    for question, structured, sql in sized:
        text = to_text(structured, catalog)
        report['size'].append({'question': question, 'json_chars': len(json.dumps(structured, ensure_ascii=False)), 'query_chars': len(' '.join(text.split())), 'sql_chars': len(sql), 'query': text})

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'report.md').write_text(markdown(report), encoding='utf-8')
    print(markdown(report))
    same = all(e['same'] for e in report['everyday'])
    return 0 if same else 1


def markdown(report: dict) -> str:
    cell = lambda v: str(v).replace('|', '\\|').replace('\n', ' ')
    lines = ['# OntoPoc Query vs hand-written SQL (planted workspace, no model)', '', '## 1. Everyday questions: the same number', '',
             '| Question | SQL gives | Query gives | Same | Stood on |', '|---|---|---|---|---|']
    for e in report['everyday']:
        lines.append(f'| {e["question"]} | {cell(e["sql_gives"])} | {cell(e["query_gives"])} | {"yes" if e["same"] else "**NO**"} | {"、".join(e["stood_on"])} |')
    lines += ['', '## 2. Traps: SQL answers without a warning', '']
    for t in report['traps']:
        lines += [f'### {t["case"]}', f'- Question: {t["question"]}', f'- SQL: `{t["sql"]}` → **{t["sql_gives"]}**',
                  f'- OntoPoc Query: `{" ".join(t["query"].split())}` → {t["query_gives"]}', f'- Truth: {t["truth"]}', '']
    lines += ['## 3. Size of what the model would write (characters)', '', '| Question | JSON today | OntoPoc Query | SQL |', '|---|---|---|---|']
    for s in report['size']:
        lines.append(f'| {s["question"]} | {s["json_chars"]} | {s["query_chars"]} | {s["sql_chars"]} |')
    total = lambda k: sum(s[k] for s in report['size'])
    lines.append(f'| **Total** | {total("json_chars")} | {total("query_chars")} | {total("sql_chars")} |')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    raise SystemExit(main())
