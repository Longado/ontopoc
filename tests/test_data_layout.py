"""The data-layout panel: what each uploaded table looks like, and — when tables are left unconnected — which column
would connect them."""
import unittest

from ontology_poc_generator.handover_form import source_profile
from ontology_poc_generator.ontology_eval import bridge_hints


def table(*rows, skipped=None):
    header, *data = rows
    return {'records': [dict(zip(header, r)) for r in data], 'requests': [], **({'skipped_rows': skipped} if skipped else {})}


COMPANIES = table(('統一編號', '公司名稱'), ('03795904', '台灣電力'), ('22099131', '台積電'), ('53111933', '富邦金'))
DIRECTORS = table(('統一編號', '職稱', '姓名'), ('53111933', '董事長', '甲'), ('53111933', '董事', '乙'),
                  ('03795904', '董事', '丙'), ('03795904', '監察人', '丁'))


class BridgeHintTests(unittest.TestCase):
    def test_a_column_whose_every_value_is_a_key_of_the_other_table_is_offered_as_a_bridge(self):
        bundle = {'sources': {'companies': COMPANIES, 'directors': DIRECTORS}}
        hints = bridge_hints(bundle, [['companies'], ['directors']])
        self.assertEqual(hints, [{'from_source': 'directors', 'from_field': '統一編號', 'to_source': 'companies',
                                  'to_field': '統一編號', 'rows': 4, 'linked_rows': 4}])

    def test_tables_already_connected_get_no_hint(self):
        bundle = {'sources': {'companies': COMPANIES, 'directors': DIRECTORS}}
        self.assertEqual(bridge_hints(bundle, [['companies', 'directors']]), [])

    def test_one_value_the_other_table_does_not_have_means_no_bridge(self):
        stray = table(('統一編號', '姓名'), ('53111933', '甲'), ('99999999', '乙'))
        self.assertEqual(bridge_hints({'sources': {'companies': COMPANIES, 'directors': stray}}, [['companies'], ['directors']]), [])

    def test_a_column_with_repeated_values_is_not_a_key_to_point_at(self):
        # every 職稱 value of one table is found in the other, but 職稱 repeats there too: nothing identifies a row
        titles = table(('職稱', '說明'), ('董事', 'a'), ('董事', 'b'), ('監察人', 'c'))
        hints = bridge_hints({'sources': {'titles': titles, 'directors': DIRECTORS}}, [['titles'], ['directors']])
        self.assertEqual(hints, [])

    def test_empty_cells_are_neither_a_match_nor_a_miss(self):
        gaps = table(('統一編號', '姓名'), ('53111933', '甲'), ('', '乙'))
        hints = bridge_hints({'sources': {'companies': COMPANIES, 'directors': gaps}}, [['companies'], ['directors']])
        self.assertEqual([(h['rows'], h['linked_rows']) for h in hints], [(2, 1)])


class SourceProfileTests(unittest.TestCase):
    def test_each_table_says_its_size_the_title_lines_skipped_and_every_column_shape(self):
        orders = table(('訂單號', '金額', '備註'), ('007', '100', ''), ('012', '50.5', '急'), skipped=['2026 年訂單匯總'])
        profile = source_profile({'sources': {'orders': orders}})
        self.assertEqual(profile, [{'name': 'orders', 'rows': 2, 'skipped_rows': ['2026 年訂單匯總'], 'fields': [
            {'path': '訂單號', 'type': 'VARCHAR', 'length': 3, 'empty': 0},
            {'path': '金額', 'type': 'DECIMAL', 'length': 4, 'empty': 0},
            {'path': '備註', 'type': 'VARCHAR', 'length': 1, 'empty': 1}]}])

    def test_a_table_with_nothing_skipped_says_so(self):
        self.assertEqual(source_profile({'sources': {'companies': COMPANIES}})[0]['skipped_rows'], [])


if __name__ == '__main__':
    unittest.main()
