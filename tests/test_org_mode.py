"""Organisation mode: a public research document becomes who and what the organisation is made of — units, roles,
people, duties — and how they belong, report, hold, move, answer for and work together. The vocabulary is fixed in
code; every item keeps a quote code finds in the text; a date is kept only as the text writes it; what the text says
is not known is listed, with its quote."""
import base64
import json
import unittest

from ontology_poc_generator.agent_harness import AGENTS
from ontology_poc_generator.company_documents import DOCUMENT_SYSTEM_PROMPT, load_document_file
from ontology_poc_generator.mcp_server import handle
from ontology_poc_generator.org_documents import ORG_SYSTEM_PROMPT, build_org_ontology
from ontology_poc_generator.recognition import ModelCompletion
from tests.test_ontology_ask_server import call
from tests.test_ontology_server import CSV, OntologyServerTests

TEXT = ('Echo 即 Deployment Strategist，Delta 即 Forward Deployed Software Engineer，两者都属于业务部署组织。\n\n'
        '2019年8月的采访显示，Ryan Beiermeister 此前做过 Deployment Strategist，后来担任 Gotham 产品经理。\n\n'
        '通用化与版本演进由产品负责人与 Dev 承担。公开材料仍未说明所有争议的最终裁决者。')


def entity(key, kind, name, evidence):
    return {'key': key, 'type': kind, 'name': name, 'evidence': evidence}


def fact(kind, a, b, evidence, when=None):
    return {'kind': kind, 'from': a, 'to': b, 'evidence': evidence, **({'when': when} if when else {})}


REPLY = {
    'entities': [
        entity('deployment_org', 'unit', '业务部署组织', '两者都属于业务部署组织'),
        entity('echo', 'role', 'Echo（Deployment Strategist）', 'Echo 即 Deployment Strategist'),
        entity('delta', 'role', 'Delta', 'Delta 即 Forward Deployed Software Engineer'),
        entity('ryan', 'person', 'Ryan Beiermeister', 'Ryan Beiermeister 此前做过 Deployment Strategist'),
        entity('gotham_pm', 'role', 'Gotham 产品经理', '后来担任 Gotham 产品经理'),
        entity('dev', 'role', 'Dev', '由产品负责人与 Dev 承担'),
        entity('generalize', 'duty', '通用化与版本演进', '通用化与版本演进由产品负责人与 Dev 承担'),
        entity('karp', 'person', 'Alex Karp', 'Alex Karp 是首席执行官'),          # not in the text
        entity('board', 'committee', '董事会', '两者都属于业务部署组织'),         # not in the vocabulary
    ],
    'facts': [
        fact('part_of', 'echo', 'deployment_org', '两者都属于业务部署组织'),
        fact('part_of', 'delta', 'deployment_org', '两者都属于业务部署组织'),
        fact('holds', 'ryan', 'gotham_pm', '后来担任 Gotham 产品经理', when='2019年'),
        fact('moved_to', 'ryan', 'gotham_pm', '后来担任 Gotham 产品经理', when='2021年'),   # a year the text does not have
        fact('responsible_for', 'dev', 'generalize', '通用化与版本演进由产品负责人与 Dev 承担'),
        fact('holds', 'echo', 'ryan', 'Ryan Beiermeister 此前做过 Deployment Strategist'),   # a role cannot hold a person
        fact('reports_to', 'delta', 'karp', '两者都属于业务部署组织'),                          # an end that was dropped
        fact('works_with', 'dev', 'echo', 'Dev 与 Echo 每周开会'),                              # a quote not in the text
        fact('owns', 'dev', 'echo', '由产品负责人与 Dev 承担'),                                  # not in the vocabulary
    ],
    'open': [{'text': '争议由谁最终裁决', 'evidence': '公开材料仍未说明所有争议的最终裁决者'},
             {'text': '预算归谁', 'evidence': '预算归属没有公开'}],
}


# the same text read in plain document mode, so a run there is verified too and a leaked confirmation would show
PLAIN = {'concepts': [{'key': 'product_manager', 'label': '产品经理', 'definition': '', 'evidence': '后来担任 Gotham 产品经理'}], 'relations': []}


class OrgModel:
    def __init__(self, reply=REPLY):
        self.reply, self.requests = reply, []

    def complete_json(self, *, system_prompt, user_prompt):
        self.requests.append((system_prompt, json.loads(user_prompt)))
        content = PLAIN if system_prompt == DOCUMENT_SYSTEM_PROMPT else self.reply
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(content))


def build():
    return build_org_ontology(load_document_file('palantir.md', TEXT.encode(), '理清 Palantir 的现场与产品分工'), OrgModel())


class OrgBuildTests(unittest.TestCase):
    def test_what_the_text_bears_out_is_kept_with_its_type(self):
        ontology = build()
        self.assertEqual(ontology['status'], 'auto_built_verified')
        self.assertEqual({t['key']: t['org_type'] for t in ontology['object_types']},
                         {'deployment_org': 'unit', 'echo': 'role', 'delta': 'role', 'ryan': 'person', 'gotham_pm': 'role', 'dev': 'role', 'generalize': 'duty'})
        self.assertEqual(sorted((r['kind'], r['from'], r['to']) for r in ontology['relations']),
                         [('holds', 'ryan', 'gotham_pm'), ('moved_to', 'ryan', 'gotham_pm'), ('part_of', 'delta', 'deployment_org'),
                          ('part_of', 'echo', 'deployment_org'), ('responsible_for', 'dev', 'generalize')])
        self.assertTrue(all(r['evidence'] for r in ontology['relations']))

    def test_a_date_is_kept_only_as_the_text_writes_it(self):
        when = {r['kind']: r.get('when') for r in build()['relations'] if r['from'] == 'ryan'}
        self.assertEqual(when, {'holds': '2019年', 'moved_to': None})

    def test_everything_dropped_says_why(self):
        reasons = ' | '.join(f"{r['item']}：{r['reason']}" for r in build()['rejected'])
        for said in ('Alex Karp', '董事会', 'committee', 'Echo', 'owns', '每周开会', '2021年', '预算归属'):
            self.assertIn(said, reasons)

    def test_what_the_text_says_is_not_known_is_listed(self):
        self.assertEqual(build()['open'], [{'text': '争议由谁最终裁决', 'evidence': '公开材料仍未说明所有争议的最终裁决者'}])

    def test_the_prompt_names_every_type_and_relation_code_accepts(self):
        for word in ('unit', 'role', 'person', 'duty', 'part_of', 'reports_to', 'holds', 'moved_to', 'responsible_for', 'works_with', 'open'):
            self.assertIn(word, ORG_SYSTEM_PROMPT)

    def test_it_is_a_named_agent(self):
        self.assertEqual(AGENTS['org_mapper'], '组织梳理员')


class OrgServerTests(unittest.TestCase):
    def upload(self, base, mode=None):
        payload = {'filename': 'palantir.md', 'content_base64': base64.b64encode(TEXT.encode()).decode(), **({'mode': mode} if mode else {})}
        return call(base, '/api/ontology/build', payload)

    def test_an_org_upload_is_kept_as_an_org_run_and_checked_like_a_document(self):
        with OntologyServerTests().server(gateway=OrgModel()) as (base, _):
            status, run = self.upload(base, 'org')
        self.assertEqual(status, 200, run)
        self.assertEqual((run['mode'], run['file']['kind']), ('org', 'document'))
        self.assertEqual(len(run['ontology']['open']), 1)
        self.assertIsNotNone(run['evaluation']['document_fit'])

    def test_tables_are_not_taken_in_org_mode_yet(self):
        with OntologyServerTests().server(gateway=OrgModel()) as (base, _):
            status, body = call(base, '/api/ontology/build', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode(), 'mode': 'org'})
        self.assertEqual(status, 400)
        self.assertIn('文档', body['error'])

    def test_a_confirmation_in_org_mode_does_not_follow_the_same_file_into_document_mode(self):
        with OntologyServerTests().server(gateway=OrgModel()) as (base, _):
            _, run = self.upload(base, 'org')
            decisions = {'types': {t['key']: {'verdict': 'ok'} for t in run['ontology']['object_types']}, 'relations': {}}
            self.assertEqual(call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions})[0], 200)
            _, again = self.upload(base, 'org')
            _, plain = self.upload(base)
        self.assertEqual(plain['ontology']['status'], 'auto_built_verified')
        self.assertTrue(again['evaluation'].get('reference'))
        self.assertFalse(plain['evaluation'].get('reference'))
        self.assertNotEqual(plain.get('mode'), 'org')

    def test_an_agent_can_ask_for_org_mode(self):
        tools = {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        self.assertIn('mode', tools['build_ontology']['inputSchema']['properties'])


if __name__ == '__main__':
    unittest.main()
