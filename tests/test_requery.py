import base64
from contextlib import contextmanager
import json
import threading
import unittest

from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
from ontology_poc_generator.recognition import ModelCompletion
from tests.test_ontology_ask_server import call
from tests.test_ontology_server import OntologyServerTests

CSV = '订单号,客户编号,地区,金额\nO1,C1,N,100\nO2,C2,N,50\nO3,C1,S,10\nO4,C2,S,5\n'.encode('utf-8')
UPLOAD = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}
PROPOSAL = {
    'reasoning': 'r',
    'object_types': [
        {'key': 'order', 'label': '订单', 'populated_from': [{'source': 'orders', 'identity': {'order_id': '订单号'}}],
         'attributes': [{'source': 'orders', 'path': '金额'}, {'source': 'orders', 'path': '客户编号'}, {'source': 'orders', 'path': '地区'}]},
        {'key': 'customer', 'label': '客户', 'populated_from': [{'source': 'orders', 'identity': {'customer_id': '客户编号'}}], 'attributes': []},
    ],
    'relations': [{'key': 'order_customer', 'from': 'order', 'to': 'customer', 'source': 'orders', 'meaning': '订单属于客户'}],
    'ignored_fields': [], 'open_questions': [],
}
QUESTION = '订单金额一共多少？'
BOTH = [{'field': '地区', 'equals': 'N'}, {'field': '客户编号', 'equals': 'C1'}]   # only O1 passes both: 100
QUERY = {'start': 'order', 'where': BOTH, 'via': [], 'group_by': None, 'share': None, 'measure': {'field': '金额', 'op': 'sum'}}
QUESTIONS = {'questions': [{'reasoning': 'r', 'question': QUESTION, 'query': QUERY}]}


class Model:
    def complete_json(self, *, system_prompt, user_prompt):
        return ModelCompletion(provider='fake', model='deepseek-flash',
                               content=json.dumps(QUESTIONS if system_prompt == QUESTION_SYSTEM_PROMPT else PROPOSAL))


def requery(base, saved_as, field='客户编号', equals='C1', question=QUESTION):
    return call(base, '/api/ontology/requery', {'saved_as': saved_as, 'question': question, 'drop': {'field': field, 'equals': equals}})


def change_run(out, saved_as, change):
    path = out / saved_as
    run = json.loads(path.read_text(encoding='utf-8'))
    change(run)
    path.write_text(json.dumps(run, ensure_ascii=False), encoding='utf-8')


@contextmanager
def asked_run():
    """A server with a model that has built the upload and been asked the question; yields (base, dir, run name)."""
    with OntologyServerTests().server(gateway=Model()) as (base, out):
        _, run = call(base, '/api/ontology/build', UPLOAD)
        status, run = call(base, '/api/ontology/ask', {'saved_as': run['saved_as'], 'question': QUESTION})
        assert status == 200, run
        assert run['evaluation']['asked'][-1]['items'][0]['answer']['measure']['value'] == 100, run
        yield base, out, run['saved_as']


class RequeryTests(unittest.TestCase):
    def test_dropping_a_condition_answers_the_question_again_as_a_new_round(self):
        with asked_run() as (base, out, saved_as):
            status, run = requery(base, saved_as)
            self.assertEqual(status, 200, run)
            rounds = run['evaluation']['asked']
            self.assertEqual(len(rounds), 2)
            latest = rounds[-1]
            self.assertEqual({k: v for k, v in latest.items() if k != 'asked_at' and k != 'items'},
                             {'prompt_version': None, 'model': None, 'answered': 1, 'total': 1, 'error': None})
            self.assertRegex(latest['asked_at'], r'^\d{4}-\d\d-\d\dT')
            [item] = latest['items']
            self.assertEqual((item['question'], item['reasoning'], item['asked']), (QUESTION, '', True))
            self.assertEqual(item['query'], {**QUERY, 'where': [{'field': '地区', 'equals': 'N'}]})
            self.assertEqual((item['status'], item['answer']['total'], item['answer']['measure']['value']), ('answered', 2, 150))
            self.assertEqual([f['field'] for f in item['evidence']['filters']], ['地区'])
            self.assertEqual(item['edited'], {'dropped': [{'field': '客户编号', 'equals': 'C1'}]})
            self.assertEqual(json.loads((out / saved_as).read_text(encoding='utf-8'))['evaluation']['asked'], rounds)

    def test_a_question_that_was_already_edited_collects_the_dropped_conditions(self):
        with asked_run() as (base, _, saved_as):
            requery(base, saved_as)
            status, run = requery(base, saved_as, field='地区', equals='N')
            self.assertEqual(status, 200, run)
            [item] = run['evaluation']['asked'][-1]['items']
            self.assertEqual(item['query']['where'], [])
            self.assertEqual((item['answer']['total'], item['answer']['measure']['value']), (4, 165))
            self.assertEqual(item['edited'], {'dropped': [{'field': '客户编号', 'equals': 'C1'}, {'field': '地区', 'equals': 'N'}]})
            self.assertEqual(len(run['evaluation']['asked']), 3)

    def test_a_condition_the_query_does_not_have_is_refused(self):
        with asked_run() as (base, out, saved_as):
            for field, equals in (('地区', 'S'), ('金额', 'N'), ('地区', ['N']), ('地区', 'n')):
                with self.subTest(field=field, equals=equals):
                    status, body = requery(base, saved_as, field, equals)
                    self.assertEqual((status, body['error']), (400, '这道题的查询里没有这个条件'))
            self.assertEqual(len(json.loads((out / saved_as).read_text(encoding='utf-8'))['evaluation']['asked']), 1)

    def test_a_run_or_question_that_is_not_there_is_not_found(self):
        with asked_run() as (base, _, saved_as):
            self.assertEqual(requery(base, saved_as, question='没问过的题')[0], 404)
            self.assertEqual(requery(base, '20260101T000000Z-deadbeef.json')[0], 404)
            self.assertEqual(requery(base, '../../etc/passwd')[0], 400)
            status, body = call(base, '/api/ontology/requery', {'saved_as': saved_as, 'question': QUESTION, 'drop': '地区'})
            self.assertEqual(status, 400)

    def test_it_works_without_a_model_because_no_model_is_called(self):
        from ontology_poc_generator.ontology_server import make_server
        with asked_run() as (_, out, saved_as):
            server = make_server(port=0, gateway=None, output_dir=out)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, run = requery(f'http://127.0.0.1:{server.server_port}', saved_as)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
            self.assertEqual(status, 200, run)
            self.assertEqual(run['evaluation']['asked'][-1]['items'][0]['answer']['measure']['value'], 150)

    def test_a_question_found_only_among_the_accepted_ones_can_be_edited_too(self):
        with asked_run() as (base, out, saved_as):
            call(base, '/api/ontology/acceptance', {'saved_as': saved_as, 'items': [{'question': QUESTION, 'query': QUERY, 'note': ''}]})
            change_run(out, saved_as, lambda run: run['evaluation'].update(asked=[]))
            status, run = requery(base, saved_as)
            self.assertEqual(status, 200, run)
            [item] = run['evaluation']['asked'][-1]['items']
            self.assertEqual((item['answer']['total'], item['edited']['dropped']), (2, [{'field': '客户编号', 'equals': 'C1'}]))

    def test_the_new_answer_can_be_accepted_in_place_of_the_old_one(self):
        with asked_run() as (base, _, saved_as):
            _, accepted = call(base, '/api/ontology/acceptance', {'saved_as': saved_as, 'items': [{'question': QUESTION, 'query': QUERY, 'note': ''}]})
            self.assertEqual(accepted['evaluation']['acceptance']['items'][0]['confirmed']['answer']['total'], 1)
            _, run = requery(base, saved_as)
            [item] = run['evaluation']['asked'][-1]['items']
            status, replaced = call(base, '/api/ontology/acceptance', {
                'saved_as': saved_as, 'replace_question': QUESTION, 'items': [{'question': QUESTION, 'query': item['query'], 'note': '只看北区'}]})
            self.assertEqual(status, 200, replaced)
            [kept] = replaced['evaluation']['acceptance']['items']
            self.assertEqual((kept['query'], kept['confirmed']['answer']['total']), (item['query'], 2))

    def test_what_cannot_be_asked_again_is_refused_with_the_reason(self):
        def no_query(run):
            run['evaluation']['asked'].append({'items': [{'question': '没有查询的题', 'query': None, 'status': 'query_limit', 'reason': 'r'}]})
        for name, change, message in (
                ('no query', no_query, '没有查询'),
                ('document', lambda run: run['file'].update(kind='document'), '文档没有数据行'),
                ('not verified', lambda run: run['ontology'].update(status='rejected'), '没有通过结构核验')):
            with self.subTest(name), asked_run() as (base, out, saved_as):
                change_run(out, saved_as, change)
                status, body = requery(base, saved_as, question='没有查询的题' if name == 'no query' else QUESTION)
                self.assertEqual(status, 400)
                self.assertIn(message, body['error'])


if __name__ == '__main__':
    unittest.main()
