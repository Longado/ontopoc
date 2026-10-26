import base64
from datetime import datetime
import json
import unittest

from tests.test_new_version import V1, V2, upload
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests

UPLOAD = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}


class AcceptanceServerTests(unittest.TestCase):
    def test_saved_questions_are_rerun_on_the_next_upload_of_the_same_file(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            _, first = call(base, '/api/ontology/build', UPLOAD)
            asked = call(base, '/api/ontology/ask', {'saved_as': first['saved_as'], 'question': '每个客户有多少订单？'})[1]
            item = asked['evaluation']['asked'][-1]['items'][0]
            status, saved = call(base, '/api/ontology/acceptance', {'saved_as': first['saved_as'],
                                                                    'items': [{'question': item['question'], 'query': item['query'], 'note': '按订单号计数'}]})
            self.assertEqual(status, 200, saved)
            self.assertEqual(saved['evaluation']['acceptance']['items'][0]['note'], '按订单号计数')
            self.assertEqual(saved['evaluation']['acceptance']['answered'], 1)
            self.assertTrue((out / 'acceptance').is_dir())
            _, again = call(base, '/api/ontology/build', UPLOAD)
            rerun = again['evaluation']['acceptance']
            self.assertEqual(rerun['total'], 1)
            self.assertIs(rerun['items'][0]['changed'], False)
            status, body = call(base, '/api/ontology/acceptance', {'saved_as': first['saved_as'], 'items': [{'question': 'x'}]})
            self.assertEqual(status, 400)
            self.assertIn('查询', body['error'])


COUNT_ORDERS = {'question': '订单总数是多少？', 'query': {'start': 'order', 'where': [], 'via': [], 'group_by': None}, 'note': ''}   # 2 orders in V1, 3 in V2


def accept(base, run, items, **extra):
    status, body = call(base, '/api/ontology/acceptance', {'saved_as': run['saved_as'], 'items': items, **extra})
    assert status == 200, body
    return body['evaluation']['acceptance']['items']


def page_shape(item, **over):
    """What the page sends back for a question that is already on the list."""
    return {**{k: item.get(k) for k in ('question', 'query', 'note', 'snapshot', 'answer', 'status', 'path')}, **over}


class ConfirmedAnswerTests(unittest.TestCase):
    def test_the_answer_a_person_accepts_is_stored_on_its_own_and_never_taken_from_the_page(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', upload(V1))
            forged = {'status': 'answered', 'answer': {'total': 99}, 'path': 'x', 'at': '2020-01-01T00:00:00+00:00', 'file': 'forged', 'saved_as': 'forged.json'}
            [item] = accept(base, run, [{**COUNT_ORDERS, 'confirmed': forged}])
            confirmed = item['confirmed']
            self.assertEqual((confirmed['status'], confirmed['answer'], confirmed['path']), ('answered', {'total': 2}, item['path']))
            self.assertEqual((confirmed['file'], confirmed['saved_as']), (run['file']['sha256'], run['saved_as']))
            self.assertGreater(datetime.fromisoformat(confirmed['at']), datetime.fromisoformat('2026-01-01T00:00:00+00:00'))
            stored = json.loads((out / 'acceptance' / f"{run['file']['sha256']}.json").read_text(encoding='utf-8'))
            self.assertEqual(stored['items'][0]['confirmed'], confirmed)

    def test_editing_the_list_keeps_what_was_agreed_and_records_only_what_is_new(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            _, first = call(base, '/api/ontology/build', upload(V1))
            [one] = accept(base, first, [COUNT_ORDERS])
            _, second = call(base, '/api/ontology/build', upload(V2, previous=first['saved_as']))
            kept = second['evaluation']['acceptance']['items'][0]
            self.assertEqual(kept['answer'], {'total': 3})
            # the same list plus one new question, sent as the page sends it: the old one still stands on the V1 answer
            other = {**COUNT_ORDERS, 'question': '有几张订单？'}
            items = accept(base, second, [page_shape(kept), other])
            self.assertEqual(items[0]['confirmed'], one['confirmed'])
            self.assertEqual(items[1]['confirmed']['answer'], {'total': 3})
            self.assertEqual(items[1]['confirmed']['saved_as'], second['saved_as'])
            # accepting the same question again is a new agreement, on the answer in front of the person now
            [again] = accept(base, second, [page_shape(kept, note='重新认可')], replace_question=kept['question'])
            self.assertEqual((again['confirmed']['answer'], again['confirmed']['file']), ({'total': 3}, second['file']['sha256']))
            # and the page reads it against that agreement at once, not against the run before
            self.assertIs(again['changed'], False)
            self.assertEqual((again['previous']['answer'], again['previous']['confirmed_at']), ({'total': 3}, again['confirmed']['at']))

    def test_slow_drift_is_reported_on_every_rerun_against_what_the_person_agreed_to(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            _, first = call(base, '/api/ontology/build', upload(V1))
            [item] = accept(base, first, [COUNT_ORDERS])
            agreed = item['confirmed']
            _, second = call(base, '/api/ontology/build', upload(V2, previous=first['saved_as']))
            _, third = call(base, '/api/ontology/build', upload(V2, previous=second['saved_as']))   # the same changed data again
            for run in (second, third):
                moved = run['evaluation']['acceptance']['items'][0]
                self.assertIs(moved['changed'], True)
                self.assertEqual(moved['answer'], {'total': 3})
                self.assertEqual(moved['previous']['answer'], {'total': 2})
                self.assertEqual((moved['previous']['confirmed_at'], moved['previous']['confirmed_file']), (agreed['at'], first['file']['sha256']))
                self.assertEqual(moved['confirmed'], agreed)
            stored = json.loads((out / 'acceptance' / f"{first['file']['sha256']}.json").read_text(encoding='utf-8'))
            self.assertEqual(stored['items'][0]['confirmed'], agreed)
            # the data comes back to what was agreed: no longer different
            _, back = call(base, '/api/ontology/build', upload(V1, previous=third['saved_as']))
            self.assertIs(back['evaluation']['acceptance']['items'][0]['changed'], False)

    def test_confirming_the_ontology_rechecks_the_list_and_keeps_what_was_agreed(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            _, first = call(base, '/api/ontology/build', upload(V1))
            [item] = accept(base, first, [COUNT_ORDERS])
            decisions = {'types': {t['key']: {'verdict': 'ok'} for t in first['ontology']['object_types']}, 'relations': {}, 'added': []}
            _, reviewed = call(base, '/api/ontology/confirm', {'saved_as': first['saved_as'], 'decisions': decisions})
            self.assertEqual(reviewed['evaluation']['acceptance']['items'][0]['confirmed'], item['confirmed'])
            stored = json.loads((out / 'acceptance' / f"{first['file']['sha256']}.json").read_text(encoding='utf-8'))
            self.assertEqual(stored['items'][0]['confirmed'], item['confirmed'])

    def test_a_list_saved_before_confirmations_existed_is_compared_as_before_and_not_given_one(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            _, first = call(base, '/api/ontology/build', upload(V1))
            accept(base, first, [COUNT_ORDERS])
            for path in (out / 'acceptance' / f"{first['file']['sha256']}.json", out / first['saved_as']):
                saved = json.loads(path.read_text(encoding='utf-8'))
                items = saved['items'] if 'items' in saved else saved['evaluation']['acceptance']['items']
                for item in items:
                    del item['confirmed']
                path.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
            _, second = call(base, '/api/ontology/build', upload(V2, previous=first['saved_as']))
            _, third = call(base, '/api/ontology/build', upload(V2, previous=second['saved_as']))
            moved, settled = second['evaluation']['acceptance']['items'][0], third['evaluation']['acceptance']['items'][0]
            self.assertIs(moved['changed'], True)
            self.assertNotIn('confirmed_at', moved['previous'])
            self.assertIs(settled['changed'], False)   # compared with the last run, as it always was
            [edited] = accept(base, third, [page_shape(settled)])
            self.assertNotIn('confirmed', edited)   # nobody agreed to this answer: an edit of the list does not make one


if __name__ == '__main__':
    unittest.main()
