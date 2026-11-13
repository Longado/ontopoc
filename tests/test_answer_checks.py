"""An answer checks its own definitions: a question that names a confirmed definition the query did not apply is refused and says
which; a filter that found nothing in a table damaged upstream says so instead of "no data". The numbers are the planted fixtures':
144 of 160 orders are not cancelled; 客户 repeats KH012; the rest are counted in the tests."""
import json
import unittest

from ontology_poc_generator.answer_checks import definition_catalog, definition_check, filter_conditions, refusal, upstream_problems, with_upstream
from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
from tests.test_workspace_store import PLANTED_DRAFT

MEANINGS = {'订单.状态码': {'labels': {'0': '进行中', '1': '已交付', '2': '已取消'}}}
CANCELLED = {'start': 'order', 'where': [{'field': '订单.状态码', 'equals': '已取消'}], 'group_by': None}
ALL_ORDERS = {'start': 'order', 'where': [], 'group_by': None}
view = lambda **kw: {'name': '有效订单', 'kind': 'filter', 'source': '订单', 'state': 'confirmed', 'why': None, 'from': 'x',
                     'definition': {'kind': 'filter', 'base': '订单', 'column': '状态码', 'op': 'is_not', 'label': '已取消'}, **kw}
def said(direction):
    """The model's word: a meaning by its catalog id (column and label), a view by its name."""
    return lambda name, field='订单.状态码': {'id': name if name == '有效订单' else f'{field}={name}', 'direction': direction, 'basis': 'b'}
inc, exc, men = said('include'), said('exclude'), said('mention')


class MeaningTests(unittest.TestCase):
    """The model says which definitions a question uses and in which direction; code checks the query against that. The tests
    give the model's word for each phrasing the word lists used to get wrong."""
    def check(self, question, query, used, views=(), meanings=MEANINGS, **kw):
        return definition_check(question, query, PLANTED_DRAFT, list(views), meanings, used, **kw)

    def test_an_included_meaning_needs_a_query_that_filters_by_it(self):
        for question in ('有多少订单已取消？', '有没有已取消的订单？', '已取消的订单有多少？'):
            self.assertEqual(self.check(question, CANCELLED, [inc('已取消')])['unmet'], [], question)
        self.assertEqual(self.check('有多少订单已取消？', {**CANCELLED, 'where': [{'field': '状态码', 'equals': '2'}]}, [inc('已取消')])['unmet'], [])   # the code is as good as its meaning
        self.assertEqual(self.check('各状态里已取消的占多少？', {'start': 'order', 'group_by': [{'via': [], 'field': '订单.状态码'}]}, [inc('已取消')])['unmet'], [])
        [unmet] = self.check('有多少订单已取消？', ALL_ORDERS, [inc('已取消')])['unmet']
        self.assertEqual((unmet['definition'], unmet['kind']), ('已取消', 'meaning'))
        self.assertIn('2 = 已取消', unmet['why'])
        wrong = self.check('有多少订单已取消？', {**CANCELLED, 'where': [{'field': '订单.状态码', 'equals': '已交付'}]}, [inc('已取消')])
        self.assertIn('已取消', [u['definition'] for u in wrong['unmet']])        # a filter on the same column for another meaning is not this one (and that other meaning the model did not list)

    def test_an_excluded_meaning_is_refused_whatever_words_said_so(self):
        for question in ('已取消的不算，有多少订单？', '除已取消外有多少订单？', '订单里把已取消的去掉还有多少？', '不含“已取消”的订单有多少？'):
            for query in (ALL_ORDERS, CANCELLED):   # a filter on equals 2 would count the cancelled ones: the opposite
                [unmet] = self.check(question, query, [exc('已取消')])['unmet']
                self.assertEqual((unmet['definition'], unmet['kind']), ('已取消', 'meaning'), question)
                self.assertIn('排除', unmet['why'])

    def test_an_excluded_meaning_reads_the_view_a_person_made_that_leaves_it_out(self):
        valid = view()
        checked = self.check('已取消的不算，有多少订单？', ALL_ORDERS, [exc('已取消')], [valid])
        self.assertEqual((checked['unmet'], checked['apply']), ([], [valid]))
        self.assertEqual(checked['understood'], [{'definition': '已取消', 'direction': 'exclude', 'how': '读视图 有效订单'}])
        by_status = {'start': 'order', 'where': [], 'group_by': [{'via': [], 'field': '订单.状态码'}]}
        self.assertEqual(self.check('已取消的不算，各状态有多少订单？', by_status, [exc('已取消')], [valid])['apply'], [valid])   # grouped by the column: the view still leaves them out
        [still] = self.check('已取消的不算，有多少订单？', CANCELLED, [exc('已取消')], [valid])['unmet']     # the query also counts the cancelled ones: contradicts
        self.assertIn('「有效订单」', still['why'])

    def test_an_excluded_meaning_on_an_object_the_query_never_reads_is_refused_not_dropped(self):
        [unmet] = self.check('已取消的不算，有多少工单？', {'start': 'ticket', 'group_by': None}, [exc('已取消')], [view()])['unmet']
        self.assertEqual(unmet['definition'], '已取消')
        self.assertIn('没有读', unmet['why'])

    def test_every_answer_says_how_the_models_word_was_carried_out(self):
        checked = self.check('有没有已取消的订单？', CANCELLED, [inc('已取消')])
        self.assertEqual(checked['understood'], [{'definition': '已取消', 'direction': 'include', 'how': '状态码 = 2'}])
        self.assertEqual(self.check('订单有多少？', ALL_ORDERS, [])['understood'], [])

    def test_a_label_of_one_or_two_characters_is_checked_once_the_model_says_it_is_used(self):
        flags = {'订单.状态码': {'labels': {'2': '作废'}}}
        [unmet] = self.check('有多少订单作废了？', ALL_ORDERS, [inc('作废')], meanings=flags)['unmet']
        self.assertEqual(unmet['definition'], '作废')
        self.assertEqual(self.check('有多少订单作废了？', {**ALL_ORDERS, 'where': [{'field': '状态码', 'equals': '2'}]}, [inc('作废')], meanings=flags)['unmet'], [])
        self.assertEqual(self.check('有多少订单作废了？', ALL_ORDERS, [], meanings=flags), {'unmet': [], 'apply': [], 'understood': []})   # not said by the model, short, no column named, no filter: nothing to go on

    def test_a_definition_the_model_did_not_list_is_refused_when_the_question_says_it_or_the_query_filters_by_it(self):
        [said] = self.check('有多少订单已取消？', ALL_ORDERS, [])['unmet']
        self.assertIn('没有说明它是怎么用的', said['why'])
        [filtered] = self.check('不含已取消的订单有多少？', CANCELLED, [])['unmet']        # the direction cannot be checked: not flagged, refused
        self.assertIn('没有说明问题是要包含还是排除', filtered['why'])
        [coded] = self.check('状态码为 2 的订单有多少？', {**ALL_ORDERS, 'where': [{'field': '状态码', 'equals': '2'}]}, None)['unmet']
        self.assertEqual(coded['definition'], '已取消')
        flags = {'订单.状态码': {'labels': {'1': '是'}}}
        self.assertEqual(self.check('订单有多少是上海的？', ALL_ORDERS, [], meanings=flags)['unmet'], [])    # one character, column not named, no filter
        self.assertEqual(len(self.check('状态码是的订单有多少？', ALL_ORDERS, [], meanings=flags)['unmet']), 1)    # column named

    def test_a_definition_the_model_was_never_told_of_is_not_held_against_it(self):
        asked_before = self.check('有多少订单已取消？', CANCELLED, None, told=[])           # confirmed after the question was written
        self.assertEqual((asked_before['unmet'], asked_before['understood']), ([], []))
        self.assertEqual(len(self.check('有多少订单已取消？', CANCELLED, None, told=['订单.状态码=已取消'])['unmet']), 1)
        self.assertEqual(self.check('已取消的订单', CANCELLED, [inc('已取消')], told=[])['unmet'], [])      # what it did declare is still checked

    def test_a_label_of_letters_must_stand_apart_from_other_letters(self):
        grades = {'订单.状态码': {'labels': {'7': 'VIP'}}}
        self.assertEqual(self.check('订单有多少个 VIPS 渠道？', ALL_ORDERS, [], meanings=grades)['unmet'], [])
        self.assertEqual(len(self.check('订单里 VIP 的有多少？', ALL_ORDERS, [], meanings=grades)['unmet']), 1)

    def test_a_malformed_or_unknown_definitions_used_is_ignored(self):
        for used in (None, 'x', [None, {'id': 3}, {'id': '订单.状态码=已取消', 'direction': 'sideways'}]):
            self.assertEqual(self.check('订单有多少？', ALL_ORDERS, used), {'unmet': [], 'apply': [], 'understood': []}, used)
        invented = [{'id': '不存在', 'direction': 'include', 'basis': 'b'}]
        self.assertEqual(self.check('订单有多少？', ALL_ORDERS, invented, meanings=None), {'unmet': [], 'apply': [], 'understood': []})   # nothing confirmed: the model was told no names

    def test_a_name_that_is_in_no_catalog_entry_is_said_so_and_not_blamed_on_silence(self):
        synonym = [{'id': '取消', 'direction': 'exclude', 'basis': 'b'}]
        checked = self.check('不含已取消的订单有多少？', ALL_ORDERS, synonym)
        [unmet] = checked['unmet']
        self.assertEqual((unmet['definition'], unmet['kind']), ('取消', 'unknown'))
        self.assertIn('模型写的定义名对不上', unmet['why'])
        self.assertNotIn('没有说明', unmet['why'])
        self.assertEqual(checked['understood'], [{'definition': '取消', 'direction': 'exclude', 'how': '定义名对不上'}])
        bare = [{'id': '已取消', 'direction': 'include', 'basis': 'b'}]   # the label alone is not an id either
        self.assertEqual(self.check('有多少订单已取消？', CANCELLED, bare)['unmet'][0]['kind'], 'unknown')
        [mentioned] = self.check('订单有多少？', ALL_ORDERS, [{'id': '取消', 'direction': 'mention', 'basis': 'b'}])['unmet']   # a mention names something too
        self.assertEqual(mentioned['kind'], 'unknown')

    def test_an_item_stored_with_a_label_in_place_of_an_id_still_reads_as_that_label(self):
        old = [{'name': '已取消', 'direction': 'include', 'basis': 'b'}]
        self.assertEqual(self.check('有多少订单已取消？', CANCELLED, old)['unmet'], [])
        self.assertEqual(len(self.check('有多少订单已取消？', ALL_ORDERS, old)['unmet']), 1)

    def test_the_same_label_in_another_column_is_another_definition(self):
        both = {**MEANINGS, '售后工单.处理状态': {'labels': {'9': '已取消'}}}
        valid = view()
        checked = self.check('已取消的不算，有多少订单？', ALL_ORDERS, [exc('已取消')], [valid], meanings=both)
        self.assertEqual((checked['unmet'], checked['apply']), ([], [valid]))     # the tickets' 已取消 is not read by a query about orders
        # a filter on a column of another table that is also called 状态码 is not a use of the orders' 已取消
        other = {**ALL_ORDERS, 'where': [{'field': '售后工单.状态码', 'equals': '2'}]}
        [unmet] = self.check('有多少订单已取消？', other, [inc('已取消')])['unmet']
        self.assertIn('没有按它筛选', unmet['why'])
        ticket = {'start': 'ticket', 'where': [{'field': '售后工单.处理状态', 'equals': '9'}], 'group_by': None}
        self.assertEqual(self.check('已取消的工单有多少？', ticket, [inc('已取消', '售后工单.处理状态')], meanings=both)['unmet'], [])
        # and the model that names only the orders' one is not refused for the tickets' one it also read nothing of
        self.assertEqual(self.check('已取消的订单有多少？', CANCELLED, [inc('已取消')], meanings=both)['unmet'], [])

    def test_a_definition_that_is_only_mentioned_selects_no_rows(self):
        rate = {'start': 'order', 'share': {'field': '订单.状态码', 'equals': '2'}, 'group_by': None}
        checked = self.check('订单的已取消率是多少？', rate, [men('已取消')])
        self.assertEqual(checked['unmet'], [])
        self.assertEqual(checked['understood'][0]['direction'], 'mention')
        by_status = {'start': 'order', 'where': [], 'group_by': [{'via': [], 'field': '订单.状态码'}]}
        self.assertEqual(self.check('各状态有多少订单，比如已取消的？', by_status, [men('已取消')])['unmet'], [])     # a dimension on the column shows it
        [selected] = self.check('订单有多少，例如已取消的？', CANCELLED, [men('已取消')])['unmet']   # a filter that picks rows is a use, not a mention
        self.assertIn('只是提到', selected['why'])
        self.assertEqual(self.check('有效订单怎么定义的？', ALL_ORDERS, [men('有效订单')], [view()])['apply'], [])

    def test_a_mention_the_query_does_not_use_is_refused_and_says_so(self):
        checked = self.check('不含已取消的订单有多少？', ALL_ORDERS, [men('已取消')])      # the model called an exclusion a mention: 160 would be said as if it were 144
        [unmet] = checked['unmet']
        self.assertEqual(unmet['definition'], '已取消')
        self.assertIn('只是提到', unmet['why'])
        self.assertEqual(checked['understood'], [{'definition': '已取消', 'direction': 'mention', 'how': '只是提到却没有用到它，没法核对'}])
        delivered = {'start': 'order', 'measure': {'field': '订单.交付天数', 'op': 'average'}, 'where': [], 'group_by': None}
        self.assertEqual(len(self.check('已交付订单的平均交付天数？', delivered, [men('已交付')])['unmet']), 1)   # the column of the word is not in the query
        [elsewhere] = self.check('已取消的工单有多少？', {'start': 'ticket', 'where': [], 'group_by': None}, [men('已取消')])['unmet']
        self.assertIn('没有读', elsewhere['why'])
        [view_unread] = self.check('有效订单怎么定义的？', {'start': 'ticket', 'where': [], 'group_by': None}, [men('有效订单')], [view()])['unmet']
        self.assertEqual(view_unread['kind'], 'view')

    def test_a_refusal_for_silence_says_how_it_was_read_too(self):
        checked = self.check('有多少订单已取消？', ALL_ORDERS, [])
        self.assertEqual(len(checked['unmet']), 1)
        self.assertEqual(checked['understood'], [{'definition': '已取消', 'direction': 'unsaid', 'how': '出题员没有说明它是怎么用的'}])

    def test_a_query_the_language_cannot_read_is_left_to_say_so(self):
        listed = {'start': 'order', 'where': [{'field': '订单.状态码', 'equals': ['2', '0']}], 'group_by': None}
        self.assertEqual(self.check('有多少订单已取消？', listed, [inc('已取消')]), {'unmet': [], 'apply': [], 'understood': []})

    def test_a_meaning_of_a_table_the_query_does_not_read_is_not_this_questions_business(self):
        self.assertEqual(self.check('产品已取消的有几个？', {'start': 'product', 'where': [], 'group_by': None}, [inc('已取消')])['unmet'], [])

    def test_the_refusal_says_which_definition_and_gives_no_number_once(self):
        answer = refusal(self.check('已取消的不算有多少订单？', ALL_ORDERS, [exc('已取消')])['unmet'])
        self.assertEqual(answer['status'], 'definition_unmet')
        self.assertIn('问题里提到「已取消」', answer['reason'])
        self.assertEqual(answer['reason'].count('没有给'), 1)
        self.assertNotIn('answer', answer)


class ViewTests(unittest.TestCase):
    def check(self, question, views, used, query=None):
        return definition_check(question, query or ALL_ORDERS, PLANTED_DRAFT, views, None, used)

    def test_a_view_the_model_says_is_used_is_applied(self):
        v = view()
        self.assertEqual(self.check('有效订单一共多少金额？', [v], [inc('有效订单')]), {'unmet': [], 'apply': [v], 'understood': [{'definition': '有效订单', 'direction': 'include', 'how': '读视图 有效订单'}]})
        self.assertEqual(self.check('订单一共多少金额？', [v], []), {'unmet': [], 'apply': [], 'understood': []})
        own = view(name='订单', definition=None, kind='labels')
        self.assertEqual(self.check('订单一共多少金额？', [own], []), {'unmet': [], 'apply': [], 'understood': []})   # a table's own view is not something a question names

    def test_a_view_the_question_leaves_out_or_the_model_did_not_list_is_not_applied(self):
        [excluded] = self.check('不是有效订单的订单有多少？', [view()], [exc('有效订单')])['unmet']
        self.assertEqual((excluded['definition'], excluded['kind']), ('有效订单', 'view'))
        self.assertIn('排除', excluded['why'])
        [unlisted] = self.check('有效订单有多少？', [view()], [])['unmet']
        self.assertIn('没有说明', unlisted['why'])

    def test_a_view_that_cannot_be_applied_is_a_refusal_naming_it_and_why(self):
        [gone] = self.check('有效订单有多少？', [view(state='unavailable', why='「已取消」现在不是已确认的含义')], [inc('有效订单')])['unmet']
        self.assertEqual((gone['definition'], gone['kind']), ('有效订单', 'view'))
        self.assertIn('已取消', gone['why'])
        [elsewhere] = self.check('有效订单有多少工单？', [view()], [inc('有效订单')], {'start': 'ticket', 'group_by': None})['unmet']
        self.assertIn('没有读这张表', elsewhere['why'])


class CatalogTests(unittest.TestCase):
    def test_the_model_is_told_each_meaning_and_each_view_a_person_named(self):
        told = definition_catalog(MEANINGS, [view(**{'from': '你定义的：订单.状态码 不是「已取消」的行'}), view(name='订单', definition=None)])
        self.assertEqual([(d['name'], d['kind']) for d in told], [('已交付', 'meaning'), ('已取消', 'meaning'), ('进行中', 'meaning'), ('有效订单', 'view')])
        self.assertEqual([d['id'] for d in told], ['订单.状态码=已交付', '订单.状态码=已取消', '订单.状态码=进行中', '有效订单'])
        self.assertIn('2 = 已取消', told[1]['means'])


class UpstreamTests(unittest.TestCase):
    CHECKS = {'tables': [{'dataset': '客户', 'status': 'ok', 'rows_in': 33, 'rows_stored': 31, 'dropped': {'blank': 1, 'title': 1}},
                         {'dataset': '库存快照', 'status': 'error', 'error': '读到 72 行，只存入 71 行', 'rows_in': 72, 'dropped': {}},
                         {'dataset': '订单', 'status': 'ok', 'rows_in': 160, 'rows_stored': 160, 'dropped': {}}],
              'keys': [{'object_type': 'customer', 'dataset': '客户', 'check_type': 'key_unique', 'status': 'failed', 'violations': 1, 'null_key_rows': 2, 'key_columns': ['客户编号']},
                       {'object_type': 'order', 'dataset': '订单', 'check_type': 'key_unique', 'status': 'passed', 'violations': 0, 'null_key_rows': 0, 'key_columns': ['订单号']}]}
    RECORDS = {'客户': [{'客户编号': 'KH001', '城市': '上海'}, {'客户编号': 'KH012', '城市': '合肥'}, {'客户编号': 'KH012', '城市': '苏州'},
                        {'客户编号': '', '城市': '南京'}, {'客户编号': None, '城市': '杭州'}],
               '订单': [], '库存快照': []}

    def said(self, city, rules=None, table='客户'):
        return upstream_problems(self.CHECKS, {table: [('城市', {city})] if table == '客户' else []}, rules or {}, self.RECORDS)

    def test_only_the_damaged_rows_the_filter_could_be_asking_for_are_said(self):
        for city in ('火星', '上海'):                       # no repeated or empty-key row lives there
            self.assertEqual(self.said(city), [], city)
        [repeated] = self.said('合肥')
        self.assertIn('1 行是重复编号，还没有定怎么算，其中 1 行符合这次的筛选条件', repeated)
        self.assertEqual(len(self.said('苏州')), 1)
        [empty] = self.said('南京')
        self.assertIn('1 行的编号是空的且符合这次的筛选条件', empty)

    def test_a_filter_on_a_column_of_another_table_or_a_table_that_could_not_be_stored(self):
        self.assertEqual(upstream_problems(self.CHECKS, {'订单': [('订单号', {'x'})]}, {}, self.RECORDS), [])
        [lost] = upstream_problems(self.CHECKS, {'库存快照': [('产品', {'x'})]}, {}, self.RECORDS)
        self.assertIn('没能存进工作区', lost)           # which row did not go in is unknown: reported whatever the filter says

    def test_a_repeated_key_a_person_decided_about_is_theirs_and_not_reported_but_empty_keys_still_are(self):
        self.assertEqual(self.said('合肥', {'customer.客户': {'rule': 'keep_both'}}), [])
        self.assertEqual(len(self.said('南京', {'customer.客户': {'rule': 'keep_both'}})), 1)

    def test_no_data_from_a_damaged_table_says_so_and_an_answer_is_left_alone(self):
        no_data = {'status': 'no_data', 'reason': '数据里没有满足筛选条件的对象', 'path': 'p'}
        said = with_upstream(no_data, ['「客户」…'])
        self.assertEqual((said['status'], said['path'], said['upstream']), ('rows_lost', 'p', ['「客户」…']))
        self.assertIn('不能当成“数据里真的没有”', said['reason'])
        self.assertEqual(with_upstream(no_data, []), no_data)
        answered = {'status': 'answered', 'answer': {'total': 3}}
        self.assertEqual(with_upstream(answered, ['x']), answered)

    def test_the_filters_become_the_values_each_table_column_accepts(self):
        self.assertEqual(filter_conditions(PLANTED_DRAFT, {'start': 'customer', 'where': [{'field': '客户.城市', 'equals': 'x'}]}, None), {'客户': [('城市', {'X'})]})
        meanings = {'订单.状态码': {'labels': {'2': '已取消', '3': '已取消'}}}
        self.assertEqual(filter_conditions(PLANTED_DRAFT, {'start': 'order', 'where': [{'field': '状态码', 'equals': '已取消'}]}, meanings), {'订单': [('状态码', {'2', '3'})]})
        self.assertEqual(filter_conditions(PLANTED_DRAFT, {'start': 'order', 'where': []}, None), {})



class ChooseRowsTests(unittest.TestCase):
    def test_an_order_a_view_leaves_out_of_the_orders_table_is_left_out_of_the_tables_that_only_mention_it(self):
        from ontology_poc_generator.answer_checks import choose_rows
        from tests.test_workspace_store import planted_bundle
        bundle = planted_bundle()
        orders = bundle['sources']['订单']['records']
        cancelled = {r['订单号'] for r in orders if r['状态码'] == '2'}
        kept = {i for i, r in enumerate(orders, 1) if r['订单号'] not in cancelled}
        chosen = choose_rows(PLANTED_DRAFT, bundle, {'订单': kept})
        self.assertEqual(len(chosen['订单']), 144)
        commitments, tickets = bundle['sources']['订单承诺']['records'], bundle['sources']['售后工单']['records']
        self.assertEqual(len(chosen['订单承诺']), len([r for r in commitments if r['订单号'] not in cancelled]))
        self.assertLess(len(chosen['订单承诺']), len(commitments))                          # 4 cancelled orders have commitments
        self.assertEqual(len(chosen['售后工单']), len([r for r in tickets if r['订单号'] not in cancelled]))
        self.assertNotIn('客户', chosen)                                                    # tables of other objects keep every row


class AskModel:
    """The planted draft; and, for a question asked, what that question is given in `queries`: a query, or (query, the
    definitions the model says it uses). `requests` keeps what the question writer was sent."""
    def __init__(self, queries):
        from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
        self.queries, self.questions, self.requests = queries, QUESTION_SYSTEM_PROMPT, []

    def complete_json(self, *, system_prompt, user_prompt):
        from ontology_poc_generator.recognition import ModelCompletion
        if system_prompt == self.questions:
            request = json.loads(user_prompt)
            self.requests.append(request)
            asked = request.get('asked')
            query, used = self.queries[asked] if isinstance(self.queries.get(asked), tuple) else (self.queries.get(asked), [])
            reply = {'questions': [{'question': asked, 'reasoning': 'r', 'query': query, 'definitions_used': used}] if asked in self.queries else []}
        else:
            reply = PLANTED_DRAFT
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(reply, ensure_ascii=False))


COUNT_ORDERS = {'start': 'order', 'group_by': None}
CITY = lambda city: {'start': 'customer', 'where': [{'field': '客户.城市', 'equals': city}], 'group_by': None}
QUERIES = {
    # what the model wrote for each phrasing: the same query, and its word on which definition the question uses and how
    '有多少订单已取消？': (CANCELLED, [inc('已取消')]), '有没有已取消的订单？': (CANCELLED, [inc('已取消')]),
    '已取消的不算，有多少订单？': (COUNT_ORDERS, [exc('已取消')]), '除已取消外有多少订单？': (COUNT_ORDERS, [exc('已取消')]),
    '未取消的订单有多少？': (COUNT_ORDERS, [exc('已取消')]), '已取消的不算，有多少订单？（带筛选）': (CANCELLED, [exc('已取消')]),
    '有多少订单作废了？': (COUNT_ORDERS, [inc('作废')]),
    '有多少订单已取消？（没说用了定义）': (COUNT_ORDERS, []), '有多少订单已取消？（漏了但筛了）': (CANCELLED, []),
    '有效订单有多少？': (COUNT_ORDERS, [inc('有效订单')]), '订单有多少？': COUNT_ORDERS,
    '火星的客户有几个？': CITY('火星'), '上海的客户有几个？': CITY('上海'), '苏州的客户有几个？': CITY('苏州'),
    '已取消的订单有多少？': ({'start': 'order', 'where': [{'field': '订单.状态码', 'equals': ['2']}], 'group_by': None}, [inc('已取消')]),
    '库存一共多少？': {'start': 'product', 'measure': {'field': '库存快照.库存数量', 'op': 'sum'}, 'group_by': None}}


class ServerAnswersTests(unittest.TestCase):
    def setUp(self):
        from tests.test_ontology_ask_server import call
        from tests.test_ontology_server import OntologyServerTests
        from tests.test_workspace_store import ServerDataChecksTests
        self.model = AskModel(QUERIES)
        server = OntologyServerTests().server(gateway=self.model)
        self.base, self.out = server.__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        self.call = call
        status, self.run = call(self.base, '/api/ontology/build', {'files': ServerDataChecksTests.files})
        self.assertEqual(status, 200, self.run)

    def post(self, path, **body):
        return self.call(self.base, path, {'saved_as': self.run['saved_as'], **body})

    def ask(self, question):
        status, run = self.post('/api/ontology/ask', question=question)
        self.assertEqual(status, 200, run)
        return run['evaluation']['asked'][-1]['items'][0]

    def confirm_meaning(self, values=({'value': '2', 'label': '已取消'},)):
        status, body = self.post('/api/ontology/code-meanings', id='code_meaning:订单.状态码', values=list(values), confirmed_by='王工')
        self.assertEqual(status, 200, body)

    def define_valid_orders(self):
        status, body = self.post('/api/ontology/views', name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消')
        self.assertEqual(status, 200, body)

    def test_a_definition_the_model_says_the_question_uses_but_the_query_did_not_apply_is_refused(self):
        self.assertEqual(self.ask('有多少订单已取消？（没说用了定义）')['status'], 'answered')   # nothing confirmed yet: nothing to check
        self.confirm_meaning()
        self.assertEqual(self.ask('有没有已取消的订单？')['answer']['total'], 16)                 # include, and the query filters by it
        item = self.ask('有多少订单已取消？（没说用了定义）')
        self.assertEqual(item['status'], 'definition_unmet')
        self.assertIn('问题里提到「已取消」', item['reason'])
        self.assertNotIn('answer', item)
        undeclared = self.ask('有多少订单已取消？（漏了但筛了）')                 # the query filters by it, the model did not say how it used it
        self.assertEqual(undeclared['status'], 'definition_unmet')
        self.assertIn('没有说明问题是要包含还是排除', undeclared['reason'])
        self.assertNotIn('answer', undeclared)

    def test_every_answer_carries_the_models_reading(self):
        self.confirm_meaning()
        self.define_valid_orders()
        included = self.ask('有没有已取消的订单？')
        self.assertEqual(included['understood'], [{'definition': '已取消', 'direction': 'include', 'how': '状态码 = 2'}])
        excluded = self.ask('已取消的不算，有多少订单？')
        self.assertEqual(excluded['understood'], [{'definition': '已取消', 'direction': 'exclude', 'how': '读视图 有效订单'}])
        refused = self.ask('已取消的不算，有多少订单？（带筛选）')
        self.assertEqual((refused['status'], refused['understood'][0]['how']), ('definition_unmet', '查询做不到排除'))
        self.assertNotIn('understood', self.ask('订单有多少？'))
        self.assertEqual(sorted(included['definitions_told']), ['有效订单', '订单.状态码=已取消'])

    def test_the_model_is_told_what_has_been_confirmed(self):
        self.confirm_meaning()
        self.define_valid_orders()
        self.ask('订单有多少？')
        told = self.model.requests[-1]['definitions']
        self.assertEqual({(d['name'], d['kind']) for d in told}, {('已取消', 'meaning'), ('有效订单', 'view')})
        self.assertIn('definitions_used', QUESTION_SYSTEM_PROMPT)

    def test_leaving_a_definition_out_is_refused_unless_a_view_leaves_it_out(self):
        self.confirm_meaning()
        for question in ('已取消的不算，有多少订单？', '除已取消外有多少订单？', '未取消的订单有多少？', '已取消的不算，有多少订单？（带筛选）'):
            item = self.ask(question)
            self.assertEqual(item['status'], 'definition_unmet', question)
            self.assertIn('排除', item['reason'])
            self.assertNotIn('answer', item)
        self.define_valid_orders()
        for question in ('已取消的不算，有多少订单？', '除已取消外有多少订单？', '未取消的订单有多少？'):
            item = self.ask(question)
            self.assertEqual((item['status'], item['answer']['total']), ('answered', 144), question)
            self.assertEqual([v['name'] for v in item['evidence']['views']], ['有效订单'])
        self.assertEqual(self.ask('已取消的不算，有多少订单？（带筛选）')['status'], 'definition_unmet')   # the query also counts them: contradicts

    def test_a_label_of_two_characters_is_checked_when_the_model_says_it_is_used(self):
        self.confirm_meaning([{'value': '2', 'label': '作废'}])
        item = self.ask('有多少订单作废了？')
        self.assertEqual(item['status'], 'definition_unmet')
        self.assertIn('作废', item['reason'])

    def test_a_named_view_in_the_question_chooses_the_rows_and_the_answer_names_it(self):
        self.confirm_meaning()
        self.define_valid_orders()
        valid = self.ask('有效订单有多少？')
        self.assertEqual(valid['answer']['total'], 144)
        self.assertEqual([(v['name'], v['kind'], v['rows']) for v in valid['evidence']['views']], [('有效订单', 'filter', 144)])
        everything = self.ask('订单有多少？')
        self.assertEqual(everything['answer']['total'], 160)
        self.assertNotIn('views', everything.get('evidence', {}))

    def test_a_named_view_that_no_longer_holds_is_a_refusal_naming_it(self):
        self.confirm_meaning()
        self.define_valid_orders()
        self.post('/api/ontology/code-meanings', id='code_meaning:订单.状态码', values=[{'value': '2', 'label': ''}], confirmed_by='王工')
        item = self.ask('有效订单有多少？')
        self.assertEqual(item['status'], 'definition_unmet')
        self.assertIn('问题里提到「有效订单」', item['reason'])
        self.assertIn('已取消', item['reason'])

    def test_no_data_is_only_called_lost_rows_when_a_damaged_row_could_be_the_one_asked_for(self):
        for city in ('火星', '上海'):             # KH012 (合肥, 苏州) repeats; neither city is its
            self.assertEqual(self.ask(f'{city}的客户有几个？')['status'], 'no_data', city)
        self.assertEqual(self.ask('苏州的客户有几个？')['answer']['total'], 8)        # a repeated row's city is found, not lost

    def test_a_list_as_a_filter_value_is_a_query_limit_not_a_definition_refusal(self):
        self.confirm_meaning()
        listed = self.ask('已取消的订单有多少？')
        self.assertEqual(listed['status'], 'query_limit')
        self.assertIn('只能等于一个值', listed['reason'])

    def test_the_stock_answer_is_the_same_with_the_views_cached(self):
        self.post('/api/ontology/repeat-rules', id='repeated_key:product.库存快照', rule='keep_latest', column='快照月份', confirmed_by='王工')
        first, second = self.ask('库存一共多少？'), self.ask('库存一共多少？')
        self.assertEqual((first['answer']['measure']['value'], second['answer']['measure']['value']), (1115, 1115))
        self.assertEqual([v['name'] for v in second['evidence']['views']], ['库存快照_当前'])

    def test_when_the_workspace_has_no_data_for_the_run_the_answer_still_comes_and_says_the_views_were_not_read(self):
        import sqlite3
        self.confirm_meaning()
        conn = sqlite3.connect(self.out / 'workspace.sqlite')
        conn.execute('DELETE FROM dataset')   # the workspace file was replaced by one that does not know this run's tables
        conn.commit()
        conn.close()
        item = self.ask('订单有多少？')
        self.assertEqual(item['answer']['total'], 160)
        self.assertIn('视图没有读出来，这次读的是原表的行', item['evidence']['views_unread'])

    def test_a_view_the_rule_needs_that_cannot_be_made_is_said_in_the_answer(self):
        from ontology_poc_generator.workspace_store import open_workspace, set_element_states
        conn = open_workspace(self.out / 'workspace.sqlite')
        key = self.run['file']['sha256']
        set_element_states(conn, [(f'repeat_rule:{key}:product.库存快照', 'confirmed', None, '王工', {'rule': 'keep_latest', 'column': '没有这列', 'covers': []})])
        conn.close()
        item = self.ask('库存一共多少？')
        self.assertIn('视图用不了', item['evidence']['views_unread'])
        self.assertIn('库存快照_当前', item['evidence']['views_unread'])


class BlockedDraftTests(unittest.TestCase):
    """A draft that failed the checks stores its tables all the same: its code columns, meanings, views and pipelines work on
    them; only the questions wait, and say which check stopped them."""
    def setUp(self):
        from tests.test_ontology_ask_server import call
        from tests.test_ontology_server import OntologyServerTests
        from tests.test_workspace_store import DraftsModel, ServerDataChecksTests
        broken = json.loads(json.dumps(PLANTED_DRAFT))
        broken['object_types'][0]['attributes'].append({'source': '客户', 'path': '没有这一列'})
        server = OntologyServerTests().server(gateway=DraftsModel(broken))
        self.base, self.out = server.__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        self.call = call
        _, self.run = call(self.base, '/api/ontology/build', {'files': ServerDataChecksTests.files})
        self.assertNotEqual(self.run['ontology']['status'], 'auto_built_verified')

    def post(self, path, **body):
        return self.call(self.base, path, {'saved_as': self.run['saved_as'], **body})

    def test_a_run_whose_draft_failed_the_checks_still_joins_the_tables_it_stored(self):
        from tests.test_pipelines import ORDERS_TICKETS
        status, body = self.post('/api/ontology/pipelines/run', pipeline=ORDERS_TICKETS)
        self.assertEqual(status, 200, body)
        self.assertEqual(body['nodes'][2]['rows_out'], 169)

    def test_meanings_and_views_work_on_the_stored_tables(self):
        from urllib.request import urlopen
        with urlopen(self.base + f"/api/ontology/runs/{self.run['saved_as']}/open-items", timeout=30) as response:
            listed = json.load(response)
        self.assertEqual({i['kind'] for i in listed['items']}, {'code_meaning'})        # no graph, no card: only what the stored tables can settle
        self.assertIn('code_meaning:订单.状态码', {i['id'] for i in listed['items']})
        status, body = self.post('/api/ontology/code-meanings', id='code_meaning:订单.状态码', values=[{'value': '2', 'label': '已取消'}], confirmed_by='王工')
        self.assertEqual(status, 200, body)
        self.assertNotIn('warning', body)
        self.assertEqual(body['meanings']['订单.状态码']['labels'], {'2': '已取消'})
        status, body = self.post('/api/ontology/views', name='有效订单', kind='filter', base='订单', column='状态码', op='is_not', label='已取消')
        self.assertEqual(status, 200, body)
        self.assertEqual({v['name']: v['rows'] for v in body['views']}, {'订单': 160, '有效订单': 144})

    def test_the_reference_page_loads_for_a_run_that_has_no_handover(self):
        from urllib.request import urlopen
        with urlopen(self.base + f"/api/ontology/runs/{self.run['saved_as']}/reference", timeout=30) as response:
            body = json.load(response)
        self.assertEqual((body['record'], body['definition'], body['stale']), (None, None, []))
        self.assertIn('不能对照领域参考', body['blocked'])
        self.assertIn(self.run['ontology']['verification']['errors'][0]['code'], body['blocked'])
        status, reply = self.call(self.base, '/api/ontology/compare', {'saved_as': self.run['saved_as'], 'reference': {'object_types': [{'label': '客户'}]}})
        self.assertEqual(status, 400)
        self.assertIn('不能对照参考本体', reply['error'])
        status, reply = self.call(self.base, '/api/ontology/reference/preview', {'saved_as': self.run['saved_as'], 'reference_id': 'x', 'mappings': []})
        self.assertEqual(status, 400)   # nothing is compared or saved against a draft that did not pass
        self.assertIn('不能对照领域参考', reply['error'])

    def test_the_questions_say_which_check_stopped_them(self):
        status, body = self.post('/api/ontology/ask', question='订单有多少？')
        self.assertEqual(status, 400)
        self.assertIn('不能出题', body['error'])
        self.assertIn(self.run['ontology']['verification']['errors'][0]['code'], body['error'])


if __name__ == '__main__':
    unittest.main()
