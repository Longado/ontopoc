"""The data-meaning card through MCP: reading it, recording what the client answered, how many cells are still blank in the
overview, and a question that a rule on the card refused."""
import json
import unittest

from ontology_poc_generator import mcp_server
from ontology_poc_generator.mcp_server import NO_SUCH_ROUTE, LocalService, ToolError, handle
from ontology_poc_generator.ontology_card import SAYS
from tests.test_mcp_open_items import ITEMS, RUN, RUN_PATH, serving

CARD = {'tables': [{'source': 'financial_rows', 'rows': 1921, 'objects': [], 'grain': {'id': 'grain:financial_rows', 'unique': None, 'answer': None},
                    'dates': [], 'amounts': []}],
        'objects': [], 'cells': 37, 'blank': 35}
ANSWERED = [{**ITEMS[0], 'id': 'unlinked:rows_to_award', 'answer': {'choice': 'incomplete', 'says': '数据没导全', 'text': '', 'by': '张三', 'basis': '10-27 会议'}}]


class Service(LocalService):
    """The local service answered from a table of path -> body (an exception in the table is raised as the service's
    refusal; a path not in it is the 404 an older service gives), remembering what was asked."""

    def __init__(self, answers):
        super().__init__('http://x')
        self.answers, self.seen = answers, []

    def request(self, path, payload=None):
        self.seen.append((path, payload))
        answer = self.answers.get(path, ToolError(NO_SUCH_ROUTE, 404))
        if isinstance(answer, Exception):
            raise answer
        return answer


def call(service, name, arguments):
    result = handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}, service)['result']
    return result['isError'], (result['content'][0]['text'] if result['isError'] else json.loads(result['content'][0]['text']))


def tools():
    return {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}


class ToolListTests(unittest.TestCase):
    def test_reading_and_saving_the_card_are_tools_with_their_schemas(self):
        listed = tools()
        self.assertEqual(listed['get_card']['inputSchema']['required'], ['saved_as'])
        save = listed['save_card']['inputSchema']
        self.assertEqual(save['required'], ['saved_as', 'by'])
        self.assertEqual(set(save['properties']), {'saved_as', 'by', 'cells', 'items'})
        self.assertEqual((save['properties']['cells']['type'], save['properties']['items']['type']), ('array', 'array'))
        self.assertIn('list_runs', save['properties']['saved_as']['description'])

    def test_saving_says_it_records_only_what_the_client_answered_and_that_the_answerer_and_source_come_from_the_person(self):
        text = tools()['save_card']['description']
        for said in ('只记人说的客户答复', 'by', 'basis', '不要自己填格', '不要替客户答'):
            self.assertIn(said, text)

    def test_the_handshake_tells_the_agent_what_to_do_with_a_refusal_by_the_card_and_with_an_answerable_item(self):
        text = handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}}, None)['result']['instructions']
        self.assertTrue(20 <= len(text.strip().splitlines()) <= 30, len(text.splitlines()))
        entry = lambda word: next(e for e in text.split('\n- ') if word in e)   # one entry of the manual, which may run over several lines
        self.assertIn('绕过', entry('refused_by_card'))
        self.assertIn('转告', entry('incomplete'))
        self.assertIn('save_card', entry('answered_items'))
        self.assertIn('get_card', entry('card_blank'))
        self.assertIn('不用另发', entry('card_blank'))   # saying 数据没导全 on an unlinked item already records the other end as partial
        self.assertIn('save_card', entry('confirm_ontology'))   # one of the person's own judgements


    def test_the_tool_descriptions_say_what_a_null_card_means_and_that_an_unlinked_answer_carries_the_partial_cell(self):
        overview = tools()['run_overview']['description']
        for said in ('旧版服务没有这条路由', '没有数据行的运行', '文档', '没通过核验', '{cells:0, blank:0}'):
            self.assertIn(said, overview)
        self.assertNotIn('没有口径卡时 card 为 null', overview)
        save = tools()['save_card']['description']
        for said in ('数据没导全', '只有一部分', '撤回', '不用另发'):
            self.assertIn(said, save)


class CellValueTests(unittest.TestCase):
    def test_reading_and_saving_the_card_list_each_kind_of_cells_values_with_what_they_mean(self):
        for name in ('get_card', 'save_card'):
            text = tools()[name]['description']
            for kind, values in SAYS.items():
                self.assertIn(kind, text)
                for value, meaning in values.items():
                    self.assertIn(f'{value}={meaning}', text, f'{name}: {kind} {value}')
            # the two an agent must tell apart when the client says "这是累计数"
            self.assertIn('running=每次事件后的累计值', text)
            self.assertIn('period_to_date=期初到期末的累计值', text)


class CardToolTests(unittest.TestCase):
    def test_get_card_reads_the_runs_card(self):
        service = Service({'/api/ontology/runs/exam.json/card': CARD})
        self.assertEqual(mcp_server.get_card(service, {'saved_as': 'exam.json'}), CARD)
        self.assertEqual(service.seen, [('/api/ontology/runs/exam.json/card', None)])

    def test_save_card_posts_the_cells_and_items_with_who_answered(self):
        cells = [{'id': 'amount:financial_rows.gross', 'value': 'period_to_date', 'note': '', 'basis': '10-27 会议'}]
        items = [{'id': 'unlinked:rows_to_award', 'choice': 'incomplete', 'text': '合同授标只导了一季度', 'basis': '10-27 会议'}]
        saved = {'card': CARD, 'items': [], 'answered': ANSWERED}
        service = Service({'/api/ontology/card': saved})
        self.assertEqual(mcp_server.save_card(service, {'saved_as': 'exam.json', 'by': ' 张三 ', 'cells': cells, 'items': items}), saved)
        self.assertEqual(service.seen, [('/api/ontology/card', {'saved_as': 'exam.json', 'by': '张三', 'cells': cells, 'items': items})])

    def test_save_card_sends_only_what_it_was_given(self):
        service = Service({'/api/ontology/card': {'card': CARD, 'items': [], 'answered': []}})
        mcp_server.save_card(service, {'saved_as': 'exam.json', 'by': '张三', 'items': []})
        self.assertEqual(service.seen[0][1], {'saved_as': 'exam.json', 'by': '张三', 'items': []})

    def test_who_answered_is_required_and_is_not_made_up(self):
        for arguments in ({'saved_as': 'exam.json', 'cells': []}, {'saved_as': 'exam.json', 'by': '  ', 'cells': []}):
            service = Service({})
            failed, text = call(service, 'save_card', arguments)
            self.assertTrue(failed)
            self.assertIn('by', text)
            self.assertEqual(service.seen, [])

    def test_the_services_refusal_comes_back_as_the_tool_error_text(self):
        for tool, arguments, path in (('save_card', {'saved_as': 'exam.json', 'by': '张三', 'items': [{'id': 'x', 'text': 'y'}]}, '/api/ontology/card'),
                                      ('get_card', {'saved_as': 'exam.json'}, '/api/ontology/runs/exam.json/card')):
            with self.subTest(tool=tool), serving({path: (400, {'error': '这件事已经不在清单上了'})}) as base:
                failed, text = call(LocalService(base), tool, arguments)
                self.assertTrue(failed)
                self.assertEqual(text, '这件事已经不在清单上了')


class OverviewTests(unittest.TestCase):
    def overview(self, **answers):
        return mcp_server.run_overview(Service({RUN_PATH: RUN, **answers}), {'saved_as': 'exam.json'})

    def test_the_overview_brings_the_answered_items_and_how_many_card_cells_are_blank(self):
        out = self.overview(**{RUN_PATH + '/open-items': {'items': ITEMS, 'answered': ANSWERED}, RUN_PATH + '/card': CARD})
        self.assertEqual((out['open_items'], out['answered_items']), (ITEMS, ANSWERED))
        self.assertEqual(out['card'], {'cells': 37, 'blank': 35})   # the counts only: the card itself is get_card
        self.assertNotIn('note', out)

    def test_the_open_items_of_an_older_shape_have_nothing_answered(self):
        out = self.overview(**{RUN_PATH + '/open-items': {'items': ITEMS}, RUN_PATH + '/card': CARD})
        self.assertEqual((out['open_items'], out['answered_items']), (ITEMS, []))

    def test_a_service_without_the_card_gives_null_for_it_and_still_the_rest(self):
        out = self.overview(**{RUN_PATH + '/open-items': {'items': ITEMS, 'answered': []}})
        self.assertIsNone(out['card'])
        self.assertEqual((out['open_items'], out['answered_items']), (ITEMS, []))
        self.assertEqual(out['checks_passed'], '6 / 7')

    def test_a_service_without_either_route_gives_null_for_both_and_says_it_is_older(self):
        out = self.overview()
        self.assertEqual((out['open_items'], out['answered_items'], out['card']), (None, None, None))
        self.assertIn('旧版本', out['note'])

    def test_another_failure_of_the_card_route_is_not_taken_for_an_old_service(self):
        service = Service({RUN_PATH: RUN, RUN_PATH + '/open-items': {'items': []}, RUN_PATH + '/card': ToolError('找不到这次运行', 404)})
        with self.assertRaisesRegex(ToolError, '找不到这次运行'):
            mcp_server.run_overview(service, {'saved_as': 'exam.json'})

    def test_a_document_run_does_not_ask_for_the_card_and_has_no_cells(self):
        document = {**RUN, 'file': {'name': 'brief.md', 'kind': 'document'}}
        for answers in ({RUN_PATH + '/open-items': {'items': ITEMS, 'answered': ANSWERED}},   # an older service refuses a document's card with a 400
                        {RUN_PATH + '/open-items': {'items': ITEMS, 'answered': ANSWERED}, RUN_PATH + '/card': ToolError('文档没有口径卡', 400)}):
            service = Service({RUN_PATH: document, **answers})
            out = mcp_server.run_overview(service, {'saved_as': 'exam.json'})
            self.assertEqual(out['card'], {'cells': 0, 'blank': 0})
            self.assertEqual((out['open_items'], out['answered_items']), (ITEMS, ANSWERED))
            self.assertNotIn(RUN_PATH + '/card', [path for path, _ in service.seen])

    def test_an_older_service_that_refuses_a_documents_lists_does_not_fail_the_overview(self):
        document = {**RUN, 'file': {'name': 'brief.md', 'kind': 'document'}}
        for refusal in (ToolError('文档没有这份清单', 400), ToolError('文档没有这份清单', 404), ToolError(NO_SUCH_ROUTE, 404)):
            service = Service({RUN_PATH: document, RUN_PATH + '/open-items': refusal, RUN_PATH + '/card': refusal})
            out = mcp_server.run_overview(service, {'saved_as': 'exam.json'})
            self.assertEqual((out['open_items'], out['answered_items'], out['card']), ([], [], {'cells': 0, 'blank': 0}))
            self.assertNotIn('note', out)   # a document is not an old service: it has nothing to settle
            self.assertEqual([path for path, _ in service.seen], [RUN_PATH])

    def test_a_finished_document_build_does_not_ask_for_the_card_either(self):
        document = {**RUN, 'file': {'name': 'brief.md', 'kind': 'document'}}
        service = Service({'/api/ontology/jobs': {'job_id': 'j1'}, '/api/ontology/jobs/j1': {'state': 'done', 'result': document},
                           RUN_PATH + '/open-items': {'items': ITEMS, 'answered': []}, RUN_PATH + '/card': ToolError('文档没有口径卡', 400)})
        out = mcp_server.build_ontology(service, {'files': [__file__]})
        self.assertEqual(out['card'], {'cells': 0, 'blank': 0})
        self.assertNotIn(RUN_PATH + '/card', [path for path, _ in service.seen])

    def test_a_finished_build_brings_them_too(self):
        service = Service({'/api/ontology/jobs': {'job_id': 'j1'}, '/api/ontology/jobs/j1': {'state': 'done', 'result': RUN},
                           RUN_PATH + '/open-items': {'items': ITEMS, 'answered': ANSWERED}, RUN_PATH + '/card': CARD})
        out = mcp_server.build_ontology(service, {'files': [__file__]})
        self.assertEqual((out['answered_items'], out['card']), (ANSWERED, {'cells': 37, 'blank': 35}))


class RefusalTests(unittest.TestCase):
    REFUSED = {'question': '总支出是多少', 'status': 'query_limit', 'answer': None, 'path': None, 'query': {'op': 'sum'},
               'reason': '「gross」在口径卡里是“每次事件后的累计值”：跨行相加会重复。', 'refused_by_card': 'amount:financial_rows.gross', 'reason_from_model': False}

    def test_a_question_keeps_which_card_cell_refused_it(self):
        out = mcp_server._question(self.REFUSED)
        self.assertEqual(out['refused_by_card'], 'amount:financial_rows.gross')
        self.assertIs(out['reason_from_model'], False)
        self.assertNotIn('refused_by_card', mcp_server._question({k: v for k, v in self.REFUSED.items() if k != 'refused_by_card'}))

    def test_a_question_keeps_the_card_lines_and_the_incomplete_note_in_its_evidence(self):
        card = {'tables': [{'source': 'financial_rows', 'rows': 1921, 'through': '2024-12-31'}],
                'lines': [{'id': 'amount:financial_rows.gross', 'field': 'gross', 'says': '期初到期末的累计值', 'by': '张三', 'basis': '10-27 会议', 'at': 'x'}],
                'incomplete': [{'type': 'contract', 'label': '合同授标', 'note': '只导了一季度', 'by': '张三'}]}
        out = mcp_server._question({'question': 'q', 'status': 'answered', 'evidence': {'filters': [], 'card': card}})
        self.assertEqual(out['evidence']['card'], card)

    def test_ask_and_list_questions_carry_them(self):
        refused = {**self.REFUSED, 'evidence': {'card': {'tables': [], 'lines': [], 'incomplete': []}}}
        ev = {'asked': [{'items': [refused]}], 'questions': {'items': [refused]}, 'acceptance': None}
        service = Service({'/api/ontology/ask': {'evaluation': ev}, RUN_PATH: {**RUN, 'evaluation': ev}})
        asked = mcp_server.ask_question(service, {'saved_as': 'exam.json', 'question': refused['question']})['items'][0]
        listed = mcp_server.list_questions(service, {'saved_as': 'exam.json'})
        for item in (asked, listed['asked'][0], listed['model_round'][0]):
            self.assertEqual(item['refused_by_card'], 'amount:financial_rows.gross')
            self.assertIn('card', item['evidence'])

    def test_the_question_tools_explain_the_refusal_and_the_card_evidence(self):
        for name in ('ask_question', 'list_questions'):
            for word in ('refused_by_card', 'evidence.card', 'incomplete'):
                self.assertIn(word, tools()[name]['description'], f'{name}: {word}')


if __name__ == '__main__':
    unittest.main()
