"""A key that repeats in the table describing the object (客户 KH012 on two rows) is not merged away: it is an open item
with a rule to choose, the object list shows every row until one is chosen, and the choice is kept with who made it."""
import unittest

from ontology_poc_generator.handover_form import handover_form
from ontology_poc_generator.object_rows import neighbourhood, object_rows
from ontology_poc_generator.ontology_questions import run_query
from ontology_poc_generator.public_ontology import build_graph
from ontology_poc_generator.repeated_keys import check_rule, column_order, latest_row, repeated_keys, unmet
from ontology_poc_generator.ttl_export import ttl_files
from tests.test_workspace_store import PLANTED_DRAFT, planted_bundle

CUSTOMER_ONLY = {'object_types': [{'key': 'customer', 'label': '客户', 'populated_from': [{'source': '客户', 'identity': {'customer_id': '客户编号'}}],
                                   'attributes': [{'source': '客户', 'path': p} for p in ('客户名称', '城市')]}], 'relations': [], 'ignored_fields': [], 'open_questions': []}


def dated(first='2026-01-01', second='2026-02-01', ontology_rule=None):
    """The planted tables with an update date on the two KH012 rows (客户 rows 11 and 12: 合肥, then 苏州)."""
    bundle = planted_bundle()
    records = list(bundle['sources']['客户']['records'])
    records[11], records[12] = {**records[11], '更新': first}, {**records[12], '更新': second}
    return {**bundle, 'sources': {**bundle['sources'], '客户': {**bundle['sources']['客户'], 'records': records}},
            **({'repeat_rules': {'customer.客户': ontology_rule}} if ontology_rule else {})}


KEEP_LATEST = {'rule': 'keep_latest', 'column': '更新'}


def found(ontology=PLANTED_DRAFT, bundle=None):
    bundle = bundle or planted_bundle()
    return repeated_keys(ontology, bundle, build_graph(ontology, bundle))


class FindingTests(unittest.TestCase):
    def test_the_repeated_customer_is_found_with_its_rows_and_what_differs(self):
        [group] = [g for g in found() if g['type'] == 'customer']
        self.assertEqual((group['id'], group['source'], group['rows']), ('repeated_key:customer.客户', '客户', 2))
        [one] = group['objects']
        self.assertEqual((one['identity'], one['rows'], one['differs']), ('KH012', [11, 12], [('城市', ['合肥', '苏州'])]))

    def test_a_table_that_only_mentions_the_object_is_not_a_broken_key(self):
        self.assertEqual({g['source'] for g in found() if g['type'] == 'customer'}, {'客户'})   # 160 orders name customers many times

    def test_a_unique_key_gives_nothing(self):
        bundle = {'sources': {'客户': {'records': [{'客户编号': 'A', '城市': 'x'}, {'客户编号': 'B', '城市': 'y'}]}}}
        self.assertEqual(found(CUSTOMER_ONLY, bundle), [])


class RuleTests(unittest.TestCase):
    GROUP = {'source': '客户', 'objects': [{'identity': 'KH012'}, {'identity': 'KH003'}], 'columns': ['客户编号', '客户名称', '城市', '更新日期', '版本', '备注'],
             'order': {'客户编号': 'text', '客户名称': 'text', '城市': 'text', '更新日期': 'date', '版本': 'same', '备注': 'empty'}}

    def test_the_three_rules_are_accepted_and_keep_latest_needs_a_column_of_the_table(self):
        covers = ['KH003', 'KH012']   # a choice says which repeated keys it was made for
        self.assertEqual(check_rule(self.GROUP, {'rule': 'keep_both'}), {'rule': 'keep_both', 'covers': covers})
        self.assertEqual(check_rule(self.GROUP, {'rule': 'data_error'}), {'rule': 'data_error', 'covers': covers})
        self.assertEqual(check_rule(self.GROUP, {'rule': 'keep_latest', 'column': '更新日期'}), {'rule': 'keep_latest', 'column': '更新日期', 'covers': covers})
        for bad in ({'rule': 'keep_latest'}, {'rule': 'keep_latest', 'column': '没有这列'}, {'rule': 'merge'}, {'rule': 'keep_both', 'column': '城市'}, None, 'keep_both'):
            with self.assertRaises(ValueError, msg=bad):
                check_rule(self.GROUP, bad)

    def test_a_text_column_cannot_say_which_row_is_latest_and_the_reason_is_in_the_message(self):
        for column, said in (('城市', '不是数字或日期'), ('客户名称', '不是数字或日期'), ('版本', '取值都一样'), ('备注', '都是空的'), ('没有这列', '要选「客户」表里的一列')):
            with self.assertRaises(ValueError, msg=column) as caught:
                check_rule(self.GROUP, {'rule': 'keep_latest', 'column': column})
            self.assertIn(said, str(caught.exception))
            if column != '没有这列':
                self.assertIn('可以用的有：更新日期', str(caught.exception))    # what can be used is named
        with self.assertRaises(ValueError) as caught:
            check_rule({**self.GROUP, 'order': {**self.GROUP['order'], '更新日期': 'text'}}, {'rule': 'keep_latest', 'column': '城市'})
        self.assertIn('没有一列能分出先后', str(caught.exception))

    def test_what_a_column_can_order_is_read_from_the_repeated_rows_only(self):
        bundle = dated()
        [group] = [g for g in found(bundle=bundle) if g['type'] == 'customer']
        self.assertEqual({c: group['order'][c] for c in ('城市', '客户名称', '更新')}, {'城市': 'text', '客户名称': 'text', '更新': 'date'})
        self.assertEqual(group['latest_columns'], ['更新'])
        numbers = planted_bundle()
        numbers['sources']['客户']['records'][11] = {**numbers['sources']['客户']['records'][11], '版本': '9'}
        numbers['sources']['客户']['records'][12] = {**numbers['sources']['客户']['records'][12], '版本': '10'}
        [group] = [g for g in found(bundle=numbers) if g['type'] == 'customer']
        self.assertEqual((group['order']['版本'], group['latest_columns']), ('number', ['版本']))
        empty = [g for g in found() if g['type'] == 'customer'][0]
        self.assertEqual(empty['latest_columns'], [])

    def test_the_latest_row_is_the_largest_value_numbers_by_value_and_the_later_row_wins_a_tie(self):
        records = [{'k': 'A', 'v': '9'}, {'k': 'A', 'v': '10'}, {'k': 'A', 'v': ''}, {'k': 'A', 'v': '10'}]
        self.assertEqual(latest_row(records, [0, 1, 2], 'v'), 1)      # 10 beats 9 as a number, not as text
        self.assertEqual(latest_row(records, [1, 3], 'v'), 3)         # a tie goes to the later row of the file
        self.assertEqual(latest_row(records, [0, 2], 'v'), 0)         # blank is the oldest
        dates = [{'d': '2026-01-05'}, {'d': '2025-12-31'}]
        self.assertEqual(latest_row(dates, [0, 1], 'd'), 0)

    def test_dates_are_dates_however_they_are_written_and_whatever_their_zone(self):
        for written in ('2026/1/5', '2026-1-5', '2026年1月5日', '2026.01.05 08:30', '2026-01-05T08:30:00Z', '2026-01-05T16:30:00+08:00', '2026-01', '2026年1月'):
            self.assertEqual(column_order([{'d': written}, {'d': '2025-12-31'}], [[0, 1]], 'd'), 'date', written)
        # one instant written three ways is one value; a zone moves the clock
        self.assertEqual(column_order([{'d': '2026-01-05T08:30:00Z'}, {'d': '2026-01-05T16:30:00+08:00'}], [[0, 1]], 'd'), 'same')
        mixed = [{'d': '2026-01-01T00:00:00Z'}, {'d': '2026-02-01'}, {'d': '2026/03/01'}]
        self.assertEqual(latest_row(mixed, [0, 1, 2], 'd'), 2)         # compared without a TypeError
        for not_a_date in ('2026-13-01', '2026-02-30', '2026', '12:30', 'nan', '2026-13'):
            self.assertEqual(column_order([{'d': not_a_date}, {'d': '2025-12-31'}], [[0, 1]], 'd'), 'text', not_a_date)

    def test_a_graph_is_never_broken_by_what_a_column_holds(self):
        for first, second in (('2026-01-01T00:00:00Z', '2026-02-01'), ('2026/1/1', '2026-02-01'), ('', ''), ('nan', '1')):
            graph = build_graph(CUSTOMER_ONLY, dated(first, second, KEEP_LATEST))
            self.assertIn(('customer', (('customer_id', 'KH012'),)), graph['records_of'], (first, second))

    def test_a_key_that_repeats_later_is_not_covered_by_a_choice_made_before_it(self):
        bundle = dated(ontology_rule=KEEP_LATEST | {'covers': ['KH012']})
        [kh005] = [r for r in bundle['sources']['客户']['records'] if r['客户编号'] == 'KH005']
        records = [*bundle['sources']['客户']['records'], {**kh005, '更新': '2026-05-01'}]
        later = {**bundle, 'sources': {**bundle['sources'], '客户': {'records': records}}}
        [group] = [g for g in found(bundle=later) if g['type'] == 'customer']
        self.assertEqual(unmet(group, later['repeat_rules']['customer.客户']), '上次的选择只管到当时重复的编号，现在又有新的重复编号：KH005。')
        self.assertEqual(len(build_graph(CUSTOMER_ONLY, later)['records_of'][('customer', (('customer_id', 'KH012'),))]), 2)   # nothing is applied until asked again
        self.assertIsNone(unmet(group, {**later['repeat_rules']['customer.客户'], 'covers': ['KH005', 'KH012']}))
        self.assertIsNone(unmet(group, {'rule': 'keep_both'}))     # a choice kept before keys were recorded holds for what repeats


class ObjectListTests(unittest.TestCase):
    def page(self, rule=None, ontology=CUSTOMER_ONLY, **over):
        bundle = {**planted_bundle(), **({'repeat_rules': {'customer.客户': rule}} if rule else {})}
        return object_rows(ontology, bundle, 'customer', size=None, **over)

    def customer_rows(self, page):
        return [(r['客户编号'], r['城市'], m) for r, m in zip(page['rows'], page['row_marks']) if r['客户编号'] == 'KH012']

    def test_until_a_rule_is_chosen_both_rows_are_listed_and_marked(self):
        page = self.page()
        self.assertEqual((page['objects'], page['total']), (30, 31))    # 30 customers, 31 rows listed
        self.assertEqual(self.customer_rows(page), [('KH012', '合肥', {'repeat': 'pending', 'rows': 2}), ('KH012', '苏州', {'repeat': 'pending', 'rows': 2})])
        self.assertEqual(sum(m is None for m in page['row_marks']), 29)

    def test_keep_both_and_data_error_list_both_rows_with_that_mark(self):
        for rule in ('keep_both', 'data_error'):
            marks = [m for _, _, m in self.customer_rows(self.page({'rule': rule}))]
            self.assertEqual([m['repeat'] for m in marks], [rule, rule])

    def test_keep_latest_lists_one_row_by_the_chosen_column(self):
        bundle = planted_bundle()
        bundle['sources']['客户']['records'][12] = {**bundle['sources']['客户']['records'][12], '更新': '2026-02-01'}
        bundle['sources']['客户']['records'][11] = {**bundle['sources']['客户']['records'][11], '更新': '2026-01-01'}
        page = object_rows(CUSTOMER_ONLY, {**bundle, 'repeat_rules': {'customer.客户': {'rule': 'keep_latest', 'column': '更新'}}}, 'customer', size=None)
        rows = [(r['客户编号'], r['城市'], m) for r, m in zip(page['rows'], page['row_marks']) if r['客户编号'] == 'KH012']
        self.assertEqual(rows, [('KH012', '苏州', {'repeat': 'keep_latest', 'rows': 2, 'column': '更新'})])
        self.assertEqual((page['objects'], page['total']), (30, 30))

    def test_the_numbers_say_where_they_come_from(self):
        page = object_rows(PLANTED_DRAFT, {**planted_bundle()}, 'customer', size=None)
        self.assertEqual(page['objects'], 31)   # KH099 is named only by orders
        self.assertEqual(page['mentioned_only'], {'count': 1, 'examples': ['KH099']})
        self.assertEqual([(r['source'], r['rows'], r['identities']) for r in page['identity_repeats']], [('客户', 31, 30)])
        self.assertEqual(page['total'], 32)     # 31 objects, KH012 on two rows
        self.assertEqual(self.page()['mentioned_only'], {'count': 0, 'examples': []})

    def test_a_chosen_rule_is_on_the_repeat_entry(self):
        rule = {'rule': 'keep_both', 'confirmed_by': '王工'}
        [entry] = [r for r in self.page(rule)['identity_repeats'] if r['source'] == '客户']
        self.assertEqual(entry['rule'], rule)
        self.assertIsNone([r for r in self.page()['identity_repeats'] if r['source'] == '客户'][0]['rule'])

    def test_pages_count_listed_rows(self):
        page = object_rows(CUSTOMER_ONLY, planted_bundle(), 'customer', page=2, size=20)
        self.assertEqual((page['total'], len(page['rows']), len(page['row_marks'])), (31, 11, 11))


class ChoiceAppliesWhereverRowsArePickedTests(unittest.TestCase):
    """"Keep the latest" is applied once, when the graph picks which rows describe an object, so the list, the relation
    graph, a question and the export all read the same row; "data error" is said beside every answer that used the rows."""
    KH012 = ('customer', (('customer_id', 'KH012'),))

    def test_the_older_row_is_not_one_of_the_rows_of_the_object(self):
        self.assertEqual(build_graph(CUSTOMER_ONLY, dated())['records_of'][self.KH012], [('客户', 11), ('客户', 12)])
        graph = build_graph(CUSTOMER_ONLY, dated(ontology_rule=KEEP_LATEST))
        self.assertEqual(graph['records_of'][self.KH012], [('客户', 12)])
        self.assertEqual(len([i for i in graph['records_of'] if i[0] == 'customer']), 30)    # the object is still there
        self.assertEqual(graph['records_all'][self.KH012], [('客户', 11), ('客户', 12)])

    def test_other_choices_leave_every_row_in_the_graph(self):
        for rule in ({'rule': 'keep_both'}, {'rule': 'data_error'}, KEEP_LATEST | {'column': '没有这列'}):
            graph = build_graph(CUSTOMER_ONLY, dated(ontology_rule=rule))
            self.assertEqual(graph['records_of'][self.KH012], [('客户', 11), ('客户', 12)], rule)

    def test_a_relation_the_older_row_would_have_made_is_gone_with_it(self):
        ontology = {**CUSTOMER_ONLY, 'object_types': [*CUSTOMER_ONLY['object_types'],
                    {'key': 'city', 'label': '城市', 'populated_from': [{'source': '客户', 'identity': {'city': '城市'}}], 'attributes': []}],
                    'relations': [{'key': 'customer_city', 'from': 'customer', 'to': 'city', 'source': '客户', 'label': '在'}]}
        edges = lambda bundle: {(a[1][0][1], b[1][0][1]) for a, b, _ in build_graph(ontology, bundle)['edges']['customer_city'] if a[1][0][1] == 'KH012'}
        self.assertEqual(edges(dated()), {('KH012', '合肥'), ('KH012', '苏州')})
        self.assertEqual(edges(dated(ontology_rule=KEEP_LATEST)), {('KH012', '苏州')})

    def test_the_question_the_relation_graph_and_the_export_read_the_same_row_as_the_list(self):
        for bundle, city in ((dated(), '合肥'), (dated(ontology_rule=KEEP_LATEST), '苏州')):
            graph = build_graph(CUSTOMER_ONLY, bundle)
            listed = [r['城市'] for r in object_rows(CUSTOMER_ONLY, bundle, 'customer', size=None, graph=graph)['rows'] if r['客户编号'] == 'KH012']
            self.assertEqual(listed, [city] if bundle.get('repeat_rules') else ['合肥', '苏州'])
            self.assertEqual(neighbourhood(CUSTOMER_ONLY, bundle, 'customer:KH012', graph=graph)['center']['fields']['城市'], city)
            data = ttl_files(CUSTOMER_ONLY, bundle, handover_form(CUSTOMER_ONLY, bundle), None, None, [], 'urn:t:', graph)['data.ttl']
            [block] = [b for b in data.split(' .\n') if b.startswith('<urn:t:data/customer/KH012>')]
            self.assertIn(f'"{city}"', block)
            if bundle.get('repeat_rules'):
                self.assertNotIn('"合肥"', block)

    def test_a_city_is_counted_for_the_customer_by_the_chosen_row_only(self):
        counts = lambda bundle: dict(tuple(g[:2]) for g in run_query(CUSTOMER_ONLY, bundle, {'start': 'customer', 'via': [], 'group_by': 'customer.城市'})['answer']['groups'])
        before, after = counts(dated()), counts(dated(ontology_rule=KEEP_LATEST))
        self.assertEqual((after['苏州'] - before['苏州'], after['合肥'] - before['合肥']), (0, -1))   # KH012 leaves 合肥, stays in 苏州

    def test_the_list_still_says_what_was_chosen_and_how_many_rows_it_covers(self):
        page = object_rows(CUSTOMER_ONLY, dated(ontology_rule=KEEP_LATEST), 'customer', size=None)
        [entry] = [r for r in page['identity_repeats'] if r['source'] == '客户']
        self.assertEqual((entry['rows'], entry['identities'], entry['repeated'], entry['rule']['rule']), (31, 30, 1, 'keep_latest'))
        self.assertEqual([m for m in page['row_marks'] if m], [{'repeat': 'keep_latest', 'rows': 2, 'column': '更新'}])

    def test_a_tie_or_a_blank_in_the_column_is_said_not_settled_silently(self):
        def with_second_key(*dates):
            """KH012 as given, and KH003 (a row with no date) repeated on a row with the earlier date and one with the later."""
            bundle = dated(*dates, ontology_rule=KEEP_LATEST)
            [kh003] = [r for r in bundle['sources']['客户']['records'] if r['客户编号'] == 'KH003']
            records = [*bundle['sources']['客户']['records'], {**kh003, '更新': '2026-01-01'}, {**kh003, '更新': '2026-03-01'}]
            page = object_rows(CUSTOMER_ONLY, {**bundle, 'sources': {**bundle['sources'], '客户': {'records': records}}}, 'customer', size=None)
            marks = {r['客户编号']: m for r, m in zip(page['rows'], page['row_marks']) if m}
            return marks, [r['rule'] for r in page['identity_repeats'] if r['source'] == '客户'][0]
        marks, rule = with_second_key('2026-02-01', '2026-02-01')
        self.assertEqual(marks, {'KH012': {'repeat': 'keep_latest', 'rows': 2, 'column': '更新', 'tie': True},
                                 'KH003': {'repeat': 'keep_latest', 'rows': 3, 'column': '更新', 'blank': True}})   # its first row has no date
        self.assertEqual((rule['ties'], rule['blank']), (1, 1))
        marks, rule = with_second_key('', '2026-02-01')
        self.assertEqual(marks['KH012'], {'repeat': 'keep_latest', 'rows': 2, 'column': '更新', 'blank': True})
        self.assertEqual((rule['ties'], rule['blank']), (0, 2))

    def test_a_choice_the_data_can_no_longer_carry_out_is_not_applied(self):
        no_column = {**planted_bundle(), 'repeat_rules': {'customer.客户': KEEP_LATEST}}     # a later upload without the column
        self.assertEqual(len(build_graph(CUSTOMER_ONLY, no_column)['records_of'][('customer', (('customer_id', 'KH012'),))]), 2)
        words = dated('合肥', '苏州', KEEP_LATEST)                                              # the column now holds text
        self.assertEqual(len(build_graph(CUSTOMER_ONLY, words)['records_of'][('customer', (('customer_id', 'KH012'),))]), 2)
        page = object_rows(CUSTOMER_ONLY, no_column, 'customer', size=None)
        self.assertEqual([m['repeat'] for m in page['row_marks'] if m], ['pending', 'pending'])

    def test_a_data_error_marks_every_answer_that_used_those_rows(self):
        bundle = {**planted_bundle(), 'repeat_rules': {'customer.客户': {'rule': 'data_error'}}}
        asked = run_query(PLANTED_DRAFT, bundle, {'start': 'customer', 'via': [], 'group_by': 'customer.城市'})
        self.assertEqual(asked['evidence']['data_error'], [{'type': '客户', 'source': '客户', 'objects': 1, 'examples': ['KH012']}])
        elsewhere = run_query(PLANTED_DRAFT, bundle, {'start': 'ticket', 'via': [], 'group_by': None})
        self.assertNotIn('data_error', elsewhere.get('evidence', {}))     # tickets do not read the customer rows
        for rule in ({'rule': 'keep_both'}, None):
            plain = {**planted_bundle(), **({'repeat_rules': {'customer.客户': rule}} if rule else {})}
            self.assertNotIn('data_error', run_query(PLANTED_DRAFT, plain, {'start': 'customer', 'via': [], 'group_by': None}).get('evidence', {}))


if __name__ == '__main__':
    unittest.main()
