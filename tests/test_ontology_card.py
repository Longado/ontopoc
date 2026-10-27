"""The data-meaning card (口径卡): what code can say about each uploaded table, the cells only a person can fill, the
checks on what a person posts, and the questions that follow the card: a running total is not added up, a
period-to-date amount is added up only on one period, a partly imported object says so beside the answer."""
import unittest

from ontology_poc_generator import ontology_card as oc
from ontology_poc_generator.derived_measures import parse_derived
from ontology_poc_generator.ontology_acceptance import check_acceptance
from ontology_poc_generator.ontology_questions import answer_query, run_query

AT = '2026-10-27T09:00:00+00:00'
LEDGER = [   # rows 2 and 3 are one object (the batch is written in lower case on the third)
    {'row_no': '1', 'batch': 'B1', 'paid_on': '2024-11-30', 'booked_at': '2024-12-01 09:30:00', 'paid': '100.5', 'running': '100.5', 'ytd': '500', 'status': 'OPEN'},
    {'row_no': '2', 'batch': 'B1', 'paid_on': '2024-12-31', 'booked_at': '2024-12-02 10:00:00', 'paid': '20', 'running': '120.5', 'ytd': '520', 'status': 'OPEN'},
    {'row_no': '2', 'batch': 'b1', 'paid_on': '', 'booked_at': '2024-12-02 11:00:00', 'paid': '5', 'running': '125.5', 'ytd': '525', 'status': 'CLOSED'},
    {'row_no': '3', 'batch': 'B2', 'paid_on': '2024-12-15', 'booked_at': '2024-12-01 08:00:00', 'paid': '', 'running': '', 'ytd': '', 'status': 'OPEN'},
]
VENDORS = [{'uei': 'V1', 'name': 'Acme'}, {'uei': 'V2', 'name': 'Bolt'}]


def bundle(ledger=LEDGER):
    return {'schema': 'company_source_bundle.v1', 'decision': '看支出', 'file': {'name': 'ledger.xlsx', 'sha256': 'a' * 64, 'kind': 'table'},
            'sources': {'ledger': {'records': ledger, 'requests': []}, 'vendors': {'records': VENDORS, 'requests': []},
                        'notes': {'records': [{'text': 'hello'}], 'requests': []}}}


ONTOLOGY = {
    'object_types': [
        {'key': 'entry', 'label': '支出行', 'populated_from': [{'source': 'ledger', 'identity': {'row_no': 'row_no', 'batch': 'batch'}}],
         'attributes': [{'source': 'ledger', 'path': p} for p in ('paid_on', 'booked_at', 'paid', 'running', 'ytd', 'status')]},
        {'key': 'vendor', 'label': '供应商', 'populated_from': [{'source': 'vendors', 'identity': {'uei': 'uei'}}],
         'attributes': [{'source': 'vendors', 'path': 'name'}]}],
    'relations': [], 'ignored_fields': []}
QA = bundle([LEDGER[0], LEDGER[1], LEDGER[3]])   # one row an object: questions on the ledger need no folding of repeated rows
GRAIN, ENTRY = 'grain:ledger', 'complete:ledger|batch,row_no'


def said(value, note='', basis='10-27 会议', by='张三'):
    return {'value': value, 'note': note, 'by': by, 'basis': basis, 'at': AT}


def total(field, op='sum', **over):
    return {'start': 'entry', 'measure': {'field': f'ledger.{field}', 'op': op}, **over}


def on_day(day='2024-12-31', field='paid_on'):
    return {'field': f'ledger.{field}', 'equals': day}


class LayoutTests(unittest.TestCase):
    def test_a_table_is_read_into_code_facts_with_nothing_answered(self):
        card = oc.build_card(ONTOLOGY, bundle())
        ledger = card['tables'][0]
        self.assertEqual([t['source'] for t in card['tables']], ['ledger', 'vendors', 'notes'])
        self.assertEqual((ledger['rows'], ledger['objects']), (4, [{'type': 'entry', 'label': '支出行', 'identity': ['batch', 'row_no']}]))
        # rows 2 and 3 carry the same key once spaces and case are folded the way the graph folds them: shown as first met
        self.assertEqual(ledger['grain'], {'id': GRAIN, 'unique': {'fields': ['batch', 'row_no'], 'distinct': 3, 'duplicates': 1, 'blank': 0, 'examples': ['B1 · 2']},
                                           'answer': None})
        self.assertEqual(ledger['dates'], [
            {'id': 'date:ledger.paid_on', 'range_id': 'range:ledger.paid_on', 'field': 'paid_on', 'type': 'DATE',
             'min': '2024-11-30', 'max': '2024-12-31', 'empty': 1, 'answer': None, 'declared': None},
            {'id': 'date:ledger.booked_at', 'range_id': 'range:ledger.booked_at', 'field': 'booked_at', 'type': 'DATETIME',
             'min': '2024-12-01', 'max': '2024-12-02', 'empty': 0, 'answer': None, 'declared': None}])
        self.assertEqual(card['objects'], [
            {'id': ENTRY, 'type': 'entry', 'label': '支出行', 'count': 3, 'answer': None},
            {'id': 'complete:vendors|uei', 'type': 'vendor', 'label': '供应商', 'count': 2, 'answer': None}])
        self.assertEqual((card['cells'], card['blank']), (10, 10))   # 3 tables + 2 dates + 3 amounts + 2 objects

    def test_amount_columns_are_the_numeric_ones_that_do_not_identify_an_object(self):
        amounts = oc.build_card(ONTOLOGY, bundle())['tables'][0]['amounts']
        self.assertEqual(amounts, [
            {'id': 'amount:ledger.paid', 'field': 'paid', 'type': 'DECIMAL', 'empty': 1, 'answer': None},
            {'id': 'amount:ledger.running', 'field': 'running', 'type': 'DECIMAL', 'empty': 1, 'answer': None},
            {'id': 'amount:ledger.ytd', 'field': 'ytd', 'type': 'INTEGER', 'empty': 1, 'answer': None}])   # row_no is a number too, and the key

    def test_a_table_no_object_reads_still_has_a_row_cell_and_no_identity_to_check(self):
        notes = oc.build_card(ONTOLOGY, bundle())['tables'][2]
        self.assertEqual((notes['source'], notes['rows'], notes['objects'], notes['grain']['unique']), ('notes', 1, [], None))
        self.assertEqual(notes['grain']['id'], 'grain:notes')

    def test_the_complete_cell_follows_the_table_and_the_key_not_the_name_the_model_gave(self):
        renamed = {**ONTOLOGY, 'object_types': [{**ONTOLOGY['object_types'][0], 'key': 'row', 'label': '行'}, ONTOLOGY['object_types'][1]]}
        self.assertEqual(oc.build_card(renamed, bundle())['objects'][0]['id'], ENTRY)
        self.assertEqual(oc.complete_id(ONTOLOGY['object_types'][0]), ENTRY)

    def test_answers_sit_beside_the_facts_with_the_words_a_person_reads(self):
        cells = {GRAIN: said('event'), 'amount:ledger.running': said('running'), 'date:ledger.paid_on': said('business'),
                 'range:ledger.paid_on': said({'from': '2024-10-01', 'to': '2024-12-31'}), ENTRY: said('partial', note='只导了 Q4')}
        card = oc.build_card(ONTOLOGY, bundle(), cells)
        ledger = card['tables'][0]
        self.assertEqual(ledger['grain']['answer'], {**said('event'), 'says': '一行是一次事件或一次修改（同一个东西有多行）'})
        self.assertEqual(ledger['amounts'][1]['answer']['says'], '每次事件后的累计值')
        self.assertEqual(ledger['dates'][0]['answer']['says'], '业务发生的日期')
        self.assertEqual(ledger['dates'][0]['declared']['says'], '声明覆盖 2024-10-01 至 2024-12-31')
        self.assertEqual(card['objects'][0]['answer']['says'], '数据里只有一部分')
        self.assertEqual((card['cells'], card['blank']), (10, 6))   # four cells answered; the range cell is optional and is not counted

    def test_unsure_is_as_blank_as_no_answer(self):
        card = oc.build_card(ONTOLOGY, bundle(), {GRAIN: said('unsure'), 'amount:ledger.paid': said('flow')})
        self.assertEqual((card['cells'], card['blank']), (10, 9))

    def test_the_one_sentence_for_a_range_with_only_one_end(self):
        self.assertEqual(oc.says('range:t.d', {'from': None, 'to': '2024-12-31'}), '声明覆盖到 2024-12-31')
        self.assertEqual(oc.says('range:t.d', {'from': '2024-10-01', 'to': None}), '声明从 2024-10-01 起')


class PostedCellTests(unittest.TestCase):
    CARD = oc.build_card(ONTOLOGY, bundle())

    def check(self, *cells, by='张三'):
        return oc.check_cells(self.CARD, list(cells), by, AT)

    def test_a_valid_answer_is_kept_with_who_said_it_and_where_from(self):
        got = self.check({'id': 'amount:ledger.running', 'value': 'running', 'note': ' 每行累加 ', 'basis': '10-27 会议'})
        self.assertEqual(got, {'amount:ledger.running': {'value': 'running', 'note': '每行累加', 'by': '张三', 'basis': '10-27 会议', 'at': AT}})
        self.assertEqual(self.check({'id': GRAIN, 'value': 'event'})[GRAIN], said('event', basis=''))

    def test_a_null_value_clears_the_cell(self):
        self.assertEqual(self.check({'id': GRAIN, 'value': None}), {GRAIN: None})

    def test_a_declared_range_has_two_ends_either_of_which_may_be_open(self):
        for value in ({'from': '2024-10-01', 'to': '2024-12-31'}, {'from': None, 'to': '2024-12-31'}, {'from': '2024-10-01', 'to': None}):
            with self.subTest(value=value):
                self.assertEqual(self.check({'id': 'range:ledger.paid_on', 'value': value})['range:ledger.paid_on']['value'], value)
        self.assertEqual(self.check({'id': 'range:ledger.paid_on', 'value': {'from': None, 'to': None}}), {'range:ledger.paid_on': None})

    def test_what_is_wrong_is_named_and_nothing_is_returned(self):
        for cell, said_so in (
                ({'id': 'amount:ledger.nope', 'value': 'flow'}, '没有这一格'),
                ({'id': 'amount:ledger.ytd', 'value': 'big'}, '只能是'),
                ({'id': 'amount:ledger.row_no', 'value': 'flow'}, '没有这一格'),   # a key is not an amount
                ({'id': 'range:ledger.paid_on', 'value': {'from': '2024-13-01', 'to': None}}, '日期'),
                ({'id': 'range:ledger.paid_on', 'value': {'from': '2024-12-31', 'to': '2024-10-01'}}, '晚于'),
                ({'id': 'range:ledger.paid_on', 'value': '2024-12-31'}, '日期'),
                ({'id': 'range:ledger.paid_on', 'value': {'from': 20241001, 'to': None}}, '日期'),
                ({'id': GRAIN, 'value': 'event', 'note': 'x' * 301}, '备注'),
                ({'id': GRAIN, 'value': 'event', 'basis': 'x' * 201}, '出处'),
                ({'value': 'event'}, '没有这一格'),
                ('not an object', '写法')):
            with self.subTest(cell=cell), self.assertRaises(oc.CardError) as caught:
                self.check({'id': GRAIN, 'value': 'event'}, cell)
            self.assertIn(said_so, str(caught.exception))

    def test_who_answered_is_required_and_short(self):
        for by in (None, '', '  ', 'x' * 41, 5):
            with self.subTest(by=by), self.assertRaises(oc.CardError) as caught:
                oc.check_cells(self.CARD, [{'id': GRAIN, 'value': 'event'}], by, AT)
            self.assertIn('答复人', str(caught.exception))


class StoredCardTests(unittest.TestCase):
    def test_every_change_goes_into_history_and_a_repeat_is_not_a_change(self):
        stored = {'cells': {}, 'items': {}, 'history': []}
        first = oc.with_changes(stored, {GRAIN: said('event')}, {'unlinked:r': {'choice': 'expected', 'by': '张三', 'at': AT}}, AT)
        self.assertEqual(first['cells'], {GRAIN: said('event')})
        self.assertEqual([(h['id'], h['old'], h['new']['value' if h['id'] == GRAIN else 'choice']) for h in first['history']],
                         [(GRAIN, None, 'event'), ('unlinked:r', None, 'expected')])
        again = oc.with_changes(first, {GRAIN: {**said('event'), 'at': '2026-10-28T00:00:00+00:00'}}, {}, AT)
        self.assertEqual(again, first)   # the same words again: the first answer keeps its date
        moved = oc.with_changes(first, {GRAIN: said('one_object')}, {}, AT)
        self.assertEqual((moved['history'][-1]['old'], moved['history'][-1]['new']), (said('event'), said('one_object')))
        cleared = oc.with_changes(moved, {GRAIN: None}, {}, AT)
        self.assertNotIn(GRAIN, cleared['cells'])
        self.assertEqual((cleared['history'][-1]['old'], cleared['history'][-1]['new']), (said('one_object'), None))
        self.assertEqual(stored, {'cells': {}, 'items': {}, 'history': []})   # the file it was given is not changed

    def test_history_keeps_the_last_two_hundred_changes(self):
        stored = {'cells': {}, 'items': {}, 'history': []}
        for n in range(205):
            stored = oc.with_changes(stored, {GRAIN: said('event', note=str(n))}, {}, AT)
        self.assertEqual(len(stored['history']), 200)
        self.assertEqual(stored['history'][0]['new']['note'], '5')
        self.assertEqual(stored['history'][-1]['new']['note'], '204')


class RunningTotalTests(unittest.TestCase):
    RUNNING = {'amount:ledger.running': said('running')}

    def test_a_column_marked_as_a_running_total_is_not_added_up(self):
        refused = run_query(ONTOLOGY, QA, total('running'), card=self.RUNNING)
        self.assertEqual(refused, {
            'status': 'query_limit', 'refused_by_card': 'amount:ledger.running',
            'reason': '「running」在口径卡里是“每次事件后的累计值”：一行已经包含之前的数，跨行相加会重复。可以改问某一次的值，或每个对象最近一次的值。'})
        self.assertEqual(run_query(ONTOLOGY, QA, total('running'))['status'], 'answered')   # no card: as before
        self.assertEqual(run_query(ONTOLOGY, QA, total('running'), card={})['status'], 'answered')

    def test_an_average_is_not_stopped(self):
        got = run_query(ONTOLOGY, QA, total('running', 'average'), card=self.RUNNING)
        self.assertEqual((got['status'], got['answer']['measure']['value']), ('answered', 110.5))

    def test_other_meanings_and_other_columns_are_not_stopped(self):
        for cells in ({'amount:ledger.running': said('latest')}, {'amount:ledger.running': said('flow')}, {'amount:ledger.paid': said('running')}):
            with self.subTest(cells=cells):
                self.assertEqual(run_query(ONTOLOGY, QA, total('running'), card=cells)['status'], 'answered')

    def test_a_derived_amount_is_stopped_by_any_column_in_its_formula(self):
        formula, _ = parse_derived(ONTOLOGY, {'type': 'entry', 'label': '合计', 'terms': [{'sign': 1, 'factors': [{'field': 'paid'}, {'field': 'running'}]}]})
        query = {'start': 'entry', 'measure': {'derived': '合计', 'op': 'sum'}}
        got = run_query(ONTOLOGY, QA, query, derived=[formula], card=self.RUNNING)
        self.assertEqual((got['status'], got['refused_by_card']), ('query_limit', 'amount:ledger.running'))
        self.assertIn('「running」', got['reason'])
        self.assertEqual(run_query(ONTOLOGY, QA, query, derived=[formula])['status'], 'answered')

    def test_the_reason_keeps_the_column_name_even_when_it_is_also_an_object_key(self):
        ontology = {**ONTOLOGY, 'object_types': [{**ONTOLOGY['object_types'][0], 'attributes': [{'source': 'ledger', 'path': 'running'}]},
                                                 {'key': 'running', 'label': '累计', 'populated_from': [{'source': 'vendors', 'identity': {'uei': 'uei'}}], 'attributes': []}]}
        got = answer_query(ontology, QA, total('running'), '一共多少？', card=self.RUNNING)
        self.assertIn('「running」在口径卡里', got['reason'])

    def test_a_refusal_comes_with_no_evidence_and_is_not_the_models_reason(self):
        got = answer_query(ONTOLOGY, QA, total('running'), '一共多少？', card=self.RUNNING)
        self.assertNotIn('evidence', got)
        self.assertFalse(got.get('reason_from_model'))


class PeriodToDateTests(unittest.TestCase):
    YTD = {'amount:ledger.ytd': said('period_to_date')}
    REASON = '「ytd」在口径卡里是“期初到期末的累计值”：要先固定在一期上（按同一张表里一个不是取数或录入时间的日期列，筛一个日期或按它分组），才能相加。'

    def refused(self, query):
        got = run_query(ONTOLOGY, QA, query, card=self.YTD)
        self.assertEqual(got, {'status': 'query_limit', 'reason': self.REASON, 'refused_by_card': 'amount:ledger.ytd'})

    def test_adding_it_up_across_periods_is_refused(self):
        self.refused(total('ytd'))
        self.refused(total('ytd', where=[{'field': 'ledger.status', 'equals': 'OPEN'}]))   # a filter on something that is not a date
        self.refused(total('ytd', group_by=[{'field': 'ledger.status'}]))

    def test_one_date_of_the_same_table_fixes_it_on_a_period(self):
        got = run_query(ONTOLOGY, QA, total('ytd', where=[on_day()]), card=self.YTD)
        self.assertEqual((got['status'], got['answer']['measure']['value']), ('answered', 520))
        got = run_query(ONTOLOGY, QA, total('ytd', where=[on_day('2024-12-02 10:00:00', 'booked_at')]), card=self.YTD)
        self.assertEqual((got['status'], got['answer']['measure']['value']), ('answered', 520))   # a date time column fixes it too

    def test_grouping_by_the_date_without_going_through_a_relation_fixes_it_on_a_period(self):
        got = run_query(ONTOLOGY, QA, total('ytd', group_by=[{'field': 'ledger.paid_on'}]), card=self.YTD)
        self.assertEqual(got['status'], 'answered')
        self.assertEqual(got['answer']['groups'][0][:2], ['2024-12-31', 520])

    def test_an_average_is_not_stopped(self):
        self.assertEqual(run_query(ONTOLOGY, QA, total('ytd', 'average'), card=self.YTD)['status'], 'answered')

    def test_the_date_is_found_by_the_values_in_the_column_not_by_its_name(self):
        text_dates = [{**r, 'paid_on': 'soon' if r['row_no'] == '2' else r['paid_on']} for r in (LEDGER[0], LEDGER[1], LEDGER[3])]
        got = run_query(ONTOLOGY, bundle(text_dates), total('ytd', where=[on_day('soon')]), card=self.YTD)
        self.assertEqual(got['refused_by_card'], 'amount:ledger.ytd')


class AnswerEvidenceTests(unittest.TestCase):
    def evidence(self, cells, query=None):
        return (run_query(ONTOLOGY, QA, query or total('paid', where=[on_day()]), card=cells).get('evidence') or {}).get('card')

    def test_nothing_is_said_until_a_cell_is_answered(self):
        for cells in (None, {}, {GRAIN: said('unsure')}):
            with self.subTest(cells=cells):
                self.assertIsNone(self.evidence(cells))
        got = run_query(ONTOLOGY, QA, total('paid'), card={GRAIN: said('event')})
        self.assertNotIn('card', got['answer'])   # the answer is what acceptance compares: the card rides beside it

    def test_the_table_the_cells_and_the_end_of_the_data_are_named(self):
        cells = {'amount:ledger.paid': said('flow'), 'date:ledger.paid_on': said('business'), 'range:ledger.paid_on': said({'from': '2024-10-01', 'to': '2024-12-31'}),
                 ENTRY: said('full'), 'amount:ledger.ytd': said('period_to_date')}
        self.assertEqual(self.evidence(cells), {
            'tables': [{'source': 'ledger', 'rows': 3, 'through': '2024-12-31'}],
            'lines': [{'id': 'amount:ledger.paid', 'field': 'paid', 'says': '每行是这一笔自己的数，可以跨行相加', 'by': '张三', 'basis': '10-27 会议', 'at': AT},
                      {'id': 'date:ledger.paid_on', 'field': 'paid_on', 'says': '业务发生的日期', 'by': '张三', 'basis': '10-27 会议', 'at': AT},
                      {'id': 'range:ledger.paid_on', 'field': 'paid_on', 'says': '声明覆盖 2024-10-01 至 2024-12-31', 'by': '张三', 'basis': '10-27 会议', 'at': AT},
                      {'id': ENTRY, 'field': '支出行', 'says': '数据里是全的', 'by': '张三', 'basis': '10-27 会议', 'at': AT}],   # not ytd: the question does not use it
            'incomplete': []})

    def test_the_end_of_the_data_is_the_declared_end_else_the_latest_date_in_a_business_date_column(self):
        through = lambda cells: (self.evidence(cells, {'start': 'entry'}) or {})['tables'][0].get('through')
        self.assertEqual(through({'date:ledger.paid_on': said('business')}), '2024-12-31')
        self.assertEqual(through({'date:ledger.paid_on': said('business'), 'range:ledger.paid_on': said({'from': None, 'to': '2024-12-15'})}), '2024-12-15')
        # several business columns: the latest end
        self.assertEqual(through({'date:ledger.paid_on': said('business'), 'range:ledger.paid_on': said({'from': None, 'to': '2024-11-30'}),
                                  'date:ledger.booked_at': said('business')}), '2024-12-02')
        # a declared range with only a start says nothing about the end: the data's own latest date
        self.assertEqual(through({'date:ledger.paid_on': said('business'), 'range:ledger.paid_on': said({'from': '2024-10-01', 'to': None})}), '2024-12-31')
        # a column that is not the business date, or no date column answered: no end is claimed
        self.assertIsNone(through({'date:ledger.paid_on': said('system')}))
        self.assertIsNone(through({GRAIN: said('event')}))

    def test_a_question_that_found_nothing_carries_it_too(self):
        got = run_query(ONTOLOGY, QA, total('paid', where=[on_day('1999-01-01')]), card={'amount:ledger.paid': said('flow')})
        self.assertEqual(got['status'], 'no_data')
        self.assertEqual(got['evidence']['card']['lines'][0]['id'], 'amount:ledger.paid')

    def test_an_object_that_is_only_partly_in_the_data_is_said_so_and_the_answer_still_comes(self):
        cells = {ENTRY: said('partial', note='只导了 Q4')}
        got = run_query(ONTOLOGY, QA, {'start': 'entry'}, card=cells)
        self.assertEqual(got['status'], 'answered')
        self.assertEqual(got['answer'], {'total': 3})
        self.assertEqual(got['evidence']['card']['incomplete'], [{'type': 'entry', 'label': '支出行', 'note': '只导了 Q4', 'by': '张三'}])
        self.assertEqual(got['evidence']['card']['lines'][0]['says'], '数据里只有一部分')
        full = run_query(ONTOLOGY, QA, {'start': 'entry'}, card={ENTRY: said('full')})
        self.assertEqual(full['evidence']['card']['incomplete'], [])

    def test_the_card_is_beside_the_check_pack_not_instead_of_it(self):
        got = run_query(ONTOLOGY, QA, total('paid', where=[on_day()]), card={'amount:ledger.paid': said('flow')})
        self.assertEqual([f['field'] for f in got['evidence']['filters']], ['paid_on'])
        self.assertIn('card', got['evidence'])


class AcceptanceTests(unittest.TestCase):
    def test_a_confirmed_sum_stops_matching_once_the_column_is_marked_as_running(self):
        item = {'question': '累计一共多少？', 'query': total('running'), 'note': '', 'snapshot': None, 'status': 'answered',
                'answer': {'total': 3, 'measure': {'field': 'running', 'op': 'sum', 'value': 221, 'counted': 2, 'skipped': 1}}, 'path': 'x'}
        before = check_acceptance(ONTOLOGY, QA, [item])
        self.assertEqual((before['answered'], before['items'][0]['changed']), (1, False))
        after = check_acceptance(ONTOLOGY, QA, [item], card={'amount:ledger.running': said('running')})
        self.assertEqual((after['answered'], after['items'][0]['status'], after['items'][0]['changed']), (0, 'query_limit', True))
        self.assertEqual(after['items'][0]['refused_by_card'], 'amount:ledger.running')


if __name__ == '__main__':
    unittest.main()
