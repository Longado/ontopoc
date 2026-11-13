"""Signatures come from the session, and a definition one person put forward is confirmed by another. Run through the real service with a
fake model, on the planted tables."""
import json
import sqlite3

from ontology_poc_generator import accounts
from tests.test_access import GOOD, Client, GateTestCase, table_part
from tests.test_card_server import CUSTOMER, UPLOAD, CardModel
from tests import test_workspace_store as planted   # the module, so its test classes are not collected a second time here

CODES = [{'value': '0', 'label': '进行中'}, {'value': '1', 'label': '已交付'}, {'value': '2', 'label': '已取消'}]
VIEW = dict(name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消')


class SigningTestCase(GateTestCase):
    def people(self, base, *names, roles=None):
        """root (admin, signed in) and one builder per name, each signed in and past the first-password change."""
        admin = Client(base)
        admin.login('root')
        people = {'admin': admin}
        for name in names:
            admin.post('/api/users', {'username': name, 'display_name': name.title(), 'role': (roles or {}).get(name, 'builder'), 'password': 'first password 1'})
            person = Client(base)
            person.login(name, 'first password 1')
            person.post('/api/auth/password', {'current': 'first password 1', 'new': GOOD})
            people[name] = person
        return people

    def build(self, client):
        status, run = client.post('/api/ontology/build', {'files': planted.ServerDataChecksTests.files})
        self.assertEqual(status, 200, run)
        return run

    def db(self, out):
        return sqlite3.connect(out / 'workspace.sqlite')


class WhoComesFromTheSessionTests(SigningTestCase):
    def test_a_name_typed_into_a_request_is_ignored_and_the_account_is_kept_beside_the_name(self):
        with self.service(gateway=planted.PlantedDraftModel()) as (base, out):
            team = self.people(base, 'ann')
            ann = team['ann']
            status, _ = ann.post('/api/workspace/datasets/upload', {'who': 'root', 'files': [table_part()]})
            self.assertEqual(status, 200)
            ann_id = next(u['id'] for u in team['admin'].get('/api/users')[1]['users'] if u['username'] == 'ann')
            versions = ann.get('/api/workspace/datasets/t')[1]['versions']
            self.assertEqual([v['who'] for v in versions], ['Ann'])
            run = self.build(ann)
            status, body = ann.post('/api/ontology/code-meanings', {'saved_as': run['saved_as'], 'id': 'code_meaning:订单.状态码', 'values': CODES, 'confirmed_by': 'root'})
            self.assertEqual(status, 200, body)
            self.assertEqual(ann.post('/api/ontology/bulk-approve', {'saved_as': run['saved_as'], 'ids': ['relation:x'], 'confirmed_by': 'root'})[0] // 100, 4)   # refused for its ids, not for a missing name
            conn = self.db(out)
            self.assertEqual(conn.execute("SELECT who, who_user_id FROM dataset WHERE name = 't'").fetchall(), [('Ann', ann_id)])
            self.assertEqual(conn.execute("SELECT confirmed_by, confirmed_by_user_id FROM element_state WHERE element_id LIKE 'property:%订单.状态码'").fetchall(), [('Ann', ann_id)])
            rows = conn.execute("SELECT who, user_id FROM log WHERE (element_id LIKE 'dataset:%' OR element_id LIKE 'property:%') AND who != 'system'").fetchall()   # the run's own import is the system's
            self.assertTrue(rows)
            self.assertEqual(set(rows), {('Ann', ann_id)})
            conn.close()

    def test_the_card_is_signed_by_the_session_too(self):
        with self.service(gateway=CardModel()) as (base, _):
            ann = self.people(base, 'ann')['ann']
            status, run = ann.post('/api/ontology/build', UPLOAD)
            self.assertEqual(status, 200, run)
            status, saved = ann.post('/api/ontology/card', {'saved_as': run['saved_as'], 'by': 'root', 'items': [], 'cells': [{'id': CUSTOMER, 'value': 'partial', 'note': '只导了一部分'}]})
            self.assertEqual(status, 200, saved)
            customer = next(o for o in saved['card']['objects'] if o['id'] == CUSTOMER)
            self.assertEqual(customer['answer']['by'], 'Ann')

    def test_the_old_free_text_signatures_stay_as_history_with_no_account(self):
        with self.service(gateway=planted.PlantedDraftModel(), no_auth=True) as (base, out):
            client = Client(base)
            self.assertEqual(client.post('/api/workspace/datasets/upload', {'who': '王工', 'files': [table_part()]})[0], 200)
            conn = self.db(out)
            self.assertEqual(conn.execute("SELECT who, who_user_id FROM dataset").fetchall(), [('王工', None)])
            conn.close()


class TwoPersonTests(SigningTestCase):
    def prepared(self, base, names=('ann', 'bob')):
        team = self.people(base, *names)
        first = team[names[0]]
        run = self.build(first)
        status, body = first.post('/api/ontology/code-meanings', {'saved_as': run['saved_as'], 'id': 'code_meaning:订单.状态码', 'values': CODES})
        self.assertEqual(status, 200, body)
        return team, run

    def view(self, client, run, **more):
        return client.post('/api/ontology/views', {'saved_as': run['saved_as'], **(more or VIEW)})

    def test_a_view_one_builder_puts_forward_is_confirmed_by_another_and_not_by_the_same(self):
        with self.service(gateway=planted.PlantedDraftModel()) as (base, out):
            team, run = self.prepared(base)
            self.assertEqual(team['admin'].get('/api/settings')[1]['two_person'], {'enabled': True, 'builders': 3, 'active': True})   # root, ann, bob
            status, body = self.view(team['ann'], run)
            self.assertEqual((status, body['message']), (200, '视图「有效订单」已提交，等另一位确认'))
            self.assertEqual([v['name'] for v in body['views']], ['订单'])   # nothing reads it yet
            self.assertEqual([(v['name'], v['proposed_by']) for v in body['proposed_views']], [('有效订单', 'Ann')])
            status, body = team['ann'].post('/api/ontology/views', {'saved_as': run['saved_as'], 'confirm': '有效订单'})
            self.assertEqual((status, body['error']), (400, '这一条是你自己提的，要另一位来确认'))
            status, body = team['bob'].post('/api/ontology/views', {'saved_as': run['saved_as'], 'confirm': '有效订单', 'confirmed_by': 'Ann'})
            self.assertEqual((status, body['message']), (200, '视图「有效订单」已确认'))
            kept = {v['name']: v for v in body['views']}['有效订单']
            self.assertEqual((kept['rows'], kept['confirmed_by']), (144, 'Bob'))
            self.assertEqual(body['proposed_views'], [])
            conn = self.db(out)
            self.assertEqual(conn.execute("SELECT state, proposed_by, confirmed_by FROM element_state WHERE element_id LIKE 'view:%'").fetchall(), [('confirmed', 'Ann', 'Bob')])
            ids = dict(conn.execute('SELECT display_name, id FROM user'))
            self.assertEqual(conn.execute("SELECT proposed_by_user_id, confirmed_by_user_id FROM element_state WHERE element_id LIKE 'view:%'").fetchone(), (ids['Ann'], ids['Bob']))
            marks = [json.loads(a).get('self_confirmed') for (a,) in conn.execute("SELECT after_json FROM log WHERE element_id LIKE 'view:%' AND change = 'confirmed'")]
            self.assertEqual(marks, [None])   # nobody confirmed their own
            conn.close()

    def test_something_nobody_put_forward_cannot_be_confirmed(self):
        with self.service(gateway=planted.PlantedDraftModel()) as (base, _):
            team, run = self.prepared(base)
            status, body = team['bob'].post('/api/ontology/views', {'saved_as': run['saved_as'], 'confirm': '没有这个'})
            self.assertEqual((status, '等着确认' in body['error']), (400, True))

    def test_a_viewer_cannot_confirm_and_a_proposal_changed_by_someone_else_needs_a_second_look(self):
        with self.service(gateway=planted.PlantedDraftModel()) as (base, _):
            team, run = self.prepared(base, ('ann', 'bob'))
            self.view(team['ann'], run)
            self.assertEqual(self.view(team['bob'], run, **{**VIEW, 'label': '进行中'})[1]['proposed_views'][0]['proposed_by'], 'Bob')   # Bob edited it: now it is Bob's
            self.assertEqual(team['ann'].post('/api/ontology/views', {'saved_as': run['saved_as'], 'confirm': '有效订单'})[1]['message'], '视图「有效订单」已确认')

    def test_with_one_person_who_can_confirm_the_rule_is_off_and_the_log_says_who_confirmed_their_own(self):
        with self.service(gateway=planted.PlantedDraftModel()) as (base, out):
            admin = Client(base)
            admin.login('root')
            run = self.build(admin)
            admin.post('/api/ontology/code-meanings', {'saved_as': run['saved_as'], 'id': 'code_meaning:订单.状态码', 'values': CODES})
            self.assertEqual(admin.get('/api/settings')[1]['two_person'], {'enabled': True, 'builders': 1, 'active': False})
            status, body = self.view(admin, run)
            self.assertEqual((status, body['message']), (200, '视图「有效订单」已确认'))
            conn = self.db(out)
            marks = [json.loads(a).get('self_confirmed') for (a,) in conn.execute("SELECT after_json FROM log WHERE element_id LIKE 'view:%' AND change = 'confirmed'")]
            self.assertEqual(marks, [True])
            conn.close()

    def test_an_admin_can_turn_it_off_for_a_team_and_a_builder_cannot(self):
        with self.service(gateway=planted.PlantedDraftModel()) as (base, _):
            team, run = self.prepared(base)
            self.assertEqual(team['ann'].post('/api/settings', {'two_person': False})[0], 403)
            self.assertEqual(team['admin'].post('/api/settings', {'two_person': False})[1]['two_person'], {'enabled': False, 'builders': 3, 'active': False})
            self.assertEqual(team['admin'].post('/api/settings', {'two_person': 'no'})[0], 400)
            self.assertEqual(self.view(team['ann'], run)[1]['message'], '视图「有效订单」已确认')   # one person, on their own account, with the rule off
            self.assertEqual(team['admin'].post('/api/settings', {'two_person': True})[1]['two_person']['active'], True)

    def test_disabling_the_second_builder_switches_the_rule_off_by_itself(self):
        with self.service(gateway=planted.PlantedDraftModel()) as (base, _):
            team, run = self.prepared(base, ('ann',))
            self.assertEqual(team['admin'].get('/api/settings')[1]['two_person']['active'], True)   # root and ann
            team['admin'].post('/api/users/disable', {'id': 2, 'disabled': True})
            self.assertEqual(team['admin'].get('/api/settings')[1]['two_person'], {'enabled': True, 'builders': 1, 'active': False})


class OlderFileTests(GateTestCase):
    def test_a_workspace_file_made_before_accounts_gains_the_columns_and_keeps_its_rows(self):
        import tempfile
        from pathlib import Path
        from ontology_poc_generator.workspace_store import open_workspace
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'workspace.sqlite'
            old = sqlite3.connect(path)
            old.executescript("""
                CREATE TABLE element_state (element_id TEXT PRIMARY KEY, state TEXT NOT NULL, evidence_ref TEXT, confirmed_by TEXT, confirmed_at TEXT, version INTEGER NOT NULL);
                CREATE TABLE log (time TEXT NOT NULL, who TEXT NOT NULL, element_id TEXT, change TEXT NOT NULL, before_json TEXT, after_json TEXT);
                INSERT INTO element_state VALUES ('view:k:v', 'confirmed', NULL, '王工', '2026-10-01T00:00:00+00:00', 3);
                INSERT INTO log VALUES ('2026-10-01T00:00:00+00:00', '王工', 'view:k:v', 'confirmed', NULL, NULL);""")
            old.commit()
            old.close()
            conn = open_workspace(path)
            self.assertEqual(conn.execute('SELECT confirmed_by, version, confirmed_by_user_id, proposed_by FROM element_state').fetchall(), [('王工', 3, None, None)])
            self.assertEqual(conn.execute('SELECT who, user_id FROM log').fetchall(), [('王工', None)])   # history stays as typed, with no account
            conn.close()
