"""Chicago's contracts were told apart by number and revision in one build, by number alone in the next: 2990 became
884 and every one read as removed or added. Objects told apart differently cannot be matched one by one."""
import unittest

from ontology_poc_generator.versions import version_diff
from tests.test_relation_suggestions import table


def run(identity):
    return {'saved_as': 'v.json', 'ontology': {'object_types': [
        {'key': 'contract', 'label': '合同', 'populated_from': [{'source': 'c', 'identity': identity}], 'attributes': []}],
        'relations': [], 'ignored_fields': [], 'open_questions': []}}


class IdentityChangeTests(unittest.TestCase):
    def test_an_object_told_apart_differently_is_counted_but_not_matched(self):
        data = {'sources': {'c': table(('号', '修订'), ('1', '0'), ('1', '1'), ('2', '0'))}}
        [change] = version_diff(run({'n': '号', 'r': '修订'}), data, run({'n': '号'}), data)['objects']
        self.assertEqual((change['before'], change['after']), (3, 2))
        self.assertEqual((change['added'], change['removed']), (None, None))
        self.assertEqual(change['identity_changed'], {'before': ['号', '修订'], 'after': ['号']})


if __name__ == '__main__':
    unittest.main()
