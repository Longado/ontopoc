"""What a person confirmed is what every consumer uses, and what a person decided is never silently carried over wrong:
an object or relation judged wrong is out of the questions and of every export; a rule that no longer finds its object
or field says it cannot be checked instead of "kept"; a confirmed relation is prefilled only in the same direction;
and an agent can say, as the page can, that an upload is the next version of an earlier run."""
import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import urlopen

from ontology_poc_generator import mcp_server
from ontology_poc_generator.mcp_server import ToolError, handle
from ontology_poc_generator.ontology_confirm import prefill_from_reference, without_wrong
from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
from ontology_poc_generator.rule_discovery import check_rules
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, PROPOSAL, OntologyServerTests

WRONG_CUSTOMER = {'types': {'order': {'verdict': 'ok'}, 'customer': {'verdict': 'wrong'}}, 'relations': {}}


class WithoutWrongTests(unittest.TestCase):
    def test_a_wrong_object_goes_with_its_relations_and_a_wrong_relation_goes_alone(self):
        ontology = copy.deepcopy(PROPOSAL)
        kept = without_wrong(ontology, WRONG_CUSTOMER)
        self.assertEqual([t['key'] for t in kept['object_types']], ['order'])
        self.assertEqual(kept['relations'], [])
        only_relation = without_wrong(ontology, {'types': {}, 'relations': {'order_customer': {'verdict': 'wrong'}}})
        self.assertEqual(([t['key'] for t in only_relation['object_types']], only_relation['relations']), (['order', 'customer'], []))
        self.assertEqual(ontology, PROPOSAL)   # a copy, never the stored draft
        self.assertEqual(without_wrong(ontology, None), ontology)


class Recording(QuestionModel):
    def __init__(self):
        self.asked = []

    def complete_json(self, *, system_prompt, user_prompt):
        if system_prompt == QUESTION_SYSTEM_PROMPT:
            self.asked.append(user_prompt)
        return super().complete_json(system_prompt=system_prompt, user_prompt=user_prompt)


class ServerTests(unittest.TestCase):
    def test_after_a_person_judges_an_object_wrong_questions_and_exports_leave_it_out(self):
        model = Recording()
        with OntologyServerTests().server(gateway=model) as (base, _):
            _, run = call(base, '/api/ontology/build', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            status, body = call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': WRONG_CUSTOMER})
            self.assertEqual(status, 200, body)
            model.asked.clear()
            call(base, '/api/ontology/ask', {'saved_as': run['saved_as'], 'question': '每个订单多少钱？'})
            self.assertEqual(len(model.asked), 1)
            self.assertNotIn('"customer"', model.asked[0])
            self.assertIn('"order"', model.asked[0])
            for kind in ('forms', 'ttl'):
                with urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/export/{kind}?format=json") as r:
                    files = json.load(r)['files']
                text = ' '.join(files) + ' '.join(files.values())
                self.assertNotIn('customer', text, kind)


class RuleTests(unittest.TestCase):
    BUNDLE = {'sources': {'orders': {'records': [{'订单号': 'O1', '客户编号': 'C1', '金额': '100'}], 'requests': []}}}

    def test_a_rule_whose_object_is_gone_cannot_be_checked_and_says_why(self):
        [rule] = check_rules(PROPOSAL, self.BUNDLE, [{'id': 'required:vendor:名称', 'kind': 'required', 'type': 'vendor', 'field': '名称'}])
        self.assertIsNone(rule['violations'])
        self.assertIn('vendor', rule['unchecked'])

    def test_a_rule_whose_field_is_gone_cannot_be_checked_either(self):
        [rule] = check_rules(PROPOSAL, self.BUNDLE, [{'id': 'required:order:备注', 'kind': 'required', 'type': 'order', 'field': '备注'}])
        self.assertIsNone(rule['violations'])
        self.assertIn('备注', rule['unchecked'])

    def test_a_rule_that_still_applies_is_checked_as_before(self):
        [rule] = check_rules(PROPOSAL, self.BUNDLE, [{'id': 'required:order:金额', 'kind': 'required', 'type': 'order', 'field': '金额'}])
        self.assertEqual((rule['violations'], rule.get('unchecked')), ({'count': 0, 'examples': []}, None))


class PrefillTests(unittest.TestCase):
    def test_a_confirmed_relation_is_prefilled_only_in_the_same_direction(self):
        reference = copy.deepcopy(PROPOSAL)
        turned = copy.deepcopy(PROPOSAL)
        turned['relations'] = [{'key': 'customer_order', 'from': 'customer', 'to': 'order', 'source': 'orders', 'meaning': '客户拥有订单'}]
        self.assertEqual(prefill_from_reference(turned, reference)['relations'], {})
        self.assertEqual(prefill_from_reference(copy.deepcopy(PROPOSAL), reference)['relations'], {'order_customer': {'verdict': 'ok'}})


class McpVersionTests(unittest.TestCase):
    def test_an_agent_can_say_an_upload_is_the_next_version_of_an_earlier_run(self):
        tools = {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        self.assertIn('previous', tools['build_ontology']['inputSchema']['properties'])

        class Session:
            poll_seconds = 0
            sent = []

            def request(self, path, payload=None):
                self.sent.append((path, payload))
                return {'job_id': 'j1'} if path == '/api/ontology/jobs' else {'state': 'failed', 'error': 'stop here'}

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'orders.csv'
            path.write_bytes(CSV)
            session = Session()
            with self.assertRaises(ToolError):
                mcp_server.build_ontology(session, {'files': [str(path)], 'previous': '20260919-orders.json'})
        self.assertEqual(session.sent[0][1]['previous'], '20260919-orders.json')


if __name__ == '__main__':
    unittest.main()
