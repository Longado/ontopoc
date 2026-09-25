"""The ontology as a Microsoft Fabric IQ ontology definition (learn.microsoft.com/rest/api/fabric/articles/item-management/
definitions/ontology-definition): entity types with their properties and key, relationship types, and — when the person
names the workspace and lakehouse the tables were loaded into — the data bindings (which table and column fills which
property) and relationship contextualizations (which table's key columns link the two ends). The body POSTs as it is
to the create-ontology API. What a binding cannot say (a split, a nested list, a filter) is left out and named."""
import base64
import copy
import json
import re
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from ontology_poc_generator.fabric_export import fabric_files
from ontology_poc_generator.handover_form import handover_form
from ontology_poc_generator.mcp_server import handle
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests
from tests.test_ttl_export import CUSTOMERS, ONTOLOGY, ORDERS, table

NAME = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,127}$')
WORKSPACE, LAKEHOUSE = '580f410e-733d-43bd-8a87-be12b536f7ff', 'd0d863bc-48e1-45b2-8f4b-54795c97ba71'


def export(ontology=ONTOLOGY, form=None, decisions=None, **where):
    bundle = {'sources': {'orders': table(*ORDERS), 'customers': table(*CUSTOMERS)}}
    return fabric_files(ontology, bundle, handover_form(ontology, bundle), form, decisions, 'orders.csv', **where)


def parts(files):
    body = json.loads(files['fabric-ontology.json'])
    for p in body['definition']['parts']:
        assert p['payloadType'] == 'InlineBase64'
    return body, {p['path']: json.loads(base64.b64decode(p['payload'])) for p in body['definition']['parts']}


def by_name(got, folder):
    return {v['name']: v for k, v in got.items() if k.startswith(folder) and k.endswith('/definition.json')}


class DefinitionTests(unittest.TestCase):
    def test_the_body_is_what_the_create_ontology_api_takes(self):
        body, got = parts(export())
        self.assertTrue(NAME.match(body['displayName']))
        self.assertEqual(got['definition.json'], {})
        self.assertEqual(got['.platform']['metadata']['type'], 'Ontology')
        types, relations = by_name(got, 'EntityTypes/'), by_name(got, 'RelationshipTypes/')
        self.assertEqual(set(types), {'order', 'customer'})
        for t in types.values():
            self.assertEqual((t['namespace'], t['namespaceType'], t['visibility']), ('usertypes', 'Custom', 'Visible'))
            ids = {p['id'] for p in t['properties']}
            self.assertTrue(set(t['entityIdParts']) <= ids and t['displayNamePropertyId'] in ids)
            for p in t['properties']:
                self.assertTrue(NAME.match(p['name']), p['name'])
                self.assertIn(p['valueType'], ('String', 'Boolean', 'DateTime', 'Object', 'BigInt', 'Double'))
            for i in [t['id'], *ids]:
                self.assertTrue(i.isdigit() and 0 < int(i) < 2 ** 53)   # a positive 64-bit id that JavaScript reads exactly
        [placed] = relations.values()
        self.assertEqual((placed['source']['entityTypeId'], placed['target']['entityTypeId']), (types['order']['id'], types['customer']['id']))

    def test_chinese_names_stay_readable_where_fabric_allows_them(self):
        _, got = parts(export(form={'types': {'customer': {'label': '买家', 'description': '下单的公司', 'display_field': '客户名称', 'fields': {}}}}))
        customer = by_name(got, 'EntityTypes/')['customer']
        self.assertEqual(customer['semanticEnrichment']['synonyms'], ['买家'])
        self.assertEqual(customer['semanticEnrichment']['description'], '下单的公司')
        shown = next(p for p in customer['properties'] if p['id'] == customer['displayNamePropertyId'])
        self.assertEqual(shown['semanticEnrichment']['customAttributes']['column'], '客户名称')

    def test_a_column_renamed_for_fabric_keeps_its_name_in_the_description(self):
        _, got = parts(export())
        order = by_name(got, 'EntityTypes/')['order']
        renamed = [p for p in order['properties'] if p['name'] != p['semanticEnrichment']['customAttributes']['column']]
        self.assertTrue(renamed)
        for p in renamed:
            self.assertEqual(p['semanticEnrichment']['description'], p['semanticEnrichment']['customAttributes']['column'])

    def test_types_are_the_ones_the_data_holds(self):
        _, got = parts(export())
        order = by_name(got, 'EntityTypes/')['order']
        kinds = {p['semanticEnrichment']['customAttributes']['column']: p['valueType'] for p in order['properties']}
        self.assertEqual(kinds, {'订单号': 'String', '金额': 'BigInt', '下单时间': 'DateTime', '发货时间': 'DateTime'})

    def test_the_same_run_exports_the_same_ids_so_an_update_replaces_not_duplicates(self):
        self.assertEqual(export(), export())

    def test_what_a_person_judged_wrong_is_left_out(self):
        _, got = parts(export(decisions={'types': {'order': {'verdict': 'wrong'}}, 'relations': {}}))
        self.assertEqual(set(by_name(got, 'EntityTypes/')), {'customer'})
        self.assertEqual(by_name(got, 'RelationshipTypes/'), {})


class BindingTests(unittest.TestCase):
    def test_without_a_lakehouse_there_are_no_bindings_and_the_note_says_why(self):
        files = export()
        _, got = parts(files)
        self.assertFalse([k for k in got if '/DataBindings/' in k or '/Contextualizations/' in k])
        self.assertIn('Lakehouse', files['说明.md'])

    def test_each_table_an_object_is_read_from_is_one_binding(self):
        files = export(workspace=WORKSPACE, lakehouse=LAKEHOUSE)
        _, got = parts(files)
        customer = by_name(got, 'EntityTypes/')['customer']
        column = {p['id']: p['semanticEnrichment']['customAttributes']['column'] for p in customer['properties']}
        bindings = [v for k, v in got.items() if k.startswith(f"EntityTypes/{customer['id']}/DataBindings/")]
        tables = {}
        for b in bindings:
            c = b['dataBindingConfiguration']
            self.assertEqual(c['dataBindingType'], 'NonTimeSeries')
            s = c['sourceTableProperties']
            self.assertEqual((s['sourceType'], s['workspaceId'], s['itemId']), ('LakehouseTable', WORKSPACE, LAKEHOUSE))
            tables[s['sourceTableName']] = {x['sourceColumnName']: column[x['targetPropertyId']] for x in c['propertyBindings']}
        self.assertEqual(tables, {'orders': {'客户编号': '客户编号'}, 'customers': {'客户编号': '客户编号', '客户名称': '客户名称'}})
        self.assertIn('orders', files['说明.md'])

    def test_a_relation_is_linked_by_the_key_columns_of_its_table(self):
        _, got = parts(export(workspace=WORKSPACE, lakehouse=LAKEHOUSE))
        types = by_name(got, 'EntityTypes/')
        [placed] = by_name(got, 'RelationshipTypes/').values()
        [ctx] = [v for k, v in got.items() if k.startswith(f"RelationshipTypes/{placed['id']}/Contextualizations/")]
        self.assertEqual(ctx['dataBindingTable']['sourceTableName'], 'orders')
        self.assertEqual([x['sourceColumnName'] for x in ctx['sourceKeyRefBindings']], ['订单号'])
        self.assertEqual([x['targetPropertyId'] for x in ctx['sourceKeyRefBindings']], types['order']['entityIdParts'])
        self.assertEqual([x['targetPropertyId'] for x in ctx['targetKeyRefBindings']], types['customer']['entityIdParts'])

    def test_a_table_name_a_lakehouse_cannot_take_is_renamed_and_the_note_says_to_what(self):
        ontology = json.loads(json.dumps(ONTOLOGY).replace('"customers"', '"客户表"'))
        bundle = {'sources': {'orders': table(*ORDERS), '客户表': table(*CUSTOMERS)}}
        files = fabric_files(ontology, bundle, handover_form(ontology, bundle), None, None, 'orders.csv', workspace=WORKSPACE, lakehouse=LAKEHOUSE)
        _, got = parts(files)
        names = {v['dataBindingConfiguration']['sourceTableProperties']['sourceTableName'] for k, v in got.items() if '/DataBindings/' in k}
        self.assertTrue(all(NAME.match(n) for n in names))
        [renamed] = names - {'orders'}
        self.assertIn(f'客户表 → {renamed}', files['说明.md'])

    def test_what_a_binding_cannot_say_is_left_out_and_named(self):
        ontology = copy.deepcopy(ONTOLOGY)
        ontology['object_types'][1]['populated_from'][1]['transform'] = 'split_comma'
        files = fabric_files(ontology, {'sources': {'orders': table(*ORDERS), 'customers': table(*CUSTOMERS)}},
                             handover_form(ontology, {'sources': {'orders': table(*ORDERS), 'customers': table(*CUSTOMERS)}}),
                             None, None, 'orders.csv', workspace=WORKSPACE, lakehouse=LAKEHOUSE)
        _, got = parts(files)
        customer = by_name(got, 'EntityTypes/')['customer']
        tables = {v['dataBindingConfiguration']['sourceTableProperties']['sourceTableName'] for k, v in got.items()
                  if k.startswith(f"EntityTypes/{customer['id']}/DataBindings/")}
        self.assertEqual(tables, {'orders'})
        self.assertIn('customers', files['说明.md'])
        self.assertIn('逗号', files['说明.md'])

    def test_an_id_that_is_not_a_guid_is_refused(self):
        with self.assertRaises(ValueError):
            export(workspace='my workspace', lakehouse=LAKEHOUSE)
        with self.assertRaises(ValueError):
            export(workspace=WORKSPACE)   # both or neither


class ServerTests(unittest.TestCase):
    def test_a_run_downloads_the_definition_and_it_is_an_mcp_tool(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            with urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/export/fabric") as r:
                self.assertEqual(r.headers['Content-Type'], 'application/zip')
            with urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/export/fabric?format=json&workspace={WORKSPACE}&lakehouse={LAKEHOUSE}") as r:
                files = json.load(r)['files']
            _, got = parts(files)
            self.assertTrue([k for k in got if '/DataBindings/' in k])
            with self.assertRaises(HTTPError) as refused:
                urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/export/fabric?format=json&workspace=x&lakehouse=y")
            self.assertEqual(refused.exception.code, 400)
        tools = {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        self.assertEqual(set(tools['export_fabric']['inputSchema']['properties']), {'saved_as', 'workspace', 'lakehouse'})


if __name__ == '__main__':
    unittest.main()
