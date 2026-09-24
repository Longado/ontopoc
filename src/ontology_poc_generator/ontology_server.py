"""Local-only upload API: a business file in, a verified company ontology and its evaluation out."""
import argparse
import base64
import binascii
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs, unquote, urlsplit
import uuid

from ontology_poc_generator.company_documents import DOCUMENT_SUFFIXES, build_and_evaluate_document, load_document_file
from ontology_poc_generator.org_documents import build_and_evaluate_org, org_mermaid
from ontology_poc_generator.company_ontology import build_and_evaluate, build_company_ontology
from ontology_poc_generator.company_sources import DEFAULT_PURPOSE, MAX_BYTES, TABLE_SUFFIXES, SourceFileError, load_table_file, load_table_files
from ontology_poc_generator.model_gateway import OpenAICompatibleGateway
from ontology_poc_generator.model_preview import model_preview
from ontology_poc_generator.agent_harness import LoggedGateway
from ontology_poc_generator.name_variants import propose_name_variants
from ontology_poc_generator.object_rows import find_instances, neighbourhood, object_rows
from ontology_poc_generator.public_ontology import build_graph
from ontology_poc_generator.relation_suggestions import suggest_relations
from ontology_poc_generator.rule_discovery import check_rules, discover_rules
from ontology_poc_generator.versions import version_diff
from ontology_poc_generator.field_descriptions import MAX_DESCRIPTION, MAX_LABEL, draft_descriptions
from ontology_poc_generator.handover_form import handover_form
from ontology_poc_generator.object_forms import form_files
from ontology_poc_generator.ttl_export import ttl_files
import io
import zipfile
from urllib.parse import quote as url_quote
from ontology_poc_generator.ontology_acceptance import check_acceptance, parse_acceptance
from ontology_poc_generator.ontology_compare import ReferenceFileError, compare_ontologies, parse_reference
from ontology_poc_generator.ontology_confirm import confirmed_reference, prefill_from_reference, without_wrong
from ontology_poc_generator.ontology_questions import ask_questions
from ontology_poc_generator.ontology_stability import STABILITY_RUNS, stability_of
from ontology_poc_generator.recognition import model_failure_text

ROOT = Path(__file__).resolve().parents[2]
MAX_BODY = MAX_BYTES * 4 // 3 + 4096  # base64 grows the file by a third, plus the JSON around it
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


def make_server(port=8767, gateway=None, output_dir: Path = ROOT / 'output/ontology-runs', code_dir: Path = Path(__file__).parent):
    running = code_fingerprint(code_dir)
    if gateway is not None:   # every model call, from any agent, leaves one line beside the runs
        gateway = LoggedGateway(gateway, output_dir / 'model_calls.jsonl')
    jobs, jobs_lock = {}, threading.Lock()
    # one run file is read, changed and written back by several endpoints; this keeps two of them from overwriting each other
    runs_lock = threading.Lock()
    jobs_dir = output_dir / 'jobs'
    graphs, graphs_lock = {}, threading.Lock()   # a kept run's graph, built once: the file and the ontology never change

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
                bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
                graphs[name] = (bundle, build_graph(result['ontology'], bundle))
        return (result, *graphs[name])

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

    def finish_build(bundle, is_document, progress=None, previous=None):
        if bundle.get('mode') == 'org':
            return save_build(bundle, build_and_evaluate_org(bundle, gateway, progress), progress, previous)
        if is_document:
            return save_build(bundle, build_and_evaluate_document(bundle, gateway, progress), progress, previous)
        # the extra runs start together with the shown one, so three runs take about as long as one
        with ThreadPoolExecutor(max_workers=STABILITY_RUNS - 1) as pool:
            extra = [pool.submit(build_company_ontology, bundle, gateway) for _ in range(STABILITY_RUNS - 1)]
            result = build_and_evaluate(bundle, gateway, progress)
            if result['ontology']['status'] == 'auto_built_verified' and bundle['decision'] != DEFAULT_PURPOSE:
                # the person's own question is answered with the draft; the model's round of questions is on request
                if progress:
                    progress('questions', {})
                answered = ask_questions(result['ontology'], bundle, gateway, purpose_only=True)
                if answered['items'] or answered['error']:
                    result['evaluation']['asked'] = [answered]
            if result['ontology']['status'] == 'auto_built_verified':
                if progress:
                    progress('stability', {'total': STABILITY_RUNS - 1})
                result['evaluation']['stability'] = stability_of(result['ontology'], [extra_result(f) for f in extra])
        return save_build(bundle, result, progress, previous)

    def extra_result(future):
        try:
            return future.result()
        except Exception as exc:   # an extra run is evidence, not the answer: its failure is counted, the upload goes on
            return {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'[:200]}

    def save_build(bundle, result, progress=None, previous_name=None):
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
                result['evaluation']['acceptance'] = check_acceptance(result['ontology'], bundle, saved['items'])
                accepted.write_text(json.dumps({**saved, 'items': result['evaluation']['acceptance']['items']}, ensure_ascii=False, indent=1), encoding='utf-8')
        if result['ontology']['status'] == 'auto_built_verified' and result['file'].get('kind') != 'document':
            result['evaluation']['rules'] = rules_state(result, bundle)
            if form_state(result):
                result['evaluation']['form'] = form_state(result)
        result['saved_as'] = name
        (output_dir / name).write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        # the uploaded rows stay on this machine so later questions can be answered from them
        (output_dir / name.replace('.json', '.bundle.json')).write_text(json.dumps(bundle, ensure_ascii=False), encoding='utf-8')
        return 200, result
    def write_back(path, change):
        """Apply one change to the run as it is on disk now: whatever was saved while the model was thinking stays."""
        with runs_lock:
            result = json.loads(path.read_text(encoding='utf-8'))
            change(result)
            path.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        return result

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def reply(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
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

        def do_GET(self):
            if not self.local_request():
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
            if self.path.startswith('/api/ontology/runs/') and self.path.count('/') > 4:
                self.object_page()
                return
            if self.path.startswith('/api/ontology/runs/'):
                self.open_run(self.path.rsplit('/', 1)[1])
                return
            if self.path != '/api/ontology/health':
                self.reply(404, {'error': 'Unknown ontology endpoint'})
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
            try:
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
                    if (query.get('format') or [''])[0] == 'json':
                        self.reply(200, {'files': files})
                    else:
                        packed = io.BytesIO()
                        with zipfile.ZipFile(packed, 'w', zipfile.ZIP_DEFLATED) as z:
                            for file_name, text in files.items():
                                z.writestr(file_name, text.encode('utf-8'))
                        self.reply_file(packed.getvalue(), 'application/zip', f"{name.split('.')[0]}-{zip_name}.zip")
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

        def read_json(self):
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                self.reply(413, {'error': f'文件太大，上限 {MAX_BYTES // 1024 // 1024} MB。'})
                return None
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.reply(415, {'error': 'Expected application/json'})
                return None
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('请求必须是 JSON 对象')
            return payload

        def do_POST(self):
            if not self.local_request():
                return
            if self.path == '/api/ontology/ask':
                self.ask()
                return
            # compare, confirm and acceptance read, change and write one run without a model call: they hold runs_lock
            # throughout; ask and variants wait on the model first and take it only to write (see write_back)
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
            self.reply(*finish_build(bundle, is_document, None, previous))

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

            def run():
                try:
                    status, body = finish_build(bundle, is_document, report, previous)
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
            result['evaluation']['reference'] = {
                'name': str(payload.get('reference_name') or '参考本体')[:120],
                'compared_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'diff': compare_ontologies(reference, result['ontology'])}
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            self.reply(200, result)

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
                self.reply(400, {'error': '本体没有通过结构核验，先看退回的原因'})
                return
            bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
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
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            stored = output_dir / 'acceptance' / f"{memory_key(result)}.json"
            if not items:   # the last question was removed: this file has no fixed questions again
                result['evaluation'].pop('acceptance', None)
                stored.unlink(missing_ok=True)
            else:
                bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
                result['evaluation']['acceptance'] = check_acceptance(result['ontology'], bundle, items)
                saved = {'saved_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'file': result['file'],
                         'purpose': result.get('purpose'), 'items': result['evaluation']['acceptance']['items']}
                stored.parent.mkdir(parents=True, exist_ok=True)
                stored.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding='utf-8')
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            self.reply(200, result)

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
            (output_dir / name).write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
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
            (output_dir / name).write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
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
                signer = payload.get('confirmed_by')
                if signer is not None and (not isinstance(signer, str) or len(signer.strip()) > 40):
                    raise ValueError('确认人最多写 40 个字')
                signer = (signer or '').strip() or None
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            now = datetime.now(timezone.utc).isoformat(timespec='seconds')
            refs = output_dir / 'references'
            refs.mkdir(parents=True, exist_ok=True)
            stored = refs / f"{memory_key(result)}.json"
            if stored.exists():   # a changed judgement replaces the old one; keep the old one so it can still be read
                old = json.loads(stored.read_text(encoding='utf-8'))
                (refs / 'history').mkdir(exist_ok=True)
                (refs / 'history' / f"{result['file']['sha256'][:8]}-{old['confirmed_at'].replace(':', '')}.json").write_text(
                    json.dumps(old, ensure_ascii=False, indent=1), encoding='utf-8')
            stored.write_text(json.dumps(
                {'confirmed_at': now, 'confirmed_by': signer, 'purpose': result.get('purpose'), 'saved_as': result['saved_as'], 'file': result['file'], 'reference': reference}, ensure_ascii=False, indent=1), encoding='utf-8')
            result['confirmation'] = {'confirmed_at': now, 'confirmed_by': signer, 'decisions': payload['decisions'], 'reference': reference}
            result['evaluation']['reference'] = {'name': '你确认过的本体', 'confirmed': True, 'confirmed_at': now, 'confirmed_by': signer, 'purpose': result.get('purpose'), 'compared_at': now,
                                                 'diff': compare_ontologies(parse_reference(reference), result['ontology'])}
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
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
            result = json.loads(result_path.read_text(encoding='utf-8'))
            if result['file'].get('kind') == 'document':
                self.reply(400, {'error': '文档没有数据行可以查询；评测二只对数据表可用'})
                return
            if result['ontology']['status'] != 'auto_built_verified':
                self.reply(400, {'error': '本体没有通过结构核验，不能出题'})
                return
            bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
            reviewed = without_wrong(result['ontology'], (result.get('confirmation') or {}).get('decisions'))
            answered = ask_questions(reviewed, bundle, gateway, question.strip() if question else None)
            if answered['error'] and answered['error'].startswith('模型请求失败'):
                self.reply(502, {'error': answered['error']})
                return
            self.reply(200, write_back(result_path, (lambda r: r['evaluation'].setdefault('asked', []).append(answered)) if question
                                       else (lambda r: r['evaluation'].update(questions=answered))))

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'output/ontology-runs',
                        help='where runs, confirmations and rules are kept; point a trial run elsewhere')
    args = parser.parse_args(argv)
    gateway = gateway_from_env()
    server = make_server(args.port, gateway, output_dir=args.data_dir)
    print(f'Ontology API: http://127.0.0.1:{server.server_port}'
          + ('' if gateway else '  (no model key: set DEEPSEEK_API_KEY to build ontologies)'), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
