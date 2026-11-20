"""Start from the definitions a team already keeps in dbt: a dbt manifest.json is read for its models and four of dbt's generic tests, and each dbt model whose
name matches a dataset of the workspace becomes the same payloads the type and relation forms post. No model is asked and nothing is confirmed.

What is read, and nothing else: metadata.dbt_schema_version (it says the file is a dbt manifest, and which version), dbt_version and project_name (shown back);
in `nodes`, each model's resource_type, name and unique_id, and each test's resource_type, test_metadata {name, namespace, kwargs}, column_name, attached_node
(manifest v9 and later; before that the model is read from depends_on.nodes), depends_on.nodes and config.where. Of the tests, dbt's own `unique`, `not_null`,
`relationships` (kwargs `to` and `field`) and `accepted_values` (kwargs `values`). Descriptions, SQL, columns' types, sources, seeds, snapshots, metrics and
the semantic layer are not read; a test of another kind, a test with a `where` condition and a test on a column the dataset lacks are listed as skipped.

From that: a model whose tests make one column both unique and not null becomes an object type keyed on it (create_type: the key check runs on the full data),
with the columns its tests name as properties and an accepted_values column marked as a code column when it can be one (its values are listed as codes that
still need a meaning: dbt lists the values, not what they mean). A relationships test becomes a many-to-one relation (create_relation: the match runs on the
full data). Each lands as the form would leave it (checked, the importer its proposer, a second builder confirms), with one log line `dbt_import` on it in the
same transaction: the import is where it came from. A type or relation whose English name is taken is "already there" and left alone, so importing again adds
nothing. The preview is the same run on a copy of the workspace file that is thrown away (as upload_preview does), so it says exactly what the apply would do.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
import tempfile
from contextlib import nullcontext

from ontology_poc_generator.lang import tr
from ontology_poc_generator.object_relations import _relation_visible, create_relation, preview_relation, relation_id
from ontology_poc_generator.object_types import (
    CODE_TYPES, RELATION_PREFIX, TYPE_PREFIX, TypeRefused, _content, _visible, create_type, dataset_columns, element_row, type_id)
from ontology_poc_generator.type_access import dataset_hidden
from ontology_poc_generator.workspace_store import current_dataset, log_line, open_workspace

MAX_MANIFEST_BYTES = 20 * 1024 * 1024   # every manifest carries dbt's own macros (about 1 MB); a project of a few hundred models is several MB more. Parsed once, in memory, and not kept
MAX_PROPOSALS = 50   # new types and relations one import writes: each runs its check on the full data under the write lock, and each is one more thing a second builder reads
SHOWN = 200   # entries in each list of the answer; the rest are counted in `more`
SHOWN_TEXT = 120   # characters of a name or value from the manifest shown back
KNOWN_VERSIONS = range(1, 13)   # the manifest versions whose shape this reader was checked against (dbt's published schemas v1 to v12)
SCHEMA_URL = re.compile(r'https://schemas\.getdbt\.com/dbt/manifest/v([0-9]{1,3})\.json')
READ_TESTS = ('unique', 'not_null', 'relationships', 'accepted_values')
REF = re.compile(r"""\bref\(\s*(['"])([^'"]+)\1\s*(?:,\s*(['"])([^'"]+)\3\s*)?""")   # ref('model') or ref('package', 'model'), version arguments ignored
LOG_CHANGE = 'dbt_import'
MAX_CODES = 100   # accepted values shown for one column


class ManifestRefused(TypeRefused):
    """The file is not read at all: not JSON, not a dbt manifest, or too large."""


def body_limit() -> int:
    """The request that carries the manifest as a JSON string: escaping can make it up to about twice the file."""
    return MAX_MANIFEST_BYTES * 2 + 64 * 1024


def _megabytes(n: int) -> str:
    return f'{n / 1024 / 1024:.1f}'.rstrip('0').rstrip('.')


def parse_manifest(text) -> dict:
    """The parts of a manifest this reads (see the top of the file): {'version', 'dbt_version', 'project', 'models': {unique_id: name}, 'tests': [...],
    'unread': [{'model', 'what', 'reason'}], 'elsewhere': tests not on a model, 'broken': nodes that could not be read}. ManifestRefused when it is not one."""
    if not isinstance(text, str) or not text.strip():
        raise ManifestRefused(tr('请求里要有 manifest：dbt 生成的 target/manifest.json 的内容', 'The request needs manifest: the contents of the target/manifest.json dbt writes'))
    size = len(text.encode('utf-8'))
    if size > MAX_MANIFEST_BYTES:
        raise ManifestRefused(tr(f'这个 manifest 有 {_megabytes(size)} MB，一次最多读 {_megabytes(MAX_MANIFEST_BYTES)} MB', f'This manifest is {_megabytes(size)} MB; at most {_megabytes(MAX_MANIFEST_BYTES)} MB is read at once'), 413)
    try:
        data = json.loads(text)
    except RecursionError:
        raise ManifestRefused(tr('这个文件嵌套太深，读不了', 'This file is nested too deeply to read')) from None
    except ValueError:
        raise ManifestRefused(tr('这个文件不是 JSON：要的是 dbt 生成的 target/manifest.json', 'This file is not JSON: the file wanted is the target/manifest.json dbt writes')) from None
    metadata = data.get('metadata') if isinstance(data, dict) else None
    found = SCHEMA_URL.fullmatch(metadata.get('dbt_schema_version') or '') if isinstance(metadata, dict) and isinstance(metadata.get('dbt_schema_version'), str) else None
    if found is None or int(found.group(1)) < 1 or not isinstance(data.get('nodes'), dict):
        raise ManifestRefused(tr('这不是 dbt 的 manifest：metadata.dbt_schema_version 没有，或不是 dbt 写的 https://schemas.getdbt.com/dbt/manifest/vN.json，或没有 nodes',
                                 'This is not a dbt manifest: metadata.dbt_schema_version is missing or is not the https://schemas.getdbt.com/dbt/manifest/vN.json dbt writes, or there are no nodes'))
    short = lambda v: v[:60] if isinstance(v, str) else None
    plan = {'version': int(found.group(1)), 'dbt_version': short(metadata.get('dbt_version')), 'project': short(metadata.get('project_name')),
            'models': {}, 'tests': [], 'unread': [], 'elsewhere': 0, 'broken': 0, 'duplicates': 0}
    nodes = data['nodes']
    for unique_id, node in nodes.items():
        if isinstance(node, dict) and node.get('resource_type') == 'model':
            if isinstance(node.get('name'), str) and node['name']:
                plan['models'][unique_id] = node['name']
            else:
                plan['broken'] += 1
    for unique_id, node in nodes.items():
        if not isinstance(node, dict) or node.get('resource_type') != 'test':
            continue
        _read_test(plan, unique_id, node)
    seen, kept = set(), []
    for test in plan['tests']:   # the same test under another id (a copy, or one listed twice) is read once, before any work is done on it
        key = _sameness(test)
        if key in seen:
            plan['duplicates'] += 1
            continue
        seen.add(key)
        kept.append(test)
    plan['tests'] = kept
    return plan


def _sameness(test: dict) -> tuple:
    """What makes two tests the same test: the model, kind, column, condition, target and, for the kinds read, `field` and the plain values. A value that
    is not plain is never compared (nor turned into text): such a test is its own."""
    kwargs = test['kwargs']
    values = kwargs.get('values')
    plain = isinstance(values, list) and all(_plain(v) for v in values)
    field = kwargs.get('field') if isinstance(kwargs.get('field'), str) else None
    return (test['model'], test['kind'], test['namespace'], test['column'], test['where'], test['target'], test['to_text'], field,
            tuple((type(v).__name__, v) for v in values) if plain else ('own', id(test)) if values is not None else None)


def _depends(node: dict) -> list[str]:
    on = node.get('depends_on')
    listed = on.get('nodes') if isinstance(on, dict) else None
    return [n for n in listed if isinstance(n, str)] if isinstance(listed, list) else []


def _plain(value) -> bool:
    """Text, a number or true/false: the only values kept from a manifest. Anything else (a list, an object, nested to any depth) is never turned into text."""
    return isinstance(value, (str, int, float, bool)) and value is not None


def _label(node: dict, unique_id: str) -> str:
    """A test's name to show: its name when that is text, else its id (always text: a key of nodes)."""
    name = node.get('name')
    return (name if isinstance(name, str) and name else unique_id)[:80]


def _ref_name(value) -> str | None:
    found = REF.search(value) if isinstance(value, str) else None
    return (found.group(4) or found.group(2)) if found else None


def _read_test(plan: dict, unique_id: str, node: dict) -> None:
    """One test node: kept in plan['tests'] as {'model', 'kind', 'column', 'where', 'kwargs', 'target'} when it is on a model, else counted or listed."""
    models = plan['models']
    on_models = [n for n in _depends(node) if n in models]
    meta = node.get('test_metadata')
    if not on_models and not (isinstance(node.get('attached_node'), str) and node['attached_node'] in models):
        plan['elsewhere'] += 1   # a test on a source, seed or snapshot, or on nothing this file names
        return
    if not isinstance(meta, dict) or not isinstance(meta.get('name'), str):   # a test written in SQL (a singular test)
        for model in dict.fromkeys(on_models):
            plan['unread'].append({'model': models[model], 'what': _label(node, unique_id), 'reason': tr('用 SQL 写的测试不读', 'A test written in SQL is not read')})
        return
    kind, namespace = meta['name'], meta.get('namespace')
    kwargs = meta.get('kwargs') if isinstance(meta.get('kwargs'), dict) else {}
    target = None
    if kind == 'relationships':
        to_name = _ref_name(kwargs.get('to'))
        named = [n for n in models if models[n] == to_name]
        target = named[0] if len(named) == 1 else None
    attached = node.get('attached_node') if isinstance(node.get('attached_node'), str) and node['attached_node'] in models else None
    if attached is None:   # before manifest v9: the model is the one depends_on names (for a relationship, the one it does not point at)
        candidates = list(dict.fromkeys(on_models))
        if kind == 'relationships' and len(candidates) == 2 and target in candidates:
            candidates.remove(target)
        elif len(candidates) > 1:
            by_model = _ref_name(kwargs.get('model'))
            candidates = [c for c in candidates if models[c] == by_model]
        attached = candidates[0] if len(candidates) == 1 else None
    what = f'{namespace + "." if isinstance(namespace, str) and namespace else ""}{kind}'
    if attached is None:
        plan['unread'].append({'model': None, 'what': f'{what} ({_label(node, unique_id)})', 'reason': tr('看不出它测的是哪个模型', 'Cannot tell which model it tests')})
        return
    rest = [n for n in dict.fromkeys(on_models) if n != attached]
    if kind == 'relationships' and target is None and len(rest) == 1:   # `to` not readable as a ref: the other model it depends on
        target = rest[0]
    column = node.get('column_name') if isinstance(node.get('column_name'), str) else kwargs.get('column_name') if isinstance(kwargs.get('column_name'), str) else None
    config = node.get('config') if isinstance(node.get('config'), dict) else {}
    plan['tests'].append({'model': attached, 'kind': kind, 'namespace': namespace if isinstance(namespace, str) and namespace else None, 'what': what, 'column': column,
                          'where': config.get('where') if isinstance(config.get('where'), str) and config['where'].strip() else None, 'kwargs': kwargs,
                          'target': target, 'to_text': kwargs.get('to') if isinstance(kwargs.get('to'), str) else None})


# --- running it ---------------------------------------------------------------------------------------------------------------------------------------

def _datasets(conn, user: dict | None) -> list[str]:
    """The names of the datasets this person may see (a dataset kept from them is not there for them, as everywhere)."""
    return [n for (n,) in conn.execute('SELECT name FROM current_dataset ORDER BY name') if not dataset_hidden(conn, n, user)]


def _write(conn, make, element_id: str, who: str | None, after: dict):
    """The form's own function and the line saying where it came from, together or not at all, inside the import's one transaction (whole_import): a
    savepoint, so that a proposal the form's checks refuse takes back only what it wrote (its key check), and the import goes on with the next."""
    conn.execute('SAVEPOINT dbt_item')
    try:
        made = make()
        log_line(conn, who or tr('未署名', 'unsigned'), element_id, LOG_CHANGE, after=after)
    except BaseException:
        conn.execute('ROLLBACK TO dbt_item')
        conn.execute('RELEASE dbt_item')
        raise
    conn.execute('RELEASE dbt_item')
    return made


def whole_import(conn, plan: dict, who: str | None, user: dict | None) -> dict:
    """run_import as one transaction: every proposal in the report is written, or, when anything goes wrong on the way, none is. The type and relation
    functions join a transaction their caller holds (workspace_store.element_state_writes), so the whole import can be one."""
    conn.execute('BEGIN IMMEDIATE')
    try:
        report = run_import(conn, plan, who, user)
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    conn.execute('COMMIT')
    return report


def _name_taken() -> str:
    return tr('这个英文名不能用来提出新的定义', 'This English name cannot be used for a new definition')


def _existing(conn, prefix: str, english: str) -> dict | None:
    """The element whose English name is this one apart from letter case (the forms refuse a name that differs only in case)."""
    wanted = f'{prefix}{english}'.casefold()
    for (element_id,) in conn.execute('SELECT element_id FROM element_state WHERE substr(element_id, 1, ?) = ?', (len(prefix), prefix)):
        if element_id.casefold() == wanted:
            return element_row(conn, element_id)
    return None


def _code_text(value) -> str:
    """One accepted value as text (only plain values reach here: _plain), cut to 120 characters."""
    return ('true' if value is True else 'false' if value is False else str(value))[:120]


def run_import(conn, plan: dict, who: str | None, user: dict | None, meta: dict | None = None) -> dict:
    """Put forward what the manifest's tests say, for the models that match a dataset this person may see. Returns the report (see the route in ontology_server)."""
    models = plan['models']
    names: dict[str, list[str]] = {}
    for unique_id, name in models.items():
        names.setdefault(name, []).append(unique_id)
    visible = _datasets(conn, user)
    report = {'types': [], 'relations': [], 'codes': [], 'unmatched_models': [], 'skipped': list(plan['unread']), 'left_out': []}
    skip = lambda model, what, reason: report['skipped'].append({'model': model, 'what': what, 'reason': reason})
    written = 0
    type_of: dict[str, str] = {}   # model unique_id -> the English name of the type that stands for it now
    datasets: dict[str, dict] = {}   # model unique_id -> its dataset's current version
    tests_of: dict[str, list[dict]] = {}
    for test in plan['tests']:
        tests_of.setdefault(test['model'], []).append(test)
    for name in sorted(names, key=lambda n: (n.casefold(), n)):
        if len(names[name]) > 1:
            skip(name, tr('模型', 'model'), tr(f'manifest 里有 {len(names[name])} 个模型都叫 {name}（不同的包或版本），不知道是哪一个', f'The manifest has {len(names[name])} models named {name} (other packages or versions), so it cannot tell which one'))
            continue
        unique_id = names[name][0]
        matched = [d for d in visible if d.casefold() == name.casefold()]
        if not matched:
            report['unmatched_models'].append(name)
            continue
        if len(matched) > 1:
            skip(name, tr('模型', 'model'), tr(f'有 {len(matched)} 个数据集的名字和它只差大小写：{"、".join(matched)}', f'{len(matched)} datasets differ from its name only in letter case: {", ".join(matched)}'))
            continue
        dataset = current_dataset(conn, matched[0])
        datasets[unique_id] = dataset
        cols = dataset_columns(conn, dataset['id'])
        usable: list[dict] = []
        for test in tests_of.get(unique_id, []):
            what = f'{test["what"]} {name}{"." + test["column"] if test["column"] else ""}'
            if test['kind'] not in READ_TESTS or test['namespace'] not in (None, 'dbt'):
                skip(name, what, tr('这种测试不读：只读 dbt 自带的 unique、not_null、relationships、accepted_values', 'This kind of test is not read: only dbt\'s own unique, not_null, relationships and accepted_values are'))
            elif test['where']:
                skip(name, what, tr(f'它只在 {test["where"][:120]} 的行上成立，不是每一行', f'It holds only on rows where {test["where"][:120]}, not on every row'))
            elif not test['column']:
                skip(name, what, tr('没有写测的是哪一列', 'It does not say which column it tests'))
            elif test['column'] not in cols:
                skip(name, what, tr(f'数据集 {dataset["name"]} 里没有“{test["column"]}”这一列（列名要完全一样）', f'The dataset {dataset["name"]} has no column "{test["column"]}" (column names must match exactly)'))
            elif test['kind'] == 'accepted_values' and not (isinstance(test['kwargs'].get('values'), list) and all(_plain(v) for v in test['kwargs']['values'])):
                skip(name, what, tr('列出的取值里有不是文本、数字或 true/false 的东西，不读', 'Its values are not all plain text, numbers or true/false, so it is not read'))
            else:
                usable.append({**test, 'label': what})
        by_kind = lambda kind: [t['column'] for t in usable if t['kind'] == kind]
        keys = sorted(set(by_kind('unique')) & set(by_kind('not_null')))
        existing = _existing(conn, TYPE_PREFIX, name)
        if existing is not None:
            if not _visible(conn, existing, user):
                skip(name, tr('对象类型', 'object type'), _name_taken())
                continue
            type_of[unique_id] = _content(existing)['english_name']
            report['types'].append(_type_line(conn, existing, name, 'already_there'))
            continue
        same = [r for (e,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objtype:%' AND json_extract(content_json, '$.dataset') = ? ORDER BY element_id", (dataset['name'],))
                if (r := element_row(conn, e)) and _visible(conn, r, user)]
        if same:   # the dataset already has a type this person may see: that one stands for the model
            type_of[unique_id] = _content(same[0])['english_name']
            report['types'].append(_type_line(conn, same[0], name, 'already_there'))
            continue
        if not keys:
            skip(name, tr('对象类型', 'object type'), tr('测试里没有主键（no key in the tests）：没有哪一列同时有 unique 和 not_null 测试。复合主键或没测的主键不猜，请用“新建对象类型”自己选', 'No key in the tests: no column has both a unique and a not_null test. A key of several columns, or one with no tests, is not guessed; pick it with New object type'))
            continue
        if len(keys) > 1:
            skip(name, tr('对象类型', 'object type'), tr(f'有几列都同时有 unique 和 not_null（{"、".join(keys)}），不替你选主键，请用“新建对象类型”自己选', f'Several columns have both unique and not_null ({", ".join(keys)}); the key is not picked for you. Pick it with New object type'))
            continue
        if written >= MAX_PROPOSALS:
            report['left_out'].append({'what': tr(f'对象类型 {name}', f'object type {name}'), 'reason': _over_cap()})
            continue
        tested = list(dict.fromkeys([keys[0], *(t['column'] for t in usable)]))
        values = {t['column']: t['kwargs'].get('values') for t in usable if t['kind'] == 'accepted_values' and isinstance(t['kwargs'].get('values'), list)}
        codes = [c for c in values if cols[c]['type'] in CODE_TYPES and cols[c]['counts']]
        payload = {'english_name': name, 'name': name, 'dataset': dataset['name'], 'key': [keys[0]],
                   'properties': [{'column': c, **({'enum': True} if c in codes else {})} for c in tested]}
        try:
            made = _write(conn, lambda: create_type(conn, payload, who, user), type_id(name), who,
                          {'from': 'dbt manifest', 'model': unique_id, 'key_tests': ['unique', 'not_null'], 'manifest_version': plan['version']})
        except TypeRefused as exc:
            skip(name, tr('对象类型', 'object type'), str(exc))
            continue
        written += 1
        type_of[unique_id] = made['id']
        report['types'].append({**_type_line(conn, element_row(conn, type_id(made['id'])), name, 'new'), 'warnings': made['warnings']})
        for column, listed in values.items():
            report['codes'].append({'type': made['id'], 'column': column, 'values': [_code_text(v) for v in listed[:MAX_CODES]], 'code_column': column in codes,
                                    'note': None if column in codes else tr('这一列在数据里不能当代码列（代码列要是整数或文本，取值不超过 20 个），只作为普通属性', 'This column cannot be a code column in the data (a code column is integer or text with at most 20 values), so it is a plain property')})
    for unique_id in sorted(tests_of, key=lambda u: models[u]):
        if unique_id not in datasets:
            continue
        for test in sorted((t for t in tests_of[unique_id] if t['kind'] == 'relationships' and t['namespace'] in (None, 'dbt') and not t['where'] and t['column']), key=lambda t: t['column']):
            if test['column'] not in dataset_columns(conn, datasets[unique_id]['id']):
                continue   # already listed as skipped
            written += _relation(conn, plan, report, test, unique_id, type_of, datasets, who, user, written)
    unmatched = set(report['unmatched_models'])
    report['skipped'] = [s for s in report['skipped'] if s['model'] not in unmatched]   # a model with no dataset is listed once, as that; its tests are not
    report['unmatched_models'] = [n[:SHOWN_TEXT] for n in report['unmatched_models']]
    report['skipped'] = [{'model': s['model'][:SHOWN_TEXT] if s['model'] else s['model'], 'what': s['what'][:2 * SHOWN_TEXT], 'reason': s['reason'][:5 * SHOWN_TEXT]} for s in report['skipped']]   # names from the file can be any length
    if plan['elsewhere']:
        report['skipped'].insert(0, {'model': None, 'what': tr(f'{plan["elsewhere"]} 个不在模型上的测试', f'{plan["elsewhere"]} {"test" if plan["elsewhere"] == 1 else "tests"} not on a model'), 'reason': tr('只读模型上的测试（source、seed、snapshot 上的不读）', 'Only tests on models are read (not on sources, seeds or snapshots)')})
    if plan['broken']:
        report['skipped'].insert(0, {'model': None, 'what': tr(f'{plan["broken"]} 个模型', f'{plan["broken"]} {"model" if plan["broken"] == 1 else "models"}'), 'reason': tr('没有名字，读不了', 'No name, so it cannot be read')})
    more = {k: max(0, len(report[k]) - SHOWN) for k in report}
    report = {k: v[:SHOWN] for k, v in report.items()}
    return {'applied': False, 'manifest': {'schema_version': plan['version'], 'dbt_version': plan['dbt_version'], 'project': plan['project'], 'models': len(models), 'tests': len(plan['tests']),
                                           'duplicates': plan['duplicates'],
                                           'note': None if plan['version'] in KNOWN_VERSIONS else tr(f'这是 v{plan["version"]}，比这里核对过的 v1–v12 新：读不了的都列在跳过里', f'This is v{plan["version"]}, newer than the v1–v12 this reader was checked against: whatever could not be read is listed as skipped')},
            **report, 'more': more, 'limits': {'proposals': MAX_PROPOSALS, 'megabytes': MAX_MANIFEST_BYTES // 1024 // 1024}}


def _over_cap() -> str:
    return tr(f'一次导入最多提出 {MAX_PROPOSALS} 项；再导入一次会接着提出剩下的', f'One import proposes at most {MAX_PROPOSALS}; import again to propose the rest')


def _type_line(conn, row: dict, model: str, status: str) -> dict:
    content = _content(row)
    anchors = json.loads(row['anchors_json']) if row['anchors_json'] else {}
    return {'model': model, 'id': content['english_name'], 'name': content['name'], 'dataset': content['dataset'], 'key': content['key'],
            'properties': [p['column'] for p in content['properties']], 'codes': [p['column'] for p in content['properties'] if p['enum']],
            'status': status, 'state': row['state'], 'key_rows': anchors.get('key_rows'), 'warnings': []}


def _relation(conn, plan: dict, report: dict, test: dict, unique_id: str, type_of: dict, datasets: dict, who: str | None, user: dict | None, written: int) -> int:
    """One relationships test as a many-to-one relation from its model's type to the one its `to` names. Returns 1 when it was written."""
    models = plan['models']
    name, column, target = models[unique_id], test['column'], test['target']
    to_name = models[target] if target else _ref_name(test['to_text']) or (test['to_text'] or '?')[:60]
    what = f'relationships {name}.{column} → {to_name}'
    skip = lambda reason: report['skipped'].append({'model': name, 'what': what, 'reason': reason})
    if target is None:
        skip(tr('看不出它指向哪个模型（指向 source 的不读）', 'Cannot tell which model it points at (one that points at a source is not read)'))
        return 0
    if unique_id not in type_of or target not in type_of:
        missing = name if unique_id not in type_of else models[target]
        skip(tr(f'这次没有 {missing} 的对象类型（没有对应的数据集，或上面跳过了）', f'There is no object type for {missing} in this import (no matching dataset, or it was skipped above)'))
        return 0
    field = test['kwargs'].get('field') if isinstance(test['kwargs'].get('field'), str) else None
    if field is None or field not in dataset_columns(conn, datasets[target]['id']):
        skip(tr(f'数据集 {datasets[target]["name"]} 里没有“{field}”这一列（列名要完全一样）', f'The dataset {datasets[target]["name"]} has no column "{field}" (column names must match exactly)'))
        return 0
    payload = {'english_name': f'{name}_{column}', 'name': f'{name}_{column}', 'from': type_of[unique_id], 'to': type_of[target], 'cardinality': 'many_to_one',
               'from_column': column, 'to_column': field}
    ends = {k: payload[k] for k in ('from', 'to', 'from_column', 'to_column')}
    existing = _existing(conn, RELATION_PREFIX, payload['english_name'])
    if existing is None:
        existing = next((r for (e,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'relation:%' ORDER BY element_id")
                         if (r := element_row(conn, e)) and {k: _content(r)[k] for k in ends} == ends and _relation_visible(conn, r, user)), None)
    if existing is not None:
        if not _relation_visible(conn, existing, user):
            skip(_name_taken())
            return 0
        content = _content(existing)
        report['relations'].append({**{k: content[k] for k in ('from', 'to', 'from_column', 'to_column', 'cardinality')}, 'id': content['english_name'], 'model': name,
                                    'status': 'already_there', 'state': existing['state'], 'numbers': None, 'cardinality_holds': None, 'warnings': []})
        return 0
    if written >= MAX_PROPOSALS:
        report['left_out'].append({'what': tr(f'关系 {payload["english_name"]}', f'relation {payload["english_name"]}'), 'reason': _over_cap()})
        return 0
    try:
        made = _write(conn, lambda: create_relation(conn, payload, who, user), relation_id(payload['english_name']), who,
                      {'from': 'dbt manifest', 'model': unique_id, 'test': 'relationships', 'manifest_version': plan['version']})
        seen = preview_relation(conn, {k: payload[k] for k in ('from', 'to', 'cardinality', 'from_column', 'to_column')}, user)   # the counts as this person may read them
    except TypeRefused as exc:
        skip(str(exc))
        return 0
    report['relations'].append({**{k: payload[k] for k in ('from', 'to', 'from_column', 'to_column', 'cardinality')}, 'id': made['id'], 'model': name, 'status': 'new',
                                'state': element_row(conn, relation_id(made['id']))['state'],
                                'numbers': {k: seen[k] for k in ('rows', 'matched', 'unmatched', 'empty', 'fan_keys')}, 'cardinality_holds': seen['cardinality_holds'], 'warnings': made['warnings']})
    return 1


def import_manifest(db_path: Path, payload: dict, who: str | None, user: dict | None, lock=None) -> dict:
    """POST /api/workspace/types/dbt-import {manifest: the file's text, apply: bool}. The file is read outside the lock; then, under it, the import runs on a
    copy of the workspace file that is thrown away (apply false: a preview, nothing written) or on the workspace itself (apply true)."""
    if user is not None and user['role'] not in ('builder', 'admin'):
        raise TypeRefused(tr('只有建设者和管理员能导入', 'Only builders and admins can import'), 403)
    plan = parse_manifest(payload.get('manifest'))
    apply = payload.get('apply') is True
    try:
        with lock or nullcontext():
            return _import(db_path, plan, apply, who, user)
    except TypeRefused:
        raise
    except Exception as exc:   # whatever went wrong (a value too deep to handle included): the one transaction was taken back, so the person is told nothing was written
        raise TypeRefused(tr(f'读这个 manifest 时出了错（{type(exc).__name__}），什么都没有写入', f'Reading this manifest failed ({type(exc).__name__}); nothing was written'), 400) from None


def _import(db_path: Path, plan: dict, apply: bool, who: str | None, user: dict | None) -> dict:
    """Apply: whole_import on the workspace. Preview: the same on a copy of the workspace file that is thrown away."""
    if apply:
        conn = open_workspace(db_path)
        try:
            return {**whole_import(conn, plan, who, user), 'applied': True}
        finally:
            conn.close()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / 'workspace.sqlite'
        source, target = sqlite3.connect(str(db_path)), sqlite3.connect(str(copy))
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        conn = open_workspace(copy)
        try:
            return whole_import(conn, plan, who, user)
        finally:
            conn.close()
