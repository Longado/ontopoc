"""A person's explicit domain mapping is not a standard answer or a change to the ontology."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ontology_poc_generator.ontology_library import library_definition
from ontology_poc_generator.ontology_server import make_server

try:
    reference = importlib.import_module('ontology_poc_generator.ontology_reference')
except ModuleNotFoundError:
    reference = None


def example():
    definition = {'sha256': 'v1', 'entry': {'id': 'test', 'title': '参考'}, 'warnings': [], 'unattached_properties': [],
        'entity_types': [
            {'id': 'urn:a', 'name': '客户', 'properties': [{'id': 'urn:name', 'name': '名字', 'type': 'string', 'unit': None, 'values': []}]},
            {'id': 'urn:b', 'name': '订单', 'properties': [{'id': 'urn:amount', 'name': '金额', 'type': 'decimal', 'unit': 'CNY', 'values': []}]},
            {'id': 'urn:other:a', 'name': '客户', 'properties': []}],
        'relationships': [{'id': 'urn:places', 'name': '下单', 'from': 'urn:a', 'to': 'urn:b', 'cardinality': 'one-to-many', 'attributes': []}]}
    run = {'saved_as': '20260926T090000000Z-12345678.json', 'ontology': {
        'object_types': [
            {'key': 'customer', 'label': '客户', 'populated_from': [{'source': 'customers', 'identity': {'id': 'id'}}], 'attributes': [{'source': 'customers', 'path': 'name'}]},
            {'key': 'order', 'label': '订单', 'populated_from': [{'source': 'orders', 'identity': {'id': 'id'}}], 'attributes': [{'source': 'orders', 'path': 'amount', 'unit': 'USD'}]}],
        'relations': [{'key': 'belongs', 'from': 'order', 'to': 'customer', 'label': '属于'}]},
        'evaluation': {'asked': [{'items': [{'answer': {'groups': [['a', 2]]}}]}],
            'handover': {'sources': [{'name': 'customers', 'fields': [{'path': 'name', 'type': 'VARCHAR'}]},
                                     {'name': 'orders', 'fields': [{'path': 'amount', 'type': 'INTEGER'}]}]}}}
    mappings = [{'kind': 'object', 'reference': 'urn:a', 'local': 'customer'},
                {'kind': 'object', 'reference': 'urn:b', 'local': 'order'}]
    return definition, run, mappings


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(reference, 'domain reference comparison is not implemented')
        self.definition, self.run, self.maps = example()

    def compare(self, maps=None):
        return reference.compare_definition(self.definition, self.run, self.maps if maps is None else maps)

    def test_names_never_automatically_match_and_original_iris_remain_distinct(self):
        diff = self.compare([])
        self.assertEqual(diff['mapped'], [])
        self.assertEqual({r['reference'] for r in diff['only_reference'] if r['kind'] == 'object'}, {'urn:a', 'urn:b', 'urn:other:a'})
        self.assertEqual(len([r for r in diff['only_local'] if r['kind'] == 'object']), 2)

    def test_manual_correspondence_does_not_mutate_ontology_or_answers(self):
        before = deepcopy(self.run)
        diff = self.compare()
        self.assertEqual(len(diff['mapped']), 2)
        self.assertEqual(self.run, before)
        self.assertIn('urn:other:a', [r['reference'] for r in diff['only_reference']])

    def test_reversed_relation_is_a_difference_not_an_equivalent_match(self):
        self.maps.append({'kind': 'relation', 'reference': 'urn:places', 'local': 'belongs'})
        diff = self.compare()
        self.assertIn('方向相反', str(diff['different']))
        self.assertIn('基数', str(diff['unchecked']))
        self.assertIn('角色', str(diff['unchecked']))

    def test_properties_compare_declared_constraints_and_preserve_missing_information(self):
        self.maps += [{'kind': 'property', 'owner': 'urn:a', 'reference': 'urn:name', 'local': {'source': 'customers', 'path': 'name'}},
                      {'kind': 'property', 'owner': 'urn:b', 'reference': 'urn:amount', 'local': {'source': 'orders', 'path': 'amount'}}]
        diff = self.compare()
        self.assertIn('类型', str(diff['different']))
        self.assertIn('单位', str(diff['different']))
        self.assertNotIn('urn:name', [r['reference'] for r in diff['different']])
        self.definition['entity_types'][0]['properties'][0]['values'] = ['金', '银']
        self.assertIn('枚举', str(self.compare()['unchecked']))

    def test_invalid_endpoints_missing_fields_and_duplicate_conflicts_are_rejected(self):
        bad = [self.maps + [self.maps[0]],
               self.maps + [{'kind': 'object', 'reference': 'urn:other:a', 'local': 'customer'}],
               self.maps + [{'kind': 'property', 'owner': 'urn:a', 'reference': 'urn:name', 'local': {'source': 'orders', 'path': 'amount'}}],
               [{'kind': 'relation', 'reference': 'urn:places', 'local': 'belongs'}],
               [{'kind': 'object', 'reference': 'urn:missing', 'local': 'customer'}],
               [{'kind': 'object', 'reference': 'urn:a', 'local': 'missing'}]]
        for mappings in bad:
            with self.subTest(mappings=mappings), self.assertRaises(ValueError):
                self.compare(mappings)
        self.run['ontology']['relations'][0]['to'] = 'missing'
        with self.assertRaises(ValueError):
            self.compare(self.maps + [{'kind': 'relation', 'reference': 'urn:places', 'local': 'belongs'}])

    def test_not_applicable_requires_a_reason_and_is_not_a_missing_error(self):
        excluded = {'kind': 'object', 'reference': 'urn:other:a', 'reason': '本次只看采购客户'}
        diff = self.compare(self.maps + [excluded])
        self.assertEqual(diff['not_applicable'][0]['reason'], excluded['reason'])
        self.assertNotIn('urn:other:a', [r['reference'] for r in diff['only_reference']])
        with self.assertRaises(ValueError):
            self.compare([dict(excluded, reason=' ')])

    def test_unsupported_owl_and_relationship_attributes_are_not_silently_dropped(self):
        self.definition['warnings'] = [{'code': 'unsupported_construct', 'message': '继承尚未转换'}]
        self.definition['unattached_properties'] = [{'id': 'urn:loose', 'name': '游离属性'}]
        self.definition['relationships'][0]['attributes'] = [{'id': 'urn:quantity', 'name': '数量'}]
        diff = self.compare()
        self.assertIn('继承尚未转换', str(diff['unchecked']))
        self.assertIn('游离属性', str(diff['unchecked']))
        self.assertIn('数量', str(diff['unchecked']))

    def test_stale_reference_or_local_schema_requires_reconfirmation_but_answers_do_not(self):
        record = {'reference_sha256': self.definition['sha256'], 'run_sha256': reference.run_fingerprint(self.run)}
        self.assertEqual(reference.stale_reasons(self.definition, self.run, record), [])
        self.run['evaluation']['asked'] = []
        self.assertEqual(reference.stale_reasons(self.definition, self.run, record), [])
        self.definition['sha256'] = 'v2'
        self.run['ontology']['object_types'][0]['attributes'] = []
        self.assertEqual(len(reference.stale_reasons(self.definition, self.run, record)), 2)

    def test_same_property_name_in_different_tables_keeps_source_identity(self):
        self.run['ontology']['object_types'][0]['attributes'].append({'source': 'other', 'path': 'name'})
        fields = reference.local_schema(self.run)['objects'][0]['fields']
        self.assertEqual(len([f for f in fields if f['path'] == 'name']), 2)


class ReferenceApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        _, self.run, _ = example()
        self.path = self.out / self.run['saved_as']
        self.path.write_text(json.dumps(self.run))
        class NoModel:
            def complete_json(self, **kwargs):
                raise AssertionError('domain comparison must not call the model')
        self.server = make_server(port=0, gateway=NoModel(), output_dir=self.out)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, payload=None):
        request = Request(self.base + path, data=None if payload is None else json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def context(self):
        status, context = self.request(f'/api/ontology/runs/{self.run["saved_as"]}/reference')
        self.assertEqual(status, 200, context)
        return context

    def payload(self):
        definition = library_definition('ecommerce')
        return {'saved_as': self.run['saved_as'], 'reference_id': 'ecommerce', 'reference_sha256': definition['sha256'],
                'run_sha256': self.context()['run_sha256'], 'mappings': [
                    {'kind': 'object', 'reference': definition['entity_types'][0]['id'], 'local': 'customer'}]}

    def test_preview_does_not_save_confirm_restores_without_changing_any_other_state(self):
        payload = self.payload()
        before = self.path.read_bytes()
        status, preview = self.request('/api/ontology/reference/preview', payload)
        self.assertEqual(status, 200, preview)
        self.assertEqual(len(preview['diff']['mapped']), 1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.request('/api/ontology/reference/confirm', payload)[0], 400)
        status, saved = self.request('/api/ontology/reference/confirm', {**payload, 'confirmed': True})
        self.assertEqual(status, 200, saved)
        context = self.context()
        self.assertEqual(context['record']['mappings'], payload['mappings'])
        self.assertEqual(context['stale'], [])
        persisted = json.loads(self.path.read_text())
        del persisted['evaluation']['domain_reference']
        self.assertEqual(persisted, self.run)
        self.assertFalse((self.out / 'model_calls.jsonl').exists())

    def test_outdated_requests_are_rejected_without_overwriting_saved_mapping(self):
        payload = self.payload()
        self.assertEqual(self.request('/api/ontology/reference/confirm', {**payload, 'confirmed': True})[0], 200)
        before = self.path.read_bytes()
        for field in ['run_sha256', 'reference_sha256']:
            status, body = self.request('/api/ontology/reference/confirm', {**payload, field: 'old', 'confirmed': True})
            self.assertEqual(status, 409, body)
            self.assertEqual(self.path.read_bytes(), before)
        run = json.loads(before)
        run['ontology']['object_types'][0]['label'] = '客户新版'
        self.path.write_text(json.dumps(run))
        self.assertTrue(self.context()['stale'])

    def test_bad_reference_and_run_names_are_bounded(self):
        self.assertEqual(self.request('/api/ontology/reference/confirm', {'saved_as': '../other.json', 'confirmed': True})[0], 400)
        payload = self.payload()
        self.assertEqual(self.request('/api/ontology/reference/preview', {**payload, 'reference_id': 'missing'})[0], 404)


if __name__ == '__main__':
    unittest.main()
