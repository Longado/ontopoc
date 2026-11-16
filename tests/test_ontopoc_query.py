"""OntoPoc Query: the text compiles into the checked query Q&A already runs, a structured query writes back as text, and every refusal says what is
missing in words. Names are looked up in what this person may see, so a hidden type or property reads exactly like one that does not exist."""
import unittest

from ontology_poc_generator.ontopoc_query import QueryError, canonical, compile_query, parse, to_text

CATALOG = {
    'types': {
        'order': {'name': '订单', 'properties': ['订单号', '客户编号', '产品编号', '金额', '状态码', '下单日期']},
        'customer': {'name': '客户', 'properties': ['客户编号', '客户名称', '城市', '客户等级']},
        'product': {'name': '产品', 'properties': ['产品编号', '产品名称', '品类']},
        'ticket': {'name': '售后工单', 'properties': ['工单号', '订单号', '问题类型']},
    },
    'relations': {
        'order_customer': {'name': '订单属于客户', 'from': 'order', 'to': 'customer'},
        'order_product': {'name': '订单买的产品', 'from': 'order', 'to': 'product'},
        'ticket_order': {'name': '工单属于订单', 'from': 'ticket', 'to': 'order'},
    },
}
EMPTY = {'start': None, 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None, 'top': None, 'order': None}
TOP3 = '''SELECT c.客户名称, sum(o.金额) AS 合计
FROM (o:订单)-[:订单属于客户]->(c:客户)
WHERE o.状态码 <> '已取消'
GROUP BY c.客户名称
ORDER BY 合计 DESC
LIMIT 3'''


def q(**parts):
    return {**EMPTY, **parts}


class CompileTests(unittest.TestCase):
    def test_the_top_three_customers_by_amount_compile_into_the_checked_query(self):
        self.assertEqual(compile_query(TOP3, CATALOG), q(start='order', where=[{'field': '状态码', 'not_equals': '已取消'}],
                                                         group_by=[{'via': ['order_customer'], 'field': '客户名称'}], measure={'field': '金额', 'op': 'sum'},
                                                         top=3, order='largest'))

    def test_keys_and_names_both_resolve_and_the_arrow_may_point_either_way_or_none(self):
        for text in ('SELECT c.客户等级, count(o) FROM (o:order)-[:order_customer]->(c:customer) GROUP BY c.客户等级',
                     'SELECT c.客户等级, count(o) FROM (c:客户)<-[:订单属于客户]-(o:订单) GROUP BY c.客户等级',
                     'select c.客户等级, COUNT(o) from (c:客户)-[:订单属于客户]-(o:订单) group by c.客户等级'):
            self.assertEqual(compile_query(text, CATALOG), q(start='order', group_by=[{'via': ['order_customer'], 'field': '客户等级'}]), text)

    def test_counting_the_objects_reached_from_filtered_ones_uses_the_top_level_via(self):
        text = "SELECT count(c) FROM (o:订单)-[:订单属于客户]->(c:客户) WHERE o.状态码 = '已取消'"
        self.assertEqual(compile_query(text, CATALOG), q(start='order', where=[{'field': '状态码', 'equals': '已取消'}], via=['order_customer']))

    def test_share_average_not_in_two_dimensions_and_ascending(self):
        text = '''SELECT p.品类, c.城市, avg(o.金额) AS 平均
                  FROM (o:订单)-[:订单属于客户]->(c:客户), (o)-[:订单买的产品]->(p:产品)
                  WHERE o.状态码 NOT IN ('已取消', '生产中')
                  GROUP BY p.品类, c.城市 ORDER BY avg(o.金额) LIMIT 2'''
        self.assertEqual(compile_query(text, CATALOG), q(start='order', where=[{'field': '状态码', 'not_equals': ['已取消', '生产中']}],
                                                         group_by=[{'via': ['order_product'], 'field': '品类'}, {'via': ['order_customer'], 'field': '城市'}],
                                                         measure={'field': '金额', 'op': 'average'}, top=2, order='smallest'))
        self.assertEqual(compile_query("SELECT share(o.状态码 = '已取消') FROM (o:订单)", CATALOG), q(start='order', share={'field': '状态码', 'equals': '已取消'}))

    def test_a_two_step_path_walks_both_relations(self):
        text = 'SELECT c.城市, count(t) FROM (t:售后工单)-[:工单属于订单]->(o:订单)-[:订单属于客户]->(c:客户) GROUP BY c.城市'
        self.assertEqual(compile_query(text, CATALOG), q(start='ticket', group_by=[{'via': ['ticket_order', 'order_customer'], 'field': '城市'}]))

    def test_parameters_are_values_never_text(self):
        text = 'SELECT count(o) FROM (o:订单) WHERE o.客户编号 = $who'
        self.assertEqual(compile_query(text, CATALOG, {'who': 'KH001'})['where'], [{'field': '客户编号', 'equals': 'KH001'}])
        sneaky = "x' OR 1=1 --"
        self.assertEqual(compile_query(text, CATALOG, {'who': sneaky})['where'], [{'field': '客户编号', 'equals': sneaky}])
        with self.assertRaisesRegex(QueryError, r'缺少参数 \$who'):
            compile_query(text, CATALOG)
        with self.assertRaisesRegex(QueryError, '参数'):
            compile_query(text, CATALOG, {'who': ['KH001']})

    def refused(self, text, *words):
        with self.assertRaises(QueryError) as caught:
            compile_query(text, CATALOG)
        for w in words:
            self.assertIn(w, str(caught.exception), text)
        return str(caught.exception)

    def test_an_unknown_relation_is_refused_listing_the_relations_that_type_has(self):
        said = self.refused('SELECT count(o) FROM (o:订单)-[:下单]->(c:客户)', '没有关系「下单」', '订单属于客户（订单→客户）', '订单买的产品（订单→产品）', '工单属于订单（售后工单→订单）')
        self.assertNotIn('库存', said)
        self.refused('SELECT count(o) FROM (o:订单)<-[:订单属于客户]-(c:客户)', '是从 订单 到 客户')

    def test_unknown_types_and_properties_say_what_there_is(self):
        self.refused('SELECT count(x) FROM (x:供应商)', '没有对象类型「供应商」', '订单、客户、产品、售后工单')
        self.refused('SELECT sum(o.利润) FROM (o:订单)', '订单 没有属性「利润」', '金额')

    def test_what_the_checked_query_cannot_say_is_refused_in_words_not_read_as_something_else(self):
        cases = [
            ("SELECT count(o) FROM (o:订单) WHERE o.金额 IS NULL", '空值'),
            ("SELECT count(o) FROM (o:订单) WHERE o.状态码 = '0' OR o.状态码 = '1'", 'OR 还不支持'),
            ("SELECT c.城市, count(o) FROM (o:订单)-[:订单属于客户]->(c:客户) WHERE c.客户等级 = 'A' GROUP BY c.城市", '条件只能写在被数或被算的对象（o）上', '跨对象'),
            ('SELECT count(o) FROM (o:订单)-[:订单属于客户]->(c:客户)', '(c:客户) 没有用到', '悄悄去掉'),
            ('SELECT count(o), sum(o.金额) FROM (o:订单)', '有且只有一个'),
            ('SELECT o.城市 FROM (o:订单)', '有且只有一个'),
            ('SELECT c.城市, count(o) FROM (o:订单)-[:订单属于客户]->(c:客户)', '也要写进 GROUP BY'),
            ('SELECT count(o) FROM (o:订单) ORDER BY 数量 DESC', 'ORDER BY 要和 GROUP BY 一起用'),
            ('SELECT count(o) FROM (o:订单) LIMIT 5', 'LIMIT 要和 GROUP BY 一起用'),
            ('SELECT c.城市, count(o) FROM (o:订单)-[:订单属于客户]->(c:客户) GROUP BY c.城市 ORDER BY c.城市', '只能按算出来的那个数排'),
            ("SELECT count(o) FROM (o:订单) WHERE o.状态码 IN ('0', '1')", 'IN 几个值还不支持', 'NOT IN'),
            ('SELECT count(o) FROM 订单 o JOIN 客户 c ON o.客户编号 = c.客户编号', '“(”'),
            ('SELECT count(o.金额) FROM (o:订单)', 'count 数的是对象'),
            ('SELECT count(o) FROM (o:订单) LIMIT 0', '大于 0 的整数'),
            ('SELECT count(o) FROM (o:订单) garbage', '多出来了'),
            ('', '请写一条查询'),
            ('SELECT count(o) FROM (o:订单) GROUP BY x.金额', '简称 x 没有在 FROM 里出现'),
            ('SELECT x.金额, count(o) FROM (o:订单) GROUP BY x.金额', '简称 x 没有在 FROM 里出现'),
        ]
        for text, *words in cases:
            self.refused(text, *words)

    def test_an_error_says_where(self):
        with self.assertRaises(QueryError) as caught:
            parse('SELECT count(o) FROM (o:订单) WHERE o.金额 ~ 3')
        self.assertEqual(caught.exception.at, len('SELECT count(o) FROM (o:订单) WHERE o.金额 '))


class RoundTripTests(unittest.TestCase):
    """JSON -> text -> JSON gives the query back: what the model writes today can be shown and edited as text."""
    QUERIES = [
        {'start': 'order', 'where': [{'field': '状态码', 'equals': '2'}], 'via': [], 'group_by': None, 'share': None, 'measure': None},
        {'start': 'order', 'where': [{'field': '状态码', 'not_equals': '已取消'}], 'measure': {'field': '金额', 'op': 'sum'}},
        {'start': 'order', 'measure': {'field': '金额', 'op': 'sum'}, 'group_by': [{'via': ['order_customer'], 'field': '客户名称'}], 'top': 3},
        {'start': 'order', 'measure': {'field': '金额', 'op': 'sum'}, 'group_by': [{'via': ['order_customer'], 'field': '客户名称'}], 'top': 1, 'order': 'smallest'},
        {'start': 'order', 'where': [{'field': '状态码', 'not_equals': ['已取消', '生产中']}], 'share': {'field': '状态码', 'equals': '已交付'},
         'group_by': [{'via': ['order_product'], 'field': '品类'}, {'via': ['order_customer'], 'field': '城市'}]},
        {'start': 'order', 'where': [{'field': '状态码', 'equals': "it's"}], 'via': ['order_customer']},
        {'start': 'customer', 'group_by': [{'via': ['order_customer', 'ticket_order'], 'field': '问题类型'}]},
        {'start': 'ticket', 'group_by': [{'via': ['ticket_order', 'order_customer'], 'field': '城市'}, {'via': ['ticket_order', 'order_product'], 'field': '品类'}]},
        {'start': 'order', 'group_by': '客户编号'},
    ]

    def test_every_query_comes_back(self):
        for query in self.QUERIES:
            text = to_text(query, CATALOG)
            self.assertEqual(compile_query(text, CATALOG), canonical(query), text)

    def test_a_structured_query_missing_a_part_is_refused_rather_than_written_as_text_that_does_not_read_back(self):
        for broken in ({'start': 'order', 'where': [{'field': '状态码'}]}, {'start': 'order', 'measure': {'op': 'sum'}},
                       {'start': 'order', 'where': [{'field': '状态码', 'not_equals': []}]}, {'start': 'order', 'share': {'field': '状态码'}}):
            with self.assertRaises(QueryError, msg=broken):
                to_text(broken, CATALOG)

    def test_the_text_reads_like_the_sketch(self):
        query = compile_query(TOP3, CATALOG)
        self.assertEqual(to_text(query, CATALOG), TOP3.replace('<>', '<>'))


if __name__ == '__main__':
    unittest.main()
