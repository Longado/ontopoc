import json
import unittest

from ontology_poc_generator.ontology_questions import QUESTION_PROMPT_VERSION, ask_questions
from tests.test_company_ontology import BUNDLE, PROPOSAL
from tests.test_ontology_questions import AskTests


class QueryLimitTests(unittest.TestCase):
    def test_a_question_the_query_format_cannot_hold_is_not_blamed_on_the_ontology(self):
        model = AskTests.Model({'questions': [
            {'reasoning': '需要同时按两个维度分组', 'question': '哪些客户、产品的订单最多？', 'query': None, 'missing': 'query_language'},
            {'reasoning': '本体里没有发票', 'question': '哪张发票金额最大？', 'query': None, 'missing': 'ontology'},
            {'reasoning': '说不清', 'question': '？', 'query': None},
        ]})
        out = ask_questions(PROPOSAL, BUNDLE, model)
        self.assertEqual([i['status'] for i in out['items']], ['query_limit', 'ontology_gap', 'ontology_gap'])
        self.assertEqual(QUESTION_PROMPT_VERSION, 'company_questions.v4')


if __name__ == '__main__':
    unittest.main()
