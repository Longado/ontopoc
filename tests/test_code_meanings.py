"""Code meanings: a low-cardinality code column (订单.状态码 0/1/2) is found, each value is counted and set against the other
fields, and a model's guess at what a value means is shown only as strong as the data behind it.

Expected numbers come from the planted fixture (tests/fixtures/planted), counted by hand: 状态码 0 in 96 orders, 1 in 48,
2 in 16, and no 交付天数 is empty under any of them."""
import json
import unittest

from ontology_poc_generator.code_meanings import (
    PATTERN_ROWS, check_enum, clean_draft, code_columns, codes_for_label, draft_meanings, meanings_of, merge_enum, shown, shown_codes)
from ontology_poc_generator.recognition import ModelCompletion
from ontology_poc_generator.open_items import _code_meanings
from tests.test_workspace_store import planted_bundle


def table(rows):
    return {'sources': {'单': {'records': rows}}}


def order_rows(cancelled=PATTERN_ROWS, with_days=False):
    """80 orders; the cancelled ones (状态码 2) have no 交付天数 unless with_days."""
    rows = [{'订单号': f'O{i}', '状态码': '0' if i % 2 else '1', '交付天数': '9'} for i in range(80 - cancelled)]
    rows += [{'订单号': f'C{i}', '状态码': '2', '交付天数': '9' if with_days else ''} for i in range(cancelled)]
    return table(rows)


class FindingCodeColumnsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.found = {c['field']: c for c in code_columns(planted_bundle())}

    def test_the_status_code_is_found_with_its_counts(self):
        status = self.found['订单.状态码']
        self.assertEqual((status['rows'], status['id']), (160, 'code_meaning:订单.状态码'))
        self.assertEqual([(v['value'], v['rows']) for v in status['values']], [('0', 96), ('1', 48), ('2', 16)])
        self.assertEqual(status['values'][2]['share'], 0.1)

    def test_candidates_come_from_the_values_alone(self):
        self.assertEqual(set(self.found), {'订单.状态码', '客户.客户等级', '订单承诺.承诺版本', '订单.产品编号', '库存快照.产品编号'})
        self.assertNotIn('售后工单.处理状态', self.found)   # 已关闭 / 处理中 say what they mean
        self.assertNotIn('产品.产品编号', self.found)   # one row per value: a key, not a list of codes
        self.assertNotIn('库存快照.快照月份', self.found)

    def test_columns_that_identify_objects_are_skipped(self):
        found = {c['field'] for c in code_columns(planted_bundle(), frozenset({('订单', '产品编号'), ('库存快照', '产品编号')}))}
        self.assertEqual(found, {'订单.状态码', '客户.客户等级', '订单承诺.承诺版本'})

    def test_in_the_planted_orders_no_value_is_set_apart_from_the_others_by_another_column(self):
        for v in self.found['订单.状态码']['values']:
            self.assertFalse(v['pattern'], v)   # every 交付天数 is filled whatever the code
            self.assertTrue(any('没看出' in f or '太少' in f for f in v['facts']), v['facts'])   # 16 rows of value 2 are under the floor

    def test_a_value_whose_rows_all_lack_a_field_the_others_have_is_a_pattern_and_says_so(self):
        status = code_columns(order_rows())[0]
        two = next(v for v in status['values'] if v['value'] == '2')
        self.assertEqual((two['rows'], two['pattern']), (PATTERN_ROWS, True))
        self.assertTrue(any('交付天数' in f and '全是空' in f for f in two['facts']), two['facts'])
        self.assertFalse(next(v for v in status['values'] if v['value'] == '0')['pattern'])

    def test_a_value_is_set_apart_only_when_the_pattern_holds_for_its_own_rows(self):
        # 20 rows under each of 0 and 1 all have 交付天数; one row under 9 has none. That one row says nothing about 0 or 1.
        rows = [{'订单号': f'O{i}', '状态码': '0' if i % 2 else '1', '交付天数': '9'} for i in range(40)] + [{'订单号': 'X', '状态码': '9', '交付天数': ''}] * 2
        values = {v['value']: v for v in code_columns(table(rows))[0]['values']}
        self.assertEqual({v: values[v]['pattern'] for v in values}, {'0': False, '1': False, '9': False})   # 9 has 2 rows: too few

    def test_a_value_with_too_few_rows_says_so_in_its_facts(self):
        rows = [{'订单号': f'O{i}', '状态码': '1', '交付天数': '9'} for i in range(20)] + [{'订单号': f'C{i}', '状态码': '2', '交付天数': ''} for i in range(PATTERN_ROWS - 1)]
        two = next(v for v in code_columns(table(rows))[0]['values'] if v['value'] == '2')
        self.assertFalse(two['pattern'])   # the rows look set apart, but one row short of the floor
        self.assertTrue(any('全是空' in f and f'只有 {PATTERN_ROWS - 1} 行' in f and '巧合' in f for f in two['facts']), two['facts'])

    def test_a_value_with_few_rows_and_no_difference_says_it_is_too_few(self):
        rows = [{'订单号': f'O{i}', '状态码': '1', '交付天数': '9'} for i in range(60)] + [{'订单号': f'C{i}', '状态码': '2', '交付天数': '9'} for i in range(3)]
        two = next(v for v in code_columns(table(rows))[0]['values'] if v['value'] == '2')
        self.assertTrue(any('只有 3 行' in f and '太少' in f for f in two['facts']), two['facts'])

    def test_years_and_two_value_flags_are_not_code_candidates_but_other_pairs_and_year_lists_with_other_text_are(self):
        def listed(column_values):
            return [c['column'] for c in code_columns(table([{'订单号': f'O{i}', '列': v} for i, v in enumerate(column_values * 10)]))]
        self.assertEqual(listed(['2022', '2023', '2024']), [])
        self.assertEqual(listed(['1999', '2001']), [])
        for pair in (['Y', 'N'], ['yes', 'no'], ['T', 'F'], ['true', 'false'], ['0', '1']):
            self.assertEqual(listed(pair), [], pair)
        self.assertEqual(listed(['Y', 'N', 'M']), ['列'])      # three values: not a yes/no flag
        self.assertEqual(listed(['SH', 'BJ']), ['列'])
        self.assertEqual(listed(['2022', 'A1']), ['列'])        # not all year-shaped
        self.assertEqual(listed(['2122', '2123']), ['列'])      # 4 digits, but not 19xx/20xx

    def test_a_value_with_plenty_of_rows_is_not_called_patternless_when_the_other_values_are_too_few_to_compare_with(self):
        rows = [{'订单号': f'O{i}', '状态码': '1', '交付天数': '9'} for i in range(95)] + [{'订单号': f'C{i}', '状态码': '2', '交付天数': '9'} for i in range(5)]
        one = next(v for v in code_columns(table(rows))[0]['values'] if v['value'] == '1')
        self.assertFalse(any('没有哪一列能把它和其他取值分开' in f for f in one['facts']), one['facts'])
        self.assertTrue(any('其余取值只有 5 行' in f and '太少' in f for f in one['facts']), one['facts'])

    def test_a_column_with_too_many_values_or_one_value_is_not_listed(self):
        many = table([{'订单号': f'O{i}', '状态码': str(i)} for i in range(30)])
        one = table([{'订单号': f'O{i}', '状态码': '1'} for i in range(10)])
        self.assertEqual(code_columns(many) + code_columns(one), [])


class Gateway:
    def __init__(self, reply):
        self.reply, self.requests = reply, []

    def complete_json(self, *, system_prompt, user_prompt):
        self.requests.append(json.loads(user_prompt))
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(self.reply))


class RecommendationTests(unittest.TestCase):
    def reply(self):
        return {'columns': [{'id': 'code_meaning:单.状态码', 'values': [
            {'value': '2', 'label': '已取消', 'description': '客户取消的订单', 'basis': '这些行都没有交付天数'},
            {'value': '0', 'label': '已交付', 'description': '', 'basis': '常见'},
            {'value': '9', 'label': '不存在的值', 'description': '', 'basis': ''}]}]}

    def test_a_recommendation_for_a_value_the_data_does_not_have_is_dropped_with_a_reason(self):
        profiles = code_columns(order_rows())
        out = draft_meanings(profiles, Gateway(self.reply()), '哪些订单被取消了')
        column = out['columns']['code_meaning:单.状态码']
        self.assertEqual(sorted(column), ['0', '2'])
        self.assertEqual(column['2'], {'label': '已取消', 'description': '客户取消的订单', 'basis': '这些行都没有交付天数'})
        self.assertIn('9', out['rejected'][0]['item'])

    def test_the_model_sees_counts_and_what_each_value_is_set_against_but_never_a_row(self):
        gateway = Gateway(self.reply())
        draft_meanings(code_columns(order_rows()), gateway, '哪些订单被取消了')
        sent = json.dumps(gateway.requests[0], ensure_ascii=False)
        self.assertIn('全是空', sent)
        self.assertNotIn('O3', sent)   # no order number: only counts and facts leave the machine

    def test_clean_draft_keeps_only_short_text(self):
        profiles = code_columns(order_rows())
        out = clean_draft(profiles, {'columns': [{'id': 'code_meaning:单.状态码', 'values': [{'value': '2', 'label': 'x' * 41}]}]})
        self.assertEqual(out['columns'], {})
        self.assertEqual(len(out['rejected']), 1)


class ShownTests(unittest.TestCase):
    meanings = {'订单.状态码': {'labels': {'2': '已取消'}}, '客户.客户等级': {'labels': {}}}

    def test_a_confirmed_code_is_shown_with_its_label_and_an_unconfirmed_one_as_unconfirmed(self):
        self.assertEqual(shown(self.meanings, '订单.状态码', '2'), '2 = 已取消')
        self.assertEqual(shown(self.meanings, '订单.状态码', '1'), '1（含义未确认）')
        self.assertEqual(shown(self.meanings, '客户.客户等级', 'A'), 'A（含义未确认）')

    def test_a_field_that_is_not_a_code_and_a_missing_table_are_left_as_written(self):
        self.assertEqual(shown(self.meanings, '订单.金额', '100'), '100')
        self.assertEqual(shown(None, '订单.状态码', '2'), '2')

    def test_a_question_that_says_the_label_stands_for_every_code_with_that_label(self):
        self.assertEqual(codes_for_label(self.meanings, '订单.状态码', '已取消'), ['2'])
        self.assertEqual(codes_for_label(self.meanings, '订单.状态码', '2'), ['2'])
        self.assertEqual(codes_for_label(self.meanings, '订单.状态码', '已作废'), ['已作废'])
        both = {'订单.状态码': {'labels': {'0': '已交付', '1': '已交付', '2': '已取消'}}}
        self.assertEqual(codes_for_label(both, '订单.状态码', '已交付'), ['0', '1'])
        self.assertEqual(shown_codes(both, '订单.状态码', ['0', '1']), '0, 1 = 已交付')


class EnumChecksTests(unittest.TestCase):
    def setUp(self):
        self.column = code_columns(order_rows())[0]

    def test_values_are_kept_with_label_and_description_and_a_blank_label_is_kept_as_a_take_back(self):
        kept = check_enum(self.column, [{'value': '2', 'label': ' 已取消 ', 'description': '客户取消'}, {'value': '0', 'label': ''}])
        self.assertEqual(kept, [{'value': '2', 'label': '已取消', 'description': '客户取消'}, {'value': '0', 'label': '', 'description': ''}])

    def test_an_answer_for_some_values_leaves_the_others_and_a_blank_label_takes_one_back(self):
        on_file = [{'value': v, 'label': l, 'description': ''} for v, l in (('0', '已交付'), ('1', '生产中'), ('2', '已取消'))]
        merged = merge_enum(on_file, check_enum(self.column, [{'value': '0', 'label': '完成'}, {'value': '1', 'label': ''}]))
        self.assertEqual([(e['value'], e['label']) for e in merged], [('0', '完成'), ('2', '已取消')])

    def test_a_value_the_column_does_not_have_or_a_label_that_is_too_long_is_refused(self):
        with self.assertRaises(ValueError):
            check_enum(self.column, [{'value': '7', 'label': '其他'}])
        with self.assertRaises(ValueError):
            check_enum(self.column, [{'value': '2', 'label': 'x' * 41}])

    def test_an_empty_answer_is_refused(self):
        with self.assertRaises(ValueError):
            check_enum(self.column, [])

    def test_meanings_of_reads_the_stored_enums_per_field(self):
        profiles = code_columns(order_rows())
        enums = {'单.状态码': {'values': [{'value': '2', 'label': '已取消', 'description': ''}]}}
        self.assertEqual(meanings_of(profiles, enums), {'单.状态码': {'labels': {'2': '已取消'}}})


DRAFT = {'code_meaning:单.状态码': {'2': {'label': '已取消', 'description': '客户取消的订单', 'basis': '这些行都没有交付天数'},
                                    '0': {'label': '已交付', 'description': '', 'basis': '数据里没看出规律'}}}


class OpenItemTests(unittest.TestCase):
    def item(self, bundle, enums=None, drafts=None):
        items = _code_meanings({'profiles': code_columns(bundle), 'enums': enums or {}, 'drafts': drafts or {}})
        return items[0] if items else None

    def values(self, item):
        return {v['value']: v for v in item['column']['values']}

    def test_a_code_column_nobody_confirmed_is_one_open_item_with_counts_and_the_evidence_per_value(self):
        status = next(i for i in _code_meanings({'profiles': code_columns(planted_bundle()), 'enums': {}, 'drafts': {}}) if i['id'] == 'code_meaning:订单.状态码')
        self.assertEqual((status['kind'], status['id'], status['target']), ('code_meaning', 'code_meaning:订单.状态码', {'tab': 'data', 'table': '订单'}))
        self.assertIn('订单', status['ask'])
        self.assertIn('状态码', status['ask'])
        two = {v['value']: v for v in status['column']['values']}['2']
        self.assertEqual(two['rows'], 16)
        self.assertEqual(two['facts'][0], '16 行，占 10%')
        self.assertTrue(any('只有 16 行，太少' in f for f in two['facts']))   # under the floor, so not "no pattern" but "too few to tell"

    def test_a_guess_the_data_supports_is_preselected_and_one_it_does_not_is_shown_but_not_selected(self):
        values = self.values(self.item(order_rows(), drafts=DRAFT))
        self.assertEqual((values['2']['recommendation']['label'], values['2']['recommendation']['strong'], values['2']['preselected']), ('已取消', True, True))
        self.assertEqual((values['0']['recommendation']['label'], values['0']['recommendation']['strong'], values['0']['preselected']), ('已交付', False, False))
        self.assertIsNone(values['1']['recommendation'])

    def test_in_the_planted_orders_every_guess_is_weak_and_none_is_preselected(self):
        draft = {'code_meaning:订单.状态码': {v: {'label': l, 'description': '', 'basis': 'b'} for v, l in (('0', '已交付'), ('1', '生产中'), ('2', '已取消'))}}
        items = _code_meanings({'profiles': code_columns(planted_bundle()), 'enums': {}, 'drafts': draft})
        status = next(i for i in items if i['id'] == 'code_meaning:订单.状态码')
        self.assertEqual([(v['recommendation']['strong'], v['preselected'], v['recommendation']['why_weak']) for v in status['column']['values']],
                         [(False, False, 'no_pattern'), (False, False, 'no_pattern'), (False, False, 'few_rows')])   # 96 and 48 rows: nothing sets them apart; 16 is under the floor

    def test_a_value_is_weak_for_few_rows_when_the_rest_of_the_column_is_the_thin_side(self):
        rows = [{'订单号': f'O{i}', '状态码': '1', '交付天数': '9'} for i in range(95)] + [{'订单号': f'C{i}', '状态码': '2', '交付天数': '9'} for i in range(5)]
        item = self.item(table(rows), drafts={'code_meaning:单.状态码': {'1': {'label': '已交付', 'description': '', 'basis': 'b'}}})
        self.assertEqual((self.values(item)['1']['recommendation']['why_weak'], self.values(item)['1']['preselected']), ('few_rows', False))

    def test_a_pattern_in_too_few_rows_is_still_weak(self):
        thin = table([{'订单号': f'O{i}', '状态码': '1', '交付天数': '9'} for i in range(20)] + [{'订单号': f'C{i}', '状态码': '2', '交付天数': ''} for i in range(PATTERN_ROWS - 1)])
        item = self.item(thin, drafts={'code_meaning:单.状态码': {'2': {'label': '已取消', 'description': '', 'basis': 'b'}}})
        self.assertEqual((self.values(item)['2']['recommendation']['strong'], self.values(item)['2']['preselected'], self.values(item)['2']['recommendation']['why_weak']), (False, False, 'few_rows'))

    def test_the_item_closes_when_every_value_has_a_confirmed_meaning_and_stays_open_for_the_rest(self):
        labels = lambda *pairs: {'单.状态码': {'values': [{'value': v, 'label': l, 'description': ''} for v, l in pairs]}}
        self.assertIsNone(self.item(order_rows(), enums=labels(('0', '已交付'), ('1', '生产中'), ('2', '已取消'))))
        partial = self.item(order_rows(), enums=labels(('2', '已取消')))
        values = self.values(partial)
        self.assertEqual(values['2']['confirmed']['label'], '已取消')
        self.assertIsNone(values['0']['confirmed'])

    def test_a_value_that_shows_up_after_the_meanings_were_confirmed_reopens_the_item(self):
        enums = {'单.状态码': {'values': [{'value': v, 'label': 'x', 'description': ''} for v in ('0', '1')]}}
        item = self.item(order_rows(), enums=enums)   # 2 is in the data, not in what was confirmed
        self.assertEqual([v['value'] for v in item['column']['values'] if v['confirmed'] is None], ['2'])


ORDERS = {'object_types': [{'key': 'order', 'label': '订单', 'populated_from': [{'source': '订单', 'identity': {'order_id': '订单号'}}],
                            'attributes': [{'source': '订单', 'path': '状态码'}, {'source': '订单', 'path': '金额'}]}],
          'relations': [], 'ignored_fields': [], 'open_questions': []}


def with_meanings(bundle, *pairs):
    enums = {'订单.状态码': {'values': [{'value': v, 'label': l, 'description': ''} for v, l in pairs]}}
    return {**bundle, 'meanings': meanings_of(code_columns(bundle), enums)}


class WhereCodesAreShownTests(unittest.TestCase):
    def test_a_question_that_says_the_confirmed_meaning_has_not_had_its_condition_added_by_the_model(self):
        from ontology_poc_generator.ontology_questions import answer_query
        bundle = with_meanings(planted_bundle(), ('2', '已取消'))
        for equals in ('已取消', '2'):   # the model wrote the meaning or the code: either way the question said 已取消
            query = {'start': 'order', 'where': [{'field': '订单.状态码', 'equals': equals}]}
            [said] = answer_query(ORDERS, bundle, query, '有多少订单已取消？')['evidence']['filters']
            self.assertEqual((said['equals'], said['labels']), ('2', ['已取消']))
            self.assertNotIn('not_in_question', said, equals)
        [added] = answer_query(ORDERS, bundle, {'start': 'order', 'where': [{'field': '订单.状态码', 'equals': '2'}]}, '一共有多少订单？')['evidence']['filters']
        self.assertTrue(added['not_in_question'])    # a question that says neither the code nor its meaning still gets the warning
        [unconfirmed] = answer_query(ORDERS, planted_bundle(), {'start': 'order', 'where': [{'field': '订单.状态码', 'equals': '2'}]}, '有多少订单已取消？')['evidence']['filters']
        self.assertTrue(unconfirmed['not_in_question'])    # no confirmed meaning: nothing says 已取消 is 2

    def test_a_label_two_codes_share_filters_by_both_and_the_path_lists_them(self):
        from ontology_poc_generator.ontology_questions import run_query
        bundle = with_meanings(planted_bundle(), ('0', '已交付'), ('1', '已交付'), ('2', '已取消'))
        both = run_query(ORDERS, bundle, {'start': 'order', 'where': [{'field': '订单.状态码', 'equals': '已交付'}]})
        self.assertEqual(both['answer'], {'total': 144})   # 96 + 48
        self.assertIn('0, 1 = 已交付', both['path'])
        share = run_query(ORDERS, bundle, {'start': 'order', 'share': {'field': '订单.状态码', 'equals': '已交付'}})
        self.assertEqual(share['answer']['matched'], 144)


    @classmethod
    def setUpClass(cls):
        cls.bundle = planted_bundle()

    def test_the_object_list_shows_a_confirmed_code_with_its_label_and_the_rest_as_unconfirmed(self):
        from ontology_poc_generator.object_rows import object_rows
        page = object_rows(ORDERS, with_meanings(self.bundle, ('2', '已取消')), 'order', size=None)
        shown = {r['状态码'] for r in page['rows']}
        self.assertEqual(shown, {'0（含义未确认）', '1（含义未确认）', '2 = 已取消'})
        self.assertEqual(sum(r['状态码'] == '2 = 已取消' for r in page['rows']), 16)

    def test_without_meanings_the_object_list_is_as_before(self):
        from ontology_poc_generator.object_rows import object_rows
        page = object_rows(ORDERS, self.bundle, 'order', size=None)
        self.assertEqual({r['状态码'] for r in page['rows']}, {'0', '1', '2'})

    def test_an_object_page_shows_the_label_too(self):
        from ontology_poc_generator.object_rows import neighbourhood
        bundle = with_meanings(self.bundle, ('0', '已交付'), ('1', '生产中'), ('2', '已取消'))
        first = bundle['sources']['订单']['records'][0]
        page = neighbourhood(ORDERS, bundle, 'order:' + first['订单号'])
        self.assertEqual(page['center']['fields']['状态码'], f"{first['状态码']} = " + {'0': '已交付', '1': '生产中', '2': '已取消'}[first['状态码']])

    def test_a_grouped_answer_names_the_code_by_its_label_and_a_question_in_labels_filters_by_code(self):
        from ontology_poc_generator.ontology_questions import run_query
        bundle = with_meanings(self.bundle, ('0', '已交付'), ('1', '生产中'), ('2', '已取消'))
        grouped = run_query(ORDERS, bundle, {'start': 'order', 'group_by': [{'via': [], 'field': '订单.状态码'}]})
        self.assertEqual(grouped['answer']['groups'], [['0 = 已交付', 96], ['1 = 生产中', 48], ['2 = 已取消', 16]])
        by_label = run_query(ORDERS, bundle, {'start': 'order', 'where': [{'field': '订单.状态码', 'equals': '已取消'}]})
        self.assertEqual(by_label['answer'], {'total': 16})
        self.assertIn('2 = 已取消', by_label['path'])

    def test_unconfirmed_codes_are_marked_in_a_grouped_answer(self):
        from ontology_poc_generator.ontology_questions import run_query
        grouped = run_query(ORDERS, with_meanings(self.bundle, ('2', '已取消')), {'start': 'order', 'group_by': [{'via': [], 'field': '订单.状态码'}]})
        self.assertEqual(grouped['answer']['groups'], [['0（含义未确认）', 96], ['1（含义未确认）', 48], ['2 = 已取消', 16]])

    def test_the_question_writer_is_told_what_each_confirmed_code_means(self):
        from ontology_poc_generator.ontology_questions import _catalog
        bundle = with_meanings(self.bundle, ('2', '已取消'))
        status = next(a for t in _catalog(ORDERS, bundle)['object_types'] for a in t['attributes'] if a['path'] == '状态码')
        self.assertEqual(status['values'], ['0', '1', '2'])
        self.assertEqual(status['meanings'], {'2': '已取消'})


class CodeModel:
    """The table modeller (planted draft), the code describer (a guess for each status code) and the question writer."""
    def __init__(self):
        from ontology_poc_generator.code_meanings import DESCRIBE_CODES_SYSTEM_PROMPT
        from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
        from tests.test_workspace_store import PLANTED_DRAFT
        self.codes, self.questions, self.draft, self.asked = DESCRIBE_CODES_SYSTEM_PROMPT, QUESTION_SYSTEM_PROMPT, PLANTED_DRAFT, []

    def complete_json(self, *, system_prompt, user_prompt):
        if system_prompt == self.codes:
            reply = {'columns': [{'id': 'code_meaning:订单.状态码', 'values': [
                {'value': '2', 'label': '已取消', 'description': '客户取消的订单', 'basis': '数据里没看出规律'},
                {'value': '0', 'label': '已交付', 'description': '', 'basis': '数据里没看出规律'}]}]}
        elif system_prompt == self.questions:
            self.asked.append(json.loads(user_prompt))
            reply = {'questions': [{'question': '各状态的订单有多少？', 'reasoning': 'r',
                                    'query': {'start': 'order', 'group_by': [{'via': [], 'field': '订单.状态码'}]}}]}
        else:
            reply = self.draft
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(reply, ensure_ascii=False))


class CancelledQuestionModel(CodeModel):
    """Writes the upload's question in the words a person would: the meaning, not the code (or the code, `equals='2'`)."""
    equals = '已取消'

    def complete_json(self, *, system_prompt, user_prompt):
        if system_prompt == self.questions:
            reply = {'questions': [{'question': '有多少订单已取消？', 'reasoning': 'r',
                                    'query': {'start': 'order', 'where': [{'field': '订单.状态码', 'equals': self.equals}], 'group_by': None}}]}
            return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(reply, ensure_ascii=False))
        return super().complete_json(system_prompt=system_prompt, user_prompt=user_prompt)


class AnswersFollowWhatIsConfirmedTests(unittest.TestCase):
    """The answer written at upload, before anyone said what 2 means, is worked out again when they do."""
    def setUp(self):
        from tests.test_ontology_ask_server import call
        from tests.test_ontology_server import OntologyServerTests
        from tests.test_workspace_store import ServerDataChecksTests
        server = OntologyServerTests().server(gateway=CancelledQuestionModel())
        self.base, self.out = server.__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        self.call = call
        status, self.run = call(self.base, '/api/ontology/build', {'files': ServerDataChecksTests.files, 'purpose': '有多少订单已取消？'})
        self.assertEqual(status, 200, self.run)

    def saved(self):
        from urllib.request import urlopen
        with urlopen(self.base + f"/api/ontology/runs/{self.run['saved_as']}", timeout=30) as response:
            return json.load(response)

    def test_the_upload_time_answer_is_replaced_with_what_it_was_and_why(self):
        [before] = self.saved()['evaluation']['asked'][0]['items']
        self.assertEqual((before['status'], before.get('reason')), ('no_data', '数据里没有满足筛选条件的对象'))
        self.assertNotIn('rerun', before)
        status, _ = self.call(self.base, '/api/ontology/code-meanings', {'saved_as': self.run['saved_as'], 'id': 'code_meaning:订单.状态码',
                                                                         'values': [{'value': '2', 'label': '已取消'}], 'confirmed_by': '王工'})
        self.assertEqual(status, 200)
        run = self.saved()
        [after] = run['evaluation']['asked'][0]['items']
        self.assertEqual((after['status'], after['answer']), ('answered', {'total': 16}))
        self.assertEqual(run['evaluation']['asked'][0]['answered'], 1)
        self.assertEqual(after['rerun'], {'because': ['「状态码」的含义已确认（2 = 已取消）'], 'was': {'status': 'no_data', 'reason': '数据里没有满足筛选条件的对象'}})
        self.assertEqual(after['question'], '有多少订单已取消？')
        self.assertNotIn('not_in_question', after['evidence']['filters'][0])    # the question said 已取消

    def post(self, values):
        return self.call(self.base, '/api/ontology/code-meanings', {'saved_as': self.run['saved_as'], 'id': 'code_meaning:订单.状态码', 'values': values, 'confirmed_by': '王工'})

    def item(self):
        [item] = self.saved()['evaluation']['asked'][0]['items']
        return item

    def test_taking_the_meaning_back_returns_the_answer_to_what_it_first_said_and_the_line_goes(self):
        self.post([{'value': '2', 'label': '已取消'}])
        self.assertEqual(self.item()['status'], 'answered')
        self.post([{'value': '2', 'label': ''}])
        item = self.item()
        self.assertEqual((item['status'], item['reason']), ('no_data', '数据里没有满足筛选条件的对象'))
        self.assertNotIn('rerun', item)       # it says what it said before anyone confirmed anything: nothing to announce

    def test_the_line_says_what_was_confirmed_and_what_was_taken_back(self):
        self.post([{'value': '1', 'label': '生产中'}])
        status, _ = self.post([{'value': '2', 'label': '已取消'}, {'value': '1', 'label': ''}])
        self.assertEqual(status, 200)
        self.assertEqual(self.item()['rerun']['because'], ['「状态码」的含义已确认（2 = 已取消），已收回（1）'])

    def test_a_blank_for_a_value_never_confirmed_is_not_a_withdrawal(self):
        self.post([{'value': '0', 'label': ''}, {'value': '1', 'label': ''}, {'value': '2', 'label': '已取消'}])    # what the form posts: every value
        self.assertEqual(self.item()['rerun']['because'], ['「状态码」的含义已确认（2 = 已取消）'])

    def test_a_question_written_with_the_code_has_the_same_number_and_no_line_about_a_change(self):
        CancelledQuestionModel.equals = '2'
        self.addCleanup(setattr, CancelledQuestionModel, 'equals', '已取消')
        self.setUp()    # a run built with the question in codes
        self.assertEqual(self.item()['answer'], {'total': 16})
        self.post([{'value': '2', 'label': '已取消'}])
        item = self.item()
        self.assertEqual(item['answer'], {'total': 16})
        self.assertNotIn('rerun', item)
        self.assertEqual(item['evidence']['filters'][0]['labels'], ['已取消'])     # only the evidence gained the meaning

    def test_a_file_uploaded_again_after_the_meaning_was_confirmed_is_answered_with_it(self):
        from tests.test_workspace_store import ServerDataChecksTests
        self.post([{'value': '2', 'label': '已取消'}])
        status, again = self.call(self.base, '/api/ontology/build', {'files': ServerDataChecksTests.files, 'purpose': '有多少订单已取消？'})
        self.assertEqual(status, 200, again)
        [item] = again['evaluation']['asked'][0]['items']
        self.assertEqual((item['status'], item['answer']), ('answered', {'total': 16}))
        self.assertNotIn('rerun', item)       # asked with the meaning from the start

    def test_a_failure_after_the_meaning_was_saved_is_a_warning_not_a_failed_save(self):
        from unittest import mock
        from ontology_poc_generator import ontology_server
        with mock.patch.object(ontology_server, 'answer_query', side_effect=RuntimeError('boom')):
            status, body = self.post([{'value': '2', 'label': '已取消'}])
        self.assertEqual(status, 200)
        self.assertIn('已保存，但这次运行里已有的答案没能按它重算', body['warning'])
        self.assertEqual(body['meanings']['订单.状态码']['labels'], {'2': '已取消'})       # what was said is kept

    def test_many_saves_at_once_and_readers_of_the_run_never_fail_or_see_half_a_file(self):
        import threading
        from urllib.request import urlopen
        failed = []

        def save(i):
            for k in range(3):
                status, body = self.post([{'value': '2', 'label': '已取消' if (i + k) % 2 else ''}])
                if status != 200 or body.get('warning'):
                    failed.append(('save', status, body.get('error') or body.get('warning')))

        def read():
            for _ in range(30):
                try:
                    with urlopen(self.base + f"/api/ontology/runs/{self.run['saved_as']}", timeout=30) as response:
                        json.load(response)
                except Exception as exc:
                    failed.append(('read', repr(exc)))
        threads = [threading.Thread(target=save, args=(i,)) for i in range(8)] + [threading.Thread(target=read) for _ in range(3)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(failed, [])

    def test_an_answer_that_comes_out_the_same_is_left_alone(self):
        self.call(self.base, '/api/ontology/code-meanings', {'saved_as': self.run['saved_as'], 'id': 'code_meaning:客户.客户等级', 'values': [{'value': 'A', 'label': '大客户'}]})
        [item] = self.saved()['evaluation']['asked'][0]['items']
        self.assertEqual(item['status'], 'no_data')
        self.assertNotIn('rerun', item)


class ServerCodeMeaningsTests(unittest.TestCase):
    def setUp(self):
        from tests.test_ontology_ask_server import call
        from tests.test_ontology_server import OntologyServerTests
        from tests.test_workspace_store import ServerDataChecksTests
        self.call, self.files = call, ServerDataChecksTests.files
        self.model = CodeModel()
        server = OntologyServerTests().server(gateway=self.model)
        self.base, self.out = server.__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        status, self.run = call(self.base, '/api/ontology/build', {'files': self.files})
        self.assertEqual(status, 200, self.run)

    def get(self, path):
        from urllib.request import urlopen
        with urlopen(self.base + f"/api/ontology/runs/{self.run['saved_as']}/{path}", timeout=30) as response:
            return json.load(response)

    def status_item(self):
        return next((i for i in self.get('open-items')['items'] if i['id'] == 'code_meaning:订单.状态码'), None)

    def save(self, values, by='王工', item='code_meaning:订单.状态码'):
        return self.call(self.base, '/api/ontology/code-meanings', {'saved_as': self.run['saved_as'], 'id': item, 'values': values, 'confirmed_by': by})

    def order_statuses(self):
        return {r['状态码'] for r in self.get('objects/order?all=1')['rows']}

    def test_the_status_code_is_an_open_item_with_its_counts_and_the_object_list_marks_the_codes_unconfirmed(self):
        item = self.status_item()
        self.assertEqual([(v['value'], v['rows']) for v in item['column']['values']], [('0', 96), ('1', 48), ('2', 16)])
        self.assertEqual({i['id'] for i in self.get('open-items')['items'] if i['kind'] == 'code_meaning'},
                         {'code_meaning:订单.状态码', 'code_meaning:客户.客户等级', 'code_meaning:订单承诺.承诺版本'})   # the identity columns are keys, not candidates
        self.assertEqual(self.order_statuses(), {'0（含义未确认）', '1（含义未确认）', '2（含义未确认）'})

    def test_the_models_guess_comes_back_with_the_item_but_the_planted_data_gives_it_no_support_so_nothing_is_selected(self):
        status, body = self.call(self.base, '/api/ontology/code-meanings/draft', {'saved_as': self.run['saved_as']})
        self.assertEqual(status, 200, body)
        values = {v['value']: v for v in next(i for i in body['items'] if i['id'] == 'code_meaning:订单.状态码')['column']['values']}
        self.assertEqual((values['2']['recommendation']['label'], values['2']['recommendation']['strong'], values['2']['preselected']), ('已取消', False, False))
        self.assertIsNone(values['1']['recommendation'])
        self.assertEqual(self.status_item()['column']['values'][2]['recommendation']['label'], '已取消')   # kept with the file

    def test_confirming_stores_the_enum_on_the_property_and_the_object_list_then_reads_the_label(self):
        status, body = self.save([{'value': '0', 'label': '已交付'}, {'value': '1', 'label': '生产中'},
                                  {'value': '2', 'label': '已取消', 'description': '客户取消，不再交付'}])
        self.assertEqual(status, 200, body)
        self.assertNotIn('code_meaning:订单.状态码', {i['id'] for i in body['items']})
        from ontology_poc_generator.workspace_store import element_contents, open_workspace
        conn = open_workspace(self.out / 'workspace.sqlite')
        self.addCleanup(conn.close)
        row = conn.execute("SELECT state, evidence_ref, confirmed_by, version FROM element_state WHERE element_id = ?",
                           (f"property:{self.run['file']['sha256']}:订单.状态码",)).fetchone()
        self.assertEqual(row, ('confirmed', 'open_item:code_meaning:订单.状态码', '王工', 1))
        stored = element_contents(conn, f"property:{self.run['file']['sha256']}:")['订单.状态码']
        self.assertEqual(stored['values'][2], {'value': '2', 'label': '已取消', 'description': '客户取消，不再交付'})
        self.assertEqual(self.order_statuses(), {'0 = 已交付', '1 = 生产中', '2 = 已取消'})

    def test_an_answer_for_one_value_leaves_what_was_confirmed_for_the_others(self):
        self.save([{'value': '0', 'label': '已交付'}, {'value': '1', 'label': '生产中'}, {'value': '2', 'label': '已取消'}])
        self.save([{'value': '0', 'label': '完成'}])
        self.assertEqual(self.order_statuses(), {'0 = 完成', '1 = 生产中', '2 = 已取消'})
        status, _ = self.save([{'value': '0', 'label': ''}, {'value': '1', 'label': ''}, {'value': '2', 'label': ''}])   # every meaning taken back
        self.assertEqual(status, 200)
        self.assertEqual(self.order_statuses(), {'0（含义未确认）', '1（含义未确认）', '2（含义未确认）'})
        self.assertIsNotNone(self.status_item())

    def test_a_person_can_say_a_candidate_is_not_a_code_and_it_does_not_come_back(self):
        status, body = self.call(self.base, '/api/ontology/code-meanings/dismiss', {'saved_as': self.run['saved_as'], 'id': 'code_meaning:订单承诺.承诺版本', 'confirmed_by': '王工'})
        self.assertEqual(status, 200, body)
        self.assertNotIn('code_meaning:订单承诺.承诺版本', {i['id'] for i in body['items']})
        self.assertNotIn('订单承诺.承诺版本', body['meanings'])
        _, again = self.call(self.base, '/api/ontology/build', {'files': self.files})   # the same files again
        with __import__('urllib.request').request.urlopen(self.base + f"/api/ontology/runs/{again['saved_as']}/open-items", timeout=30) as response:
            self.assertNotIn('code_meaning:订单承诺.承诺版本', {i['id'] for i in json.load(response)['items']})
        from ontology_poc_generator.workspace_store import open_workspace
        conn = open_workspace(self.out / 'workspace.sqlite')
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute("SELECT state, confirmed_by FROM element_state WHERE element_id LIKE '%订单承诺.承诺版本'").fetchone(), ('rejected', '王工'))

    def test_the_open_item_list_carries_the_meanings_for_the_page_to_show_beside_answers_and_fields(self):
        self.save([{'value': '2', 'label': '已取消'}])
        meanings = self.get('open-items')['meanings']
        self.assertEqual(meanings['订单.状态码'], {'labels': {'2': '已取消'}})
        self.assertEqual(meanings['客户.客户等级'], {'labels': {}})

    def test_the_code_columns_are_worked_out_once_per_run_however_many_times_the_lists_are_read(self):
        from unittest import mock
        import ontology_poc_generator.ontology_server as server
        with mock.patch.object(server, 'code_columns', wraps=server.code_columns) as counted:
            for _ in range(3):
                self.get('open-items')
            self.save([{'value': '2', 'label': '已取消'}])
            self.get('objects/order?all=1')
            self.assertEqual(counted.call_count, 1)

    def test_a_value_left_unlabelled_keeps_its_item_open_and_stays_marked_unconfirmed(self):
        self.save([{'value': '2', 'label': '已取消'}])
        item = self.status_item()
        self.assertEqual({v['value']: bool(v['confirmed']) for v in item['column']['values']}, {'0': False, '1': False, '2': True})
        self.assertEqual(self.order_statuses(), {'0（含义未确认）', '1（含义未确认）', '2 = 已取消'})

    def test_the_question_box_uses_the_label_both_ways(self):
        self.save([{'value': '0', 'label': '已交付'}, {'value': '1', 'label': '生产中'}, {'value': '2', 'label': '已取消'}])
        status, run = self.call(self.base, '/api/ontology/ask', {'saved_as': self.run['saved_as'], 'question': '各状态的订单有多少？'})
        self.assertEqual(status, 200, run)
        answer = run['evaluation']['asked'][-1]['items'][0]
        self.assertEqual(answer['answer']['groups'], [['0 = 已交付', 96], ['1 = 生产中', 48], ['2 = 已取消', 16]])
        catalog = self.model.asked[-1]['ontology']['object_types']
        status_field = next(a for t in catalog for a in t['attributes'] if a['path'] == '状态码')
        self.assertEqual(status_field['meanings'], {'0': '已交付', '1': '生产中', '2': '已取消'})

    def test_the_same_files_uploaded_again_keep_the_meanings(self):
        self.save([{'value': '2', 'label': '已取消'}])
        _, again = self.call(self.base, '/api/ontology/build', {'files': self.files})
        from urllib.request import urlopen
        with urlopen(self.base + f"/api/ontology/runs/{again['saved_as']}/objects/order?all=1", timeout=30) as response:
            self.assertIn('2 = 已取消', {r['状态码'] for r in json.load(response)['rows']})

    def test_a_column_that_is_not_there_or_a_label_that_is_too_long_is_refused_and_nothing_is_kept(self):
        self.assertEqual(self.save([{'value': '2', 'label': '已取消'}], item='code_meaning:订单.没有这列')[0], 400)
        self.assertEqual(self.save([{'value': '2', 'label': 'x' * 41}])[0], 400)
        self.assertEqual(self.save([{'value': '9', 'label': '其他'}])[0], 400)
        self.assertEqual(self.order_statuses(), {'0（含义未确认）', '1（含义未确认）', '2（含义未确认）'})


if __name__ == '__main__':
    unittest.main()
