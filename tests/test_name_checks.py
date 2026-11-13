"""A column whose name claims a statistic is worked out again from the rows it came from. Planted fixture (counted from the xlsx
by hand): 交付统计.交付天数P50 is, for all 12 products, the mean of 订单.交付天数 written to one decimal, and not the median
(CP05: written 18.3, mean 18.33, median 13.5; CP03: written 27.6, median 28.0)."""
import copy
import math
import unittest

from ontology_poc_generator.name_checks import claim_of, name_vs_calculation
from ontology_poc_generator.open_items import check_answers
from tests.test_workspace_store import PLANTED_DRAFT, planted_bundle


class ClaimTests(unittest.TestCase):
    def test_a_name_claims_one_statistic_or_none(self):
        self.assertEqual(claim_of('交付天数P50'), ('median', 'P50', '交付天数'))
        self.assertEqual(claim_of('交付天数中位数'), ('median', '中位数', '交付天数'))
        self.assertEqual(claim_of('平均金额')[0:3:2], ('mean', '金额'))
        self.assertEqual(claim_of('delay_p90'), ('p90', 'p90', 'delay'))
        self.assertEqual(claim_of('金额合计')[0], 'sum')
        for plain in ('订单数', '交付天数', 'CP50', '平均中位数', 'P100x', '最大值'):   # no claim, two claims, no measure left once the claim is taken out
            self.assertIsNone(claim_of(plain), plain)


class PlantedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        [cls.found] = name_vs_calculation(PLANTED_DRAFT, planted_bundle())
        cls.rows = {r['key']: r for r in cls.found['rows']}

    def test_the_p50_column_is_the_mean_for_every_product_and_the_median_for_none(self):
        f = self.found
        self.assertEqual((f['table'], f['column'], f['says'], f['source'], f['source_column'], f['by']), ('交付统计', '交付天数P50', 'median', '订单', '交付天数', ['产品编号']))
        self.assertEqual((f['compared'], f['mismatched'], f['no_source'], f['actual']), (12, 12, 0, 'mean'))
        self.assertEqual({k: r['agrees_with'] for k, r in self.rows.items()}, {k: ['mean'] for k in self.rows})

    def test_the_two_values_of_a_row_are_the_written_one_and_the_worked_out_one(self):
        cp05, cp03 = self.rows['CP05'], self.rows['CP03']
        self.assertEqual((cp05['written'], cp05['rows'], cp05['computed']['median']), (18.3, 12, 13.5))
        self.assertAlmostEqual(cp05['computed']['mean'], 18.3333, places=3)
        self.assertEqual((cp03['written'], cp03['computed']['median']), (27.6, 28.0))


def tables(median_written, extra_source=None):
    """Orders with delivery days 1..4 for product A and 10, 20 for B; a statistics table that writes `median_written` for A."""
    orders = [{'订单号': str(i), '产品编号': p, '交付天数': str(d)} for i, (p, d) in enumerate([('A', 1), ('A', 2), ('A', 3), ('A', 4), ('B', 10), ('B', 20)])]
    stats = [{'产品编号': 'A', '交付天数P90': median_written, '订单数': '4'}, {'产品编号': 'B', '交付天数P90': '19', '订单数': '2'}]
    pop = lambda source, key: {'source': source, 'identity': {'p': key}}
    draft = {'object_types': [{'key': 'product', 'label': '产品', 'attributes': [], 'populated_from': [pop('订单', '产品编号'), pop('统计', '产品编号'), *([pop(extra_source, '产品编号')] if extra_source else [])]}]}
    sources = {'订单': {'records': orders}, '统计': {'records': stats}, **({extra_source: {'records': orders}} if extra_source else {})}
    return draft, {'sources': sources}


class SyntheticTests(unittest.TestCase):
    def test_a_percentile_is_interpolated_and_a_column_that_agrees_is_not_a_mismatch(self):
        [f] = name_vs_calculation(*tables('3.7'))          # P90 of 1,2,3,4 is 3.7; of 10,20 it is 19
        self.assertEqual((f['says'], f['compared'], f['mismatched']), ('p90', 2, 0))

    def test_a_value_off_by_more_than_its_rounding_is_a_mismatch_and_a_row_with_no_source_is_counted_apart(self):
        draft, bundle = tables('3.5')
        bundle['sources']['统计']['records'].append({'产品编号': 'C', '交付天数P90': '5', '订单数': '1'})
        [f] = name_vs_calculation(draft, bundle)
        self.assertEqual((f['compared'], f['mismatched'], f['no_source'], f['actual']), (2, 1, 1, None))

    def test_two_possible_sources_are_not_guessed_between_and_the_finding_says_which_two(self):
        [f] = name_vs_calculation(*tables('3.7', extra_source='订单二'))
        self.assertEqual((f['column'], f['candidates'], f['compared'], f['mismatched']), ('交付天数P90', ['订单', '订单二'], 0, 0))
        from ontology_poc_generator.open_items import _name_vs_calc
        [item] = _name_vs_calc(*tables('3.7', extra_source='订单二'))
        self.assertEqual((item['kind'], item['id']), ('name_source', 'name_source:统计.交付天数P90'))
        self.assertIn('「订单」、「订单二」都有「交付天数」', item['ask'])

    def test_no_column_to_work_it_from_means_no_claim_to_check(self):
        draft, bundle = tables('3.7')
        for r in bundle['sources']['订单']['records']:
            r['配送天数'] = r.pop('交付天数')
        self.assertEqual(name_vs_calculation(draft, bundle), [])


def one_product(column, written, days):
    """Product A's statistic written as `written` in a statistics table; its orders' source column holds `days` (texts)."""
    orders = [{'订单号': str(i), '产品编号': 'A', '交付天数': d, '金额': '10', '状态': '已取消' if i == 0 else '有效'} for i, d in enumerate(days)]
    pop = lambda source: {'source': source, 'identity': {'p': '产品编号'}}
    draft = {'object_types': [{'key': 'product', 'label': '产品', 'attributes': [], 'populated_from': [pop('订单'), pop('统计')]}]}
    return draft, {'sources': {'订单': {'records': orders}, '统计': {'records': [{'产品编号': 'A', column: written}]}}}


class PrecisionAndSpellingTests(unittest.TestCase):
    def test_a_whole_number_is_the_worked_out_value_rounded_not_anything_within_a_half(self):
        days = ['1', '2', '5', '6']                       # the median is 3.5
        self.assertEqual(name_vs_calculation(*one_product('交付天数P50', '4', days))[0]['mismatched'], 0)
        self.assertEqual(name_vs_calculation(*one_product('交付天数P50', '3', days))[0]['mismatched'], 1)
        self.assertEqual(name_vs_calculation(*one_product('交付天数P50', '5', days))[0]['mismatched'], 1)

    def test_a_percentile_may_be_written_by_nearest_rank_and_the_finding_says_which(self):
        days = [str(i) for i in range(1, 11)]             # P90: 9.1 by interpolation, 9 by nearest rank
        for written, method in (('9.1', 'interpolation'), ('9.0', 'nearest_rank')):
            [f] = name_vs_calculation(*one_product('交付天数P90', written, days))
            self.assertEqual((f['mismatched'], f['method']), (0, method), written)
        self.assertEqual(name_vs_calculation(*one_product('交付天数P90', '9.5', days))[0]['mismatched'], 1)

    def test_values_that_are_not_numbers_are_counted_and_shown_not_dropped(self):
        [f] = name_vs_calculation(*one_product('交付天数P50', '2', ['1', '2', '3', '12天', 'N/A', 'nan', '']))
        self.assertEqual((f['unreadable'], f['unreadable_shown'], f['mismatched']), (3, ['12天', 'N/A', 'nan'], 0), f)   # the blank is not one of them
        from ontology_poc_generator.open_items import _name_vs_calc
        [item] = _name_vs_calc(*one_product('交付天数P50', '5', ['1', '2', '3', '12天', 'N/A', 'nan']))
        self.assertIn('有 3 个值不是数字（如12天、N/A、nan），没有算进去', item['facts'][0])

    def test_english_names_with_underscores_claim_a_statistic_too(self):
        for name, kind, base in (('days_avg', 'mean', 'days'), ('avg_days', 'mean', 'days'), ('total_amount', 'sum', 'amount'), ('delay_p90', 'p90', 'delay'), ('max_days', 'max', 'days')):
            claim = claim_of(name)
            self.assertEqual((claim[0], claim[2]), (kind, base), name)
        for plain in ('summary', 'meanwhile', 'totally'):
            self.assertIsNone(claim_of(plain), plain)

    def test_a_table_without_a_claiming_column_reads_no_numbers(self):
        draft, bundle = one_product('订单数', '4', ['1', '2'])
        from unittest import mock
        with mock.patch('ontology_poc_generator.name_checks._read', side_effect=AssertionError('read a value')):
            self.assertEqual(name_vs_calculation(draft, bundle), [])

    def test_the_result_is_kept_until_the_views_change(self):
        draft, bundle = one_product('交付天数P50', '2', ['1', '2', '3'])
        signature = ['a']
        bundle = {**bundle, 'calc_memo': {}, 'views_signature': lambda: signature[0]}
        first = name_vs_calculation(draft, bundle)
        self.assertIs(name_vs_calculation(draft, bundle), first)
        signature[0] = 'b'
        self.assertIsNot(name_vs_calculation(draft, bundle), first)


class MedianMethodTests(unittest.TestCase):
    def test_p50_and_the_median_in_words_are_the_standard_median_and_nothing_else(self):
        days = ['11', '12']                                # the median is 11.5: written 12 (rounded half up) is it; 11, the lower middle, is not
        for name in ('交付天数P50', '交付天数中位数', 'median_交付天数'):
            [f] = name_vs_calculation(*one_product(name, '12', days))
            self.assertEqual((f['says'], f['mismatched'], f['method']), ('median', 0, None), name)
            self.assertEqual(name_vs_calculation(*one_product(name, '11', days))[0]['mismatched'], 1, name)
            self.assertEqual(name_vs_calculation(*one_product(name, '13', days))[0]['mismatched'], 1, name)
            self.assertEqual(name_vs_calculation(*one_product(name, '1', ['1', '100']))[0]['mismatched'], 1, name)      # 50.5, not the lower of the two

    def test_the_row_lines_say_what_it_should_be_and_what_it_is_instead_with_no_method_words(self):
        from ontology_poc_generator.open_items import _name_vs_calc
        for name in ('交付天数P50', '交付天数中位数', '交付天数P90'):
            [item] = _name_vs_calc(*one_product(name, '20', ['11', '12']))
            self.assertNotIn('插值', ''.join(item['facts']), name)
            self.assertNotIn('最近秩', ''.join(item['facts']), name)
            self.assertEqual(item['column']['how'] is None, name != '交付天数P90', name)         # the method goes with the evidence, and only for a percentile that has a choice of two
        [item] = _name_vs_calc(*one_product('交付天数中位数', '20', ['11', '12']))
        self.assertEqual(item['facts'], ['A：写的是 20，中位数应是 11.5'])


class HugeValueTests(unittest.TestCase):
    def test_values_too_large_to_round_never_raise_and_never_agree_by_accident(self):
        from ontology_poc_generator.open_items import _name_vs_calc
        for written, days in (('1e30', ['1e30']), ('1000000000000000000000000000000', ['1e30']), ('1.5', ['1e308', '1e308']),
                              ('5', ['1e300'] * 3), ('9' * 400, ['1e308']), ('1.' + '5' * 600, ['1.5'])):
            for name in ('交付天数P50', '交付天数平均', '交付天数合计'):
                found = name_vs_calculation(*one_product(name, written, days))
                _name_vs_calc(*one_product(name, written, days))                 # the open items read the finding: neither may raise
                for f in found:
                    for r in f['rows']:
                        self.assertTrue(all(math.isfinite(v) for v in r['computed'].values()), (name, written))

    def test_a_huge_value_that_is_the_worked_out_one_agrees(self):
        [f] = name_vs_calculation(*one_product('交付天数合计', '1000000000000000000000000000000', ['1e30']))
        self.assertEqual((f['compared'], f['mismatched']), (1, 0))

    def test_the_item_says_how_many_rows_were_not_compared_and_prints_a_huge_value_short(self):
        from ontology_poc_generator.open_items import _name_vs_calc
        draft, bundle = one_product('交付天数合计', '5', ['1e308', '1e308'])
        bundle['sources']['订单']['records'].append({'订单号': 'x', '产品编号': 'B', '交付天数': '4'})
        bundle['sources']['统计']['records'].append({'产品编号': 'B', '交付天数合计': '9'})
        [item] = _name_vs_calc(draft, bundle)
        self.assertIn('1 行的重算值大到不是数字，没有比', item['facts'])
        [big] = _name_vs_calc(*one_product('交付天数合计', '5', ['1e300', '1e300']))
        self.assertEqual(big['facts'], ['A：写的是 5，合计应是 2e+300'])

    def test_a_sum_too_large_to_be_a_number_is_not_compared(self):
        draft, bundle = one_product('交付天数合计', '5', ['1e308', '1e308'])
        bundle['sources']['订单']['records'].append({'订单号': 'x', '产品编号': 'B', '交付天数': '4'})
        bundle['sources']['统计']['records'].append({'产品编号': 'B', '交付天数合计': '4'})
        [f] = name_vs_calculation(draft, bundle)
        self.assertEqual((f['compared'], f['mismatched'], f['no_source'], f['too_large']), (1, 0, 0, 1))        # B is compared; A's sum is not a number


class WrittenNonNumberTests(unittest.TestCase):
    def test_a_non_number_in_the_claiming_column_is_counted_and_shown(self):
        draft, bundle = tables('3.7')
        bundle['sources']['统计']['records'].extend([{'产品编号': 'C', '交付天数P90': 'N/A', '订单数': '1'}, {'产品编号': 'D', '交付天数P90': '', '订单数': '1'}])
        [f] = name_vs_calculation(draft, bundle)
        self.assertEqual((f['mismatched'], f['written_unreadable'], f['written_unreadable_shown']), (0, 1, ['N/A']))   # the blank is not one
        from ontology_poc_generator.open_items import CHOICES, _name_vs_calc
        [item] = _name_vs_calc(draft, bundle)
        self.assertEqual((item['kind'], item['id'], CHOICES['name_values']), ('name_values', 'name_values:统计.交付天数P90', ()))
        self.assertIn('有 1 个值不是数字（如N/A）', item['ask'])

    def test_it_is_a_line_on_the_mismatch_item_when_there_is_one(self):
        draft, bundle = tables('9')
        bundle['sources']['统计']['records'].append({'产品编号': 'C', '交付天数P90': '约5', '订单数': '1'})
        from ontology_poc_generator.open_items import _name_vs_calc
        [item] = _name_vs_calc(draft, bundle)
        self.assertEqual(item['kind'], 'name_vs_calc')
        self.assertTrue(any('有 1 个值不是数字（如约5）' in fact for fact in item['facts']), item['facts'])

    def test_a_clean_column_asks_nothing(self):
        self.assertEqual(__import__('ontology_poc_generator.open_items', fromlist=['x'])._name_vs_calc(*tables('3.7')), [])


class ViewTests(unittest.TestCase):
    def three_products(self, written_c):
        orders = [{'订单号': f'{p}{i}', '产品编号': p, '金额': a} for p, rows in (('A', ['10', '10']), ('B', ['5', '7']), ('C', ['4', '9'])) for i, a in enumerate(rows)]
        stats = [{'产品编号': 'A', '金额合计': '10'}, {'产品编号': 'B', '金额合计': '5'}, {'产品编号': 'C', '金额合计': written_c}]
        pop = lambda source: {'source': source, 'identity': {'p': '产品编号'}}
        draft = {'object_types': [{'key': 'product', 'label': '产品', 'attributes': [], 'populated_from': [pop('订单'), pop('统计')]}]}
        view = {'订单': {'前两单': {1, 3}}}              # one order each of A and B (C: all of its orders are outside the view)
        return draft, {'sources': {'订单': {'records': orders}, '统计': {'records': stats}}, 'subsets': lambda source: view.get(source, {})}

    def test_a_product_with_no_rows_in_the_view_does_not_block_it_when_its_total_is_written_as_nothing(self):
        for written, told in (('0', '前两单'), ('', '前两单'), ('N/A', '前两单'), ('13', None)):
            [f] = name_vs_calculation(*self.three_products(written))
            self.assertEqual(f['view'], told, written)
        [f] = name_vs_calculation(*self.three_products('0'))
        self.assertEqual((f['compared'], f['mismatched']), (3, 3))       # over the whole table none of the three is right

    def test_a_percentile_written_by_nearest_rank_over_a_view_is_told_as_the_view(self):
        orders = [{'订单号': str(i), '产品编号': 'A', '交付天数': str(d)} for i, d in enumerate(range(1, 21), 1)]
        pop = lambda source: {'source': source, 'identity': {'p': '产品编号'}}
        draft = {'object_types': [{'key': 'product', 'label': '产品', 'attributes': [], 'populated_from': [pop('订单'), pop('统计')]}]}
        kept = set(range(1, 11))                               # the first ten orders: days 1..10; P90 by nearest rank is 9, by interpolation 9.1
        bundle = {'sources': {'订单': {'records': orders}, '统计': {'records': [{'产品编号': 'A', '交付天数P90': '9'}]}}, 'subsets': lambda source: {'前十单': kept}}
        [f] = name_vs_calculation(draft, bundle)
        self.assertEqual((f['mismatched'], f['view']), (1, '前十单'))

    def test_a_view_that_keeps_the_rows_of_one_product_of_three_does_not_stand_for_all_three(self):
        orders = [{'订单号': f'{p}{i}', '产品编号': p, '金额': a} for p, rows in (('A', ['10', '10', '10']), ('B', ['5', '7']), ('C', ['4', '9'])) for i, a in enumerate(rows)]
        stats = [{'产品编号': 'A', '金额合计': '20'}, {'产品编号': 'B', '金额合计': '99'}, {'产品编号': 'C', '金额合计': '99'}]
        pop = lambda source: {'source': source, 'identity': {'p': '产品编号'}}
        draft = {'object_types': [{'key': 'product', 'label': '产品', 'attributes': [], 'populated_from': [pop('订单'), pop('统计')]}]}
        bundle = {'sources': {'订单': {'records': orders}, '统计': {'records': stats}}}
        one_of_three = {'订单': {'只看A': {1, 2}}}                     # product A's first two orders: its total 20 holds, B and C have no rows in the view
        [f] = name_vs_calculation(draft, {**bundle, 'subsets': lambda source: one_of_three.get(source, {})})
        self.assertEqual((f['compared'], f['mismatched'], f['view']), (3, 3, None))
        from ontology_poc_generator.open_items import _name_vs_calc
        [item] = _name_vs_calc(draft, {**bundle, 'subsets': lambda source: one_of_three.get(source, {})})
        self.assertEqual(item['kind'], 'name_vs_calc')


    def test_a_total_over_a_confirmed_view_is_told_as_that_and_not_as_a_mismatch(self):
        draft, bundle = one_product('金额合计', '90', ['1'] * 10)         # ten orders of 10; the first is cancelled: 有效订单 keeps nine
        subsets = {'订单': {'有效订单': set(range(2, 11))}}
        [f] = name_vs_calculation(draft, {**bundle, 'subsets': lambda source: subsets.get(source, {})})
        self.assertEqual((f['mismatched'] > 0, f['view']), (True, '有效订单'))
        [plain] = name_vs_calculation(draft, bundle)
        self.assertIsNone(plain['view'])
        from ontology_poc_generator.open_items import _name_vs_calc
        [item] = _name_vs_calc(draft, {**bundle, 'subsets': lambda source: subsets.get(source, {})})
        self.assertEqual((item['kind'], item['column']['view']), ('name_by_view', '有效订单'))
        self.assertIn('按「有效订单」算的合计', item['ask'])
        [asked] = _name_vs_calc(draft, bundle)
        self.assertEqual(asked['kind'], 'name_vs_calc')              # no view: a mismatch as before
        from ontology_poc_generator.open_items import CHOICES
        self.assertEqual(CHOICES['name_by_view'], ())               # the choice that blames the data is not offered for it


class OpenItemTests(unittest.TestCase):
    def test_the_mismatch_is_an_open_item_on_the_column_and_can_be_answered(self):
        from tests.test_ontology_server import OntologyServerTests
        from tests.test_open_items_server import call, fetch
        from tests.test_workspace_store import DraftsModel, ServerDataChecksTests
        with OntologyServerTests().server(gateway=DraftsModel(copy.deepcopy(PLANTED_DRAFT))) as (base, _):
            _, run = call(base, '/api/ontology/build', {'files': ServerDataChecksTests.files})
            _, listed = fetch(base, f"/api/ontology/runs/{run['saved_as']}/open-items")
            [item] = [i for i in listed['items'] if i['kind'] == 'name_vs_calc']
            self.assertEqual(item['id'], 'name_vs_calc:交付统计.交付天数P50')
            self.assertIn('名字说是中位数', item['ask'])
            self.assertIn('12 行里有 12 行对不上', item['ask'])
            self.assertEqual((item['column']['says_text'], item['column']['actual_text'], item['target']), ('中位数', '平均数', {'tab': 'data', 'table': '交付统计'}))
            self.assertEqual(len(item['facts']), 12)
            self.assertIn('CP05：写的是 18.3，中位数应是 13.5，平均数是 18.33', item['facts'])
            status, saved = call(base, '/api/ontology/card', {'saved_as': run['saved_as'], 'by': '王工', 'items': [{'id': item['id'], 'choice': 'rename', 'text': '改成平均'}]})
            self.assertEqual(status, 200, saved)
            _, after = fetch(base, f"/api/ontology/runs/{run['saved_as']}/open-items")
            self.assertNotIn(item['id'], [i['id'] for i in after['items']])
            self.assertEqual([a['answer']['says'] for a in after['answered'] if a['id'] == item['id']], ['名字说错了，按实际算法改名'])

    def test_only_the_two_choices_are_accepted(self):
        listed = [{'id': 'name_vs_calc:a.b', 'kind': 'name_vs_calc', 'ask': 'q'}]
        check_answers(listed, [{'id': 'name_vs_calc:a.b', 'choice': 'name_right'}], '王工', 't')
        with self.assertRaises(Exception):
            check_answers(listed, [{'id': 'name_vs_calc:a.b', 'choice': 'same'}], '王工', 't')


if __name__ == '__main__':
    unittest.main()
