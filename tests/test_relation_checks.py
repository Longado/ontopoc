"""A relation is checked on the stored tables: how many rows of its source find their object in the table that describes it, which
keys miss, which keys repeat on the described side, and whether the cardinality it declares holds. The numbers are the planted
fixtures', counted from the xlsx files by hand: 3 of 160 orders name KH099, which 客户 does not have; 客户 has KH012 twice and
2 orders name it."""
import json
import unittest

from ontology_poc_generator.relation_checks import check_relations, unmatched_answer, with_relation_gaps
from ontology_poc_generator.workspace_store import check_bundle, import_records, open_workspace, records_sha256
from tests.test_workspace_store import PLANTED_DRAFT, planted_bundle

RELATIONS = [
    {'key': 'order_customer', 'from': 'order', 'to': 'customer', 'source': '订单', 'label': '下单', 'meaning': '订单属于客户',
     'from_identity': {'order_id': '订单号'}, 'to_identity': {'customer_id': '客户编号'}},
    {'key': 'order_product', 'from': 'order', 'to': 'product', 'source': '订单', 'label': '含', 'meaning': '订单买的产品',
     'from_identity': {'order_id': '订单号'}, 'to_identity': {'product_id': '产品编号'}},
    {'key': 'ticket_engineer', 'from': 'ticket', 'to': 'engineer', 'source': '售后工单', 'label': '负责', 'meaning': '工单的负责人',
     'from_identity': {'ticket_id': '工单号'}, 'to_identity': {'engineer_id': '负责工程师'}}]
DRAFT = {**PLANTED_DRAFT, 'relations': RELATIONS}


class RelationCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = open_workspace(':memory:')
        cls.addClassCleanup(cls.conn.close)
        cls.found = {r['key']: r for r in check_bundle(cls.conn, DRAFT, planted_bundle(), 'planted')['relations']}

    def side(self, key):
        [side] = self.found[key]['sides']
        return side

    def test_orders_naming_a_customer_the_customer_table_does_not_have(self):
        side = self.side('order_customer')
        self.assertEqual((side['rows'], side['matched'], side['unmatched'], side['empty']), (160, 157, 3, 0))
        self.assertEqual((side['lookup'], side['unmatched_keys'], side['samples']), ('客户', 1, [{'key': 'KH099', 'rows': 3}]))
        self.assertEqual(side['if_trimmed'], 0)

    def test_a_key_that_repeats_on_the_described_side_says_how_many_rows_a_join_would_add(self):
        fanout = self.side('order_customer')['fanout']
        self.assertEqual((fanout['keys'], fanout['source_rows'], fanout['extra_rows'], fanout['samples']), (1, 2, 2, [{'key': 'KH012', 'rows': 2}]))
        self.assertEqual(self.side('order_product')['fanout']['keys'], 0)

    def test_a_relation_that_matches_everything_says_so(self):
        side = self.side('order_product')
        self.assertEqual((side['rows'], side['matched'], side['unmatched'], side['samples']), (160, 160, 0, []))

    def test_the_planted_relation_read_by_its_own_key_has_no_blank_rows_there(self):
        relation = self.found['order_product']
        self.assertEqual((relation['own_ends'], relation['own_blank']), (['from'], {'from': 0}))

    def test_an_end_no_table_describes_has_nothing_to_match_against(self):
        self.assertNotIn('ticket_engineer', self.found)

    def test_each_finding_is_a_check_result_tied_to_the_dataset_version_it_read(self):
        side = self.side('order_customer')
        rows = {r[0]: r for r in self.conn.execute('SELECT check_type, dataset_id, rows_checked, violations, status, element_id FROM check_result WHERE element_id LIKE ?', ('relation:order_customer%',)) if r[0] != 'relation_cardinality'}
        self.assertEqual(rows['relation_match'][1:], (self.found['order_customer']['dataset_id'], 160, 3, 'failed', 'relation:order_customer:to'))
        self.assertEqual(rows['relation_fanout'][1:5], (side['lookup_dataset_id'], 31, 1, 'failed'))
        name = self.conn.execute('SELECT name FROM dataset WHERE id = ?', (rows['relation_match'][1],)).fetchone()[0]
        self.assertEqual(name, '订单')

    def test_a_declared_cardinality_is_held_to_the_rows(self):
        cursor = self.conn.execute('SELECT * FROM dataset')
        datasets = {row[1]: dict(zip([c[0] for c in cursor.description], row)) for row in cursor}
        declared = lambda kind: check_relations(self.conn, {**DRAFT, 'relations': [{**RELATIONS[0], 'cardinality': kind}]}, datasets)[0]['cardinality']
        held = declared('many_to_one')
        self.assertEqual((held['holds'], held['observed'], held['most_from'], held['most_to']), (True, 'many_to_one', 1, 9))
        broken = declared('one_to_one')
        self.assertEqual(broken['holds'], False)
        self.assertEqual(self.found['order_customer']['cardinality']['holds'], None)   # nothing declared: said as observed only
        statuses = {r[0] for r in self.conn.execute("SELECT status FROM check_result WHERE check_type = 'relation_cardinality'")}
        self.assertEqual(statuses, {'skipped', 'passed', 'failed'})


class KeyShapeTests(unittest.TestCase):
    """Empty keys, keys that differ only in spaces or case, and keys of two columns."""
    def check(self, orders, customers):
        conn = open_workspace(':memory:')
        self.addCleanup(conn.close)
        datasets = {n: import_records(conn, n, rows, 't', records_sha256(rows)) for n, rows in (('订单', orders), ('客户', customers))}
        draft = {'object_types': [
            {'key': 'customer', 'label': '客户', 'populated_from': [{'source': '客户', 'identity': {'id': '编号'}}], 'attributes': [{'source': '客户', 'path': '名称'}]},
            {'key': 'order', 'label': '订单', 'populated_from': [{'source': '订单', 'identity': {'id': '订单号'}}], 'attributes': [{'source': '订单', 'path': '金额'}]}],
            'relations': [{'key': 'oc', 'from': 'order', 'to': 'customer', 'source': '订单', 'from_identity': {'id': '订单号'}, 'to_identity': {'id': '客户'}}]}
        self.last = check_relations(conn, draft, datasets)[0]
        return self.last['sides'][0]

    def test_empty_keys_are_not_matches_or_misses_and_near_misses_are_counted_apart(self):
        orders = [{'订单号': str(i), '金额': '1', '客户': k} for i, k in enumerate(['A', ' B', '', 'c', 'Z', 'Z'])]
        customers = [{'编号': 'A', '名称': 'a'}, {'编号': 'B', '名称': 'b'}, {'编号': 'C', '名称': 'c'}]
        side = self.check(orders, customers)
        self.assertEqual((side['rows'], side['empty'], side['matched'], side['unmatched']), (6, 1, 1, 4))
        self.assertEqual((side['unmatched_keys'], side['samples'][0], side['if_trimmed']), (3, {'key': 'Z', 'rows': 2}, 2))   # " B" and "c" would match trimmed / ignoring case


    def test_a_table_read_by_its_own_key_counts_the_rows_where_that_key_is_blank(self):
        orders = [{'订单号': str(i) if i > 3 else '', '金额': '1', '客户': 'A'} for i in range(10)]   # four of ten orders have no number
        side = self.check(orders, [{'编号': 'A', '名称': 'a'}])
        self.assertEqual(side['rows'], 10)
        self.assertEqual(self.last['own_blank'], {'from': 4})

    def test_keys_that_differ_only_in_how_a_number_is_written_are_near_misses_too(self):
        orders = [{'订单号': str(i), '金额': '1', '客户': k} for i, k in enumerate(['1.0', '001', '7', '2'])]
        customers = [{'编号': '1', '名称': 'a'}, {'编号': '2', '名称': 'b'}]
        side = self.check(orders, customers)
        self.assertEqual((side['unmatched'], side['if_trimmed']), (3, 2))     # 1.0 and 001 would match 1; 7 matches nothing

    def test_the_cost_follows_the_rows_not_rows_times_rows(self):
        import time
        orders = [{'订单号': str(i), '金额': '1', '客户': f'C{i % 20000}' if i % 50 else f'X{i}'} for i in range(40000)]
        customers = [{'编号': f'C{j}', '名称': 'a'} for j in range(20000)]
        started = time.monotonic()
        side = self.check(orders, customers)
        self.assertEqual(side['unmatched'], 800)
        self.assertLess(time.monotonic() - started, 10)        # 52 s when every order was looked for in the whole table


class AnswerNoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        conn = open_workspace(':memory:')
        cls.addClassCleanup(conn.close)
        cls.relations = check_bundle(conn, DRAFT, planted_bundle(), 'planted')['relations']

    def test_a_query_that_groups_by_the_other_object_says_the_rows_landed_in_no_group(self):
        query = {'start': 'order', 'group_by': [{'via': ['order_customer'], 'field': '客户.城市'}]}
        gap = with_relation_gaps({'status': 'answered'}, query, DRAFT, self.relations)['evidence']['relation_gaps']
        self.assertEqual(gap, [{'relation': 'order_customer', 'many': '订单', 'one': '客户', 'table': '客户', 'rows': 3, 'keys': ['KH099'], 'distinct': 1, 'effect': 'dropped'}])

    def test_a_query_that_only_walks_the_relation_says_the_object_is_still_counted(self):
        [gap] = with_relation_gaps({'status': 'answered'}, {'start': 'order', 'via': ['order_customer']}, DRAFT, self.relations)['evidence']['relation_gaps']
        self.assertEqual(gap['effect'], 'counted')

    def test_a_query_that_walks_no_relation_with_a_gap_is_left_alone(self):
        answer = {'status': 'answered'}
        self.assertIs(with_relation_gaps(answer, {'start': 'order', 'via': ['order_product']}, DRAFT, self.relations), answer)
        self.assertIs(with_relation_gaps(answer, {'start': 'order'}, DRAFT, self.relations), answer)

    def test_the_unmatched_question_is_answered_from_the_check(self):
        spec = lambda **kw: {'relation': 'order_customer', 'direction': 'many_without_one', 'other_conditions': False, **kw}
        answered = unmatched_answer(DRAFT, self.relations, spec())
        self.assertEqual((answered['status'], answered['answer']['total'], answered['answer']['relation_gap']['keys']), ('answered', 3, ['KH099']))
        self.assertIsNone(unmatched_answer(DRAFT, self.relations, spec(relation='no_such')))
        self.assertIsNone(unmatched_answer(DRAFT, self.relations, spec(relation='ticket_engineer')))
        self.assertIsNone(unmatched_answer(DRAFT, self.relations, 'order_customer'))           # not the shape asked for
        self.assertIsNone(unmatched_answer({**DRAFT, 'relations': []}, self.relations, spec()))   # a relation a person judged wrong is not in the ontology

    def test_the_other_direction_or_another_condition_is_not_what_the_check_counts(self):
        for says in ({'direction': 'one_without_many'}, {'other_conditions': True}, {'other_conditions': None}):
            refused = unmatched_answer(DRAFT, self.relations, {'relation': 'order_customer', 'direction': 'many_without_one', 'other_conditions': False, **says})
            self.assertEqual(refused['status'], 'query_limit', says)
            self.assertNotIn('answer', refused)
            self.assertIn('反过来问', refused['reason'])


class RelationQuestionServerTests(unittest.TestCase):
    """The model cannot write "no related object" as a query; it says which relation, and code answers from the relation check."""
    def setUp(self):
        from tests.test_ontology_ask_server import call
        from tests.test_ontology_server import OntologyServerTests
        from tests.test_workspace_store import ModelCompletion, ServerDataChecksTests
        asked = {
            '有多少订单的客户编号在客户表里找不到？': {'query': None, 'missing': 'query_language', 'unmatched_relation': {'relation': 'order_customer', 'direction': 'many_without_one', 'other_conditions': False}},
            '哪些客户没有订单？': {'query': None, 'missing': 'query_language', 'unmatched_relation': {'relation': 'order_customer', 'direction': 'one_without_many', 'other_conditions': False}},
            '已取消的订单里有多少客户找不到？': {'query': None, 'missing': 'query_language', 'unmatched_relation': {'relation': 'order_customer', 'direction': 'many_without_one', 'other_conditions': True}},
            '每个城市有多少订单？': {'query': {'start': 'order', 'group_by': [{'via': ['order_customer'], 'field': '客户.城市'}]}}}

        class Model:
            def complete_json(model, *, system_prompt, user_prompt):
                from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
                if system_prompt == QUESTION_SYSTEM_PROMPT:
                    q = json.loads(user_prompt).get('asked')
                    reply = {'questions': [{'question': q, 'reasoning': 'r', **asked[q]}] if q in asked else []}
                else:
                    reply = DRAFT
                return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(reply, ensure_ascii=False))
        server = OntologyServerTests().server(gateway=Model())
        self.base, self.out = server.__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        status, self.run = call(self.base, '/api/ontology/build', {'files': ServerDataChecksTests.files})
        self.assertEqual((status, self.run['ontology']['status']), (200, 'auto_built_verified'), self.run['ontology'].get('verification'))
        self.call = call

    def ask(self, question):
        status, run = self.call(self.base, '/api/ontology/ask', {'saved_as': self.run['saved_as'], 'question': question})
        self.assertEqual(status, 200, run)
        return run['evaluation']['asked'][-1]['items'][0]

    def test_the_relation_check_is_kept_with_the_run(self):
        relations = {r['key']: r for r in self.run['data_checks']['relations']}
        self.assertEqual(relations['order_customer']['sides'][0]['samples'], [{'key': 'KH099', 'rows': 3}])

    def test_how_many_orders_name_a_customer_the_table_does_not_have(self):
        item = self.ask('有多少订单的客户编号在客户表里找不到？')
        self.assertEqual((item['status'], item['answer']['total'], item['answer']['relation_gap']['keys']), ('answered', 3, ['KH099']))
        self.assertTrue(item['from_relation_check'])

    def test_the_questions_the_check_cannot_count_are_refused_not_answered_with_3(self):
        for question in ('哪些客户没有订单？', '已取消的订单里有多少客户找不到？'):
            item = self.ask(question)
            self.assertEqual(item['status'], 'query_limit', question)
            self.assertNotIn('answer', item)

    def test_a_question_asked_from_the_relation_check_does_not_break_the_lists_that_read_the_questions(self):
        """The answered item has no query; the open items, the card and the pages that save a rule read every asked question."""
        from urllib.request import urlopen
        self.ask('有多少订单的客户编号在客户表里找不到？')
        for path in ('open-items', 'card'):
            with urlopen(self.base + f"/api/ontology/runs/{self.run['saved_as']}/{path}", timeout=30) as response:
                self.assertEqual(response.status, 200, path)
        status, body = self.call(self.base, '/api/ontology/code-meanings', {'saved_as': self.run['saved_as'], 'id': 'code_meaning:订单.状态码', 'values': [{'value': '2', 'label': '已取消'}], 'confirmed_by': '王工'})
        self.assertEqual(status, 200, body)        # a save works the answers out again, and reads the same list

    def test_the_rule_chosen_for_a_repeated_key_is_sent_with_the_lists_so_the_page_can_say_what_became_of_the_fan_out(self):
        from urllib.request import urlopen
        status, body = self.call(self.base, '/api/ontology/repeat-rules', {'saved_as': self.run['saved_as'], 'id': 'repeated_key:customer.客户', 'rule': 'keep_both', 'confirmed_by': '王工'})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['repeat_rules']['customer.客户']['rule'], 'keep_both')
        with urlopen(self.base + f"/api/ontology/runs/{self.run['saved_as']}/open-items", timeout=30) as response:
            self.assertEqual(json.load(response)['repeat_rules']['customer.客户']['rule'], 'keep_both')

    def test_an_answer_that_walks_the_relation_notes_the_rows_it_could_not_place(self):
        item = self.ask('每个城市有多少订单？')
        self.assertEqual(item['status'], 'answered')
        [gap] = item['evidence']['relation_gaps']
        self.assertEqual((gap['rows'], gap['keys'], gap['effect']), (3, ['KH099'], 'dropped'))


if __name__ == '__main__':
    unittest.main()
