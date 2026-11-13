"""A confirmation remembers the data it was confirmed on. The numbers are the planted fixtures': 订单.状态码 has 96 rows of 0, 48
of 1 and 16 of 2; a next version with the codes shifted (1 becomes 2, 2 becomes 3) has 96 of 0, 48 of 2 and 16 of 3, and
"2 = 已取消" must not answer 48 for it."""
import base64
import io
import json
from collections import Counter
import sqlite3
import unittest

import openpyxl

from ontology_poc_generator.anchors import check_code, check_relation, check_view, code_anchor, moved, relation_anchor, view_anchor
from tests.test_answer_checks import AskModel, QUERIES
from tests import test_workspace_store as ws
from tests.test_relation_checks import DRAFT


class MovedTests(unittest.TestCase):
    def test_a_share_that_triples_or_vanishes_moved_and_a_bigger_table_alone_did_not(self):
        self.assertTrue(moved(16, 160, 48, 160))
        self.assertTrue(moved(16, 160, 0, 160))
        self.assertFalse(moved(16, 160, 32, 320))        # twice the rows, the same share
        self.assertFalse(moved(16, 160, 20, 160))        # 10% to 12.5%
        self.assertFalse(moved(1, 100, 4, 100))          # four times, but fewer than five rows more than expected
        self.assertTrue(moved(0, 100, 5, 100))           # nothing, then five rows
        self.assertFalse(moved(5, 0, 5, 10))             # nothing to compare with


def column(counts, other=None):
    """A code column as code_meanings.code_columns reports it, and the rows it came from (an order number beside each code)."""
    records = [{'订单号': f'D{i}', '状态码': code} for i, code in enumerate(c for c, n in counts.items() for _ in range(n))]
    profile = {'source': '订单', 'column': '状态码', 'field': '订单.状态码', 'rows': len(records), 'values': [{'value': c, 'rows': n} for c, n in counts.items()]}
    return profile, records


class CodeTests(unittest.TestCase):
    def setUp(self):
        self.profile, self.records = column({'0': 96, '1': 48, '2': 16})
        self.anchor = code_anchor(self.profile, self.records)
        self.labels = {'2': '已取消'}

    def test_the_anchor_keeps_the_values_their_counts_and_a_few_rows_each(self):
        self.assertEqual(self.anchor['values'], {'0': 96, '1': 48, '2': 16})
        self.assertEqual([s['订单号'] for s in self.anchor['samples']['2']], ['D144', 'D145', 'D146'])

    def test_the_same_data_and_a_bigger_month_with_the_same_shape_hold(self):
        self.assertEqual(check_code(self.anchor, self.labels, self.profile, self.records), [])
        bigger, rows = column({'0': 96, '1': 48, '2': 16})
        rows += [{**r, '订单号': f'E{i}'} for i, r in enumerate(rows)]       # the same orders and as many new ones: twice the rows, the same shares
        bigger = {**bigger, 'rows': 320, 'values': [{'value': c, 'rows': 2 * n} for c, n in (('0', 96), ('1', 48), ('2', 16))]}
        self.assertEqual(check_code(self.anchor, self.labels, bigger, rows), [])

    def test_shifted_codes_say_what_the_label_sat_on_and_what_it_sits_on_now(self):
        shifted, rows = column({'0': 96, '2': 48, '3': 16})
        for r in rows:                                                  # the same orders, their codes shifted
            r['状态码'] = {'0': '0', '1': '2', '2': '3'}[next(x['状态码'] for x in self.records if x['订单号'] == r['订单号'])]
        changes = check_code(self.anchor, self.labels, shifted, rows)
        self.assertIn('上次 2 有 16 行（占 10%），现在 2 有 48 行（占 30%）', changes)
        self.assertIn('多了取值 3（16 行）', changes)
        self.assertTrue(any('3 行上次是 2，现在是 3' in c for c in changes), changes)

    def test_a_new_value_alone_is_a_change_and_a_value_nobody_gave_a_meaning_may_move(self):
        more, rows = column({'0': 96, '1': 48, '2': 16, '3': 2})
        self.assertEqual(check_code(self.anchor, self.labels, more, rows), ['多了取值 3（2 行）'])
        moved_one, rows = column({'0': 96, '1': 8, '2': 16})
        self.assertEqual(check_code(self.anchor, self.labels, moved_one, rows), [])      # 1 has no meaning: nothing was confirmed about it

    def test_a_column_that_is_gone_or_no_longer_a_code_is_a_change(self):
        self.assertEqual(check_code(self.anchor, self.labels, None, [{'订单号': 'D1'}]), ['表里现在没有「状态码」这一列'])
        free = [{'订单号': f'D{i}', '状态码': f'X{i}'} for i in range(30)]
        self.assertIn('不再像一列代码', check_code(self.anchor, self.labels, None, free)[0])


class RowIdTests(unittest.TestCase):
    """With a key every row is found again by it: a swap beyond the first sample rows is caught, a status that moves on for a few rows is not."""
    def setUp(self):
        self.profile, self.records = column({'0': 96, '1': 48, '2': 16})
        self.anchor = code_anchor(self.profile, self.records, ['订单号'])
        self.labels = {'0': '进行中', '2': '已取消'}

    def changed(self, moves):
        """The same rows with the code of the order numbers given moved: {order number: new code}."""
        rows = [{**r, '状态码': moves.get(r['订单号'], r['状态码'])} for r in self.records]
        counts = Counter(r['状态码'] for r in rows)
        return {**self.profile, 'values': [{'value': c, 'rows': counts[c]} for c in sorted(counts)]}, rows

    def test_the_anchor_keeps_a_short_hash_per_row_and_no_samples(self):
        self.assertEqual((self.anchor['key'], self.anchor['samples']), (['订单号'], {}))
        self.assertEqual({c: len(ids) // 16 for c, ids in self.anchor['ids'].items()}, {'0': 96, '1': 48, '2': 16})

    def test_codes_swapped_on_rows_beyond_the_first_three_are_found_with_the_counts_unchanged(self):
        moves = {**{f'D{i}': '1' for i in range(150, 160)}, **{f'D{i}': '2' for i in range(96, 106)}}      # 10 of the 16 cancelled now 1, ten of 1 now 2
        profile, rows = self.changed(moves)
        self.assertEqual({v['value']: v['rows'] for v in profile['values']}, {'0': 96, '1': 48, '2': 16})
        [change] = check_code(self.anchor, self.labels, profile, rows)
        self.assertEqual(change, '按「订单号」对，上次是 2 的 16 行里有 10 行现在是 1（如订单号 D150）')

    def test_seven_of_sixteen_swapped_is_found_and_twenty_of_ninety_six_moving_on_is_not(self):
        profile, rows = self.changed({f'D{i}': '1' for i in range(150, 157)})
        self.assertEqual(len(check_code(self.anchor, self.labels, profile, rows)), 1)
        profile, rows = self.changed({f'D{i}': '1' for i in range(150, 156)})        # 6 of 16 is 37%: found too; 4 of 16 is under five rows
        self.assertEqual(len(check_code(self.anchor, self.labels, profile, rows)), 1)
        profile, rows = self.changed({f'D{i}': '1' for i in range(150, 154)})
        self.assertEqual(check_code(self.anchor, self.labels, profile, rows), [])
        profile, rows = self.changed({f'D{i}': '1' for i in range(0, 28)})           # 28 of 96 is 29%
        self.assertEqual(check_code(self.anchor, self.labels, profile, rows), [])

    def test_some_rows_moving_on_is_not_a_swap(self):
        profile, rows = self.changed({f'D{i}': '1' for i in range(0, 20)})       # 20 of 96 open orders were delivered: nothing says 0 means something else
        self.assertEqual(check_code(self.anchor, self.labels, profile, rows), [])
        profile, rows = self.changed({f'D{i}': '1' for i in range(0, 3)})
        self.assertEqual(check_code(self.anchor, self.labels, profile, rows), [])

    def test_a_row_that_is_gone_or_new_does_not_count_and_a_table_without_a_key_keeps_samples(self):
        profile, rows = self.changed({})
        rows = [r for r in rows if r['订单号'] not in {f'D{i}' for i in range(144, 160)}] + [{'订单号': 'N1', '状态码': '2'}]
        self.assertEqual(check_code(self.anchor, self.labels, profile, rows), [])
        self.assertEqual(code_anchor(self.profile, self.records)['samples']['2'][0]['订单号'], 'D144')

    def test_a_repeated_or_empty_key_names_no_row(self):
        rows = [{'订单号': 'X', '状态码': '1'}, {'订单号': 'X', '状态码': '2'}, {'订单号': '', '状态码': '2'}]
        anchor = code_anchor({'source': '订单', 'column': '状态码', 'field': '订单.状态码', 'rows': 3, 'values': [{'value': '1', 'rows': 1}, {'value': '2', 'rows': 2}]}, rows, ['订单号'])
        self.assertNotIn('ids', anchor)


class ViewAndRelationTests(unittest.TestCase):
    def test_a_view_that_keeps_a_different_share_of_its_table(self):
        anchor = view_anchor(144, 160, '订单', 1)
        self.assertEqual(check_view(anchor, 288, 320, 2), [])
        [change] = check_view(anchor, 60, 160, 2)
        self.assertIn('上次视图留下 144 行（「订单」共 160 行里的 90%），现在留下 60 行（共 160 行里的 38%）', change)
        self.assertIn('第 1 版换成了第 2 版', change)

    def test_a_relation_whose_unmatched_share_jumped(self):
        side = lambda unmatched: {'end': 'to', 'object': 'customer', 'rows': 160, 'matched': 157 - unmatched + 3, 'unmatched': unmatched}
        anchor = relation_anchor({'sides': [side(3)]})
        self.assertEqual(check_relation(anchor, {'sides': [side(4)]}, str), [])
        self.assertEqual(check_relation(anchor, {'sides': [side(40)]}, str), ['customer那一头：上次 160 行里 3 行找不到对应，现在 160 行里 40 行找不到'])


def edited(name, change) -> bytes:
    """A planted table with `change(sheet)` done to it, as the bytes of an xlsx."""
    workbook = openpyxl.load_workbook(ws.PLANTED / name)
    change(workbook.active)
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def shift_codes(sheet):
    for row in sheet.iter_rows(min_row=2):
        row[6].value = {1: 2, 2: 3}.get(int(row[6].value), row[6].value)


shifted_orders = lambda: edited('订单.xlsx', shift_codes)


class Versions:
    """A server with the planted tables uploaded and a code meaning and a view confirmed on them; helpers to upload the next version."""
    model = lambda self: AskModel(QUERIES)

    def setUp(self):
        from tests.test_ontology_ask_server import call
        from tests.test_ontology_server import OntologyServerTests
        server = OntologyServerTests().server(gateway=self.model())
        self.base, self.out = server.__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        self.call = call
        status, self.first = call(self.base, '/api/ontology/build', {'files': ws.ServerDataChecksTests.files})
        self.assertEqual(status, 200, self.first)
        post = lambda path, **body: call(self.base, path, {'saved_as': self.first['saved_as'], **body})
        self.assertEqual(post('/api/ontology/code-meanings', id='code_meaning:订单.状态码', values=[{'value': '2', 'label': '已取消'}], confirmed_by='王工')[0], 200)
        self.assertEqual(post('/api/ontology/views', name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消', confirmed_by='王工')[0], 200)
        self.assertEqual(self.ask(self.first['saved_as'], '有没有已取消的订单？')['answer']['total'], 16)

    def new_version(self, orders=None, **tables):
        changed = {'订单.xlsx': orders, **{f'{k}.xlsx': v for k, v in tables.items()}}
        files = [{**f, 'content_base64': base64.b64encode(changed[f['filename']]).decode()} if changed.get(f['filename']) else f for f in ws.ServerDataChecksTests.files]
        status, run = self.call(self.base, '/api/ontology/build', {'files': files, 'previous': self.first['saved_as']})
        self.assertEqual(status, 200, run)
        self.assertEqual(run['lineage'], self.first['file']['sha256'])
        return run

    def ask(self, saved_as, question):
        status, run = self.call(self.base, '/api/ontology/ask', {'saved_as': saved_as, 'question': question})
        self.assertEqual(status, 200, run)
        return run['evaluation']['asked'][-1]['items'][0]

    def listing(self, saved_as):
        from urllib.request import urlopen
        with urlopen(self.base + f'/api/ontology/runs/{saved_as}/open-items', timeout=30) as response:
            return json.load(response)


    def forget_anchors(self):
        """The state of a confirmation made before anchors existed."""
        conn = sqlite3.connect(str(self.out / 'workspace.sqlite'))
        conn.execute('UPDATE element_state SET anchors_json = NULL')
        conn.commit()
        conn.close()

    def anchors_on_file(self):
        conn = sqlite3.connect(str(self.out / 'workspace.sqlite'))
        try:
            return [r[0] for r in conn.execute("SELECT anchors_json IS NOT NULL FROM element_state WHERE element_id LIKE 'property:%'")]
        finally:
            conn.close()


class NewVersionServerTests(Versions, unittest.TestCase):
    def test_data_that_looks_the_same_keeps_the_confirmation(self):
        run = self.new_version()
        listed = self.listing(run['saved_as'])
        self.assertEqual((listed['review'], listed['meanings']['订单.状态码']['labels']), ([], {'2': '已取消'}))
        self.assertEqual(self.ask(run['saved_as'], '有没有已取消的订单？')['answer']['total'], 16)

    def test_codes_shifted_in_the_next_version_are_not_answered_under_the_old_label(self):
        run = self.new_version(shifted_orders())
        listed = self.listing(run['saved_as'])
        [waiting] = [r for r in listed['review'] if r['kind'] == 'code_meaning']
        self.assertEqual((waiting['id'], waiting['confirmed_by']), ('review:property:订单.状态码', '王工'))
        self.assertIn('上次 2 有 16 行（占 10%），现在 2 有 48 行（占 30%）', waiting['changes'])
        self.assertIn('多了取值 3（16 行）', waiting['changes'])
        self.assertEqual(waiting['depends'], ['视图「有效订单」读它，现在读不了'])
        self.assertEqual(listed['meanings']['订单.状态码']['labels'], {})                  # nobody reads 2 as 已取消 any more
        item = next(i for i in listed['items'] if i['kind'] == 'code_meaning' and i['id'] == 'code_meaning:订单.状态码')
        self.assertEqual({v['value']: (v['waiting'] or {}).get('label') for v in item['column']['values']}, {'0': None, '2': '已取消', '3': None})   # the old words start in the form
        for question in ('有没有已取消的订单？', '有效订单有多少？'):
            refused = self.ask(run['saved_as'], question)
            self.assertEqual(refused['status'], 'definition_unmet', question)
            self.assertNotIn('answer', refused)
        self.assertIn('在等你再看一眼', self.ask(run['saved_as'], '有没有已取消的订单？')['reason'])
        self.assertIn('要你再看一眼', self.ask(run['saved_as'], '有效订单有多少？')['reason'])

    def test_one_click_confirms_it_again_on_the_new_rows_and_answers_follow(self):
        run = self.new_version(shifted_orders())
        status, body = self.call(self.base, '/api/ontology/review/confirm', {'saved_as': run['saved_as'], 'id': 'review:property:订单.状态码', 'confirmed_by': '李工'})
        self.assertEqual(status, 200, body)
        self.assertEqual((body['review'], body['meanings']['订单.状态码']['labels']), ([], {'2': '已取消'}))
        self.assertEqual(self.ask(run['saved_as'], '有没有已取消的订单？')['answer']['total'], 48)       # the person's reading of the new data
        again = self.call(self.base, '/api/ontology/review/confirm', {'saved_as': run['saved_as'], 'id': 'review:property:订单.状态码'})
        self.assertEqual(again[0], 400)
        self.assertIn('不在', again[1]['error'])

    def test_a_confirmation_from_before_anchors_is_held_against_the_rows_of_the_run_it_came_from(self):
        self.forget_anchors()
        self.assertEqual(self.anchors_on_file(), [0])
        run = self.new_version(shifted_orders())
        [waiting] = [r for r in self.listing(run['saved_as'])['review'] if r['kind'] == 'code_meaning']
        self.assertIn('上次 2 有 16 行（占 10%），现在 2 有 48 行（占 30%）', waiting['changes'])
        self.assertEqual(self.ask(run['saved_as'], '有没有已取消的订单？')['status'], 'definition_unmet')

    def test_a_legacy_confirmation_that_holds_gets_its_anchors_so_that_the_next_version_is_held_against_them(self):
        self.forget_anchors()
        run = self.new_version()
        self.assertEqual((self.listing(run['saved_as'])['review'], self.anchors_on_file()), ([], [1]))

    def test_an_older_run_cannot_keep_or_change_what_waits_and_points_at_the_newer_one(self):
        run = self.new_version(shifted_orders())
        old = self.first['saved_as']
        [waiting] = self.listing(old)['review']
        self.assertEqual(waiting['newer'], run['saved_as'])
        self.assertIsNone(self.listing(run['saved_as'])['review'][0]['newer'])
        confirm = self.call(self.base, '/api/ontology/review/confirm', {'saved_as': old, 'id': waiting['id']})
        self.assertEqual(confirm[0], 400)
        self.assertIn(f'有更新的版本（{run["saved_as"]}）', confirm[1]['error'])
        edit = self.call(self.base, '/api/ontology/code-meanings', {'saved_as': old, 'id': 'code_meaning:订单.状态码', 'values': [{'value': '2', 'label': '已取消'}]})
        self.assertEqual(edit[0], 400)
        self.assertEqual(self.ask(run['saved_as'], '有没有已取消的订单？')['status'], 'definition_unmet')      # still waiting: nothing was anchored on the old rows
        self.assertEqual(self.call(self.base, '/api/ontology/review/confirm', {'saved_as': run['saved_as'], 'id': waiting['id']})[0], 200)

    def test_nothing_is_confirmed_or_changed_from_an_older_run_when_a_newer_one_exists(self):
        run = self.new_version(shifted_orders())
        old = self.first['saved_as']
        listed = self.listing(old)
        self.assertEqual((listed['newer'], self.listing(run['saved_as'])['newer']), (run['saved_as'], None))
        for path, body in (('/api/ontology/code-meanings', {'id': 'code_meaning:订单.状态码', 'values': [{'value': '0', 'label': '进行中'}]}),
                           ('/api/ontology/code-meanings/dismiss', {'id': 'code_meaning:订单.状态码'}),
                           ('/api/ontology/views', {'name': '前线', 'kind': 'latest', 'base': '订单', 'key': ['订单号'], 'order': '下单日期'}),
                           ('/api/ontology/views', {'name': '有效订单', 'remove': True}),
                           ('/api/ontology/repeat-rules', {'id': 'repeated_key:customer.客户', 'rule': 'keep_both'}),
                           ('/api/ontology/review/confirm', {'id': 'review:property:订单.状态码'})):
            status, answered = self.call(self.base, path, {'saved_as': old, **body})
            self.assertEqual(status, 400, (path, answered))
            self.assertIn(f'有更新的版本（{run["saved_as"]}）', answered['error'])
        self.assertEqual(self.call(self.base, '/api/ontology/code-meanings', {'saved_as': run['saved_as'], 'id': 'code_meaning:订单.状态码', 'values': [{'value': '0', 'label': '进行中'}]})[0], 200)

    def test_the_log_keeps_the_size_and_fingerprint_of_the_anchors_not_the_hashes(self):
        conn = sqlite3.connect(str(self.out / 'workspace.sqlite'))
        try:
            kept = conn.execute("SELECT anchors_json FROM element_state WHERE element_id LIKE 'property:%'").fetchone()[0]
            logged = [r[0] for r in conn.execute("SELECT after_json FROM log WHERE element_id LIKE 'property:%'")]
        finally:
            conn.close()
        self.assertIn('"ids"', kept)
        self.assertTrue(logged and all(len(x) < 700 and '"ids"' not in x and 'bytes, sha256' in x for x in logged), logged)

    def test_a_later_version_that_looks_like_the_second_holds_against_it_not_the_first(self):
        run = self.new_version(shifted_orders())
        self.call(self.base, '/api/ontology/review/confirm', {'saved_as': run['saved_as'], 'id': 'review:property:订单.状态码', 'confirmed_by': '李工'})
        status, third = self.call(self.base, '/api/ontology/build', {'files': [{**f, 'content_base64': base64.b64encode(shifted_orders()).decode()} if f['filename'] == '订单.xlsx' else f
                                                                              for f in ws.ServerDataChecksTests.files], 'previous': run['saved_as']})
        self.assertEqual(status, 200, third)
        self.assertEqual(self.listing(third['saved_as'])['review'], [])


def more_snapshots(sheet):
    """Twelve more months for every product, and a product with two rows that was not there before."""
    for year in ('2027',):
        for month in range(1, 13):
            for n in range(1, 13):
                sheet.append([f'{year}-{month:02d}', f'CP{n:02d}', 10])
    sheet.append(['2026-01', 'CP13', 1])
    sheet.append(['2026-02', 'CP13', 2])


def lost_customers(sheet):
    for row in list(sheet.iter_rows(min_row=2))[:40]:
        row[1].value = 'KH999'


class WithRelations(AskModel):
    def complete_json(self, *, system_prompt, user_prompt):
        from ontology_poc_generator.recognition import ModelCompletion
        if system_prompt == self.questions:
            return super().complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(DRAFT, ensure_ascii=False))


class OtherDefinitionsServerTests(Versions, unittest.TestCase):
    """A repeat rule, a named view and a relation judged right, each held against the rows they were confirmed on."""
    model = lambda self: WithRelations(QUERIES)

    def setUp(self):
        super().setUp()
        post = lambda path, **body: self.call(self.base, path, {'saved_as': self.first['saved_as'], **body})
        self.assertEqual(post('/api/ontology/repeat-rules', id='repeated_key:product.库存快照', rule='keep_latest', column='快照月份', confirmed_by='王工')[0], 200)
        self.assertEqual(post('/api/ontology/views', name='最新快照', kind='latest', base='库存快照', key=['产品编号'], order='快照月份', confirmed_by='王工')[0], 200)
        ontology = self.first['ontology']
        decisions = {'types': {t['key']: {'verdict': 'ok'} for t in ontology['object_types']}, 'relations': {r['key']: {'verdict': 'ok'} for r in ontology['relations']}, 'added': []}
        self.assertEqual(post('/api/ontology/confirm', decisions=decisions, confirmed_by='王工')[0], 200)

    def test_a_new_repeated_id_a_view_over_far_more_rows_and_lost_customers_each_wait_for_a_second_look(self, legacy=False):
        if legacy:
            self.forget_anchors()                     # confirmed before anchors existed: they are worked out from the first run's rows
        run = self.new_version(库存快照=edited('库存快照.xlsx', more_snapshots), 订单=edited('订单.xlsx', lost_customers))
        listed = self.listing(run['saved_as'])
        by_kind = {}
        for r in listed['review']:
            by_kind.setdefault(r['kind'], []).append(r)
        [rule] = by_kind['repeat_rule']
        self.assertIn('现在又有新的重复编号：CP13', rule['changes'][0])
        [snapshot] = by_kind['view']
        self.assertEqual(snapshot['name'], '最新快照')
        self.assertIn('上次视图留下 12 行（「库存快照」共 72 行里的 17%）', snapshot['changes'][0])
        self.assertIn('第 1 版换成了第 2 版', snapshot['changes'][0])
        [link] = by_kind['relation']
        self.assertIn('上次 160 行里 3 行找不到对应，现在 160 行里 42 行找不到', link['changes'][0])
        suggested = (run['evaluation'].get('reference') or {}).get('suggested') or {}
        self.assertNotIn(link['name'], suggested.get('relations', {}))                 # it does not start as judged right
        for r in by_kind['repeat_rule'] + by_kind['view'] + by_kind['relation']:
            status, body = self.call(self.base, '/api/ontology/review/confirm', {'saved_as': run['saved_as'], 'id': r['id'], 'confirmed_by': '李工'})
            self.assertEqual(status, 200, (r['id'], body))
        self.assertEqual(self.listing(run['saved_as'])['review'], [])

    def test_the_same_when_the_confirmations_were_made_before_anchors_existed(self):
        self.test_a_new_repeated_id_a_view_over_far_more_rows_and_lost_customers_each_wait_for_a_second_look(legacy=True)


class BlockedDraftVersionTests(unittest.TestCase):
    def test_a_draft_that_did_not_pass_verification_still_holds_its_code_meanings_against_the_new_rows(self):
        from tests.test_ontology_ask_server import call
        from tests.test_ontology_server import OntologyServerTests
        broken = json.loads(json.dumps(ws.PLANTED_DRAFT))
        broken['object_types'][0]['attributes'].append({'source': '客户', 'path': '没有这一列'})
        server = OntologyServerTests().server(gateway=ws.DraftsModel(broken))
        base, out = server.__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        status, first = call(base, '/api/ontology/build', {'files': ws.ServerDataChecksTests.files})
        self.assertNotEqual(first['ontology']['status'], 'auto_built_verified')
        self.assertEqual(call(base, '/api/ontology/code-meanings', {'saved_as': first['saved_as'], 'id': 'code_meaning:订单.状态码', 'values': [{'value': '2', 'label': '已取消'}]})[0], 200)
        files = [{**f, 'content_base64': base64.b64encode(shifted_orders()).decode()} if f['filename'] == '订单.xlsx' else f for f in ws.ServerDataChecksTests.files]
        status, second = call(base, '/api/ontology/build', {'files': files, 'previous': first['saved_as']})
        self.assertEqual(status, 200, second)
        from urllib.request import urlopen
        with urlopen(base + f"/api/ontology/runs/{second['saved_as']}/open-items", timeout=30) as response:
            listed = json.load(response)
        self.assertEqual([r['id'] for r in listed['review']], ['review:property:订单.状态码'])
        self.assertEqual(listed['meanings']['订单.状态码']['labels'], {})


if __name__ == '__main__':
    unittest.main()
