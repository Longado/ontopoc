"""Local-only recall lookup API. No model calls, writes, or credentials."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlsplit

from ontology_poc_generator.recall_scope import load_catalog, match_recall


def make_server(port=8766):
    catalog = load_catalog()

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
            if self.path != '/api/recall/catalog':
                self.reply(404, {'error': 'Unknown recall endpoint'})
                return
            self.reply(200, {key: value for key, value in catalog.items() if key != 'records'})

        def do_POST(self):
            if not self.local_request():
                return
            if self.path != '/api/recall/match':
                self.reply(404, {'error': 'Unknown recall endpoint'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    self.reply(413, {'error': '请求必须为 1–4096 字节。'})
                    return
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    self.reply(415, {'error': 'Expected application/json'})
                    return
                query = json.loads(self.rfile.read(length))
                self.reply(200, match_recall(catalog, query))
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    server = make_server(parser.parse_args().port)
    print(f'Recall API: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
