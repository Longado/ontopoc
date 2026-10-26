import unittest

from ontology_poc_generator.derived_measures import parse_derived
from ontology_poc_generator.ontology_confirm import without_wrong
from ontology_poc_generator.public_ontology import build_graph
from ontology_poc_generator.ontology_questions import QUESTION_PROMPT_VERSION, QUESTION_SYSTEM_PROMPT, run_query
from tests.test_company_ontology import BUNDLE, PROPOSAL

# 订单：O1 金额 100（客户甲）、O2 金额 50（客户乙）、O3 金额 70（客户 C9，客户表里没有）
SUM = {'start': 'order', 'measure': {'field': '订单.金额', 'op': 'sum'}}
BY_CUSTOMER = {'via': ['order_customer'], 'field': '客户.名称'}


class MeasureTests(unittest.TestCase):
    def test_a_total_is_added_up_by_code_and_says_how_many_rows_it_added(self):
        answer = run_query(PROPOSAL, BUNDLE, SUM)['answer']
        self.assertEqual(answer['measure'], {'field': '金额', 'op': 'sum', 'value': 220, 'counted': 3, 'skipped': 0})

    def test_an_average_says_what_its_denominator_was(self):
        answer = run_query(PROPOSAL, BUNDLE, {**SUM, 'measure': {'field': '订单.金额', 'op': 'average'}})['answer']
        self.assertEqual(answer['measure']['value'], 220 / 3)
        self.assertEqual(answer['measure']['counted'], 3)

    def test_values_that_are_not_numbers_are_skipped_and_counted_not_read_as_zero(self):
        records = [{**r} for r in BUNDLE['sources']['订单']['records']]
        records[0]['金额'] = 'DUR'   # the shape a real export has: a word where a number belongs
        records[1]['金额'] = ''
        bundle = {**BUNDLE, 'sources': {**BUNDLE['sources'], '订单': {'records': records, 'requests': []}}}
        measure = run_query(PROPOSAL, bundle, {**SUM, 'measure': {'field': '订单.金额', 'op': 'average'}})['answer']['measure']
        self.assertEqual((measure['value'], measure['counted'], measure['skipped']), (70, 1, 2))

    def test_a_total_per_group_ranks_by_the_total(self):
        answer = run_query(PROPOSAL, BUNDLE, {**SUM, 'group_by': [BY_CUSTOMER]})['answer']
        self.assertEqual(answer['groups'], [['甲', 100, 1], ['乙', 50, 1]])   # name, total, how many values were read
        self.assertEqual(answer['measure']['field'], '金额')
        self.assertEqual(answer['without_value'], 1)   # O3's customer is not in the customer table

    def test_the_path_says_what_was_added_up(self):
        self.assertEqual(run_query(PROPOSAL, BUNDLE, SUM)['path'], '订单，把“金额”加起来')
        grouped = run_query(PROPOSAL, BUNDLE, {**SUM, 'group_by': [BY_CUSTOMER], 'measure': {'field': '订单.金额', 'op': 'average'}})
        self.assertEqual(grouped['path'], '订单 → 客户，按“名称”分组，算每组“金额”的平均')
        total = run_query(PROPOSAL, BUNDLE, {**SUM, 'group_by': [BY_CUSTOMER]})
        self.assertEqual(total['path'], '订单 → 客户，按“名称”分组，算每组“金额”的合计')

    def test_a_measure_on_a_field_the_start_type_lacks_is_a_gap(self):
        gap = run_query(PROPOSAL, BUNDLE, {**SUM, 'measure': {'field': '客户.城市', 'op': 'sum'}})
        self.assertEqual(gap['status'], 'ontology_gap')

    def test_the_prompt_moves_to_v5_and_describes_the_measure(self):
        self.assertEqual(QUESTION_PROMPT_VERSION, 'company_questions.v7')
        self.assertIn('"measure"', QUESTION_SYSTEM_PROMPT)


# 发票表一行一张发票。客户 A 有三张（5、5、4），授信额度每行都抄一遍；客户从这张表里认出来，所以一个客户有好几行
INVOICES = {
    'schema': 'company_source_bundle.v1', 'decision': '看各客户的发票',
    'file': {'name': 'invoices.csv', 'sha256': 'e' * 64, 'kind': 'table'},
    'sources': {'invoices': {'records': [
        {'invoice_id': 'I1', 'customer_id': 'A', 'amount': '5', 'credit_limit': '100'},
        {'invoice_id': 'I2', 'customer_id': 'A', 'amount': '5', 'credit_limit': '100'},
        {'invoice_id': 'I3', 'customer_id': 'A', 'amount': '4', 'credit_limit': '100'},
        {'invoice_id': 'I4', 'customer_id': 'B', 'amount': '10', 'credit_limit': '50'},
    ], 'requests': []}},
}
CUSTOMER = {'key': 'customer', 'label': '客户', 'populated_from': [{'source': 'invoices', 'identity': {'customer_id': 'customer_id'}}],
            'attributes': [{'source': 'invoices', 'path': 'amount'}, {'source': 'invoices', 'path': 'credit_limit'}]}
INVOICE = {'key': 'invoice', 'label': '发票', 'populated_from': [{'source': 'invoices', 'identity': {'invoice_id': 'invoice_id'}}],
           'attributes': [{'source': 'invoices', 'path': 'amount'}]}
WITH_INVOICE_TYPE = {'object_types': [CUSTOMER, INVOICE], 'ignored_fields': [],
                     'relations': [{'key': 'invoice_customer', 'from': 'invoice', 'to': 'customer', 'source': 'invoices', 'meaning': '发票属于客户'}]}
CUSTOMER_ONLY = {'object_types': [CUSTOMER], 'relations': [], 'ignored_fields': []}
AMOUNT_SUM = {'field': 'invoices.amount', 'op': 'sum'}
LIMIT = {'field': 'invoices.credit_limit', 'op': 'sum'}


class RowsBehindOneObjectTests(unittest.TestCase):
    def test_adding_a_per_row_value_by_an_object_that_owns_several_rows_is_refused_and_names_the_row_level_object(self):
        result = run_query(WITH_INVOICE_TYPE, INVOICES, {'start': 'customer', 'measure': AMOUNT_SUM})
        self.assertEqual(result['status'], 'query_limit')
        self.assertNotIn('answer', result)
        for said in ('一个客户', 'invoices', 'amount', '“发票”', '按客户分组'):
            self.assertIn(said, result['reason'])

    def test_starting_from_the_row_level_object_adds_every_row_and_can_group_by_the_customer(self):
        total = run_query(WITH_INVOICE_TYPE, INVOICES, {'start': 'invoice', 'measure': AMOUNT_SUM})
        self.assertEqual(total['answer']['measure'], {'field': 'amount', 'op': 'sum', 'value': 24, 'counted': 4, 'skipped': 0})
        by_customer = run_query(WITH_INVOICE_TYPE, INVOICES, {'start': 'invoice', 'measure': AMOUNT_SUM,
                                                              'group_by': [{'via': ['invoice_customer'], 'field': 'invoices.customer_id'}]})
        self.assertEqual(by_customer['answer']['groups'], [['A', 14, 3], ['B', 10, 1]])   # 5 + 5 + 4: the repeated 5 is not lost

    def test_rows_that_disagree_are_refused_even_when_no_object_reads_one_row_each(self):
        result = run_query(CUSTOMER_ONLY, INVOICES, {'start': 'customer', 'measure': {**AMOUNT_SUM, 'op': 'average'}})
        self.assertEqual(result['status'], 'query_limit')
        self.assertIn('一个客户', result['reason'])
        self.assertNotIn('请从', result['reason'])   # nothing to start from instead: do not point at an object that is not there

    def test_a_value_copied_on_every_row_of_an_object_counts_once_for_that_object(self):
        answer = run_query(CUSTOMER_ONLY, INVOICES, {'start': 'customer', 'measure': LIMIT})['answer']
        self.assertEqual(answer['measure'], {'field': 'credit_limit', 'op': 'sum', 'value': 150, 'counted': 2, 'skipped': 0})

    def test_a_derived_measure_reads_every_factor_field_the_same_way(self):
        formula = lambda label, field: parse_derived(WITH_INVOICE_TYPE, {'type': 'customer', 'label': label, 'terms': [{'sign': 1, 'factors': [{'field': field}]}]})[0]
        per_row = run_query(WITH_INVOICE_TYPE, INVOICES, {'start': 'customer', 'measure': {'derived': '金额', 'op': 'sum'}}, derived=[formula('金额', 'amount')])
        self.assertEqual(per_row['status'], 'query_limit')
        self.assertIn('“发票”', per_row['reason'])
        limit = formula('授信', 'credit_limit')   # only the customer carries it: a copy on every row, one value per customer
        for ontology in (WITH_INVOICE_TYPE, CUSTOMER_ONLY):
            answered = run_query(ontology, INVOICES, {'start': 'customer', 'measure': {'derived': '授信', 'op': 'sum'}}, derived=[limit])
            self.assertEqual(answered['answer']['measure']['value'], 150)

    def test_an_identity_field_is_one_value_per_object_however_many_rows_it_has(self):
        numbered = {**INVOICES, 'sources': {'invoices': {'records': [{**r, 'customer_id': {'A': '1', 'B': '2'}[r['customer_id']]}
                                                                      for r in INVOICES['sources']['invoices']['records']], 'requests': []}}}
        answer = run_query(WITH_INVOICE_TYPE, numbered, {'start': 'customer', 'measure': {'field': 'invoices.customer_id', 'op': 'sum'}})['answer']
        self.assertEqual((answer['measure']['value'], answer['measure']['counted']), (3, 2))


# C1 两张发票都是 9.90：按客户把行并成一个值是 14.9，真实合计 24.8
SAME_AMOUNTS = {**INVOICES, 'sources': {'invoices': {'records': [
    {'invoice_id': 'I1', 'customer_id': 'C1', 'amount': '9.90', 'credit_limit': '100'},
    {'invoice_id': 'I2', 'customer_id': 'C1', 'amount': '9.90', 'credit_limit': '100'},
    {'invoice_id': 'I3', 'customer_id': 'C2', 'amount': '5.00', 'credit_limit': '50'}], 'requests': []}}}


class RepeatedValuesTests(unittest.TestCase):
    def test_equal_values_on_every_row_are_refused_when_the_row_level_object_carries_the_field(self):
        result = run_query(WITH_INVOICE_TYPE, SAME_AMOUNTS, {'start': 'customer', 'measure': AMOUNT_SUM})
        self.assertEqual(result['status'], 'query_limit')
        for said in ('都一样', '“发票”', '按客户分组'):
            self.assertIn(said, result['reason'])

    def test_a_value_only_the_object_carries_is_a_copy_counted_once_and_the_fold_is_shown_beside_the_answer(self):
        # 授信额度只挂在客户上，发票类型没有这个字段：它是抄在每行上的客户属性，改从发票加反而会加三遍
        result = run_query(WITH_INVOICE_TYPE, INVOICES, {'start': 'customer', 'measure': LIMIT})
        self.assertEqual(result['answer']['measure']['value'], 150)
        self.assertEqual(result['evidence']['folded'], [{'field': 'credit_limit', 'table': 'invoices', 'objects': 1, 'examples': ['A']}])

    def test_one_row_read_twice_by_the_same_object_is_one_row(self):
        party = {'key': 'party', 'label': '往来方', 'attributes': [{'source': 'invoices', 'path': 'amount'}],
                 'populated_from': [{'source': 'invoices', 'identity': {'id': 'customer_id'}}, {'source': 'invoices', 'identity': {'id': 'payer_id'}}]}
        rows = {**INVOICES, 'sources': {'invoices': {'records': [{'invoice_id': 'I1', 'customer_id': 'A', 'payer_id': 'A', 'amount': '5'},
                                                                  {'invoice_id': 'I2', 'customer_id': 'B', 'payer_id': 'B', 'amount': '7'}], 'requests': []}}}
        result = run_query({'object_types': [party, INVOICE], 'relations': [], 'ignored_fields': []}, rows, {'start': 'party', 'measure': AMOUNT_SUM})
        self.assertEqual(result['answer']['measure']['value'], 12)
        self.assertNotIn('evidence', result)

    def test_several_values_inside_one_row_are_refused(self):
        orders = {**INVOICES, 'sources': {'orders': {'records': [{'oid': 'O1', 'lines': [{'qty': '2'}, {'qty': '2'}]},
                                                                  {'oid': 'O2', 'lines': [{'qty': '3'}]}], 'requests': []}}}
        ontology = {'object_types': [{'key': 'order', 'label': '订单', 'populated_from': [{'source': 'orders', 'identity': {'oid': 'oid'}}],
                                      'attributes': [{'source': 'orders', 'path': 'lines[].qty'}]}], 'relations': [], 'ignored_fields': []}
        result = run_query(ontology, orders, {'start': 'order', 'measure': {'field': 'orders.lines[].qty', 'op': 'sum'}})
        self.assertEqual(result['status'], 'query_limit')   # 2 + 2 + 3 is 7; the distinct values give 5
        self.assertIn('一个订单', result['reason'])

    def test_a_row_level_object_a_person_rejected_is_neither_named_nor_a_crash(self):
        limit, _ = parse_derived(WITH_INVOICE_TYPE, {'type': 'customer', 'label': '授信', 'terms': [{'sign': 1, 'factors': [{'field': 'credit_limit'}]}]})
        reviewed = without_wrong(WITH_INVOICE_TYPE, {'types': {'invoice': {'verdict': 'wrong'}}})
        graph = build_graph(WITH_INVOICE_TYPE, INVOICES)   # confirming a formula builds the graph from the ontology before review
        result = run_query(reviewed, INVOICES, {'start': 'customer', 'measure': {'derived': '授信', 'op': 'sum'}}, graph, [limit])
        self.assertEqual(result['answer']['measure']['value'], 150)


if __name__ == '__main__':
    unittest.main()
