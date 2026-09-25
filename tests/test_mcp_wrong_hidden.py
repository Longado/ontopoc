"""An agent reading the ontology through MCP gets what the person kept, as the page, the questions and the exports do:
objects and relations judged wrong are left out by default and named, so nothing disappears silently; asking for them
explicitly shows everything with its verdict."""
import copy
import unittest

from ontology_poc_generator import mcp_server
from ontology_poc_generator.mcp_server import handle
from tests.test_ontology_server import PROPOSAL


class Session:
    def __init__(self, decisions):
        self.data = {'saved_as': 'r.json', 'ontology': copy.deepcopy(PROPOSAL), 'evaluation': {}, 'confirmation': {'decisions': decisions}}

    def run(self, saved_as):
        return self.data


WRONG = {'types': {'order': {'verdict': 'ok'}, 'customer': {'verdict': 'wrong'}}, 'relations': {}}


class HiddenTests(unittest.TestCase):
    def test_what_was_judged_wrong_is_left_out_and_named(self):
        objects = mcp_server.list_objects(Session(WRONG), {'saved_as': 'r.json'})
        self.assertEqual([o['key'] for o in objects['objects']], ['order'])
        self.assertEqual(objects['left_out'], [{'key': 'customer', 'label': '客户', 'verdict': 'wrong'}])
        relations = mcp_server.list_relations(Session(WRONG), {'saved_as': 'r.json'})
        self.assertEqual(relations['relations'], [])
        self.assertEqual([r['key'] for r in relations['left_out']], ['order_customer'])   # its other end was judged wrong

    def test_asked_for_explicitly_everything_comes_with_its_verdict(self):
        objects = mcp_server.list_objects(Session(WRONG), {'saved_as': 'r.json', 'include_wrong': True})
        self.assertEqual({o['key']: o['verdict'] for o in objects['objects']}, {'order': 'ok', 'customer': 'wrong'})
        relations = mcp_server.list_relations(Session(WRONG), {'saved_as': 'r.json', 'include_wrong': True})
        self.assertEqual([r['key'] for r in relations['relations']], ['order_customer'])

    def test_nothing_is_left_out_before_anything_is_judged(self):
        objects = mcp_server.list_objects(Session({}), {'saved_as': 'r.json'})
        self.assertEqual((len(objects['objects']), objects['left_out']), (2, []))

    def test_a_rerun_shows_the_last_judgement_of_the_file(self):
        session = Session({})
        session.data['confirmation'] = None
        session.data['evaluation'] = {'reference': {'suggested': {'types': {'customer': {'verdict': 'wrong'}}, 'relations': {'order_customer': {'verdict': 'wrong'}}}}}
        objects = mcp_server.list_objects(session, {'saved_as': 'r.json', 'include_wrong': True})
        self.assertEqual({o['key']: o['last_time'] for o in objects['objects']}, {'order': None, 'customer': 'wrong'})
        relations = mcp_server.list_relations(session, {'saved_as': 'r.json', 'include_wrong': True})
        self.assertEqual([r['last_time'] for r in relations['relations']], ['wrong'])

    def test_the_tools_say_they_can_include_what_was_judged_wrong(self):
        tools = {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        for name in ('list_objects', 'list_relations'):
            self.assertIn('include_wrong', tools[name]['inputSchema']['properties'])


if __name__ == '__main__':
    unittest.main()
