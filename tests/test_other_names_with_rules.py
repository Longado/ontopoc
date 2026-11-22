"""Other names beside value rules, the OWL download and the list of questions we need.

A type's value rules and its other names are each kept by an edit that does not mention them. A type whose value rules are not known to hold is not confirmed to a
reader: its other names name it as its name does (refused before the model), and nothing tells the model or a readout it is confirmed. A rule names a column by
the column, and nothing of a rule is a name. The OWL download gives each confirmed definition's other names as skos:altLabel, declared as SKOS declares it (an
annotation property); a definition the person may not see, or one that waits, is absent with its other names. The list of questions we need asks through the
same gate, other names included."""
import json
import sqlite3

from ontology_poc_generator import accounts, other_names, workspace_questions
from ontology_poc_generator.workspace_store import open_workspace
from tests.test_derived_properties import GROSS, TICKET
from tests.test_demo_view_waits import Seeded
from tests.test_object_types import ORDER
from tests.test_one_number import Planted, Scripted, item, setUpModule, tearDownModule  # noqa: F401  (the caps of the module)
from tests.test_owl_export import SchemaCase, graph
from tests.test_workspace_questions import ALL_ORDERS, AskModel, cancelled
from unittest import TestCase, mock

RULE = [{'column': '金额', 'check': 'not_empty'}]


class RulesAndOtherNamesTests(Planted):
    def update(self, client, **change):
        now = client.get('/api/workspace/types/order')[1]
        status, body = client.post('/api/workspace/types/update', {**{k: v for k, v in ORDER.items() if k != 'enums'}, 'id': 'order', 'version': now['version'], **change})
        self.assertEqual(status, 200, body)
        return client.get('/api/workspace/types/order')[1]

    def test_an_edit_keeps_what_it_does_not_mention_each_on_its_own(self):
        with self.service(gateway=Scripted(item(ALL_ORDERS))) as (base, out):
            ann = self.team(base)['ann']
            self.assertEqual(ann.post('/api/workspace/types', {**ORDER, 'rules': RULE, 'other_names': ['销售单']})[0], 200)
            now = self.update(ann, description='说明')   # neither
            self.assertEqual(([r['column'] for r in now['rules']], now['other_names']), (['金额'], ['销售单']))
            now = self.update(ann, other_names=['单据'])   # only the other names
            self.assertEqual(([r['column'] for r in now['rules']], now['other_names']), (['金额'], ['单据']))
            now = self.update(ann, rules=[])   # only the rules
            self.assertEqual((now.get('rules'), now['other_names']), (None, ['单据']))

    def test_nothing_of_a_rule_is_a_name(self):
        content = {'name': '订单', 'english_name': 'order', 'description': '', 'dataset': '订单', 'key': ['订单号'], 'other_names': ['单据'],
                   'properties': [{'column': '订单号', 'name': '订单号', 'type': 'text', 'enum': False}, {'column': '金额', 'name': '金额', 'type': 'integer', 'enum': False}],
                   'rules': [{'column': '金额', 'check': 'gt', 'value': '大于零的金额'}]}
        texts = {e['text'] for e in other_names.entries_of('objtype:order', content)}
        self.assertEqual(texts, {'订单', 'order', '单据', '订单号', '金额'})

    def test_a_type_whose_rules_are_not_known_to_hold_is_named_by_its_other_name_and_not_told_as_confirmed(self):
        model = Scripted(item(ALL_ORDERS))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types', {**ORDER, 'rules': RULE, 'other_names': ['销售单']})[0], 200)
            self.confirm(bob, 'order', '状态码')
            self.confirm(bob, 'order')
            conn = sqlite3.connect(out / 'workspace.sqlite')   # what an older version leaves: a count kept on this version that shows a broken row
            element, dataset, rows, kept = conn.execute("SELECT element_id, dataset_id, rows_checked, samples_json FROM check_result WHERE element_id = 'objtype:order' "
                                                        "AND check_type = 'value_rules' ORDER BY id DESC LIMIT 1").fetchone()
            conn.execute("INSERT INTO check_result(element_id, check_type, query, rows_checked, violations, samples_json, status, checked_at, dataset_id, null_key_rows) "
                         "VALUES (?, 'value_rules', '', ?, 1, ?, 'failed', '2026-11-22T00:00:00+00:00', ?, NULL)", (element, rows, json.dumps({**json.loads(kept), 'broken': [1]}), dataset))
            conn.commit()
            conn.close()
            model.requests = []
            status, body = bob.post('/api/workspace/ask', {'question': '销售单有多少？'})
            self.assertEqual((status, body['status'], body['refusal']['kind'], model.requests), (200, 'refused', 'unsettled', []))
            self.assertIn('订单', body['reason'])
            told = bob.get('/api/workspace/agent/definitions')[1]
            self.assertNotIn('销售单', json.dumps(told, ensure_ascii=False))
            standing = {e['id']: e for e in bob.get('/api/workspace/agent/standing')[1]['definitions']}
            self.assertEqual((standing['objtype:order']['confirmed'], standing['objtype:order']['other_names']), (False, ['销售单']))


class NeededQuestionsTests(TestCase):
    """A run of the list of questions we need asks through `ask` with nothing kept: the demo's other names are heard there too."""

    def test_the_run_hears_other_names(self):
        demo = Seeded().__enter__()
        try:
            conn = open_workspace(demo.folder / 'workspace.sqlite')
            try:
                admin = accounts.get_user(conn, conn.execute("SELECT id FROM user WHERE username = 'demo-admin'").fetchone()[0])
                said = workspace_questions.ask(conn, None, admin, '按客户城市看有效订单金额', keep=False)   # Customer waits: refused before any model
                self.assertEqual((said['status'], said['id']), ('refused', None))
                with mock.patch.object(other_names, 'HEARD', False):
                    with self.assertRaises(workspace_questions.QaRefused):   # not heard: on to the model, and there is none here
                        workspace_questions.ask(conn, None, admin, '按客户城市看有效订单金额', keep=False)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM qa_question WHERE question = '按客户城市看有效订单金额'").fetchone()[0], 0)
            finally:
                conn.close()
        finally:
            demo.__exit__(None, None, None)


class AltLabelTests(SchemaCase):
    def named(self, team):
        ann = team['ann']
        now = ann.get('/api/workspace/types/order')[1]
        props = [{'column': p['column'], **({'enum': True} if p['enum'] else {}), **({'other_names': ['货款']} if p['column'] == '金额' else {})} for p in now['properties']]
        status, body = ann.post('/api/workspace/types/update', {'id': 'order', 'version': now['version'], 'name': now['name'], 'description': now.get('description') or '', 'dataset': now['dataset'],
                                                                'key': now['key'], 'properties': props, 'other_names': ['销售单']})
        self.assertEqual((status, body.get('state')), (200, 'confirmed'), body)
        view = ann.get('/api/workspace/types/order/views')[1]['views'][0]
        self.assertEqual(ann.post('/api/workspace/types/views/update', {'id': view['name'], 'version': view['version'], 'type': 'order', 'filters': view['filters'], 'other_names': ['好订单']})[0], 200)

    def test_confirmed_definitions_carry_their_other_names_as_skos_altlabel_declared_as_skos_declares_it(self):
        from rdflib import Literal, RDF
        from rdflib.namespace import OWL, SKOS
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            plain = self.files(out, 'bob')['ontology.ttl']
            self.assertNotIn('altLabel', plain)   # no other names: the file is as before
            self.named(team)
            onto = graph(self.files(out, 'bob')['ontology.ttl'])
            self.assertEqual(set(onto.objects(SKOS.altLabel, RDF.type)), {OWL.AnnotationProperty})   # SKOS Reference S10
            labels = {str(o) for o in onto.objects(None, SKOS.altLabel)}
            self.assertEqual(labels, {'销售单', '货款', '好订单'})
            order = next(onto.subjects(SKOS.altLabel, Literal('销售单')))
            self.assertIn((order, RDF.type, OWL.Class), onto)

    def test_words_in_a_description_do_not_make_the_file_declare_altlabel(self):
        from rdflib.namespace import SKOS
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann = team['ann']
            now = ann.get('/api/workspace/types/order')[1]
            props = [{'column': p['column'], **({'enum': True} if p['enum'] else {})} for p in now['properties']]
            status, body = ann.post('/api/workspace/types/update', {'id': 'order', 'version': now['version'], 'name': now['name'], 'description': 'see skos:altLabel for names',
                                                                    'dataset': now['dataset'], 'key': now['key'], 'properties': props})
            self.assertEqual(status, 200, body)
            text = self.files(out, 'bob')['ontology.ttl']
            self.assertIn('see skos:altLabel for names', text)   # the description is there, as text
            self.assertNotIn('skos:altLabel a ', text)           # and nothing is declared: no other name was written
            self.assertEqual(list(graph(text).subject_objects(SKOS.altLabel)), [])

    def test_hidden_and_waiting_definitions_other_names_are_absent_byte_for_byte(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, admin = team['ann'], team['admin']
            now = ann.get('/api/workspace/types/ticket')[1]
            status, body = ann.post('/api/workspace/types/update', {**TICKET, 'id': 'ticket', 'version': now['version'], 'other_names': ['维修单']})
            self.assertEqual(status, 200, body)
            self.assertEqual(ann.post('/api/workspace/types/derived', {**GROSS, 'other_names': ['税后总额']})[0], 200)   # waits: nobody confirmed it
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'ticket', 'visible_to': [ids['ann']]})[0], 200)
            self.assertIn('维修单', self.files(out, 'ann')['ontology.ttl'])
            elsewhere = self.without(out, self.on_type(out, 'ticket') | {'derived:order:gross'})
            for person in ('vera', 'bob'):
                made = self.files(out, person)
                self.assertEqual(made, self.files(out, person, elsewhere), person)
                for text in made.values():
                    for word in ('维修单', '税后总额'):
                        self.assertNotIn(word, text)
