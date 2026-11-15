"""The two places that rewrite the words of a reason: reason_for (what a page reads once a parent is confirmed again) and refresh_new_value_reasons (a view
waiting on a new code value, after its meanings are written or confirmed). On a bare workspace, so each rule is seen on its own."""
import json
import unittest
from unittest import mock

from ontology_poc_generator import object_views
from ontology_poc_generator.caliber import line_of
from ontology_poc_generator.object_types import _settled_since, element_row
from ontology_poc_generator.workspace_store import open_workspace


def element(conn, element_id, state, content, reason=None, anchors=None):
    conn.execute('INSERT INTO element_state (element_id, state, version, content_json, reason, anchors_json) VALUES (?, ?, 1, ?, ?, ?)',
                 (element_id, state, json.dumps(content, ensure_ascii=False), reason, json.dumps(anchors) if anchors else None))


class SettledSinceTests(unittest.TestCase):
    def test_a_name_with_a_backslash_is_kept_as_written_not_read_as_a_pattern(self):
        conn = open_workspace(':memory:')
        element(conn, 'objtype:x', 'confirmed', {'name': 'a\\d', 'english_name': 'x'})
        element(conn, 'objview:v', 'needs_look', {'name': 'v', 'type': 'x', 'filters': []}, reason='它用的“a\\d”类型需要再看（原因见那个对象类型）')
        conn.execute("INSERT INTO element_dep VALUES ('objview:v', 'objtype:x')")
        conn.execute("INSERT INTO confirmation (element_id, confirmed_by, confirmed_at) VALUES ('objtype:x', 'B\\1ob', '2026-11-15')")
        self.assertEqual(_settled_since(conn, element_row(conn, 'objview:v')), '它用的“a\\d”类型已经由 B\\1ob 重新确认，这一项还要再确认一次')


class LineOfTests(unittest.TestCase):
    def test_the_line_an_agent_reads_says_a_parent_was_confirmed_again_as_the_pages_do(self):
        conn = open_workspace(':memory:')
        element(conn, 'objtype:order', 'confirmed', {'name': '订单', 'english_name': 'order', 'dataset': '订单', 'key': ['订单号'], 'properties': [], 'description': ''})
        element(conn, 'objview:v', 'needs_look', {'name': '有效订单', 'type': 'order', 'filters': [{'column': '状态码', 'op': 'is_not', 'label': '已取消'}]},
                reason='它用的“订单”类型需要再看（原因见那个对象类型）')
        conn.execute("INSERT INTO element_dep VALUES ('objview:v', 'objtype:order')")
        conn.execute("INSERT INTO confirmation (element_id, confirmed_by, confirmed_at) VALUES ('objtype:order', 'Bob', '2026-11-15')")
        line = line_of(conn, 'objview:v')
        self.assertEqual(line['reason'], '它用的“订单”类型已经由 Bob 重新确认，这一项还要再确认一次')
        self.assertIn(line['reason'], line['line'])

class RefreshTests(unittest.TestCase):
    def test_only_a_reason_about_a_new_value_is_written_again(self):
        conn = open_workspace(':memory:')
        content = {'name': 'v', 'type': 'order', 'filters': [{'column': '状态码', 'op': 'is_not', 'label': '已取消'}]}
        element(conn, 'objview:new', 'needs_look', {**content, 'name': 'new'}, reason='“状态码”出现了新值 3（16 行）：新值 3 算不算进来？')
        element(conn, 'objview:rows', 'needs_look', {**content, 'name': 'rows'}, reason='确认时 144 / 160 行，现在 143 / 160 行')
        with mock.patch.object(object_views, 'new_value_reason', return_value='写好的新句子'):
            object_views.refresh_new_value_reasons(conn, 'order', '状态码')
        self.assertEqual(element_row(conn, 'objview:new')['reason'], '写好的新句子')
        self.assertEqual(element_row(conn, 'objview:rows')['reason'], '确认时 144 / 160 行，现在 143 / 160 行')   # sent back for its rows, not for a new value


if __name__ == '__main__':
    unittest.main()
