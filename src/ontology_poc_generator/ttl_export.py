"""The ontology in the W3C standards (Turtle), for what they are for:

- exchange: ontology.ttl is OWL — a class per object, a property per field and per relation, the identity fields as
  owl:hasKey — so Protégé, a triple store or rdflib reads it without being told our JSON;
- merge: every object in data.ttl is named from the file's line of versions, its type and its identity values, so the
  same customer met in two tables is one node, and the next version of the file names it the same way;
- checking: shapes.ttl writes the rules a person adopted as SHACL, so a generic validator enforces them.

Written by hand, no RDF library: the output is a few statement shapes. What a person judged wrong is left out.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from ontology_poc_generator.object_rows import _read, _row
from ontology_poc_generator.ontology_confirm import without_wrong
from ontology_poc_generator.public_ontology import build_graph, normalize_proposal

PREFIXES = ('@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n'
            '@prefix owl: <http://www.w3.org/2002/07/owl#> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n')
RANGES = {'INTEGER': 'xsd:integer', 'DECIMAL': 'xsd:decimal', 'DATE': 'xsd:date', 'DATETIME': 'xsd:dateTime', 'VARCHAR': 'xsd:string'}


def _text(value: str, lang: str | None = None) -> str:
    escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return f'"{escaped}"' + (f'@{lang}' if lang else '')


def _value(value: str, kind: str | None) -> str:
    """A typed literal when the value is written the way its type says, plain text otherwise."""
    if kind == 'INTEGER' and re.fullmatch(r'-?\d+', value):
        return f'"{value}"^^xsd:integer'
    if kind == 'DECIMAL' and re.fullmatch(r'-?\d+(\.\d+)?', value):
        return f'"{value}"^^xsd:decimal'
    if kind == 'DATE' and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return f'"{value}"^^xsd:date'
    m = re.fullmatch(r'(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(:\d{2}(\.\d+)?)?', value) if kind == 'DATETIME' else None
    if m:
        return f'"{m[1]}T{m[2]}{m[3] or ":00"}"^^xsd:dateTime'
    return _text(value)


def ttl_files(ontology: dict, bundle: dict, handover: dict, form: dict | None, decisions: dict | None, rules: list[dict],
              base: str, graph: dict | None = None) -> dict[str, str]:
    """file name -> Turtle: ontology.ttl and data.ttl, and shapes.ttl when rules were adopted. base ends with '/'."""
    def iri(*parts):
        return '<' + base + '/'.join(quote(str(p), safe='') for p in parts) + '>'

    graph = graph or build_graph(ontology, bundle)
    p = without_wrong(normalize_proposal(ontology), decisions)
    judged = (decisions or {}).get('types', {})
    written = (form or {}).get('types', {})
    types, relations = p['object_types'], p['relations']
    kept = {t['key'] for t in types}
    fields = {t['type']: t['fields'] for t in handover.get('types', []) if t['type'] in kept}
    labels = {t['key']: judged.get(t['key'], {}).get('label') or written.get(t['key'], {}).get('label') or t.get('label') or t['key'] for t in types}

    schema = [PREFIXES, f"<{base.rstrip('/')}> a owl:Ontology .\n"]
    for t in types:
        key, own = t['key'], written.get(t['key'], {})
        comment = own.get('description') or t.get('definition')
        keys = ' '.join(iri(key, f['path']) for f in fields.get(key, []) if f.get('identity'))
        schema.append(f"{iri(key)} a owl:Class ;\n    rdfs:label {_text(labels[key], 'zh')}"
                      + (f" ;\n    rdfs:comment {_text(comment, 'zh')}" if comment else '')
                      + (f" ;\n    owl:hasKey ( {keys} )" if keys else '') + ' .\n')
        for f in fields.get(key, []):
            label = own.get('fields', {}).get(f['path'], {}).get('label') or f['path']
            schema.append(f"{iri(key, f['path'])} a owl:DatatypeProperty ;\n    rdfs:label {_text(label)} ;\n    rdfs:domain {iri(key)}"
                          + (f" ;\n    rdfs:range {RANGES[f['type']]}" if f.get('type') in RANGES else '') + ' .\n')
    for r in relations:
        schema.append(f"{iri('rel', r['key'])} a owl:ObjectProperty ;\n    rdfs:label {_text(r.get('label') or r['key'], 'zh')} ;\n"
                      f"    rdfs:domain {iri(r['from'])} ;\n    rdfs:range {iri(r['to'])} .\n")

    def node(inst):
        return iri('data', inst[0], '|'.join(str(v) for _, v in inst[1]))

    data = [PREFIXES]
    by_key = {t['key']: t for t in types}
    for inst in sorted((i for i in graph['records_of'] if i[0] in kept), key=node):
        kinds = {f['path']: f.get('type') for f in fields.get(inst[0], [])}
        row = _row(bundle, graph['records_of'], _read(by_key[inst[0]]), inst)
        facts = [f"{iri(inst[0], path)} {_value(value, kinds[path])}" for path, value in row.items() if path in kinds]
        data.append(f"{node(inst)} a {iri(inst[0])}" + ''.join(f' ;\n    {x}' for x in facts) + ' .\n')
    for r in relations:
        data += sorted({f"{node(a)} {iri('rel', r['key'])} {node(b)} .\n" for a, b, _ in graph['edges'].get(r['key'], ())})
    files = {'ontology.ttl': '\n'.join(schema), 'data.ttl': ''.join(data)}

    shapes = {}
    for rule in rules:
        paths = {f['path'] for f in fields.get(rule['type'], [])}
        if rule['kind'] == 'required' and rule['field'] in paths:
            shapes.setdefault(rule['type'], []).append(f"[ sh:path {iri(rule['type'], rule['field'])} ; sh:minCount 1 ]")
        elif rule['kind'] == 'order' and {rule['before'], rule['after']} <= paths:
            shapes.setdefault(rule['type'], []).append(f"[ sh:path {iri(rule['type'], rule['before'])} ; sh:lessThanOrEquals {iri(rule['type'], rule['after'])} ]")
    if shapes:
        files['shapes.ttl'] = '@prefix sh: <http://www.w3.org/ns/shacl#> .\n\n' + '\n'.join(
            f"{iri('shape', key)} a sh:NodeShape ;\n    sh:targetClass {iri(key)} ;\n    sh:property " + ' ,\n        '.join(props) + ' .\n'
            for key, props in shapes.items())
    return files
