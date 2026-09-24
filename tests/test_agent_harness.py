import base64
import json
import unittest

from ontology_poc_generator.agent_harness import AGENTS, ask_model
from ontology_poc_generator.recognition import ModelCompletion, RecognitionError
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests


class Gateway:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def complete_json(self, *, system_prompt, user_prompt):
        self.calls.append(json.loads(user_prompt))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return ModelCompletion(provider='fake', model='deepseek-flash', content=reply)


class Logged(Gateway):
    def __init__(self, *replies):
        super().__init__(*replies)
        self.records = []

    def log_call(self, record):
        self.records.append(record)


class AskModelTests(unittest.TestCase):
    def test_a_reply_is_parsed_and_the_call_is_recorded_under_the_agent_that_made_it(self):
        gateway = Logged('{"groups": []}')
        judgement = ask_model(gateway, 'variant_matcher', 'company_name_variants.v1', 'system', {'names': ['甲']})
        self.assertEqual((judgement.reply, judgement.model, judgement.failure), ({'groups': []}, 'deepseek-flash', None))
        self.assertEqual(gateway.calls, [{'names': ['甲']}])
        record = gateway.records[0]
        self.assertEqual((record['agent'], record['label'], record['prompt_version'], record['outcome']),
                         ('variant_matcher', '名称对应员', 'company_name_variants.v1', 'ok'))
        self.assertIsInstance(record['ms'], int)

    def test_a_failed_request_and_a_reply_that_is_not_json_are_told_apart(self):
        failed = ask_model(Logged(RecognitionError('model request failed: timed out')), 'question_writer', 'v', 's', {})
        self.assertEqual((failed.reply, failed.failure), (None, 'request'))
        self.assertIn('timed out', failed.message)
        garbled = ask_model(Logged('not json'), 'question_writer', 'v', 's', {})
        self.assertEqual((garbled.reply, garbled.model, garbled.failure), (None, 'deepseek-flash', 'not_json'))

    def test_an_empty_account_is_recognised_as_such(self):
        empty = ask_model(Gateway(RecognitionError('model request failed: HTTP Error 402: Payment Required')), 'table_modeller', 'v', 's', {})
        self.assertTrue(empty.account_empty)
        self.assertFalse(ask_model(Gateway(RecognitionError('model request failed: timed out')), 'table_modeller', 'v', 's', {}).account_empty)

    def test_every_agent_the_product_calls_has_a_name_a_person_can_read(self):
        self.assertEqual(AGENTS, {'table_modeller': '表格建模员', 'document_modeller': '文档建模员',
                                  'question_writer': '出题员', 'variant_matcher': '名称对应员', 'field_describer': '字段释义员',
                                  'org_mapper': '组织梳理员'})
        with self.assertRaises(KeyError):
            ask_model(Gateway('{}'), 'free_chat', 'v', 's', {})   # no call goes out under a name nobody defined


class EmptyAccountTests(unittest.TestCase):
    def test_the_modeller_stops_at_once_when_the_account_is_empty(self):
        from ontology_poc_generator.company_ontology import build_company_ontology
        from tests.test_company_ontology import BUNDLE
        gateway = Gateway(*[RecognitionError('model request failed: HTTP Error 402: Payment Required')] * 3)
        result = build_company_ontology(BUNDLE, gateway)
        self.assertEqual(len(result['attempts']), 1)   # retrying cannot fill the account
        self.assertEqual(result['status'], 'blocked')


class CallLogTests(unittest.TestCase):
    def test_the_service_keeps_one_line_per_model_call(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            upload = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode(), 'purpose': '哪个客户订单最多？'}
            status, run = call(base, '/api/ontology/build', upload)
            self.assertEqual(status, 200, run)
            lines = [json.loads(line) for line in (out / 'model_calls.jsonl').read_text(encoding='utf-8').splitlines()]
        agents = [r['agent'] for r in lines]
        self.assertEqual(agents.count('question_writer'), 1)   # the question written as the purpose
        self.assertGreaterEqual(agents.count('table_modeller'), 3)   # the build, and the two runs beside it for stability
        self.assertTrue(all(r['outcome'] == 'ok' for r in lines))


if __name__ == '__main__':
    unittest.main()
