"""A workspace whose types have no value rules answers and stores exactly what it did before value rules existed. The walk below goes through the type routes
(propose, read, edit, confirm, the queue, the agent's readouts, uploads that recheck the type) and the rows it leaves in the file; what it saw was recorded
once, before value rules were built, in golden/types_without_rules.json. Times are blanked: they are the only thing that may differ between two walks.

To record it again (only when an intended change to these routes lands): ONTOPOC_RECORD_GOLDEN=1 python -m unittest tests.test_types_without_rules"""
import json
import os
import re
import sqlite3
from pathlib import Path

from tests.test_object_types import MEANINGS, ORDER, TABLES, orders_upload, shifted_orders_csv
from tests.test_two_person import SigningTestCase

GOLDEN = Path(__file__).parent / 'golden' / 'types_without_rules.json'
TIME = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+00:00|Z)?')


def blank_times(value):
    if isinstance(value, str):
        return TIME.sub('<time>', value)
    if isinstance(value, list):
        return [blank_times(v) for v in value]
    if isinstance(value, dict):
        return {k: blank_times(v) for k, v in value.items()}
    return value


def stored(out: Path) -> dict:
    """What the walk left in the file: the definitions, what they read, their confirmations, the checks, the log and the notices."""
    conn = sqlite3.connect(out / 'workspace.sqlite')
    try:
        def rows(sql):
            cursor = conn.execute(sql)
            names = [c[0] for c in cursor.description]
            return [dict(zip(names, r)) for r in cursor]
        return {'element_state': rows('SELECT * FROM element_state ORDER BY element_id'),
                'element_dep': rows('SELECT * FROM element_dep ORDER BY element_id, depends_on'),
                'confirmation': rows('SELECT * FROM confirmation ORDER BY id'),
                'check_result': rows('SELECT * FROM check_result ORDER BY id'),
                'log': rows("SELECT * FROM log WHERE element_id IS NULL OR element_id NOT LIKE 'session%' ORDER BY rowid"),
                'notice': rows('SELECT * FROM notice ORDER BY id')}
    finally:
        conn.close()


class TypesWithoutRulesTests(SigningTestCase):
    def walk(self) -> dict:
        seen = {}
        with self.service() as (base, out):
            team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            seen['upload'] = ann.post('/api/workspace/datasets/upload', {'files': TABLES})[0]
            seen['create'] = ann.post('/api/workspace/types', ORDER)
            seen['list_ann'] = ann.get('/api/workspace/types')
            seen['page_ann'] = ann.get('/api/workspace/types/order')
            seen['page_bob'] = bob.get('/api/workspace/types/order')
            seen['queue_bob'] = bob.get('/api/workspace/queue')
            meanings = next(p for p in seen['page_bob'][1]['properties'] if p['column'] == '状态码')['meanings']
            seen['confirm_meanings'] = bob.post('/api/workspace/types/confirm', {'id': 'order', 'column': '状态码', 'version': meanings['version'], 'seen': meanings['seen']})
            page = bob.get('/api/workspace/types/order')[1]
            seen['confirm_type'] = bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': page['version'], 'seen': page['seen']})
            seen['page_vera'] = vera.get('/api/workspace/types/order')
            seen['definitions_vera'] = vera.get('/api/workspace/agent/definitions')
            page = ann.get('/api/workspace/types/order')[1]
            seen['edit_names'] = ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': page['version'], 'description': '一张订单'})
            page = ann.get('/api/workspace/types/order')[1]
            more = {**ORDER, 'id': 'order', 'version': page['version'], 'description': '一张订单', 'properties': [*ORDER['properties'], {'column': '数量'}], 'enums': {'状态码': MEANINGS}}
            seen['edit_properties'] = ann.post('/api/workspace/types/update', more)
            seen['page_after_edit'] = bob.get('/api/workspace/types/order')
            page = seen['page_after_edit'][1]
            seen['confirm_again'] = bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': page['version'], 'seen': page['seen']})
            seen['negative_amount'] = ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(lambda r, i: {**r, '金额': '-5'} if i < 3 else r)]})[0]
            seen['page_after_negative'] = bob.get('/api/workspace/types/order')
            seen['shifted'] = ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0]
            seen['page_shifted_bob'] = bob.get('/api/workspace/types/order')
            seen['page_shifted_vera'] = vera.get('/api/workspace/types/order')
            seen['list_vera'] = vera.get('/api/workspace/types')
            seen['queue_after'] = bob.get('/api/workspace/queue')
            seen['unconfirmed_ann'] = ann.get('/api/workspace/agent/unconfirmed')
            seen['standing_ann'] = ann.get('/api/workspace/agent/standing')
            seen['standing_vera'] = vera.get('/api/workspace/agent/standing')
            seen['log_bob'] = bob.get('/api/workspace/types/order/log')
            seen['notices_bob'] = bob.get('/api/workspace/notices')
            seen['stored'] = stored(out)
        return blank_times(json.loads(json.dumps(seen, ensure_ascii=False)))

    def test_a_workspace_with_no_rules_answers_and_stores_what_it_did_before(self):
        now = self.walk()
        if os.environ.get('ONTOPOC_RECORD_GOLDEN') == '1':
            GOLDEN.parent.mkdir(exist_ok=True)
            GOLDEN.write_text(json.dumps(now, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        before = json.loads(GOLDEN.read_text(encoding='utf-8'))
        self.maxDiff = None
        for part in before:
            self.assertEqual(now[part], before[part], part)
        self.assertEqual(set(now), set(before))
