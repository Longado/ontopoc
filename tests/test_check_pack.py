"""The check pack: beside every answered query, what each filter removed, so a consultant can see which condition
shrank the result and which one the model added on its own. It rides in `evidence`, never inside `answer`."""
import unittest

from ontology_poc_generator.derived_measures import parse_derived
from ontology_poc_generator.ontology_questions import ask_questions, flag_unasked_filters, run_query
from tests import test_ontology_questions as asked
from tests.test_derived_measures import AMOUNT, ONTOLOGY as LINES, bundle as lines_bundle
from tests.test_group_fan_trap import BY_PARENT_NAME, GREENBERRY, VENDOR_ONTOLOGY, VENDORS
from tests.test_measure import AMOUNT_SUM, CUSTOMER, INVOICE, INVOICES, WITH_INVOICE_TYPE

RECLAMATION = 'BUREAU OF RECLAMATION'
OTHER = 'OTHER SUBAGENCY'
COLUMNS = ('award_id', 'agency_id', 'sub_agency', 'status', 'amount')
ROWS = [('A1', '1425', RECLAMATION, 'ACTIVE', '100'),
        ('A2', '1425', RECLAMATION, 'ACTIVE', '2,000.50'),
        ('A3', '1425', RECLAMATION, 'CLOSED', '50'),
        ('A4', '1425', OTHER, 'ACTIVE', '30'),
        ('A5', '1425', OTHER, 'ACTIVE', 'n/a'),      # a word where a number belongs: never read as zero
        ('A6', '1425', RECLAMATION, 'ACTIVE', '7'),
        ('A7', '1425', RECLAMATION, 'ACTIVE', ''),
        ('A8', '1425', OTHER, 'CLOSED', '20'),
        ('A9', '1425', OTHER, 'ACTIVE', '10')]
BUNDLE = {'schema': 'company_source_bundle.v1', 'decision': '看各子机构的合同金额',
          'file': {'name': 'awards.csv', 'sha256': 'f' * 64, 'kind': 'table'},
          'sources': {'awards': {'records': [dict(zip(COLUMNS, row)) for row in ROWS], 'requests': []}}}
ONTOLOGY = {'object_types': [{'key': 'award', 'label': '合同', 'populated_from': [{'source': 'awards', 'identity': {'award_id': 'award_id'}}],
                              'attributes': [{'source': 'awards', 'path': p} for p in COLUMNS[1:]]}],
            'relations': [], 'ignored_fields': []}
where = lambda field, value: {'field': f'awards.{field}', 'equals': value}
THREE = [where('agency_id', '1425'), where('sub_agency', RECLAMATION), where('status', 'ACTIVE')]   # the first removes nothing, the third removes A3
TOTAL = {'field': 'awards.amount', 'op': 'sum'}


class FilterChainTests(unittest.TestCase):
    def test_each_filter_shows_what_it_alone_removed_in_the_order_written(self):
        result = run_query(ONTOLOGY, BUNDLE, {'start': 'award', 'where': THREE, 'measure': TOTAL})
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['evidence']['filters'], [
            {'field': 'agency_id', 'equals': '1425', 'before': 9, 'after': 9, 'examples': []},   # removes nothing: before == after
            {'field': 'sub_agency', 'equals': RECLAMATION, 'before': 9, 'after': 5, 'examples': ['A4', 'A5', 'A8'], 'removed_measure': 60},   # A5 is not a number; a fourth removed object is not named
            {'field': 'status', 'equals': 'ACTIVE', 'before': 5, 'after': 4, 'examples': ['A3'], 'removed_measure': 50}])

    def test_evidence_never_goes_inside_the_answer(self):
        result = run_query(ONTOLOGY, BUNDLE, {'start': 'award', 'where': THREE, 'measure': TOTAL})
        self.assertNotIn('evidence', result['answer'])
        self.assertEqual(result['answer']['measure'], {'field': 'amount', 'op': 'sum', 'value': 2107.5, 'counted': 3, 'skipped': 1})

    def test_without_a_measure_no_removed_amount_is_reported(self):
        filters = run_query(ONTOLOGY, BUNDLE, {'start': 'award', 'where': THREE})['evidence']['filters']
        self.assertEqual([f['after'] for f in filters], [9, 5, 4])
        self.assertTrue(all('removed_measure' not in f for f in filters))

    def test_no_condition_means_no_filter_evidence(self):
        self.assertNotIn('evidence', run_query(ONTOLOGY, BUNDLE, {'start': 'award', 'where': [], 'measure': TOTAL}))

    def test_a_filter_that_removed_everything_still_shows_up_when_the_answer_is_no_data(self):
        result = run_query(ONTOLOGY, BUNDLE, {'start': 'award', 'where': [where('agency_id', '1425'), where('status', 'VOID')], 'measure': TOTAL})
        self.assertEqual(result['status'], 'no_data')
        self.assertEqual(result['evidence']['filters'], [
            {'field': 'agency_id', 'equals': '1425', 'before': 9, 'after': 9, 'examples': []},
            {'field': 'status', 'equals': 'VOID', 'before': 9, 'after': 0, 'examples': ['A1', 'A2', 'A3'], 'removed_measure': 2217.5}])

    def test_it_rides_beside_a_grouped_answer_and_the_merged_groups(self):
        result = run_query(VENDOR_ONTOLOGY, VENDORS, {'start': 'vendor', 'where': [{'field': 'vendors.amount', 'equals': '100'}], 'group_by': [BY_PARENT_NAME]})
        self.assertEqual(result['answer']['groups'], [[GREENBERRY, 1]])
        self.assertEqual(result['evidence'], {
            'filters': [{'field': 'amount', 'equals': '100', 'before': 3, 'after': 1, 'examples': ['V2', 'V3']}],
            'merged': [{'group': GREENBERRY, 'starts': 1, 'objects': 2, 'start': '供应商', 'reached': '最终母公司', 'examples': ['P1', 'P2']}]})

    def test_a_derived_measure_reports_what_the_removed_objects_would_have_added(self):
        derived, _ = parse_derived(LINES, AMOUNT)
        query = {'start': 'order_line', 'where': [{'field': 'lines.折扣', 'equals': '0'}], 'measure': {'derived': '金额', 'op': 'sum'}}
        result = run_query(LINES, lines_bundle(), query, derived=[derived])
        self.assertEqual(result['answer']['measure']['value'], 23)   # 20 + 3
        self.assertEqual(result['evidence']['filters'], [{'field': '折扣', 'equals': '0', 'before': 3, 'after': 2, 'examples': ['O1 · P1'], 'removed_measure': 10}])

    def test_looking_one_object_up_by_its_identity_names_no_other_objects(self):
        result = run_query(ONTOLOGY, BUNDLE, {'start': 'award', 'where': [where('award_id', 'A2')], 'measure': TOTAL})
        self.assertEqual(result['evidence']['filters'], [{'field': 'award_id', 'equals': 'A2', 'before': 9, 'after': 1}])

    def test_removed_objects_whose_rows_cannot_be_added_report_no_removed_amount(self):
        records = [{**r, 'region': 'N' if r['customer_id'] == 'A' else 'S'} for r in INVOICES['sources']['invoices']['records']]
        regions = {**INVOICES, 'sources': {'invoices': {'records': records, 'requests': []}}}
        ontology = {**WITH_INVOICE_TYPE, 'object_types': [{**CUSTOMER, 'attributes': [*CUSTOMER['attributes'], {'source': 'invoices', 'path': 'region'}]}, INVOICE]}
        result = run_query(ontology, regions, {'start': 'customer', 'where': [{'field': 'invoices.region', 'equals': 'S'}], 'measure': AMOUNT_SUM})
        self.assertEqual(result['answer']['measure']['value'], 10)
        self.assertNotIn('removed_measure', result['evidence']['filters'][0])   # A's 5 + 5 + 4 cannot be read through 客户


class NotInQuestionTests(unittest.TestCase):
    QUERY = {'start': 'award', 'where': THREE, 'measure': TOTAL}

    def ask(self, text, **kwargs):
        model = asked.AskTests.Model({'questions': [{'reasoning': 'r', 'question': text, 'query': self.QUERY}]})
        [item] = ask_questions(ONTOLOGY, BUNDLE, model, **kwargs)['items']
        return item

    def flags(self, item):
        return [f.get('not_in_question') for f in item['evidence']['filters']]

    def test_only_the_filter_whose_value_the_question_never_says_is_marked(self):
        item = self.ask('bureau of reclamation 的合同里 active 的合计金额是多少？')   # case does not matter; 1425 is nowhere
        self.assertEqual(self.flags(item), [True, None, None])

    def test_spaces_and_longer_tokens_do_not_hide_a_value_that_is_there(self):
        item = self.ask('BureauOfReclamation 在 FY1425 年度 ACTIVE 合同合计？')
        self.assertEqual(self.flags(item), [None, None, None])

    def test_it_is_a_hint_the_answer_and_status_stay_as_run_query_gave_them(self):
        item = self.ask('合同金额合计是多少？')
        self.assertEqual(self.flags(item), [True, True, True])
        plain = run_query(ONTOLOGY, BUNDLE, self.QUERY)
        self.assertEqual((item['status'], item['answer']), (plain['status'], plain['answer']))
        self.assertNotIn('not_in_question', plain['evidence']['filters'][0])   # the input is not changed in place

    def test_a_question_the_person_typed_is_what_the_filters_are_checked_against(self):
        item = self.ask('BUREAU OF RECLAMATION 1425 ACTIVE 合同合计', question='合同金额合计是多少？')   # the model's rewording says them all
        self.assertEqual(self.flags(item), [True, True, True])

    def test_a_short_code_counts_only_as_a_word_of_its_own(self):
        result = {'evidence': {'filters': [{'field': 'region', 'equals': 'N'}, {'field': 'zone', 'equals': 'S'}]}}
        flagged = flag_unasked_filters(result, 'How many invoices in Nanjing, zone S?')
        self.assertEqual([f.get('not_in_question') for f in flagged['evidence']['filters']], [True, None])


if __name__ == '__main__':
    unittest.main()
