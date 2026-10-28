"""A condition the model added on its own is the person's call: fixing the question as it stands is refused until the
person has either dropped the condition (recomputed without the model) or written down why it belongs."""
import unittest

from ontology_poc_generator import mcp_server
from ontology_poc_generator.mcp_server import LocalService, ToolError, handle

QUESTION = '垦务局签的合同在 2025 财年第一季度累计付了多少钱？'
ADDED = {'field': 'awarding_subagency', 'equals': 'BUREAU OF RECLAMATION', 'before': 1455, 'after': 1444, 'not_in_question': True,
         'removed_measure': 4176392.96}
ASKED = {'field': 'fiscal_year', 'equals': '2025', 'before': 1500, 'after': 1455}   # the question says 2025: not the model's own
WHERE = [{'field': 'payments.fiscal_year', 'equals': '2025'}, {'field': 'payments.awarding_subagency', 'equals': 'BUREAU OF RECLAMATION'}]


def item(filters, **more):
    return {'question': QUESTION, 'reasoning': '', 'query': {'start': 'payment', 'where': WHERE}, 'status': 'answered',
            'answer': {'groups': [[None, 140216640.65]]}, 'path': ['payment'], 'evidence': {'filters': filters}, **more}


class Service(LocalService):
    def __init__(self, items, reply=None):
        self.items, self.reply, self.sent = items, reply or {}, []

    def request(self, path, payload=None):
        self.sent.append((path, payload))
        if path == '/api/ontology/acceptance':
            return {'evaluation': {'acceptance': {'items': payload['items']}}}
        if path == '/api/ontology/requery':
            return self.reply
        return {'saved_as': 'r.json', 'evaluation': {'asked': [{'items': self.items}], 'acceptance': None}}


class FixQuestionTests(unittest.TestCase):
    def test_a_condition_the_model_added_blocks_fixing_until_the_person_decides(self):
        service = Service([item([ASKED, ADDED])])
        with self.assertRaises(ToolError) as caught:
            mcp_server.fix_question(service, {'saved_as': 'r.json', 'question': QUESTION})
        self.assertEqual(str(caught.exception), '这道题的答案里模型自己加了条件“awarding_subagency = BUREAU OF RECLAMATION”（筛掉 11 个）。'
                                                '先问人：不该加就用 drop_filter 去掉重算；该加就在 note 里写明口径再固定。')
        self.assertEqual([path for path, _ in service.sent], ['/api/ontology/runs/r.json'])   # nothing was saved

    def test_a_note_that_says_why_the_condition_belongs_lets_it_through(self):
        service = Service([item([ASKED, ADDED])])
        out = mcp_server.fix_question(service, {'saved_as': 'r.json', 'question': QUESTION, 'note': '只算垦务局自己签的'})
        [(_, payload)] = [s for s in service.sent if s[0] == '/api/ontology/acceptance']
        self.assertEqual(payload['items'][0]['note'], '只算垦务局自己签的')
        self.assertEqual(out['acceptance']['items'][0]['question'], QUESTION)

    def test_a_blank_note_is_no_note(self):
        with self.assertRaisesRegex(ToolError, 'drop_filter'):
            mcp_server.fix_question(Service([item([ADDED])]), {'saved_as': 'r.json', 'question': QUESTION, 'note': '  '})

    def test_conditions_the_question_names_or_that_filtered_nothing_do_not_block(self):
        for filters in ([], [ASKED], [{**ADDED, 'after': 1455}], [{k: v for k, v in ADDED.items() if k != 'not_in_question'}]):
            with self.subTest(filters=filters):
                service = Service([item(filters)])
                mcp_server.fix_question(service, {'saved_as': 'r.json', 'question': QUESTION})
                self.assertIn('/api/ontology/acceptance', [path for path, _ in service.sent])

    def test_every_added_condition_is_named_with_how_many_it_removed(self):
        second = {'field': 'award_type', 'equals': 'D', 'before': 1444, 'after': 144, 'not_in_question': True}
        with self.assertRaises(ToolError) as caught:
            mcp_server.fix_question(Service([item([ADDED, second])]), {'saved_as': 'r.json', 'question': QUESTION})
        self.assertIn('“awarding_subagency = BUREAU OF RECLAMATION”（筛掉 11 个）、“award_type = D”（筛掉 1,300 个）', str(caught.exception))


class DropFilterTests(unittest.TestCase):
    NEW = {'question': QUESTION, 'reasoning': '', 'query': {'start': 'payment', 'where': WHERE[:1]}, 'status': 'answered',
           'answer': {'groups': [[None, 144393033.61]]}, 'path': ['payment'], 'asked': True,
           'edited': {'dropped': [{'field': 'payments.awarding_subagency', 'equals': 'BUREAU OF RECLAMATION'}]}}

    def drop(self, **args):
        service = Service([], {'evaluation': {'asked': [{'items': [self.NEW]}]}})
        return service, mcp_server.drop_filter(service, {'saved_as': 'r.json', 'question': QUESTION, 'field': 'payments.awarding_subagency',
                                                         'equals': 'BUREAU OF RECLAMATION', **args})

    def test_it_asks_the_service_to_recompute_without_that_condition_and_returns_the_new_answer(self):
        service, out = self.drop()
        self.assertEqual(service.sent, [('/api/ontology/requery', {
            'saved_as': 'r.json', 'question': QUESTION,
            'drop': {'field': 'payments.awarding_subagency', 'equals': 'BUREAU OF RECLAMATION'}})])
        self.assertEqual(out, {'item': {'question': QUESTION, 'status': 'answered', 'answer': {'groups': [[None, 144393033.61]]},
                                        'path': ['payment'], 'reason': None, 'query': {'start': 'payment', 'where': WHERE[:1]},
                                        'edited': self.NEW['edited']}})

    def test_the_value_goes_as_written_even_when_it_is_not_text(self):
        service, _ = self.drop(equals=2025)
        self.assertEqual(service.sent[0][1]['drop']['equals'], 2025)

    def test_it_is_a_tool_that_needs_all_four_arguments_and_says_it_does_not_call_the_model(self):
        tools = {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        self.assertEqual(tools['drop_filter']['inputSchema']['required'], ['saved_as', 'question', 'field', 'equals'])
        self.assertIn('不调模型', tools['drop_filter']['description'])
        self.assertIn('人', tools['drop_filter']['description'])
        reply = handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
            'name': 'drop_filter', 'arguments': {'saved_as': 'r.json', 'question': QUESTION, 'field': 'f'}}}, None)['result']
        self.assertTrue(reply['isError'])
        self.assertIn('equals', reply['content'][0]['text'])

    def test_the_description_says_both_spellings_of_the_field_are_taken(self):
        tools = {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        tool = tools['drop_filter']
        self.assertNotIn('带来源表前缀', tool['description'])   # the exam data's query.where has no table in front of the field
        self.assertNotIn('payments.awarding_subagency', tool['description'])
        for text in (tool['description'], tool['inputSchema']['properties']['field']['description']):
            self.assertIn('query.where', text)
            self.assertIn('evidence.filters', text)

    def test_the_edit_that_was_made_shows_up_in_the_questions_an_agent_reads(self):
        self.assertEqual(mcp_server._question(self.NEW)['edited'], self.NEW['edited'])


if __name__ == '__main__':
    unittest.main()
