"""Some upstream references name endpoints with Playground annotations instead of rdfs:domain/range."""
import unittest

from ontology_poc_generator.ontology_library import library_definition, parse_rdf

PREFIX = '''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns:owl="http://www.w3.org/2002/07/owl#" xmlns:ont="https://example.org/"
 xml:base="https://example.org/">'''


class AnnotationEndpointTests(unittest.TestCase):
    def test_zava_has_all_thirteen_relationships_available_to_the_graph(self):
        definition = library_definition('zava-grove-to-shelf')
        known = {e['id'] for e in definition['entity_types']}
        self.assertEqual(len(definition['relationships']), 13)
        self.assertTrue(all(r['from'] in known and r['to'] in known for r in definition['relationships']))
        self.assertFalse(any(w['code'] == 'unresolved_endpoint' for w in definition['warnings']))

    def test_unique_annotation_ids_resolve_to_original_class_iris(self):
        text = PREFIX + '<owl:Class rdf:about="Customer"/><owl:Class rdf:about="Order"/>' \
               '<owl:ObjectProperty rdf:about="places"><ont:fromEntityId>customer</ont:fromEntityId>' \
               '<ont:toEntityId>order</ont:toEntityId></owl:ObjectProperty></rdf:RDF>'
        rel = parse_rdf(text)['relationships'][0]
        self.assertEqual((rel['from'], rel['to']), ('https://example.org/Customer', 'https://example.org/Order'))

    def test_short_annotation_id_does_not_choose_between_same_names_in_two_namespaces(self):
        text = PREFIX + '<owl:Class rdf:about="Customer"/><owl:Class rdf:about="https://other.org/Customer"/>' \
               '<owl:ObjectProperty rdf:about="r"><ont:fromEntityId>customer</ont:fromEntityId>' \
               '<ont:toEntityId>customer</ont:toEntityId></owl:ObjectProperty></rdf:RDF>'
        definition = parse_rdf(text)
        self.assertIsNone(definition['relationships'][0]['from'])
        self.assertIn('unresolved_endpoint', {w['code'] for w in definition['warnings']})

    def test_unknown_declared_type_and_cardinality_remain_unknown(self):
        text = PREFIX + '<owl:Class rdf:about="Customer"/><owl:ObjectProperty rdf:about="r">' \
               '<ont:fromEntityId>customer</ont:fromEntityId><ont:toEntityId>customer</ont:toEntityId>' \
               '<ont:cardinality>exactly-seven</ont:cardinality></owl:ObjectProperty></rdf:RDF>'
        definition = parse_rdf(text)
        self.assertIsNone(definition['relationships'][0]['cardinality'])
        self.assertIn('unknown_cardinality', {w['code'] for w in definition['warnings']})


if __name__ == '__main__':
    unittest.main()
