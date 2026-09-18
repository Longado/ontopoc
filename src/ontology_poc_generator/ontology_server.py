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
from ontology_poc_generator.company_ontology import build_and_evaluate, build_company_ontology
from ontology_poc_generator.company_sources import MAX_BYTES, TABLE_SUFFIXES, SourceFileError, load_table_file, load_table_files
from ontology_poc_generator.model_gateway import OpenAICompatibleGateway
from ontology_poc_generator.model_preview import model_preview
from ontology_poc_generator.agent_harness import LoggedGateway
from ontology_poc_generator.name_variants import propose_name_variants
from ontology_poc_generator.object_rows import object_rows
from ontology_poc_generator.ontology_acceptance import check_acceptance, parse_acceptance
from ontology_poc_generator.ontology_compare import ReferenceFileError, compare_ontologies, parse_reference
from ontology_poc_generator.ontology_confirm import confirmed_reference, prefill_from_reference
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
        files = payload.get('files')
        if not isinstance(files, list):
            filename, data, is_document = decode_part(payload)
            return (load_document_file if is_document else load_table_file)(filename, data, payload.get('purpose')), is_document
        if not files:
            raise SourceFileError('没有选择文件')
        parts = []
        for part in files:
            filename, data, is_document = decode_part(part if isinstance(part, dict) else {})
            if is_document:
                raise SourceFileError(f'{Path(filename).name}：一次只能传数据表，或者单独传一份文档，不能混在一起')
            parts.append((filename, data))
        return load_table_files(parts, payload.get('purpose')), False

    def previous_run(sha256):
        """The latest verified earlier run of the same file, so a rerun shows what changed."""
        for path in sorted(output_dir.glob('*.json'), reverse=True):
            if path.name.endswith('.bundle.json') or not SAVED_NAME.match(path.name):
                continue
            earlier = json.loads(path.read_text(encoding='utf-8'))
            if earlier['file']['sha256'] == sha256 and earlier['ontology']['status'] == 'auto_built_verified':
                return earlier
        return None

    def finish_build(bundle, is_document, progress=None):
        if is_document:
            return save_build(bundle, build_and_evaluate_document(bundle, gateway, progress), progress)
        # the extra runs start together with the shown one, so three runs take about as long as one
        with ThreadPoolExecutor(max_workers=STABILITY_RUNS - 1) as pool:
            extra = [pool.submit(build_company_ontology, bundle, gateway) for _ in range(STABILITY_RUNS - 1)]
            result = build_and_evaluate(bundle, gateway, progress)
            if result['ontology']['status'] == 'auto_built_verified':
                if progress:
                    progress('questions', {})
                result['evaluation']['questions'] = ask_questions(result['ontology'], bundle, gateway)
                if progress:
                    progress('stability', {'total': STABILITY_RUNS - 1})
                result['evaluation']['stability'] = stability_of(result['ontology'], [extra_result(f) for f in extra])
        return save_build(bundle, result, progress)

    def extra_result(future):
        try:
            return future.result()
        except Exception as exc:   # an extra run is evidence, not the answer: its failure is counted, the upload goes on
            return {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'[:200]}

    def save_build(bundle, result, progress=None):
        outage = [e['message'] for a in result['ontology']['attempts'] for e in a['errors'] if e['code'] == 'model_request_failed']
        if result['ontology']['status'] != 'auto_built_verified' and outage:
            return 502, {'error': model_failure_text(outage[-1])}
        now = datetime.now(timezone.utc)
        name = f'{now.strftime("%Y%m%dT%H%M%S")}{now.microsecond // 1000:03d}Z-{bundle["file"]["sha256"][:8]}.json'
        output_dir.mkdir(parents=True, exist_ok=True)
        previous = previous_run(bundle['file']['sha256'])
        if previous and result['ontology']['status'] == 'auto_built_verified':
            result['previous'] = {'saved_as': previous['saved_as'], 'started_at': previous['started_at'], 'purpose': previous.get('purpose'),
                                  'counts': {'types': len(previous['ontology']['object_types']), 'relations': len(previous['ontology']['relations'])},
                                  'diff': compare_ontologies(previous['ontology'], result['ontology'])}
        confirmed = output_dir / 'references' / f"{bundle['file']['sha256']}.json"
        if confirmed.exists() and result['ontology']['status'] == 'auto_built_verified':
            # a person confirmed an earlier run of this file: compare against that judgement without being asked
            ref = json.loads(confirmed.read_text(encoding='utf-8'))
            result['evaluation']['reference'] = {'name': '你确认过的本体', 'confirmed': True, 'confirmed_at': ref['confirmed_at'], 'confirmed_by': ref.get('confirmed_by'),
                                                 'purpose': ref.get('purpose'),   # what the judgement was made for; this upload may be for something else
                                                 'compared_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                                                 'diff': compare_ontologies(parse_reference(ref['reference']), result['ontology']),
                                                 'suggested': prefill_from_reference(result['ontology'], ref['reference'])}
        accepted = output_dir / 'acceptance' / f"{bundle['file']['sha256']}.json"
        if accepted.exists() and result['ontology']['status'] == 'auto_built_verified' and result['file'].get('kind') != 'document':
            # the questions a person fixed for this file: the same queries, so two runs can be judged on the same thing
            with runs_lock:
                saved = json.loads(accepted.read_text(encoding='utf-8'))
                result['evaluation']['acceptance'] = check_acceptance(result['ontology'], bundle, saved['items'])
                accepted.write_text(json.dumps({**saved, 'items': result['evaluation']['acceptance']['items']}, ensure_ascii=False, indent=1), encoding='utf-8')
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
            if self.path.startswith('/api/ontology/runs/') and '/objects/' in self.path:
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
            """One object's rows from a kept run, a page at a time: /api/ontology/runs/<run>/objects/<type>?page=N"""
            url = urlsplit(self.path)
            name, _, type_key = url.path[len('/api/ontology/runs/'):].partition('/objects/')
            type_key = unquote(type_key)
            bundle_path = output_dir / name.replace('.json', '.bundle.json')
            if not SAVED_NAME.match(name) or not (output_dir / name).exists() or not bundle_path.exists():
                self.reply(404, {'error': '找不到这次运行，可能已经被删掉了'})
                return
            try:
                page = int((parse_qs(url.query).get('page') or ['1'])[0])
                result = json.loads((output_dir / name).read_text(encoding='utf-8'))
                if result['file'].get('kind') == 'document':
                    raise ValueError('文档没有数据行')
                self.reply(200, object_rows(result['ontology'], json.loads(bundle_path.read_text(encoding='utf-8')), type_key, page))
            except KeyError:
                self.reply(404, {'error': f'这份本体里没有对象 {type_key}'})
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
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            if gateway is None:
                self.reply(503, {'error': NO_KEY})
                return
            self.reply(*finish_build(bundle, is_document))

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
                    status, body = finish_build(bundle, is_document, report)
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
            stored = output_dir / 'acceptance' / f"{result['file']['sha256']}.json"
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
            stored = refs / f"{result['file']['sha256']}.json"
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
            answered = ask_questions(result['ontology'], bundle, gateway, question.strip() if question else None)
            if answered['error'] and answered['error'].startswith('模型请求失败'):
                self.reply(502, {'error': answered['error']})
                return
            self.reply(200, write_back(result_path, (lambda r: r['evaluation'].setdefault('asked', []).append(answered)) if question
                                       else (lambda r: r['evaluation'].update(questions=answered))))

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8767)
    gateway = gateway_from_env()
    server = make_server(parser.parse_args().port, gateway)
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
