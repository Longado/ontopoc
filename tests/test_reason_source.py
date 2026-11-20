"""A reason the model wrote is marked as the model's, so the page can say it plainly and keep the model's words one
click away; a reason code found (a field the ontology lacks) is short and stands as it is."""
import json
import unittest

from ontology_poc_generator.company_sources import load_table_file
from ontology_poc_generator.ontology_questions import ask_questions
from ontology_poc_generator.recognition import ModelCompletion
from tests.test_derived_measures import CSV, ONTOLOGY


class Model:
    def __init__(self, reply):
        self.reply = reply

    def complete_json(self, *, system_prompt, user_prompt):
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(self.reply))


def ask(question):
    reply = {'questions': [question]}
    return ask_questions(ONTOLOGY, load_table_file('lines.csv', CSV), Model(reply), question['question'])['items'][0]


class ReasonSourceTests(unittest.TestCase):
    def test_the_models_reason_is_marked_as_its_own(self):
        item = ask({'question': '上个月卖了多少？', 'reasoning': '要限定时间段，order_line 上没有日期', 'query': None, 'missing': 'query_language'})
        self.assertEqual((item['status'], item['reason_from_model']), ('query_limit', True))
        self.assertIn('订单明细', item['reason'])

    def test_the_models_words_about_the_query_format_are_left_out_of_the_reason_it_gives(self):
        reasoning = ('本体里没有客户对象类型，也没有城市属性，所以没法按客户城市分组。所以 query 为 null，missing 为 ontology。'
                     '有效订单由代码在查询前应用，方向为 include。where 只支持单个 equals。')
        item = ask({'question': '按客户城市看订单金额', 'reasoning': reasoning, 'query': None, 'missing': 'ontology'})
        self.assertEqual((item['status'], item['reason_from_model']), ('ontology_gap', True))
        self.assertIn('本体里没有客户对象类型，也没有城市属性，所以没法按客户城市分组。', item['reason'])
        for internal in ('query', 'null', 'missing', 'include', 'where', 'equals'):
            self.assertNotIn(internal, item['reason'])
        self.assertEqual(item['reasoning'], reasoning)   # the model's own words stay as they were, one click away
        only = ask({'question': '上个月卖了多少？', 'reasoning': '所以 query 为 null，missing 为 query_language。', 'query': None, 'missing': 'query_language'})
        self.assertEqual(only['status'], 'query_limit')
        self.assertTrue(only['reason'])
        self.assertNotIn('null', only['reason'])
        english = 'The ontology has no product type, so the query cannot group by product. Query is null.'
        self.assertEqual(ask({'question': 'Best product?', 'reasoning': english, 'query': None, 'missing': 'ontology'})['reason'], 'The ontology has no product type, so the query cannot group by product.')

    def test_a_reason_code_found_is_not(self):
        query = {'start': 'order_line', 'where': [{'field': '地区', 'equals': '华东'}], 'via': [], 'group_by': [], 'share': None, 'measure': None}
        item = ask({'question': '华东有几条明细？', 'reasoning': 'r', 'query': query})
        self.assertEqual(item['status'], 'ontology_gap')
        self.assertNotIn('reason_from_model', item)


if __name__ == '__main__':
    unittest.main()
