"""Read-only RDF/XML definitions. No instances, model calls, confirmation or inferred constraints."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET

RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
RDFS = 'http://www.w3.org/2000/01/rdf-schema#'
OWL = 'http://www.w3.org/2002/07/owl#'
XSD = 'http://www.w3.org/2001/XMLSchema#'
XML = 'http://www.w3.org/XML/1998/namespace'
LIBRARY = Path(__file__).resolve().parents[2] / 'examples/ontologies/playground'
MAX_RDF_BYTES = 2 * 1024 * 1024
CARDINALITIES = {'one-to-one', 'one-to-many', 'many-to-one', 'many-to-many'}
XSD_TYPES = {'string': 'string', 'integer': 'integer', 'int': 'integer', 'long': 'integer',
             'decimal': 'decimal', 'float': 'decimal', 'double': 'double', 'date': 'date',
             'dateTime': 'datetime', 'boolean': 'boolean'}
PROPERTY_TYPES = set(XSD_TYPES.values()) | {'enum'}


def _local(iri):
    return iri.rsplit('}', 1)[-1].rsplit('#', 1)[-1].rsplit('/', 1)[-1]


def _text(element, tag):
    child = element.find(tag)
    return ''.join(child.itertext()).strip() if child is not None else ''


def _annotation(element, name):
    # Playground annotations use a per-ontology namespace, not a fixed prefix or URI.
    return next((''.join(c.itertext()).strip() for c in element
                 if _local(c.tag) == name and c.tag.split('}', 1)[0].lstrip('{') not in {RDF, RDFS, OWL, XSD}), '')


def parse_rdf(text: str, filename='ontology.rdf') -> dict:
    if len(text.encode('utf-8')) > MAX_RDF_BYTES:
        raise ValueError('本体文件太大，上限 2 MB。')
    if re.search(r'<!\s*(DOCTYPE|ENTITY)\b', text, re.I):
        raise ValueError('不支持带 DTD 或 ENTITY 声明的本体文件。')
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f'XML 格式不正确：{exc}') from exc
    if root.tag != f'{{{RDF}}}RDF':
        raise ValueError('要导入 RDF/XML：根元素应是 rdf:RDF。')

    bases = {}
    def collect(element, inherited=''):
        own = element.get(f'{{{XML}}}base', '')
        bases[element] = urljoin(inherited, own) if own else inherited
        for child in element:
            collect(child, bases[element])
    collect(root)
    warnings = []
    def warn(code, message, subject=''):
        item = {'code': code, 'message': message, 'subject': subject}
        if item not in warnings:
            warnings.append(item)

    def resource(element, attr='resource'):
        value = element.get(f'{{{RDF}}}{attr}')
        if value is None and attr == 'about' and element.get(f'{{{RDF}}}ID'):
            value = '#' + element.get(f'{{{RDF}}}ID')
        if value is None:
            return None
        base = bases[element]
        if urlsplit(value).scheme:
            return value
        if base.startswith('urn:') and value.startswith('#'):
            return base.split('#')[0] + value
        resolved = urljoin(base, value)
        if not urlsplit(resolved).scheme:
            warn('relative_iri', 'IRI 没有绝对地址或 xml:base，按原文保留。', resolved)
        return resolved

    def endpoint(element, tag):
        children = element.findall(f'{{{RDFS}}}{tag}')
        if len(children) > 1:
            warn('multiple_endpoints', f'同一项声明了多个 {tag}，暂未转换该约束；完整声明保留在 RDF 原文中。', resource(element, 'about') or '')
            return None
        return resource(children[0]) if children else None

    allowed = {f'{{{RDF}}}RDF', *(f'{{{OWL}}}{n}' for n in ('Ontology', 'Class', 'DatatypeProperty', 'ObjectProperty')),
               *(f'{{{RDFS}}}{n}' for n in ('label', 'comment', 'domain', 'range'))}
    for element in root.iter():
        if element.tag.startswith(tuple(f'{{{n}}}' for n in (RDF, RDFS, OWL))) and element.tag not in allowed:
            warn('unsupported_construct', f'原文中的 {_local(element.tag)} 暂未转换；完整内容保留在 RDF 原文中。', element.tag)
        if _local(element.tag) == 'DataBinding':
            warn('sample_binding', '原文含数据绑定声明；这里只浏览定义，没有连接其中的数据源。')

    entities = {}
    for element in root.findall(f'{{{OWL}}}Class'):
        iri = resource(element, 'about')
        if not iri:
            warn('unsupported_construct', '没有 IRI 的匿名类暂未转换；完整内容保留在 RDF 原文中。')
            continue
        if iri in entities:
            raise ValueError(f'同一个对象 IRI 重复声明，暂不支持合并：{iri}')
        entities[iri] = {'id': iri, 'name': _text(element, f'{{{RDFS}}}label') or _local(iri),
                         'description': _text(element, f'{{{RDFS}}}comment'), 'properties': []}
    if not entities:
        raise ValueError('没有可浏览的 owl:Class 对象；本轮支持显式类、属性和关系定义。')

    attributes, unattached = {}, []
    for element in root.findall(f'{{{OWL}}}DatatypeProperty'):
        iri = resource(element, 'about')
        if not iri:
            warn('unsupported_construct', '没有 IRI 的属性暂未转换。')
            continue
        range_iri = endpoint(element, 'range')
        declared = _annotation(element, 'propertyType') or _annotation(element, 'attributeType')
        kind = declared if declared in PROPERTY_TYPES else XSD_TYPES.get((range_iri or '').removeprefix(XSD)) if range_iri and range_iri.startswith(XSD) else None
        if len(element.findall(f'{{{RDFS}}}range')) > 1:
            kind = None
        if kind is None:
            warn('unknown_type', '属性类型未声明或暂不支持，按原文保留，未补成字符串。', iri)
        comments = [''.join(c.itertext()).strip() for c in element.findall(f'{{{RDFS}}}comment')]
        enum = _annotation(element, 'enumValues')
        prop = {'id': iri, 'name': _text(element, f'{{{RDFS}}}label') or _local(iri), 'type': kind,
                'range_iri': range_iri, 'unit': _annotation(element, 'unit') or None,
                'isIdentifier': _annotation(element, 'isIdentifier') == 'true' or any(c.casefold() == 'identifier property' for c in comments),
                'values': enum.split(',') if enum else [],
                'description': next((c for c in comments if c.casefold() != 'identifier property'), '')}
        relation = _annotation(element, 'relationshipAttributeOf')
        if relation:
            attributes.setdefault(relation, []).append(prop)
        else:
            domain = endpoint(element, 'domain')
            if domain in entities:
                entities[domain]['properties'].append(prop)
            else:
                unattached.append({**prop, 'domain_iri': domain})
                warn('unresolved_property', '属性未能对应到显式类，已单独保留。', iri)

    relationships = []
    def annotated_endpoint(element, name):
        declared = _annotation(element, name)
        if declared in entities:
            return declared
        matches = [iri for iri in entities if declared and _local(iri).casefold() == declared.casefold()]
        return matches[0] if len(matches) == 1 else None

    relation_elements = root.findall(f'{{{OWL}}}ObjectProperty')
    relation_ids = [resource(element, 'about') for element in relation_elements]
    for element, iri in zip(relation_elements, relation_ids):
        if not iri:
            warn('unsupported_construct', '没有 IRI 的关系暂未转换。')
            continue
        cardinality = _annotation(element, 'cardinality')
        if cardinality and cardinality not in CARDINALITIES:
            warn('unknown_cardinality', '关系基数暂不支持，未填入默认值。', iri)
        ends = {side: endpoint(element, tag) for side, tag in [('from', 'domain'), ('to', 'range')]}
        for side, annotation in [('from', 'fromEntityId'), ('to', 'toEntityId')]:
            tag = 'domain' if side == 'from' else 'range'
            if ends[side] is None and len(element.findall(f'{{{RDFS}}}{tag}')) <= 1:
                ends[side] = annotated_endpoint(element, annotation)
        if any(end not in entities for end in ends.values()):
            warn('unresolved_endpoint', '关系端点未能对应到显式类，定义已保留，图中没有连线。', iri)
        relation_attributes = attributes.pop(iri, [])
        short_id = _local(iri)
        if short_id != iri and sum(_local(r) == short_id for r in relation_ids if r) == 1:
            relation_attributes.extend(attributes.pop(short_id, []))
        relationships.append({'id': iri, 'name': _text(element, f'{{{RDFS}}}label') or _local(iri), **ends,
                              'description': _text(element, f'{{{RDFS}}}comment'),
                              'cardinality': cardinality if cardinality in CARDINALITIES else None,
                              'attributes': relation_attributes})
    for relation, props in attributes.items():
        unattached.extend(props)
        warn('unresolved_property', '关系属性未能对应到显式关系，已单独保留。', relation)
    ontology = root.find(f'{{{OWL}}}Ontology')
    return {'schema': 'ontology_definition.v1', 'name': (_text(ontology, f'{{{RDFS}}}label') if ontology is not None else '') or filename,
            'description': _text(ontology, f'{{{RDFS}}}comment') if ontology is not None else '',
            'entity_types': list(entities.values()), 'relationships': relationships, 'unattached_properties': unattached,
            'warnings': warnings, 'rdf_xml': text, 'filename': filename,
            'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}


def import_definition(payload: dict) -> dict:
    filename, encoded = payload.get('filename'), payload.get('content_base64')
    if not isinstance(filename, str) or Path(filename).suffix.lower() not in {'.rdf', '.owl'}:
        raise ValueError('本体定义请用 .rdf 或 .owl 文件。')
    if not isinstance(encoded, str):
        raise ValueError('缺少 content_base64。')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError('content_base64 不是有效的 base64。') from exc
    if len(raw) > MAX_RDF_BYTES:
        raise ValueError('本体文件太大，上限 2 MB。')
    return parse_rdf(raw.decode('utf-8-sig'), Path(filename).name)


def _index():
    return json.loads((LIBRARY / 'index.json').read_text(encoding='utf-8'))


def library_definition(entry_id: str) -> dict:
    index = _index()
    entry = next((e for e in index['entries'] if e['id'] == entry_id), None)
    if entry is None:
        raise KeyError('本体库里没有这一项。')
    directory = LIBRARY / entry['id']
    raw = (directory / entry['rdf_file']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry['sha256']:
        raise ValueError('本体原文与收录版本不同，请检查本体库文件。')
    definition = parse_rdf(raw.decode('utf-8-sig'), entry['rdf_file'])
    metadata = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
    return {**definition, 'entry': {**entry, 'repository': index['repository'], 'commit': index['commit'],
                                  'source_url': f"https://github.com/{index['repository']}/blob/{index['commit']}/{entry['source_path']}"},
            'metadata': metadata}


def library_catalogue() -> dict:
    entries = []
    for selected in _index()['entries']:
        definition = library_definition(selected['id'])
        meta = definition['metadata']
        entries.append({**definition['entry'], 'name': meta['name'], 'description': meta['description'],
                        'author': meta.get('author', ''), 'tags': meta.get('tags', []),
                        'counts': {'entities': len(definition['entity_types']), 'relationships': len(definition['relationships']),
                                   'properties': sum(len(e['properties']) for e in definition['entity_types'])}})
    return {'entries': entries}
