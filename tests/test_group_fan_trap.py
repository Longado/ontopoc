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

    def test_the_longer_path_first_still_reads_one_chain(self):
        answer = run_query(ONTOLOGY, BUNDLE, {'start': 'business', 'group_by': [BY_TYPE, BY_LICENSE]})['answer']
        self.assertEqual(sorted(g[0] for g in answer['groups']), sorted(['食品 · L1', '烟草 · L2', '食品 · L3']))   # not 食品 · L2 or 烟草 · L1


# V1 经两行关系连到 P1、P2 两个对象，它们的名字相同（真实采购数据里同一母公司被登记成两个对象）；V3 也连 P1
VENDORS = {
    'schema': 'company_source_bundle.v1', 'decision': '看各最终母公司名下有多少供应商',
    'file': {'name': 'vendors.csv', 'sha256': 'd' * 64, 'kind': 'table'},
    'sources': {
        'vendors': {'records': [{'vendor_id': 'V1', 'amount': '100'}, {'vendor_id': 'V2', 'amount': '30'}, {'vendor_id': 'V3', 'amount': '7'}], 'requests': []},
        'links': {'records': [
            {'vendor_id': 'V1', 'parent_id': 'P1', 'parent_name': 'GREENBERRY INDUSTRIAL LLC'},
            {'vendor_id': 'V1', 'parent_id': 'P2', 'parent_name': 'GREENBERRY INDUSTRIAL LLC'},
            {'vendor_id': 'V3', 'parent_id': 'P1', 'parent_name': 'GREENBERRY INDUSTRIAL LLC'},
            {'vendor_id': 'V2', 'parent_id': 'P3', 'parent_name': 'OTHER CO'},
        ], 'requests': []},
    },
}
VENDOR_ONTOLOGY = {
    'object_types': [
        {'key': 'vendor', 'label': '供应商', 'populated_from': [{'source': 'vendors', 'identity': {'id': 'vendor_id'}},
                                                          {'source': 'links', 'identity': {'id': 'vendor_id'}}],
         'attributes': [{'source': 'vendors', 'path': 'amount'}]},
        {'key': 'parent', 'label': '最终母公司', 'populated_from': [{'source': 'links', 'identity': {'id': 'parent_id'}}],
         'attributes': [{'source': 'links', 'path': 'parent_name'}]},
    ],
    'relations': [{'key': 'vendor_parent', 'from': 'vendor', 'to': 'parent', 'source': 'links', 'meaning': '供应商属于最终母公司'}],
    'ignored_fields': [],
}
BY_PARENT_NAME = {'via': ['vendor_parent'], 'field': 'links.parent_name'}
GREENBERRY = 'GREENBERRY INDUSTRIAL LLC'


class SameValueFromTwoObjectsTests(unittest.TestCase):
    def test_a_start_object_counts_once_per_group_and_the_merge_is_shown_beside_the_answer(self):
        result = run_query(VENDOR_ONTOLOGY, VENDORS, {'start': 'vendor', 'group_by': [BY_PARENT_NAME]})
        self.assertEqual(result['answer']['groups'], [[GREENBERRY, 2], ['OTHER CO', 1]])   # V1 and V3, not V1 twice
        self.assertEqual(result['evidence'], {'merged': [{'group': GREENBERRY, 'starts': 1, 'objects': 2, 'start': '供应商', 'reached': '最终母公司', 'examples': ['P1', 'P2']}]})
        self.assertNotIn('evidence', result['answer'])   # acceptance compares the answer between runs

    def test_a_sum_and_a_share_read_each_start_object_once(self):
        total = run_query(VENDOR_ONTOLOGY, VENDORS, {'start': 'vendor', 'group_by': [BY_PARENT_NAME],
                                                      'measure': {'field': 'vendors.amount', 'op': 'sum'}})
        self.assertEqual(total['answer']['groups'], [[GREENBERRY, 107, 2], ['OTHER CO', 30, 1]])   # V1's 100 once, not twice
        self.assertEqual(total['evidence']['merged'][0]['group'], GREENBERRY)
        share = run_query(VENDOR_ONTOLOGY, VENDORS, {'start': 'vendor', 'group_by': [BY_PARENT_NAME],
                                                      'share': {'field': 'vendors.amount', 'equals': '100'}})
        self.assertEqual(share['answer']['groups'], [[GREENBERRY, 1, 2], ['OTHER CO', 0, 1]])

    def test_nothing_is_reported_when_no_start_object_reached_a_group_through_two_objects(self):
        result = run_query(VENDOR_ONTOLOGY, VENDORS, {'start': 'vendor', 'group_by': [{'via': [], 'field': 'vendors.amount'}]})
        self.assertEqual(result['status'], 'answered')
        self.assertNotIn('evidence', result)


# 甲公司的三张执照都是食品，两个网点都在杭州：一组“食品 · 杭州”背后是 3 张执照和 2 个网点，不是 6 个对象
BRANCHES = {
    'schema': 'company_source_bundle.v1', 'decision': '看各类执照和网点城市',
    'file': {'name': 'branches.csv', 'sha256': 'b' * 64, 'kind': 'table'},
    'sources': {
        'licences': {'records': [{'licence': f'L{i}', 'firm': 'E1', 'kind': '食品'} for i in (1, 2, 3)], 'requests': []},
        'branches': {'records': [{'branch': f'B{i}', 'firm': 'E1', 'city': '杭州'} for i in (1, 2)], 'requests': []},
    },
}
BRANCH_ONTOLOGY = {
    'object_types': [
        {'key': 'firm', 'label': '企业', 'populated_from': [{'source': 'licences', 'identity': {'id': 'firm'}}, {'source': 'branches', 'identity': {'id': 'firm'}}], 'attributes': []},
        {'key': 'licence', 'label': '执照', 'populated_from': [{'source': 'licences', 'identity': {'id': 'licence'}}], 'attributes': [{'source': 'licences', 'path': 'kind'}]},
        {'key': 'branch', 'label': '网点', 'populated_from': [{'source': 'branches', 'identity': {'id': 'branch'}}], 'attributes': [{'source': 'branches', 'path': 'city'}]},
    ],
    'relations': [{'key': 'holds', 'from': 'firm', 'to': 'licence', 'source': 'licences', 'meaning': '企业持有执照'},
                  {'key': 'has_branch', 'from': 'firm', 'to': 'branch', 'source': 'branches', 'meaning': '企业有网点'}],
    'ignored_fields': [],
}


class MergedObjectsTests(unittest.TestCase):
    def test_the_objects_named_are_the_ones_that_differ_not_every_chain(self):
        result = run_query(BRANCH_ONTOLOGY, BRANCHES, {'start': 'firm', 'group_by': [{'via': ['holds'], 'field': 'licences.kind'},
                                                                                     {'via': ['has_branch'], 'field': 'branches.city'}]})
        self.assertEqual(result['answer']['groups'], [['食品 · 杭州', 1]])
        self.assertEqual(result['evidence']['merged'], [{'group': '食品 · 杭州', 'starts': 1, 'objects': 5, 'start': '企业', 'reached': '网点、执照', 'examples': ['B1', 'B2', 'L1']}])


if __name__ == '__main__':
    unittest.main()
