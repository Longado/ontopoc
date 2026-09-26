"""A local reference library is definitions, never a verified run or a model request."""
import base64
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ontology_poc_generator.ontology_server import make_server


RDF = '''<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
 xmlns:owl="http://www.w3.org/2002/07/owl#" xmlns:ont="https://example.org/ontology/"
 xml:base="https://example.org/ontology/">
 <owl:Ontology rdf:about=""><rdfs:label>订单参考</rdfs:label></owl:Ontology>
 <owl:Class rdf:about="Customer"><rdfs:label>客户</rdfs:label></owl:Class>
 <owl:Class rdf:about="https://other.example/Customer"><rdfs:label>另一种客户</rdfs:label></owl:Class>
 <owl:DatatypeProperty rdf:about="amount"><rdfs:label>金额</rdfs:label>
  <rdfs:domain rdf:resource="Customer"/><rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#decimal"/>
  <ont:unit>CNY</ont:unit><ont:isIdentifier>false</ont:isIdentifier>
 </owl:DatatypeProperty>
 <owl:DatatypeProperty rdf:about="tier"><rdfs:label>等级</rdfs:label>
  <rdfs:domain rdf:resource="Customer"/><ont:propertyType>enum</ont:propertyType><ont:enumValues>金,银</ont:enumValues>
 </owl:DatatypeProperty>
 <owl:ObjectProperty rdf:about="refersTo"><rdfs:domain rdf:resource="Customer"/>
  <rdfs:range rdf:resource="https://other.example/Customer"/></owl:ObjectProperty>
</rdf:RDF>'''


class NoModelCalls:
    def complete_json(self, **kwargs):
        raise AssertionError('Browsing or importing a definition must not call a model')


class OntologyLibraryTests(unittest.TestCase):
    @contextmanager
    def server(self):
        with tempfile.TemporaryDirectory() as out:
            server = make_server(port=0, gateway=NoModelCalls(), output_dir=Path(out))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                yield f'http://127.0.0.1:{server.server_port}', Path(out)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def request(self, base, path, payload=None, headers=None):
        request = Request(base + path, data=None if payload is None else json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def imported(self, base, text=RDF, filename='参考.owl', headers=None):
        return self.request(base, '/api/ontology/library/import',
                            {'filename': filename, 'content_base64': base64.b64encode(text.encode()).decode()}, headers)

    def test_catalogue_has_the_twelve_selected_references_and_no_generated_runs(self):
        with self.server() as (base, out):
            status, body = self.request(base, '/api/ontology/library')
            self.assertEqual(status, 200, body)
            self.assertEqual({e['id'] for e in body['entries']}, {
                'cosmic-coffee', 'ecommerce', 'healthcare', 'finance', 'manufacturing', 'university',
                'iq-lab-retail-step-6', 'zava-grove-to-shelf', 'service-order-management', 'hr-system',
                'supply-chain-disruption-risk-propagation', 'productionline-ontology-sample'})
            self.assertTrue(all(e['title'] and e['author'] and e['source_path'] and e['counts']['entities'] for e in body['entries']))
            self.assertEqual(self.request(base, '/api/ontology/runs')[1]['runs'], [])
            self.assertEqual(list(out.iterdir()), [])

    def test_every_catalogue_definition_keeps_original_rdf_and_metadata(self):
        with self.server() as (base, _):
            status, body = self.request(base, '/api/ontology/library')
            self.assertEqual(status, 200, body)
            for entry in body['entries']:
                with self.subTest(entry=entry['id']):
                    status, definition = self.request(base, '/api/ontology/library/' + entry['id'])
                    self.assertEqual(status, 200, definition)
                    self.assertEqual(definition['schema'], 'ontology_definition.v1')
                    self.assertIn('<rdf:RDF', definition['rdf_xml'])
                    self.assertEqual(definition['metadata']['author'], entry['author'])
                    self.assertEqual(len(definition['entity_types']), entry['counts']['entities'])
                    self.assertEqual(len(definition['relationships']), entry['counts']['relationships'])
                    self.assertNotIn('verification', definition)
                    self.assertNotIn('saved_as', definition)

    def test_import_preserves_namespaces_types_units_enums_and_unknown_cardinality(self):
        with self.server() as (base, out):
            status, body = self.imported(base)
            self.assertEqual(status, 200, body)
            self.assertEqual(body['name'], '订单参考')
            entities = {e['id']: e for e in body['entity_types']}
            self.assertEqual(set(entities), {'https://example.org/ontology/Customer', 'https://other.example/Customer'})
            props = entities['https://example.org/ontology/Customer']['properties']
            self.assertEqual(props[0]['type'], 'decimal')
            self.assertEqual(props[0]['unit'], 'CNY')
            self.assertEqual(props[1]['values'], ['金', '银'])
            self.assertIsNone(body['relationships'][0]['cardinality'])
            self.assertEqual(body['rdf_xml'], RDF)
            self.assertEqual(list(out.iterdir()), [])

    def test_explicit_cardinality_and_relationship_attributes_are_kept(self):
        text = RDF.replace('<owl:ObjectProperty rdf:about="refersTo">',
                           '<owl:ObjectProperty rdf:about="refersTo"><ont:cardinality>many-to-one</ont:cardinality>')
        text = text.replace('</rdf:RDF>', '<owl:DatatypeProperty rdf:about="quantity"><rdfs:label>数量</rdfs:label>'
                            '<ont:relationshipAttributeOf>refersTo</ont:relationshipAttributeOf>'
                            '<ont:attributeType>integer</ont:attributeType></owl:DatatypeProperty></rdf:RDF>')
        with self.server() as (base, _):
            status, body = self.imported(base, text)
            self.assertEqual(status, 200, body)
            self.assertEqual(body['relationships'][0]['cardinality'], 'many-to-one')
            self.assertEqual(body['relationships'][0]['attributes'][0]['type'], 'integer')

    def test_unsupported_owl_and_unresolved_endpoints_are_visible_not_invented(self):
        text = RDF.replace('<rdfs:label>客户</rdfs:label>', '<rdfs:label>客户</rdfs:label><rdfs:subClassOf>'
                           '<owl:Restriction><owl:minCardinality>1</owl:minCardinality></owl:Restriction></rdfs:subClassOf>')
        text = text.replace('rdf:resource="https://other.example/Customer"', 'rdf:resource="Missing"')
        with self.server() as (base, _):
            status, body = self.imported(base, text)
            self.assertEqual(status, 200, body)
            codes = {w['code'] for w in body['warnings']}
            self.assertIn('unsupported_construct', codes)
            self.assertIn('unresolved_endpoint', codes)
            self.assertEqual(body['relationships'][0]['to'], 'https://example.org/ontology/Missing')
            self.assertEqual(len(body['entity_types']), 2)

    def test_import_reports_malformed_xml_empty_ontology_and_dtd(self):
        with self.server() as (base, _):
            for text, reason in [(RDF[:-12], 'XML'),
                                 ('<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>', '对象'),
                                 ('<!DOCTYPE rdf:RDF [<!ENTITY secret SYSTEM "file:///etc/passwd">]>' + RDF, 'DTD')]:
                with self.subTest(reason=reason):
                    status, body = self.imported(base, text)
                    self.assertEqual(status, 400, body)
                    self.assertIn(reason, body['error'])

    def test_import_refuses_wrong_extension_invalid_base64_and_nonlocal_origin(self):
        with self.server() as (base, _):
            self.assertEqual(self.imported(base, filename='a.txt')[0], 400)
            self.assertEqual(self.request(base, '/api/ontology/library/import', {'filename': 'a.rdf', 'content_base64': '***'})[0], 400)
            self.assertEqual(self.imported(base, headers={'Origin': 'https://evil.example'})[0], 403)
            self.assertEqual(self.request(base, '/api/ontology/library/not-a-library-entry')[0], 404)


if __name__ == '__main__':
    unittest.main()
