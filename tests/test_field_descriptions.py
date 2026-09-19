"""The fifth agent, 字段释义员: drafts the columns of a data platform's object form only a person was left to write — a Chinese name and a
description for each object and field, and which field to display. One call, on request. Code keeps what names a
real field and says why the rest was dropped; a person edits, and what they write is not overwritten by a redraft."""
import base64
import json
import unittest

from ontology_poc_generator.agent_harness import AGENTS
from ontology_poc_generator.field_descriptions import DESCRIBE_SYSTEM_PROMPT, draft_descriptions
from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
from ontology_poc_generator.recognition import ModelCompletion, RecognitionError
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests

HANDOVER = {'types': [{'type': 'order', 'label': '订单', 'identity_fields': ['订单号'], 'fields': [
    {'path': '订单号', 'type': 'VARCHAR', 'length': 2}, {'path': '金额', 'type': 'INTEGER', 'length': 3}]}]}
BUNDLE = {'sources': {'orders': {'records': [{'订单号': 'O1', '金额': '100'}, {'订单号': 'O2', '金额': '50'}]}}}
ONTOLOGY = {'object_types': [{'key': 'order', 'label': '订单', 'populated_from': [{'source': 'orders', 'identity': {'id': '订单号'}}],
                              'attributes': [{'source': 'orders', 'path': '金额'}]}], 'relations': []}
REPLY = {'types': [{'type': 'order', 'reasoning': 'r', 'label': '销售订单', 'description': '客户的一次下单', 'display_field': '备注',
                    'fields': [{'path': '金额', 'label': '订单金额', 'description': '含税金额'}, {'path': '折扣', 'label': '折扣', 'description': 'x'}]},
                   {'type': 'invoice', 'label': '发票', 'fields': []}]}


class Fake:
    def __init__(self, reply):
        self.reply, self.requests = reply, []

    def complete_json(self, *, system_prompt, user_prompt):
        self.requests.append(json.loads(user_prompt))
        if isinstance(self.reply, Exception):
            raise self.reply
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(self.reply))


class DraftTests(unittest.TestCase):
    def test_what_names_a_real_field_is_kept_and_the_rest_is_dropped_with_a_reason(self):
        gateway = Fake(REPLY)
        out = draft_descriptions(ONTOLOGY, BUNDLE, HANDOVER, gateway, '看清订单')
        order = out['types']['order']
        self.assertEqual((order['label'], order['description'], order['display_field']), ('销售订单', '客户的一次下单', None))
        self.assertEqual(order['fields'], {'金额': {'label': '订单金额', 'description': '含税金额', 'drafted': True}})
        self.assertTrue(order['drafted'])
        reasons = ' '.join(r['reason'] for r in out['rejected'])
        for said in ('备注', '折扣', 'invoice'):
            self.assertIn(said, reasons)
        self.assertEqual(out['prompt_version'], 'company_field_descriptions.v1')

    def test_the_model_sees_field_names_types_and_at_most_three_values_never_whole_rows(self):
        gateway = Fake(REPLY)
        draft_descriptions(ONTOLOGY, {'sources': {'orders': {'records': [{'订单号': f'O{i}', '金额': str(i)} for i in range(50)]}}}, HANDOVER, gateway, '')
        sent = gateway.requests[0]['types'][0]['fields']
        self.assertEqual([f['path'] for f in sent], ['订单号', '金额'])
        self.assertTrue(all(len(f['examples']) <= 3 for f in sent))

    def test_a_failed_call_says_so_and_drafts_nothing(self):
        out = draft_descriptions(ONTOLOGY, BUNDLE, HANDOVER, Fake(RecognitionError('model request failed: timed out')), '')
        self.assertEqual(out['types'], {})
        self.assertIn('模型请求失败', out['error'])

    def test_it_is_a_named_agent(self):
        self.assertEqual(AGENTS['field_describer'], '字段释义员')


class DescribeModel(QuestionModel):
    def complete_json(self, *, system_prompt, user_prompt):
        if system_prompt == DESCRIBE_SYSTEM_PROMPT:
            reply = {'types': [{'type': 'order', 'reasoning': 'r', 'label': '销售订单', 'description': '一次下单', 'display_field': '订单号',
                                'fields': [{'path': '金额', 'label': '订单金额', 'description': '含税'}]}]}
            return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(reply))
        return super().complete_json(system_prompt=system_prompt, user_prompt=user_prompt)


class FormServerTests(unittest.TestCase):
    def test_a_drafted_form_is_edited_kept_and_not_overwritten_by_a_redraft(self):
        upload = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}
        with OntologyServerTests().server(gateway=DescribeModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', upload)
            status, drafted = call(base, '/api/ontology/form/draft', {'saved_as': run['saved_as']})
            self.assertEqual(status, 200, drafted)
            form = drafted['evaluation']['form']
            self.assertEqual(form['types']['order']['label'], '销售订单')
            form['types']['order']['fields']['金额'] = {'label': '成交金额', 'description': '人写的', 'drafted': False}
            self.assertEqual(call(base, '/api/ontology/form', {'saved_as': run['saved_as'], 'form': form})[0], 200)
            _, again = call(base, '/api/ontology/form/draft', {'saved_as': run['saved_as']})
            self.assertEqual(again['evaluation']['form']['types']['order']['fields']['金额']['label'], '成交金额')   # a person's words stay
            _, rebuilt = call(base, '/api/ontology/build', upload)
            self.assertEqual(rebuilt['evaluation']['form']['types']['order']['fields']['金额']['label'], '成交金额')   # kept per file


if __name__ == '__main__':
    unittest.main()
