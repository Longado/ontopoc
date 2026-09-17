import unittest

from ontology_poc_generator.ontology_eval import data_fit
from ontology_poc_generator.name_variants import MAX_VALUES, variant_candidates, variant_catalog
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
    def test_objects_identified_by_one_field_with_few_values_are_offered_for_matching(self):
        ontology, bundle = by_name(ROWS)
        catalog = variant_catalog(ontology, bundle)
        self.assertEqual({v['value']: v['records'] for v in catalog['customer']['values']},
                         {'苏州某某机械有限公司': 1, '苏州某某机械': 1, '无锡别的公司': 1})
        self.assertEqual(catalog['customer']['fields'], ['名称'])

    def test_an_object_with_too_many_values_is_not_sent_to_the_model(self):
        rows = [{'客户编号': f'C{i}', '名称': f'公司{i}', '城市': '苏州'} for i in range(MAX_VALUES + 1)]
        ontology, bundle = by_name(rows)
        self.assertNotIn('customer', variant_catalog(ontology, bundle))

    def test_an_object_identified_by_several_fields_is_left_alone(self):
        two_fields = {**PROPOSAL, 'object_types': [
            {'key': 'customer', 'label': '客户', 'populated_from': [{'source': '客户', 'identity': {'name': '名称', 'city': '城市'}}],
             'attributes': []}, PROPOSAL['object_types'][1]], 'relations': []}
        self.assertNotIn('customer', variant_catalog(two_fields, BUNDLE))
        self.assertTrue(data_fit(PROPOSAL, BUNDLE)['identity_conflicts'] is not None)


class CandidateTests(unittest.TestCase):
    def test_a_proposal_carries_the_evidence_a_person_needs_and_never_merges_on_its_own(self):
        ontology, bundle = by_name(ROWS)
        catalog = variant_catalog(ontology, bundle)
        kept, rejected = variant_candidates(catalog, [
            {'type': 'customer', 'values': ['苏州某某机械有限公司', '苏州某某机械'], 'reasoning': '同一家公司的全称和简称'},
            {'type': 'customer', 'values': ['苏州某某机械有限公司', '无锡别的公司'], 'reasoning': '都在江苏'},
            {'type': 'customer', 'values': ['不存在的公司', '苏州某某机械'], 'reasoning': '瞎编的'},
            {'type': 'invoice', 'values': ['I1', 'I2'], 'reasoning': '本体里根本没有的类型'},
        ])
        self.assertEqual(len(kept), 2)   # the model's semantic call is kept; only what the data cannot support is dropped
        self.assertEqual(kept[0]['values'], ['苏州某某机械', '苏州某某机械有限公司'])
        self.assertEqual(kept[0]['records'], [1, 1])
        self.assertEqual(kept[0]['verdict'], 'needs_person')
        self.assertEqual([r['reason'] for r in rejected],
                         ['这个值不在数据里：不存在的公司', '这个对象不在可对应的范围里，写法问题看数据体检'])


if __name__ == '__main__':
    unittest.main()
