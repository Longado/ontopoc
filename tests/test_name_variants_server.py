import base64
import json
import unittest

from ontology_poc_generator.recognition import ModelCompletion
from tests.test_ontology_ask_server import call
from tests.test_ontology_server import OntologyServerTests

ROWS = '名称,城市\n苏州某某机械有限公司,苏州\n苏州某某机械,苏州\n无锡别的公司,无锡\n'.encode('utf-8')
PROPOSAL = {'reasoning': 'r', 'ignored_fields': [], 'open_questions': [],
            'object_types': [{'key': 'customer', 'label': '客户', 'populated_from': [{'source': '客户', 'identity': {'name': '名称'}}],
                              'attributes': [{'source': '客户', 'path': '城市'}], 'rationale': 'r'}],
            'relations': []}
VARIANTS = {'groups': [{'type': 'customer', 'values': ['苏州某某机械有限公司', '苏州某某机械'], 'reasoning': '全称和简称'}]}


class Model:
    """Builds the ontology, then proposes which names denote the same thing."""

    def complete_json(self, *, system_prompt, user_prompt):
        reply = VARIANTS if '写法' in system_prompt or 'variant' in system_prompt.lower() else PROPOSAL
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(reply, ensure_ascii=False))


class VariantServerTests(unittest.TestCase):
    def test_a_consultant_asks_for_candidates_and_gets_them_with_their_evidence(self):
        with OntologyServerTests().server(gateway=Model()) as (base, _):
            _, run = call(base, '/api/ontology/build', {'filename': '客户.csv', 'content_base64': base64.b64encode(ROWS).decode()})
            status, out = call(base, '/api/ontology/variants', {'saved_as': run['saved_as']})
        self.assertEqual(status, 200, out)
        variants = out['evaluation']['variants']
        self.assertEqual(variants['groups'][0]['values'], ['苏州某某机械', '苏州某某机械有限公司'])
        self.assertEqual(variants['groups'][0]['records'], [1, 1])
        self.assertEqual(variants['groups'][0]['verdict'], 'needs_person')
        self.assertEqual(variants['rejected'], [])
        self.assertIn('model', variants)

    def test_a_file_with_nothing_to_match_says_so_instead_of_calling_the_model(self):
        rows = ('编号,名称\n' + ''.join(f'C{i},公司{i}\n' for i in range(250))).encode('utf-8')
        proposal = {**PROPOSAL, 'object_types': [{**PROPOSAL['object_types'][0],
                                                  'populated_from': [{'source': '客户', 'identity': {'id': '编号'}}],
                                                  'attributes': [{'source': '客户', 'path': '名称'}]}]}

        class ByNumber(Model):
            def complete_json(self, *, system_prompt, user_prompt):
                if '写法' in system_prompt:
                    raise AssertionError('should not ask the model when nothing can be matched')
                return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(proposal, ensure_ascii=False))

        with OntologyServerTests().server(gateway=ByNumber()) as (base, _):
            _, run = call(base, '/api/ontology/build', {'filename': '客户.csv', 'content_base64': base64.b64encode(rows).decode()})
            _, out = call(base, '/api/ontology/variants', {'saved_as': run['saved_as']})
        self.assertEqual(out['evaluation']['variants']['groups'], [])
        self.assertIn('取值太多', out['evaluation']['variants']['note'])


if __name__ == '__main__':
    unittest.main()
