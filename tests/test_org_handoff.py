"""What an organisation study draws besides the tree: who hands what to whom (the label on the arrow is the point),
and the periods the study is cut into, each fact placed in the period its year falls in."""
import json
import unittest

from ontology_poc_generator.company_documents import load_document_file
from ontology_poc_generator.org_documents import ORG_SYSTEM_PROMPT, build_org_ontology, periods_of
from ontology_poc_generator.recognition import ModelCompletion

TEXT = ('第一阶段 2003—2015 以现场探索为主。第二阶段 2016—2022 走向平台化与专业分工。\n\n'
        'Echo 把业务目标与约束交给 Delta，Delta 把功能论证与使用反馈交给产品经理。\n\n'
        '2019年，Ryan Beiermeister 担任 Gotham 产品经理。')


def entity(key, kind, name, evidence, **extra):
    return {'key': key, 'type': kind, 'name': name, 'evidence': evidence, **extra}


REPLY = {
    'entities': [
        entity('p1', 'period', '第一阶段', '第一阶段 2003—2015 以现场探索为主', when='2003—2015'),
        entity('p2', 'period', '第二阶段', '第二阶段 2016—2022 走向平台化与专业分工', when='2016—2022'),
        entity('p3', 'period', '第三阶段', '第二阶段 2016—2022 走向平台化与专业分工', when='2023年以来'),   # a time the text does not have
        entity('echo', 'role', 'Echo', 'Echo 把业务目标与约束交给 Delta', note='业务定义与采用'),
        entity('delta', 'role', 'Delta', 'Echo 把业务目标与约束交给 Delta'),
        entity('pm', 'role', '产品经理', 'Delta 把功能论证与使用反馈交给产品经理'),
        entity('ryan', 'person', 'Ryan Beiermeister', 'Ryan Beiermeister 担任 Gotham 产品经理'),
    ],
    'facts': [
        {'kind': 'hands_to', 'from': 'echo', 'to': 'delta', 'what': '业务目标与约束', 'evidence': 'Echo 把业务目标与约束交给 Delta'},
        {'kind': 'hands_to', 'from': 'delta', 'to': 'pm', 'what': '功能论证与使用反馈', 'evidence': 'Delta 把功能论证与使用反馈交给产品经理'},
        {'kind': 'hands_to', 'from': 'pm', 'to': 'echo', 'evidence': 'Delta 把功能论证与使用反馈交给产品经理'},   # handing over nothing named
        {'kind': 'holds', 'from': 'ryan', 'to': 'pm', 'when': '2019年', 'evidence': 'Ryan Beiermeister 担任 Gotham 产品经理'},
    ],
    'open': [],
}


class Model:
    def complete_json(self, *, system_prompt, user_prompt):
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(REPLY))


def build():
    return build_org_ontology(load_document_file('study.md', TEXT.encode()), Model())


class HandoffTests(unittest.TestCase):
    def test_a_handoff_keeps_what_is_handed_over(self):
        handed = {(r['from'], r['to']): r.get('what') for r in build()['relations'] if r['kind'] == 'hands_to'}
        self.assertEqual(handed, {('echo', 'delta'): '业务目标与约束', ('delta', 'pm'): '功能论证与使用反馈'})

    def test_a_handoff_of_nothing_named_is_dropped_and_says_why(self):
        reasons = ' | '.join(f"{r['item']}：{r['reason']}" for r in build()['rejected'])
        self.assertIn('产品经理 → Echo', reasons)
        self.assertIn('交接什么', reasons)

    def test_a_role_keeps_its_line_of_duties(self):
        echo = next(t for t in build()['object_types'] if t['key'] == 'echo')
        self.assertEqual(echo['definition'], '业务定义与采用')

    def test_the_prompt_asks_for_handoffs_and_periods(self):
        for word in ('hands_to', 'what', 'period'):
            self.assertIn(word, ORG_SYSTEM_PROMPT)


class PeriodTests(unittest.TestCase):
    def test_a_period_keeps_its_time_only_as_the_text_writes_it(self):
        ontology = build()
        when = {t['key']: t.get('when') for t in ontology['object_types'] if t['org_type'] == 'period'}
        self.assertEqual(when, {'p1': '2003—2015', 'p2': '2016—2022', 'p3': None})

    def test_periods_come_in_order_with_the_dated_facts_that_fall_in_them(self):
        laid = periods_of(build())
        self.assertEqual([(p['name'], p['from'], p['to']) for p in laid['periods']], [('第一阶段', 2003, 2015), ('第二阶段', 2016, 2022)])
        self.assertEqual([f['kind'] for f in laid['periods'][1]['facts']], ['holds'])
        self.assertEqual(laid['undated'], ['第三阶段'])


class RunTests(unittest.TestCase):
    def test_the_run_carries_the_periods_so_every_reader_lays_them_out_the_same(self):
        from ontology_poc_generator.org_documents import build_and_evaluate_org
        run = build_and_evaluate_org(load_document_file('study.md', TEXT.encode()), Model())
        self.assertEqual([p['name'] for p in run['evaluation']['periods']['periods']], ['第一阶段', '第二阶段'])
        self.assertEqual(run['evaluation']['periods']['undated'], ['第三阶段'])


if __name__ == '__main__':
    unittest.main()
