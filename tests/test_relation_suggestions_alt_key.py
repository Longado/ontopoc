"""A column that holds another object's name rather than its number (the idea from ontexus's alternate-key inference):
the directors table's 所代表法人 names companies, some of which are in the registry. Names can sit several to a cell."""
import unittest

from ontology_poc_generator.relation_suggestions import suggest_relations
from tests.test_relation_suggestions import table

BUNDLE = {'sources': {
    'directors': table(('職務編號', '姓名', '所代表法人', '持股'), ('D1', '甲', '匯弘投資、長春投資', '10'), ('D2', '乙', '長春投資', '20'),
                       ('D3', '丙', '', '5'), ('D4', '丁', '外國公司', '3')),
    'registry': table(('統一編號', '公司名稱', '資本'), ('001', '匯弘投資', '10'), ('002', '長春投資', '20'), ('003', '台灣電力', '30')),
}}
ONTOLOGY = {
    'object_types': [
        {'key': 'officer', 'label': '董監事任職', 'populated_from': [{'source': 'directors', 'identity': {'id': '職務編號'}}],
         'attributes': [{'source': 'directors', 'path': '姓名'}, {'source': 'directors', 'path': '所代表法人'}, {'source': 'directors', 'path': '持股'}]},
        {'key': 'company', 'label': '公司', 'populated_from': [{'source': 'registry', 'identity': {'id': '統一編號'}}],
         'attributes': [{'source': 'registry', 'path': '公司名稱'}, {'source': 'registry', 'path': '資本'}]},
    ],
    'relations': [], 'ignored_fields': [], 'open_questions': [],
}


class AlternateKeyTests(unittest.TestCase):
    def test_a_column_of_another_objects_names_is_suggested_with_how_many_rows_match(self):
        [s] = [x for x in suggest_relations(ONTOLOGY, BUNDLE) if x['kind'] == 'alternate_key']
        self.assertEqual((s['from'], s['to']), ('officer', 'company'))
        self.assertEqual(s['via'], {'source': 'directors', 'field': '所代表法人'})
        self.assertEqual(s['key'], {'source': 'registry', 'field': '公司名稱'})
        # three rows name someone; two of them name companies the registry has, one cell naming two of them
        self.assertEqual((s['rows'], s['filled'], s['linked']), (4, 3, 2))

    def test_numbers_are_not_names(self):
        # 資本 is unique in the registry and 持股 shares values with it, but numbers matching numbers is not a name matching
        self.assertEqual([x for x in suggest_relations(ONTOLOGY, BUNDLE) if x['key']['field'] == '資本'], [])


if __name__ == '__main__':
    unittest.main()
