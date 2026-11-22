"""The confirmed definitions as OWL and SHACL, schema only: GET /api/workspace/agent/schema gives, as the signed-in person or the token's owner, a Turtle file of the
ontology (classes, properties, keys, relations, code meanings as SKOS, views and derived properties as annotated text) and a Turtle file of SHACL shapes for what
code already checks. Both files are read back with rdflib, and the shapes are run with pyshacl over a few objects written inside the test (never over the data).
A person who may not see a definition gets the same bytes as from a workspace where it does not exist."""
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from unittest import mock
from urllib.request import Request, urlopen
import zipfile

from ontology_poc_generator import owl_export
from ontology_poc_generator.accounts import get_user
from ontology_poc_generator.workspace_store import open_workspace
from tests.test_access import Client
from tests.test_agent_access import AgentCase
from tests.test_derived_properties import CANCELLED, COMMIT, CUSTOMER, GROSS, ORDER, PRODUCT, RELATIONS, STOCK, TICKET
from tests.test_explorer import CUSTOMERS, ORDERS
from tests.test_object_relations import table_csv
from tests.test_object_types import LATEST_STOCK, VALID, shifted_orders_csv
from tests.test_workspace_questions import AskModel, cancelled

try:
    import pyshacl
    from rdflib import BNode, Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD
    from rdflib.collection import Collection
    from rdflib.namespace import OWL, SKOS
except ImportError:   # the `check` extra is not installed: these tests are skipped, as the earlier screen's Turtle tests are
    pyshacl = None

SCHEMA = '/api/workspace/agent/schema'
STANDING = '/api/workspace/agent/standing'
MADE = datetime(2026, 11, 22, 8, 0, 0, tzinfo=timezone.utc)
OP = 'urn:ontopoc:vocab:'
ROOT = Path(__file__).resolve().parents[1]


def graph(text: str):
    g = Graph()
    g.parse(data=text, format='turtle')
    return g


def bearer(token):
    return {'Authorization': f'Bearer {token}'}


@unittest.skipIf(pyshacl is None, 'rdflib and pyshacl come with the check extra')
class SchemaCase(AgentCase):
    def files(self, out, username, path=None):
        """The two files as `username` gets them from the workspace at `path` (the service's own by default), made at MADE."""
        conn = open_workspace(path or out / 'workspace.sqlite')
        try:
            (user_id,) = conn.execute('SELECT id FROM user WHERE username = ?', (username,)).fetchone()
            return owl_export.files(conn, get_user(conn, user_id), now=MADE)
        finally:
            conn.close()

    def fetch(self, base, headers, query=''):
        with urlopen(Request(base + SCHEMA + query, headers=headers), timeout=30) as response:
            return response.headers['Content-Type'], response.headers['Content-Disposition'], response.read()

    def cookie(self, client):
        return {'Cookie': f'{client.cookie_name}={client.cookie}'}

    @staticmethod
    def without(out, gone: set[str], change=None) -> Path:
        """A copy of the workspace in which the definitions `gone` never existed: every row that names one of them, in any table, is taken out. `change(conn)` may
        edit the copy further. Everything else (who confirmed what, when, on which data) is the same rows, so a file made from it can be compared byte for byte."""
        copy = Path(tempfile.mkdtemp()) / 'workspace.sqlite'
        source, target = sqlite3.connect(out / 'workspace.sqlite'), sqlite3.connect(copy)
        source.backup(target)
        source.close()
        marks = ','.join('?' * len(gone))
        for (table,) in target.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
            columns = {r[1] for r in target.execute(f'PRAGMA table_info("{table}")')}
            for column in ('element_id', 'type_id', 'depends_on') if gone else ():
                if column in columns:
                    target.execute(f'DELETE FROM "{table}" WHERE "{column}" IN ({marks})', sorted(gone))
        if change:
            change(target)
        target.commit()
        target.close()
        return copy

    @staticmethod
    def waiting(out) -> dict[str, str]:
        """{definition id: state} of every definition that is not confirmed now."""
        conn = sqlite3.connect(out / 'workspace.sqlite')
        try:
            return dict(conn.execute("SELECT element_id, state FROM element_state WHERE state != 'confirmed'").fetchall())
        finally:
            conn.close()

    @staticmethod
    def on_type(out, name: str) -> set[str]:
        """Every definition that is a type's or names it: the type, its meanings, relations to or from it, its views, derived properties that pass through it."""
        conn = sqlite3.connect(out / 'workspace.sqlite')
        found = set()
        for element_id, content in conn.execute('SELECT element_id, content_json FROM element_state').fetchall():
            c = json.loads(content or '{}')
            if element_id == f'objtype:{name}' or element_id.startswith(f'enum:{name}:') or c.get('type') == name or name in (c.get('from'), c.get('to')) or name in (c.get('types') or []):
                found.add(element_id)
        conn.close()
        return found

    def iri_of(self, g, definition_id):
        found = list(g.subjects(URIRef(OP + 'definitionId'), Literal(definition_id)))
        self.assertEqual(len(found), 1, definition_id)
        return found[0]

    def column(self, g, type_iri, column):
        found = [p for p in g.subjects(RDFS.domain, type_iri) if (p, URIRef(OP + 'column'), Literal(column)) in g]
        self.assertEqual(len(found), 1, column)
        return found[0]


class WhatTheFilesSayTests(SchemaCase):
    def test_each_kind_of_confirmed_definition_is_written_and_read_back_by_rdflib(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            made = self.files(out, 'bob')
            onto, shapes = graph(made['ontology.ttl']), graph(made['shapes.ttl'])
            self.assertTrue(len(onto) > 50 and len(shapes) > 10)
            self.assertEqual(len(list(onto.subjects(RDF.type, OWL.Ontology))), 1)
            # a type: a class with its name, description, key and who confirmed it on which data
            order = self.iri_of(onto, 'objtype:order')
            self.assertEqual(str(order), 'urn:ontopoc:type/order')
            self.assertIn((order, RDF.type, OWL.Class), onto)
            self.assertEqual((str(onto.value(order, RDFS.label)), str(onto.value(order, RDFS.comment))), ('订单', '客户下的一张订单'))
            self.assertEqual(str(onto.value(order, URIRef(OP + 'confirmedBy'))), 'Bob')
            self.assertEqual(str(onto.value(order, URIRef(OP + 'confirmedOnData'))), '订单 v1')
            self.assertEqual(onto.value(order, URIRef(OP + 'confirmedAt')).datatype, XSD.dateTime)
            number = self.column(onto, order, '订单号')
            self.assertEqual(list(Collection(onto, onto.value(order, OWL.hasKey))), [number])
            self.assertEqual({o for o in onto.objects(number, RDF.type)}, {OWL.DatatypeProperty, OWL.FunctionalProperty})
            self.assertEqual(onto.value(number, RDFS.range), XSD.string)
            self.assertEqual(onto.value(self.column(onto, order, '金额'), RDFS.range), XSD.integer)   # whole numbers in the planted table
            customer = self.iri_of(onto, 'objtype:customer')
            self.assertEqual(len(list(Collection(onto, onto.value(customer, OWL.hasKey)))), 2)   # a key of two columns
            # a month is text with a note (xsd:gYearMonth is not among OWL 2's datatypes); a date would be xsd:dateTime
            month = self.column(onto, self.iri_of(onto, 'objtype:stock'), '快照月份')
            self.assertEqual(onto.value(month, RDFS.range), XSD.string)
            self.assertIn('YYYY-MM', ' '.join(str(n) for n in onto.objects(month, URIRef(OP + 'note'))))
            # code meanings: a SKOS concept scheme with one concept per code that has a meaning
            status = self.column(onto, order, '状态码')
            scheme = self.iri_of(onto, 'enum:order:状态码')
            self.assertEqual(onto.value(status, URIRef(OP + 'codeList')), scheme)
            self.assertIn((scheme, RDF.type, SKOS.ConceptScheme), onto)
            concepts = {str(onto.value(c, SKOS.notation)): str(onto.value(c, SKOS.prefLabel)) for c in onto.objects(scheme, SKOS.hasTopConcept)}
            self.assertEqual(concepts, {'0': '已交付', '1': '生产中', '2': '已取消'})
            self.assertTrue(all(isinstance(c, BNode) for c in onto.objects(scheme, SKOS.hasTopConcept)))   # a code is never part of a name
            # a relation: many to one is a functional object property, with its domain and range
            placed = self.iri_of(onto, 'relation:order_customer')
            self.assertEqual({o for o in onto.objects(placed, RDF.type)}, {OWL.ObjectProperty, OWL.FunctionalProperty})
            self.assertEqual((onto.value(placed, RDFS.domain), onto.value(placed, RDFS.range)), (order, customer))
            self.assertEqual(str(onto.value(placed, URIRef(OP + 'cardinality'))), 'many_to_one')
            # a view and a derived property: what they say is text, marked as not an axiom
            valid = self.iri_of(onto, 'objview:有效订单')
            self.assertEqual(onto.value(valid, RDFS.subClassOf), order)
            self.assertIn('已取消', str(onto.value(valid, URIRef(OP + 'definitionText'))))
            cancelled_orders = self.iri_of(onto, 'derived:customer:cancelled_orders')
            self.assertEqual((onto.value(cancelled_orders, RDFS.domain), onto.value(cancelled_orders, RDFS.range)), (customer, XSD.integer))
            self.assertIn('已取消', str(onto.value(cancelled_orders, URIRef(OP + 'definitionText'))))
            for said in (valid, cancelled_orders):
                self.assertIn('not an OWL axiom', ' '.join(str(n) for n in onto.objects(said, URIRef(OP + 'note'))))
            # the same confirmed set, and the same words, as the standing sheet the person downloads
            listed = {e['id'] for e in team['bob'].get(STANDING)[1]['definitions'] if e['confirmed']}
            self.assertEqual({str(o) for o in onto.objects(None, URIRef(OP + 'definitionId'))}, listed)

    def test_the_files_say_which_tools_read_them_and_claim_no_owl_profile_of_their_own(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            made = self.files(out, 'bob')
            for text in made.values():
                head = ''.join(line for line in text.splitlines(keepends=True) if line.startswith('#'))
                body = ''.join(line for line in text.splitlines(keepends=True) if not line.startswith('#'))
                self.assertIn('rdflib', head)
                self.assertIn('pyshacl', head)
                self.assertIn(STANDING, head)   # a snapshot: the live standing is there
                for claim in ('OWL 2 DL', 'OWL 2 EL', 'OWL 2 QL', 'OWL 2 RL', 'OWL DL'):
                    self.assertNotIn(claim, body)
            head = ''.join(line for line in made['ontology.ttl'].splitlines(keepends=True) if line.startswith('#'))
            for words in ('ROBOT', 'HermiT', 'once, by hand', 'not by the test suite', '手工', '不是测试'):   # the one real OWL tool run, said as what it was
                self.assertIn(words, head)
            self.assertIn('2026-11-22T08:00:00', made['ontology.ttl'])

    def test_the_skos_terms_used_are_declared_with_the_kinds_skos_gives_them(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            onto = graph(self.files(out, 'bob')['ontology.ttl'])
            used = {p for p in onto.predicates() if str(p).startswith(str(SKOS))} | {o for o in onto.objects(None, RDF.type) if str(o).startswith(str(SKOS))}
            kinds = {SKOS.Concept: OWL.Class, SKOS.ConceptScheme: OWL.Class, SKOS.inScheme: OWL.ObjectProperty, SKOS.hasTopConcept: OWL.ObjectProperty,
                     SKOS.prefLabel: OWL.AnnotationProperty, SKOS.notation: OWL.DatatypeProperty}   # SKOS Reference S1, S2, S3, S10, S15
            self.assertEqual(used, set(kinds))
            for term, kind in kinds.items():
                self.assertEqual(set(onto.objects(term, RDF.type)), {kind}, term)

    def test_what_a_definition_says_carries_no_language_tag(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            onto = graph(self.files(out, 'bob')['ontology.ttl'])
            said = list(onto.objects(None, URIRef(OP + 'definitionText')))
            self.assertTrue(said)
            self.assertEqual({t.language for t in said}, {None})   # the sentence mixes the asker's language with names in whatever language they were written

    def test_every_name_the_files_mint_is_the_base_a_fixed_word_an_english_name_or_a_hash(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            for env, root in ((None, 'urn:ontopoc:'), ('https://example.org/ontology/', 'https://example.org/ontology/')):
                with mock.patch.dict(os.environ, {owl_export.BASE_ENV: env} if env else {}, clear=False):
                    if env is None:
                        os.environ.pop(owl_export.BASE_ENV, None)
                    made = self.files(out, 'bob')
                minted = {str(t) for text in made.values() for triple in graph(text) for t in triple if isinstance(t, URIRef) and str(t).startswith(root) and not str(t).startswith(owl_export.VOCAB)}
                self.assertTrue(minted)
                for iri in minted:
                    self.assertRegex(iri[len(root):], r'^(ontology|(type|relation|view|shape)(/[A-Za-z0-9_]+)*(/(column|derived|codes|key)(/[A-Za-z0-9_]+)?)*)$', iri)
                self.assertFalse(any(re.search(r'[^\x21-\x7e]', i) for i in minted))   # nothing Chinese, no space: no name a person typed, no value
            with mock.patch.dict(os.environ, {owl_export.BASE_ENV: 'https://example.org/a b/'}):
                status, body = team['bob'].get(SCHEMA + '?file=ontology')
                self.assertEqual(status, 409)
                self.assertIn(owl_export.BASE_ENV, body['error'])

    def test_names_with_spaces_quotes_backslashes_newlines_and_chinese_come_back_unchanged(self):
        for text in ('订单 "VIP" \\ 名单', 'a\nb\r\tc', 'end \\', '"', '中文 名称', '\x00\x1f\x7f', 'emoji 😀'):
            g = graph(f'<urn:x> <urn:p> {owl_export.literal(text)} .\n')
            self.assertEqual(str(g.value(URIRef('urn:x'), URIRef('urn:p'))), text)
        odd_column, odd_name = '备 注 "x" \\ y', '名单 "VIP" \\ 一'
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            records = [{'编号': 'A1', odd_column: 'p'}, {'编号': 'A2', odd_column: 'q'}]
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [table_csv('名单.csv', records)]})[0], 200)
            status, body = ann.post('/api/workspace/types', {'english_name': 'odd', 'name': odd_name, 'dataset': '名单', 'key': ['编号'], 'description': 'say "hi" \\ there',
                                                             'properties': [{'column': '编号'}, {'column': odd_column}]})
            self.assertEqual(status, 200, body)
            self.confirm_type(bob, 'odd')
            onto = graph(self.files(out, 'bob')['ontology.ttl'])
            odd = self.iri_of(onto, 'objtype:odd')
            self.assertEqual((str(onto.value(odd, RDFS.label)), str(onto.value(odd, RDFS.comment))), (odd_name, 'say "hi" \\ there'))
            self.assertEqual(str(onto.value(self.column(onto, odd, odd_column), RDFS.label)), odd_column)


class ShapesTests(SchemaCase):
    def objects(self, onto, *, order_keys=('A-1', 'A-2'), codes=(0, 2), customers=(('K1', '上海'),), links=((0, 0), (1, 0)), extra=()):
        """A few objects written here, in the test, with the names the ontology file gives: orders with their numbers and codes, customers with their keys,
        and links from order to customer. Never the data in the workspace."""
        g = Graph()
        order, customer = self.iri_of(onto, 'objtype:order'), self.iri_of(onto, 'objtype:customer')
        number, status = self.column(onto, order, '订单号'), self.column(onto, order, '状态码')
        cid, city = self.column(onto, customer, '客户编号'), self.column(onto, customer, '城市')
        placed = self.iri_of(onto, 'relation:order_customer')
        orders = [URIRef(f'urn:test:order/{i}') for i in range(len(order_keys))]
        people = [URIRef(f'urn:test:customer/{i}') for i in range(len(customers))]
        for node, key, code in zip(orders, order_keys, codes):
            g.add((node, RDF.type, order))
            if key is not None:
                g.add((node, number, Literal(key)))
            g.add((node, status, Literal(code)))
        for node, (k, c) in zip(people, customers):
            g += [(node, RDF.type, customer), (node, cid, Literal(k)), (node, city, Literal(c))]
        for o, c in links:
            g.add((orders[o], placed, people[c] if c is not None else URIRef('urn:test:nobody')))
        for triple in extra:
            g.add(triple)
        return g

    def check(self, shapes, data):
        conforms, _, text = pyshacl.validate(data, shacl_graph=shapes, inference='none')
        return conforms, text

    def test_good_objects_conform_and_a_repeated_key_an_unknown_code_a_missing_key_and_a_broken_many_to_one_do_not(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            made = self.files(out, 'bob')
            onto, shapes = graph(made['ontology.ttl']), graph(made['shapes.ttl'])
            conforms, text = self.check(shapes, self.objects(onto))
            self.assertTrue(conforms, text)
            repeated = self.check(shapes, self.objects(onto, order_keys=('A-1', 'A-1')))
            self.assertFalse(repeated[0])
            self.assertIn('MaxCount', repeated[1])
            unknown = self.check(shapes, self.objects(onto, codes=(0, 7)))
            self.assertFalse(unknown[0])
            self.assertIn('InConstraint', unknown[1])
            self.assertFalse(self.check(shapes, self.objects(onto, order_keys=('A-1', None)))[0])
            two_customers = self.objects(onto, customers=(('K1', '上海'), ('K2', '北京')), links=((0, 0), (0, 1), (1, 0)))
            self.assertFalse(self.check(shapes, two_customers)[0])   # many to one: an order with two customers
            self.assertFalse(self.check(shapes, self.objects(onto, links=((0, None), (1, 0))))[0])   # a link to something that is not a customer

    def test_a_link_to_something_unknown_is_reported_by_sh_class_with_inference_off_and_not_with_rdfs_inference_on(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            made = self.files(out, 'bob')
            onto, shapes = graph(made['ontology.ttl']), graph(made['shapes.ttl'])
            dangling = self.objects(onto, links=((0, None), (1, 0)))
            off = self.check(shapes, dangling)
            self.assertFalse(off[0])
            self.assertIn('ClassConstraint', off[1])
            inferred = pyshacl.validate(dangling, shacl_graph=shapes, ont_graph=onto, inference='rdfs')[2]
            self.assertNotIn('ClassConstraint', inferred)   # rdfs:range made the unknown end a customer: why the pages say to check with inference off

    def test_a_key_of_several_columns_is_not_checked_for_repeats_and_both_the_file_and_the_pages_say_so(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            made = self.files(out, 'bob')
            onto, shapes = graph(made['ontology.ttl']), graph(made['shapes.ttl'])
            twice = self.objects(onto, customers=(('K1', '上海'), ('K1', '上海')), links=((0, 0), (1, 1)))
            self.assertTrue(self.check(shapes, twice)[0])   # core SHACL has no way to say "no two objects share this pair": what is not checked, said
            self.assertIn(owl_export.SEVERAL_COLUMNS_NOTE[1], made['shapes.ttl'])
            self.assertIn(owl_export.SEVERAL_COLUMNS_NOTE[0], made['shapes.ttl'])
            self.assertIn(owl_export.SEVERAL_COLUMNS_NOTE[1], (ROOT / 'docs/STANDARDS.en.md').read_text(encoding='utf-8'))
            self.assertIn(owl_export.SEVERAL_COLUMNS_NOTE[0], (ROOT / 'docs/STANDARDS.md').read_text(encoding='utf-8'))

    def test_nothing_in_the_files_is_a_row_of_data(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            made = self.files(out, 'bob')
            onto = graph(made['ontology.ttl'])
            classes = {c for c in onto.subjects(RDF.type, OWL.Class) if not str(c).startswith(str(SKOS))}   # the concept schemes and their codes are SKOS's
            self.assertTrue(classes)
            self.assertFalse([s for c in classes for s in onto.subjects(RDF.type, c)])   # no object of any type or view
            values = {r['订单号'] for r in ORDERS} | {r['客户编号'] for r in CUSTOMERS} | {r['客户名称'] for r in CUSTOMERS}
            for text in made.values():
                self.assertFalse([v for v in values if v and v in text])


class WhoGetsWhatTests(SchemaCase):
    def test_a_viewer_and_a_builder_kept_from_a_type_get_the_same_bytes_as_from_a_workspace_without_it_and_a_waiting_one_is_absent(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, admin = team['ann'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)   # 含税金额 waits: nobody has confirmed it
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            self.assertIn('售后工单', self.files(out, 'bob')['ontology.ttl'])
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'ticket', 'visible_to': [ids['ann']]})[0], 200)
            self.assertIn('售后工单', self.files(out, 'ann')['ontology.ttl'])   # Ann still gets it
            gone = self.on_type(out, 'ticket') | {'derived:order:gross'}
            self.assertIn('relation:ticket_order', gone)
            elsewhere = self.without(out, gone)
            for person in ('vera', 'bob'):
                made, plain = self.files(out, person), self.files(out, person, elsewhere)
                self.assertEqual(made, plain, person)
                for text in made.values():
                    for word in ('售后工单', 'ticket', '含税金额', 'gross'):
                        self.assertNotIn(word, text)

    def test_a_type_a_relation_a_view_a_derived_property_and_meanings_that_wait_are_absent_as_if_they_never_existed(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            later = next(r for r in RELATIONS if r['english_name'] == 'order_product')
            self.foundation(team, types=(ORDER, CUSTOMER, PRODUCT, STOCK, COMMIT), relations=[r for r in RELATIONS if r is not later])
            self.assertEqual(ann.post('/api/workspace/types/views', VALID)[0], 200)
            shown = bob.get('/api/workspace/types/order/views')[1]['views'][0]
            self.assertEqual(bob.post('/api/workspace/types/views/confirm', {'id': VALID['name'], 'version': shown['version'], 'seen': shown['seen']})[0], 200)
            self.assertEqual(ann.post('/api/workspace/types/derived', CANCELLED)[0], 200)
            self.assertEqual(self.confirm(bob, CANCELLED)[0], 200)
            before = self.files(out, 'bob')
            # put forward and not confirmed: a type, a relation, a view, a derived property, and a code column's meanings on a confirmed type
            self.assertEqual(ann.post('/api/workspace/types', TICKET)[0], 200)
            self.assertEqual(ann.post('/api/workspace/relations', later)[0], 200)
            self.assertEqual(ann.post('/api/workspace/types/views', LATEST_STOCK)[0], 200)
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)
            # confirmed, then changed in what it says (its cardinality): it waits for a confirmation again
            stock_product = next(r for r in RELATIONS if r['english_name'] == 'stock_product')
            detail = bob.get('/api/workspace/relations/stock_product')[1]
            status, body = ann.post('/api/workspace/relations/update', {**stock_product, 'id': 'stock_product', 'version': detail['version'], 'cardinality': 'one_to_one'})
            self.assertEqual(status, 200, body)
            conn = sqlite3.connect(out / 'workspace.sqlite')   # one put forward by a model and not yet checked: the same as any other that waits
            conn.execute("UPDATE element_state SET state = 'proposed' WHERE element_id = 'relation:order_product'")
            conn.commit()
            conn.close()
            waiting = self.waiting(out)
            self.assertEqual({k: waiting.get(k) for k in ('objtype:ticket', 'relation:order_product', 'objview:最新快照', 'derived:order:gross', 'relation:stock_product')},
                             {'objtype:ticket': 'checked', 'relation:order_product': 'proposed', 'objview:最新快照': 'checked', 'derived:order:gross': 'checked',
                              'relation:stock_product': waiting.get('relation:stock_product')})
            self.assertIn(waiting['relation:stock_product'], ('proposed', 'checked', 'needs_look'))
            elsewhere = self.without(out, set(waiting))
            for person in ('bob', 'vera'):
                made = self.files(out, person)
                self.assertEqual(made, self.files(out, person, elsewhere), person)
                for text in made.values():
                    for word in ('售后工单', 'ticket', '订单买的产品', 'order_product', '最新快照', '含税金额', 'gross', '库存属于产品', 'stock_product'):
                        self.assertNotIn(word, text)
            self.assertIn('库存属于产品', before['ontology.ttl'])   # it was in the file while it was confirmed

    def test_meanings_that_need_another_look_after_the_data_moved_are_absent_with_everything_that_stands_on_them(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            self.assertIn('已取消', self.files(out, 'bob')['ontology.ttl'])
            self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)   # the codes move
            waiting = self.waiting(out)
            self.assertEqual(waiting['enum:order:状态码'], 'needs_look')
            elsewhere = self.without(out, set(waiting))
            for person in ('bob', 'vera'):
                made = self.files(out, person)
                self.assertEqual(made, self.files(out, person, elsewhere), person)
                for text in made.values():
                    self.assertNotIn('已取消', text)
                    self.assertNotIn('enum:order', text)

    def test_meanings_that_wait_on_a_type_that_stays_confirmed_are_absent(self):
        """The pages do not leave a type confirmed while its meanings wait (rewriting them sends the type back too); the file does not rely on that."""
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            conn = sqlite3.connect(out / 'workspace.sqlite')
            conn.execute("UPDATE element_state SET state = 'checked' WHERE element_id = 'enum:order:状态码'")
            conn.commit()
            conn.close()
            self.assertEqual(self.waiting(out), {'enum:order:状态码': 'checked'})
            elsewhere = self.without(out, {'enum:order:状态码'})
            for person in ('bob', 'vera'):
                made = self.files(out, person)
                self.assertEqual(made, self.files(out, person, elsewhere), person)
                for text in made.values():
                    self.assertNotIn('已交付', text)
                    self.assertNotIn('enum:order', text)
                    self.assertNotIn('sh:in (', text)

    def test_a_column_kept_from_a_person_is_absent_as_if_the_type_never_had_it(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            admin = team['admin']
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'customer', 'column': '客户等级', 'visible_to': [ids['ann']]})[0], 200)
            self.assertIn('客户等级', self.files(out, 'ann')['ontology.ttl'])

            def drop_column(conn):
                (content,) = conn.execute("SELECT content_json FROM element_state WHERE element_id = 'objtype:customer'").fetchone()
                c = json.loads(content)
                c['properties'] = [p for p in c['properties'] if p['column'] != '客户等级']
                conn.execute("UPDATE element_state SET content_json = ? WHERE element_id = 'objtype:customer'", (json.dumps(c, ensure_ascii=False),))
                conn.execute("DELETE FROM column_access")
            made = self.files(out, 'bob')
            self.assertNotIn('客户等级', json.dumps(made, ensure_ascii=False))
            self.assertEqual(made, self.files(out, 'bob', self.without(out, set(), drop_column)))

    def test_a_column_whose_values_are_kept_from_models_keeps_its_standing_and_loses_its_meanings_as_in_the_sheet(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann = team['ann']
            self.assertEqual(ann.post('/api/workspace/types/privacy', {'id': 'order', 'column': '状态码', 'hide_values': True})[0], 200)
            made = self.files(out, 'bob')
            onto, shapes = graph(made['ontology.ttl']), graph(made['shapes.ttl'])
            scheme = self.iri_of(onto, 'enum:order:状态码')
            self.assertEqual(str(onto.value(scheme, URIRef(OP + 'confirmedBy'))), 'Bob')
            self.assertEqual(list(onto.objects(scheme, SKOS.hasTopConcept)), [])
            self.assertIsNone(onto.value(scheme, URIRef(OP + 'definitionText')))
            self.assertEqual(list(shapes.objects(None, URIRef('http://www.w3.org/ns/shacl#in'))), [])   # the codes themselves are not listed either
            derived = self.iri_of(onto, 'derived:customer:cancelled_orders')
            self.assertIsNone(onto.value(derived, URIRef(OP + 'definitionText')))
            for text in made.values():
                self.assertNotIn('"已取消"', text)   # no meaning (the name 已取消订单数 is listed, as the sheet lists it)
                self.assertNotIn('有效订单', text)   # a view on that column is out of the scope, as in the sheet
            sheet = {e['id'] for e in team['bob'].get(STANDING)[1]['definitions'] if e['confirmed']}
            self.assertEqual({str(o) for o in onto.objects(None, URIRef(OP + 'definitionId'))}, sheet)

    def test_a_read_token_gets_what_its_person_gets_and_the_route_is_a_viewers_read(self):
        from ontology_poc_generator.access import read_token_allows, required_role
        self.assertEqual(required_role('GET', SCHEMA), 'viewer')
        self.assertTrue(read_token_allows('GET', SCHEMA))
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            admin, vera = team['admin'], team['vera']
            token = self.token_for(admin, 'vera', scope='read')['token']
            with mock.patch.object(owl_export, '_now', return_value=MADE):
                by_token = {q: self.fetch(base, bearer(token), q) for q in ('', '?file=ontology', '?file=shapes')}
                by_person = {q: self.fetch(base, self.cookie(vera), q) for q in ('', '?file=ontology', '?file=shapes')}
            self.assertEqual(by_token, by_person)
            kind, disposition, packed = by_token['']
            self.assertEqual(kind, 'application/zip')
            self.assertIn('.zip', disposition)
            inside = zipfile.ZipFile(io.BytesIO(packed))
            self.assertEqual(sorted(inside.namelist()), ['ontology.ttl', 'shapes.ttl'])
            self.assertEqual(inside.read('ontology.ttl'), by_token['?file=ontology'][2])
            self.assertTrue(by_token['?file=shapes'][0].startswith('text/turtle'))
            self.assertEqual(by_token['?file=ontology'][2].decode('utf-8'), self.files(out, 'vera')['ontology.ttl'])
            self.assertEqual(Client(base).get(SCHEMA)[0], 401)
            self.assertEqual(vera.get(SCHEMA + '?file=nothing')[0], 404)
