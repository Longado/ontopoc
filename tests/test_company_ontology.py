import copy
import json
import unittest

from ontology_poc_generator.company_ontology import (
    COMPANY_PROMPT_VERSION, COMPANY_SYSTEM_PROMPT, build_company_ontology, verify_company_proposal,
)
from ontology_poc_generator.recognition import ModelCompletion

BUNDLE = {
    'schema': 'company_source_bundle.v1', 'decision': '描述这家公司的业务',
    'file': {'name': 'demo.xlsx', 'sha256': 'a' * 64, 'kind': 'table'},
    'sources': {
        '客户': {'records': [{'客户编号': 'C1', '名称': '甲', '城市': '苏州'}, {'客户编号': 'C2', '名称': '乙', '城市': '无锡'},
                           {'客户编号': 'C2', '名称': '乙', '城市': '常州'}], 'requests': []},
        '订单': {'records': [{'订单号': 'O1', '客户编号': 'C1', '金额': '100', '下单日期': '2026-01-02'},
                           {'订单号': 'O2', '客户编号': 'C2', '金额': '50', '下单日期': '2026-01-03'},
                           {'订单号': 'O3', '客户编号': 'C9', '金额': '70', '下单日期': '2026-01-04'}], 'requests': []},
    },
}

PROPOSAL = {
    'reasoning': 'orders reference customers by 客户编号',
    'object_types': [
        {'key': 'customer', 'label': '客户', 'populated_from': [
            {'source': '客户', 'identity': {'customer_id': '客户编号'}}, {'source': '订单', 'identity': {'customer_id': '客户编号'}}],
         'attributes': [{'source': '客户', 'path': '名称'}, {'source': '客户', 'path': '城市'}], 'rationale': 'r'},
        {'key': 'order', 'label': '订单', 'populated_from': [{'source': '订单', 'identity': {'order_id': '订单号'}}],
         'attributes': [{'source': '订单', 'path': '金额'}], 'time_field': {'source': '订单', 'path': '下单日期'}, 'rationale': 'r'},
    ],
    'relations': [{'key': 'order_customer', 'from': 'order', 'to': 'customer', 'source': '订单', 'meaning': '订单属于客户'}],
    'ignored_fields': [],
    'open_questions': ['订单没有产品明细'],
}


class Reply:
    def __init__(self, *contents):
        self.contents = list(contents)
        self.prompts = []

    def complete_json(self, *, system_prompt, user_prompt):
        self.prompts.append((system_prompt, json.loads(user_prompt)))
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(self.contents.pop(0)))


class CompanyOntologyTests(unittest.TestCase):
    def test_a_company_ontology_needs_no_recall_roles(self):
        self.assertEqual(verify_company_proposal(PROPOSAL, BUNDLE)['errors'], [])

    def test_code_still_catches_missing_fields_and_relations_that_link_nothing(self):
        broken = copy.deepcopy(PROPOSAL)
        broken['object_types'][1]['attributes'] = []
        broken['relations'].append({'key': 'customer_order_self', 'from': 'customer', 'to': 'customer', 'source': '客户', 'meaning': 'x'})
        codes = {e['code'] for e in verify_company_proposal(broken, BUNDLE)['errors']}
        self.assertIn('field_unaccounted', codes)

    def test_errors_go_back_to_the_model_and_the_result_records_the_contract(self):
        first = copy.deepcopy(PROPOSAL)
        first['object_types'][1]['attributes'] = []
        gateway = Reply(first, PROPOSAL)
        ontology = build_company_ontology(BUNDLE, gateway)
        self.assertEqual(ontology['status'], 'auto_built_verified')
        self.assertEqual(ontology['schema'], 'company_ontology.v1')
        self.assertEqual(ontology['prompt_version'], COMPANY_PROMPT_VERSION)
        self.assertEqual(len(ontology['attempts']), 2)
        self.assertEqual(gateway.prompts[0][0], COMPANY_SYSTEM_PROMPT)
        self.assertIn('errors_found_by_code', gateway.prompts[1][1])
        self.assertEqual(ontology['data_gaps'], ['订单没有产品明细'])
        self.assertNotIn('role', json.dumps(COMPANY_SYSTEM_PROMPT).lower().replace('roles', ''))

    def test_the_model_sees_field_names_and_examples_not_whole_files(self):
        gateway = Reply(PROPOSAL)
        build_company_ontology(BUNDLE, gateway)
        sent = gateway.prompts[0][1]
        self.assertEqual(sent['sources']['订单']['record_count'], 3)
        self.assertLessEqual(len(sent['sources']['订单']['fields']['订单号']), 3)


if __name__ == '__main__':
    unittest.main()
