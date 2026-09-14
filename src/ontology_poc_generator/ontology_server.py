"""Local-only upload API: a business file in, a verified company ontology and its evaluation out."""
import argparse
import base64
import binascii
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from ontology_poc_generator.company_ontology import build_and_evaluate
from ontology_poc_generator.company_sources import MAX_BYTES, SourceFileError, load_table_file
from ontology_poc_generator.model_gateway import OpenAICompatibleGateway
from ontology_poc_generator.ontology_compare import ReferenceFileError, compare_ontologies, parse_reference
from ontology_poc_generator.ontology_questions import ask_questions

ROOT = Path(__file__).resolve().parents[2]
MAX_BODY = MAX_BYTES * 4 // 3 + 4096  # base64 grows the file by a third, plus the JSON around it
SAVED_NAME = re.compile(r'^\d{8}T\d{6}Z-[0-9a-f]{8}\.json$')


def gateway_from_env():
    key = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('EIP_MODEL_API_KEY')
    if not key:
        return None
    return OpenAICompatibleGateway(api_base='https://api.deepseek.com', api_key=key,
                                   model=os.environ.get('EIP_MODEL_NAME', 'deepseek-flash'), timeout_seconds=180, temperature=0)


def make_server(port=8767, gateway=None, output_dir: Path = ROOT / 'output/ontology-runs'):
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
            if self.path != '/api/ontology/health':
                self.reply(404, {'error': 'Unknown ontology endpoint'})
                return
            self.reply(200, {'model_ready': gateway is not None})

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
            if self.path == '/api/ontology/compare':
                self.compare()
                return
            if self.path != '/api/ontology/build':
                self.reply(404, {'error': 'Unknown ontology endpoint'})
                return
            try:
                payload = self.read_json()
                if payload is None:
                    return
                if not isinstance(payload.get('content_base64'), str):
                    raise SourceFileError('请求缺少 content_base64（文件内容）')
                try:
                    data = base64.b64decode(payload['content_base64'], validate=True)
                except (binascii.Error, ValueError):
                    raise SourceFileError('文件内容不是有效的 base64') from None
                bundle = load_table_file(str(payload.get('filename') or ''), data, payload.get('purpose'))
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            if gateway is None:
                self.reply(503, {'error': '本机服务没有模型凭据：设置 DEEPSEEK_API_KEY 后重启 ontology_server。'})
                return
            result = build_and_evaluate(bundle, gateway)
            outage = [e['message'] for a in result['ontology']['attempts'] for e in a['errors'] if e['code'] == 'model_request_failed']
            if result['ontology']['status'] != 'auto_built_verified' and outage:
                self.reply(502, {'error': f'模型请求失败（{outage[-1][:160]}）。这不是数据的问题，请稍后重试。'})
                return
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            name = f'{stamp}-{bundle["file"]["sha256"][:8]}.json'
            output_dir.mkdir(parents=True, exist_ok=True)
            previous = self.previous_run(bundle['file']['sha256'])
            if previous and result['ontology']['status'] == 'auto_built_verified':
                result['previous'] = {'saved_as': previous['saved_as'], 'started_at': previous['started_at'],
                                      'diff': compare_ontologies(previous['ontology'], result['ontology'])}
            result['saved_as'] = name
            (output_dir / name).write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            # the uploaded rows stay on this machine so later questions can be answered from them
            (output_dir / name.replace('.json', '.bundle.json')).write_text(json.dumps(bundle, ensure_ascii=False), encoding='utf-8')
            self.reply(200, result)

        def previous_run(self, sha256):
            """The latest verified earlier run of the same file, so a rerun shows what changed."""
            for path in sorted(output_dir.glob('*.json'), reverse=True):
                if path.name.endswith('.bundle.json') or not SAVED_NAME.match(path.name):
                    continue
                earlier = json.loads(path.read_text(encoding='utf-8'))
                if earlier['file']['sha256'] == sha256 and earlier['ontology']['status'] == 'auto_built_verified':
                    return earlier
            return None

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
                self.reply(503, {'error': '本机服务没有模型凭据：设置 DEEPSEEK_API_KEY 后重启 ontology_server。'})
                return
            result = json.loads(result_path.read_text(encoding='utf-8'))
            if result['ontology']['status'] != 'auto_built_verified':
                self.reply(400, {'error': '本体没有通过结构核验，不能出题'})
                return
            bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
            answered = ask_questions(result['ontology'], bundle, gateway, question.strip() if question else None)
            if answered['error'] and answered['error'].startswith('模型请求失败'):
                self.reply(502, {'error': answered['error']})
                return
            if question:
                result['evaluation'].setdefault('asked', []).append(answered)
            else:
                result['evaluation']['questions'] = answered
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            self.reply(200, result)

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
