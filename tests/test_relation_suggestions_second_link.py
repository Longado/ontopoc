"""On the Taiwan registry, the model joined a director's appointment to the company it is at (統一編號). 所代表法人 names
the corporation the director represents, and 455 of those are registered companies too: a second, different relation
between the same two types. A relation already between them does not make this one a repeat."""
import unittest

from ontology_poc_generator.relation_suggestions import suggest_relations
from tests.test_relation_suggestions_alt_key import BUNDLE, ONTOLOGY


class SecondLinkTests(unittest.TestCase):
    def test_a_name_link_through_another_column_is_suggested_even_when_the_types_are_already_related(self):
        related = {**ONTOLOGY, 'relations': [{'key': 'serves_at', 'from': 'officer', 'to': 'company', 'source': 'directors'}]}
        found = [x for x in suggest_relations(related, BUNDLE) if x['kind'] == 'alternate_key']
        self.assertEqual([(x['from'], x['to'], x['via']['field']) for x in found], [('officer', 'company', '所代表法人')])


if __name__ == '__main__':
    unittest.main()
