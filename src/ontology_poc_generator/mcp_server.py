"""OntoPoc's features as standard MCP tools, over stdio.

Each tool calls the local modelling service (ontology_server, the one the page calls), so there is one set of checks,
counts and records whichever way a person or an agent comes in. The protocol part is the few JSON-RPC methods a tool
server needs — initialize, ping, tools/list, tools/call — written out here rather than adding a dependency.

Run: PYTHONPATH=src python -m ontology_poc_generator.mcp_server   (ONTOPOC_URL defaults to http://127.0.0.1:8767)
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import ProxyHandler, Request, build_opener

from ontology_poc_generator.ontology_confirm import without_wrong

PROTOCOL_VERSIONS = ('2025-06-18', '2025-03-26', '2024-11-05')
KEPT = ('question', 'query', 'note', 'snapshot', 'answer', 'status', 'path', 'reason')   # what an acceptance question carries
UNMET = ('query_limit', 'ontology_gap')


class ToolError(Exception):
    """What a tool reports back to the client as its error text."""


class LocalService:
    def __init__(self, base: str, poll_seconds: float = 2.0):
        self.base, self.poll_seconds = base.rstrip('/'), poll_seconds
        self._open = build_opener(ProxyHandler({})).open   # a system proxy must not carry calls to this machine

    def request(self, path: str, payload: dict | None = None):
        data = None if payload is None else json.dumps(payload).encode()
        req = Request(self.base + path, data=data, headers={'Content-Type': 'application/json'} if data else {})
        try:
            with self._open(req, timeout=600) as response:
                return json.load(response)
        except HTTPError as exc:
            try:
                raise ToolError(json.load(exc).get('error') or f'服务返回 {exc.code}') from None
            except ValueError:
                raise ToolError(f'服务返回 {exc.code}') from None
        except URLError as exc:
            raise ToolError(f'连不上本机建模服务 {self.base}（{exc.reason}）。先启动 ontology_server。') from None

    def run(self, saved_as: str) -> dict:
        return self.request(f'/api/ontology/runs/{quote(_text(saved_as, "saved_as"))}')


def _text(value, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f'缺少参数 {name}')
    return value.strip()


def _upload(files, purpose, previous=None, mode=None) -> dict:
    if not isinstance(files, list) or not files:
        raise ToolError('files 要写一个或几个本机文件路径')
    parts = []
    for f in files:
        path = Path(_text(f, 'files')).expanduser()
        if not path.is_file():
            raise ToolError(f'找不到文件 {path}')
        parts.append({'filename': path.name, 'content_base64': base64.b64encode(path.read_bytes()).decode()})
    extra = {'purpose': purpose.strip()} if isinstance(purpose, str) and purpose.strip() else {}
    if previous is not None:
        extra['previous'] = _text(previous, 'previous')
    if mode is not None:
        extra['mode'] = _text(mode, 'mode')
    return {**parts[0], **extra} if len(parts) == 1 else {'files': parts, **extra}


def _overview(run: dict) -> dict:
    ontology, ev = run['ontology'], run['evaluation']
    fit = ev.get('data_fit') or ev.get('document_fit') or {}
    items = [i for r in ev.get('asked', []) for i in r.get('items', [])] + (ev.get('questions') or {}).get('items', [])
    return {'saved_as': run.get('saved_as'), 'file': run['file']['name'], 'kind': run['file'].get('kind'), 'purpose': run.get('purpose'),
            'status': ontology['status'], 'objects': len(ontology['object_types']), 'relations': len(ontology['relations']),
            'checks_passed': f"{sum(c['passed'] for c in fit.get('checks', []))} / {len(fit.get('checks', []))}",
            'questions_answered': f"{sum(i.get('status') == 'answered' for i in items)} / {len(items)}",
            'stability': ev.get('stability') and {'runs': ev['stability']['runs'], 'types': ev['stability']['types']},
            'confirmed': bool(run.get('confirmation')), 'acceptance': bool(ev.get('acceptance'))}


def _question(item: dict) -> dict:
    return {**{k: item.get(k) for k in ('question', 'status', 'answer', 'path', 'reason', 'query')},
            **({'derive': item['derive']} if 'derive' in item else {})}


# ---- the tools: one per feature ----

def health(s, a):
    return s.request('/api/ontology/health')


def list_runs(s, a):
    runs = s.request('/api/ontology/runs')['runs']
    return {'runs': runs[: a.get('limit') or 20], 'total': len(runs)}


def preview_upload(s, a):
    return s.request('/api/ontology/preview', _upload(a.get('files'), a.get('purpose')))


def build_ontology(s, a):
    job = s.request('/api/ontology/jobs', _upload(a.get('files'), a.get('purpose'), a.get('previous'), a.get('mode')))['job_id']
    while True:   # the job always ends as done, failed or interrupted; a dead service raises in request()
        state = s.request(f'/api/ontology/jobs/{job}')
        if state['state'] == 'done':
            return _overview(state['result'])
        if state['state'] != 'running':
            raise ToolError(state.get('error') or '建模失败')
        time.sleep(s.poll_seconds)


def run_overview(s, a):
    return _overview(s.run(a.get('saved_as')))


def _kept(run: dict, a: dict) -> tuple[dict, dict]:
    """The ontology an agent reads: what the person judged wrong is out, as on the page and in the exports, unless the
    caller asks for everything."""
    decisions = (run.get('confirmation') or {}).get('decisions') or {}
    return (run['ontology'] if a.get('include_wrong') else without_wrong(run['ontology'], decisions)), decisions


def list_objects(s, a):
    run = s.run(a.get('saved_as'))
    ontology, decisions = _kept(run, a)
    last = ((run['evaluation'].get('reference') or {}).get('suggested') or {})   # how the person judged this file last time
    counts = (run['ontology'].get('verification') or {}).get('metrics', {}).get('instances', {})
    verdicts = decisions.get('types', {})
    shown = {t['key'] for t in ontology['object_types']}
    return {'objects': [{'key': t['key'], 'label': t.get('label') or t['key'], 'definition': t.get('definition') or t.get('rationale'),
                         'sources': sorted({p['source'] for p in t['populated_from']}),
                         'identity': sorted({f for p in t['populated_from'] for f in p['identity'].values()}),
                         'count': counts.get(t['key']), 'relations': sum(t['key'] in (r['from'], r['to']) for r in ontology['relations']),
                         'verdict': verdicts.get(t['key'], {}).get('verdict'),
                         'last_time': last.get('types', {}).get(t['key'], {}).get('verdict')} for t in ontology['object_types']],
            'left_out': [{'key': t['key'], 'label': t.get('label') or t['key'], 'verdict': 'wrong'}
                         for t in run['ontology']['object_types'] if t['key'] not in shown]}


def object_fields(s, a):
    run, key = s.run(a.get('saved_as')), _text(a.get('type'), 'type')
    form = next((t for t in (run['evaluation'].get('handover') or {}).get('types', []) if t['type'] == key), None)
    if form:
        return form
    t = next((t for t in run['ontology']['object_types'] if t['key'] == key), None)
    if t is None:
        raise ToolError(f'这份本体里没有对象 {key}')
    return {'type': key, 'attributes': [x.get('path') for x in t['attributes']], 'note': '这次运行没有逐列的类型和长度'}


def object_rows(s, a):
    key = quote(_text(a.get('type'), 'type'))
    query = 'all=1' if a.get('all') else f"page={int(a.get('page') or 1)}"
    return s.request(f"/api/ontology/runs/{quote(_text(a.get('saved_as'), 'saved_as'))}/objects/{key}?{query}")


def list_relations(s, a):
    run = s.run(a.get('saved_as'))
    ontology, decisions = _kept(run, a)
    last = ((run['evaluation'].get('reference') or {}).get('suggested') or {})
    verdicts = decisions.get('relations', {})
    cards = {c['key']: c for c in (run['evaluation'].get('handover') or {}).get('relations', [])}
    shown = {r['key'] for r in ontology['relations']}
    return {'relations': [{**{k: r.get(k) for k in ('key', 'from', 'to', 'label', 'meaning', 'source')},
                           **{k: cards.get(r['key'], {}).get(k) for k in ('cardinality', 'most_from', 'most_to')},
                           'verdict': verdicts.get(r['key'], {}).get('verdict'),
                           'last_time': last.get('relations', {}).get(r['key'], {}).get('verdict')} for r in ontology['relations']],
            'left_out': [{'key': r['key'], 'from': r['from'], 'to': r['to'], 'reason': '判错了' if verdicts.get(r['key'], {}).get('verdict') == 'wrong' else '一端的对象判错了'}
                         for r in run['ontology']['relations'] if r['key'] not in shown]}


def suggest_relations(s, a):
    return s.request(f"/api/ontology/runs/{quote(_text(a.get('saved_as'), 'saved_as'))}/suggestions")


def find_instances(s, a):
    key = quote(_text(a.get('type'), 'type'))
    return s.request(f"/api/ontology/runs/{quote(_text(a.get('saved_as'), 'saved_as'))}/instances/{key}?q={quote(str(a.get('query') or ''))}")


def instance_neighbourhood(s, a):
    return s.request(f"/api/ontology/runs/{quote(_text(a.get('saved_as'), 'saved_as'))}/graph?node={quote(_text(a.get('node'), 'node'))}")


def list_rules(s, a):
    return s.request(f"/api/ontology/runs/{quote(_text(a.get('saved_as'), 'saved_as'))}/rules")


def set_rules(s, a):
    adopted, declined = a.get('adopted'), a.get('declined') or []
    if not isinstance(adopted, list) or not isinstance(declined, list):
        raise ToolError('adopted、declined 要写规则 id 的列表')
    run = s.request('/api/ontology/rules', {'saved_as': _text(a.get('saved_as'), 'saved_as'), 'adopted': adopted, 'declined': declined})
    return run['evaluation']['rules']


def draft_form(s, a):
    return s.request('/api/ontology/form/draft', {'saved_as': _text(a.get('saved_as'), 'saved_as')})['evaluation']['form']


def save_form(s, a):
    return s.request('/api/ontology/form', {'saved_as': _text(a.get('saved_as'), 'saved_as'), 'form': a.get('form')})['evaluation']['form']


def export_forms(s, a):
    return s.request(f"/api/ontology/runs/{quote(_text(a.get('saved_as'), 'saved_as'))}/export/forms?format=json")


def export_mermaid(s, a):
    years = a.get('years')
    return s.request(f"/api/ontology/runs/{quote(_text(a.get('saved_as'), 'saved_as'))}/export/mermaid?format=json"
                     + (f"&years={quote(_text(years, 'years'))}" if years is not None else ''))


def export_ttl(s, a):
    return s.request(f"/api/ontology/runs/{quote(_text(a.get('saved_as'), 'saved_as'))}/export/ttl?format=json")


def data_layout(s, a):
    ev = s.run(a.get('saved_as'))['evaluation']
    fit = ev.get('data_fit') or {}
    return {'tables': (ev.get('handover') or {}).get('sources'), 'source_groups': fit.get('source_groups'), 'bridges': fit.get('bridges', [])}


def data_check(s, a):
    ev = s.run(a.get('saved_as'))['evaluation']
    fit = ev.get('data_fit') or ev.get('document_fit')
    if not fit:
        raise ToolError('本体没有通过核验，没有体检结果')
    findings = {k: v for k, v in fit.items() if isinstance(v, list) and k not in ('checks', 'source_groups', 'relations', 'orphans')}
    return {'checks': fit['checks'], 'findings': {k: {'count': len(v), 'first': v[:3]} for k, v in findings.items() if v},
            'relations': fit.get('relations'), 'orphans': [o for o in fit.get('orphans', []) if o.get('count')]}


def ask_question(s, a):
    question = a.get('question')
    payload = {'saved_as': _text(a.get('saved_as'), 'saved_as'), **({'question': _text(question, 'question')} if question else {})}
    ev = s.request('/api/ontology/ask', payload)['evaluation']
    got = ev['asked'][-1] if question else ev['questions']
    if got.get('error'):
        raise ToolError(got['error'])
    return {'items': [_question(i) for i in got['items']], 'model': got.get('model'), 'prompt_version': got.get('prompt_version')}


def list_questions(s, a):
    ev = s.run(a.get('saved_as'))['evaluation']
    return {'model_round': [_question(i) for i in (ev.get('questions') or {}).get('items', [])],
            'asked': [_question(i) for r in ev.get('asked', []) for i in r.get('items', [])],
            'acceptance': ev.get('acceptance')}


def confirm_derived(s, a):
    derive = a.get('derive')
    if not isinstance(derive, dict):
        raise ToolError('derive 要写 {type, label, terms}：用 ask_question 或 list_questions 里那道题的 derive')
    run = s.request('/api/ontology/derived', {'saved_as': _text(a.get('saved_as'), 'saved_as'), 'derive': derive})
    return {'derived': run['evaluation'].get('derived', []), 'asked': run['evaluation'].get('asked', [])}


def fix_question(s, a):
    run, question = s.run(a.get('saved_as')), _text(a.get('question'), 'question')
    ev = run['evaluation']
    candidates = [i for r in reversed(ev.get('asked', [])) for i in reversed(r.get('items', []))] + (ev.get('questions') or {}).get('items', [])
    item = next((i for i in candidates if i.get('question') == question), None)
    if item is None:
        raise ToolError('这份运行里没有问过这道题：先用 ask_question 问它')
    if item.get('status') != 'answered' and item.get('status') not in UNMET:
        raise ToolError('只有答出来的题，或问过但现在还答不了的题，才能固定为验收问题')
    kept = [{k: i.get(k) for k in KEPT} for i in (ev.get('acceptance') or {}).get('items', []) if i.get('question') != question]
    new = {**{k: item.get(k) for k in KEPT}, 'note': str(a.get('note') or '').strip()}
    result = s.request('/api/ontology/acceptance', {'saved_as': run['saved_as'], 'items': kept + [new]})
    return {'acceptance': result['evaluation']['acceptance']}


def confirm_ontology(s, a):
    payload = {'saved_as': _text(a.get('saved_as'), 'saved_as'), 'decisions': a.get('decisions')}
    if a.get('confirmed_by'):
        payload['confirmed_by'] = a['confirmed_by']
    run = s.request('/api/ontology/confirm', payload)
    return {'confirmation': run['confirmation'], 'reference': run['evaluation']['reference']}


def compare_reference(s, a):
    payload = {'saved_as': _text(a.get('saved_as'), 'saved_as'), 'reference': a.get('reference'), 'reference_name': a.get('reference_name') or '参考本体'}
    return s.request('/api/ontology/compare', payload)['evaluation']['reference']


def find_name_variants(s, a):
    return s.request('/api/ontology/variants', {'saved_as': _text(a.get('saved_as'), 'saved_as')})['evaluation']['variants']


WRONG = {'include_wrong': {'type': 'boolean', 'description': '连人判错的也给（默认不给）'}}
RUN = {'saved_as': {'type': 'string', 'description': '运行的保存名，来自 list_runs 或 build_ontology'}}
TYPE = {'type': {'type': 'string', 'description': '对象的 key，来自 list_objects'}}
FILES = {'files': {'type': 'array', 'items': {'type': 'string'}, 'description': '本机文件路径：一份或几份数据表（.csv .xlsx），或一份文档（.md .txt .docx .pdf）'},
         'purpose': {'type': 'string', 'description': '建模目的：这份本体要帮你回答什么问题'}}


def _tool(fn, description, properties=None, required=()):
    return {'name': fn.__name__, 'description': description, 'fn': fn,
            'inputSchema': {'type': 'object', 'properties': properties or {}, 'required': list(required)}}


TOOLS = [
    _tool(health, '本机建模服务是否在跑、有没有模型凭据、是否在跑旧代码。'),
    _tool(list_runs, '本机保存过的运行，新的在前。', {'limit': {'type': 'integer', 'minimum': 1}}),
    _tool(preview_upload, '不调用模型：看这几份文件会发给模型什么（字段名和示例值）。', FILES, ('files',)),
    _tool(build_ontology, '上传文件并建本体：模型提出、代码核验、数据体检、建三次比稳定性，并回答 purpose 里写的问题。给 previous 表示这是那次运行的新版本，沿用它的确认、验收问题和规则。会调用模型，等它跑完才返回。',
          {**FILES, 'previous': {'type': 'string', 'description': '上一版本的运行保存名（来自 list_runs）；不是新版本就不写'},
           'mode': {'type': 'string', 'enum': ['org'], 'description': '写 org 就按组织架构梳理一份文档：组织单元、岗位、人、工作环节及其关系'}}, ('files',)),
    _tool(run_overview, '一次运行的概况：对象和关系数、体检通过几项、问答能答几道、稳定性、是否确认过。', RUN, ('saved_as',)),
    _tool(list_objects, '本体里的对象：名称、说明、来自哪些表、识别字段、数据里有多少个、几条关系、人的判断。人判错的默认不给，列在 left_out 里；include_wrong=true 全给。', {**RUN, **WRONG}, ('saved_as',)),
    _tool(object_fields, '一个对象的属性：每个字段的类型、长度、空值和来源表（交接到数据平台时要填的列）。', {**RUN, **TYPE}, ('saved_as', 'type')),
    _tool(object_rows, '一个对象在数据里的每一个实例，一页 20 个；all=true 一次给全部。', {**RUN, **TYPE, 'page': {'type': 'integer', 'minimum': 1}, 'all': {'type': 'boolean'}}, ('saved_as', 'type')),
    _tool(list_relations, '本体里的关系：两端、含义、来源表、一对一/一对多/多对多、人的判断。判错的、或一端对象判错的默认不给，列在 left_out 里；include_wrong=true 全给。', {**RUN, **WRONG}, ('saved_as',)),
    _tool(suggest_relations, '代码在数据里看到、本体里没有的关系，只作建议：同一行上的两个对象没连起来；某列写的是别的对象的名称（且指向的不是本行已连着的那个）；或某列按名字和取值指向别的对象的编号。', RUN, ('saved_as',)),
    _tool(find_instances, '按名称或编号找数据里的某个对象（实例图谱的起点），给出节点 id。', {**RUN, **TYPE, 'query': {'type': 'string'}}, ('saved_as', 'type')),
    _tool(instance_neighbourhood, '实例图谱：一个对象的字段，和数据里与它相连的对象；每条关系先给 20 个，其余计数。',
          {**RUN, 'node': {'type': 'string', 'description': '节点 id，来自 find_instances 或上一次的结果'}}, ('saved_as', 'node')),
    _tool(list_rules, '代码在数据里找到的规则（某字段每个对象都有值；两个日期总是先后有序）和人采纳的规则，采纳的带本次数据里的违反数和例子。', RUN, ('saved_as',)),
    _tool(set_rules, '采纳或不要规则：adopted、declined 各写完整的规则 id 列表（id 来自 list_rules）。采纳的规则以后每次重跑都会检查。',
          {**RUN, 'adopted': {'type': 'array', 'items': {'type': 'string'}}, 'declined': {'type': 'array', 'items': {'type': 'string'}}}, ('saved_as', 'adopted')),
    _tool(draft_form, '让字段释义员起草对象表单里只有人能写的列：每个对象和字段的中文名、一句话描述、展示字段。一次模型调用；人写过的不会被覆盖。', RUN, ('saved_as',)),
    _tool(save_form, '保存对象表单。form 形如 {"types": {"<对象key>": {"label": "中文名", "description": "描述", "display_field": "字段", '
          '"drafted": false, "fields": {"<字段>": {"label": "…", "description": "…", "drafted": false}}}}}；drafted=false 表示人写的。',
          {**RUN, 'form': {'type': 'object'}}, ('saved_as', 'form')),
    _tool(export_forms, '按对象表单导出：每个对象一张 CSV（主键、展示、中文名称、英文名称、描述、类型、长度、属性类型）和一份说明。导入契约还没实测，说明里写着导入前要测。', RUN, ('saved_as',)),
    _tool(export_mermaid, '组织架构模式的运行导出组织图（Mermaid）：组织隶属.mmd（隶属、汇报、担任）和协作交接.mmd（协作、交接及交接内容）。'
          'years 写 2016-2022 只画这段时间的关系，没写时间的关系每段都画；判错的不画。',
          {**RUN, 'years': {'type': 'string', 'pattern': '^[0-9]{4}-[0-9]{4}$'}}, ('saved_as',)),
    _tool(export_ttl, '按 W3C 标准导出 Turtle：ontology.ttl（OWL 类、字段、关系、识别键）、data.ttl（每个对象按识别值命名，同一对象跨表跨版本同名）、'
          'shapes.ttl（采纳的规则写成 SHACL，有规则时才有）。判错的对象和关系不导出。', RUN, ('saved_as',)),
    _tool(data_layout, '上传的每张表：行数、跳过的标题行、每列类型长度空值；表没连上时，能把它们连起来的列。', RUN, ('saved_as',)),
    _tool(data_check, '数据体检：七项检查是否通过，以及每类发现的数量和前几个例子。全部由代码算。', RUN, ('saved_as',)),
    _tool(ask_question, '用数据回答一个业务问题：模型把问题写成查询，代码在数据上算答案。不给 question 就让模型出一组题。会调用模型。',
          {**RUN, 'question': {'type': 'string', 'maxLength': 300}}, ('saved_as',)),
    _tool(list_questions, '这次运行里模型出的题、人问过的题和固定的验收问题，带答案和查询路径。', RUN, ('saved_as',)),
    _tool(confirm_derived, '确认一个派生指标（例如 金额 = 单价 × 数量 ×（1 − 折扣））：服务再核一遍公式，存下后重算等它的题。'
          '只在人看过公式和试算结果、同意之后调用；derive 用那道题返回的 derive 原样传。',
          {**RUN, 'derive': {'type': 'object', 'description': '{type, label, terms}，来自那道题的 derive'}}, ('saved_as', 'derive')),
    _tool(fix_question, '把问过的一道题固定为验收问题：以后重传同一份文件，用同一个查询再算一次。',
          {**RUN, 'question': {'type': 'string'}, 'note': {'type': 'string', 'description': '口径说明，例如"按订单号计数"'}}, ('saved_as', 'question')),
    _tool(confirm_ontology, '保存人对本体的逐项判断，成为这个文件的参考本体并马上对照。decisions 形如 '
          '{"types": {"<对象key>": {"verdict": "ok"|"wrong", "label": "改名（可选）"}}, "relations": {"<关系key>": {"verdict": "ok"|"wrong"}}, "added": ["漏掉的对象名"]}。',
          {**RUN, 'decisions': {'type': 'object'}, 'confirmed_by': {'type': 'string', 'maxLength': 40}}, ('saved_as', 'decisions')),
    _tool(compare_reference, '拿一份人写的参考本体（JSON）和这次的本体对照：哪些对象、关系对上了，哪些多了、少了。',
          {**RUN, 'reference': {'type': 'object'}, 'reference_name': {'type': 'string'}}, ('saved_as', 'reference')),
    _tool(find_name_variants, '找出同一类对象里可能是同一个东西的不同写法，只给建议、不合并。会调用模型。', RUN, ('saved_as',)),
]
BY_NAME = {t['name']: t for t in TOOLS}


def handle(message: dict, service) -> dict | None:
    """One JSON-RPC message in, its reply out; None for a notification."""
    method, mid = message.get('method'), message.get('id')
    reply = lambda result: {'jsonrpc': '2.0', 'id': mid, 'result': result}
    error = lambda code, text: {'jsonrpc': '2.0', 'id': mid, 'error': {'code': code, 'message': text}}
    if 'id' not in message:
        return None
    if method == 'initialize':
        asked = (message.get('params') or {}).get('protocolVersion')
        return reply({'protocolVersion': asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                      'capabilities': {'tools': {'listChanged': False}},
                      'serverInfo': {'name': 'ontopoc', 'version': '0.1.0'},
                      'instructions': '本机 OntoPoc：上传业务表建本体，代码核验，体检、问答、确认。先 health，再 list_runs 或 build_ontology。'})
    if method == 'ping':
        return reply({})
    if method == 'tools/list':
        return reply({'tools': [{k: t[k] for k in ('name', 'description', 'inputSchema')} for t in TOOLS]})
    if method == 'tools/call':
        params = message.get('params') or {}
        tool = BY_NAME.get(params.get('name'))
        if tool is None:
            return error(-32602, f"没有这个工具：{params.get('name')}")
        missing = [k for k in tool['inputSchema']['required'] if (params.get('arguments') or {}).get(k) in (None, '')]
        try:
            if missing:
                raise ToolError(f"缺少参数 {'、'.join(missing)}")
            result = tool['fn'](service, params.get('arguments') or {})
        except (ToolError, ValueError, OSError) as exc:
            return reply({'content': [{'type': 'text', 'text': str(exc)}], 'isError': True})
        return reply({'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}], 'structuredContent': result, 'isError': False})
    return error(-32601, f'不支持的方法 {method}')


def check(base: str) -> None:
    """For a session start: one line when the modelling service does not answer, nothing when it does. Never fails the
    session, so it always exits 0."""
    try:
        with build_opener(ProxyHandler({})).open(base.rstrip('/') + '/api/ontology/health', timeout=3) as response:
            json.load(response)
    except Exception:   # any way of not answering is the same news for the person
        print(f'OntoPoc：本机建模服务没有在 {base} 运行，OntoPoc 的工具暂时用不了。在仓库里运行 PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server 启动它。')


def main():
    base = os.environ.get('ONTOPOC_URL', 'http://127.0.0.1:8767')
    if sys.argv[1:] == ['--check']:
        check(base)
        return
    service = LocalService(base)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            out = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': '不是合法的 JSON'}}
        else:
            out = handle(message, service) if isinstance(message, dict) else {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': '请求必须是 JSON 对象'}}
        if out is not None:
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + '\n')
            sys.stdout.flush()


if __name__ == '__main__':
    main()
