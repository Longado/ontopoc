"""--page-dir: the service serves the built page itself, and the page's files never open a way around the sign-in or out of the folder."""
from contextlib import contextmanager
import http.client
from pathlib import Path
import tempfile
import threading
import unittest

from ontology_poc_generator import accounts, ontology_server
from ontology_poc_generator.workspace_store import open_workspace


@contextmanager
def serving(with_page=True, admin=False):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        page = root / 'site' / 'client'
        (page / 'assets').mkdir(parents=True)
        (page / 'index.html').write_text('<!doctype html><title>page</title>', encoding='utf-8')
        (page / 'legacy.html').write_text('<!doctype html><title>legacy</title>', encoding='utf-8')
        (page / 'assets' / 'app-1.js').write_text('console.log(1)', encoding='utf-8')
        (page / 'assets' / 'app-1.css').write_text('a{}', encoding='utf-8')
        (page / 'assets' / 'locked.js').write_text('x', encoding='utf-8')
        (page / 'assets' / 'locked.js').chmod(0)   # a file of the build this account cannot read
        (root / 'site' / 'secret.txt').write_text('outside', encoding='utf-8')   # beside the page folder, not in it
        server = ontology_server.make_server(port=0, gateway=None, output_dir=root / 'data', page_dir=page if with_page else None)
        if admin:
            conn = open_workspace(root / 'data' / 'workspace.sqlite')
            accounts.create_user(conn, 'root', 'root', 'admin', 'correct horse battery', 'host', must_change=False)
            conn.close()
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


def get(port, path):
    """The path exactly as written: urllib would tidy a /../ away before it was sent."""
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        conn.putrequest('GET', path, skip_host=True)
        conn.putheader('Host', f'127.0.0.1:{port}')
        conn.endheaders()
        response = conn.getresponse()
        return response.status, response.getheader('Content-Type') or '', response.read(), response
    finally:
        conn.close()


class PageDirTests(unittest.TestCase):
    def test_root_and_page_routes_get_index_without_signing_in(self):
        with serving() as port:   # no account exists yet either
            for path in ('/', '/index.html', '/workspace', '/team/runs/3', '/?x=1'):
                status, kind, body, response = get(port, path)
                self.assertEqual((status, kind.split(';')[0], b'<title>page</title>' in body), (200, 'text/html', True), path)
            self.assertIn("default-src 'self'", response.getheader('Content-Security-Policy'))

    def test_real_files_keep_their_type(self):
        with serving() as port:
            status, kind, body, _ = get(port, '/assets/app-1.js')
            self.assertEqual((status, body), (200, b'console.log(1)'))
            self.assertIn('javascript', kind)
            self.assertEqual(get(port, '/assets/app-1.css')[1].split(';')[0], 'text/css')
            self.assertIn(b'legacy', get(port, '/legacy.html')[2])

    def test_a_missing_asset_is_a_404_not_the_page(self):
        with serving() as port:
            self.assertEqual(get(port, '/assets/nope.js')[0], 404)

    def test_an_unreadable_file_is_an_error_reply_not_a_dropped_connection(self):
        with serving() as port:
            self.assertEqual(get(port, '/assets/locked.js')[0], 404)

    def test_no_way_out_of_the_folder(self):
        with serving() as port:
            for path in ('/../secret.txt', '/assets/../../secret.txt', '/%2e%2e/secret.txt', '/%2E%2E/%2e%2e/secret.txt', '/assets/%2e%2e/%2e%2e/secret.txt',
                         '/..%2fsecret.txt', '/%2e%2e%2fsecret.txt', '//etc/passwd', '/assets/..%5c..%5csecret.txt', '/%00', '/a%00.js'):
                status, _, body, _ = get(port, path)
                self.assertNotIn(b'outside', body, path)
                self.assertNotIn(b'root:', body, path)
                self.assertIn(status, (200, 400, 404), path)
                if status == 200:
                    self.assertIn(b'<title>page</title>', body, path)   # only ever the page itself

    def test_a_folder_is_not_listed(self):
        with serving() as port:
            status, _, body, _ = get(port, '/assets/')
            self.assertNotIn(b'app-1.js', body)

    def test_api_stays_behind_the_sign_in(self):
        with serving() as port:
            status, kind, body, response = get(port, '/api/workspace/datasets')
            self.assertEqual(status, 503)   # no account yet: the API's answer, not the page
            self.assertIn('json', kind)
            self.assertEqual(response.getheader('Content-Security-Policy'), dict(ontology_server.SECURITY_HEADERS)['Content-Security-Policy'])
            for path in ('/api', '/api/', '/api/anything/../../x'):
                self.assertNotIn(b'<title>', get(port, path)[2], path)

    def test_api_asks_for_sign_in_once_there_is_an_account(self):
        with serving(admin=True) as port:
            self.assertEqual(get(port, '/api/workspace/datasets')[0], 401)
            self.assertEqual(get(port, '/')[0], 200)

    def test_without_page_dir_nothing_changes(self):
        with serving(with_page=False) as port:
            self.assertNotIn(b'<title>page</title>', get(port, '/')[2])

    def test_a_page_dir_without_index_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                ontology_server.make_server(port=0, gateway=None, output_dir=Path(tmp) / 'd', page_dir=Path(tmp))


if __name__ == '__main__':
    unittest.main()
