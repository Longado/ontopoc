"""Value rules with no conditional rule and no citation answer and store exactly what they did before conditional rules, citations and conflict findings existed
(ops/cards/cited-rules.md, rule 5). The walk below goes through the type routes with every kind of value rule there was (propose, refusals, read, the queue, the
agent's readouts, confirm, a refused confirm, an edit, uploads that recheck the type, the log and the notices) in a workspace that also holds a confirmed document
and a waiting one, and keeps the rows it leaves in the file. What it saw was recorded once from the base commit's code (c244fa3f), before any of this card was
built, in golden/cited_rules_main.json. Times are blanked: they are the only thing that may differ between two walks.

To record it again (only on a checkout of the base, never to make a change pass): ONTOPOC_RECORD_GOLDEN=1 python -m unittest tests.test_cited_rules_main"""
import base64
import json
import os
from pathlib import Path

from tests.test_object_types import MEANINGS, ORDER, TABLES, orders_upload
from tests.test_two_person import SigningTestCase
from tests.test_types_without_rules import blank_times, stored

GOLDEN = Path(__file__).parent / 'golden' / 'cited_rules_main.json'
EN = {'Accept-Language': 'en'}
POLICY = '''# 订单管理规定

第一条 金额：每一笔订单的金额都要大于零，以订单为准。

第二条 数量：一张订单的数量在 1 到 50 之间。
'''
RULES = [
    {'column': '金额', 'check': 'not_empty'},
    {'column': '金额', 'check': 'gt', 'value': 0},
    {'column': '数量', 'check': 'between', 'low': 1, 'high': 50},
    {'column': '交付天数', 'check': 'ge', 'value': 0},
    {'column': '状态码', 'check': 'in_codes'},
    {'column': '下单日期', 'check': 'not_empty'},
]
RULED = {**ORDER, 'properties': [*ORDER['properties'], {'column': '数量'}, {'column': '交付天数'}, {'column': '下单日期'}], 'rules': RULES}
REFUSED = [   # rules the base refuses, each with its own sentence
    [{'column': '没有这列', 'check': 'not_empty'}],
    [{'column': '金额', 'check': 'xyz'}],
    [{'column': '下单日期', 'check': 'gt', 'value': 1}],
    [{'column': '数量', 'check': 'between', 'low': 9, 'high': 1}],
    [{'column': '金额', 'check': 'gt', 'value': 'abc'}],
    [{'column': '金额', 'check': 'not_empty'}, {'column': '金额', 'check': 'not_empty'}],
    [{'column': '数量', 'check': 'in_codes'}],
    [{'column': '下单日期', 'check': 'not_before', 'other': '金额'}],
    {'column': '金额', 'check': 'not_empty'},
]


def document(name: str, text: str, builders_only: bool = False) -> dict:
    return {'filename': name, 'content_base64': base64.b64encode(text.encode()).decode(), 'builders_only': builders_only}


class ExistingRulesAsBeforeTests(SigningTestCase):
    def walk(self) -> dict:
        seen = {}
        with self.service() as (base, out):
            team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            seen['upload'] = ann.post('/api/workspace/datasets/upload', {'files': TABLES})[0]
            status, doc = ann.post('/api/workspace/documents/upload', document('订单管理规定.md', POLICY))
            seen['doc_upload'] = status
            seen['doc_confirm'] = bob.post('/api/workspace/documents/confirm', {'id': doc['id'], 'version': doc['version']})[0]
            seen['doc_waiting'] = ann.post('/api/workspace/documents/upload', document('草稿.md', '# 草稿\n\n第一条 金额要大于零。\n', True))[0]
            for i, rules in enumerate(REFUSED):
                seen[f'refused_{i}'] = ann.post('/api/workspace/types', {**RULED, 'rules': rules})
                seen[f'refused_{i}_en'] = ann.post('/api/workspace/types', {**RULED, 'rules': rules}, headers=EN)
            seen['create'] = ann.post('/api/workspace/types', RULED)
            seen['list_ann'] = ann.get('/api/workspace/types')
            seen['page_ann'] = ann.get('/api/workspace/types/order')
            seen['page_bob'] = bob.get('/api/workspace/types/order')
            seen['page_bob_en'] = bob.get('/api/workspace/types/order', headers=EN)
            seen['queue_bob'] = bob.get('/api/workspace/queue')
            seen['queue_bob_en'] = bob.get('/api/workspace/queue', headers=EN)
            meanings = next(p for p in seen['page_bob'][1]['properties'] if p['column'] == '状态码')['meanings']
            seen['confirm_meanings'] = bob.post('/api/workspace/types/confirm', {'id': 'order', 'column': '状态码', 'version': meanings['version'], 'seen': meanings['seen']})
            page = bob.get('/api/workspace/types/order')[1]
            seen['confirm_own'] = ann.post('/api/workspace/types/confirm', {'id': 'order', 'version': page['version'], 'seen': page['seen']})
            seen['confirm_type'] = bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': page['version'], 'seen': page['seen']})
            seen['page_vera'] = vera.get('/api/workspace/types/order')
            seen['list_vera'] = vera.get('/api/workspace/types')
            seen['definitions_vera'] = vera.get('/api/workspace/agent/definitions')
            seen['definitions_ann'] = ann.get('/api/workspace/agent/definitions')
            page = ann.get('/api/workspace/types/order')[1]
            seen['edit_names'] = ann.post('/api/workspace/types/update', {**RULED, 'id': 'order', 'version': page['version'], 'description': '一张订单'})
            page = ann.get('/api/workspace/types/order')[1]
            seen['edit_rules'] = ann.post('/api/workspace/types/update', {**RULED, 'id': 'order', 'version': page['version'], 'description': '一张订单', 'enums': {'状态码': MEANINGS},
                                                                          'rules': [*RULES, {'column': '交付天数', 'check': 'le', 'value': 60}]})
            seen['page_after_edit'] = bob.get('/api/workspace/types/order')
            page = seen['page_after_edit'][1]
            seen['confirm_again'] = bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': page['version'], 'seen': page['seen']})
            seen['negative_amount'] = ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(lambda r, i: {**r, '金额': '-5'} if i < 3 else r)]})[0]
            seen['page_after_negative'] = bob.get('/api/workspace/types/order')
            seen['page_after_negative_vera'] = vera.get('/api/workspace/types/order')
            page = seen['page_after_negative'][1]
            seen['confirm_broken'] = bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': page['version'], 'seen': page['seen']})
            seen['confirm_broken_en'] = bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': page['version'], 'seen': page['seen']}, headers=EN)
            seen['queue_after'] = bob.get('/api/workspace/queue')
            seen['mended'] = ann.post('/api/workspace/datasets/upload', {'files': [orders_upload()]})[0]
            seen['page_mended'] = bob.get('/api/workspace/types/order')
            seen['unconfirmed_ann'] = ann.get('/api/workspace/agent/unconfirmed')
            seen['standing_ann'] = ann.get('/api/workspace/agent/standing')
            seen['standing_vera'] = vera.get('/api/workspace/agent/standing')
            seen['log_bob'] = bob.get('/api/workspace/types/order/log')
            seen['notices_bob'] = bob.get('/api/workspace/notices')
            seen['notices_ann'] = ann.get('/api/workspace/notices')
            seen['documents_vera'] = vera.get('/api/workspace/documents')
            seen['stored'] = stored(out)
        return blank_times(json.loads(json.dumps(seen, ensure_ascii=False)))

    def test_existing_value_rules_answer_and_store_what_they_did_at_the_base(self):
        now = self.walk()
        if os.environ.get('ONTOPOC_RECORD_GOLDEN') == '1':
            GOLDEN.parent.mkdir(exist_ok=True)
            GOLDEN.write_text(json.dumps(now, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        before = json.loads(GOLDEN.read_text(encoding='utf-8'))
        self.maxDiff = None
        for part in before:
            self.assertEqual(now[part], before[part], part)
        self.assertEqual(set(now), set(before))
