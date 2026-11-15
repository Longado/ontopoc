"""The early screen (/api/ontology/*) keeps whole tables in its runs and answers from them with no type list, row rule or kept-back value applied. So it is
only for a builder or an admin no such rule limits; a viewer, or a builder a type list or a row rule limits, uses the team app, where every read is filtered.
Found by the pre-pilot security review: a viewer limited to one customer read every customer's orders through the run pages."""
import json
import sqlite3
import unittest

from ontology_poc_generator.auth_http import limited_anywhere
from ontology_poc_generator.workspace_store import open_workspace
from tests.test_access import GateTestCase


class EarlyScreenTests(GateTestCase):
    def test_a_viewer_and_a_builder_a_rule_limits_are_refused_the_runs_and_the_ask_and_others_are_not(self):
        with self.service() as (base, out):
            people = self.team(base)
            admin, builder, viewer = people['admin'], people['builder'], people['viewer']
            for path in ('/api/ontology/runs', '/api/ontology/jobs/abc'):
                self.assertEqual(viewer.get(path)[0], 403, path)
            self.assertEqual(viewer.post('/api/ontology/ask', {'question': '有多少订单？'})[0], 403)
            self.assertEqual(viewer.get('/api/ontology/library')[0], 200)   # the reference ontologies hold no company data
            self.assertEqual(builder.get('/api/ontology/runs')[0], 200)
            self.assertEqual(admin.get('/api/ontology/runs')[0], 200)
            conn = sqlite3.connect(out / 'workspace.sqlite')
            conn.execute("INSERT INTO type_access(type_id, user_ids_json) VALUES ('objtype:order', '[]')")   # a type only the admin sees
            conn.commit()
            conn.close()
            status, body = builder.get('/api/ontology/runs')
            self.assertEqual(status, 403)
            self.assertIn('团队应用', body['error'])   # where to go instead
            self.assertEqual(builder.post('/api/ontology/ask', {'question': '有多少订单？'})[0], 403)
            self.assertEqual(admin.get('/api/ontology/runs')[0], 200)   # an admin is never limited


class LimitedAnywhereTests(unittest.TestCase):
    def test_a_type_list_or_a_row_rule_that_does_not_give_all_rows_limits_a_person_and_an_admin_is_never_limited(self):
        conn = open_workspace(':memory:')
        builder, other, admin = {'id': 5, 'role': 'builder'}, {'id': 6, 'role': 'builder'}, {'id': 1, 'role': 'admin'}
        self.assertFalse(limited_anywhere(conn, builder))
        conn.execute("INSERT INTO element_state (element_id, state, version, content_json) VALUES ('objtype:t', 'confirmed', 1, ?)", (json.dumps({'dataset': 'd'}),))
        conn.execute("INSERT INTO row_rule(type_id, column_name, value, user_ids_json) VALUES ('objtype:t', '城市', '苏州', '[5]')")
        self.assertTrue(limited_anywhere(conn, builder))    # sees the 苏州 rows only
        self.assertTrue(limited_anywhere(conn, other))      # named on no rule of a ruled type: no rows
        self.assertFalse(limited_anywhere(conn, admin))
        conn.execute("DELETE FROM row_rule")
        conn.execute("INSERT INTO type_access(type_id, user_ids_json) VALUES ('objtype:t', '[5]')")
        self.assertFalse(limited_anywhere(conn, builder))   # on the list
        self.assertTrue(limited_anywhere(conn, other))      # not on it


if __name__ == '__main__':
    unittest.main()
