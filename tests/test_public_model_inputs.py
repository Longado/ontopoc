import copy
import io
import json
from pathlib import Path
import unittest

from ontology_poc_generator.model_gateway import OpenAICompatibleGateway
from ontology_poc_generator.public_ontology import MODELER_SYSTEM_PROMPT, auto_build_ontology
from ontology_poc_generator.public_scope import check_candidates, scope
from ontology_poc_generator.recognition import ModelCompletion

FIXTURES = Path(__file__).resolve().parent / 'fixtures/nhtsa'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class Sequence:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def complete_json(self, *, system_prompt, user_prompt):
        self.requests.append(json.loads(user_prompt))
        reply = self.replies.pop(0)
        return ModelCompletion(provider='fake', model='m', content=reply if isinstance(reply, str) else json.dumps(reply))


class ModelInputTests(unittest.TestCase):
    def setUp(self):
        self.bundle = load('mini_bundle.json')
        self.reference = load('reference_proposal.json')

    def test_matcher_sees_recall_part_and_complaint_parts(self):
        ontology = auto_build_ontology(self.bundle, Sequence([self.reference]))
        result = scope(ontology, self.bundle, {'campaign_number': '21V650000'})
        gw = Sequence([{'results': []}])
        check_candidates(result, ontology, self.bundle, gw)
        request = gw.requests[0]
        self.assertEqual(request['recall_component'], ['ELECTRICAL SYSTEM:PROPULSION SYSTEM:TRACTION BATTERY'])
        fire = next(i for i in request['complaints'] if i['id'] == '11600123')
        self.assertEqual(fire['parts'], ['ELECTRICAL SYSTEM', 'SEATS', 'UNKNOWN OR OTHER'])

    def test_modeler_stops_after_three_attempts_even_while_improving(self):
        def missing(n):
            p = copy.deepcopy(self.reference)
            drop = ['complaint_is_about_model_year', 'complaint_flags_component', 'recall_targets_component'][:n]
            p['relations'] = [r for r in p['relations'] if r['key'] not in drop]
            return p
        gw = Sequence([missing(3), missing(2), missing(1), self.reference])
        ontology = auto_build_ontology(self.bundle, gw)
        self.assertEqual(len(gw.requests), 3)
        self.assertEqual(ontology['status'], 'blocked')

    def test_modeler_prompt_asks_for_time_fields_and_filters(self):
        self.assertIn('time_field', MODELER_SYSTEM_PROMPT)
        self.assertIn('where', MODELER_SYSTEM_PROMPT)


class GatewayTemperatureTests(unittest.TestCase):
    def body(self, **kw):
        sent = {}

        class Reply(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def opener(request, timeout):
            sent.update(json.loads(request.data))
            return Reply(json.dumps({'model': 'm', 'choices': [{'message': {'content': '{}'}}]}).encode())

        OpenAICompatibleGateway(api_base='https://x', api_key='k', model='m', opener=opener, **kw) \
            .complete_json(system_prompt='s', user_prompt='u')
        return sent

    def test_temperature_is_sent_only_when_set(self):
        self.assertNotIn('temperature', self.body())
        self.assertEqual(self.body(temperature=0)['temperature'], 0)


if __name__ == '__main__':
    unittest.main()
