"""Local-only upload API: a business file in, a verified company ontology and its evaluation out."""
import argparse
import base64
import binascii
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from ontology_poc_generator.company_ontology import build_and_evaluate
from ontology_poc_generator.company_sources import MAX_BYTES, SourceFileError, load_table_file
from ontology_poc_generator.model_gateway import OpenAICompatibleGateway

ROOT = Path(__file__).resolve().parents[2]
MAX_BODY = MAX_BYTES * 4 // 3 + 4096  # base64 grows the file by a third, plus the JSON around it


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

        def do_POST(self):
            if not self.local_request():
                return
            if self.path != '/api/ontology/build':
                self.reply(404, {'error': 'Unknown ontology endpoint'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BODY:
                    self.reply(413, {'error': f'文件太大，上限 {MAX_BYTES // 1024 // 1024} MB。'})
                    return
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    self.reply(415, {'error': 'Expected application/json'})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or not isinstance(payload.get('content_base64'), str):
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
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            name = f'{stamp}-{bundle["file"]["sha256"][:8]}.json'
            output_dir.mkdir(parents=True, exist_ok=True)
            result['saved_as'] = name
            (output_dir / name).write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
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
