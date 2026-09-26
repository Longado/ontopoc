"""Explicit, human-confirmed correspondence to a versioned domain definition.

This compares declarations. It never changes bindings, computes a quality score,
or turns a library definition into a verified business ontology.
"""
from __future__ import annotations

import hashlib
import json


def local_schema(run: dict) -> dict:
    shapes = {(s['name'], f['path']): f for s in run.get('evaluation', {}).get('handover', {}).get('sources', [])
              for f in s.get('fields', [])}
    objects = []
    for obj in run['ontology']['object_types']:
        fields = {}
        bound = [{'source': p['source'], 'path': path} for p in obj.get('populated_from', []) for path in p.get('identity', {}).values()]
        for field in bound + obj.get('attributes', []):
            source, path = field.get('source'), field.get('path')
            if not source or not path:
                continue
            shape = shapes.get((source, path), {})
            fields[(source, path)] = {'source': source, 'path': path, 'type': field.get('type') or shape.get('type'),
                                       'unit': field.get('unit'), 'values': field.get('values')}
        objects.append({'key': obj['key'], 'label': obj.get('label') or obj['key'], 'fields': list(fields.values())})
    return {'objects': objects, 'relations': run['ontology']['relations']}


def run_fingerprint(run: dict) -> str:
    relevant = {'ontology': run['ontology'], 'fields': local_schema(run),
                'decisions': (run.get('confirmation') or {}).get('decisions')}
    return hashlib.sha256(json.dumps(relevant, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def stale_reasons(definition: dict, run: dict, record: dict) -> list:
    reasons = []
    if record.get('reference_sha256') != definition['sha256']:
        reasons.append('参考本体版本已变化，请重新核对并确认对应。')
    if record.get('run_sha256') != run_fingerprint(run):
        reasons.append('本次本体或字段已变化，请重新核对并确认对应。')
    return reasons


def compare_definition(definition: dict, run: dict, mappings: list) -> dict:
    if not isinstance(mappings, list):
        raise ValueError('对应关系必须是列表。')
    entities = {e['id']: e for e in definition['entity_types']}
    relations = {r['id']: r for r in definition['relationships']}
    refs = {('object', '', e['id']): e for e in entities.values()}
    refs.update({('relation', '', r['id']): r for r in relations.values()})
    refs.update({('property', e['id'], p['id']): p for e in entities.values() for p in e['properties']})
    schema = local_schema(run)
    objects = {o['key']: o for o in schema['objects']}
    local_relations = {r['key']: r for r in schema['relations']}
    if len(mappings) > len(refs):
        raise ValueError('对应条目重复或超出了参考定义范围。')
    decisions, taken, object_map = {}, set(), {}
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ValueError('每条对应必须写清类型、参考标识和本次标识。')
        kind, owner, iri = mapping.get('kind'), mapping.get('owner', ''), mapping.get('reference')
        if not all(isinstance(v, str) for v in (kind, owner, iri)) or (kind, owner, iri) not in refs:
            raise ValueError('参考对象、关系或属性不存在，请重新选择。')
        key = (kind, owner, iri)
        if key in decisions:
            raise ValueError('同一参考项不能重复对应。')
        local = mapping.get('local')
        if local is None:
            reason = mapping.get('reason')
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
                raise ValueError('标为不适用时，请写 1–500 字原因。')
        else:
            if mapping.get('reason'):
                raise ValueError('一项不能同时对应并标为不适用。')
            if kind in ('object', 'relation'):
                known = objects if kind == 'object' else local_relations
                if not isinstance(local, str) or local not in known:
                    raise ValueError('本次对象或关系不存在，请重新选择。')
                target = (kind, local)
                if kind == 'object':
                    object_map[iri] = local
            else:
                if not isinstance(local, dict) or not all(isinstance(local.get(k), str) and local[k] for k in ('source', 'path')):
                    raise ValueError('属性对应必须写清 source 和 path。')
                target = (kind, owner, local['source'], local['path'])
            if target in taken:
                raise ValueError('多个参考项指向同一项，请先消除对应冲突。')
            taken.add(target)
        decisions[key] = mapping

    # Validate after collecting all object mappings; request order carries no meaning.
    for (kind, owner, iri), mapping in decisions.items():
        local = mapping.get('local')
        if local is None:
            continue
        if kind == 'property':
            obj = objects.get(object_map.get(owner))
            if obj is None or not any(f['source'] == local['source'] and f['path'] == local['path'] for f in obj['fields']):
                raise ValueError('属性字段没有绑定在对应对象上；请先对应对象，再选择它的字段。')
        elif kind == 'relation':
            ref, ours = relations[iri], local_relations[local]
            ends = [object_map.get(ref['from']), object_map.get(ref['to'])]
            if None in ends or set(ends) != {ours['from'], ours['to']}:
                raise ValueError('关系端点不对应；请先确认两端对象，再选择连接这两个对象的关系。')

    diff = {key: [] for key in ('mapped', 'only_reference', 'only_local', 'different', 'unchecked', 'not_applicable')}
    for (kind, owner, iri), ref in refs.items():
        row = {'kind': kind, 'owner': owner, 'reference': iri,
               'reference_label': f"{entities[owner]['name']} · {ref['name']}" if owner else ref['name']}
        mapping = decisions.get((kind, owner, iri))
        if mapping is None:
            diff['only_reference'].append(row)
            continue
        if mapping.get('local') is None:
            diff['not_applicable'].append({**row, 'reason': mapping['reason'].strip()})
            continue
        local = mapping['local']
        different, unchecked = [], []
        if kind == 'object':
            row.update(local=local, local_label=objects[local]['label'], local_owner=local)
        elif kind == 'relation':
            ours = local_relations[local]
            row.update(local=local, local_label=ours.get('label') or ours.get('meaning') or local)
            if (object_map[ref['from']], object_map[ref['to']]) != (ours['from'], ours['to']):
                different.append('方向相反；对应不代表关系含义相同。')
            if ref.get('cardinality'):
                if not ours.get('cardinality'):
                    unchecked.append(f"参考基数为 {ref['cardinality']}，本次未声明基数；数据统计不能代替业务约束。")
                elif ref['cardinality'] != ours['cardinality']:
                    different.append(f"基数声明不同：参考 {ref['cardinality']} / 本次 {ours['cardinality']}。")
            unchecked.append('关系角色与业务含义由人核对，代码只检查端点和方向。')
        else:
            obj = objects[object_map[owner]]
            ours = next(f for f in obj['fields'] if (f['source'], f['path']) == (local['source'], local['path']))
            row.update(local={'source': local['source'], 'path': local['path']}, local_owner=obj['key'],
                       local_label=f"{obj['label']} · {local['source']}.{local['path']}")
            aliases = {'VARCHAR': 'string', 'INTEGER': 'integer', 'DECIMAL': 'decimal', 'DATE': 'date', 'DATETIME': 'datetime', 'BOOLEAN': 'boolean'}
            ours_type = aliases.get(ours['type'], ours['type'])
            if not ref.get('type') or not ours_type:
                unchecked.append('类型信息不足，无法检查。')
            elif ref['type'] != ours_type:
                different.append(f"类型不同：参考声明 {ref['type']} / 本次字段 {ours_type}（字段类型可能来自数据推断）。")
            for key, label in [('unit', '单位'), ('values', '枚举')]:
                rv, ov = ref.get(key), ours.get(key)
                if rv and not ov:
                    unchecked.append(f'{label}：参考声明 {rv}，本次未声明，无法检查。')
                elif ov and not rv:
                    unchecked.append(f'{label}：本次声明 {ov}，参考未声明，无法检查。')
                elif rv and ov and (set(rv) != set(ov) if key == 'values' else rv != ov):
                    different.append(f'{label}不同：参考 {rv} / 本次 {ov}。')
        diff['mapped'].append(row)
        if different:
            diff['different'].append({**row, 'details': different})
        if unchecked:
            diff['unchecked'].append({**row, 'details': unchecked})

    mapped_objects = set(object_map.values())
    for obj in schema['objects']:
        if obj['key'] not in mapped_objects:
            diff['only_local'].append({'kind': 'object', 'local': obj['key'], 'local_owner': obj['key'], 'local_label': obj['label']})
        fields_taken = {(m['local']['source'], m['local']['path']) for m in mappings
                        if m['kind'] == 'property' and m.get('local') and object_map.get(m['owner']) == obj['key']}
        for field in obj['fields']:
            if (field['source'], field['path']) not in fields_taken:
                diff['only_local'].append({'kind': 'property', 'local_owner': obj['key'],
                    'local': {'source': field['source'], 'path': field['path']},
                    'local_label': f"{obj['label']} · {field['source']}.{field['path']}"})
    mapped_relations = {m['local'] for m in mappings if m['kind'] == 'relation' and m.get('local')}
    for rel in schema['relations']:
        if rel['key'] not in mapped_relations:
            diff['only_local'].append({'kind': 'relation', 'local': rel['key'], 'local_label': rel.get('label') or rel['key']})
    for warning in definition.get('warnings', []):
        diff['unchecked'].append({'kind': 'definition', 'reference_label': '参考定义提示', 'details': [warning['message']]})
    for prop in definition.get('unattached_properties', []):
        diff['unchecked'].append({'kind': 'definition', 'reference_label': prop['name'], 'details': ['属性未能对应到参考对象，无法检查。']})
    for rel in definition['relationships']:
        for prop in rel.get('attributes', []):
            diff['unchecked'].append({'kind': 'definition', 'reference_label': f"{rel['name']} · {prop['name']}",
                                      'details': ['关系属性暂未支持字段对应，原始定义仍保留。']})
    return diff
