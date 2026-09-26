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

    def test_a_reason_code_found_is_not(self):
        query = {'start': 'order_line', 'where': [{'field': '地区', 'equals': '华东'}], 'via': [], 'group_by': [], 'share': None, 'measure': None}
        item = ask({'question': '华东有几条明细？', 'reasoning': 'r', 'query': query})
        self.assertEqual(item['status'], 'ontology_gap')
        self.assertNotIn('reason_from_model', item)


if __name__ == '__main__':
    unittest.main()
