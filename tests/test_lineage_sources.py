"""Data sources on the lineage graph (血缘): a database connection is drawn in front of the datasets it fills, and a dataset says where its current version came
from (a source's table, an upload, a pipeline). What the graph says of a source is what its page says to the same person: name, kind and whether it works, never
the host, the account or the password. A viewer is not shown sources (their page is a builder's), and is told only that a dataset came from a source."""
import json
import unittest

from tests.test_object_types import TABLES
from tests.test_sources import PASSWORD, SourceCase

LINEAGE = '/api/workspace/graph/lineage'


def load_tests(loader, standard, pattern):
    return unittest.TestSuite(cls(name) for cls in (LineageSourceTests, CameFromNamingTests) for name in vars(cls) if name.startswith('test_'))


class LineageSourceTests(SourceCase):
    def graph(self, client):
        status, body = self.ask(client, 'get', LINEAGE)
        self.assertEqual(status, 200, body)
        return {n['id']: n for n in body['nodes']}, {(e['from'], e['to']) for e in body['edges']}

    def test_a_source_is_drawn_before_the_dataset_it_fills_and_a_dataset_says_where_it_came_from(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            nodes, edges = self.graph(ann)
            self.assertEqual(nodes['source:订单库']['tables'], [])   # a source nothing is read from yet is there for a builder
            self.pull(ann)
            self.assertEqual(self.ask(ann, 'post', '/api/workspace/datasets/upload', {'files': [t for t in TABLES if t['filename'].startswith('客户')]})[0], 200)
            nodes, edges = self.graph(ann)
            source = nodes['source:订单库']
            self.assertEqual((source['kind'], source['name'], source['kind_label'], source['tables']), ('source', '订单库', 'PostgreSQL', [{'table': 'orders', 'dataset': '订单'}]))
            self.assertIn(('source:订单库', 'dataset:订单'), edges)
            self.assertEqual(nodes['dataset:订单']['came_from'], {'kind': 'source', 'source': '订单库', 'table': 'orders'})
            uploaded = next(n for n in nodes.values() if n['kind'] == 'dataset' and n['name'].startswith('客户'))
            self.assertEqual(uploaded['came_from'], {'kind': 'upload'})
            said = json.dumps(list(nodes.values()), ensure_ascii=False)
            for secret in (PASSWORD, 'localhost', '15432', 'reader', 'shop'):
                self.assertNotIn(secret, said)   # the connection is the admin's, on the source page, not on the graph

    def test_a_source_whose_last_test_failed_says_so_on_its_node(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.pull(team['ann'])
            self.db = None
            self.ask(team['admin'], 'post', '/api/workspace/sources/test', {'name': '订单库'})
            node = self.graph(team['ann'])[0]['source:订单库']
            self.assertEqual(node['status'], 'failed')
            self.assertTrue(node['status_label'])
            self.assertNotIn('password', json.dumps(node, ensure_ascii=False))

    def test_a_viewer_sees_no_source_and_only_that_a_dataset_came_from_one(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            self.pull(ann)
            from tests.test_sources import ORDER_TYPE
            self.assertEqual(self.ask(ann, 'post', '/api/workspace/types', ORDER_TYPE)[0], 200)
            for column in ('状态码', None):
                self.assertEqual(self.confirm(bob, column)[0], 200)
            nodes, edges = self.graph(vera)
            self.assertFalse([n for n in nodes.values() if n['kind'] == 'source'])
            self.assertEqual(nodes['dataset:订单']['came_from'], {'kind': 'source'})
            self.assertNotIn('订单库', json.dumps(list(nodes.values()), ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()


class CameFromNamingTests(unittest.TestCase):
    """Found in the review of PR #86: a pipeline or an action is named only to someone who may see it, whatever the dataset version says."""

    def test_a_pipeline_or_action_this_person_may_not_see_is_not_named(self):
        from unittest import mock
        from ontology_poc_generator import ontology_graph as g
        builder = {'id': 2, 'role': 'builder'}
        with mock.patch.object(g, 'element_row', return_value={'element_id': 'x'}), \
                mock.patch.object(g, 'pipeline_visible', return_value=False), mock.patch.object(g, 'action_visible', return_value=False):
            self.assertEqual(g._came_from(None, 'pipeline:客户合计@run3', True, builder), {'kind': 'pipeline'})
            self.assertEqual(g._came_from(None, 'action:改状态', True, builder), {'kind': 'action'})
        with mock.patch.object(g, 'element_row', return_value={'element_id': 'x'}), \
                mock.patch.object(g, 'pipeline_visible', return_value=True), mock.patch.object(g, 'action_visible', return_value=True):
            self.assertEqual(g._came_from(None, 'pipeline:客户合计@run3', True, builder), {'kind': 'pipeline', 'pipeline': '客户合计'})
            self.assertEqual(g._came_from(None, 'action:改状态', True, builder), {'kind': 'action', 'action': '改状态'})
        with mock.patch.object(g, 'element_row', return_value=None):
            self.assertEqual(g._came_from(None, 'pipeline:已删除@run1', True, builder), {'kind': 'pipeline'})   # one that is gone is not named either
