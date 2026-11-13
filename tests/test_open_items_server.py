import base64
import json
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from tests.test_ontology_ask_server import call
from tests.test_ontology_server import CSV, OntologyServerTests

UPLOAD = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}


def fetch(base, path):
    try:
        with urlopen(base + path, timeout=30) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


class OpenItemsRouteTests(unittest.TestCase):
    def test_a_kept_run_lists_what_is_still_to_be_settled(self):
        with OntologyServerTests().server() as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            status, body = fetch(base, f"/api/ontology/runs/{run['saved_as']}/open-items")
            self.assertEqual(status, 200, body)
            self.assertEqual(body['answered'], [])
            self.assertEqual([(i['kind'], i['ask']) for i in body['items']],
                             [('card_blank', '口径卡还有 4 格没说清（1 张表）：数值列能不能相加、日期列是什么时间、一行是什么、对象全不全。会上逐张过一遍？'),
                              ('unjudged', '2 个对象、1 条关系还没人判过对错。会上逐项过一遍？')])

    def test_judging_every_object_and_relation_empties_the_list(self):
        with OntologyServerTests().server() as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            decisions = {'types': {'order': {'verdict': 'ok'}, 'customer': {'verdict': 'ok'}}, 'relations': {'order_customer': {'verdict': 'ok'}}}
            call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions})
            status, body = fetch(base, f"/api/ontology/runs/{run['saved_as']}/open-items")
            self.assertEqual((status, [i['kind'] for i in body['items']], body['answered']), (200, ['card_blank'], []))   # the card is still to fill in

    def test_an_unknown_run_is_not_found(self):
        with OntologyServerTests().server() as (base, _):
            for name in ('20260101T000000Z-deadbeef.json', 'not-a-run.json'):
                with self.subTest(name=name):
                    status, body = fetch(base, f'/api/ontology/runs/{name}/open-items')
                    self.assertEqual(status, 404)
                    self.assertIn('找不到这次运行', body['error'])

    def test_an_ontology_that_did_not_pass_verification_has_no_items_but_still_lists_the_stored_tables(self):
        with OntologyServerTests().server() as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            path = out / run['saved_as']
            saved = json.loads(path.read_text(encoding='utf-8'))
            saved['ontology']['status'] = 'rejected'
            path.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
            status, body = fetch(base, f"/api/ontology/runs/{run['saved_as']}/open-items")
            self.assertEqual((status, body['items'], body['answered'], body['views']), (200, [], [], []))
            self.assertEqual([t['name'] for t in body['view_tables']], ['orders'])        # the tables are stored: views can still be made on them


class ColumnGapRouteTests(unittest.TestCase):
    def test_a_gap_the_model_names_a_column_in_is_an_item_about_that_column_and_can_be_answered(self):
        import copy
        from tests.test_workspace_store import PLANTED_DRAFT, DraftsModel, ServerDataChecksTests
        draft = {**copy.deepcopy(PLANTED_DRAFT), 'open_questions': ['订单的状态码没有字典，不知道 0、1、2 各是什么。', '售后工单的处理状态不知道有没有填全。', '库存是否完整，数据里看不出来。']}
        with OntologyServerTests().server(gateway=DraftsModel(draft)) as (base, _):
            _, run = call(base, '/api/ontology/build', {'files': ServerDataChecksTests.files})
            _, listed = fetch(base, f"/api/ontology/runs/{run['saved_as']}/open-items")
            gaps = {i['id']: i for i in listed['items'] if i['kind'] in ('data_gap', 'data_gaps')}
            self.assertEqual(set(gaps), {'data_gap:处理状态', 'data_gaps'})   # 状态码 has a code item of its own: the sentence is on that
            [codes] = [i for i in listed['items'] if i['id'] == 'code_meaning:订单.状态码']
            self.assertIn('模型指出：“订单的状态码没有字典，不知道 0、1、2 各是什么。”（模型的说法）', codes['facts'])
            self.assertEqual(gaps['data_gap:处理状态']['facts'], ['售后工单：45 行，「处理状态」0 行为空，2 个不同取值'])
            self.assertEqual(gaps['data_gap:处理状态']['target'], {'tab': 'data', 'table': '售后工单'})
            self.assertEqual(gaps['data_gaps']['facts'], ['库存是否完整，数据里看不出来。'])
            status, saved = call(base, '/api/ontology/card', {'saved_as': run['saved_as'], 'by': '王工', 'items': [{'id': 'data_gap:处理状态', 'text': '客户会给字典'}]})
            self.assertEqual(status, 200, saved)
            self.assertNotIn('data_gap:处理状态', {i['id'] for i in saved['items']})
            self.assertEqual([i['id'] for i in saved['answered'] if i['kind'] == 'data_gap'], ['data_gap:处理状态'])


class RepeatRuleRouteTests(unittest.TestCase):
    """客户 KH012 is on two rows. Until a rule is chosen both are listed; the choice is kept with who made it."""
    def setUp(self):
        import copy
        from tests.test_workspace_store import PLANTED_DRAFT, DraftsModel, ServerDataChecksTests
        self.draft, self.files = copy.deepcopy(PLANTED_DRAFT), ServerDataChecksTests.files
        self.model = DraftsModel(self.draft)

    def run_with(self, check):
        with OntologyServerTests().server(gateway=self.model) as (base, out):
            _, run = call(base, '/api/ontology/build', {'files': self.files})
            check(base, out, run['saved_as'])

    def customers(self, base, name):
        status, page = fetch(base, f'/api/ontology/runs/{name}/objects/customer?all=1')
        self.assertEqual(status, 200, page)
        return page

    def item(self, base, name):
        _, listed = fetch(base, f'/api/ontology/runs/{name}/open-items')
        return next((i for i in listed['items'] if i['id'] == 'repeated_key:customer.客户'), None)

    def test_the_repeat_is_an_item_and_the_list_shows_both_rows_with_where_each_number_comes_from(self):
        def check(base, out, name):
            item = self.item(base, name)
            self.assertEqual(item['facts'], ['KH012：2 行，城市：合肥 / 苏州'])
            page = self.customers(base, name)
            self.assertEqual((page['objects'], page['total'], page['mentioned_only']), (31, 32, {'count': 1, 'examples': ['KH099']}))
            marked = [(r['客户编号'], m) for r, m in zip(page['rows'], page['row_marks']) if m]
            self.assertEqual(marked, [('KH012', {'repeat': 'pending', 'rows': 2})] * 2)
        self.run_with(check)

    def test_choosing_a_rule_keeps_it_with_the_confirmer_and_the_item_closes(self):
        def check(base, out, name):
            status, body = call(base, '/api/ontology/repeat-rules', {'saved_as': name, 'id': 'repeated_key:customer.客户', 'rule': 'keep_both', 'confirmed_by': '王工'})
            self.assertEqual(status, 200, body)
            self.assertNotIn('repeated_key:customer.客户', {i['id'] for i in body['items']})
            self.assertIsNone(self.item(base, name))
            page = self.customers(base, name)
            self.assertEqual(page['total'], 32)    # both rows stay listed, now marked as kept
            self.assertEqual({m['repeat'] for m in page['row_marks'] if m}, {'keep_both'})
            [entry] = [r for r in page['identity_repeats'] if r['source'] == '客户']
            self.assertEqual((entry['rule']['rule'], entry['rule']['confirmed_by']), ('keep_both', '王工'))
            from ontology_poc_generator.workspace_store import open_workspace
            conn = open_workspace(out / 'workspace.sqlite')
            try:
                [row] = conn.execute("SELECT state, evidence_ref, confirmed_by, content_json FROM element_state WHERE element_id LIKE 'repeat_rule:%'").fetchall()
            finally:
                conn.close()
            self.assertEqual(row, ('confirmed', 'open_item:repeated_key:customer.客户', '王工', '{"covers": ["KH012"], "rule": "keep_both"}'))
        self.run_with(check)

    def test_keep_latest_needs_an_ordering_column_and_every_reader_then_reads_the_chosen_row_and_a_rule_can_be_taken_back(self):
        import io
        import openpyxl
        book = openpyxl.load_workbook(io.BytesIO(base64.b64decode(next(f for f in self.files if f['filename'] == '客户.xlsx')['content_base64'])))
        sheet = book.active
        sheet.cell(1, sheet.max_column + 1, '更新日期')
        dates = {'合肥': '2026-02-01', '苏州': '2026-01-01'}     # the first row of the file is the later in time: the date decides, not the file order
        for row in sheet.iter_rows(min_row=2):
            if row[0].value == 'KH012':
                sheet.cell(row[0].row, sheet.max_column, dates[row[3].value])
        out = io.BytesIO()
        book.save(out)
        from tests.test_workspace_store import DraftsModel
        self.draft['object_types'][0]['attributes'].append({'source': '客户', 'path': '更新日期'})
        self.model = DraftsModel(self.draft)
        self.files = [{**f, 'content_base64': base64.b64encode(out.getvalue()).decode()} if f['filename'] == '客户.xlsx' else f for f in self.files]

        def check(base, _, name):
            body = {'saved_as': name, 'id': 'repeated_key:customer.客户', 'confirmed_by': '王工'}
            item = self.item(base, name)
            self.assertEqual(item['repeat']['columns'], ['更新日期'])
            for bad in ({'rule': 'keep_latest'}, {'rule': 'keep_latest', 'column': '没有'}, {'rule': 'keep_latest', 'column': '城市'}, {'rule': 'merge'}, {'id': 'repeated_key:x.y', 'rule': 'keep_both'}):
                status, answer = call(base, '/api/ontology/repeat-rules', {**body, **bad})
                self.assertEqual(status, 400, bad)
                if bad.get('column') == '城市':
                    self.assertIn('不是数字或日期', answer['error'])
            self.assertIsNotNone(self.item(base, name))     # nothing was kept
            city = lambda: [r['城市'] for r in self.customers(base, name)['rows'] if r['客户编号'] == 'KH012']
            centre = lambda: fetch(base, f'/api/ontology/runs/{name}/graph?node=customer:KH012')[1]['center']['fields']['城市']
            self.assertEqual((city(), centre()), (['合肥', '苏州'], '合肥'))
            status, _ = call(base, '/api/ontology/repeat-rules', {**body, 'rule': 'keep_latest', 'column': '更新日期'})
            self.assertEqual(status, 200)
            page = self.customers(base, name)
            self.assertEqual((page['objects'], page['total']), (31, 31))
            self.assertEqual((city(), centre()), (['合肥'], '合肥'))
            conflicts = lambda: [c.get('settled') for c in fetch(base, f'/api/ontology/runs/{name}')[1]['evaluation']['data_fit']['identity_conflicts'] if c['identity'] == 'KH012']
            self.assertEqual(set(conflicts()), {'keep_latest'})     # the check's finding is kept, marked as settled by the choice
            status, _ = call(base, '/api/ontology/repeat-rules', {**body, 'rule': None})
            self.assertEqual(status, 200)
            self.assertIsNotNone(self.item(base, name))
            self.assertEqual(self.customers(base, name)['total'], 32)
            self.assertEqual((city(), centre()), (['合肥', '苏州'], '合肥'))
            self.assertEqual(set(conflicts()), {None})              # and not settled again once the choice is taken back
        self.run_with(check)

    def test_runs_dropped_from_memory_are_read_again_with_their_choice(self):
        from unittest import mock
        from ontology_poc_generator import ontology_server
        with mock.patch.object(ontology_server, 'KEPT_RUNS_IN_MEMORY', 1), OntologyServerTests().server(gateway=self.model) as (base, _):
            names = [call(base, '/api/ontology/build', {'files': self.files})[1]['saved_as'] for _ in range(2)]
            call(base, '/api/ontology/repeat-rules', {'saved_as': names[0], 'id': 'repeated_key:customer.客户', 'rule': 'keep_both'})
            self.assertEqual([self.customers(base, n)['total'] for n in (names[0], names[1], names[0])], [32, 32, 32])
            self.assertEqual([m['repeat'] for m in self.customers(base, names[0])['row_marks'] if m], ['keep_both'] * 2)
            self.assertEqual([m['repeat'] for m in self.customers(base, names[1])['row_marks'] if m], ['keep_both'] * 2)   # the same file is one line: one choice

    def test_a_question_asked_after_the_choice_reads_the_chosen_row_and_a_data_error_is_said_beside_the_answer(self):
        from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
        from ontology_poc_generator.recognition import ModelCompletion

        class Asker:
            def complete_json(self, *, system_prompt, user_prompt):
                content = {'questions': [{'reasoning': 'r', 'question': '各城市有多少客户？',
                                          'query': {'start': 'customer', 'where': [], 'via': [], 'group_by': 'customer.城市'}}]} \
                    if system_prompt == QUESTION_SYSTEM_PROMPT else self.draft
                return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(content, ensure_ascii=False))
        asker = Asker()
        asker.draft = self.draft
        self.model = asker

        def check(base, out, name):
            def asked():
                status, run = call(base, '/api/ontology/ask', {'saved_as': name, 'question': '各城市有多少客户？'})
                self.assertEqual(status, 200, run)
                return run['evaluation']['asked'][-1]['items'][0]
            body = {'saved_as': name, 'id': 'repeated_key:customer.客户', 'confirmed_by': '王工'}
            groups = lambda item: dict(tuple(g[:2]) for g in item['answer']['groups'])
            before = asked()
            self.assertNotIn('data_error', before.get('evidence', {}))
            call(base, '/api/ontology/repeat-rules', {**body, 'rule': 'data_error'})
            marked = asked()
            self.assertEqual(marked['evidence']['data_error'], [{'type': '客户', 'source': '客户', 'objects': 1, 'examples': ['KH012']}])
            self.assertEqual(groups(marked), groups(before))      # the rows are still used: the answer says so instead of staying quiet
            # the answer asked before the choice is worked out again and says why
            _, saved = fetch(base, f'/api/ontology/runs/{name}')
            [first] = saved['evaluation']['asked'][0]['items']
            self.assertEqual(first['evidence']['data_error'][0]['examples'], ['KH012'])
            self.assertNotIn('rerun', first)      # the number is the same: only the answer's check gained the mark, so nothing is announced
        self.run_with(check)


if __name__ == '__main__':
    unittest.main()
