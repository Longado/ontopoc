"""The team workspace's confirmed definitions as two Turtle files, schema only, for another tool to read:

- ontology.ttl: OWL. A class per object type with its key (owl:hasKey), a datatype property per property with its range, an object property per relation with
  its cardinality as functional or inverse-functional, code meanings as a SKOS concept scheme per code column, and views and derived properties as annotated
  resources whose definition is text, not an axiom. Each definition carries who confirmed it, when and on which data versions, as annotations.
- shapes.ttl: SHACL for what code already checks: a key filled with one value (and, for a key of one column, not repeated), the codes of a code column that have
  a meaning, and a relation's cardinality.

Read from workspace_questions.scope as the person asking: the same confirmed set, and the same words, as describe_definitions and the standing sheet
(agent_access). Nothing that waits, nothing that person may not see, no column kept from them: what is left out leaves no trace, so their file is the file of a
workspace without it. The meanings of a column marked "don't send values" are left out, as the sheet leaves them blank. No row of data, no count of the data.

Written by hand, like the earlier screen's exporter (ttl_export, which this does not use): no RDF library at run time. Every name minted here is the base, a fixed
word, an English name the product already checks, or a hash; what people typed (names, columns, descriptions) and codes are only ever escaped literals.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import os
import re
import zipfile

from ontology_poc_generator.agent_access import STANDING_PATH, _last_confirmation, _says
from ontology_poc_generator.lang import current, tr
from ontology_poc_generator.object_types import TypeRefused, _content, type_id
from ontology_poc_generator.type_access import hidden_values
from ontology_poc_generator.workspace_questions import scope

SCHEMA_PATH = '/api/workspace/agent/schema'
BASE_ENV = 'ONTOPOC_IRI_BASE'
DEFAULT_BASE = 'urn:ontopoc:'
VOCAB = 'urn:ontopoc:vocab:'
# https://host[:port]/path/ ending in "/", or urn:<name>: with optional parts ending in ":" or "/": characters an IRI takes as they are
_BASE = re.compile(r'https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?/([A-Za-z0-9._~-]+/)*|urn:[A-Za-z0-9][A-Za-z0-9-]{1,31}:([A-Za-z0-9._~-]+[:/])*')
_DATETIME = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?')

PREFIXES = ('@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n'
            '@prefix owl: <http://www.w3.org/2002/07/owl#> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n'
            '@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n@prefix sh: <http://www.w3.org/ns/shacl#> .\n'
            f'@prefix op: <{VOCAB}> .\n')

# Only datatypes in OWL 2's datatype map: xsd:date and xsd:gYearMonth are not in it, so a date is written as xsd:dateTime and a month as text, each with a note.
RANGES = {'integer': 'xsd:integer', 'decimal': 'xsd:decimal', 'text': 'xsd:string', 'boolean': 'xsd:boolean', 'datetime': 'xsd:dateTime', 'date': 'xsd:dateTime', 'month': 'xsd:string'}
TYPE_NOTES = {
    'date': ('A column of days. OWL 2 has no date-only datatype, so the range is xsd:dateTime: write a day as that day at 00:00:00, for example 2024-01-05T00:00:00.',
             '一列日期。OWL 2 没有只到日的数据类型，所以值域写成 xsd:dateTime：一天写成当天 00:00:00，例如 2024-01-05T00:00:00。'),
    'month': ('A column of months, written YYYY-MM (for example 2024-01). OWL 2 has no month datatype, so the range is xsd:string.',
              '一列月份，写成 YYYY-MM（例如 2024-01）。OWL 2 没有月份的数据类型，所以值域写成 xsd:string。'),
    'datetime': ('In the data a time may be written with a space and without seconds; as xsd:dateTime it is YYYY-MM-DDThh:mm:ss.',
                 '数据里的时间可能用空格分开、不带秒；写成 xsd:dateTime 是 YYYY-MM-DDThh:mm:ss。'),
    'boolean': ('In the data a yes/no column may be written as a pair such as 是/否 or Y/N; as xsd:boolean it is true or false.',
                '数据里的是否列可能写成 是/否、Y/N 这样的一对；写成 xsd:boolean 是 true 或 false。'),
}
NOT_AN_AXIOM = ('What this definition says is in op:definitionText. That text is not an OWL axiom: OntoPoc works it out on the rows, and nothing in this file lets a reasoner work it out.',
                '这条定义说的是 op:definitionText 里的话。这段话不是 OWL 公理：OntoPoc 在数据行上算它，这个文件里没有任何东西能让推理机算出它。')
KEPT_MEANINGS = ('This column is marked "don\'t send values", so its meanings are not written here, as in the standing sheet.',
                 '这一列被设成“取值不对模型开放”，所以含义不写在这里，和定义状态表一样。')
KEPT_FROM_MODELS = ('A column it reads is marked "don\'t send values", so its meanings are not written here, as in the standing sheet.',
                    '它读的一列被设成“取值不对模型开放”，所以含义不写在这里，和定义状态表一样。')
SEVERAL_COLUMNS_NOTE = ('核心 SHACL 写不出“几列合起来不重复”：由几列组成的主键，这里只检查每一列都填了、只有一个值，不检查组合有没有重复。',
                        'Core SHACL cannot say "no two objects share these values together": for a key of several columns, these shapes check only that each column is filled with one value, not that the combination is unique.')
VOCAB_TERMS = {
    'definitionId': ('The id of the definition in OntoPoc, as in the standing sheet.', '定义在 OntoPoc 里的编号，和定义状态表一样。'),
    'confirmedBy': ('Who confirmed it last.', '最后是谁确认的。'),
    'confirmedAt': ('When it was confirmed last.', '最后一次确认的时间。'),
    'confirmedOnData': ('A dataset and its version that the last confirmation was made on.', '最后一次确认是在哪个数据集的哪一版上。'),
    'dataset': ('The dataset whose rows are the objects of this type.', '这个类型的对象来自哪个数据集的行。'),
    'column': ('The column of the dataset that this property is.', '这个属性是数据集里的哪一列。'),
    'codeList': ('The concept scheme of the meanings of this code column.', '这个代码列的含义所在的概念体系。'),
    'cardinality': ('The cardinality the relation was confirmed with: many_to_one, one_to_many or one_to_one.', '关系确认时的基数：many_to_one、one_to_many 或 one_to_one。'),
    'definitionText': ('What the definition says, in the words of the standing sheet.', '定义说的话，和定义状态表的写法一样。'),
    'note': ('A note for a person reading the file.', '给读这个文件的人的说明。'),
    'madeAt': ('When this file was made.', '这个文件是什么时候生成的。'),
    'standing': ('Where the live standing of each definition is read.', '每条定义现在的状态在哪里读。'),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def base() -> str:
    """The base every name in the files starts with: ONTOPOC_IRI_BASE when it is set, else urn:ontopoc:. A value that is not a plain base is refused (409),
    rather than replaced by the default quietly, because every name would change."""
    value = os.environ.get(BASE_ENV, '').strip() or DEFAULT_BASE
    if not _BASE.fullmatch(value):
        raise TypeRefused(tr(f'{BASE_ENV} 要写成 https://主机名/路径/（以 / 结尾）或 urn:名字:，只用字母、数字和 . _ ~ -，现在的值用不了',
                             f'{BASE_ENV} must be written as https://host/path/ (ending in /) or urn:name:, with only letters, digits and . _ ~ -; the value set now cannot be used'), 409)
    return value


def literal(text: str, lang: str | None = None) -> str:
    """A Turtle string literal of any text: quotes, backslashes, line breaks and other control characters escaped; a lone surrogate (not text) becomes U+FFFD."""
    out = []
    for ch in text:
        code = ord(ch)
        if ch in '\\"':
            out.append('\\' + ch)
        elif ch in '\n\r\t':
            out.append({'\n': '\\n', '\r': '\\r', '\t': '\\t'}[ch])
        elif code < 0x20 or code == 0x7f:
            out.append(f'\\u{code:04X}')
        elif 0xD800 <= code <= 0xDFFF:
            out.append('�')
        else:
            out.append(ch)
    return '"' + ''.join(out) + '"' + (f'@{lang}' if lang else '')


def _both(pair: tuple[str, str]) -> str:
    return f'{literal(pair[0], "en")} , {literal(pair[1], "zh")}'


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


class _Names:
    """The names minted under one base: from English names the product checks, and hashes of what people typed."""

    def __init__(self, root: str):
        self.root = root

    def __call__(self, *parts: str) -> str:
        return '<' + self.root + '/'.join(parts) + '>'

    def type(self, name):
        return self('type', name)

    def column(self, type_name, column):
        return self('type', type_name, 'column', _hash(column))

    def codes(self, type_name, column):
        return self('type', type_name, 'column', _hash(column), 'codes')

    def relation(self, name):
        return self('relation', name)

    def view(self, name):
        return self('view', _hash(name))

    def derived(self, type_name, name):
        return self('type', type_name, 'derived', name)


def _statement(subject: str, kinds: list[str], facts: list[tuple[str, str]]) -> str:
    lines = [f'{subject} a {" , ".join(kinds)}'] + [f'    {p} {o}' for p, o in facts]
    return ' ;\n'.join(lines) + ' .\n'


def _stamp(conn, element_id: str) -> list[tuple[str, str]]:
    """Who confirmed it last, when and on which data versions, as the standing sheet says it."""
    last = _last_confirmation(conn, element_id)
    out = [('op:definitionId', literal(element_id))]
    if last['confirmed_by']:
        out.append(('op:confirmedBy', literal(last['confirmed_by'])))
    if last['confirmed_at']:
        at = last['confirmed_at']
        out.append(('op:confirmedAt', f'{literal(at)}^^xsd:dateTime' if _DATETIME.fullmatch(at) else literal(at)))
    out += [('op:confirmedOnData', literal(f'{n} v{v}')) for n, v in (last['data_versions'] or {}).items()]
    return out


def _said(text: str | None) -> list[tuple[str, str]]:
    return [('op:definitionText', literal(text, current()))] if text else []


def _code(value: str, kind: str) -> str:
    return f'{literal(value)}^^xsd:integer' if kind == 'integer' else literal(value)


def _header(made: datetime, root: str, what: tuple[str, str], more: list[tuple[str, str]] = ()) -> str:
    lines = [
        ('OntoPoc: ' + what[0], 'OntoPoc：' + what[1]),
        (f'Made {made.isoformat(timespec="seconds")} for the person who downloaded it, from the confirmed definitions they may see. No row of data is in it.',
         f'生成于 {made.isoformat(timespec="seconds")}，只含下载它的人能看到的已确认定义，不含任何数据行。'),
        (f'A snapshot: whether each definition is still confirmed is read live at GET {STANDING_PATH}.', f'这是快照：每条定义现在是不是还已确认，以 GET {STANDING_PATH} 为准。'),
        (f'Names start with {root} and are names only: what people typed and codes are never part of a name.', f'名字都以 {root} 开头，只是名字：人写的文字和代码取值不进名字。'),
        ('Annotations (op:) carry no logical meaning: nothing in this file enforces "confirmed".', '注释（op:）没有逻辑含义：文件里没有任何东西能保证“已确认”。'),
        ('Read so far by rdflib (both files) and pyshacl (the shapes) in OntoPoc\'s tests; no OWL reasoner, profile checker or ontology editor has been run on it.',
         '目前读过它的只有 OntoPoc 测试里的 rdflib（两个文件）和 pyshacl（规则文件）；没有用 OWL 推理机、语言子集检查工具或本体编辑器读过。'),
        ('Check data with the SHACL shapes and inference off. A reasoner does not check: it reads two objects with the same key as one object.',
         '检查数据用 SHACL 规则，并关掉推理。推理机不做检查：它会把主键相同的两个对象读成同一个对象。'),
        *more]
    return ''.join(f'# {en}\n' for en, _ in lines) + ''.join(f'# {zh}\n' for _, zh in lines)


def files(conn, user: dict | None, now: datetime | None = None) -> dict[str, str]:
    """{'ontology.ttl': Turtle, 'shapes.ttl': Turtle}: the confirmed definitions this person may see, as the standing sheet lists them."""
    root = base()
    made = (now or _now()).astimezone(timezone.utc)
    n = _Names(root)
    sc = scope(conn, user)
    types = sc['types']
    onto = [_header(made, root, ('the confirmed definitions of one workspace, as OWL (schema only).', '一个工作区已确认的定义，写成 OWL（只有结构）。')), PREFIXES]
    onto.append(_statement(n('ontology'), ['owl:Ontology'], [
        ('rdfs:label', _both(('OntoPoc confirmed definitions', 'OntoPoc 已确认的定义'))), ('op:madeAt', f'{literal(made.isoformat(timespec="seconds"))}^^xsd:dateTime'),
        ('op:standing', literal(STANDING_PATH)),
        ('rdfs:comment', _both(('A snapshot of the confirmed definitions one person may see. No row of data. Annotations carry no logical meaning; check data with the SHACL shapes.',
                                '一个人能看到的已确认定义的快照。不含数据行。注释没有逻辑含义；检查数据用 SHACL 规则。')))]))
    onto += [_statement(f'op:{term}', ['owl:AnnotationProperty'], [('rdfs:comment', _both(words))]) for term, words in VOCAB_TERMS.items()]
    shapes = {}   # type name -> property shapes
    keys = []     # (type name, key property): a key of one column, whose repeats SHACL can see
    for name, t in types.items():
        content = t['content']
        cls = n.type(name)
        columns = {p['column'] for p in content['properties']}
        facts = [('rdfs:label', literal(content['name']))] + ([('rdfs:comment', literal(content['description']))] if content['description'] else [])
        facts += [('op:dataset', literal(content['dataset']))] + _stamp(conn, t['row']['element_id'])
        if set(content['key']) <= columns:   # a key column kept from this person: no key rather than half of one
            facts.append(('owl:hasKey', '( ' + ' '.join(n.column(name, c) for c in content['key']) + ' )'))
            own = shapes.setdefault(name, [])
            own += [f'[ sh:path {n.column(name, c)} ; sh:minCount 1 ; sh:maxCount 1 ]' for c in content['key']]
            if len(content['key']) == 1:
                keys.append((name, n.column(name, content['key'][0])))
        onto.append(_statement(cls, ['owl:Class'], facts))
        meanings = sc['meanings'].get(name, {})
        kept = hidden_values(conn, type_id(name))
        for p in content['properties']:
            facts = [('rdfs:label', literal(p['name'])), ('op:column', literal(p['column'])), ('rdfs:domain', cls)]
            facts += [('rdfs:range', RANGES[p['type']])] if p['type'] in RANGES else []
            facts += [('op:note', _both(TYPE_NOTES[p['type']]))] if p['type'] in TYPE_NOTES else []
            if p['column'] in meanings:
                facts.append(('op:codeList', n.codes(name, p['column'])))
            onto.append(_statement(n.column(name, p['column']), ['owl:DatatypeProperty', 'owl:FunctionalProperty'], facts))
        for column, m in meanings.items():
            scheme = n.codes(name, column)
            facts = [('rdfs:label', literal(f'{content["name"]}.{column}'))] + _stamp(conn, m['row']['element_id'])
            if column in kept:
                facts.append(('op:note', _both(KEPT_MEANINGS)))
            else:
                facts += _said(_says(conn, sc, 'meaning', _content(m['row'])))
                kind = next(p['type'] for p in content['properties'] if p['column'] == column)
                facts += [('skos:hasTopConcept', f'[ a skos:Concept ; skos:inScheme {scheme} ; skos:notation {literal(v)} ; skos:prefLabel {literal(label)} ]') for v, label in m['labels'].items()]
                if m['labels']:
                    shapes.setdefault(name, []).append(f'[ sh:path {n.column(name, column)} ; sh:in ( {" ".join(_code(v, kind) for v in m["labels"])} ) ]')
            onto.append(_statement(scheme, ['skos:ConceptScheme'], facts))
    for name, r in sc['relations'].items():
        c = r['content']
        kinds = ['owl:ObjectProperty'] + (['owl:FunctionalProperty'] if c['cardinality'] in ('many_to_one', 'one_to_one') else []) \
            + (['owl:InverseFunctionalProperty'] if c['cardinality'] in ('one_to_many', 'one_to_one') else [])
        facts = [('rdfs:label', literal(c['name']))] + ([('rdfs:comment', literal(c['description']))] if c.get('description') else [])
        facts += [('op:cardinality', literal(c['cardinality']))] + _said(_says(conn, sc, 'relation', c)) + _stamp(conn, r['row']['element_id'])
        facts += [('rdfs:domain', n.type(c['from'])), ('rdfs:range', n.type(c['to']))]
        onto.append(_statement(n.relation(name), kinds, facts))
        rel = n.relation(name)
        shapes.setdefault(c['from'], []).append(f'[ sh:path {rel} ; sh:class {n.type(c["to"])}' + (' ; sh:maxCount 1 ]' if c['cardinality'] != 'one_to_many' else ' ]'))
        if c['cardinality'] != 'many_to_one':
            shapes.setdefault(c['to'], []).append(f'[ sh:path [ sh:inversePath {rel} ] ; sh:maxCount 1 ]')
    for name, v in sc['views'].items():
        c = v['content']
        facts = [('rdfs:subClassOf', n.type(c['type'])), ('rdfs:label', literal(c['name']))] + ([('rdfs:comment', literal(c['description']))] if c.get('description') else [])
        facts += _said(_says(conn, sc, 'view', c)) + _stamp(conn, v['row']['element_id']) + [('op:note', _both(NOT_AN_AXIOM))]
        onto.append(_statement(n.view(name), ['owl:Class'], facts))
    derived = [(element_id, d, True) for element_id, d in sc['derived'].items()] + [(element_id, d, False) for element_id, d in sc['derived_kept_back'].items()]
    for element_id, d, open_text in sorted(derived, key=lambda x: x[0]):
        c = d['content']
        facts = [('rdfs:label', literal(c['name'])), ('rdfs:domain', n.type(c['type']))] + ([('rdfs:range', RANGES[c['output_type']])] if c.get('output_type') in RANGES else [])
        facts += (_said(_says(conn, sc, 'derived', c)) if open_text else []) + _stamp(conn, element_id)
        facts.append(('op:note', _both(NOT_AN_AXIOM if open_text else KEPT_FROM_MODELS)))
        onto.append(_statement(n.derived(c['type'], c['english_name']), ['owl:DatatypeProperty'], facts))

    out = [_header(made, root, ('SHACL shapes for what OntoPoc checks on the confirmed definitions (schema only).', '已确认定义里 OntoPoc 会检查的规则，写成 SHACL（只有结构）。'),
                   [(SEVERAL_COLUMNS_NOTE[1], SEVERAL_COLUMNS_NOTE[0])]), PREFIXES]
    for name in types:
        if shapes.get(name):
            out.append(_statement(n('shape', 'type', name), ['sh:NodeShape'], [('rdfs:label', literal(types[name]['content']['name'])), ('sh:targetClass', n.type(name)),
                                                                                ('sh:property', ' ,\n        '.join(shapes[name]))]))
    for name, prop in keys:   # the values of a key of one column: each is held by one object at most
        out.append(_statement(n('shape', 'type', name, 'key'), ['sh:NodeShape'], [('sh:targetObjectsOf', prop), ('sh:property', f'[ sh:path [ sh:inversePath {prop} ] ; sh:maxCount 1 ]')]))
    return {'ontology.ttl': '\n'.join(onto), 'shapes.ttl': '\n'.join(out)}


ZIP_NAME = 'ontopoc-definitions-owl.zip'
TURTLE = 'text/turtle; charset=utf-8'


def download(conn, user: dict | None, which: str | None = None) -> tuple[str, str, bytes]:
    """(content type, file name, bytes): both files in a zip, or one of them with which = 'ontology' or 'shapes'."""
    if which not in (None, 'ontology', 'shapes'):
        raise TypeRefused(tr('file 只能是 ontology 或 shapes', 'file must be ontology or shapes'), 404)
    made = _now()
    written = files(conn, user, made)
    if which is not None:
        return TURTLE, f'ontopoc-{which}.ttl', written[f'{which}.ttl'].encode('utf-8')
    packed = io.BytesIO()
    stamp = made.astimezone(timezone.utc).timetuple()[:6]
    with zipfile.ZipFile(packed, 'w', zipfile.ZIP_DEFLATED) as z:
        for file_name, text in written.items():
            z.writestr(zipfile.ZipInfo(file_name, date_time=stamp), text.encode('utf-8'), compress_type=zipfile.ZIP_DEFLATED)
    return 'application/zip', ZIP_NAME, packed.getvalue()
