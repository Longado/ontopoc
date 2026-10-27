"""The data-meaning card over HTTP: read it, post what the client said, and see the answers follow it. No test here needs
a model key for the card itself; the fake model only builds the ontology and writes the questions."""
import base64
from datetime import datetime
import json
from pathlib import Path
import unittest
from unittest import mock

from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
from ontology_poc_generator.recognition import ModelCompletion
from tests.test_ontology_ask_server import call
from tests.test_ontology_server import OntologyServerTests
from tests.test_open_items_server import fetch

CSV = ('订单号,客户编号,金额,累计,下单日\n'
       'O1,C1,100,100,2024-10-01\n'
       'O2,C2,50,150,2024-10-02\n'
       'O3,,70,220,\n').encode('utf-8')   # the third order names no customer: that row is left unlinked
UPLOAD = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}
PROPOSAL = {
    'reasoning': 'r',
    'object_types': [
        {'key': 'order', 'label': '订单', 'populated_from': [{'source': 'orders', 'identity': {'order_id': '订单号'}}],
         'attributes': [{'source': 'orders', 'path': p} for p in ('金额', '累计', '下单日')]},
        {'key': 'customer', 'label': '客户', 'populated_from': [{'source': 'orders', 'identity': {'customer_id': '客户编号'}}], 'attributes': []}],
    'relations': [{'key': 'order_customer', 'from': 'order', 'to': 'customer', 'source': 'orders', 'meaning': '订单属于客户'}],
    'ignored_fields': [], 'open_questions': []}
RUNNING_SUM = {'start': 'order', 'where': [{'field': '金额', 'equals': '100'}], 'via': [], 'group_by': None, 'measure': {'field': 'orders.累计', 'op': 'sum'}}
SUM_QUESTION = {'reasoning': 'r', 'question': '累计一共多少？', 'query': RUNNING_SUM}
DERIVED_QUESTION = {'reasoning': 'r', 'question': '金额乘累计一共多少？',
                    'derive': {'type': 'order', 'label': '合计', 'terms': [{'sign': 1, 'factors': [{'field': '金额'}, {'field': '累计'}]}]},
                    'query': {'start': 'order', 'where': [], 'via': [], 'group_by': None, 'measure': {'derived': '合计', 'op': 'sum'}}}
RUNNING = 'amount:orders.累计'
GRAIN = 'grain:orders'
CUSTOMER = 'complete:orders|客户编号'
EMPTY = {'tables': [], 'objects': [], 'cells': 0, 'blank': 0}
ITEM = 'unlinked:order_customer'
STALE = {'range:orders.不存在': {'value': {'from': None, 'to': '2024-12-31'}, 'note': '', 'by': '张三', 'basis': '', 'at': '2026-10-27T09:00:00+00:00'}}   # no such column now
WRONG_CUSTOMER = {'types': {'order': {'verdict': 'ok'}, 'customer': {'verdict': 'wrong'}}, 'relations': {}}


class CardModel:
    def __init__(self, question=SUM_QUESTION):
        self.question = question

    def complete_json(self, *, system_prompt, user_prompt):
        content = {'questions': [self.question]} if system_prompt == QUESTION_SYSTEM_PROMPT else PROPOSAL
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(content))


def card_of(base, run):
    status, card = fetch(base, f"/api/ontology/runs/{run['saved_as']}/card")
    assert status == 200, card
    return card


def save(base, run, cells=(), items=(), by='张三'):
    return call(base, '/api/ontology/card', {'saved_as': run['saved_as'], 'by': by, 'cells': list(cells), 'items': list(items)})


def mark(base, run, cell_id, value, **extra):
    status, body = save(base, run, [{'id': cell_id, 'value': value, **extra}])
    assert status == 200, body
    return body


def keep_cells(out, run, cells):
    """Put these answers in the file's card file as they would be left by an earlier layout of the card."""
    (out / 'cards').mkdir(exist_ok=True)
    (out / 'cards' / f"{run['file']['sha256']}.json").write_text(json.dumps({'cells': cells, 'items': {}, 'history': []}, ensure_ascii=False), encoding='utf-8')


def stored_card(out, run):
    return json.loads((out / 'cards' / f"{run['file']['sha256']}.json").read_text(encoding='utf-8'))


def cell_ids(card):
    return [*(t['grain']['id'] for t in card['tables']), *(d['id'] for t in card['tables'] for d in t['dates']),
            *(a['id'] for t in card['tables'] for a in t['amounts']), *(o['id'] for o in card['objects'])]


class ReadTests(unittest.TestCase):
    def test_a_kept_run_has_its_card_with_what_code_can_say_and_nothing_answered(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            card = card_of(base, run)
        [table] = card['tables']
        self.assertEqual((table['source'], table['rows']), ('orders', 3))
        self.assertEqual(table['grain']['id'], GRAIN)
        self.assertEqual(table['grain']['unique']['fields'], ['客户编号', '订单号'])
        self.assertEqual([(a['id'], a['type']) for a in table['amounts']], [(RUNNING.replace('累计', '金额'), 'INTEGER'), (RUNNING, 'INTEGER')])
        [dated] = table['dates']
        self.assertEqual((dated['id'], dated['type'], dated['min'], dated['max'], dated['empty']), ('date:orders.下单日', 'DATE', '2024-10-01', '2024-10-02', 1))
        self.assertEqual([(o['id'], o['type'], o['count']) for o in card['objects']], [('complete:orders|订单号', 'order', 3), (CUSTOMER, 'customer', 2)])
        self.assertEqual((card['cells'], card['blank']), (6, 6))
        self.assertIsNone(table['grain']['answer'])

    def test_an_order_with_no_customer_is_still_a_key_and_is_counted_as_blank(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            unique = card_of(base, run)['tables'][0]['grain']['unique']
        self.assertEqual(unique, {'fields': ['客户编号', '订单号'], 'distinct': 3, 'duplicates': 0, 'blank': 1, 'examples': []})

    def test_a_run_that_is_unknown_is_not_found(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            for name in ('20260101T000000Z-deadbeef.json', 'not-a-run.json'):
                with self.subTest(name=name):
                    status, body = fetch(base, f'/api/ontology/runs/{name}/card')
                    self.assertEqual(status, 404)
                    self.assertIn('找不到这次运行', body['error'])
                    self.assertEqual(call(base, '/api/ontology/card', {'saved_as': name, 'by': '张三', 'cells': [{'id': GRAIN, 'value': 'event'}]})[0], 404)

    def test_a_document_or_an_ontology_that_did_not_pass_has_the_empty_card(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            path = out / run['saved_as']
            saved = json.loads(path.read_text(encoding='utf-8'))
            for change in ({'ontology': {**saved['ontology'], 'status': 'rejected'}}, {'file': {**saved['file'], 'kind': 'document'}}):
                with self.subTest(change=list(change)):
                    path.write_text(json.dumps({**saved, **change}, ensure_ascii=False), encoding='utf-8')
                    self.assertEqual(fetch(base, f"/api/ontology/runs/{run['saved_as']}/card"), (200, EMPTY))
                    status, body = save(base, run, [{'id': GRAIN, 'value': 'event'}])
                    self.assertEqual(status, 400, body)   # no cell is on that card
            self.assertFalse((out / 'cards').exists())


class SaveTests(unittest.TestCase):
    def test_what_is_wrong_is_refused_with_a_reason_and_nothing_is_written(self):
        good = {'id': GRAIN, 'value': 'event'}
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            for payload, said_so in (
                    ({'by': '张三'}, '至少'),
                    ({'by': '张三', 'cells': [], 'items': []}, '至少'),
                    ({'cells': [good]}, '答复人'),
                    ({'by': 'x' * 41, 'cells': [good]}, '答复人'),
                    ({'by': '张三', 'cells': [good, {'id': 'amount:orders.nope', 'value': 'flow'}]}, '没有这一格'),
                    ({'by': '张三', 'cells': [good, {'id': RUNNING, 'value': 'huge'}]}, '只能是'),
                    ({'by': '张三', 'cells': [good, {'id': 'range:orders.下单日', 'value': {'from': '2024-12-31', 'to': '2024-10-01'}}]}, '晚于'),
                    ({'by': '张三', 'cells': [good, {'id': RUNNING, 'value': 'flow', 'note': 'x' * 301}]}, '备注'),
                    ({'by': '张三', 'cells': [good], 'items': [{'id': 'unlinked:gone', 'choice': 'expected'}]}, '这件事已经不在清单上了'),
                    ({'by': '张三', 'cells': [good], 'items': [{'id': 'unjudged', 'text': '好'}]}, '判对错'),
                    ({'by': '张三', 'cells': [good], 'items': [{'id': 'card_blank', 'text': '好'}]}, '口径卡填完'),
                    ({'by': '张三', 'cells': [good], 'items': [{'id': 'unlinked:order_customer', 'choice': 'same'}]}, '只能'),
                    ({'by': '张三', 'cells': [good], 'items': [{'id': 'unlinked:order_customer'}]}, '选一个')):
                with self.subTest(said_so=said_so, payload=payload):
                    status, body = call(base, '/api/ontology/card', {'saved_as': run['saved_as'], **payload})
                    self.assertEqual(status, 400, body)
                    self.assertIn(said_so, body['error'])
            self.assertFalse((out / 'cards').exists())   # not even the good cell next to the bad one

    def test_a_cell_without_a_value_key_is_refused_and_nothing_is_written(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            status, body = save(base, run, [{'id': GRAIN, 'value': 'event'}, {'id': RUNNING, 'note': '忘了写 value'}])
            self.assertEqual(status, 400, body)
            self.assertEqual(body['error'], '每一格都要写 value（清空就写 null）')
            self.assertFalse((out / 'cards').exists())

    def test_the_card_file_is_written_beside_itself_and_moved_into_place(self):
        moved, real = [], Path.replace

        def spy(self, target):
            moved.append((self.name, Path(target).name))
            return real(self, target)
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            with mock.patch.object(Path, 'replace', spy):
                mark(base, run, RUNNING, 'running')
            name = f"{run['file']['sha256']}.json"
            self.assertIn((f'{name}.part', name), moved)
            self.assertEqual([p.name for p in (out / 'cards').iterdir()], [name])   # no half-written file is left beside it

    def test_an_answer_is_kept_with_who_said_it_and_where_from_and_read_back(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            status, saved = save(base, run, [{'id': RUNNING, 'value': 'running', 'note': '每行累加', 'basis': '10-27 会议'}])
            self.assertEqual(status, 200, saved)
            self.assertEqual(set(saved), {'card', 'items', 'answered'})
            answer = saved['card']['tables'][0]['amounts'][1]['answer']
            self.assertEqual({k: answer[k] for k in ('value', 'says', 'note', 'by', 'basis')},
                             {'value': 'running', 'says': '每次事件后的累计值', 'note': '每行累加', 'by': '张三', 'basis': '10-27 会议'})
            self.assertIsNotNone(datetime.fromisoformat(answer['at']))
            self.assertEqual((saved['card']['cells'], saved['card']['blank']), (6, 5))
            self.assertEqual(card_of(base, run), saved['card'])
            stored = json.loads((out / 'cards' / f"{run['file']['sha256']}.json").read_text(encoding='utf-8'))
            self.assertEqual(stored['cells'][RUNNING]['value'], 'running')
            self.assertEqual([(h['id'], h['old'], h['new']['value']) for h in stored['history']], [(RUNNING, None, 'running')])

    def test_a_cell_is_cleared_with_a_null_value_and_the_change_is_in_the_history(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            mark(base, run, RUNNING, 'running')
            cleared = mark(base, run, RUNNING, None)
            self.assertIsNone(cleared['card']['tables'][0]['amounts'][1]['answer'])
            self.assertEqual(cleared['card']['blank'], 6)
            stored = json.loads((out / 'cards' / f"{run['file']['sha256']}.json").read_text(encoding='utf-8'))
            self.assertEqual(stored['cells'], {})
            self.assertEqual([(h['old'] and h['old']['value'], h['new'] and h['new']['value']) for h in stored['history']], [(None, 'running'), ('running', None)])

    def test_a_declared_range_and_the_date_meaning_are_two_cells_of_one_column(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            mark(base, run, 'date:orders.下单日', 'business')
            saved = mark(base, run, 'range:orders.下单日', {'from': '2024-10-01', 'to': None})
            [dated] = saved['card']['tables'][0]['dates']
            self.assertEqual(dated['answer']['says'], '业务发生的日期')
            self.assertEqual((dated['declared']['value'], dated['declared']['says']), ({'from': '2024-10-01', 'to': None}, '声明从 2024-10-01 起'))
            self.assertEqual(saved['card']['blank'], 5)   # the range is optional: it is not one of the cells counted

    def test_the_card_belongs_to_the_file_and_is_there_on_the_next_upload(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, first = call(base, '/api/ontology/build', UPLOAD)
            mark(base, first, RUNNING, 'running')
            _, second = call(base, '/api/ontology/build', UPLOAD)
            self.assertNotEqual(first['saved_as'], second['saved_as'])
            self.assertEqual(card_of(base, second)['tables'][0]['amounts'][1]['answer']['value'], 'running')


class QuestionsFollowTheCardTests(unittest.TestCase):
    def asked(self, base, run, question='累计一共多少？'):
        status, body = call(base, '/api/ontology/ask', {'saved_as': run['saved_as'], 'question': question})
        self.assertEqual(status, 200, body)
        return body['evaluation']['asked'][-1]['items'][0]

    def test_an_answer_carries_the_card_only_after_a_cell_was_answered_and_stops_at_a_running_total(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            before = self.asked(base, run)
            self.assertEqual((before['status'], before['answer']['measure']['value']), ('answered', 100))
            self.assertNotIn('card', before['evidence'])
            mark(base, run, RUNNING, 'flow', basis='10-27 会议')
            during = self.asked(base, run)
            self.assertEqual(during['answer'], before['answer'])
            self.assertEqual(during['evidence']['card']['tables'], [{'source': 'orders', 'rows': 3}])
            self.assertEqual([(l['id'], l['says'], l['by'], l['basis']) for l in during['evidence']['card']['lines']],
                             [(RUNNING, '每行是这一笔自己的数，可以跨行相加', '张三', '10-27 会议')])
            mark(base, run, RUNNING, 'running')
            after = self.asked(base, run)
            self.assertEqual((after['status'], after['refused_by_card']), ('query_limit', RUNNING))
            self.assertIn('每次事件后的累计值', after['reason'])
            self.assertNotIn('evidence', after)

    def test_asking_again_without_a_condition_follows_the_card_too(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            self.asked(base, run)
            mark(base, run, RUNNING, 'running')
            status, body = call(base, '/api/ontology/requery', {'saved_as': run['saved_as'], 'question': '累计一共多少？', 'drop': {'field': '金额', 'equals': '100'}})
            self.assertEqual(status, 200, body)
            again = body['evaluation']['asked'][-1]['items'][0]
            self.assertEqual((again['status'], again['refused_by_card']), ('query_limit', RUNNING))

    def test_confirming_a_derived_amount_follows_the_card_too(self):
        with OntologyServerTests().server(gateway=CardModel(DERIVED_QUESTION)) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            waiting = self.asked(base, run, '金额乘累计一共多少？')
            self.assertEqual(waiting['status'], 'needs_derived')
            mark(base, run, RUNNING, 'running')
            status, body = call(base, '/api/ontology/derived', {'saved_as': run['saved_as'], 'derive': waiting['derive']})
            self.assertEqual(status, 200, body)
            [again] = body['evaluation']['asked'][-1]['items']
            self.assertEqual((again['status'], again['refused_by_card']), ('query_limit', RUNNING))

    def test_the_fixed_questions_are_checked_again_when_the_card_is_saved(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            item = self.asked(base, run)
            query = {k: item['query'][k] for k in ('start', 'where', 'via', 'group_by', 'measure')}
            status, body = call(base, '/api/ontology/acceptance', {'saved_as': run['saved_as'], 'items': [{'question': item['question'], 'query': query, 'note': ''}]})
            self.assertEqual(status, 200, body)
            self.assertEqual(body['evaluation']['acceptance']['answered'], 1)
            mark(base, run, RUNNING, 'running')
            _, reopened = fetch(base, f"/api/ontology/runs/{run['saved_as']}")
            [checked] = reopened['evaluation']['acceptance']['items']
            self.assertEqual((checked['status'], checked['refused_by_card'], checked['changed']), ('query_limit', RUNNING, True))
            self.assertEqual(reopened['evaluation']['acceptance']['answered'], 0)
            stored = json.loads((out / 'acceptance' / f"{run['file']['sha256']}.json").read_text(encoding='utf-8'))
            self.assertEqual(stored['items'][0]['status'], 'answered')   # the file's shared list is what the next upload inherits: saving a card does not rewrite it
            _, rerun = call(base, '/api/ontology/build', UPLOAD)   # and the next upload of the file is judged by the same card
            self.assertEqual(rerun['evaluation']['acceptance']['items'][0]['refused_by_card'], RUNNING)


    def test_saving_a_card_leaves_the_files_shared_questions_alone_even_on_an_older_run(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, older = call(base, '/api/ontology/build', UPLOAD)
            item = self.asked(base, older)
            query = {k: item['query'][k] for k in ('start', 'where', 'via', 'group_by', 'measure')}
            first = {'question': item['question'], 'query': query, 'note': ''}
            self.assertEqual(call(base, '/api/ontology/acceptance', {'saved_as': older['saved_as'], 'items': [first]})[0], 200)
            _, newer = call(base, '/api/ontology/build', UPLOAD)   # it inherits the one question, and a person adds a second there
            second = {'question': '再问一遍累计一共多少？', 'query': query, 'note': ''}
            self.assertEqual(call(base, '/api/ontology/acceptance', {'saved_as': newer['saved_as'], 'items': [first, second]})[0], 200)
            shared = out / 'acceptance' / f"{older['file']['sha256']}.json"
            before = shared.read_text(encoding='utf-8')
            self.assertEqual(len(json.loads(before)['items']), 2)
            mark(base, older, RUNNING, 'running')   # the older run holds one question: it must not replace the file's two
            self.assertEqual(shared.read_text(encoding='utf-8'), before)
            _, reopened = fetch(base, f"/api/ontology/runs/{older['saved_as']}")
            self.assertEqual(reopened['evaluation']['acceptance']['items'][0]['refused_by_card'], RUNNING)   # its own question was asked again


class StaleCellTests(unittest.TestCase):
    """What an earlier layout of the card left in the file is not an answer on the card now: no path to the questions hands it on."""
    def asked(self, base, run, question='累计一共多少？'):
        status, body = call(base, '/api/ontology/ask', {'saved_as': run['saved_as'], 'question': question})
        self.assertEqual(status, 200, body)
        return body['evaluation']['asked'][-1]['items'][0]

    def no_card(self, item):
        self.assertNotIn('card', item.get('evidence') or {})

    def test_the_card_does_not_count_them_and_asking_carries_no_card(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            keep_cells(out, run, STALE)
            card = card_of(base, run)
            self.assertEqual((card['cells'], card['blank']), (6, 6))
            item = self.asked(base, run)
            self.assertEqual(item['status'], 'answered')
            self.no_card(item)
            self.assertEqual(stored_card(out, run)['cells'], STALE)   # the file still holds them: the column may come back

    def test_asking_again_without_a_condition_carries_no_card(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            self.asked(base, run)
            keep_cells(out, run, STALE)
            status, body = call(base, '/api/ontology/requery', {'saved_as': run['saved_as'], 'question': '累计一共多少？', 'drop': {'field': '金额', 'equals': '100'}})
            self.assertEqual(status, 200, body)
            self.no_card(body['evaluation']['asked'][-1]['items'][0])

    def test_confirming_a_derived_amount_carries_no_card(self):
        with OntologyServerTests().server(gateway=CardModel(DERIVED_QUESTION)) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            waiting = self.asked(base, run, '金额乘累计一共多少？')
            keep_cells(out, run, STALE)
            status, body = call(base, '/api/ontology/derived', {'saved_as': run['saved_as'], 'derive': waiting['derive']})
            self.assertEqual(status, 200, body)
            [again] = body['evaluation']['asked'][-1]['items']
            self.assertEqual(again['status'], 'answered')
            self.no_card(again)

    def test_the_fixed_questions_carry_no_card_when_saved_or_asked_again_after_a_confirmation(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            item = self.asked(base, run)
            query = {k: item['query'][k] for k in ('start', 'where', 'via', 'group_by', 'measure')}
            keep_cells(out, run, STALE)
            status, body = call(base, '/api/ontology/acceptance', {'saved_as': run['saved_as'], 'items': [{'question': item['question'], 'query': query, 'note': ''}]})
            self.assertEqual(status, 200, body)
            [saved] = body['evaluation']['acceptance']['items']
            self.assertEqual(saved['status'], 'answered')
            self.no_card(saved)
            decisions = {'types': {'order': {'verdict': 'ok'}, 'customer': {'verdict': 'ok'}}, 'relations': {}}
            status, body = call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions})
            self.assertEqual(status, 200, body)
            self.no_card(body['evaluation']['acceptance']['items'][0])

    def test_the_questions_an_upload_answers_carry_no_card(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, first = call(base, '/api/ontology/build', UPLOAD)
            keep_cells(out, first, STALE)
            status, run = call(base, '/api/ontology/build', {**UPLOAD, 'purpose': '看累计'})
            self.assertEqual(status, 200, run)
            [item] = run['evaluation']['asked'][0]['items']
            self.assertEqual(item['status'], 'answered')
            self.no_card(item)


class WrongObjectTests(unittest.TestCase):
    def test_an_object_judged_wrong_leaves_the_card_and_what_was_said_on_it_is_no_longer_heard(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            mark(base, run, CUSTOMER, 'partial', note='只导了一部分')
            self.assertEqual(call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': WRONG_CUSTOMER})[0], 200)
            card = card_of(base, run)
            self.assertEqual([o['id'] for o in card['objects']], ['complete:orders|订单号'])
            self.assertEqual((card['cells'], card['blank']), (5, 5))
            self.assertEqual(card['tables'][0]['grain']['id'], GRAIN)   # the table is still there with its own cells
            self.assertEqual(len(card['tables'][0]['amounts']), 2)
            status, body = save(base, run, [{'id': CUSTOMER, 'value': 'full'}])
            self.assertEqual(status, 400, body)
            self.assertIn('没有这一格', body['error'])
            status, listed = fetch(base, f"/api/ontology/runs/{run['saved_as']}/open-items")
            [blank] = [i for i in listed['items'] if i['kind'] == 'card_blank']
            self.assertIn('还有 5 格没说清', blank['ask'])
            status, asked = call(base, '/api/ontology/ask', {'saved_as': run['saved_as'], 'question': '累计一共多少？'})
            self.assertNotIn('card', asked['evaluation']['asked'][-1]['items'][0].get('evidence') or {})
            self.assertEqual(stored_card(out, run)['cells'][CUSTOMER]['value'], 'partial')   # the file keeps it, for a judgement taken back


class OpenItemTests(unittest.TestCase):
    def listing(self, base, run):
        status, body = fetch(base, f"/api/ontology/runs/{run['saved_as']}/open-items")
        self.assertEqual(status, 200, body)
        return body

    def test_the_list_has_the_card_item_and_an_unlinked_item_that_names_its_cell(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            body = self.listing(base, run)
        self.assertEqual(set(body), {'items', 'answered'})
        self.assertEqual(body['answered'], [])
        by_kind = {i['kind']: i for i in body['items']}
        self.assertEqual(by_kind['card_blank']['ask'], '口径卡还有 6 格没说清（1 张表）：数值列能不能相加、日期列是什么时间、一行是什么、对象全不全。会上逐张过一遍？')
        self.assertEqual(by_kind['card_blank']['facts'], ['orders：6 格（下单日、金额、累计）'])
        self.assertEqual((by_kind['unlinked']['id'], by_kind['unlinked']['complete_id']), ('unlinked:order_customer', CUSTOMER))

    def test_an_answered_item_moves_to_the_answered_list_and_the_cell_beside_it_is_set_in_the_same_request(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            [unlinked] = [i for i in self.listing(base, run)['items'] if i['kind'] == 'unlinked']
            status, saved = save(base, run, [{'id': CUSTOMER, 'value': 'partial', 'note': '客户表只导了一部分', 'basis': '10-27 会议'}],
                                 [{'id': unlinked['id'], 'choice': 'incomplete', 'text': '客户表只导了一部分', 'basis': '10-27 会议'}])
            self.assertEqual(status, 200, saved)
            self.assertNotIn(unlinked['id'], [i['id'] for i in saved['items']])
            [answered] = saved['answered']
            self.assertEqual(answered['id'], unlinked['id'])
            self.assertEqual({k: v for k, v in answered['answer'].items() if k != 'at'},
                             {'choice': 'incomplete', 'says': '数据没导全', 'text': '客户表只导了一部分', 'by': '张三', 'basis': '10-27 会议', 'asked': unlinked['ask']})
            customer = next(o for o in saved['card']['objects'] if o['id'] == CUSTOMER)
            self.assertEqual((customer['answer']['value'], customer['answer']['says']), ('partial', '数据里只有一部分'))
            self.assertEqual(self.listing(base, run), {'items': saved['items'], 'answered': saved['answered']})
            _, rerun = call(base, '/api/ontology/build', UPLOAD)   # the same thing on the next upload is still answered
            self.assertEqual([i['id'] for i in self.listing(base, rerun)['answered']], [unlinked['id']])

    def test_an_answer_can_be_changed_and_the_ask_it_answers_is_the_one_at_that_time(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            item = 'unlinked:order_customer'
            save(base, run, items=[{'id': item, 'choice': 'incomplete', 'text': '先这么记'}])
            _, saved = save(base, run, items=[{'id': item, 'choice': 'expected', 'text': '改了：本来就没有'}], by='李四')
            [answered] = saved['answered']
            self.assertEqual((answered['answer']['choice'], answered['answer']['says'], answered['answer']['by']), ('expected', '本来就没有对应，属正常', '李四'))
            stored = json.loads((out / 'cards' / f"{run['file']['sha256']}.json").read_text(encoding='utf-8'))
            self.assertEqual([(h['old'] and h['old']['choice'], h['new']['choice']) for h in stored['history']], [(None, 'incomplete'), ('incomplete', 'expected')])

    def test_the_card_item_goes_when_every_cell_has_an_answer_and_unsure_does_not_count(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            ids = cell_ids(card_of(base, run))
            values = {i: ('flow' if i.startswith('amount:') else 'business' if i.startswith('date:') else 'one_object' if i.startswith('grain:') else 'full') for i in ids}
            _, unsure = save(base, run, [{'id': i, 'value': 'unsure'} for i in ids])
            self.assertIn('card_blank', [i['kind'] for i in unsure['items']])
            self.assertEqual(unsure['card']['blank'], 6)
            _, full = save(base, run, [{'id': i, 'value': v} for i, v in values.items()])
            self.assertEqual(full['card']['blank'], 0)
            self.assertNotIn('card_blank', [i['kind'] for i in full['items']])
            self.assertNotIn('card_blank', [i['kind'] for i in self.listing(base, run)['items']])


class LinkedCellTests(unittest.TestCase):
    """An unlinked item answered "the data was not all imported" marks the other end as only partly in the data, here on the
    server: the page sends the item alone."""
    @staticmethod
    def customer(body):
        return next(o for o in body['card']['objects'] if o['id'] == CUSTOMER)['answer']

    @staticmethod
    def incomplete(text='客户表只导了一部分', **extra):
        return {'id': ITEM, 'choice': 'incomplete', 'text': text, 'basis': '10-27 会议', **extra}

    def test_answering_incomplete_marks_the_other_end_as_partly_in_the_data_and_says_which_item_did(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            status, saved = save(base, run, items=[self.incomplete()])
            self.assertEqual(status, 200, saved)
            answer = self.customer(saved)
            self.assertEqual({k: v for k, v in answer.items() if k != 'at'},
                             {'value': 'partial', 'says': '数据里只有一部分', 'note': '客户表只导了一部分', 'by': '张三', 'basis': '10-27 会议', 'item': ITEM})
            self.assertEqual(card_of(base, run), saved['card'])
            self.assertEqual(sorted(h['id'] for h in stored_card(out, run)['history']), sorted([CUSTOMER, ITEM]))   # both writes are in the history
            self.assertEqual(saved['card']['blank'], 5)

    def test_answering_incomplete_again_keeps_it_partial_and_the_same_words_are_no_change(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            save(base, run, items=[self.incomplete('先这么记')])
            written = len(stored_card(out, run)['history'])
            _, same = save(base, run, items=[self.incomplete('先这么记')])
            self.assertEqual(len(stored_card(out, run)['history']), written)
            self.assertEqual((self.customer(same)['value'], self.customer(same)['item']), ('partial', ITEM))
            _, again = save(base, run, items=[self.incomplete('改了说法：只有 FY25Q1')], by='李四')
            answer = self.customer(again)
            self.assertEqual((answer['value'], answer['note'], answer['by'], answer['item']), ('partial', '改了说法：只有 FY25Q1', '李四', ITEM))

    def test_an_answer_that_is_not_incomplete_writes_no_cell(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            _, saved = save(base, run, items=[{'id': ITEM, 'choice': 'expected', 'text': '本来就没有'}])
            self.assertIsNone(self.customer(saved))
            self.assertEqual(stored_card(out, run)['cells'], {})

    def test_changing_the_answer_away_takes_back_the_cell_it_wrote(self):
        for away in ({'choice': 'expected', 'text': '本来就没有对应'}, {'text': '再核实一下'}):
            with self.subTest(away=away), OntologyServerTests().server(gateway=CardModel()) as (base, out):
                _, run = call(base, '/api/ontology/build', UPLOAD)
                save(base, run, items=[self.incomplete()])
                _, saved = save(base, run, items=[{'id': ITEM, **away}])
                self.assertIsNone(self.customer(saved))
                stored = stored_card(out, run)
                self.assertNotIn(CUSTOMER, stored['cells'])
                cleared = [h for h in stored['history'] if h['id'] == CUSTOMER]
                self.assertEqual([(h['old'] and h['old']['value'], h['new'] and h['new']['value']) for h in cleared], [(None, 'partial'), ('partial', None)])
                self.assertEqual(saved['card']['blank'], 6)

    def test_changing_the_answer_away_leaves_a_cell_that_is_no_longer_what_it_wrote(self):
        away = {'id': ITEM, 'choice': 'expected', 'text': '本来就没有对应'}
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            save(base, run, items=[self.incomplete()])
            mark(base, run, CUSTOMER, 'full')   # a person set the cell on the card afterwards
            _, saved = save(base, run, items=[away])
            self.assertEqual(self.customer(saved)['value'], 'full')
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            mark(base, run, CUSTOMER, 'partial', note='我自己记的')   # partial, but not written by the item
            _, saved = save(base, run, items=[away])
            self.assertEqual((self.customer(saved)['value'], self.customer(saved)['note']), ('partial', '我自己记的'))
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            save(base, run, items=[self.incomplete()])
            mark(base, run, CUSTOMER, 'partial', note='改成我自己的话')   # the same value, said again by a person: it is theirs now
            _, saved = save(base, run, items=[away])
            self.assertEqual((self.customer(saved)['value'], self.customer(saved)['note']), ('partial', '改成我自己的话'))
            self.assertNotIn('item', self.customer(saved))

    def test_a_request_that_sets_the_cell_itself_wins_over_what_the_item_would_do(self):
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            _, saved = save(base, run, [{'id': CUSTOMER, 'value': 'full', 'note': '其实是全的'}], [self.incomplete()])
            answer = self.customer(saved)
            self.assertEqual((answer['value'], answer['note']), ('full', '其实是全的'))
            self.assertNotIn('item', answer)
            _, cleared = save(base, run, [{'id': CUSTOMER, 'value': None}], [self.incomplete()])
            self.assertIsNone(self.customer(cleared))
        with OntologyServerTests().server(gateway=CardModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            save(base, run, items=[self.incomplete()])
            _, kept = save(base, run, [{'id': CUSTOMER, 'value': 'partial', 'note': '换个说法'}], [{'id': ITEM, 'choice': 'expected', 'text': '本来就没有对应'}])
            answer = self.customer(kept)
            self.assertEqual((answer['value'], answer['note']), ('partial', '换个说法'))
            self.assertNotIn('item', answer)


if __name__ == '__main__':
    unittest.main()
