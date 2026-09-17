import unittest

from ontology_poc_generator.ontology_eval import data_fit
from ontology_poc_generator.name_variants import variant_candidates, variant_catalog
from tests.test_company_ontology import BUNDLE, PROPOSAL


def by_name(records):
    """An ontology whose customer is identified by its name, as a table without customer numbers forces."""
    return ({**PROPOSAL, 'object_types': [
        {'key': 'customer', 'label': '客户', 'populated_from': [{'source': '客户', 'identity': {'name': '名称'}}],
         'attributes': [{'source': '客户', 'path': '城市'}]},
        PROPOSAL['object_types'][1]], 'relations': []},
        {**BUNDLE, 'sources': {**BUNDLE['sources'], '客户': {'records': records, 'requests': []}}})


ROWS = [{'客户编号': 'C1', '名称': '苏州某某机械有限公司', '城市': '苏州'},
        {'客户编号': 'C2', '名称': '苏州某某机械', '城市': '苏州'},
        {'客户编号': 'C3', '名称': '无锡别的公司', '城市': '无锡'}]


class CatalogTests(unittest.TestCase):
    def test_only_objects_identified_by_a_name_are_offered_for_matching(self):
        ontology, bundle = by_name(ROWS)
        catalog = variant_catalog(ontology, bundle)
        self.assertEqual(list(catalog), ['customer'])
        self.assertEqual({v['value']: v['records'] for v in catalog['customer']['values']},
                         {'苏州某某机械有限公司': 1, '苏州某某机械': 1, '无锡别的公司': 1})
        # 订单按订单号识别，名字不是它的身份，不该出现在这里
        self.assertNotIn('order', catalog)

    def test_an_object_with_a_number_to_identify_it_is_left_to_the_data_check(self):
        self.assertEqual(variant_catalog(PROPOSAL, BUNDLE), {})
        self.assertTrue(data_fit(PROPOSAL, BUNDLE)['identity_conflicts'] is not None)


class CandidateTests(unittest.TestCase):
    def test_a_proposal_carries_the_evidence_a_person_needs_and_never_merges_on_its_own(self):
        ontology, bundle = by_name(ROWS)
        catalog = variant_catalog(ontology, bundle)
        kept, rejected = variant_candidates(catalog, [
            {'type': 'customer', 'values': ['苏州某某机械有限公司', '苏州某某机械'], 'reasoning': '同一家公司的全称和简称'},
            {'type': 'customer', 'values': ['苏州某某机械有限公司', '无锡别的公司'], 'reasoning': '都在江苏'},
            {'type': 'customer', 'values': ['不存在的公司', '苏州某某机械'], 'reasoning': '瞎编的'},
            {'type': 'order', 'values': ['O1', 'O2'], 'reasoning': '不该提的类型'},
        ])
        self.assertEqual(len(kept), 2)   # the model's semantic call is kept; only what the data cannot support is dropped
        self.assertEqual(kept[0]['values'], ['苏州某某机械', '苏州某某机械有限公司'])
        self.assertEqual(kept[0]['records'], [1, 1])
        self.assertEqual(kept[0]['verdict'], 'needs_person')
        self.assertEqual([r['reason'] for r in rejected],
                         ['这个值不在数据里：不存在的公司', '这个对象不是按名字识别的，写法问题看数据体检'])


if __name__ == '__main__':
    unittest.main()
