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


MANIFEST = '.ontopoc-export.json'


def names_in(folder):
    return sorted(p.name for p in Path(folder).iterdir() if p.name != MANIFEST)


class FileNameTests(unittest.TestCase):
    def test_a_name_that_could_leave_the_folder_fails_the_whole_export_and_nothing_is_written(self):
        for tool, _ in TOOLS:
            for bad in ('../../x.csv', 'a/b.csv', 'a\\b.csv', '', '.', '..', 'ABS'):
                with self.subTest(tool=tool, name=bad), tempfile.TemporaryDirectory() as tmp:
                    out = Path(tmp) / 'inner' / 'out'
                    name = str(Path(tmp) / 'abs' / 'x.csv') if bad == 'ABS' else bad
                    service = Service({'good.csv': 'GOOD', name: 'BAD'})   # the good one comes first: it must not be written either
                    with self.assertRaisesRegex(ToolError, '文件名'):
                        getattr(mcp_server, tool)(service, {'saved_as': 'exam.json', 'out_dir': str(out)})
                    self.assertEqual(list(Path(tmp).rglob('*')), [])

    def test_plain_names_with_dots_or_spaces_still_go_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            mcp_server.export_forms(Service({'a.b.csv': 'A', 'my file.txt': 'B', '.hidden': 'C'}), {'saved_as': 'exam.json', 'out_dir': tmp})
            self.assertEqual(names_in(tmp), ['.hidden', 'a.b.csv', 'my file.txt'])


class StaleFileTests(unittest.TestCase):
    def export(self, tmp, files, tool='export_forms'):
        return getattr(mcp_server, tool)(Service(files), {'saved_as': 'exam.json', 'out_dir': tmp})

    def test_a_file_the_last_export_wrote_and_this_one_does_not_is_removed_and_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.export(tmp, {'a.csv': 'A', 'b.csv': 'B', '说明.txt': 'S'})
            self.assertEqual(first['removed'], [])
            Path(tmp, 'mine.txt').write_text('MINE', encoding='utf-8')
            second = self.export(tmp, {'a.csv': 'A2', '说明.txt': 'S2'})
            self.assertEqual(second['removed'], ['b.csv'])
            self.assertEqual([f['name'] for f in second['files']], ['a.csv', '说明.txt'])
            self.assertEqual(names_in(tmp), ['a.csv', 'mine.txt', '说明.txt'])   # what the export never wrote is not touched
            self.assertEqual(Path(tmp, 'a.csv').read_text(encoding='utf-8'), 'A2')

    def test_what_is_no_longer_there_is_not_an_error_and_the_next_export_forgets_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.export(tmp, {'a.csv': 'A', 'b.csv': 'B'})
            Path(tmp, 'b.csv').unlink()
            self.assertEqual(self.export(tmp, {'a.csv': 'A'})['removed'], [])
            self.assertEqual(self.export(tmp, {'a.csv': 'A'})['removed'], [])

    def test_a_file_of_the_same_name_that_a_person_put_there_before_the_first_export_stays(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'b.csv').write_text('MINE', encoding='utf-8')
            self.export(tmp, {'a.csv': 'A'})
            self.assertEqual(self.export(tmp, {'a.csv': 'A'})['removed'], [])
            self.assertEqual(Path(tmp, 'b.csv').read_text(encoding='utf-8'), 'MINE')

    def test_the_forms_and_the_turtle_exported_to_one_folder_do_not_remove_each_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.export(tmp, {'order.csv': 'O', '说明.txt': 'S'}, 'export_forms')
            ttl = self.export(tmp, {'ontology.ttl': 'T', 'data.ttl': 'D'}, 'export_ttl')
            self.assertEqual(ttl['removed'], [])
            again = self.export(tmp, {'ontology.ttl': 'T2'}, 'export_ttl')
            self.assertEqual(again['removed'], ['data.ttl'])
            self.assertEqual(names_in(tmp), ['ontology.ttl', 'order.csv', '说明.txt'])

    def test_a_list_that_names_something_outside_the_folder_or_is_not_a_list_removes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, outside = Path(tmp) / 'out', Path(tmp) / 'outside.txt'
            out.mkdir()
            outside.write_text('KEEP', encoding='utf-8')
            for written in ({'forms': ['../outside.txt', str(outside), 'sub/b.csv', '']}, {'forms': 'b.csv'}, ['b.csv'], 'not an object'):
                with self.subTest(written=written):
                    (out / MANIFEST).write_text(json.dumps(written), encoding='utf-8')
                    self.assertEqual(self.export(str(out), {'a.csv': 'A'})['removed'], [])
                    self.assertEqual(outside.read_text(encoding='utf-8'), 'KEEP')
            (out / MANIFEST).write_text('{not json', encoding='utf-8')
            self.assertEqual(self.export(str(out), {'a.csv': 'A'})['removed'], [])

    def test_a_folder_inside_the_list_is_not_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'sub').mkdir()
            (Path(tmp) / MANIFEST).write_text(json.dumps({'forms': ['sub']}), encoding='utf-8')
            self.assertEqual(self.export(tmp, {'a.csv': 'A'})['removed'], [])
            self.assertTrue((Path(tmp) / 'sub').is_dir())

    def test_the_export_tools_say_that_files_from_the_last_export_are_cleared(self):
        tools = {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        for tool, _ in TOOLS:
            self.assertIn('removed', tools[tool]['description'])
            self.assertIn(MANIFEST, tools[tool]['description'])


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
