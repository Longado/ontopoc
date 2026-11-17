"""The sentences the service writes for questions, queries, pipelines, derived values and AI come in the asker's language: Chinese by default, English when the
request asked for it (lang.use('en')). Each test checks one module with real input, in English, and that the Chinese is unchanged without the switch."""
import json
import unittest
from datetime import datetime, timezone

from ontology_poc_generator import lang, ontology_questions, ontopoc_query   # ontology_questions hands ontopoc_query the language switch
from ontology_poc_generator.caliber import _kind_word, _state_word
from ontology_poc_generator.derived_measures import parse_derived
from ontology_poc_generator.derived_properties import KINDS, OPS, STAT_FNS, TYPE_WORD, _reset_labels, _routing_hint
from ontology_poc_generator.pipeline_assist import _in_language
from ontology_poc_generator.pipeline_expr import compile_expression
from ontology_poc_generator.pipeline_llm import check_llm_step
from ontology_poc_generator.pipeline_ops import AGGREGATIONS, CAST_TYPES, CATALOG
from ontology_poc_generator.pipelines import check_pipeline
from ontology_poc_generator.workspace_questions import ENGLISH_NOTE, QaRefused, _kind_word as question_kind_word, _state_words, run_text
from ontology_poc_generator.workspace_schedules import cadence_text
from ontology_poc_generator.workspace_store import open_workspace

CATALOG_OF_TYPES = {'types': {'o': {'name': '订单', 'label': '订单', 'properties': ['金额']}}, 'relations': {}}


class EnglishDataTest(unittest.TestCase):
    def tearDown(self):
        lang.use('zh')

    def test_a_query_that_cannot_be_read_says_so_in_english_and_in_chinese_without_the_switch(self):
        text = 'SELECT count(o) FROM (o:订单) WHERE o.金额 LIKE 1'
        with self.assertRaises(ontopoc_query.QueryError) as zh:
            ontopoc_query.parse(text)
        lang.use('en')
        with self.assertRaises(ontopoc_query.QueryError) as en:
            ontopoc_query.parse(text)
        self.assertIn('fuzzy matching', str(en.exception))
        self.assertIn('模糊匹配', str(zh.exception))
        with self.assertRaises(ontopoc_query.QueryError) as empty:
            ontopoc_query.parse('')
        self.assertEqual(str(empty.exception), 'Write a query, for example SELECT count(o) FROM (o:orders)')

    def test_a_query_naming_a_type_that_does_not_exist_lists_the_types_in_english(self):
        lang.use('en')
        with self.assertRaises(ontopoc_query.QueryError) as caught:
            ontopoc_query.compile_query('SELECT count(x) FROM (x:客户)', CATALOG_OF_TYPES)
        self.assertEqual(str(caught.exception), 'There is no object type "客户". Object types you can query: 订单')

    def test_the_questions_engine_names_what_the_query_cannot_say_in_english(self):
        lang.use('en')
        self.assertEqual(ontology_questions._shape_limit({'start': 'order', 'foo': 1}),
                         'This question uses foo, which the query format cannot express yet')
        self.assertEqual(ontology_questions.range_text('amount', {'more_than': 1, 'at_most': 5}), 'amount > 1 and <= 5')
        self.assertTrue(ontology_questions._condition_limit({'field': 'x', 'more_than': 5, 'less_than': 2}, True).startswith('The lower bound 5 is not below the upper bound 2'))
        lang.use('zh')
        self.assertEqual(ontology_questions.range_text('金额', {'more_than': 1, 'at_most': 5}), '金额 > 1 且 <= 5')

    def test_the_words_for_a_definition_come_in_english_for_the_refusal_and_the_caliber(self):
        lang.use('en')
        self.assertEqual((_kind_word('meaning'), _state_word('needs_look')), ('Meaning', 'Needs another look'))
        self.assertEqual((question_kind_word('derived'), _state_words('rejected')), ('Derived property', 'Sent back'))
        lang.use('zh')
        self.assertEqual((_kind_word('meaning'), question_kind_word('derived'), _state_words('proposed')), ('含义', '派生属性', '模型提出了，还没有人确认'))

    def test_an_empty_question_is_refused_in_english(self):
        lang.use('en')
        with self.assertRaises(QaRefused) as caught:
            run_text(open_workspace(':memory:'), None, '')
        self.assertEqual(str(caught.exception), 'Write a query, for example SELECT count(o) FROM (o:orders)')

    def test_a_derived_measure_that_does_not_parse_says_why_in_english(self):
        from tests.test_derived_measures import ONTOLOGY as ontology
        lang.use('en')
        formula, why = parse_derived(ontology, {'type': 'nothing', 'label': 'x', 'terms': []})
        self.assertEqual((formula, why), (None, 'There is no object nothing in the ontology'))
        self.assertEqual(parse_derived(ontology, 'no')[1], 'A measure must be written as {type, label, terms}')

    def test_the_word_tables_of_a_derived_property_read_in_the_asking_language(self):
        lang.use('en')
        self.assertEqual((KINDS['statistic'], OPS['is_not'], STAT_FNS['latest'], TYPE_WORD['datetime']), ('Statistic', 'is not', 'Latest', 'date and time'))
        self.assertEqual(STAT_FNS['sum'], 'Sum')
        self.assertEqual(dict(_reset_labels())['fn'], 'Calculation')
        self.assertTrue(_routing_hint().startswith('For a value worked out only from the object'))
        lang.use('zh')
        self.assertEqual((KINDS['statistic'], OPS['is_not'], STAT_FNS['latest'], AGGREGATIONS['sum']), ('统计', '不是', '取最新', '求和'))
        self.assertEqual(dict(_reset_labels())['fn'], '统计方式')

    def test_pipeline_words_the_picker_lists_are_english(self):
        lang.use('en')
        self.assertEqual([name for _, name, _, _ in CATALOG][:3], ['Filter', 'Fill empty values', 'Clean text'])
        self.assertEqual((AGGREGATIONS['count_distinct'], CAST_TYPES['boolean']), ('Count distinct', 'Yes/no'))
        self.assertEqual(AGGREGATIONS.items()[0], ('sum', 'Sum'))
        lang.use('zh')
        self.assertEqual([name for _, name, _, _ in CATALOG][:2], ['数据过滤', '空值替换'])

    def test_a_step_the_pipeline_cannot_check_says_so_in_english(self):
        lang.use('en')
        with self.assertRaises(ValueError) as caught:
            check_pipeline({'steps': []}, {})
        self.assertEqual(str(caught.exception), 'A pipeline needs steps: a list of steps written in order')
        with self.assertRaises(ValueError) as caught:
            check_pipeline({'steps': [{'id': 'a', 'type': 'input', 'dataset': 'gone'}]}, {})
        self.assertEqual(str(caught.exception), 'Step a: this run has no table gone')
        lang.use('zh')
        with self.assertRaises(ValueError) as caught:
            check_pipeline({'steps': [{'id': 'a', 'type': 'input', 'dataset': 'gone'}]}, {})
        self.assertEqual(str(caught.exception), '步骤 a：这次运行里没有这张表 gone')

    def test_a_broken_operator_names_the_step_and_the_column_in_english(self):
        from tests.test_pipeline_ops import ORDERS_COLUMNS
        from ontology_poc_generator.pipeline_ops import compile_op, new_context
        lang.use('en')
        with self.assertRaises(Exception) as caught:
            compile_op({'op': 'filter', 'where': {'column': '没有这列', 'cmp': 'eq', 'value': 1}}, 'in', ORDERS_COLUMNS, new_context(), 'Step t')
        self.assertIn('Step t', str(caught.exception))
        self.assertIn('no column', str(caught.exception))
        self.assertNotRegex(str(caught.exception).replace('没有这列', ''), '[一-龥]')

    def test_an_expression_error_is_english(self):
        lang.use('en')
        result = compile_expression('1 +', [])
        self.assertFalse(result['ok'])
        self.assertNotRegex(result['errors'][0]['message'], '[一-龥]')

    def test_an_ai_step_without_a_prompt_column_is_refused_in_english(self):
        lang.use('en')
        with self.assertRaises(Exception) as caught:
            check_llm_step({'id': 'a', 'type': 'llm', 'from': 'in', 'name': 'x', 'template': 'classify', 'column': 'c', 'categories': ['a', 'b']}, 'a', [{'name': 'c', 'type': 'text'}])
        self.assertNotRegex(str(caught.exception).replace('c', ''), '[一-龥]')

    def test_the_model_is_asked_to_write_in_english_for_an_english_asker_and_the_chinese_prompt_is_unchanged(self):
        from ontology_poc_generator.pipeline_assist import EXPLAIN_SYSTEM_PROMPT
        self.assertEqual(_in_language(EXPLAIN_SYSTEM_PROMPT), EXPLAIN_SYSTEM_PROMPT)
        lang.use('en')
        self.assertTrue(_in_language(EXPLAIN_SYSTEM_PROMPT).endswith('in English.'))
        self.assertIn('reasoning', ENGLISH_NOTE)
        self.assertIn('reasoning', ontology_questions.ENGLISH_NOTE)

    def test_a_schedule_says_when_it_runs_in_english(self):
        lang.use('en')
        self.assertEqual(cadence_text({'cadence': 'weekly', 'weekday': 0, 'hour': 9, 'minute': 5, 'tz': 'UTC'}), 'Every Monday at 09:05 (UTC)')
        self.assertEqual(cadence_text({'cadence': 'upstream'}), 'When upstream updates')


if __name__ == '__main__':
    unittest.main()
