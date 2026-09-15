import json
import unittest

from ontology_poc_generator.ontology_questions import QUESTION_PROMPT_VERSION, ask_questions, categorical_values, run_query
from ontology_poc_generator.recognition import ModelCompletion
from tests.test_company_ontology import BUNDLE, PROPOSAL


class RunQueryTests(unittest.TestCase):
    def test_counts_start_objects_per_group_of_the_type_reached(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'where': [], 'via': ['order_customer'], 'group_by': '客户.名称'})
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['answer'], {'groups': [['乙', 1], ['甲', 1]], 'total_groups': 2, 'without_value': 1})
        self.assertEqual(result['path'], '订单 → 客户，按“名称”分组数订单')

    def test_filters_on_the_start_type_and_counts_when_nothing_is_grouped(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'where': [{'field': '订单.金额', 'equals': '100'}], 'via': [], 'group_by': None})
        self.assertEqual((result['status'], result['answer']), ('answered', {'total': 1}))
        reached = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'where': [], 'via': ['order_customer'], 'group_by': None})
        self.assertEqual(reached['answer'], {'total': 3})

    def test_queries_the_ontology_cannot_express_say_what_is_missing(self):
        for query, reason in (({'start': 'invoice', 'via': []}, 'invoice'),
                              ({'start': 'order', 'via': ['order_product']}, 'order_product'),
                              ({'start': 'order', 'where': [{'field': '订单.客户编号', 'equals': 'C1'}], 'via': []}, '订单.客户编号'),
                              ({'start': 'order', 'via': [], 'group_by': '客户.城市'}, '客户.城市')):
            with self.subTest(query=query):
                result = run_query(PROPOSAL, BUNDLE, query)
                self.assertEqual(result['status'], 'ontology_gap')
                self.assertIn(reason, result['reason'])

    def test_a_filter_value_the_data_never_has_is_reported_as_empty(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'where': [{'field': '订单.金额', 'equals': '999'}], 'via': []})
        self.assertEqual(result['status'], 'no_data')


class AskTests(unittest.TestCase):
    class Model:
        def __init__(self, reply):
            self.reply, self.prompts = reply, []

        def complete_json(self, *, system_prompt, user_prompt):
            self.prompts.append(json.loads(user_prompt))
            return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(self.reply))

    REPLY = {'questions': [
        {'reasoning': 'r', 'question': '哪个城市的客户订单最多？',
         'query': {'start': 'order', 'where': [], 'via': ['order_customer'], 'group_by': '客户.城市'}},
        {'reasoning': '本体里没有产品', 'question': '哪个产品最常出问题？', 'query': None},
    ]}

    def test_one_model_call_writes_the_questions_and_code_answers_them(self):
        model = self.Model(self.REPLY)
        out = ask_questions(PROPOSAL, BUNDLE, model)
        self.assertEqual(len(model.prompts), 1)
        self.assertEqual(out['prompt_version'], QUESTION_PROMPT_VERSION)
        self.assertEqual([i['status'] for i in out['items']], ['answered', 'ontology_gap'])
        self.assertEqual(out['items'][1]['reason'], '本体里没有产品')
        self.assertEqual((out['answered'], out['total']), (1, 2))
        sent = model.prompts[0]
        self.assertEqual(sent['purpose'], BUNDLE['decision'])
        self.assertIn('城市', json.dumps(sent['ontology'], ensure_ascii=False))
        self.assertNotIn('asked', sent)

    def test_the_readers_own_question_is_passed_through(self):
        model = self.Model({'questions': [self.REPLY['questions'][0]]})
        out = ask_questions(PROPOSAL, BUNDLE, model, question='哪个城市订单最多？')
        self.assertEqual(model.prompts[0]['asked'], '哪个城市订单最多？')
        self.assertEqual(out['items'][0]['asked'], True)

    def test_a_broken_reply_becomes_an_explained_failure(self):
        out = ask_questions(PROPOSAL, BUNDLE, self.Model({'nope': 1}))
        self.assertEqual((out['items'], out['error']), ([], '模型没有返回问题列表'))

    def test_the_model_sees_the_few_values_a_category_field_takes(self):
        values = categorical_values(PROPOSAL, BUNDLE)
        self.assertEqual(values['客户.城市'], ['常州', '无锡', '苏州'])
        self.assertEqual(values['客户.客户编号'], ['C1', 'C2'])   # identity fields with few values are listed too


if __name__ == '__main__':
    unittest.main()
