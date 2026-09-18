"""The model names an object again on every build: Chicago's vendors were `vendor` in one version and `supplier` in the
next. Same table, same identity field: the same object, compared as one."""
import unittest

from ontology_poc_generator.versions import version_diff
from tests.test_relation_suggestions import table


def run(key):
    return {'saved_as': 'v.json', 'ontology': {'object_types': [
        {'key': key, 'label': '供应商', 'populated_from': [{'source': 'c', 'identity': {'vendor_id': 'vendor_id'}}], 'attributes': []}],
        'relations': [], 'ignored_fields': [], 'open_questions': []}}


class RenameTests(unittest.TestCase):
    def test_an_object_renamed_between_builds_is_compared_as_one(self):
        before = {'sources': {'c': table(('vendor_id',), ('A',), ('B',))}}
        after = {'sources': {'c': table(('vendor_id',), ('B',), ('C',))}}
        [change] = version_diff(run('vendor'), before, run('supplier'), after)['objects']
        self.assertEqual((change['type'], change['before'], change['after'], change['added'], change['removed']), ('supplier', 2, 2, 1, 1))
        self.assertEqual((change['added_examples'], change['removed_examples']), (['C'], ['A']))


if __name__ == '__main__':
    unittest.main()
