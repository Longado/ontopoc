"""Unsupported multiple RDF domains/ranges must remain visible, not become one endpoint."""
import unittest
from ontology_poc_generator.ontology_library import parse_rdf

HEADER = '''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#" xmlns:owl="http://www.w3.org/2002/07/owl#"
 xmlns:ont="https://example.org/annotation/" xml:base="https://example.org/review#">
 <owl:Class rdf:about="https://example.org/A"/><owl:Class rdf:about="https://example.org/B"/>
 <owl:Class rdf:about="https://example.org/C"/>'''

class MultipleEndpointTests(unittest.TestCase):
    def test_multiple_relation_domains_and_ranges_are_unresolved_even_with_annotations(self):
        for endpoint, annotation in [('domain', 'fromEntityId'), ('range', 'toEntityId')]:
            with self.subTest(endpoint=endpoint):
                other = 'range' if endpoint == 'domain' else 'domain'
                text = HEADER + f'''<owl:ObjectProperty rdf:about="https://example.org/rel">
                 <rdfs:{endpoint} rdf:resource="https://example.org/A"/>
                 <rdfs:{endpoint} rdf:resource="https://example.org/B"/>
                 <rdfs:{other} rdf:resource="https://example.org/C"/>
                 <ont:{annotation}>A</ont:{annotation}></owl:ObjectProperty></rdf:RDF>'''
                result = parse_rdf(text)
                relation = result['relationships'][0]
                self.assertIsNone(relation['from' if endpoint == 'domain' else 'to'])
                self.assertTrue(any(w['code'] == 'multiple_endpoints' for w in result['warnings']))
                self.assertEqual(result['rdf_xml'], text)

    def test_multiple_property_domains_stay_unattached(self):
        text = HEADER + '''<owl:DatatypeProperty rdf:about="https://example.org/name">
         <rdfs:domain rdf:resource="https://example.org/A"/><rdfs:domain rdf:resource="https://example.org/B"/>
         <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>
         </owl:DatatypeProperty></rdf:RDF>'''
        result = parse_rdf(text)
        self.assertFalse(any(e['properties'] for e in result['entity_types']))
        self.assertEqual(result['unattached_properties'][0]['id'], 'https://example.org/name')
        self.assertTrue(any(w['code'] == 'multiple_endpoints' for w in result['warnings']))
        self.assertEqual(result['rdf_xml'], text)

    def test_multiple_property_ranges_do_not_claim_one_type_even_with_annotation(self):
        text = HEADER + '''<owl:DatatypeProperty rdf:about="https://example.org/value">
         <rdfs:domain rdf:resource="https://example.org/A"/>
         <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#string"/>
         <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#integer"/>
         <ont:propertyType>string</ont:propertyType></owl:DatatypeProperty></rdf:RDF>'''
        result = parse_rdf(text)
        prop = result['entity_types'][0]['properties'][0]
        self.assertIsNone(prop['type'])
        self.assertIsNone(prop['range_iri'])
        self.assertTrue(any(w['code'] == 'multiple_endpoints' for w in result['warnings']))
        self.assertEqual(result['rdf_xml'], text)
