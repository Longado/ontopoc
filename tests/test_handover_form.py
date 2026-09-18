import unittest

from ontology_poc_generator.handover_form import handover_form

# 统一编号带前导零（当成整数就丢了），金额是整数，股数很大，日期是 ISO，备注有空值。
BUNDLE = {
    'schema': 'company_source_bundle.v1', 'decision': '看清公司和董监事', 'file': {'name': 'tw', 'sha256': 'f' * 64, 'kind': 'table'},
    'sources': {
        '公司': {'records': [{'统编': '03795904', '公司名': '台灣電力股份有限公司', '资本额': '600000000000', '设立日': '2026-01-02', '备注': ''},
                           {'统编': '53111933', '公司名': '匯弘', '资本额': '1000', '设立日': '2026-03-04', '备注': '甲'}], 'requests': []},
        '董监事': {'records': [{'统编': '03795904', '姓名': '张三', '持股': '1.5'}, {'统编': '03795904', '姓名': '李四', '持股': '2'},
                            {'统编': '53111933', '姓名': '王五', '持股': ''}], 'requests': []},
    },
}
ONTOLOGY = {
    'object_types': [
        {'key': 'company', 'label': '公司', 'populated_from': [{'source': '公司', 'identity': {'id': '统编'}}, {'source': '董监事', 'identity': {'id': '统编'}}],
         'attributes': [{'source': '公司', 'path': '公司名'}, {'source': '公司', 'path': '资本额'}, {'source': '公司', 'path': '设立日'}, {'source': '公司', 'path': '备注'}]},
        {'key': 'director', 'label': '董监事', 'populated_from': [{'source': '董监事', 'identity': {'id': '统编', 'name': '姓名'}}],
         'attributes': [{'source': '董监事', 'path': '持股'}]},
    ],
    'relations': [{'key': 'company_director', 'from': 'company', 'to': 'director', 'source': '董监事', 'meaning': '公司有董监事'}],
    'ignored_fields': [],
}


class HandoverFormTests(unittest.TestCase):
    def setUp(self):
        self.form = handover_form(ONTOLOGY, BUNDLE)

    def field(self, type_key, path):
        return next(f for t in self.form['types'] if t['type'] == type_key for f in t['fields'] if f['path'] == path)

    def test_a_number_written_with_a_leading_zero_stays_text(self):
        # 03795904 当成整数就丢了开头的 0，那是另一个统编
        self.assertEqual(self.field('company', '统编')['type'], 'VARCHAR')
        self.assertEqual(self.field('company', '统编')['length'], 8)
        self.assertTrue(self.field('company', '统编')['identity'])

    def test_types_are_read_from_every_value_not_from_the_field_name(self):
        self.assertEqual(self.field('company', '资本额')['type'], 'INTEGER')
        self.assertEqual(self.field('company', '设立日')['type'], 'DATE')
        self.assertEqual(self.field('company', '公司名')['type'], 'VARCHAR')
        self.assertEqual(self.field('company', '公司名')['length'], 10)   # 最长的那个名字有多少个字
        self.assertEqual(self.field('director', '持股')['type'], 'DECIMAL')   # 1.5 和 2 混在一起

    def test_empty_values_are_counted_and_an_all_empty_field_has_no_type(self):
        self.assertEqual(self.field('company', '备注')['empty'], 1)
        self.assertEqual(self.field('company', '备注')['type'], 'VARCHAR')
        empty = handover_form({**ONTOLOGY, 'object_types': [{**ONTOLOGY['object_types'][0],
                                                             'attributes': [{'source': '公司', 'path': '空列'}]}]},
                              {**BUNDLE, 'sources': {**BUNDLE['sources'],
                                                     '公司': {'records': [{'统编': 'A', '空列': ''}], 'requests': []}}})
        self.assertEqual(empty['types'][0]['fields'][-1], {'path': '空列', 'identity': False, 'source': '公司',
                                                           'type': None, 'length': 0, 'empty': 1, 'rows': 1})

    def test_a_relation_says_how_many_hang_off_each_end(self):
        self.assertEqual(self.form['relations'], [{'key': 'company_director', 'from': 'company', 'to': 'director',
                                                   'cardinality': 'one_to_many', 'most_from': 2, 'most_to': 1}])

    def test_an_object_identified_by_two_fields_is_marked_for_a_single_primary_key(self):
        director = next(t for t in self.form['types'] if t['type'] == 'director')
        self.assertEqual(director['identity_fields'], ['姓名', '统编'])
        self.assertTrue(director['needs_single_key'])
        self.assertFalse(next(t for t in self.form['types'] if t['type'] == 'company')['needs_single_key'])


if __name__ == '__main__':
    unittest.main()
