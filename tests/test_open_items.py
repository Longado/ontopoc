import copy
import unittest

from ontology_poc_generator import ontology_card
from ontology_poc_generator.open_items import check_answers, open_items, split_answers
from tests.test_ontology_card import ONTOLOGY as LEDGER_ONTOLOGY, bundle as ledger_bundle

KINDS = ['model_filter', 'merged', 'found_elsewhere', 'unlinked', 'same_name', 'unstable', 'check_finding',
         'data_gaps', 'unanswered', 'unjudged']

ONTOLOGY = {
    'status': 'auto_built_verified', 'data_gaps': [],
    'object_types': [
        {'key': 'spend', 'label': '支出行', 'populated_from': [{'source': 'spend', 'identity': {'row_id': 'row_id'}}], 'attributes': []},
        {'key': 'contract', 'label': '合同授标', 'populated_from': [{'source': 'contracts', 'identity': {'award_key': 'award_key'}}], 'attributes': []},
        {'key': 'vehicle', 'label': '母合同', 'populated_from': [{'source': 'vehicles', 'identity': {'vehicle_key': 'vehicle_key'}}], 'attributes': []},
        {'key': 'vendor', 'label': '承包商', 'populated_from': [{'source': 'vendors', 'identity': {'uei': 'uei'}}],
         'attributes': [{'source': 'vendors', 'path': 'vendor_name'}]},
    ],
    'relations': [
        {'key': 'spend_contract', 'from': 'spend', 'to': 'contract', 'label': '对应', 'source': 'spend'},
        {'key': 'contract_vehicle', 'from': 'contract', 'to': 'vehicle', 'label': '属于', 'source': 'contracts'},
        {'key': 'contract_vendor', 'from': 'contract', 'to': 'vendor', 'label': '授予', 'source': 'contracts'},
    ],
}
DECIDED = {'decisions': {'types': {t['key']: {'verdict': 'ok'} for t in ONTOLOGY['object_types']},
                         'relations': {r['key']: {'verdict': 'ok'} for r in ONTOLOGY['relations']}}}


def vendors(*rows):
    return {'sources': {'spend': {'records': []}, 'contracts': {'records': []}, 'vehicles': {'records': []},
                        'vendors': {'records': [{'uei': uei, 'vendor_name': name} for uei, name in rows]}}}


def padded(count, *rows):
    """Vendors that share a name only in `rows`, among `count` vendors in all: the rest each have a name of their own."""
    return vendors(*rows, *((f'U{n}', f'Unique {n}') for n in range(count - len(rows))))


BUNDLE = vendors(('K1', 'Acme'), ('K2', 'Bolt'))


def run(evaluation=None, ontology=None, **top):
    """A kept run as the server saves it, with every object and relation already judged unless the test says otherwise."""
    return {'file': {'kind': 'table'}, 'ontology': ontology or ONTOLOGY, 'evaluation': evaluation or {},
            'confirmation': DECIDED, **top}


def answered(question, evidence, **over):
    return {'question': question, 'status': 'answered', 'asked': True, 'evidence': evidence,
            'query': {'start': 'spend', 'where': [], 'measure': {'field': 'amount', 'op': 'sum'}},
            'answer': {'total': 3, 'measure': {'field': 'amount', 'op': 'sum', 'value': 1, 'counted': 1, 'skipped': 0}}, **over}


def asked(*items):
    return [{'prompt_version': None, 'model': None, 'asked_at': '2026-10-27T00:00:00+00:00', 'items': list(items),
             'answered': 0, 'total': len(items), 'error': None}]


def kinds(items):
    return [i['kind'] for i in items]


PAID = '垦务局签的合同累计付了多少钱？'
ADDED = {'field': 'subagency', 'equals': 'BUREAU OF RECLAMATION', 'before': 1455, 'after': 1444,
         'examples': ['4431 · P03', '4948 · P03'], 'removed_measure': 4176392.96, 'not_in_question': True}


class ModelFilterTests(unittest.TestCase):
    def test_a_condition_the_model_added_is_asked_with_the_rows_it_removed_and_their_sum(self):
        filters = [
            {'field': 'period', 'equals': '2024-12-31', 'before': 1921, 'after': 1455, 'examples': [], 'removed_measure': 24998153.82},
            {'field': 'agency_id', 'equals': '1425', 'before': 1455, 'after': 1455, 'examples': [], 'not_in_question': True},
            ADDED]
        items = open_items(run({'asked': asked(answered(PAID, {'filters': filters}))}), BUNDLE)
        self.assertEqual(kinds(items), ['model_filter'])
        self.assertEqual(items[0], {
            'kind': 'model_filter', 'from_model': False, 'question': PAID,
            'ask': f'「{PAID}」的答案里，模型自己加了条件“subagency = BUREAU OF RECLAMATION”，问题里没提。'
                   '它筛掉了 11 个支出行，这些行的“amount”合计 4,176,392.96。这个条件该不该加？',
            'facts': ['筛选前 1,455 个支出行，筛选后 1,444 个', '被筛掉的有：4431 · P03、4948 · P03'],
            'target': {'tab': 'qa', 'place': 'ask', 'question': PAID},
            'filter': {'field': 'subagency', 'equals': 'BUREAU OF RECLAMATION', 'before': 1455, 'after': 1444, 'removed_measure': 4176392.96}})

    def test_without_a_removed_sum_the_sentence_stops_at_the_count(self):
        added = {k: v for k, v in ADDED.items() if k != 'removed_measure'}
        [item] = open_items(run({'asked': asked(answered(PAID, {'filters': [{**added, 'before': 3, 'after': 2}]}))}), BUNDLE)
        self.assertEqual(item['ask'], f'「{PAID}」的答案里，模型自己加了条件“subagency = BUREAU OF RECLAMATION”，问题里没提。'
                                      '它筛掉了 1 个支出行。这个条件该不该加？')
        self.assertNotIn('removed_measure', item['filter'])

    def test_a_whole_number_sum_is_written_with_thousands_separators_and_no_decimals(self):
        [item] = open_items(run({'asked': asked(answered(PAID, {'filters': [{**ADDED, 'removed_measure': 1279108723}]}))}), BUNDLE)
        self.assertIn('合计 1,279,108,723。', item['ask'])

    def test_an_accepted_question_with_a_written_basis_is_not_asked_again(self):
        item = answered(PAID, {'filters': [ADDED]}, note='只算垦务局自己的合同')
        self.assertEqual(open_items(run({'acceptance': {'items': [item]}}), BUNDLE), [])
        [listed] = open_items(run({'acceptance': {'items': [{**item, 'note': ''}]}}), BUNDLE)
        self.assertEqual(listed['target'], {'tab': 'qa', 'place': 'acceptance', 'question': PAID})

    def test_only_the_latest_ask_of_a_question_counts_and_the_models_own_round_does_not(self):
        earlier = answered(PAID, {'filters': [ADDED]})
        later = answered(PAID, {'filters': [{**ADDED, 'not_in_question': False}]})
        self.assertEqual(open_items(run({'asked': asked(earlier) + asked(later)}), BUNDLE), [])
        own_round = {'items': [answered('模型自己出的题', {'filters': [ADDED]})]}
        self.assertEqual(open_items(run({'questions': own_round}), BUNDLE), [])

    def test_the_accepted_version_of_a_question_stands_in_for_the_asked_one(self):
        accepted = answered(PAID, {'filters': [{**ADDED, 'not_in_question': False}]}, note='')
        evaluation = {'asked': asked(answered(PAID, {'filters': [ADDED]})), 'acceptance': {'items': [accepted]}}
        self.assertEqual(open_items(run(evaluation), BUNDLE), [])


    def test_an_accepted_question_already_asked_again_without_the_condition_asks_to_replace_it(self):
        accepted = answered(PAID, {'filters': [ADDED]}, note='')
        again = answered(PAID, {'filters': []}, query={'start': 'spend', 'where': []},
                         edited={'dropped': [{'field': 'spend.subagency', 'equals': 'BUREAU OF RECLAMATION'}]})
        [item] = open_items(run({'asked': asked(again), 'acceptance': {'items': [accepted]}}), BUNDLE)
        self.assertEqual(item['kind'], 'model_filter')
        self.assertEqual(item['ask'], f'「{PAID}」去掉模型加的条件“subagency = BUREAU OF RECLAMATION”重算过了，'
                                      '验收题里存的还是带这个条件的答案。要换成新答案吗？')
        self.assertEqual(item['target'], {'tab': 'qa', 'place': 'ask', 'question': PAID})

    def test_only_the_item_for_a_condition_already_asked_again_says_so(self):
        [plain] = open_items(run({'asked': asked(answered(PAID, {'filters': [ADDED]}))}), BUNDLE)
        self.assertNotIn('requeried', plain)
        accepted = answered(PAID, {'filters': [ADDED]}, note='')
        again = answered(PAID, {'filters': []}, edited={'dropped': [{'field': 'spend.subagency', 'equals': 'BUREAU OF RECLAMATION'}]})
        [replaced] = open_items(run({'asked': asked(again), 'acceptance': {'items': [accepted]}}), BUNDLE)
        self.assertIs(replaced['requeried'], True)


class MergedAndElsewhereTests(unittest.TestCase):
    GROUP = {'group': 'GREENBERRY INDUSTRIAL LLC', 'starts': 1, 'objects': 2, 'start': '承包商', 'reached': '最终母公司',
             'examples': ['PRRXANJSLS26', 'ZZ3GL25MGJH2']}

    def test_groups_that_hold_several_objects_are_asked_up_to_three_per_question(self):
        who = '承包商 ZZ3GL25MGJH2 的最终母公司是谁？'
        groups = [{**self.GROUP, 'group': f'G{n}'} for n in range(4)]
        items = open_items(run({'asked': asked(answered(who, {'merged': groups}))}), BUNDLE)
        self.assertEqual(kinds(items), ['merged'] * 3)
        self.assertEqual(items[0], {
            'kind': 'merged', 'from_model': False, 'question': who,
            'ask': f'「{who}」的答案里，“G0”这一组下有 2 个不同的最终母公司（PRRXANJSLS26、ZZ3GL25MGJH2），按同一个算了。它们是同一个吗？',
            'facts': ['1 个承包商落在“G0”这一组里'], 'target': {'tab': 'qa', 'place': 'ask', 'question': who}})

    def test_a_value_missing_from_the_start_object_but_present_elsewhere_is_asked(self):
        question = '框架合同 GS03F102CA 的潜在合同总值是多少？'
        no_data = {'question': question, 'status': 'no_data', 'asked': True, 'query': {'start': 'contract', 'where': []},
                   'evidence': {'filters': [], 'found_elsewhere': [
                       {'type': 'vehicle', 'field': 'piid', 'equals': 'GS03F102CA', 'count': 1, 'linked': 9}]}}
        items = open_items(run({'asked': asked(no_data)}), BUNDLE)
        self.assertEqual(kinds(items), ['found_elsewhere'])
        self.assertEqual(items[0], {
            'kind': 'found_elsewhere', 'from_model': False, 'question': question,
            'ask': f'「{question}」在合同授标里找不到“GS03F102CA”，但母合同里有，9 个合同授标连着它。这道题问的是不是母合同？',
            'facts': ['条件“piid = GS03F102CA”在合同授标里没有一个对象满足', '母合同里有 1 个对象的编号含“GS03F102CA”，其中连着 9 个合同授标'],
            'target': {'tab': 'qa', 'place': 'ask', 'question': question}})

    def test_several_types_and_several_objects_are_all_named(self):
        question = '编号 X1 的合同值是多少？'
        found = [{'type': 'vehicle', 'field': 'piid', 'equals': 'X1', 'count': 2, 'linked': 5},
                 {'type': 'vendor', 'field': 'piid', 'equals': 'X1', 'count': 1, 'linked': 0}]
        no_data = {'question': question, 'status': 'no_data', 'query': {'start': 'contract'}, 'evidence': {'found_elsewhere': found}}
        [item] = open_items(run({'asked': asked(no_data)}), BUNDLE)
        self.assertEqual(item['ask'], f'「{question}」在合同授标里找不到“X1”，但母合同里有 2 个，5 个合同授标连着它；'
                                      '承包商里有，但没有合同授标连着它。这道题问的是不是母合同、承包商？')


class UnlinkedTests(unittest.TestCase):
    FIT = {'relations': [
        {'key': 'spend_contract', 'source': 'spend', 'rows': 1921, 'linked_rows': 613, 'empty_rows': 1308},
        {'key': 'contract_vendor', 'source': 'contracts', 'rows': 365, 'linked_rows': 365, 'empty_rows': 0},
        {'key': 'contract_vehicle', 'source': 'contracts', 'rows': 365, 'linked_rows': 158, 'empty_rows': 207}],
        'orphans': [{'type': 'spend', 'count': 1308, 'examples': ['10071|FY2025P03', '10078|FY2025P03']},
                    {'type': 'contract', 'count': 0, 'examples': []}]}

    def test_each_relation_that_leaves_rows_unlinked_is_asked_with_the_rows_left_over(self):
        items = open_items(run({'data_fit': self.FIT}), BUNDLE)
        self.assertEqual(kinds(items), ['unlinked', 'unlinked'])
        self.assertEqual(items[0], {
            'kind': 'unlinked', 'from_model': False, 'relation': 'spend_contract',
            'ask': '支出行（spend）1,921 行里有 1,308 行没连上“支出行 对应 合同授标”。是这些行本来就没有对应的合同授标，还是数据没导全？',
            'facts': ['没连上任何对象的支出行，例如 10071|FY2025P03、10078|FY2025P03', '其中 1,308 行用来连的编号是空的'],
            'target': {'tab': 'graph', 'relation': 'spend_contract'}})
        self.assertEqual(items[1]['relation'], 'contract_vehicle')
        self.assertEqual(items[1]['ask'], '合同授标（contracts）365 行里有 207 行没连上“合同授标 属于 母合同”。是这些行本来就没有对应的母合同，还是数据没导全？')
        self.assertEqual(items[1]['facts'], ['其中 207 行用来连的编号是空的'])

    def test_a_relation_without_a_label_is_named_by_its_key(self):
        ontology = copy.deepcopy(ONTOLOGY)
        ontology['relations'][0].pop('label')
        fit = {'relations': [self.FIT['relations'][0]], 'orphans': []}
        [item] = open_items(run({'data_fit': fit}, ontology), BUNDLE)
        self.assertIn('“支出行 spend_contract 合同授标”', item['ask'])


    def test_a_relation_judged_wrong_or_with_a_wrong_end_is_not_asked(self):
        decided = copy.deepcopy(DECIDED)
        decided['decisions']['relations']['spend_contract'] = {'verdict': 'wrong'}
        decided['decisions']['types']['vehicle'] = {'verdict': 'wrong'}
        self.assertEqual(open_items(run({'data_fit': self.FIT}, confirmation=decided), BUNDLE), [])


class SameNameTests(unittest.TestCase):
    def test_objects_sharing_a_name_but_not_a_number_are_asked_one_item_per_type(self):
        bundle = padded(60, ('K1', 'Stantec'), ('K2', 'STANTEC '), ('K3', 'Acme'), ('K4', 'Zed'), ('K5', 'zed'), ('K6', 'Zed'))
        [item] = open_items(run(), bundle)
        self.assertEqual(item, {
            'kind': 'same_name', 'from_model': False,
            'ask': '承包商里有 2 组名字相同、编号不同，例如 Stantec（K1 / K2）。它们是同一个承包商的不同主体，还是该合并？',
            'facts': ['Stantec：K1 / K2', 'Zed：K4 / K5 / K6'], 'target': {'tab': 'objects', 'object': 'vendor'}})

    def test_at_most_five_groups_are_listed_but_all_are_counted(self):
        pairs = [(f'{n}A', f'Name{n}') for n in range(7)] + [(f'{n}B', f'name{n}') for n in range(7)]
        [item] = open_items(run(), padded(300, *pairs))
        self.assertTrue(item['ask'].startswith('承包商里有 7 组名字相同'))
        self.assertEqual(len(item['facts']), 5)

    def test_a_type_shown_by_part_of_its_own_identity_is_skipped(self):
        ontology = copy.deepcopy(ONTOLOGY)
        ontology['object_types'].append({'key': 'region', 'label': '区域', 'populated_from': [
            {'source': 'regions', 'identity': {'name': 'name', 'code': 'code'}}], 'attributes': [{'source': 'regions', 'path': 'name'}]})
        bundle = vendors(('K1', 'Acme'))
        bundle['sources']['regions'] = {'records': [{'name': 'North', 'code': '1'}, {'name': 'North', 'code': '2'},
                                                    *({'name': f'R{n}', 'code': f'C{n}'} for n in range(30))]}
        self.assertEqual(open_items(run(ontology=ontology, confirmation={'decisions': {
            'types': {t['key']: {'verdict': 'ok'} for t in ontology['object_types']},
            'relations': DECIDED['decisions']['relations']}}), bundle), [])


    def test_a_name_that_many_objects_share_is_not_the_objects_own_name_and_asks_nothing(self):
        # orders carry the receiver's name: 5 names shared by 10 of 20 orders
        names = ['A', 'A', 'B', 'B', 'C', 'C', 'D', 'D', 'E', 'E', *'FGHIJKLMNO']
        self.assertEqual(open_items(run(), vendors(*((f'K{n}', name) for n, name in enumerate(names)))), [])

    def test_a_tenth_of_the_named_objects_sharing_names_is_still_asked_and_just_over_is_not(self):
        shared = [('K1', 'Zed'), ('K2', 'Zed')]
        [item] = open_items(run(), padded(20, *shared))   # 2 of 20
        self.assertEqual(item['kind'], 'same_name')
        self.assertEqual(open_items(run(), padded(19, *shared)), [])   # 2 of 19

    def test_objects_without_a_name_are_not_counted_among_the_named(self):
        # 2 of 20 objects share a name, but only 15 have one: 2 of 15 is over a tenth
        rows = [('K1', 'Zed'), ('K2', 'zed'), *((f'U{n}', f'Unique {n}') for n in range(13)), *((f'B{n}', '') for n in range(5))]
        self.assertEqual(open_items(run(), vendors(*rows)), [])

    def test_a_type_judged_wrong_is_not_asked(self):
        decided = copy.deepcopy(DECIDED)
        decided['decisions']['types']['vendor'] = {'verdict': 'wrong'}
        self.assertEqual(open_items(run(confirmation=decided), padded(60, ('K1', 'Stantec'), ('K2', 'Stantec'))), [])


class UnstableTests(unittest.TestCase):
    STABILITY = {'runs': 3, 'failed': 0, 'failures': [], 'types': {'spend': 3, 'vendor': 2},
                 'relations': {'spend_contract': 3, 'contract_vendor': 2},
                 'elsewhere': {'types': [{'label': '仓库', 'count': 1}], 'relations': [{'label': '合同动作 — 最终母公司', 'count': 1}]}}

    def test_what_did_not_come_back_every_time_and_what_only_other_runs_found_are_asked(self):
        items = open_items(run({'stability': self.STABILITY}), BUNDLE)
        self.assertEqual(kinds(items), ['unstable'] * 4)
        target = {'tab': 'objects', 'place': 'stability'}
        self.assertEqual(items[0], {
            'kind': 'unstable', 'from_model': False, 'relation': 'contract_vendor',
            'ask': '关系“合同授标 授予 承包商”在 3 次建模里只出现了 2 次。这条关系要保留吗？',
            'facts': ['共建模 3 次，这条关系出现了 2 次'], 'target': target})
        self.assertEqual(items[1]['ask'], '对象“承包商”在 3 次建模里只出现了 2 次。这类对象要保留吗？')
        self.assertNotIn('relation', items[1])
        self.assertEqual(items[2]['ask'], '另外 1 次建模里出现过关系“合同动作 — 最终母公司”，这次的本体里没有。要不要加？')
        self.assertEqual(items[3]['ask'], '另外 1 次建模里出现过对象“仓库”，这次的本体里没有。要不要加？')
        self.assertTrue(all(i['target'] == target for i in items))

    def test_a_run_that_came_back_every_time_asks_nothing(self):
        steady = {'runs': 3, 'types': {'spend': 3}, 'relations': {'spend_contract': 3}, 'elsewhere': {'types': [], 'relations': []}}
        self.assertEqual(open_items(run({'stability': steady}), BUNDLE), [])


class CheckFindingTests(unittest.TestCase):
    FIT = {
        'identity_conflicts': [{'type': 'vendor', 'source': 'vendors', 'identity': 'K1', 'field': 'vendor_name', 'values': ['Acme', 'ACME Inc']}],
        'identity_spellings': [{'type': 'vendor', 'identity': 'K2', 'variants': ['k2', 'K2 ']}],
        'suspected_duplicates': [{'type': 'vendor', 'rule': 'leading_zeros', 'identities': ['00106', '106']}],
        'missing_across_sources': [
            {'type': 'vendor', 'source': 'vendors', 'count': 4, 'examples': ['K1', 'K2', 'K3', 'K4', 'K5']},
            {'type': 'vendor', 'source': 'contracts', 'relation': 'contract_vendor', 'endpoint': 'to', 'fields': ['uei'], 'count': 2, 'examples': ['X1', 'X2']}],
        'identity_risks': [{'type': 'vendor', 'fields': ['vendor_name'], 'reason': '…'}],
        'unused_sources': [{'source': 'notes', 'rows': 12, 'fields': 3}]}

    def test_each_kind_of_finding_becomes_one_item_with_its_count_and_first_three_examples(self):
        items = open_items(run({'data_fit': self.FIT}), BUNDLE)
        self.assertEqual(kinds(items), ['check_finding'] * 6)
        self.assertTrue(all(i['target'] == {'tab': 'check'} and not i['from_model'] for i in items))
        asks = [i['ask'] for i in items]
        self.assertEqual(asks, [
            '有 1 处同一个对象在原表的不同行里取值不一样，例如承包商 K1 的“vendor_name”：Acme / ACME Inc。以哪个为准？',
            '有 1 个对象的编号写法不止一种，系统已按同一个算，例如承包商 K2：“k2” / “K2 ”。这样合并对吗？',
            '有 1 组编号只差前面的 0，目前算成了不同对象，例如承包商：00106 / 106。它们是同一个吗？',
            '有 6 个对象被别的表提到，却不在描述它们的表里，例如承包商在 vendors 表里缺 K1、K2、K3 等 4 个。这些数据能补上吗？',
            '有 1 类对象只靠名称一类的字段识别，例如承包商：只靠“vendor_name”识别。改名或写法一变就会被当成另一个对象，有没有编号可用？',
            '有 1 张上传的表没被本体读取，例如“notes”表：12 行、3 个字段。是漏了还是确实用不上？'])
        self.assertEqual(items[3]['facts'], ['承包商在 vendors 表里缺 K1、K2、K3 等 4 个',
                                             '承包商在 contracts 表里被“授予”引用却不存在：X1、X2，共 2 个'])

    def test_an_object_missing_from_a_table_that_refers_to_it_by_a_relation_judged_wrong_is_not_listed(self):
        for wrong in ({'relations': {'contract_vendor': {'verdict': 'wrong'}}}, {'types': {'contract': {'verdict': 'wrong'}}}):
            with self.subTest(wrong=wrong):
                decisions = copy.deepcopy(DECIDED['decisions'])
                for part, verdicts in wrong.items():
                    decisions[part].update(verdicts)
                [item] = [i for i in open_items(run({'data_fit': self.FIT}, confirmation={'decisions': decisions}), BUNDLE)
                          if '被别的表提到' in i['ask']]
                self.assertTrue(item['ask'].startswith('有 4 个对象被别的表提到'), item['ask'])
                self.assertEqual(item['facts'], ['承包商在 vendors 表里缺 K1、K2、K3 等 4 个'])

    def test_a_finding_lists_at_most_three_examples(self):
        many = {'unused_sources': [{'source': f's{n}', 'rows': n, 'fields': 1} for n in range(5)]}
        [item] = open_items(run({'data_fit': many}), BUNDLE)
        self.assertTrue(item['ask'].startswith('有 5 张上传的表没被本体读取'))
        self.assertEqual(item['facts'], ['“s0”表：0 行、1 个字段', '“s1”表：1 行、1 个字段', '“s2”表：2 行、1 个字段'])

    def test_findings_that_are_empty_ask_nothing(self):
        empty = {k: [] for k in self.FIT}
        self.assertEqual(open_items(run({'data_fit': empty}), BUNDLE), [])


class DataGapTests(unittest.TestCase):
    def test_the_models_own_data_gaps_are_one_item_marked_as_the_models(self):
        gaps = ['财务行缺少稳定的交易主键。', '办公室只有编号和名称。']
        [item] = open_items(run(ontology={**ONTOLOGY, 'data_gaps': gaps}), BUNDLE)
        self.assertEqual(item, {'kind': 'data_gaps', 'from_model': True, 'ask': '模型指出 2 处数据缺口（下面逐条）。客户那边有没有能补上的数据？',
                                'facts': gaps, 'target': {'tab': 'objects', 'place': 'build'}})


class UnansweredTests(unittest.TestCase):
    @staticmethod
    def stuck(question, status, **over):
        return {'question': question, 'status': status, 'asked': True, **over}

    def test_questions_that_could_not_be_answered_are_one_item_with_a_line_each(self):
        items = asked(
            self.stuck('甲', 'query_limit', reason='很长的模型说明', reason_from_model=True),
            self.stuck('乙', 'ontology_gap', reason='很长的模型说明', reason_from_model=True),
            self.stuck('丙', 'ontology_gap', reason='本体里没有对象类型 invoice', query={'start': 'invoice'}),
            self.stuck('丁', 'no_data', reason='数据里没有满足筛选条件的对象'),
            self.stuck('戊', 'no_data', evidence={'found_elsewhere': [{'type': 'vehicle', 'field': 'f', 'equals': 'x', 'count': 1, 'linked': 1}]},
                       query={'start': 'contract'}),
            answered('己', {}))
        out = open_items(run({'asked': items}), BUNDLE)
        self.assertEqual(kinds(out), ['found_elsewhere', 'unanswered'])
        self.assertEqual(out[1], {
            'kind': 'unanswered', 'from_model': True, 'ask': '4 道问过的题现在答不了。这次 POC 要不要答它们？',
            'facts': ['「甲」：查询写不出来（模型的判断）', '「乙」：本体缺回答它要的东西（模型的判断）',
                      '「丙」：本体里没有对象类型 invoice', '「丁」：数据里没有'],
            'target': {'tab': 'qa', 'place': 'ask'}})

    def test_the_item_is_not_from_the_model_when_every_reason_was_written_by_code(self):
        items = asked(self.stuck('甲', 'query_limit', reason='这道题用了 having：查询语言还表达不了', query={'start': 'spend', 'having': {}}),
                      self.stuck('乙', 'no_data'))
        [item] = open_items(run({'asked': items}), BUNDLE)
        self.assertIs(item['from_model'], False)
        self.assertEqual(item['facts'], ['「甲」：这道题用了 having：查询语言还表达不了', '「乙」：数据里没有'])

    def test_a_question_answered_the_second_time_is_no_longer_unanswered(self):
        items = asked(self.stuck('甲', 'query_limit', reason_from_model=True)) + asked(answered('甲', {}))
        self.assertEqual(open_items(run({'asked': items}), BUNDLE), [])

    def test_an_accepted_question_that_nothing_can_answer_keeps_the_origin_of_its_reason(self):
        accepted = {'question': '甲', 'status': 'query_limit', 'reason': '很长的模型说明', 'query': None, 'note': ''}
        evaluation = {'asked': asked(self.stuck('甲', 'query_limit', reason='很长的模型说明', reason_from_model=True)), 'acceptance': {'items': [accepted]}}
        [item] = open_items(run(evaluation), BUNDLE)
        self.assertEqual((item['from_model'], item['facts']), (True, ['「甲」：查询写不出来（模型的判断）']))


class UnansweredOriginTests(unittest.TestCase):
    def test_an_accepted_question_without_a_query_is_the_models_reason_even_when_nothing_else_remembers_it(self):
        accepted = [{'question': '甲', 'status': 'query_limit', 'reason': '很长的模型说明', 'query': None, 'note': ''},
                    {'question': '乙', 'status': 'ontology_gap', 'reason': '很长的模型说明', 'query': None, 'note': ''}]
        [item] = open_items(run({'acceptance': {'items': accepted}}), BUNDLE)
        self.assertIs(item['from_model'], True)
        self.assertEqual(item['facts'], ['「甲」：查询写不出来（模型的判断）', '「乙」：本体缺回答它要的东西（模型的判断）'])

    def test_an_accepted_question_whose_query_exists_keeps_the_reason_code_gave(self):
        accepted = [{'question': '甲', 'status': 'query_limit', 'reason': '这道题用了 having：查询语言还表达不了',
                     'query': {'start': 'spend', 'having': {}}, 'note': ''}]
        [item] = open_items(run({'acceptance': {'items': accepted}}), BUNDLE)
        self.assertIs(item['from_model'], False)
        self.assertEqual(item['facts'], ['「甲」：这道题用了 having：查询语言还表达不了'])


class UnjudgedTests(unittest.TestCase):
    def test_everything_is_unjudged_when_nobody_has_confirmed(self):
        [item] = open_items(run(confirmation=None), BUNDLE)
        self.assertEqual(item, {'kind': 'unjudged', 'from_model': False, 'ask': '4 个对象、3 条关系还没人判过对错。会上逐项过一遍？',
                                'facts': [], 'target': {'tab': 'objects', 'place': 'confirm'}})

    def test_only_what_has_no_verdict_is_counted(self):
        decisions = {'types': {'spend': {'verdict': 'ok'}, 'vendor': {'verdict': 'wrong'}}, 'relations': {'spend_contract': {'verdict': 'ok'}}}
        [item] = open_items(run(confirmation={'decisions': decisions}), BUNDLE)
        self.assertEqual(item['ask'], '2 个对象、2 条关系还没人判过对错。会上逐项过一遍？')

    def test_a_side_with_nothing_left_is_not_mentioned(self):
        decisions = {'types': {t['key']: {'verdict': 'ok'} for t in ONTOLOGY['object_types'][:3]}, 'relations': DECIDED['decisions']['relations']}
        [item] = open_items(run(confirmation={'decisions': decisions}), BUNDLE)
        self.assertEqual(item['ask'], '1 个对象还没人判过对错。会上逐项过一遍？')


class WholeRunTests(unittest.TestCase):
    def test_items_come_in_the_fixed_order_of_their_kinds(self):
        found = {'question': '丙', 'status': 'no_data', 'query': {'start': 'contract'},
                 'evidence': {'found_elsewhere': [{'type': 'vehicle', 'field': 'f', 'equals': 'x', 'count': 1, 'linked': 1}]}}
        stuck = {'question': '丁', 'status': 'query_limit', 'reason': '原因'}
        evaluation = {
            'asked': asked(stuck, found, answered(PAID, {'filters': [ADDED], 'merged': [MergedAndElsewhereTests.GROUP]})),
            'data_fit': {**UnlinkedTests.FIT, 'unused_sources': [{'source': 'notes', 'rows': 1, 'fields': 1}]},
            'stability': UnstableTests.STABILITY}
        bundle = padded(30, ('K1', 'Acme'), ('K2', 'ACME'))
        out = open_items(run(evaluation, ontology={**ONTOLOGY, 'data_gaps': ['缺口']}, confirmation=None), bundle)
        self.assertEqual(set(kinds(out)), set(KINDS))
        self.assertEqual(kinds(out), sorted(kinds(out), key=KINDS.index))

    def test_a_run_that_did_not_pass_verification_has_nothing_to_confirm(self):
        failed = {**ONTOLOGY, 'status': 'rejected', 'data_gaps': ['缺口']}
        self.assertEqual(open_items(run(ontology=failed, confirmation=None), BUNDLE), [])


AT = '2026-10-27T09:00:00+00:00'
EVERYTHING = {
    'asked': asked({'question': '丁', 'status': 'query_limit', 'reason': '原因'},
                   {'question': '丙', 'status': 'no_data', 'query': {'start': 'contract'},
                    'evidence': {'found_elsewhere': [{'type': 'vehicle', 'field': 'f', 'equals': 'x', 'count': 1, 'linked': 1}]}},
                   answered(PAID, {'filters': [ADDED], 'merged': [MergedAndElsewhereTests.GROUP]})),
    'data_fit': {**UnlinkedTests.FIT, 'unused_sources': [{'source': 'notes', 'rows': 1, 'fields': 1}]},
    'stability': UnstableTests.STABILITY}


def everything():
    return open_items(run(EVERYTHING, ontology={**ONTOLOGY, 'data_gaps': ['缺口']}, confirmation=None), padded(30, ('K1', 'Acme'), ('K2', 'ACME')))


class ItemIdTests(unittest.TestCase):
    def test_every_item_has_an_id_made_from_the_thing_itself(self):
        self.assertEqual([i['id'] for i in everything()], [
            f'model_filter:{PAID}|subagency=BUREAU OF RECLAMATION', f'merged:{PAID}|GREENBERRY INDUSTRIAL LLC', 'found_elsewhere:丙',
            'unlinked:spend_contract', 'unlinked:contract_vehicle', 'same_name:vendor',
            'unstable:relation:contract_vendor', 'unstable:type:vendor', 'unstable:new:relations:合同动作 — 最终母公司', 'unstable:new:types:仓库',
            'check_finding:unused_sources', 'data_gaps', 'unanswered', 'unjudged'])

    def test_the_ids_are_the_same_on_the_next_call_and_never_repeat_within_a_list(self):
        first, second = [i['id'] for i in everything()], [i['id'] for i in everything()]
        self.assertEqual(first, second)
        self.assertEqual(len(set(first)), len(first))

    def test_each_kind_of_finding_has_its_own_id(self):
        fit = {k: v for k, v in CheckFindingTests.FIT.items()}
        self.assertEqual([i['id'] for i in open_items(run({'data_fit': fit}), BUNDLE)],
                         [f'check_finding:{k}' for k in ('identity_conflicts', 'identity_spellings', 'suspected_duplicates',
                                                          'missing_across_sources', 'identity_risks', 'unused_sources')])

    def test_an_unlinked_item_names_the_complete_cell_of_the_end_that_may_be_missing(self):
        items = [i for i in everything() if i['kind'] == 'unlinked']
        # spend rows that find no contract: the contracts may not all be there; contract rows that find no vehicle: the vehicles
        self.assertEqual([(i['relation'], i['complete_id']) for i in items],
                         [('spend_contract', 'complete:contracts|award_key'), ('contract_vehicle', 'complete:vehicles|vehicle_key')])
        self.assertTrue(all('complete_id' not in i for i in everything() if i['kind'] != 'unlinked'))


class CardBlankTests(unittest.TestCase):
    def card(self, cells=None, ontology=ONTOLOGY, bundle=BUNDLE):
        return ontology_card.build_card(ontology, bundle, cells)

    @staticmethod
    def cell_ids(card):
        return [*(t['grain']['id'] for t in card['tables']), *(d['id'] for t in card['tables'] for d in t['dates']),
                *(a['id'] for t in card['tables'] for a in t['amounts']), *(o['id'] for o in card['objects'])]

    @staticmethod
    def blank_item(items):
        return next((i for i in items if i['kind'] == 'card_blank'), None)

    def test_a_card_with_cells_nobody_has_answered_is_one_item_with_a_line_per_table(self):
        self.assertEqual(open_items(run(), BUNDLE, card=self.card()), [{
            'kind': 'card_blank', 'id': 'card_blank', 'from_model': False,
            'ask': '口径卡还有 8 格没说清（4 张表）：数值列能不能相加、日期列是什么时间、一行是什么、对象全不全。会上逐张过一遍？',
            'facts': ['spend：2 格', 'contracts：2 格', 'vehicles：2 格', 'vendors：2 格'], 'target': {'tab': 'card'}}])

    def test_the_columns_waiting_for_an_answer_are_named_up_to_five(self):
        ledger = {**LEDGER_ONTOLOGY, 'status': 'auto_built_verified', 'data_gaps': []}
        bundle = ledger_bundle()
        item = self.blank_item(open_items(run(ontology=ledger, confirmation=None), bundle, card=self.card(ontology=ledger, bundle=bundle)))
        self.assertEqual(item['facts'], ['ledger：7 格（paid_on、booked_at、paid、running、ytd）', 'vendors：2 格', 'notes：1 格'])
        wide = ledger_bundle([{**r, **{f'x{n}': '1' for n in range(3)}} for r in bundle['sources']['ledger']['records']])
        item = self.blank_item(open_items(run(ontology=ledger, confirmation=None), wide, card=self.card(ontology=ledger, bundle=wide)))
        self.assertEqual(item['facts'][0], 'ledger：10 格（paid_on、booked_at、paid、running、ytd等）')

    def test_the_object_cell_is_counted_under_the_first_table_that_object_is_read_from(self):
        ontology = copy.deepcopy(ONTOLOGY)
        ontology['object_types'][3]['populated_from'].append({'source': 'spend', 'identity': {'uei': 'uei'}})
        item = self.blank_item(open_items(run(ontology=ontology), BUNDLE, card=self.card(ontology=ontology)))
        self.assertEqual(item['facts'], ['spend：2 格', 'contracts：2 格', 'vehicles：2 格', 'vendors：2 格'])

    def test_answered_cells_come_off_the_count_and_a_table_filled_in_drops_out(self):
        card = self.card()
        ids = self.cell_ids(card)
        answer = {'value': 'full', 'note': '', 'by': '张三', 'basis': '', 'at': AT}
        item = self.blank_item(open_items(run(), BUNDLE, card=self.card({'grain:spend': answer, 'complete:spend|row_id': answer, 'grain:vendors': answer})))
        self.assertEqual(item['facts'], ['contracts：2 格', 'vehicles：2 格', 'vendors：1 格'])
        self.assertTrue(item['ask'].startswith('口径卡还有 5 格没说清（3 张表）'))
        self.assertIn('complete:spend|row_id', ids)

    def test_unsure_still_counts_and_the_item_is_gone_when_every_cell_is_answered(self):
        ids = self.cell_ids(self.card())
        unsure = self.card({i: {'value': 'unsure', 'note': '', 'by': '张三', 'basis': '', 'at': AT} for i in ids})
        self.assertEqual(self.blank_item(open_items(run(), BUNDLE, card=unsure))['ask'][:12], '口径卡还有 8 格没说清')
        full = self.card({i: {'value': 'full', 'note': '', 'by': '张三', 'basis': '', 'at': AT} for i in ids})
        self.assertEqual(open_items(run(), BUNDLE, card=full), [])

    def test_it_sits_after_the_check_findings_and_before_the_data_gaps(self):
        evaluation = {'data_fit': {'unused_sources': [{'source': 'notes', 'rows': 1, 'fields': 1}]}}
        items = open_items(run(evaluation, ontology={**ONTOLOGY, 'data_gaps': ['缺口']}, confirmation=None), BUNDLE, card=self.card())
        self.assertEqual(kinds(items), ['check_finding', 'card_blank', 'data_gaps', 'unjudged'])

    def test_without_a_card_there_is_nothing_to_say(self):
        self.assertEqual(open_items(run(), BUNDLE), [])


class AnswerTests(unittest.TestCase):
    RUN = run({'data_fit': UnlinkedTests.FIT}, ontology={**ONTOLOGY, 'data_gaps': ['缺口']}, confirmation=None)
    LISTED = open_items(RUN, BUNDLE)   # spend_contract, contract_vehicle, data_gaps, unjudged

    def check(self, *items, by='张三'):
        return check_answers(self.LISTED, list(items), by, AT)

    def test_a_choice_and_a_few_words_are_kept_with_the_ask_they_answered(self):
        got = self.check({'id': 'unlinked:spend_contract', 'choice': 'incomplete', 'text': ' 合同授标只导了 FY25Q1 的 ', 'basis': '10-27 会议'})
        self.assertEqual(got, {'unlinked:spend_contract': {
            'choice': 'incomplete', 'text': '合同授标只导了 FY25Q1 的', 'by': '张三', 'basis': '10-27 会议', 'at': AT, 'asked': self.LISTED[0]['ask']}})

    def test_a_choice_alone_is_enough_and_so_are_words_alone_where_there_is_no_choice(self):
        got = self.check({'id': 'unlinked:contract_vehicle', 'choice': 'expected'}, {'id': 'data_gaps', 'text': '客户下周补'})
        self.assertEqual((got['unlinked:contract_vehicle']['choice'], got['unlinked:contract_vehicle']['text']), ('expected', ''))
        self.assertEqual((got['data_gaps']['choice'], got['data_gaps']['text']), (None, '客户下周补'))

    def test_what_is_wrong_is_named(self):
        for item, said_so in (
                ({'id': 'unlinked:gone', 'choice': 'expected'}, '这件事已经不在清单上了'),
                ({'id': 'unjudged', 'text': '好'}, '逐项判对错'),
                ({'id': 'card_blank', 'text': '好'}, '不在清单上'),   # this list has no card item
                ({'id': 'unlinked:spend_contract', 'choice': 'same'}, '只能'),
                ({'id': 'data_gaps', 'choice': 'expected', 'text': '好'}, '只能'),
                ({'id': 'unlinked:spend_contract'}, '选一个'),
                ({'id': 'data_gaps', 'text': '  '}, '选一个'),
                ({'id': 'data_gaps', 'text': 'x' * 301}, '最多'),
                ({'id': 'data_gaps', 'text': '好', 'basis': 'x' * 201}, '出处'),
                ({'text': '好'}, '不在清单上'),
                ('not an object', '写法')):
            with self.subTest(item=item), self.assertRaises(ontology_card.CardError) as caught:
                self.check({'id': 'data_gaps', 'text': '好'}, item)
            self.assertIn(said_so, str(caught.exception))

    def test_a_card_blank_or_a_model_filter_cannot_be_closed_by_an_answer(self):
        listed = [{'kind': 'card_blank', 'id': 'card_blank', 'ask': 'a'}, {'kind': 'model_filter', 'id': 'model_filter:q|f=1', 'ask': 'b'}]
        for item_id, said_so in (('card_blank', '把口径卡填完'), ('model_filter:q|f=1', '去掉条件')):
            with self.subTest(item_id=item_id), self.assertRaises(ontology_card.CardError) as caught:
                check_answers(listed, [{'id': item_id, 'text': '好'}], '张三', AT)
            self.assertIn(said_so, str(caught.exception))

    def test_answered_items_move_to_their_own_list_with_the_answer_and_its_words(self):
        stored = {'unlinked:spend_contract': {'choice': 'incomplete', 'text': '只导了一部分', 'by': '张三', 'basis': '会议', 'at': AT, 'asked': '当时的问法'},
                  'data_gaps': {'choice': None, 'text': '客户下周补', 'by': '李四', 'basis': '', 'at': AT, 'asked': '缺口怎么办？'}}
        listed, answered = split_answers(self.LISTED, stored)
        self.assertEqual([i['id'] for i in listed], ['unlinked:contract_vehicle', 'unjudged'])
        self.assertEqual([i['id'] for i in answered], ['unlinked:spend_contract', 'data_gaps'])
        self.assertEqual(answered[0]['answer'], {**stored['unlinked:spend_contract'], 'says': '数据没导全'})
        self.assertEqual(answered[0]['ask'], self.LISTED[0]['ask'])   # the item as it is now; the ask it answered is inside the answer
        self.assertEqual(answered[1]['answer'], stored['data_gaps'])    # no choice, nothing to say about it

    def test_an_answer_whose_item_was_not_listed_this_time_is_in_neither_list(self):
        stored = {'unlinked:long_gone': {'choice': 'expected', 'text': '', 'by': '张三', 'basis': '', 'at': AT, 'asked': 'x'}}
        self.assertEqual(split_answers(self.LISTED, stored), (self.LISTED, []))

    def test_every_choice_has_its_words(self):
        words = {'expected': '本来就没有对应，属正常', 'incomplete': '数据没导全', 'distinct': '是不同的对象', 'same': '是同一个'}
        for choice, said_so in words.items():
            _, answered = split_answers(self.LISTED[:1], {'unlinked:spend_contract': {'choice': choice, 'text': '', 'by': '张三', 'basis': '', 'at': AT, 'asked': 'x'}})
            self.assertEqual(answered[0]['answer']['says'], said_so)

    def test_the_choices_each_kind_takes(self):
        table = {'unlinked': ('expected', 'incomplete'), 'same_name': ('distinct', 'same'), 'merged': ('distinct', 'same')}
        for kind, choices in table.items():
            listed = [{'kind': kind, 'id': f'{kind}:x', 'ask': 'a'}]
            for choice in (*choices, None):
                with self.subTest(kind=kind, choice=choice):
                    got = check_answers(listed, [{'id': f'{kind}:x', 'choice': choice, 'text': '好'}], '张三', AT)
                    self.assertEqual(got[f'{kind}:x']['choice'], choice)
        for kind in ('found_elsewhere', 'unstable', 'check_finding', 'data_gaps', 'unanswered'):
            listed = [{'kind': kind, 'id': f'{kind}:x', 'ask': 'a'}]
            with self.subTest(kind=kind), self.assertRaises(ontology_card.CardError):
                check_answers(listed, [{'id': f'{kind}:x', 'choice': 'same', 'text': '好'}], '张三', AT)
            self.assertIn(f'{kind}:x', check_answers(listed, [{'id': f'{kind}:x', 'text': '好'}], '张三', AT))


if __name__ == '__main__':
    unittest.main()
