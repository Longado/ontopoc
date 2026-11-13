"""Local-only upload API: a business file in, a verified company ontology and its evaluation out."""
import argparse
import base64
import binascii
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import threading
from urllib.parse import parse_qs, unquote, urlsplit
import uuid

from ontology_poc_generator.company_documents import DOCUMENT_SUFFIXES, build_and_evaluate_document, load_document_file
from ontology_poc_generator.org_documents import build_and_evaluate_org, org_mermaid
from ontology_poc_generator.company_ontology import build_and_evaluate, build_company_ontology
from ontology_poc_generator.code_meanings import check_enum, code_columns, draft_meanings, meanings_of, merge_enum
from ontology_poc_generator.answer_checks import choose_rows, definition_catalog, definition_check, filter_conditions, refusal, upstream_problems, with_upstream
from ontology_poc_generator.accounts import two_person
from ontology_poc_generator.actor import set_actor
from ontology_poc_generator.named_views import StaleProposal, proposed_views, compiled_views, definitions_signature, drop_views_except, name_views, read_views, save_definition, sync_views, table_columns, view_anchor_now, view_rowids, views_of_run
from ontology_poc_generator.pipelines import ROW_CAP, run_pipeline, workspace_datasets, workspace_views
from ontology_poc_generator.anchors import check_code, check_relation, check_view, code_anchor, relation_anchor, review_items, view_anchor, stored as stored_anchors, waiting as waiting_change
from ontology_poc_generator.repeated_keys import check_rule, repeated_keys, settled_by_latest, unmet
from ontology_poc_generator.workspace_store import (
    RowCountMismatch, SelfConfirmation, check_bundle, describes_rows, element_contents, element_ids, element_rejected, element_rows, element_state_writes, log_write, open_workspace, set_element_states, store_anchors)
from ontology_poc_generator.company_sources import DEFAULT_PURPOSE, MAX_BYTES, TABLE_SUFFIXES, SourceFileError, load_table_file, load_table_files
from ontology_poc_generator.model_gateway import OpenAICompatibleGateway
from ontology_poc_generator.model_preview import model_preview
from ontology_poc_generator.agent_harness import LoggedGateway
from ontology_poc_generator.name_variants import propose_name_variants
from ontology_poc_generator.object_rows import find_instances, neighbourhood, object_rows
from ontology_poc_generator.review_stack import check_mode, relation_band
from ontology_poc_generator.open_items import check_answers, code_meaning_items, linked_cells, open_items, split_answers, with_replies
from ontology_poc_generator.ontology_card import NO_CARD, build_card, check_cells, live_cells, with_changes
from ontology_poc_generator.public_ontology import build_graph, normalize_proposal
from ontology_poc_generator.relation_suggestions import suggest_relations
from ontology_poc_generator.rule_discovery import check_rules, discover_rules
from ontology_poc_generator.versions import version_diff
from ontology_poc_generator.field_descriptions import MAX_DESCRIPTION, MAX_LABEL, draft_descriptions
from ontology_poc_generator.handover_form import handover_form
from ontology_poc_generator.object_forms import form_files
from ontology_poc_generator.pipeline_spec import pipeline_files, pipeline_spec
from ontology_poc_generator.ttl_export import ttl_files
import io
import zipfile
from urllib.parse import quote as url_quote
from ontology_poc_generator.ontology_acceptance import check_acceptance, parse_acceptance, record_confirmed
from ontology_poc_generator.ontology_compare import ReferenceFileError, compare_ontologies, parse_reference
from ontology_poc_generator.ontology_confirm import confirmed_reference, element_changes, prefill_from_reference, without_wrong
from ontology_poc_generator.ontology_library import import_definition, library_catalogue, library_definition
from ontology_poc_generator.ontology_reference import compare_definition, local_schema, run_fingerprint, stale_reasons
from ontology_poc_generator.ontology_questions import QUESTION_PROMPT_VERSION, answer_query, ask_questions
from ontology_poc_generator.workspace_questions import QaRefused, ask as ask_workspace, history as question_history, reopen as reopen_question, scope_line
from ontology_poc_generator.public_ontology import MAX_MODELER_ATTEMPTS
from ontology_poc_generator.derived_measures import parse_derived
from ontology_poc_generator.ontology_stability import STABILITY_RUNS, stability_of
from ontology_poc_generator.recognition import model_failure_text
from ontology_poc_generator.relation_checks import unmatched_answer, with_relation_gaps
from ontology_poc_generator.auth_http import LOOPBACK, Gate
from ontology_poc_generator.dataset_readers import dataset_readers
from ontology_poc_generator.workspace_datasets import UploadRefused, dataset_csv, dataset_detail, delete_dataset, list_datasets, upload as upload_datasets
from ontology_poc_generator.workspace_tasks import list_tasks
from ontology_poc_generator.object_types import TypeRefused, _type_row, confirm_element, create_type, key_preview, list_types, propose_meanings, type_detail, type_log, type_objects, update_type
from ontology_poc_generator.object_type_suggest import suggest_types
from ontology_poc_generator.object_relations import (
    confirm_relation, create_relation, list_relations, relation_columns, relation_detail, relation_log, update_relation)
from ontology_poc_generator.review_queue import confirm_item, queue, send_back
from ontology_poc_generator.type_access import AccessRefused, access_table, dataset_hidden, set_access, set_values_hidden

ROOT = Path(__file__).resolve().parents[2]
KEPT_VIEW_CONTEXTS = 6   # runs whose views, row counts and graphs built from them are kept until a definition changes
KEPT_RUNS_IN_MEMORY = 8   # runs whose rows and graph stay in memory; the least recently used is dropped and read again when asked for
MAX_BODY = MAX_BYTES * 4 // 3 + 4096  # base64 grows the file by a third, plus the JSON around it
LOGGED_WRITES = {'/api/ontology/acceptance': 'acceptance', '/api/ontology/rules': 'rules', '/api/ontology/form': 'form', '/api/ontology/derived': 'derived',
                 '/api/ontology/reference/confirm': 'reference', '/api/ontology/card': 'card'}   # library/import only reads a file and keeps nothing
SECURITY_HEADERS = (('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'),
                    ('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'"))   # the service answers JSON and downloads, never a page
MAX_BULK = 200   # relations approved in one request: far above what a run has


class RunChanged(ValueError):
    """What the person was shown (the clean band, the run's confirmations) changed under them before the write; nothing was written."""


SAVED_NAME = re.compile(r'^\d{8}T\d{6,12}Z-[0-9a-f]{8}\.json$')
JOB_ID = re.compile(r'^[0-9a-f]{12}$')
NO_KEY = '本机服务没有模型凭据：设置 DEEPSEEK_API_KEY 后重启 ontology_server。'
INTERRUPTED = '建模服务在这次建模途中重启过，这次作业中断了。请重新上传文件。'


def gateway_from_env():
    key = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('EIP_MODEL_API_KEY')
    if not key:
        return None
    return OpenAICompatibleGateway(api_base='https://api.deepseek.com', api_key=key,
                                   model=os.environ.get('EIP_MODEL_NAME', 'deepseek-flash'), timeout_seconds=180, temperature=0)


def code_fingerprint(code_dir: Path) -> str:
    """What the service's Python files hold right now. Taken once at start and again on every health check: when the
    two differ, the files changed after the service started and it is still running the old code."""
    digest = hashlib.sha256()
    for path in sorted(code_dir.glob('*.py')):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def write_run(path: Path, run: dict) -> None:
    """A run file written whole or not at all: to a file of its own beside it, then renamed over it, so a reader of the
    file (every page of the run) never meets half of it, and two saves never write into the same file."""
    part = path.with_name(f'{path.name}.{uuid.uuid4().hex[:8]}.part')
    part.write_text(json.dumps(run, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    os.replace(part, path)


def close_to_others(folder: Path) -> None:
    """The folder and everything under it readable by this account only: folders 0700, files 0600 (customer rows, every prompt, the workspace). Links are left alone."""
    for path in [folder, *folder.rglob('*')]:
        if not path.is_symlink():
            mode = 0o700 if path.is_dir() else 0o600
            if path.stat().st_mode & 0o777 != mode:
                path.chmod(mode)


def make_server(port=8767, gateway=None, output_dir: Path = ROOT / 'output/ontology-runs', code_dir: Path = Path(__file__).parent,
                no_auth: bool = False, origins=(), trusted_proxies=None):
    """no_auth: no sign-in, every request is the local admin (trials and tests only). origins: the addresses, besides the service's own, that
    people reach it at: a proxy's https address, or a dev server."""
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)   # the data holds password hashes, every prompt sent to the model and the people's names
    close_to_others(output_dir)   # a folder made before this was a rule may be open to every account on the machine
    running = code_fingerprint(code_dir)
    if gateway is not None:   # every model call, from any agent, leaves one line beside the runs
        gateway = LoggedGateway(gateway, output_dir / 'model_calls.jsonl')
    jobs, jobs_lock = {}, threading.Lock()
    # one run file is read, changed and written back by several endpoints; this keeps two of them from overwriting each other
    runs_lock = threading.Lock()
    jobs_dir = output_dir / 'jobs'
    graphs, graphs_lock = OrderedDict(), threading.Lock()   # the most recently used kept runs: rows, graph without a choice, and the graph for the repeated-key rules now chosen

    def memory_key(result):
        """Judgements are kept per file, or per line of versions once a person says a file is the next version of
        another: then the line's first file names them all. An organisation map of a file is judged apart from its
        plain reading, so the two never share a confirmation."""
        return result.get('lineage') or (f"org-{result['file']['sha256']}" if result.get('mode') == 'org' else result['file']['sha256'])

    def previous_version(payload):
        """The kept run the person says this upload is the next version of, or None."""
        name = payload.get('previous')
        if name is None:
            return None
        if not isinstance(name, str) or not SAVED_NAME.match(name) or not (output_dir / name).exists() \
                or not (output_dir / name.replace('.json', '.bundle.json')).exists():
            raise ValueError('previous 要写一次保存过的运行名')
        return name

    def form_path(result):
        return output_dir / 'forms' / f"{memory_key(result)}.json"

    def form_state(result):
        """The object form columns a person (or the drafting agent) wrote for this file, for the objects and fields there are."""
        path = form_path(result)
        if not path.exists():
            return None
        stored = json.loads(path.read_text(encoding='utf-8'))
        fields = {t['type']: {f['path'] for f in t['fields']} for t in (result['evaluation'].get('handover') or {}).get('types', [])}
        return {**stored, 'types': {k: {**v, 'fields': {f: x for f, x in v['fields'].items() if f in fields[k]}}
                                    for k, v in stored['types'].items() if k in fields}}

    def parse_form(form, handover):
        """A form sent by the page: every object and field must exist, every text short, the display field its own."""
        fields = {t['type']: {f['path'] for f in t['fields']} for t in handover.get('types', [])}
        if not isinstance(form, dict) or not isinstance(form.get('types'), dict):
            raise ValueError('form 要写 {"types": {对象: …}}')
        out = {}
        for key, t in form['types'].items():
            if key not in fields or not isinstance(t, dict):
                raise ValueError(f'本体里没有对象 {key}')
            def text(v, limit, what):
                if v is None or (isinstance(v, str) and len(v) <= limit):
                    return v
                raise ValueError(f'{key} 的{what}太长或不是文字')
            if t.get('display_field') not in (None, *fields[key]):
                raise ValueError(f"{key} 的展示字段 {t.get('display_field')} 不是它的字段")
            entry = {'label': text(t.get('label'), MAX_LABEL, '中文名'), 'description': text(t.get('description'), MAX_DESCRIPTION, '描述'),
                     'display_field': t.get('display_field'), 'drafted': bool(t.get('drafted')), 'fields': {}}
            for path, f in (t.get('fields') or {}).items():
                if path not in fields[key] or not isinstance(f, dict):
                    raise ValueError(f'{key} 没有字段 {path}')
                entry['fields'][path] = {'label': text(f.get('label'), MAX_LABEL, f'字段 {path} 的中文名'),
                                         'description': text(f.get('description'), MAX_DESCRIPTION, f'字段 {path} 的描述'), 'drafted': bool(f.get('drafted'))}
            out[key] = entry
        return {'types': out}

    def derived_of(key):
        """The derived measures a person confirmed for this file (its line of versions), oldest first."""
        path = output_dir / 'derived' / f'{key}.json'
        return json.loads(path.read_text(encoding='utf-8'))['measures'] if path.exists() else []

    def card_file(key):
        """What was said on this file's data-meaning card and on its open items: {cells, items, history}."""
        path = output_dir / 'cards' / f'{key}.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'cells': {}, 'items': {}, 'history': []}

    def card_cells(result, bundle, graph=None, key=None):
        """What the questions are given of this file's card: the answers it still has a place for (ontology_card.live_cells).
        The file keeps the others. `key` names another line's card for a run that is not saved yet."""
        return live_cells(card_file(key or memory_key(result))['cells'], result['ontology'], bundle,
                          (result.get('confirmation') or {}).get('decisions'), graph)

    def reviewed_acceptance(result, bundle, items):
        # A rerun carries the previous human decisions as suggestions until reviewed again.
        # Those rejected objects/relations must not silently become passing acceptance paths.
        decisions = (result.get('confirmation') or {}).get('decisions')
        if decisions is None:
            decisions = (result['evaluation'].get('reference') or {}).get('suggested')
        return check_acceptance(without_wrong(result['ontology'], decisions), bundle, items,
                                derived=derived_of(memory_key(result)), snapshot_ontology=result['ontology'], card=card_cells(result, bundle))

    def card_run(name):
        """(run, rows, graph) as kept() gives them, for a table run whose ontology passed verification; None for a document
        or one that did not, which have no card; FileNotFoundError when there is no such run."""
        path = output_dir / name
        if not SAVED_NAME.match(name) or not path.exists():
            raise FileNotFoundError(name)
        run = json.loads(path.read_text(encoding='utf-8'))
        if run['ontology']['status'] != 'auto_built_verified' or run['file'].get('kind') == 'document':
            return None
        return kept(name)

    def workspace_run(name):
        """(run, rows, graph) as card_run gives them; for a table run whose draft was blocked, its rows and no graph: its tables
        are stored in the workspace all the same, so its code columns, their meanings and its views can be worked on. None for
        a document or a run whose rows were not kept."""
        found = card_run(name)
        if found is not None or not (output_dir / name.replace('.json', '.bundle.json')).exists():
            return found
        result = json.loads((output_dir / name).read_text(encoding='utf-8'))
        if result['file'].get('kind') == 'document' or not (result.get('data_checks') or {}).get('tables'):
            return None
        return result, with_meanings(result, json.loads((output_dir / name.replace('.json', '.bundle.json')).read_text(encoding='utf-8'))), None

    def blocked_text(result, what):
        """Why a draft that did not pass the checks cannot do `what`, with the checks it failed (the first two)."""
        errors = [f'{e["code"]}: {e["message"]}' for e in (result['ontology'].get('verification') or {}).get('errors', [])[:2]]
        return f'本体没有通过结构核验，{what}' + (f'。没通过的核验：{"；".join(errors)}' if errors else '')

    code_cache, code_lock = {}, threading.Lock()   # a run's code columns are worked out once: its rows never change

    def code_candidates(result, bundle):
        """The columns of a run that look like code lists, leaving out the ones the draft uses to identify objects."""
        identity = frozenset((pop['source'], path) for t in normalize_proposal(result['ontology'])['object_types']
                             for pop in t['populated_from'] for path in pop['identity'].values())
        if 'saved_as' not in result:   # a run being built: not kept yet, so nothing to cache it under
            return code_columns(bundle, identity)
        with code_lock:
            if result['saved_as'] not in code_cache:
                code_cache[result['saved_as']] = code_columns(bundle, identity)
            return code_cache[result['saved_as']]

    def code_state(result, bundle):
        """(code columns still on offer, the meanings a person confirmed by field): a column a person said is not a code is gone."""
        conn = open_workspace(output_dir / 'workspace.sqlite')
        try:
            prefix = f'property:{memory_key(result)}:'
            rejected = element_rejected(conn, prefix)
            return [p for p in code_candidates(result, bundle) if p['field'] not in rejected], element_contents(conn, prefix)
        finally:
            conn.close()

    def code_drafts(result):
        """The model's guesses at what codes mean, kept with the file: {item id: {value: guess}}."""
        path = output_dir / 'code_meanings' / f'{memory_key(result)}.json'
        return json.loads(path.read_text(encoding='utf-8'))['columns'] if path.exists() else {}

    def repeat_rules(result):
        """How a person said the rows of a repeated key are read, by "<object type>.<table>"."""
        conn = open_workspace(output_dir / 'workspace.sqlite')
        try:
            return element_contents(conn, f'repeat_rule:{memory_key(result)}:')
        finally:
            conn.close()

    def with_rules(result, bundle):
        """The bundle as anything that picks rows should see it: with the rules chosen for repeated keys, which build_graph applies."""
        return {**bundle, 'repeat_rules': repeat_rules(result)}

    def code_waiting(result):
        """{field: {'labels': {code: meaning}, 'values': {code: {'label', 'description'}}, 'changes': [what changed]}} for the code
        meanings of this file that wait for a second look (anchors.py): kept, not counted as confirmed."""
        conn = open_workspace(output_dir / 'workspace.sqlite')
        try:
            rows = element_rows(conn, f'property:{memory_key(result)}:', 'checked')
        finally:
            conn.close()
        out = {}
        for field, row in rows.items():
            values = {e['value']: {'label': e['label'], 'description': e.get('description') or ''} for e in (row['content'] or {}).get('values', []) if e.get('label')}
            out[field] = {'labels': {v: x['label'] for v, x in values.items()}, 'values': values, 'changes': (row['review'] or {}).get('changes', [])}
        return out

    def with_meanings(result, bundle):
        """The bundle as every reader of rows should see it: with the rules for repeated keys, and with what each code
        column's values mean, confirmed or not (and which meanings wait for a second look)."""
        profiles, enums = code_state(result, bundle)
        return {**with_rules(result, bundle), 'meanings': meanings_of(profiles, enums), 'waiting': code_waiting(result)}

    def stored_tables(conn, result):
        """{table: {'table', 'rows', 'columns'}} of the dataset versions this run stored in the workspace."""
        return workspace_datasets(conn, {t['dataset']: t['dataset_id'] for t in (result.get('data_checks') or {}).get('tables', []) if t.get('status') == 'ok'})

    def run_id(name):
        """What a run's views are named after in the workspace file: views belong to one run, not to the file's version line."""
        return hashlib.sha1(name.encode()).hexdigest()[:8]

    def readonly_workspace():
        return sqlite3.connect(f'file:{output_dir / "workspace.sqlite"}?mode=ro', uri=True)   # reading views needs no write to the file

    views_cache, views_cache_lock = OrderedDict(), threading.Lock()   # what was worked out from a run's views, kept until a definition or a table changes

    def view_context(result):
        """The run's views as a read of the workspace file sees them, with their row counts, and what was worked out from them
        (the rows each view keeps, the graphs built from them): kept per run and per version of every definition and table,
        so a read that finds nothing changed costs one small query. Raises when the workspace cannot be read."""
        key, rid = memory_key(result), run_id(result['saved_as'])
        conn = readonly_workspace()
        try:
            tables = stored_tables(conn, result)
            signature = (rid, definitions_signature(conn, key), tuple(sorted((n, d['table']) for n, d in tables.items())))
            with views_cache_lock:
                if signature in views_cache:
                    views_cache.move_to_end(signature)
                    return views_cache[signature]
            views = views_of_run(conn, key, rid, result['ontology'], tables)
        finally:
            conn.close()
        context = {'signature': signature, 'views': views, 'view_tables': table_columns(tables), 'tables': tables, 'rowids': {}, 'graphs': {}}
        with views_cache_lock:
            views_cache[signature] = context
            while len(views_cache) > KEPT_VIEW_CONTEXTS:
                views_cache.popitem(last=False)
        return context

    def view_state(result):
        """The run's confirmed definitions as views, each with its SQL and row count, read without writing to the workspace
        file; with the reason when they could not be read (the page shows that beside the lists, the rest still works)."""
        try:
            context = view_context(result)
            conn = readonly_workspace()
            try:
                waiting = proposed_views(conn, memory_key(result))
            finally:
                conn.close()
            return {'views': context['views'], 'view_tables': context['view_tables'], 'proposed_views': waiting}
        except Exception as exc:
            return {'views': [], 'view_tables': [], 'proposed_views': [], 'views_error': f'视图没有读出来：{type(exc).__name__}: {exc}'[:300]}

    def rows_kept(result, context, view):
        """The positions of the rows a view keeps in its table, read once per version of the definitions."""
        with views_cache_lock:
            if view['name'] in context['rowids']:
                return context['rowids'][view['name']]
        conn = readonly_workspace()
        try:
            read_views(conn, run_id(result['saved_as']), context['views'])
            rows = view_rowids(conn, view)
        finally:
            conn.close()
        with views_cache_lock:
            context['rowids'][view['name']] = rows
        return rows

    def views_signature(result):
        """What the confirmed views and the stored tables of a run are at (None when they cannot be read): a result worked out
        with the views is worked out again when it changes."""
        try:
            return view_context(result)['signature']
        except Exception:
            return None

    def view_subsets(result, source):
        """{view name: positions (from 1) of the rows the table's confirmed views keep}, for the name checks: which confirmed view a
        statistic written in another table was worked out over. {} when the views cannot be read or the stored table is not this
        run's rows (the name check then says what it found on the whole table)."""
        try:
            context = view_context(result)
            return {v['name']: set(rows_kept(result, context, v)) for v in context['views']
                    if v['state'] == 'confirmed' and v['source'] == source and v['kind'] != 'labels'}
        except Exception:
            return {}

    def make_answerer(result, bundle, reviewed, derived, cells, graph=None):
        """fn(query, question, used=None, check=True, told=None) -> answer, for this run, with `.definitions`: what a person confirmed, as the
        model is told it. Each answer is worked out from the rows its definitions keep: a table with a "current" view (a confirmed
        keep-latest rule) always, and a view a person named when the model says the question uses it; the answer says which views
        it used. `used` is the model's `definitions_used`: a definition the question refers to that the query did not apply is
        refused and says which (see answer_checks; `check=False` skips it, for a question a person changed by hand); a filter
        that found nothing in a table that was damaged upstream says that and not "no data".
        When the views cannot be read the tables' rows are used and every answer says so."""
        meanings = bundle.get('meanings')
        relations = [r for r in (result.get('data_checks') or {}).get('relations') or [] if r['key'] in {x['key'] for x in reviewed['relations']}]   # what the relation check found on the rows stored at upload, for the relations nobody judged wrong
        meaning_key = json.dumps([meanings, bundle.get('repeat_rules')], sort_keys=True, ensure_ascii=False)
        try:   # the workspace file is a second store: failing to read it must not stop an answer that the rows alone can give
            context, unread = view_context(result), None
        except Exception as exc:
            context, unread = None, f'视图没有读出来，这次读的是原表的行：{type(exc).__name__}: {exc}'[:300]

        def rows_of(applied):
            """(bundle, graph) holding only the rows the views in `applied` keep, per table (a row all of them keep)."""
            names = tuple(sorted(v['name'] for v in applied))
            with views_cache_lock:
                if (names, meaning_key) in context['graphs']:
                    return context['graphs'][(names, meaning_key)]
            kept_rows = {}
            for v in applied:
                rows = set(rows_kept(result, context, v))
                kept_rows[v['source']] = rows if v['source'] not in kept_rows else kept_rows[v['source']] & rows
            for table in kept_rows:
                if len(bundle['sources'][table]['records']) != context['tables'][table]['rows']:
                    raise ValueError(f'「{table}」表在工作区里是 {context["tables"][table]["rows"]} 行，这次运行的数据是 {len(bundle["sources"][table]["records"])} 行，对不上')
            chosen = choose_rows(reviewed, bundle, kept_rows)
            reading = {**bundle, 'sources': {**bundle['sources'], **{t: {**bundle['sources'][t], 'records': r} for t, r in chosen.items()}}}
            built = (reading, build_graph(result['ontology'], reading))
            with views_cache_lock:
                context['graphs'][(names, meaning_key)] = built
            return built

        def answer(query, question, used=None, check=True, told=None):
            problem = unread
            views = context['views'] if context else []
            checked = definition_check(question, query, reviewed, views, meanings, used, told, bundle.get('waiting')) if check and isinstance(query, dict) else {'unmet': [], 'apply': [], 'understood': []}
            if checked['unmet']:
                return {**refusal(checked['unmet']), 'understood': checked['understood']}
            broken = [f'「{v["name"]}」{v["why"]}' for v in views if v['kind'] == 'current' and v['state'] != 'confirmed']
            if broken and not problem:   # the rule still picks the rows (by its own code), but the view that should say so cannot be used
                problem = f'视图用不了，这次读的是原表的行，由确认过的规则取最新：{"；".join(broken)}'[:300]
            applied = [v for v in views if v['kind'] == 'current' and v['state'] == 'confirmed'] + checked['apply']
            reading, reading_graph = bundle, graph
            if applied:
                try:
                    reading, reading_graph = rows_of(applied)
                except (sqlite3.Error, ValueError, KeyError) as exc:   # the views chose rows that this run's rows do not line up with
                    applied, problem = [], f'视图没有用上，这次读的是原表的行：{exc}'[:300]
            now = answer_query(reviewed, reading, query, question, reading_graph, derived, cells)
            if now.get('status') == 'no_data':   # only a filter that found nothing is looked at, and rows are read only then
                records = {t: v['records'] for t, v in bundle['sources'].items()}
                now = with_upstream(now, upstream_problems(result.get('data_checks'), filter_conditions(reviewed, query, meanings), bundle.get('repeat_rules'), records))
            now = name_views(now, query, reviewed, applied, problem)
            now = with_relation_gaps(now, query, reviewed, relations)
            return {**now, 'understood': checked['understood']} if checked['understood'] else now
        answer.definitions = definition_catalog(meanings, context['views'] if context else [])
        answer.unmatched = lambda key: unmatched_answer(reviewed, relations, key)
        return answer

    def sync_run_views(result):
        """After a definition changed: the file's views for this run as the definitions now say, and no views of a run whose
        file is gone. None when it worked, else what went wrong (the definition itself is kept)."""
        try:
            conn = open_workspace(output_dir / 'workspace.sqlite')
            try:
                tables = stored_tables(conn, result)
                refused = sync_views(conn, run_id(result['saved_as']), compiled_views(conn, memory_key(result), run_id(result['saved_as']), result['ontology'], tables))
                drop_views_except(conn, {run_id(p.name) for p in output_dir.glob('*.json') if SAVED_NAME.match(p.name)})
            finally:
                conn.close()
            return '；'.join(f'{n}：{e}' for n, e in refused.items()) or None
        except Exception as exc:
            return f'{type(exc).__name__}: {exc}'[:300]

    views_warning = lambda problem: f'已记下，但工作区里的视图没有更新：{problem}' if problem else None

    def settled_definitions(result, profiles, enums, rules, open_ids):
        """What a person decided through the code-meaning and repeat-rule endpoints and no item asks about any more, as the list of
        decisions shows it: {id, kind, ask, answer: {says, text, by, at, mode}}. The same rows the stack counts as decided."""
        out = []
        for p in profiles:
            kept = enums.get(p['field'])
            if p['id'] not in open_ids and kept:
                out.append({'id': p['id'], 'kind': 'code_meaning', 'ask': f'「{p["source"]}」的「{p["column"]}」是代码',
                            'answer': {'says': '含义已确认', 'text': '、'.join(f'{e["value"]} = {e["label"]}' for e in kept['values'] if e.get('label')),
                                       'by': kept['confirmed_by'], 'at': kept['confirmed_at'], 'mode': kept.get('mode')}})
        for key, rule in rules.items():
            if f'repeated_key:{key}' not in open_ids:
                said = {'keep_both': '每一行都留', 'data_error': '当作数据错误'}.get(rule['rule'], f'只留「{rule.get("column")}」最新的一行')
                out.append({'id': f'repeated_key:{key}', 'kind': 'repeated_key', 'ask': f'{key.partition(".")[2]}表重复的编号怎么算',
                            'answer': {'says': said, 'text': '', 'by': rule['confirmed_by'], 'at': rule['confirmed_at'], 'mode': rule.get('mode')}})
        conn = open_workspace(output_dir / 'workspace.sqlite')
        try:
            said_no = element_rows(conn, f'property:{memory_key(result)}:', 'rejected')
            approved = element_rows(conn, f'relation:{memory_key(result)}:', 'confirmed')
        finally:
            conn.close()
        p = normalize_proposal(result['ontology'])
        label = lambda key: next((t.get('label') or key for t in p['object_types'] if t['key'] == key), key)
        for r in (r for r in p['relations'] if ((approved.get(r['key']) or {}).get('content') or {}).get('mode') == 'bulk'):   # judged right with others in one action: the one judgement the person did not make on a card
            row = approved[r['key']]
            out.append({'id': f'relation:{r["key"]}', 'kind': 'relation', 'ask': f'关系 {label(r["from"])} {r.get("label") or r["key"]} {label(r["to"])}',
                        'answer': {'says': '判对', 'text': '', 'by': row['confirmed_by'], 'at': row['confirmed_at'], 'mode': 'bulk'}})
        for field, row in said_no.items():
            out.append({'id': f'code_meaning:{field}', 'kind': 'code_meaning', 'ask': f'「{field.partition(".")[0]}」的「{field.partition(".")[2]}」是代码',
                        'answer': {'says': '不是代码', 'text': '', 'by': row['confirmed_by'], 'at': row['confirmed_at'], 'mode': (row['content'] or {}).get('mode')}})
        return out

    def bulk_band_of(result, newer):
        """What can be approved together (review_stack.relation_band), worked out from a run as it is kept: nothing on a run that a newer
        version of the file has replaced, where definitions are changed, and nothing on a draft that did not pass verification."""
        if newer or result['ontology']['status'] != 'auto_built_verified':
            return []
        p = normalize_proposal(result['ontology'])
        names = {t['key']: t.get('label') or t['key'] for t in p['object_types']}
        label = lambda key: names.get(key, key)
        relation_name = lambda r: next((f'{label(x["from"])} {x.get("label") or x["key"]} {label(x["to"])}' for x in p['relations'] if x['key'] == r['key']), r['key'])
        return relation_band((result.get('data_checks') or {}).get('relations') or [], (result.get('confirmation') or {}).get('decisions'), label, relation_name)

    def bulk_judged(result):
        """The relations of this run judged right in a bulk approval, as {key: the kept definition with who confirmed it}."""
        conn = open_workspace(output_dir / 'workspace.sqlite')
        try:
            kept = element_contents(conn, f'relation:{memory_key(result)}:')
        finally:
            conn.close()
        here = {r['key'] for r in result['ontology'].get('relations') or []}
        return {k: c for k, c in kept.items() if c.get('mode') == 'bulk' and k in here}

    def code_reply(found):
        """The open items and answered ones, with what each code column's values mean (the page shows them beside answers and fields),
        and the named views the confirmed definitions make."""
        card, items, answered = card_for(found)
        if found is None:
            return {'items': items, 'answered': answered, 'settled': [], 'bulk': [], 'meanings': {}, 'views': [], 'view_tables': [], 'row_cap': ROW_CAP, 'repeat_rules': {}, 'review': [], 'newer': None}
        profiles, enums = code_state(found[0], found[1])
        newer = newer_run(found[0])   # the run of this line that is more recent than the one shown: definitions are changed there
        rules = repeat_rules(found[0])
        return {'items': items, 'answered': answered, 'settled': settled_definitions(found[0], profiles, enums, rules, {i['id'] for i in items}),
                'bulk': bulk_band_of(found[0], newer),
                'meanings': meanings_of(profiles, enums), 'row_cap': ROW_CAP, 'repeat_rules': rules,
                'review': review_list(found[0], newer), 'newer': newer, **view_state(found[0])}

    def code_labels(row):
        return {e['value']: e['label'] for e in (row['content'] or {}).get('values', []) if e.get('label')}

    def key_columns(ontology, source):
        """The identity columns of the type whose rows `source` describes: what tells one row of the table from another (None: none)."""
        own = describes_rows(ontology)
        for t in normalize_proposal(ontology)['object_types']:
            for pop in t['populated_from']:
                if pop['source'] == source and pop['transform'] == 'none' and not pop.get('where') and own(t['key'], source):
                    return [pop['identity'][k] for k in sorted(pop['identity'])]
        return None

    def earlier_of(previous):
        """(run, rows) of the kept table run a new version is the next of, for what confirmations made before anchors existed were most
        likely confirmed on; None when there is none or its rows are not kept."""
        if not previous:
            return None
        path = output_dir / previous.replace('.json', '.bundle.json')
        run = json.loads((output_dir / previous).read_text(encoding='utf-8'))
        if run['file'].get('kind') == 'document' or not path.exists():
            return None
        return {**run, 'saved_as': previous}, json.loads(path.read_text(encoding='utf-8'))

    def recheck_data_anchors(result, bundle, key, earlier=None):
        """A new version of a file whose definitions were confirmed on the one before: each code meaning and repeat rule is looked at
        again on the rows that came in (anchors.py). One whose anchor is broken moves to "checked" with what changed, so that
        nothing below (the questions of this upload included) reads it as confirmed. Run before the questions are answered. A
        meaning confirmed before anchors existed has none: they are worked out from the earlier run's rows (`earlier`) and kept,
        so that the next version is held against them too. A draft that did not pass verification has no repeated keys to look at;
        its code meanings are looked at all the same."""
        conn = open_workspace(output_dir / 'workspace.sqlite')
        try:
            verified = result['ontology']['status'] == 'auto_built_verified'
            codes, rules = element_rows(conn, f'property:{key}:', 'confirmed'), element_rows(conn, f'repeat_rule:{key}:', 'confirmed') if verified else {}
            against, flips = bundle['file']['name'], []
            if codes:
                profiles = {p['field']: p for p in code_candidates(result, bundle)}
                was = {p['field']: p for p in code_candidates(*earlier)} if earlier and any(r['anchors'] is None for r in codes.values()) else {}
                for field, row in codes.items():
                    table = field.partition('.')[0]
                    legacy = row['anchors'] is None
                    if table not in bundle['sources'] or (legacy and (field not in was or table not in earlier[1]['sources'])):
                        continue
                    if legacy:
                        row = {**row, 'anchors': code_anchor(was[field], earlier[1]['sources'][table]['records'], key_columns(earlier[0]['ontology'], table))}
                    changes = check_code(row['anchors'], code_labels(row), profiles.get(field), bundle['sources'][table]['records'])
                    if changes:
                        flips.append(waiting_change(row, changes, against))
                    elif legacy:
                        store_anchors(conn, row['element_id'], stored_anchors(row['anchors']))
            if rules:
                groups = {g['rule_key']: g for g in repeated_keys(result['ontology'], bundle, build_graph(result['ontology'], bundle))}
                for name, row in rules.items():
                    why = unmet(groups[name], row['content']) if name in groups else None
                    if why:
                        flips.append(waiting_change(row, [why], against))
            if flips:
                set_element_states(conn, flips)
        finally:
            conn.close()

    def recheck_workspace_anchors(result, name, key, earlier=None):
        """The same for what is only known once the new tables are stored: a named view (its rows against its table's rows) and a
        relation judged right (how many rows found their object). Anchors missing from older confirmations are worked out from the
        earlier run's stored tables and checks. A relation that waits no longer starts as right in this run."""
        conn = open_workspace(output_dir / 'workspace.sqlite')
        try:
            views, relations = element_rows(conn, f'view:{key}:', 'confirmed'), element_rows(conn, f'relation:{key}:', 'confirmed')
            checks, against, flips = result['data_checks'], result['file']['name'], []
            versions_of = lambda run: {t['dataset']: t['version'] for t in run['data_checks']['tables'] if t.get('status') == 'ok'}
            if views:
                tables = stored_tables(conn, result)
                now = {v['name']: v for v in views_of_run(conn, key, run_id(name), result['ontology'], tables)}
                before = None
                for vname, row in views.items():
                    v = now.get(vname)
                    if not (v and v['state'] == 'confirmed' and v['source'] in tables):
                        continue
                    legacy = row['anchors'] is None
                    if legacy:
                        if before is None and earlier:
                            old_tables = stored_tables(conn, earlier[0])
                            before = ({x['name']: x for x in views_of_run(conn, key, run_id(earlier[0]['saved_as']), earlier[0]['ontology'], old_tables)}, old_tables, versions_of(earlier[0]))
                        old = before[0].get(vname) if before else None
                        if not (old and old['state'] == 'confirmed' and old['source'] in before[1]):
                            continue
                        row = {**row, 'anchors': view_anchor(old['rows'], before[1][old['source']]['rows'], old['source'], before[2].get(old['source']))}
                    changes = check_view(row['anchors'], v['rows'], tables[v['source']]['rows'], versions_of(result).get(v['source']))
                    if changes:
                        flips.append(waiting_change(row, changes, against))
                    elif legacy:
                        store_anchors(conn, row['element_id'], stored_anchors(row['anchors']))
            if relations:
                found = {r['key']: r for r in checks.get('relations') or []}
                was = {r['key']: r for r in ((earlier or ({},))[0].get('data_checks') or {}).get('relations') or []}
                label = relation_labels(result['ontology'])
                for rkey, row in relations.items():
                    legacy = row['anchors'] is None
                    if rkey not in found or (legacy and rkey not in was):
                        continue
                    if legacy:
                        row = {**row, 'anchors': relation_anchor(was[rkey])}
                    changes = check_relation(row['anchors'], found[rkey], label)
                    if changes:
                        flips.append(waiting_change(row, changes, against))
                    elif legacy:
                        store_anchors(conn, row['element_id'], stored_anchors(row['anchors']))
            if flips:
                set_element_states(conn, flips)
            return set(element_rows(conn, f'relation:{key}:', 'checked'))
        finally:
            conn.close()

    def newer_run(result):
        """The newest run on this file's line of versions that read other rows than this one, else None (names begin with the time they were made)."""
        key = memory_key(result)
        for path in sorted(output_dir.glob('*.json'), reverse=True):
            if path.name <= result['saved_as']:
                break
            if path.name.endswith('.bundle.json') or not SAVED_NAME.match(path.name):
                continue
            try:
                run = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if run['file'].get('kind') != 'document' and memory_key(run) == key and run['file']['sha256'] != result['file']['sha256']:   # the same file again is not a newer version
                return path.name
        return None

    def stale_check(result):
        """Raises ValueError when this is not the line's latest run: a definition is confirmed or changed on the newest rows, not on
        older ones (an anchor taken from old rows would make the newer run read it as confirmed on its own)."""
        newer = newer_run(result)
        if newer:
            raise ValueError(f'有更新的版本（{newer}）：定义请在那一次运行里确认或修改，这里的数据已经过时')

    def relation_labels(ontology):
        types = {t['key']: t.get('label') or t['key'] for t in normalize_proposal(ontology)['object_types']}
        return lambda key: types.get(key, key)

    def review_list(result, newer):
        """What waits for a second look in this file's line of versions: each with what changed, who confirmed it and what depends on it."""
        key = memory_key(result)
        conn = open_workspace(output_dir / 'workspace.sqlite')
        try:
            rows = {prefix: element_rows(conn, f'{prefix}:{key}:', 'checked') for prefix in ('property', 'repeat_rule', 'view', 'relation')}
            named = element_contents(conn, f'view:{key}:')
        finally:
            conn.close()
        types = {t['key']: t.get('label') or t['key'] for t in normalize_proposal(result['ontology'])['object_types']}
        relations = {r['key']: f'{types.get(r["from"], r["from"])} {r.get("label") or r["key"]} {types.get(r["to"], r["to"])}' for r in normalize_proposal(result['ontology'])['relations']}
        return review_items(rows, named, relations, newer)

    def card_for(found):
        """The card of a kept run (see card_run) with what was said on it, the items still open and the ones answered."""
        if found is None:
            return NO_CARD, [], []
        result, bundle, graph = found
        stored = card_file(memory_key(result))
        if graph is None:   # a blocked draft's rows: no graph and no card, but the code columns of its stored tables can be given meanings
            profiles, enums = code_state(result, bundle)
            open_, answered = split_answers(code_meaning_items({'profiles': profiles, 'enums': enums, 'drafts': code_drafts(result), 'waiting': code_waiting(result)}), stored['items'])
            return NO_CARD, with_replies(open_, bundle), with_replies(answered, bundle)
        card = build_card(result['ontology'], bundle, stored['cells'], graph, (result.get('confirmation') or {}).get('decisions'))
        profiles, enums = code_state(result, bundle)
        codes = {'profiles': profiles, 'enums': enums, 'drafts': code_drafts(result), 'waiting': code_waiting(result)}
        items, answered = split_answers(open_items(result, bundle, graph, card, codes), stored['items'])
        return card, with_replies(items, bundle), with_replies(answered, bundle)

    def pipeline_for(name):
        """The pipeline requirements of a kept table run whose ontology passed verification; ValueError says why there are none.
        The status comes first: a run that did not pass may name a table the data does not have, which its graph cannot be built from."""
        path = output_dir / name
        if not SAVED_NAME.match(name) or not path.exists():
            raise FileNotFoundError(name)
        saved = json.loads(path.read_text(encoding='utf-8'))
        if saved['file'].get('kind') == 'document':
            raise ValueError('文档没有数据行，没有编排需求单')
        if saved['ontology']['status'] != 'auto_built_verified':
            raise ValueError(blocked_text(saved, '没有编排需求单；先看退回的原因'))
        result, bundle, graph = kept(name)
        key = memory_key(result)
        stored = card_file(key)
        card = build_card(result['ontology'], bundle, stored['cells'], graph, (result.get('confirmation') or {}).get('decisions'))
        return pipeline_spec(result, bundle, graph, card, stored, derived_of(key), rules_state(result, bundle, graph)['adopted'],
                             datetime.now(timezone.utc).isoformat(timespec='seconds'))

    def rules_state(result, bundle, graph=None):
        """The rules offered for this file and the ones a person adopted, checked against this run's data."""
        stored_path = output_dir / 'rules' / f"{memory_key(result)}.json"
        stored = json.loads(stored_path.read_text(encoding='utf-8')) if stored_path.exists() else {'adopted': [], 'declined': []}
        taken = {r['id'] for r in stored['adopted']} | set(stored['declined'])
        return {'candidates': [r for r in discover_rules(result['ontology'], bundle, graph) if r['id'] not in taken],
                'adopted': check_rules(result['ontology'], bundle, stored['adopted'], graph), 'declined': stored['declined']}

    def kept(name):
        """A kept table run with its rows and its graph; KeyError when there is no such run."""
        bundle_path = output_dir / name.replace('.json', '.bundle.json')
        if not SAVED_NAME.match(name) or not (output_dir / name).exists() or not bundle_path.exists():
            raise FileNotFoundError(name)
        result = json.loads((output_dir / name).read_text(encoding='utf-8'))
        if result['file'].get('kind') == 'document':
            raise ValueError('文档没有数据行')
        with graphs_lock:
            if name not in graphs:
                raw = json.loads(bundle_path.read_text(encoding='utf-8'))
                graphs[name] = {'rows': raw, 'whole': build_graph(result['ontology'], raw), 'rules': None, 'graph': None, 'calc': {}}
                while len(graphs) > KEPT_RUNS_IN_MEMORY:
                    graphs.popitem(last=False)
            graphs.move_to_end(name)
            kept_run = graphs[name]
            bundle = {**with_meanings(result, kept_run['rows']), 'calc_memo': kept_run['calc'], 'subsets': lambda source: view_subsets(result, source),
                      'views_signature': lambda: views_signature(result)}
            # the graph is where rows are picked, so it follows the rules chosen for repeated keys: built again when they change
            rules = json.dumps(bundle['repeat_rules'], sort_keys=True)
            if kept_run['rules'] != rules:
                kept_run['rules'], kept_run['graph'] = rules, build_graph(result['ontology'], bundle, kept_run['whole'])
        return result, bundle, kept_run['graph']

    def keep_job(job_id, job):
        """The job as it stands, on disk, so a restarted service can still say how it ended. Called under jobs_lock."""
        jobs_dir.mkdir(parents=True, exist_ok=True)
        kept = {'state': job['state'], 'events': job['events'], 'error': job['error'],
                'saved_as': (job['result'] or {}).get('saved_as')}
        partial = jobs_dir / f'{job_id}.json.part'
        partial.write_text(json.dumps(kept, ensure_ascii=False), encoding='utf-8')
        partial.replace(jobs_dir / f'{job_id}.json')   # a reader never sees half a file

    def job_from_disk(job_id):
        path = jobs_dir / f'{job_id}.json'
        if not path.exists():
            return None
        job = {**json.loads(path.read_text(encoding='utf-8')), 'result': None}
        if job['state'] == 'running':   # nothing in this process is running it: the service restarted in the middle
            return {**job, 'state': 'interrupted', 'error': INTERRUPTED}
        run = output_dir / (job.pop('saved_as') or '')
        if job['state'] == 'done':
            if not SAVED_NAME.match(run.name) or not run.exists():
                return {**job, 'state': 'failed', 'error': '这次作业的结果文件已经不在了，请重新上传文件'}
            job['result'] = json.loads(run.read_text(encoding='utf-8'))
        return job

    def decode_part(part):
        if not isinstance(part.get('content_base64'), str):
            raise SourceFileError('请求缺少 content_base64（文件内容）')
        try:
            data = base64.b64decode(part['content_base64'], validate=True)
        except (binascii.Error, ValueError):
            raise SourceFileError('文件内容不是有效的 base64') from None
        filename = str(part.get('filename') or '')
        suffix = Path(filename).suffix.lower()
        if suffix not in DOCUMENT_SUFFIXES + TABLE_SUFFIXES:
            raise SourceFileError(f'只支持数据表（{" / ".join(TABLE_SUFFIXES)}）或文档（{" / ".join(DOCUMENT_SUFFIXES)}），不支持 {suffix or "无扩展名"} 文件')
        return filename, data, suffix in DOCUMENT_SUFFIXES

    def parse_upload(payload):
        mode = payload.get('mode')
        if mode not in (None, 'org'):
            raise SourceFileError('mode 只能不写，或写 org（组织架构）')
        files = payload.get('files')
        if not isinstance(files, list):
            filename, data, is_document = decode_part(payload)
            if mode == 'org' and not is_document:
                raise SourceFileError(f'组织架构模式目前只收文档（{" / ".join(DOCUMENT_SUFFIXES)}），不收数据表')
            bundle = (load_document_file if is_document else load_table_file)(filename, data, payload.get('purpose'))
            return ({**bundle, 'mode': mode} if mode else bundle), is_document
        if mode == 'org':
            raise SourceFileError('组织架构模式一次只收一份文档')
        if not files:
            raise SourceFileError('没有选择文件')
        parts = []
        for part in files:
            filename, data, is_document = decode_part(part if isinstance(part, dict) else {})
            if is_document:
                raise SourceFileError(f'{Path(filename).name}：一次只能传数据表，或者单独传一份文档，不能混在一起')
            parts.append((filename, data))
        return load_table_files(parts, payload.get('purpose')), False

    def previous_run(sha256, mode=None):
        """The latest verified earlier run of the same file in the same mode, so a rerun shows what changed."""
        for path in sorted(output_dir.glob('*.json'), reverse=True):
            if path.name.endswith('.bundle.json') or not SAVED_NAME.match(path.name):
                continue
            earlier = json.loads(path.read_text(encoding='utf-8'))
            if earlier['file']['sha256'] == sha256 and earlier.get('mode') == mode and earlier['ontology']['status'] == 'auto_built_verified':
                return earlier
        return None

    def finish_build(bundle, is_document, progress=None, previous=None, starter=None):
        """starter: the signed-in person who started the build; the datasets it stores are signed by them."""
        if bundle.get('mode') == 'org':
            return save_build(bundle, build_and_evaluate_org(bundle, gateway, progress), progress, previous, starter)
        if is_document:
            return save_build(bundle, build_and_evaluate_document(bundle, gateway, progress), progress, previous, starter)
        # the extra runs start together with the shown one, so three runs take about as long as one
        with ThreadPoolExecutor(max_workers=STABILITY_RUNS - 1) as pool:
            extra = [pool.submit(build_company_ontology, bundle, gateway, None, False) for _ in range(STABILITY_RUNS - 1)]
            result = build_and_evaluate(bundle, gateway, progress)
            if previous:
                # the new version's rows are held against what each earlier confirmation was confirmed on, before any question is answered
                recheck_data_anchors(result, bundle, memory_key(json.loads((output_dir / previous).read_text(encoding='utf-8'))), earlier_of(previous))
            if result['ontology']['status'] == 'auto_built_verified' and bundle['decision'] != DEFAULT_PURPOSE:
                # the person's own question is answered with the draft; the model's round of questions is on request
                if progress:
                    progress('questions', {})
                calls = result['ontology']['attempts']
                if len(calls) >= MAX_MODELER_ATTEMPTS:
                    from_data = sum(1 for a in calls if a.get('data_retry'))
                    used = f'本次建模已用满 {MAX_MODELER_ATTEMPTS} 次调用' if not from_data else \
                        f'本次建模已调用模型 {len(calls)} 次（其中 {from_data} 次是按数据检查结果重试），已到 {MAX_MODELER_ATTEMPTS} 次上限'
                    answered = {'prompt_version': QUESTION_PROMPT_VERSION, 'model': None,
                                'asked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                                'items': [], 'answered': 0, 'total': 0,
                                'error': f'{used}，目的问题尚未回答。可在“智能问答”中单独提问。'}
                else:
                    key = memory_key(json.loads((output_dir / previous).read_text(encoding='utf-8'))) if previous else bundle['file']['sha256']
                    # the person's own question is answered with what was already confirmed for this file: its codes' meanings and its repeated-key rules
                    unsaved = {'file': bundle['file'], 'mode': bundle.get('mode'), 'lineage': key, 'ontology': result['ontology']}
                    answered = ask_questions(result['ontology'], with_meanings(unsaved, bundle), gateway, purpose_only=True, derived=derived_of(key),
                                             card=card_cells(result, bundle, key=key))
                if answered['items'] or answered['error']:
                    result['evaluation']['asked'] = [answered]
            if result['ontology']['status'] == 'auto_built_verified':
                if progress:
                    progress('stability', {'total': STABILITY_RUNS - 1})
                result['evaluation']['stability'] = stability_of(result['ontology'], [extra_result(f) for f in extra])
        return save_build(bundle, result, progress, previous, starter)

    def extra_result(future):
        try:
            return future.result()
        except Exception as exc:   # an extra run is evidence, not the answer: its failure is counted, the upload goes on
            return {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'[:200]}

    def data_checks(ontology, bundle, starter=None):
        """Every source table goes into the workspace file beside the runs, and each drafted identity is checked over the
        stored rows. A failed check stays in the result as failed; a check that cannot run is returned as an error the
        person sees, and the upload goes on."""
        try:
            set_actor(starter)   # a build runs in the starter's name even on a job's own thread, which has no request behind it
            who = starter['display_name'] if starter and starter['id'] is not None else 'system'
            conn = open_workspace(output_dir / 'workspace.sqlite')
            try:
                return check_bundle(conn, ontology, bundle, bundle['file']['name'], who=who)
            finally:
                conn.close()
        except Exception as exc:   # the checks are evidence on top of the build: their failure is shown, not fatal
            return {'tables': [], 'keys': [], 'error': f'{type(exc).__name__}: {exc}'[:300]}

    def save_build(bundle, result, progress=None, previous_name=None, starter=None):
        outage = [e['message'] for a in result['ontology']['attempts'] for e in a['errors'] if e['code'] == 'model_request_failed']
        if result['ontology']['status'] != 'auto_built_verified' and outage:
            return 502, {'error': model_failure_text(outage[-1])}
        now = datetime.now(timezone.utc)
        name = f'{now.strftime("%Y%m%dT%H%M%S")}{now.microsecond // 1000:03d}Z-{bundle["file"]["sha256"][:8]}.json'
        output_dir.mkdir(parents=True, exist_ok=True)
        if previous_name:   # the person said this is the next version of that run: its judgements carry over
            earlier = json.loads((output_dir / previous_name).read_text(encoding='utf-8'))
            result['lineage'] = memory_key(earlier)
            if result['ontology']['status'] == 'auto_built_verified' and earlier['ontology']['status'] == 'auto_built_verified' \
                    and result['file'].get('kind') != 'document' and earlier['file'].get('kind') != 'document':
                earlier_bundle = json.loads((output_dir / previous_name.replace('.json', '.bundle.json')).read_text(encoding='utf-8'))
                result['version'] = version_diff(earlier, earlier_bundle, result, bundle)
        previous = previous_run(bundle['file']['sha256'], bundle.get('mode'))
        if previous and result['ontology']['status'] == 'auto_built_verified':
            result['previous'] = {'saved_as': previous['saved_as'], 'started_at': previous['started_at'], 'purpose': previous.get('purpose'),
                                  'counts': {'types': len(previous['ontology']['object_types']), 'relations': len(previous['ontology']['relations'])},
                                  'diff': compare_ontologies(previous['ontology'], result['ontology'])}
        confirmed = output_dir / 'references' / f"{memory_key(result)}.json"
        if confirmed.exists() and result['ontology']['status'] == 'auto_built_verified':
            # a person confirmed an earlier run of this file: compare against that judgement without being asked
            ref = json.loads(confirmed.read_text(encoding='utf-8'))
            result['evaluation']['reference'] = {'name': '你确认过的本体', 'confirmed': True, 'confirmed_at': ref['confirmed_at'], 'confirmed_by': ref.get('confirmed_by'),
                                                 'purpose': ref.get('purpose'),   # what the judgement was made for; this upload may be for something else
                                                 'compared_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                                                 'diff': compare_ontologies(parse_reference(ref['reference']), result['ontology']),
                                                 'suggested': prefill_from_reference(result['ontology'], ref['reference'])}
        accepted = output_dir / 'acceptance' / f"{memory_key(result)}.json"
        if accepted.exists() and result['ontology']['status'] == 'auto_built_verified' and result['file'].get('kind') != 'document':
            # the questions a person fixed for this file: the same queries, so two runs can be judged on the same thing
            with runs_lock:
                saved = json.loads(accepted.read_text(encoding='utf-8'))
                result['evaluation']['acceptance'] = reviewed_acceptance(result, bundle, saved['items'])
                accepted.write_text(json.dumps({**saved, 'items': result['evaluation']['acceptance']['items']}, ensure_ascii=False, indent=1), encoding='utf-8')
        if result['file'].get('kind') != 'document':
            result['data_checks'] = data_checks(result['ontology'], bundle, starter)   # also for a draft that failed the model checks
            if previous_name and result['data_checks'].get('tables'):
                waiting_relations = recheck_workspace_anchors(result, name, result['lineage'], earlier_of(previous_name))
                suggested = (result['evaluation'].get('reference') or {}).get('suggested')
                if suggested and waiting_relations:
                    suggested['relations'] = {k: v for k, v in suggested['relations'].items() if k not in waiting_relations}
        if result['ontology']['status'] == 'auto_built_verified' and result['file'].get('kind') != 'document':
            result['evaluation']['rules'] = rules_state(result, bundle)
            result['evaluation']['derived'] = derived_of(memory_key(result))
            if form_state(result):
                result['evaluation']['form'] = form_state(result)
        result['saved_as'] = name
        write_run((output_dir / name), result)
        # the uploaded rows stay on this machine so later questions can be answered from them
        (output_dir / name.replace('.json', '.bundle.json')).write_text(json.dumps(bundle, ensure_ascii=False), encoding='utf-8')
        return 200, result
    def write_back(path, change):
        """Apply one change to the run as it is on disk now: whatever was saved while the model was thinking stays."""
        with runs_lock:
            result = json.loads(path.read_text(encoding='utf-8'))
            change(result)
            write_run(path, result)
        return result

    ANSWER_PARTS = ('derive', 'reason', 'answer', 'path', 'status', 'evidence', 'refused_by_card', 'reason_from_model', 'unmet', 'upstream', 'understood')   # what answering again replaces

    def answers_again(name, because):
        """After something an answer was worked out from has changed (a code's meaning confirmed, a rule chosen for a
        repeated key), work out again, by code alone, every question of this run that has a query. An answer that comes
        out differently is replaced and carries `rerun`: what changed and what it said before. One that comes out the
        same is left alone. The check's finding that rows of a key disagree is marked settled where "keep the latest"
        now leaves one row. Answers a person accepted as fixed questions are theirs and are not touched. An answer that
        comes out as it first was says nothing of the change."""
        result, bundle, graph = kept(name)
        reviewed = without_wrong(result['ontology'], (result.get('confirmation') or {}).get('decisions'))
        derived, cells = derived_of(memory_key(result)), card_cells(result, bundle, graph)
        settled = settled_by_latest(result['ontology'], bundle, graph)
        answer_with = make_answerer(result, bundle, reviewed, derived, cells, graph)

        def again(item):
            if not isinstance(item.get('query'), dict) or item.get('status') == 'needs_derived':
                return item
            now = answer_with(item['query'], item['question'], item.get('definitions_used'), check=not item.get('edited'), told=item.get('definitions_told') or [])
            said = lambda x: json.dumps([x.get(k) for k in ('status', 'answer', 'reason')], sort_keys=True, ensure_ascii=False)   # what a person reads as the answer
            replaced = {**{k: v for k, v in item.items() if k not in (*ANSWER_PARTS, 'rerun')}, **now}
            was = (item.get('rerun') or {}).get('was') or {k: item[k] for k in ('status', 'answer', 'reason') if k in item}
            if said(now) == said(was):   # unchanged, or back to what it first said: the evidence is kept up to date and nothing is announced
                return replaced if 'rerun' in item or json.dumps(now.get('evidence'), sort_keys=True) != json.dumps(item.get('evidence'), sort_keys=True) else item
            reasons = list(dict.fromkeys([*(item.get('rerun') or {}).get('because', []), because]))
            return {**replaced, 'rerun': {'because': reasons, 'was': was}}

        def round_again(answered):
            items = [again(i) for i in answered.get('items') or []]
            return {**answered, 'items': items, 'answered': sum(i['status'] == 'answered' for i in items)}

        def change(run):
            evaluation = run['evaluation']
            if evaluation.get('questions'):
                evaluation['questions'] = round_again(evaluation['questions'])
            if evaluation.get('asked'):
                evaluation['asked'] = [round_again(r) for r in evaluation['asked']]
            fit = evaluation.get('data_fit')
            if fit and fit.get('identity_conflicts'):
                fit['identity_conflicts'] = [{**{k: v for k, v in c.items() if k != 'settled'}, **({'settled': 'keep_latest'} if (c['type'], c['source'], c['identity']) in settled else {})}
                                             for c in fit['identity_conflicts']]
        return write_back(output_dir / name, change)

    def recompute_warning(name, because):
        """Work the answers out again after something was saved. What was saved stays saved whatever happens here: a failure
        is returned as the words to show beside it, never as a failed save."""
        try:
            if json.loads((output_dir / name).read_text(encoding='utf-8'))['ontology']['status'] != 'auto_built_verified':
                return None   # a blocked draft has no answers to work out again
            answers_again(name, because)
        except Exception as exc:
            return f'已保存，但这次运行里已有的答案没能按它重算：{type(exc).__name__}: {exc}'[:300]
        return None

    gate = Gate(output_dir / 'workspace.sqlite', port, origins, no_auth, trusted_proxies)

    class Handler(BaseHTTPRequestHandler):
        timeout = 15   # seconds the service waits on one read from a client, so a connection that sends nothing does not hold a thread

        def version_string(self):
            return 'ontopoc'   # no software name or version in the Server header

        def log_message(self, format, *args):
            pass

        def end_headers(self):
            for name, value in SECURITY_HEADERS:
                self.send_header(name, value)
            super().end_headers()

        def reply(self, status, payload, headers=None):
            if status < 300 and self.command == 'POST' and self.path in LOGGED_WRITES:
                self.note_write()   # before the answer goes out: whoever sees it saved can find its line
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def org_diagrams(self, name, query):
            """/api/ontology/runs/<run>/export/mermaid?years=2016-2022&format=json: the organisation map as Mermaid."""
            path = output_dir / name
            if not SAVED_NAME.match(name) or not path.exists():
                self.reply(404, {'error': '找不到这次运行'})
                return
            result = json.loads(path.read_text(encoding='utf-8'))
            if result.get('mode') != 'org':
                self.reply(400, {'error': '只有组织架构模式的运行能导出组织图'})
                return
            span = (query.get('years') or [''])[0]
            found = re.fullmatch(r'(\d{4})-(\d{4})', span)
            if span and not found:
                self.reply(400, {'error': 'years 写成 2016-2022 这样的年份段'})
                return
            files = org_mermaid(result['ontology'], (result.get('confirmation') or {}).get('decisions'),
                                (int(found[1]), int(found[2])) if found else None)
            if (query.get('format') or [''])[0] == 'json':
                self.reply(200, {'files': files})
                return
            packed = io.BytesIO()
            with zipfile.ZipFile(packed, 'w', zipfile.ZIP_DEFLATED) as z:
                for file_name, text in files.items():
                    z.writestr(file_name, text.encode('utf-8'))
            self.reply_file(packed.getvalue(), 'application/zip', f"{name.split('.')[0]}-组织图{('-' + span) if span else ''}.zip")

        def card_page(self, name, tail):
            """/api/ontology/runs/<run>/open-items: what is still to be settled with the client, and what the client has
            answered; /card: the data-meaning card. Both from the kept run; a run with no rows to read has neither."""
            try:
                found = workspace_run(name) if tail == 'open-items' else card_run(name)
                body = code_reply(found) if tail == 'open-items' else card_for(found)[0]
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            self.reply(200, body)

        def reply_files(self, files, query, name, zip_name):
            """The files of an export as a zip to download, or as JSON with ?format=json."""
            if (query.get('format') or [''])[0] == 'json':
                self.reply(200, {'files': files})
                return
            packed = io.BytesIO()
            with zipfile.ZipFile(packed, 'w', zipfile.ZIP_DEFLATED) as z:
                for file_name, text in files.items():
                    z.writestr(file_name, text.encode('utf-8'))
            self.reply_file(packed.getvalue(), 'application/zip', f"{name.split('.')[0]}-{zip_name}.zip")

        def reply_file(self, body: bytes, content_type: str, filename: str):
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{url_quote(filename)}")
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def local_request(self):
            try:
                host = urlsplit('http://' + self.headers.get('Host', '')).hostname
                origin = self.headers.get('Origin')
                parsed = urlsplit(origin) if origin else None
                if host not in {'127.0.0.1', 'localhost'} or (parsed and (
                        parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'})):
                    raise ValueError('local only')
                return True
            except ValueError:
                self.reply(403, {'error': '仅允许本机请求。'})
                return False

        def workspace_get(self):
            """/api/workspace/datasets, /api/workspace/datasets/<name>?version=N: the workspace's datasets, which belong to no run;
            /api/workspace/tasks: modelling jobs and dataset uploads, newest first."""
            url = urlsplit(self.path)
            conn = open_workspace(output_dir / 'workspace.sqlite')
            try:
                if url.path == '/api/workspace/datasets':
                    self.reply(200, {'datasets': list_datasets(conn, self.user)})
                    return
                if url.path == '/api/workspace/tasks':
                    with jobs_lock:
                        running = {job_id for job_id, job in jobs.items() if job['state'] == 'running'}
                    tasks, unreadable = list_tasks(conn, jobs_dir, running, self.user)
                    self.reply(200, {'tasks': tasks, 'unreadable': unreadable})
                    return
                if url.path.startswith('/api/workspace/datasets/'):
                    query = parse_qs(url.query)
                    version, page = (query.get('version') or [None])[0], (query.get('page') or ['1'])[0]
                    if any(v is not None and not re.fullmatch(r'[0-9]{1,9}', v) for v in (version, page)):
                        self.reply(400, {'error': '版本和页码要写成数字'})
                        return
                    name = unquote(url.path[len('/api/workspace/datasets/'):])
                    if (query.get('format') or [''])[0] == 'csv':
                        if dataset_hidden(conn, name, self.user):   # not found, before anything is said about what a viewer may do with it
                            self.reply(404, {'error': '没有这个数据集或这个版本'})
                            return
                        if self.user['role'] == 'viewer':
                            self.reply(403, {'error': '查看者读不到数据集的行：数据要通过你能看到的对象类型来读'})
                            return
                        csv_file = dataset_csv(conn, name, int(version) if version else None, self.user)
                        if csv_file is None:
                            self.reply(404, {'error': '没有这个数据集或这个版本'})
                        else:
                            self.reply_file(csv_file[1], 'text/csv; charset=utf-8', csv_file[0])
                        return
                    found = dataset_detail(conn, name, int(version) if version else None, int(page), self.user)
                    self.reply(*((200, found) if found else (404, {'error': '没有这个数据集或这个版本'})))
                    return
            finally:
                conn.close()
            self.reply(404, {'error': 'Unknown workspace endpoint'})

        def workspace_upload(self):
            """POST /api/workspace/datasets/upload {who, files: [{filename, content_base64, target?, mode?, key_columns?, name?}]}."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                parts = payload.get('files')
                if not isinstance(parts, list):
                    raise ValueError('请求里要有 files 列表')
                with runs_lock:
                    conn = open_workspace(output_dir / 'workspace.sqlite')
                    try:
                        results = upload_datasets(conn, parts, self.signer(payload, 'who'), self.user)
                    finally:
                        conn.close()
            except UploadRefused as exc:
                self.reply(400, {'error': str(exc), 'files': {str(i): m for i, m in exc.files.items()}})
                return
            except (ValueError, UnicodeError, RowCountMismatch) as exc:
                self.reply(400, {'error': str(exc)})
                return
            self.reply(200, {'results': results})

        def workspace_delete(self):
            """POST /api/workspace/datasets/delete {who, name}: remove a dataset with all its versions, unless something reads it (409, naming what)."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                name = payload.get('name')
                if not isinstance(name, str) or not name:
                    raise ValueError('要写明数据集的名字（name）')
                with runs_lock:
                    conn = open_workspace(output_dir / 'workspace.sqlite')
                    try:
                        if dataset_hidden(conn, name, self.user):   # a dataset they may not see is not there to delete, and its readers are not named to them
                            self.reply(404, {'error': '没有这个数据集'})
                            return
                        readers = dataset_readers(conn, [p for p in output_dir.glob('*.json') if SAVED_NAME.match(p.name)], name, self.user)
                        try:
                            deleted = delete_dataset(conn, name, self.signer(payload, 'who'), readers)
                        except KeyError:
                            self.reply(404, {'error': '没有这个数据集'})
                            return
                        except ValueError as exc:
                            self.reply(409, {'error': str(exc), 'readers': readers})
                            return
                    finally:
                        conn.close()
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            self.reply(200, deleted)

        def types_get(self):
            """/api/workspace/types, /types/<id>, /types/<id>/objects?page=N, /types/<id>/log: the object types of the workspace (a viewer sees the confirmed ones)."""
            url = urlsplit(self.path)
            parts = [unquote(p) for p in url.path[len('/api/workspace/types'):].split('/') if p]
            page = (parse_qs(url.query).get('page') or ['1'])[0]
            if not re.fullmatch(r'[0-9]{1,9}', page):
                self.reply(400, {'error': '页码要写成数字'})
                return
            conn = open_workspace(output_dir / 'workspace.sqlite')
            try:
                if not parts:
                    body = {'types': list_types(conn, self.user)}
                elif len(parts) == 1:
                    body = type_detail(conn, parts[0], self.user)
                elif len(parts) == 2 and parts[1] == 'objects':
                    body = type_objects(conn, parts[0], int(page), self.user)
                elif len(parts) == 2 and parts[1] == 'log':
                    body = {'log': type_log(conn, parts[0], self.user)}
                else:
                    self.reply(404, {'error': 'Unknown workspace endpoint'})
                    return
            except TypeRefused as exc:
                self.reply(exc.status, {'error': str(exc)})
                return
            finally:
                conn.close()
            self.reply(200, body)

        def types_post(self):
            """POST /api/workspace/types (create), /types/update, /types/meanings, /types/confirm, /types/key-check, /types/suggest: see object_types.py. A refusal
            of who (confirming one's own proposal) is a 403, a stale version a 409, the rest a 400 that says what is wrong."""
            route = self.path[len('/api/workspace/types'):]
            try:
                payload = self.read_json()
                if payload is None:
                    return
                who = self.signer(payload, 'who')
                conn = open_workspace(output_dir / 'workspace.sqlite')
                try:
                    if route == '/suggest':   # the model takes up to two minutes: asked without the lock, its answer is written under it (suggest_types)
                        if gateway is None:
                            self.reply(503, {'error': NO_KEY})
                            return
                        body = suggest_types(conn, gateway, payload.get('datasets'), payload.get('purpose') or '', who, datetime.now(timezone.utc).isoformat(timespec='seconds'),
                                             self.user, runs_lock)
                    else:
                        with runs_lock:   # the lock an upload takes: a check and the write that stands on it are not split by new data
                            if route == '':
                                body = create_type(conn, payload, who, self.user)
                            elif route == '/update':
                                body = update_type(conn, payload, who, self.user)
                            elif route == '/meanings':
                                body = propose_meanings(conn, payload, who, self.user)
                            elif route == '/confirm':
                                body = confirm_element(conn, payload, who, self.user)
                            elif route == '/key-check':
                                body = key_preview(conn, payload.get('dataset'), payload.get('key'), self.user)
                            elif route == '/privacy':
                                _type_row(conn, payload.get('id'), self.user)   # a type this person may not see is not there for them
                                body = set_values_hidden(conn, str(payload.get('id')), str(payload.get('column')), payload.get('hide_values'), who)
                            else:
                                self.reply(404, {'error': 'Unknown workspace endpoint'})
                                return
                finally:
                    conn.close()
            except SelfConfirmation as exc:
                self.reply(403, {'error': str(exc)})
                return
            except TypeRefused as exc:
                self.reply(exc.status, {'error': str(exc), **(exc.detail or {})})
                return
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            self.reply(200, body)

        def ask_get(self):
            """/api/workspace/ask (the scope line and the person's own history), /api/workspace/ask/<id> (one saved answer as it stands now)."""
            parts = [p for p in urlsplit(self.path).path[len('/api/workspace/ask'):].split('/') if p]
            conn = open_workspace(output_dir / 'workspace.sqlite')
            try:
                if not parts:
                    body = {**scope_line(conn, self.user), 'history': question_history(conn, self.user), 'model_ready': gateway is not None}
                elif len(parts) == 1 and parts[0].isdigit():
                    body = reopen_question(conn, self.user, int(parts[0]))
                else:
                    self.reply(404, {'error': 'Unknown workspace endpoint'})
                    return
            except QaRefused as exc:
                self.reply(exc.status, {'error': str(exc)})
                return
            finally:
                conn.close()
            self.reply(200, body)

        def ask_post(self):
            """POST /api/workspace/ask {question}: answered from the confirmed definitions this person may see, or refused with the reason (see workspace_questions.py).
            The model is asked without the lock; the answer is kept under it."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                conn = open_workspace(output_dir / 'workspace.sqlite')
                try:
                    body = ask_workspace(conn, gateway, self.user, payload.get('question'))
                finally:
                    conn.close()
            except QaRefused as exc:
                self.reply(exc.status, {'error': str(exc)})
                return
            self.reply(200, body)

        def relations_get(self):
            """/api/workspace/relations, /relations/<id>, /relations/<id>/log, /relation-form (the types and columns a relation can be made from), /queue (待确认),
            /permissions (admin): what this person may see of them (type_access, relation_visible)."""
            url = urlsplit(self.path)
            parts = [unquote(p) for p in url.path[len('/api/workspace/'):].split('/') if p]
            conn = open_workspace(output_dir / 'workspace.sqlite')
            try:
                if parts == ['relations']:
                    body = {'relations': list_relations(conn, self.user)}
                elif len(parts) == 2 and parts[0] == 'relations':
                    body = relation_detail(conn, parts[1], self.user)
                elif len(parts) == 3 and parts[0] == 'relations' and parts[2] == 'log':
                    body = {'log': relation_log(conn, parts[1], self.user)}
                elif parts == ['relation-form']:
                    body = {'types': relation_columns(conn, self.user)}
                elif parts == ['queue']:   # ?count=1: only how many this person may confirm, read from the states (the navigation item asks on every page)
                    body = queue(conn, self.user, light='count' in parse_qs(url.query))
                elif parts == ['permissions']:
                    body = access_table(conn)
                else:
                    self.reply(404, {'error': 'Unknown workspace endpoint'})
                    return
            except TypeRefused as exc:
                self.reply(exc.status, {'error': str(exc)})
                return
            finally:
                conn.close()
            self.reply(200, body)

        def relations_post(self):
            """POST /api/workspace/relations (create), /relations/update, /relations/confirm, /queue/confirm, /queue/send-back, /permissions (admin): see
            object_relations.py, review_queue.py and type_access.py. Refusals are 403 (of who), 409 (the data or the version moved) or a 400 that says what is wrong."""
            route = self.path[len('/api/workspace/'):]
            try:
                payload = self.read_json()
                if payload is None:
                    return
                who = self.signer(payload, 'who')
                conn = open_workspace(output_dir / 'workspace.sqlite')
                try:
                    with runs_lock:   # the lock an upload takes (see types_post)
                        if route == 'relations':
                            body = create_relation(conn, payload, who, self.user)
                        elif route == 'relations/update':
                            body = update_relation(conn, payload, who, self.user)
                        elif route == 'relations/confirm':
                            body = confirm_relation(conn, payload, who, self.user)
                        elif route == 'queue/confirm':
                            body = confirm_item(conn, payload, who, self.user)
                        elif route == 'queue/send-back':
                            body = send_back(conn, payload, who, self.user)
                        elif route == 'permissions':
                            body = set_access(conn, str(payload.get('type')), payload.get('visible_to'), who)
                        else:
                            self.reply(404, {'error': 'Unknown workspace endpoint'})
                            return
                finally:
                    conn.close()
            except SelfConfirmation as exc:
                self.reply(403, {'error': str(exc)})
                return
            except (TypeRefused, AccessRefused) as exc:
                self.reply(exc.status, {'error': str(exc), **(getattr(exc, 'detail', None) or {})})
                return
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            self.reply(200, body)

        def do_GET(self):
            if not gate.admit(self, 'GET') or gate.handle(self, 'GET'):
                return
            if self.path.split('?')[0] == '/api/workspace/ask' or self.path.startswith('/api/workspace/ask/'):
                self.ask_get()
                return
            if self.path.split('?')[0] in ('/api/workspace/relations', '/api/workspace/relation-form', '/api/workspace/queue', '/api/workspace/permissions') \
                    or self.path.startswith('/api/workspace/relations/'):
                self.relations_get()
                return
            if self.path == '/api/workspace/types' or self.path.startswith('/api/workspace/types/') or self.path.startswith('/api/workspace/types?'):
                self.types_get()
                return
            if self.path.startswith('/api/workspace/'):
                self.workspace_get()
                return
            if self.path == '/api/ontology/library' or self.path.startswith('/api/ontology/library/'):
                try:
                    self.reply(200, library_catalogue() if self.path == '/api/ontology/library'
                               else library_definition(unquote(self.path[len('/api/ontology/library/'):])))
                except KeyError:
                    self.reply(404, {'error': '本体库里没有这一项。'})
                except (ValueError, OSError) as exc:
                    self.reply(400, {'error': str(exc)})
                return
            if self.path.startswith('/api/ontology/jobs/'):
                job_id = self.path.rsplit('/', 1)[1]
                if JOB_ID.match(job_id):
                    self.job_status(job_id)
                else:
                    self.reply(404, {'error': '找不到这个任务'})
                return
            if self.path == '/api/ontology/runs':
                self.list_runs()
                return
            if self.path.startswith('/api/ontology/runs/') and self.path.endswith('/reference'):
                self.reference_context(self.path.split('/')[-2])
                return
            if self.path.startswith('/api/ontology/runs/') and self.path.count('/') > 4:
                self.object_page()
                return
            if self.path.startswith('/api/ontology/runs/'):
                self.open_run(self.path.rsplit('/', 1)[1])
                return
            if self.path != '/api/ontology/health':
                self.reply(404, {'error': 'Unknown ontology endpoint'})
                return
            if self.user is None:   # a stranger learns only that the service is up
                self.reply(200, {'ok': True})
                return
            on_disk = code_fingerprint(code_dir)
            self.reply(200, {'model_ready': gateway is not None, 'running': running, 'on_disk': on_disk, 'stale': on_disk != running})

        def list_runs(self):
            """Every run kept on this machine, newest first, so a closed tab or another day does not lose one."""
            runs = []
            for path in sorted(output_dir.glob('*.json'), reverse=True):
                if not SAVED_NAME.match(path.name):
                    continue
                try:
                    run = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    continue   # a file cut short by a crash is not a run anyone can open
                ontology = run.get('ontology') or {}
                runs.append({'saved_as': path.name, 'file': (run.get('file') or {}).get('name'), 'kind': (run.get('file') or {}).get('kind'),
                             'purpose': run.get('purpose'), 'started_at': run.get('started_at'), 'status': ontology.get('status'),
                             'types': len(ontology.get('object_types') or []), 'relations': len(ontology.get('relations') or []),
                             'confirmed': bool(run.get('confirmation'))})
            self.reply(200, {'runs': runs})

        def object_page(self):
            """/api/ontology/runs/<run>/objects/<type>?page=N|all=1, /instances/<type>?q=, /graph?node=<id>, /suggestions"""
            url = urlsplit(self.path)
            rest = url.path[len('/api/ontology/runs/'):]
            name, _, tail = rest.partition('/')
            query = parse_qs(url.query)
            if tail == 'export/mermaid':   # an organisation map is a document: no rows, so not through kept()
                self.org_diagrams(name, query)
                return
            if tail in ('open-items', 'card'):
                self.card_page(name, tail)
                return
            try:
                if tail == 'export/pipeline':
                    self.reply_files(pipeline_files(pipeline_for(name)), query, name, '编排需求单')
                    return
                result, bundle, graph = kept(name)
                if tail.startswith('objects/'):
                    type_key = unquote(tail[len('objects/'):])
                    page = int((query.get('page') or ['1'])[0])
                    size = None if query.get('all') == ['1'] else 20   # all=1: every row, for a download
                    self.reply(200, object_rows(result['ontology'], bundle, type_key, page, size, graph))
                elif tail.startswith('instances/'):
                    type_key = unquote(tail[len('instances/'):])
                    self.reply(200, find_instances(result['ontology'], bundle, type_key, (query.get('q') or [''])[0], graph=graph))
                elif tail in ('export/forms', 'export/ttl'):
                    handover = result['evaluation'].get('handover') or handover_form(result['ontology'], bundle)
                    form = form_state({**result, 'evaluation': {**result['evaluation'], 'handover': handover}})
                    decisions = (result.get('confirmation') or {}).get('decisions')
                    reviewed = without_wrong(result['ontology'], decisions)   # both exports carry what the person kept
                    kept_types = {t['key'] for t in reviewed['object_types']}
                    handover = {**handover, 'types': [t for t in handover.get('types', []) if t['type'] in kept_types]}
                    if tail == 'export/forms':
                        files, zip_name = form_files(reviewed, handover, form), '对象表单'
                    else:
                        files, zip_name = ttl_files(reviewed, bundle, handover, form, decisions,
                                                    rules_state(result, bundle, graph)['adopted'], f'urn:ontopoc:{memory_key(result)}/', graph), 'TTL'
                    self.reply_files(files, query, name, zip_name)
                elif tail == 'rules':
                    self.reply(200, rules_state(result, bundle, graph))
                elif tail == 'suggestions':
                    self.reply(200, {'suggestions': suggest_relations(result['ontology'], bundle, graph)})
                elif tail == 'graph':
                    self.reply(200, neighbourhood(result['ontology'], bundle, (query.get('node') or [''])[0], graph=graph))
                else:
                    self.reply(404, {'error': 'Unknown ontology endpoint'})
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
            except KeyError as exc:
                self.reply(404, {'error': f'这份本体里没有 {exc.args[0]}'})
            except ValueError as exc:
                self.reply(400, {'error': str(exc)})

        def open_run(self, name):
            path = output_dir / name
            if not SAVED_NAME.match(name) or not path.exists():
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            self.reply(200, json.loads(path.read_text(encoding='utf-8')))

        def reference_context(self, name):
            try:
                path = self.load_run({'saved_as': name})
                result = json.loads(path.read_text(encoding='utf-8'))
                record = result.get('evaluation', {}).get('domain_reference')
                definition, stale = None, []
                if record:
                    try:
                        definition = library_definition(record['reference_id'])
                        stale = stale_reasons(definition, result, record)
                    except (KeyError, ValueError, OSError):
                        stale = ['参考版本已不可用，请重新选择本体库参考。']
                blocked = None if result['ontology']['status'] == 'auto_built_verified' else blocked_text(result, '不能对照领域参考')
                self.reply(200, {'run_sha256': run_fingerprint(result), 'local': local_schema(result),
                                 'record': record, 'definition': definition, 'stale': stale, 'blocked': blocked})
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，请重新打开。'})
            except ValueError as exc:
                self.reply(400, {'error': str(exc)})

        def signer(self, payload, field='confirmed_by', required=False, raw=False):
            """Who a write is signed by. A signed-in person: their display name, whatever the request says in `field` (a name typed into a request
            is a claim, not an identity). With --no-auth, what the request says: at most 40 characters, None when it says nothing (the three
            routes that need a name refuse then); `raw` leaves it exactly as sent, for the one route that checks it itself."""
            if self.user['id'] is not None:
                return self.user['display_name']
            value = payload.get(field)
            if raw:
                return value
            if required:
                if not isinstance(value, str) or not value.strip() or len(value.strip()) > 40:
                    raise ValueError('要写确认人，最多 40 个字')
            elif value is not None and (not isinstance(value, str) or len(value.strip()) > 40):
                raise ValueError('确认人最多写 40 个字')
            return (value or '').strip() or None

        def read_json(self, limit=MAX_BODY):
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= limit:
                self.reply(413, {'error': f'文件太大，上限 {MAX_BYTES // 1024 // 1024} MB。' if limit == MAX_BODY else '请求太大。'})
                return None
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.reply(415, {'error': 'Expected application/json'})
                return None
            try:
                payload = json.loads(self.rfile.read(length))
            except RecursionError:
                raise ValueError('请求的嵌套层数太多') from None
            if not isinstance(payload, dict):
                raise ValueError('请求必须是 JSON 对象')
            self.payload = payload
            return payload

        def do_POST(self):
            self.payload = None
            self.post_route()

        def note_write(self):
            """A write that keeps its data in a file of its own (a rule, a form, a derived measure, an acceptance question, a reference,
            a card) leaves a line in the log: the signed-in person, what, and which run it was about."""
            what = LOGGED_WRITES[self.path]
            run = (self.payload or {}).get('saved_as')
            try:
                conn = open_workspace(output_dir / 'workspace.sqlite')
                try:
                    log_write(conn, self.user['display_name'], f'write:{what}', 'saved', {'saved_as': run[:80]} if isinstance(run, str) else None)
                finally:
                    conn.close()
            except sqlite3.Error as exc:   # the answer has gone out; the failure is not lost
                print(f'log line for {what} not written: {exc}', file=sys.stderr, flush=True)

        def post_route(self):
            if not gate.admit(self, 'POST') or gate.handle(self, 'POST'):
                return
            if self.path == '/api/workspace/types' or self.path.startswith('/api/workspace/types/'):
                self.types_post()
                return
            if self.path == '/api/workspace/ask':
                self.ask_post()
                return
            if self.path in ('/api/workspace/relations', '/api/workspace/relations/update', '/api/workspace/relations/confirm', '/api/workspace/queue/confirm',
                             '/api/workspace/queue/send-back', '/api/workspace/permissions'):
                self.relations_post()
                return
            if self.path == '/api/workspace/datasets/upload':
                self.workspace_upload()
                return
            if self.path == '/api/workspace/datasets/delete':
                self.workspace_delete()
                return
            if self.path in ('/api/ontology/reference/preview', '/api/ontology/reference/confirm'):
                with runs_lock:
                    self.domain_reference(self.path.endswith('/confirm'))
                return
            if self.path == '/api/ontology/library/import':
                try:
                    payload = self.read_json()
                    if payload is not None:
                        self.reply(200, import_definition(payload))
                except (ValueError, UnicodeError) as exc:
                    self.reply(400, {'error': str(exc)})
                return
            if self.path == '/api/ontology/ask':
                self.ask()
                return
            # compare, confirm, acceptance and requery read, change and write one run without a model call: they hold
            # runs_lock throughout; ask and variants wait on the model first and take it only to write (see write_back)
            if self.path == '/api/ontology/compare':
                with runs_lock:
                    self.compare()
                return
            if self.path == '/api/ontology/jobs':
                self.start_job()
                return
            if self.path == '/api/ontology/preview':
                self.preview()
                return
            if self.path == '/api/ontology/confirm':
                with runs_lock:
                    self.confirm()
                return
            if self.path == '/api/ontology/acceptance':
                with runs_lock:
                    self.acceptance()
                return
            if self.path == '/api/ontology/card':
                with runs_lock:
                    self.save_card()
                return
            if self.path == '/api/ontology/derived':
                with runs_lock:
                    self.confirm_derived()
                return
            if self.path == '/api/ontology/code-meanings':
                self.save_code_meanings()
                return
            if self.path == '/api/ontology/code-meanings/dismiss':
                self.dismiss_code_column()
                return
            if self.path == '/api/ontology/code-meanings/withdraw':
                self.withdraw_code_decision()
                return
            if self.path == '/api/ontology/bulk-approve':
                self.bulk_approve()
                return
            if self.path == '/api/ontology/code-meanings/draft':
                self.draft_code_meanings()
                return
            if self.path == '/api/ontology/repeat-rules':
                self.save_repeat_rule()
                return
            if self.path == '/api/ontology/review/confirm':
                self.confirm_again()
                return
            if self.path == '/api/ontology/views':
                self.save_view()
                return
            if self.path == '/api/ontology/pipelines/run':
                self.run_pipeline_request()
                return
            if self.path == '/api/ontology/requery':
                with runs_lock:
                    self.requery()
                return
            if self.path == '/api/ontology/rules':
                with runs_lock:
                    self.rules()
                return
            if self.path == '/api/ontology/form/draft':
                self.draft_form()
                return
            if self.path == '/api/ontology/form':
                with runs_lock:
                    self.save_form()
                return
            if self.path == '/api/ontology/variants':
                self.variants()
                return
            if self.path != '/api/ontology/build':
                self.reply(404, {'error': 'Unknown ontology endpoint'})
                return
            try:
                payload = self.read_json()
                if payload is None:
                    return
                bundle, is_document = parse_upload(payload)
                previous = previous_version(payload)
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            if gateway is None:
                self.reply(503, {'error': NO_KEY})
                return
            self.reply(*finish_build(bundle, is_document, None, previous, self.user))

        def preview(self):
            try:
                payload = self.read_json()
                if payload is None:
                    return
                bundle, _ = parse_upload(payload)
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            self.reply(200, model_preview(bundle))

        def start_job(self):
            try:
                payload = self.read_json()
                if payload is None:
                    return
                bundle, is_document = parse_upload(payload)
                previous = previous_version(payload)
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            if gateway is None:
                self.reply(503, {'error': NO_KEY})
                return
            job_id = uuid.uuid4().hex[:12]
            job = {'state': 'running', 'events': [], 'result': None, 'error': None}
            with jobs_lock:
                jobs[job_id] = job
                keep_job(job_id, job)

            def report(stage, detail):
                with jobs_lock:
                    job['events'].append({'stage': stage, 'detail': detail,
                                          'at': datetime.now(timezone.utc).isoformat(timespec='seconds')})
                    keep_job(job_id, job)
            report('read', {'file': bundle['file']['name'], 'kind': bundle['file']['kind']})
            starter = self.user

            def run():
                try:
                    status, body = finish_build(bundle, is_document, report, previous, starter)
                except Exception as exc:  # the job must end in a state the page can show; the server log keeps the rest
                    status, body = 500, {'error': f'建模时出错：{exc}'}
                report('done' if status == 200 else 'failed', {})
                with jobs_lock:
                    job['state'] = 'done' if status == 200 else 'failed'
                    job['result' if status == 200 else 'error'] = body if status == 200 else body['error']
                    keep_job(job_id, job)
            threading.Thread(target=run, daemon=True).start()
            self.reply(202, {'job_id': job_id})

        def job_status(self, job_id):
            with jobs_lock:
                job = jobs.get(job_id)
                snapshot = job_from_disk(job_id) if job is None else json.loads(json.dumps(job))
            if snapshot is None:
                self.reply(404, {'error': '找不到这个任务'})
                return
            self.reply(200, snapshot)

        def load_run(self, payload):
            name = str(payload.get('saved_as') or '')
            if not SAVED_NAME.match(name):
                raise ValueError('saved_as 不是这个服务保存的结果名')
            return output_dir / name

        def compare(self):
            try:
                payload = self.read_json()
                if payload is None:
                    return
                result_path = self.load_run(payload)
                reference = parse_reference(payload.get('reference'))
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            if not result_path.exists():
                self.reply(404, {'error': '找不到这次上传的结果，请重新上传文件'})
                return
            result = json.loads(result_path.read_text(encoding='utf-8'))
            if result['ontology']['status'] != 'auto_built_verified':
                self.reply(400, {'error': blocked_text(result, '不能对照参考本体')})
                return
            result['evaluation']['reference'] = {
                'name': str(payload.get('reference_name') or '参考本体')[:120],
                'compared_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'diff': compare_ontologies(reference, result['ontology'])}
            write_run(result_path, result)
            self.reply(200, result)

        def domain_reference(self, save):
            try:
                payload = self.read_json()
                if payload is None:
                    return
                path = self.load_run(payload)
                result = json.loads(path.read_text(encoding='utf-8'))
                if result['ontology']['status'] != 'auto_built_verified':
                    raise ValueError(blocked_text(result, '不能对照领域参考'))
                definition = library_definition(payload.get('reference_id'))
                stale = stale_reasons(definition, result, payload)
                if stale:
                    self.reply(409, {'error': ' '.join(stale)})
                    return
                if save and payload.get('confirmed') is not True:
                    raise ValueError('请先人工确认本次对应关系，再保存。')
                mappings = payload.get('mappings')
                diff = compare_definition(definition, result, mappings)
                if not save:
                    self.reply(200, {'diff': diff})
                    return
                result.setdefault('evaluation', {})['domain_reference'] = {
                    'reference_id': definition['entry']['id'], 'reference_title': definition['entry']['title'],
                    'reference_sha256': definition['sha256'], 'source_url': definition['entry']['source_url'],
                    'source_commit': definition['entry']['commit'], 'run_sha256': run_fingerprint(result),
                    'mappings': mappings, 'diff': diff,
                    'confirmed_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
                write_run(path, result)
                self.reply(200, result)
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，请重新打开。'})
            except KeyError:
                self.reply(404, {'error': '本体库里没有这一项。'})
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})

        def variants(self):
            try:
                payload = self.read_json()
                if payload is None:
                    return
                result_path = self.load_run(payload)
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            bundle_path = output_dir / result_path.name.replace('.json', '.bundle.json')
            if not result_path.exists() or not bundle_path.exists():
                self.reply(404, {'error': '找不到这次上传的结果，请重新上传文件'})
                return
            if gateway is None:
                self.reply(503, {'error': NO_KEY})
                return
            result = json.loads(result_path.read_text(encoding='utf-8'))
            if result['ontology']['status'] != 'auto_built_verified':
                self.reply(400, {'error': blocked_text(result, '先看退回的原因')})
                return
            bundle = with_rules(result, json.loads(bundle_path.read_text(encoding='utf-8')))
            found = propose_name_variants(result['ontology'], bundle, gateway)
            if found['error'] and found['error'].startswith('模型请求失败'):
                self.reply(502, {'error': found['error']})
                return
            self.reply(200, write_back(result_path, lambda r: r['evaluation'].update(variants=found)))

        def acceptance(self):
            try:
                payload = self.read_json()
                if payload is None:
                    return
                result_path = self.load_run(payload)
                if not result_path.exists():
                    self.reply(404, {'error': '找不到这次上传的结果，请重新上传文件'})
                    return
                result = json.loads(result_path.read_text(encoding='utf-8'))
                bundle_path = output_dir / result['saved_as'].replace('.json', '.bundle.json')
                if not bundle_path.exists():
                    self.reply(404, {'error': '找不到这次上传的数据，请重新上传文件'})
                    return
                items = parse_acceptance(payload.get('items')) if payload.get('items') else []
                existing = {item['question']: item for item in (result['evaluation'].get('acceptance') or {}).get('items', [])}
                # the file's line keeps one list: an older run opened from the library may hold an agreement made since replaced
                shared_path = output_dir / 'acceptance' / f"{memory_key(result)}.json"
                latest = {i['question']: i for i in json.loads(shared_path.read_text(encoding='utf-8'))['items']} if shared_path.exists() else {}
                accepted_now = set()   # what the person agrees to in this request; the rest of the list was agreed earlier
                for item in items:
                    old = existing.get(item['question'])
                    same = isinstance(item.get('query'), dict) and old and item['query'] == old.get('query')
                    if item['question'] == payload.get('replace_question'):
                        item['snapshot'] = None   # explicitly accepting this query again uses the current ontology
                        accepted_now.add(item['question'])   # and is a new agreement, on the answer in front of the person now
                        continue
                    if same and old.get('snapshot') is not None:
                        # A list edit keeps server-held identity evidence; accepting a new query is a separate decision.
                        item.update({key: old.get(key) for key in ('snapshot', 'status', 'answer', 'path')})
                    # the line's list is written last by every save, so it wins a tie (agreements are stamped to the second); an
                    # agreement is made for one query, so it lends its own only when it holds this question on the same query
                    lent = latest.get(item['question']) or {}
                    agreements = [c for c in (lent.get('confirmed') if lent.get('query') == item['query'] else None, old.get('confirmed') if old else None) if c]
                    if same and agreements:
                        item['confirmed'] = max(agreements, key=lambda c: c['at'])   # the page never holds it: an edit gives back the latest agreement
                    elif not same:
                        accepted_now.add(item['question'])
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            stored = output_dir / 'acceptance' / f"{memory_key(result)}.json"
            if not items:   # the last question was removed: this file has no fixed questions again
                result['evaluation'].pop('acceptance', None)
                stored.unlink(missing_ok=True)
            else:
                bundle = with_rules(result, json.loads(bundle_path.read_text(encoding='utf-8')))
                result['evaluation']['acceptance'] = record_confirmed(reviewed_acceptance(result, bundle, items), accepted_now,
                                                                      result['file']['sha256'], result['saved_as'])
                saved = {'saved_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'file': result['file'],
                         'purpose': result.get('purpose'), 'items': result['evaluation']['acceptance']['items']}
                stored.parent.mkdir(parents=True, exist_ok=True)
                stored.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding='utf-8')
            write_run(result_path, result)
            self.reply(200, result)

        def save_card(self):
            """What the client said, written down by the consultant: answers on the data-meaning card and on the open items,
            kept with the file. This run's own fixed questions are then asked again of the data, since the card may stop one;
            the file's shared list, which the next upload inherits, is not touched. Nothing is written unless every answer
            in the request is valid."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                name = str(payload.get('saved_as') or '')
                found = card_run(name)
                card, items, answered = card_for(found)
                cells_raw, items_raw = payload.get('cells') or [], payload.get('items') or []
                if not cells_raw and not items_raw:
                    raise ValueError('cells、items 至少要给一样')
                if items_raw:
                    stale_check(found[0])   # an answer keeps what the item was about on these rows: not older ones, and a reopen must not wipe the newest run's
                now = datetime.now(timezone.utc).isoformat(timespec='seconds')
                by = payload.get('by')   # who gave the answer: the client or whoever spoke to them, said by the person writing it down; data, not a signature
                cells = check_cells(card, cells_raw, by, now)
                answers = check_answers([*items, *answered], items_raw, by, now)
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            result, bundle, graph = found   # a run with no card has no cell or item to answer: the checks above refused it
            key = memory_key(result)
            stored = card_file(key)
            # an unlinked item answered "incomplete" marks the other end's object as only partly in the data; a cell the request sets itself wins
            cells = self.recorded({**linked_cells([*items, *answered], answers, stored['cells'], now), **cells})
            answers = self.recorded(answers)
            kept_card = output_dir / 'cards' / f'{key}.json'
            kept_card.parent.mkdir(parents=True, exist_ok=True)
            partial = kept_card.with_name(f'{key}.json.part')
            partial.write_text(json.dumps(with_changes(stored, cells, answers, now), ensure_ascii=False, indent=1), encoding='utf-8')
            partial.replace(kept_card)   # a reader never sees half a file
            if result['evaluation'].get('acceptance'):
                checked = reviewed_acceptance(result, bundle, result['evaluation']['acceptance']['items'])
                result = {**result, 'evaluation': {**result['evaluation'], 'acceptance': checked}}
                write_run((output_dir / name), result)
            card, items, answered = card_for((result, bundle, graph))
            self.reply(200, {'card': card, 'items': items, 'answered': answered})

        def recorded(self, entries):
            """Answers as they are kept: `by` stays whoever gave the answer, and who wrote it down, the signed-in account, goes in `recorded_by`
            (and `recorded_by_id`). With --no-auth there is no account and nothing is added."""
            if self.user['id'] is None:
                return entries
            return {k: v and {**v, 'recorded_by': self.user['display_name'], 'recorded_by_id': self.user['id']} for k, v in entries.items()}

        def code_column_request(self):
            """The run, the code column and the signer a code-meanings request is about; replies and returns None when it cannot be read."""
            try:
                payload = self.read_json()
                if payload is None:
                    return None
                found = workspace_run(str(payload.get('saved_as') or ''))
                if found is None:
                    raise ValueError('这份运行没有数据表，没有代码列')
                profiles, enums = code_state(found[0], found[1])
                profile = next((p for p in profiles if p['id'] == payload.get('id')), None)
                if profile is None:
                    raise ValueError('这一列已经不在清单上了')
                signer = self.signer(payload)
                check_mode(payload)
                return found, profile, enums, signer, payload
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
            return None

        def keep_code_state(self, found, change, what, because):
            """Write one property's element_state, work the run's answers out again, and answer with the lists as they now stand."""
            try:
                conn = open_workspace(output_dir / 'workspace.sqlite')
                try:
                    set_element_states(conn, [change])
                finally:
                    conn.close()
            except SelfConfirmation as exc:
                self.reply(403, {'error': str(exc)})
                return
            except Exception as exc:
                self.reply(500, {'error': f'{what}没有保存：{type(exc).__name__}: {exc}'[:300]})
                return
            warning = recompute_warning(found[0]['saved_as'], because) or views_warning(sync_run_views(found[0]))
            self.reply(200, {**code_reply(found), **({'warning': warning} if warning else {})})

        def save_code_meanings(self):
            """A person says what some values of one code column mean: the labels are kept on the property (element_state,
            confirmed, with the open item as its evidence) over what was kept before, and every place that shows the code
            reads them from there. A blank label takes a value's meaning back; none left takes the whole confirmation back."""
            request = self.code_column_request()
            if request is None:
                return
            found, profile, enums, signer, payload = request
            try:
                stale_check(found[0])
                posted = check_enum(profile, payload.get('values'))
            except ValueError as exc:
                self.reply(400, {'error': str(exc)})
                return
            merged = merge_enum((enums.get(profile['field']) or {}).get('values') or [], posted)
            element = f'property:{memory_key(found[0])}:{profile["field"]}'
            anchors = stored_anchors(code_anchor(profile, found[1]['sources'][profile['source']]['records'], key_columns(found[0]['ontology'], profile['source'])))   # what the person looked at: the next version is held against it
            change = (element, 'confirmed', f'open_item:{profile["id"]}', signer, {'values': merged, 'mode': check_mode(payload)}, anchors) if merged else (element, 'proposed', None, signer)
            given = [f'{e["value"]} = {e["label"]}' for e in posted if e['label']]
            held = {e['value'] for e in (enums.get(profile['field']) or {}).get('values', []) if e['label']}
            taken = [e['value'] for e in posted if not e['label'] and e['value'] in held]   # a blank for a value never confirmed takes nothing back
            what = '，'.join([*([f'已确认（{"、".join(given)}）'] if given else []), *([f'已收回（{"、".join(taken)}）'] if taken else [])])
            self.keep_code_state(found, change, '含义', f'「{profile["column"]}」的含义{what}')

        def save_repeat_rule(self):
            """A person says how the rows of a repeated key are read: both kept, the latest by a column, or a data error.
            Kept as a confirmed element_state with the open item as its evidence and the person who chose; {"rule": null}
            takes the choice back. Answers with the lists as they now stand."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                name = str(payload.get('saved_as') or '')
                found = card_run(name)
                if found is None:
                    raise ValueError('这份运行没有数据表')
                result, bundle, graph = found
                names = {t['key']: t.get('label') or t['key'] for t in normalize_proposal(result['ontology'])['object_types']}
                group = next((g for g in repeated_keys(result['ontology'], bundle, graph) if g['id'] == payload.get('id')), None)
                if group is None:
                    raise ValueError('这个重复的编号已经不在清单上了')
                signer = self.signer(payload)
                element = f'repeat_rule:{memory_key(result)}:{group["rule_key"]}'
                stale_check(result)
                if 'rule' in payload and payload['rule'] is None:
                    change = (element, 'proposed', None, signer)
                    because = f'{names[group["type"]]}（{group["source"]}表）重复编号的处理办法已收回'
                else:
                    change = (element, 'confirmed', f'open_item:{group["id"]}', signer, {**check_rule(group, payload), 'mode': check_mode(payload)})
                    said = {'keep_both': '每一行都留', 'data_error': '当作数据错误', 'keep_latest': f'只留「{change[4].get("column")}」最新的一行'}[change[4]['rule']]
                    because = f'{names[group["type"]]}（{group["source"]}表）重复的编号已选「{said}」'
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            try:
                conn = open_workspace(output_dir / 'workspace.sqlite')
                try:
                    set_element_states(conn, [change])
                finally:
                    conn.close()
                found = card_run(name)   # read again: the rule is part of what every reader of the rows sees
            except SelfConfirmation as exc:
                self.reply(403, {'error': str(exc)})
                return
            except Exception as exc:
                self.reply(500, {'error': f'处理办法没有保存：{type(exc).__name__}: {exc}'[:300]})
                return
            warning = recompute_warning(name, because) or views_warning(sync_run_views(found[0]))
            self.reply(200, {**code_reply(found), **({'warning': warning} if warning else {})})

        def confirm_again(self):
            """{"saved_as", "id": "review:<property|repeat_rule|view|relation>:<name>", "confirmed_by"}: a person looked again at a definition
            that waited for a second look (anchors.py) and keeps it as it is. It is confirmed again, by them, on the rows of this run:
            its anchors are taken from these rows now. A definition that cannot be kept as it is (its column is no longer a code, the
            column it orders by is gone, a view that reads a meaning still waiting) is refused with the reason."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                found = workspace_run(str(payload.get('saved_as') or ''))
                if found is None:
                    raise ValueError('这份运行没有数据表')
                signer = self.signer(payload)
                asked = re.fullmatch(r'review:(property|repeat_rule|view|relation):(.+)', str(payload.get('id') or ''), re.S)
                if asked is None:
                    raise ValueError('这一项不在“需要再看一眼”的清单上')
                prefix, name = asked.groups()
                result, bundle, graph = found
                stale_check(result)
                conn = open_workspace(output_dir / 'workspace.sqlite')
                try:
                    row = element_rows(conn, f'{prefix}:{memory_key(result)}:', 'checked').get(name)
                    if row is None:
                        raise ValueError('这一项已经不在“需要再看一眼”的清单上了')
                    content, anchors = row['content'], None
                    if prefix == 'property':
                        profile = next((p for p in code_candidates(result, bundle) if p['field'] == name), None)
                        if profile is None:
                            raise ValueError('这一列现在不再像一列代码，没法照旧确认；要改就去改它的含义')
                        anchors = code_anchor(profile, bundle['sources'][profile['source']]['records'], key_columns(result['ontology'], profile['source']))
                    elif prefix == 'repeat_rule':
                        group = next((g for g in repeated_keys(result['ontology'], bundle, graph or build_graph(result['ontology'], bundle)) if g['rule_key'] == name), None)
                        content = {**content, 'covers': sorted(o['identity'] for o in group['objects']) if group else []}
                        why = unmet(group, content) if group else None
                        if why:
                            raise ValueError(f'{why}没法照旧确认，请重新选一种处理办法')
                    elif prefix == 'view':
                        versions = {t['dataset']: t['version'] for t in (result.get('data_checks') or {}).get('tables', []) if t.get('status') == 'ok'}
                        anchors = view_anchor_now(conn, memory_key(result), run_id(result['saved_as']), result['ontology'], stored_tables(conn, result), name, content, versions)
                    else:
                        now = next((r for r in (result.get('data_checks') or {}).get('relations') or [] if r['key'] == name), None)
                        if now is None:
                            raise ValueError('这次的数据里查不出这条关系，没法照旧确认')
                        anchors = relation_anchor(now)
                finally:
                    conn.close()
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            except sqlite3.Error as exc:
                self.reply(500, {'error': f'再确认没有保存：{type(exc).__name__}: {exc}'[:300]})
                return
            self.keep_code_state(found, (row['element_id'], 'confirmed', row['evidence_ref'], signer, content, stored_anchors(anchors)), '再确认', f'「{name}」的定义照旧再确认了')

        def save_view(self):
            """A person defines a named view from confirmed meanings ("有效订单": 状态码 is not 已取消) or for the latest row per key
            ("最新快照"), or takes one back ({"name", "remove": true}). Kept as a confirmed element_state with the person who
            defined it; answers with the lists, the views among them, as they now stand."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                found = workspace_run(str(payload.get('saved_as') or ''))
                if found is None:
                    raise ValueError('这份运行没有数据表')
                signer = self.signer(payload)
                stale_check(found[0])
                conn = open_workspace(output_dir / 'workspace.sqlite')
                try:
                    versions = {t['dataset']: t['version'] for t in (found[0].get('data_checks') or {}).get('tables', []) if t.get('status') == 'ok'}
                    message = save_definition(conn, memory_key(found[0]), payload, stored_tables(conn, found[0]), found[0]['ontology'], signer,
                                              run_id(found[0]['saved_as']), versions,
                                              propose=self.user['id'] is not None and two_person(conn)['active'])   # a person's own view waits for a second person
                finally:
                    conn.close()
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            except SelfConfirmation as exc:
                self.reply(403, {'error': str(exc)})
                return
            except StaleProposal as exc:
                self.reply(409, {'error': str(exc)})
                return
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            except sqlite3.Error as exc:
                self.reply(500, {'error': f'视图没有保存：{type(exc).__name__}: {exc}'[:300]})
                return
            warning = views_warning(sync_run_views(found[0]))
            self.reply(200, {**code_reply(found), 'message': message, **({'warning': warning} if warning else {})})

        def run_pipeline_request(self):
            """{"saved_as", "pipeline": {"steps": [...]}}: the pipeline run on the tables this run stored and on its views
            (an input may name either), read-only. Answers with each node's rows in and out and, for a join, what it did (see
            pipelines.py). Nothing is written: not the workspace, not the run."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                name = str(payload.get('saved_as') or '')
                if not SAVED_NAME.match(name) or not (output_dir / name).exists():
                    raise FileNotFoundError(name)
                result = json.loads((output_dir / name).read_text(encoding='utf-8'))
                if not (result.get('data_checks') or {}).get('tables'):
                    raise ValueError('这次运行没有存进工作区的表，没有数据可以编排')
                found = card_run(name)   # None when the draft did not pass the checks: its tables are still stored and can be joined, but it has no definitions to read
                listed, codes = [], frozenset()
                if found is not None:
                    profiles, enums = code_state(found[0], found[1])
                    codes = {p['field'] for p in profiles} | set(enums)   # columns that are codes, confirmed or not: a sum of them means nothing
                    listed = view_context(result)['views']
                conn = readonly_workspace()   # read-only: a pipeline cannot change a table
                try:
                    tables = stored_tables(conn, result)
                    read_views(conn, run_id(name), listed)
                    reply = run_pipeline(conn, payload.get('pipeline'), tables, workspace_views(listed), codes)
                finally:
                    conn.close()
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            self.reply(200, reply)

        def dismiss_code_column(self):
            """A person says this column is not a code list ("不是代码"): kept as rejected on the property, so it is not offered again."""
            request = self.code_column_request()
            if request is None:
                return
            found, profile, _, signer, payload = request
            try:
                stale_check(found[0])
            except ValueError as exc:
                self.reply(400, {'error': str(exc)})
                return
            self.keep_code_state(found, (f'property:{memory_key(found[0])}:{profile["field"]}', 'rejected', f'open_item:{profile["id"]}', signer, {'mode': check_mode(payload)}), '“不是代码”',
                                 f'「{profile["column"]}」被说成不是代码列')

        def withdraw_code_decision(self):
            """{"saved_as", "id": "code_meaning:<table>.<column>", "confirmed_by"}: take back what was decided about a code column, whether its
            meanings were confirmed or it was said not to be a code; the column is a question again. Answers with the lists as they now stand."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                found = workspace_run(str(payload.get('saved_as') or ''))
                if found is None:
                    raise ValueError('这份运行没有数据表，没有代码列')
                signer = self.signer(payload)
                stale_check(found[0])
                prefix = f'property:{memory_key(found[0])}:'
                field = str(payload.get('id') or '').removeprefix('code_meaning:')
                conn = open_workspace(output_dir / 'workspace.sqlite')
                try:
                    decided = {*element_contents(conn, prefix), *element_rejected(conn, prefix)}
                finally:
                    conn.close()
                if field not in decided:
                    raise ValueError('这一列没有定过什么，没有可收回的')
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            column = field.partition('.')[2]
            self.keep_code_state(found, (f'{prefix}{field}', 'proposed', None, signer), '收回', f'「{column}」的判断已收回')

        def bulk_approve(self):
            """{"saved_as", "ids", "confirmed_by"}: approve together what is in the clean band (review_stack.relation_band): relations code
            verifies completely. The band is worked out again from the stored run, and once more inside the write; an id that is not in it
            refuses the whole request and writes nothing. What is written is the approved relations only, each marked bulk and signed by
            the confirmer; what others judged before (their signatures, versions, the run's own confirmer) is left as it is. Answers with the
            lists as they now stand."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                name = str(payload.get('saved_as') or '')
                found = workspace_run(name)
                if found is None:
                    raise ValueError('这份运行没有数据表')
                if payload.get('mode', 'bulk') != 'bulk':
                    raise ValueError('一起通过的 mode 只能是 bulk')
                signer = self.signer(payload, required=True)
                ids = payload.get('ids')
                if not isinstance(ids, list) or not ids or len(ids) > MAX_BULK or not all(isinstance(i, str) for i in ids):
                    raise ValueError(f'ids 要写成列表，至少一项，最多 {MAX_BULK} 项')
                stale_check(found[0])
                ids = list(dict.fromkeys(ids))
                in_band = {b['id'] for b in bulk_band_of(found[0], None)}
                outside = [i for i in ids if i not in in_band]
                if outside:
                    raise ValueError(f'有 {len(outside)} 件不在可以一起通过的范围里（有检查没通过，或已经定了）：{"、".join(i[:60] for i in outside[:5])}{"等" if len(outside) > 5 else ""}')
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            try:
                self.keep_bulk_relations(name, [i.partition(':')[2] for i in ids], ids, signer)
                found = workspace_run(name)   # read again: what was kept is part of what every reader sees
            except RunChanged as exc:
                self.reply(409, {'error': str(exc)})
                return
            except SelfConfirmation as exc:
                self.reply(403, {'error': str(exc)})
                return
            except Exception as exc:
                self.reply(500, {'error': f'批量通过没有保存：{type(exc).__name__}: {exc}'[:300]})
                return
            warning = views_warning(sync_run_views(found[0]))
            self.reply(200, {**code_reply(found), **({'warning': warning} if warning else {})})

        def keep_bulk_relations(self, name, keys, ids, signer):
            """Judge these relations right, in bulk, and nothing else. Inside the write lock the run is read again and the band worked out
            again from it: if a relation is no longer in it (someone judged or changed something meanwhile) nothing is written. The run's
            decisions get the approved relations added to what they were; the run's own confirmer and time, the signature and version of
            every other judgement, stay as they are."""
            path = output_dir / name
            earlier = json.loads(path.read_text(encoding='utf-8'))
            seen = {r['key']: r for r in (earlier.get('data_checks') or {}).get('relations') or []}
            changes = [(f'relation:{memory_key(earlier)}:{k}', 'confirmed', None, signer, {'mode': 'bulk'}, stored_anchors(relation_anchor(seen[k]))) for k in keys]
            conn = open_workspace(output_dir / 'workspace.sqlite')
            try:
                with element_state_writes(conn, changes) as rows:
                    result = json.loads(path.read_text(encoding='utf-8'))   # as it is now, with the write lock held
                    if newer_run(result) or not set(ids) <= {b['id'] for b in bulk_band_of(result, None)}:
                        raise RunChanged('这期间清单变了，什么都没有通过；请再看一遍清单')
                    confirmation = result['confirmation']
                    decisions = {**confirmation['decisions'], 'relations': {**(confirmation['decisions'].get('relations') or {}), **{k: {'verdict': 'ok'} for k in keys}}}
                    reference = confirmed_reference(result['ontology'], decisions)
                    refs = output_dir / 'references'
                    stored = refs / f"{memory_key(result)}.json"
                    if stored.exists():   # the reference the next upload is compared with has these relations too; whose it is does not change
                        self.archive_reference(refs, stored, result)
                        stored.write_text(json.dumps({**json.loads(stored.read_text(encoding='utf-8')), 'reference': reference}, ensure_ascii=False, indent=1), encoding='utf-8')
                    elements = {**(confirmation.get('elements') or {}), **{f'relations:{k}': {c: rows[change[0]][c] for c in ('state', 'evidence_ref', 'confirmed_by', 'confirmed_at', 'version')}
                                                                           for k, change in zip(keys, changes)}}
                    shown = result['evaluation'].get('reference')
                    write_run(path, {**result, 'confirmation': {**confirmation, 'decisions': decisions, 'reference': reference, 'elements': elements},
                                     'evaluation': {**result['evaluation'], **({'reference': {**shown, 'diff': compare_ontologies(parse_reference(reference), result['ontology'])}} if shown else {})}})
            finally:
                conn.close()

        def draft_code_meanings(self):
            """One call to the 字段释义员 for the code columns whose meanings nobody confirmed. The guesses are kept with
            the file and shown with the open item, each marked as strong only when the data backs it."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                found = workspace_run(str(payload.get('saved_as') or ''))
                if found is None:
                    raise ValueError('这份运行没有数据表，没有代码列')
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            if gateway is None:
                self.reply(503, {'error': NO_KEY})
                return
            result, bundle, graph = found
            profiles, enums = code_state(result, bundle)
            open_columns = [p for p in profiles if any(v['value'] not in {e['value'] for e in (enums.get(p['field']) or {}).get('values', [])} for v in p['values'])]
            drafted = draft_meanings(open_columns, gateway, result.get('purpose') or '')
            if drafted['error']:
                self.reply(502, {'error': drafted['error']})
                return
            path = output_dir / 'code_meanings' / f'{memory_key(result)}.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'columns': {**code_drafts(result), **drafted['columns']}, 'model': drafted['model'],
                                        'asked_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}, ensure_ascii=False, indent=1), encoding='utf-8')
            self.reply(200, {**code_reply(found), 'rejected': drafted['rejected']})

        def draft_form(self):
            """One call to the 字段释义员; what a person already wrote is kept."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                name = str(payload.get('saved_as') or '')
                result, bundle, _ = kept(name)
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            if gateway is None:
                self.reply(503, {'error': NO_KEY})
                return
            handover = result['evaluation'].get('handover') or handover_form(result['ontology'], bundle)
            drafted = draft_descriptions(result['ontology'], bundle, handover, gateway, result.get('purpose') or '')
            if drafted['error']:
                self.reply(502, {'error': drafted['error']})
                return

            def keep_person(was, new):
                """The draft fills in what nobody wrote yet; an object's or field's text a person wrote stays."""
                if was is None:
                    return new
                head = new if was.get('drafted') else was
                fields = dict(was['fields'])
                for path, f in new['fields'].items():
                    if fields.get(path, {}).get('drafted', True):
                        fields[path] = f
                return {**head, 'fields': fields}

            def merge(run):
                run['evaluation'].setdefault('handover', handover)
                old = form_state(run) or {'types': {}}
                types = {key: keep_person(old['types'].get(key), new) for key, new in drafted['types'].items()}
                stored = {'types': {**old['types'], **types}, 'model': drafted['model'], 'prompt_version': drafted['prompt_version']}
                form_path(run).parent.mkdir(parents=True, exist_ok=True)
                form_path(run).write_text(json.dumps(stored, ensure_ascii=False, indent=1), encoding='utf-8')
                run['evaluation']['form'] = {**form_state(run), 'rejected': drafted['rejected']}
            self.reply(200, write_back(output_dir / name, merge))

        def save_form(self):
            try:
                payload = self.read_json()
                if payload is None:
                    return
                name = str(payload.get('saved_as') or '')
                result, bundle, _ = kept(name)
                handover = result['evaluation'].get('handover') or handover_form(result['ontology'], bundle)
                form = parse_form(payload.get('form'), handover)
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            old = form_state(result) or {}
            stored = {**{k: v for k, v in old.items() if k != 'types'}, 'types': {**old.get('types', {}), **form['types']}}
            form_path(result).parent.mkdir(parents=True, exist_ok=True)
            form_path(result).write_text(json.dumps(stored, ensure_ascii=False, indent=1), encoding='utf-8')
            result['evaluation'].setdefault('handover', handover)
            result['evaluation']['form'] = form_state(result)
            write_run((output_dir / name), result)
            self.reply(200, result)

        def rules(self):
            """Adopt or decline rules for this file: {saved_as, adopted: [rule ids], declined: [rule ids]}, each the whole list."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                name = str(payload.get('saved_as') or '')
                result, bundle, graph = kept(name)
                adopted, declined = payload.get('adopted') or [], payload.get('declined') or []
                if not all(isinstance(x, str) for x in [*adopted, *declined]):
                    raise ValueError('adopted 和 declined 要写规则 id')
            except FileNotFoundError:
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            now = rules_state(result, bundle, graph)
            known = {r['id']: {k: v for k, v in r.items() if k != 'violations'} for r in now['candidates'] + now['adopted']}
            missing = [x for x in adopted if x not in known]
            if missing:
                self.reply(400, {'error': f'这份数据里没有这条规则：{missing[0]}'})
                return
            stored = output_dir / 'rules' / f"{memory_key(result)}.json"
            stored.parent.mkdir(parents=True, exist_ok=True)
            stored.write_text(json.dumps({'adopted': [known[x] for x in adopted], 'declined': sorted(set(declined) - set(adopted))},
                                         ensure_ascii=False, indent=1), encoding='utf-8')
            result['evaluation']['rules'] = rules_state(result, bundle, graph)
            write_run((output_dir / name), result)
            self.reply(200, result)

        def confirm(self):
            try:
                payload = self.read_json()
                if payload is None:
                    return
                result_path = self.load_run(payload)
                if not result_path.exists():
                    self.reply(404, {'error': '找不到这次上传的结果，请重新上传文件'})
                    return
                result = json.loads(result_path.read_text(encoding='utf-8'))
                reference = confirmed_reference(result['ontology'], payload.get('decisions'))
                signer = self.signer(payload)
                if payload['decisions'].get('relations'):   # a relation judged right keeps what its check found: only the newest run's
                    stale_check(result)
                cleared = payload.get('cleared') or []   # relations the page held a verdict on (as kept) and clicked off: a verdict taken back, not silence
                if not isinstance(cleared, list) or not all(isinstance(k, str) for k in cleared):
                    raise ValueError('cleared 要写成关系编号的列表')
                kept_bulk = bulk_judged(result)   # a page that loaded before a bulk approval does not have it: its silence about it is not a verdict
                silent = {k for k in kept_bulk if k not in cleared and not ((payload['decisions'].get('relations') or {}).get(k) or {}).get('verdict')}
                if silent:
                    payload = {**payload, 'decisions': {**payload['decisions'], 'relations': {**(payload['decisions'].get('relations') or {}), **{k: {'verdict': 'ok'} for k in silent}}}}
                    reference = confirmed_reference(result['ontology'], payload['decisions'])
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            earlier = result.get('confirmation') or {}
            if earlier.get('decisions') == payload.get('decisions') and earlier.get('confirmed_by') == signer and 'elements' in earlier:
                self.reply(200, result)   # the same judgement again (a retried call): nothing new to keep
                return
            try:   # the workspace rows are written first but kept only once the run files are written too: the two never disagree
                rules = repeat_rules(result)   # read before the write below holds the workspace
                conn = open_workspace(output_dir / 'workspace.sqlite')
                try:
                    on_file = element_ids(conn, 'object_type:') + element_ids(conn, 'relation:')
                    changes = element_changes(memory_key(result), payload['decisions'], (result.get('data_checks') or {}).get('keys') or [], signer, on_file)
                    seen = {r['key']: r for r in (result.get('data_checks') or {}).get('relations') or []}
                    for name, change in list(changes.items()):   # a relation judged right keeps what the check found when it was judged
                        kind, _, rkey = name.partition(':')
                        if kind == 'relations' and change[1] == 'confirmed' and rkey in seen:
                            changes[name] = (*change, None, stored_anchors(relation_anchor(seen[rkey])))
                    for k in silent & seen.keys():   # the bulk approval stays as it was: its signer, its mark, its version
                        changes[f'relations:{k}'] = (changes[f'relations:{k}'][0], 'confirmed', None, kept_bulk[k]['confirmed_by'], {'mode': 'bulk'}, stored_anchors(relation_anchor(seen[k])))
                    with element_state_writes(conn, list(changes.values())) as rows:
                        if json.loads(result_path.read_text(encoding='utf-8')).get('confirmation') != result.get('confirmation'):   # read again with the write lock held
                            raise RunChanged('这期间这次运行的确认有了变化（比如别人批量通过了关系），什么都没有保存；请刷新页面后再确认')
                        result = self.keep_confirmation(result, result_path, payload, reference, signer, rules, {
                            name: {k: rows[change[0]][k] for k in ('state', 'evidence_ref', 'confirmed_by', 'confirmed_at', 'version')}
                            for name, change in changes.items()})
                finally:
                    conn.close()
            except RunChanged as exc:
                self.reply(409, {'error': str(exc)})
                return
            except SelfConfirmation as exc:
                self.reply(403, {'error': str(exc)})
                return
            except Exception as exc:   # whatever failed, the person is told and nothing of the confirmation is kept
                self.reply(500, {'error': f'确认没有保存：{type(exc).__name__}: {exc}'[:300]})
                return
            self.reply(200, result)

        def archive_reference(self, refs, stored, result):
            """A changed judgement replaces the old one; keep the old one so it can still be read."""
            if stored.exists():
                old = json.loads(stored.read_text(encoding='utf-8'))
                (refs / 'history').mkdir(exist_ok=True)
                (refs / 'history' / f"{result['file']['sha256'][:8]}-{old['confirmed_at'].replace(':', '')}.json").write_text(
                    json.dumps(old, ensure_ascii=False, indent=1), encoding='utf-8')

        def keep_confirmation(self, result, result_path, payload, reference, signer, rules, elements):
            """Write what a saved confirmation changes in the run files; returns the run as it now stands."""
            now = datetime.now(timezone.utc).isoformat(timespec='seconds')
            refs = output_dir / 'references'
            refs.mkdir(parents=True, exist_ok=True)
            stored = refs / f"{memory_key(result)}.json"
            self.archive_reference(refs, stored, result)
            stored.write_text(json.dumps(
                {'confirmed_at': now, 'confirmed_by': signer, 'purpose': result.get('purpose'), 'saved_as': result['saved_as'], 'file': result['file'], 'reference': reference}, ensure_ascii=False, indent=1), encoding='utf-8')
            result['confirmation'] = {'confirmed_at': now, 'confirmed_by': signer, 'decisions': payload['decisions'], 'reference': reference, 'elements': elements}
            result['evaluation']['reference'] = {'name': '你确认过的本体', 'confirmed': True, 'confirmed_at': now, 'confirmed_by': signer, 'purpose': result.get('purpose'), 'compared_at': now,
                                                 'diff': compare_ontologies(parse_reference(reference), result['ontology'])}
            acceptance = result['evaluation'].get('acceptance')
            bundle_path = output_dir / result['saved_as'].replace('.json', '.bundle.json')
            if acceptance and result['file'].get('kind') != 'document' and bundle_path.exists():
                bundle = {**json.loads(bundle_path.read_text(encoding='utf-8')), 'repeat_rules': rules}
                # only this run's own copy: the file's shared list may be newer than this run, and the next upload inherits it as it is
                result['evaluation']['acceptance'] = reviewed_acceptance(result, bundle, acceptance['items'])
            write_run(result_path, result)
            return result

        def confirm_derived(self):
            """A person confirms a derived measure: code checks the formula again, keeps it with the file, and answers
            again every question of this run that was waiting for it."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                result_path = self.load_run(payload)
                if not result_path.exists():
                    self.reply(404, {'error': '找不到这次上传的结果，请重新上传文件'})
                    return
                result = json.loads(result_path.read_text(encoding='utf-8'))
                if result['file'].get('kind') == 'document':
                    raise ValueError('文档没有数据行，不能定义指标')
                formula, why = parse_derived(result['ontology'], payload.get('derive'))
                if formula is None:
                    raise ValueError(why)
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            key = memory_key(result)
            kept = [d for d in derived_of(key) if (d['type'], d['label']) != (formula['type'], formula['label'])]
            measures = kept + [{**formula, 'confirmed_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}]
            (output_dir / 'derived').mkdir(parents=True, exist_ok=True)
            (output_dir / 'derived' / f'{key}.json').write_text(json.dumps({'measures': measures}, ensure_ascii=False, indent=1), encoding='utf-8')
            bundle = with_rules(result, json.loads((output_dir / result['saved_as'].replace('.json', '.bundle.json')).read_text(encoding='utf-8')))
            reviewed = without_wrong(result['ontology'], (result.get('confirmation') or {}).get('decisions'))
            graph = build_graph(result['ontology'], bundle)
            cells = card_cells(result, bundle, graph)
            answer_with = make_answerer(result, bundle, reviewed, measures, cells, graph)
            rounds = [*(result['evaluation'].get('asked') or []), *([result['evaluation']['questions']] if result['evaluation'].get('questions') else [])]
            for answered in rounds:
                for i, item in enumerate(answered.get('items') or []):
                    wanted = ((item.get('query') or {}).get('measure') or {}).get('derived') if isinstance(item.get('query'), dict) else None
                    if wanted != formula['label'] or item.get('query', {}).get('start') != formula['type']:
                        continue
                    again = answer_with(item['query'], item['question'], item.get('definitions_used'), check=not item.get('edited'), told=item.get('definitions_told') or [])
                    answered['items'][i] = {**{k: v for k, v in item.items() if k not in ('derive', 'reason', 'answer', 'path', 'status', 'evidence', 'unmet', 'upstream', 'understood')}, **again}
                answered['answered'] = sum(x['status'] == 'answered' for x in answered.get('items') or [])
            result['evaluation']['derived'] = measures
            write_run(result_path, result)
            self.reply(200, result)

        def requery(self):
            """A question asked again with one of its conditions taken off, answered by code alone (so with no model key
            too). The answer is kept as a new round beside the others; the page can accept it in place of the old one."""
            try:
                payload = self.read_json()
                if payload is None:
                    return
                result_path = self.load_run(payload)
                question, drop = payload.get('question'), payload.get('drop')
                if not isinstance(question, str) or not isinstance(drop, dict) or not {'field', 'equals'} <= drop.keys():
                    raise ValueError('要写清题目原文，和要去掉的条件 {"field": …, "equals": …}')
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            bundle_path = output_dir / result_path.name.replace('.json', '.bundle.json')
            if not result_path.exists() or not bundle_path.exists():
                self.reply(404, {'error': '找不到这次上传的结果，请重新上传文件'})
                return
            result = json.loads(result_path.read_text(encoding='utf-8'))
            if result['file'].get('kind') == 'document':
                self.reply(400, {'error': '文档没有数据行可以查询；评测二只对数据表可用'})
                return
            if result['ontology']['status'] != 'auto_built_verified':
                self.reply(400, {'error': blocked_text(result, '不能出题')})
                return
            evaluation = result['evaluation']
            accepted = (evaluation.get('acceptance') or {}).get('items') or []
            # the questions asked one by one, newest first; then the model's own round, which the page offers this for too
            asked = [i for r in reversed(evaluation.get('asked') or []) for i in reversed(r['items']) if i['question'] == question]
            own_round = [i for i in (evaluation.get('questions') or {}).get('items') or [] if i['question'] == question]
            candidates = asked + own_round + [i for i in accepted if i['question'] == question]
            if not candidates:
                self.reply(404, {'error': '找不到这道题，可能已经被删掉了'})
                return
            queried = [i for i in candidates if isinstance(i.get('query'), dict)]
            if not queried:
                self.reply(400, {'error': '这道题没有查询，不能去掉条件重算'})
                return
            where_of = lambda i: i['query'].get('where') if isinstance(i['query'].get('where'), list) else []
            # the check pack names a field without its table, the query may carry it ("orders.地区")
            same = lambda w: isinstance(w, dict) and drop['field'] in (w.get('field'), str(w.get('field')).partition('.')[2]) \
                and w.get('equals') == drop['equals']
            # the latest version still holding the condition: an accepted question keeps it after the ask was edited
            found = next((i for i in queried if any(map(same, where_of(i)))), None)
            if found is None:
                self.reply(400, {'error': '这道题的查询里没有这个条件'})
                return
            query = {**found['query'], 'where': [w for w in where_of(found) if not same(w)]}
            reviewed = without_wrong(result['ontology'], (result.get('confirmation') or {}).get('decisions'))
            bundle = with_meanings(result, json.loads(bundle_path.read_text(encoding='utf-8')))
            answer = make_answerer(result, bundle, reviewed, derived_of(memory_key(result)), card_cells(result, bundle))(query, question, check=False)   # the person took a condition off on purpose
            dropped = [*((found.get('edited') or {}).get('dropped') or []), {'field': drop['field'], 'equals': drop['equals']}]
            evaluation.setdefault('asked', []).append({
                'prompt_version': None, 'model': None, 'asked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'items': [{'question': question, 'reasoning': '', 'query': query, **answer, 'asked': True, 'edited': {'dropped': dropped}}],
                'answered': int(answer['status'] == 'answered'), 'total': 1, 'error': None})
            write_run(result_path, result)
            self.reply(200, result)

        def ask(self):
            try:
                payload = self.read_json()
                if payload is None:
                    return
                name = str(payload.get('saved_as') or '')
                if not SAVED_NAME.match(name):
                    raise ValueError('saved_as 不是这个服务保存的结果名')
                question = payload.get('question')
                if question is not None and (not isinstance(question, str) or not 0 < len(question.strip()) <= 300):
                    raise ValueError('问题要写 1–300 个字')
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            result_path, bundle_path = output_dir / name, output_dir / name.replace('.json', '.bundle.json')
            if not result_path.exists() or not bundle_path.exists():
                self.reply(404, {'error': '找不到这次上传的结果，请重新上传文件'})
                return
            if gateway is None:
                self.reply(503, {'error': NO_KEY})
                return
            with runs_lock:
                result = json.loads(result_path.read_text(encoding='utf-8'))
            if result['file'].get('kind') == 'document':
                self.reply(400, {'error': '文档没有数据行可以查询；评测二只对数据表可用'})
                return
            if result['ontology']['status'] != 'auto_built_verified':
                self.reply(400, {'error': blocked_text(result, '不能出题')})
                return
            bundle = with_meanings(result, json.loads(bundle_path.read_text(encoding='utf-8')))
            reviewed = without_wrong(result['ontology'], (result.get('confirmation') or {}).get('decisions'))
            cells = card_cells(result, bundle)
            answerer = make_answerer(result, bundle, reviewed, derived_of(memory_key(result)), cells)
            answered = ask_questions(reviewed, bundle, gateway, question.strip() if question else None, derived=derived_of(memory_key(result)), card=cells,
                                     answerer=answerer, definitions=answerer.definitions)
            if answered['error'] and answered['error'].startswith('模型请求失败'):
                self.reply(502, {'error': answered['error']})
                return
            keeps = self.user['role'] != 'viewer'   # a viewer reads: the answer comes back and nothing is written into the run
            with runs_lock:
                latest = json.loads(result_path.read_text(encoding='utf-8'))
                if (latest.get('confirmation') or {}).get('decisions') != (result.get('confirmation') or {}).get('decisions'):
                    self.reply(409, {'error': '等待回答期间，本体的人工确认已改变。这次回答没有保存，请按最新确认重新提问。'})
                    return
                if keeps:
                    answered = {**answered, 'asked_by': self.user['display_name'], 'asked_by_id': self.user['id']}   # who put the question to the run
                if question:
                    latest['evaluation'].setdefault('asked', []).append(answered)
                else:
                    latest['evaluation']['questions'] = answered
                if keeps:
                    write_run(result_path, latest)
                    conn = open_workspace(output_dir / 'workspace.sqlite')
                    try:
                        log_write(conn, self.user['display_name'], 'write:ask', 'saved', {'saved_as': name[:80]})
                    finally:
                        conn.close()
            self.reply(200, latest)

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.gate = gate
    gate.origins |= {f'http://{h}:{server.server_port}' for h in LOOPBACK}   # the port is known only now when port=0
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'output/ontology-runs',
                        help='where runs, confirmations and rules are kept; point a trial run elsewhere')
    parser.add_argument('--origin', action='append', default=[], metavar='URL',
                        help='an address people reach the service at besides http://127.0.0.1:<port> (the https address of the proxy in front, or a dev server); repeat for several')
    parser.add_argument('--trusted-proxy', action='append', default=None, metavar='ADDRESS',
                        help='the address of the proxy in front, whose X-Forwarded-For is believed (default with an https --origin: this machine); repeat for several')
    parser.add_argument('--no-auth', action='store_true', help='no sign-in: every request is the local admin. Only for a trial on your own machine; needs ONTOPOC_DEV=1, and refuses --origin and proxied requests')
    args = parser.parse_args(argv)
    gateway = gateway_from_env()
    os.umask(0o077)   # files the service makes (runs, confirmations, the model log, the workspace) are this account's only
    try:
        server = make_server(args.port, gateway, output_dir=args.data_dir, no_auth=args.no_auth, origins=args.origin, trusted_proxies=args.trusted_proxy)
    except ValueError as exc:
        parser.error(str(exc))
    print(f'Ontology API: http://127.0.0.1:{server.server_port}'
          + ('' if gateway else '  (no model key: set DEEPSEEK_API_KEY to build ontologies)'), flush=True)
    if args.no_auth:
        print('Sign-in is OFF (--no-auth): every request is the local admin. Do not use this on a shared machine.', flush=True)
    elif server.gate.needs_first_admin():
        print('No accounts yet. Make the first admin on this machine:  python -m ontology_poc_generator.accounts create-admin'
              + ('' if args.data_dir == ROOT / 'output/ontology-runs' else f' --data-dir {args.data_dir}'), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
