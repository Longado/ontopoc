import unittest

from ontology_poc_generator.ontology_questions import run_query

# 一家企业持两张执照，各自一个类型：E1 的 L1 是食品、L2 是烟草。交叉相乘会凭空多出两组。
BUNDLE = {
    'schema': 'company_source_bundle.v1', 'decision': '看清每家企业持有哪些执照',
    'file': {'name': 'licenses.csv', 'sha256': 'c' * 64, 'kind': 'table'},
    'sources': {
        '执照': {'records': [
            {'执照号': 'L1', '企业号': 'E1', '企业名': '甲公司', '类型名': '食品', '费用': '100'},
            {'执照号': 'L2', '企业号': 'E1', '企业名': '甲公司', '类型名': '烟草', '费用': '50'},
            {'执照号': 'L3', '企业号': 'E2', '企业名': '乙公司', '类型名': '食品', '费用': '70'},
        ], 'requests': []},
    },
}
ONTOLOGY = {
    'object_types': [
        {'key': 'business', 'label': '企业', 'populated_from': [{'source': '执照', 'identity': {'id': '企业号'}}],
         'attributes': [{'source': '执照', 'path': '企业名'}]},
        {'key': 'license', 'label': '执照', 'populated_from': [{'source': '执照', 'identity': {'id': '执照号'}}],
         'attributes': [{'source': '执照', 'path': '费用'}]},
        {'key': 'license_type', 'label': '执照类型', 'populated_from': [{'source': '执照', 'identity': {'id': '类型名'}}], 'attributes': []},
    ],
    'relations': [{'key': 'business_holds', 'from': 'business', 'to': 'license', 'source': '执照', 'meaning': '企业持有执照'},
                  {'key': 'license_typed', 'from': 'license', 'to': 'license_type', 'source': '执照', 'meaning': '执照属于某个类型'}],
    'ignored_fields': [],
}
BY_NAME = {'via': [], 'field': '企业.企业名'}
BY_LICENSE = {'via': ['business_holds'], 'field': '执照.执照号'}
BY_TYPE = {'via': ['business_holds', 'license_typed'], 'field': '执照类型.类型名'}


class FanTrapTests(unittest.TestCase):
    def test_two_dimensions_down_one_chain_only_report_pairs_the_data_really_has(self):
        answer = run_query(ONTOLOGY, BUNDLE, {'start': 'business', 'where': [], 'via': [], 'group_by': [BY_NAME, BY_LICENSE, BY_TYPE]})['answer']
        self.assertEqual(sorted(g[0] for g in answer['groups']),
                         ['乙公司 · L3 · 食品', '甲公司 · L1 · 食品', '甲公司 · L2 · 烟草'])   # not 甲公司 · L1 · 烟草
        self.assertEqual(answer['total_groups'], 3)

    def test_a_measure_per_group_is_read_from_the_objects_that_really_belong_to_it(self):
        answer = run_query(ONTOLOGY, BUNDLE, {'start': 'license', 'where': [], 'via': [],
                                              'group_by': [{'via': ['license_typed'], 'field': '执照类型.类型名'}],
                                              'measure': {'field': '执照.费用', 'op': 'sum'}})['answer']
        self.assertEqual(answer['groups'], [['食品', 170, 2], ['烟草', 50, 1]])

    def test_dimensions_on_separate_branches_still_cross(self):
        # 从执照出发，一边到企业、一边到类型：两条独立的路，各自一个值，交叉是对的
        answer = run_query(ONTOLOGY, BUNDLE, {'start': 'license', 'where': [], 'via': [],
                                              'group_by': [{'via': ['business_holds'], 'field': '企业.企业名'},
                                                           {'via': ['license_typed'], 'field': '执照类型.类型名'}]})['answer']
        self.assertEqual(sorted(g[0] for g in answer['groups']), ['乙公司 · 食品', '甲公司 · 烟草', '甲公司 · 食品'])
        self.assertEqual(answer['total_groups'], 3)


if __name__ == '__main__':
    unittest.main()
