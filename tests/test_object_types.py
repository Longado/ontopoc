"""Object types on the workspace, walked through the real service with two builders on the seven planted tables: a type is built from a dataset with its key
checked on every row, its code meanings are confirmed by someone other than the one who proposed them, and a re-upload that shifts the codes sends the
confirmation back to "needs another look" with the reason. Expected numbers come from the planted fixtures, counted by hand."""
import base64
import csv
import io
import json
import sqlite3
import unittest
from urllib.parse import quote

from ontology_poc_generator.object_views import kept_positions
from ontology_poc_generator.recognition import ModelCompletion
from ontology_poc_generator.workspace_store import open_workspace
from tests import test_workspace_store as planted
from tests.test_two_person import SigningTestCase

TABLES = [{'filename': p.name, 'content_base64': base64.b64encode(p.read_bytes()).decode()} for p in sorted(planted.PLANTED.glob('*.xlsx'))]
MEANINGS = [{'value': '0', 'label': '已交付'}, {'value': '1', 'label': '生产中'}, {'value': '2', 'label': '已取消'}]
ORDER = {'english_name': 'order', 'name': '订单', 'dataset': '订单', 'key': ['订单号'], 'description': '客户下的一张订单',
         'properties': [{'column': '订单号'}, {'column': '金额'}, {'column': '状态码', 'enum': True}], 'enums': {'状态码': MEANINGS}}
STOCK = {'english_name': 'stock', 'name': '库存快照', 'dataset': '库存快照', 'key': ['快照月份', '产品编号'], 'properties': [{'column': '库存数量'}]}
COMMIT = {'english_name': 'commit', 'name': '订单承诺', 'dataset': '订单承诺', 'key': ['订单号', '承诺版本'], 'properties': [{'column': '承诺数量'}]}
VALID = {'name': '有效订单', 'type': 'order', 'filters': [{'column': '状态码', 'op': 'is_not', 'label': '已取消'}]}
LATEST_STOCK = {'name': '最新快照', 'type': 'stock', 'latest': {'key': ['产品编号'], 'order': '快照月份'}}
LATEST_COMMIT = {'name': '最新承诺', 'type': 'commit', 'latest': {'key': ['订单号'], 'order': '承诺版本'}}
ORDERS = planted.planted_bundle()['sources']['订单']['records']
SHIFTED = {'0': '1', '1': '2', '2': '3'}   # the same rows, each code one higher: 1/2/3 where the file had 0/1/2


def shifted_orders_csv() -> dict:
    """The 订单 table as a CSV, with every 状态码 shifted by one: an overwrite that makes 0 disappear and 3 appear."""
    records = planted.planted_bundle()['sources']['订单']['records']
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows({**r, '状态码': SHIFTED[r['状态码']]} for r in records)
    return {'filename': '订单.csv', 'content_base64': base64.b64encode(out.getvalue().encode('utf-8')).decode(), 'target': '订单', 'mode': 'overwrite'}


def orders_upload(change=lambda r, i: r, drop=(), **part) -> dict:
    """The 订单 table as a CSV after `change(record, position)` and without the columns in `drop`: an overwrite of 订单, or what `part` says instead."""
    records = planted.planted_bundle()['sources']['订单']['records']
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=[c for c in records[0] if c not in drop], extrasaction='ignore')
    writer.writeheader()
    writer.writerows(change(dict(r), i) for i, r in enumerate(records))
    return {'filename': '订单.csv', 'content_base64': base64.b64encode(out.getvalue().encode('utf-8')).decode(), **(part or {'target': '订单', 'mode': 'overwrite'})}


class Suggester:
    """A model that answers with what it is given and remembers what it was asked."""

    def __init__(self, reply):
        self.reply, self.asked, self.timeouts = reply, [], []

    def complete_json(self, *, system_prompt, user_prompt, timeout_seconds=None):
        self.asked.append(user_prompt)
        self.timeouts.append(timeout_seconds)
        return ModelCompletion('test', 'test-model', json.dumps(self.reply, ensure_ascii=False))


class ObjectTypeTests(SigningTestCase):
    def team(self, base, *names, roles=None):
        team = self.people(base, *names, roles=roles)
        status, body = team[names[0]].post('/api/workspace/datasets/upload', {'files': TABLES})
        self.assertEqual(status, 200, body)
        return team

    def detail(self, client, name='order'):
        status, body = client.get(f'/api/workspace/types/{name}')
        self.assertEqual(status, 200, body)
        return body

    def meanings(self, detail, column='状态码'):
        return next(p for p in detail['properties'] if p['column'] == column)['meanings']

    def confirm(self, client, column=None, name='order'):
        """Confirm what this person's page shows now: the type, or the meanings of one code column, with the version and the data they read."""
        detail = self.detail(client, name)
        shown = self.meanings(detail, column) if column else detail
        return client.post('/api/workspace/types/confirm', {'id': name, 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})

    def confirm_all(self, proposer, confirmer):
        """The planted 订单 type with its code meanings, put forward by one builder and confirmed by the other."""
        self.assertEqual(proposer.post('/api/workspace/types', ORDER)[0], 200)
        for column in ('状态码', None):   # the meanings first: a type is confirmed once all of them are
            status, body = self.confirm(confirmer, column)
            self.assertEqual(status, 200, body)

    def test_a_type_built_from_a_dataset_is_confirmed_by_the_other_builder_and_not_by_its_proposer(self):
        with self.service() as (base, out):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            status, body = ann.post('/api/workspace/types', ORDER)
            self.assertEqual(status, 200, body)
            detail = self.detail(ann)
            self.assertEqual((detail['state'], detail['proposed_by'], detail['rows'], detail['key']), ('checked', 'Ann', 160, ['订单号']))
            meanings = self.meanings(detail)
            self.assertEqual((meanings['can_confirm'], meanings['confirmers']), (False, ['Bob', '管理员']))   # the proposer sees no button, and who could
            self.assertEqual((detail['can_confirm'], detail['confirmers']), (False, []))   # the type waits for its meanings first
            self.assertEqual(([(v['value'], v['label'], v['rows']) for v in meanings['values']]), [('0', '已交付', 96), ('1', '生产中', 48), ('2', '已取消', 16)])
            confirm = {'id': 'order', 'column': '状态码', 'version': meanings['version'], 'seen': meanings['seen']}
            status, body = ann.post('/api/workspace/types/confirm', confirm)
            self.assertEqual((status, body['error']), (403, '这一条是你自己提的，要另一位来确认'))
            self.assertEqual(ann.post('/api/workspace/types/confirm', {'id': 'order', 'version': detail['version'], 'seen': detail['seen']})[0], 409)   # refused for its meanings before it is for who
            status, body = bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': detail['version'], 'seen': detail['seen']})   # the type waits for its meanings
            self.assertEqual((status, '“状态码”的含义还没有确认' in body['error']), (409, True))
            self.assertEqual((detail['can_confirm'], detail['meanings_blocking']), (False, ['状态码']))
            self.assertEqual((self.detail(bob)['can_confirm'], self.meanings(self.detail(bob))['can_confirm']), (False, True))   # Bob is offered the meanings, not the type yet
            status, body = bob.post('/api/workspace/types/confirm', {**confirm, 'who': 'Ann'})   # a name typed into the request is ignored
            self.assertEqual(status, 200, body)
            self.assertEqual(self.confirm(bob)[0], 200)
            detail = self.detail(bob)
            self.assertEqual((detail['state'], detail['confirmed_by'], detail['confirmed_on'], detail['can_confirm']), ('confirmed', 'Bob', {'订单': 1}, False))
            self.assertEqual((self.meanings(detail)['state'], self.meanings(detail)['confirmed_by']), ('confirmed', 'Bob'))
            conn = sqlite3.connect(out / 'workspace.sqlite')
            snapshots = conn.execute('SELECT element_id, confirmed_by, proposed_by, dataset_versions_json, self_confirmed FROM confirmation ORDER BY id').fetchall()
            self.assertEqual(snapshots, [('enum:order:状态码', 'Bob', 'Ann', '{"订单": 1}', 0), ('objtype:order', 'Bob', 'Ann', '{"订单": 1}', 0)])
            self.assertEqual(set(conn.execute("SELECT depends_on FROM element_dep WHERE element_id = 'objtype:order'").fetchall()), {('dataset:订单',), ('enum:order:状态码',)})
            self.assertEqual(conn.execute("SELECT depends_on FROM element_dep WHERE element_id = 'enum:order:状态码'").fetchall(), [('column:订单.状态码',)])
            conn.close()

    def test_shifted_codes_in_a_new_version_send_the_confirmed_meaning_back_and_the_log_names_both_accounts(self):
        with self.service() as (base, out):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.confirm_all(ann, bob)
            before = self.detail(bob)
            self.assertEqual(self.meanings(before)['state'], 'confirmed')
            status, body = ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})
            self.assertEqual((status, body['results'][0]['version']), (200, 2))
            detail = self.detail(bob)
            meaning = self.meanings(detail)
            self.assertEqual(meaning['state'], 'needs_look')
            self.assertIn('新出现 3（16 行，没有含义）', meaning['reason'])
            self.assertIn('不再出现 0（原来是「已交付」）', meaning['reason'])
            self.assertIn('第 2 版（Ann上传）', meaning['reason'])
            self.assertEqual([(v['value'], v['label'], v['rows_at_confirmation'], v['rows']) for v in meaning['values']],
                             [('0', '已交付', 96, None), ('1', '生产中', 48, 96), ('2', '已取消', 16, 48), ('3', '', None, 16)])
            self.assertEqual(detail['state'], 'needs_look')   # the type reads its meanings: it moves with them
            self.assertIn('需要再看', detail['reason'])
            self.assertEqual(detail['can_confirm'], False)   # not until its meanings are looked at again
            self.assertEqual(detail['confirmed_by'], 'Bob')   # who confirmed it before is still there, beside the reason
            log = bob.get('/api/workspace/types/order/log')[1]['log']
            moved = next(e for e in log if e['element'] == 'meaning' and e['to'] == 'needs_look')
            self.assertEqual((moved['who'], moved['from'], moved['caused_by']), ('system', 'confirmed', 'Ann'))
            self.assertIn('新出现 3', moved['reason'])
            names = {e['who'] for e in log} - {'system'}
            self.assertEqual(names, {'Ann', 'Bob'})   # the proposer, the confirmer and (as Ann) the upload are all in it
            self.assertTrue(any(e['element'] == 'dataset' and e['who'] == 'Ann' and 'import v2' in e['text'] for e in log))
            status, body = self.confirm(bob, '状态码')
            self.assertEqual(status, 409)   # as it was it cannot be confirmed again: meanings are put forward anew
            # Bob puts the new meanings forward; Ann (who proposed the type) confirms them but cannot confirm the type, Bob can
            new = [{'value': '0', 'label': ''}, {'value': '1', 'label': '已交付'}, {'value': '2', 'label': '生产中'}, {'value': '3', 'label': '已取消'}]
            self.assertEqual(bob.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': new})[1], {'changed': True})
            meaning = self.meanings(self.detail(ann))
            self.assertEqual((meaning['state'], meaning['proposed_by'], [(v['value'], v['label']) for v in meaning['values']]),
                             ('checked', 'Bob', [('1', '已交付'), ('2', '生产中'), ('3', '已取消')]))
            self.assertEqual(self.confirm(bob, '状态码')[0], 403)
            self.assertEqual(self.confirm(ann, '状态码')[0], 200)
            self.assertEqual(self.confirm(ann)[0], 403)   # Ann proposed the type
            self.assertEqual(self.confirm(bob)[0], 200)
            self.assertEqual(self.detail(bob)['state'], 'confirmed')

    def test_a_confirmation_names_the_version_the_reviewer_saw(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            team['ann'].post('/api/workspace/types', ORDER)
            seen = self.detail(team['bob'])['version']
            team['ann'].post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': seen, 'name': '客户订单'})
            status, body = team['bob'].post('/api/workspace/types/confirm', {'id': 'order', 'version': seen, 'seen': {}})
            self.assertEqual(status, 409, body)
            self.assertEqual(team['bob'].post('/api/workspace/types/confirm', {'id': 'order'})[0], 409)   # no version at all
            status, body = team['ann'].post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': seen})
            self.assertEqual(status, 409)   # a save carries the revision it was based on

    def test_a_confirmation_is_about_the_data_the_reviewer_saw_not_only_the_row_version(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)
            old = self.meanings(self.detail(bob))
            self.assertEqual([v['rows'] for v in old['values']], [96, 48, 16])   # Bob reads the codes 0, 1, 2
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(lambda r, i: {**r, '状态码': '3'} if i < 5 else r)]})[0], 200)   # five rows get a code 3
            status, body = bob.post('/api/workspace/types/confirm', {'id': 'order', 'column': '状态码', 'version': old['version'], 'seen': old['seen']})
            self.assertEqual(status, 409)
            self.assertIn('数据在你看过之后变了', body['error'])
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order', 'column': '状态码', 'version': old['version']})[0], 400)   # no `seen` at all
            self.assertEqual(self.confirm(bob, '状态码')[0], 200)   # having looked again, Bob can
            type_seen = self.detail(bob)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(lambda r, i: {**r, '金额': '1'})]})[0], 200)   # another version, same codes
            status, body = bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': type_seen['version'], 'seen': type_seen['seen']})
            self.assertEqual(status, 409)
            self.assertIn('第 3 版', body['error'])
            self.assertEqual(self.confirm(bob)[0], 200)

    def test_changing_confirmed_meanings_takes_the_type_back_and_a_type_waits_for_its_meanings(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.confirm_all(ann, bob)
            relabelled = [{'value': '0', 'label': '已取消'}]
            self.assertEqual(bob.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': relabelled})[1], {'changed': True})
            detail = self.detail(ann)
            self.assertEqual((self.meanings(detail)['state'], detail['state']), ('checked', 'needs_look'))   # the type was confirmed on the old meanings
            self.assertIn('“状态码”的含义改了', detail['reason'])
            status, body = self.confirm(bob)
            self.assertEqual(status, 409)   # not while its meanings are not confirmed, and it says which
            self.assertIn('“状态码”的含义还没有确认', body['error'])
            self.assertEqual(self.confirm(ann, '状态码')[0], 200)
            self.assertEqual(self.confirm(bob)[0], 200)
            detail = self.detail(bob)   # the same through a save of the type
            self.assertEqual(ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': detail['version'], 'enums': {'状态码': [{'value': '1', 'label': '待发货'}]}})[0], 200)
            self.assertEqual((self.detail(bob)['state'], self.meanings(self.detail(bob))['state']), ('needs_look', 'checked'))

    def test_taking_the_code_flag_off_or_pointing_the_type_at_another_dataset_takes_the_meanings_away(self):
        with self.service() as (base, out):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.confirm_all(ann, bob)
            plain = [{'column': '订单号'}, {'column': '金额'}, {'column': '状态码'}]
            status, body = bob.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': self.detail(bob)['version'], 'properties': plain, 'enums': {}})
            self.assertEqual((status, body['state'], body['reset']), (200, 'checked', ['属性的类型']))
            self.assertIsNone(next(p for p in self.detail(bob)['properties'] if p['column'] == '状态码')['meanings'])
            conn = sqlite3.connect(out / 'workspace.sqlite')
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM element_state WHERE element_id LIKE 'enum:%'").fetchone(), (0,))
            self.assertEqual(conn.execute("SELECT change FROM log WHERE element_id = 'objtype:order' AND change = 'meanings_retired'").fetchall(), [('meanings_retired',)])
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)   # a code shift no longer concerns this type
            self.assertEqual(self.detail(bob)['state'], 'checked')
            # the code column again, with meanings, and then the type is pointed at a copy of the table
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(lambda r, i: r, name='订单副本')]})[0], 200)
            self.assertEqual(bob.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': self.detail(bob)['version'], 'enums': {'状态码': [{'value': '1', 'label': '生产中'}]}})[0], 200)
            self.assertEqual(self.meanings(self.detail(bob))['state'], 'checked')
            status, body = ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': self.detail(ann)['version'], 'dataset': '订单副本', 'enums': {}})
            self.assertEqual((status, body['reset']), (200, ['来源数据集']))
            self.assertEqual(self.meanings(self.detail(ann))['state'], None)   # the meanings were of the other dataset's values
            self.assertEqual(ann.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': [{'value': '1', 'label': '生产中'}]})[1], {'changed': True})
            content = json.loads(conn.execute("SELECT content_json FROM element_state WHERE element_id = 'enum:order:状态码'").fetchone()[0])
            self.assertEqual(content['dataset'], '订单副本')
            conn.close()

    def test_when_the_recheck_cannot_run_what_reads_the_dataset_is_flagged_and_the_upload_says_so(self):
        from unittest import mock
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.confirm_all(ann, bob)
            with mock.patch('ontology_poc_generator.object_types.recheck_dependents', side_effect=RuntimeError('boom')):
                status, body = ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})
            self.assertEqual((status, body['results'][0]['version'], body['results'][0]['recheck_error']), (200, 2, 'boom'))
            detail = self.detail(bob)
            self.assertEqual((detail['state'], self.meanings(detail)['state']), ('needs_look', 'needs_look'))
            self.assertIn('重新检查出了错（boom）', self.meanings(detail)['reason'])

    def test_a_column_a_new_version_dropped_is_a_conflict_with_the_reason_and_not_its_own_name_as_a_value(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.confirm_all(ann, bob)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(drop=('金额',))]})[0], 200)
            status, body = bob.get('/api/workspace/types/order/objects')
            self.assertEqual(status, 409)
            self.assertIn('没有这些列了：金额', body['error'])
            self.assertIn('金额', self.detail(bob)['reason'])   # and the type is waiting for another look, with the same reason

    def test_a_write_to_an_element_that_moved_since_it_was_read_is_refused_and_writes_nothing(self):
        from ontology_poc_generator.object_types import TypeRefused, element_row, write_elements
        with self.service() as (base, out):
            team = self.team(base, 'ann')
            self.assertEqual(team['ann'].post('/api/workspace/types', ORDER)[0], 200)
            conn = open_workspace(out / 'workspace.sqlite')
            row = element_row(conn, 'objtype:order')
            with self.assertRaises(TypeRefused) as caught:
                write_elements(conn, [('objtype:order', 'rejected', None, 'Bob', json.loads(row['content_json']), None, None)], {}, {'objtype:order': row['version'] - 1})
            self.assertEqual(caught.exception.status, 409)
            self.assertEqual(element_row(conn, 'objtype:order')['state'], 'checked')
            conn.close()

    def test_a_key_that_repeats_is_refused_and_the_repeated_values_are_named(self):
        with self.service() as (base, _):
            ann = self.team(base, 'ann')['ann']
            customer = {'english_name': 'customer', 'name': '客户', 'dataset': '客户', 'key': ['客户编号']}
            status, body = ann.post('/api/workspace/types', customer)
            self.assertEqual(status, 400)
            self.assertIn('KH012', body['error'])
            self.assertEqual((body['key_check']['rows_checked'], body['key_check']['violations'], body['key_check']['repeated']), (31, 1, [{'key': ['KH012'], 'rows': 2}]))
            self.assertEqual(ann.get('/api/workspace/types')[1], {'types': []})   # nothing was saved
            status, body = ann.post('/api/workspace/types/key-check', {'dataset': '订单承诺', 'key': ['订单号']})
            self.assertEqual((status, body['key_check']['violations']), (400, 61))
            status, body = ann.post('/api/workspace/types/key-check', {'dataset': '订单承诺', 'key': ['订单号', '承诺版本']})   # a composite key is fine
            self.assertEqual((status, body['rows_checked']), (200, 121))

    def test_a_decimal_or_yes_no_key_is_refused_and_a_date_key_warns(self):
        with self.service() as (base, _):
            ann = self.team(base, 'ann')['ann']
            status, body = ann.post('/api/workspace/types/key-check', {'dataset': '交付统计', 'key': ['交付天数P50']})
            self.assertEqual(status, 400)
            self.assertIn('小数', body['error'])
            status, body = ann.post('/api/workspace/types/key-check', {'dataset': '订单', 'key': ['订单号', '下单日期']})
            self.assertEqual(status, 200)
            self.assertEqual(len(body['warnings']), 1)
            self.assertIn('下单日期', body['warnings'][0])

    def test_only_what_a_confirmation_was_about_resets_it(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.confirm_all(ann, bob)
            version = self.detail(bob)['version']
            status, body = bob.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': version, 'name': '客户订单', 'description': '改了说明'})
            self.assertEqual((status, body['state'], body['reset']), (200, 'confirmed', []))   # a name and a description are not what was confirmed
            detail = self.detail(bob)
            self.assertEqual((detail['name'], detail['description'], detail['state'], detail['confirmed_by']), ('客户订单', '改了说明', 'confirmed', 'Bob'))
            log = bob.get('/api/workspace/types/order/log')[1]['log']
            self.assertTrue(any(e['change'] == 'edited' and e['who'] == 'Bob' for e in log))
            properties = [{'column': '订单号'}, {'column': '金额', 'type': 'text'}, {'column': '状态码', 'enum': True}]   # the amount is text now
            status, body = bob.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': detail['version'], 'properties': properties})
            self.assertEqual((status, body['state'], body['reset']), (200, 'checked', ['属性的类型']))
            detail = self.detail(ann)
            self.assertEqual((detail['proposed_by'], detail['can_confirm']), ('Bob', True))   # Bob put it forward again: now Ann may confirm
            self.assertEqual(self.meanings(detail)['state'], 'confirmed')   # the meanings were not touched
            status, body = ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': detail['version'], 'properties': [{'column': '数量', 'type': 'decimal'}, {'column': '状态码', 'enum': True}]})
            self.assertEqual(status, 200)   # an integer column read as decimal fits
            status, body = ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': self.detail(ann)['version'], 'properties': [{'column': '下单日期', 'type': 'integer'}]})
            self.assertEqual(status, 400)   # a date does not fit an integer

    def test_a_code_column_is_an_integer_or_text_never_a_yes_no_and_has_few_values(self):
        with self.service() as (base, _):
            ann = self.team(base, 'ann')['ann']
            for column, kind in (('状态码', 'boolean'), ('订单号', None)):
                status, body = ann.post('/api/workspace/types', {**ORDER, 'properties': [{'column': column, 'enum': True, **({'type': kind} if kind else {})}], 'enums': {}})
                self.assertEqual(status, 400, (column, body))   # 160 order numbers are not a code list; a code is not a boolean
            status, body = ann.post('/api/workspace/types', {**ORDER, 'enums': {'状态码': [{'value': '7', 'label': '没有这个值'}]}})
            self.assertEqual((status, '没有取值 7' in body['error']), (400, True))

    def test_a_viewer_sees_only_confirmed_types_and_cannot_write(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob', 'vic', roles={'vic': 'viewer'})
            team['ann'].post('/api/workspace/types', ORDER)
            self.assertEqual(team['vic'].get('/api/workspace/types')[1], {'types': []})
            self.assertEqual(team['vic'].get('/api/workspace/types/order')[0], 404)
            self.assertEqual(team['vic'].post('/api/workspace/types/confirm', {'id': 'order', 'version': 1})[0], 403)
            self.assertEqual(team['vic'].post('/api/workspace/types', ORDER)[0], 403)
            detail = self.detail(team['bob'])
            for column in ('状态码', None):
                self.assertEqual(self.confirm(team['bob'], column)[0], 200)
            self.assertEqual([t['id'] for t in team['vic'].get('/api/workspace/types')[1]['types']], ['order'])
            self.assertEqual(self.detail(team['vic'])['can_confirm'], False)

    def test_a_dataset_that_a_type_reads_cannot_be_deleted_and_says_which(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann')
            team['ann'].post('/api/workspace/types', ORDER)
            status, body = team['ann'].post('/api/workspace/datasets/delete', {'name': '订单'})
            self.assertEqual(status, 409)
            self.assertEqual(body['readers'], [{'kind': '对象类型', 'name': '订单'}])
            page = team['ann'].get('/api/workspace/datasets/' + quote('订单'))[1]
            self.assertEqual(page['readers'], [{'kind': '对象类型', 'name': '订单'}])
            self.assertEqual({d['name']: d['used_by'] for d in team['ann'].get('/api/workspace/datasets')[1]['datasets']}['订单'], 1)

    def test_objects_are_the_rows_of_the_current_version_with_the_meanings_that_are_confirmed(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            ann.post('/api/workspace/types', ORDER)
            objects = ann.get('/api/workspace/types/order/objects')[1]
            self.assertEqual((objects['total'], len(objects['rows']), objects['pages'], objects['dataset_version']), (160, 50, 4, 1))
            self.assertEqual([c['column'] for c in objects['columns']], ['订单号', '金额', '状态码'])
            self.assertEqual((objects['enums']['状态码']['state'], objects['enums']['状态码']['labels']), ('checked', {'0': '已交付', '1': '生产中', '2': '已取消'}))
            self.assertEqual(ann.get('/api/workspace/types/order/objects?page=9')[1]['page'], 4)

    def test_with_one_person_who_can_confirm_the_rule_is_off_and_the_log_marks_a_self_confirmation(self):
        with self.service() as (base, out):
            admin = self.people(base)['admin']
            self.assertEqual(admin.post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
            self.assertEqual(admin.post('/api/workspace/types', ORDER)[0], 200)
            detail = self.detail(admin)
            self.assertEqual((self.meanings(detail)['can_confirm'], detail['can_confirm']), (True, False))
            self.assertEqual(self.confirm(admin, '状态码')[0], 200)
            self.assertEqual(self.detail(admin)['can_confirm'], True)
            self.assertEqual(self.confirm(admin)[0], 200)
            log = admin.get('/api/workspace/types/order/log')[1]['log']
            self.assertEqual([e['self_confirmed'] for e in log if e['element'] == 'type' and e['to'] == 'confirmed'], [True])

    def test_the_model_suggests_only_what_the_purpose_needs_and_every_suggestion_is_a_draft(self):
        reply = {'object_types': [
            {'name': '订单', 'english_name': 'order', 'dataset': '订单', 'key': ['订单号'], 'basis': '一行一张订单，订单号不重复',
             'properties': [{'column': '订单号', 'needed_for': '数订单'}, {'column': '状态码', 'needed_for': '数已取消的'}, {'column': '金额'}]},
            {'name': '客户', 'english_name': 'customer', 'dataset': '客户', 'key': ['客户编号'], 'basis': '一行一个客户', 'properties': []},
            {'name': '库存', 'english_name': 'stock', 'dataset': '库存快照', 'key': ['快照月份', '产品编号'], 'basis': '月份加产品',
             'properties': [{'column': '库存数量', 'needed_for': '看库存'}]}]}
        model = Suggester(reply)
        with self.service(gateway=model) as (base, out):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            status, body = ann.post('/api/workspace/types/suggest', {'datasets': ['订单', '客户', '库存快照'], 'purpose': '数已取消的订单'})
            self.assertEqual(status, 200, body)
            self.assertEqual([p['id'] for p in body['proposed']], ['order', 'stock'])
            self.assertEqual([r['name'] for r in body['rejected']], ['客户'])
            self.assertIn('KH012', body['rejected'][0]['reason'])   # the key checks a person's definition goes through caught the repeated customer
            self.assertEqual((len(model.asked), model.timeouts), (1, [120]))   # one call, which may take up to two minutes
            self.assertIn('状态码', model.asked[0])   # it saw the column names
            self.assertNotIn('DD20260001', model.asked[0])   # and no row
            detail = self.detail(ann)
            self.assertEqual((detail['state'], detail['proposed_by'], detail['model_draft'], detail['can_confirm']), ('proposed', None, True, True))
            self.assertEqual([p['column'] for p in detail['properties']], ['订单号', '状态码'])   # the amount had no reason, the other columns were not asked for
            tasks = ann.get('/api/workspace/tasks')[1]['tasks']
            task = next(t for t in tasks if t['kind'] == 'suggest')
            self.assertEqual((task['state'], task['who'], task['title'], [p['id'] for p in task['proposed']]), ('done', 'Ann', '订单、客户、库存快照', ['order', 'stock']))
            self.assertEqual(team['admin'].get('/api/workspace/tasks')[0], 200)
            from ontology_poc_generator.workspace_tasks import suggest_tasks
            conn = open_workspace(out / 'workspace.sqlite')
            self.assertEqual(suggest_tasks(conn, {'id': 99, 'role': 'viewer'}), [])   # what the checks dropped quotes the data's repeated values: not for a viewer
            conn.close()
            # a draft a person saves is theirs, and checked; another builder confirms
            status, saved = ann.post('/api/workspace/types/update', {'id': 'order', 'version': detail['version'], 'name': '订单', 'english_name': 'order', 'dataset': '订单',
                                                                       'key': ['订单号'], 'properties': [{'column': '订单号'}, {'column': '状态码'}]})
            self.assertEqual((status, saved['state']), (200, 'checked'))
            self.assertEqual(self.detail(ann)['proposed_by'], 'Ann')
            self.assertEqual(self.detail(bob)['can_confirm'], True)

    def test_a_failed_model_request_is_a_failed_task_with_nothing_proposed(self):
        class Down:
            def complete_json(self, **_):
                from ontology_poc_generator.recognition import RecognitionError
                raise RecognitionError('model request failed: timed out')
        with self.service(gateway=Down()) as (base, _):
            ann = self.team(base, 'ann')['ann']
            status, body = ann.post('/api/workspace/types/suggest', {'datasets': ['订单'], 'purpose': 'x'})
            self.assertEqual(status, 502)
            self.assertEqual(ann.get('/api/workspace/types')[1], {'types': []})
            task = next(t for t in ann.get('/api/workspace/tasks')[1]['tasks'] if t['kind'] == 'suggest')
            self.assertEqual(task['state'], 'failed')
            self.assertIn('请稍后重试', task['error'])
        with self.service() as (base, _):   # no model configured
            ann = self.team(base, 'ann')['ann']
            self.assertEqual(ann.post('/api/workspace/types/suggest', {'datasets': ['订单'], 'purpose': 'x'})[0], 503)


    # --- views: a type plus conditions on confirmed meanings and/or "latest per key" ---------------------------------------------------------------------

    def make_view(self, client, view, expect=200):
        status, body = client.post('/api/workspace/types/views', view)
        self.assertEqual(status, expect, body)
        return body

    def view_of(self, client, type_name, name):
        status, body = client.get(f'/api/workspace/types/{type_name}/views')
        self.assertEqual(status, 200, body)
        return next((v for v in body['views'] if v['name'] == name), None)

    def confirm_view(self, client, type_name, name):
        shown = self.view_of(client, type_name, name)
        return client.post('/api/workspace/types/views/confirm', {'id': name, 'version': shown['version'], 'seen': shown['seen']})

    def test_a_view_shows_how_many_rows_it_keeps_and_is_confirmed_by_the_other_builder_then_needs_a_look_when_the_codes_shift(self):
        with self.service() as (base, out):
            team = self.team(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            self.confirm_all(ann, bob)
            kept = sum(1 for r in ORDERS if r['状态码'] != '2')   # counted from the planted rows: the 16 cancelled ones are not in it
            body = self.make_view(ann, VALID)
            self.assertEqual((body['rows'], body['of'], kept), (144, 160, 144))
            mine, theirs = self.view_of(ann, 'order', '有效订单'), self.view_of(bob, 'order', '有效订单')
            self.assertEqual((mine['state'], mine['rows'], mine['of'], mine['proposed_by'], mine['can_confirm'], theirs['can_confirm']), ('checked', 144, 160, 'Ann', False, True))
            self.assertEqual(mine['says'], '订单里只留 状态码 不是「已取消」 的行')
            form = bob.get('/api/workspace/types/order/views')[1]['form']
            self.assertEqual(form['codes'], [{'column': '状态码', 'name': '状态码', 'labels': ['已交付', '已取消', '生产中']}])
            self.assertEqual([c['name'] for c in form['columns'] if c['orderable']], ['数量', '金额', '下单日期', '状态码', '交付天数'])   # numbers and dates; the text columns are not
            self.assertEqual(vera.get('/api/workspace/types/order/views')[1], {'views': [], 'form': None})   # a viewer reads confirmed views only
            self.assertEqual(vera.post('/api/workspace/types/views', {**VALID, 'name': '另一个'})[0], 403)
            # the same person cannot confirm it; a count that is not what the page showed is refused; the right one is taken
            self.assertEqual(self.confirm_view(ann, 'order', '有效订单')[0], 403)
            status, body = bob.post('/api/workspace/types/views/confirm', {'id': '有效订单', 'version': theirs['version'], 'seen': {**theirs['seen'], 'rows': 143}})
            self.assertEqual((status, '和你看到的不一样' in body['error']), (409, True))
            self.assertEqual(self.confirm_view(bob, 'order', '有效订单')[0], 200)
            shown = self.view_of(vera, 'order', '有效订单')
            self.assertEqual((shown['state'], shown['confirmed_by'], shown['confirmed_on'], shown['rows']), ('confirmed', 'Bob', {'订单': 1}, 144))
            conn = sqlite3.connect(out / 'workspace.sqlite')
            self.assertEqual(conn.execute("SELECT confirmed_by, proposed_by, dataset_versions_json FROM confirmation WHERE element_id = 'objview:有效订单'").fetchall(), [('Bob', 'Ann', '{"订单": 1}')])
            self.assertEqual(set(conn.execute("SELECT depends_on FROM element_dep WHERE element_id = 'objview:有效订单'").fetchall()),
                             {('objtype:order',), ('dataset:订单',), ('enum:order:状态码',)})
            conn.close()
            # what cannot be a view
            self.assertIn('不是“状态码”已写的含义', self.make_view(ann, {**VALID, 'name': 'x', 'filters': [{'column': '状态码', 'op': 'is_not', 'label': '作废'}]}, 400)['error'])
            self.assertIn('不是“订单”的代码列', self.make_view(ann, {**VALID, 'name': 'x', 'filters': [{'column': '金额', 'op': 'is', 'label': '1'}]}, 400)['error'])
            self.assertIn('至少一个条件', self.make_view(ann, {'name': 'x', 'type': 'order'}, 400)['error'])
            self.assertIn('“订单”', self.make_view(ann, {**VALID, 'name': '订单'}, 409)['error'])   # a question names a type or a view, not both
            self.assertEqual(self.make_view(ann, {**VALID, 'name': '有效订单'}, 409)['error'], '已经有叫“有效订单”的视图')
            self.assertEqual(self.make_view(ann, {**VALID, 'type': 'nothing'}, 404)['error'], '没有这个对象类型')
            # a new version with every code one higher: the meaning needs a look, the type under it, and so the view, with the reason
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            moved = self.view_of(bob, 'order', '有效订单')
            self.assertEqual(moved['state'], 'needs_look')
            self.assertIn('需要再看', moved['reason'])
            self.assertEqual((moved['confirmed_by'], moved['can_confirm']), ('Bob', False))   # not until the type and the meaning are looked at again
            self.assertEqual(vera.get('/api/workspace/types/order/views')[0], 404)   # the type is not confirmed now, so a viewer is not shown it, nor what stands on it
            queue = bob.get('/api/workspace/queue')[1]['items']
            self.assertIn(('view', 'objview:有效订单', 'needs_look'), [(i['kind'], i['element'], i['state']) for i in queue])
            log = bob.get('/api/workspace/types/order/log')[1]['log']
            self.assertTrue(any(e['element'] == 'view' and e['to'] == 'needs_look' and e['who'] == 'system' for e in log))
            new = [{'value': '0', 'label': ''}, {'value': '1', 'label': '已交付'}, {'value': '2', 'label': '生产中'}, {'value': '3', 'label': '已取消'}]
            self.assertEqual(bob.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': new})[1], {'changed': True})
            self.assertEqual(self.confirm(ann, '状态码')[0], 200)
            self.assertEqual(self.view_of(bob, 'order', '有效订单')['waiting_on'][0]['name'], '订单')   # the type is not confirmed yet
            self.assertEqual(self.confirm(bob)[0], 200)
            back = self.view_of(bob, 'order', '有效订单')
            self.assertEqual((back['state'], back['can_confirm'], back['rows'], back['dataset_version']), ('needs_look', True, 144, 2))
            self.assertEqual(self.confirm_view(bob, 'order', '有效订单')[0], 200)
            self.assertEqual(self.view_of(bob, 'order', '有效订单')['confirmed_on'], {'订单': 2})

    def test_new_rows_that_change_how_many_a_view_keeps_send_it_back_without_touching_the_type(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.confirm_all(ann, bob)
            self.make_view(ann, VALID)
            self.assertEqual(self.confirm_view(bob, 'order', '有效订单')[0], 200)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(lambda r, i: {**r, '状态码': '2'} if i == 0 else r)]})[0], 200)   # the first order is cancelled now
            self.assertEqual(self.detail(bob)['state'], 'confirmed')   # no code is new, no key repeats: the type stands
            moved = self.view_of(bob, 'order', '有效订单')
            self.assertEqual((moved['state'], moved['rows'], moved['of']), ('needs_look', 143, 160))
            self.assertIn('确认时 144 / 160 行，现在 143 / 160 行', moved['reason'])
            self.assertEqual(self.confirm_view(bob, 'order', '有效订单')[0], 200)   # looked at again: 143 is what the page shows

    def test_a_new_version_that_swaps_which_rows_a_view_keeps_sends_it_back_though_the_count_stays_the_same(self):
        first, cancelled = 0, next(i for i, r in enumerate(ORDERS) if r['状态码'] == '2')
        self.assertEqual((ORDERS[first]['状态码'], ORDERS[cancelled]['状态码']), ('0', '2'))
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.confirm_all(ann, bob)
            self.make_view(ann, VALID)
            self.assertEqual(self.confirm_view(bob, 'order', '有效订单')[0], 200)
            swap = lambda r, i: {**r, '状态码': '2'} if i == first else {**r, '状态码': '0'} if i == cancelled else r   # one cancelled for one delivered
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(swap)]})[0], 200)
            moved = self.view_of(bob, 'order', '有效订单')
            self.assertEqual((moved['state'], moved['rows'], moved['of']), ('needs_look', 144, 160))
            self.assertIn('已经不是确认时的那些行', moved['reason'])

    def test_a_latest_view_keeps_one_row_per_key_and_refuses_a_column_that_cannot_be_put_in_order(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            for t in (STOCK, COMMIT):
                self.assertEqual(ann.post('/api/workspace/types', t)[0], 200)
                self.assertEqual(self.confirm(bob, None, t['english_name'])[0], 200)
            snapshots = planted.planted_bundle()['sources']['库存快照']['records']
            latest = {}
            for r in snapshots:   # by hand: per product the greatest month (months are written year first)
                if r['产品编号'] not in latest or r['快照月份'] > latest[r['产品编号']]['快照月份']:
                    latest[r['产品编号']] = r
            body = self.make_view(ann, LATEST_STOCK)
            self.assertEqual((body['rows'], body['of'], len(latest), len(snapshots)), (12, 72, 12, 72))
            commitments = planted.planted_bundle()['sources']['订单承诺']['records']
            newest = {}
            for r in commitments:
                if r['订单号'] not in newest or int(r['承诺版本']) > int(newest[r['订单号']]['承诺版本']):
                    newest[r['订单号']] = r
            body = self.make_view(ann, LATEST_COMMIT)
            self.assertEqual((body['rows'], body['of'], len(newest), len(commitments)), (60, 121, 60, 121))
            self.assertIn('排不出先后', self.make_view(ann, {**LATEST_STOCK, 'name': 'x', 'latest': {'key': ['快照月份'], 'order': '产品编号'}}, 400)['error'])
            self.assertIn('不能是编号列', self.make_view(ann, {**LATEST_STOCK, 'name': 'x', 'latest': {'key': ['快照月份'], 'order': '快照月份'}}, 400)['error'])
            self.assertIn('编号要选', self.make_view(ann, {**LATEST_STOCK, 'name': 'x', 'latest': {'key': ['没有这列'], 'order': '快照月份'}}, 400)['error'])
            self.assertEqual(self.confirm_view(bob, 'stock', '最新快照')[0], 200)
            self.assertEqual(self.view_of(bob, 'stock', '最新快照')['says'], '库存快照里每个「产品编号」只留「快照月份」最新的一行')

    def test_which_rows_a_definition_keeps_latest_first_then_the_conditions_later_row_wins_a_tie_and_a_row_without_a_key_stays(self):
        records = [{'k': 'a', 'v': '1', 's': '1'}, {'k': 'a', 'v': '3', 's': '2'}, {'k': 'b', 'v': '2', 's': '1'}, {'k': 'b', 'v': '2', 's': '2'},
                   {'k': '', 'v': '1', 's': '1'}, {'k': 'c', 'v': '', 's': '1'}, {'k': 'c', 'v': '5', 's': '1'}]
        kinds, labels = {'k': 'text', 'v': 'integer', 's': 'integer'}, {'s': {'1': '开', '2': '关'}}
        latest = {'key': ['k'], 'order': 'v'}
        self.assertEqual(kept_positions(records, kinds, labels, {'filters': [], 'latest': latest}), [2, 4, 5, 7])   # a: v=3; b: tie, the later; no key: stays; c: the filled one
        self.assertEqual(kept_positions(records, kinds, labels, {'filters': [{'column': 's', 'op': 'is', 'label': '开'}], 'latest': latest}), [5, 7])   # a's latest is 关: it is gone, not its earlier row
        self.assertEqual(kept_positions(records, kinds, labels, {'filters': [{'column': 's', 'op': 'is_not', 'label': '开'}], 'latest': None}), [2, 4])

    def test_a_views_visibility_follows_its_type_and_the_queue_lists_it_for_the_builder_who_can_confirm(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            self.confirm_all(ann, bob)
            self.make_view(ann, VALID)
            item = next(i for i in bob.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'view')
            self.assertEqual((item['title'], item['can_confirm']), ('有效订单（订单的视图）', True))
            self.assertIn('视图留下 144 行', ' '.join(l['text'] for l in item['lines']))
            self.assertEqual(bob.post('/api/workspace/queue/confirm', {'element': item['element'], 'version': item['version'], 'seen': item['seen']})[0], 200)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': [3]})[0], 200)   # only Bob
            self.assertEqual(ann.get('/api/workspace/types/order/views')[0], 404)
            self.assertEqual(ann.post('/api/workspace/types/views/confirm', {'id': '有效订单', 'version': 1, 'seen': {}})[0], 404)
            self.assertEqual(self.view_of(bob, 'order', '有效订单')['state'], 'confirmed')


ORDER_WITH_CUSTOMER = {**ORDER, 'properties': [*ORDER['properties'], {'column': '客户编号'}]}
STATUS_ACTION = {'name': '改订单状态', 'type': 'order', 'properties': ['状态码'], 'condition': {'column': '状态码', 'value': '1'}, 'description': '生产中的订单改成已交付'}
ACTION_URL = '/api/workspace/actions/' + quote('改订单状态')
DATASET_URL = '/api/workspace/datasets/' + quote('订单')
IN_PRODUCTION = next(r for r in ORDERS if r['状态码'] == '1')   # the first order still in production
STATUS_COUNTS = {k: sum(1 for r in ORDERS if r['状态码'] == k) for k in '012'}   # 96 delivered, 48 in production, 16 cancelled, counted from the records


class ActionTests(SigningTestCase):
    """One edit action with a second person's approval, and the rows a row rule keeps from someone, on the planted tables."""

    def setUp(self):
        super().setUp()
        self.order = ORDER_WITH_CUSTOMER

    def team(self, base):
        team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        self.assertEqual(team['ann'].post('/api/workspace/types', self.order)[0], 200)
        for column in ('状态码', None):
            shown = team['bob'].get('/api/workspace/types/order')[1]
            shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
            status, body = team['bob'].post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})
            self.assertEqual(status, 200, body)
        return team

    def confirmed_action(self, team, payload=STATUS_ACTION):
        self.assertEqual(team['ann'].post('/api/workspace/actions', payload)[0], 200)
        shown = team['bob'].get(f'/api/workspace/actions/{quote(payload["name"])}')[1]
        status, body = team['bob'].post('/api/workspace/actions/confirm', {'id': payload['name'], 'version': shown['version']})
        self.assertEqual(status, 200, body)

    def submit(self, client, order=IN_PRODUCTION, to='0', action='改订单状态', **more):
        return client.post('/api/workspace/actions/submit', {'action': action, 'key': {'订单号': order['订单号']}, 'params': {'状态码': to}, 'reason': '客户已签收', **more})

    def log(self, client, name='改订单状态'):
        return client.get(f'/api/workspace/actions/{quote(name)}')[1]['log']

    def status_counts(self, client):
        column = next(c for c in client.get(DATASET_URL)[1]['columns'] if c['name'] == '状态码')
        return column['values']

    def test_ann_defines_bob_confirms_ann_submits_and_cannot_approve_bob_approves_and_the_order_has_a_new_version_with_the_action_on_it(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            self.assertEqual(STATUS_COUNTS, {'0': 96, '1': 48, '2': 16})
            self.assertEqual(ann.post('/api/workspace/actions', STATUS_ACTION)[0], 200)
            # not confirmed yet: nobody can run it, and the refused attempt is on the log with who and why
            status, body = self.submit(ann)
            self.assertEqual(status, 409)
            self.assertIn('还没有另一位确认', body['error'])
            shown = ann.get(ACTION_URL)[1]
            self.assertEqual((shown['state'], shown['says']), ('checked', '改 订单 的「状态码」；只在 状态码 是「生产中」时可以提交'))
            self.assertEqual([{'value': o['value'], 'label': o['label']} for o in shown['parameters'][0]['options']], [{'value': v['value'], 'label': v['label']} for v in MEANINGS])
            self.assertFalse(shown['can_confirm'])   # the proposer
            self.assertEqual(ann.post('/api/workspace/actions/confirm', {'id': '改订单状态', 'version': shown['version']})[0], 403)
            self.assertEqual(self.submit(vera)[0], 403)   # a viewer runs nothing
            status, body = bob.post('/api/workspace/actions/confirm', {'id': '改订单状态', 'version': shown['version']})
            self.assertEqual((status, body), (200, {'state': 'confirmed'}))
            # a value that is not one of the meanings, and an order that is not in production: refused naming the field and value
            status, body = self.submit(ann, to='7')
            self.assertEqual(status, 400)
            self.assertIn('“状态码”的值“7”不是它的含义里的取值', body['error'])
            cancelled = next(r for r in ORDERS if r['状态码'] == '2')
            status, body = self.submit(ann, order=cancelled)
            self.assertEqual(status, 409)
            self.assertIn(f'{cancelled["订单号"]}', body['error'])
            self.assertIn('现在是“已取消”', body['error'])
            self.assertEqual(self.submit(ann, to='1')[1]['error'].split('：')[0], '订单 ' + IN_PRODUCTION['订单号'] + ' 已经是这些值了，没有要改的')
            # the real one
            status, body = self.submit(ann)
            self.assertEqual((status, body['state']), (200, 'pending'))
            record = body['record']
            self.assertEqual(self.status_counts(ann), STATUS_COUNTS)   # nothing written by a submit
            self.assertEqual(ann.get(DATASET_URL)[1]['version'], 1)
            # the card is in Bob's queue and not Ann's to approve
            card = next(i for i in bob.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'approval')
            self.assertEqual((card['record'], card['can_confirm'], card['state']), (record, True, 'pending'))
            self.assertIn('Ann 想把 订单 ' + IN_PRODUCTION['订单号'], card['lines'][0]['text'])
            own = next(i for i in ann.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'approval')
            self.assertFalse(own['can_confirm'])
            status, body = ann.post('/api/workspace/actions/decide', {'id': record, 'decision': 'approve'})
            self.assertEqual(status, 403)
            self.assertEqual(ann.get(DATASET_URL)[1]['version'], 1)
            # Bob approves: a new version of 订单 by key, the action on it, the order now delivered, the log naming all three people
            status, body = bob.post('/api/workspace/actions/decide', {'id': record, 'decision': 'approve', 'note': '收到签收单'})
            self.assertEqual((status, body['state'], body['version']), (200, 'approved', 2), body)
            version = ann.get(DATASET_URL)[1]['versions'][0]
            self.assertEqual((version['version'], version['mode'], version['origin'], version['who'], version['changed'], version['added']), (2, 'update_by_key', 'action:改订单状态', 'Bob', 1, 0))
            self.assertEqual(version['action'], {'id': '改订单状态', 'record': record, 'submitted_by': 'Ann', 'approved_by': 'Bob'})
            self.assertEqual(self.status_counts(ann), {'0': STATUS_COUNTS['0'] + 1, '1': STATUS_COUNTS['1'] - 1, '2': STATUS_COUNTS['2']})
            texts = [(e['who'], e['change'], e['text']) for e in self.log(ann)]
            self.assertEqual([t[:2] for t in texts if t[1].startswith('action_')][::-1],
                             [('Ann', 'action_refused'), ('Ann', 'action_refused'), ('Ann', 'action_refused'), ('Ann', 'action_refused'), ('Ann', 'action_submitted'), ('Ann', 'action_refused'), ('Bob', 'action_approved')])
            approved = next(t for t in texts if t[1] == 'action_approved')[2]
            self.assertIn('Bob 批准了', approved)
            self.assertIn('Ann 提交', approved)
            self.assertIn('第 2 版', approved)
            self.assertTrue(any('还没有另一位确认' in (t[2] or '') for t in texts))
            self.assertEqual(next(r for r in ann.get(ACTION_URL)[1]['records'])['state'], 'approved')
            # the same record cannot be approved twice
            self.assertEqual(bob.post('/api/workspace/actions/decide', {'id': record, 'decision': 'approve'})[0], 409)
            # the type's own log tab carries it too
            self.assertTrue(any(e['change'] == 'action_approved' for e in ann.get('/api/workspace/types/order/log')[1]['log']))

    def test_a_submit_on_a_row_that_changed_before_approval_goes_to_needs_look_and_writes_nothing(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.confirmed_action(team)
            record = self.submit(ann)[1]['record']
            # someone else's upload moves this very order (update by key) before Bob looks
            moved = orders_upload(lambda r, i: {**r, '状态码': '2'} if r['订单号'] == IN_PRODUCTION['订单号'] else r, target='订单', mode='update_by_key', key_columns=['订单号'])
            status, body = ann.post('/api/workspace/datasets/upload', {'files': [moved]})
            self.assertEqual(status, 200, body)
            self.assertEqual(ann.get(DATASET_URL)[1]['version'], 2)
            card = next(i for i in bob.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'approval')
            self.assertIn('现在是第 2 版', ' '.join(l['text'] for l in card['lines']))   # the card says so before he decides
            status, body = bob.post('/api/workspace/actions/decide', {'id': record, 'decision': 'approve'})
            self.assertEqual((status, body['state']), (200, 'needs_look'))
            self.assertIn('数据在提交后变了', body['why'])
            self.assertIn('提交时是“生产中”，现在是“已取消”', body['why'])
            self.assertEqual(ann.get(DATASET_URL)[1]['version'], 2)   # nothing written
            self.assertEqual(self.status_counts(ann), {'0': STATUS_COUNTS['0'], '1': STATUS_COUNTS['1'] - 1, '2': STATUS_COUNTS['2'] + 1})
            shown = ann.get(ACTION_URL)[1]['records'][0]
            self.assertEqual((shown['state'], shown['can_withdraw']), ('needs_look', True))
            self.assertEqual(bob.post('/api/workspace/actions/decide', {'id': record, 'decision': 'approve'})[0], 409)   # it cannot be approved as it was
            self.assertEqual(ann.post('/api/workspace/actions/withdraw', {'id': record})[1], {'state': 'withdrawn'})
            self.assertEqual(bob.post('/api/workspace/actions/withdraw', {'id': record})[0], 403)
            self.assertIn('action_needs_look', [e['change'] for e in self.log(ann)])

    def test_a_pending_record_ends_rejected_withdrawn_or_expired_and_is_kept(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.confirmed_action(team)
            first = self.submit(ann)[1]['record']
            status, body = bob.post('/api/workspace/actions/decide', {'id': first, 'decision': 'reject', 'note': '还没签收'})
            self.assertEqual((status, body['state']), (200, 'rejected'))
            second = self.submit(ann)[1]['record']
            self.assertEqual(ann.post('/api/workspace/actions/withdraw', {'id': second})[1], {'state': 'withdrawn'})
            third = self.submit(ann)[1]['record']
            conn = self.db(out)
            conn.execute("UPDATE action_record SET submitted_at = '2026-01-01T00:00:00+00:00' WHERE id = ?", (third,))
            conn.commit()
            conn.close()
            self.assertEqual([r['state'] for r in ann.get(ACTION_URL)[1]['records']], ['expired', 'withdrawn', 'rejected'])
            self.assertEqual(bob.post('/api/workspace/actions/decide', {'id': third, 'decision': 'approve'})[0], 409)
            conn = self.db(out)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM action_record').fetchone()[0], 3)   # none deleted
            conn.close()
            self.assertEqual(ann.get(DATASET_URL)[1]['version'], 1)

    @staticmethod
    def user_id(admin, username):
        return next(u['id'] for u in admin.get('/api/users')[1]['users'] if u['username'] == username)

    def rule(self, admin, *usernames, value='KH001'):
        return admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': value, 'user_ids': [self.user_id(admin, u) for u in usernames]}] if usernames else []})

    def test_an_action_that_writes_a_property_a_row_rule_reads_is_refused_in_both_orders_and_a_changed_meaning_sends_the_action_to_needs_look(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            customer_action = {'name': '改订单客户', 'type': 'order', 'properties': ['客户编号']}
            self.assertEqual(self.rule(admin, 'vera')[0], 200)
            status, body = ann.post('/api/workspace/actions', customer_action)
            self.assertEqual(status, 409)
            self.assertIn('行规则用到“客户编号”', body['error'])
            self.assertEqual(self.rule(admin)[0], 200)   # the rule taken away
            self.assertEqual(ann.post('/api/workspace/actions', customer_action)[0], 200)
            status, body = self.rule(admin, 'vera')
            self.assertEqual(status, 409)
            self.assertIn('改订单客户', body['error'])
            # the meanings it uses change: the action needs another look at once, and cannot be run until it is confirmed again
            self.confirmed_action(team)
            changed = ann.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': [{'value': '1', 'label': '制造中'}]})
            self.assertEqual(changed[0], 200, changed)
            shown = ann.get(ACTION_URL)[1]
            self.assertEqual(shown['state'], 'needs_look')
            self.assertIn('需要再看', shown['reason'])
            status, body = self.submit(ann)
            self.assertEqual(status, 409)
            self.assertIn('需要再看', body['error'])

    def test_a_row_rule_limits_the_objects_tab_the_dataset_and_a_submit_to_the_rows_the_rule_keeps_and_an_upload_over_an_action_write_is_warned(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            self.confirmed_action(team)
            kh001 = [r for r in ORDERS if r['客户编号'] == 'KH001']
            self.assertEqual(len(kh001), 5)
            self.assertEqual(vera.get('/api/workspace/types/order/objects')[1]['total'], 160)   # no rule yet
            status, body = self.rule(admin, 'vera')
            self.assertEqual(status, 200, body)
            self.assertEqual(ann.post('/api/workspace/row-rules', {'type': 'order', 'rules': []})[0], 403)   # the admin's
            objects = vera.get('/api/workspace/types/order/objects')[1]
            self.assertEqual((objects['total'], objects['rows_limited']), (5, True))
            self.assertEqual({r[3] for r in objects['rows']}, {'KH001'})
            self.assertEqual(vera.get('/api/workspace/types/order')[1]['rows'], 5)
            self.assertEqual(next(t for t in vera.get('/api/workspace/types')[1]['types'] if t['id'] == 'order')['rows'], 5)
            self.assertEqual(admin.get('/api/workspace/types/order/objects')[1]['total'], 160)   # admins see all
            # a builder no rule names sees no row, and the dataset under the rule is the admins' (no way round through its own page)
            self.assertEqual(ann.get('/api/workspace/types/order/objects')[1]['total'], 0)
            self.assertEqual(ann.get(DATASET_URL)[0], 404)
            self.assertEqual(ann.get(DATASET_URL + '?format=csv')[0], 404)
            self.assertNotIn('订单', [d['name'] for d in ann.get('/api/workspace/datasets')[1]['datasets']])
            # a submit on an order the person cannot read is "no such object", and the attempt is logged
            status, body = self.submit(ann)
            self.assertEqual((status, body['error']), (404, '没有这个对象，或者你看不到它'))
            self.assertEqual(self.log(ann)[0]['change'], 'action_refused')
            # Ann is named by a rule, Bob is not: Ann can submit an order the rule keeps; Bob is not shown the record and cannot approve it
            self.assertEqual(self.rule(admin, 'vera', 'ann')[0], 200)
            in_rule = next(r for r in kh001 if r['状态码'] == '1')
            record = self.submit(ann, order=in_rule)[1]['record']
            self.assertEqual([i['record'] for i in bob.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'approval'], [])
            status, body = bob.post('/api/workspace/actions/decide', {'id': record, 'decision': 'approve'})
            self.assertEqual((status, body['error']), (404, '没有这个对象，或者你看不到它'))
            self.assertEqual(self.rule(admin)[0], 200)   # the rule is taken away: Bob can read the order and approves
            self.assertEqual(bob.post('/api/workspace/actions/decide', {'id': record, 'decision': 'approve'})[1]['state'], 'approved')
            # an upload by key that would put the order back is warned about, naming the order, the column, the action and the approver; and is not blocked
            back = orders_upload(target='订单', mode='update_by_key', key_columns=['订单号'])   # the planted file: that order is in production again
            status, body = ann.post('/api/workspace/datasets/upload', {'files': [back]})
            self.assertEqual(status, 200, body)
            self.assertEqual(body['results'][0]['overwrites_action_rows'],
                             [{'key': in_rule['订单号'], 'columns': ['状态码'], 'removed': False, 'action': '改订单状态', 'record': record, 'approved_by': 'Bob'}])
            self.assertEqual(body['results'][0]['version'], 3)
            status, body = ann.post('/api/workspace/datasets/upload', {'files': [back]})
            self.assertEqual((status, body['results'][0]['overwrites_action_rows']), (200, []))   # the same file again changes nothing


class OlderFileTests(unittest.TestCase):
    def test_a_workspace_file_made_before_needs_look_existed_takes_it_and_keeps_its_rows(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'workspace.sqlite'
            old = sqlite3.connect(path)
            old.executescript("""
                CREATE TABLE element_state (
                    element_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL CHECK (state IN ('proposed', 'checked', 'confirmed', 'rejected')),
                    evidence_ref TEXT, confirmed_by TEXT, confirmed_at TEXT, version INTEGER NOT NULL, content_json TEXT, anchors_json TEXT);
                INSERT INTO element_state VALUES ('view:k:v', 'confirmed', NULL, '王工', '2026-10-01T00:00:00+00:00', 3, '{"a": 1}', NULL);""")
            old.commit()
            old.close()
            conn = open_workspace(path)
            conn.execute("UPDATE element_state SET state = 'needs_look', reason = 'x' WHERE element_id = 'view:k:v'")
            self.assertEqual(conn.execute('SELECT state, confirmed_by, version, content_json, reason FROM element_state').fetchall(), [('needs_look', '王工', 3, '{"a": 1}', 'x')])
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE element_state SET state = 'somewhere'")
            conn.close()


if __name__ == '__main__':
    unittest.main()
