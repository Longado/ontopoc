"""The ontology as a Microsoft Fabric IQ ontology definition, the body the create-ontology REST API takes
(learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/ontology-definition).

What a hand-drawn ontology cannot carry and this one can: the data bindings. Every object says which table and column
fills each property, and every relation says which table's key columns link its two ends, because that is how the
ontology was checked on the data. Bindings need the workspace and lakehouse the tables were loaded into; without them
the definition carries the types alone. What a lakehouse binding cannot say — a value split on commas, a list inside a
cell, rows picked by a condition — is left out and named, never approximated.

Ids are derived from the keys, not drawn at random, so exporting the same ontology again updates it in place.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid

from ontology_poc_generator.ontology_confirm import without_wrong
from ontology_poc_generator.public_ontology import normalize_proposal

NAME = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,127}$')   # entity, property and relationship names
GUID = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
VALUE_TYPES = {'INTEGER': 'BigInt', 'DECIMAL': 'Double', 'DATE': 'DateTime', 'DATETIME': 'DateTime', 'VARCHAR': 'String'}
UNBOUND = {'split_comma': '一个格子里用逗号分了几个值', 'colon_hierarchy': '一个值里用冒号写了上下级'}


def _id(*parts) -> str:
    """A positive id below 2^53, so JavaScript clients read it exactly."""
    return str(int(hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:13], 16) + 1)


def _guid(*parts) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'ontopoc:' + '|'.join(map(str, parts))))


def _names(wanted: list[str], fallback: str) -> dict[str, str]:
    """Each name as Fabric accepts it: kept when it already fits, invalid characters turned into _, and a numbered
    fallback when nothing readable is left (a Chinese column name); unique within the list."""
    out, taken = {}, set()
    for i, name in enumerate(wanted, 1):
        clean = re.sub(r'[^a-zA-Z0-9_-]', '_', name).strip('_')[:120]
        clean = clean if NAME.match(clean) and re.search(r'[a-zA-Z0-9]', clean) else f'{fallback}_{i}'
        base, n = clean, 2
        while clean.lower() in taken:
            clean, n = f'{base}_{n}', n + 1
        taken.add(clean.lower())
        out[name] = clean
    return out


def _part(path: str, content) -> dict:
    payload = base64.b64encode(json.dumps(content, ensure_ascii=False, indent=2).encode('utf-8')).decode()
    return {'path': path, 'payload': payload, 'payloadType': 'InlineBase64'}


def _unbindable(pop: dict) -> str | None:
    if pop.get('transform', 'none') != 'none':
        return UNBOUND.get(pop['transform'], pop['transform'])
    if any('[].' in c for c in pop['identity'].values()):
        return '识别字段在格子里的列表中'
    if pop.get('where'):
        return '只取满足条件的行'
    return None


def fabric_files(ontology: dict, bundle: dict, handover: dict, form: dict | None, decisions: dict | None, file_name: str,
                 workspace: str | None = None, lakehouse: str | None = None) -> dict[str, str]:
    """file name -> text: fabric-ontology.json (the create-ontology request body) and 说明.md."""
    if (workspace is None) != (lakehouse is None):
        raise ValueError('工作区 ID 和 Lakehouse ID 要一起给，或都不给')
    if workspace is not None and not (GUID.match(workspace) and GUID.match(lakehouse)):
        raise ValueError('工作区 ID 和 Lakehouse ID 要写成 GUID，例如 580f410e-733d-43bd-8a87-be12b536f7ff')
    bind = workspace is not None
    p = without_wrong(normalize_proposal(ontology), decisions)
    judged, written = (decisions or {}).get('types', {}), (form or {}).get('types', {})
    shapes = {t['type']: {f['path']: f for f in t['fields']} for t in handover.get('types', [])}
    tables = _names(list(bundle['sources']), 'table')
    display = _names([re.sub(r'\.[^.]+$', '', file_name)], 'ontology')[re.sub(r'\.[^.]+$', '', file_name)]
    type_names = _names([t['key'] for t in p['object_types']], 'entity')

    parts = [_part('.platform', {'metadata': {'type': 'Ontology', 'displayName': display}}), _part('definition.json', {})]
    keys_of, left_out, used_tables = {}, [], set()
    for t in p['object_types']:
        key, own = t['key'], written.get(t['key'], {})
        type_id = _id('type', key)
        identity = sorted(t['populated_from'][0]['identity'])   # the logical key; each table names its own column for it
        columns = [t['populated_from'][0]['identity'][k] for k in identity]
        extra = [a['path'] for a in t['attributes'] if a.get('source') in bundle['sources'] and a['path'] not in columns]
        wanted = columns + list(dict.fromkeys(extra))
        names = _names(wanted, 'field')
        props, prop_id = [], {}
        for column in wanted:
            prop_id[column] = _id('property', key, column)
            mine = own.get('fields', {}).get(column, {})
            enrich = {'customAttributes': {'column': column}}
            if mine.get('description') or mine.get('label'):
                enrich['description'] = mine.get('description') or mine['label']
            props.append({'id': prop_id[column], 'name': names[column], 'redefines': None, 'baseTypeNamespaceType': None,
                          'valueType': VALUE_TYPES.get((shapes.get(key, {}).get(column) or {}).get('type'), 'String'),
                          'semanticEnrichment': enrich})
        id_parts = [prop_id[c] for c in columns]
        keys_of[key] = dict(zip(identity, id_parts))
        label = judged.get(key, {}).get('label') or own.get('label') or t.get('label')
        enrich = {k: v for k, v in (('description', own.get('description') or t.get('definition')),
                                    ('synonyms', [label] if label and label != key else None)) if v}
        entity = {'id': type_id, 'namespace': 'usertypes', 'baseEntityTypeId': None, 'name': type_names[key],
                  'entityIdParts': id_parts, 'displayNamePropertyId': prop_id.get(own.get('display_field'), id_parts[0]),
                  'namespaceType': 'Custom', 'visibility': 'Visible', **({'semanticEnrichment': enrich} if enrich else {}),
                  'properties': props, 'timeseriesProperties': []}
        parts.append(_part(f'EntityTypes/{type_id}/definition.json', entity))
        if not bind:
            continue
        for pop in t['populated_from']:
            why = _unbindable(pop) or (None if sorted(pop['identity']) == identity else '这张表用来识别它的字段和别的表不一样')
            if why:
                left_out.append(f"{label or key} 在 {pop['source']} 里没有绑定：{why}")
                continue
            own_columns = [pop['identity'][k] for k in identity]
            bound = [{'sourceColumnName': c, 'targetPropertyId': keys_of[key][k]} for k, c in zip(identity, own_columns)]
            bound += [{'sourceColumnName': a['path'], 'targetPropertyId': prop_id[a['path']]} for a in t['attributes']
                      if a.get('source') == pop['source'] and a['path'] in prop_id and a['path'] not in own_columns]
            binding_id = _guid('binding', key, pop['source'])
            used_tables.add(pop['source'])
            parts.append(_part(f'EntityTypes/{type_id}/DataBindings/{binding_id}.json', {'id': binding_id, 'dataBindingConfiguration': {
                'dataBindingType': 'NonTimeSeries', 'propertyBindings': bound,
                'sourceTableProperties': _table(workspace, lakehouse, tables[pop['source']])}}))

    by_key = {t['key']: t for t in p['object_types']}
    rel_names = _names([r['key'] for r in p['relations']], 'relation')
    for r in p['relations']:
        rel_id = _id('relation', r['key'])
        rel = {'namespace': 'usertypes', 'id': rel_id, 'name': rel_names[r['key']], 'namespaceType': 'Custom',
               'source': {'entityTypeId': _id('type', r['from'])}, 'target': {'entityTypeId': _id('type', r['to'])}}
        if r.get('meaning') or r.get('label'):
            rel['semanticEnrichment'] = {'description': r.get('meaning') or r['label']}
        parts.append(_part(f'RelationshipTypes/{rel_id}/definition.json', rel))
        if not bind:
            continue
        ends = []
        for end in (r['from'], r['to']):
            pop = next((x for x in by_key[end]['populated_from'] if x['source'] == r['source']), None)
            why = '关系一端的对象不从这张表读' if pop is None else _unbindable(pop) or (
                None if sorted(pop['identity']) == sorted(keys_of[end]) else '这张表用来识别它的字段和别的表不一样')
            ends.append((pop, why))
        why = next((w for _, w in ends if w), None)
        if why:
            left_out.append(f"关系 {r.get('label') or r['key']} 在 {r['source']} 里没有绑定：{why}")
            continue
        refs = [[{'sourceColumnName': pop['identity'][k], 'targetPropertyId': keys_of[end][k]} for k in sorted(keys_of[end])]
                for (pop, _), end in zip(ends, (r['from'], r['to']))]
        ctx_id = _guid('contextualization', r['key'])
        used_tables.add(r['source'])
        parts.append(_part(f'RelationshipTypes/{rel_id}/Contextualizations/{ctx_id}.json', {
            'id': ctx_id, 'dataBindingTable': _table(workspace, lakehouse, tables[r['source']]),
            'sourceKeyRefBindings': refs[0], 'targetKeyRefBindings': refs[1]}))

    body = {'displayName': display, 'description': f'OntoPoc 从 {file_name} 建模并在数据上核验的本体'[:256], 'definition': {'parts': parts}}
    return {'fabric-ontology.json': json.dumps(body, ensure_ascii=False, indent=2), '说明.md': _note(bind, tables, used_tables, left_out)}


def _table(workspace: str, lakehouse: str, name: str) -> dict:
    return {'sourceType': 'LakehouseTable', 'workspaceId': workspace, 'itemId': lakehouse, 'sourceTableName': name, 'sourceSchema': 'dbo'}


def _note(bind: bool, tables: dict, used: set, left_out: list[str]) -> str:
    lines = ['# 导入 Microsoft Fabric IQ', '',
             'fabric-ontology.json 是 Fabric 建本体接口的请求体，原样发送即可：',
             '', '```', 'POST https://api.fabric.microsoft.com/v1/workspaces/{工作区 ID}/ontologies', '```', '',
             '判错的对象和关系没有导出。同一份本体再导出一次，ID 不变，可以用 updateDefinition 覆盖更新。', '']
    if not bind:
        lines += ['这份只含对象、属性和关系，没有数据绑定：导出时填上数据所在的工作区 ID 和 Lakehouse ID，才会带上每个对象读哪张表哪一列、每条关系靠哪两列连起来。', '']
    else:
        lines += ['## 先把表放进 Lakehouse', '', '数据绑定按下面的表名找表，列名和上传的文件一致：', '']
        lines += [f'- {source} → {name}' if source != name else f'- {name}' for source, name in tables.items() if source in used]
        lines += ['']
    if left_out:
        lines += ['## 没有绑定的部分', '', 'Lakehouse 的数据绑定只能一列对一个属性，下面这些要先在表里整理好，再在 Fabric 里补绑定：', '']
        lines += [f'- {x}' for x in left_out] + ['']
    lines += ['OntoPoc 没有在真实的 Fabric 工作区里导入过这份文件；格式按微软的公开文档写成。']
    return '\n'.join(lines) + '\n'
