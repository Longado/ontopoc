"""A derived measure: an amount no column holds, written as a formula over one object's fields (unit price × quantity ×
(1 − discount)). The model proposes the formula, code computes it on every object and says how many it could not,
the person confirms it; after that the question is answered and later questions can use it. Only sums of products of
fields (a field or 1 − field) are allowed, never an arbitrary expression. And an answer that cannot be given says why
in the business's words, not in the ontology's keys."""
import base64
import json
import unittest

from ontology_poc_generator.company_sources import load_table_file
from ontology_poc_generator.derived_measures import compute, formula_text, parse_derived, plain_reason
from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT, run_query
from ontology_poc_generator.recognition import ModelCompletion
from tests.test_ontology_ask_server import call
from tests.test_ontology_server import OntologyServerTests

CSV = ('订单号,产品,客户,单价,数量,折扣\n'
       'O1,P1,C1,10,2,0.5\n'
       'O1,P2,C1,5,4,0\n'
       'O2,P1,C2,3,1,0\n').encode('utf-8')
ONTOLOGY = {
    'reasoning': 'r',
    'object_types': [
        {'key': 'order_line', 'label': '订单明细', 'populated_from': [{'source': 'lines', 'identity': {'order': '订单号', 'product': '产品'}}],
         'attributes': [{'source': 'lines', 'path': p} for p in ('单价', '数量', '折扣')]},
        {'key': 'customer', 'label': '客户', 'populated_from': [{'source': 'lines', 'identity': {'customer_id': '客户'}}], 'attributes': []},
    ],
    'relations': [{'key': 'line_of_customer', 'from': 'order_line', 'to': 'customer', 'source': 'lines', 'label': '属于', 'meaning': '明细属于客户'}],
    'ignored_fields': [], 'open_questions': [],
}
AMOUNT = {'type': 'order_line', 'label': '金额',
          'terms': [{'sign': 1, 'factors': [{'field': '单价'}, {'field': '数量'}, {'field': '折扣', 'complement': True}]}]}
BY_CUSTOMER = {'start': 'order_line', 'where': [], 'via': [], 'share': None,
               'group_by': [{'via': ['line_of_customer'], 'field': '客户'}], 'measure': {'derived': '金额', 'op': 'sum'}}


def bundle(csv=CSV):
    return load_table_file('lines.csv', csv)


class FormulaTests(unittest.TestCase):
    def test_a_formula_is_read_back_in_the_business_words(self):
        derived, reason = parse_derived(ONTOLOGY, AMOUNT)
        self.assertIsNone(reason)
        self.assertEqual(formula_text(derived), '单价 × 数量 ×（1 − 折扣）')
        margin, _ = parse_derived(ONTOLOGY, {'type': 'order_line', 'label': '差额',
                                             'terms': [{'sign': 1, 'factors': [{'field': '单价'}]}, {'sign': -1, 'factors': [{'field': '折扣'}]}]})
        self.assertEqual(formula_text(margin), '单价 − 折扣')

    def test_anything_but_fields_of_that_object_is_refused_with_a_reason(self):
        for bad, said in ((dict(AMOUNT, type='invoice'), 'invoice'),
                          (dict(AMOUNT, terms=[{'sign': 1, 'factors': [{'field': '运费'}]}]), '运费'),
                          (dict(AMOUNT, terms=[{'sign': 1, 'factors': [{'field': '单价', 'expr': '__import__("os")'}]}]), '只能'),
                          (dict(AMOUNT, terms=[]), '公式')):
            derived, reason = parse_derived(ONTOLOGY, bad)
            self.assertIsNone(derived)
            self.assertIn(said, reason)

    def test_code_computes_it_on_every_object_and_counts_what_it_could_not(self):
        rows = CSV.decode() + 'O3,P3,C2,abc,1,0\n'
        derived, _ = parse_derived(ONTOLOGY, AMOUNT)
        got = compute(ONTOLOGY, bundle(rows.encode()), derived)
        self.assertEqual((got['counted'], got['skipped']), (3, 1))
        self.assertEqual(sorted(got['values'].values()), [3.0, 10.0, 20.0])
        self.assertIn('abc', got['skipped_examples'][0])


class QueryTests(unittest.TestCase):
    def test_once_confirmed_the_amount_is_summed_per_customer(self):
        derived, _ = parse_derived(ONTOLOGY, AMOUNT)
        result = run_query(ONTOLOGY, bundle(), BY_CUSTOMER, derived=[derived])
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['answer']['groups'], [['C1', 30, 2], ['C2', 3, 1]])
        self.assertIn('金额', result['path'])

    def test_before_it_is_confirmed_the_query_says_what_it_waits_for(self):
        result = run_query(ONTOLOGY, bundle(), BY_CUSTOMER, derived=[])
        self.assertEqual(result['status'], 'ontology_gap')
        self.assertIn('金额', result['reason'])

    def test_the_prompt_tells_the_model_how_to_propose_one(self):
        for word in ('derive', 'complement', 'derived'):
            self.assertIn(word, QUESTION_SYSTEM_PROMPT)


class ReasonTests(unittest.TestCase):
    def test_keys_in_a_reason_become_the_names_people_read(self):
        text = '从 customer 经 line_of_customer 到 order_line，再算 单价 × 数量'
        self.assertEqual(plain_reason(ONTOLOGY, text), '从 客户 经 属于 到 订单明细，再算 单价 × 数量')


REPLY = {'questions': [{'reasoning': '客户的金额要从 order_line 算：单价 × 数量 ×（1 − 折扣）', 'question': '每个客户买了多少钱？',
                        'derive': AMOUNT, 'query': BY_CUSTOMER}]}


class Model:
    def __init__(self):
        self.asked = []

    def complete_json(self, *, system_prompt, user_prompt):
        if system_prompt == QUESTION_SYSTEM_PROMPT:
            self.asked.append(json.loads(user_prompt))
            content = REPLY
        else:
            content = ONTOLOGY
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(content))


class ServerTests(unittest.TestCase):
    def test_propose_try_confirm_and_the_question_is_answered(self):
        model = Model()
        upload = {'filename': 'lines.csv', 'content_base64': base64.b64encode(CSV).decode()}
        with OntologyServerTests().server(gateway=model) as (base, _):
            _, run = call(base, '/api/ontology/build', upload)
            status, asked = call(base, '/api/ontology/ask', {'saved_as': run['saved_as'], 'question': '每个客户买了多少钱？'})
            self.assertEqual(status, 200, asked)
            [item] = asked['evaluation']['asked'][-1]['items']
            self.assertEqual(item['status'], 'needs_derived')
            self.assertEqual(item['derive']['formula'], '单价 × 数量 ×（1 − 折扣）')
            self.assertEqual((item['derive']['preview']['counted'], item['derive']['preview']['skipped']), (3, 0))
            status, confirmed = call(base, '/api/ontology/derived', {'saved_as': run['saved_as'], 'derive': item['derive']})
            self.assertEqual(status, 200, confirmed)
            [again] = confirmed['evaluation']['asked'][-1]['items']
            self.assertEqual((again['status'], again['answer']['groups']), ('answered', [['C1', 30, 2], ['C2', 3, 1]]))
            _, rerun = call(base, '/api/ontology/build', upload)
            self.assertEqual([d['label'] for d in rerun['evaluation']['derived']], ['金额'])   # it stays with the file
            call(base, '/api/ontology/ask', {'saved_as': rerun['saved_as'], 'question': '每个客户买了多少钱？'})
        catalog = model.asked[-1]['ontology']['object_types']
        line = next(t for t in catalog if t['key'] == 'order_line')
        self.assertEqual(line['derived'], [{'name': '金额', 'formula': '单价 × 数量 ×（1 − 折扣）'}])

    def test_a_formula_the_page_sends_is_checked_again(self):
        upload = {'filename': 'lines.csv', 'content_base64': base64.b64encode(CSV).decode()}
        with OntologyServerTests().server(gateway=Model()) as (base, _):
            _, run = call(base, '/api/ontology/build', upload)
            status, body = call(base, '/api/ontology/derived', {'saved_as': run['saved_as'], 'derive': dict(AMOUNT, type='invoice')})
        self.assertEqual(status, 400)
        self.assertIn('invoice', body['error'])


if __name__ == '__main__':
    unittest.main()
