"""The MCP `ask` tool tells an agent that a WHERE in an answer's query is the model's own filter on confirmed code meanings, not a confirmed view: a question about
"valid orders" with no confirmed view behind it came back as a plain number (124,790) an agent could pass on as the confirmed definition."""
import unittest

from ontology_poc_generator import mcp_server


class Session:
    def __init__(self, body):
        self.body = body

    def request(self, path, payload=None):
        return self.body


ANSWER = {'status': 'answered', 'answer': {'total': 114}, 'definitions': [{'id': 'objtype:order', 'kind': 'type', 'name': 'Order', 'state': 'confirmed'}], 'datasets': {'orders': 1}}


class AskFilterNoteTests(unittest.TestCase):
    def test_a_filter_the_model_wrote_is_said_to_be_its_own(self):
        got = mcp_server.ask(Session({**ANSWER, 'query_text': "SELECT sum(o.amount) AS 合计\nFROM (o:`Order`)\nWHERE o.status_code NOT IN ('Cancelled', 'Refunded')"}), {'question': '有效订单的总金额是多少？'})
        self.assertIn('模型', got['filter_note'])
        self.assertIn('不是已确认的视图', got['filter_note'])

    def test_no_filter_or_no_answer_has_no_note(self):
        self.assertNotIn('filter_note', mcp_server.ask(Session({**ANSWER, 'query_text': 'SELECT count(o) FROM (o:`Order`)'}), {'question': '一共有多少订单？'}))
        self.assertNotIn('filter_note', mcp_server.ask(Session({'status': 'refused', 'reason': 'x', 'query_text': "SELECT count(o) FROM (o:`Order`) WHERE o.status_code = 'Paid'"}), {'question': 'x'}))


if __name__ == '__main__':
    unittest.main()
