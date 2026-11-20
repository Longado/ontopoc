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
import sys
import tempfile
import traceback
from contextlib import nullcontext

from ontology_poc_generator.lang import tr
from ontology_poc_generator.object_relations import _relation_visible, create_relation, relation_id
from ontology_poc_generator.object_types import (
    CODE_TYPES, RELATION_PREFIX, TYPE_PREFIX, TypeRefused, _content, _visible, create_type, dataset_columns, element_row, limited_on, type_id)
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
    pinned = node.get('attached_node')
    if isinstance(pinned, str) and pinned not in models:   # dbt names what it is on, and it is not a model this reader can read: never fall back to depends_on
        if pinned.startswith('model.'):   # a model whose name is not text: the test is on it, not on the model it points at
            kind = meta.get('name') if isinstance(meta, dict) and isinstance(meta.get('name'), str) else _label(node, unique_id)
            plan['unread'].append({'model': None, 'what': f'{kind} ({_label(node, unique_id)})', 'reason': tr('看不出它测的是哪个模型', 'Cannot tell which model it tests')})
        else:
            plan['elsewhere'] += 1
        return
    if not on_models and not (isinstance(pinned, str) and pinned in models):
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


def _write(conn, make, element_id: str, who: str | None, after: dict, lock=None, state: dict | None = None):
    """The form's own function and the line saying where it came from, together or not at all: one transaction per proposal, as short as the form's, under
    the lock an upload takes (as the form's request is). Both are let go before the next proposal, so other requests get through in between. Once it is
    committed, state['committed'] says so: from then on nothing may answer "nothing was written"."""
    with lock or nullcontext():
        conn.execute('BEGIN IMMEDIATE')
        try:
            made = make()
            log_line(conn, who or tr('未署名', 'unsigned'), element_id, LOG_CHANGE, after=after)
        except BaseException:
            conn.execute('ROLLBACK')
            raise
        conn.execute('COMMIT')
    if state is not None:
        state['committed'].append(element_id)
    return made


def _failure(exc: BaseException, written: bool = False, general: bool = False) -> str:
    """Why an item failed, or the import (`general`), for the report: the kind of error only (the text of a database error can name the store's own
    tables). The whole of it goes to the service's log, for whoever runs it. `written`: the item's own write had gone through (general: something had)."""
    kind = type(exc).__name__
    try:
        traceback.print_exception(exc, file=sys.stderr)
    except Exception:   # printing it must not be what stops the report
        pass
    if general:
        return (tr(f'导入出错停下了（{kind}）。上面列为提出的都已经写入；详情在服务的日志里', f'The import stopped on an error ({kind}). What is listed above as proposed is written; the details are in the service log') if written
                else tr(f'导入出错停下了（{kind}），还没有写入任何一项；详情在服务的日志里', f'The import stopped on an error ({kind}) before any proposal was written; the details are in the service log'))
    if written:
        return tr(f'已经写入了，但这一项在报告里的说明没做出来（{kind}），导入在这里停下；详情在服务的日志里', f'It is written, but its line in this report could not be made ({kind}); the import stopped here. The details are in the service log')
    return tr(f'出错了（{kind}），这一项没有写入，导入在这里停下；详情在服务的日志里', f'It failed ({kind}); this one was not written and the import stopped here. The details are in the service log')


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


def run_import(conn, plan: dict, who: str | None, user: dict | None, lock=None, state: dict | None = None) -> dict:
    """Put forward what the manifest's tests say, for the models that match a dataset this person may see: types first, then relations, each proposal in
    its own short transaction (_write). Returns the report (see the route).

    Two phases, one rule each:
    - Phase one (_plan, up to the first proposal): read and plan everything that can be planned without writing: the datasets each model matches and
      their versions, the order of the types, and the relations to try with their names. Nothing has been written, so an error here reaches
      import_manifest and is answered 400 "nothing was written", which is true.
    - Phase two (_propose and _finish, from the first proposal to the returned report): ONE guard around all of it, the proposals, the report and its
      caps. An unexpected error anywhere in it gives the report anyway (stopped: true): what was written, what failed and why (a general entry when it is
      not one item's), and what was not attempted. Each item also has its own guard, so the report can name the item that failed."""
    state = state if state is not None else {'committed': []}
    planned = _plan(conn, plan, user, state)
    try:
        _propose(conn, plan, planned, state, who, user, lock)
        return _finish(plan, planned['report'], state['stopped'])
    except Exception as exc:   # phase two: whatever happened, something may be written, so the answer is a report
        return _stopped_report(plan, planned, state, exc)


def _plan(conn, plan: dict, user: dict | None, state: dict) -> dict:
    """Phase one: reads only. The models by name, the datasets each one matches (state['datasets']: model unique_id -> its dataset's current version), the
    tests of each model, the order the types are tried in, and the relation jobs (they depend on the datasets, not on the types written)."""
    models = plan['models']
    names: dict[str, list[str]] = {}
    for unique_id, name in models.items():
        names.setdefault(name, []).append(unique_id)
    visible = _datasets(conn, user)
    state.update({'written': 0, 'type_of': {}, 'datasets': {}, 'stopped': False, 'next_job': 0})   # type_of: model unique_id -> the English name of the type that stands for it now
    tests_of: dict[str, list[dict]] = {}
    for test in plan['tests']:
        tests_of.setdefault(test['model'], []).append(test)
    order = sorted(names, key=lambda n: (n.casefold(), n))
    matched = {name: [d for d in visible if d.casefold() == name.casefold()] for name in order}
    for name in order:
        if len(names[name]) == 1 and len(matched[name]) == 1:
            state['datasets'][names[name][0]] = current_dataset(conn, matched[name][0])
    jobs = _relation_jobs(conn, models, tests_of, state['datasets'])
    report = {'types': [], 'relations': [], 'codes': [], 'unmatched_models': [], 'skipped': list(plan['unread']), 'left_out': [], 'failed': [], 'not_attempted': []}
    return {'names': names, 'tests_of': tests_of, 'order': order, 'matched': matched, 'jobs': jobs, 'report': report}


def _propose(conn, plan: dict, planned: dict, state: dict, who: str | None, user: dict | None, lock) -> None:
    """Phase two, the proposals: each type, then each relation. An error on one item stops here, naming it: written or not (state['committed'] says),
    and what was not attempted."""
    models, names, tests_of, order, report = plan['models'], planned['names'], planned['tests_of'], planned['order'], planned['report']
    matches = lambda name: len(names[name]) == 1 and len(planned['matched'][name]) == 1

    def would_try(unique_id: str) -> bool:   # a model whose type would have been tried: a dataset of its name, and a column with both unique and not_null
        keyed = lambda kind: {t['column'] for t in tests_of.get(unique_id, []) if t['kind'] == kind and t['namespace'] in (None, 'dbt') and not t['where'] and t['column']}
        return matches(models[unique_id]) and bool(keyed('unique') & keyed('not_null'))
    for i, name in enumerate(order):
        before = len(state['committed'])
        try:
            _model(conn, plan, report, state, name, names[name], planned['matched'][name], tests_of, who, user, lock)
        except Exception as exc:
            _item_failed(report, state, before, tr(f'对象类型 {name}', f'object type {name}'), exc)
            later = order[i + 1:]
            for other in later:
                if len(names[other]) == 1 and would_try(names[other][0]):
                    report['not_attempted'].append({'what': tr(f'对象类型 {other}', f'object type {other}')})
                elif len(names[other]) == 1 and not planned['matched'][other]:
                    report['unmatched_models'].append(other)
            pending = set(order[i:])
            ready = lambda u: u in state['type_of'] or (models[u] in pending and would_try(u))   # a type there now, the one that failed, or one that would have been tried
            report['not_attempted'] += [{'what': _relation_what(models, u, t)} for u, t, _ in planned['jobs'] if t['target'] and ready(u) and ready(t['target'])]
            return
    for k, (unique_id, test, several) in enumerate(planned['jobs']):
        state['next_job'] = k
        before = len(state['committed'])
        try:
            _relation(conn, plan, report, test, unique_id, state, who, user, several, lock)
        except Exception as exc:
            _item_failed(report, state, before, _relation_what(models, unique_id, test), exc)
            report['not_attempted'] += [{'what': _relation_what(models, u, t)} for u, t, _ in planned['jobs'][k + 1:]]
            return
    state['next_job'] = len(planned['jobs'])


def _item_failed(report: dict, state: dict, before: int, what: str, exc: BaseException) -> None:
    """One item hit an unexpected error: stop. When its own write had gone through first, it is written, and listed as such (with what its report line
    could say), not as not written."""
    state['stopped'] = True
    if len(state['committed']) > before:
        element_id = state['committed'][-1]
        report['types' if element_id.startswith(TYPE_PREFIX) else 'relations'].append(_written_line(element_id))
        report['failed'].append({'what': what, 'reason': _failure(exc, written=True)})
    else:
        report['failed'].append({'what': what, 'reason': _failure(exc)})


def _written_line(element_id: str) -> dict:
    """The report line of a proposal that was written but whose own line could not be made: its name and that it is written, nothing read back."""
    english = element_id.partition(':')[2]
    if element_id.startswith(TYPE_PREFIX):
        return {'model': english, 'id': english, 'name': english, 'dataset': None, 'key': [], 'properties': [], 'codes': [], 'status': 'new', 'state': 'checked', 'key_rows': None, 'warnings': []}
    return {'id': english, 'model': None, 'from': None, 'to': None, 'from_column': None, 'to_column': None, 'cardinality': 'many_to_one', 'status': 'new', 'state': 'checked',
            'numbers': None, 'cardinality_holds': None, 'warnings': []}


def _finish(plan: dict, report: dict, stopped: bool) -> dict:
    """Phase two, last step: the report as it is answered, each list capped."""
    models = plan['models']
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
    return {'applied': False, 'stopped': stopped, 'manifest': {'schema_version': plan['version'], 'dbt_version': plan['dbt_version'], 'project': plan['project'], 'models': len(models), 'tests': len(plan['tests']),
                                           'duplicates': plan['duplicates'],
                                           'note': None if plan['version'] in KNOWN_VERSIONS else tr(f'这是 v{plan["version"]}，比这里核对过的 v1–v12 新：读不了的都列在跳过里', f'This is v{plan["version"]}, newer than the v1–v12 this reader was checked against: whatever could not be read is listed as skipped')},
            **report, 'more': more, 'limits': {'proposals': MAX_PROPOSALS, 'megabytes': MAX_MANIFEST_BYTES // 1024 // 1024}}


def _stopped_report(plan: dict, planned: dict, state: dict, exc: BaseException) -> dict:
    """Phase two failed outside one item (building the report, say): the report from what is already known, with a general entry for the failure and the
    relations not reached as not attempted. Plain lists and literals only."""
    report = planned['report']
    models = plan['models']
    lists = {k: list(report.get(k, [])) for k in ('types', 'relations', 'codes', 'unmatched_models', 'skipped', 'left_out', 'failed', 'not_attempted')}
    lists['failed'].append({'what': tr('导入', 'the import'), 'reason': _failure(exc, written=bool(state['committed']), general=True)})
    if not state.get('stopped'):   # the relations not reached (none when it was the report that failed)
        lists['not_attempted'] += [{'what': _relation_what(models, u, t)} for u, t, _ in planned['jobs'][state.get('next_job', 0):]]
    return {'applied': False, 'stopped': True, 'manifest': {'schema_version': plan.get('version'), 'dbt_version': plan.get('dbt_version'), 'project': plan.get('project'),
                                                           'models': len(models), 'tests': len(plan.get('tests', [])), 'duplicates': plan.get('duplicates', 0), 'note': None},
            **{k: v[:SHOWN] for k, v in lists.items()}, 'more': {k: max(0, len(v) - SHOWN) for k, v in lists.items()},
            'limits': {'proposals': MAX_PROPOSALS, 'megabytes': MAX_MANIFEST_BYTES // 1024 // 1024}}


def _model(conn, plan: dict, report: dict, state: dict, name: str, unique_ids: list[str], matched: list[str], tests_of: dict, who: str | None, user: dict | None, lock) -> None:
    """One dbt model, with the datasets of its name planned before any write (`matched`; its dataset in state['datasets']): its tests read, and a type
    proposed (or found already there, or skipped with the reason)."""
    skip = lambda model, what, reason: report['skipped'].append({'model': model, 'what': what, 'reason': reason})
    if len(unique_ids) > 1:
        skip(name, tr('模型', 'model'), tr(f'manifest 里有 {len(unique_ids)} 个模型都叫 {name}（不同的包或版本），不知道是哪一个', f'The manifest has {len(unique_ids)} models named {name} (other packages or versions), so it cannot tell which one'))
        return
    unique_id = unique_ids[0]
    if not matched:
        report['unmatched_models'].append(name)
        return
    if len(matched) > 1:
        skip(name, tr('模型', 'model'), tr(f'有 {len(matched)} 个数据集的名字和它只差大小写：{"、".join(matched)}', f'{len(matched)} datasets differ from its name only in letter case: {", ".join(matched)}'))
        return
    dataset = state['datasets'][unique_id]
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
            return
        state['type_of'][unique_id] = _content(existing)['english_name']
        report['types'].append(_type_line(conn, existing, name, 'already_there'))
        return
    same = [r for (e,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objtype:%' AND json_extract(content_json, '$.dataset') = ? ORDER BY element_id", (dataset['name'],))
            if (r := element_row(conn, e)) and _visible(conn, r, user)]
    if same:   # the dataset already has a type this person may see: that one stands for the model
        state['type_of'][unique_id] = _content(same[0])['english_name']
        report['types'].append(_type_line(conn, same[0], name, 'already_there'))
        return
    if not keys:
        skip(name, tr('对象类型', 'object type'), tr('测试里没有主键：没有哪一列同时有 unique 和 not_null 测试。复合主键或没测的主键不猜，请用“新建对象类型”自己选', 'No key in the tests: no column has both a unique and a not_null test. A key of several columns, or one with no tests, is not guessed; pick it with New object type'))
        return
    if len(keys) > 1:
        skip(name, tr('对象类型', 'object type'), tr(f'有几列都同时有 unique 和 not_null（{"、".join(keys)}），不替你选主键，请用“新建对象类型”自己选', f'Several columns have both unique and not_null ({", ".join(keys)}); the key is not picked for you. Pick it with New object type'))
        return
    if state['written'] >= MAX_PROPOSALS:
        report['left_out'].append({'what': tr(f'对象类型 {name}', f'object type {name}'), 'reason': _over_cap()})
        return
    tested = list(dict.fromkeys([keys[0], *(t['column'] for t in usable)]))
    values = {t['column']: t['kwargs'].get('values') for t in usable if t['kind'] == 'accepted_values' and isinstance(t['kwargs'].get('values'), list)}
    codes = [c for c in values if cols[c]['type'] in CODE_TYPES and cols[c]['counts']]
    payload = {'english_name': name, 'name': name, 'dataset': dataset['name'], 'key': [keys[0]],
               'properties': [{'column': c, **({'enum': True} if c in codes else {})} for c in tested]}
    try:
        made = _write(conn, lambda: create_type(conn, payload, who, user), type_id(name), who,
                      {'from': 'dbt manifest', 'model': unique_id, 'key_tests': ['unique', 'not_null'], 'manifest_version': plan['version']}, lock, state)
    except TypeRefused as exc:
        skip(name, tr('对象类型', 'object type'), str(exc))
        return
    state['written'] += 1
    state['type_of'][unique_id] = made['id']
    report['types'].append({**_type_line(conn, element_row(conn, type_id(made['id'])), name, 'new'), 'warnings': made['warnings']})
    for column, listed in values.items():
        report['codes'].append({'type': made['id'], 'column': column, 'values': [_code_text(v) for v in listed[:MAX_CODES]], 'code_column': column in codes,
                                'note': None if column in codes else tr('这一列在数据里不能当代码列（代码列要是整数或文本，取值不超过 20 个），只作为普通属性', 'This column cannot be a code column in the data (a code column is integer or text with at most 20 values), so it is a plain property')})


def _relation_jobs(conn, models: dict, tests_of: dict, datasets: dict) -> list[tuple]:
    """(model unique_id, relationships test, several) for each relationships test that can be tried, by model and column; `several`: its column points at
    several models, so each relation's name says which (orders_customer_id_customers). One on a column the dataset lacks is already listed as skipped."""
    jobs = []
    for unique_id in sorted(tests_of, key=lambda u: models[u]):
        if unique_id not in datasets:
            continue
        present = dataset_columns(conn, datasets[unique_id]['id'])
        readable = sorted((t for t in tests_of[unique_id] if t['kind'] == 'relationships' and t['namespace'] in (None, 'dbt') and not t['where'] and t['column'] in present),
                          key=lambda t: (t['column'], models[t['target']] if t['target'] else ''))
        targets: dict[str, set] = {}
        for test in readable:
            targets.setdefault(test['column'], set()).add(test['target'])
        jobs += [(unique_id, test, len(targets[test['column']]) > 1) for test in readable]
    return jobs


def _relation_what(models: dict, unique_id: str, test: dict) -> str:
    to_name = models[test['target']] if test['target'] else _ref_name(test['to_text']) or (test['to_text'] or '?')[:60]
    return f'relationships {models[unique_id]}.{test["column"]} → {to_name}'


def _over_cap() -> str:
    return tr(f'一次导入最多提出 {MAX_PROPOSALS} 项；再导入一次会接着提出剩下的', f'One import proposes at most {MAX_PROPOSALS}; import again to propose the rest')


def _type_line(conn, row: dict, model: str, status: str) -> dict:
    content = _content(row)
    anchors = json.loads(row['anchors_json']) if row['anchors_json'] else {}
    return {'model': model, 'id': content['english_name'], 'name': content['name'], 'dataset': content['dataset'], 'key': content['key'],
            'properties': [p['column'] for p in content['properties']], 'codes': [p['column'] for p in content['properties'] if p['enum']],
            'status': status, 'state': row['state'], 'key_rows': anchors.get('key_rows'), 'warnings': []}


def _relation(conn, plan: dict, report: dict, test: dict, unique_id: str, state: dict, who: str | None, user: dict | None, several: bool = False, lock=None) -> None:
    """One relationships test as a many-to-one relation from its model's type to the one its `to` names, called <model>_<column>, or
    <model>_<column>_<target> when the column has relationships tests to several models. A relation that already has the name
    is "already there" only when it joins the same ends; one between other ends is skipped, saying so."""
    models, type_of, datasets = plan['models'], state['type_of'], state['datasets']
    name, column, target = models[unique_id], test['column'], test['target']
    what = _relation_what(models, unique_id, test)
    skip = lambda reason: report['skipped'].append({'model': name, 'what': what, 'reason': reason})
    if target is None:
        skip(tr('看不出它指向哪个模型（指向 source 的不读）', 'Cannot tell which model it points at (one that points at a source is not read)'))
        return
    if unique_id not in type_of or target not in type_of:
        missing = name if unique_id not in type_of else models[target]
        skip(tr(f'这次没有 {missing} 的对象类型（没有对应的数据集，或上面跳过了）', f'There is no object type for {missing} in this import (no matching dataset, or it was skipped above)'))
        return
    field = test['kwargs'].get('field') if isinstance(test['kwargs'].get('field'), str) else None
    if field is None or field not in dataset_columns(conn, datasets[target]['id']):
        skip(tr(f'数据集 {datasets[target]["name"]} 里没有“{field}”这一列（列名要完全一样）', f'The dataset {datasets[target]["name"]} has no column "{field}" (column names must match exactly)'))
        return
    english = f'{name}_{column}_{models[target]}' if several else f'{name}_{column}'
    payload = {'english_name': english, 'name': english, 'from': type_of[unique_id], 'to': type_of[target], 'cardinality': 'many_to_one',
               'from_column': column, 'to_column': field}
    ends = {k: payload[k] for k in ('from', 'to', 'from_column', 'to_column')}
    existing = _existing(conn, RELATION_PREFIX, payload['english_name'])
    if existing is not None and _relation_visible(conn, existing, user) and {k: _content(existing)[k] for k in ends} != ends:
        held = _content(existing)
        skip(tr(f'已经有一个叫 {held["english_name"]} 的关系，连的是 {held["from"]}.{held["from_column"]} → {held["to"]}.{held["to_column"]}，不是这一条：这一条没有提出，请用“新建关系”另起名字',
                f'A relation named {held["english_name"]} already joins {held["from"]}.{held["from_column"]} → {held["to"]}.{held["to_column"]}, not these ends, so this one is not proposed. Make it with New relation under another name'))
        return
    if existing is None:
        existing = next((r for (e,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'relation:%' ORDER BY element_id")
                         if (r := element_row(conn, e)) and {k: _content(r)[k] for k in ends} == ends and _relation_visible(conn, r, user)), None)
    if existing is not None:
        if not _relation_visible(conn, existing, user):
            skip(_name_taken())
            return
        content = _content(existing)
        report['relations'].append({**{k: content[k] for k in ('from', 'to', 'from_column', 'to_column', 'cardinality')}, 'id': content['english_name'], 'model': name,
                                    'status': 'already_there', 'state': existing['state'], 'numbers': None, 'cardinality_holds': None, 'warnings': []})
        return
    if state['written'] >= MAX_PROPOSALS:
        report['left_out'].append({'what': tr(f'关系 {payload["english_name"]}', f'relation {payload["english_name"]}'), 'reason': _over_cap()})
        return
    try:
        made = _write(conn, lambda: create_relation(conn, payload, who, user), relation_id(payload['english_name']), who,
                      {'from': 'dbt manifest', 'model': unique_id, 'test': 'relationships', 'manifest_version': plan['version']}, lock, state)
    except TypeRefused as exc:
        skip(str(exc))
        return
    state['written'] += 1
    row = element_row(conn, relation_id(made['id']))
    n = made['numbers']   # the form's own check of it, on the full data: it is not run again for the report
    shown = None if limited_on(conn, row, user) else {'rows': n['rows'], 'matched': n['matched'], 'unmatched': n['unmatched'], 'empty': n['rows'] - n['matched'] - n['unmatched'], 'fan_keys': n['fan_keys']}
    report['relations'].append({**{k: payload[k] for k in ('from', 'to', 'from_column', 'to_column', 'cardinality')}, 'id': made['id'], 'model': name, 'status': 'new', 'state': row['state'],
                                'numbers': shown, 'cardinality_holds': None if shown is None else not (n['extra_rows'] or n['many_repeats']), 'warnings': made['warnings']})   # a row rule or a kept column limits them: no counts of the whole data; the relation's page shows theirs


def import_manifest(db_path: Path, payload: dict, who: str | None, user: dict | None, lock=None) -> dict:
    """POST /api/workspace/types/dbt-import {manifest: the file's text, apply: bool}. The file is read with no lock held. Apply: the import runs on the
    workspace, each proposal under `lock` (the one an upload takes) and in its own transaction, both let go between proposals. Preview: `lock` is held only
    while the workspace file is copied (the copy reads it; it takes no write lock on it); the import then runs on the copy, which is thrown away."""
    if user is not None and user['role'] not in ('builder', 'admin'):
        raise TypeRefused(tr('只有建设者和管理员能导入', 'Only builders and admins can import'), 403)
    plan = parse_manifest(payload.get('manifest'))
    apply = payload.get('apply') is True
    state = {'committed': []}   # what has been written: from the first entry on, the answer is a report, never "nothing was written"
    try:
        if apply:
            conn = open_workspace(db_path)
            try:
                return {**run_import(conn, plan, who, user, lock, state), 'applied': True}
            finally:
                conn.close()
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / 'workspace.sqlite'
            with lock or nullcontext():
                source, target = sqlite3.connect(str(db_path)), sqlite3.connect(str(copy))
                try:
                    source.backup(target)
                finally:
                    target.close()
                    source.close()
            conn = open_workspace(copy)
            try:
                return run_import(conn, plan, who, user, None, state)
            finally:
                conn.close()
    except Exception as exc:
        if state['committed']:   # cannot happen through run_import, whose phase two answers a report; kept so that "nothing was written" is never said after a write
            return _last_report(state['committed'], apply, exc)
        if isinstance(exc, TypeRefused):
            raise
        raise TypeRefused(tr(f'读这个 manifest 时出了错（{type(exc).__name__}），什么都没有写入', f'Reading this manifest failed ({type(exc).__name__}); nothing was written'), 400) from None


def _last_report(committed: list[str], apply: bool, exc: BaseException) -> dict:
    """The report when even the stopped report could not be made: the written proposals by name, and the failure. Literals only."""
    lines = [_written_line(e) for e in committed]
    empty = {k: [] for k in ('codes', 'unmatched_models', 'skipped', 'left_out', 'not_attempted')}
    failed = [{'what': tr('导入', 'the import'), 'reason': _failure(exc, written=True, general=True)}]
    return {'applied': apply, 'stopped': True, 'manifest': {}, 'types': [x for x in lines if 'dataset' in x], 'relations': [x for x in lines if 'dataset' not in x], 'failed': failed,
            **empty, 'more': {k: 0 for k in ('types', 'relations', 'codes', 'unmatched_models', 'skipped', 'left_out', 'failed', 'not_attempted')},
            'limits': {'proposals': MAX_PROPOSALS, 'megabytes': MAX_MANIFEST_BYTES // 1024 // 1024}}
