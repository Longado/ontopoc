"""Organisation maps the way a report draws them: who hands what to whom (a phrase on the arrow, grounded by a quote),
a membership tree and a collaboration flow exported as Mermaid for the report's own diagram pipeline, and a period
filter so each stage of the organisation gets its own picture."""
import base64
import json
import unittest
from urllib.request import urlopen

from ontology_poc_generator.company_documents import load_document_file
from ontology_poc_generator.mcp_server import handle
from ontology_poc_generator.org_documents import build_org_ontology, org_mermaid
from tests.test_ontology_ask_server import call
from tests.test_ontology_server import OntologyServerTests
from tests.test_org_mode import OrgModel, entity, fact

TEXT = ('2019年官方披露：Dev 属于 Product Development，Delta 属于 Business Development。\n\n'
        '现场项目团队向产品协作团队提交功能论证与候选代码，产品团队回以路线协调与代码评审。\n\n'
        '2023年起，客户与工程师在 Bootcamp 中共同构建初始应用。')

REPLY = {
    'entities': [
        entity('pd', 'unit', 'Product Development', 'Dev 属于 Product Development'),
        entity('bd', 'unit', 'Business Development', 'Delta 属于 Business Development'),
        entity('dev', 'role', 'Dev', 'Dev 属于 Product Development'),
        entity('delta', 'role', 'Delta', 'Delta 属于 Business Development'),
        entity('field', 'unit', '现场项目团队', '现场项目团队向产品协作团队提交功能论证与候选代码'),
        entity('product', 'unit', '产品协作团队', '现场项目团队向产品协作团队提交功能论证与候选代码'),
        entity('customer', 'unit', '客户', '客户与工程师在 Bootcamp 中共同构建初始应用'),
        entity('engineer', 'role', '工程师', '客户与工程师在 Bootcamp 中共同构建初始应用'),
    ],
    'facts': [
        fact('part_of', 'dev', 'pd', 'Dev 属于 Product Development', when='2019年'),
        fact('part_of', 'delta', 'bd', 'Delta 属于 Business Development', when='2019年'),
        {**fact('hands_to', 'field', 'product', '现场项目团队向产品协作团队提交功能论证与候选代码'), 'what': '功能论证与候选代码'},
        {**fact('hands_to', 'product', 'field', '产品团队回以路线协调与代码评审'), 'what': '路线协调与代码评审'},
        {**fact('works_with', 'customer', 'engineer', '客户与工程师在 Bootcamp 中共同构建初始应用', when='2023年'), 'what': '共同构建初始应用'},
    ],
    'open': [],
}


def build():
    return build_org_ontology(load_document_file('palantir.md', TEXT.encode(), ''), OrgModel(REPLY))


class HandoffTests(unittest.TestCase):
    def test_a_handoff_keeps_its_direction_and_what_is_handed_over(self):
        handoffs = {(r['from'], r['to']): r['what'] for r in build()['relations'] if r['kind'] == 'hands_to'}
        self.assertEqual(handoffs, {('field', 'product'): '功能论证与候选代码', ('product', 'field'): '路线协调与代码评审'})

    def test_what_is_handed_over_is_a_short_phrase_or_nothing(self):
        long = {**REPLY, 'facts': [{**REPLY['facts'][2], 'what': '很' * 80}]}
        [r] = build_org_ontology(load_document_file('p.md', TEXT.encode(), ''), OrgModel(long))['relations']
        self.assertIsNone(r['what'])


class MermaidTests(unittest.TestCase):
    def test_the_membership_tree_and_the_collaboration_flow_are_mermaid(self):
        files = org_mermaid(build())
        tree, flow = files['组织隶属.mmd'], files['协作交接.mmd']
        self.assertTrue(tree.startswith('flowchart TB'))
        self.assertIn('Product Development', tree)
        self.assertNotIn('功能论证', tree)
        self.assertTrue(flow.startswith('flowchart LR'))
        self.assertIn('-->|"功能论证与候选代码"|', flow)
        self.assertIn('<-->|"共同构建初始应用"|', flow)
        self.assertNotIn('Product Development', flow)

    def test_a_period_keeps_what_it_dates_inside_it_and_what_is_undated(self):
        flow = org_mermaid(build(), years=(2016, 2022))['协作交接.mmd']
        self.assertIn('功能论证与候选代码', flow)          # undated: kept in every period
        self.assertNotIn('共同构建初始应用', flow)          # 2023: outside
        self.assertIn('Product Development', org_mermaid(build(), years=(2016, 2022))['组织隶属.mmd'])
        self.assertNotIn('Product Development', org_mermaid(build(), years=(2023, 2026))['组织隶属.mmd'])

    def test_what_a_person_judged_wrong_is_not_drawn_and_labels_cannot_break_the_syntax(self):
        ontology = build()
        ontology['object_types'][0]['label'] = 'Product "Dev" [core]'
        tree = org_mermaid(ontology)['组织隶属.mmd']
        self.assertNotIn('Product "Dev"', tree)   # a quote inside a label would end it early
        self.assertNotIn('[core]', tree)
        flow = org_mermaid(ontology, decisions={'types': {'field': {'verdict': 'wrong'}}, 'relations': {}})['协作交接.mmd']
        self.assertNotIn('现场项目团队', flow)


class MermaidServerTests(unittest.TestCase):
    def test_an_org_run_exports_mermaid_and_so_can_an_agent(self):
        with OntologyServerTests().server(gateway=OrgModel(REPLY)) as (base, _):
            _, run = call(base, '/api/ontology/build', {'filename': 'palantir.md', 'content_base64': base64.b64encode(TEXT.encode()).decode(), 'mode': 'org'})
            with urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/export/mermaid?format=json&years=2023-2026") as r:
                files = json.load(r)['files']
        self.assertEqual(sorted(files), ['协作交接.mmd', '组织隶属.mmd'])
        self.assertIn('共同构建初始应用', files['协作交接.mmd'])
        self.assertIn('功能论证与候选代码', files['协作交接.mmd'])   # undated, so in every period
        tools = {t['name'] for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        self.assertIn('export_mermaid', tools)


if __name__ == '__main__':
    unittest.main()
