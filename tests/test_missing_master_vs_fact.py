import unittest

from ontology_poc_generator.ontology_eval import data_fit

# A master table of hospitals, and a results table whose rows are about results but repeat the hospital's name.
BUNDLE = {
    'schema': 'company_source_bundle.v1', 'decision': '看清医院的指标', 'file': {'name': 'cms', 'sha256': 'b' * 64, 'kind': 'table'},
    'sources': {
        '医院': {'records': [{'医院编号': 'H1', '名称': '甲院'}, {'医院编号': 'H2', '名称': '乙院'}, {'医院编号': 'H3', '名称': '丙院'}], 'requests': []},
        '结果': {'records': [{'医院编号': 'H1', '医院名称': '甲院', '指标': 'M1', '得分': '1'}, {'医院编号': 'H1', '医院名称': '甲院', '指标': 'M2', '得分': '2'},
                           {'医院编号': 'H2', '医院名称': '乙院', '指标': 'M1', '得分': '3'}], 'requests': []},
    },
}
ONTOLOGY = {
    'object_types': [
        {'key': 'hospital', 'label': '医院', 'populated_from': [{'source': '医院', 'identity': {'id': '医院编号'}}, {'source': '结果', 'identity': {'id': '医院编号'}}],
         'attributes': [{'source': '医院', 'path': '名称'}, {'source': '结果', 'path': '医院名称'}]},
        {'key': 'result', 'label': '指标结果', 'populated_from': [{'source': '结果', 'identity': {'id': '医院编号', 'measure': '指标'}}],
         'attributes': [{'source': '结果', 'path': '得分'}]},
    ],
    'relations': [{'key': 'hospital_result', 'from': 'hospital', 'to': 'result', 'source': '结果', 'meaning': '医院的指标结果'}],
    'ignored_fields': [],
}


class MasterVersusFactTableTests(unittest.TestCase):
    def test_a_hospital_with_no_results_is_not_a_broken_reference(self):
        fit = data_fit(ONTOLOGY, BUNDLE)
        self.assertEqual(fit['missing_across_sources'], [])   # H3 is in the hospital table; the results table is about results
        self.assertTrue(next(c for c in fit['checks'] if c['key'] == 'references_resolve')['passed'])
        self.assertEqual([o for o in fit['orphans'] if o['type'] == 'hospital'][0]['count'], 1)   # it still shows as having no results

    def test_a_result_for_a_hospital_the_master_table_lacks_is_still_reported(self):
        records = BUNDLE['sources']['结果']['records'] + [{'医院编号': 'H9', '医院名称': '不存在', '指标': 'M1', '得分': '4'}]
        bundle = {**BUNDLE, 'sources': {**BUNDLE['sources'], '结果': {'records': records, 'requests': []}}}
        missing = data_fit(ONTOLOGY, bundle)['missing_across_sources']
        self.assertEqual([(m['type'], m['source'], m['count'], m['examples']) for m in missing], [('hospital', '医院', 1, ['H9'])])


if __name__ == '__main__':
    unittest.main()
