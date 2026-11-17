"""Over HTTP: the same question asked with Accept-Language: en comes back with an English caliber line."""
import json

from tests.test_workspace_questions import AskModel, QUESTION, QuestionTests, cancelled


class EnglishAnswerTests(QuestionTests):
    # only the one test below; the inherited ones run in their own module
    def test_an_ask_with_accept_language_en_writes_the_caliber_in_english(self):
        with self.service(gateway=AskModel(cancelled())) as (base, _):
            team = self.team(base)
            self.confirmed_orders(team)
            ann = team['ann']
            status, zh = ann.post('/api/workspace/ask', {'question': QUESTION})
            self.assertEqual(status, 200, zh)
            status, en = ann.post('/api/workspace/ask', {'question': QUESTION}, headers={'Accept-Language': 'en-US,en;q=0.9'})
            self.assertEqual(status, 200, en)
            self.assertEqual(en['answer']['total'], zh['answer']['total'])
            self.assertEqual(en['path'], '订单 where "状态码" is "2 = 已取消"')   # the words are English; the type and meaning names are the data's
            self.assertEqual([step['name'] for step in en['steps']], ['Understand the question', 'Find object types', 'Find relations', 'Write the query', 'Check definitions', 'Result'])
            self.assertEqual(en['steps'][-1]['text'], 'Worked out the result')
            self.assertEqual(zh['path'], '只看“状态码”为“2 = 已取消”的订单')
            self.assertEqual(zh['steps'][-1]['text'], '算出了结果')
            status, refused = ann.post('/api/workspace/ask', {'question': ' '}, headers={'Accept-Language': 'en'})
            self.assertEqual((status, refused['error']), (400, 'Write the question you want to ask'))


for _name in dir(QuestionTests):   # the inherited walks run in their own module
    if _name.startswith('test_'):
        setattr(EnglishAnswerTests, _name, None)
