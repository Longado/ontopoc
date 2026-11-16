"""R10 step 4: a question the model answers by writing OntoPoc Query text instead of the JSON query. Asked with {"writes": "query"}, the model gets the same
catalog and definitions (still no row), writes text, and the text runs exactly as POST /api/workspace/query would run it for this person: the meanings it
uses are read from the text (= is include, <> exclude), not from the model's word. Text that does not compile is a miss that says why, never a number."""
import json

from ontology_poc_generator.recognition import ModelCompletion
from tests.test_object_types import VALID
from tests.test_workspace_questions import CANCELLED, ORDERS, QuestionTests

COUNT_CANCELLED = "SELECT count(o) FROM (o:订单) WHERE o.状态码 = '已取消'"


class TextModel:
    """Writes the reply it was given (a dict, or a list of them for one call each), and keeps every request and system prompt it received."""

    def __init__(self, *replies):
        self.replies, self.requests, self.prompts = list(replies), [], []

    def complete_json(self, *, system_prompt, user_prompt, timeout_seconds=None):
        self.requests.append(json.loads(user_prompt))
        self.prompts.append(system_prompt)
        reply = self.replies[min(len(self.requests), len(self.replies)) - 1]
        return ModelCompletion('test', 'test-model', json.dumps(reply, ensure_ascii=False))


def load_tests(loader, standard, pattern):
    import unittest
    return unittest.TestSuite(WritesQueryTests(name) for name in vars(WritesQueryTests) if name.startswith('test_'))


class WritesQueryTests(QuestionTests):
    def ask_text(self, client, question='已取消的订单有多少？', writes='query'):
        return client.post('/api/workspace/ask', {'question': question, 'writes': writes})

    def test_the_model_writes_query_text_and_the_answer_is_the_one_the_text_runs_to_with_the_meaning_it_names(self):
        model = TextModel({'reasoning': '订单里状态码是已取消的', 'query': COUNT_CANCELLED})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            status, body = self.ask_text(team['ann'])
            self.assertEqual(status, 200, body)
            self.assertEqual((body['status'], body['answer']['total'], body['writes'], body['reasoning']), ('answered', CANCELLED, 'query', '订单里状态码是已取消的'))
            self.assertEqual(body['query_text'], "SELECT count(o) AS 数量\nFROM (o:订单)\nWHERE o.状态码 = '已取消'")
            self.assertEqual(body['written'], COUNT_CANCELLED)   # what the model wrote, kept beside the canonical text
            self.assertIn(('meaning', '订单.状态码'), [(d['kind'], d['name']) for d in body['definitions']])
            self.assertEqual(body['query']['where'], [{'field': '状态码', 'equals': '已取消'}])   # the meaning as written: the engine reads it as its confirmed code
            # the model was told the grammar, the same catalog as for JSON (meanings, no rows) and the question
            self.assertIn('OntoPoc Query', model.prompts[0])
            self.assertIn('GROUP BY', model.prompts[0])
            sent = json.dumps(model.requests[0], ensure_ascii=False)
            self.assertIn('已取消', sent)
            self.assertNotIn(ORDERS[0]['订单号'], sent)
            self.assertEqual(model.requests[0]['asked'], '已取消的订单有多少？')
            # kept in the history like any answer
            history = team['ann'].get('/api/workspace/ask')[1]['history']
            self.assertEqual(history[0]['status'], 'answered')

    def test_text_that_does_not_compile_is_a_miss_that_says_why_and_gives_no_number(self):
        model = TextModel({'reasoning': '', 'query': 'SELECT count(o) FROM (o:订单) WHERE o.颜色 = 1'})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            status, body = self.ask_text(team['ann'])
            self.assertEqual(status, 200, body)
            self.assertEqual(body['status'], 'query_limit')
            self.assertNotIn('answer', body)
            self.assertIn('颜色', body['reason'])
            self.assertEqual(body['written'], 'SELECT count(o) FROM (o:订单) WHERE o.颜色 = 1')

    def test_a_meaning_the_question_names_and_the_text_leaves_out_is_refused(self):
        model = TextModel({'reasoning': '数订单', 'query': 'SELECT count(o) FROM (o:订单)'})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            status, body = self.ask_text(team['ann'])
            self.assertEqual(status, 200, body)
            self.assertNotEqual(body['status'], 'answered')   # 已取消 is in the question and nowhere in the query: 160 would be a wrong number

    def test_leaving_a_meaning_out_is_written_with_not_equals_and_is_an_exclusion(self):
        model = TextModel({'reasoning': '', 'query': "SELECT count(o) FROM (o:订单) WHERE o.状态码 <> '已取消'"})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            status, body = self.ask_text(team['ann'], '没取消的订单有多少？')
            self.assertEqual(status, 200, body)
            self.assertEqual((body['status'], body['answer']['total']), ('answered', len(ORDERS) - CANCELLED))

    def test_a_question_the_text_cannot_say_comes_back_as_the_models_reason(self):
        model = TextModel({'reasoning': '要按周分组，查询只有按月和按年', 'query': None, 'missing': 'query_language'})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            status, body = self.ask_text(team['ann'], '每周有多少订单？')
            self.assertEqual(status, 200, body)
            self.assertEqual(body['status'], 'query_limit')
            self.assertIn('按周', body['reason'])

    def test_a_view_the_model_names_is_applied_before_the_text_runs(self):
        model = TextModel({'reasoning': '有效订单', 'query': 'SELECT count(o) FROM (o:订单)', 'views': ['有效订单']})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann = team['ann']
            self.confirmed_orders(team)
            self.assertEqual(ann.post('/api/workspace/types/views', VALID)[0], 200)
            self.confirm_view(team['bob'], 'order', '有效订单')
            status, body = self.ask_text(ann, '有效订单有多少？')
            self.assertEqual(status, 200, body)
            self.assertEqual(body['status'], 'answered', body)
            self.assertEqual(body['answer']['total'], len(ORDERS) - CANCELLED)
            self.assertIn(('view', '有效订单'), [(d['kind'], d['name']) for d in body['definitions']])

    def test_a_viewer_gets_the_answer_without_rows_and_the_json_form_is_still_the_default(self):
        from tests.test_workspace_questions import AskModel, cancelled
        with self.service(gateway=TextModel({'reasoning': '', 'query': COUNT_CANCELLED})) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            status, body = self.ask_text(team['vera'])
            self.assertEqual((status, body['status'], body['answer']['total']), (200, 'answered', CANCELLED))
            self.assertNotIn('examples', json.dumps(body['answer'], ensure_ascii=False))
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            status, body = team['ann'].post('/api/workspace/ask', {'question': '取消的订单有多少？'})
            self.assertEqual((status, body['status'], body.get('writes', 'json')), (200, 'answered', 'json'))

    def test_writes_must_be_json_or_query(self):
        with self.service(gateway=TextModel({'query': COUNT_CANCELLED})) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            status, body = self.ask_text(team['ann'], writes='sql')
            self.assertEqual(status, 400, body)
            self.assertIn('query', body['error'])

    def test_orders_whose_customer_is_missing_are_answered_from_the_relation_check_as_in_the_json_form(self):
        from tests.test_object_relations import CUSTOMER, RELATION, customers_mended
        from tests.test_object_types import ORDER
        model = TextModel({'reasoning': '订单里客户编号在客户表里找不到的', 'query': None, 'missing': 'query_language',
                           'unmatched_relation': {'relation': 'order_customer', 'direction': 'many_without_one', 'other_conditions': False}})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types', {k: v for k, v in ORDER.items() if k != 'enums'} | {'properties': [{'column': '订单号'}, {'column': '金额'}]})[0], 200)
            self.assertEqual(ann.post('/api/workspace/types', CUSTOMER)[0], 200)
            self.assertEqual(ann.post('/api/workspace/relations', RELATION)[0], 200)
            for name in ('order', 'customer'):
                self.confirm(bob, name)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
            shown = bob.get('/api/workspace/relations/order_customer')[1]
            self.assertEqual(bob.post('/api/workspace/queue/confirm', {'element': 'relation:order_customer', 'version': shown['version'], 'seen': shown['check']['signature']})[0], 200)
            status, body = self.ask_text(ann, '有多少订单的客户在客户表里找不到？')
            self.assertEqual(status, 200, body)
            self.assertEqual((body['status'], body['answer']['total'], body['writes']), ('answered', 3, 'query'), body)
            self.assertEqual(sorted(d['name'] for d in body['definitions']), ['客户', '订单', '订单属于客户'])

    def test_views_that_are_not_a_list_of_known_names_are_left_out_rather_than_crashing_or_sinking_the_query(self):
        """Found in the review of PR #87: "views": 5 dropped the connection, "views": "有效订单" read each character as a view."""
        replies = [{'reasoning': '', 'query': COUNT_CANCELLED, 'views': bad} for bad in (5, True, '有效订单', {'a': 1}, ['不存在', 3])]
        model = TextModel(*replies)
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            for bad in replies:
                status, body = self.ask_text(team['ann'])
                self.assertEqual((status, body.get('status'), (body.get('answer') or {}).get('total')), (200, 'answered', CANCELLED), (bad['views'], body))
