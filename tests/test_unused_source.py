import unittest

from ontology_poc_generator.ontology_eval import data_fit

# 传了两份表，模型把第二份的每一列都标成"不用"：这份文件等于没进本体，而人是特意传它的。
BUNDLE = {
    'schema': 'company_source_bundle.v1', 'decision': '看清公司和董监事', 'file': {'name': 'tw', 'sha256': 'e' * 64, 'kind': 'table'},
    'sources': {
        '公司': {'records': [{'统编': 'A1', '公司名': '甲'}, {'统编': 'A2', '公司名': '乙'}], 'requests': []},
        '董监事': {'records': [{'统编': 'A1', '职称': '董事长', '姓名': '张三'}, {'统编': 'A1', '职称': '董事', '姓名': '李四'}], 'requests': []},
    },
}
ONTOLOGY = {
    'object_types': [{'key': 'company', 'label': '公司', 'populated_from': [{'source': '公司', 'identity': {'id': '统编'}}],
                      'attributes': [{'source': '公司', 'path': '公司名'}]}],
    'relations': [],
    'ignored_fields': [{'source': '董监事', 'path': p, 'reason': '没有唯一识别码'} for p in ('统编', '职称', '姓名')],
}


class UnusedSourceTests(unittest.TestCase):
    def test_a_table_nothing_reads_is_named_and_fails_its_own_check(self):
        fit = data_fit(ONTOLOGY, BUNDLE)
        self.assertEqual(fit['unused_sources'], [{'source': '董监事', 'rows': 2, 'fields': 3}])
        self.assertFalse(next(c for c in fit['checks'] if c['key'] == 'sources_used')['passed'])

    def test_every_table_read_by_something_passes(self):
        ontology = {**ONTOLOGY, 'ignored_fields': [],
                    'object_types': ONTOLOGY['object_types'] + [
                        {'key': 'director', 'label': '董监事',
                         'populated_from': [{'source': '董监事', 'identity': {'company': '统编', 'name': '姓名'}}],
                         'attributes': [{'source': '董监事', 'path': '职称'}]}]}
        fit = data_fit(ontology, BUNDLE)
        self.assertEqual(fit['unused_sources'], [])
        self.assertTrue(next(c for c in fit['checks'] if c['key'] == 'sources_used')['passed'])

    def test_a_few_ignored_columns_are_still_fine(self):
        ontology = {**ONTOLOGY, 'object_types': [{**ONTOLOGY['object_types'][0], 'attributes': []}],
                    'ignored_fields': [{'source': '公司', 'path': '公司名', 'reason': '这次用不上'},
                                       *ONTOLOGY['ignored_fields']]}
        fit = data_fit(ontology, BUNDLE)
        self.assertEqual([u['source'] for u in fit['unused_sources']], ['董监事'])   # 公司表仍被识别字段读着


if __name__ == '__main__':
    unittest.main()
