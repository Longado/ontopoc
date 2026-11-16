"""A board card that is an OntoPoc Query, and the board's $parameters: asked once at the top of the board and passed to every query card (R10 step 3b).

A query card is a saved query: its text is kept on the board and worked out each time someone opens it, by that person, over the rows and properties they may
read, with no model. A parameter is a value only: whatever a reader types is compared as a value, never read as query text. Every $name a card uses must be
declared on the board with a default, so the board always has a number to show and the save checks it."""
from tests.test_dashboards import BoardCase
from tests.test_explorer import ORDERS

WHO = "SELECT count(o) AS 数量 FROM (o:订单) WHERE o.客户编号 = $who"
BIG = 'SELECT count(o) FROM (o:订单) WHERE o.金额 >= $min'
AMOUNT = 'SELECT sum(o.金额) FROM (o:订单) WHERE o.客户编号 = $who'
PARAMS = [{'name': 'who', 'label': '客户', 'default': 'KH001'}, {'name': 'min', 'label': '金额至少', 'default': '20000'}]


def card(ident, text, title='卡片'):
    return {'id': ident, 'title': title, 'text': text, 'chart': {'kind': 'query'}}


def spec(*cards, params=PARAMS, filters=()):
    return {'components': list(cards), 'filters': list(filters), 'params': params}


def mine(kh):
    return sum(r['客户编号'] == kh for r in ORDERS)


class QueryCardTests(BoardCase):
    def params_data(self, client, board, params, expect=200):
        status, body = client.post('/api/workspace/dashboards/data', {'id': board, 'bar': {}, 'params': params})
        self.assertEqual(status, expect, body)
        return body

    def test_a_query_card_takes_the_board_s_parameters_with_their_defaults_and_what_the_reader_types(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            board = self.make(team['ann'], spec=spec(card('who', WHO), card('big', BIG)), scope='everyone')
            self.assertEqual(board['spec']['params'], PARAMS)
            body = self.data(team['bob'], board['id'])
            self.assertEqual(self.card(body, 'who')['result']['answer']['total'], mine('KH001'))
            self.assertEqual(self.card(body, 'big')['result']['answer']['total'], sum(int(r['金额']) >= 20000 for r in ORDERS))
            self.assertEqual([(p['name'], p['value']) for p in body['params']], [('who', 'KH001'), ('min', '20000')])
            picked = self.params_data(team['bob'], board['id'], {'who': 'KH026', 'min': 50000})
            self.assertEqual(self.card(picked, 'who')['result']['answer']['total'], mine('KH026'))
            self.assertEqual(self.card(picked, 'big')['result']['answer']['total'], sum(int(r['金额']) >= 50000 for r in ORDERS))
            got = self.card(picked, 'who')['result']
            self.assertEqual(got['text'], "SELECT count(o) AS 数量\nFROM (o:订单)\nWHERE o.客户编号 = 'KH026'")   # what was worked out, with the value in it
            self.assertTrue(got['standing']['confirmed'])
            self.assertIn('订单', [d['name'] for d in got['definitions']])
            self.assertEqual(picked['headline']['text'], '全部按已确认的定义算出')
            empty = self.params_data(team['bob'], board['id'], {'who': '', 'nope': 'x'})   # an empty value is the default; a name the board has not is ignored
            self.assertEqual(self.card(empty, 'who')['result']['answer']['total'], mine('KH001'))

    def test_a_parameter_is_a_value_never_query_text(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            board = self.make(team['ann'], spec=spec(card('who', WHO)))
            body = self.params_data(team['ann'], board['id'], {'who': "KH001' OR '1'='1"})
            got = self.card(body, 'who')
            self.assertEqual(got['status'], 'ok')
            self.assertEqual(got['result']['answer']['total'], 0)   # a SQL template that pastes the value in would count all 160

    def test_a_card_and_its_parameters_are_checked_when_the_board_is_saved(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann = team['ann']
            for bad, words in ((spec(card('x', 'SELECT count(o) FROM (o:订单) WHERE o.客户编号 = $nobody')), '$nobody'),
                               (spec(card('x', 'SELECT count(o) FROM (o:订单)-[:下单]->(p:产品)')), '订单买的产品'),
                               (spec(card('x', 'SELECT count(o) FROM (o:订单)'), params=[{'name': 'who', 'label': '客户', 'default': ''}]), '默认值'),
                               (spec(card('x', 'SELECT count(o) FROM (o:订单)'), params=[{'name': 'who', 'default': 'a'}, {'name': 'who', 'default': 'b'}]), '重复'),
                               (spec(card('x', 'SELECT count(o) FROM (o:订单)'), params=[{'name': '1x', 'default': 'a'}]), '参数名'),
                               (spec(card('x', 'SELECT count(o) FROM (o:订单)'), params=[{'name': f'p{i}', 'default': 'a'} for i in range(5)]), '最多'),
                               (spec(card('x', '')), '查询'),
                               (spec({'id': 'x', 'title': 't', 'text': WHO, 'chart': {'kind': 'bar'}}), '查询')):
                body = self.make(ann, spec=bad, expect=400)
                self.assertIn(words, body['error'], bad)
            ok = self.make(ann, spec=spec(card('x', 'SELECT count(o) FROM (o:订单)'), params=[{'name': 'who', 'default': 'KH001'}]))
            self.assertEqual(ok['spec']['params'], [{'name': 'who', 'label': 'who', 'default': 'KH001'}])   # the label is the name when none is written
            for odd in ({'who': ['KH001']}, {'who': 'x' * 201}, 'who'):
                self.params_data(ann, ok['id'], odd, expect=400)

    def test_every_reader_gets_the_card_over_their_own_rows_and_properties(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            admin, ann, vera = team['admin'], team['ann'], team['vera']
            ids = self.ids(admin)
            board = self.make(ann, spec=spec(card('who', WHO), card('amount', AMOUNT)), scope='everyone')
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH026', 'user_ids': [ids['vera']]}]})[0], 200)
            self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'order', 'column': '金额', 'visible_to': [ids['ann']]})[0], 200)
            seen = self.params_data(vera, board['id'], {'who': 'KH026'})
            got = self.card(seen, 'who')['result']
            self.assertEqual(got['answer']['total'], mine('KH026'))
            self.assertEqual([l['rule'] for l in got['limited_by_rule']], ['客户编号 = KH026'])
            self.assertEqual(self.card(self.params_data(vera, board['id'], {'who': 'KH001'}), 'who')['result']['answer']['total'], 0)   # not her rows
            hidden = self.card(seen, 'amount')
            self.assertEqual(hidden['status'], 'unavailable')
            self.assertNotIn('金额', str(hidden))   # the card is there; what it reads is not told to someone who may not read it
            self.assertIn('你现在看不到', seen['headline']['text'])
            self.assertEqual(self.card(self.params_data(ann, board['id'], {'who': 'KH026'}), 'amount')['result']['answer']['measure']['value'],
                             sum(int(r['金额']) for r in ORDERS if r['客户编号'] == 'KH026'))
            reader = vera.get(f'/api/workspace/dashboards/{board["id"]}')[1]
            self.assertNotIn('spec', reader)   # a reader gets the board worked out, not its texts

    def test_query_cards_sit_beside_the_other_cards_and_the_filter_bar_leaves_them_alone(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            from tests.test_dashboards import BY_STATUS
            board = self.make(team['ann'], spec=spec(card('who', WHO), BY_STATUS, filters=[{'field': '状态码', 'label': '状态'}]))
            status, body = team['ann'].post('/api/workspace/dashboards/data', {'id': board['id'], 'bar': {'状态码': '2'}, 'params': {}})
            self.assertEqual(status, 200, body)
            self.assertEqual(self.card(body, 'who')['result']['answer']['total'], mine('KH001'))   # the bar picks fields for the explorer cards; a query card says its own conditions
            self.assertEqual(self.card(body, 'status')['status'], 'ok')
            status, preview = team['ann'].post('/api/workspace/dashboards/preview', {'spec': spec(card('who', WHO))})
            self.assertEqual((status, self.card(preview, 'who')['result']['answer']['total']), (200, mine('KH001')))
