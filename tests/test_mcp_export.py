"""The exports are written to a folder and the tool returns only where they went: a Turtle export of a real run is
millions of characters, and none of that belongs in an agent's context."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ontology_poc_generator import mcp_server
from ontology_poc_generator.mcp_server import LocalService, ToolError, handle
from tests.test_ontology_server import CSV, OntologyServerTests

FILES = {'order.csv': 'ROW-ONE-MARKER,100\n', '说明.txt': '中文说明-MARKER\n'}
TOOLS = (('export_forms', 'forms'), ('export_ttl', 'ttl'), ('export_mermaid', 'mermaid'))


class Service(LocalService):
    def __init__(self, files=None):
        self.files, self.sent = files or FILES, []

    def request(self, path, payload=None):
        self.sent.append(path)
        return {'files': self.files}


class WrittenToDiskTests(unittest.TestCase):
    def test_every_file_lands_in_out_dir_and_the_result_only_names_them(self):
        for tool, kind in TOOLS:
            with self.subTest(tool=tool), tempfile.TemporaryDirectory() as tmp:
                service = Service()
                out = getattr(mcp_server, tool)(service, {'saved_as': 'exam.json', 'out_dir': tmp})
                self.assertEqual(service.sent, [f'/api/ontology/runs/exam.json/export/{kind}?format=json'])
                self.assertEqual(out['dir'], tmp)
                self.assertEqual(out['files'], [{'name': 'order.csv', 'path': f'{tmp}/order.csv', 'bytes': 19},
                                                {'name': '说明.txt', 'path': f'{tmp}/说明.txt', 'bytes': 20}])
                self.assertEqual(out['total_bytes'], 39)
                self.assertEqual((Path(tmp) / 'order.csv').read_text(encoding='utf-8'), FILES['order.csv'])
                self.assertEqual((Path(tmp) / '说明.txt').read_text(encoding='utf-8'), FILES['说明.txt'])
                self.assertNotIn('MARKER', json.dumps(out, ensure_ascii=False))

    def test_a_folder_that_is_not_there_yet_is_made_and_a_file_of_the_same_name_is_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'a' / 'b'
            target.mkdir(parents=True)
            (target / 'order.csv').write_text('OLD', encoding='utf-8')
            (target / 'kept.txt').write_text('KEPT', encoding='utf-8')
            fresh = Path(tmp) / 'c' / 'd'
            mcp_server.export_forms(Service(), {'saved_as': 'exam.json', 'out_dir': str(target)})
            mcp_server.export_forms(Service(), {'saved_as': 'exam.json', 'out_dir': str(fresh)})
            self.assertEqual((target / 'order.csv').read_text(encoding='utf-8'), FILES['order.csv'])
            self.assertEqual((target / 'kept.txt').read_text(encoding='utf-8'), 'KEPT')
            self.assertTrue((fresh / '说明.txt').is_file())

    def test_without_out_dir_they_go_under_downloads_by_run_and_kind(self):
        for tool, kind in TOOLS:
            with self.subTest(tool=tool), tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {'HOME': home}):
                out = getattr(mcp_server, tool)(Service(), {'saved_as': 'exam.json'})
                self.assertEqual(out['dir'], f'{home}/Downloads/OntoPoc/exam/{kind}')
                self.assertTrue(Path(out['dir'], 'order.csv').is_file())

    def test_the_years_of_an_organisation_map_still_reach_the_service(self):
        service = Service({'组织隶属.mmd': 'flowchart TD\n'})
        with tempfile.TemporaryDirectory() as tmp:
            mcp_server.export_mermaid(service, {'saved_as': 'org.json', 'years': '2016-2022', 'out_dir': tmp})
        self.assertEqual(service.sent, ['/api/ontology/runs/org.json/export/mermaid?format=json&years=2016-2022'])


class RefusedTests(unittest.TestCase):
    def test_a_relative_out_dir_is_an_error_and_nothing_is_asked_or_written(self):
        for tool, _ in TOOLS:
            for bad in ('exports', './exports', '~/exports'):
                with self.subTest(tool=tool, out_dir=bad), tempfile.TemporaryDirectory() as cwd:
                    before, service = os.getcwd(), Service()
                    os.chdir(cwd)
                    try:
                        with self.assertRaisesRegex(ToolError, '绝对路径'):
                            getattr(mcp_server, tool)(service, {'saved_as': 'exam.json', 'out_dir': bad})
                        self.assertEqual(list(Path(cwd).iterdir()), [])
                    finally:
                        os.chdir(before)
                    self.assertEqual(service.sent, [])

    def test_the_tools_offer_out_dir_as_an_optional_absolute_path(self):
        tools = {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        for tool, _ in TOOLS:
            self.assertIn('绝对路径', tools[tool]['inputSchema']['properties']['out_dir']['description'])
            self.assertNotIn('out_dir', tools[tool]['inputSchema']['required'])
            self.assertIn('路径', tools[tool]['description'])


class RealServiceTests(unittest.TestCase):
    def test_the_forms_and_the_turtle_of_a_real_run_are_written_with_their_real_sizes(self):
        import base64
        with OntologyServerTests().server() as (base, _), tempfile.TemporaryDirectory() as tmp:
            service = LocalService(base)
            run = service.request('/api/ontology/build', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            forms = mcp_server.export_forms(service, {'saved_as': run['saved_as'], 'out_dir': f'{tmp}/forms'})
            self.assertEqual(sorted(f['name'] for f in forms['files']), ['customer.csv', 'order.csv', '说明.txt'])
            ttl = mcp_server.export_ttl(service, {'saved_as': run['saved_as'], 'out_dir': f'{tmp}/ttl'})
            self.assertEqual(sorted(f['name'] for f in ttl['files']), ['data.ttl', 'ontology.ttl'])
            for out in (forms, ttl):
                for f in out['files']:
                    self.assertEqual(Path(f['path']).stat().st_size, f['bytes'])
                    self.assertGreater(f['bytes'], 0)
                self.assertEqual(out['total_bytes'], sum(f['bytes'] for f in out['files']))
                self.assertLess(len(json.dumps(out, ensure_ascii=False)), 1000)


if __name__ == '__main__':
    unittest.main()
