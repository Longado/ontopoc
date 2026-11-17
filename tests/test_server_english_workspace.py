"""The sentences the workspace service writes (object types, relations, the review queue, actions, notices, sources, accounts, boards) come in the asker's
language: Chinese by default, English when the request asked for it (lang.use('en')). Each test checks one module with real input, in English, and that the
Chinese is unchanged without the switch. The names and values inside a sentence are the data's and stay as they are."""
import json
import re
import unittest

from ontology_poc_generator import lang
from ontology_poc_generator.accounts import ROLE_LABEL, password_problem
from ontology_poc_generator.code_meanings import exclusion_text, shown, unconfirmed
from ontology_poc_generator.explorer import CHARTS, FILTER_OPS, ORDERS, STAT_COLUMNS, empty_group
from ontology_poc_generator.object_relations import CARDINALITY
from ontology_poc_generator.object_types import CAUSE_WORDS, TYPE_NAME, VIA_WORDS, limited_note, stale_note, stale_word
from ontology_poc_generator.notices import in_language, kept_in_both
from ontology_poc_generator.ontology_card import SAYS
from ontology_poc_generator.ontology_graph import CAUSE_LABEL, CARDINALITY_NAME
from ontology_poc_generator.review_queue import approval_item
from ontology_poc_generator.source_connect import describe, generic_failure
from ontology_poc_generator.workspace_sources import STATUS_WORDS
from tests import test_object_relations as relations
from tests import test_object_types as types

EN = {'Accept-Language': 'en-US,en;q=0.9'}
CJK = re.compile('[一-龥，。；：、（）“”「」？！]')


class EnglishWorkspaceTest(unittest.TestCase):
    def tearDown(self):
        lang.use('zh')

    def test_the_four_words_a_lineage_card_shows_for_why_it_needs_review(self):
        self.assertEqual((stale_word('data', 'self'), stale_word('definition', 'self'), stale_word('definition', 'parent'), stale_word('data', 'ancestor')),
                         ('数据变了', '定义改了', '上一步过时', '更上游过时'))
        lang.use('en')
        self.assertEqual((stale_word('data', 'self'), stale_word('definition', 'self'), stale_word('definition', 'parent'), stale_word('data', 'ancestor')),
                         ('Data changed', 'Definition changed', 'Previous step out of date', 'Further upstream out of date'))
        self.assertEqual((CAUSE_LABEL['upstream'], CAUSE_LABEL['far_upstream'], CAUSE_WORDS.get('nothing'), VIA_WORDS.get('parent')), ('Previous step out of date', 'Further upstream out of date', None, 'Previous step out of date'))

    def test_cardinality_types_and_the_chart_words_read_in_english_and_keep_their_keys(self):
        self.assertEqual((CARDINALITY['many_to_one'], CARDINALITY_NAME['one_to_many'], TYPE_NAME['decimal']), ('多对一', '一对多', '小数'))
        lang.use('en')
        self.assertEqual((CARDINALITY['many_to_one'], CARDINALITY_NAME['one_to_many'], TYPE_NAME['decimal'], TYPE_NAME.get('date')), ('many to one', 'one to many', 'decimal', 'date'))
        self.assertEqual(list(CARDINALITY), ['many_to_one', 'one_to_many', 'one_to_one'])   # the keys the page sends back are plain
        self.assertEqual((CHARTS['bar'], ORDERS['desc'], FILTER_OPS['ne'], STAT_COLUMNS['median'], empty_group()), ('Bar chart', 'Largest first', 'does not equal', 'Median', '(empty)'))
        self.assertEqual([name for _, name in STAT_COLUMNS.items()][:3], ['Filled', 'Sum', 'Average'])
        self.assertEqual(json.loads(json.dumps(CHARTS))['pie'], 'Pie chart')   # what the page receives is English too

    def test_the_card_words_a_code_and_a_limited_note_read_in_english(self):
        self.assertEqual((SAYS['amount']['running'], SAYS['grain'].get('unsure')), ('每次事件后的累计值', '说不清'))
        self.assertEqual(shown({'status': {'labels': {'2': '已取消'}}}, 'status', '3'), '3（含义未确认）')
        lang.use('en')
        self.assertEqual((SAYS['amount']['running'], SAYS['grain'].get('unsure'), list(SAYS['complete'])), ('A running total after each event', 'Not sure', ['full', 'partial', 'unsure']))
        self.assertEqual(shown({'status': {'labels': {'2': 'Cancelled'}}}, 'status', '3'), '3 (meaning not confirmed)')
        self.assertEqual(shown({'status': {'labels': {'2': 'Cancelled'}}}, 'status', '2'), '2 = Cancelled')
        self.assertEqual(exclusion_text({'orders.status': {'labels': {'0': 'Delivered', '1': 'In production', '2': 'Cancelled'}}}, 'orders.status', ['2']),
                         'status is not 2 (Cancelled): counts 0 Delivered, 1 In production')
        self.assertEqual(unconfirmed(), ' (meaning not confirmed)')
        self.assertEqual(limited_note(), 'A row rule limits you, so you cannot see statistics over all the data')
        self.assertIn('Refresh and look again', stale_note())

    def test_a_submission_waiting_in_the_review_queue_says_what_it_wants_in_english(self):
        rec = {'id': 4, 'action': 'Mark delivered', 'type': 'order', 'can_decide': True, 'can_withdraw': False, 'submitted_at': '2026-11-17T00:00:00+00:00', 'object': 'Order ORD1', 'kind': 'create', 'after_text': 'Order ID ORD1, Amount 5', 'before_text': '', 'change_text': '', 'submitted_by': 'Ann', 'reason': 'a new order',
               'state': 'pending', 'why': None, 'stale': False, 'dataset': 'Orders', 'dataset_version': 1, 'dataset_now': 1, 'undo_of': None}
        zh = [line['text'] for line in approval_item(rec)['lines']]
        self.assertEqual(zh[0], 'Ann 想新建 Order ORD1：Order ID ORD1, Amount 5')
        lang.use('en')
        lines = [line['text'] for line in approval_item(rec)['lines']]
        self.assertEqual(lines, ['Ann wants to create Order ORD1: Order ID ORD1, Amount 5', 'Reason: a new order',
                                 'Orders is still version 1, the one read at submission; approving checks the current values again'])
        changed = approval_item({**rec, 'kind': 'edit', 'change_text': 'Status: In production to Delivered'})['lines'][0]['text']
        self.assertEqual(changed, 'Ann wants to change Order ORD1: Status: In production to Delivered')
        deleted = approval_item({**rec, 'kind': 'delete', 'before_text': 'Order ID ORD1', 'undo_of': 7})['lines'][0]['text']
        self.assertEqual(deleted, 'Ann wants to delete Order ORD1: Order ID ORD1 (undo of #7)')
        stale = approval_item({**rec, 'stale': True, 'dataset_now': 3})['lines'][-1]['text']
        self.assertEqual(stale, 'Orders was version 1 when submitted and is now version 3: approving will find that the data changed, and nothing will be written')

    def test_a_notice_is_kept_in_both_languages_and_read_in_the_readers(self):
        text = kept_in_both(lambda: lang.tr('“标记交付”：已批准', '"Mark delivered": approved'))
        self.assertEqual(in_language(text), '“标记交付”：已批准')
        lang.use('en')
        self.assertEqual(in_language(text), '"Mark delivered": approved')
        self.assertEqual(in_language('only one text'), 'only one text')   # a notice kept as a plain string reads as it is
        self.assertEqual(kept_in_both('plain'), 'plain')

    def test_a_connection_that_fails_says_why_in_english(self):
        refused = ConnectionRefusedError()
        self.assertIn('拒绝', describe(refused, 'secret'))
        lang.use('en')
        self.assertEqual(describe(refused, 'secret'), 'The other side refused the connection: the address or port is wrong, or the database is not listening')
        self.assertTrue(generic_failure().startswith('Cannot connect to this source'))
        self.assertEqual((STATUS_WORDS['untested'], STATUS_WORDS['failed'], ROLE_LABEL['builder'], ROLE_LABEL['viewer']), ('Not tested', 'Failed', 'Builder', 'Viewer'))
        self.assertEqual(password_problem('short'), 'The password must be at least 12 characters, not counting spaces at either end')


class EnglishWorkspaceHttpTest(types.ObjectTypeTests):
    """The same service, asked with Accept-Language: en: a person who wrote a refusal, a stale reason and a relation line reads English; without the header it is Chinese."""

    def test_a_stale_confirmation_a_queue_card_a_relation_and_the_refusals_read_in_english_over_http(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            self.assertEqual(ann.post('/api/workspace/types', types.ORDER)[0], 200)
            meanings = self.meanings(self.detail(ann))
            confirm = {'id': 'order', 'column': '状态码', 'version': meanings['version'], 'seen': meanings['seen']}
            status, refused = ann.post('/api/workspace/types/confirm', confirm, headers=EN)
            self.assertEqual((status, refused['error']), (403, 'You put this forward yourself, so someone else must confirm it'))
            status, refused = ann.post('/api/workspace/types/confirm', confirm)
            self.assertEqual((status, refused['error']), (403, '这一条是你自己提的，要另一位来确认'))
            status, refused = vera.post('/api/workspace/types', {**types.ORDER, 'english_name': 'order2', 'name': '订单2'}, headers=EN)
            self.assertEqual((status, refused['error']), (403, 'Your role cannot do this'))
            status, refused = vera.post('/api/workspace/types', {**types.ORDER, 'english_name': 'order2', 'name': '订单2'})
            self.assertEqual((status, refused['error']), (403, '你的角色不能做这个'))
            status, refused = ann.post('/api/workspace/types', {**types.ORDER, 'english_name': 'new'}, headers=EN)
            self.assertEqual((status, refused['error']), (400, 'The English name cannot be "new": the New page uses that address'))
            self.assertEqual(bob.post('/api/workspace/types/confirm', confirm)[0], 200)
            shown = self.detail(bob)
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen']})[0], 200)
            relation = {**relations.RELATION, 'cardinality': 'many_to_many'}
            self.assertEqual(ann.post('/api/workspace/types', relations.CUSTOMER)[0], 200)
            status, refused = ann.post('/api/workspace/relations', relation, headers=EN)
            self.assertEqual(status, 400)
            self.assertTrue(refused['error'].startswith('Many to many needs a table that joins the two sides'), refused)
            status, saved = ann.post('/api/workspace/relations', relations.RELATION)
            self.assertEqual(status, 200, saved)
            check = bob.get('/api/workspace/relations/order_customer', headers=EN)[1]
            texts = [line['text'] for line in check['lines']]
            self.assertTrue(any(t.startswith('Of the 160 rows in 订单 version 1, 157 connected through "客户编号" to "客户编号" in 客户') for t in texts), texts)
            self.assertTrue(any(t.startswith('3 订单 rows have no 客户: KH099') for t in texts), texts)
            self.assertEqual((check['cardinality_label'] if 'cardinality_label' in check else None), None)
            zh_texts = [line['text'] for line in bob.get('/api/workspace/relations/order_customer')[1]['lines']]
            self.assertTrue(any('行订单找不到客户' in t for t in zh_texts), zh_texts)
            # the codes shift in a new version, uploaded by someone reading English: what the page says about it is English
            status, body = ann.post('/api/workspace/datasets/upload', {'files': [types.shifted_orders_csv()]}, headers=EN)
            self.assertEqual(status, 200, body)
            detail = bob.get('/api/workspace/types/order', headers=EN)[1]
            meaning = self.meanings(detail)
            self.assertEqual((meaning['state'], meaning['stale_word']), ('needs_look', 'Data changed'))
            self.assertIn('new: 3 (16 rows, no meaning)', meaning['reason'])
            self.assertIn('gone: 0 (was "已交付")', meaning['reason'])
            self.assertIn('version 2 (uploaded by Ann)', meaning['reason'])
            self.assertEqual((detail['state'], detail['stale_word']), ('needs_look', 'Previous step out of date'))
            self.assertEqual(detail['reason'], 'It uses the meanings of "状态码", which needs review (see the reason on that set of meanings)')
            self.assertEqual(bob.get('/api/workspace/types/order')[1]['stale_word'], '上一步过时')   # without the header the words are Chinese
            queue = bob.get('/api/workspace/queue', headers=EN)[1]['items']
            card = next(i for i in queue if i['element'] == 'objtype:order')
            self.assertEqual(card['stale_word'], 'Previous step out of date')
            self.assertEqual(card['lines'][0]['text'], 'It uses the meanings of "状态码", which needs review (see the reason on that set of meanings)')
            names = sorted(['订单属于客户', '订单', '客户', '状态码', '已交付', '生产中', '已取消', '客户编号', '城市'], key=len, reverse=True)
            words = [re.sub('|'.join(names), '', line['text']) for item in queue for line in item['lines'] + [{'text': item['title']}]]
            self.assertEqual([w for w in words if CJK.search(w)], [])   # what is left once the data's names are taken out is English


for _name in dir(types.ObjectTypeTests):   # the inherited walks run in their own module
    if _name.startswith('test_'):
        setattr(EnglishWorkspaceHttpTest, _name, None)


if __name__ == '__main__':
    unittest.main()
