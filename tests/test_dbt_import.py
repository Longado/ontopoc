"""Starting from the definitions a team already keeps in dbt: a builder hands the service a dbt manifest.json, sees what it would propose (nothing written),
then applies it. Driven through the real service with two builders, a viewer and an admin, on two small invented tables (orders, customers) and a
hand-written manifest in dbt's public shape. Expected numbers are counted from the records here, and the relation's are checked again with plain SQL."""
import json
import sqlite3
import unittest
from unittest import mock

from ontology_poc_generator import dbt_import, object_relations
from tests.test_object_relations import table_csv
from tests.test_two_person import SigningTestCase

ORDERS = [
    {'order_id': 'O1', 'customer_id': 'C1', 'status': 'placed', 'amount': '10'},
    {'order_id': 'O2', 'customer_id': 'C1', 'status': 'shipped', 'amount': '20'},
    {'order_id': 'O3', 'customer_id': 'C2', 'status': 'completed', 'amount': '30'},
    {'order_id': 'O4', 'customer_id': 'C9', 'status': 'returned', 'amount': '5'},    # C9 is not a customer
    {'order_id': 'O5', 'customer_id': 'C3', 'status': 'placed', 'amount': '7'},
    {'order_id': 'O6', 'customer_id': '', 'status': 'placed', 'amount': '3'},        # no customer at all
]
CUSTOMERS = [
    {'customer_id': 'C1', 'name': 'Ash Co', 'tier': 'gold'},
    {'customer_id': 'C2', 'name': 'Birch Ltd', 'tier': 'silver'},
    {'customer_id': 'C3', 'name': 'Cedar Inc', 'tier': 'gold'},
]
ORDER_ITEMS = [{'order_id': 'O1', 'line': '1', 'qty': '2'}, {'order_id': 'O1', 'line': '2', 'qty': '1'}, {'order_id': 'O2', 'line': '1', 'qty': '4'}]
CUSTOMER_IDS = {c['customer_id'] for c in CUSTOMERS}
MATCHED = sum(1 for o in ORDERS if o['customer_id'] in CUSTOMER_IDS)                          # 4
UNMATCHED = sum(1 for o in ORDERS if o['customer_id'] and o['customer_id'] not in CUSTOMER_IDS)   # 1
EMPTY = sum(1 for o in ORDERS if not o['customer_id'])                                          # 1
STATUSES = ['placed', 'shipped', 'completed', 'returned']
V12 = 'https://schemas.getdbt.com/dbt/manifest/v12.json'
ROUTE = '/api/workspace/types/dbt-import'


def tables():
    return [table_csv('orders.csv', ORDERS), table_csv('customers.csv', CUSTOMERS), table_csv('order_items.csv', ORDER_ITEMS)]


def model(name, *columns):
    return {f'model.shop.{name}': {'resource_type': 'model', 'name': name, 'unique_id': f'model.shop.{name}', 'package_name': 'shop',
                                   'description': f'The {name} model', 'columns': {c: {'name': c, 'description': ''} for c in columns}}}


def generic_test(kind, on, column, attached=True, namespace=None, where=None, also=(), **kwargs):
    """A generic test node as dbt writes it: test_metadata {name, kwargs, namespace}, column_name, depends_on.nodes and (from manifest v9 on) attached_node."""
    unique_id = f'test.shop.{kind}_{on}_{column}'
    node = {'resource_type': 'test', 'name': f'{kind}_{on}_{column}', 'unique_id': unique_id, 'package_name': 'shop', 'column_name': column,
            'test_metadata': {'name': kind, 'kwargs': {'column_name': column, 'model': "{{ get_where_subquery(ref('" + on + "')) }}", **kwargs}, 'namespace': namespace},
            'depends_on': {'macros': [f'macro.dbt.test_{kind}'], 'nodes': [*(f'model.shop.{m}' for m in also), f'model.shop.{on}']},
            'config': {'enabled': True, 'severity': 'ERROR', 'where': where}}
    if attached:
        node['attached_node'] = f'model.shop.{on}'
    return {unique_id: node}


def manifest(version=V12, attached=True, extra=None):
    """orders: order_id unique + not_null, customer_id -> customers.customer_id, status in four values; a test on a column the table lacks and one with a
    condition. customers: customer_id unique + not_null. order_items: only a two-column key from a package (no key a code can read). payments: no dataset."""
    nodes = {**model('orders', 'order_id', 'customer_id', 'status', 'amount'), **model('customers', 'customer_id', 'name'), **model('order_items', 'order_id', 'line'),
             **model('payments', 'payment_id'),
             **generic_test('unique', 'orders', 'order_id', attached), **generic_test('not_null', 'orders', 'order_id', attached),
             **generic_test('relationships', 'orders', 'customer_id', attached, also=('customers',), to="ref('customers')", field='customer_id'),
             **generic_test('accepted_values', 'orders', 'status', attached, values=STATUSES),
             **generic_test('accepted_values', 'orders', 'channel', attached, values=['web', 'store']),
             **generic_test('not_null', 'orders', 'amount', attached, where="status != 'returned'"),
             **generic_test('unique', 'customers', 'customer_id', attached), **generic_test('not_null', 'customers', 'customer_id', attached),
             **generic_test('unique_combination_of_columns', 'order_items', None, attached, namespace='dbt_utils', combination_of_columns=['order_id', 'line']),
             **generic_test('unique', 'payments', 'payment_id', attached), **generic_test('not_null', 'payments', 'payment_id', attached),
             **(extra or {})}
    return {'metadata': {'dbt_schema_version': version, 'dbt_version': '1.8.0', 'project_name': 'shop'}, 'nodes': nodes, 'sources': {}, 'macros': {}}


def by(items, key, value):
    return next(i for i in items if i[key] == value)


class DbtImportTests(SigningTestCase):
    def team(self, base):
        team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        status, body = team['ann'].post('/api/workspace/datasets/upload', {'files': tables()})
        self.assertEqual(status, 200, body)
        return team

    def run_import(self, client, text, apply):
        return client.post(ROUTE, {'manifest': text, 'apply': apply}, headers={'Accept-Language': 'en'})

    def written(self, out):
        conn = sqlite3.connect(out / 'workspace.sqlite')
        try:
            return (conn.execute('SELECT element_id, state, version FROM element_state ORDER BY element_id').fetchall(),
                    conn.execute("SELECT COUNT(*) FROM log WHERE change = 'dbt_import'").fetchone()[0])
        finally:
            conn.close()

    def test_the_preview_proposes_types_a_relation_and_codes_from_the_tests_and_writes_nothing(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            before = self.written(out)
            status, body = self.run_import(ann, json.dumps(manifest()), apply=False)
            self.assertEqual(status, 200, body)
            self.assertEqual(self.written(out), before)   # nothing kept: not a type, not a check, not a log line
            self.assertFalse(body['applied'])
            orders, customers = by(body['types'], 'id', 'orders'), by(body['types'], 'id', 'customers')
            self.assertEqual((orders['status'], orders['state'], orders['dataset'], orders['key']), ('new', 'checked', 'orders', ['order_id']))
            self.assertEqual((customers['status'], customers['key']), ('new', ['customer_id']))
            self.assertIn('status', orders['codes'])
            self.assertEqual({'order_id', 'customer_id', 'status'} - set(orders['properties']), set())
            relation = body['relations'][0]
            self.assertEqual(len(body['relations']), 1)
            self.assertEqual((relation['from'], relation['to'], relation['from_column'], relation['to_column'], relation['cardinality'], relation['status']),
                             ('orders', 'customers', 'customer_id', 'customer_id', 'many_to_one', 'new'))
            self.assertEqual((relation['numbers']['rows'], relation['numbers']['matched'], relation['numbers']['unmatched'], relation['numbers']['empty']),
                             (len(ORDERS), MATCHED, UNMATCHED, EMPTY))
            codes = by(body['codes'], 'column', 'status')
            self.assertEqual((codes['type'], codes['values'], codes['code_column']), ('orders', STATUSES, True))   # dbt lists the values; what they mean is still to be written
            self.assertEqual(body['unmatched_models'], ['payments'])
            self.assertTrue(any(s['model'] == 'order_items' and 'no key in the tests' in s['reason'].lower() for s in body['skipped']), body['skipped'])   # a two-column key from a package is not guessed at
            self.assertTrue(any(s['model'] == 'orders' and 'channel' in s['what'] for s in body['skipped']))    # a test on a column the table lacks
            self.assertTrue(any(s['model'] == 'orders' and 'amount' in s['what'] for s in body['skipped']))     # a test that holds only where a condition does
            self.assertEqual(body['left_out'], [])

    def test_apply_puts_them_forward_as_the_form_would_marked_as_imported_and_a_second_import_adds_nothing(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            status, body = self.run_import(ann, json.dumps(manifest()), apply=True)
            self.assertEqual(status, 200, body)
            self.assertTrue(body['applied'])
            conn = sqlite3.connect(out / 'workspace.sqlite')
            rows = {e: (s, p, json.loads(c)) for e, s, p, c in conn.execute('SELECT element_id, state, proposed_by, content_json FROM element_state')}
            self.assertEqual(set(rows), {'objtype:orders', 'objtype:customers', 'relation:orders_customer_id'})   # no meanings: dbt does not say what a code means
            self.assertEqual({e: r[:2] for e, r in rows.items()}, {e: ('checked', 'Ann') for e in rows})   # never confirmed; Ann put them forward
            self.assertEqual(rows['objtype:orders'][2]['key'], ['order_id'])
            self.assertTrue(next(p for p in rows['objtype:orders'][2]['properties'] if p['column'] == 'status')['enum'])
            marks = conn.execute("SELECT element_id, who FROM log WHERE change = 'dbt_import' ORDER BY element_id").fetchall()
            self.assertEqual(marks, [('objtype:customers', 'Ann'), ('objtype:orders', 'Ann'), ('relation:orders_customer_id', 'Ann')])
            tables = dict(conn.execute("SELECT d.name, d.table_name FROM dataset d JOIN current_dataset c ON c.dataset_id = d.id"))
            sql_matched = conn.execute(f'SELECT COUNT(*) FROM "{tables["orders"]}" o WHERE EXISTS (SELECT 1 FROM "{tables["customers"]}" c WHERE c.customer_id = o.customer_id)').fetchone()[0]
            conn.close()
            relation = body['relations'][0]
            self.assertEqual(relation['numbers']['matched'], sql_matched)
            self.assertEqual(relation['numbers']['matched'], MATCHED)
            self.assertEqual(ann.post('/api/workspace/types/confirm', {'id': 'orders', 'version': 1, 'seen': ann.get('/api/workspace/types/orders')[1]['seen']})[0], 403)   # her own
            shown = bob.get('/api/workspace/types/orders')[1]
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'orders', 'version': shown['version'], 'seen': shown['seen']})[0], 200)   # another builder confirms as usual
            before = self.written(out)
            status, again = self.run_import(ann, json.dumps(manifest()), apply=True)
            self.assertEqual(status, 200, again)
            self.assertEqual(self.written(out), before)
            self.assertEqual({t['id']: t['status'] for t in again['types']}, {'orders': 'already_there', 'customers': 'already_there'})
            self.assertEqual(by(again['types'], 'id', 'orders')['state'], 'confirmed')   # left alone
            self.assertEqual([r['status'] for r in again['relations']], ['already_there'])

    def test_a_test_written_in_sql_is_listed_on_a_model_with_a_dataset_and_not_on_one_without(self):
        singular = lambda on: {f'test.shop.check_{on}': {'resource_type': 'test', 'name': f'check_{on}', 'unique_id': f'test.shop.check_{on}', 'test_metadata': None,
                                                        'attached_node': None, 'column_name': None, 'depends_on': {'nodes': [f'model.shop.{on}']}}}
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            status, body = self.run_import(ann, json.dumps(manifest(extra={**singular('orders'), **singular('payments')})), apply=False)
            self.assertEqual(status, 200, body)
            self.assertTrue(any(s['model'] == 'orders' and s['what'] == 'check_orders' for s in body['skipped']))
            self.assertFalse(any(s['model'] == 'payments' for s in body['skipped']), body['skipped'])   # payments is listed once, as a model with no dataset
            self.assertIn('payments', body['unmatched_models'])

    def test_a_manifest_that_is_not_dbt_or_is_too_large_is_refused_and_a_viewer_may_not_import(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            status, body = self.run_import(ann, 'this is not json', apply=False)
            self.assertEqual(status, 400)
            self.assertIn('JSON', body['error'])
            status, body = self.run_import(ann, json.dumps({'nodes': {}}), apply=False)
            self.assertEqual(status, 400)
            self.assertIn('dbt_schema_version', body['error'])
            status, body = self.run_import(ann, json.dumps({'metadata': {'dbt_schema_version': 'https://example.com/other/v1.json'}, 'nodes': {}}), apply=False)
            self.assertEqual(status, 400)
            with mock.patch.object(dbt_import, 'MAX_MANIFEST_BYTES', 2000):
                status, body = self.run_import(ann, json.dumps(manifest()), apply=False)
            self.assertEqual(status, 413)
            self.assertIn('MB', body['error'])
            self.assertEqual(self.run_import(team['vera'], json.dumps(manifest()), apply=False)[0], 403)
            self.assertEqual(self.written(out)[0], [])

    def test_an_older_manifest_without_attached_node_reads_the_same(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            status, body = self.run_import(ann, json.dumps(manifest(version='https://schemas.getdbt.com/dbt/manifest/v7.json', attached=False)), apply=False)
            self.assertEqual(status, 200, body)
            self.assertEqual({t['id']: t['key'] for t in body['types']}, {'orders': ['order_id'], 'customers': ['customer_id']})
            self.assertEqual([(r['from'], r['to']) for r in body['relations']], [('orders', 'customers')])

    def test_a_dataset_or_type_kept_from_the_person_is_never_named_and_their_own_type_is_already_there(self):
        with self.service() as (base, out):
            team = self.team(base)
            admin, ann, bob = team['admin'], team['ann'], team['bob']
            self.assertEqual(admin.post('/api/workspace/types', {'english_name': 'vip', 'name': 'Secret accounts', 'dataset': 'customers', 'key': ['customer_id']})[0], 200)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'vip', 'visible_to': []})[0], 200)   # admins only: customers is not Ann's to see now
            self.assertEqual(bob.post('/api/workspace/types', {'english_name': 'orders', 'name': 'Orders', 'dataset': 'orders', 'key': ['order_id']})[0], 200)
            status, body = self.run_import(ann, json.dumps(manifest()), apply=True)
            self.assertEqual(status, 200, body)
            text = json.dumps(body)
            self.assertNotIn('vip', text)
            self.assertNotIn('Secret', text)
            self.assertIn('customers', body['unmatched_models'])   # as if there were no such dataset
            self.assertEqual([(t['id'], t['status'], t['state']) for t in body['types']], [('orders', 'already_there', 'checked')])
            self.assertEqual(body['relations'], [])
            self.assertTrue(any('customers' in s['what'] for s in body['skipped'] if s['model'] == 'orders'))

    def test_one_import_writes_at_most_the_cap_and_says_what_was_left_out(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            with mock.patch.object(dbt_import, 'MAX_PROPOSALS', 1):
                status, body = self.run_import(ann, json.dumps(manifest()), apply=True)
            self.assertEqual(status, 200, body)
            self.assertEqual([t['id'] for t in body['types']], ['customers'])   # by model name
            self.assertEqual({e for e, _, _ in self.written(out)[0]}, {'objtype:customers'})
            left = ' '.join(item['what'] for item in body['left_out'])
            self.assertIn('orders', left)
            self.assertTrue(body['left_out'])


    def deep_text(self, where):
        """The test manifest with one value nested 100,000 lists deep: as an accepted value of orders.status, or as the name of a test node on orders."""
        deep = '[' * 100_000 + '1' + ']' * 100_000
        if where == 'value':
            return json.dumps(manifest(extra=generic_test('accepted_values', 'orders', 'status', values=['placed', 'DEEP']))).replace('"DEEP"', deep)
        node = {'test.shop.deep': {'resource_type': 'test', 'name': 'DEEP', 'test_metadata': None, 'depends_on': {'nodes': ['model.shop.orders']}}}
        return json.dumps(manifest(extra=node)).replace('"DEEP"', deep)

    def test_a_value_nested_very_deep_is_skipped_with_a_reason_or_the_file_refused_on_preview_and_apply(self):
        for where in ('value', 'name'):
            for apply in (False, True):
                with self.subTest(where=where, apply=apply), self.service() as (base, out):
                    ann = self.team(base)['ann']
                    status, body = self.run_import(ann, self.deep_text(where), apply=apply)
                    self.assertIn(status, (200, 400), body)   # a Python whose json reader refuses the depth says so: 400; one that reads it answers with the rest
                    rows = {e for e, _, _ in self.written(out)[0]}
                    if status == 400:
                        self.assertTrue(body['error'])
                        self.assertEqual(rows, set())
                        continue
                    self.assertEqual({t['id'] for t in body['types']}, {'orders', 'customers'})
                    self.assertEqual([r['id'] for r in body['relations']], ['orders_customer_id'])
                    if where == 'value':
                        self.assertNotIn('status', [c['column'] for c in body['codes']])
                        self.assertTrue(any('status' in s['what'] and 'plain' in s['reason'] for s in body['skipped']), body['skipped'])
                    self.assertEqual(rows, {'objtype:orders', 'objtype:customers', 'relation:orders_customer_id'} if apply else set())

    def test_an_unexpected_error_on_the_second_of_three_items_stops_the_import_and_the_report_says_what_was_written_failed_and_not_tried(self):
        real = dbt_import.create_type
        calls = []

        def second_fails(*args, **kwargs):   # customers first, then orders (by model name), then the relation
            calls.append(1)
            if len(calls) == 2:
                raise RecursionError('maximum recursion depth exceeded')
            return real(*args, **kwargs)
        for apply in (False, True):
            with self.subTest(apply=apply), self.service() as (base, out):
                ann = self.team(base)['ann']
                calls.clear()
                with mock.patch.object(dbt_import, 'create_type', side_effect=second_fails):
                    status, body = self.run_import(ann, json.dumps(manifest()), apply=apply)
                self.assertEqual(status, 200, body)   # a report, not a dropped answer
                self.assertTrue(body['stopped'])
                self.assertEqual([(t['id'], t['status']) for t in body['types']], [('customers', 'new')])
                self.assertEqual(len(body['failed']), 1)
                self.assertIn('orders', body['failed'][0]['what'])
                self.assertIn('RecursionError', body['failed'][0]['reason'])
                self.assertNotIn('maximum recursion', body['failed'][0]['reason'])   # the kind of error, not its text: a database error's text can name internal tables
                self.assertEqual(body['relations'], [])
                self.assertTrue(any('customer_id' in n['what'] for n in body['not_attempted']), body['not_attempted'])
                self.assertEqual({e for e, _, _ in self.written(out)[0]}, {'objtype:customers'} if apply else set())   # the first stays written; the second was taken back

    def test_identical_tests_are_read_once_and_every_list_in_the_answer_is_capped(self):
        copies = {}
        for i in range(500):   # the same relationships test under 500 ids
            node = next(iter(generic_test('relationships', 'orders', 'customer_id', also=('customers',), to="ref('customers')", field='customer_id').values()))
            copies[f'test.shop.copy_{i}'] = {**node, 'unique_id': f'test.shop.copy_{i}', 'name': f'copy_{i}'}
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            for apply in (False, True):
                status, body = self.run_import(ann, json.dumps(manifest(extra=copies)), apply=apply)
                self.assertEqual(status, 200, body)
                self.assertEqual([(r['id'], r['status']) for r in body['relations']], [('orders_customer_id', 'new')])
                self.assertEqual(body['manifest']['duplicates'], 500)   # the fixture's own copy and these 500 are one test
            extra = {k: v for i in range(5) for k, v in model(f'unmatched_{i}', 'id').items()}
            with mock.patch.object(dbt_import, 'SHOWN', 2):
                status, body = self.run_import(ann, json.dumps(manifest(extra={**extra, **copies})), apply=False)
            self.assertEqual(status, 200, body)
            self.assertEqual(len(body['unmatched_models']), 2)
            self.assertEqual(body['more']['unmatched_models'], 4)   # payments and the five
            self.assertTrue(all(len(body[k]) <= 2 for k in ('types', 'relations', 'codes', 'unmatched_models', 'skipped', 'left_out', 'failed', 'not_attempted')))
            self.assertEqual(set(body['more']), {'types', 'relations', 'codes', 'unmatched_models', 'skipped', 'left_out', 'failed', 'not_attempted'})

    def test_two_relationships_on_one_column_to_different_models_get_their_own_names_and_a_taken_name_is_never_already_there(self):
        accounts = [{'customer_id': c['customer_id'], 'region': 'north'} for c in CUSTOMERS]
        second = {**model('accounts', 'customer_id'), **generic_test('unique', 'accounts', 'customer_id'), **generic_test('not_null', 'accounts', 'customer_id')}
        node = next(iter(generic_test('relationships', 'orders', 'customer_id', also=('accounts',), to="ref('accounts')", field='customer_id').values()))
        second['test.shop.relationships_orders_customer_id_accounts'] = {**node, 'unique_id': 'test.shop.relationships_orders_customer_id_accounts'}
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [table_csv('accounts.csv', accounts)]})[0], 200)
            for apply, status_word in ((True, 'new'), (True, 'already_there')):
                status, body = self.run_import(ann, json.dumps(manifest(extra=second)), apply=apply)
                self.assertEqual(status, 200, body)
                self.assertEqual(sorted((r['id'], r['to'], r['status']) for r in body['relations']),
                                 [('orders_customer_id_accounts', 'accounts', status_word), ('orders_customer_id_customers', 'customers', status_word)])
        with self.service() as (base, out):   # a relation by hand already holds the name the import would give, between other ends
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            for payload in ({'english_name': 'orders', 'name': 'Orders', 'dataset': 'orders', 'key': ['order_id']},
                            {'english_name': 'customers', 'name': 'Customers', 'dataset': 'customers', 'key': ['customer_id']}):
                self.assertEqual(bob.post('/api/workspace/types', payload)[0], 200)
            self.assertEqual(bob.post('/api/workspace/relations', {'english_name': 'orders_customer_id', 'name': 'By hand', 'from': 'orders', 'to': 'orders',
                                                                  'cardinality': 'many_to_one', 'from_column': 'order_id', 'to_column': 'order_id'})[0], 200)
            status, body = self.run_import(ann, json.dumps(manifest()), apply=False)
            self.assertEqual(status, 200, body)
            self.assertEqual(body['relations'], [])
            self.assertTrue(any('customer_id' in s['what'] and 'orders_customer_id' in s['reason'] for s in body['skipped']), body['skipped'])

    def test_each_proposal_is_committed_on_its_own_and_other_requests_get_through_between_two(self):
        real = dbt_import._write
        seen = []
        for apply in (False, True):
            with self.subTest(apply=apply), self.service() as (base, out):
                team = self.team(base)
                ann, bob = team['ann'], team['bob']
                seen.clear()

                def probe(conn, make, element_id, *rest, **kwargs):   # between two proposals, before the relation's own write
                    if element_id.startswith('relation:'):
                        status, listed = bob.get('/api/workspace/types')   # a reader gets in
                        seen.append((status, sorted(t['id'] for t in listed.get('types', []))))
                        status, _ = bob.post('/api/workspace/types/key-check', {'dataset': 'customers', 'key': ['customer_id']})   # and a writer: it takes the lock an upload takes
                        seen.append(status)
                        other = sqlite3.connect(out / 'workspace.sqlite', timeout=0.5)
                        try:
                            other.execute('BEGIN IMMEDIATE')   # nobody holds the database's write lock now
                            other.execute('ROLLBACK')
                        finally:
                            other.close()
                    return real(conn, make, element_id, *rest, **kwargs)
                with mock.patch.object(dbt_import, '_write', side_effect=probe):
                    status, body = self.run_import(ann, json.dumps(manifest()), apply=apply)
                self.assertEqual(status, 200, body)
                self.assertEqual(seen, [(200, ['customers', 'orders'] if apply else []), 200])   # on Apply the two types were already committed

    def test_a_new_relations_check_runs_as_often_as_the_forms_own_and_no_more(self):
        counted = []
        real = object_relations._check_relation

        def count(*args, **kwargs):
            counted.append(1)
            return real(*args, **kwargs)
        with self.service() as (base, out):   # the form: two types, then the relation
            ann = self.team(base)['ann']
            for payload in ({'english_name': 'orders', 'name': 'orders', 'dataset': 'orders', 'key': ['order_id']},
                            {'english_name': 'customers', 'name': 'customers', 'dataset': 'customers', 'key': ['customer_id']}):
                self.assertEqual(ann.post('/api/workspace/types', payload)[0], 200)
            with mock.patch.object(object_relations, '_check_relation', side_effect=count):
                self.assertEqual(ann.post('/api/workspace/relations', {'english_name': 'orders_customer_id', 'name': 'orders_customer_id', 'from': 'orders', 'to': 'customers',
                                                                      'cardinality': 'many_to_one', 'from_column': 'customer_id', 'to_column': 'customer_id'})[0], 200)
        by_form = len(counted)
        counted.clear()
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            with mock.patch.object(object_relations, '_check_relation', side_effect=count):
                status, body = self.run_import(ann, json.dumps(manifest()), apply=True)
            self.assertEqual(status, 200, body)
            self.assertEqual(len(counted), by_form)
            self.assertEqual((body['relations'][0]['numbers']['matched'], body['relations'][0]['numbers']['empty']), (MATCHED, EMPTY))

    def test_a_relationships_test_on_a_model_that_cannot_be_read_is_not_pinned_on_its_target(self):
        weird = {'model.shop.weird': {'resource_type': 'model', 'name': ['not', 'text'], 'unique_id': 'model.shop.weird'}}
        node = next(iter(generic_test('relationships', 'weird', 'customer_id', also=('customers',), to="ref('customers')", field='customer_id').values()))
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            status, body = self.run_import(ann, json.dumps(manifest(extra={**weird, 'test.shop.weird_rel': node})), apply=False)
            self.assertEqual(status, 200, body)
            self.assertFalse([r for r in body['relations'] if r['from'] == r['to']], body['relations'])
            self.assertTrue(any('Cannot tell which model' in s['reason'] for s in body['skipped']), body['skipped'])

    def test_the_chinese_reasons_carry_no_english_words_in_brackets(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            status, body = ann.post(ROUTE, {'manifest': json.dumps(manifest()), 'apply': False}, headers={'Accept-Language': 'zh-CN'})
            self.assertEqual(status, 200, body)
            reason = next(s['reason'] for s in body['skipped'] if s['model'] == 'order_items' and s['what'] == '对象类型')
            self.assertNotIn('no key', reason)

    def test_the_dialog_text_says_a_check_on_a_large_table_can_take_minutes(self):
        import re
        from pathlib import Path
        app = Path(__file__).resolve().parents[1] / 'landing-page/src/app/i18n'
        self.assertRegex((app / 'en/types.js').read_text(encoding='utf-8'), re.compile(r'"dbt\.slow": ".*minutes'))
        self.assertRegex((app / 'zh/types.js').read_text(encoding='utf-8'), re.compile(r'"dbt\.slow": ".*分钟'))

    def test_after_the_first_type_fails_only_what_would_have_been_tried_is_listed_as_not_attempted(self):
        def fail(*args, **kwargs):
            raise RuntimeError('boom')
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            with mock.patch.object(dbt_import, 'create_type', side_effect=fail):
                status, body = self.run_import(ann, json.dumps(manifest()), apply=True)
            self.assertEqual(status, 200, body)
            self.assertEqual([f['what'] for f in body['failed']], ['object type customers'])
            listed = [n['what'] for n in body['not_attempted']]
            self.assertIn('object type orders', listed)
            self.assertFalse([w for w in listed if 'order_items' in w or 'payments' in w], listed)   # order_items has no key in its tests and payments no dataset: neither would have been tried

    def written_ids(self, out):
        return {e for e, _, _ in self.written(out)[0]}

    def test_planning_the_relations_happens_before_any_write_so_its_error_is_a_true_nothing_was_written(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            with mock.patch.object(dbt_import, '_relation_jobs', side_effect=RuntimeError('database is locked')):
                status, body = self.run_import(ann, json.dumps(manifest()), apply=True)
            self.assertEqual(status, 400, body)
            self.assertIn('nothing was written', body['error'])
            self.assertEqual(self.written(out), ([], 0))   # and it is true: the types were not written before it

    def test_an_error_after_the_types_were_written_in_the_relation_step_answers_a_report(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            with mock.patch.object(dbt_import, '_relation', side_effect=sqlite3.OperationalError('database is locked')):
                status, body = self.run_import(ann, json.dumps(manifest()), apply=True)
            self.assertEqual(status, 200, body)
            self.assertNotIn('nothing was written', json.dumps(body))
            self.assertTrue(body['stopped'])
            self.assertEqual({(t['id'], t['status']) for t in body['types']}, {('customers', 'new'), ('orders', 'new')})
            self.assertEqual(self.written_ids(out), {'objtype:customers', 'objtype:orders'})
            self.assertIn('customer_id', body['failed'][0]['what'])

    def test_an_error_while_the_report_is_built_after_everything_was_written_still_answers_a_report(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            with mock.patch.object(dbt_import, '_finish', side_effect=RuntimeError('boom')):
                status, body = self.run_import(ann, json.dumps(manifest()), apply=True)
            self.assertEqual(status, 200, body)
            self.assertNotIn('nothing was written', json.dumps(body))
            self.assertTrue(body['stopped'])
            self.assertEqual({t['id'] for t in body['types']}, {'customers', 'orders'})
            self.assertEqual([r['id'] for r in body['relations']], ['orders_customer_id'])
            self.assertEqual(self.written_ids(out), {'objtype:customers', 'objtype:orders', 'relation:orders_customer_id'})
            self.assertTrue(body['failed'])

    def test_a_type_written_whose_report_line_then_fails_is_listed_as_written_not_as_not_written(self):
        real = dbt_import._type_line

        def line(conn, row, model, status):
            if status == 'new' and model == 'customers':
                raise RuntimeError('boom')
            return real(conn, row, model, status)
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            with mock.patch.object(dbt_import, '_type_line', side_effect=line):
                status, body = self.run_import(ann, json.dumps(manifest()), apply=True)
            self.assertEqual(status, 200, body)
            self.assertIn('objtype:customers', self.written_ids(out))
            self.assertIn('customers', [t['id'] for t in body['types']])
            self.assertIn('written', body['failed'][0]['reason'])
            self.assertNotIn('not written', body['failed'][0]['reason'])

    def test_a_preview_that_stops_never_says_written_in_either_language(self):
        def always(*args, **kwargs):
            raise RuntimeError('boom')
        real_type, real_line, calls = dbt_import.create_type, dbt_import._type_line, []

        def second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError('boom')
            return real_type(*args, **kwargs)

        def line(conn, row, model, status):
            if status == 'new' and model == 'orders':
                raise RuntimeError('boom')
            return real_line(conn, row, model, status)
        cases = {'first item': ('create_type', always), 'middle item': ('create_type', second), 'last item': ('create_relation', always),
                 'building the report': ('_finish', always), "an item's line": ('_type_line', line)}
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            for label, (target, effect) in cases.items():
                for language in ('en', 'zh-CN'):
                    with self.subTest(case=label, language=language):
                        calls.clear()
                        with mock.patch.object(dbt_import, target, side_effect=effect):
                            status, body = ann.post(ROUTE, {'manifest': json.dumps(manifest()), 'apply': False}, headers={'Accept-Language': language})
                        self.assertEqual(status, 200, body)
                        self.assertTrue(body['stopped'])
                        text = json.dumps(body, ensure_ascii=False)
                        self.assertNotIn('written', text.lower())
                        self.assertNotIn('写入', text)
            self.assertEqual(self.written(out), ([], 0))   # and the real workspace is unchanged

if __name__ == '__main__':
    unittest.main()
