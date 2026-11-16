"""What an outside agent may read, and the skill folder that carries the same definitions.

Three things come out of the confirmed definitions, always as the person the request signs in as (a person's session for the page, a token's owner for an MCP
server): the definitions themselves (`definitions`), what is not confirmed and so must not be relied on (`unconfirmed`), and the value of a confirmed derived
property for the objects that person may read (`read_derived`). Asking a question goes through the existing Q&A (workspace_questions.ask), which refuses rather
than guesses; there is no second answerer here.

Nothing unconfirmed is in `definitions` or in the skill folder: both are read from workspace_questions.scope, the same set the Q&A may use. A code column a builder
marked "don't send values" gives no meanings, because an outside agent is a model. No count of the whole data is in either (a row-limited person would otherwise
read it).
"""
from __future__ import annotations

from datetime import date
import io
import json
from pathlib import Path
import zipfile

from ontology_poc_generator.caliber import line_of
from ontology_poc_generator.derived_properties import derived_id, derived_visible, describe as describe_derived, evaluate
from ontology_poc_generator.explorer import _load, _object_key, whole_page
from ontology_poc_generator.object_types import OBJECT_PAGE, TypeRefused, element_row, type_id
from ontology_poc_generator.object_views import describe as describe_view
from ontology_poc_generator.type_access import hidden_values
from ontology_poc_generator.workspace_questions import _definition_line, _may_see, scope
from ontology_poc_generator.workspace_store import _canonical

SKILL_NAME = 'ontopoc-definitions'
REFUSAL_RULES = [
    '只按这里列出的、已经确认的定义回答。定义里没有的东西，不要猜。',
    '问到的对象类型、关系、视图或派生属性不在这里：回答“这个还没有确认的定义”，不要用常识或字面意思补一个；可以说一句让谁去确认（见 list_unconfirmed）。',
    '代码列（例如 状态码）只用这里写出的含义。取值没有写含义，或者含义不在这里：不解释它，不从取值的大小或排列推测含义。',
    '数字一定带上口径：它按哪些确认的定义算出（视图的条件、派生属性的算式）。口径里有任何一条不在这里，就不要报这个数。',
    '定义被标成“需要再看”或还没确认时，它背后的数据可能已经变了：不要用它回答，告诉人它现在不是已确认的状态。',
    '这里没有数据行，也没有全部数据的行数。要数字，先用 ontopoc_query 写本体查询（不调用模型），写不出来再用 ask；要某个对象的派生属性的值，用 read_derived_property。被拒绝就把拒绝的原因原样转告。',
]


# --- the definitions ----------------------------------------------------------------------------------------------------------------------------------

def _stamp(conn, element_id: str) -> dict:
    line = line_of(conn, element_id)
    return {'confirmed_by': line['by'], 'confirmed_on': line['on']}


def definitions(conn, user: dict | None) -> dict:
    """The confirmed definitions this person may see: {'types', 'relations', 'views', 'derived', 'rules'}. Nothing that is not confirmed, no row, no count of the data."""
    sc = scope(conn, user)
    types = []
    for name, t in sc['types'].items():
        content = t['content']
        hidden = hidden_values(conn, type_id(name))
        meanings = {column: {'values': m['labels'], **_stamp(conn, m['row']['element_id'])} for column, m in sc['meanings'].get(name, {}).items() if column not in hidden}
        types.append({'id': name, 'name': content['name'], 'description': content['description'], 'dataset': content['dataset'], 'key': content['key'],
                      'properties': [{'column': p['column'], 'name': p['name'], 'type': p['type'], 'code': p['enum'] and p['column'] in meanings} for p in content['properties']],
                      'meanings': meanings, **_stamp(conn, t['row']['element_id'])})
    relations = [{'id': name, 'name': r['content']['name'], 'from': r['content']['from'], 'to': r['content']['to'], 'cardinality': r['content']['cardinality'],
                  'from_column': r['content']['from_column'], 'to_column': r['content']['to_column'], **_stamp(conn, r['row']['element_id'])} for name, r in sc['relations'].items()]
    views = [{'id': name, 'name': name, 'type': v['content']['type'], 'says': describe_view(v['content'], sc['types'][v['content']['type']]['content']['name']),
              'line': line_of(conn, v['row']['element_id'])['line'], **_stamp(conn, v['row']['element_id'])} for name, v in sc['views'].items()]
    derived = [{'id': d['content']['english_name'], 'name': d['content']['name'], 'type': d['content']['type'], 'kind': d['content']['kind'], 'output_type': d['content']['output_type'],
                'says': describe_derived(conn, d['content']), **_stamp(conn, element_id)} for element_id, d in sc['derived'].items()]
    # one that names a column the owner keeps from models is listed, but not the sentence that spells out that column's meaning (its meanings are left out above too)
    derived += [{'id': d['content']['english_name'], 'name': d['content']['name'], 'type': d['content']['type'], 'kind': d['content']['kind'], 'output_type': d['content']['output_type'],
                 'says': None, **_stamp(conn, element_id)} for element_id, d in sc['derived_kept_back'].items()]
    return {'types': types, 'relations': relations, 'views': views, 'derived': derived, 'rules': REFUSAL_RULES}


def unconfirmed(conn, user: dict | None) -> dict:
    """What this person may see that is not confirmed (proposed, checked, needs another look, sent back), each with its state, the reason and who could confirm it: what an
    agent must not answer from. A viewer sees none (they see only confirmed things)."""
    out = []
    if user is None or user['role'] != 'viewer':
        for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE state != 'confirmed' AND (element_id LIKE 'objtype:%' OR element_id LIKE 'enum:%' OR element_id LIKE 'relation:%' "
                                          "OR element_id LIKE 'objview:%' OR element_id LIKE 'derived:%') ORDER BY element_id").fetchall():
            if _may_see(conn, user, element_id):
                out.append(_definition_line(conn, element_row(conn, element_id), user))
    return {'unconfirmed': out, 'note': '这些定义现在不是“已确认”：不要拿它们回答问题，也不要把里面的数字或含义当成已经说定的。'}


def read_derived(conn, user: dict | None, type_name, name, key=None, page=1) -> dict:
    """The value of a confirmed derived property for the objects this person may read: one object when `key` ({key column: value}) is given, else one page of them. A
    property that is not confirmed gives no value: the refusal says its state and why (409)."""
    row = element_row(conn, derived_id(type_name, name)) if isinstance(type_name, str) and isinstance(name, str) else None
    if row is None or not derived_visible(conn, row, user):
        raise TypeRefused('没有这个派生属性', 404)
    if row['state'] != 'confirmed':
        line = line_of(conn, row['element_id'])
        raise TypeRefused(f'派生属性「{line["name"]}」现在不是已确认的状态（{line["reason"]}），不给出它的值', 409)
    sc = scope(conn, user)   # the one list of what may be told to a model: a property that reads a column kept from models is not in it
    if row['element_id'] not in sc['derived']:
        if row['element_id'] in sc['derived_kept_back']:
            raise TypeRefused(f'派生属性「{line_of(conn, row["element_id"])["name"]}」用到的一列，所有者设成了取值不对模型开放，所以不给出它的值', 403)
        raise TypeRefused('没有这个派生属性', 404)
    content = json.loads(row['content_json'])
    result = evaluate(conn, content, user)
    if result['problems']:
        raise TypeRefused(f'派生属性「{content["name"]}」现在算不出来：{result["problems"][0]}', 409)
    table = _load(conn, user, content['type'])
    objects = [{'key': _object_key(table, r)[0], 'value': result['values'].get(r['pos'])} for r in table['rows']]
    if key is not None:
        if not isinstance(key, dict) or set(key) != set(table['content']['key']):
            raise TypeRefused(f'key 要写成 {{{"、".join(table["content"]["key"])}: 取值}}')
        wanted = {c: _canonical(str(v)) for c, v in key.items()}
        objects = [o for o in objects if {c: _canonical(None if v is None else str(v)) for c, v in o['key'].items()} == wanted]
        if not objects:
            raise TypeRefused('没有这个对象', 404)
    pages = max(1, -(-len(objects) // OBJECT_PAGE))
    page = min(max(whole_page(page), 1), pages)
    shown = objects if key is not None else objects[(page - 1) * OBJECT_PAGE:page * OBJECT_PAGE]
    return {'type': content['type'], 'name': content['name'], 'says': describe_derived(conn, content), 'output_type': result['output_type'], 'datasets': result['datasets'],
            **_stamp(conn, row['element_id']), 'objects': shown, 'total': len(objects), 'page': page, 'pages': pages, 'rows_limited': table['limit'] is not None,
            'no_value': result.get('no_value')}


# --- the skill folder ------------------------------------------------------------------------------------------------------------------------------------

def _meaning_lines(t: dict) -> list[str]:
    return [f'- {column}：' + '、'.join(f'{v} = {label}' for v, label in m['values'].items()) + f'（{m["confirmed_by"]} 确认于 {m["confirmed_on"]}）' for column, m in t['meanings'].items()]


def _type_file(t: dict) -> str:
    props = [f'- {p["name"]}（{p["column"]}，{p["type"]}{"，代码列" if p["code"] else ""}）' for p in t['properties']]
    return '\n'.join([f'# {t["name"]}（{t["id"]}）', '', t['description'] or '', '', f'来自数据集 {t["dataset"]}；主键 {"、".join(t["key"])}；{t["confirmed_by"]} 确认于 {t["confirmed_on"]}。', '',
                      '## 属性', *props, *(['', '## 代码的含义', *_meaning_lines(t)] if t['meanings'] else [])]).strip() + '\n'


def skill_files(conn, user: dict | None, today: date | None = None) -> dict[str, str]:
    """{path inside the folder: text}: SKILL.md, one file for each confirmed type, relations, views, derived properties, the refusal rules and the same definitions as JSON."""
    d = definitions(conn, user)
    day = (today or date.today()).isoformat()
    by_type = {t['id']: t for t in d['types']}
    files = {f'definitions/{t["id"]}.md': _type_file(t) for t in d['types']}
    files['definitions/relations.md'] = '# 关系\n\n' + ('\n'.join(
        f'- {r["name"]}：{by_type[r["from"]]["name"]} → {by_type[r["to"]]["name"]}（{r["cardinality"]}，{r["from_column"]} = {r["to_column"]}；{r["confirmed_by"]} 确认于 {r["confirmed_on"]}）'
        for r in d['relations']) or '还没有已确认的关系。') + '\n'
    files['definitions/views.md'] = '# 视图（取哪些行）\n\n' + ('\n'.join(f'- {v["name"]}：{v["line"]}' for v in d['views']) or '还没有已确认的视图。') + '\n'
    files['definitions/derived.md'] = '# 派生属性\n\n' + ('\n'.join(f'- {x["name"]}：{x["says"] or "算法没有写出来（用到的列的含义不对模型开放），值用 read_derived_property 读"}（{x["confirmed_by"]} 确认于 {x["confirmed_on"]}）' for x in d['derived']) or '还没有已确认的派生属性。') + '\n'
    files['refusal-rules.md'] = '# 什么时候该拒绝回答\n\n' + '\n'.join(f'{i}. {r}' for i, r in enumerate(d['rules'], 1)) + '\n'
    files['definitions/definitions.json'] = json.dumps({k: d[k] for k in ('types', 'relations', 'views', 'derived')}, ensure_ascii=False, indent=2) + '\n'
    index = '\n'.join(f'- [{t["name"]}](definitions/{t["id"]}.md)' for t in d['types']) or '还没有已确认的对象类型。'
    files['SKILL.md'] = '\n'.join([
        '---', f'name: {SKILL_NAME}', 'description: 这个团队已经确认的业务定义（对象、代码含义、关系、视图、派生属性）和拒答规则。回答和这些业务对象有关的问题前先读它；定义里没有的，不要猜。', '---', '',
        '# 已确认的业务定义', '', f'导出于 {day}。里面只有已经由两个人确认过的定义，没有数据行，也没有还在等确认的东西。定义之后可能被改动：以导出日期为准，需要最新的用 MCP 的 describe_definitions。', '',
        '## 怎么用', '', '1. 先看下面的对象类型，找到问题说的是哪一个。', '2. 代码列的含义、视图的取行条件、派生属性的算式，都以对应文件为准。', '3. 文件里没有的，按 [refusal-rules.md](refusal-rules.md) 拒答。', '',
        '## 对象类型', '', index, '', '## 其他定义', '', '- [关系](definitions/relations.md)', '- [视图](definitions/views.md)', '- [派生属性](definitions/derived.md)', '- [拒答规则](refusal-rules.md)',
        '- 同样的内容，机器可读：definitions/definitions.json', '', '## 拒答规则', '', *(f'{i}. {r}' for i, r in enumerate(d['rules'], 1)), ''])
    return files


def skill_zip(conn, user: dict | None) -> bytes:
    """The skill folder as a zip, every file under ontopoc-definitions/."""
    packed = io.BytesIO()
    with zipfile.ZipFile(packed, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, text in skill_files(conn, user).items():
            z.writestr(f'{SKILL_NAME}/{path}', text.encode('utf-8'))
    return packed.getvalue()


# --- the page ------------------------------------------------------------------------------------------------------------------------------------------------

def agent_info(conn, user: dict | None) -> dict:
    """What the 智能体 page says: the tools an outside agent can call (name and what it does), how to start the server, and what is in the skill folder."""
    from ontology_poc_generator import mcp_server   # not at the top: the server module is the one that imports the service's routes
    tools = [{'name': t['name'], 'description': t['description'], 'arguments': [{'name': k, 'description': v.get('description', ''), 'required': k in t['inputSchema']['required']}
                                                                                for k, v in t['inputSchema']['properties'].items()]}
             for t in mcp_server.TOOLS if t['name'] in mcp_server.READ_TOOLS]
    d = definitions(conn, user)
    command = {'python': 'python3', 'module': 'ontology_poc_generator.mcp_server'}
    if user is None or user['role'] == 'admin':
        command = {**command, 'local_src': str(Path(__file__).resolve().parents[1])}   # where the code sits on this machine: the admin's to know, not every builder's
    return {'tools': tools, 'more_with_all': len(mcp_server.TOOLS) - len(tools), 'command': command,
            'skill': {'types': len(d['types']), 'relations': len(d['relations']), 'views': len(d['views']), 'derived': len(d['derived']), 'file': f'{SKILL_NAME}.zip'}}
