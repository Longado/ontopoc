import unittest

from ontology_poc_generator.company_ontology import verify_company_proposal
from ontology_poc_generator.public_ontology import build_graph

# 站点表：每个站台记着它属于哪个上级车站。S1、S2 都属于 P。
BUNDLE = {
    'schema': 'company_source_bundle.v1', 'decision': '看清站点', 'file': {'name': 'stops', 'sha256': 'a' * 64, 'kind': 'table'},
    'sources': {'站点': {'records': [{'站点号': 'P', '站名': '总站', '上级': ''},
                                   {'站点号': 'S1', '站名': '一号台', '上级': 'P'},
                                   {'站点号': 'S2', '站名': '二号台', '上级': 'P'}], 'requests': []}},
}


def proposal(populated_from):
    parent_read = any(pop['identity'].get('id') == '上级' for pop in populated_from)
    attributes = [{'source': '站点', 'path': '站名'}] + ([] if parent_read else [{'source': '站点', 'path': '上级'}])   # as in the real run: kept as a plain attribute
    return {'reasoning': 'r', 'object_types': [
        {'key': 'stop', 'label': '站点', 'populated_from': populated_from,
         'attributes': attributes, 'rationale': 'r'}],
        'relations': [{'key': 'stop_parent', 'from': 'stop', 'to': 'stop', 'source': '站点', 'meaning': '站台属于上级车站'}],
        'ignored_fields': [], 'open_questions': []}


class SelfRelationTests(unittest.TestCase):
    def test_a_relation_that_only_ever_links_an_object_to_itself_is_sent_back(self):
        only_id = proposal([{'source': '站点', 'identity': {'id': '站点号'}}])
        errors = verify_company_proposal(only_id, BUNDLE)['errors']
        linking = [e for e in errors if e['code'] == 'relation_zero_links']
        self.assertEqual(len(linking), 1)
        self.assertIn('same kind of object', linking[0]['message'])   # says how to fix it, not just that it failed
        self.assertEqual(len(build_graph(only_id, BUNDLE)['edges']['stop_parent']), 0)

    def test_a_relation_that_reads_the_other_end_from_its_own_column_links_different_objects(self):
        both_ends = proposal([{'source': '站点', 'identity': {'id': '站点号'}}, {'source': '站点', 'identity': {'id': '上级'}}])
        self.assertEqual([e for e in verify_company_proposal(both_ends, BUNDLE)['errors'] if e['code'] == 'relation_zero_links'], [])
        pairs = {(a[1][0][1], b[1][0][1]) for a, b, _ in build_graph(both_ends, BUNDLE)['edges']['stop_parent']}
        self.assertTrue(all(x != y for x, y in pairs))   # no object is linked to itself
        self.assertIn(('S1', 'P'), pairs | {(y, x) for x, y in pairs})


if __name__ == '__main__':
    unittest.main()
