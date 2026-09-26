"""Imported relationship attributes must not disappear or choose an ambiguous namespace."""
import unittest

from ontology_poc_generator.ontology_library import parse_rdf

PREFIX = '''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns:owl="http://www.w3.org/2002/07/owl#" xmlns:ont="https://example.org/"
 xml:base="https://example.org/">'''


def attribute(name, relationship):
    return f'''<owl:DatatypeProperty rdf:about="{name}">
      <ont:relationshipAttributeOf>{relationship}</ont:relationshipAttributeOf>
      <ont:attributeType>integer</ont:attributeType></owl:DatatypeProperty>'''


class RelationshipAttributeTests(unittest.TestCase):
    def test_full_and_unique_short_relationship_references_are_both_preserved(self):
        text = PREFIX + '<owl:Class rdf:about="A"/>' + attribute('quantity', 'https://example.org/r') \
            + attribute('count', 'r') + '<owl:ObjectProperty rdf:about="r"/></rdf:RDF>'
        definition = parse_rdf(text)
        self.assertEqual({p['id'] for p in definition['relationships'][0]['attributes']},
                         {'https://example.org/quantity', 'https://example.org/count'})

    def test_ambiguous_short_relationship_reference_stays_unattached(self):
        text = PREFIX + '<owl:Class rdf:about="A"/>' + attribute('quantity', 'r') \
            + '<owl:ObjectProperty rdf:about="r"/><owl:ObjectProperty rdf:about="https://other.org/r"/></rdf:RDF>'
        definition = parse_rdf(text)
        self.assertTrue(all(not r['attributes'] for r in definition['relationships']))
        self.assertEqual([p['id'] for p in definition['unattached_properties']], ['https://example.org/quantity'])
        self.assertIn('unresolved_property', {w['code'] for w in definition['warnings']})
