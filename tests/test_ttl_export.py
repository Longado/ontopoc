"""The ontology as RDF, for the three things the standard is for: exchange (any OWL tool reads the classes, fields,
relations and keys), merge (the same thing gets the same name, across tables and across versions of the file) and
checking (adopted rules become SHACL shapes a generic validator enforces)."""
import base64
import io
import json
import unittest
import zipfile
from urllib.request import urlopen

from ontology_poc_generator.handover_form import handover_form
from ontology_poc_generator.mcp_server import handle
from ontology_poc_generator.ttl_export import ttl_files
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests

try:
    import pyshacl
    from rdflib import Graph, Literal, Namespace, URIRef
    from rdflib.collection import Collection
    from rdflib.namespace import OWL, RDF, RDFS, XSD
except ImportError:   # CI installs .[check]; a bare checkout skips only the tests that read the RDF back
    Graph = None


def table(*rows):
    header, *data = rows
    return {'records': [dict(zip(header, r)) for r in data], 'requests': []}


ORDERS = [('订单号', '客户编号', '金额', '下单时间', '发货时间'),
          ('O1', 'C1', '100', '2024-01-05 10:30', '2024-01-06 09:00'),
          ('O2', 'C2', '50', '2024-02-01 08:00', '2024-02-03 17:45'),
          ('O3', 'C1', '75', '2024-03-10 12:00', '2024-03-11 12:00')]
CUSTOMERS = [('客户编号', '客户名称'), ('C1', '甲公司'), ('C2', '乙公司')]
ONTOLOGY = {
    'object_types': [
        {'key': 'order', 'label': '订单', 'populated_from': [{'source': 'orders', 'identity': {'id': '订单号'}}],
         'attributes': [{'source': 'orders', 'path': p} for p in ('金额', '下单时间', '发货时间')]},
        {'key': 'customer', 'label': '客户', 'populated_from': [{'source': 'orders', 'identity': {'id': '客户编号'}}, {'source': 'customers', 'identity': {'id': '客户编号'}}],
         'attributes': [{'source': 'customers', 'path': '客户名称'}]},
    ],
    'relations': [{'key': 'placed_by', 'from': 'order', 'to': 'customer', 'source': 'orders', 'label': '属于'}],
    'ignored_fields': [], 'open_questions': [],
}
RULES = [{'id': 'required:customer:客户名称', 'kind': 'required', 'type': 'customer', 'field': '客户名称'},
         {'id': 'order:order:下单时间:发货时间', 'kind': 'order', 'type': 'order', 'before': '下单时间', 'after': '发货时间'}]
BASE = 'urn:ontopoc:abc123/'


def export(orders=ORDERS, decisions=None, rules=RULES, base=BASE):
    bundle = {'sources': {'orders': table(*orders), 'customers': table(*CUSTOMERS)}}
    return ttl_files(ONTOLOGY, bundle, handover_form(ONTOLOGY, bundle), None, decisions, rules, base)


def parsed(text):
    return Graph().parse(data=text, format='turtle')


@unittest.skipIf(Graph is None, 'rdflib and pyshacl are not installed (pip install -e ".[check]")')
class ExchangeTests(unittest.TestCase):
    def test_objects_fields_relations_and_keys_are_owl_any_tool_reads(self):
        g = parsed(export()['ontology.ttl'])
        S = Namespace(BASE)
        order, customer, placed = S['order'], S['customer'], S['rel/placed_by']
        self.assertEqual({order, customer}, set(g.subjects(RDF.type, OWL.Class)))
        self.assertEqual(g.value(customer, RDFS.label), Literal('客户', lang='zh'))
        self.assertEqual((g.value(placed, RDFS.domain), g.value(placed, RDFS.range)), (order, customer))
        self.assertIn((placed, RDF.type, OWL.ObjectProperty), g)
        self.assertEqual(list(Collection(g, g.value(customer, OWL.hasKey))), [S['customer/%E5%AE%A2%E6%88%B7%E7%BC%96%E5%8F%B7']])
        self.assertEqual(g.value(S['order/%E9%87%91%E9%A2%9D'], RDFS.range), XSD.integer)

    def test_what_a_person_judged_wrong_is_left_out_and_their_names_are_used(self):
        decisions = {'types': {'customer': {'verdict': 'ok', 'label': '买家'}, 'order': {'verdict': 'wrong'}}, 'relations': {}}
        files = export(decisions=decisions)
        g = parsed(files['ontology.ttl'])
        self.assertEqual([str(x) for x in g.subjects(RDF.type, OWL.Class)], [BASE + 'customer'])
        self.assertEqual(g.value(URIRef(BASE + 'customer'), RDFS.label), Literal('买家', lang='zh'))
        self.assertEqual(set(g.subjects(RDF.type, OWL.ObjectProperty)), set())   # its relation had the wrong object at one end
        self.assertNotIn('order', ' '.join(str(s) for s in parsed(files['data.ttl']).subjects()))


@unittest.skipIf(Graph is None, 'rdflib and pyshacl are not installed (pip install -e ".[check]")')
class MergeTests(unittest.TestCase):
    def test_a_customer_in_two_tables_is_one_node_with_facts_from_both(self):
        g = parsed(export()['data.ttl'])
        c1 = URIRef(BASE + 'data/customer/C1')
        self.assertEqual(g.value(c1, URIRef(BASE + 'customer/%E5%AE%A2%E6%88%B7%E5%90%8D%E7%A7%B0')), Literal('甲公司'))
        self.assertEqual(sorted(str(s) for s in g.subjects(URIRef(BASE + 'rel/placed_by'), c1)), [BASE + 'data/order/O1', BASE + 'data/order/O3'])
        self.assertEqual(len(set(g.subjects(RDF.type, URIRef(BASE + 'customer')))), 2)

    def test_a_new_version_names_the_same_things_the_same_way_so_the_two_merge(self):
        newer = ORDERS + [('O4', 'C2', '20', '2024-04-01 09:00', '2024-04-02 09:00')]
        both = parsed(export()['data.ttl']) + parsed(export(orders=newer)['data.ttl'])
        self.assertEqual(len(set(both.subjects(RDF.type, URIRef(BASE + 'order')))), 4)
        self.assertEqual(len(set(both.subjects(RDF.type, URIRef(BASE + 'customer')))), 2)

    def test_times_are_typed_so_they_compare_as_times(self):
        g = parsed(export()['data.ttl'])
        value = g.value(URIRef(BASE + 'data/order/O1'), URIRef(BASE + 'order/%E4%B8%8B%E5%8D%95%E6%97%B6%E9%97%B4'))
        self.assertEqual((str(value), value.datatype), ('2024-01-05T10:30:00', XSD.dateTime))

    def test_times_with_fractions_of_a_second_are_typed_too(self):
        exported = [('订单号', '客户编号', '金额', '下单时间', '发货时间'), ('O1', 'C1', '100', '2024-01-05T10:30:00.000', '2024-01-06T09:00:00.000')]
        g = parsed(export(orders=exported)['data.ttl'])
        value = g.value(URIRef(BASE + 'data/order/O1'), URIRef(BASE + 'order/%E4%B8%8B%E5%8D%95%E6%97%B6%E9%97%B4'))
        self.assertEqual((str(value), value.datatype), ('2024-01-05T10:30:00.000', XSD.dateTime))


@unittest.skipIf(Graph is None, 'rdflib and pyshacl are not installed (pip install -e ".[check]")')
class CheckTests(unittest.TestCase):
    def validate(self, files):
        conforms, report, _ = pyshacl.validate(parsed(files['data.ttl']), shacl_graph=parsed(files['shapes.ttl']))
        return conforms, sorted(str(o) for o in report.objects(None, URIRef('http://www.w3.org/ns/shacl#focusNode')))

    def test_adopted_rules_hold_on_the_data_they_were_found_in(self):
        self.assertEqual(self.validate(export()), (True, []))

    def test_a_generic_validator_names_what_breaks_them(self):
        broken = ORDERS[:3] + [('O3', 'C3', '75', '2024-03-10 12:00', '2024-03-09 12:00')]
        self.assertEqual(self.validate(export(orders=broken)), (False, [BASE + 'data/customer/C3', BASE + 'data/order/O3']))

    def test_without_adopted_rules_there_is_no_shapes_file(self):
        self.assertNotIn('shapes.ttl', export(rules=[]))


class ServerTests(unittest.TestCase):
    def test_a_kept_run_downloads_as_a_zip_and_is_an_mcp_tool(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            with urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/export/ttl") as r:
                self.assertEqual(r.headers['Content-Type'], 'application/zip')
                names = zipfile.ZipFile(io.BytesIO(r.read())).namelist()
            self.assertEqual(sorted(names), ['data.ttl', 'ontology.ttl'])
            with urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/export/ttl?format=json") as r:
                files = json.load(r)['files']
            self.assertIn(f"urn:ontopoc:{run['file']['sha256']}/", files['ontology.ttl'])
        tools = {t['name'] for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        self.assertIn('export_ttl', tools)


if __name__ == '__main__':
    unittest.main()
