"""An action parameter whose value must be one of another type's values (or its own type's): the form offers the values of the rows the person may read, and a
submit or an approval with any other value is refused. The choice is part of the action's definition: changing it asks for another confirmation."""
from urllib.parse import quote

from tests.test_explorer import CUSTOMERS, ORDERS
from tests.test_notices import NoticeTests

PICK = {'name': '改订单客户', 'type': 'order', 'properties': ['客户编号'], 'description': '订单转给另一个客户',
        'choices': {'客户编号': {'type': 'customer', 'column': '客户编号'}}}
URL = '/api/workspace/actions/' + quote(PICK['name'])


def load_tests(loader, standard, pattern):
    import unittest
    return unittest.TestSuite(ChoiceTests(name) for name in vars(ChoiceTests) if name.startswith('test_'))


class ChoiceTests(NoticeTests):
    def define(self, team, payload=PICK):
        ann, bob = team['ann'], team['bob']
        status, body = ann.post('/api/workspace/actions', payload)
        self.assertEqual(status, 200, body)
        shown = bob.get(URL)[1]
        self.assertEqual(bob.post('/api/workspace/actions/confirm', {'id': payload['name'], 'version': shown['version']})[0], 200)

    def test_the_form_offers_the_other_types_values_and_a_value_outside_them_is_refused(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            self.ready(team)
            self.define(team)
            parameter = ann.get(URL)[1]['parameters'][0]
            self.assertEqual(parameter['choices_from'], {'type': 'customer', 'type_name': '客户', 'column': '客户编号'})
            self.assertEqual([o['value'] for o in parameter['options']], sorted({c['客户编号'] for c in CUSTOMERS}))
            order = next(r for r in ORDERS if r['客户编号'] == 'KH001')
            submit = lambda value: bob.post('/api/workspace/actions/submit', {'action': PICK['name'], 'key': {'订单号': order['订单号']}, 'params': {'客户编号': value}, 'reason': '转单'})
            status, body = submit('KH999')
            self.assertEqual(status, 400, body)   # a value that is not allowed, like any other bad value
            self.assertIn('不在“客户”的“客户编号”里', body['error'])
            status, body = submit('KH002')
            self.assertEqual(status, 200, body)
            self.assertEqual(ann.post('/api/workspace/actions/decide', {'id': body['record'], 'decision': 'approve'})[1]['state'], 'approved')
            # a person a row rule limits on the other type is offered only the values of the rows they may read
            ids = {u: self.user_id(admin, u) for u in ('ann', 'bob')}
            rule = [{'column': '客户等级', 'value': 'A', 'user_ids': [ids['bob']]}, {'user_ids': [ids['ann']]}]
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'customer', 'rules': rule})[0], 200)
            offered = [o['value'] for o in bob.get(URL)[1]['parameters'][0]['options']]
            self.assertEqual(offered, sorted({c['客户编号'] for c in CUSTOMERS if c['客户等级'] == 'A'}))

    def test_a_choice_is_checked_and_part_of_the_definition(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            self.ready(team)
            for bad, status in (({'客户编号': {'type': 'customer', 'column': '不存在'}}, 400), ({'客户编号': {'type': 'nothing', 'column': '客户编号'}}, 404),
                                ({'金额': {'type': 'customer', 'column': '客户编号'}}, 400), ({'客户编号': 'customer'}, 400), ('x', 400),
                                ({'状态码': {'type': 'customer', 'column': '客户编号'}}, 400)):
                payload = {**PICK, 'properties': ['客户编号', '状态码'] if '状态码' in str(bad) else PICK['properties'], 'choices': bad}
                self.assertEqual(ann.post('/api/workspace/actions', payload)[0], status, bad)
            self.define(team)
            version = ann.get(URL)[1]['version']
            status, body = ann.post('/api/workspace/actions/update', {**PICK, 'id': PICK['name'], 'version': version, 'choices': {}})
            self.assertEqual(status, 200, body)
            shown = ann.get(URL)[1]
            self.assertNotEqual(shown['state'], 'confirmed')   # what may be written changed: it is looked at again
            self.assertIsNone(shown['parameters'][0]['choices_from'])
