import unittest

from ontology_poc_generator.handover_form import handover_form

# 站点在站点表里有 6 位的编号，在停靠表里只出现过 5 位的：同一个字段，表单里只该有一行。
BUNDLE = {
    'schema': 'company_source_bundle.v1', 'decision': '看清线路', 'file': {'name': 'gtfs', 'sha256': 'b' * 64, 'kind': 'table'},
    'sources': {
        '站点': {'records': [{'站点号': 'ABCDEF', '站名': '总站'}, {'站点号': 'XYZ12', '站名': '一号台'}], 'requests': []},
        '停靠': {'records': [{'班次': 'T1', '站点号': 'XYZ12'}, {'班次': 'T1', '站点号': 'XYZ12'}, {'班次': 'T2', '站点号': ''}], 'requests': []},
    },
}
ONTOLOGY = {
    'object_types': [{'key': 'stop', 'label': '站点',
                      'populated_from': [{'source': '站点', 'identity': {'id': '站点号'}}, {'source': '停靠', 'identity': {'id': '站点号'}}],
                      'attributes': [{'source': '站点', 'path': '站名'}]}],
    'relations': [], 'ignored_fields': [],
}


class MergedFieldTests(unittest.TestCase):
    def test_one_field_read_from_two_tables_is_one_row_of_the_form(self):
        fields = handover_form(ONTOLOGY, BUNDLE)['types'][0]['fields']
        self.assertEqual([f['path'] for f in fields], ['站点号', '站名'])
        key = fields[0]
        self.assertEqual((key['type'], key['length'], key['empty'], key['rows']), ('VARCHAR', 6, 1, 5))
        self.assertEqual(key['sources'], ['停靠', '站点'])


if __name__ == '__main__':
    unittest.main()
