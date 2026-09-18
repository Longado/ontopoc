"""字段释义员: drafts the columns of DIP's object form that only a person was left to fill — a business name and a one-line
description for each object and each of its fields, and which field shows an object to people. Type, length and key
are read from the data by code (handover_form); this is the one part that is a judgement about meaning, most of all
when the headers are English. One call, on request. Code keeps only what names a real object and field of this
ontology and says why the rest was dropped; a person edits it before it goes anywhere."""
from __future__ import annotations

from ontology_poc_generator.agent_harness import ask_model
from ontology_poc_generator.public_ontology import normalize_proposal, resolve
from ontology_poc_generator.recognition import model_failure_text

DESCRIBE_PROMPT_VERSION = 'company_field_descriptions.v1'
EXAMPLES = 3            # the same sample the modeller sees for a column; no rows
MAX_LABEL, MAX_DESCRIPTION = 40, 200   # what a form cell holds; longer is refused, not cut

DESCRIBE_SYSTEM_PROMPT = """你在帮顾问填一张数据平台的对象表单：每个业务对象、每个字段的中文业务名称和一句话描述，以及每个对象用哪个字段展示给人看。

你会收到建模目的，以及每个对象的 key、名称和字段清单（字段名、类型、长度、是否识别字段、最多 3 个示例值）。

只输出 JSON：
{"types": [{"type": "对象 key", "reasoning": "先写你的判断依据", "label": "对象中文名", "description": "一句话说它是什么",
  "display_field": "这个对象里最能让人认出它的字段名，拿不准写 null",
  "fields": [{"path": "字段名，原样照抄", "label": "字段中文名", "description": "一句话；看不出含义就写空字符串"}]}]}

规则：
- type 和 path 只能用给你的，原样照抄，不要编新的对象或字段。
- 中文名简短（一般 2 到 8 个字），描述一句话。看不出含义就留空，不要猜。
- display_field：主数据对象（客户、产品、供应商）选名称类字段；交易类对象（订单、合同）选它的编号。只能从这个对象自己的字段里选。
"""


def _examples(bundle: dict, sources: list[str], path: str) -> list[str]:
    seen = []
    for source in sources:
        for record in bundle['sources'].get(source, {}).get('records', []):
            for v in resolve(record, path)[:1]:
                if v not in (None, '') and str(v) not in seen:
                    seen.append(str(v)[:60])
            if len(seen) >= EXAMPLES:
                return seen
    return seen


def _text(value, limit):
    """A short string, or None when it is not one."""
    return value.strip() if isinstance(value, str) and len(value.strip()) <= limit else None


def draft_descriptions(ontology: dict, bundle: dict, handover: dict, gateway, purpose: str) -> dict:
    p = normalize_proposal(ontology)
    sources = {t['key']: sorted({pop['source'] for pop in t['populated_from']} | {a.get('source') for a in t['attributes'] if a.get('source')}) for t in p['object_types']}
    forms = {t['type']: t for t in handover.get('types', [])}
    request = {'purpose': purpose, 'types': [
        {'type': key, 'label': f['label'], 'fields': [{'path': x['path'], 'type': x.get('type'), 'length': x.get('length'), 'identity': x['path'] in f.get('identity_fields', []),
                                                       'examples': _examples(bundle, sources.get(key, []), x['path'])} for x in f['fields']]}
        for key, f in forms.items()]}
    out = {'prompt_version': DESCRIBE_PROMPT_VERSION, 'model': None, 'types': {}, 'rejected': [], 'error': None}
    judgement = ask_model(gateway, 'field_describer', DESCRIBE_PROMPT_VERSION, DESCRIBE_SYSTEM_PROMPT, request)
    out['model'] = judgement.model
    if judgement.failure == 'request':
        return {**out, 'error': model_failure_text(judgement.message)}
    if judgement.failure == 'not_json' or not isinstance(judgement.reply, dict) or not isinstance(judgement.reply.get('types'), list):
        return {**out, 'error': '模型返回的不是约定的 JSON'}
    for t in judgement.reply['types']:
        key = t.get('type') if isinstance(t, dict) else None
        if key not in forms:
            out['rejected'].append({'item': str(key), 'reason': f'本体里没有对象 {key}'})
            continue
        paths = [x['path'] for x in forms[key]['fields']]
        entry = {'label': _text(t.get('label'), MAX_LABEL), 'description': _text(t.get('description'), MAX_DESCRIPTION),
                 'display_field': None, 'drafted': True, 'fields': {}}
        if t.get('display_field') in paths:
            entry['display_field'] = t['display_field']
        elif t.get('display_field') is not None:
            out['rejected'].append({'item': f"{key}.display_field", 'reason': f"展示字段 {t.get('display_field')} 不是这个对象的字段"})
        for f in t.get('fields') if isinstance(t.get('fields'), list) else []:
            path = f.get('path') if isinstance(f, dict) else None
            if path not in paths:
                out['rejected'].append({'item': f'{key}.{path}', 'reason': f'{forms[key]["label"]} 没有字段 {path}'})
                continue
            label, description = _text(f.get('label'), MAX_LABEL), _text(f.get('description') or '', MAX_DESCRIPTION)
            if label is None or description is None:
                out['rejected'].append({'item': f'{key}.{path}', 'reason': '中文名或描述不是一段短文字'})
                continue
            entry['fields'][path] = {'label': label, 'description': description, 'drafted': True}
        out['types'][key] = entry
    return out
